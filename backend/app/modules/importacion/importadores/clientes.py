"""Importador de clientes (`specs/importacion/importacion-de-maestros`, `design.md` D6):
una fila por cliente, solo altas, sobre `clientes.service.crear_cliente`.

Las mismas reglas que el alta individual (TR-10): el servicio normaliza el documento y
rechaza la ficha incompleta y los duplicados con sus códigos. El cliente nace `ACTIVO`, sin
crédito propio y sin lista de precios, como en `CLIENTE_CREAR`. La repetición dentro del
archivo (código o documento) se detecta antes (`FILA_DUPLICADA`).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.errors import DomainError
from app.modules.clientes import service as clientes_service
from app.modules.importacion.domain.clientes import (
    claves_de_cliente,
    columna_de_ficha_incompleta,
    datos_de_cliente,
)
from app.modules.importacion.domain.duplicados import marcar_duplicadas
from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.informe import ErrorDeFila, traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.importadores.base import ContextoDeImportacion, procesar_filas

TIPO = "CLIENTES"


def _columna(fila: FilaPlanilla, error: DomainError) -> str | None:
    return columna_de_ficha_incompleta(fila) if error.codigo == "FICHA_INCOMPLETA" else None


def importar_clientes(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    ilegibles: dict[int, ErrorDeFila] = {}
    for fila in filas:
        try:
            datos_de_cliente(fila)
        except ErrorDeValor as error:
            ilegibles[fila.fila] = traducir_error(TIPO, fila.fila, error)
    duplicadas = marcar_duplicadas(filas, claves_de_cliente)

    def crear(fila: FilaPlanilla) -> None:
        datos = datos_de_cliente(fila)
        clientes_service.crear_cliente(
            contexto.organizacion_id,
            contexto.sesion,  # type: ignore[arg-type]
            contexto.reloj,
            nombre=datos["nombre"] or "",
            codigo=datos["codigo"],
            razon_social=datos["razon_social"],
            documento_tipo=datos["documento_tipo"],
            documento_numero=datos["documento_numero"],
            direccion=datos["direccion"] or "",
            contacto=datos["contacto"] or "",
            telefono=datos["telefono"],
            email=datos["email"],
            estado_facturacion_default=datos["estado_facturacion_default"],
            actor_id=contexto.usuario_id,
        )

    return procesar_filas(
        TIPO,
        contexto.sesion,
        filas,
        crear,
        omitidas={**duplicadas, **ilegibles},
        columna=_columna,
    )
