"""Change 13, tarea 6.1: `catalogo/service.py` entrega en una consulta los productos activos de
la organización con su presentación de referencia, categoría, marca y proveedor, que es lo que
`precios` necesita para generar un borrador sin consultar producto por producto (`design.md`
"Lecturas nuevas en otros módulos").

Reglas citadas: CAT-05 (un producto inactivo no entra), CAT-08 (la presentación de
referencia), INV-21 (solo la organización del token), `design.md` D1 y D4.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from precios_utiles import Entorno
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql

from app.modules.catalogo import service as catalogo_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_entrega_los_productos_activos_con_su_referencia_categoria_marca_y_proveedor(
    entorno: Entorno,
) -> None:
    cerveza_id = entorno.crear_producto(
        "Cerveza B",
        unidades_base=12,
        categoria_id=entorno.categoria_id,
        marca_id=entorno.marca_id,
    )

    productos = catalogo_service.listar_productos_activos_con_referencia(
        entorno.org, entorno.sesion
    )

    por_id = {producto.producto_id: producto for producto in productos}
    assert set(por_id) == {entorno.vino_id, cerveza_id}
    cerveza = por_id[cerveza_id]
    assert cerveza.nombre == "Cerveza B"
    assert cerveza.unidades_referencia == 12
    assert cerveza.presentacion_referencia_id == entorno.presentacion_de_referencia(cerveza_id)
    assert cerveza.categoria_id == entorno.categoria_id
    assert cerveza.marca_id == entorno.marca_id
    assert cerveza.proveedor_id == entorno.proveedor_id
    vino = por_id[entorno.vino_id]
    assert vino.unidades_referencia == 6
    assert vino.marca_id is None, "un producto sin marca no la inventa"


def test_un_producto_activo_sin_presentacion_de_referencia_se_devuelve_sin_unidades(
    entorno: Entorno,
) -> None:
    """Decisión del 2026-10-06 (design D4): el producto sin referencia NO se descarta; se
    entrega sin presentación ni unidades de referencia para que `precios` lo informe."""
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")

    productos = catalogo_service.listar_productos_activos_con_referencia(
        entorno.org, entorno.sesion
    )

    por_id = {producto.producto_id: producto for producto in productos}
    assert set(por_id) == {entorno.vino_id, sin_referencia_id}
    sin_referencia = por_id[sin_referencia_id]
    assert sin_referencia.presentacion_referencia_id is None
    assert sin_referencia.unidades_referencia is None
    assert sin_referencia.proveedor_id == entorno.proveedor_id
    assert por_id[entorno.vino_id].unidades_referencia == 6, "los demás no cambian"


def test_un_producto_inactivo_sin_referencia_tampoco_se_devuelve(entorno: Entorno) -> None:
    inactivo_id = entorno.crear_producto_sin_referencia("Gaseosa vieja sin referencia")
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :p"), {"p": inactivo_id}
    )

    productos = catalogo_service.listar_productos_activos_con_referencia(
        entorno.org, entorno.sesion
    )

    assert [producto.producto_id for producto in productos] == [entorno.vino_id]


def test_no_devuelve_productos_inactivos(entorno: Entorno) -> None:
    inactivo_id = entorno.crear_producto("Gaseosa vieja")
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :p"), {"p": inactivo_id}
    )

    productos = catalogo_service.listar_productos_activos_con_referencia(
        entorno.org, entorno.sesion
    )

    assert [producto.producto_id for producto in productos] == [entorno.vino_id]


def test_no_devuelve_productos_de_otra_organizacion(db_session: Session) -> None:
    propia = Entorno(db_session)
    ajena = Entorno(db_session)

    productos = catalogo_service.listar_productos_activos_con_referencia(propia.org, db_session)

    assert {producto.producto_id for producto in productos} == {propia.vino_id}
    assert ajena.vino_id not in {producto.producto_id for producto in productos}


def test_es_una_sola_consulta_sin_importar_cuantos_productos_hay(entorno: Entorno) -> None:
    for numero in range(5):
        entorno.crear_producto(f"Producto {numero}")
    consultas: list[str] = []

    def _contar(_conexion: object, _cursor: object, sentencia: str, *_resto: object) -> None:
        consultas.append(sentencia)

    motor = entorno.sesion.get_bind()
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        productos = catalogo_service.listar_productos_activos_con_referencia(
            entorno.org, entorno.sesion
        )
    finally:
        event.remove(motor, "before_cursor_execute", _contar)

    assert len(productos) == 6
    assert len(consultas) == 1


def test_ordena_por_codigo_para_que_el_resultado_sea_estable(entorno: Entorno) -> None:
    for numero in range(3):
        entorno.crear_producto(f"Producto {numero}")

    productos = catalogo_service.listar_productos_activos_con_referencia(
        entorno.org, entorno.sesion
    )

    codigos = [
        entorno.sesion.execute(
            text("SELECT codigo FROM producto WHERE id = :p"), {"p": producto.producto_id}
        ).scalar_one()
        for producto in productos
    ]
    assert codigos == sorted(codigos)
    assert all(isinstance(producto.producto_id, UUID) for producto in productos)


# --- ajuste B: presentaciones de venta por lote (para las líneas del borrador, PRC-22) ------


def test_presentaciones_de_venta_solo_activas_y_de_venta_de_menor_a_mayor(
    entorno: Entorno,
) -> None:
    """Un producto con `Caja x6` (referencia), `Botella` (1), una presentación solo de compra
    y una inactiva: entrega las dos de venta activas, de menos unidades a más."""
    entorno.crear_presentacion(entorno.vino_id, "Botella", 1)
    crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Pallet",
        unidades_base=72,
        usar_en_venta=False,
    )
    crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Caja x12",
        unidades_base=12,
        activo=False,
    )

    por_producto = catalogo_service.presentaciones_de_venta_de_productos(
        entorno.org, [entorno.vino_id], entorno.sesion
    )

    assert [(p.nombre, p.unidades_base) for p in por_producto[entorno.vino_id]] == [
        ("Botella", 1),
        ("Caja x6", 6),
    ]


def test_presentaciones_de_venta_agrupa_por_producto_y_omite_los_que_no_tienen(
    entorno: Entorno,
) -> None:
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)
    sin_presentaciones = entorno.crear_producto("Sin nada", unidades_base=1)
    entorno.sesion.execute(
        text("DELETE FROM presentacion WHERE producto_id = :p"), {"p": sin_presentaciones}
    )

    por_producto = catalogo_service.presentaciones_de_venta_de_productos(
        entorno.org, [entorno.vino_id, cerveza_id, sin_presentaciones], entorno.sesion
    )

    assert set(por_producto) == {entorno.vino_id, cerveza_id}
    assert [p.unidades_base for p in por_producto[cerveza_id]] == [12]


def test_presentaciones_de_venta_es_una_consulta_y_no_cruza_organizaciones(
    db_session: Session,
) -> None:
    propia = Entorno(db_session)
    ajena = Entorno(db_session)
    productos = [propia.vino_id] + [propia.crear_producto(f"P{n}") for n in range(4)]
    consultas: list[str] = []

    def _contar(_conexion: object, _cursor: object, sentencia: str, *_resto: object) -> None:
        consultas.append(sentencia)

    motor = db_session.get_bind()
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        por_producto = catalogo_service.presentaciones_de_venta_de_productos(
            propia.org, [*productos, ajena.vino_id], db_session
        )
    finally:
        event.remove(motor, "before_cursor_execute", _contar)

    assert len(consultas) == 1
    assert set(por_producto) == set(productos)
    assert catalogo_service.presentaciones_de_venta_de_productos(propia.org, [], db_session) == {}
