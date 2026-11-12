"""Tarea 5.1 (change 19; spec `stock/libro-de-stock` y `costeo/costo-promedio`; `design.md` D5,
D6, D7): el ingreso `ANULACION_VENTA` de `stock.registrar_movimientos` contra PostgreSQL real.

Lleva el costo congelado de la línea vendida y recalcula el promedio (CST-11), o sube el stock
total sin recalcular y con costo nulo si la línea se vendió sin costo (CST-12); acepta producto
inactivo (CAT-05) pero no ubicación inactiva y respeta la toma de ubicación (STK-09).

Reglas citadas: STK-03, CST-11, CST-12, CAT-05, STK-09, INV-01, ADR-058.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
)

from app.core.clock import FixedClock
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import service
from app.modules.stock.domain.errores import (
    ProductoInactivoError,
    TipoDeMovimientoInvalidoError,
    UbicacionInactivaError,
    UbicacionTomadaError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.models import StockMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_FIXTURE_CST11 = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "calculo"
    / "cst-11-costo-promedio.json"
)
_CASOS_DE_ANULACION_DE_VENTA: list[dict[str, Any]] = [
    caso
    for caso in json.loads(_FIXTURE_CST11.read_text(encoding="utf-8"))
    if caso["id"].startswith("CST11-anulacion-venta")
]

MOMENTO = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.otro_usuario_id, self.otro_dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org
        )
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua = crear_producto_sql(sesion, self.org, nombre="Agua B")
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

    def mover(
        self,
        *lineas: LineaDeMovimiento,
        puede_tomada: bool = False,
        permitir_negativo: bool = False,
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
            puede_operar_ubicacion_tomada=puede_tomada,
            permitir_negativo=permitir_negativo,
        )

    def linea(
        self,
        cantidad: int,
        tipo: str,
        *,
        costo: str | None = None,
        producto: UUID | None = None,
        ubicacion: UUID | None = None,
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=producto or self.vino,
            ubicacion_id=ubicacion or self.deposito,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo="VENTA" if tipo in {"VENTA", "ANULACION_VENTA"} else tipo,
            origen_id=uuid4(),
        )

    def compra(self, cantidad: int, costo: str, producto: UUID | None = None) -> None:
        self.mover(self.linea(cantidad, "COMPRA", costo=costo, producto=producto))

    def anular(
        self,
        cantidad: int,
        costo: str | None,
        *,
        producto: UUID | None = None,
        ubicacion: UUID | None = None,
        puede_tomada: bool = False,
    ) -> service.ResultadoDeMovimiento:
        (resultado,) = self.mover(
            self.linea(
                cantidad, "ANULACION_VENTA", costo=costo, producto=producto, ubicacion=ubicacion
            ),
            puede_tomada=puede_tomada,
        )
        return resultado

    def saldo(self, producto: UUID | None = None, ubicacion: UUID | None = None) -> int:
        return service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=producto or self.vino,
            ubicacion_id=ubicacion or self.deposito,
        )

    def costo(self, producto: UUID | None = None) -> CostoProducto:
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == (producto or self.vino),
            )
            .execution_options(populate_existing=True)
        ).one()

    def historia(self, producto: UUID | None = None) -> list[CostoProductoMov]:
        return list(
            self.sesion.scalars(
                select(CostoProductoMov)
                .where(
                    CostoProductoMov.organizacion_id == self.org,
                    CostoProductoMov.producto_id == (producto or self.vino),
                )
                .order_by(CostoProductoMov.registered_at, CostoProductoMov.id)
                .execution_options(populate_existing=True)
            ).all()
        )

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


# --- ingreso con costo (STK-03, CST-11) ---------------------------------------------------


def test_cst11_el_ingreso_con_costo_recalcula_el_promedio_y_deja_historia(
    entorno: Entorno,
) -> None:
    """Escenario "Ingreso con costo" y el ejemplo de D5 (`01` §6): stock 108 a $1.133,333333, se
    anula una venta de 72 a $1.050 -> promedio $1.100,000000 con historia `ANULACION_VENTA`."""
    entorno.compra(48, "1050")
    entorno.compra(60, "1200")  # 48 a 1050 + 60 a 1200 -> 108 a 1133.333333
    assert entorno.costo().costo_promedio == Decimal("1133.333333")
    filas_previas = len(entorno.historia())

    resultado = entorno.anular(72, "1050.000000")

    assert resultado.movimiento.tipo == "ANULACION_VENTA"
    assert resultado.movimiento.cantidad_base == 72
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    assert resultado.saldo == 180
    costo = entorno.costo()
    assert (costo.stock_total, costo.costo_promedio) == (180, Decimal("1100.000000"))
    historia = entorno.historia()
    assert len(historia) == filas_previas + 1
    ultima = historia[-1]
    assert ultima.origen_tipo == "ANULACION_VENTA"
    assert ultima.stock_nuevo == 180
    assert ultima.promedio_nuevo == Decimal("1100.000000")


def test_cst11_con_stock_total_previo_cero_el_promedio_pasa_al_costo_de_la_linea(
    entorno: Entorno,
) -> None:
    """Triangula: sin stock previo (la venta lo dejó en 0) el promedio es el costo de la línea."""
    entorno.compra(72, "900")
    entorno.mover(entorno.linea(-72, "VENTA"))
    assert entorno.costo().stock_total == 0

    entorno.anular(72, "1050.000000")

    costo = entorno.costo()
    assert (costo.stock_total, costo.costo_promedio) == (72, Decimal("1050.000000"))
    assert entorno.saldo() == 72


# --- ingreso sin costo (CST-12) ------------------------------------------------------------


def test_cst12_el_ingreso_sin_costo_sube_el_stock_sin_recalcular_ni_dejar_historia(
    entorno: Entorno,
) -> None:
    """Escenario "Ingreso sin costo": Agua B vendida sin costo; el saldo y el stock total suben
    12, el promedio no cambia, no hay historia nueva y el movimiento queda con costo nulo."""
    entorno.compra(30, "500", producto=entorno.agua)
    historia_previa = len(entorno.historia(entorno.agua))

    resultado = entorno.anular(12, None, producto=entorno.agua)

    assert resultado.movimiento.costo_unitario is None
    assert resultado.movimiento.cantidad_base == 12
    assert entorno.saldo(entorno.agua) == 42
    costo = entorno.costo(entorno.agua)
    assert (costo.stock_total, costo.costo_promedio) == (42, Decimal("500.000000"))
    assert len(entorno.historia(entorno.agua)) == historia_previa


def test_cst12_el_ingreso_sin_costo_de_un_producto_sin_promedio_deja_el_promedio_nulo(
    entorno: Entorno,
) -> None:
    """Triangula: un producto que nunca tuvo costo sube el stock y sigue sin promedio."""
    entorno.anular(5, None, producto=entorno.agua)

    costo = entorno.costo(entorno.agua)
    assert (costo.stock_total, costo.costo_promedio) == (5, None)
    assert entorno.historia(entorno.agua) == []


def test_cst11_cst12_un_mismo_producto_en_dos_lineas_son_dos_ingresos_en_orden(
    entorno: Entorno,
) -> None:
    """D5: dos líneas del mismo producto (una con costo y otra sin él) en un solo movimiento."""
    entorno.compra(10, "1000")

    resultados = entorno.mover(
        entorno.linea(10, "ANULACION_VENTA", costo="1200.000000"),
        entorno.linea(5, "ANULACION_VENTA", costo=None),
    )

    assert [r.movimiento.costo_unitario for r in resultados] == [Decimal("1200.000000"), None]
    assert entorno.saldo() == 25
    costo = entorno.costo()
    assert (costo.stock_total, costo.costo_promedio) == (25, Decimal("1100.000000"))


# --- cantidad negativa (INV-01) ------------------------------------------------------------


def test_inv01_una_anulacion_de_venta_con_cantidad_negativa_se_rechaza_y_no_escribe_nada(
    entorno: Entorno,
) -> None:
    entorno.compra(10, "1000")
    antes = entorno.movimientos()

    with pytest.raises(TipoDeMovimientoInvalidoError):
        entorno.anular(-5, None)

    assert entorno.movimientos() == antes
    assert entorno.saldo() == 10


# --- maestros inactivos (CAT-05, D7) ----------------------------------------------------------


def test_cat05_la_anulacion_de_venta_acepta_un_producto_inactivo(entorno: Entorno) -> None:
    entorno.compra(10, "1000")
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino)

    resultado = entorno.anular(6, "1000.000000")

    assert resultado.saldo == 16


def test_cat05_otro_tipo_de_ingreso_sigue_exigiendo_producto_activo(entorno: Entorno) -> None:
    # Escenario: "Otro tipo sigue exigiendo producto activo" (stock/libro-de-stock)
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino)

    with pytest.raises(ProductoInactivoError):
        entorno.compra(10, "1000")


def test_una_ubicacion_inactiva_rechaza_la_anulacion_de_venta(entorno: Entorno) -> None:
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Vieja", activo=False)
    antes = entorno.movimientos()

    with pytest.raises(UbicacionInactivaError):
        entorno.anular(6, "1000.000000", ubicacion=inactiva)

    assert entorno.movimientos() == antes


# --- toma de ubicación (STK-09, D6) ---------------------------------------------------------


def _camioneta_tomada(entorno: Entorno) -> tuple[UUID, UUID]:
    camioneta = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
    )
    jornada = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.otro_usuario_id,
        dispositivo_id=entorno.otro_dispositivo_id,
        ubicacion_id=camioneta,
    )
    return camioneta, jornada


def test_stk09_la_ubicacion_tomada_por_otra_jornada_rechaza_sin_liberar_ubicacion(
    entorno: Entorno,
) -> None:
    """Escenario "Ubicación tomada sin permiso de excepción": `UBICACION_TOMADA` y nada escrito."""
    camioneta, _ = _camioneta_tomada(entorno)
    antes = entorno.movimientos()

    with pytest.raises(UbicacionTomadaError):
        entorno.anular(6, "1000.000000", ubicacion=camioneta)

    assert entorno.movimientos() == antes


def test_stk09_con_liberar_ubicacion_ingresa_sin_jornada_y_deja_la_constancia(
    entorno: Entorno,
) -> None:
    """D6: por excepción el movimiento no lleva `jornada_id` y el resultado trae la jornada que
    tenía tomada la ubicación (para la constancia de la auditoría)."""
    camioneta, jornada = _camioneta_tomada(entorno)

    resultado = entorno.anular(6, "1000.000000", ubicacion=camioneta, puede_tomada=True)

    assert resultado.movimiento.jornada_id is None
    assert resultado.jornada_tomada_id == jornada
    assert entorno.saldo(ubicacion=camioneta) == 6


# --- los casos compartidos `cst-11` de anulación de venta contra el servicio real -----------


def test_los_casos_compartidos_de_anulacion_de_venta_se_descubren() -> None:
    assert len(_CASOS_DE_ANULACION_DE_VENTA) >= 4


@pytest.mark.parametrize(
    "caso", _CASOS_DE_ANULACION_DE_VENTA, ids=[c["id"] for c in _CASOS_DE_ANULACION_DE_VENTA]
)
def test_cst11_cst12_los_casos_compartidos_pasan_contra_el_servicio_real(
    entorno: Entorno, caso: dict[str, Any]
) -> None:
    """Se arma el estado previo del caso (stock total y promedio) por el libro y se anula con
    `ANULACION_VENTA`: el promedio y el stock total salen como dice `salida_esperada`.

    Escenarios de `costeo/costo-promedio`: "Ejemplo de CST-11", "Stock total previo en cero",
    "Stock total previo negativo" y "Línea sin costo" (los casos `stock_previo` 0 y −5 y la línea
    sin costo de `cst-11-costo-promedio.json`)."""
    entrada, esperado = caso["entrada"], caso["salida_esperada"]
    stock_previo, promedio_previo = entrada["stock_previo"], entrada["promedio_previo"]
    if promedio_previo is not None:
        cantidad_comprada = max(stock_previo, 0) + (10 if stock_previo < 0 else 0)
        entorno.compra(cantidad_comprada, promedio_previo)
        if stock_previo < 0:  # vende de más con permiso: el promedio no cambia
            entorno.mover(
                entorno.linea(stock_previo - cantidad_comprada, "VENTA"), permitir_negativo=True
            )
        assert entorno.costo().stock_total == stock_previo

    entorno.anular(entrada["cantidad"], entrada["costo_ingreso"])

    costo = entorno.costo()
    assert costo.stock_total == esperado["stock_nuevo"]
    nuevo = esperado["promedio_nuevo"]
    assert costo.costo_promedio == (None if nuevo is None else Decimal(nuevo))
