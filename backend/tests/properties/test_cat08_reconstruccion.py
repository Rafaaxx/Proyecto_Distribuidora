"""Change 05, tarea 5.4: propiedad Hypothesis de reconstrucción de CAT-08
(`s × (c × u + r) = q`, `0 <= r < u`), citando CAT-08 e INV-04."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.modules.catalogo.domain.cantidades import visualizar_cantidad


@given(
    cantidad_base=st.integers(min_value=-1_000_000, max_value=1_000_000),
    unidades_referencia=st.integers(min_value=1, max_value=10_000),
)
def test_cat08_inv04_reconstruccion_exacta(cantidad_base: int, unidades_referencia: int) -> None:
    resultado = visualizar_cantidad(cantidad_base, unidades_referencia)

    signo = -1 if resultado.negativo else 1
    assert signo * (resultado.cajas * unidades_referencia + resultado.unidades) == cantidad_base
    assert 0 <= resultado.unidades < unidades_referencia
