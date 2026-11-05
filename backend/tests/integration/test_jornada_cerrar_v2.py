"""Change 24, tarea 9.1: `JORNADA_CERRAR` v2 con el remanente por el bus contra PostgreSQL real
(spec `stock/rendicion-de-jornada`, requisito "El cierre puede devolver el remanente", y spec
`stock/toma-de-ubicacion`, "La devolución del cierre sale del vehículo tomado"; `design.md` D3,
D6).

Se procesa por `sync_service.procesar_comando` resolviendo el handler `(tipo, versión)` como lo
hacen el lote y la ruta. La cobertura por HTTP es de `test_jornadas_api.py`.

Reglas citadas: RUT-08, STK-07, STK-09, INV-01, INV-06, INV-16, SEG-06, TR-06.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

from app.commands import registro
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.stock import (
    jornadas_commands,  # noqa: F401  (registra JORNADA_CERRAR v1)
    rendicion_commands,  # noqa: F401  (registra JORNADA_CERRAR v2)
)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    LineasInvalidasError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    UbicacionConTomaError,
    UbicacionesIgualesError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import Jornada, StockMovimiento, Transferencia
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DIA = datetime(2026, 11, 4, tzinfo=UTC)
CARGA = DIA + timedelta(hours=7)
APERTURA = DIA + timedelta(hours=8)
CIERRE = DIA + timedelta(hours=19)
CERRAR = "JORNADA_CERRAR"

VENDEDOR = frozenset({"ABRIR_JORNADA"})
SUPERVISORA = frozenset({"RENDIR_JORNADA", "TRANSFERIR_STOCK"})
SIN_TRANSFERIR = frozenset({"RENDIR_JORNADA"})
CON_NEGATIVO = frozenset({"RENDIR_JORNADA", "TRANSFERIR_STOCK", "PERMITIR_STOCK_NEGATIVO"})


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """La jornada `EN_RENDICION` de Juan sobre "Camioneta 1" con 37 de Vino A y 12 de Agua 500;
    "Depósito central" (sin toma), "Camioneta 2" (con toma) y una Supervisora con
    `RENDIR_JORNADA` y `TRANSFERIR_STOCK`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.supervisora = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
        )
        self.sin_transferir = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SIN_TRANSFERIR)
        )
        self.con_negativo = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=CON_NEGATIVO)
        )
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.motivo_anulacion = crear_motivo_sql(sesion, self.org, ambito="ANULACION_TRANSFERENCIA")
        self._cargar(self.vino, 37, "1050")
        self._cargar(self.agua, 12, "400")
        self.jornada_id = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            ubicacion_id=self.camioneta,
            estado="EN_RENDICION",
            abierta_en=APERTURA,
        )
        sesion.commit()

    def _cargar(self, producto_id: UUID, cantidad: int, costo: str) -> None:
        stock_service.registrar_stock_inicial(
            self.org,
            self.sesion,
            FixedClock(CARGA),
            ubicacion_id=self.camioneta,
            lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=CARGA,
        )

    def devolucion(
        self, lineas: list[tuple[UUID, int]], destino: UUID | None = None
    ) -> dict[str, Any]:
        return {
            "ubicacion_destino_id": str(destino or self.deposito),
            "lineas": [
                {"producto_id": str(producto), "cantidad_base": cantidad}
                for producto, cantidad in lineas
            ],
        }

    def contenido(self, devolucion: dict[str, Any] | None = None) -> dict[str, Any]:
        contenido: dict[str, Any] = {"jornada_id": str(self.jornada_id)}
        if devolucion is not None:
            contenido["devolucion"] = devolucion
        return contenido

    def enviar(
        self,
        contenido: dict[str, Any],
        *,
        actor: Actor | None = None,
        version: int = 2,
        operation_id: UUID | None = None,
    ) -> Comando:
        quien = actor or self.supervisora
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=CERRAR,
            version=version,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=quien.usuario_id,
            dispositivo_id=quien.dispositivo_id,
            occurred_at=CIERRE,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre, validado, sesion=sesion_protegida, reloj=FixedClock(CIERRE)
            )

        return sync_service.procesar_comando(
            self.sesion,
            FixedClock(CIERRE),
            sobre=sobre,
            huella=huella,
            ejecutar_handler=_ejecutar,
        )

    # --- lectura ---------------------------------------------------------------------------

    def jornada(self) -> Jornada:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(Jornada).where(
                Jornada.organizacion_id == self.org, Jornada.id == self.jornada_id
            )
        ).one()

    def transferencias(self) -> list[Transferencia]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(Transferencia).where(Transferencia.organizacion_id == self.org)
            )
        )

    def movimientos(self, tipo: str) -> list[StockMovimiento]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org, StockMovimiento.tipo == tipo)
                .order_by(StockMovimiento.producto_id, StockMovimiento.cantidad_base)
            )
        )

    def cantidad_de_movimientos(self) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
            )
            or 0
        )

    def saldo(self, producto_id: UUID, ubicacion_id: UUID) -> int:
        self.sesion.rollback()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        )

    def esta_tomada(self) -> bool:
        self.sesion.rollback()
        return stock_service.tiene_jornada_no_cerrada(
            self.org, self.juan.usuario_id, self.juan.dispositivo_id, self.sesion
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _sin_efectos(entorno: Entorno, movimientos_antes: int) -> None:
    """La jornada sigue `EN_RENDICION`, sin transferencia y sin movimientos nuevos (INV-01)."""
    assert entorno.jornada().estado == "EN_RENDICION"
    assert entorno.transferencias() == []
    assert entorno.cantidad_de_movimientos() == movimientos_antes


# --- Cerrar devolviendo el remanente (RUT-08, STK-07, INV-16) --------------------------------


def test_cerrar_devolviendo_al_deposito_escribe_la_transferencia_y_libera(
    entorno: Entorno,
) -> None:
    """Spec "Cerrar devolviendo al depósito": una transferencia de la camioneta al depósito, la
    jornada `CERRADA` y la camioneta libre (RUT-08, STK-07, INV-16)."""
    comando = entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)])))

    assert comando.estado == "ACEPTADO"
    jornada = entorno.jornada()
    assert jornada.estado == "CERRADA"
    assert jornada.cerrada_en == CIERRE
    assert jornada.cerrada_por_id == entorno.supervisora.usuario_id
    (transferencia,) = entorno.transferencias()
    assert transferencia.ubicacion_origen_id == entorno.camioneta
    assert transferencia.ubicacion_destino_id == entorno.deposito
    assert transferencia.estado == "CONFIRMADA"
    assert entorno.saldo(entorno.vino, entorno.camioneta) == 0
    assert entorno.saldo(entorno.vino, entorno.deposito) == 37
    assert entorno.saldo(entorno.agua, entorno.camioneta) == 12  # lo no devuelto queda
    assert not entorno.esta_tomada()
    assert comando.resultado is not None
    assert comando.resultado["estado"] == "CERRADA"
    assert comando.resultado["transferencia_id"] == str(transferencia.id)


