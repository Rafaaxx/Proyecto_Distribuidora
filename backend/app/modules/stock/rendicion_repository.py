"""Acceso a datos de la rendición de una jornada (change 24; `design.md` D2, D4, D5).

Archivo propio del área dentro de `stock` (ADR-049 punto 2): `service.py` sigue siendo la única
puerta pública. Aquí solo hay SQL; las reglas viven en `domain/rendicion.py` y el orden de las
operaciones en `rendicion_casos.py`.

Ninguna suma se hace en Python (`CLAUDE.md` §4, STK-04, INV-12): el desglose del esperado de cada
producto sale de UNA consulta agrupada sobre el libro de la ubicación. `rendicion` y
`rendicion_linea` son de solo inserción (INV-05): ninguna función las actualiza ni las borra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.modules.stock.domain.movimientos import (
    ANULACION_VENTA,
    TRANSFERENCIA_ENTRADA,
    VENTA,
)
from app.modules.stock.models import Rendicion, RendicionLinea, StockMovimiento, Ubicacion


@dataclass(frozen=True)
class DesgloseDeProducto:
    """El esperado de un producto en la ubicación, con la ventana de la jornada (RUT-07, D4):
    `al_abrir` es la suma anterior a la apertura; `ingresos`, `ventas` (en positivo),
    `anulaciones` y `otros` (neto, con signo) son los movimientos desde la apertura. `esperado`
    es la suma de los cinco y coincide con el saldo (INV-12)."""

    al_abrir: int
    ingresos: int
    ventas: int
    anulaciones: int
    otros: int
    con_movimiento_en_la_ventana: bool

    @property
    def esperado(self) -> int:
        return self.al_abrir + self.ingresos - self.ventas + self.anulaciones + self.otros


def desglose_por_producto(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID,
    abierta_en: datetime,
    hasta: datetime | None = None,
) -> dict[UUID, DesgloseDeProducto]:
    """Por producto, el desglose del esperado de la ubicación con la ventana desde `abierta_en`
    (por momento de registro, D4) y, con `hasta`, hasta ese momento inclusive (el resumen de una
    jornada sin rendición, D8). Devuelve solo los productos con saldo distinto de cero o con
    algún movimiento en la ventana: el conjunto a contar (D2). Una sola consulta SQL agrupada;
    quien llama tiene la ubicación `FOR UPDATE`, así que el resultado es exacto."""
    m = StockMovimiento
    en_ventana = m.registered_at >= abierta_en
    if hasta is not None:
        en_ventana = en_ventana & (m.registered_at <= hasta)

    def _suma(condicion: ColumnElement[bool]) -> ColumnElement[int]:
        return func.coalesce(func.sum(m.cantidad_base).filter(condicion), 0)

    # Lo registrado después de `hasta` no existe para esta ventana (ni en el saldo, D8).
    hasta_ahora = m.registered_at <= hasta if hasta is not None else m.registered_at.is_not(None)
    al_abrir = _suma(m.registered_at < abierta_en).label("al_abrir")
    ingresos = _suma(en_ventana & (m.tipo == TRANSFERENCIA_ENTRADA)).label("ingresos")
    ventas = (-_suma(en_ventana & (m.tipo == VENTA))).label("ventas")
    anulaciones = _suma(en_ventana & (m.tipo == ANULACION_VENTA)).label("anulaciones")
    otros = _suma(
        en_ventana & m.tipo.not_in((TRANSFERENCIA_ENTRADA, VENTA, ANULACION_VENTA))
    ).label("otros")
    movimientos = func.count().filter(en_ventana)
    consulta = (
        select(
            m.producto_id,
            al_abrir,
            ingresos,
            ventas,
            anulaciones,
            otros,
            movimientos.label("movimientos"),
        )
        .where(m.organizacion_id == organizacion_id, m.ubicacion_id == ubicacion_id, hasta_ahora)
        .group_by(m.producto_id)
        .having((func.sum(m.cantidad_base) != 0) | (movimientos > 0))
    )
    return {
        fila.producto_id: DesgloseDeProducto(
            al_abrir=int(fila.al_abrir),
            ingresos=int(fila.ingresos),
            ventas=int(fila.ventas),
            anulaciones=int(fila.anulaciones),
            otros=int(fila.otros),
            con_movimiento_en_la_ventana=int(fila.movimientos) > 0,
        )
        for fila in sesion.execute(consulta)
    }


def insertar_rendicion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    rendicion_id: UUID,
    jornada_id: UUID,
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
) -> Rendicion:
    rendicion = Rendicion(
        id=rendicion_id,
        organizacion_id=organizacion_id,
        jornada_id=jornada_id,
        observacion=observacion,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    sesion.add(rendicion)
    sesion.flush()
    return rendicion


@dataclass(frozen=True)
class LineaParaInsertar:
    """Una línea de la rendición lista para guardar: el desglose congelado, lo contado, la
    diferencia y el costo con que se valorizó (nulo sin diferencia o sin promedio)."""

    producto_id: UUID
    desglose: DesgloseDeProducto
    contado: int
    diferencia: int
    costo_unitario: Decimal | None


def insertar_lineas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    rendicion_id: UUID,
    lineas: Sequence[LineaParaInsertar],
) -> list[RendicionLinea]:
    filas = [
        RendicionLinea(
            organizacion_id=organizacion_id,
            rendicion_id=rendicion_id,
            producto_id=linea.producto_id,
            stock_al_abrir=linea.desglose.al_abrir,
            ingresos=linea.desglose.ingresos,
            ventas=linea.desglose.ventas,
            anulaciones=linea.desglose.anulaciones,
            otros=linea.desglose.otros,
            cantidad_esperada=linea.desglose.esperado,
            cantidad_contada=linea.contado,
            diferencia=linea.diferencia,
            costo_unitario=linea.costo_unitario,
        )
        for linea in lineas
    ]
    sesion.add_all(filas)
    sesion.flush()
    return filas


def leer_ubicacion(
    organizacion_id: UUID, sesion: Session, *, ubicacion_id: UUID
) -> Ubicacion | None:
    """La ubicación de la organización SIN bloquear (el destino de la devolución del cierre:
    la puerta del libro la toma `FOR SHARE` en su orden, D3), o `None` (INV-21)."""
    return sesion.scalars(
        select(Ubicacion)
        .where(Ubicacion.organizacion_id == organizacion_id, Ubicacion.id == ubicacion_id)
        .execution_options(populate_existing=True)
    ).one_or_none()


def leer_rendicion(organizacion_id: UUID, sesion: Session, *, jornada_id: UUID) -> Rendicion | None:
    """La rendición de la jornada (una sola, `UNIQUE (organizacion_id, jornada_id)`), o `None`."""
    return sesion.scalars(
        select(Rendicion).where(
            Rendicion.organizacion_id == organizacion_id, Rendicion.jornada_id == jornada_id
        )
    ).one_or_none()


@dataclass(frozen=True)
class LineaCongelada:
    """Una línea de la rendición tal como se guardó (D4): el desglose, lo contado y la diferencia,
    con el valor de la diferencia (`round(diferencia * costo, 2)` en SQL, INV-03); nulo si la
    diferencia no tiene costo (el producto no tenía promedio, CST-12)."""

    producto_id: UUID
    al_abrir: int
    ingresos: int
    ventas: int
    anulaciones: int
    otros: int
    esperado: int
    contado: int
    diferencia: int
    valor: Decimal | None


def _valor_de_la_diferencia() -> ColumnElement[Decimal]:
    linea = RendicionLinea
    return case(
        (linea.diferencia == 0, Decimal("0.00")),
        else_=func.round(linea.diferencia * linea.costo_unitario, 2),
    )


def lineas_de_rendicion(
    organizacion_id: UUID, sesion: Session, *, rendicion_id: UUID
) -> list[LineaCongelada]:
    linea = RendicionLinea
    filas = sesion.execute(
        select(
            linea.producto_id,
            linea.stock_al_abrir,
            linea.ingresos,
            linea.ventas,
            linea.anulaciones,
            linea.otros,
            linea.cantidad_esperada,
            linea.cantidad_contada,
            linea.diferencia,
            _valor_de_la_diferencia().label("valor"),
        )
        .where(linea.organizacion_id == organizacion_id, linea.rendicion_id == rendicion_id)
        .order_by(linea.producto_id)
    )
    return [
        LineaCongelada(
            producto_id=fila.producto_id,
            al_abrir=fila.stock_al_abrir,
            ingresos=fila.ingresos,
            ventas=fila.ventas,
            anulaciones=fila.anulaciones,
            otros=fila.otros,
            esperado=fila.cantidad_esperada,
            contado=fila.cantidad_contada,
            diferencia=fila.diferencia,
            valor=fila.valor,
        )
        for fila in filas
    ]


def valor_de_las_diferencias(
    organizacion_id: UUID, sesion: Session, *, rendicion_id: UUID
) -> Decimal:
    """La suma, en la base, del valor de las diferencias de la rendición (las líneas sin costo
    no suman)."""
    linea = RendicionLinea
    return sesion.scalar(
        select(func.coalesce(func.sum(_valor_de_la_diferencia()), Decimal("0.00"))).where(
            linea.organizacion_id == organizacion_id, linea.rendicion_id == rendicion_id
        )
    ) or Decimal("0.00")
