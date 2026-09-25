"""Handlers de comandos de `proveedores` (change 06, grupo 9; `design.md`
D3, D4, D12, D14 -- plantilla D7 del change 04, aprobada tal cual el
2026-09-22: un tipo de comando por escritura ya existente en `service.py`,
un esquema de contenido versión 1, un handler de pocas líneas que llama al
método de servicio, sin `commit` propio (lo gestiona el bus).

Tres tipos, todos `ONLINE`, `admite_offline=False` (mismo motivo que
`catalogo/commands.py`: los tres exigen `sesion`/`reloj` como parámetros de
palabra clave obligatorios y sus endpoints, cuando lleguen en el grupo 10,
llaman al handler directamente con los cuatro argumentos):

- `PROVEEDOR_CREAR`, `PROVEEDOR_MODIFICAR` -- permiso `GESTIONAR_PROVEEDORES`
  (D8; el permiso se exige en la capa de API del grupo 10, no acá: el
  catálogo de tipos de comando no modela permisos, igual que en
  `catalogo/commands.py`).
- `COSTO_INFORMAR` -- permiso `EDITAR_COSTOS` (D12).

Mismo criterio que `catalogo/commands.py` (D6 del 05): los handlers NO
atrapan errores de dominio, los dejan subir; el bus (`sync/service.py::
procesar_comando`) revierte toda la transacción, incluida la reserva del
`operation_id`, y el comando puede reintentarse con contenido corregido.

Los ids de entidades nuevas (proveedor, costos informados) se generan en el
servidor (UUIDv7, `core/ids.py`, dentro de `proveedores/service.py`) y se
devuelven en el resultado del comando.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.lote import CostoDelLote

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""


# --- PROVEEDOR_CREAR / PROVEEDOR_MODIFICAR (D7, D5/ADR-026) ----------------


class ProveedorCrearContenidoV1(BaseModel):
    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None


def manejar_proveedor_crear(
    sobre: SobreComando, contenido: ProveedorCrearContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    proveedor = proveedores_service.crear_proveedor(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        cuit=contenido.cuit,
        contacto=contenido.contacto,
        telefono=contenido.telefono,
        email=contenido.email,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"proveedor_id": str(proveedor.id)}, None


registrar_handler("PROVEEDOR_CREAR", 1, ProveedorCrearContenidoV1)(
    manejar_proveedor_crear  # type: ignore[arg-type]
)
declarar_tipo("PROVEEDOR_CREAR", admite_online=True, admite_offline=False)


class ProveedorModificarContenidoV1(BaseModel):
    proveedor_id: UUID
    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    activo: bool


def manejar_proveedor_modificar(
    sobre: SobreComando, contenido: ProveedorModificarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    proveedor = proveedores_service.modificar_proveedor(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        nombre=contenido.nombre,
        cuit=contenido.cuit,
        contacto=contenido.contacto,
        telefono=contenido.telefono,
        email=contenido.email,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"proveedor_id": str(proveedor.id)}, None


registrar_handler("PROVEEDOR_MODIFICAR", 1, ProveedorModificarContenidoV1)(
    manejar_proveedor_modificar  # type: ignore[arg-type]
)
declarar_tipo("PROVEEDOR_MODIFICAR", admite_online=True, admite_offline=False)


# --- COSTO_INFORMAR (D3, D4, D12, D14; CST-01, CST-02, INV-01, INV-18) -----


class CostoDelLoteContenidoV1(BaseModel):
    """Un costo dentro del lote (D12): decimales como string, Pydantic los
    valida como `Decimal` sin pasar por `float` (`CLAUDE.md` §4)."""

    producto_id: UUID
    presentacion_id: UUID
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal = Decimal("0")
    vigencia_desde: date
    observacion: str | None = None


class CostoInformarContenidoV1(BaseModel):
    proveedor_id: UUID
    costos: list[CostoDelLoteContenidoV1]


def manejar_costo_informar(
    sobre: SobreComando, contenido: CostoInformarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    costos = [
        CostoDelLote(
            producto_id=costo.producto_id,
            presentacion_id=costo.presentacion_id,
            valor=costo.valor,
            incluye_iva=costo.incluye_iva,
            bonificacion=costo.bonificacion,
            vigencia_desde=costo.vigencia_desde,
            observacion=costo.observacion,
        )
        for costo in contenido.costos
    ]
    creados = proveedores_service.informar_costos(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        costos=costos,
        operation_id=sobre.operation_id,
        actor_id=sobre.usuario_id,
    )
    return (
        "ACEPTADO",
        {
            "costo_ids": [str(costo.id) for costo in creados],
            "costos_base": [str(costo.costo_base) for costo in creados],
        },
        None,
    )


registrar_handler("COSTO_INFORMAR", 1, CostoInformarContenidoV1)(
    manejar_costo_informar  # type: ignore[arg-type]
)
declarar_tipo("COSTO_INFORMAR", admite_online=True, admite_offline=False)
