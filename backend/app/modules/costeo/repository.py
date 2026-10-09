"""Acceso a datos de `costeo` (`docs/02-arquitectura.md` §7, §8, `CLAUDE.md` §4).
Mismo contrato no negociable que `cuentas_corrientes/repository.py`: toda función
pública recibe `organizacion_id` como primer parámetro obligatorio y lo usa para
filtrar toda consulta (`tests/unit/test_repositorios_organizacion_obligatoria.py`).

Ninguna suma se hace en Python (`CLAUDE.md` §4): el nuevo `stock_total` sale de
`UPDATE ... SET stock_total = stock_total + :cantidad` en la base. El promedio
nuevo lo decide `domain/` con la fila ya bloqueada y llega como dato.

Ninguna función actualiza ni borra `costo_producto_mov`: es un libro de solo
inserción y el usuario de aplicación no tiene `UPDATE` ni `DELETE` (CST-13,
INV-05). `costo_producto` sí se actualiza (`02` §7.2).

Traducción de errores de la base a errores de dominio (`design.md` D9, Risks): la
FK compuesta que valida que el producto exista en la organización
(`fk_costo_producto__producto`, `fk_costo_producto_mov__producto`) se traduce a
`RecursoNoEncontradoError` (404, INV-21, SEG-07) y un `integer out of range` del
stock total a `StockFueraDeRangoError`. El `flush` ocurre dentro de un `SAVEPOINT`
(`begin_nested`) para que el error no deje la sesión inutilizable y el bus pueda
revertir la transacción entera.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.modules.costeo.domain.errores import RecursoNoEncontradoError, StockFueraDeRangoError
from app.modules.costeo.models import CostoProducto, CostoProductoMov

_FK_DE_PRODUCTO = ("fk_costo_producto__producto", "fk_costo_producto_mov__producto")


def _con_traduccion[T](sesion: Session, operacion: Callable[[], T]) -> T:
    """Ejecuta `operacion` dentro de un `SAVEPOINT` y traduce los errores de la
    base que tienen significado de negocio."""
    try:
        with sesion.begin_nested():
            return operacion()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if any(fk in mensaje for fk in _FK_DE_PRODUCTO):
            raise RecursoNoEncontradoError("El producto no existe en esta organización.") from error
        raise
    except DataError as error:
        mensaje = str(getattr(error, "orig", error))
        if "integer out of range" in mensaje:
            raise StockFueraDeRangoError(
                "El stock total resultante no entra en un entero de 32 bits."
            ) from error
        raise


# --- fila de costo: creación perezosa y bloqueo (D10) ------------------------


def asegurar_costo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID, momento: datetime
) -> None:
    """`INSERT ... ON CONFLICT DO NOTHING` de la fila de costo (`costo_promedio`
    nulo, `stock_total` 0, D10).

    La carrera de la primera fila la resuelve la clave primaria: si dos
    transacciones la crean a la vez, la segunda espera a la primera y no hace
    nada. La FK compuesta valida acá, con un bloqueo liviano sobre la fila del
    producto, que el producto existe en la organización."""
    sentencia = (
        pg_insert(CostoProducto)
        .values(organizacion_id=organizacion_id, producto_id=producto_id, actualizado_en=momento)
        .on_conflict_do_nothing(index_elements=["organizacion_id", "producto_id"])
    )
    _con_traduccion(sesion, lambda: sesion.execute(sentencia))


def bloquear_costo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID
) -> CostoProducto | None:
    """`SELECT ... FOR UPDATE` de la fila de costo (`02` §7.3, ADR-015).
    `populate_existing` para que el valor devuelto sea el de la base y no el de
    una instancia que la sesión ya tuviera cargada."""
    consulta = (
        select(CostoProducto)
        .where(
            CostoProducto.organizacion_id == organizacion_id,
            CostoProducto.producto_id == producto_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_costo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID
) -> CostoProducto | None:
    """Fila de costo sin bloquear, o `None` si el producto nunca tuvo un
    movimiento (no tiene fila)."""
    consulta = (
        select(CostoProducto)
        .where(
            CostoProducto.organizacion_id == organizacion_id,
            CostoProducto.producto_id == producto_id,
        )
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_promedios(
    organizacion_id: UUID, sesion: Session, *, productos: Collection[UUID]
) -> dict[UUID, Decimal]:
    """Promedio vigente de cada producto que ya tiene uno. Los productos sin fila
    o sin ingresos con costo no aparecen (D10)."""
    if not productos:
        return {}
    consulta = select(CostoProducto.producto_id, CostoProducto.costo_promedio).where(
        CostoProducto.organizacion_id == organizacion_id,
        CostoProducto.producto_id.in_(productos),
        CostoProducto.costo_promedio.is_not(None),
    )
    return {
        producto_id: promedio
        for producto_id, promedio in sesion.execute(consulta).all()
        if promedio is not None
    }


def obtener_stock_totales(organizacion_id: UUID, sesion: Session) -> dict[UUID, int]:
    """`stock_total` materializado de cada producto de la organización que tiene
    fila de costo."""
    consulta = select(CostoProducto.producto_id, CostoProducto.stock_total).where(
        CostoProducto.organizacion_id == organizacion_id
    )
    return {producto_id: total for producto_id, total in sesion.execute(consulta).all()}


def aplicar_ingreso_al_costo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    costo_promedio: Decimal,
    cantidad: int,
    momento: datetime,
) -> int:
    """`UPDATE costo_producto SET costo_promedio = :nuevo, stock_total =
    stock_total + :cantidad ... RETURNING stock_total`: la suma la hace la base.
    Devuelve el stock total nuevo."""
    sentencia = (
        update(CostoProducto)
        .where(
            CostoProducto.organizacion_id == organizacion_id,
            CostoProducto.producto_id == producto_id,
        )
        .values(
            costo_promedio=costo_promedio,
            stock_total=CostoProducto.stock_total + cantidad,
            actualizado_en=momento,
        )
        .returning(CostoProducto.stock_total)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one())


def aplicar_egreso_al_costo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    cantidad: int,
    momento: datetime,
) -> int:
    """`UPDATE costo_producto SET stock_total = stock_total - :cantidad ...
    RETURNING stock_total`. NO toca el promedio (CST-12). Devuelve el stock total
    nuevo."""
    sentencia = (
        update(CostoProducto)
        .where(
            CostoProducto.organizacion_id == organizacion_id,
            CostoProducto.producto_id == producto_id,
        )
        .values(stock_total=CostoProducto.stock_total - cantidad, actualizado_en=momento)
        .returning(CostoProducto.stock_total)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one())


def sumar_al_stock_total(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    cantidad: int,
    momento: datetime,
) -> int:
    """`UPDATE costo_producto SET stock_total = stock_total + :cantidad ... RETURNING
    stock_total`. NO toca el promedio (CST-12): el ingreso sin costo de una transferencia,
    un ajuste o un inverso de anulación. Devuelve el stock total nuevo."""
    sentencia = (
        update(CostoProducto)
        .where(
            CostoProducto.organizacion_id == organizacion_id,
            CostoProducto.producto_id == producto_id,
        )
        .values(stock_total=CostoProducto.stock_total + cantidad, actualizado_en=momento)
        .returning(CostoProducto.stock_total)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one())


# --- historia del promedio (CST-13) -------------------------------------------


def insertar_historia(
    organizacion_id: UUID,
    sesion: Session,
    *,
    historia_id: UUID,
    producto_id: UUID,
    origen_tipo: str,
    origen_id: UUID,
    cantidad: int,
    costo_ingreso: Decimal,
    stock_anterior: int,
    promedio_anterior: Decimal | None,
    stock_nuevo: int,
    promedio_nuevo: Decimal,
    recalculado: bool,
    operation_id: UUID,
    registered_at: datetime,
) -> CostoProductoMov:
    """Inserta una fila de la historia del promedio ya calculada por `domain/`."""
    fila = CostoProductoMov(
        id=historia_id,
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        cantidad=cantidad,
        costo_ingreso=costo_ingreso,
        stock_anterior=stock_anterior,
        promedio_anterior=promedio_anterior,
        stock_nuevo=stock_nuevo,
        promedio_nuevo=promedio_nuevo,
        recalculado=recalculado,
        operation_id=operation_id,
        registered_at=registered_at,
    )
    _con_traduccion(sesion, lambda: sesion.add(fila))
    return fila


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Sin excepción (mismo criterio que `cuentas_corrientes.repository`): `costeo`
no tiene ningún catálogo global propio -- toda función pública recibe
`organizacion_id` primero."""
