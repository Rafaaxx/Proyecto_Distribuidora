"""Change 14, tareas 5.1 y 5.2: `STOCK_TRANSFERIR` v1 por el bus contra PostgreSQL real
(spec `stock/transferencias`, `design.md` D1, D4, D6, D9, D10).

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio
que `test_stock_comandos.py`). La cobertura por HTTP es de `test_stock_transferencias_api.py`.

Reglas citadas: STK-03, STK-05, STK-07, CST-12, CST-13, CAT-05, SEG-06, SYN-02, SYN-07,
INV-01, INV-04, INV-06, INV-12, INV-15, INV-21, AUD-01.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
)

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.costeo import service as costeo_service
from app.modules.costeo.models import CostoProductoMov
from app.modules.identidad.models import Auditoria
from app.modules.stock import commands as stock_commands
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    CantidadInvalidaError,
    LineasInvalidasError,
    ProductoInactivoError,
    ProductoRepetidoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    UbicacionesIgualesError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import StockMovimiento, Transferencia, TransferenciaLinea
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TRANSFERIR = "STOCK_TRANSFERIR"

VENDEDOR = frozenset({"TRANSFERIR_STOCK"})
ADMINISTRADOR = frozenset({"TRANSFERIR_STOCK", "PERMITIR_STOCK_NEGATIVO"})


class Entorno:
    """Una organización con Vino A y Agua 500 en el depósito (120 y 40 unidades, promedios
    1050 y 400), una camioneta vacía y un usuario con permisos configurables."""

    def __init__(self, sesion: Session, *, permisos: frozenset[str] = VENDEDOR) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua_id = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        for producto_id, cantidad, costo in (
            (self.vino_id, 120, "1050"),
            (self.agua_id, 40, "400"),
        ):
            stock_service.registrar_stock_inicial(
                self.org,
                sesion,
                RELOJ,
                ubicacion_id=self.deposito_id,
                lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        sesion.commit()

    def contenido(
        self, lineas: list[tuple[UUID, object]] | None = None, **cambios: object
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "ubicacion_origen_id": str(self.deposito_id),
            "ubicacion_destino_id": str(self.camioneta_id),
            "lineas": [
                {"producto_id": str(producto_id), "cantidad_base": cantidad}
                for producto_id, cantidad in (lineas or [(self.vino_id, 48)])
            ],
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(self, contenido: dict[str, Any], *, operation_id: UUID | None = None) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=TRANSFERIR,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def enviar(self, contenido: dict[str, Any], *, operation_id: UUID | None = None) -> Comando:
        sobre = self.sobre(contenido, operation_id=operation_id)
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return stock_commands.manejar_stock_transferir(  # type: ignore[return-value]
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def saldo(self, producto_id: UUID, ubicacion_id: UUID) -> int:
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        )

    def stock_total(self, producto_id: UUID) -> int:
        costo = costeo_service.obtener_costo(self.org, self.sesion, producto_id)
        assert costo is not None
        return costo.stock_total

    def promedio(self, producto_id: UUID) -> Decimal | None:
        return costeo_service.obtener_promedio(self.org, self.sesion, producto_id)

    def movimientos(self, tipo: str | None = None) -> list[StockMovimiento]:
        consulta = select(StockMovimiento).where(
            StockMovimiento.organizacion_id == self.org,
            StockMovimiento.origen_tipo == "TRANSFERENCIA",
        )
        if tipo is not None:
            consulta = consulta.where(StockMovimiento.tipo == tipo)
        return list(self.sesion.scalars(consulta.order_by(StockMovimiento.id)).all())

    def transferencias(self) -> list[Transferencia]:
        return list(
            self.sesion.scalars(
                select(Transferencia).where(Transferencia.organizacion_id == self.org)
            ).all()
        )

    def lineas(self) -> list[TransferenciaLinea]:
        return list(
            self.sesion.scalars(
                select(TransferenciaLinea).where(TransferenciaLinea.organizacion_id == self.org)
            ).all()
        )

    def historia_de_costo(self) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(CostoProductoMov)
                .where(CostoProductoMov.organizacion_id == self.org)
            )
            or 0
        )

    def sin_efectos(self) -> None:
        """Ninguna transferencia, línea ni movimiento de transferencia (INV-01)."""
        self.sesion.rollback()
        assert self.transferencias() == []
        assert self.lineas() == []
        assert self.movimientos() == []


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _auditorias(entorno: Entorno, operation_id: UUID) -> list[Auditoria]:
    return list(
        entorno.sesion.scalars(
            select(Auditoria).where(
                Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id
            )
        ).all()
    )


# --- catálogo --------------------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5."""
    declarado = catalogo_bus.tipo_declarado(TRANSFERIR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(TRANSFERIR, 1).tipo == TRANSFERIR


# --- escenarios felices ------------------------------------------------------------


def test_carga_de_la_camioneta_desde_el_deposito(entorno: Entorno) -> None:
    """Escenario "Carga de la camioneta desde el depósito" (STK-07, CST-12, INV-15)."""
    historia = entorno.historia_de_costo()

    comando = entorno.enviar(entorno.contenido())

    assert comando.estado == "ACEPTADO"
    (transferencia,) = entorno.transferencias()
    assert transferencia.estado == "CONFIRMADA"
    assert (transferencia.ubicacion_origen_id, transferencia.ubicacion_destino_id) == (
        entorno.deposito_id,
        entorno.camioneta_id,
    )
    (linea,) = entorno.lineas()
    assert (linea.producto_id, linea.cantidad_base, linea.orden) == (entorno.vino_id, 48, 1)

    salida, entrada = (
        entorno.movimientos("TRANSFERENCIA_SALIDA"),
        entorno.movimientos("TRANSFERENCIA_ENTRADA"),
    )
    assert [(m.ubicacion_id, m.cantidad_base) for m in salida] == [(entorno.deposito_id, -48)]
    assert [(m.ubicacion_id, m.cantidad_base) for m in entrada] == [(entorno.camioneta_id, 48)]
    assert [m.costo_unitario for m in (*salida, *entrada)] == [Decimal("1050.000000")] * 2
    assert {m.origen_id for m in (*salida, *entrada)} == {transferencia.id}
    assert (
        entorno.saldo(entorno.vino_id, entorno.deposito_id),
        entorno.saldo(entorno.vino_id, entorno.camioneta_id),
    ) == (72, 48)
    assert entorno.stock_total(entorno.vino_id) == 120  # INV-15
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert entorno.historia_de_costo() == historia  # CST-13: sin historia de costo


def test_el_resultado_trae_los_saldos_resultantes_en_origen_y_destino(entorno: Entorno) -> None:
    comando = entorno.enviar(entorno.contenido())

    assert comando.resultado is not None
    assert comando.resultado["estado"] == "CONFIRMADA"
    assert comando.resultado["lineas"] == [
        {
            "producto_id": str(entorno.vino_id),
            "cantidad_base": 48,
            "saldo_origen": 72,
            "saldo_destino": 48,
        }
    ]
    assert "costo_unitario" not in str(comando.resultado)


def test_varias_lineas_en_una_transferencia(entorno: Entorno) -> None:
    """Escenario "Varias líneas": una transferencia, cuatro movimientos, un solo origen."""
    entorno.enviar(entorno.contenido([(entorno.vino_id, 48), (entorno.agua_id, 24)]))

    (transferencia,) = entorno.transferencias()
    assert sorted(linea.orden for linea in entorno.lineas()) == [1, 2]
    movimientos = entorno.movimientos()
    assert len(movimientos) == 4
    assert {m.origen_id for m in movimientos} == {transferencia.id}
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 48
    assert entorno.saldo(entorno.agua_id, entorno.camioneta_id) == 24
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 16
    # Cada producto se valoriza a su propio promedio.
    costos = {(m.producto_id, m.tipo): m.costo_unitario for m in movimientos}
    assert costos[(entorno.agua_id, "TRANSFERENCIA_ENTRADA")] == Decimal("400.000000")
    assert costos[(entorno.vino_id, "TRANSFERENCIA_SALIDA")] == Decimal("1050.000000")


def test_la_observacion_se_guarda_recortada(entorno: Entorno) -> None:
    entorno.enviar(entorno.contenido(observacion="  carga del lunes  "))

    assert entorno.transferencias()[0].observacion == "carga del lunes"


# --- rechazos de contenido -----------------------------------------------------------


def test_origen_y_destino_iguales(entorno: Entorno) -> None:
    with pytest.raises(UbicacionesIgualesError):
        entorno.enviar(entorno.contenido(ubicacion_destino_id=str(entorno.deposito_id)))

    entorno.sin_efectos()


@pytest.mark.parametrize("cantidad", [0, -5])
def test_cantidad_cero_o_negativa_es_cantidad_invalida(entorno: Entorno, cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, cantidad)]))

    entorno.sin_efectos()


