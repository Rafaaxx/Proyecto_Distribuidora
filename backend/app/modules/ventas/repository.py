"""Acceso a datos de `ventas`. Toda consulta filtra por `organizacion_id` (INV-02, INV-21) y la
carga de relaciones es siempre explícita (`CLAUDE.md` §4)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, exists, false, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql import ColumnElement

from app.modules.ventas.domain.consultas import codificar_cursor, decodificar_cursor
from app.modules.ventas.domain.errores import NumeroDuplicadoError
from app.modules.ventas.models import Venta, VentaAnulacion, VentaLinea, VentaLineaDescuento


def presentacion_figura_en_alguna_linea(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    """`True` si la presentación figura en alguna línea de venta, de cualquier estado de venta
    (INV-18, TR-06: una venta anulada sigue contando)."""
    consulta = select(
        exists().where(
            VentaLinea.organizacion_id == organizacion_id,
            VentaLinea.presentacion_id == presentacion_id,
        )
    )
    return bool(sesion.scalar(consulta))


def existe_venta(organizacion_id: UUID, venta_id: UUID, sesion: Session) -> bool:
    """`True` si el identificador ya lo usa una venta de la organización."""
    consulta = select(
        exists().where(Venta.organizacion_id == organizacion_id, Venta.id == venta_id)
    )
    return bool(sesion.scalar(consulta))


def existe_numero(organizacion_id: UUID, numero: str, sesion: Session) -> bool:
    """`True` si una venta de la organización ya usa el número (VTA-06)."""
    consulta = select(
        exists().where(Venta.organizacion_id == organizacion_id, Venta.numero == numero)
    )
    return bool(sesion.scalar(consulta))


def insertar_venta(sesion: Session, venta: Venta, lineas: Sequence[VentaLinea]) -> None:
    """Escribe la cabecera y sus líneas de una vez (INV-01); las tablas son de solo inserción.
    Una carrera por el mismo número viola `ux_venta__numero` y se traduce a `NUMERO_DUPLICADO`
    (la otra transacción ya confirmó entre la lectura previa y este insert); el punto de
    guardado deja la transacción usable para que el bus la revierta con su error."""
    try:
        with sesion.begin_nested():
            sesion.add(venta)
            sesion.flush()
    except IntegrityError as error:
        if "ux_venta__numero" in str(error.orig):
            raise NumeroDuplicadoError(f"El número {venta.numero} ya fue usado.") from error
        raise
    sesion.add_all(lineas)
    sesion.flush()


def insertar_descuentos(sesion: Session, descuentos: Sequence[VentaLineaDescuento]) -> None:
    """Escribe los descuentos congelados de las líneas de la venta (DSC-08, INV-10); solo
    inserción. Se llama después de `insertar_venta`: sus claves foráneas apuntan a las líneas."""
    sesion.add_all(descuentos)
    sesion.flush()


def listar_ventas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    cliente_id: UUID | None,
    usuario_id: UUID | None,
    jornada_id: UUID | None,
    ubicacion_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
    estado: str | None = None,
    numero: str | None = None,
) -> tuple[list[Venta], str | None]:
    """Ventas de la organización de la más reciente a la más vieja, por cursor
    `(occurred_at, id)` descendente (índices `ix_venta__occurred_at`, `ix_venta__cliente` e
    `ix_venta__usuario`, D16). `desde` es inclusivo y `hasta` exclusivo (instantes: ver
    `rango_de_instantes`). Devuelve `(filas, cursor_siguiente)`."""
    consulta = select(Venta).where(Venta.organizacion_id == organizacion_id)
    if cliente_id is not None:
        consulta = consulta.where(Venta.cliente_id == cliente_id)
    if usuario_id is not None:
        consulta = consulta.where(Venta.usuario_id == usuario_id)
    if jornada_id is not None:
        consulta = consulta.where(Venta.jornada_id == jornada_id)
    if ubicacion_id is not None:
        consulta = consulta.where(Venta.ubicacion_id == ubicacion_id)
    if estado is not None:
        consulta = consulta.where(Venta.estado == estado)
    if numero is not None and numero != "":
        # Coincidencia parcial sin distinguir mayúsculas, en la base; `%` y `_` valen como texto.
        consulta = consulta.where(Venta.numero.icontains(numero, autoescape=True))
    if desde is not None:
        consulta = consulta.where(Venta.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(Venta.occurred_at < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Venta.occurred_at, Venta.id) < (momento, id_cursor))
    consulta = consulta.order_by(Venta.occurred_at.desc(), Venta.id.desc()).limit(limite + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1]
        return pagina, codificar_cursor(ultima.occurred_at, ultima.id)
    return filas, None


def obtener_venta(organizacion_id: UUID, venta_id: UUID, sesion: Session) -> Venta | None:
    """La venta de la organización sin bloquearla (INV-21: la de otra organización no existe)."""
    return sesion.scalar(
        select(Venta).where(Venta.organizacion_id == organizacion_id, Venta.id == venta_id)
    )


def tomar_venta_para_actualizar(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> Venta | None:
    """La venta `FOR UPDATE` (change 19, D10: primera fila que toma la anulación). Relee el estado
    con la fila tomada (`populate_existing`): la lectura previa sin candado pudo ser anterior a
    una anulación concurrente."""
    return sesion.scalar(
        select(Venta)
        .where(Venta.organizacion_id == organizacion_id, Venta.id == venta_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def insertar_anulacion(sesion: Session, anulacion: VentaAnulacion) -> None:
    """La anulación de la venta (`UNIQUE (organizacion_id, venta_id)`, D11)."""
    sesion.add(anulacion)
    sesion.flush()


def marcar_venta_anulada(sesion: Session, venta: Venta) -> None:
    """El único `UPDATE` sobre `venta` (D11): `estado` pasa a `ANULADA`. `app_runtime` solo tiene
    `UPDATE (estado)`; ninguna otra columna se toca (INV-10)."""
    venta.estado = "ANULADA"
    sesion.flush()


def obtener_anulacion_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> VentaAnulacion | None:
    """La anulación de la venta, o `None` si no está anulada (D11: una por venta)."""
    return sesion.scalar(
        select(VentaAnulacion).where(
            VentaAnulacion.organizacion_id == organizacion_id, VentaAnulacion.venta_id == venta_id
        )
    )


def listar_lineas_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> list[VentaLinea]:
    """Las líneas de la venta en el orden en que se cargaron (a lo sumo 200, D8)."""
    return list(
        sesion.scalars(
            select(VentaLinea)
            .where(VentaLinea.organizacion_id == organizacion_id, VentaLinea.venta_id == venta_id)
            .order_by(VentaLinea.orden)
        ).all()
    )


def listar_descuentos_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> list[VentaLineaDescuento]:
    """Los descuentos de todas las líneas de la venta, por línea y orden (DSC-08)."""
    return list(
        sesion.scalars(
            select(VentaLineaDescuento)
            .join(
                VentaLinea,
                and_(
                    VentaLinea.organizacion_id == VentaLineaDescuento.organizacion_id,
                    VentaLinea.id == VentaLineaDescuento.venta_linea_id,
                ),
            )
            .where(
                VentaLinea.organizacion_id == organizacion_id,
                VentaLinea.venta_id == venta_id,
            )
            .order_by(VentaLinea.orden, VentaLineaDescuento.orden)
        ).all()
    )


def totales_de_ventas_de_jornada(
    organizacion_id: UUID, jornada_id: UUID, corte: datetime | None, sesion: Session
) -> tuple[tuple[int, Decimal], tuple[int, Decimal], tuple[int, Decimal], tuple[int, Decimal]]:
    """Cantidad y total de las ventas de una jornada, sumados en la base (RUT-07, change 24 D4):
    `(vigentes, anuladas, vigentes_tardias, anuladas_tardias)`.

    Vigentes: ventas `CONFIRMADA` de la jornada. Anuladas: las ventas cuya anulación se hizo con
    esa jornada (`venta_anulacion.jornada_id`, aunque la jornada ya esté liberada, ADR-066).
    Tardías: registradas después de `corte` (el momento de la rendición); sin `corte` ninguna es
    tardía."""

    def _tardia(momento: InstrumentedAttribute[datetime]) -> ColumnElement[bool]:
        return momento > corte if corte is not None else false()

    vigentes_tardia = _tardia(Venta.registered_at)
    vigentes = sesion.execute(
        select(
            func.count().filter(~vigentes_tardia),
            func.coalesce(func.sum(Venta.total).filter(~vigentes_tardia), 0),
            func.count().filter(vigentes_tardia),
            func.coalesce(func.sum(Venta.total).filter(vigentes_tardia), 0),
        ).where(
            Venta.organizacion_id == organizacion_id,
            Venta.jornada_id == jornada_id,
            Venta.estado == "CONFIRMADA",
        )
    ).one()
    anulada_tardia = _tardia(VentaAnulacion.registered_at)
    anuladas = sesion.execute(
        select(
            func.count().filter(~anulada_tardia),
            func.coalesce(func.sum(Venta.total).filter(~anulada_tardia), 0),
            func.count().filter(anulada_tardia),
            func.coalesce(func.sum(Venta.total).filter(anulada_tardia), 0),
        )
        .select_from(VentaAnulacion)
        .join(
            Venta,
            and_(
                Venta.organizacion_id == VentaAnulacion.organizacion_id,
                Venta.id == VentaAnulacion.venta_id,
            ),
        )
        .where(
            VentaAnulacion.organizacion_id == organizacion_id,
            VentaAnulacion.jornada_id == jornada_id,
        )
    ).one()
    return (
        (int(vigentes[0]), Decimal(vigentes[1])),
        (int(anuladas[0]), Decimal(anuladas[1])),
        (int(vigentes[2]), Decimal(vigentes[3])),
        (int(anuladas[2]), Decimal(anuladas[3])),
    )


def ordenes_de_lineas(
    organizacion_id: UUID, linea_ids: Sequence[UUID], sesion: Session
) -> dict[UUID, int]:
    """`{linea_id: orden}` (desde 0) de las líneas de venta de la organización entre `linea_ids`,
    en una consulta (las de otra organización no aparecen; INV-21)."""
    if not linea_ids:
        return {}
    consulta = select(VentaLinea.id, VentaLinea.orden).where(
        VentaLinea.organizacion_id == organizacion_id, VentaLinea.id.in_(list(linea_ids))
    )
    return {f.id: f.orden for f in sesion.execute(consulta)}


def resumir_ventas(
    organizacion_id: UUID, ids: Sequence[UUID], sesion: Session
) -> list[tuple[UUID, str, UUID, Decimal, datetime]]:
    """`(id, número, cliente, total, momento)` de las ventas de la organización entre `ids`, en una
    consulta (las de otra organización no aparecen; INV-21). Para el resumen de la bandeja."""
    if not ids:
        return []
    consulta = select(
        Venta.id, Venta.numero, Venta.cliente_id, Venta.total, Venta.occurred_at
    ).where(Venta.organizacion_id == organizacion_id, Venta.id.in_(list(ids)))
    return [
        (f.id, f.numero, f.cliente_id, f.total, f.occurred_at) for f in sesion.execute(consulta)
    ]
