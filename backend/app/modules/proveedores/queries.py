"""Casos de uso de lectura de `proveedores` (`02` §5.1): listado y detalle de compras
(change 11, CMP-01, `design.md` D14).

Solo lee: ninguna función escribe ni bloquea. Todas reciben `organizacion_id` primero y
lo usan para filtrar (INV-21): una compra de otra organización es inexistente
(`RecursoNoEncontradoError`, 404). Los nombres de producto, presentación, medio de pago
y motivo se resuelven por el `service.py` de su módulo (`CLAUDE.md` §4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.proveedores import repository
from app.modules.proveedores.domain.compras import (
    LIMITE_DEFAULT_DE_PAGINA,
    LIMITE_MAXIMO_DE_PAGINA,
    LIMITE_MINIMO_DE_PAGINA,
    validar_rango_de_fechas,
)
from app.modules.proveedores.domain.errores import RecursoNoEncontradoError
from app.modules.proveedores.models import Compra


@dataclass(frozen=True)
class CompraDelListado:
    compra: Compra
    proveedor_nombre: str


@dataclass(frozen=True)
class PaginaDeCompras:
    compras: list[CompraDelListado]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class LineaDelDetalle:
    orden: int
    producto_id: UUID
    producto_codigo: str | None
    producto_nombre: str | None
    presentacion_id: UUID
    presentacion_nombre: str | None
    unidades_presentacion: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    cantidad: Decimal
    cantidad_base: int
    valor_presentacion: Decimal
    incluye_iva: bool
    bonificacion: Decimal
    alicuota_aplicada: Decimal
    costo_base: Decimal
    importe_neto: Decimal


@dataclass(frozen=True)
class MedioDelDetalle:
    medio_pago_id: UUID
    medio_nombre: str | None
    importe: Decimal
    referencia: str | None


@dataclass(frozen=True)
class PagoDelDetalle:
    id: UUID
    fecha: date
    importe: Decimal
    estado: str
    anulado_en: datetime | None
    medios: list[MedioDelDetalle]


@dataclass(frozen=True)
class AnulacionDelDetalle:
    motivo_id: UUID
    motivo_nombre: str | None
    anulada_en: datetime
    anulada_por_id: UUID


@dataclass(frozen=True)
class DetalleDeCompra:
    compra: Compra
    proveedor_nombre: str
    lineas: list[LineaDelDetalle]
    pago: PagoDelDetalle | None
    anulacion: AnulacionDelDetalle | None


def listar_compras(
    organizacion_id: UUID,
    sesion: Session,
    *,
    proveedor_id: UUID | None = None,
    estado: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    numero_comprobante: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeCompras:
    """Compras de la organización por cursor, de la más reciente a la más vieja.
    `limite` va de 1 a 200 (la API responde 422 fuera de rango; acá solo se acota por
    seguridad; `None` es el default) y `estado` es `CONFIRMADA` o `ANULADA` (también lo
    valida la API)."""
    validar_rango_de_fechas(desde, hasta)
    limite_pagina = min(
        max(LIMITE_DEFAULT_DE_PAGINA if limite is None else limite, LIMITE_MINIMO_DE_PAGINA),
        LIMITE_MAXIMO_DE_PAGINA,
    )
    filas, cursor_siguiente = repository.listar_compras_paginado(
        organizacion_id,
        sesion,
        limite=limite_pagina,
        cursor=cursor,
        proveedor_id=proveedor_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
        numero_comprobante=numero_comprobante,
    )
    return PaginaDeCompras(
        compras=[CompraDelListado(compra, nombre) for compra, nombre in filas],
        cursor_siguiente=cursor_siguiente,
    )


def obtener_detalle_de_compra(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> DetalleDeCompra:
    """La compra con sus líneas (con nombres y la unidad de referencia para mostrar
    cajas + unidades, CAT-08), su pago con medios y su anulación. 404 si no existe en la
    organización (INV-21)."""
    encontrada = repository.obtener_compra(organizacion_id, compra_id, sesion)
    if encontrada is None:
        raise RecursoNoEncontradoError(f"La compra {compra_id} no existe en esta organización.")
    compra, proveedor_nombre = encontrada

    lineas: list[LineaDelDetalle] = []
    for linea in repository.listar_lineas_de_compra(organizacion_id, compra_id, sesion):
        producto = catalogo_service.obtener_producto(organizacion_id, linea.producto_id, sesion)
        presentacion = catalogo_service.obtener_presentacion(
            organizacion_id, linea.presentacion_id, sesion
        )
        referencia = catalogo_service.obtener_referencia_de_producto(
            organizacion_id, linea.producto_id, sesion
        )
        lineas.append(
            LineaDelDetalle(
                orden=linea.orden,
                producto_id=linea.producto_id,
                producto_codigo=None if producto is None else producto.codigo,
                producto_nombre=None if producto is None else producto.nombre,
                presentacion_id=linea.presentacion_id,
                presentacion_nombre=None if presentacion is None else presentacion.nombre,
                unidades_presentacion=linea.unidades_presentacion,
                unidades_referencia=None if referencia is None else referencia.unidades_base,
                nombre_referencia=None if referencia is None else referencia.nombre,
                cantidad=linea.cantidad,
                cantidad_base=linea.cantidad_base,
                valor_presentacion=linea.valor_presentacion,
                incluye_iva=linea.incluye_iva,
                bonificacion=linea.bonificacion,
                alicuota_aplicada=linea.alicuota_aplicada,
                costo_base=linea.costo_base,
                importe_neto=linea.importe_neto,
            )
        )

    pago_fila = repository.obtener_pago_de_compra_sin_bloquear(organizacion_id, compra_id, sesion)
    pago: PagoDelDetalle | None = None
    if pago_fila is not None:
        medios = []
        for medio in repository.listar_medios_de_pago(organizacion_id, pago_fila.id, sesion):
            fila_medio = configuracion_service.obtener_medio_pago(
                organizacion_id, medio.medio_pago_id, sesion
            )
            medios.append(
                MedioDelDetalle(
                    medio_pago_id=medio.medio_pago_id,
                    medio_nombre=None if fila_medio is None else fila_medio.nombre,
                    importe=medio.importe,
                    referencia=medio.referencia,
                )
            )
        pago = PagoDelDetalle(
            id=pago_fila.id,
            fecha=pago_fila.fecha,
            importe=pago_fila.importe,
            estado=pago_fila.estado,
            anulado_en=pago_fila.anulado_en,
            medios=medios,
        )

    anulacion: AnulacionDelDetalle | None = None
    if (
        compra.estado == "ANULADA"
        and compra.anulacion_motivo_id is not None
        and compra.anulada_en is not None
        and compra.anulada_por_id is not None
    ):
        motivo = configuracion_service.obtener_motivo(
            organizacion_id, compra.anulacion_motivo_id, sesion
        )
        anulacion = AnulacionDelDetalle(
            motivo_id=compra.anulacion_motivo_id,
            motivo_nombre=None if motivo is None else motivo.nombre,
            anulada_en=compra.anulada_en,
            anulada_por_id=compra.anulada_por_id,
        )
    return DetalleDeCompra(
        compra=compra,
        proveedor_nombre=proveedor_nombre,
        lineas=lineas,
        pago=pago,
        anulacion=anulacion,
    )
