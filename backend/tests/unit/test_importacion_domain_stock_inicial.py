"""Tarea 7.1 (change 10): dominio puro de la importación de stock inicial
(`specs/importacion/puesta-en-marcha`, `design.md` D4, D13).

De la fila de planilla a la línea de `registrar_stock_inicial`: `cantidad_base` entera
(INV-04), `costo_unitario` con coma decimal convertido sin punto flotante (INV-03) y vacío
como `None`; las reglas de signo, rango y cantidad de decimales del costo son del servicio
(ADR-037). Más el orden estable por (producto, ubicación) que mantiene el orden global de
bloqueo (`02` §7.3) sin separar una corrección negativa de su positivo.

Reglas citadas: INV-03, INV-04, STK-10, CST-11, CST-12.
"""

from __future__ import annotations

import pytest

from app.modules.importacion.domain.errores import (
    CantidadInvalidaError,
    NumeroInvalidoError,
    ValorObligatorioError,
)
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.stock_inicial import (
    DatosDeStockInicial,
    datos_de_stock_inicial,
    ordenar_para_bloqueo,
)


def fila(numero: int = 2, **cambios: str) -> FilaPlanilla:
    valores = {
        "ubicacion": "Depósito Central",
        "producto_codigo": "VA-750",
        "cantidad_base": "60",
        "costo_unitario": "1000",
    }
    valores.update(cambios)
    return FilaPlanilla(fila=numero, valores=valores)


def test_lee_cantidad_entera_y_costo_exacto_con_coma() -> None:
    assert datos_de_stock_inicial(fila(cantidad_base="60", costo_unitario="1239,669421")) == (
        DatosDeStockInicial(
            ubicacion="Depósito Central",
            producto_codigo="VA-750",
            cantidad_base=60,
            costo_unitario="1239.669421",
        )
    )


def test_la_correccion_negativa_sin_costo_lleva_costo_none() -> None:
    datos = datos_de_stock_inicial(fila(cantidad_base="-12", costo_unitario=""))

    assert (datos.cantidad_base, datos.costo_unitario) == (-12, None)


def test_costo_con_siete_decimales_no_se_redondea() -> None:
    """INV-03: el texto llega entero al servicio, que lo rechaza como COSTO_INVALIDO."""
    assert datos_de_stock_inicial(fila(costo_unitario="1000,1234567")).costo_unitario == (
        "1000.1234567"
    )


@pytest.mark.parametrize("texto", ["10,5", "diez", ""])
def test_cantidad_no_entera_es_cantidad_invalida_en_su_columna(texto: str) -> None:
    with pytest.raises(CantidadInvalidaError) as excinfo:
        datos_de_stock_inicial(fila(cantidad_base=texto))

    assert excinfo.value.columna == "cantidad_base"


@pytest.mark.parametrize("texto", ["1.000", "mil"])
def test_costo_mal_escrito_es_numero_invalido_en_su_columna(texto: str) -> None:
    with pytest.raises(NumeroInvalidoError) as excinfo:
        datos_de_stock_inicial(fila(costo_unitario=texto))

    assert excinfo.value.columna == "costo_unitario"


@pytest.mark.parametrize("columna", ["ubicacion", "producto_codigo"])
def test_ubicacion_y_producto_son_obligatorios(columna: str) -> None:
    with pytest.raises(ValorObligatorioError) as excinfo:
        datos_de_stock_inicial(fila(**{columna: "  "}))

    assert excinfo.value.columna == columna


def test_el_orden_de_bloqueo_es_por_producto_y_ubicacion_y_es_estable() -> None:
    """Dos filas del mismo (producto, ubicación) conservan su orden de archivo: el
    ingreso antes que su corrección negativa."""
    filas = [
        ("p2", "u1", "ingreso"),
        ("p1", "u2", "ingreso"),
        ("p1", "u1", "ingreso"),
        ("p1", "u1", "correccion"),
    ]

    ordenadas = ordenar_para_bloqueo(filas, clave=lambda f: (f[0], f[1]))

    assert ordenadas == [
        ("p1", "u1", "ingreso"),
        ("p1", "u1", "correccion"),
        ("p1", "u2", "ingreso"),
        ("p2", "u1", "ingreso"),
    ]
