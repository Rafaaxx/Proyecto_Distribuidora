"""Spec `dinero-y-redondeo`, requisito "Los importes viajan como texto"
(`docs/02-arquitectura.md` §10.2): los importes, costos y porcentajes
DEBEN serializarse como cadena en JSON, nunca como número.

Este change no agrega ningún endpoint de negocio (llegan en el change 02),
así que el escenario se prueba con el mismo mecanismo que usará cualquier
`schemas.py` futuro: un modelo Pydantic con un campo `Decimal`, serializado
en modo `json`.
"""

from __future__ import annotations

import json
from decimal import Decimal

from pydantic import BaseModel

from app.core.money import redondear_importe


class _RecursoConImporte(BaseModel):
    importe: Decimal


def test_un_importe_redondeado_se_serializa_como_cadena_no_como_numero() -> None:
    """Escenario "Serialización de un importe": `31250` con dos decimales
    aparece en JSON como la cadena `"31250.00"`, no como número."""
    importe = redondear_importe(Decimal("31250"))
    recurso = _RecursoConImporte(importe=importe)

    serializado = recurso.model_dump(mode="json")

    assert serializado["importe"] == "31250.00"
    assert isinstance(serializado["importe"], str)

    # Y el JSON final, tal como viaja por HTTP, nunca es un literal numérico.
    texto_json = json.dumps(serializado)
    assert '"importe":"31250.00"' in texto_json.replace(" ", "")
