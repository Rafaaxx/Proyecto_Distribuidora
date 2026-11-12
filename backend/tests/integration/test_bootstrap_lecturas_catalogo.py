"""Change 21, tarea 1.1 y 2.2 (spec `sync/bootstrap`, requisito "trae el catálogo activo para
vender"): `catalogo/service.py` entrega TODOS los productos activos con categoría, marca, alícuota y
presentaciones de venta, en una lectura masiva.

Reglas citadas: CAT-02, CAT-05, SYN-11, ADR-050, INV-21.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_referencia_sql,
    crear_presentacion_sql,
    crear_producto_sql,
    desactivar_producto_sql,
)

from app.modules.catalogo import service as catalogo_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _producto(sesion: Session, org: UUID, nombre: str) -> tuple[UUID, UUID, UUID]:
    """`(producto, caja de 6 de referencia, botella)`."""
    producto_id = crear_producto_sql(sesion, org, nombre=nombre)
    caja = crear_presentacion_referencia_sql(sesion, org, producto_id, unidades_base=6)
    botella = crear_presentacion_sql(sesion, org, producto_id, nombre="Botella", unidades_base=1)
    return producto_id, caja, botella


def test_cat05_trae_los_productos_activos_con_sus_presentaciones_de_menos_a_mas_unidades(
    db_session: Session,
) -> None:
    """Escenario "Producto activo con presentaciones": caja de 6 y unidad, con categoría, marca y
    alícuota del producto."""
    org = crear_organizacion(db_session).id
    producto_id, caja, botella = _producto(db_session, org, "Malbec 750")

    (producto,) = catalogo_service.listar_productos_para_dispositivo(org, db_session)

    assert producto.producto_id == producto_id
    assert producto.nombre == "Malbec 750"
    assert producto.marca_id is None
    fila = db_session.execute(
        text("SELECT categoria_id, alicuota_id FROM producto WHERE id = :p"), {"p": producto_id}
    ).one()
    assert (producto.categoria_id, producto.alicuota_id) == (fila.categoria_id, fila.alicuota_id)
    assert [
        (p.presentacion_id, p.unidades_base, p.es_referencia) for p in producto.presentaciones
    ] == [
        (botella, 1, False),
        (caja, 6, True),
    ]


def test_cat05_un_producto_inactivo_no_figura(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    activo, _, _ = _producto(db_session, org, "Activo")
    inactivo, _, _ = _producto(db_session, org, "Inactivo")
    desactivar_producto_sql(db_session, org, inactivo)

    ids = [
        p.producto_id for p in catalogo_service.listar_productos_para_dispositivo(org, db_session)
    ]

    assert ids == [activo]


def test_cat02_solo_baja_presentaciones_activas_y_de_venta(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    producto_id, caja, _ = _producto(db_session, org, "Vino")
    crear_presentacion_sql(
        db_session, org, producto_id, nombre="De baja", unidades_base=12, activo=False
    )
    crear_presentacion_sql(
        db_session, org, producto_id, nombre="Solo compra", unidades_base=24, usar_en_venta=False
    )

    (producto,) = catalogo_service.listar_productos_para_dispositivo(org, db_session)

    assert {p.nombre for p in producto.presentaciones} == {"Botella", "Caja x6"}
    assert caja in {p.presentacion_id for p in producto.presentaciones}


def test_trae_la_marca_cuando_el_producto_la_tiene(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    producto_id, _, _ = _producto(db_session, org, "Con marca")
    marca_id = UUID(int=1)
    db_session.execute(
        text(
            "INSERT INTO marca (id, organizacion_id, nombre, activo, creado_en, actualizado_en) "
            "VALUES (:id, :o, 'Bodega Norte', true, now(), now())"
        ),
        {"id": marca_id, "o": org},
    )
    db_session.execute(
        text("UPDATE producto SET marca_id = :m WHERE id = :p"), {"m": marca_id, "p": producto_id}
    )

    (producto,) = catalogo_service.listar_productos_para_dispositivo(org, db_session)

    assert producto.marca_id == marca_id


def test_inv21_no_trae_productos_de_otra_organizacion(db_session: Session) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    mio, _, _ = _producto(db_session, propia, "Mío")
    _producto(db_session, ajena, "Ajeno")

    productos = catalogo_service.listar_productos_para_dispositivo(propia, db_session)

    assert [p.producto_id for p in productos] == [mio]
