"""Tarea 8.1 (change 18b; spec `clientes/datos-de-credito`, `design.md` D5, D8, D14): los datos de
crédito de la venta se resuelven con la herencia de la organización. Función pura.

Reglas citadas: CRE-01, CRE-03, CRE-06.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.clientes.domain.credito import DatosDeCredito, resolver_datos_de_credito


def _resolver(**cambios: object) -> DatosDeCredito:
    base: dict[str, object] = {
        "limite_cliente": None,
        "politica_cliente": None,
        "tolerancia_tipo_cliente": None,
        "tolerancia_valor_cliente": None,
        "politica_organizacion": "AUTORIZAR",
        "tolerancia_tipo_organizacion": None,
        "tolerancia_valor_organizacion": None,
    }
    base.update(cambios)
    return resolver_datos_de_credito(**base)  # type: ignore[arg-type]


def test_cre03_sin_politica_propia_hereda_la_de_la_organizacion() -> None:
    assert _resolver(politica_organizacion="BLOQUEAR").politica == "BLOQUEAR"


def test_cre03_la_politica_propia_gana_sobre_la_de_la_organizacion() -> None:
    assert _resolver(politica_cliente="ADVERTIR", politica_organizacion="BLOQUEAR").politica == (
        "ADVERTIR"
    )


def test_cre01_el_limite_nunca_se_hereda_nulo_es_sin_control() -> None:
    assert _resolver().limite is None
    assert _resolver(limite_cliente=Decimal("0.00")).limite == Decimal("0.00")
    assert _resolver(limite_cliente=Decimal("200000.00")).limite == Decimal("200000.00")


def test_cre06_sin_tolerancia_propia_hereda_el_par_de_la_organizacion() -> None:
    datos = _resolver(
        tolerancia_tipo_organizacion="IMPORTE", tolerancia_valor_organizacion=Decimal("20000.00")
    )

    assert (datos.tolerancia_tipo, datos.tolerancia_valor) == ("IMPORTE", Decimal("20000.00"))


def test_cre06_la_tolerancia_propia_reemplaza_el_par_entero() -> None:
    datos = _resolver(
        tolerancia_tipo_cliente="PORCENTAJE",
        tolerancia_valor_cliente=Decimal("2.50"),
        tolerancia_tipo_organizacion="IMPORTE",
        tolerancia_valor_organizacion=Decimal("20000.00"),
    )

    assert (datos.tolerancia_tipo, datos.tolerancia_valor) == ("PORCENTAJE", Decimal("2.50"))


def test_cre06_sin_tolerancia_en_ninguno_queda_vacia() -> None:
    datos = _resolver()

    assert (datos.tolerancia_tipo, datos.tolerancia_valor) == (None, None)
