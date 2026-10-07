"""Change 13, grupo 7: el dominio del borrador (`precios/domain/borrador.py`): el precio
manual (validación y lo que guarda), la relación de un precio con el de la versión base y las
señales de un precio (`design.md` D1, D2, D3, D4, D7; spec `precios/borrador-de-lista`).

Reglas citadas: PRC-16, PRC-17, TR-01, TR-02, INV-03, CST-06, `design.md` D2, D3, D7.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.precios.domain.borrador import (
    CAMBIA,
    IGUAL,
    NUEVO,
    Senales,
    calcular_senales,
    referencia_de_precio_manual,
    relacion_con_la_base,
    validar_precio_manual,
)
from app.modules.precios.domain.errores import ImporteInvalidoError
from app.modules.precios.domain.reglas import Regla


def _regla(tipo: str = "MARGEN_BRUTO", valor: str = "0.300000") -> Regla:
    return Regla(
        id=uuid4(),
        alcance_tipo="LISTA",
        alcance_id=None,
        tipo=tipo,
        valor=Decimal(valor),
        activo=True,
    )


# --- validar_precio_manual (D7, TR-01) ---------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("9000.00", Decimal("9000.00")),
        ("8990", Decimal("8990.00")),
        ("0.01", Decimal("0.01")),
        (Decimal("12000.5"), Decimal("12000.50")),
    ],
)
def test_un_precio_manual_valido_queda_con_dos_decimales(
    entrada: str | Decimal, esperado: Decimal
) -> None:
    precio = validar_precio_manual(entrada)

    assert precio == esperado
    assert precio.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "entrada", ["0.00", "0", "-10.00", "8600.005", "abc", "", " ", "1e3", "NaN", "Infinity"]
)
def test_un_precio_manual_invalido_se_rechaza_con_importe_invalido(entrada: str) -> None:
    with pytest.raises(ImporteInvalidoError) as error:
        validar_precio_manual(entrada)

    assert error.value.codigo == "IMPORTE_INVALIDO"


def test_un_precio_manual_con_mas_digitos_que_numeric_14_2_se_rechaza() -> None:
    with pytest.raises(ImporteInvalidoError):
        validar_precio_manual("1000000000000.00")
    assert validar_precio_manual("999999999999.99") == Decimal("999999999999.99")


@pytest.mark.parametrize("entrada", [8600.0, 8600, True])
def test_un_precio_manual_que_no_es_dinero_exacto_se_rechaza_inv_03(entrada: object) -> None:
    with pytest.raises((EntradaNoEsDineroExactoError, ImporteInvalidoError)):
        validar_precio_manual(entrada)  # type: ignore[arg-type]


# --- referencia_de_precio_manual (PRC-16, D7) --------------------------------------------


def test_un_manual_con_costo_y_regla_guarda_costo_de_referencia_regla_y_calculado() -> None:
    regla = _regla()

    referencia = referencia_de_precio_manual(Decimal("1000.000000"), 6, regla)

    assert referencia.costo_referencia == Decimal("6000.000000")
    assert referencia.regla_id == regla.id
    assert referencia.tipo_margen == "MARGEN_BRUTO"
    assert referencia.valor_margen == Decimal("0.300000")
    assert referencia.precio_calculado == Decimal("8571.428571")


def test_otro_costo_y_otras_unidades_dan_otra_referencia() -> None:
    referencia = referencia_de_precio_manual(Decimal("1100.000000"), 12, _regla("MARKUP", "0.5"))

    assert referencia.costo_referencia == Decimal("13200.000000")
    assert referencia.precio_calculado == Decimal("19800.000000")


def test_un_manual_sin_costo_no_guarda_nada_del_calculo() -> None:
    referencia = referencia_de_precio_manual(None, 6, _regla())

    assert referencia.costo_referencia is None
    assert referencia.regla_id is None
    assert referencia.tipo_margen is None
    assert referencia.valor_margen is None
    assert referencia.precio_calculado is None


def test_un_manual_con_costo_y_sin_regla_guarda_el_costo_pero_no_la_regla() -> None:
    referencia = referencia_de_precio_manual(Decimal("1000.000000"), 6, None)

    assert referencia.costo_referencia == Decimal("6000.000000")
    assert referencia.regla_id is None
    assert referencia.precio_calculado is None


# --- relacion_con_la_base (PRC-17) -------------------------------------------------------


def test_sin_precio_en_la_base_el_precio_es_nuevo() -> None:
    assert relacion_con_la_base(Decimal("8600.00"), None) == NUEVO


def test_igual_al_de_la_base_es_igual() -> None:
    assert relacion_con_la_base(Decimal("31200.00"), Decimal("31200.00")) == IGUAL


def test_distinto_del_de_la_base_cambia_para_arriba_y_para_abajo() -> None:
    assert relacion_con_la_base(Decimal("9500.00"), Decimal("8600.00")) == CAMBIA
    assert relacion_con_la_base(Decimal("8000.00"), Decimal("8600.00")) == CAMBIA


# --- calcular_senales (D2, D3, D7) -------------------------------------------------------


def _senales(**cambios: object) -> Senales:
    argumentos: dict[str, object] = {
        "manual": False,
        "precio_final": Decimal("8600.00"),
        "precio_calculado": Decimal("8571.428571"),
        "computa_credito_fiscal_del_costo": True,
        "computa_credito_fiscal_actual": True,
        "costos_distintos_por_presentacion": False,
    }
    argumentos.update(cambios)
    return calcular_senales(**argumentos)  # type: ignore[arg-type]


def test_un_precio_calculado_comun_no_lleva_ninguna_senal() -> None:
    assert _senales() == Senales(
        sin_costo=False,
        margen_menor=False,
        costo_otra_regla_iva=False,
        costos_distintos_por_presentacion=False,
    )


def test_un_manual_por_debajo_del_calculado_lleva_la_senal_de_margen_menor() -> None:
    senales = _senales(
        manual=True, precio_final=Decimal("9000.00"), precio_calculado=Decimal("9428.571429")
    )

    assert senales.margen_menor is True
    assert senales.sin_costo is False


def test_un_manual_por_encima_o_igual_al_calculado_no_lleva_la_senal_de_margen() -> None:
    assert _senales(manual=True, precio_final=Decimal("9000.00")).margen_menor is False
    igual = _senales(
        manual=True, precio_final=Decimal("8571.43"), precio_calculado=Decimal("8571.430000")
    )
    assert igual.margen_menor is False


def test_un_precio_no_manual_nunca_lleva_la_senal_de_margen_menor() -> None:
    """El precio calculado redondeado hacia abajo puede quedar bajo el calculado exacto
    (`ABAJO`), pero eso es el redondeo de la lista, no una decisión manual (D7)."""
    senales = _senales(manual=False, precio_final=Decimal("8500.00"))

    assert senales.margen_menor is False


def test_un_manual_sin_costo_o_sin_regla_lleva_sin_costo_y_no_la_senal_de_margen() -> None:
    senales = _senales(manual=True, precio_final=Decimal("12000.00"), precio_calculado=None)

    assert senales.sin_costo is True
    assert senales.margen_menor is False


def test_un_costo_con_otra_regla_de_iva_lleva_la_senal() -> None:
    sin_credito_hoy_con_credito = _senales(
        computa_credito_fiscal_del_costo=False, computa_credito_fiscal_actual=True
    )
    con_credito_hoy_sin_credito = _senales(
        computa_credito_fiscal_del_costo=True, computa_credito_fiscal_actual=False
    )
    misma_regla_sin_credito = _senales(
        computa_credito_fiscal_del_costo=False, computa_credito_fiscal_actual=False
    )

    assert sin_credito_hoy_con_credito.costo_otra_regla_iva is True
    assert con_credito_hoy_sin_credito.costo_otra_regla_iva is True
    assert misma_regla_sin_credito.costo_otra_regla_iva is False


def test_sin_costo_no_hay_senal_de_otra_regla_de_iva_ni_de_presentaciones() -> None:
    senales = _senales(
        manual=True,
        precio_calculado=None,
        computa_credito_fiscal_del_costo=None,
        costos_distintos_por_presentacion=False,
    )

    assert senales.costo_otra_regla_iva is False
    assert senales.costos_distintos_por_presentacion is False


def test_los_costos_distintos_por_presentacion_se_senalan() -> None:
    assert _senales(costos_distintos_por_presentacion=True).costos_distintos_por_presentacion


def test_las_senales_no_aceptan_float_en_los_importes() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        _senales(manual=True, precio_final=9000.0)
