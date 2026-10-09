"""Acceso a datos de `stock` (`docs/02-arquitectura.md` §7, §8, `CLAUDE.md` §4).
Mismo contrato no negociable que `cuentas_corrientes/repository.py`: toda función
pública recibe `organizacion_id` como primer parámetro obligatorio y lo usa para
filtrar toda consulta (`tests/unit/test_repositorios_organizacion_obligatoria.py`).

Ninguna suma se hace en Python (`CLAUDE.md` §4, STK-04, INV-12): el saldo nuevo
(`cantidad_base + cantidad`), la condición de saldo suficiente
(`WHERE cantidad_base >= :cantidad`, `02` §7.4), la suma del libro, el saldo
anterior de un período, el acumulado del kardex (`SUM(...) OVER (ORDER BY
occurred_at, id)`) y la consulta de consistencia se calculan con SQL. La
`cantidad` con signo de un movimiento la decide el dominio y llega como dato.

Ninguna función borra ni actualiza `stock_movimiento`: es un libro de solo
inserción y el usuario de aplicación no tiene `UPDATE` ni `DELETE` sobre él
(STK-03, INV-05). `stock_saldo` y `ubicacion` sí se actualizan (`02` §7.2).

Traducción de errores de la base a errores de dominio (`design.md` D7, D9, Risks):
`ux_ubicacion__nombre` a `NombreDuplicadoError` (409); las FK compuestas que
validan que el producto, la ubicación o el motivo existan en la organización a
`RecursoNoEncontradoError` (404, INV-21, SEG-07, ADR-035 punto 4); y un `integer
out of range` de la cantidad a `CantidadFueraDeRangoError`. El `flush` ocurre
dentro de un `SAVEPOINT` (`begin_nested`) para que el error no deje la sesión
inutilizable y el bus pueda revertir la transacción entera.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from app.modules.stock.domain.errores import (
    CantidadFueraDeRangoError,
    NombreDuplicadoError,
    RecursoNoEncontradoError,
)
from app.modules.stock.domain.kardex import (
    DiferenciaDeStock,
    LineaDeKardex,
    codificar_cursor,
    decodificar_cursor,
    limite_efectivo,
)
from app.modules.stock.models import (
    AjusteStock,
    AjusteStockLinea,
    StockMovimiento,
    StockSaldo,
    Transferencia,
    TransferenciaLinea,
    Ubicacion,
)

# Las FK que garantizan que el producto, la ubicación o el motivo existen en la
# organización (INV-02): una referencia ajena o inexistente es 404, no un error de
# integridad.
_FK_A_404 = {
    "fk_stock_saldo__producto": "El producto no existe en esta organización.",
    "fk_stock_movimiento__producto": "El producto no existe en esta organización.",
    "fk_stock_saldo__ubicacion": "La ubicación no existe en esta organización.",
    "fk_stock_movimiento__ubicacion": "La ubicación no existe en esta organización.",
    "fk_stock_movimiento__motivo": "El motivo no existe en esta organización.",
    "fk_transferencia__origen": "La ubicación no existe en esta organización.",
    "fk_transferencia__destino": "La ubicación no existe en esta organización.",
    "fk_transferencia_linea__producto": "El producto no existe en esta organización.",
}


def _con_traduccion[T](sesion: Session, operacion: Callable[[], T]) -> T:
    """Ejecuta `operacion` dentro de un `SAVEPOINT` y traduce los errores de la
    base que tienen significado de negocio (D7, D9, Risks)."""
    try:
        with sesion.begin_nested():
            return operacion()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_ubicacion__nombre" in mensaje:
            raise NombreDuplicadoError(
                "Ya existe una ubicación con ese nombre en la organización."
            ) from error
        for restriccion, texto in _FK_A_404.items():
            if restriccion in mensaje:
                raise RecursoNoEncontradoError(texto) from error
        raise
    except DataError as error:
        mensaje = str(getattr(error, "orig", error))
        if "integer out of range" in mensaje:
            raise CantidadFueraDeRangoError(
                "La cantidad o el saldo resultante no entra en un entero de 32 bits."
            ) from error
        raise


# --- ubicación (STK-02, D7, D8) ------------------------------------------------


def crear_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID,
    nombre: str,
    tipo: str,
    requiere_toma: bool,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> Ubicacion:
    """Inserta una ubicación ya validada por `domain/`."""
    ubicacion = Ubicacion(
        id=ubicacion_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        tipo=tipo,
        requiere_toma=requiere_toma,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    _con_traduccion(sesion, lambda: sesion.add(ubicacion))
    return ubicacion


def obtener_ubicacion(
    organizacion_id: UUID, sesion: Session, *, ubicacion_id: UUID, para_actualizar: bool = False
) -> Ubicacion | None:
    """Ubicación de la organización, o `None`. Con `para_actualizar`, `SELECT ...
    FOR UPDATE`: nadie registra movimientos sobre ella mientras se modifica (D8).
    `populate_existing` para que el valor devuelto sea el de la base."""
    consulta = (
        select(Ubicacion)
        .where(Ubicacion.organizacion_id == organizacion_id, Ubicacion.id == ubicacion_id)
        .execution_options(populate_existing=True)
    )
    if para_actualizar:
        consulta = consulta.with_for_update()
    return sesion.scalars(consulta).one_or_none()


def listar_ubicaciones(
    organizacion_id: UUID,
    sesion: Session,
    *,
    activo: bool | None,
    despues_de_id: UUID | None,
    limite: int,
) -> list[Ubicacion]:
    """Ubicaciones de la organización ordenadas por `id` (UUIDv7: orden de alta),
    con filtro opcional por estado, desde la que sigue a `despues_de_id`. Pide
    `limite` filas (quien llama pide una de más para saber si hay otra página)."""
    consulta = select(Ubicacion).where(Ubicacion.organizacion_id == organizacion_id)
    if activo is not None:
        consulta = consulta.where(Ubicacion.activo == activo)
    if despues_de_id is not None:
        consulta = consulta.where(Ubicacion.id > despues_de_id)
    return list(sesion.scalars(consulta.order_by(Ubicacion.id).limit(limite)).all())


def buscar_ubicaciones_por_nombre(
    organizacion_id: UUID, sesion: Session, *, nombre: str
) -> list[Ubicacion]:
    """Ubicaciones de la organización con ese nombre, sin distinguir mayúsculas ni
    espacios al borde, activas o no (change 10, `design.md` D4)."""
    clave = nombre.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Ubicacion)
        .where(
            Ubicacion.organizacion_id == organizacion_id,
            func.lower(func.btrim(Ubicacion.nombre)) == clave,
        )
        .order_by(Ubicacion.id)
    )
    return list(sesion.scalars(consulta).all())


def bloquear_ubicaciones_compartidas(
    organizacion_id: UUID, sesion: Session, *, ubicaciones: Collection[UUID]
) -> dict[UUID, Ubicacion]:
    """`SELECT ... FOR SHARE` de cada ubicación, en orden ascendente de id. Un
    movimiento la toma antes de sus costos y saldos: así una desactivación
    concurrente (que la toma `FOR UPDATE` primero, D8) espera a que termine o hace
    esperar al movimiento, y nunca queda stock en una ubicación recién
    desactivada. Las que no existen en la organización no aparecen."""
    encontradas: dict[UUID, Ubicacion] = {}
    for ubicacion_id in sorted(set(ubicaciones)):
        consulta = (
            select(Ubicacion)
            .where(Ubicacion.organizacion_id == organizacion_id, Ubicacion.id == ubicacion_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        ubicacion = sesion.scalars(consulta).one_or_none()
        if ubicacion is not None:
            encontradas[ubicacion_id] = ubicacion
    return encontradas


def modificar_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion: Ubicacion,
    nombre: str,
    tipo: str,
    requiere_toma: bool,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> Ubicacion:
    """Actualiza los datos de una ubicación ya validados por `domain/`. Se rechaza
    una ubicación que no sea de la organización (defensa: la carga ya filtró)."""
    if ubicacion.organizacion_id != organizacion_id:  # pragma: no cover -- defensa
        raise RecursoNoEncontradoError("La ubicación no existe en esta organización.")

    def _actualizar() -> None:
        ubicacion.nombre = nombre
        ubicacion.tipo = tipo
        ubicacion.requiere_toma = requiere_toma
        ubicacion.activo = activo
        ubicacion.actualizado_en = momento
        ubicacion.actualizado_por_id = actualizado_por_id
        sesion.flush()

    _con_traduccion(sesion, _actualizar)
    return ubicacion


def hay_saldos_distintos_de_cero(
    organizacion_id: UUID, sesion: Session, *, ubicacion_id: UUID
) -> bool:
    """¿Alguna fila de `stock_saldo` de la ubicación es distinta de cero? Las filas
    se leen `FOR SHARE`, en orden de producto, para no competir con el orden global
    de bloqueo ni dejar que un movimiento las cambie mientras se decide (D8). La
    cuenta se hace en SQL sobre TODAS las filas bloqueadas."""
    bloqueadas = (
        select(StockSaldo.cantidad_base.label("cantidad_base"))
        .where(
            StockSaldo.organizacion_id == organizacion_id, StockSaldo.ubicacion_id == ubicacion_id
        )
        .order_by(StockSaldo.producto_id)
        .with_for_update(read=True)
        .subquery()
    )
    consulta = select(func.count()).select_from(bloqueadas).where(bloqueadas.c.cantidad_base != 0)
    return (sesion.scalar(consulta) or 0) > 0


def hay_saldos_del_producto_distintos_de_cero(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID
) -> bool:
    """¿Alguna fila de `stock_saldo` del producto, en cualquier ubicación de la organización, es
    distinta de cero? (change 14, D4, D4.2). Un saldo negativo cuenta, y dos saldos que suman cero
    (+5 y −5) también: se mira cada fila. Las filas se leen `FOR SHARE`, en orden de ubicación,
    para que un movimiento no las cambie mientras se decide; la cuenta se hace en SQL."""
    bloqueadas = (
        select(StockSaldo.cantidad_base.label("cantidad_base"))
        .where(StockSaldo.organizacion_id == organizacion_id, StockSaldo.producto_id == producto_id)
        .order_by(StockSaldo.ubicacion_id)
        .with_for_update(read=True)
        .subquery()
    )
    consulta = select(func.count()).select_from(bloqueadas).where(bloqueadas.c.cantidad_base != 0)
    return (sesion.scalar(consulta) or 0) > 0


# --- fila de saldo: creación perezosa y bloqueo (D10) --------------------------


def asegurar_saldo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    momento: datetime,
) -> None:
    """`INSERT ... ON CONFLICT DO NOTHING` de la fila de saldo en cero (D10). La
    carrera de la primera fila la resuelve la clave primaria; las FK compuestas
    validan acá que el producto y la ubicación existen en la organización (404)."""
    sentencia = (
        pg_insert(StockSaldo)
        .values(
            organizacion_id=organizacion_id,
            producto_id=producto_id,
            ubicacion_id=ubicacion_id,
            actualizado_en=momento,
        )
        .on_conflict_do_nothing(index_elements=["organizacion_id", "producto_id", "ubicacion_id"])
    )
    _con_traduccion(sesion, lambda: sesion.execute(sentencia))


def bloquear_saldo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID, ubicacion_id: UUID
) -> StockSaldo | None:
    """`SELECT ... FOR UPDATE` de la fila de saldo (`02` §7.3, ADR-015).
    `populate_existing` para que el valor devuelto sea el de la base y no el de
    una instancia que la sesión ya tuviera cargada."""
    consulta = (
        select(StockSaldo)
        .where(
            StockSaldo.organizacion_id == organizacion_id,
            StockSaldo.producto_id == producto_id,
            StockSaldo.ubicacion_id == ubicacion_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_saldo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID, ubicacion_id: UUID
) -> int | None:
    """Saldo materializado sin bloquear, o `None` si el par nunca tuvo un
    movimiento (no tiene fila)."""
    consulta = select(StockSaldo.cantidad_base).where(
        StockSaldo.organizacion_id == organizacion_id,
        StockSaldo.producto_id == producto_id,
        StockSaldo.ubicacion_id == ubicacion_id,
    )
    return sesion.scalar(consulta)


def ingresar_al_saldo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    cantidad: int,
    momento: datetime,
) -> int:
    """`UPDATE stock_saldo SET cantidad_base = cantidad_base + :cantidad ...
    RETURNING cantidad_base`: la suma la hace la base. Devuelve el saldo nuevo."""
    sentencia = (
        update(StockSaldo)
        .where(
            StockSaldo.organizacion_id == organizacion_id,
            StockSaldo.producto_id == producto_id,
            StockSaldo.ubicacion_id == ubicacion_id,
        )
        .values(cantidad_base=StockSaldo.cantidad_base + cantidad, actualizado_en=momento)
        .returning(StockSaldo.cantidad_base)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one())


def egresar_del_saldo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    cantidad: int,
    momento: datetime,
    permitir_negativo: bool = False,
) -> int | None:
    """`UPDATE stock_saldo SET cantidad_base = cantidad_base - :cantidad WHERE
    ... AND cantidad_base >= :cantidad RETURNING cantidad_base` (`02` §7.4): el
    egreso se aplica solo si el saldo alcanza, en una sentencia. Devuelve el saldo
    nuevo, o `None` si el saldo no alcanzaba (nada cambió). Con `permitir_negativo`
    (solo `ANULACION_COMPRA` con permiso, CMP-07) se omite la condición."""
    condiciones = [
        StockSaldo.organizacion_id == organizacion_id,
        StockSaldo.producto_id == producto_id,
        StockSaldo.ubicacion_id == ubicacion_id,
    ]
    if not permitir_negativo:
        condiciones.append(StockSaldo.cantidad_base >= cantidad)
    sentencia = (
        update(StockSaldo)
        .where(*condiciones)
        .values(cantidad_base=StockSaldo.cantidad_base - cantidad, actualizado_en=momento)
        .returning(StockSaldo.cantidad_base)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one_or_none())


# --- libro (STK-03) ------------------------------------------------------------


def insertar_movimiento(
    organizacion_id: UUID,
    sesion: Session,
    *,
    movimiento_id: UUID,
    producto_id: UUID,
    ubicacion_id: UUID,
    cantidad_base: int,
    tipo: str,
    origen_tipo: str,
    origen_id: UUID,
    costo_unitario: Decimal | None,
    jornada_id: UUID | None,
    motivo_id: UUID | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
) -> StockMovimiento:
    """Inserta un movimiento ya validado por `domain/`. `jornada_id` no tiene FK
    hasta el change 15 (D12)."""
    movimiento = StockMovimiento(
        id=movimiento_id,
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        ubicacion_id=ubicacion_id,
        cantidad_base=cantidad_base,
        tipo=tipo,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        costo_unitario=costo_unitario,
        jornada_id=jornada_id,
        motivo_id=motivo_id,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    _con_traduccion(sesion, lambda: sesion.add(movimiento))
    return movimiento


# --- transferencias (STK-07, change 14, D8) -------------------------------------


def insertar_transferencia(
    organizacion_id: UUID,
    sesion: Session,
    *,
    transferencia_id: UUID,
    ubicacion_origen_id: UUID,
    ubicacion_destino_id: UUID,
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
) -> Transferencia:
    """Inserta la cabecera `CONFIRMADA` ya validada por `domain/` (nace sin anulación)."""
    transferencia = Transferencia(
        id=transferencia_id,
        organizacion_id=organizacion_id,
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        observacion=observacion,
        estado="CONFIRMADA",
        anulacion_motivo_id=None,
        anulada_en=None,
        anulada_por_id=None,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    _con_traduccion(sesion, lambda: sesion.add(transferencia))
    return transferencia


def insertar_transferencia_linea(
    organizacion_id: UUID,
    sesion: Session,
    *,
    linea_id: UUID,
    transferencia_id: UUID,
    orden: int,
    producto_id: UUID,
    cantidad_base: int,
) -> TransferenciaLinea:
    """Inserta una línea ya validada por `domain/`; `orden` empieza en 1."""
    linea = TransferenciaLinea(
        id=linea_id,
        organizacion_id=organizacion_id,
        transferencia_id=transferencia_id,
        orden=orden,
        producto_id=producto_id,
        cantidad_base=cantidad_base,
    )
    _con_traduccion(sesion, lambda: sesion.add(linea))
    return linea


# --- ajustes (STK-08, change 14, D8) ----------------------------------------------


def insertar_ajuste(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ajuste_id: UUID,
    ubicacion_id: UUID,
    motivo_id: UUID,
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
) -> AjusteStock:
    """Inserta la cabecera `CONFIRMADA` ya validada por `domain/` (nace sin anulación)."""
    ajuste = AjusteStock(
        id=ajuste_id,
        organizacion_id=organizacion_id,
        ubicacion_id=ubicacion_id,
        motivo_id=motivo_id,
        observacion=observacion,
        estado="CONFIRMADA",
        anulacion_motivo_id=None,
        anulado_en=None,
        anulado_por_id=None,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    _con_traduccion(sesion, lambda: sesion.add(ajuste))
    return ajuste


def insertar_ajuste_linea(
    organizacion_id: UUID,
    sesion: Session,
    *,
    linea_id: UUID,
    ajuste_id: UUID,
    orden: int,
    producto_id: UUID,
    cantidad_base: int,
    costo_unitario: Decimal | None,
) -> AjusteStockLinea:
    """Inserta una línea ya validada; `costo_unitario` es el del movimiento que generó."""
    linea = AjusteStockLinea(
        id=linea_id,
        organizacion_id=organizacion_id,
        ajuste_id=ajuste_id,
        orden=orden,
        producto_id=producto_id,
        cantidad_base=cantidad_base,
        costo_unitario=costo_unitario,
    )
    _con_traduccion(sesion, lambda: sesion.add(linea))
    return linea


def lineas_de_ajuste(
    organizacion_id: UUID, sesion: Session, *, ajuste_id: UUID
) -> list[AjusteStockLinea]:
    """Las líneas de un ajuste de la organización, por `orden`."""
    return list(
        sesion.scalars(
            select(AjusteStockLinea)
            .where(
                AjusteStockLinea.organizacion_id == organizacion_id,
                AjusteStockLinea.ajuste_id == ajuste_id,
            )
            .order_by(AjusteStockLinea.orden)
        ).all()
    )


# --- lecturas de transferencias y ajustes (change 14, D7) -----------------------------------


def listar_transferencias(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: str | None,
    limite: int,
) -> tuple[list[tuple[Transferencia, str, str, int]], str | None]:
    """Transferencias de la organización de la más reciente a la más vieja, por cursor
    `(occurred_at, id)` descendente (índices `ix_transferencia__*`). Cada fila trae el nombre
    del origen y del destino y la cantidad de líneas, contada en la base. `ubicacion_id`
    alcanza a la transferencia que la tiene como origen O como destino; `desde` (inclusive) y
    `hasta` (exclusive) son instantes ya convertidos desde las fechas de negocio. Devuelve
    `(filas, cursor_siguiente)`."""
    origen = aliased(Ubicacion)
    destino = aliased(Ubicacion)
    cantidad_de_lineas = (
        select(func.count())
        .select_from(TransferenciaLinea)
        .where(
            TransferenciaLinea.organizacion_id == Transferencia.organizacion_id,
            TransferenciaLinea.transferencia_id == Transferencia.id,
        )
        .correlate(Transferencia)
        .scalar_subquery()
    )
    consulta = (
        select(Transferencia, origen.nombre, destino.nombre, cantidad_de_lineas)
        .join(
            origen,
            (origen.organizacion_id == Transferencia.organizacion_id)
            & (origen.id == Transferencia.ubicacion_origen_id),
        )
        .join(
            destino,
            (destino.organizacion_id == Transferencia.organizacion_id)
            & (destino.id == Transferencia.ubicacion_destino_id),
        )
        .where(Transferencia.organizacion_id == organizacion_id)
    )
    if ubicacion_id is not None:
        consulta = consulta.where(
            or_(
                Transferencia.ubicacion_origen_id == ubicacion_id,
                Transferencia.ubicacion_destino_id == ubicacion_id,
            )
        )
    if desde is not None:
        consulta = consulta.where(Transferencia.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(Transferencia.occurred_at < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(Transferencia.occurred_at, Transferencia.id) < (momento, id_cursor)
        )
    consulta = consulta.order_by(Transferencia.occurred_at.desc(), Transferencia.id.desc()).limit(
        limite + 1
    )

    filas = [
        (transferencia, nombre_origen, nombre_destino, int(lineas))
        for transferencia, nombre_origen, nombre_destino, lineas in sesion.execute(consulta).all()
    ]
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1][0]
        return pagina, codificar_cursor(ultima.occurred_at, ultima.id)
    return filas, None


def obtener_transferencia(
    organizacion_id: UUID, sesion: Session, *, transferencia_id: UUID
) -> tuple[Transferencia, str, str] | None:
    """La transferencia con el nombre de su origen y de su destino, sin bloquear, o `None` si
    no existe en la organización (INV-21)."""
    origen = aliased(Ubicacion)
    destino = aliased(Ubicacion)
    fila = sesion.execute(
        select(Transferencia, origen.nombre, destino.nombre)
        .join(
            origen,
            (origen.organizacion_id == Transferencia.organizacion_id)
            & (origen.id == Transferencia.ubicacion_origen_id),
        )
        .join(
            destino,
            (destino.organizacion_id == Transferencia.organizacion_id)
            & (destino.id == Transferencia.ubicacion_destino_id),
        )
        .where(
            Transferencia.organizacion_id == organizacion_id, Transferencia.id == transferencia_id
        )
    ).one_or_none()
    return None if fila is None else (fila[0], fila[1], fila[2])


def listar_ajustes(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID | None,
    motivo_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: str | None,
    limite: int,
) -> tuple[list[tuple[AjusteStock, str, int]], str | None]:
    """Ajustes de la organización de más reciente a más viejo, por cursor `(occurred_at, id)`
    descendente, con el nombre de la ubicación y la cantidad de líneas. Mismo contrato que
    `listar_transferencias`; `motivo_id` filtra por el motivo del ajuste (no por el de su
    anulación)."""
    cantidad_de_lineas = (
        select(func.count())
        .select_from(AjusteStockLinea)
        .where(
            AjusteStockLinea.organizacion_id == AjusteStock.organizacion_id,
            AjusteStockLinea.ajuste_id == AjusteStock.id,
        )
        .correlate(AjusteStock)
        .scalar_subquery()
    )
    consulta = (
        select(AjusteStock, Ubicacion.nombre, cantidad_de_lineas)
        .join(
            Ubicacion,
            (Ubicacion.organizacion_id == AjusteStock.organizacion_id)
            & (Ubicacion.id == AjusteStock.ubicacion_id),
        )
        .where(AjusteStock.organizacion_id == organizacion_id)
    )
    if ubicacion_id is not None:
        consulta = consulta.where(AjusteStock.ubicacion_id == ubicacion_id)
    if motivo_id is not None:
        consulta = consulta.where(AjusteStock.motivo_id == motivo_id)
    if desde is not None:
        consulta = consulta.where(AjusteStock.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(AjusteStock.occurred_at < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(AjusteStock.occurred_at, AjusteStock.id) < (momento, id_cursor)
        )
    consulta = consulta.order_by(AjusteStock.occurred_at.desc(), AjusteStock.id.desc()).limit(
        limite + 1
    )

    filas = [
        (ajuste, nombre_ubicacion, int(lineas))
        for ajuste, nombre_ubicacion, lineas in sesion.execute(consulta).all()
    ]
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1][0]
        return pagina, codificar_cursor(ultima.occurred_at, ultima.id)
    return filas, None


def obtener_ajuste(
    organizacion_id: UUID, sesion: Session, *, ajuste_id: UUID
) -> tuple[AjusteStock, str] | None:
    """El ajuste con el nombre de su ubicación, sin bloquear, o `None` si no existe en la
    organización (INV-21)."""
    fila = sesion.execute(
        select(AjusteStock, Ubicacion.nombre)
        .join(
            Ubicacion,
            (Ubicacion.organizacion_id == AjusteStock.organizacion_id)
            & (Ubicacion.id == AjusteStock.ubicacion_id),
        )
        .where(AjusteStock.organizacion_id == organizacion_id, AjusteStock.id == ajuste_id)
    ).one_or_none()
    return None if fila is None else (fila[0], fila[1])


def estados_de_operaciones(
    organizacion_id: UUID,
    sesion: Session,
    *,
    transferencias: Collection[UUID],
    ajustes: Collection[UUID],
) -> dict[UUID, str]:
    """Estado (`CONFIRMADA` o `ANULADA`) de las transferencias y de los ajustes pedidos, por
    id, en una consulta por tabla. Los ids son UUIDv7 únicos, así que un solo diccionario sirve
    para las dos. Lo usa el kardex para marcar la operación de origen de cada movimiento."""
    estados: dict[UUID, str] = {}
    if transferencias:
        for transferencia_id, estado in sesion.execute(
            select(Transferencia.id, Transferencia.estado).where(
                Transferencia.organizacion_id == organizacion_id,
                Transferencia.id.in_(transferencias),
            )
        ).tuples():
            estados[transferencia_id] = estado
    if ajustes:
        for ajuste_id, estado in sesion.execute(
            select(AjusteStock.id, AjusteStock.estado).where(
                AjusteStock.organizacion_id == organizacion_id,
                AjusteStock.id.in_(ajustes),
            )
        ).tuples():
            estados[ajuste_id] = estado
    return estados


# --- anulaciones (TR-06, change 14, D5) ---------------------------------------------


def obtener_transferencia_para_actualizar(
    organizacion_id: UUID, sesion: Session, *, transferencia_id: UUID
) -> Transferencia | None:
    """La cabecera de la organización con `SELECT ... FOR UPDATE`, o `None` (INV-21): es lo
    primero que toma una anulación (`02` §7.3), así dos anulaciones de la misma transferencia
    se serializan y la segunda ve el estado ya cambiado (`populate_existing`)."""
    return sesion.scalars(
        select(Transferencia)
        .where(
            Transferencia.organizacion_id == organizacion_id, Transferencia.id == transferencia_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def lineas_de_transferencia(
    organizacion_id: UUID, sesion: Session, *, transferencia_id: UUID
) -> list[TransferenciaLinea]:
    """Las líneas de una transferencia de la organización, por `orden`."""
    return list(
        sesion.scalars(
            select(TransferenciaLinea)
            .where(
                TransferenciaLinea.organizacion_id == organizacion_id,
                TransferenciaLinea.transferencia_id == transferencia_id,
            )
            .order_by(TransferenciaLinea.orden)
        ).all()
    )


def movimientos_de_origen(
    organizacion_id: UUID, sesion: Session, *, origen_tipo: str, origen_id: UUID
) -> list[StockMovimiento]:
    """Los movimientos del libro que originó una operación (por `origen_tipo` y `origen_id`),
    en el orden en que se escribieron. Solo lee: una anulación arma sus inversos con ellos
    (D5.2)."""
    return list(
        sesion.scalars(
            select(StockMovimiento)
            .where(
                StockMovimiento.organizacion_id == organizacion_id,
                StockMovimiento.origen_tipo == origen_tipo,
                StockMovimiento.origen_id == origen_id,
            )
            .order_by(StockMovimiento.registered_at, StockMovimiento.id)
        ).all()
    )


def anular_transferencia(
    organizacion_id: UUID,
    sesion: Session,
    *,
    transferencia: Transferencia,
    motivo_id: UUID,
    usuario_id: UUID,
    momento: datetime,
) -> None:
    """Pasa la cabecera (ya bloqueada) a `ANULADA` con su motivo, usuario y momento: es lo
    único que `app_runtime` puede actualizar (INV-05, D8). La cabecera tiene que ser de
    `organizacion_id` (INV-21): si no, es inexistente."""
    if transferencia.organizacion_id != organizacion_id:
        raise RecursoNoEncontradoError("La transferencia no existe en esta organización.")
    transferencia.estado = "ANULADA"
    transferencia.anulacion_motivo_id = motivo_id
    transferencia.anulada_por_id = usuario_id
    transferencia.anulada_en = momento
    _con_traduccion(sesion, sesion.flush)


def obtener_ajuste_para_actualizar(
    organizacion_id: UUID, sesion: Session, *, ajuste_id: UUID
) -> AjusteStock | None:
    """Como `obtener_transferencia_para_actualizar`, para un ajuste."""
    return sesion.scalars(
        select(AjusteStock)
        .where(AjusteStock.organizacion_id == organizacion_id, AjusteStock.id == ajuste_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def anular_ajuste(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ajuste: AjusteStock,
    motivo_id: UUID,
    usuario_id: UUID,
    momento: datetime,
) -> None:
    """Pasa la cabecera (ya bloqueada) a `ANULADA` con su motivo, usuario y momento. La
    cabecera tiene que ser de `organizacion_id` (INV-21): si no, es inexistente."""
    if ajuste.organizacion_id != organizacion_id:
        raise RecursoNoEncontradoError("El ajuste no existe en esta organización.")
    ajuste.estado = "ANULADA"
    ajuste.anulacion_motivo_id = motivo_id
    ajuste.anulado_por_id = usuario_id
    ajuste.anulado_en = momento
    _con_traduccion(sesion, sesion.flush)


def existe_movimiento(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    excluyendo_tipo: str | None = None,
) -> bool:
    """¿El producto tiene algún movimiento en la organización, en cualquier
    ubicación? Con `excluyendo_tipo`, solo de otro tipo (D4: "movimientos de otro
    tipo" que `STOCK_INICIAL`)."""
    condiciones: list[ColumnElement[bool]] = [
        StockMovimiento.organizacion_id == organizacion_id,
        StockMovimiento.producto_id == producto_id,
    ]
    if excluyendo_tipo is not None:
        condiciones.append(StockMovimiento.tipo != excluyendo_tipo)
    return sesion.scalar(select(literal(1)).where(*condiciones).limit(1)) is not None


def suma_del_libro(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID, ubicacion_id: UUID
) -> int:
    """Suma SQL de los movimientos de un producto en una ubicación (STK-04,
    INV-12). Cero si no tiene movimientos."""
    consulta = select(func.coalesce(func.sum(StockMovimiento.cantidad_base), 0)).where(
        StockMovimiento.organizacion_id == organizacion_id,
        StockMovimiento.producto_id == producto_id,
        StockMovimiento.ubicacion_id == ubicacion_id,
    )
    return int(sesion.scalar(consulta) or 0)


# --- stock por ubicación (CAT-08, D11) -----------------------------------------


def saldos_de_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID,
    despues_de_producto_id: UUID | None,
    limite: int,
) -> list[tuple[UUID, int]]:
    """Saldos distintos de cero de la ubicación, ordenados por `producto_id`,
    desde el que sigue a `despues_de_producto_id`. Pide `limite` filas (quien llama
    pide una de más para saber si hay otra página)."""
    consulta = select(StockSaldo.producto_id, StockSaldo.cantidad_base).where(
        StockSaldo.organizacion_id == organizacion_id,
        StockSaldo.ubicacion_id == ubicacion_id,
        StockSaldo.cantidad_base != 0,
    )
    if despues_de_producto_id is not None:
        consulta = consulta.where(StockSaldo.producto_id > despues_de_producto_id)
    consulta = consulta.order_by(StockSaldo.producto_id).limit(limite)
    return [(producto_id, cantidad) for producto_id, cantidad in sesion.execute(consulta).all()]


