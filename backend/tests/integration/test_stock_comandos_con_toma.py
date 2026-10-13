"""Change 15, tarea 8.2: STK-09 en los comandos de `stock` por el bus contra PostgreSQL real (spec
`stock/toma-de-ubicacion`, requisitos "Una ubicación tomada solo acepta movimientos de su
jornada", "La regla de toma alcanza a todo camino que mueve stock" y "La carga del vehículo es
una transferencia"; `design.md` D4, D6, D7, D22).

Las compras y la importación están en la tarea 8.3; la constancia en la auditoría, en la 8.5.

Reglas citadas: STK-07, STK-08, STK-09, STK-10, RUT-02, RUT-08, INV-01, INV-06, INV-12, INV-15,
SEG-06.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.costeo import service as costeo_service
from app.modules.identidad.models import Auditoria
from app.modules.stock import commands as _stock_commands  # noqa: F401  (registra los handlers)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import AjusteStock, StockMovimiento, Transferencia
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

TRANSFERIR = "STOCK_TRANSFERIR"
AJUSTAR = "STOCK_AJUSTAR"
ANULAR_TRANSFERENCIA = "STOCK_TRANSFERENCIA_ANULAR"
ANULAR_AJUSTE = "STOCK_AJUSTE_ANULAR"
INICIAL = "STOCK_INICIAL_REGISTRAR"

VENDEDOR = frozenset({"TRANSFERIR_STOCK", "ABRIR_JORNADA"})
ADMINISTRACION = frozenset(
    {"TRANSFERIR_STOCK", "AJUSTAR_STOCK", "ANULAR_TRANSFERENCIA", "IMPORTAR_DATOS"}
)
SUPERVISORA = ADMINISTRACION | {"LIBERAR_UBICACION"}


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """Vino A con 120 unidades en el depósito y 48 en "Camioneta 1" (promedio 1050). Juan
    (vendedor, `TRANSFERIR_STOCK`) puede tomar "Camioneta 1" con `tomar_camioneta_1()`; Pedro es
    otro vendedor; Administración no tiene `LIBERAR_UBICACION` y la Supervisora sí."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.pedro = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.administracion = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=ADMINISTRACION)
        )
        self.supervisora = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
        )
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.camioneta_1 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        for ubicacion_id, cantidad in ((self.deposito, 120), (self.camioneta_1, 48)):
            stock_service.registrar_stock_inicial(
                self.org,
                sesion,
                RELOJ,
                ubicacion_id=ubicacion_id,
                lineas=[LineaDeStockInicial(self.vino, cantidad, "1050")],
                usuario_id=self.administracion.usuario_id,
                dispositivo_id=self.administracion.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        self.motivo_de_ajuste = crear_motivo_sql(sesion, self.org, ambito="AJUSTE_STOCK")
        self.motivo_anula_transferencia = crear_motivo_sql(
            sesion, self.org, ambito="ANULACION_TRANSFERENCIA"
        )
        self.motivo_anula_ajuste = crear_motivo_sql(sesion, self.org, ambito="ANULACION_AJUSTE")
        sesion.commit()

    # --- jornadas ----------------------------------------------------------------------

    def tomar(self, actor: Actor, ubicacion_id: UUID, estado: str = "ABIERTA") -> UUID:
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            ubicacion_id=ubicacion_id,
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id

    def tomar_camioneta_1(self) -> UUID:
        return self.tomar(self.juan, self.camioneta_1)

    # --- comandos ----------------------------------------------------------------------

    def enviar(
        self,
        tipo: str,
        actor: Actor,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
    ) -> Comando:
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre,
                validado,
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def transferir(
        self,
        actor: Actor,
        origen: UUID,
        destino: UUID,
        cantidad: int = 6,
        *,
        operation_id: UUID | None = None,
    ) -> Comando:
        return self.enviar(
            TRANSFERIR,
            actor,
            {
                "ubicacion_origen_id": str(origen),
                "ubicacion_destino_id": str(destino),
                "lineas": [{"producto_id": str(self.vino), "cantidad_base": cantidad}],
            },
            operation_id=operation_id,
        )

    def ajustar(self, actor: Actor, ubicacion_id: UUID, cantidad: int = -6) -> Comando:
        return self.enviar(
            AJUSTAR,
            actor,
            {
                "ubicacion_id": str(ubicacion_id),
                "motivo_id": str(self.motivo_de_ajuste),
                "lineas": [{"producto_id": str(self.vino), "cantidad_base": cantidad}],
            },
        )

    # --- lecturas -----------------------------------------------------------------------

    def saldo(self, ubicacion_id: UUID, producto_id: UUID | None = None) -> int:
        self.sesion.rollback()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id or self.vino, ubicacion_id=ubicacion_id
        )

    def movimientos(self, ubicacion_id: UUID) -> list[StockMovimiento]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org,
                    StockMovimiento.ubicacion_id == ubicacion_id,
                )
                .order_by(StockMovimiento.registered_at, StockMovimiento.id)
            ).all()
        )

    def cantidad(self, modelo: type) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count()).select_from(modelo).where(modelo.organizacion_id == self.org)  # type: ignore[attr-defined]
            )
            or 0
        )

    def stock_total_y_promedio(self) -> tuple[int, Decimal | None]:
        self.sesion.rollback()
        total = costeo_service.obtener_stock_totales(self.org, self.sesion)[self.vino]
        return total, costeo_service.obtener_promedio(self.org, self.sesion, self.vino)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- el vendedor de la jornada ------------------------------------------------------------------


