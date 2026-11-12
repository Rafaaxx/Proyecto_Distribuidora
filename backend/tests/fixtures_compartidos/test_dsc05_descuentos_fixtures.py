"""Change 16, tarea 2.1: ejecuta contra `app.modules.descuentos.domain` los casos compartidos de
`shared/fixtures/calculo/dsc-05-descuentos.json` cuya entrada declara `"motor": "dsc05"`
(DSC-03, DSC-04, DSC-05, DSC-07, DSC-08; `design.md` D4; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/dsc05.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.descuentos.domain.motor import calcular_descuentos
from app.modules.descuentos.domain.tipos import AlcanceRegla, LineaVenta, ReglaDescuento

_CASOS_DSC05 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "dsc05"]

if not _CASOS_DSC05:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "dsc05" en '
        "shared/fixtures/calculo/ -- el arnés del motor de descuentos quedaría mudo"
    )


def _decimal_o_crudo(valor: Any) -> Any:
    """Una cadena entra como `Decimal` exacto; todo lo demás (nulo, número JSON) entra tal cual,
    para que el motor rechace un punto flotante (INV-03)."""
    return Decimal(valor) if isinstance(valor, str) else valor


def _linea(bruto: dict[str, Any]) -> LineaVenta:
    return LineaVenta(
        id=bruto["id"],
        bruto=_decimal_o_crudo(bruto["bruto"]),
        cantidad_base=bruto["cantidad_base"],
        unidades_referencia=bruto["unidades_referencia"],
        producto_id=bruto["producto_id"],
        categoria_id=bruto["categoria_id"],
        marca_id=bruto["marca_id"],
        descuento_manual=_decimal_o_crudo(bruto["descuento_manual"]),
    )


def _regla(bruto: dict[str, Any]) -> ReglaDescuento:
    return ReglaDescuento(
        id=bruto["id"],
        tipo=bruto["tipo"],
        medida=bruto["medida"],
        operador=bruto["operador"],
        umbral=Decimal(bruto["umbral"]),
        accion_tipo=bruto["accion_tipo"],
        accion_porcentaje=_decimal_o_crudo(bruto["accion_porcentaje"]),
        accion_importe=_decimal_o_crudo(bruto["accion_importe"]),
        acumulable=bruto["acumulable"],
        prioridad=bruto["prioridad"],
        alcances=tuple(AlcanceRegla(a["tipo"], a["entidad_id"]) for a in bruto["alcances"]),
    )


def _texto(valor: Decimal | None, decimales: int) -> str | None:
    return None if valor is None else f"{valor:.{decimales}f}"


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    resultado = calcular_descuentos(
        [_linea(linea) for linea in entrada["lineas"]],
        [_regla(regla) for regla in entrada["reglas_descuento"]],
        _decimal_o_crudo(entrada["descuento_manual_general"]),
    )
    return {
        "lineas": [
            {
                "id": linea.id,
                "descuentos": [
                    {
                        "origen": descuento.origen,
                        "regla_id": descuento.regla_id,
                        "porcentaje": _texto(descuento.porcentaje, 6),
                        "importe": _texto(descuento.importe, 2),
                    }
                    for descuento in linea.descuentos
                ],
                "descuento_total": _texto(linea.descuento_total, 2),
                "neto": _texto(linea.neto, 2),
            }
            for linea in resultado.lineas
        ],
        "porcentaje_manual_maximo": _texto(resultado.porcentaje_manual_maximo, 6),
    }


@pytest.mark.parametrize("caso", _CASOS_DSC05, ids=[caso.id for caso in _CASOS_DSC05])
def test_caso_compartido_de_dsc05(caso: Any) -> None:
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(caso.entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(caso.entrada) == salida_esperada
