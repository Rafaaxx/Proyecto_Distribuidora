"""Tarea 6.2 (change 10): dominio puro de la importación de costos
(`specs/importacion/importacion-de-maestros`, `design.md` D4, D8, D12).

De la fila de planilla a los datos del costo informado: importe y bonificación con coma
decimal y sin punto flotante (INV-03), bonificación en porcentaje que pasa a fracción
(`10` es `0.10`, TR-02), booleano `S`/`N`, fecha de vigencia y la clave natural que detecta
la repetición dentro del archivo. El cálculo del costo base (CST-02) es del servicio de
`proveedores`.

Reglas citadas: CST-01, CST-02, CST-03, INV-03, TR-02.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.importacion.domain.costos import DatosDeCosto, claves_de_costo, datos_de_costo
from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.planilla import FilaPlanilla


def fila(numero: int = 2, **cambios: str) -> FilaPlanilla:
    valores = {
        "producto_codigo": "CB-473",
        "presentacion": "Caja x12",
        "valor": "18000",
        "incluye_iva": "N",
        "bonificacion": "",
        "vigencia_desde": "2026-10-01",
        "observacion": "",
    }
    valores.update(cambios)
    return FilaPlanilla(fila=numero, valores=valores)


def test_los_datos_del_costo_salen_de_la_fila_con_importes_exactos() -> None:
    datos = datos_de_costo(fila(valor="18000,50", incluye_iva="si", observacion="Lista octubre"))

    assert datos == DatosDeCosto(
        producto_codigo="CB-473",
        presentacion="Caja x12",
        valor=Decimal("18000.50"),
        incluye_iva=True,
        bonificacion=Decimal("0"),
        vigencia_desde=date(2026, 10, 1),
        observacion="Lista octubre",
    )
    assert isinstance(datos.valor, Decimal)


def test_sin_bonificacion_es_cero_y_sin_observacion_es_none() -> None:
    datos = datos_de_costo(fila())

    assert datos.bonificacion == Decimal("0")
    assert datos.observacion is None
    assert datos.incluye_iva is False


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [("10", Decimal("0.10")), ("12,5", Decimal("0.125")), ("0", Decimal("0"))],
)
def test_la_bonificacion_en_porcentaje_pasa_a_fraccion_exacta(
    texto: str, esperada: Decimal
) -> None:
    """TR-02: `10` es `0.10`, sin punto flotante."""
    assert datos_de_costo(fila(bonificacion=texto)).bonificacion == esperada


@pytest.mark.parametrize("texto", ["2026-10-01", "01/10/2026"])
def test_la_vigencia_admite_las_dos_formas_de_fecha(texto: str) -> None:
    assert datos_de_costo(fila(vigencia_desde=texto)).vigencia_desde == date(2026, 10, 1)


@pytest.mark.parametrize(
    ("cambios", "columna", "codigo"),
    [
        ({"valor": "18.000"}, "valor", "NUMERO_INVALIDO"),
        ({"valor": ""}, "valor", "NUMERO_INVALIDO"),
        ({"incluye_iva": "tal vez"}, "incluye_iva", "VALOR_INVALIDO"),
        ({"incluye_iva": ""}, "incluye_iva", "VALOR_OBLIGATORIO"),
        ({"bonificacion": "diez"}, "bonificacion", "NUMERO_INVALIDO"),
        ({"bonificacion": "10.5"}, "bonificacion", "NUMERO_INVALIDO"),
        ({"vigencia_desde": "mañana"}, "vigencia_desde", "FECHA_INVALIDA"),
        ({"vigencia_desde": "31/02/2026"}, "vigencia_desde", "FECHA_INVALIDA"),
        ({"producto_codigo": ""}, "producto_codigo", "VALOR_OBLIGATORIO"),
        ({"presentacion": "  "}, "presentacion", "VALOR_OBLIGATORIO"),
    ],
)
def test_una_celda_ilegible_o_vacia_lleva_su_columna_y_su_codigo(
    cambios: dict[str, str], columna: str, codigo: str
) -> None:
    with pytest.raises(ErrorDeValor) as excinfo:
        datos_de_costo(fila(**cambios))

    assert (excinfo.value.columna, excinfo.value.codigo) == (columna, codigo)


def test_la_clave_es_producto_presentacion_y_vigencia_sin_distinguir_mayusculas() -> None:
    una = claves_de_costo(fila(producto_codigo="cb-473", presentacion=" CAJA x12 "))
    otra = claves_de_costo(fila(vigencia_desde="01/10/2026"))

    assert una == otra == [("producto_codigo", "cb-473|caja x12|2026-10-01")]


def test_cambia_la_clave_si_cambia_la_vigencia_o_la_presentacion() -> None:
    base = claves_de_costo(fila())

    assert claves_de_costo(fila(vigencia_desde="2026-11-01")) != base
    assert claves_de_costo(fila(presentacion="Lata")) != base


def test_sin_fecha_legible_no_hay_clave() -> None:
    """Su error de fecha lo informa la lectura de la fila."""
    assert claves_de_costo(fila(vigencia_desde="mañana")) == []


# --- 11b: organización sin crédito fiscal (CST-06, D6) ---------------------------------------


@pytest.mark.parametrize("texto", ["", "  ", "N", "no"])
def test_cst06_sin_credito_fiscal_la_columna_vacia_o_n_es_falso(texto: str) -> None:
    datos = datos_de_costo(fila(incluye_iva=texto), computa_credito_fiscal=False)

    assert datos.incluye_iva is False


def test_cst06_sin_credito_fiscal_la_s_se_lee_verdadera_y_la_rechaza_el_servicio() -> None:
    """El dominio de importación solo lee la celda: rechazar `S` es de `proveedores` (D4,
    `INCLUYE_IVA_NO_APLICA`), la misma regla que el alta individual (TR-10)."""
    datos = datos_de_costo(fila(incluye_iva="S"), computa_credito_fiscal=False)

    assert datos.incluye_iva is True


def test_cst06_sin_credito_fiscal_una_celda_ilegible_sigue_siendo_invalida() -> None:
    with pytest.raises(ErrorDeValor) as excinfo:
        datos_de_costo(fila(incluye_iva="tal vez"), computa_credito_fiscal=False)

    assert (excinfo.value.columna, excinfo.value.codigo) == ("incluye_iva", "VALOR_INVALIDO")


def test_cst06_con_credito_fiscal_la_columna_vacia_es_valor_obligatorio() -> None:
    with pytest.raises(ErrorDeValor) as excinfo:
        datos_de_costo(fila(incluye_iva=""), computa_credito_fiscal=True)

    assert (excinfo.value.columna, excinfo.value.codigo) == ("incluye_iva", "VALOR_OBLIGATORIO")


def test_cst06_el_valor_es_el_pagado_con_importe_exacto() -> None:
    datos = datos_de_costo(fila(valor="21780", incluye_iva=""), computa_credito_fiscal=False)

    assert datos.valor == Decimal("21780")
    assert isinstance(datos.valor, Decimal)