def test_stk09_la_jornada_transfiere_desde_su_vehiculo(entorno: Entorno) -> None:
    """Escenario "El vendedor de la jornada mueve stock de su vehículo": 48 → 42, con la
    jornada en la línea de la camioneta y sin jornada en el depósito."""
    jornada_id = entorno.tomar_camioneta_1()

    comando = entorno.transferir(entorno.juan, entorno.camioneta_1, entorno.deposito)

    assert comando.estado == "ACEPTADO"
    assert (entorno.saldo(entorno.camioneta_1), entorno.saldo(entorno.deposito)) == (42, 126)
    assert entorno.movimientos(entorno.camioneta_1)[-1].jornada_id == jornada_id
    assert entorno.movimientos(entorno.deposito)[-1].jornada_id is None


def test_stk09_otro_vendedor_no_transfiere_a_un_vehiculo_tomado(entorno: Entorno) -> None:
    """Escenario "Otro vendedor intenta mover stock de un vehículo tomado": sin transferencia,
    sin movimientos y sin cambio de saldos ni de stock total (INV-01, INV-12)."""
    entorno.tomar_camioneta_1()
    antes = (entorno.cantidad(StockMovimiento), entorno.stock_total_y_promedio())

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.transferir(entorno.pedro, entorno.deposito, entorno.camioneta_1)

    assert error.value.codigo == "UBICACION_TOMADA"
    assert entorno.cantidad(Transferencia) == 0
    assert (entorno.cantidad(StockMovimiento), entorno.stock_total_y_promedio()) == antes
    assert (entorno.saldo(entorno.camioneta_1), entorno.saldo(entorno.deposito)) == (48, 120)


def test_stk09_la_toma_no_reemplaza_el_permiso_de_la_operacion(entorno: Entorno) -> None:
    """Escenario "La toma no reemplaza el permiso de la operación": Juan, dueño de la jornada,
    no tiene `AJUSTAR_STOCK`."""
    entorno.tomar_camioneta_1()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.ajustar(entorno.juan, entorno.camioneta_1)

    assert error.value.status_http == 403
    assert entorno.cantidad(AjusteStock) == 0


# --- la carga del vehículo (RUT-02, D4) ----------------------------------------------------------


