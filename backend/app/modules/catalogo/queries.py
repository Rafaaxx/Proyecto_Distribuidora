"""Casos de uso de lectura de `catalogo` para su propia API (`estructura del
backend` de `CLAUDE.md` §7; change 05, tarea 9.2).

A diferencia de `service.py` (que expone `obtener_producto`/etc. para que
OTROS módulos lean catálogo sin importar `repository.py`, tarea 7.7), este
archivo es interno del propio módulo: `catalogo/api.py` lo usa para armar
las respuestas de sus rutas `GET`, y aquí sí se llama a `repository.py`
directamente (mismo patrón que `identidad/api.py::listar_usuarios`, que
llama a `identidad/repository.py` sin pasar por `identidad/service.py`
para sus propias lecturas).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.catalogo import repository
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.models import Categoria, Marca, Presentacion, Producto


def listar_categorias_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    solo_activas: bool,
) -> tuple[list[Categoria], str | None]:
    return repository.listar_categorias_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor, solo_activas=solo_activas
    )


def listar_marcas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    solo_activas: bool,
) -> tuple[list[Marca], str | None]:
    return repository.listar_marcas_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor, solo_activas=solo_activas
    )


def listar_productos_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    texto: str | None,
    categoria_id: UUID | None,
    marca_id: UUID | None,
    activo: bool | None,
) -> tuple[list[Producto], str | None]:
    return repository.listar_productos_paginado(
        organizacion_id,
        sesion,
        limite=limite,
        cursor=cursor,
        texto=texto,
        categoria_id=categoria_id,
        marca_id=marca_id,
        activo=activo,
    )


def obtener_producto_con_presentaciones(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> tuple[Producto, list[Presentacion], str] | None:
    """Detalle de producto (tarea 9.2, change 06 tarea 10.2 -- contrato-api.md
    §3.2, D13 opción B): `None` si no existe en la organización (la ruta lo
    traduce a 404, INV-21/SEG-07). El tercer elemento es `proveedor_nombre`,
    resuelto vía el puerto de consulta de ADR-025 (`catalogo_service.
    consultar_proveedor`) -- viene siempre, con el proveedor activo o
    inactivo, sin que este módulo lea la tabla `proveedor`. La FK
    `fk_producto__proveedor` garantiza que el proveedor existe: un `None`
    del puerto es un error interno (`assert`), no un 404."""
    producto = repository.obtener_producto_por_id(organizacion_id, producto_id, sesion)
    if producto is None:
        return None
    presentaciones = repository.listar_presentaciones_de_producto(
        organizacion_id, producto_id, sesion
    )
    estado_proveedor = catalogo_service.consultar_proveedor(
        organizacion_id, producto.proveedor_id, sesion
    )
    assert estado_proveedor is not None  # la FK del producto garantiza su existencia.
    return producto, presentaciones, estado_proveedor.nombre
