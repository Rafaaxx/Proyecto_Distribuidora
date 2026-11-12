"""Nombre y CUIT de la organización (change 20, D15, VTA-13, CLI-05).

Dominio puro: sin SQLAlchemy ni FastAPI. El nombre se recorta, no puede quedar vacío y tiene un
máximo de 200 caracteres. El CUIT es opcional: se descartan guiones y espacios (los puntos no se
aceptan), debe quedar en exactamente 11 dígitos y el vacío pasa a nulo. Sin dígito verificador,
igual que el CUIT del proveedor y el documento CUIT del cliente.
"""

from __future__ import annotations

from app.core.errors import DomainError

NOMBRE_DE_ORGANIZACION_MAXIMO = 200
CUIT_LARGO = 11

_DIGITOS = frozenset("0123456789")
_SEPARADORES = frozenset("- ")


class NombreDeOrganizacionInvalidoError(DomainError):
    """Nombre vacío o de más de 200 caracteres (VTA-13, change 20 D15)."""

    codigo = "NOMBRE_DE_ORGANIZACION_INVALIDO"
    status_http = 422


class CuitInvalidoError(DomainError):
    """CUIT de la organización que no queda en 11 dígitos (CLI-05, change 20 D15)."""

    codigo = "CUIT_INVALIDO"
    status_http = 422


def normalizar_nombre_de_organizacion(texto: str) -> str:
    """El nombre recortado; lanza `NombreDeOrganizacionInvalidoError` si queda vacío o supera
    `NOMBRE_DE_ORGANIZACION_MAXIMO` caracteres."""
    recortado = texto.strip()
    if not recortado:
        raise NombreDeOrganizacionInvalidoError("El nombre de la organización es obligatorio.")
    if len(recortado) > NOMBRE_DE_ORGANIZACION_MAXIMO:
        raise NombreDeOrganizacionInvalidoError(
            f"El nombre de la organización no puede superar los "
            f"{NOMBRE_DE_ORGANIZACION_MAXIMO} caracteres."
        )
    return recortado


def normalizar_cuit_de_organizacion(texto: str | None) -> str | None:
    """Los 11 dígitos del CUIT, o `None` si viene vacío; lanza `CuitInvalidoError` si trae otros
    caracteres que dígitos, guiones y espacios, o si no quedan exactamente 11 dígitos."""
    if texto is None:
        return None
    recortado = texto.strip()
    if not recortado:
        return None
    if not all(c in _DIGITOS or c in _SEPARADORES for c in recortado):
        raise CuitInvalidoError("El CUIT solo admite dígitos, guiones y espacios.")
    digitos = "".join(c for c in recortado if c in _DIGITOS)
    if len(digitos) != CUIT_LARGO:
        raise CuitInvalidoError(f"El CUIT debe tener {CUIT_LARGO} dígitos.")
    return digitos
