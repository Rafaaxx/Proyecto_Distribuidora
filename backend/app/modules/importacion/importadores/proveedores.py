"""Importador de proveedores (`specs/importacion/importacion-de-maestros`, `design.md`
D6, D10): una fila por proveedor, solo altas, sobre `proveedores.service.crear_proveedor`.

Las mismas reglas que el alta individual (TR-10): el servicio normaliza el nombre y el
CUIT y rechaza los inválidos y los duplicados con sus códigos. La repetición dentro
del archivo se detecta antes (`FILA_DUPLICADA`).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.modules.importacion.domain.duplicados import marcar_duplicadas
from app.modules.importacion.domain.informe import ErrorDeFila
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.proveedores import claves_de_proveedor, datos_de_proveedor
from app.modules.importacion.importadores.base import ContextoDeImportacion, procesar_filas
from app.modules.proveedores import service as proveedores_service

TIPO = "PROVEEDORES"


def importar_proveedores(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    def crear(fila: FilaPlanilla) -> None:
        datos = datos_de_proveedor(fila)
        proveedores_service.crear_proveedor(
            contexto.organizacion_id,
            contexto.sesion,  # type: ignore[arg-type]
            contexto.reloj,
            nombre=datos["nombre"] or "",
            cuit=datos["cuit"],
            contacto=datos["contacto"],
            telefono=datos["telefono"],
            email=datos["email"],
            actor_id=contexto.usuario_id,
        )

    return procesar_filas(
        TIPO,
        contexto.sesion,
        filas,
        crear,
        omitidas=marcar_duplicadas(filas, claves_de_proveedor),
    )
