"""Datos de la organización que se imprimen en la nota de venta (change 20, D10, VTA-13).

Dominio puro: sin SQLAlchemy ni FastAPI. Normaliza el domicilio y el teléfono: recorta los
espacios, pasa el vacío a nulo y rechaza lo que excede el largo permitido (los mismos topes que
los `CHECK` de `configuracion_organizacion`).
"""

from __future__ import annotations

from app.core.errors import DomainError

DOMICILIO_MAXIMO = 200
TELEFONO_MAXIMO = 50


class DatoDeNotaInvalidoError(DomainError):
    """Domicilio o teléfono de la nota fuera de los topes de largo (VTA-13, change 20 D10)."""

    codigo = "DATO_DE_NOTA_INVALIDO"
    status_http = 422


def _normalizar(valor: str | None, *, maximo: int, campo: str) -> str | None:
    if valor is None:
        return None
    recortado = valor.strip()
    if not recortado:
        return None
    if len(recortado) > maximo:
        raise DatoDeNotaInvalidoError(
            f"El {campo} de la nota no puede superar los {maximo} caracteres (VTA-13)."
        )
    return recortado


def normalizar_datos_de_nota(
    domicilio: str | None, telefono: str | None
) -> tuple[str | None, str | None]:
    """`(domicilio, telefono)` listos para guardar: recortados, vacío a `None`; lanza
    `DatoDeNotaInvalidoError` si alguno supera su largo máximo."""
    return (
        _normalizar(domicilio, maximo=DOMICILIO_MAXIMO, campo="domicilio"),
        _normalizar(telefono, maximo=TELEFONO_MAXIMO, campo="teléfono"),
    )
