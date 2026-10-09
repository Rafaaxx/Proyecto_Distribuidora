"""Interfaz pública de `costeo` (`CLAUDE.md` §4: un módulo usa a otro solo a
través de su `service.py`).

La usan `stock` (grupo 5) y, más adelante, compras (11), ajustes (14), ventas
(18a, 19) y rendiciones (24): bloquear las filas de costo en el orden global,
aplicar un ingreso con costo (CST-11), aplicar un egreso valorizado al promedio
vigente (CST-12) y leer el promedio. Es el ÚNICO lugar que calcula costos
(CST-14, ADR-002): ningún otro módulo escribe `costo_producto` ni
`costo_producto_mov`.

Sin `commit`: la transacción la gestiona el bus de comandos o quien llama en
pruebas (`CLAUDE.md` §4). Todas las funciones reciben `organizacion_id` como
primer parámetro y lo usan para filtrar.

Toda la validación y el cálculo viven en `domain/`; acá solo se orquesta el orden:
bloquear la fila de costo (que serializa todo movimiento del producto, `02` §7.3,
ADR-015), leer sus valores ya bloqueados, decidir, actualizar y dejar la historia.
Este módulo no importa `catalogo`: que el producto exista en la organización lo
garantiza la FK compuesta de `costo_producto`, que el repositorio traduce a 404
(`design.md` D9).

`producto_tiene_movimientos_distintos_de` que nombra `tasks.md` 5.1 NO vive acá:
`design.md` D4 pide comprobar que el producto no tenga movimientos de OTRO TIPO en
el libro de stock, que es de `stock` (`costo_producto_mov` solo registra los
ingresos con costo y no vería ventas, ajustes ni transferencias).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.costeo import repository
from app.modules.costeo.domain.costo_promedio import (
    calcular_egreso,
    calcular_ingreso,
    calcular_ingreso_sin_recalculo,
    calcular_reversion,
    validar_costo,
    validar_origen_de_costo,
)
from app.modules.costeo.domain.errores import RecursoNoEncontradoError

__all__ = [
    "CostoVigente",
    "ResultadoDeEgresoAplicado",
    "ResultadoDeIngresoAplicado",
    "ResultadoDeReversionAplicada",
    "aplicar_egreso",
    "aplicar_ingreso",
    "aplicar_ingreso_sin_recalculo",
    "bloquear_costos",
    "obtener_costo",
    "obtener_promedio",
    "obtener_promedios",
    "obtener_stock_totales",
    "revertir_ingreso",
    "validar_costo",
]


@dataclass(frozen=True)
class CostoVigente:
    """Costo promedio (nulo hasta el primer ingreso con costo, D10) y stock total
    de un producto en la organización."""

    costo_promedio: Decimal | None
    stock_total: int


@dataclass(frozen=True)
class ResultadoDeIngresoAplicado:
    """Estado del producto antes y después de un ingreso con costo (CST-13)."""

    stock_anterior: int
    promedio_anterior: Decimal | None
    stock_nuevo: int
    promedio_nuevo: Decimal


@dataclass(frozen=True)
class ResultadoDeEgresoAplicado:
    """Estado del producto después de un egreso (CST-12). `costo_valorizacion` es
    `None` mientras el producto no tuvo ingresos con costo (D10)."""

    costo_valorizacion: Decimal | None
    stock_nuevo: int


@dataclass(frozen=True)
class ResultadoDeReversionAplicada:
    """Estado del producto antes y después de revertir un ingreso (CMP-06).
    `recalculado` es `False` cuando el promedio se mantuvo (D9)."""

    stock_anterior: int
    promedio_anterior: Decimal | None
    stock_nuevo: int
    promedio_nuevo: Decimal
    recalculado: bool


def bloquear_costos(
    organizacion_id: UUID, sesion: Session, reloj: Clock, productos: Collection[UUID]
) -> dict[UUID, CostoVigente]:
    """Bloquea la fila de costo de cada producto (`SELECT ... FOR UPDATE`) en orden
    ascendente de `producto_id` y sin repetidos (`02` §7.3, ADR-015), creándola en
    cero y sin promedio si no existe, sin carrera (D10). Devuelve el estado de cada
    producto ya bloqueado, en ese mismo orden. Es el segundo nivel del orden global
    de bloqueo (después de `saldo_cuenta`, antes de `stock_saldo`): `stock` lo llama
    ANTES de bloquear sus saldos. Un producto que no existe en la organización es
    `RecursoNoEncontradoError` (D9)."""
    bloqueados: dict[UUID, CostoVigente] = {}
    for producto_id in sorted(set(productos)):
        bloqueados[producto_id] = _bloquear(organizacion_id, sesion, reloj, producto_id)
    return bloqueados


def _bloquear(
    organizacion_id: UUID, sesion: Session, reloj: Clock, producto_id: UUID
) -> CostoVigente:
    repository.asegurar_costo(organizacion_id, sesion, producto_id=producto_id, momento=reloj.now())
    fila = repository.bloquear_costo(organizacion_id, sesion, producto_id=producto_id)
    if fila is None:  # pragma: no cover -- `asegurar_costo` acaba de crearla o ya existía
        raise RecursoNoEncontradoError("El producto no existe en esta organización.")
    return CostoVigente(costo_promedio=fila.costo_promedio, stock_total=fila.stock_total)


def aplicar_ingreso(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    cantidad: int,
    costo_unitario: object,
    origen_tipo: str,
    origen_id: UUID,
    operation_id: UUID,
) -> ResultadoDeIngresoAplicado:
    """Ingreso con costo (CST-11): recalcula el promedio con la fila bloqueada,
    actualiza `costo_producto` (promedio y `stock_total`) y deja la historia en
    `costo_producto_mov` (CST-13), todo en la transacción de quien llama (INV-01).

    `costo_unitario` se recibe como `object` a propósito: solo un `str` o un
    `Decimal` es dinero exacto (INV-03) y `validar_costo` rechaza el resto con
    `COSTO_INVALIDO`. Valida ANTES de escribir. Bloquea la fila si quien llama no
    lo hizo (el bloqueo repetido dentro de la transacción es inocuo)."""
    costo = validar_costo(costo_unitario)
    validar_origen_de_costo(origen_tipo)
    ahora = reloj.now()

    previo = _bloquear(organizacion_id, sesion, reloj, producto_id)
    resultado = calcular_ingreso(
        stock_previo=previo.stock_total,
        promedio_previo=previo.costo_promedio,
        cantidad=cantidad,
        costo_ingreso=costo,
    )
    repository.aplicar_ingreso_al_costo(
        organizacion_id,
        sesion,
        producto_id=producto_id,
        costo_promedio=resultado.promedio_nuevo,
        cantidad=cantidad,
        momento=ahora,
    )
    repository.insertar_historia(
        organizacion_id,
        sesion,
        historia_id=nuevo_id(),
        producto_id=producto_id,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        cantidad=cantidad,
        costo_ingreso=costo,
        stock_anterior=previo.stock_total,
        promedio_anterior=previo.costo_promedio,
        stock_nuevo=resultado.stock_nuevo,
        promedio_nuevo=resultado.promedio_nuevo,
        recalculado=True,
        operation_id=operation_id,
        registered_at=ahora,
    )
    return ResultadoDeIngresoAplicado(
        stock_anterior=previo.stock_total,
        promedio_anterior=previo.costo_promedio,
        stock_nuevo=resultado.stock_nuevo,
        promedio_nuevo=resultado.promedio_nuevo,
    )


def aplicar_ingreso_sin_recalculo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    cantidad: int,
) -> Decimal | None:
    """Ingreso sin costo (CST-12, `design.md` D3, D9): la entrada de una transferencia, un
    ajuste positivo o el ingreso inverso de una anulación. Suma `cantidad` a `stock_total`
    con la fila bloqueada, NO cambia el promedio, NO deja historia en `costo_producto_mov`
    (CST-13) y devuelve el promedio vigente con el que se valoriza el movimiento, o `None`
    si el producto todavía no tiene. Valida ANTES de escribir."""
    previo = _bloquear(organizacion_id, sesion, reloj, producto_id)
    resultado = calcular_ingreso_sin_recalculo(
        stock_previo=previo.stock_total, promedio_previo=previo.costo_promedio, cantidad=cantidad
    )
    repository.sumar_al_stock_total(
        organizacion_id,
        sesion,
        producto_id=producto_id,
        cantidad=cantidad,
        momento=reloj.now(),
    )
    return resultado.promedio


def revertir_ingreso(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    cantidad: int,
    costo_unitario: object,
    origen_id: UUID,
    operation_id: UUID,
) -> ResultadoDeReversionAplicada:
    """Reversión de un ingreso con costo (CMP-06, `design.md` D9): quita
    `cantidad` del stock total y recalcula el promedio como inverso de CST-11 si
    el stock restante y el promedio resultante son positivos. Escribe SIEMPRE una
    fila de `costo_producto_mov` con origen `ANULACION_COMPRA`, cantidad negativa y
    el costo de la línea; si no recalcula, `promedio_nuevo` es el anterior y
    `recalculado` es `False` (CST-13). Valida ANTES de escribir."""
    costo = validar_costo(costo_unitario)
    ahora = reloj.now()

    previo = _bloquear(organizacion_id, sesion, reloj, producto_id)
    resultado = calcular_reversion(
        stock_previo=previo.stock_total,
        promedio_previo=previo.costo_promedio,
        cantidad=cantidad,
        costo_ingreso=costo,
    )
    if resultado.recalculado:
        repository.aplicar_ingreso_al_costo(
            organizacion_id,
            sesion,
            producto_id=producto_id,
            costo_promedio=resultado.promedio_nuevo,
            cantidad=-cantidad,
            momento=ahora,
        )
    else:
        repository.aplicar_egreso_al_costo(
            organizacion_id, sesion, producto_id=producto_id, cantidad=cantidad, momento=ahora
        )
    repository.insertar_historia(
        organizacion_id,
        sesion,
        historia_id=nuevo_id(),
        producto_id=producto_id,
        origen_tipo="ANULACION_COMPRA",
        origen_id=origen_id,
        cantidad=-cantidad,
        costo_ingreso=costo,
        stock_anterior=previo.stock_total,
        promedio_anterior=previo.costo_promedio,
        stock_nuevo=resultado.stock_nuevo,
        promedio_nuevo=resultado.promedio_nuevo,
        recalculado=resultado.recalculado,
        operation_id=operation_id,
        registered_at=ahora,
    )
    return ResultadoDeReversionAplicada(
        stock_anterior=previo.stock_total,
        promedio_anterior=previo.costo_promedio,
        stock_nuevo=resultado.stock_nuevo,
        promedio_nuevo=resultado.promedio_nuevo,
        recalculado=resultado.recalculado,
    )


def aplicar_egreso(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    cantidad: int,
) -> ResultadoDeEgresoAplicado:
    """Egreso (CST-12): reduce `stock_total` sin cambiar el promedio y devuelve el
    promedio vigente con el que se valoriza el movimiento. No deja historia: el
    promedio no cambió (CST-13). La condición de saldo suficiente es de `stock`
    (STK-05, `02` §7.4); acá el stock total puede quedar negativo."""
    previo = _bloquear(organizacion_id, sesion, reloj, producto_id)
    resultado = calcular_egreso(
        stock_previo=previo.stock_total, promedio_previo=previo.costo_promedio, cantidad=cantidad
    )
    repository.aplicar_egreso_al_costo(
        organizacion_id,
        sesion,
        producto_id=producto_id,
        cantidad=cantidad,
        momento=reloj.now(),
    )
    return ResultadoDeEgresoAplicado(
        costo_valorizacion=resultado.costo_valorizacion, stock_nuevo=resultado.stock_nuevo
    )


def obtener_costo(organizacion_id: UUID, sesion: Session, producto_id: UUID) -> CostoVigente | None:
    """Promedio y stock total sin bloquear, o `None` si el producto nunca tuvo un
    movimiento (no tiene fila). No valida que el producto exista: quien lo expone
    (la ruta) resuelve el 404."""
    fila = repository.obtener_costo(organizacion_id, sesion, producto_id=producto_id)
    if fila is None:
        return None
    return CostoVigente(costo_promedio=fila.costo_promedio, stock_total=fila.stock_total)


def obtener_promedio(organizacion_id: UUID, sesion: Session, producto_id: UUID) -> Decimal | None:
    """Promedio vigente, o `None` si el producto no tuvo ingresos con costo (D10)."""
    costo = obtener_costo(organizacion_id, sesion, producto_id)
    return None if costo is None else costo.costo_promedio


def obtener_promedios(
    organizacion_id: UUID, sesion: Session, productos: Collection[UUID]
) -> dict[UUID, Decimal]:
    """Promedio vigente de varios productos con una sola consulta. Los que no
    tienen promedio (D10) no aparecen en el resultado."""
    return repository.obtener_promedios(organizacion_id, sesion, productos=productos)


def obtener_stock_totales(organizacion_id: UUID, sesion: Session) -> dict[UUID, int]:
    """`stock_total` materializado de cada producto con fila de costo. Lo usa
    `stock.verificar_consistencia` para compararlo con la suma SQL de sus saldos
    (INV-12, `02` §7.6) sin importar el modelo de `costeo`."""
    return repository.obtener_stock_totales(organizacion_id, sesion)
