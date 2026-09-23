"""Change 05, tarea 5.1/5.2: ejecuta contra
`app.modules.catalogo.domain.cantidades.visualizar_cantidad` los casos
compartidos de `shared/fixtures/calculo/` cuya entrada declara
`"motor": "cat08"` (CAT-08, `02` §10.4)."""

from __future__ import annotations

import pytest
from cargador import descubrir_casos

from app.modules.catalogo.domain.cantidades import (
    UnidadesDeReferenciaInvalidasError,
    visualizar_cantidad,
)

_CASOS_CAT08 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "cat08"]

if not _CASOS_CAT08:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "cat08" en '
        "shared/fixtures/calculo/ -- el arnés de cantidades.py quedaría mudo"
    )


@pytest.mark.parametrize("caso", _CASOS_CAT08, ids=[caso.id for caso in _CASOS_CAT08])
def test_caso_compartido_de_cat08(caso: object) -> None:
    entrada = caso.entrada  # type: ignore[attr-defined]
    salida_esperada = caso.salida_esperada  # type: ignore[attr-defined]

    if salida_esperada.get("error"):
        with pytest.raises(UnidadesDeReferenciaInvalidasError):
            visualizar_cantidad(entrada["cantidad_base"], entrada["unidades_referencia"])
        return

    resultado = visualizar_cantidad(entrada["cantidad_base"], entrada["unidades_referencia"])
    assert resultado.cajas == salida_esperada["cajas"]
    assert resultado.unidades == salida_esperada["unidades"]
    assert resultado.negativo == salida_esperada["negativo"]
