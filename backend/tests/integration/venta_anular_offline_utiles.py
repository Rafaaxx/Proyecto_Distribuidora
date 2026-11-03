"""Armado compartido de las pruebas de `VENTA_ANULAR` sin conexión (change 22d, grupos 1 a 3).

Vender y anular por el lote (`procesar_lote`) sobre la `Ruta` de `test_ventas_offline`. Es un módulo
y no un `conftest.py` por el mismo motivo que `ventas_anular_utiles`."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from test_ventas_offline import Ruta, lote
from ventas_anular_utiles import MOMENTO_ANULACION, EntornoAnulacion

from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote


def item_de_anulacion(
    entorno: EntornoAnulacion,
    venta_id: UUID,
    *,
    jornada_id: UUID | None,
    modo: str = "OFFLINE",
    operation_id: UUID | None = None,
    secuencia: int = 2,
    **opciones: Any,
) -> ItemLote:
    """Un ítem de lote `VENTA_ANULAR` v1 (`opciones`: motivo, observación, devolución)."""
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="VENTA_ANULAR",
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO_ANULACION,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido=entorno.contenido_de_anulacion(venta_id, **opciones),
        jornada_id=jornada_id,
    )


def vender(ruta: Ruta, *lineas: dict[str, Any], **cambios: object) -> UUID:
    """Una venta sin conexión aceptada de la jornada de `ruta`; devuelve su identificador."""
    item, resultado = ruta.enviar(*lineas, **cambios)
    assert resultado.estado in {"ACEPTADO", "ACEPTADO_CON_OBSERVACIONES"}
    return UUID(str(item.contenido["venta_id"]))


def anular(
    entorno: EntornoAnulacion, ruta: Ruta, venta_id: UUID, **opciones: Any
) -> tuple[ItemLote, sync_service.ResultadoItemLote]:
    """Anula por el lote `OFFLINE` con la jornada de `ruta`."""
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, **opciones)
    return item, lote(entorno, item)[item.operation_id]


def comandos(entorno: EntornoAnulacion, operation_id: UUID) -> list[Comando]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


def observaciones(entorno: EntornoAnulacion) -> list[Observacion]:
    """Todas las observaciones de la organización, por código."""
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
            .order_by(Observacion.codigo, Observacion.id)
        ).all()
    )


def rechazada(
    resultado: sync_service.ResultadoItemLote,
    codigo: str,
    item: ItemLote,
    entorno: EntornoAnulacion,
) -> None:
    """Rechazo del ítem con `codigo`, sin fila de comando (reintentable)."""
    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", codigo)
    assert comandos(entorno, item.operation_id) == []


def sin_efectos(entorno: EntornoAnulacion, ruta: Ruta, venta_id: UUID, *, saldo: str) -> None:
    """La anulación rechazada no escribió nada (INV-01): la venta sigue `CONFIRMADA` (descontada
    de la camioneta de `ruta`), sin fila de anulación, sin reingreso ni acreditación."""
    entorno.sesion.rollback()
    assert entorno.venta(venta_id).estado == "CONFIRMADA"
    assert entorno.anulaciones_de_venta() == []
    assert entorno.movimientos_de_stock("ANULACION_VENTA") == []
    assert entorno.movimientos("ANULACION_VENTA") == []
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert str(entorno.saldo()) == saldo
