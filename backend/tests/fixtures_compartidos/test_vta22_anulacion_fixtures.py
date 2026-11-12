"""Change 19, tarea 1.3: ejecuta contra `app.modules.ventas.domain.anulacion`
los casos compartidos de `shared/fixtures/calculo/vta-22-anulacion.json`
cuya entrada declara `"motor": "vta22"` (VTA-21, VTA-22, INV-19; `design.md`
D4, D17).

ROJO a propósito: el dominio de la anulación todavía no existe. Este archivo
prueba que el cargador descubre los casos de `vta22`; la importación inexistente
es la evidencia de ROJO. Cada caso es una prueba con su `id`."""

from __future__ import annotations

from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.ventas.domain.anulacion import efecto_en_cuenta

_CASOS_VTA22 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "vta22"]

if not _CASOS_VTA22:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "vta22" en '
        "shared/fixtures/calculo/ -- el arnés de vta22 quedaría mudo"
    )


@pytest.mark.parametrize("caso", _CASOS_VTA22, ids=[caso.id for caso in _CASOS_VTA22])
def test_caso_compartido_de_vta22(caso: Any) -> None:
    entrada = caso.entrada
    salida_esperada = caso.salida_esperada

    total = entrada["total_venta"]
    importe_cobranza = entrada.get("importe_cobranza")
    devuelve = entrada.get("devuelve_dinero")
    resultado = efecto_en_cuenta(total, importe_cobranza, devuelve)
    movimientos = [{"tipo": m.tipo, "importe": m.importe} for m in resultado.movimientos]
    assert movimientos == salida_esperada["movimientos"]
    assert resultado.saldo_final_relativo == salida_esperada["saldo_final_relativo"]
