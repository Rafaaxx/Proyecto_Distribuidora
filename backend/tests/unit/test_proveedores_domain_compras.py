"""Change 11, tareas 4.1 a 4.3: dominio puro de compras (`proveedores/domain/compras.py`).

Cálculo de línea y totales (CMP-02, `design.md` D5, sobre `calcular_costo_base`),
validación de condición, medios y fecha (CMP-01, CMP-03, INV-08, D1, D2, D6) y
comparación con el costo informado vigente (CMP-04, D7). Los casos de cálculo comunes
con TypeScript viven en `tests/fixtures_compartidos/test_cmp02_compra_fixtures.py`;
acá se fija el error exacto, el rango y las propiedades.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.proveedores.domain.compras import (
    MAXIMO_DE_LINEAS,
    CostoDeLinea,
    EntradaDeLinea,
    MedioDeEntrada,
    calcular_compra,
    calcular_linea,
    diferencias_de_costo,
    validar_fecha,
    validar_pago,
    validar_total_factura,
)
from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    CantidadInvalidaError,
    CompraSinLineasError,
    CondicionInvalidaError,
    FechaInvalidaError,
    ImporteInvalidoError,
    LineasInvalidasError,
    MediosNoSumanImporteError,
    ReferenciaObligatoriaError,
    ValorInvalidoError,
)


def linea(
    *,
    unidades: int = 6,
    cantidad: str = "1",
    valor: str = "6000.00",
    incluye_iva: bool = False,
    alicuota: str = "0.210000",
    bonificacion: str = "0",
) -> EntradaDeLinea:
    return EntradaDeLinea(
        unidades_presentacion=unidades,
        cantidad=Decimal(cantidad),
        valor=Decimal(valor),
        incluye_iva=incluye_iva,
        alicuota=Decimal(alicuota),
        bonificacion=Decimal(bonificacion),
    )


# --- 4.1: cálculo de línea -------------------------------------------------------------


def test_linea_caja_por_unidades_deriva_cantidad_base_costo_base_e_importe() -> None:
    calculada = calcular_linea(linea(unidades=6, cantidad="10", valor="6000.00"))

    assert calculada.cantidad_base == 60
    assert calculada.costo_base == Decimal("1000.000000")
    assert calculada.importe_neto == Decimal("60000.00")


def test_linea_con_iva_incluido_y_bonificacion_usa_la_formula_de_cst02() -> None:
    sin_bonificar = calcular_linea(linea(unidades=12, valor="18000.00", incluye_iva=True))
    bonificada = calcular_linea(linea(unidades=12, valor="18000.00", bonificacion="0.100000"))

    assert sin_bonificar.costo_base == Decimal("1239.669421")
    assert sin_bonificar.importe_neto == Decimal("14876.03")
    assert bonificada.costo_base == Decimal("1350.000000")
    assert bonificada.importe_neto == Decimal("16200.00")


def test_linea_importe_con_iva_sugerido_redondea_a_dos_decimales_por_linea() -> None:
    calculada = calcular_linea(linea(unidades=12, valor="18000.00", incluye_iva=True))

    assert calculada.importe_con_iva == Decimal("18000.00")


@pytest.mark.parametrize(
    ("cantidad", "esperada"),
    [("2.5", 15), ("0.5", 3), ("1.500", 9), ("10", 60), ("1E+1", 60)],
)
def test_cantidad_fraccionaria_que_da_unidades_enteras_es_valida(
    cantidad: str, esperada: int
) -> None:
    assert calcular_linea(linea(unidades=6, cantidad=cantidad)).cantidad_base == esperada


@pytest.mark.parametrize("cantidad", ["2.3", "0.1", "1.0001", "0", "-1", "0.000"])
def test_cantidad_invalida_se_rechaza(cantidad: str) -> None:
    with pytest.raises(CantidadInvalidaError) as error:
        calcular_linea(linea(unidades=6, cantidad=cantidad))

    assert error.value.codigo == "CANTIDAD_INVALIDA"


def test_cantidad_base_que_no_entra_en_un_entero_de_32_bits_se_rechaza() -> None:
    with pytest.raises(CantidadInvalidaError):
        calcular_linea(linea(unidades=1, cantidad="2147483648", valor="0.01"))
    maxima = calcular_linea(linea(unidades=1, cantidad="2147483647", valor="0.01"))
    assert maxima.cantidad_base == 2147483647


@pytest.mark.parametrize("valor", ["0.00", "-1.00", "6000.001", "0.001"])
def test_valor_invalido_se_rechaza(valor: str) -> None:
    with pytest.raises(ValorInvalidoError) as error:
        calcular_linea(linea(valor=valor))

    assert error.value.codigo == "VALOR_INVALIDO"


@pytest.mark.parametrize("bonificacion", ["1", "1.000000", "-0.000001", "0.1234567"])
def test_bonificacion_invalida_se_rechaza(bonificacion: str) -> None:
    with pytest.raises(BonificacionInvalidaError):
        calcular_linea(linea(bonificacion=bonificacion))


def test_costo_base_que_redondea_a_cero_se_rechaza() -> None:
    """ADR-039: el costo promedio es positivo; un costo base de 0,000000 no es un costo."""
    with pytest.raises(ValorInvalidoError):
        calcular_linea(linea(unidades=1_000_000, valor="0.01"))


# --- 4.1: totales de la compra ---------------------------------------------------------


def test_compra_del_criterio_2_suma_importes_netos_y_sugiere_el_iva() -> None:
    totales = calcular_compra(
        [
            linea(unidades=6, cantidad="10", valor="6000.00"),
            linea(unidades=1, cantidad="60", valor="1100.00"),
        ]
    )

    assert totales.total_neto == Decimal("126000.00")
    assert totales.total_factura_sugerido == Decimal("152460.00")
    assert [parte.cantidad_base for parte in totales.lineas] == [60, 60]


def test_compra_con_el_mismo_producto_en_dos_lineas_conserva_el_orden() -> None:
    totales = calcular_compra(
        [linea(unidades=6, cantidad="10"), linea(unidades=1, cantidad="60", valor="1100.00")]
    )

    assert [parte.costo_base for parte in totales.lineas] == [
        Decimal("1000.000000"),
        Decimal("1100.000000"),
    ]


def test_inv07_compra_sin_lineas_se_rechaza() -> None:
    with pytest.raises(CompraSinLineasError) as error:
        calcular_compra([])

    assert error.value.codigo == "COMPRA_SIN_LINEAS"


def test_mas_de_200_lineas_se_rechaza() -> None:
    assert MAXIMO_DE_LINEAS == 200
    calcular_compra([linea()] * 200)

    with pytest.raises(LineasInvalidasError):
        calcular_compra([linea()] * 201)


def test_el_error_de_una_linea_indica_su_indice() -> None:
    with pytest.raises(CantidadInvalidaError) as error:
        calcular_compra([linea(), linea(), linea(cantidad="2.3")])

    assert error.value.extension == {"linea": 2}


def test_el_error_de_valor_de_la_primera_linea_indica_cero() -> None:
    with pytest.raises(ValorInvalidoError) as error:
        calcular_compra([linea(valor="0.00"), linea()])

    assert error.value.extension == {"linea": 0}


def test_un_total_neto_que_no_entra_en_numeric_14_2_se_rechaza() -> None:
    enorme = linea(unidades=1, cantidad="1", valor="999999999999.99")

    with pytest.raises(ImporteInvalidoError):
        calcular_compra([enorme, enorme])


_UNIDADES = st.integers(min_value=1, max_value=240)
_ENTRADAS = st.builds(
    EntradaDeLinea,
    unidades_presentacion=_UNIDADES,
    cantidad=st.integers(min_value=1, max_value=500).map(Decimal),
    valor=st.decimals(
        min_value=Decimal("0.50"),
        max_value=Decimal("500000.00"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
    incluye_iva=st.booleans(),
    alicuota=st.sampled_from([Decimal("0"), Decimal("0.105000"), Decimal("0.210000")]),
    bonificacion=st.sampled_from([Decimal("0"), Decimal("0.100000"), Decimal("0.076923")]),
)


@given(entradas=st.lists(_ENTRADAS, min_size=1, max_size=12))
def test_inv04_total_neto_es_la_suma_de_los_importes_y_la_cantidad_base_es_entera(
    entradas: list[EntradaDeLinea],
) -> None:
    """INV-04 (cantidad base entera) y CMP-02 / TR-03 (total = suma de importes de línea)."""
    try:
        totales = calcular_compra(entradas)
    except ValorInvalidoError:
        return  # un costo base que redondea a cero no es una compra válida (ADR-039)

    assert totales.total_neto == sum((parte.importe_neto for parte in totales.lineas), Decimal(0))
    for entrada, parte in zip(entradas, totales.lineas, strict=True):
        assert isinstance(parte.cantidad_base, int)
        assert parte.cantidad_base == int(entrada.cantidad) * entrada.unidades_presentacion
        assert parte.importe_neto == parte.importe_neto.quantize(Decimal("0.01"))


@given(
    cajas_por_dos=st.integers(min_value=1, max_value=400),
    unidades=st.integers(min_value=1, max_value=48),
)
def test_cantidad_con_medios_decimales_es_valida_si_y_solo_si_da_entero(
    cajas_por_dos: int, unidades: int
) -> None:
    cantidad = Decimal(cajas_por_dos) / Decimal(2)  # n o n,5
    entrada = linea(unidades=unidades, cantidad=str(cantidad))

    if (cajas_por_dos * unidades) % 2 == 0:
        assert calcular_linea(entrada).cantidad_base == cajas_por_dos * unidades // 2
    else:
        with pytest.raises(CantidadInvalidaError):
            calcular_linea(entrada)


# --- 4.2: total de factura, condición, medios y fecha -----------------------------------


@pytest.mark.parametrize("total", ["0.01", "152460.00", "152460", "999999999999.99"])
def test_total_de_factura_valido(total: str) -> None:
    assert validar_total_factura(Decimal(total)) == Decimal(total).quantize(Decimal("0.01"))


@pytest.mark.parametrize("total", ["0", "0.00", "-1.00", "152460.001", "1000000000000.00"])
def test_total_de_factura_invalido(total: str) -> None:
    with pytest.raises(ImporteInvalidoError) as error:
        validar_total_factura(Decimal(total))

    assert error.value.codigo == "IMPORTE_INVALIDO"


def medio(importe: str, *, referencia: str | None = None, exige: bool = False) -> MedioDeEntrada:
    return MedioDeEntrada(
        importe=Decimal(importe), referencia=referencia, requiere_referencia=exige
    )


def test_credito_sin_medios_es_valido() -> None:
    validar_pago("CREDITO", Decimal("152460.00"), [])


def test_credito_con_medios_es_condicion_invalida() -> None:
    with pytest.raises(CondicionInvalidaError) as error:
        validar_pago("CREDITO", Decimal("152460.00"), [medio("152460.00")])

    assert error.value.codigo == "CONDICION_INVALIDA"


@pytest.mark.parametrize("condicion", ["MIXTA", "contado", ""])
def test_condicion_fuera_del_catalogo_es_invalida(condicion: str) -> None:
    with pytest.raises(CondicionInvalidaError):
        validar_pago(condicion, Decimal("100.00"), [])


def test_contado_con_dos_medios_que_suman_el_total_es_valido() -> None:
    validar_pago(
        "CONTADO",
        Decimal("152460.00"),
        [medio("100000.00"), medio("52460.00", referencia="0042", exige=True)],
    )


@pytest.mark.parametrize(
    "importes", [["150000.00"], ["100000.00", "52460.01"], ["152460.00", "0.01"], []]
)
def test_inv08_contado_con_medios_que_no_suman_el_total_se_rechaza(importes: list[str]) -> None:
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_pago("CONTADO", Decimal("152460.00"), [medio(i) for i in importes])

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_medio_que_exige_referencia_sin_referencia_se_rechaza(referencia: str | None) -> None:
    with pytest.raises(ReferenciaObligatoriaError) as error:
        validar_pago(
            "CONTADO",
            Decimal("100.00"),
            [medio("100.00", referencia=referencia, exige=True)],
        )

    assert error.value.codigo == "REFERENCIA_OBLIGATORIA"


def test_medio_que_no_exige_referencia_la_admite_vacia() -> None:
    validar_pago("CONTADO", Decimal("100.00"), [medio("100.00", referencia=None)])


@pytest.mark.parametrize("importe", ["0.00", "-5.00", "10.001"])
def test_importe_de_medio_invalido_se_rechaza(importe: str) -> None:
    with pytest.raises(ImporteInvalidoError):
        validar_pago("CONTADO", Decimal("100.00"), [medio(importe), medio("100.00")])


_CENTAVOS_TOTAL = st.integers(min_value=2, max_value=10_000_000)


@given(data=st.data(), total_en_centavos=_CENTAVOS_TOTAL)
def test_inv08_cualquier_reparto_exacto_pasa_y_cualquier_desvio_falla(
    data: st.DataObject, total_en_centavos: int
) -> None:
    """INV-08: la suma de los medios de un pago es igual a su importe."""
    cortes = sorted(
        data.draw(
            st.lists(
                st.integers(min_value=1, max_value=total_en_centavos - 1),
                unique=True,
                max_size=4,
            )
        )
    )
    limites = [0, *cortes, total_en_centavos]
    partes = [limites[i + 1] - limites[i] for i in range(len(limites) - 1)]
    total = Decimal(total_en_centavos) / Decimal(100)
    medios = [medio(str(Decimal(parte) / Decimal(100))) for parte in partes]

    validar_pago("CONTADO", total, medios)

    desviado = [*medios, medio("0.01")]
    with pytest.raises(MediosNoSumanImporteError):
        validar_pago("CONTADO", total, desviado)


def test_fecha_de_hoy_o_anterior_es_valida() -> None:
    hoy = date(2026, 10, 2)

    validar_fecha(hoy, hoy=hoy)
    validar_fecha(date(2020, 1, 1), hoy=hoy)


def test_fecha_posterior_a_hoy_es_invalida() -> None:
    with pytest.raises(FechaInvalidaError) as error:
        validar_fecha(date(2026, 10, 3), hoy=date(2026, 10, 2))

    assert error.value.codigo == "FECHA_INVALIDA"


def test_todos_los_errores_de_la_compra_son_errores_de_dominio_con_codigo_estable() -> None:
    errores = [
        CantidadInvalidaError,
        CompraSinLineasError,
        CondicionInvalidaError,
        FechaInvalidaError,
        ImporteInvalidoError,
        LineasInvalidasError,
        MediosNoSumanImporteError,
        ReferenciaObligatoriaError,
    ]

    assert all(issubclass(error, DomainError) for error in errores)
    assert len({error.codigo for error in errores}) == len(errores)
    assert {error.status_http for error in errores} == {422}


# --- 4.3: comparación con el costo informado vigente (CMP-04, D7) -----------------------


def test_costo_distinto_del_vigente_aparece_con_ambos_valores() -> None:
    vino = uuid4()

    diferencias = diferencias_de_costo(
        [CostoDeLinea(linea=0, producto_id=vino, costo_base=Decimal("1100.000000"))],
        {vino: Decimal("1000.000000")},
    )

    assert len(diferencias) == 1
    assert diferencias[0].linea == 0
    assert diferencias[0].producto_id == vino
    assert diferencias[0].costo_base_compra == Decimal("1100.000000")
    assert diferencias[0].costo_base_vigente == Decimal("1000.000000")


def test_costo_igual_al_vigente_no_aparece() -> None:
    vino = uuid4()

    assert (
        diferencias_de_costo(
            [CostoDeLinea(linea=0, producto_id=vino, costo_base=Decimal("1000.000000"))],
            {vino: Decimal("1000.000000")},
        )
        == []
    )


def test_producto_sin_costo_vigente_aparece_con_vigente_nulo() -> None:
    cerveza = uuid4()

    diferencias = diferencias_de_costo(
        [CostoDeLinea(linea=1, producto_id=cerveza, costo_base=Decimal("1100.000000"))],
        {cerveza: None},
    )

    assert [(d.linea, d.costo_base_vigente) for d in diferencias] == [(1, None)]


def test_producto_ausente_del_mapa_se_trata_como_sin_vigente() -> None:
    cerveza = uuid4()

    diferencias = diferencias_de_costo(
        [CostoDeLinea(linea=0, producto_id=cerveza, costo_base=Decimal("1.000000"))], {}
    )

    assert len(diferencias) == 1
    assert diferencias[0].costo_base_vigente is None


def test_cada_linea_se_compara_por_separado_y_conserva_el_orden() -> None:
    vino, cerveza = uuid4(), uuid4()

    diferencias = diferencias_de_costo(
        [
            CostoDeLinea(linea=0, producto_id=vino, costo_base=Decimal("1000.000000")),
            CostoDeLinea(linea=1, producto_id=cerveza, costo_base=Decimal("1200.000000")),
            CostoDeLinea(linea=2, producto_id=vino, costo_base=Decimal("1010.000000")),
        ],
        {vino: Decimal("1000.000000"), cerveza: Decimal("1100.000000")},
    )

    assert [d.linea for d in diferencias] == [1, 2]
