"""Change 11, tarea 1.1: ejecuta contra `app.modules.proveedores.domain.compras` los
casos compartidos de `shared/fixtures/calculo/cmp-02-compra.json` cuya entrada declara
`"motor": "cmp02"` (CMP-02, `design.md` D5, D15; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/cmp02.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.proveedores.domain.compras import (
    EntradaDeLinea,
    calcular_compra,
    calcular_linea,
)

_CASOS_CMP02 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "cmp02"]

if not _CASOS_CMP02:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "cmp02" en '
        "shared/fixtures/calculo/ -- el arnés de compras.py quedaría mudo"
    )


def _linea(datos: dict[str, Any]) -> EntradaDeLinea:
    return EntradaDeLinea(
        unidades_presentacion=datos["unidades_presentacion"],
        cantidad=Decimal(datos["cantidad"]),
        valor=Decimal(datos["valor"]),
        incluye_iva=datos["incluye_iva"],
        alicuota=Decimal(datos["alicuota"]),
        bonificacion=Decimal(datos["bonificacion"]),
    )


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    if entrada["operacion"] == "calcular_linea":
        linea = calcular_linea(_linea(entrada))
        return {
            "cantidad_base": linea.cantidad_base,
            "costo_base": str(linea.costo_base),
            "importe_neto": str(linea.importe_neto),
        }
    totales = calcular_compra([_linea(linea) for linea in entrada["lineas"]])
    return {
        "total_neto": str(totales.total_neto),
        "total_factura_sugerido": str(totales.total_factura_sugerido),
    }


@pytest.mark.parametrize("caso", _CASOS_CMP02, ids=[caso.id for caso in _CASOS_CMP02])
def test_caso_compartido_de_cmp02(caso: Any) -> None:
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(caso.entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(caso.entrada) == salida_esperada
