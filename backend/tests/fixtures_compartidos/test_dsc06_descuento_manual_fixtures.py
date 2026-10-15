"""Change 16, tarea 12.2: ejecuta contra `app.modules.descuentos.domain.manual` los casos
compartidos de `shared/fixtures/calculo/dsc-06-descuento-manual.json` cuya entrada declara
`"motor": "dsc06"` (DSC-06, TR-02, INV-03; `design.md` D4, D12; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/dsc06.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.descuentos.domain.manual import Autorizador, evaluar_descuento_manual

_CASOS_DSC06 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "dsc06"]

if not _CASOS_DSC06:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "dsc06" en '
        "shared/fixtures/calculo/ -- el arnés del descuento manual quedaría mudo"
    )


def _decimal_o_crudo(valor: Any) -> Any:
    """Una cadena entra como `Decimal` exacto; todo lo demás (nulo, número JSON) entra tal cual,
    para que la evaluación rechace un punto flotante (INV-03)."""
    return Decimal(valor) if isinstance(valor, str) else valor


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    autorizador = entrada["autorizador"]
    resultado = evaluar_descuento_manual(
        usuario_id=entrada["usuario_id"],
        descuento_manual_habilitado=entrada["descuento_manual_habilitado"],
        motivo_obligatorio=entrada["motivo_obligatorio"],
        permisos_usuario=frozenset(entrada["permisos_usuario"]),
        tope_rol=Decimal(entrada["tope_rol"]),
        tope_propio=_decimal_o_crudo(entrada["tope_propio"]),
        porcentaje_maximo=_decimal_o_crudo(entrada["porcentaje_maximo"]),
        motivo=entrada["motivo"],
        autorizador=None
        if autorizador is None
        else Autorizador(autorizador["usuario_id"], frozenset(autorizador["permisos"])),
    )
    return {
        "tope_aplicado": f"{resultado.tope_aplicado:.6f}",
        "requirio_autorizacion": resultado.requirio_autorizacion,
        "resolucion": resultado.resolucion,
        "autorizador_id": resultado.autorizador_id,
    }


@pytest.mark.parametrize("caso", _CASOS_DSC06, ids=[caso.id for caso in _CASOS_DSC06])
def test_caso_compartido_de_dsc06(caso: Any) -> None:
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(caso.entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(caso.entrada) == salida_esperada
