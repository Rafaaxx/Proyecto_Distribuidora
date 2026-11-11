"""Limpieza de `intento_login` (ADR-018, ADR-057 punto 9; change 28, D3, D7).

Borra, en una sola transacción, los intentos de inicio de sesión de más de 24 horas respecto del
reloj inyectable. Lo hace con el rol `app_mantenimiento`: `app_runtime` no tiene `DELETE` sobre la
tabla (INV-05). Registra cuántas filas borró, sin pares ni direcciones IP. No toca la auditoría.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.modules.identidad import service as identidad_service

logger = logging.getLogger("app.tareas.limpieza")


def limpiar_intentos_de_login(fabrica: sessionmaker[Session], reloj: Clock) -> int:
    """Devuelve cuántas filas borró."""
    with fabrica() as sesion:
        borradas = identidad_service.limpiar_intentos_de_login(sesion, reloj)
        sesion.commit()
    logger.info("Limpieza de intentos de inicio de sesión: %d filas borradas", borradas)
    return borradas
