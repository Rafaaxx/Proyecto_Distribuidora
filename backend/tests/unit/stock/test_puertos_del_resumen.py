"""Change 24, tarea 10.1/11.1: `stock` lee las ventas y las cobranzas de una jornada por puertos que
registran `ventas` y `cobranzas` (nunca las importa: contratos de import-linter). Sin lector
registrado falla cerrado, no devuelve un resumen sin dinero (RUT-07)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.modules.stock import service as stock_service
from app.modules.stock.domain.resumen import TotalDeVentas, VentasDeJornada

CORTE = datetime(2026, 11, 4, 18, tzinfo=UTC)


def _ventas(total: str) -> VentasDeJornada:
    vacio = TotalDeVentas(0, Decimal("0.00"))
    return VentasDeJornada(TotalDeVentas(1, Decimal(total)), vacio, vacio, vacio)


def test_sin_lector_de_ventas_registrado_falla_cerrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stock_service, "_LECTOR_DE_VENTAS", None)

    with pytest.raises(RuntimeError, match="ventas"):
        stock_service.ventas_de_jornada(uuid4(), None, jornada_id=uuid4(), corte=None)  # type: ignore[arg-type]


def test_sin_lector_de_cobranzas_registrado_falla_cerrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stock_service, "_LECTOR_DE_COBRANZAS", None)

    with pytest.raises(RuntimeError, match="cobranzas"):
        stock_service.cobranzas_de_jornada(uuid4(), None, jornada_id=uuid4(), corte=None)  # type: ignore[arg-type]


def test_el_lector_registrado_recibe_organizacion_jornada_y_corte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recibido: list[Any] = []

    def lector(organizacion_id: Any, sesion: Any, jornada_id: Any, corte: Any) -> VentasDeJornada:
        recibido.append((organizacion_id, jornada_id, corte))
        return _ventas("100.00")

    monkeypatch.setattr(stock_service, "_LECTOR_DE_VENTAS", None)
    stock_service.registrar_lector_de_ventas_de_jornada(lector)
    organizacion, jornada = uuid4(), uuid4()

    resultado = stock_service.ventas_de_jornada(organizacion, None, jornada_id=jornada, corte=CORTE)  # type: ignore[arg-type]

    assert recibido == [(organizacion, jornada, CORTE)]
    assert resultado.vigentes.total == Decimal("100.00")