def test_devolver_varios_productos_en_una_sola_transferencia(entorno: Entorno) -> None:
    """Triangulación: dos productos, una sola cabecera con las dos líneas (STK-07)."""
    entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 30), (entorno.agua, 12)])))

    assert len(entorno.transferencias()) == 1
    assert entorno.saldo(entorno.vino, entorno.camioneta) == 7
    assert entorno.saldo(entorno.agua, entorno.camioneta) == 0
    assert entorno.saldo(entorno.vino, entorno.deposito) == 30
    assert entorno.saldo(entorno.agua, entorno.deposito) == 12


def test_la_salida_lleva_la_jornada_y_la_entrada_no(entorno: Entorno) -> None:
    """Spec toma-de-ubicacion "La devolución del cierre sale del vehículo tomado": la salida de
    la camioneta con la jornada de Juan y la entrada del depósito sin jornada (STK-09, RUT-08)."""
    entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)])))

    (salida,) = entorno.movimientos("TRANSFERENCIA_SALIDA")
    (entrada,) = entorno.movimientos("TRANSFERENCIA_ENTRADA")
    assert (salida.ubicacion_id, salida.cantidad_base) == (entorno.camioneta, -37)
    assert salida.jornada_id == entorno.jornada_id
    assert (entrada.ubicacion_id, entrada.cantidad_base) == (entorno.deposito, 37)
    assert entrada.jornada_id is None


