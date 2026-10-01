"""Errores de dominio de `costeo` (`CLAUDE.md` §5): código estable, heredan de
`DomainError`.

`COSTO_INVALIDO` lo nombran la spec `costeo/costo-promedio` y la de stock inicial
(`design.md` D6). `CANTIDAD_INVALIDA`, `PROMEDIO_INCONSISTENTE`,
`STOCK_FUERA_DE_RANGO` y `ORIGEN_COSTO_INVALIDO` son defensas del servicio para
quien lo llame con datos que el esquema de un comando ya habría rechazado, o para un estado que este
change no produce (un promedio nulo con stock positivo).

Un producto que no existe en la organización del token, o que pertenece a otra,
es `RecursoNoEncontradoError` (INV-21, SEG-07): 404, no 403.
"""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """El producto no existe en la organización del token (o pertenece a otra)
    (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class CostoInvalidoError(DomainError):
    """Costo que no es un decimal exacto positivo con hasta 6 decimales, o que
    no entra en `numeric(18,6)` (`design.md` D6, TR-02, INV-03)."""

    codigo = "COSTO_INVALIDO"
    status_http = 422


class CantidadInvalidaError(DomainError):
    """Cantidad base que no es un entero positivo (INV-04). El signo de un
    movimiento lo decide quien llama: el ingreso y el egreso reciben magnitud."""

    codigo = "CANTIDAD_INVALIDA"
    status_http = 422


class PromedioInconsistenteError(DomainError):
    """Producto con stock total positivo y sin costo promedio. `design.md` D10
    deja el promedio nulo solo hasta el primer ingreso con costo, así que este
    estado no lo produce ningún camino de este change."""

    codigo = "PROMEDIO_INCONSISTENTE"
    status_http = 409


class StockFueraDeRangoError(DomainError):
    """El stock total resultante no entra en `integer` (INV-04)."""

    codigo = "STOCK_FUERA_DE_RANGO"
    status_http = 422


class OrigenDeCostoInvalidoError(DomainError):
    """`origen_tipo` fuera de los cuatro que dejan historia del promedio
    (`03` §7, `design.md` D13)."""

    codigo = "ORIGEN_COSTO_INVALIDO"
    status_http = 422