@pytest.mark.parametrize("cantidad", ["12", True])
def test_cantidad_fraccionaria_o_que_no_es_entera_es_contenido_invalido(
    entorno: Entorno, cantidad: object
) -> None:
    """INV-04: 422 de validación del contenido (`StrictInt`), no un error de dominio. Un
    `1.5` JSON no llega acá: lo rechaza el esquema de la ruta (ver el test de la API)."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, cantidad)]))

    entorno.sin_efectos()


@pytest.mark.parametrize("cantidad_de_lineas", [0, 201])
def test_lineas_fuera_de_rango(entorno: Entorno, cantidad_de_lineas: int) -> None:
    contenido = entorno.contenido()
    contenido["lineas"] = [
        {"producto_id": str(uuid4()), "cantidad_base": 1} for _ in range(cantidad_de_lineas)
    ]

    with pytest.raises(LineasInvalidasError):
        entorno.enviar(contenido)

    entorno.sin_efectos()


def test_producto_repetido(entorno: Entorno) -> None:
    with pytest.raises(ProductoRepetidoError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, 1), (entorno.vino_id, 2)]))

    entorno.sin_efectos()


def test_el_contenido_no_puede_traer_la_organizacion(entorno: Entorno) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido(organizacion_id=str(uuid4())))

    entorno.sin_efectos()


# --- ubicaciones y productos (STK-02, CAT-05, INV-21) ----------------------------------


@pytest.mark.parametrize("lado", ["origen", "destino"])
def test_ubicacion_inactiva_como_origen_o_destino(entorno: Entorno, lado: str) -> None:
    inactiva = entorno.deposito_id if lado == "origen" else entorno.camioneta_id
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": inactiva},
    )

    with pytest.raises(UbicacionInactivaError):
        entorno.enviar(entorno.contenido())

    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120


@pytest.mark.parametrize("que", ["destino", "origen", "producto"])
def test_ubicacion_o_producto_ajeno_es_404(entorno: Entorno, que: str) -> None:
    """INV-21, SEG-07: lo de otra organización responde como inexistente."""
    ajena = Entorno(entorno.sesion)
    contenido = entorno.contenido()
    if que == "destino":
        contenido["ubicacion_destino_id"] = str(ajena.camioneta_id)
    elif que == "origen":
        contenido["ubicacion_origen_id"] = str(ajena.deposito_id)
    else:
        contenido["lineas"] = [{"producto_id": str(ajena.vino_id), "cantidad_base": 1}]

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(contenido)

    assert error.value.status_http == 404
    entorno.sin_efectos()
    assert ajena.saldo(ajena.vino_id, ajena.deposito_id) == 120


def test_producto_inactivo_se_rechaza_y_se_acepta_tras_reactivarlo(entorno: Entorno) -> None:
    """D4 (ADR-038 punto 5): el stock de un producto que se discontinúa se mueve antes de
    desactivarlo; uno ya inactivo se reactiva, se vacía y se vuelve a desactivar."""
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)

    with pytest.raises(ProductoInactivoError):
        entorno.enviar(entorno.contenido())

    entorno.sin_efectos()
    entorno.sesion.execute(
        text("UPDATE producto SET activo = true WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.vino_id},
    )
    entorno.enviar(entorno.contenido())
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 48


# --- stock negativo (D1, STK-05, SYN-07) --------------------------------------------------


def test_saldo_insuficiente_sin_permiso_es_stock_insuficiente(entorno: Entorno) -> None:
    with pytest.raises(StockInsuficienteError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, 121)]))

    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 0


def test_saldo_insuficiente_con_permiso_deja_negativo_y_observa(db_session: Session) -> None:
    """Escenario "Saldo insuficiente con permiso": −12 y 60, stock total 48, el comando
    queda `ACEPTADO_CON_OBSERVACIONES` con `STOCK_NEGATIVO` sobre la transferencia."""
    entorno = Entorno(db_session, permisos=ADMINISTRADOR)

    comando = entorno.enviar(entorno.contenido([(entorno.agua_id, 52)]))  # hay 40

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == -12
    assert entorno.saldo(entorno.agua_id, entorno.camioneta_id) == 52
    assert entorno.stock_total(entorno.agua_id) == 40  # INV-15
    (transferencia,) = entorno.transferencias()
    observaciones = list(
        entorno.sesion.scalars(
            select(Observacion).where(Observacion.organizacion_id == entorno.org)
        ).all()
    )
    assert [(o.codigo, o.operacion_tipo, o.operacion_id) for o in observaciones] == [
        ("STOCK_NEGATIVO", "TRANSFERENCIA", transferencia.id)
    ]
    assert observaciones[0].detalle == {
        "producto_id": str(entorno.agua_id),
        "ubicacion_id": str(entorno.deposito_id),
        "saldo": -12,
    }


def test_con_permiso_y_saldo_suficiente_no_hay_observacion(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=ADMINISTRADOR)

    comando = entorno.enviar(entorno.contenido())

    assert comando.estado == "ACEPTADO"
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
        )
        == 0
    )


# --- permiso y modo (SEG-06, `02` §6.5) ----------------------------------------------------


def test_sin_transferir_stock_responde_403_sin_efectos_ni_reserva(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"AJUSTAR_STOCK"}))
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(entorno.contenido(), operation_id=operation_id)

    assert error.value.status_http == 403
    entorno.sin_efectos()
    assert (
        db_session.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )


def test_el_lote_rechaza_una_transferencia_enviada_sin_conexion(entorno: Entorno) -> None:
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=TRANSFERIR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    entorno.sin_efectos()


# --- idempotencia y auditoría (INV-06, AUD-01) -------------------------------------------------


def test_el_reenvio_devuelve_el_resultado_original_sin_nuevos_movimientos(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    primero = entorno.enviar(entorno.contenido(), operation_id=operation_id)
    segundo = entorno.enviar(entorno.contenido(), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.transferencias()) == 1
    assert len(entorno.movimientos()) == 2
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 48


def test_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    operation_id = uuid4()
    entorno.enviar(entorno.contenido(), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, 5)]), operation_id=operation_id)

    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 48


def test_una_sola_fila_de_auditoria_con_motivo_nulo(entorno: Entorno) -> None:
    """La transferencia no lleva motivo (D10): su fila queda con `motivo_id` nulo."""
    operation_id = uuid4()

    entorno.enviar(entorno.contenido(), operation_id=operation_id)
    entorno.enviar(entorno.contenido(), operation_id=operation_id)  # reenvío

    (auditoria,) = _auditorias(entorno, operation_id)
    assert auditoria.motivo_id is None
    assert auditoria.accion == TRANSFERIR


# --- atomicidad (INV-01, tarea 5.2) ----------------------------------------------------------


def test_inv01_una_falla_despues_de_la_primera_salida_no_deja_nada_y_se_puede_reintentar(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla entre la salida y la entrada": ni transferencia, ni línea, ni
    movimiento, ni cambio de saldo o de stock total, y el `operation_id` se reintenta."""
    original = stock_service.repository.insertar_movimiento
    llamadas: list[int] = []

    def insertar_y_fallar(*args: Any, **kwargs: Any) -> Any:
        llamadas.append(1)
        movimiento = original(*args, **kwargs)
        if len(llamadas) == 1:
            raise RuntimeError("falla inyectada después de la primera salida")
        return movimiento

    monkeypatch.setattr(stock_service.repository, "insertar_movimiento", insertar_y_fallar)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(
            entorno.contenido([(entorno.vino_id, 48), (entorno.agua_id, 24)]),
            operation_id=operation_id,
        )

    assert llamadas == [1]  # la primera salida ya se había escrito
    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 0
    assert entorno.stock_total(entorno.vino_id) == 120
    assert _auditorias(entorno, operation_id) == []

    monkeypatch.undo()
    comando = entorno.enviar(
        entorno.contenido([(entorno.vino_id, 48), (entorno.agua_id, 24)]),
        operation_id=operation_id,
    )
    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 48
