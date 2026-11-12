"""Change 16, tarea 2.1: condición de volumen del motor de descuentos (spec
`descuentos/motor-de-descuentos`, requisito "La condición de volumen se evalúa sobre las líneas
elegibles"; DSC-02, DSC-03, INV-04, TR-03). Aritmética exacta: las cajas equivalentes se suman como
fracciones enteras, sin redondear (`design.md` D5)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from app.modules.descuentos.domain.condicion import (
    cumple_condicion,
    lineas_elegibles,
    medir,
)
from app.modules.descuentos.domain.tipos import AlcanceRegla, LineaVenta, ReglaDescuento


def _linea(
    id: str = "l1",
    *,
    bruto: str = "100.00",
    cantidad_base: int = 1,
    unidades_referencia: int = 1,
    producto: str = "p1",
    categoria: str = "c1",
    marca: str = "m1",
) -> LineaVenta:
    return LineaVenta(
        id=id,
        bruto=Decimal(bruto),
        cantidad_base=cantidad_base,
        unidades_referencia=unidades_referencia,
        producto_id=producto,
        categoria_id=categoria,
        marca_id=marca,
        descuento_manual=None,
    )


def _regla(
    *,
    tipo: str = "VOLUMEN_OPERACION",
    medida: str = "UNIDADES_BASE",
    operador: str = "GTE",
    umbral: str = "1",
    alcances: tuple[AlcanceRegla, ...] = (),
) -> ReglaDescuento:
    return ReglaDescuento(
        id="r1",
        tipo=tipo,  # type: ignore[arg-type]
        medida=medida,  # type: ignore[arg-type]
        operador=operador,  # type: ignore[arg-type]
        umbral=Decimal(umbral),
        accion_tipo="PORCENTAJE",
        accion_porcentaje=Decimal("0.050000"),
        accion_importe=None,
        acumulable=False,
        prioridad=1,
        alcances=alcances,
    )


# --- líneas elegibles (DSC-02, D6) -------------------------------------------------------------


def test_regla_de_operacion_toma_todas_las_lineas() -> None:
    lineas = [_linea("a", producto="p1"), _linea("b", producto="p2")]
    assert [x.id for x in lineas_elegibles(_regla(), lineas)] == ["a", "b"]


def test_regla_de_alcance_toma_la_union_de_producto_categoria_y_marca() -> None:
    regla = _regla(
        tipo="VOLUMEN_ALCANCE",
        alcances=(AlcanceRegla("CATEGORIA", "vinos"), AlcanceRegla("MARCA", "sur")),
    )
    vino = _linea("vino", categoria="vinos", marca="otra")
    cerveza = _linea("cerveza", categoria="cervezas", marca="sur")
    alfajor = _linea("alfajor", categoria="golosinas", marca="dulce")

    assert [x.id for x in lineas_elegibles(regla, [vino, cerveza, alfajor])] == ["vino", "cerveza"]


def test_regla_de_alcance_por_producto() -> None:
    regla = _regla(tipo="VOLUMEN_ALCANCE", alcances=(AlcanceRegla("PRODUCTO", "pa"),))
    lineas = [_linea("a", producto="pa"), _linea("b", producto="pb")]
    assert [x.id for x in lineas_elegibles(regla, lineas)] == ["a"]


def test_alcance_de_un_tipo_no_se_confunde_con_otro_tipo() -> None:
    # El identificador "x" como marca no hace elegible a un producto cuyo id es "x".
    regla = _regla(tipo="VOLUMEN_ALCANCE", alcances=(AlcanceRegla("MARCA", "x"),))
    assert lineas_elegibles(regla, [_linea("a", producto="x")]) == []


# --- medidas (DSC-03, D5) ----------------------------------------------------------------------


def test_medida_unidades_base_suma_las_cantidades() -> None:
    lineas = [_linea(cantidad_base=60), _linea("b", cantidad_base=5)]
    assert medir("UNIDADES_BASE", lineas) == Fraction(65)


def test_medida_importe_bruto_suma_los_brutos_exactos() -> None:
    lineas = [_linea(bruto="31250.00"), _linea("b", bruto="0.01")]
    assert medir("IMPORTE_BRUTO", lineas) == Fraction(3125001, 100)


def test_cajas_equivalentes_de_19_cajas_y_5_unidades_son_119_sextos() -> None:
    lineas = [
        _linea(cantidad_base=114, unidades_referencia=6),
        _linea("b", cantidad_base=5, unidades_referencia=6),
    ]
    assert medir("CAJAS_EQUIVALENTES", lineas) == Fraction(119, 6)


def test_cajas_equivalentes_suma_cajas_de_distinto_tamano() -> None:
    lineas = [
        _linea(cantidad_base=3, unidades_referencia=6),
        _linea("b", cantidad_base=6, unidades_referencia=12),
    ]
    assert medir("CAJAS_EQUIVALENTES", lineas) == Fraction(1)


def test_tres_tercios_de_caja_suman_exactamente_uno() -> None:
    lineas = [_linea(x, cantidad_base=2, unidades_referencia=6) for x in "abc"]
    assert medir("CAJAS_EQUIVALENTES", lineas) == 1


# --- condición (operadores y umbral) -----------------------------------------------------------


@pytest.mark.parametrize(
    ("operador", "cantidad", "esperado"),
    [
        ("GTE", 120, True),  # 20 cajas alcanzan "≥ 20"
        ("GTE", 119, False),  # 19,83 no
        ("GT", 120, False),  # 20 exactas no superan "> 20"
        ("GT", 126, True),  # 21 cajas sí
    ],
)
def test_operadores_sobre_cajas_equivalentes(operador: str, cantidad: int, esperado: bool) -> None:
    regla = _regla(medida="CAJAS_EQUIVALENTES", operador=operador, umbral="20")
    lineas = [_linea(cantidad_base=cantidad, unidades_referencia=6)]
    assert cumple_condicion(regla, lineas) is esperado


def test_tres_tercios_cumplen_gte_uno_pero_no_gt_uno() -> None:
    lineas = [_linea(x, cantidad_base=2, unidades_referencia=6) for x in "abc"]
    assert cumple_condicion(_regla(medida="CAJAS_EQUIVALENTES", umbral="1"), lineas) is True
    assert (
        cumple_condicion(_regla(medida="CAJAS_EQUIVALENTES", operador="GT", umbral="1"), lineas)
        is False
    )


def test_umbral_con_cuatro_decimales_se_compara_exacto() -> None:
    # 1/3 = 0,3333...: no alcanza 0,3334 pero sí 0,3333.
    lineas = [_linea(cantidad_base=2, unidades_referencia=6)]
    alcanza = _regla(medida="CAJAS_EQUIVALENTES", umbral="0.3333")
    no_alcanza = _regla(medida="CAJAS_EQUIVALENTES", umbral="0.3334")
    assert cumple_condicion(alcanza, lineas) is True
    assert cumple_condicion(no_alcanza, lineas) is False


@pytest.mark.parametrize(
    ("operador", "umbral", "esperado"),
    [("GTE", "31250", True), ("GT", "31250", False), ("GTE", "31250.01", False)],
)
def test_importe_bruto_es_inclusivo_con_gte(operador: str, umbral: str, esperado: bool) -> None:
    regla = _regla(medida="IMPORTE_BRUTO", operador=operador, umbral=umbral)
    assert cumple_condicion(regla, [_linea(bruto="31250.00")]) is esperado


def test_regla_de_alcance_mide_solo_sus_lineas() -> None:
    regla = _regla(
        tipo="VOLUMEN_ALCANCE",
        medida="CAJAS_EQUIVALENTES",
        umbral="10",
        alcances=(AlcanceRegla("PRODUCTO", "pa"),),
    )
    a = _linea("a", producto="pa", cantidad_base=48, unidades_referencia=6)  # 8 cajas
    b = _linea("b", producto="pb", cantidad_base=60, unidades_referencia=6)  # 10 cajas
    assert cumple_condicion(regla, [a, b]) is False


def test_regla_sin_lineas_elegibles_no_aplica_aunque_el_umbral_sea_cero() -> None:
    regla = _regla(
        tipo="VOLUMEN_ALCANCE",
        umbral="0",
        alcances=(AlcanceRegla("PRODUCTO", "no-esta"),),
    )
    assert cumple_condicion(regla, [_linea()]) is False
