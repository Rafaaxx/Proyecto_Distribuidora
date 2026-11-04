"""Change 23, tarea 1.1 (`design.md` D2; SYN-01, COB-01, INV-03): el fixture de contrato
`shared/fixtures/sync/cobranza-registrar-offline.json` (los sobres que arma el teléfono al
registrar una cobranza) valida con el esquema del lote (`ItemLoteComandoRequest`) y su contenido
con el del handler (`CobranzaRegistrarContenidoV1`). Es la mitad "esquema" del contrato; la mitad
"el lote lo acepta" está en `tests/integration/test_cobranza_offline_desde_telefono.py` y la del
teléfono, en `frontend/tests/unit/sync/sobreDeCobranza.test.ts`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.cobranzas.commands import CobranzaRegistrarContenidoV1
from app.modules.sync.schemas import ItemLoteComandoRequest

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "cobranza-registrar-offline.json"
)
SOBRES = ("un_medio", "dos_medios_con_referencia", "con_observacion")


def _con_ids_reales(nombre: str) -> dict[str, Any]:
    """El sobre `nombre` con cada identificador simbólico sustituido por un UUID nuevo (el mismo
    símbolo, el mismo UUID)."""
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

    assert (item.tipo, item.version, item.modo) == ("COBRANZA_REGISTRAR", 1, "OFFLINE")
    assert item.jornada_id is not None
    assert item.occurred_at.utcoffset() is not None  # UTC explícito, no una fecha ingenua


@pytest.mark.parametrize(
    ("nombre", "importe", "referencias", "observacion"),
    [
        ("un_medio", "50000.00", [None], None),
        ("dos_medios_con_referencia", "50000.00", [None, "0042"], None),
        ("con_observacion", "12500.50", [None], "Pago de la cuota de octubre"),
    ],
)
def test_cob01_el_contenido_valida_como_cobranza_registrar_v1_y_los_medios_suman_el_importe(
    nombre: str, importe: str, referencias: list[str | None], observacion: str | None
) -> None:
    contenido = CobranzaRegistrarContenidoV1.model_validate(_con_ids_reales(nombre)["contenido"])

    assert contenido.importe == importe
    assert [m.referencia for m in contenido.medios] == referencias
    assert contenido.observacion == observacion
    # INV-08: lo que el teléfono manda ya suma el importe (y viaja como string, INV-03).
    assert sum((Decimal(m.importe) for m in contenido.medios), Decimal(0)) == Decimal(importe)


def test_adr056_el_lote_rechaza_un_sobre_con_credenciales() -> None:
    """Contrapunto: el esquema del lote prohíbe campos ajenos (`extra="forbid"`)."""
    sobre = _con_ids_reales("un_medio")
    sobre["credenciales"] = [{"autorizador_id": str(uuid4()), "pin": "123456"}]

    with pytest.raises(ValidationError):
        ItemLoteComandoRequest.model_validate(sobre)


def test_inv21_el_contenido_rechaza_organizacion_id_y_origen() -> None:
    """La organización sale del token y la cobranza nace `INDEPENDIENTE` (TR-08, COB-01)."""
    for campo, valor in (("organizacion_id", str(uuid4())), ("origen", "VENTA")):
        contenido = _con_ids_reales("un_medio")["contenido"]
        contenido[campo] = valor

        with pytest.raises(ValidationError):
            CobranzaRegistrarContenidoV1.model_validate(contenido)
