"""Tarea 6.2 (change 18a; spec `stock/libro-de-stock`; `design.md` D10, D11): el egreso `VENTA`
de `stock.registrar_movimientos` se valoriza al promedio vigente (nulo si no hay) y deja el saldo
negativo solo con `PERMITIR_STOCK_NEGATIVO` o, sin conexión, sin condición.

Reglas citadas: STK-03, STK-05, STK-06, CST-12, INV-12.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql

from app.core.clock import FixedClock
from app.modules.costeo.models import CostoProducto
from app.modules.stock import service
from app.modules.stock.domain.errores import StockInsuficienteError
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.models import StockMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.producto_id = crear_producto_sql(sesion, self.org)
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

    def mover(
        self,
        *lineas: LineaDeMovimiento,
        permitir_negativo: bool = False,
        negativo_sin_condicion: bool = False,
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
            negativo_sin_condicion=negativo_sin_condicion,
        )

    def linea(self, cantidad: int, tipo: str, *, costo: str | None = None) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=self.producto_id,
            ubicacion_id=self.deposito_id,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo="VENTA" if tipo == "VENTA" else tipo,
            origen_id=uuid4(),
        )

    def compra(self, cantidad: int, costo: str) -> None:
        self.mover(self.linea(cantidad, "COMPRA", costo=costo))

    def venta(self, cantidad: int, **opciones: bool) -> list[service.ResultadoDeMovimiento]:
        return self.mover(self.linea(-cantidad, "VENTA"), **opciones)

    def saldo(self) -> int:
        return service.obtener_saldo(
            self.org, self.sesion, producto_id=self.producto_id, ubicacion_id=self.deposito_id
        )

    def costo(self) -> CostoProducto:
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == self.producto_id,
            )
            .execution_options(populate_existing=True)
        ).one()

    def movimientos(self) -> int:
        return int(
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- valorización al promedio (CST-12, STK-03) -------------------------------------------


def test_cst12_la_venta_con_saldo_suficiente_se_valoriza_al_promedio_sin_cambiarlo(
    entorno: Entorno,
) -> None:
    """Escenario "Venta con saldo suficiente": 48 botellas a $1.050, egreso de 15."""
    entorno.compra(48, "1050")

    (resultado,) = entorno.venta(15)

    assert resultado.movimiento.tipo == "VENTA"
    assert resultado.movimiento.cantidad_base == -15
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    assert resultado.saldo == 33
    assert resultado.saldo_negativo is False
    assert entorno.saldo() == 33
    costo = entorno.costo()
    assert (costo.stock_total, costo.costo_promedio) == (33, Decimal("1050.000000"))


def test_cst12_otra_venta_con_otro_promedio_se_valoriza_al_promedio_de_ese_momento(
    entorno: Entorno,
) -> None:
    """Triangula: dos compras a distinto costo dejan un promedio de $1.133,333333 y la venta
    lo usa; el promedio tampoco cambia."""
    entorno.compra(120, "1050")
    entorno.venta(72)
    entorno.compra(60, "1200")  # 48 a 1050 + 60 a 1200 -> 1133.333333

    (resultado,) = entorno.venta(10)

    assert resultado.movimiento.costo_unitario == Decimal("1133.333333")
    assert entorno.costo().costo_promedio == Decimal("1133.333333")
    assert entorno.costo().stock_total == 98


def test_cst12_sin_promedio_el_costo_del_egreso_es_nulo(entorno: Entorno) -> None:
    """Un producto sin ingresos con costo no tiene promedio: el egreso se guarda con costo
    nulo (el rechazo con conexión, `PRODUCTO_SIN_COSTO`, es del servicio de ventas)."""
    (resultado,) = entorno.venta(3, negativo_sin_condicion=True)

    assert resultado.movimiento.costo_unitario is None
    assert resultado.saldo == -3


# --- saldo negativo (STK-05, STK-06) -------------------------------------------------------


def test_stk05_sin_permiso_una_venta_que_deja_negativo_se_rechaza_sin_escribir(
    entorno: Entorno,
) -> None:
    """Escenario "Negativo sin permiso": 48 botellas, venta de 50."""
    entorno.compra(48, "1050")
    antes = entorno.movimientos()

    with pytest.raises(StockInsuficienteError) as error:
        entorno.venta(50)

    assert error.value.codigo == "STOCK_INSUFICIENTE"
    assert error.value.extension == {
        "producto_id": str(entorno.producto_id),
        "ubicacion_id": str(entorno.deposito_id),
    }
    assert entorno.saldo() == 48
    assert entorno.movimientos() == antes
    assert entorno.costo().stock_total == 48


def test_stk05_con_permiso_la_venta_deja_el_saldo_negativo_y_lo_marca(entorno: Entorno) -> None:
    """Escenario "Negativo con permiso": saldo -2 con costo congelado $1.050."""
    entorno.compra(48, "1050")

    (resultado,) = entorno.venta(50, permitir_negativo=True)

    assert resultado.saldo == -2
    assert resultado.saldo_negativo is True
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    assert entorno.costo().stock_total == -2


def test_stk05_con_permiso_pero_con_saldo_suficiente_no_marca_negativo(entorno: Entorno) -> None:
    entorno.compra(48, "1050")

    (resultado,) = entorno.venta(10, permitir_negativo=True)

    assert (resultado.saldo, resultado.saldo_negativo) == (38, False)


def test_stk06_sin_conexion_la_venta_se_aplica_sin_condicion_y_marca_el_negativo(
    entorno: Entorno,
) -> None:
    """Escenario "Negativo sin conexión": sin permiso y con modo sin condición."""
    entorno.compra(48, "1050")

    (resultado,) = entorno.venta(50, negativo_sin_condicion=True)

    assert resultado.saldo == -2
    assert resultado.saldo_negativo is True
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")


# --- lo que no cambia (STK-05, ADR-048) -----------------------------------------------------


@pytest.mark.parametrize(
    "opciones", [{"permitir_negativo": True}, {"negativo_sin_condicion": True}]
)
def test_stk05_el_permiso_y_el_modo_sin_condicion_no_alcanzan_a_un_ajuste(
    entorno: Entorno, opciones: dict[str, bool]
) -> None:
    """Escenario "El permiso no alcanza a un ajuste": un ajuste negativo que deja -2 sigue
    rechazado con `STOCK_INSUFICIENTE`, con el permiso o en modo sin condición."""
    entorno.compra(48, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-50, "AJUSTE"), **opciones)

    assert entorno.saldo() == 48


def test_stk05_el_modo_sin_condicion_no_alcanza_a_la_salida_de_una_transferencia(
    entorno: Entorno,
) -> None:
    entorno.compra(48, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-50, "TRANSFERENCIA_SALIDA"), negativo_sin_condicion=True)
