"""Composición de las líneas de una venta (VTA-02, CAT-02, CAT-05, CAT-07, INV-04, INV-07;
`design.md` D8). Funciones puras: reciben datos y devuelven resultados o lanzan errores de
dominio de código estable."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.ventas.domain.errores import (
    CantidadInvalidaError,
    LineaDuplicadaError,
    LineasInvalidasError,
    PresentacionNoVendibleError,
    ProductoInactivoError,
    VentaSinLineasError,
)

MAXIMO_LINEAS = 200


@dataclass(frozen=True)
class LineaPedida:
    """Una línea tal como llega en el comando: producto, presentación y cantidad en esa
    presentación."""

    producto_id: UUID
    presentacion_id: UUID
    cantidad: int


def validar_lineas(lineas: Sequence[LineaPedida]) -> None:
    """De 1 a 200 líneas, cantidad entera mayor que cero (INV-04) y ningún par producto y
    presentación repetido (VTA-02). El mismo producto en dos presentaciones son dos líneas."""
    if not lineas:
        raise VentaSinLineasError("La venta necesita al menos una línea (INV-07).")
    if len(lineas) > MAXIMO_LINEAS:
        raise LineasInvalidasError(
            f"La venta admite hasta {MAXIMO_LINEAS} líneas y trae {len(lineas)}."
        )
    vistas: set[tuple[UUID, UUID]] = set()
    for posicion, linea in enumerate(lineas):
        cantidad = linea.cantidad
        if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
            raise CantidadInvalidaError(
                f"La cantidad de la línea {posicion} tiene que ser un entero mayor que cero.",
                extension={"linea": posicion},
            )
        clave = (linea.producto_id, linea.presentacion_id)
        if clave in vistas:
            raise LineaDuplicadaError(
                f"La línea {posicion} repite el producto y la presentación de otra línea.",
                extension={"linea": posicion},
            )
        vistas.add(clave)


def cantidad_base(cantidad: int, unidades_presentacion: int) -> int:
    """`cantidad × unidades de la presentación` (VTA-02)."""
    return cantidad * unidades_presentacion


def validar_producto_y_presentacion(
    *, producto_activo: bool, presentacion_activa: bool, presentacion_usar_en_venta: bool
) -> None:
    """Producto activo (CAT-05) y presentación activa con uso en venta (CAT-02)."""
    if not producto_activo:
        raise ProductoInactivoError("El producto está inactivo.")
    if not (presentacion_activa and presentacion_usar_en_venta):
        raise PresentacionNoVendibleError("La presentación está inactiva o no se usa en venta.")
