"""Tarea 6.4 (change 18a; spec `catalogo/productos-y-presentaciones`; `design.md` D17, D18):
`catalogo.presentaciones_para_venta` lee las presentaciones con `FOR KEY SHARE`, y `ventas`
registra su verificador de uso: una presentación que figura en una línea de venta queda con sus
unidades congeladas.

Reglas citadas: INV-18, CAT-02, CAT-04, CAT-05, INV-21, ADR-023.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql, crear_producto_sql
from ventas_utiles import sembrar_venta_sql

from app.core.clock import FixedClock
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import UnidadesCongeladasError
from app.modules.ventas import service as ventas_service  # registra el verificador (D18)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RELOJ = FixedClock(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))


def _modificar_unidades(org: Any, sesion: Session, presentacion_id: Any, unidades: int) -> None:
    catalogo_service.modificar_presentacion(
        org,
        sesion,
        RELOJ,
        presentacion_id=presentacion_id,
        nombre="Caja x6",
        unidades_base=unidades,
        usar_en_venta=True,
        usar_en_compra=True,
        activo=True,
        actor_id=None,
    )


# --- la lectura para vender (D17 punto 3) -----------------------------------------------


def test_d17_devuelve_todas_las_presentaciones_de_los_productos_con_sus_marcas(
    db_session: Session,
) -> None:
    """Las vendibles y las que no (inactiva, sin uso en venta): quien vende decide con las marcas
    (`PRESENTACION_NO_VENDIBLE`)."""
    org = crear_organizacion(db_session).id
    vino = crear_producto_sql(db_session, org, nombre="Vino A")
    cerveza = crear_producto_sql(db_session, org, nombre="Cerveza B")
    caja = crear_presentacion_sql(db_session, org, vino, nombre="Caja x6", unidades_base=6)
    botella = crear_presentacion_sql(db_session, org, vino, nombre="Botella", unidades_base=1)
    pallet = crear_presentacion_sql(
        db_session, org, vino, nombre="Pallet", unidades_base=240, usar_en_venta=False
    )
    vieja = crear_presentacion_sql(
        db_session, org, vino, nombre="Caja x4", unidades_base=4, activo=False
    )
    caja12 = crear_presentacion_sql(db_session, org, cerveza, nombre="Caja x12", unidades_base=12)

    por_producto = catalogo_service.presentaciones_para_venta(org, [vino], db_session)

    assert set(por_producto) == {vino}
    marcas = {
        p.presentacion_id: (p.nombre, p.unidades_base, p.activo, p.usar_en_venta)
        for p in por_producto[vino]
    }
    assert marcas == {
        caja: ("Caja x6", 6, True, True),
        botella: ("Botella", 1, True, True),
        pallet: ("Pallet", 240, True, False),
        vieja: ("Caja x4", 4, False, True),
    }
    assert all(p.producto_id == vino for p in por_producto[vino])
    # Triangula: pedir los dos productos trae también el segundo, y sólo lo pedido.
    ambos = catalogo_service.presentaciones_para_venta(org, [vino, cerveza], db_session)
    assert [p.presentacion_id for p in ambos[cerveza]] == [caja12]


def test_inv21_no_trae_presentaciones_de_otra_organizacion_ni_de_productos_no_pedidos(
    db_session: Session,
) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    producto_ajeno = crear_producto_sql(db_session, ajena)
    crear_presentacion_sql(db_session, ajena, producto_ajeno, nombre="Caja x6", unidades_base=6)

    assert catalogo_service.presentaciones_para_venta(propia, [producto_ajeno], db_session) == {}
    assert catalogo_service.presentaciones_para_venta(propia, [], db_session) == {}


def test_inv18_la_lectura_toma_for_key_share_sobre_las_presentaciones(db_session: Session) -> None:
    """D18: la sentencia lleva `FOR KEY SHARE`. La espera real frente a una modificación
    simultánea se prueba con commits reales en la prueba de concurrencia de ventas (14.1)."""
    org = crear_organizacion(db_session).id
    producto = crear_producto_sql(db_session, org)
    crear_presentacion_sql(db_session, org, producto, nombre="Caja x6", unidades_base=6)
    sentencias: list[str] = []

    def _capturar(
        conexion: Connection, cursor: Any, sentencia: str, *resto: Any, **kw: Any
    ) -> None:
        sentencias.append(sentencia)

    motor = db_session.get_bind()
    event.listen(motor, "before_cursor_execute", _capturar)
    try:
        catalogo_service.presentaciones_para_venta(org, [producto], db_session)
    finally:
        event.remove(motor, "before_cursor_execute", _capturar)

    assert len(sentencias) == 1
    assert "FOR KEY SHARE" in sentencias[0]


# --- el verificador de uso de ventas (INV-18, ADR-023) -----------------------------------


def test_inv18_una_presentacion_vendida_conserva_sus_unidades(db_session: Session) -> None:
    """Escenario "INV-18 — presentación usada en una venta": `Caja x6` en una línea de venta
    (sembrada por SQL), sin compras ni costos: `PRESENTACION_MODIFICAR` a 12 unidades se
    rechaza con `UNIDADES_CONGELADAS` y conserva 6."""
    org = crear_organizacion(db_session).id
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, org)
    venta = sembrar_venta_sql(
        db_session,
        org,
        cliente_id=crear_cliente(db_session, org),
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
    )

    with pytest.raises(UnidadesCongeladasError) as error:
        _modificar_unidades(org, db_session, venta.presentacion_id, 12)

    assert error.value.codigo == "UNIDADES_CONGELADAS"
    presentacion = catalogo_service.obtener_presentacion(org, venta.presentacion_id, db_session)
    assert presentacion is not None
    assert presentacion.unidades_base == 6


def test_inv18_el_verificador_cuenta_la_linea_de_cualquier_estado_de_venta(
    db_session: Session,
) -> None:
    """D18: una presentación usada en una venta `ANULADA` también sigue congelada (TR-06)."""
    org = crear_organizacion(db_session).id
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, org)
    venta = sembrar_venta_sql(
        db_session,
        org,
        cliente_id=crear_cliente(db_session, org),
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        estado="ANULADA",
    )

    assert catalogo_service.presentacion_fue_usada(org, venta.presentacion_id, db_session)
    with pytest.raises(UnidadesCongeladasError):
        _modificar_unidades(org, db_session, venta.presentacion_id, 12)


def test_inv18_una_presentacion_sin_ventas_se_modifica_y_la_de_otra_organizacion_no_cuenta(
    db_session: Session,
) -> None:
    """Triangula: la presentación nunca vendida admite el cambio; la vendida de otra
    organización no la congela."""
    org = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    usuario_ajeno, dispositivo_ajeno = crear_usuario_y_dispositivo(db_session, ajena)
    sembrar_venta_sql(
        db_session,
        ajena,
        cliente_id=crear_cliente(db_session, ajena),
        usuario_id=usuario_ajeno,
        dispositivo_id=dispositivo_ajeno,
    )
    producto = crear_producto_sql(db_session, org)
    presentacion = crear_presentacion_sql(
        db_session, org, producto, nombre="Caja x6", unidades_base=6
    )

    assert not catalogo_service.presentacion_fue_usada(org, presentacion, db_session)
    _modificar_unidades(org, db_session, presentacion, 12)

    modificada = catalogo_service.obtener_presentacion(org, presentacion, db_session)
    assert modificada is not None
    assert modificada.unidades_base == 12


def test_el_verificador_de_ventas_esta_registrado_con_su_nombre() -> None:
    assert "ventas" in catalogo_service._REGISTRO_VERIFICADORES
    assert callable(ventas_service.presentacion_usada_en_venta)
    assert catalogo_service._REGISTRO_VERIFICADORES["ventas"] is (
        ventas_service.presentacion_usada_en_venta
    )
