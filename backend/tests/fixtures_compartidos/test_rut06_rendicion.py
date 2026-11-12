"""Change 24, tarea 1.2: ejecuta contra `app.modules.stock.domain.rendicion` los casos
compartidos de `shared/fixtures/calculo/rut-06-rendicion.json` cuya entrada declara
`"motor": "rut06"` (RUT-06, RUT-07, STK-04, INV-04; `design.md` D2, D4). Los mismos casos de
`esperado`, `diferencia` y `faltantes` los corre Vitest contra `domain/stock/rendicion.ts`; el
conjunto a contar y la validación del conteo son del servidor."""

from __future__ import annotations

from typing import Any

import pytest
from cargador import descubrir_casos

from app.core.errors import DomainError
from app.modules.stock.domain import rendicion
from app.modules.stock.domain.rendicion import LineaContada

_CASOS_RUT06 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "rut06"]

if not _CASOS_RUT06:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "rut06" en '
        "shared/fixtures/calculo/ -- el arnés de rut06 quedaría mudo"
    )

_OPERACIONES = {"conjunto", "esperado", "diferencia", "faltantes", "conteo"}


def _conteo(entrada: dict[str, Any]) -> dict[str, Any]:
    lineas = [
        LineaContada(producto=x["producto"], contada=x["contada"], esperada=x["esperada"])
        for x in entrada["lineas"]
    ]
    try:
        validadas = rendicion.validar_conteo(
            conjunto=set(entrada["conjunto"]), esperados=entrada["esperados"], lineas=lineas
        )
    except DomainError as error:
        return {"error": {"codigo": error.codigo, **(error.extension or {})}}
    return {
        "lineas": [
            {
                "producto": x.producto,
                "esperado": x.esperado,
                "contado": x.contado,
                "diferencia": x.diferencia,
            }
            for x in validadas
        ]
    }


@pytest.mark.parametrize("caso", _CASOS_RUT06, ids=[caso.id for caso in _CASOS_RUT06])
def test_caso_compartido_de_rut06(caso: Any) -> None:
    entrada = caso.entrada
    operacion = entrada["operacion"]
    assert operacion in _OPERACIONES, f"operación desconocida en {caso.id}: {operacion}"

    if operacion == "conjunto":
        resultado: dict[str, Any] = {
            "conjunto": sorted(
                rendicion.conjunto_a_contar(
                    entrada["saldos"], con_movimiento=set(entrada["con_movimiento"])
                )
            )
        }
    elif operacion == "esperado":
        resultado = {
            "esperado": rendicion.esperado(
                al_abrir=entrada["al_abrir"],
                ingresos=entrada["ingresos"],
                ventas=entrada["ventas"],
                anulaciones=entrada["anulaciones"],
                otros=entrada["otros"],
            )
        }
    elif operacion == "diferencia":
        resultado = {
            "diferencia": rendicion.diferencia(
                contada=entrada["contada"], esperada=entrada["esperada"]
            )
        }
    elif operacion == "faltantes":
        resultado = {
            "faltantes": rendicion.productos_faltantes(
                entrada["conjunto"], contados=entrada["contados"]
            )
        }
    else:
        resultado = _conteo(entrada)

    assert resultado == caso.salida_esperada
