"""Change 14, tareas 6.1 y 6.2: `STOCK_AJUSTAR` v1 por el bus contra PostgreSQL real (spec
`stock/ajustes-de-stock`, `design.md` D1, D2, D3, D4, D6, D9).

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio
que `test_stock_transferir.py`). La cobertura por HTTP es de `test_stock_ajustes_api.py`. El
motivo en la auditoría del bus (tarea 7.1) se prueba aquí y en `test_bus_auditoria_motivo.py`.

Reglas citadas: STK-03, STK-05, STK-08, CST-12, CST-13, CAT-05, SEG-06, SYN-02, INV-01,
INV-04, INV-05, INV-06, INV-12, INV-21, AUD-01, AUD-02.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_motivo_sql,
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
    MotivoInvalidoError,
    ObservacionInvalidaError,
    ProductoInactivoError,
    ProductoRepetidoError,
    ProductoSinCostoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import AjusteStock, AjusteStockLinea, StockMovimiento
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
AJUSTAR = "STOCK_AJUSTAR"

ADMINISTRACION = frozenset({"AJUSTAR_STOCK"})
ADMINISTRADOR = frozenset({"AJUSTAR_STOCK", "PERMITIR_STOCK_NEGATIVO", "TRANSFERIR_STOCK"})


class Entorno:
    """Una organización con Vino A (120 a 1050) y Agua 500 (40 a 400) en el depósito, una
    camioneta vacía, un producto sin costo y motivos de ajuste; usuario con permisos
    configurables."""

    def __init__(self, sesion: Session, *, permisos: frozenset[str] = ADMINISTRACION) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua_id = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.sin_costo_id = crear_producto_sql(sesion, self.org, nombre="Agua 1500")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.motivo_id = crear_motivo_sql(sesion, self.org)
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

    def motivo(self, *, ambito: str = "AJUSTE_STOCK", activo: bool = True) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :o, :a, :n, :act, :m, :m)"
            ),
            {
                "id": motivo_id,
                "o": self.org,
                "a": ambito,
                "n": f"M {uuid4().hex[:6]}",
                "act": activo,
                "m": MOMENTO,
            },
        )
        self.sesion.commit()
        return motivo_id

    def contenido(
        self, lineas: list[tuple[UUID, object]] | None = None, **cambios: object
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "ubicacion_id": str(self.deposito_id),
            "motivo_id": str(self.motivo_id),
            "lineas": [
                {"producto_id": str(producto_id), "cantidad_base": cantidad}
                for producto_id, cantidad in (lineas or [(self.vino_id, -6)])
            ],
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(self, contenido: dict[str, Any], *, operation_id: UUID | None = None) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=AJUSTAR,
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
            return stock_commands.manejar_stock_ajustar(
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

    def movimientos(self) -> list[StockMovimiento]:
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org,
                    StockMovimiento.origen_tipo == "AJUSTE_STOCK",
                )
                .order_by(StockMovimiento.id)
            ).all()
        )

    def ajustes(self) -> list[AjusteStock]:
        return list(
            self.sesion.scalars(select(AjusteStock).where(AjusteStock.organizacion_id == self.org))
        )

    def lineas(self) -> list[AjusteStockLinea]:
        return list(
            self.sesion.scalars(
                select(AjusteStockLinea)
                .where(AjusteStockLinea.organizacion_id == self.org)
                .order_by(AjusteStockLinea.orden)
            )
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
        """Ningún ajuste, línea ni movimiento de ajuste (INV-01)."""
        self.sesion.rollback()
        assert self.ajustes() == []
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
    declarado = catalogo_bus.tipo_declarado(AJUSTAR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(AJUSTAR, 1).tipo == AJUSTAR


# --- escenarios felices ------------------------------------------------------------


def test_rotura_en_el_deposito(entorno: Entorno) -> None:
    """Escenario "Rotura en el depósito" (STK-08, CST-12, CST-13)."""
    historia = entorno.historia_de_costo()

    comando = entorno.enviar(entorno.contenido())

    assert comando.estado == "ACEPTADO"
    (ajuste,) = entorno.ajustes()
    assert (ajuste.estado, ajuste.motivo_id, ajuste.ubicacion_id) == (
        "CONFIRMADA",
        entorno.motivo_id,
        entorno.deposito_id,
    )
    (linea,) = entorno.lineas()
    assert (linea.producto_id, linea.cantidad_base, linea.orden) == (entorno.vino_id, -6, 1)
    assert linea.costo_unitario == Decimal("1050.000000")
    (movimiento,) = entorno.movimientos()
    assert (movimiento.tipo, movimiento.cantidad_base) == ("AJUSTE", -6)
    assert movimiento.motivo_id == entorno.motivo_id
    assert movimiento.costo_unitario == Decimal("1050.000000")
    assert movimiento.origen_id == ajuste.id
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114
    assert entorno.stock_total(entorno.vino_id) == 114
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert entorno.historia_de_costo() == historia


def test_el_resultado_trae_el_saldo_resultante_y_no_trae_costos(entorno: Entorno) -> None:
    comando = entorno.enviar(entorno.contenido(observacion="  conteo  "))

    assert comando.resultado is not None
    assert comando.resultado["estado"] == "CONFIRMADA"
    assert comando.resultado["lineas"] == [
        {"producto_id": str(entorno.vino_id), "cantidad_base": -6, "saldo": 114}
    ]
    assert comando.resultado["observacion"] == "conteo"
    assert "costo" not in str(comando.resultado)


def test_conteo_con_signos_mezclados(entorno: Entorno) -> None:
    """Escenario "Conteo con sobrantes y faltantes": Vino A −2 y Agua 500 +1."""
    entorno.enviar(entorno.contenido([(entorno.vino_id, -2), (entorno.agua_id, 1)]))

    assert sorted(linea.orden for linea in entorno.lineas()) == [1, 2]
    assert len(entorno.movimientos()) == 2
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 118
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 41
    costos = {m.producto_id: m.costo_unitario for m in entorno.movimientos()}
    assert costos == {
        entorno.vino_id: Decimal("1050.000000"),
        entorno.agua_id: Decimal("400.000000"),
    }


def test_ajuste_positivo_al_promedio_sin_historia(entorno: Entorno) -> None:
    """Escenario "Ajuste positivo al promedio" (CST-12, CST-13): +2 → stock total 122."""
    historia = entorno.historia_de_costo()

    entorno.enviar(entorno.contenido([(entorno.vino_id, 2)]))

    (movimiento,) = entorno.movimientos()
    assert movimiento.costo_unitario == Decimal("1050.000000")
    assert entorno.stock_total(entorno.vino_id) == 122
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert entorno.historia_de_costo() == historia


def test_ajuste_positivo_de_un_producto_sin_costo(entorno: Entorno) -> None:
    """Escenario "Ajuste positivo de un producto sin costo" (D3): `PRODUCTO_SIN_COSTO`."""
    with pytest.raises(ProductoSinCostoError):
        entorno.enviar(entorno.contenido([(entorno.sin_costo_id, 24)]))

    entorno.sin_efectos()


def test_producto_sin_costo_en_una_segunda_linea_rechaza_todo(entorno: Entorno) -> None:
    with pytest.raises(ProductoSinCostoError) as error:
        entorno.enviar(entorno.contenido([(entorno.vino_id, 2), (entorno.sin_costo_id, 24)]))

    assert error.value.extension is not None and error.value.extension["linea"] == 1
    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.stock_total(entorno.vino_id) == 120


# --- stock negativo (D1 = B, D2) -----------------------------------------------------------


def test_ajuste_mayor_que_el_saldo_sin_permiso(db_session: Session) -> None:
    """Escenario "Ajuste mayor que el saldo sin permiso" (STK-05, D1)."""
    entorno = Entorno(db_session)

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(entorno.contenido([(entorno.agua_id, -41)]))  # hay 40

    entorno.sin_efectos()
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 40


def test_ajuste_mayor_que_el_saldo_con_permiso_se_rechaza_igual_sin_observacion(
    db_session: Session,
) -> None:
    """D1 = B: `PERMITIR_STOCK_NEGATIVO` no alcanza al ajuste."""
    entorno = Entorno(db_session, permisos=ADMINISTRADOR)

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(entorno.contenido([(entorno.agua_id, -41)]))

    entorno.sin_efectos()
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 40
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
        )
        == 0
    )


@pytest.mark.parametrize("permisos", [ADMINISTRACION, ADMINISTRADOR])
def test_una_linea_que_no_alcanza_rechaza_todo_el_ajuste(
    db_session: Session, permisos: frozenset[str]
) -> None:
    entorno = Entorno(db_session, permisos=permisos)

    with pytest.raises(StockInsuficienteError) as error:
        entorno.enviar(entorno.contenido([(entorno.vino_id, -2), (entorno.agua_id, -41)]))

    assert error.value.extension is not None and error.value.extension["linea"] == 1
    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.stock_total(entorno.vino_id) == 120


def test_el_ajuste_puede_dejar_el_saldo_exactamente_en_cero(entorno: Entorno) -> None:
    entorno.enviar(entorno.contenido([(entorno.agua_id, -40)]))

    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 0


def test_regularizacion_de_un_saldo_negativo_a_cero(db_session: Session) -> None:
    """Escenario "Regularizar a cero" (D2): −12 por una transferencia con permiso → +12."""
    entorno = Entorno(db_session, permisos=ADMINISTRADOR)
    stock_service.transferir(
        entorno.org,
        db_session,
        RELOJ,
        ubicacion_origen_id=entorno.deposito_id,
        ubicacion_destino_id=entorno.camioneta_id,
        lineas=[stock_service.LineaDeTransferencia(entorno.agua_id, 52)],
        observacion=None,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=MOMENTO,
        permitir_negativo=True,
    )
    db_session.commit()
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == -12

    entorno.enviar(entorno.contenido([(entorno.agua_id, 12)]))

    (movimiento,) = entorno.movimientos()
    assert movimiento.costo_unitario == Decimal("400.000000")
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 0
    assert entorno.promedio(entorno.agua_id) == Decimal("400.000000")


# --- rechazos de contenido -----------------------------------------------------------


def test_motivo_inactivo_o_de_otro_ambito_es_motivo_invalido(entorno: Entorno) -> None:
    inactivo = entorno.motivo(activo=False)
    otro_ambito = entorno.motivo(ambito="ANULACION_COMPRA")

    for motivo_id in (inactivo, otro_ambito):
        with pytest.raises(MotivoInvalidoError):
            entorno.enviar(entorno.contenido(motivo_id=str(motivo_id)))
        entorno.sin_efectos()


@pytest.mark.parametrize("que", ["motivo", "ubicacion", "producto"])
def test_motivo_ubicacion_o_producto_ajeno_es_404(entorno: Entorno, que: str) -> None:
    """INV-21, SEG-07."""
    ajena = Entorno(entorno.sesion)
    contenido = entorno.contenido()
    if que == "motivo":
        contenido["motivo_id"] = str(ajena.motivo_id)
    elif que == "ubicacion":
        contenido["ubicacion_id"] = str(ajena.deposito_id)
    else:
        contenido["lineas"] = [{"producto_id": str(ajena.vino_id), "cantidad_base": -1}]

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(contenido)

    assert error.value.status_http == 404
    entorno.sin_efectos()
    assert ajena.saldo(ajena.vino_id, ajena.deposito_id) == 120


def test_cantidad_cero_es_cantidad_invalida(entorno: Entorno) -> None:
    with pytest.raises(CantidadInvalidaError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, 0)]))

    entorno.sin_efectos()


@pytest.mark.parametrize("cantidad", ["12", True])
def test_cantidad_que_no_es_entera_es_contenido_invalido(
    entorno: Entorno, cantidad: object
) -> None:
    """INV-04."""
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
        entorno.enviar(entorno.contenido([(entorno.vino_id, 1), (entorno.vino_id, -2)]))

    entorno.sin_efectos()


def test_observacion_de_501_caracteres(entorno: Entorno) -> None:
    with pytest.raises(ObservacionInvalidaError):
        entorno.enviar(entorno.contenido(observacion="x" * 501))

    entorno.sin_efectos()


def test_el_contenido_no_puede_traer_la_organizacion(entorno: Entorno) -> None:
    """INV-21, TR-08."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido(organizacion_id=str(uuid4())))

    entorno.sin_efectos()