# --- kardex (STK-04, D11) ------------------------------------------------------


def _del_par(
    organizacion_id: UUID, producto_id: UUID, ubicacion_id: UUID
) -> list[ColumnElement[bool]]:
    return [
        StockMovimiento.organizacion_id == organizacion_id,
        StockMovimiento.producto_id == producto_id,
        StockMovimiento.ubicacion_id == ubicacion_id,
    ]


def saldo_anterior(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    antes_de: datetime,
) -> int:
    """Suma SQL de lo anterior al instante `antes_de` (D11: el saldo con el que
    arranca el período)."""
    consulta = select(func.coalesce(func.sum(StockMovimiento.cantidad_base), 0)).where(
        *_del_par(organizacion_id, producto_id, ubicacion_id),
        StockMovimiento.occurred_at < antes_de,
    )
    return int(sesion.scalar(consulta) or 0)


def kardex(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: str | None,
    limite: int | None,
) -> tuple[list[LineaDeKardex], str | None]:
    """Movimientos del par en orden `(occurred_at, id)` con su saldo acumulado,
    paginados por cursor `(occurred_at, id)` (D11).

    El acumulado se calcula con `SUM(...) OVER (ORDER BY occurred_at, id)` sobre
    TODA la historia del par en una subconsulta, y el período (`desde` inclusive,
    `hasta` exclusive) y el cursor se filtran después, por fuera: cada fila trae el
    saldo real y no uno que arranca de cero en cada página. Usa el índice
    `(organizacion_id, producto_id, ubicacion_id, occurred_at, id)`.

    Pide una fila de más para saber si hay otra página; `cursor_siguiente` es
    `None` en la última."""
    limite_pagina = limite_efectivo(limite)
    acumulado = (
        func.sum(StockMovimiento.cantidad_base)
        .over(order_by=(StockMovimiento.occurred_at, StockMovimiento.id))
        .label("saldo_acumulado")
    )
    con_acumulado = (
        select(
            StockMovimiento.id,
            StockMovimiento.tipo,
            StockMovimiento.cantidad_base,
            StockMovimiento.costo_unitario,
            StockMovimiento.origen_tipo,
            StockMovimiento.origen_id,
            StockMovimiento.motivo_id,
            StockMovimiento.occurred_at,
            StockMovimiento.registered_at,
            StockMovimiento.usuario_id,
            StockMovimiento.operation_id,
            acumulado,
        )
        .where(*_del_par(organizacion_id, producto_id, ubicacion_id))
        .subquery()
    )
    consulta = select(con_acumulado)
    if desde is not None:
        consulta = consulta.where(con_acumulado.c.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(con_acumulado.c.occurred_at < hasta)
    if cursor is not None:
        momento_cursor, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(con_acumulado.c.occurred_at, con_acumulado.c.id) > (momento_cursor, id_cursor)
        )
    consulta = consulta.order_by(con_acumulado.c.occurred_at, con_acumulado.c.id).limit(
        limite_pagina + 1
    )

    filas = list(sesion.execute(consulta).all())
    hay_mas = len(filas) > limite_pagina
    lineas = [
        LineaDeKardex(
            id=fila.id,
            tipo=fila.tipo,
            cantidad_base=fila.cantidad_base,
            costo_unitario=fila.costo_unitario,
            origen_tipo=fila.origen_tipo,
            origen_id=fila.origen_id,
            motivo_id=fila.motivo_id,
            occurred_at=fila.occurred_at,
            registered_at=fila.registered_at,
            usuario_id=fila.usuario_id,
            operation_id=fila.operation_id,
            saldo_acumulado=int(fila.saldo_acumulado),
        )
        for fila in filas[:limite_pagina]
    ]
    cursor_siguiente = (
        codificar_cursor(lineas[-1].occurred_at, lineas[-1].id) if hay_mas and lineas else None
    )
    return lineas, cursor_siguiente


