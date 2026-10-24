"""Change 18b, tarea 1.3: ejecuta contra `app.modules.clientes.domain.credito` los casos
compartidos de `shared/fixtures/calculo/cre-01-credito.json` cuya entrada declara
`"motor": "cre01"` (CRE-01 a CRE-07, ADR-032, TR-03, INV-03; `design.md` D5, D6, D8; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/cre01.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.clientes.domain.credito import Autorizador, evaluar_credito

_CASOS_CRE01 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "cre01"]

if not _CASOS_CRE01:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "cre01" en '
        "shared/fixtures/calculo/ -- el arnés del motor de crédito quedaría mudo"
    )


def _decimal_o_crudo(valor: Any) -> Any:
    """Una cadena entra como `Decimal` exacto; todo lo demás (nulo, número JSON) entra tal cual,
    para que el motor rechace un punto flotante (INV-03)."""
    return Decimal(valor) if isinstance(valor, str) else valor


def _texto(valor: Decimal | None) -> str | None:
    return None if valor is None else f"{valor:.2f}"


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    autorizador = entrada["autorizador"]
    resultado = evaluar_credito(
        limite=_decimal_o_crudo(entrada["limite"]),
        saldo_actual=_decimal_o_crudo(entrada["saldo_actual"]),
        total_venta=_decimal_o_crudo(entrada["total_venta"]),
        cobranza=_decimal_o_crudo(entrada["cobranza"]),
        politica=entrada["politica"],
        tolerancia_tipo=entrada["tolerancia_tipo"],
        tolerancia_valor=_decimal_o_crudo(entrada["tolerancia_valor"]),
        modo=entrada["modo"],
        acepta_exceso=entrada["acepta_exceso"],
        usuario_id=entrada["usuario_id"],
        permisos_usuario=frozenset(entrada["permisos_usuario"]),
        autorizador=None
        if autorizador is None
        else Autorizador(autorizador["usuario_id"], frozenset(autorizador["permisos"])),
    )
    return {
        "disponible": _texto(resultado.disponible),
        "saldo_resultante": _texto(resultado.saldo_resultante),
        "exceso": _texto(resultado.exceso),
        "tolerancia": _texto(resultado.tolerancia),
        "resolucion": resultado.resolucion,
        "autorizador_id": resultado.autorizador_id,
    }


@pytest.mark.parametrize("caso", _CASOS_CRE01, ids=[caso.id for caso in _CASOS_CRE01])
def test_caso_compartido_de_cre01(caso: Any) -> None:
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(caso.entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(caso.entrada) == salida_esperada


def test_los_casos_cre01_tienen_id_unico_y_cubren_las_reglas_de_la_spec() -> None:
    """Escenario "Los casos compartidos corren en las dos suites": el `id` identifica a cada caso
    sin repetirse y las reglas CRE-01 a CRE-07, ADR-032, TR-03 e INV-03 están citadas."""
    ids = [caso.id for caso in _CASOS_CRE01]
    citadas = {regla for caso in _CASOS_CRE01 for regla in caso.reglas}

    assert len(ids) == len(set(ids))
    assert {
        "CRE-01",
        "CRE-02",
        "CRE-03",
        "CRE-04",
        "CRE-05",
        "CRE-06",
        "CRE-07",
        "ADR-032",
        "TR-03",
        "INV-03",
    } <= citadas