def test_la_transferencia_de_la_devolucion_se_anula_como_cualquier_otra(
    entorno: Entorno,
) -> None:
    """Es una transferencia común, anulable con `STOCK_TRANSFERENCIA_ANULAR` (TR-06): con la
    jornada ya cerrada el vehículo está libre y el stock vuelve a él."""
    entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)])))
    (transferencia,) = entorno.transferencias()

    stock_service.anular_transferencia(
        entorno.org,
        entorno.sesion,
        FixedClock(CIERRE),
        transferencia_id=transferencia.id,
        motivo_id=entorno.motivo_anulacion,
        permisos={"TRANSFERIR_STOCK", "ANULAR_TRANSFERENCIA"},
        operation_id=uuid4(),
        usuario_id=entorno.supervisora.usuario_id,
        dispositivo_id=entorno.supervisora.dispositivo_id,
        occurred_at=CIERRE,
    )
    entorno.sesion.commit()

    assert entorno.saldo(entorno.vino, entorno.camioneta) == 37
    assert entorno.saldo(entorno.vino, entorno.deposito) == 0


# --- Rechazos (INV-01: sin cambios) ---------------------------------------------------------


def test_devolver_mas_de_lo_que_hay_es_stock_insuficiente_sin_efectos(entorno: Entorno) -> None:
    """Spec "Devolver más de lo que hay": 40 de Vino A con saldo 37 (RUT-08, INV-01)."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 40)])))

    _sin_efectos(entorno, antes)


def test_el_permiso_de_stock_negativo_no_alcanza_a_la_devolucion(entorno: Entorno) -> None:
    """Es físico: sin excepción por permiso (D6). Quien puede dejar stock negativo igual recibe
    `STOCK_INSUFICIENTE`."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 40)])),
            actor=entorno.con_negativo,
        )

    _sin_efectos(entorno, antes)


def test_una_linea_que_no_alcanza_no_deja_las_anteriores(entorno: Entorno) -> None:
    """Todo o nada (INV-01): la primera línea alcanza, la segunda no; no queda ninguna."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 37), (entorno.agua, 13)]))
        )

    _sin_efectos(entorno, antes)


def test_destino_con_toma_es_ubicacion_con_toma(entorno: Entorno) -> None:
    """Spec "Destino con toma": "Camioneta 2" no es un depósito (STK-09, D6)."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(UbicacionConTomaError) as error:
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 37)], entorno.camioneta_2))
        )

    assert error.value.codigo == "UBICACION_CON_TOMA"
    assert error.value.status_http == 409
    _sin_efectos(entorno, antes)


def test_destino_con_otra_jornada_abierta_es_ubicacion_con_toma(entorno: Entorno) -> None:
    """Triangulación: la camioneta 2 tiene la jornada de Pedro (tomada de verdad)."""
    pedro = Actor(*crear_usuario_y_dispositivo(entorno.sesion, entorno.org, permisos=VENDEDOR))
    crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=pedro.usuario_id,
        dispositivo_id=pedro.dispositivo_id,
        ubicacion_id=entorno.camioneta_2,
    )
    entorno.sesion.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(UbicacionConTomaError):
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 37)], entorno.camioneta_2))
        )

    _sin_efectos(entorno, antes)


def test_destino_igual_al_origen_es_ubicaciones_iguales(entorno: Entorno) -> None:
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(UbicacionesIgualesError):
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 37)], entorno.camioneta))
        )

    _sin_efectos(entorno, antes)


def test_destino_inactivo_es_ubicacion_inactiva(entorno: Entorno) -> None:
    inactivo = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Viejo", activo=False)
    entorno.sesion.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(UbicacionInactivaError):
        entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)], inactivo)))

    _sin_efectos(entorno, antes)


