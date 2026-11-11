"""Estado de la última corrida y salud del servicio (change 28, D5 c, D6; modelo: el backup).

El servicio escribe `estado.json` en `ESTADO_DIR` y la salud de Docker lo lee con
`python -m app.tareas salud`. No es sana si la última corrida encontró diferencias o falló, o si
no hubo corrida en 26 horas (cuenta desde el arranque si todavía no hubo ninguna).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

MAXIMO_SIN_CORRIDA = timedelta(hours=26)
_ARCHIVO = "estado.json"


def leer_estado(directorio: Path) -> dict[str, object] | None:
    try:
        cargado = json.loads((directorio / _ARCHIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cargado if isinstance(cargado, dict) else None


def guardar_estado(directorio: Path, cambios: dict[str, object]) -> None:
    """Suma `cambios` al estado y lo escribe de forma atómica."""
    directorio.mkdir(parents=True, exist_ok=True)
    estado = {**(leer_estado(directorio) or {}), **cambios}
    temporal = directorio / f"{_ARCHIVO}.tmp"
    temporal.write_text(json.dumps(estado), encoding="utf-8")
    os.replace(temporal, directorio / _ARCHIVO)


def evaluar_salud(estado: dict[str, object] | None, ahora: datetime) -> tuple[bool, str]:
    """`(sana, motivo)`; el motivo se imprime para quien mira `docker compose ps` o el log."""
    if estado is None:
        return False, "no hay archivo de estado: el servicio todavía no arrancó"
    resultado = estado.get("resultado")
    if resultado == "CON_DIFERENCIAS":
        return False, f"la última corrida encontró {estado.get('diferencias')} diferencias"
    if resultado == "FALLIDA":
        return False, "la última corrida falló"
    referencia = estado.get("ultima_corrida") or estado.get("arranque")
    if not isinstance(referencia, str):
        return False, "el estado no tiene ni corrida ni arranque"
    if ahora - datetime.fromisoformat(referencia) > MAXIMO_SIN_CORRIDA:
        return False, "no hubo corrida en las últimas 26 horas"
    return True, "ok"