def test_rut02_la_carga_antes_de_abrir_la_hace_cualquiera_con_transferir_stock(
    entorno: Entorno,
) -> None:
    """Escenario "Carga del vehículo antes de abrir": "Camioneta 2" no tiene jornada."""
    comando = entorno.transferir(entorno.pedro, entorno.deposito, entorno.camioneta_2, 48)

    assert comando.estado == "ACEPTADO"
    assert (entorno.saldo(entorno.deposito), entorno.saldo(entorno.camioneta_2)) == (72, 48)


def test_rut02_inv15_la_carga_durante_la_jornada_no_cambia_stock_total_ni_promedio(
    entorno: Entorno,
) -> None:
    """Escenario "Carga durante la jornada por el propio vendedor": 48 → 72 en la camioneta."""
    jornada_id = entorno.tomar_camioneta_1()
    total_y_promedio = entorno.stock_total_y_promedio()

    comando = entorno.transferir(entorno.juan, entorno.deposito, entorno.camioneta_1, 24)

    assert comando.estado == "ACEPTADO"
    assert (entorno.saldo(entorno.deposito), entorno.saldo(entorno.camioneta_1)) == (96, 72)
    assert entorno.stock_total_y_promedio() == total_y_promedio
    assert entorno.movimientos(entorno.camioneta_1)[-1].jornada_id == jornada_id


def test_inv06_el_doble_envio_de_la_carga_devuelve_el_resultado_original(
    entorno: Entorno,
) -> None:
    entorno.tomar_camioneta_1()
    operation_id = uuid4()

    primero = entorno.transferir(
        entorno.juan, entorno.deposito, entorno.camioneta_1, 24, operation_id=operation_id
    )
    segundo = entorno.transferir(
        entorno.juan, entorno.deposito, entorno.camioneta_1, 24, operation_id=operation_id
    )

    assert primero.resultado == segundo.resultado
    assert entorno.saldo(entorno.camioneta_1) == 72
    assert entorno.cantidad(Transferencia) == 1


@pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
def test_rut08_el_remanente_se_devuelve_despues_del_cierre(entorno: Entorno, estado: str) -> None:
    """Escenario "Devolución del remanente después del cierre"."""
    entorno.tomar(entorno.juan, entorno.camioneta_1, estado)

    comando = entorno.transferir(entorno.pedro, entorno.camioneta_1, entorno.deposito, 12)

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.camioneta_1) == 36


# --- ajustes ----------------------------------------------------------------------------------


def test_stk09_un_ajuste_sobre_un_vehiculo_tomado_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Ajuste sobre un vehículo tomado": Administración, sin `LIBERAR_UBICACION`."""
    entorno.tomar_camioneta_1()

    with pytest.raises(UbicacionTomadaError):
        entorno.ajustar(entorno.administracion, entorno.camioneta_1)

    assert entorno.cantidad(AjusteStock) == 0
    assert entorno.saldo(entorno.camioneta_1) == 48


def test_stk09_la_supervisora_ajusta_un_vehiculo_tomado_sin_jornada_en_el_movimiento(
    entorno: Entorno,
) -> None:
    entorno.tomar_camioneta_1()

    comando = entorno.ajustar(entorno.supervisora, entorno.camioneta_1)

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.camioneta_1) == 42
    assert entorno.movimientos(entorno.camioneta_1)[-1].jornada_id is None


def test_un_deposito_se_ajusta_como_antes_aunque_haya_jornadas_abiertas(
    entorno: Entorno,
) -> None:
    """Escenario "Un depósito nunca queda tomado"."""
    entorno.tomar_camioneta_1()

    comando = entorno.ajustar(entorno.administracion, entorno.deposito)

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.deposito) == 114


# --- anulaciones --------------------------------------------------------------------------------


