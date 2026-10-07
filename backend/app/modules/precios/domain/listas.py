"""Datos de una lista de precios: el nombre (PRC-01, `design.md` D13; spec
`precios/listas-de-precios`). Funciones puras."""

from __future__ import annotations

from app.modules.precios.domain.errores import NombreInvalidoError


def normalizar_nombre(nombre: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`NOMBRE_INVALIDO`, TR-10). La
    unicidad sin distinguir mayúsculas (`NOMBRE_DUPLICADO`) la garantiza la base con
    `ux_lista_precio__nombre`."""
    recortado = nombre.strip()
    if not recortado:
        raise NombreInvalidoError("El nombre de la lista no puede quedar vacío.")
    return recortado
