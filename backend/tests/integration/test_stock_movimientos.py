"""Change 11, tarea 7.1: egresos `ANULACION_COMPRA` en `stock.registrar_movimientos`
contra PostgreSQL real (CMP-06, CMP-07, STK-05, CAT-05, `design.md` D9, D10, D11).

Reglas citadas: CMP-06, CMP-07, STK-03, STK-05, CST-13, CAT-05, INV-12.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql, desactivar_producto_sql

from app.core.clock import FixedClock
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import service
from app.modules.stock.domain.errores import (
    CostoInvalidoError,
    ProductoInactivoError,
    StockInsuficienteError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.models import StockMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.producto_id = crear_producto_sql(sesion, self.org)
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

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

    def ingreso(self, cantidad: int, costo: str) -> LineaDeMovimiento:
        return self.linea(cantidad, costo, "COMPRA")

    def linea(
        self, cantidad: int, costo: str | None, tipo: str, *, producto_id: UUID | None = None
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=producto_id or self.producto_id,
            ubicacion_id=self.deposito_id,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo=tipo,
            origen_id=uuid4(),
        )

    def reversion(self, cantidad: int, costo: str | None) -> LineaDeMovimiento:
        return self.linea(-cantidad, costo, "ANULACION_COMPRA")

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

    def historia(self) -> list[CostoProductoMov]:
        return list(
            self.sesion.scalars(
                select(CostoProductoMov)
                .where(CostoProductoMov.organizacion_id == self.org)
                .order_by(CostoProductoMov.registered_at, CostoProductoMov.id)
            )
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- delegación en costeo y costo en el kardex (CMP-06, D9) --------------------


def test_el_egreso_anulacion_compra_revierte_el_promedio_y_queda_con_su_costo(
    entorno: Entorno,
) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))
    entorno.mover(entorno.ingreso(60, "1100"))

    (resultado,) = entorno.mover(entorno.reversion(60, "1100"))

    movimiento = resultado.movimiento
    assert (movimiento.tipo, movimiento.cantidad_base) == ("ANULACION_COMPRA", -60)
    assert movimiento.costo_unitario == Decimal("1100.000000")
    assert resultado.saldo == 60
    assert resultado.saldo_negativo is False
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1000.000000"), 60)
    reversion = entorno.historia()[-1]
    assert (reversion.origen_tipo, reversion.cantidad) == ("ANULACION_COMPRA", -60)
    assert reversion.recalculado is True


def test_el_egreso_anulacion_compra_sin_recalculo_deja_la_fila_de_historia(
    entorno: Entorno,
) -> None:
    entorno.mover(entorno.ingreso(48, "1050"))

    entorno.mover(entorno.reversion(48, "1100"))

    reversion = entorno.historia()[-1]
    assert reversion.recalculado is False
    assert reversion.promedio_nuevo == Decimal("1050.000000")
    assert entorno.costo().stock_total == 0


def test_un_egreso_anulacion_compra_sin_costo_es_costo_invalido(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))

    with pytest.raises(CostoInvalidoError):
        entorno.mover(entorno.reversion(10, None))

    assert entorno.saldo() == 60


def test_un_egreso_de_venta_sigue_valorizandose_al_promedio_sin_historia(
    entorno: Entorno,
) -> None:
    """Red de seguridad del 09: el resto de los egresos conserva su comportamiento."""
    entorno.mover(entorno.ingreso(60, "1000"))

    (resultado,) = entorno.mover(entorno.linea(-10, None, "VENTA"))

    assert resultado.movimiento.costo_unitario == Decimal("1000.000000")
    assert len(entorno.historia()) == 1


# --- stock negativo con permiso (CMP-07, D10) ---------------------------------


def test_sin_permiso_el_egreso_que_no_alcanza_es_stock_insuficiente(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(48, "1050"))

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.reversion(60, "1100"))

    assert entorno.saldo() == 48
    assert entorno.costo().stock_total == 48


def test_con_permiso_la_anulacion_deja_saldo_negativo_y_lo_marca(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(48, "1050"))

    (resultado,) = entorno.mover(entorno.reversion(60, "1100"), permitir_negativo=True)

    assert resultado.saldo == -12
    assert resultado.saldo_negativo is True
    assert entorno.saldo() == -12
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1050.000000"), -12)


def test_con_permiso_y_saldo_suficiente_no_marca_negativo(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))

    (resultado,) = entorno.mover(entorno.reversion(60, "1000"), permitir_negativo=True)

    assert (resultado.saldo, resultado.saldo_negativo) == (0, False)


@pytest.mark.parametrize("tipo", ["VENTA", "AJUSTE"])
def test_el_permiso_no_alcanza_a_los_egresos_de_otro_tipo(entorno: Entorno, tipo: str) -> None:
    entorno.mover(entorno.ingreso(10, "100"))

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-11, None, tipo), permitir_negativo=True)

    assert entorno.saldo() == 10


# La salida de transferencia SÍ admite stock negativo con permiso desde el change 14
# (`design.md` D1); lo prueba `test_stock_movimientos_transferencias_ajustes.py`.


# --- maestros inactivos (CAT-05, D11) -----------------------------------------


def test_la_reversion_admite_un_producto_inactivo(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)

    entorno.mover(entorno.reversion(60, "1000"))

    assert entorno.saldo() == 0


def test_otros_tipos_siguen_rechazando_un_producto_inactivo(entorno: Entorno) -> None:
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)

    with pytest.raises(ProductoInactivoError):
        entorno.mover(entorno.ingreso(10, "100"))


def test_una_ubicacion_inactiva_sigue_rechazando_la_reversion(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": entorno.deposito_id},
    )

    with pytest.raises(UbicacionInactivaError):
        entorno.mover(entorno.reversion(10, "1000"))


def test_el_libro_registra_un_movimiento_por_linea(entorno: Entorno) -> None:
    entorno.mover(entorno.ingreso(60, "1000"))
    entorno.mover(entorno.reversion(20, "1000"))

    tipos = list(
        entorno.sesion.scalars(
            select(StockMovimiento.tipo).where(StockMovimiento.organizacion_id == entorno.org)
        )
    )
    assert sorted(tipos) == ["ANULACION_COMPRA", "COMPRA"]
