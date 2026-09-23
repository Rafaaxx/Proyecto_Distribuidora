"""Reglas puras de presentaciones (CAT-02, CAT-03, CAT-04, `design.md`
D6). Sin acceso a datos: el servicio (`catalogo/service.py`) resuelve
"fue usada" (D2, puerto de verificadores) y llama acá con el resultado ya
calculado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.catalogo.domain.errores import (
    ProductoSinPresentacionesError,
    ReferenciaInvalidaError,
    UnidadesCongeladasError,
    UnidadesInvalidasError,
)


@dataclass(frozen=True)
class DatosPresentacion:
    """Datos de una presentación tal como llegan en el contenido de un
    alta (`PRODUCTO_CREAR`) o de un `PRESENTACION_AGREGAR` (CAT-02)."""

    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    es_referencia: bool


def validar_unidades_base(unidades_base: int) -> None:
    """CAT-02, INV-04: entero `>= 1`. `isinstance(..., bool)` se excluye a
    propósito -- `bool` es subclase de `int` en Python, y `True`/`False`
    nunca son una cantidad de unidades válida aunque `True == 1` sea cierto
    a nivel de lenguaje."""
    if isinstance(unidades_base, bool) or not isinstance(unidades_base, int):
        raise UnidadesInvalidasError(
            f"Las unidades base deben ser un entero, no {unidades_base!r}."
        )
    if unidades_base < 1:
        raise UnidadesInvalidasError(
            f"Las unidades base deben ser un entero >= 1 (recibido {unidades_base})."
        )


def validar_alta_presentaciones(presentaciones: Sequence[DatosPresentacion]) -> None:
    """CAT-02 (al menos una), CAT-03 (exactamente una referencia, de
    venta). Orden de validación (spec productos-y-presentaciones): vacío
    primero, unidades de cada una después (para que "una falla en una
    presentación no deja el producto a medias" se detecte sin que la
    quede enmascarada por la validación de referencia), y por último la
    referencia -- así una presentación con unidades inválidas nunca se
    reporta como un problema de referencia."""
    if len(presentaciones) == 0:
        raise ProductoSinPresentacionesError(
            "Un producto debe tener al menos una presentación (CAT-02)."
        )
    for presentacion in presentaciones:
        validar_unidades_base(presentacion.unidades_base)

    referencias = [presentacion for presentacion in presentaciones if presentacion.es_referencia]
    if len(referencias) != 1:
        raise ReferenciaInvalidaError(
            f"Debe haber exactamente una presentación de referencia (hay {len(referencias)})."
        )
    if not referencias[0].usar_en_venta:
        raise ReferenciaInvalidaError("La presentación de referencia debe usarse en venta.")


def validar_nueva_referencia(*, activo: bool, usar_en_venta: bool) -> None:
    """CAT-03: la presentación destino de `PRESENTACION_REFERENCIA_CAMBIAR`
    debe estar activa y usarse en venta."""
    if not activo or not usar_en_venta:
        raise ReferenciaInvalidaError(
            "La nueva referencia debe estar activa y usarse en venta (CAT-03)."
        )


def validar_modificacion_presentacion(
    *,
    es_referencia: bool,
    unidades_base_actual: int,
    unidades_base_nueva: int,
    usar_en_venta_nuevo: bool,
    activo_nuevo: bool,
    fue_usada: bool,
) -> None:
    """`PRESENTACION_MODIFICAR` (CAT-03, CAT-04, INV-18): la referencia no
    se desactiva ni deja la venta (para eso primero se cambia la
    referencia); las unidades de una presentación usada no cambian (se
    crea una nueva y se desactiva la anterior); el resto (nombre, usos,
    actividad de una no-referencia) se permite sin restricción adicional
    de esta función."""
    if es_referencia and (not usar_en_venta_nuevo or not activo_nuevo):
        raise ReferenciaInvalidaError(
            "La presentación de referencia no puede desactivarse ni dejar de "
            "usarse en venta: cambiá primero la referencia (CAT-03)."
        )
    validar_unidades_base(unidades_base_nueva)
    if unidades_base_nueva != unidades_base_actual and fue_usada:
        raise UnidadesCongeladasError(
            "Las unidades de una presentación ya usada no pueden modificarse "
            "(CAT-04, INV-18): creá una presentación nueva y desactivá esta."
        )