def test_ubicacion_inactiva(entorno: Entorno) -> None:
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": entorno.deposito_id},
    )

    with pytest.raises(UbicacionInactivaError):
        entorno.enviar(entorno.contenido())

    entorno.sin_efectos()


# --- producto inactivo (D4) --------------------------------------------------------------


@pytest.mark.parametrize("cantidad", [-18, 6])
def test_producto_inactivo_se_rechaza_en_negativo_y_en_positivo(
    entorno: Entorno, cantidad: int
) -> None:
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)

    with pytest.raises(ProductoInactivoError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, cantidad)]))

    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120


def test_reactivar_dar_de_baja_y_volver_a_desactivar(entorno: Entorno) -> None:
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.agua_id)
    entorno.sesion.execute(
        text("UPDATE producto SET activo = true WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.agua_id},
    )

    entorno.enviar(entorno.contenido([(entorno.agua_id, -40)]))

    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 0


# --- permiso y modo (SEG-06, `02` §6.5) ----------------------------------------------------


def test_vendedor_con_solo_transferir_stock_responde_403_sin_efectos(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"TRANSFERIR_STOCK"}))
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


def test_el_lote_rechaza_un_ajuste_enviado_sin_conexion(entorno: Entorno) -> None:
    item = ItemLote(
        operation_id=uuid4(),
        tipo=AJUSTAR,
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
    assert len(entorno.ajustes()) == 1
    assert len(entorno.movimientos()) == 1
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114


def test_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    operation_id = uuid4()
    entorno.enviar(entorno.contenido(), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, -5)]), operation_id=operation_id)

    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114