def test_destino_de_otra_organizacion_es_404(entorno: Entorno, db_session: Session) -> None:
    """INV-21: una ubicación ajena es inexistente."""
    ajena = crear_ubicacion_sql(db_session, crear_organizacion(db_session).id, nombre="Ajeno")
    db_session.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)], ajena)))

    _sin_efectos(entorno, antes)


def test_devolucion_sin_lineas_es_lineas_invalidas(entorno: Entorno) -> None:
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(LineasInvalidasError):
        entorno.enviar(entorno.contenido(entorno.devolucion([])))

    _sin_efectos(entorno, antes)


def test_devolucion_sin_transferir_stock_es_403_sin_cambios(entorno: Entorno) -> None:
    """Spec "Devolución sin permiso de transferir" (`01` §19, SEG-06)."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(
            entorno.contenido(entorno.devolucion([(entorno.vino, 37)])),
            actor=entorno.sin_transferir,
        )

    _sin_efectos(entorno, antes)


def test_el_vendedor_no_cierra(entorno: Entorno) -> None:
    """Sin `RENDIR_JORNADA` no se cierra, con o sin devolución (SEG-06)."""
    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(entorno.contenido(), actor=entorno.juan)

    assert entorno.jornada().estado == "EN_RENDICION"


def test_cerrar_una_jornada_abierta_con_devolucion_no_mueve_stock(entorno: Entorno) -> None:
    """`JORNADA_ESTADO_INVALIDO` y nada escrito: el estado se revalida antes de transferir."""
    entorno.sesion.execute(
        text(
            "UPDATE jornada SET estado = 'ABIERTA', rendida_en = NULL, rendida_por_id = NULL "
            "WHERE id = :id"
        ),
        {"id": entorno.jornada_id},
    )
    entorno.sesion.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)])))

    assert entorno.jornada().estado == "ABIERTA"
    assert entorno.transferencias() == []
    assert entorno.cantidad_de_movimientos() == antes


# --- Cerrar sin devolver y versiones --------------------------------------------------------


def test_cerrar_sin_devolver_libera_y_deja_el_stock(entorno: Entorno) -> None:
    """Spec "Cerrar sin devolver": con v2 y sin devolución alcanza `RENDIR_JORNADA` solo."""
    comando = entorno.enviar(entorno.contenido(), actor=entorno.sin_transferir)

    assert comando.estado == "ACEPTADO"
    assert entorno.jornada().estado == "CERRADA"
    assert entorno.transferencias() == []
    assert entorno.saldo(entorno.vino, entorno.camioneta) == 37
    assert not entorno.esta_tomada()
    assert comando.resultado is not None
    assert comando.resultado["transferencia_id"] is None


def test_la_version_1_del_cierre_sigue_registrada_y_no_lleva_devolucion(
    entorno: Entorno,
) -> None:
    """v1 sigue igual (D6): cierra sin devolución y rechaza un contenido con ella."""
    comando = entorno.enviar({"jornada_id": str(entorno.jornada_id)}, version=1)

    assert comando.estado == "ACEPTADO"
    assert entorno.jornada().estado == "CERRADA"
    assert comando.resultado is not None
    assert "transferencia_id" not in comando.resultado


# --- Idempotencia (SYN-02, INV-06) ----------------------------------------------------------


def test_doble_envio_del_cierre_con_devolucion_devuelve_lo_mismo_con_una_transferencia(
    entorno: Entorno,
) -> None:
    """Spec "Doble envío del cierre con devolución" (SYN-02, INV-06)."""
    operation_id = uuid4()
    contenido = entorno.contenido(entorno.devolucion([(entorno.vino, 37)]))

    primero = entorno.enviar(contenido, operation_id=operation_id)
    segundo = entorno.enviar(contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.transferencias()) == 1
    assert len(entorno.movimientos("TRANSFERENCIA_SALIDA")) == 1


def test_la_version_1_no_admite_devolucion(entorno: Entorno) -> None:
    """v1 es el cierre sin devolución: un contenido con ella es inválido (`extra="forbid"`) y
    la jornada no cambia."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido(entorno.devolucion([(entorno.vino, 37)])), version=1)

    assert entorno.jornada().estado == "EN_RENDICION"
    assert entorno.transferencias() == []