def _anular_transferencia(entorno: Entorno, actor: Actor, comando: Comando) -> Comando:
    assert comando.resultado is not None
    return entorno.enviar(
        ANULAR_TRANSFERENCIA,
        actor,
        {
            "transferencia_id": str(comando.resultado["transferencia_id"]),
            "motivo_id": str(entorno.motivo_anula_transferencia),
        },
    )


def test_stk09_anular_una_transferencia_cuyo_destino_quedo_tomado_se_rechaza(
    entorno: Entorno,
) -> None:
    """Escenario "Anulación de una transferencia cuyo destino quedó tomado"."""
    original = entorno.transferir(entorno.administracion, entorno.deposito, entorno.camioneta_1, 48)
    entorno.tomar_camioneta_1()

    with pytest.raises(UbicacionTomadaError):
        _anular_transferencia(entorno, entorno.administracion, original)

    estado = entorno.sesion.scalars(select(Transferencia.estado)).one()
    assert estado == "CONFIRMADA"
    assert entorno.saldo(entorno.camioneta_1) == 96


def test_stk09_el_vendedor_anula_su_propia_carga_durante_la_jornada(entorno: Entorno) -> None:
    """Escenario "El vendedor anula su propia carga durante la jornada": el inverso de la
    camioneta queda con su jornada."""
    jornada_id = entorno.tomar_camioneta_1()
    carga = entorno.transferir(entorno.juan, entorno.deposito, entorno.camioneta_1, 24)

    anulacion = _anular_transferencia(entorno, entorno.juan, carga)

    assert anulacion.estado == "ACEPTADO"
    assert entorno.saldo(entorno.camioneta_1) == 48
    assert entorno.movimientos(entorno.camioneta_1)[-1].jornada_id == jornada_id


def test_stk09_anular_un_ajuste_sobre_un_vehiculo_tomado_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Anulación de un ajuste sobre un vehículo tomado"."""
    ajuste = entorno.ajustar(entorno.administracion, entorno.camioneta_1)
    entorno.tomar_camioneta_1()
    assert ajuste.resultado is not None

    with pytest.raises(UbicacionTomadaError):
        entorno.enviar(
            ANULAR_AJUSTE,
            entorno.administracion,
            {
                "ajuste_id": str(ajuste.resultado["ajuste_id"]),
                "motivo_id": str(entorno.motivo_anula_ajuste),
            },
        )

    assert entorno.sesion.scalars(select(AjusteStock.estado)).one() == "CONFIRMADA"
    assert entorno.saldo(entorno.camioneta_1) == 42


# --- stock inicial (salda la deuda del change 09) ---------------------------------------


def _stock_inicial(entorno: Entorno, actor: Actor) -> Comando:
    return entorno.enviar(
        INICIAL,
        actor,
        {
            "ubicacion_id": str(entorno.camioneta_1),
            "lineas": [
                {"producto_id": str(entorno.agua), "cantidad_base": 24, "costo_unitario": "400"}
            ],
        },
    )


def test_stk09_stock_inicial_sobre_un_vehiculo_tomado_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Stock inicial sobre un vehículo tomado" (STK-10)."""
    entorno.tomar_camioneta_1()

    with pytest.raises(UbicacionTomadaError):
        _stock_inicial(entorno, entorno.administracion)

    assert entorno.saldo(entorno.camioneta_1, entorno.agua) == 0


def test_stk09_stock_inicial_sobre_un_vehiculo_tomado_lo_registra_quien_tiene_liberar_ubicacion(
    entorno: Entorno,
) -> None:
    entorno.tomar_camioneta_1()

    comando = _stock_inicial(entorno, entorno.supervisora)

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.camioneta_1, entorno.agua) == 24
    assert entorno.movimientos(entorno.camioneta_1)[-1].jornada_id is None


# --- constancia de la excepción en la auditoría (tarea 8.5, D8; AUD-01, AUD-02) ---


