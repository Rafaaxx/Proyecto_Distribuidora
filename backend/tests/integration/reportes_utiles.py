"""Utilidades de las pruebas de los reportes (change 26).

Siembra por SQL ventas con líneas a medida (producto, presentación, referencia congelada, neto,
costo), anulaciones y los usuarios que consultan. Sobre `ventas_utiles` / `ventas_lecturas_utiles`:
es un módulo y no un `conftest.py` porque `tests/integration` no es un paquete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)
from test_ventas_api import Sesion
from ventas_utiles import insertar_sql, valores_de_linea, valores_de_venta

from app.core.clock import FixedClock
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.reportes.api import obtener_reloj

URL_VENTAS = "/api/v1/reportes/ventas"
MENDOZA_UTC_OFFSET = timedelta(hours=-3)
ABRIR_REPORTES = frozenset({"VER_REPORTES"})
CON_UTILIDAD = frozenset({"VER_REPORTES", "VER_UTILIDAD"})


def dia(mes: int, dia_: int, hora: int = 12) -> datetime:
    """Un instante de 2026 a la hora local de Mendoza dada (UTC-3), en UTC."""
    return datetime(2026, mes, dia_, hora, 0, tzinfo=UTC) - MENDOZA_UTC_OFFSET


def fijar_reloj(cliente_http: TestClient, momento: datetime) -> None:
    """El reloj inyectable de los reportes (`obtener_reloj`) fijo en `momento`."""
    app: FastAPI = cliente_http.app  # type: ignore[assignment]
    app.dependency_overrides[obtener_reloj] = lambda: FixedClock(momento)


@dataclass
class LineaDePrueba:
    """Una línea a sembrar: neto, costo (None = sin costo) y cantidad base con su referencia."""

    neto: str = "1000.00"
    costo_total: str | None = "700.00"
    cantidad_base: int = 6
    unidades_referencia: int = 6
    unidades_presentacion: int = 6
    producto: str = "vino"  # "vino" (Vino A del entorno) o "otro" (producto nuevo)
    presentacion: str = "caja"  # "caja" (x6) o "botella" (x1) del vino
    importe_descuento: str = "0.00"


@dataclass
class VentaDePrueba:
    venta_id: UUID
    numero: str
    total: Decimal
    producto_ids: list[UUID]


def sembrar_venta(
    sesion: Any,
    s: Sesion,
    *,
    vendedor_id: UUID | None = None,
    occurred_at: datetime | None = None,
    lineas: list[LineaDePrueba] | None = None,
    modo_confirmacion: str = "ONLINE",
    cliente_id: UUID | None = None,
    iva: str = "0.00",
    jornada_id: UUID | None = None,
    registered_at: datetime | None = None,
) -> VentaDePrueba:
    """Una venta `CONFIRMADA` con sus líneas; la cabecera suma las líneas (modo A: IVA `iva`)."""
    entorno = s.entorno
    lineas = lineas if lineas is not None else [LineaDePrueba()]
    total_neto = sum((Decimal(linea.neto) for linea in lineas), Decimal("0"))
    total_iva = Decimal(iva)
    if modo_confirmacion == "OFFLINE" and jornada_id is None:
        jornada_id = entorno.crear_jornada()  # `ck_venta__jornada`: sin conexion exige jornada
    cabecera = valores_de_venta(
        entorno.org,
        cliente_id=cliente_id or entorno.cliente_id,
        usuario_id=vendedor_id or entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=entorno.deposito_id,
        lista_id=entorno.lista_id,
        version_id=entorno.version_id,
        modo_confirmacion=modo_confirmacion,
        jornada_id=jornada_id,
        total_neto=str(total_neto),
        total_iva=str(total_iva),
        total=str(total_neto + total_iva),
        occurred_at=occurred_at or dia(11, 3),
    )
    if registered_at is not None:
        cabecera["registered_at"] = registered_at
    insertar_sql(sesion, "venta", cabecera)
    producto_ids: list[UUID] = []
    for orden, linea in enumerate(lineas):
        if linea.producto == "vino":
            producto_id = entorno.vino_id
            presentacion_id = (
                entorno.caja_id if linea.presentacion == "caja" else entorno.botella_id
            )
        else:
            producto_id = crear_producto_sql(sesion, entorno.org, nombre="Gaseosa")
            presentacion_id = crear_presentacion_referencia_sql(
                sesion, entorno.org, producto_id, unidades_base=linea.unidades_referencia
            )
        producto_ids.append(producto_id)
        insertar_sql(
            sesion,
            "venta_linea",
            valores_de_linea(
                entorno.org,
                cabecera["id"],  # type: ignore[arg-type]
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                version_id=entorno.version_id,
                orden=orden,
                unidades_presentacion=linea.unidades_presentacion,
                cantidad=max(linea.cantidad_base // linea.unidades_presentacion, 1),
                cantidad_base=linea.cantidad_base,
                unidades_referencia=linea.unidades_referencia,
                importe_bruto=str(Decimal(linea.neto) + Decimal(linea.importe_descuento)),
                importe_descuento=linea.importe_descuento,
                importe_neto=linea.neto,
                costo_unitario=None if linea.costo_total is None else "1.000000",
                costo_total=linea.costo_total,
            ),
        )
    sesion.commit()
    return VentaDePrueba(
        venta_id=cabecera["id"],  # type: ignore[arg-type]
        numero=str(cabecera["numero"]),
        total=total_neto + total_iva,
        producto_ids=producto_ids,
    )


def anular_venta(
    sesion: Any,
    s: Sesion,
    venta_id: UUID,
    *,
    anulada_en: datetime,
    motivo: str = "Error de carga",
    devuelve_dinero: bool | None = False,
    jornada_id: UUID | None = None,
    registered_at: datetime | None = None,
) -> None:
    """Marca la venta `ANULADA` y escribe su `venta_anulacion` con el motivo dado."""
    entorno = s.entorno
    motivo_id = sesion.execute(
        text(
            "SELECT id FROM motivo WHERE organizacion_id = :o AND ambito = 'ANULACION_VENTA' "
            "AND nombre = :n"
        ),
        {"o": entorno.org, "n": motivo},
    ).scalar_one_or_none() or entorno.crear_motivo("ANULACION_VENTA", motivo)
    sesion.execute(
        text("UPDATE venta SET estado = 'ANULADA' WHERE organizacion_id = :o AND id = :v"),
        {"o": entorno.org, "v": venta_id},
    )
    insertar_sql(
        sesion,
        "venta_anulacion",
        {
            "id": uuid4(),
            "organizacion_id": entorno.org,
            "venta_id": venta_id,
            "motivo_id": motivo_id,
            "observacion": None,
            "devuelve_dinero": devuelve_dinero,
            "jornada_id": jornada_id,
            "operation_id": uuid4(),
            "usuario_id": entorno.usuario_id,
            "dispositivo_id": entorno.dispositivo_id,
            "occurred_at": anulada_en,
            "registered_at": registered_at or anulada_en,
        },
    )
    sesion.commit()


# --- jornadas, rendiciones y cobranzas (change 26, grupo 4) -----------------------------------


@dataclass
class Vendedor:
    """Un vendedor de la organización con su dispositivo (para abrir jornadas y vender)."""

    usuario_id: UUID
    dispositivo_id: UUID
    nombre: str


def crear_vendedor(sesion: Any, s: Sesion, nombre: str) -> Vendedor:
    """Un usuario con dispositivo en la organización de `s`, con un nombre reconocible."""
    org = s.entorno.org
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
        sesion, org, permisos=frozenset({"VENDER"})
    )
    sesion.execute(
        text("UPDATE usuario SET nombre = :n WHERE organizacion_id = :o AND id = :u"),
        {"n": nombre, "o": org, "u": usuario_id},
    )
    sesion.commit()
    return Vendedor(usuario_id, dispositivo_id, nombre)


def sembrar_jornada(
    sesion: Any,
    s: Sesion,
    *,
    vendedor: Vendedor,
    estado: str = "ABIERTA",
    abierta_en: datetime | None = None,
    ubicacion: str | None = None,
) -> UUID:
    """Una jornada del vendedor en una camioneta nueva; las transiciones caen a las 8 y 9 horas
    de la apertura."""
    org = s.entorno.org
    apertura = abierta_en or dia(11, 3, hora=8)
    cambios: dict[str, object] = {"abierta_en": apertura}
    if estado in {"EN_RENDICION", "CERRADA"}:
        cambios["rendida_en"] = apertura + timedelta(hours=8)
    if estado == "CERRADA":
        cambios["cerrada_en"] = apertura + timedelta(hours=9)
    if estado == "LIBERADA":
        cambios["liberada_en"] = apertura + timedelta(hours=8)
    jornada_id = crear_jornada_sql(
        sesion,
        org,
        usuario_id=vendedor.usuario_id,
        dispositivo_id=vendedor.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, org, nombre=ubicacion, requiere_toma=True),
        estado=estado,
        **cambios,
    )
    sesion.commit()
    return jornada_id


@dataclass
class LineaContada:
    """Un producto contado al rendir: lo esperado, lo contado y el costo con que se valoriza."""

    producto_id: UUID
    esperada: int
    contada: int
    costo_unitario: str | None = "100.000000"


def sembrar_rendicion(
    sesion: Any,
    s: Sesion,
    jornada_id: UUID,
    *,
    vendedor: Vendedor,
    lineas: list[LineaContada],
) -> datetime:
    """La rendición de la jornada (de las `EN_RENDICION` o `CERRADA`), registrada en el instante
    `rendida_en` de la jornada; devuelve ese instante (el corte de lo tardío, RUT-07)."""
    org = s.entorno.org
    rendida_en = sesion.execute(
        text("SELECT rendida_en FROM jornada WHERE organizacion_id = :o AND id = :j"),
        {"o": org, "j": jornada_id},
    ).scalar_one()
    rendicion_id = uuid4()
    insertar_sql(
        sesion,
        "rendicion",
        {
            "id": rendicion_id,
            "organizacion_id": org,
            "jornada_id": jornada_id,
            "operation_id": uuid4(),
            "usuario_id": vendedor.usuario_id,
            "dispositivo_id": vendedor.dispositivo_id,
            "occurred_at": rendida_en,
            "registered_at": rendida_en,
        },
    )
    for linea in lineas:
        insertar_sql(
            sesion,
            "rendicion_linea",
            {
                "id": uuid4(),
                "organizacion_id": org,
                "rendicion_id": rendicion_id,
                "producto_id": linea.producto_id,
                "stock_al_abrir": linea.esperada,
                "ingresos": 0,
                "ventas": 0,
                "anulaciones": 0,
                "otros": 0,
                "cantidad_esperada": linea.esperada,
                "cantidad_contada": linea.contada,
                "diferencia": linea.contada - linea.esperada,
                "costo_unitario": linea.costo_unitario,
            },
        )
    sesion.commit()
    return rendida_en  # type: ignore[no-any-return]


def sembrar_cobranza(
    sesion: Any,
    s: Sesion,
    jornada_id: UUID,
    medios: list[tuple[UUID, str]],
    *,
    cuando: datetime,
    vendedor: Vendedor,
    estado: str = "CONFIRMADA",
) -> UUID:
    """Una cobranza de la jornada con sus medios `(medio_pago_id, importe)`."""
    org = s.entorno.org
    cobranza_id = uuid4()
    importe = sum((Decimal(i) for _, i in medios), Decimal("0"))
    insertar_sql(
        sesion,
        "cobranza",
        {
            "id": cobranza_id,
            "organizacion_id": org,
            "cliente_id": s.entorno.cliente_id,
            "venta_id": None,
            "origen": "INDEPENDIENTE",
            "importe": importe,
            "estado": estado,
            "jornada_id": jornada_id,
            "operation_id": uuid4(),
            "usuario_id": vendedor.usuario_id,
            "dispositivo_id": vendedor.dispositivo_id,
            "occurred_at": cuando,
            "registered_at": cuando,
        },
    )
    for orden, (medio_id, importe_medio) in enumerate(medios):
        insertar_sql(
            sesion,
            "cobranza_medio",
            {
                "id": uuid4(),
                "organizacion_id": org,
                "cobranza_id": cobranza_id,
                "orden": orden,
                "medio_pago_id": medio_id,
                "importe": importe_medio,
            },
        )
    sesion.commit()
    return cobranza_id


# --- ajustes de stock y diferencias de rendición (change 26, grupo 6) -------------------------


def _motivo_de_ajuste(sesion: Any, s: Sesion, nombre: str) -> UUID:
    org = s.entorno.org
    existente = sesion.execute(
        text(
            "SELECT id FROM motivo WHERE organizacion_id = :o AND ambito = 'AJUSTE_STOCK' "
            "AND nombre = :n"
        ),
        {"o": org, "n": nombre},
    ).scalar_one_or_none()
    return existente or crear_motivo_sql(sesion, org, ambito="AJUSTE_STOCK", nombre=nombre)


def sembrar_ajuste(
    sesion: Any,
    s: Sesion,
    *,
    motivo: str,
    lineas: list[tuple[UUID, int, str | None]],
    occurred_at: datetime,
    anulado: bool = False,
) -> UUID:
    """Un ajuste de stock con el motivo dado y sus líneas `(producto_id, cantidad_base con signo,
    costo_unitario o None)`; `anulado` lo deja `ANULADA` (con su anulación coherente)."""
    entorno = s.entorno
    ajuste_id = uuid4()
    valores: dict[str, object] = {
        "id": ajuste_id,
        "organizacion_id": entorno.org,
        "ubicacion_id": entorno.deposito_id,
        "motivo_id": _motivo_de_ajuste(sesion, s, motivo),
        "estado": "ANULADA" if anulado else "CONFIRMADA",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": occurred_at,
        "registered_at": occurred_at,
    }
    if anulado:
        valores.update(
            anulacion_motivo_id=entorno.crear_motivo(
                "ANULACION_AJUSTE", f"Error {uuid4().hex[:4]}"
            ),
            anulado_en=occurred_at + timedelta(hours=1),
            anulado_por_id=entorno.usuario_id,
        )
    insertar_sql(sesion, "ajuste_stock", valores)
    for orden, (producto_id, cantidad_base, costo) in enumerate(lineas, start=1):
        insertar_sql(
            sesion,
            "ajuste_stock_linea",
            {
                "id": uuid4(),
                "organizacion_id": entorno.org,
                "ajuste_id": ajuste_id,
                "orden": orden,
                "producto_id": producto_id,
                "cantidad_base": cantidad_base,
                "costo_unitario": costo,
            },
        )
    sesion.commit()
    return ajuste_id


def sembrar_diferencia_de_rendicion(
    sesion: Any,
    s: Sesion,
    producto_id: UUID,
    cantidad_base: int,
    *,
    costo_unitario: str | None,
    occurred_at: datetime,
) -> None:
    """El movimiento `DIFERENCIA_RENDICION` que deja una rendición (con signo, RUT-06)."""
    entorno = s.entorno
    insertar_stock_movimiento_sql(
        sesion,
        organizacion_id=entorno.org,
        producto_id=producto_id,
        ubicacion_id=entorno.deposito_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        cantidad_base=cantidad_base,
        tipo="DIFERENCIA_RENDICION",
        origen_tipo="RENDICION",
        costo_unitario=None if costo_unitario is None else Decimal(costo_unitario),
        occurred_at=occurred_at,
        registered_at=occurred_at,
    )
    sesion.commit()


# --- cuentas corrientes (change 26, grupo 7) --------------------------------------------------

SENTIDO_DE_MOVIMIENTO = {
    "SALDO_INICIAL": "AUMENTA",
    "VENTA": "AUMENTA",
    "COBRANZA": "REDUCE",
    "COMPRA": "AUMENTA",
    "PAGO": "REDUCE",
}


def sembrar_cliente_de_cartera(
    sesion: Any,
    s: Sesion,
    *,
    nombre: str,
    codigo: str | None = None,
    razon_social: str | None = None,
    vendedor_id: UUID | None = None,
    limite_credito: str | None = None,
    estado: str = "ACTIVO",
) -> UUID:
    """Un cliente de la organización de `s` con los rasgos que miran los saldos."""
    cliente_id = crear_cliente(sesion, s.entorno.org, nombre=nombre, estado=estado)
    sesion.execute(
        text(
            "UPDATE cliente SET codigo = :c, razon_social = :r, vendedor_id = :v, "
            "limite_credito = :l WHERE organizacion_id = :o AND id = :i"
        ),
        {
            "c": codigo,
            "r": razon_social,
            "v": vendedor_id,
            "l": limite_credito,
            "o": s.entorno.org,
            "i": cliente_id,
        },
    )
    sesion.commit()
    return cliente_id


def sembrar_proveedor_de_prueba(
    sesion: Any, s: Sesion, *, nombre: str, activo: bool = True
) -> UUID:
    return crear_proveedor(sesion, s.entorno.org, nombre=nombre, activo=activo)


def mover_cuenta(
    sesion: Any,
    s: Sesion,
    cuenta_tipo: str,
    entidad_id: UUID,
    tipo: str,
    importe: str,
) -> None:
    """Un movimiento del libro por el servicio de cuentas corrientes (mantiene `saldo_cuenta`)."""
    cuentas_service.registrar_movimiento(
        s.entorno.org,
        sesion,
        FixedClock(dia(11, 3)),
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        tipo=tipo,
        sentido=SENTIDO_DE_MOVIMIENTO[tipo],
        importe=Decimal(importe),
        origen_tipo=tipo,
        origen_id=uuid4(),
        occurred_at=dia(11, 3),
        usuario_id=s.entorno.usuario_id,
        dispositivo_id=s.entorno.dispositivo_id,
        operation_id=uuid4(),
    )
    sesion.commit()


def suma_del_libro(sesion: Any, s: Sesion, cuenta_tipo: str, entidad_id: UUID) -> Decimal:
    """El saldo según la suma en SQL de `cuenta_movimiento` (INV-13)."""
    return sesion.execute(  # type: ignore[no-any-return]
        text(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o AND cuenta_tipo = :t "
            "AND entidad_id = :e"
        ),
        {"o": s.entorno.org, "t": cuenta_tipo, "e": entidad_id},
    ).scalar_one()


def cuentas_del_entorno_en_cero(sesion: Any, s: Sesion) -> Sesion:
    """El entorno de ventas siembra un cliente con saldo inicial; se lo cancela con una cobranza
    para que las pruebas de saldos vean solo lo que ellas siembran."""
    saldo = suma_del_libro(sesion, s, "CLIENTE", s.entorno.cliente_id)
    if saldo != 0:
        mover_cuenta(sesion, s, "CLIENTE", s.entorno.cliente_id, "COBRANZA", str(saldo))
    return s
