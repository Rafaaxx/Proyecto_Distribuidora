"""Change 16, tarea 2.2: acciones del motor de descuentos (spec `descuentos/motor-de-descuentos`,
requisitos "El descuento porcentual se calcula y redondea por línea" y "El importe fijo se reparte
entre las líneas elegibles"; DSC-04, DSC-07, TR-03, INV-03; `design.md` D10)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.acciones import descuento_porcentual, repartir_importe_fijo


def _d(*valores: str) -> list[Decimal]:
    return [Decimal(v) for v in valores]


# --- porcentaje por línea ----------------------------------------------------------------------


def test_porcentaje_se_redondea_por_linea_mitad_hacia_arriba() -> None:
    # 5% de 1433.33 = 71.6665 -> 71.67
    assert descuento_porcentual(_d("1433.33"), Decimal("0.05")) == _d("71.67")


def test_porcentaje_se_redondea_linea_por_linea_no_sobre_el_total() -> None:
    # Por línea: 71.67 + 71.67 = 143.34; sobre el total 2866.66 daría 143.33.
    importes = _d("1433.33", "1433.33")
    assert descuento_porcentual(importes, Decimal("0.05")) == _d("71.67", "71.67")


def test_porcentaje_cinco_sobre_250000() -> None:
    assert descuento_porcentual(_d("250000.00"), Decimal("0.050000")) == _d("12500.00")


def test_porcentaje_que_redondea_a_cero_devuelve_cero() -> None:
    assert descuento_porcentual(_d("0.05"), Decimal("0.05")) == _d("0.00")


def test_porcentaje_cien_por_cien_deja_neto_cero() -> None:
    assert descuento_porcentual(_d("4300.00"), Decimal("1")) == _d("4300.00")


def test_porcentaje_de_punto_flotante_se_rechaza() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        descuento_porcentual(_d("100.00"), 0.05)  # type: ignore[arg-type]


# --- importe fijo ------------------------------------------------------------------------------


def test_importe_fijo_reparto_proporcional_sin_remanente() -> None:
    partes = repartir_importe_fijo(_d("31250.00", "4300.00"), Decimal("1000.00"))
    assert partes == _d("879.04", "120.96")


def test_importe_fijo_remanente_negativo_va_a_la_linea_de_mayor_importe() -> None:
    partes = repartir_importe_fijo(_d("31250.00", "4300.00", "1433.33"), Decimal("1000.00"))
    assert partes == _d("844.97", "116.27", "38.76")
    assert sum(partes) == Decimal("1000.00")


def test_importe_fijo_remanente_va_a_la_mayor_aunque_no_sea_la_primera() -> None:
    partes = repartir_importe_fijo(_d("1433.33", "4300.00", "31250.00"), Decimal("1000.00"))
    assert partes == _d("38.76", "116.27", "844.97")


def test_importe_fijo_remanente_positivo_con_empate_va_a_la_primera() -> None:
    partes = repartir_importe_fijo(_d("8600.00", "8600.00", "8600.00"), Decimal("100.00"))
    assert partes == _d("33.34", "33.33", "33.33")


def test_importe_fijo_mayor_que_la_suma_se_topa_en_la_suma() -> None:
    assert repartir_importe_fijo(_d("4300.00"), Decimal("5000.00")) == _d("4300.00")


def test_importe_fijo_topado_con_dos_lineas_las_descuenta_enteras() -> None:
    partes = repartir_importe_fijo(_d("100.00", "50.00"), Decimal("1000.00"))
    assert partes == _d("100.00", "50.00")


def test_importe_fijo_sobre_importes_en_cero_no_descuenta_nada() -> None:
    assert repartir_importe_fijo(_d("0.00", "0.00"), Decimal("10.00")) == _d("0.00", "0.00")


def test_importe_fijo_de_punto_flotante_se_rechaza() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        repartir_importe_fijo(_d("100.00"), 10.5)  # type: ignore[arg-type]
