"""Normalización y validación de nombre y código (`design.md` D6, tarea
4.2). Puro: sin acceso a datos, sin `organizacion_id` (la unicidad la
valida el servicio/repositorio, no esta capa)."""

from __future__ import annotations

from app.modules.catalogo.domain.errores import CodigoInvalidoError, NombreInvalidoError


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
