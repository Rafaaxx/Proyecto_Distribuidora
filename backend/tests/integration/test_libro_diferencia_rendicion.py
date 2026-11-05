"""Change 24, tarea 6.1: `DIFERENCIA_RENDICION` en la única puerta del libro contra PostgreSQL real
(spec `stock/libro-de-stock`, requisito "La diferencia de rendición entra por la única puerta sin
recalcular el promedio"; `design.md` D5).

Reglas citadas: CST-12, CST-13, STK-03, STK-05, INV-01, INV-03.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql

from app.core.clock import FixedClock
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import service
from app.modules.stock.domain.errores import (
    StockInsuficienteError,
    TipoDeMovimientoInvalidoError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.models import StockMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
DIFERENCIA = "DIFERENCIA_RENDICION"


class Entorno:
    """Vino A con 120 en el depósito y promedio 1050; Pedro con `PERMITIR_STOCK_NEGATIVO`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

    def mover(
        self, *lineas: LineaDeMovimiento, permitir_negativo: bool = False
    ) -> list[service.ResultadoDeMovimiento]:
        return service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=list(lineas),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            permitir_negativo=permitir_negativo,
        )

    def linea(
        self,
        cantidad: int,
        tipo: str,
        *,
        costo: str | None = None,
        origen_tipo: str | None = None,
        producto_id: UUID | None = None,
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=producto_id or self.vino,
            ubicacion_id=self.deposito,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo=origen_tipo or tipo,
            origen_id=uuid4(),
        )

    def compra(self, cantidad: int, costo: str, producto_id: UUID | None = None) -> None:
        self.mover(self.linea(cantidad, "COMPRA", costo=costo, producto_id=producto_id))

    def costo(self, producto_id: UUID | None = None) -> CostoProducto | None:
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == (producto_id or self.vino),
            )
            .execution_options(populate_existing=True)
        ).one_or_none()

    def historia(self, producto_id: UUID | None = None) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(CostoProductoMov)
                .where(
                    CostoProductoMov.organizacion_id == self.org,
                    CostoProductoMov.producto_id == (producto_id or self.vino),
                )
            )
            or 0
        )

    def saldo(self, producto_id: UUID | None = None) -> int:
        return service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=producto_id or self.vino,
            ubicacion_id=self.deposito,
        )

    def movimientos_de_diferencia(self) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org, StockMovimiento.tipo == DIFERENCIA
                )
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_sobrante_se_valoriza_al_promedio_vigente_sin_recalcularlo(entorno: Entorno) -> None:
    """CST-12, CST-13, INV-03: +2 con origen `RENDICION` guarda el promedio y no deja historia."""
    entorno.compra(120, "1050")
    historia_previa = entorno.historia()

    (resultado,) = entorno.mover(entorno.linea(2, DIFERENCIA, origen_tipo="RENDICION"))

    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    assert resultado.movimiento.tipo == DIFERENCIA
    assert entorno.saldo() == 122
    costo = entorno.costo()
    assert costo is not None
    assert (costo.stock_total, costo.costo_promedio) == (122, Decimal("1050.000000"))
    assert entorno.historia() == historia_previa


def test_el_sobrante_no_recalcula_ni_con_otro_promedio(entorno: Entorno) -> None:
    """Triangulación: con otro promedio y varios sobrantes el promedio sigue intacto."""
    entorno.compra(10, "200.50")

    entorno.mover(entorno.linea(7, DIFERENCIA, origen_tipo="RENDICION"))

    costo = entorno.costo()
    assert costo is not None
    assert (costo.stock_total, costo.costo_promedio) == (17, Decimal("200.500000"))


def test_faltante_baja_el_stock_total_al_promedio_vigente(entorno: Entorno) -> None:
    """CST-12: el faltante se valoriza al promedio y baja `stock_total`, sin historia."""
    entorno.compra(120, "1050")
    historia_previa = entorno.historia()

    (resultado,) = entorno.mover(entorno.linea(-3, DIFERENCIA, origen_tipo="RENDICION"))

    assert resultado.movimiento.cantidad_base == -3
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    costo = entorno.costo()
    assert costo is not None
    assert costo.stock_total == 117
    assert entorno.historia() == historia_previa


def test_sobrante_de_producto_sin_promedio_queda_con_costo_nulo(entorno: Entorno) -> None:
    """D5: sin promedio, el sobrante entra con costo nulo (CST-12)."""
    sin_costo = crear_producto_sql(entorno.sesion, entorno.org, nombre="Sin costo")

    (resultado,) = entorno.mover(
        entorno.linea(4, DIFERENCIA, origen_tipo="RENDICION", producto_id=sin_costo)
    )

    assert resultado.movimiento.costo_unitario is None
    assert entorno.saldo(sin_costo) == 4


@pytest.mark.parametrize("permitir_negativo", [False, True])
def test_faltante_que_dejaria_negativo_se_rechaza_aun_con_permiso(
    entorno: Entorno, permitir_negativo: bool
) -> None:
    """STK-05, INV-01: con o sin `PERMITIR_STOCK_NEGATIVO`, nada queda escrito."""
    entorno.compra(2, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(
            entorno.linea(-3, DIFERENCIA, origen_tipo="RENDICION"),
            permitir_negativo=permitir_negativo,
        )

    assert entorno.saldo() == 2
    assert entorno.movimientos_de_diferencia() == 0


@pytest.mark.parametrize("origen", ["AJUSTE_STOCK", "TRANSFERENCIA", "DIFERENCIA_RENDICION"])
@pytest.mark.parametrize("cantidad", [2, -1])
def test_diferencia_con_otro_origen_es_tipo_invalido(
    entorno: Entorno, origen: str, cantidad: int
) -> None:
    """STK-03: solo el origen `RENDICION` admite el tipo."""
    entorno.compra(5, "1050")

    with pytest.raises(TipoDeMovimientoInvalidoError):
        entorno.mover(entorno.linea(cantidad, DIFERENCIA, origen_tipo=origen))

    assert entorno.movimientos_de_diferencia() == 0


def test_diferencia_con_costo_es_costo_invalido(entorno: Entorno) -> None:
    """El costo lo pone la puerta (promedio vigente): una línea con costo se rechaza."""
    from app.modules.stock.domain.errores import CostoInvalidoError

    entorno.compra(5, "1050")

    with pytest.raises(CostoInvalidoError):
        entorno.mover(entorno.linea(2, DIFERENCIA, costo="10", origen_tipo="RENDICION"))
