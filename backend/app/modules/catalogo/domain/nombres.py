"""Normalización y validación de nombre y código (`design.md` D6, tarea
4.2). Puro: sin acceso a datos, sin `organizacion_id` (la unicidad la
valida el servicio/repositorio, no esta capa)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.modules.catalogo.domain.errores import (
    CodigoInvalidoError,
    NombreInvalidoError,
    ValorObligatorioError,
)
from app.modules.catalogo.domain.presentaciones import DatosPresentacion


def normalizar_nombre(nombre: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`NOMBRE_INVALIDO`,
    spec categorias-y-marcas: "Nombre vacío o solo espacios")."""
    recortado = nombre.strip()
    if not recortado:
        raise NombreInvalidoError("El nombre no puede quedar vacío tras recortar espacios.")
    return recortado


def normalizar_codigo(codigo: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`CODIGO_INVALIDO`,
    spec productos-y-presentaciones: "El código se DEBE guardar sin
    espacios ... y NO DEBE quedar vacío")."""
    recortado = codigo.strip()
    if not recortado:
        raise CodigoInvalidoError("El código no puede quedar vacío tras recortar espacios.")
    return recortado


def normalizar_unidad_base(unidad_base: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`VALOR_OBLIGATORIO`, CAT-01:
    todo producto tiene unidad base). La misma regla para el alta por pantalla y para la
    importación de productos (TR-10)."""
    recortada = unidad_base.strip()
    if not recortada:
        raise ValorObligatorioError("La unidad base no puede quedar vacía tras recortar espacios.")
    return recortada


def normalizar_nombres_de_presentaciones(
    presentaciones: Sequence[DatosPresentacion],
) -> list[DatosPresentacion]:
    """Las presentaciones con su nombre recortado; una con nombre vacío o solo espacios
    es `NOMBRE_INVALIDO` y el producto entero se rechaza (CAT-02, INV-01)."""
    return [replace(p, nombre=normalizar_nombre(p.nombre)) for p in presentaciones]
