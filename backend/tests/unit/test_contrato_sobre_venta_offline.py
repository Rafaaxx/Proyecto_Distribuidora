"""Change 22a, tarea 3.3 (`design.md` D2; SYN-01, SYN-06): el fixture de contrato
`shared/fixtures/sync/venta-confirmar-offline.json` (el sobre que arma el teléfono) valida con el
esquema del lote (`ItemLoteComandoRequest`) y su contenido con `VentaConfirmarRequest`, sin
errores de esquema. Es la mitad "esquema" del contrato; la mitad "el lote lo acepta" está en
`tests/integration/test_contrato_sobre_venta_offline.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.sync.schemas import ItemLoteComandoRequest
from app.modules.ventas.schemas import VentaConfirmarRequest

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "venta-confirmar-offline.json"
)


def _con_ids_reales() -> dict[str, Any]:
    """El sobre del fixture con cada identificador simbólico sustituido por un UUID nuevo (el
    mismo símbolo, el mismo UUID; `{{numero}}` no es un UUID)."""
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))
    texto = json.dumps(crudo["sobre"])
    for simbolo in crudo["simbolos"]:
        reemplazo = "V03-000142" if simbolo == "{{numero}}" else str(uuid4())
        texto = texto.replace(simbolo, reemplazo)
    assert "{{" not in texto, "quedó un identificador simbólico sin declarar en `simbolos`"
    resultado: dict[str, Any] = json.loads(texto)
    return resultado


def test_syn01_el_sobre_del_fixture_valida_como_item_del_lote() -> None:
    item = ItemLoteComandoRequest.model_validate(_con_ids_reales())

    assert (item.tipo, item.version, item.modo) == ("VENTA_CONFIRMAR", 1, "OFFLINE")
    assert item.jornada_id is not None
    assert item.occurred_at.utcoffset() is not None  # UTC explícito, no una fecha ingenua


def test_syn06_el_contenido_valida_como_venta_confirmar_sin_credenciales() -> None:
    sobre = _con_ids_reales()

    venta = VentaConfirmarRequest.model_validate(sobre["contenido"])

    assert venta.credenciales == []
    assert venta.credito is not None
    assert venta.credito.resolucion == "TOLERANCIA_OFFLINE"
    assert venta.credito.autorizador_id is None
    assert venta.total == "29687.50"
    assert [linea.cantidad for linea in venta.lineas] == [2, 3]
    assert venta.cobranza is not None
    assert len(venta.cobranza.medios) == 2


def test_adr056_el_lote_rechaza_un_sobre_con_credenciales() -> None:
    """Contrapunto: el esquema del lote prohíbe campos ajenos (`extra="forbid"`)."""
    sobre = _con_ids_reales()
    sobre["credenciales"] = [{"autorizador_id": str(uuid4()), "pin": "123456"}]

    with pytest.raises(ValidationError):
        ItemLoteComandoRequest.model_validate(sobre)