def test_una_sola_fila_de_auditoria_por_ajuste(entorno: Entorno) -> None:
    """AUD-01, AUD-02: el reenvío no escribe otra, y la fila lleva el motivo del ajuste."""
    operation_id = uuid4()

    entorno.enviar(entorno.contenido(), operation_id=operation_id)
    entorno.enviar(entorno.contenido(), operation_id=operation_id)

    (auditoria,) = _auditorias(entorno, operation_id)
    assert auditoria.accion == AJUSTAR
    assert auditoria.motivo_id == entorno.motivo_id
    assert auditoria.observacion is None


def test_aud02_el_ajuste_por_rotura_deja_el_motivo_de_rotura_y_no_el_de_otro(
    entorno: Entorno,
) -> None:
    """Escenario "Auditoría del ajuste con motivo": cada ajuste lleva SU motivo."""
    rotura = entorno.motivo()
    vencimiento = entorno.motivo()
    por_rotura, por_vencimiento = uuid4(), uuid4()

    entorno.enviar(entorno.contenido(motivo_id=str(rotura)), operation_id=por_rotura)
    entorno.enviar(
        entorno.contenido([(entorno.agua_id, -3)], motivo_id=str(vencimiento)),
        operation_id=por_vencimiento,
    )

    (fila_rotura,) = _auditorias(entorno, por_rotura)
    (fila_vencimiento,) = _auditorias(entorno, por_vencimiento)
    assert fila_rotura.motivo_id == rotura
    assert fila_rotura.usuario_id == entorno.usuario_id
    assert fila_rotura.dispositivo_id == entorno.dispositivo_id
    assert fila_vencimiento.motivo_id == vencimiento


