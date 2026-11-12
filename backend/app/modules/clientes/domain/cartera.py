"""Reglas puras de la cartera de clientes (change 20b, `design.md` D13, D14, D15; spec
`clientes/cartera-de-clientes`; `01` §19, CLI-03, ADR-052).

Sin FastAPI, SQLAlchemy ni infraestructura: reciben datos y devuelven un resultado o lanzan un
error de dominio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.clientes.domain.errores import (
    AsignacionDeClientesInvalidaError,
    ClienteConsumidorFinalSinVendedorError,
    VendedorInvalidoError,
)

MAXIMO_CLIENTES_POR_ASIGNACION = 500

ALCANCE_TODOS = "TODOS"
ALCANCE_CARTERA = "CARTERA"


@dataclass(frozen=True)
class ClienteAsignable:
    id: UUID
    es_consumidor_final: bool


def validar_cantidad_a_asignar(cantidad: int) -> None:
    """La lista de clientes de un pedido no puede estar vacía ni pasar de 500 (422)."""
    if cantidad == 0:
        raise AsignacionDeClientesInvalidaError("Hace falta al menos un cliente.")
    if cantidad > MAXIMO_CLIENTES_POR_ASIGNACION:
        raise AsignacionDeClientesInvalidaError(
            f"Se pueden asignar hasta {MAXIMO_CLIENTES_POR_ASIGNACION} clientes por pedido."
        )


def validar_asignacion(clientes: Sequence[ClienteAsignable], vendedor_valido: bool | None) -> None:
    """Valida una asignación de vendedor antes de escribir nada (INV-01, todo o nada).

    `vendedor_valido` es `None` al quitar el vendedor, y el veredicto de
    `identidad_service.es_vendedor_valido` al asignarlo. Orden: la lista (vacía o de más de 500,
    422), el consumidor final (409, aunque solo se le quite el vendedor) y el vendedor (409)."""
    validar_cantidad_a_asignar(len(clientes))
    if any(cliente.es_consumidor_final for cliente in clientes):
        raise ClienteConsumidorFinalSinVendedorError(
            "El consumidor final no tiene vendedor: lo ven todos (CLI-03)."
        )
    if vendedor_valido is False:
        raise VendedorInvalidoError(
            "El vendedor debe estar activo, con un rol activo y con VENDER o REGISTRAR_COBRANZA."
        )


def alcance_de_opciones(
    tiene_gestionar_clientes: bool, cantidad_asignados: int, pide_todos: bool
) -> str:
    """Qué clientes ofrece la lista para vender y cobrar (D14, ADR-052): `CARTERA` (sus clientes
    más el consumidor final) solo para quien no administra clientes, tiene al menos un cliente
    asignado y no pidió todos; en cualquier otro caso, `TODOS`."""
    if tiene_gestionar_clientes or pide_todos or cantidad_asignados == 0:
        return ALCANCE_TODOS
    return ALCANCE_CARTERA
