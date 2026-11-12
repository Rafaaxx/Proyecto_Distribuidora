"""Utilidades de las pruebas de integración de `ventas` (change 18a).

Siembra por SQL directo una venta con su línea y las filas que sus claves foráneas compuestas
exigen (ubicación, lista de precios con una versión publicada, producto y presentación), para
probar la base y los módulos vecinos antes de que exista el comando `VENTA_CONFIRMAR` (grupo 7).

Es un módulo y no un `conftest.py` por el mismo motivo que `stock_utiles`: `tests/integration`
no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

MOMENTO = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class ListaSembrada(NamedTuple):
    lista_id: UUID
    version_id: UUID


class VentaSembrada(NamedTuple):
    venta_id: UUID
    linea_id: UUID
    numero: str
    lista_id: UUID
    version_id: UUID
    ubicacion_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    cliente_id: UUID


def insertar_sql(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def sembrar_lista_sql(sesion: Session, organizacion_id: UUID, usuario_id: UUID) -> ListaSembrada:
    """Una lista de precios activa con una versión `PUBLICADA` (número 1)."""
    lista_id, version_id = uuid4(), uuid4()
    insertar_sql(
        sesion,
        "lista_precio",
        {
            "id": lista_id,
            "organizacion_id": organizacion_id,
            "nombre": f"General {uuid4().hex[:6]}",
            "redondeo_multiplo": 100,
            "redondeo_direccion": "ARRIBA",
            "activo": True,
            "creado_en": MOMENTO,
            "actualizado_en": MOMENTO,
        },
    )
    insertar_sql(
        sesion,
        "lista_version",
        {
            "id": version_id,
            "organizacion_id": organizacion_id,
            "lista_id": lista_id,
            "numero": 1,
            "estado": "PUBLICADA",
            "vigencia_desde": MOMENTO,
            "creado_por_id": usuario_id,
            "creado_en": MOMENTO,
            "publicado_por_id": usuario_id,
            "publicado_en": MOMENTO,
            "operation_id": uuid4(),
        },
    )
    return ListaSembrada(lista_id, version_id)


def valores_de_venta(
    organizacion_id: UUID,
    *,
    cliente_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    ubicacion_id: UUID,
    lista_id: UUID,
    version_id: UUID,
    **cambios: object,
) -> dict[str, object]:
    """Columnas de una `venta` válida (una línea de $31.250,00 en modo A, `ONLINE`)."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": organizacion_id,
        "numero": f"V01-{uuid4().int % 1_000_000:06d}",
        "cliente_id": cliente_id,
        "usuario_id": usuario_id,
        "dispositivo_id": dispositivo_id,
        "ubicacion_id": ubicacion_id,
        "lista_id": lista_id,
        "lista_version_id": version_id,
        "modo_impositivo": "A",
        "modo_confirmacion": "ONLINE",
        "total_neto": "31250.00",
        "total_iva": "0.00",
        "total": "31250.00",
        "estado": "CONFIRMADA",
        "estado_facturacion": "NO_REQUIERE",
        "importe_facturado": "0.00",
        "operation_id": uuid4(),
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
        "creado_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def valores_de_linea(
    organizacion_id: UUID,
    venta_id: UUID,
    *,
    producto_id: UUID,
    presentacion_id: UUID,
    version_id: UUID,
    **cambios: object,
) -> dict[str, object]:
    """Columnas de una `venta_linea` válida: 18 botellas de Vino A (3 cajas x6)."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": organizacion_id,
        "venta_id": venta_id,
        "orden": 0,
        "producto_id": producto_id,
        "presentacion_id": presentacion_id,
        "lista_version_id": version_id,
        "unidades_presentacion": 6,
        "cantidad": 3,
        "cantidad_base": 18,
        "precio_referencia": "12500.00",
        "unidades_referencia": 6,
        "importe_bruto": "37500.00",
        "importe_descuento": "0.00",
        "importe_neto": "37500.00",
        "alicuota": "0.210000",
        "importe_iva": "0.00",
        "costo_unitario": "1050.000000",
        "costo_total": "18900.00",
    }
    valores.update(cambios)
    return valores


def sembrar_venta_sql(
    sesion: Session,
    organizacion_id: UUID,
    *,
    cliente_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    con_linea: bool = True,
    **cambios: object,
) -> VentaSembrada:
    """Una venta confirmada (con su línea salvo `con_linea=False`) escrita por SQL; arma la
    ubicación, la lista, el producto y la presentación que sus claves foráneas piden.

    Los totales de la cabecera son coherentes con la línea sembrada (neto $37.500,00)."""
    lista = sembrar_lista_sql(sesion, organizacion_id, usuario_id)
    ubicacion_id = crear_ubicacion_sql(sesion, organizacion_id)
    producto_id = crear_producto_sql(sesion, organizacion_id)
    presentacion_id = crear_presentacion_referencia_sql(
        sesion, organizacion_id, producto_id, unidades_base=6
    )
    base: dict[str, object] = {
        "total_neto": "37500.00",
        "total": "37500.00",
        **cambios,
    }
    venta = valores_de_venta(
        organizacion_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        ubicacion_id=ubicacion_id,
        lista_id=lista.lista_id,
        version_id=lista.version_id,
        **base,
    )
    insertar_sql(sesion, "venta", venta)
    linea = valores_de_linea(
        organizacion_id,
        venta["id"],  # type: ignore[arg-type]
        producto_id=producto_id,
        presentacion_id=presentacion_id,
        version_id=lista.version_id,
    )
    if con_linea:
        insertar_sql(sesion, "venta_linea", linea)
    return VentaSembrada(
        venta_id=venta["id"],  # type: ignore[arg-type]
        linea_id=linea["id"],  # type: ignore[arg-type]
        numero=str(venta["numero"]),
        lista_id=lista.lista_id,
        version_id=lista.version_id,
        ubicacion_id=ubicacion_id,
        producto_id=producto_id,
        presentacion_id=presentacion_id,
        cliente_id=cliente_id,
    )