def test_aud02_un_ajuste_rechazado_no_deja_fila_de_auditoria_con_motivo(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(entorno.contenido([(entorno.vino_id, -500)]), operation_id=operation_id)

    assert _auditorias(entorno, operation_id) == []
    entorno.sin_efectos()


# --- atomicidad (INV-01) e INV-05 (tarea 6.2) ----------------------------------------------


def test_inv01_una_falla_despues_del_primer_movimiento_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla entre dos líneas": ni ajuste, ni línea, ni movimiento, ni cambio de
    saldo o de stock total, y el `operation_id` se reintenta."""
    original = stock_service.repository.insertar_movimiento
    llamadas: list[int] = []

    def insertar_y_fallar(*args: Any, **kwargs: Any) -> Any:
        llamadas.append(1)
        movimiento = original(*args, **kwargs)
        if len(llamadas) == 1:
            raise RuntimeError("falla inyectada después del primer movimiento")
        return movimiento

    monkeypatch.setattr(stock_service.repository, "insertar_movimiento", insertar_y_fallar)
    operation_id = uuid4()
    contenido = entorno.contenido([(entorno.vino_id, -6), (entorno.agua_id, -3)])

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(contenido, operation_id=operation_id)

    assert llamadas == [1]
    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.stock_total(entorno.vino_id) == 120
    assert _auditorias(entorno, operation_id) == []

    monkeypatch.undo()
    comando = entorno.enviar(contenido, operation_id=operation_id)
    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114


def _como_app_runtime(entorno: Entorno, sentencia: str, **parametros: object) -> None:
    """Ejecuta la sentencia con el rol `app_runtime` sobre los datos reales de la prueba (la
    sesión de prueba no confirma, así que otra conexión no los vería). El savepoint devuelve
    la sesión a su estado y el `SET LOCAL ROLE` se descarta con él."""
    with entorno.sesion.begin_nested():
        entorno.sesion.execute(text("SET LOCAL ROLE app_runtime"))
        entorno.sesion.execute(text(sentencia), parametros)


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM ajuste_stock WHERE id = :a",
        "DELETE FROM ajuste_stock_linea WHERE ajuste_id = :a",
        "UPDATE ajuste_stock_linea SET cantidad_base = 5 WHERE ajuste_id = :a",
        "UPDATE ajuste_stock SET observacion = 'x' WHERE id = :a",
        "UPDATE ajuste_stock SET motivo_id = motivo_id WHERE id = :a",
        "UPDATE stock_movimiento SET cantidad_base = 5 WHERE origen_id = :a",
        "DELETE FROM stock_movimiento WHERE origen_id = :a",
    ],
)
def test_inv05_app_runtime_no_modifica_ni_borra_un_ajuste_confirmado(
    entorno: Entorno, sentencia: str
) -> None:
    entorno.enviar(entorno.contenido())
    (ajuste,) = entorno.ajustes()

    with pytest.raises(ProgrammingError, match="(?i)permission denied"):
        _como_app_runtime(entorno, sentencia, a=ajuste.id)

    assert len(entorno.ajustes()) == 1
    assert len(entorno.lineas()) == 1
    assert len(entorno.movimientos()) == 1


def test_inv05_la_cabecera_acepta_update_de_anulacion_pero_no_un_estado_incoherente(
    entorno: Entorno,
) -> None:
    """Contraste: `UPDATE` del estado es un privilegio de `app_runtime` (D5, D8); lo rechaza
    el `CHECK` de coherencia (anulada sin motivo), no el privilegio."""
    entorno.enviar(entorno.contenido())
    (ajuste,) = entorno.ajustes()

    with pytest.raises(IntegrityError, match="ck_ajuste_stock__anulacion_coherente"):
        _como_app_runtime(
            entorno, "UPDATE ajuste_stock SET estado = 'ANULADA' WHERE id = :a", a=ajuste.id
        )