# --- consistencia saldo vs libro (INV-12, `02` §7.6) ----------------------------


def diferencias_de_saldos_contra_el_libro(
    organizacion_id: UUID, sesion: Session
) -> list[DiferenciaDeStock]:
    """Cada `stock_saldo` de la organización contra la suma de su libro, calculado
    con SQL. Un par con movimientos y sin fila de saldo también es una diferencia
    (su saldo materializado cuenta como cero). Solo lee: no corrige nada
    (ADR-015); la tarea diaria que la ejecuta es del change 28."""
    libro = (
        select(
            StockMovimiento.producto_id.label("producto_id"),
            StockMovimiento.ubicacion_id.label("ubicacion_id"),
            func.sum(StockMovimiento.cantidad_base).label("suma"),
        )
        .where(StockMovimiento.organizacion_id == organizacion_id)
        .group_by(StockMovimiento.producto_id, StockMovimiento.ubicacion_id)
        .subquery()
    )
    saldos = (
        select(
            StockSaldo.producto_id.label("producto_id"),
            StockSaldo.ubicacion_id.label("ubicacion_id"),
            StockSaldo.cantidad_base.label("cantidad"),
        )
        .where(StockSaldo.organizacion_id == organizacion_id)
        .subquery()
    )
    producto_id = func.coalesce(saldos.c.producto_id, libro.c.producto_id)
    ubicacion_id = func.coalesce(saldos.c.ubicacion_id, libro.c.ubicacion_id)
    materializado = func.coalesce(saldos.c.cantidad, 0)
    suma = func.coalesce(libro.c.suma, 0)
    consulta = (
        select(
            producto_id.label("producto_id"),
            ubicacion_id.label("ubicacion_id"),
            materializado.label("materializado"),
            suma.label("esperado"),
        )
        .select_from(
            saldos.outerjoin(
                libro,
                (saldos.c.producto_id == libro.c.producto_id)
                & (saldos.c.ubicacion_id == libro.c.ubicacion_id),
                full=True,
            )
        )
        .where(materializado != suma)
        .order_by(producto_id, ubicacion_id)
    )
    return [
        DiferenciaDeStock(
            producto_id=fila.producto_id,
            ubicacion_id=fila.ubicacion_id,
            valor_materializado=int(fila.materializado),
            valor_esperado=int(fila.esperado),
        )
        for fila in sesion.execute(consulta).all()
    ]


def sumas_de_saldos_por_producto(organizacion_id: UUID, sesion: Session) -> dict[UUID, int]:
    """Suma SQL de los saldos de cada producto en todas sus ubicaciones: contra
    ella se verifica `costo_producto.stock_total` (INV-12)."""
    consulta = (
        select(StockSaldo.producto_id, func.sum(StockSaldo.cantidad_base))
        .where(StockSaldo.organizacion_id == organizacion_id)
        .group_by(StockSaldo.producto_id)
    )
    return {producto_id: int(suma) for producto_id, suma in sesion.execute(consulta).all()}


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Sin excepción (mismo criterio que `cuentas_corrientes.repository`): `stock` no
tiene ningún catálogo global propio -- toda función pública recibe
`organizacion_id` primero."""
