"""Change 22d, tarea 4.1 (`design.md` D1 y D6; SYN-01, VTA-24): los sobres del fixture de contrato
`shared/fixtures/sync/venta-anular-offline.json`, con los identificadores reales de la base de
prueba, los acepta el lote con PostgreSQL real. Es la mitad "el lote lo acepta"; la mitad "esquema"
está en `tests/unit/test_fixture_venta_anular_offline.py`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, lote
from venta_anular_offline_utiles import vender
from ventas_anular_utiles import EntornoAnulacion

from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "venta-anular-offline.json"
)


def _item_del_fixture(
    nombre: str, entorno: EntornoAnulacion, ruta: Ruta, venta_id: UUID
) -> ItemLote:
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))
    reales = {
        "{{operation_id}}": str(uuid4()),
        "{{usuario_id}}": str(entorno.usuario_id),
        "{{dispositivo_id}}": str(entorno.dispositivo_id),
        "{{jornada_id}}": str(ruta.jornada_id),
        "{{venta_id}}": str(venta_id),
        "{{motivo_id}}": str(entorno.motivo_anulacion_id),
    }
    assert set(reales) == set(crudo["simbolos"]), "el fixture declara símbolos desconocidos"
    texto = json.dumps(crudo["sobres"][nombre])
    for simbolo, valor in reales.items():
        texto = texto.replace(simbolo, valor)
    sobre: dict[str, Any] = json.loads(texto)
    return ItemLote(
        operation_id=UUID(sobre["operation_id"]),
        tipo=sobre["tipo"],
        version=sobre["version"],
        modo=sobre["modo"],
        usuario_id=UUID(sobre["usuario_id"]),
        dispositivo_id=UUID(sobre["dispositivo_id"]),
        occurred_at=datetime.fromisoformat(sobre["occurred_at"]),
        secuencia=sobre["secuencia"],
        app_version=sobre["app_version"],
        contenido=sobre["contenido"],
        jornada_id=UUID(sobre["jornada_id"]),
    )


@pytest.mark.parametrize(
    ("nombre", "con_cobro", "cobranza_anulada"),
    [("con_devolucion", True, True), ("sin_devolucion", True, False), ("sin_cobro", False, False)],
)
def test_syn01_el_lote_acepta_cada_sobre_del_fixture_y_el_reenvio_no_duplica(
    db_session: Session, nombre: str, con_cobro: bool, cobranza_anulada: bool
) -> None:
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    venta_id = vender(ruta, **({"cobranza": entorno.cobranza()} if con_cobro else {}))
    item = _item_del_fixture(nombre, entorno, ruta, venta_id)

    primero = lote(entorno, item)[item.operation_id]
    segundo = lote(entorno, item)[item.operation_id]

    assert primero.estado == "ACEPTADO", primero
    assert primero.resultado is not None
    assert primero.resultado["cobranza_anulada"] is cobranza_anulada
    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert len(entorno.anulaciones_de_venta()) == 1
    assert entorno.venta(venta_id).estado == "ANULADA"
