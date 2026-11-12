"""Change 18a, tarea 2.1: propiedades del motor de cálculo de la venta con Hypothesis (sin base
de datos; `docs/02-arquitectura.md` §15). Citan INV-14, VTA-04, TR-03.

Para ventas válidas generadas en modo `A`: el total es la suma de netos más la suma de IVA y el
IVA es cero (a); ningún neto es negativo y cada neto es el bruto menos sus descuentos (b); el
total no depende del orden de las líneas (c)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.ventas.domain.calculo import LineaCalculo, calcular_venta

_PRECIOS = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("99999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)
_ALICUOTAS = st.sampled_from(
    [Decimal("0.000000"), Decimal("0.105000"), Decimal("0.210000"), Decimal("0.270000")]
)
_PORCENTAJES = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)


@st.composite
def _lineas(draw: st.DrawFn) -> list[LineaCalculo]:
    cantidad = draw(st.integers(min_value=1, max_value=8))
    return [
        LineaCalculo(
            id=f"l-{posicion}",
            precio_referencia=draw(_PRECIOS),
            unidades_referencia=draw(st.integers(min_value=1, max_value=24)),
            cantidad_base=draw(st.integers(min_value=1, max_value=500)),
            alicuota=draw(_ALICUOTAS),
            producto_id=f"prod-{posicion}",
            categoria_id="cat",
            marca_id="marca",
            descuento_manual=draw(st.one_of(st.none(), _PORCENTAJES)),
        )
        for posicion in range(cantidad)
    ]


@settings(max_examples=200, deadline=None)
@given(lineas=_lineas(), general=st.one_of(st.none(), _PORCENTAJES))
def test_inv14_el_total_es_la_suma_de_netos_mas_la_suma_de_iva(
    lineas: list[LineaCalculo], general: Decimal | None
) -> None:
    resultado = calcular_venta("A", lineas, [], general)

    assert resultado.total_neto == sum((linea.neto for linea in resultado.lineas), Decimal("0.00"))
    assert resultado.total_iva == sum(
        (linea.importe_iva for linea in resultado.lineas), Decimal("0.00")
    )
    assert resultado.total == resultado.total_neto + resultado.total_iva
    assert all(linea.importe_iva == Decimal("0.00") for linea in resultado.lineas)


@settings(max_examples=200, deadline=None)
@given(lineas=_lineas(), general=st.one_of(st.none(), _PORCENTAJES))
def test_ningun_neto_es_negativo_y_cada_neto_es_el_bruto_menos_sus_descuentos(
    lineas: list[LineaCalculo], general: Decimal | None
) -> None:
    resultado = calcular_venta("A", lineas, [], general)

    for linea in resultado.lineas:
        assert linea.neto >= 0
        assert linea.neto == linea.bruto - linea.descuento_total
        assert linea.descuento_total == sum((d.importe for d in linea.descuentos), Decimal("0.00"))


@settings(max_examples=100, deadline=None)
@given(lineas=_lineas(), general=st.one_of(st.none(), _PORCENTAJES))
def test_el_total_no_depende_del_orden_de_las_lineas(
    lineas: list[LineaCalculo], general: Decimal | None
) -> None:
    directo = calcular_venta("A", lineas, [], general)
    invertido = calcular_venta("A", list(reversed(lineas)), [], general)

    assert directo.total == invertido.total
    assert directo.total_neto == invertido.total_neto
