"""Change 22d, tarea 4.1 (`design.md` D1 y D6; SYN-01, VTA-24): el fixture de contrato
`shared/fixtures/sync/venta-anular-offline.json` (los sobres que arma el teléfono al anular una
venta de su jornada) valida con el esquema del lote (`ItemLoteComandoRequest`) y su contenido con
el del handler (`VentaAnularContenidoV1`). Es la mitad "esquema" del contrato; la mitad "el lote lo
acepta" está en `tests/integration/test_contrato_sobre_venta_anular_offline.py` y la del teléfono,
en `frontend/tests/unit/sync/sobreDeAnulacion.test.ts`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.sync.schemas import ItemLoteComandoRequest
from app.modules.ventas.commands import VentaAnularContenidoV1

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "venta-anular-offline.json"
)
SOBRES = ("con_devolucion", "sin_devolucion", "sin_cobro")


def _con_ids_reales(nombre: str) -> dict[str, Any]:
    """El sobre `nombre` del fixture con cada identificador simbólico sustituido por un UUID nuevo
    (el mismo símbolo, el mismo UUID)."""
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))
    texto = json.dumps(crudo["sobres"][nombre])
    for simbolo in crudo["simbolos"]:
        texto = texto.replace(simbolo, str(uuid4()))
    assert "{{" not in texto, "quedó un identificador simbólico sin declarar en `simbolos`"
    resultado: dict[str, Any] = json.loads(texto)
    return resultado


def test_syn01_el_fixture_trae_los_tres_sobres_y_no_declara_simbolos_de_mas() -> None:
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))

    assert tuple(crudo["sobres"]) == SOBRES
    usados = json.dumps(crudo["sobres"])
    assert all(simbolo in usados for simbolo in crudo["simbolos"])


@pytest.mark.parametrize("nombre", SOBRES)
def test_syn01_cada_sobre_del_fixture_valida_como_item_del_lote(nombre: str) -> None:
    item = ItemLoteComandoRequest.model_validate(_con_ids_reales(nombre))

    assert (item.tipo, item.version, item.modo) == ("VENTA_ANULAR", 1, "OFFLINE")
    assert item.jornada_id is not None
    assert item.occurred_at.utcoffset() is not None  # UTC explícito, no una fecha ingenua


@pytest.mark.parametrize(
    ("nombre", "devuelve_dinero", "observacion"),
    [
        ("con_devolucion", True, "El cliente no recibio la mercaderia"),
        ("sin_devolucion", False, None),
        ("sin_cobro", None, None),
    ],
)
def test_vta24_el_contenido_valida_como_venta_anular_v1(
    nombre: str, devuelve_dinero: bool | None, observacion: str | None
) -> None:
    sobre = _con_ids_reales(nombre)

    contenido = VentaAnularContenidoV1.model_validate(sobre["contenido"])

    assert contenido.devuelve_dinero is devuelve_dinero
    assert contenido.observacion == observacion


def test_vta22_el_sobre_sin_cobro_omite_devuelve_dinero_en_vez_de_mandar_null() -> None:
    """La indicación del dinero se omite cuando la venta no tuvo cobro en el acto (VTA-22)."""
    assert "devuelve_dinero" not in _con_ids_reales("sin_cobro")["contenido"]
    assert "devuelve_dinero" in _con_ids_reales("sin_devolucion")["contenido"]


def test_adr056_el_lote_rechaza_un_sobre_con_credenciales() -> None:
    """Contrapunto: el esquema del lote prohíbe campos ajenos (`extra="forbid"`)."""
    sobre = _con_ids_reales("con_devolucion")
    sobre["credenciales"] = [{"autorizador_id": str(uuid4()), "pin": "123456"}]

    with pytest.raises(ValidationError):
        ItemLoteComandoRequest.model_validate(sobre)


def test_inv03_el_contenido_rechaza_un_campo_ajeno_como_el_importe() -> None:
    """La anulación es total: no hay importe ni `organizacion_id` en el contenido (TR-08)."""
    contenido = _con_ids_reales("con_devolucion")["contenido"]
    contenido["importe"] = "100.00"

    with pytest.raises(ValidationError):
        VentaAnularContenidoV1.model_validate(contenido)