def _filas_de_auditoria(entorno: Entorno, comando: Comando) -> list[Auditoria]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Auditoria).where(
                Auditoria.organizacion_id == entorno.org,
                Auditoria.operation_id == comando.operation_id,
            )
        ).all()
    )


def _constancia(jornada_id: UUID) -> str:
    return f"STK-09: ubicación tomada por la jornada {jornada_id}"


def test_aud02_la_transferencia_por_excepcion_deja_la_constancia_en_la_unica_fila(
    entorno: Entorno,
) -> None:
    jornada_id = entorno.tomar_camioneta_1()

    comando = entorno.transferir(entorno.supervisora, entorno.deposito, entorno.camioneta_1, 12)

    (fila,) = _filas_de_auditoria(entorno, comando)
    assert fila.accion == TRANSFERIR
    assert fila.observacion == _constancia(jornada_id)


def test_aud02_sin_excepcion_la_observacion_es_nula(entorno: Entorno) -> None:
    """Ubicación libre, aunque quien opera tenga `LIBERAR_UBICACION`; y la jornada propia."""
    jornada_id = entorno.tomar_camioneta_1()
    libre = entorno.transferir(entorno.supervisora, entorno.deposito, entorno.camioneta_2, 12)
    propia = entorno.transferir(entorno.juan, entorno.camioneta_1, entorno.deposito, 6)

    assert [f.observacion for f in _filas_de_auditoria(entorno, libre)] == [None]
    assert [f.observacion for f in _filas_de_auditoria(entorno, propia)] == [None]
    assert jornada_id


def test_aud02_un_comando_rechazado_no_deja_la_constancia(entorno: Entorno) -> None:
    entorno.tomar_camioneta_1()
    operation_id = uuid4()

    with pytest.raises(UbicacionTomadaError):
        entorno.transferir(
            entorno.pedro, entorno.deposito, entorno.camioneta_1, operation_id=operation_id
        )

    entorno.sesion.rollback()
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.operation_id == operation_id)
        )
        == 0
    )


def test_aud02_el_ajuste_por_excepcion_lleva_motivo_y_constancia(entorno: Entorno) -> None:
    jornada_id = entorno.tomar_camioneta_1()

    comando = entorno.ajustar(entorno.supervisora, entorno.camioneta_1)

    (fila,) = _filas_de_auditoria(entorno, comando)
    assert (fila.motivo_id, fila.observacion) == (entorno.motivo_de_ajuste, _constancia(jornada_id))


def test_aud02_las_anulaciones_por_excepcion_dejan_la_constancia(entorno: Entorno) -> None:
    carga = entorno.transferir(entorno.supervisora, entorno.deposito, entorno.camioneta_1, 24)
    ajuste = entorno.ajustar(entorno.supervisora, entorno.camioneta_1)
    jornada_id = entorno.tomar_camioneta_1()
    assert carga.resultado is not None and ajuste.resultado is not None

    anula_transferencia = _anular_transferencia(entorno, entorno.supervisora, carga)
    anula_ajuste = entorno.enviar(
        ANULAR_AJUSTE,
        entorno.supervisora,
        {
            "ajuste_id": str(ajuste.resultado["ajuste_id"]),
            "motivo_id": str(entorno.motivo_anula_ajuste),
        },
    )

    for comando, motivo in (
        (anula_transferencia, entorno.motivo_anula_transferencia),
        (anula_ajuste, entorno.motivo_anula_ajuste),
    ):
        (fila,) = _filas_de_auditoria(entorno, comando)
        assert (fila.motivo_id, fila.observacion) == (motivo, _constancia(jornada_id))


def test_aud02_el_stock_inicial_por_excepcion_deja_la_constancia(entorno: Entorno) -> None:
    jornada_id = entorno.tomar_camioneta_1()

    comando = _stock_inicial(entorno, entorno.supervisora)

    (fila,) = _filas_de_auditoria(entorno, comando)
    assert fila.observacion == _constancia(jornada_id)
