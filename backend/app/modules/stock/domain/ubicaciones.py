"""Reglas puras de la ubicación (STK-02, `design.md` D7, D8).

Sin acceso a datos y sin `organizacion_id`: la unicidad del nombre la garantiza
`ux_ubicacion__nombre` y la traduce el repositorio a `NOMBRE_DUPLICADO`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.stock.domain.errores import (
    NombreInvalidoError,
    TipoDeUbicacionInvalidoError,
    UbicacionConStockError,
    VehiculoRequiereTomaError,
)

DEPOSITO = "DEPOSITO"
VEHICULO = "VEHICULO"
OTRO = "OTRO"
TIPOS_DE_UBICACION = frozenset({DEPOSITO, VEHICULO, OTRO})


@dataclass(frozen=True)
class DatosDeUbicacion:
    """Una ubicación ya validada y normalizada, lista para escribir."""

    nombre: str
    tipo: str
    requiere_toma: bool


def normalizar_nombre(nombre: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`NOMBRE_INVALIDO`,
    D7: "nombre normalizado"). La comparación para la unicidad no distingue
    mayúsculas y la hace la base."""
    recortado = nombre.strip()
    if not recortado:
        raise NombreInvalidoError("El nombre no puede quedar vacío tras recortar espacios.")
    return recortado


def validar_tipo_de_ubicacion(tipo: str) -> str:
    """`tipo` del catálogo de STK-02 o `TIPO_UBICACION_INVALIDO`."""
    if tipo not in TIPOS_DE_UBICACION:
        raise TipoDeUbicacionInvalidoError(
            f"El tipo {tipo!r} no es una ubicación válida: use DEPOSITO, VEHICULO u OTRO."
        )
    return tipo


def validar_ubicacion(*, nombre: str, tipo: str, requiere_toma: bool) -> DatosDeUbicacion:
    """Normaliza el nombre, valida el tipo y aplica STK-02: un vehículo siempre
    requiere toma (`VEHICULO_REQUIERE_TOMA`, D7). Para `DEPOSITO` y `OTRO` la
    toma es libre."""
    nombre_normalizado = normalizar_nombre(nombre)
    tipo_validado = validar_tipo_de_ubicacion(tipo)
    if tipo_validado == VEHICULO and requiere_toma is not True:
        raise VehiculoRequiereTomaError("Un vehículo siempre requiere toma (STK-02).")
    return DatosDeUbicacion(
        nombre=nombre_normalizado, tipo=tipo_validado, requiere_toma=bool(requiere_toma)
    )


def validar_desactivacion(*, tiene_saldos_distintos_de_cero: bool) -> None:
    """D8: una ubicación con algún saldo distinto de cero no se desactiva."""
    if tiene_saldos_distintos_de_cero:
        raise UbicacionConStockError(
            "La ubicación tiene stock: no se puede desactivar mientras algún saldo sea "
            "distinto de cero."
        )
