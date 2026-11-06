"""Casos de uso de lectura de la revisión de observaciones (change 25; `design.md` D3, D4, D5).

Solo leen: ninguna función escribe ni bloquea. Todas reciben `organizacion_id` primero y lo usan
para filtrar (INV-21). La agregación por operación y los contadores se calculan en la base
(`CLAUDE.md` §4); acá solo se arma lo que se muestra (nombres de usuarios y resumen de cada
operación, una consulta por tipo).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.resumen import SIN_REFERENCIA, ResumenDeContenido, ResumenDeOperacion, como_uuid
from app.modules.catalogo import service as catalogo_service
from app.modules.identidad import service as identidad_service
from app.modules.sync import revision_repository as repository
from app.modules.sync import service as sync_service
from app.modules.sync.domain import revision as dominio
from app.modules.sync.domain.errores import RecursoNoEncontradoError
from app.modules.sync.revision_repository import FiltroDeBandeja, FiltroDeRechazos

LIMITE_MAXIMO = 200


@dataclass(frozen=True)
class NombresDeObservacion:
    """Los nombres que el detalle de una observación solo nombra por id (lote extra del change 25,
    D3/D12). Un id que ya no existe en la organización (o es de otra: INV-21) es «(no existe)»;
    un campo que el detalle no trae queda `None`."""

    autorizador: str | None = None
    producto: str | None = None
    linea: int | None = None
    vendedor_de_jornada: str | None = None


@dataclass(frozen=True)
class ObservacionDeBandeja:
    id: UUID
    codigo: str
    detalle: dict[str, object] | None
    estado: str
    resuelto_por_id: UUID | None
    resuelto_por_nombre: str | None
    resuelto_en: datetime | None
    comentario: str | None
    nombres: NombresDeObservacion | None = None


@dataclass(frozen=True)
class OperacionObservada:
    operacion_tipo: str
    operacion_id: UUID
    estado: str
    resumen: ResumenDeOperacion | None
    usuario_id: UUID
    usuario_nombre: str | None
    dispositivo_id: UUID
    jornada_id: UUID | None
    modo: str
    occurred_at: datetime
    registered_at: datetime
    observaciones: tuple[ObservacionDeBandeja, ...]


@dataclass(frozen=True)
class PaginaDeBandeja:
    items: tuple[OperacionObservada, ...]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class ResumenDePendientes:
    observaciones_por_codigo: dict[str, int]
    observaciones_pendientes: int
    rechazos_pendientes: int
    cuarentenas_pendientes: int
    total_pendiente: int


def _ids_del_detalle(filas: list[repository.FilaDeObservacion], clave: str) -> set[UUID]:
    return {
        id_ for fila in filas if (id_ := como_uuid((fila.detalle or {}).get(clave))) is not None
    }


def _nombres_de_observaciones(
    organizacion_id: UUID, sesion: Session, filas: list[repository.FilaDeObservacion]
) -> dict[UUID, NombresDeObservacion]:
    """Los nombres de la página entera, una consulta por tipo de entidad (usuarios, productos,
    jornadas y líneas por tipo de operación): sin N+1 y siempre dentro de la organización."""
    autorizadores = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, _ids_del_detalle(filas, "autorizador_id"), sesion
    )
    productos = catalogo_service.nombres_de_productos(
        organizacion_id, _ids_del_detalle(filas, "producto_id"), sesion
    )
    vendedores = sync_service.nombres_de_jornadas(
        organizacion_id, sesion, _ids_del_detalle(filas, "jornada_id")
    )
    lineas_por_tipo: dict[str, set[UUID]] = defaultdict(set)
    for fila in filas:
        if (linea := como_uuid((fila.detalle or {}).get("linea_id"))) is not None:
            lineas_por_tipo[fila.operacion_tipo].add(linea)
    numeros: dict[tuple[str, UUID], int] = {
        (tipo, linea): numero
        for tipo, ids in lineas_por_tipo.items()
        for linea, numero in sync_service.numerar_lineas(
            organizacion_id, sesion, tipo, sorted(ids)
        ).items()
    }

    def _nombre(mapa: dict[UUID, str], id_: UUID | None) -> str | None:
        return None if id_ is None else mapa.get(id_, SIN_REFERENCIA)

    resultado: dict[UUID, NombresDeObservacion] = {}
    for fila in filas:
        detalle = fila.detalle or {}
        autorizador = como_uuid(detalle.get("autorizador_id"))
        producto = como_uuid(detalle.get("producto_id"))
        jornada = como_uuid(detalle.get("jornada_id"))
        linea = como_uuid(detalle.get("linea_id"))
        nombres = NombresDeObservacion(
            autorizador=(
                _nombre(autorizadores, autorizador)
                if fila.codigo == "AUTORIZACION_OFFLINE"
                else None
            ),
            producto=_nombre(productos, producto) if fila.codigo in _CON_PRODUCTO else None,
            linea=(
                None
                if linea is None or fila.codigo not in _CON_PRODUCTO
                else numeros.get((fila.operacion_tipo, linea))
            ),
            vendedor_de_jornada=(
                _nombre(vendedores, jornada)
                if fila.codigo == "UBICACION_TOMADA_AL_SINCRONIZAR"
                else None
            ),
        )
        if nombres != NombresDeObservacion():
            resultado[fila.id] = nombres
    return resultado


_CON_PRODUCTO = frozenset({"STOCK_NEGATIVO", "VENTA_SIN_COSTO", "PRODUCTO_DESACTIVADO"})


def listar_bandeja(
    organizacion_id: UUID,
    sesion: Session,
    filtro: FiltroDeBandeja,
    *,
    cursor: str | None,
    limite: int,
) -> PaginaDeBandeja:
    """La bandeja por operación (D3): una entrada por operación observada con todas sus
    observaciones, de la llegada más reciente a la más antigua. Un cursor ilegible es
    `CURSOR_INVALIDO`."""
    despues_de = None if cursor is None else dominio.decodificar_cursor(cursor)
    claves = repository.pagina_de_operaciones(
        organizacion_id, sesion, filtro, despues_de=despues_de, limite=limite + 1
    )
    hay_mas = len(claves) > limite
    claves = claves[:limite]
    filas = repository.observaciones_de_operaciones(organizacion_id, sesion, claves)

    por_operacion: dict[tuple[str, UUID], list[repository.FilaDeObservacion]] = defaultdict(list)
    for fila in filas:
        por_operacion[(fila.operacion_tipo, fila.operacion_id)].append(fila)

    usuarios = {fila.usuario_id for fila in filas} | {
        fila.resuelto_por_id for fila in filas if fila.resuelto_por_id is not None
    }
    nombres = identidad_service.obtener_nombres_de_usuarios(organizacion_id, usuarios, sesion)

    nombres_de_detalle = _nombres_de_observaciones(organizacion_id, sesion, filas)

    ids_por_tipo: dict[str, list[UUID]] = defaultdict(list)
    for clave in claves:
        ids_por_tipo[clave.operacion_tipo].append(clave.operacion_id)
    resumenes = {
        (tipo, id_): resumen
        for tipo, ids in ids_por_tipo.items()
        for id_, resumen in sync_service.resumir_operaciones(
            organizacion_id, sesion, tipo, ids
        ).items()
    }

    items = []
    for clave in claves:
        filas_de_la_operacion = por_operacion[(clave.operacion_tipo, clave.operacion_id)]
        primera = filas_de_la_operacion[0]
        items.append(
            OperacionObservada(
                operacion_tipo=clave.operacion_tipo,
                operacion_id=clave.operacion_id,
                estado=(
                    repository.PENDIENTE
                    if any(f.estado == repository.PENDIENTE for f in filas_de_la_operacion)
                    else repository.RESUELTA
                ),
                resumen=resumenes.get((clave.operacion_tipo, clave.operacion_id)),
                usuario_id=primera.usuario_id,
                usuario_nombre=nombres.get(primera.usuario_id),
                dispositivo_id=primera.dispositivo_id,
                jornada_id=primera.jornada_id,
                modo=primera.modo,
                occurred_at=primera.occurred_at,
                registered_at=primera.registered_at,
                observaciones=tuple(
                    ObservacionDeBandeja(
                        id=f.id,
                        codigo=f.codigo,
                        detalle=f.detalle,
                        estado=f.estado,
                        resuelto_por_id=f.resuelto_por_id,
                        resuelto_por_nombre=(
                            None if f.resuelto_por_id is None else nombres.get(f.resuelto_por_id)
                        ),
                        resuelto_en=f.resuelto_en,
                        comentario=f.comentario,
                        nombres=nombres_de_detalle.get(f.id),
                    )
                    for f in filas_de_la_operacion
                ),
            )
        )
    ultima = claves[-1] if claves else None
    return PaginaDeBandeja(
        items=tuple(items),
        cursor_siguiente=(
            dominio.codificar_cursor(ultima.llegada, ultima.operacion_id)
            if hay_mas and ultima is not None
            else None
        ),
    )


def resumen_de_pendientes(organizacion_id: UUID, sesion: Session) -> ResumenDePendientes:
    """Lo pendiente de la organización para el aviso de `/admin` (D5, CRE-09): observaciones por
    código, rechazos y cuarentenas, contados en la base."""
    por_codigo = repository.pendientes_por_codigo(organizacion_id, sesion)
    observaciones = sum(por_codigo.values())
    rechazos = repository.contar_rechazos_pendientes(organizacion_id, sesion)
    cuarentenas = repository.contar_cuarentenas_pendientes(organizacion_id, sesion)
    return ResumenDePendientes(
        observaciones_por_codigo=por_codigo,
        observaciones_pendientes=observaciones,
        rechazos_pendientes=rechazos,
        cuarentenas_pendientes=cuarentenas,
        total_pendiente=observaciones + rechazos + cuarentenas,
    )


@dataclass(frozen=True)
class RechazoLeido:
    """Un rechazo o una cuarentena para la pantalla «Rechazadas». `contenido` (lo crudo que envió
    el teléfono) solo se completa en el detalle."""

    origen: str
    id: UUID
    operation_id: UUID
    tipo: str
    estado: str
    codigo: str
    usuario_id: UUID
    usuario_nombre: str | None
    dispositivo_id: UUID
    jornada_id: UUID | None
    recibido_en: datetime
    occurred_at: datetime | None
    aceptada_despues: bool
    resumen: ResumenDeContenido | None
    resuelto_por_id: UUID | None
    resuelto_por_nombre: str | None
    resuelto_en: datetime | None
    comentario: str | None
    vinculo_tipo: str | None
    vinculo_id: UUID | None
    contenido: object | None = None


@dataclass(frozen=True)
class PaginaDeRechazos:
    items: tuple[RechazoLeido, ...]
    cursor_siguiente: str | None


def _armar_rechazos(
    organizacion_id: UUID,
    sesion: Session,
    filas: list[repository.FilaDeRechazo],
    *,
    con_contenido: bool,
) -> list[RechazoLeido]:
    """Completa las filas con los nombres, el resumen del contenido (una consulta por tipo de
    comando) y si el mismo `operation_id` se aceptó después (una consulta)."""
    usuarios = {fila.usuario_id for fila in filas} | {
        fila.resuelto_por_id for fila in filas if fila.resuelto_por_id is not None
    }
    nombres = identidad_service.obtener_nombres_de_usuarios(organizacion_id, usuarios, sesion)
    aceptadas = repository.operaciones_aceptadas_despues(
        organizacion_id, sesion, [fila.operation_id for fila in filas]
    )
    por_tipo: dict[str, list[repository.FilaDeRechazo]] = defaultdict(list)
    for fila in filas:
        por_tipo[fila.tipo].append(fila)
    resumenes: dict[UUID, ResumenDeContenido | None] = {}
    for tipo, del_tipo in por_tipo.items():
        resumidos = sync_service.resumir_contenidos(
            organizacion_id, sesion, tipo, [fila.contenido for fila in del_tipo]
        )
        resumenes.update({fila.id: r for fila, r in zip(del_tipo, resumidos, strict=True)})
    return [
        RechazoLeido(
            origen=fila.origen,
            id=fila.id,
            operation_id=fila.operation_id,
            tipo=fila.tipo,
            estado=fila.estado,
            codigo=fila.codigo,
            usuario_id=fila.usuario_id,
            usuario_nombre=nombres.get(fila.usuario_id),
            dispositivo_id=fila.dispositivo_id,
            jornada_id=fila.jornada_id,
            recibido_en=fila.recibido_en,
            occurred_at=fila.occurred_at,
            aceptada_despues=fila.operation_id in aceptadas,
            resumen=resumenes.get(fila.id),
            resuelto_por_id=fila.resuelto_por_id,
            resuelto_por_nombre=(
                None if fila.resuelto_por_id is None else nombres.get(fila.resuelto_por_id)
            ),
            resuelto_en=fila.resuelto_en,
            comentario=fila.comentario,
            vinculo_tipo=fila.vinculo_tipo,
            vinculo_id=fila.vinculo_id,
            contenido=fila.contenido if con_contenido else None,
        )
        for fila in filas
    ]


def listar_rechazos(
    organizacion_id: UUID,
    sesion: Session,
    filtro: FiltroDeRechazos,
    *,
    cursor: str | None,
    limite: int,
) -> PaginaDeRechazos:
    """Los rechazos y las cuarentenas de la organización, del más reciente al más antiguo
    (D6, D7). Un cursor ilegible es `CURSOR_INVALIDO`."""
    despues_de = None if cursor is None else dominio.decodificar_cursor(cursor)
    filas = repository.pagina_de_rechazos(
        organizacion_id, sesion, filtro, despues_de=despues_de, limite=limite + 1
    )
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    items = _armar_rechazos(organizacion_id, sesion, filas, con_contenido=False)
    ultima = filas[-1] if filas else None
    return PaginaDeRechazos(
        items=tuple(items),
        cursor_siguiente=(
            dominio.codificar_cursor(ultima.recibido_en, ultima.id)
            if hay_mas and ultima is not None
            else None
        ),
    )


def obtener_rechazo(organizacion_id: UUID, sesion: Session, id_: UUID) -> RechazoLeido:
    """Un rechazo o una cuarentena con lo crudo que envió el teléfono; 404 si no existe en la
    organización (INV-21)."""
    fila = repository.rechazo_o_cuarentena_por_id(organizacion_id, sesion, id_)
    if fila is None:
        raise RecursoNoEncontradoError("No se encontró el rechazo.")
    return _armar_rechazos(organizacion_id, sesion, [fila], con_contenido=True)[0]
