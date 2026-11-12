"""Clave del contador de fallos del login (ADR-057, enmienda a ADR-018, SEG-01).

Función pura: sin FastAPI ni SQLAlchemy.
"""

from __future__ import annotations

import hashlib
import json


def clave_de_intento_login(organizacion_slug: str, nombre_usuario: str) -> str:
    """SHA-256 en hexadecimal (64 caracteres) del par escrito (slug, usuario).

    La normalización es la identidad: los dos textos tal como llegan, sin recorte ni minúsculas,
    igual que la búsqueda del login (ADR-057 punto 1); si el login pasa a normalizar, se cambia
    acá y en la búsqueda en el mismo cambio. El par se codifica como JSON de la lista
    `[slug, usuario]` (sin ambigüedad entre los dos textos) y se guarda el resumen, no el texto:
    largo fijo y sin dejar legible lo escrito (ADR-057 punto 2)."""
    codificado = json.dumps([organizacion_slug, nombre_usuario], ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(codificado).hexdigest()
