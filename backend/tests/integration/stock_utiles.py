"""Utilidades compartidas de las pruebas de integración de `stock` y `costeo`
(change 09).

Reusa `cuentas_corrientes_utiles` (organización, usuario, dispositivo) y agrega
lo que el libro de stock necesita para no insertar en el vacío: un producto
(con su categoría, alícuota y proveedor), una ubicación y un motivo. Inserta con
SQL directo para probar la base sin pasar por los servicios de otros módulos.

Es un módulo y no un `conftest.py` por el mismo motivo que
`cuentas_corrientes_utiles`: `tests/integration` no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

# `costo_producto`, `stock_saldo` y `stock_movimiento` tienen FK a `producto`: la
# tabla tiene que estar en `Base.metadata` para que SQLAlchemy resuelva las FK al
# hacer `flush`. En la aplicacion la registra `app.main`; en las pruebas de un
# servicio suelto, este import.
from app.modules.catalogo import models as _catalogo_models  # noqa: F401
from app.modules.costeo import models as _costeo_models  # noqa: F401
from app.modules.stock import models as _stock_models  # noqa: F401

try:
    from cuentas_corrientes_utiles import crear_proveedor
except ModuleNotFoundError:  # desde `tests/properties`, `tests/integration` no está en el path
    from tests.integration.cuentas_corrientes_utiles import crear_proveedor

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def crear_producto_sql(sesion: Session, organizacion_id: UUID, *, nombre: str = "Vino A") -> UUID:
    """Producto activo mínimo (categoría, alícuota y proveedor propios)."""
    categoria_id = uuid4()
    alicuota_id = uuid4()
    producto_id = uuid4()
    proveedor_id = crear_proveedor(sesion, organizacion_id)
    sesion.execute(
        text(
            "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, :nombre, true, :m, :m)"
        ),
        {
            "id": categoria_id,
            "org": organizacion_id,
            "nombre": f"Cat-{uuid4().hex[:8]}",
            "m": MOMENTO,
        },
    )
    sesion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, '21%', 0.210000, true, :m, :m)"
        ),
        {"id": alicuota_id, "org": organizacion_id, "m": MOMENTO},
    )
    sesion.execute(
        text(
            "INSERT INTO producto (id, organizacion_id, codigo, nombre, categoria_id, marca_id, "
            "proveedor_id, unidad_base, alicuota_id, activo, creado_en, actualizado_en) "
            "VALUES (:id, :org, :codigo, :nombre, :cat, NULL, :prov, 'botella', :ali, true, "
            ":m, :m)"
        ),
        {
            "id": producto_id,
            "org": organizacion_id,
            "codigo": f"COD-{uuid4().hex[:8]}",
            "nombre": nombre,
            "cat": categoria_id,
            "prov": proveedor_id,
            "ali": alicuota_id,
            "m": MOMENTO,
        },
    )
    return producto_id


def crear_ubicacion_sql(
    sesion: Session,
    organizacion_id: UUID,
    *,
    nombre: str | None = None,
    tipo: str = "DEPOSITO",
    requiere_toma: bool = False,
    activo: bool = True,
) -> UUID:
    ubicacion_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO ubicacion (id, organizacion_id, nombre, tipo, requiere_toma, activo, "
            "creado_en, actualizado_en) VALUES (:id, :org, :nombre, :tipo, :toma, :activo, "
            ":m, :m)"
        ),
        {
            "id": ubicacion_id,
            "org": organizacion_id,
            "nombre": nombre or f"Depósito {uuid4().hex[:6]}",
            "tipo": tipo,
            "toma": requiere_toma,
            "activo": activo,
            "m": MOMENTO,
        },
    )
    return ubicacion_id


def crear_motivo_sql(sesion: Session, organizacion_id: UUID) -> UUID:
    motivo_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, 'AJUSTE_STOCK', :nombre, true, :m, :m)"
        ),
        {
            "id": motivo_id,
            "org": organizacion_id,
            "nombre": f"Motivo {uuid4().hex[:6]}",
            "m": MOMENTO,
        },
    )
    return motivo_id


def insertar_stock_movimiento_sql(sesion: Session, **cambios: object) -> UUID:
    """`INSERT` directo en `stock_movimiento`. Los valores por defecto arman un
    `STOCK_INICIAL` de 60 unidades a 1000; `organizacion_id`, `producto_id`,
    `ubicacion_id`, `usuario_id` y `dispositivo_id` los pasa quien llama."""
    movimiento_id = uuid4()
    valores: dict[str, object] = {
        "id": movimiento_id,
        "cantidad_base": 60,
        "tipo": "STOCK_INICIAL",
        "origen_tipo": "STOCK_INICIAL",
        "origen_id": uuid4(),
        "costo_unitario": Decimal("1000.000000"),
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
        "operation_id": uuid4(),
        **cambios,
    }
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(
        text(f"INSERT INTO stock_movimiento ({columnas}) VALUES ({marcadores})"), valores
    )
    return movimiento_id


def crear_presentacion_referencia_sql(
    sesion: Session, organizacion_id: UUID, producto_id: UUID, *, unidades_base: int = 6
) -> UUID:
    """Presentación de referencia (CAT-08) del producto: la que la pantalla usa
    para mostrar el stock en cajas + unidades."""
    presentacion_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO presentacion (id, organizacion_id, producto_id, nombre, unidades_base, "
            "usar_en_venta, usar_en_compra, es_referencia, activo, creado_en, actualizado_en) "
            "VALUES (:id, :org, :prod, :nombre, :u, true, true, true, true, :m, :m)"
        ),
        {
            "id": presentacion_id,
            "org": organizacion_id,
            "prod": producto_id,
            "nombre": f"Caja x{unidades_base}",
            "u": unidades_base,
            "m": MOMENTO,
        },
    )
    return presentacion_id


def desactivar_producto_sql(sesion: Session, organizacion_id: UUID, producto_id: UUID) -> None:
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": organizacion_id, "p": producto_id},
    )
