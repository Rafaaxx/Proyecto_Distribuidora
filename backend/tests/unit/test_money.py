"""Unitarias de `core/money.py` (INV-03, `docs/02-arquitectura.md` §10.1).

`redondear_importe` cuantiza a 2 decimales y `redondear_costo` a 6, ambas con
`ROUND_HALF_UP` explícito -- el contexto decimal por defecto de Python
redondea al par y no debe usarse para cuantizar dinero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import EntradaNoEsDineroExactoError, redondear_costo, redondear_importe


class TestRedondearImporte:
    def test_medio_positivo_se_redondea_hacia_arriba(self) -> None:
        # ROUND_HALF_UP: 0.125 -> 0.13, no 0.12 (que daría el redondeo al par
        # del contexto decimal por defecto).
        assert redondear_importe(Decimal("0.125")) == Decimal("0.13")

    def test_medio_negativo_se_aleja_de_cero(self) -> None:
        assert redondear_importe(Decimal("-0.125")) == Decimal("-0.13")

    def test_resultado_tiene_exactamente_dos_decimales(self) -> None:
        resultado = redondear_importe(Decimal("10"))

        assert str(resultado) == "10.00"

    def test_acepta_una_cadena_numerica_exacta(self) -> None:
        assert redondear_importe("31250") == Decimal("31250.00")

    def test_rechaza_float_binario(self) -> None:
        with pytest.raises(EntradaNoEsDineroExactoError):
            redondear_importe(0.125)  # type: ignore[arg-type]

    def test_rechaza_cadena_no_numerica(self) -> None:
        with pytest.raises(EntradaNoEsDineroExactoError):
            redondear_importe("abc")


class TestRedondearCosto:
    def test_cuantiza_a_seis_decimales_con_medio_hacia_arriba(self) -> None:
        assert redondear_costo(Decimal("1.0000005")) == Decimal("1.000001")

    def test_resultado_tiene_exactamente_seis_decimales(self) -> None:
        resultado = redondear_costo(Decimal("1"))

        assert str(resultado) == "1.000000"

    def test_alicuota_iva_veintiuno_por_ciento(self) -> None:
        assert redondear_costo(Decimal("0.21")) == Decimal("0.210000")

    def test_rechaza_float_binario(self) -> None:
        with pytest.raises(EntradaNoEsDineroExactoError):
            redondear_costo(1.0000005)  # type: ignore[arg-type]

    def test_rechaza_cadena_no_numerica(self) -> None:
        with pytest.raises(EntradaNoEsDineroExactoError):
            redondear_costo("no-es-un-numero")
