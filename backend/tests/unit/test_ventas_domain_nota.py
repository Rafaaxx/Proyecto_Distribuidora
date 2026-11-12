"""Tarea 6.1 (change 20; `design.md` D4): `saldo_de_la_nota`, el saldo resultante que se imprime
en la nota de venta y los casos en que se omite.

Reglas citadas: CRE-02, VTA-13, CLI-03.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.ventas.domain.nota import saldo_de_la_nota


def _saldo(
    *,
    muestra_saldo: bool = True,
    es_consumidor_final: bool = False,
    estado: str = "CONFIRMADA",
    saldo_considerado: Decimal | None = Decimal("150000.00"),
    total: Decimal = Decimal("80000.00"),
    cobrado: Decimal = Decimal("20000.00"),
) -> Decimal | None:
    return saldo_de_la_nota(
        muestra_saldo, es_consumidor_final, estado, saldo_considerado, total, cobrado
    )


def test_cre02_el_ejemplo_de_la_regla_da_210000() -> None:
    """Saldo actual $150.000 + total $80.000 - cobranza $20.000 = $210.000."""
    assert _saldo() == Decimal("210000.00")


def test_cre02_sin_cobranza_el_saldo_suma_todo_el_total() -> None:
    assert _saldo(cobrado=Decimal("0.00")) == Decimal("230000.00")


def test_cre02_cobrado_todo_el_saldo_no_cambia() -> None:
    assert _saldo(cobrado=Decimal("80000.00")) == Decimal("150000.00")


def test_cre02_un_saldo_a_favor_se_conserva_con_su_signo() -> None:
    assert _saldo(saldo_considerado=Decimal("-100000.00")) == Decimal("-40000.00")
    assert _saldo(saldo_considerado=Decimal("0.00"), cobrado=Decimal("100000.00")) == Decimal(
        "-20000.00"
    )


def test_cre02_el_resultado_es_un_importe_de_dos_decimales() -> None:
    resultado = _saldo(
        saldo_considerado=Decimal("10.10"), total=Decimal("0.20"), cobrado=Decimal("0.05")
    )
    assert resultado == Decimal("10.25")
    assert resultado is not None and resultado.as_tuple().exponent == -2


def test_vta13_con_el_parametro_inactivo_no_hay_saldo() -> None:
    assert _saldo(muestra_saldo=False) is None


def test_cli03_al_consumidor_final_no_se_le_muestra_saldo() -> None:
    assert _saldo(es_consumidor_final=True) is None


def test_vta13_sin_saldo_considerado_no_hay_saldo() -> None:
    """Una venta anterior al change 18b no tiene el snapshot: se omite."""
    assert _saldo(saldo_considerado=None) is None


def test_vta13_una_venta_anulada_no_muestra_saldo() -> None:
    assert _saldo(estado="ANULADA") is None


@pytest.mark.parametrize(
    "omision",
    [
        {"muestra_saldo": False},
        {"es_consumidor_final": True},
        {"saldo_considerado": None},
        {"estado": "ANULADA"},
    ],
    ids=["parametro", "consumidor_final", "sin_snapshot", "anulada"],
)
def test_vta13_cada_omision_alcanza_por_si_sola_aunque_lo_demas_pida_saldo(
    omision: dict[str, object],
) -> None:
    assert _saldo(**omision) is None  # type: ignore[arg-type]
    assert _saldo() is not None
