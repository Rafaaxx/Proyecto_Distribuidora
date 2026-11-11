"""Configuración del servicio de tareas, leída del entorno (change 28, D2, D3, D6).

Es propia y no usa `app.core.config.Settings`: el servicio se conecta solo como `app_mantenimiento`
y no recibe el secreto de firma de sesiones ni ninguna otra credencial. Un valor mal armado
produce un error que nombra la variable y nunca su valor (la URL lleva la contraseña).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfiguracionInvalidaError(ValueError):
    """Variable de entorno ausente o mal armada; el mensaje nombra la variable."""


@dataclass(frozen=True)
class ConfiguracionDeTareas:
    database_url: str
    hora: time
    zona: ZoneInfo
    estado_dir: Path
    aviso_url: str | None

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> ConfiguracionDeTareas:
        from app.tareas.programador import parsear_hora

        database_url = entorno.get("DATABASE_URL", "")
        if not database_url:
            raise ConfiguracionInvalidaError(
                "Falta DATABASE_URL (la conexión de app_mantenimiento)"
            )
        nombre_zona = entorno.get("TZ") or "America/Argentina/Mendoza"
        try:
            zona = ZoneInfo(nombre_zona)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ConfiguracionInvalidaError(
                f"TZ no es una zona horaria válida: {nombre_zona}"
            ) from error
        return cls(
            database_url=database_url,
            hora=parsear_hora(entorno.get("TAREAS_HORA") or "05:00"),
            zona=zona,
            estado_dir=Path(entorno.get("ESTADO_DIR") or "/tmp/estado-tareas"),  # noqa: S108
            aviso_url=entorno.get("AVISO_TAREAS_URL") or None,
        )
