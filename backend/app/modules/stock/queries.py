"""Casos de uso de lectura de transferencias y ajustes de stock (change 14, tareas 10.1 y
10.2; `design.md` D5, D7).

Solo lee: ninguna función escribe ni bloquea. Todas reciben `organizacion_id` primero y lo usan
para filtrar (INV-21): una transferencia o un ajuste de otra organización es inexistente
(`RecursoNoEncontradoError`, 404). Los nombres de producto, motivo y usuario se resuelven por el
`service.py` de su módulo (`CLAUDE.md` §4); el costo de las líneas de un ajuste lo expone
quien llama solo con `VER_COSTOS` (ADR-036). Las cantidades de líneas se cuentan en la base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import service as identidad_service
from app.modules.stock import repository
from app.modules.stock.domain.errores import RecursoNoEncontradoError
from app.modules.stock.domain.kardex import limite_efectivo, rango_de_instantes


@dataclass(frozen=True)
class AnulacionDeOperacion:
    """Quién anuló una transferencia o un ajuste, cuándo y con qué motivo."""

    motivo_id: UUID
    motivo_nombre: str | None
    momento: datetime
    usuario_id: UUID
    usuario_nombre: str | None


@dataclass(frozen=True)
class TransferenciaDelListado:
    id: UUID
    estado: str
    ubicacion_origen_id: UUID
    ubicacion_origen_nombre: str
    ubicacion_destino_id: UUID
    ubicacion_destino_nombre: str
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    cantidad_de_lineas: int


@dataclass(frozen=True)
class PaginaDeTransferencias:
    transferencias: list[TransferenciaDelListado]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class LineaDelDetalle:
    """Una línea de transferencia o de ajuste con el producto y su presentación de referencia
    (CAT-08). `costo_unitario` solo existe en un ajuste y lo expone quien llama con
    `VER_COSTOS`."""

    orden: int
    producto_id: UUID
    producto_codigo: str | None
    producto_nombre: str | None
    cantidad_base: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    costo_unitario: Decimal | None = None


@dataclass(frozen=True)
class DetalleDeTransferencia:
    id: UUID
    estado: str
    ubicacion_origen_id: UUID
    ubicacion_origen_nombre: str
    ubicacion_destino_id: UUID
    ubicacion_destino_nombre: str
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    registered_at: datetime
    lineas: list[LineaDelDetalle]
    anulacion: AnulacionDeOperacion | None


@dataclass(frozen=True)
class AjusteDelListado:
    id: UUID
    estado: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    cantidad_de_lineas: int


@dataclass(frozen=True)
class PaginaDeAjustes:
    ajustes: list[AjusteDelListado]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class DetalleDeAjuste:
    id: UUID
    estado: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    registered_at: datetime
    lineas: list[LineaDelDetalle]
    anulacion: AnulacionDeOperacion | None


def _rango(
    organizacion_id: UUID, sesion: Session, desde: date | None, hasta: date | None
) -> tuple[datetime | None, datetime | None]:
    """Las fechas de negocio del filtro (TR-04) como instantes `[desde, hasta)` en la zona
    horaria de la organización; `desde` posterior a `hasta` es `RANGO_DE_FECHAS_INVALIDO`."""
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    return rango_de_instantes(desde, hasta, organizacion.zona_horaria)


def _nombres_de_usuarios(
    organizacion_id: UUID, sesion: Session, usuarios: set[UUID]
) -> dict[UUID, str]:
    return identidad_service.obtener_nombres_de_usuarios(organizacion_id, usuarios, sesion)


def _nombres_de_motivos(
    organizacion_id: UUID, sesion: Session, motivos: set[UUID]
) -> dict[UUID, str]:
    """Nombre de cada motivo pedido: una lectura por motivo DISTINTO (un puñado por página)."""
    nombres: dict[UUID, str] = {}
    for motivo_id in motivos:
        motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
        if motivo is not None:
            nombres[motivo_id] = motivo.nombre
    return nombres


def _lineas_del_detalle(
    organizacion_id: UUID,
    sesion: Session,
    lineas: list[tuple[int, UUID, int, Decimal | None]],
) -> list[LineaDelDetalle]:
    resultado: list[LineaDelDetalle] = []
    for orden, producto_id, cantidad_base, costo_unitario in lineas:
        producto = catalogo_service.obtener_producto(organizacion_id, producto_id, sesion)
        referencia = catalogo_service.obtener_referencia_de_producto(
            organizacion_id, producto_id, sesion
        )
        resultado.append(
            LineaDelDetalle(
                orden=orden,
                producto_id=producto_id,
                producto_codigo=None if producto is None else producto.codigo,
                producto_nombre=None if producto is None else producto.nombre,
                cantidad_base=cantidad_base,
                unidades_referencia=None if referencia is None else referencia.unidades_base,
                nombre_referencia=None if referencia is None else referencia.nombre,
                costo_unitario=costo_unitario,
            )
        )
    return resultado


# --- transferencias -----------------------------------------------------------------------


def listar_transferencias(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeTransferencias:
    """Transferencias de la organización, más recientes primero, con el estado de cada una.
    `ubicacion_id` alcanza origen y destino; `desde` y `hasta` son fechas de negocio. Un
    cursor ilegible es `CURSOR_INVALIDO`; `limite` va de 1 a 200 (la API responde 422 fuera de
    rango)."""
    inicio, fin = _rango(organizacion_id, sesion, desde, hasta)
    filas, cursor_siguiente = repository.listar_transferencias(
        organizacion_id,
        sesion,
        ubicacion_id=ubicacion_id,
        desde=inicio,
        hasta=fin,
        cursor=cursor,
        limite=limite_efectivo(limite),
    )
    usuarios = _nombres_de_usuarios(organizacion_id, sesion, {fila[0].usuario_id for fila in filas})
    return PaginaDeTransferencias(
        transferencias=[
            TransferenciaDelListado(
                id=t.id,
                estado=t.estado,
                ubicacion_origen_id=t.ubicacion_origen_id,
                ubicacion_origen_nombre=nombre_origen,
                ubicacion_destino_id=t.ubicacion_destino_id,
                ubicacion_destino_nombre=nombre_destino,
                observacion=t.observacion,
                usuario_id=t.usuario_id,
                usuario_nombre=usuarios.get(t.usuario_id),
                occurred_at=t.occurred_at,
                cantidad_de_lineas=cantidad,
            )
            for t, nombre_origen, nombre_destino, cantidad in filas
        ],
        cursor_siguiente=cursor_siguiente,
    )


def obtener_detalle_de_transferencia(
    organizacion_id: UUID, sesion: Session, transferencia_id: UUID
) -> DetalleDeTransferencia:
    """La transferencia con sus líneas (código, nombre y unidades de referencia, sin costo) y,
    si está anulada, el motivo, el usuario y el momento de la anulación. 404 si no existe en
    la organización (INV-21)."""
    encontrada = repository.obtener_transferencia(
        organizacion_id, sesion, transferencia_id=transferencia_id
    )
    if encontrada is None:
        raise RecursoNoEncontradoError("La transferencia no existe en esta organización.")
    transferencia, nombre_origen, nombre_destino = encontrada

    usuarios_pedidos = {transferencia.usuario_id}
    if transferencia.anulada_por_id is not None:
        usuarios_pedidos.add(transferencia.anulada_por_id)
    usuarios = _nombres_de_usuarios(organizacion_id, sesion, usuarios_pedidos)

    anulacion = None
    if (
        transferencia.anulada_en is not None
        and transferencia.anulacion_motivo_id is not None
        and transferencia.anulada_por_id is not None
    ):
        motivos = _nombres_de_motivos(organizacion_id, sesion, {transferencia.anulacion_motivo_id})
        anulacion = AnulacionDeOperacion(
            motivo_id=transferencia.anulacion_motivo_id,
            motivo_nombre=motivos.get(transferencia.anulacion_motivo_id),
            momento=transferencia.anulada_en,
            usuario_id=transferencia.anulada_por_id,
            usuario_nombre=usuarios.get(transferencia.anulada_por_id),
        )
    return DetalleDeTransferencia(
        id=transferencia.id,
        estado=transferencia.estado,
        ubicacion_origen_id=transferencia.ubicacion_origen_id,
        ubicacion_origen_nombre=nombre_origen,
        ubicacion_destino_id=transferencia.ubicacion_destino_id,
        ubicacion_destino_nombre=nombre_destino,
        observacion=transferencia.observacion,
        usuario_id=transferencia.usuario_id,
        usuario_nombre=usuarios.get(transferencia.usuario_id),
        occurred_at=transferencia.occurred_at,
        registered_at=transferencia.registered_at,
        lineas=_lineas_del_detalle(
            organizacion_id,
            sesion,
            [
                (linea.orden, linea.producto_id, linea.cantidad_base, None)
                for linea in repository.lineas_de_transferencia(
                    organizacion_id, sesion, transferencia_id=transferencia_id
                )
            ],
        ),
        anulacion=anulacion,
    )


# --- ajustes ---------------------------------------------------------------------------------


def listar_ajustes(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID | None = None,
    motivo_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeAjustes:
    """Ajustes de la organización, más recientes primero, con el estado y el motivo de cada
    uno. Mismo contrato de filtros y paginación que `listar_transferencias`."""
    inicio, fin = _rango(organizacion_id, sesion, desde, hasta)
    filas, cursor_siguiente = repository.listar_ajustes(
        organizacion_id,
        sesion,
        ubicacion_id=ubicacion_id,
        motivo_id=motivo_id,
        desde=inicio,
        hasta=fin,
        cursor=cursor,
        limite=limite_efectivo(limite),
    )
    usuarios = _nombres_de_usuarios(organizacion_id, sesion, {fila[0].usuario_id for fila in filas})
    motivos = _nombres_de_motivos(organizacion_id, sesion, {fila[0].motivo_id for fila in filas})
    return PaginaDeAjustes(
        ajustes=[
            AjusteDelListado(
                id=a.id,
                estado=a.estado,
                ubicacion_id=a.ubicacion_id,
                ubicacion_nombre=nombre_ubicacion,
                motivo_id=a.motivo_id,
                motivo_nombre=motivos.get(a.motivo_id),
                observacion=a.observacion,
                usuario_id=a.usuario_id,
                usuario_nombre=usuarios.get(a.usuario_id),
                occurred_at=a.occurred_at,
                cantidad_de_lineas=cantidad,
            )
            for a, nombre_ubicacion, cantidad in filas
        ],
        cursor_siguiente=cursor_siguiente,
    )


def obtener_detalle_de_ajuste(
    organizacion_id: UUID, sesion: Session, ajuste_id: UUID
) -> DetalleDeAjuste:
    """El ajuste con su motivo, sus líneas (con el costo con que se valorizó cada una: quien
    lo expone decide si el usuario tiene `VER_COSTOS`) y, si está anulado, el motivo, el
    usuario y el momento de la anulación. 404 si no existe en la organización (INV-21)."""
    encontrado = repository.obtener_ajuste(organizacion_id, sesion, ajuste_id=ajuste_id)
    if encontrado is None:
        raise RecursoNoEncontradoError("El ajuste no existe en esta organización.")
    ajuste, nombre_ubicacion = encontrado

    usuarios_pedidos = {ajuste.usuario_id}
    motivos_pedidos = {ajuste.motivo_id}
    if ajuste.anulado_por_id is not None:
        usuarios_pedidos.add(ajuste.anulado_por_id)
    if ajuste.anulacion_motivo_id is not None:
        motivos_pedidos.add(ajuste.anulacion_motivo_id)
    usuarios = _nombres_de_usuarios(organizacion_id, sesion, usuarios_pedidos)
    motivos = _nombres_de_motivos(organizacion_id, sesion, motivos_pedidos)

    anulacion = None
    if (
        ajuste.anulado_en is not None
        and ajuste.anulacion_motivo_id is not None
        and ajuste.anulado_por_id is not None
    ):
        anulacion = AnulacionDeOperacion(
            motivo_id=ajuste.anulacion_motivo_id,
            motivo_nombre=motivos.get(ajuste.anulacion_motivo_id),
            momento=ajuste.anulado_en,
            usuario_id=ajuste.anulado_por_id,
            usuario_nombre=usuarios.get(ajuste.anulado_por_id),
        )
    return DetalleDeAjuste(
        id=ajuste.id,
        estado=ajuste.estado,
        ubicacion_id=ajuste.ubicacion_id,
        ubicacion_nombre=nombre_ubicacion,
        motivo_id=ajuste.motivo_id,
        motivo_nombre=motivos.get(ajuste.motivo_id),
        observacion=ajuste.observacion,
        usuario_id=ajuste.usuario_id,
        usuario_nombre=usuarios.get(ajuste.usuario_id),
        occurred_at=ajuste.occurred_at,
        registered_at=ajuste.registered_at,
        lineas=_lineas_del_detalle(
            organizacion_id,
            sesion,
            [
                (linea.orden, linea.producto_id, linea.cantidad_base, linea.costo_unitario)
                for linea in repository.lineas_de_ajuste(
                    organizacion_id, sesion, ajuste_id=ajuste_id
                )
            ],
        ),
        anulacion=anulacion,
    )
