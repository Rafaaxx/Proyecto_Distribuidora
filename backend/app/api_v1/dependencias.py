"""Dependencias compartidas por los routers de negocio de `api_v1`
(`docs/02-arquitectura.md` §11): configuración y sesión de base de datos
por petición.

Separado de `app/api_v1/sistema.py` (que resuelve `Settings`/`Engine` para
sus propios endpoints) porque los routers de negocio necesitan además una
`Session` de SQLAlchemy por petición -- `sistema` no toca la ORM.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def _get_settings() -> Settings:
    """Se sobreescribe con `app.dependency_overrides` en `crear_app`."""
    raise NotImplementedError


def _get_session_factory() -> sessionmaker[Session]:
    """Se sobreescribe con `app.dependency_overrides` en `crear_app`."""
    raise NotImplementedError


def get_session(
    factory: Annotated[sessionmaker[Session], Depends(_get_session_factory)],
) -> Iterator[Session]:
    """Una `Session` por petición. Sin `commit`: cada handler confirma la
    transacción explícitamente al terminar (`design.md` D6: los endpoints de
    este change no pasan por el bus de comandos, que es quien haría el
    `commit` desde el change 04 en adelante)."""
    with factory() as sesion:
        yield sesion
