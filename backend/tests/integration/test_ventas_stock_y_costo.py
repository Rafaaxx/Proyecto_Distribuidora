"""Tarea 7.4 (change 18a; spec `ventas/confirmacion-de-venta`, requisitos "El costo de cada línea
se congela al promedio vigente" y "Una venta que deja stock negativo se rechaza salvo permiso";
`design.md` D10, D11; gobernanza ALTA): stock y costo de `VENTA_CONFIRMAR` con conexión, contra
PostgreSQL real.

Reglas citadas: VTA-05, CST-11, CST-12, CST-14, STK-05, STK-06, ADR-039, INV-10, INV-12.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql
from ventas_confirmar_utiles import (
    PERMISOS_DE_SUPERVISOR,
    PERMISOS_DE_VENTA,
    EntornoVenta,
)

from app.modules.stock.domain.errores import StockInsuficienteError
from app.modules.sync.models import Observacion
from app.modules.ventas.domain.errores import ProductoSinCostoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _observaciones(entorno: EntornoVenta) -> list[Observacion]:
    entorno.sesion.expire_all()
    return list(
        entorno.sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
            .order_by(Observacion.codigo, Observacion.id)
        ).all()
    )


# --- el costo congelado (VTA-05, CST-11, CST-12, CST-14) ----------------------------------------


def test_cst11_la_venta_congela_el_promedio_y_una_compra_posterior_no_lo_cambia(
    db_session: Session,
) -> None:
    """Escenarios "Costo congelado del ejemplo de CST-11" y "Una compra posterior no cambia el
    costo congelado": 120 botellas a $1.050, se venden 72 y después se compran 60 a $1.200."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA, stock_inicial=120)

    entorno.vender(entorno.linea(cantidad=72))

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.costo_unitario, linea.costo_total) == (
        Decimal("1050.000000"),
        Decimal("75600.00"),
    )
    costo = entorno.costo()
    assert (costo.stock_total, costo.costo_promedio) == (48, Decimal("1050.000000"))

    entorno.comprar(entorno.vino_id, 60, "1200")
    entorno.sesion.commit()

    assert entorno.costo().costo_promedio == Decimal("1133.333333")
    entorno.sesion.expire_all()
    (linea_despues,) = entorno.lineas_de_venta(venta.id)
    assert (linea_despues.costo_unitario, linea_despues.costo_total) == (
        Decimal("1050.000000"),
        Decimal("75600.00"),
    )


def test_cst14_el_costo_total_redondea_una_sola_vez_con_el_promedio_de_seis_decimales(
    db_session: Session,
) -> None:
    """Triangula con un promedio periódico: 48 a $1.050 y 60 a $1.200 = $1.133,333333; 7
    botellas cuestan `7933.333331` -> `7933.33` (VTA-05, CST-14)."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)
    entorno.comprar(entorno.vino_id, 60, "1200")
    entorno.sesion.commit()

    entorno.vender(entorno.linea(cantidad=7))

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.costo_unitario == Decimal("1133.333333")
    assert linea.costo_total == Decimal("7933.33")
    assert entorno.costo().costo_promedio == Decimal("1133.333333")


def test_stk03_el_egreso_de_stock_lleva_el_origen_venta_y_el_costo(db_session: Session) -> None:
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)

    entorno.vender()

    (venta,) = entorno.ventas()
    (movimiento,) = entorno.movimientos_de_stock()
    assert (movimiento.origen_tipo, movimiento.origen_id) == ("VENTA", venta.id)
    assert (movimiento.cantidad_base, movimiento.costo_unitario) == (-15, Decimal("1050.000000"))
    assert movimiento.ubicacion_id == entorno.deposito_id


# --- el producto sin costo (D10, ADR-039) -------------------------------------------------------


def _vino_c_sin_costo(entorno: EntornoVenta) -> dict[str, object]:
    """Vino C: sin ingresos con costo, con precio y su presentación de una unidad."""
    from stock_utiles import crear_presentacion_sql

    producto_id = crear_producto_sql(entorno.sesion, entorno.org, nombre="Vino C")
    botella_id = crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        producto_id,
        nombre="Botella",
        unidades_base=1,
        es_referencia=True,
    )
    entorno.poner_precio(entorno.version_id, producto_id, "9000.00", 1)
    entorno.sesion.commit()
    return entorno.linea(
        producto_id, botella_id, 3, unidades_presentacion=1, precio="9000.00", unidades_referencia=1
    )


def test_d10_un_producto_sin_costo_se_rechaza_con_conexion_aun_con_el_permiso_de_negativo(
    db_session: Session,
) -> None:
    """Escenario "Producto sin costo con conexión": Vino C sin ingresos con costo y un usuario
    con `PERMITIR_STOCK_NEGATIVO`; el detalle nombra el producto."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)
    linea = _vino_c_sin_costo(entorno)

    with pytest.raises(ProductoSinCostoError) as error:
        entorno.vender(linea)

    assert (error.value.codigo, error.value.status_http) == ("PRODUCTO_SIN_COSTO", 409)
    assert error.value.extension is not None
    assert error.value.extension["productos"] == [
        {"producto_id": linea["producto_id"], "nombre": "Vino C"}
    ]
    entorno.sin_efectos_de_venta()


def test_d10_un_producto_sin_costo_y_sin_el_permiso_se_rechaza_por_stock(
    db_session: Session,
) -> None:
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)
    linea = _vino_c_sin_costo(entorno)

    with pytest.raises(StockInsuficienteError):
        entorno.vender(linea)

    entorno.sin_efectos_de_venta()


# --- stock insuficiente y negativo (D11, STK-05) ------------------------------------------------


def test_stk05_sin_el_permiso_una_venta_que_deja_negativo_se_rechaza(db_session: Session) -> None:
    """Escenario "Sin permiso": 48 botellas, un Vendedor sin el permiso vende 50."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)

    with pytest.raises(StockInsuficienteError) as error:
        entorno.vender(entorno.linea(cantidad=50))

    assert (error.value.codigo, error.value.status_http) == ("STOCK_INSUFICIENTE", 409)
    entorno.sin_efectos_de_venta()


def test_stk05_con_el_permiso_se_acepta_con_stock_negativo_y_costo_al_promedio(
    db_session: Session,
) -> None:
    """Escenario "Con permiso": se venden 50 con 48; saldo −2, costo total $52.500,00 y el
    comando queda `ACEPTADO_CON_OBSERVACIONES`."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)

    comando = entorno.vender(entorno.linea(cantidad=50))

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.costo_unitario, linea.costo_total) == (
        Decimal("1050.000000"),
        Decimal("52500.00"),
    )
    assert entorno.stock() == -2
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "STOCK_NEGATIVO"
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    assert observacion.detalle == {
        "linea_id": str(linea.id),
        "producto_id": str(entorno.vino_id),
        "ubicacion_id": str(entorno.deposito_id),
        "saldo_resultante": -2,
    }


def test_stk05_solo_la_linea_que_deja_negativo_se_observa(db_session: Session) -> None:
    """Triangula con dos líneas del mismo producto: 8 cajas (48) dejan 0; 2 botellas dejan −2
    y solo esa se observa."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)

    entorno.vender(
        entorno.linea(presentacion_id=entorno.caja_id, cantidad=8, unidades_presentacion=6),
        entorno.linea(cantidad=2),
    )

    (venta,) = entorno.ventas()
    _, segunda = entorno.lineas_de_venta(venta.id)
    (observacion,) = _observaciones(entorno)
    assert observacion.detalle is not None
    assert observacion.detalle["linea_id"] == str(segunda.id)
    assert observacion.detalle["saldo_resultante"] == -2


def test_stk05_el_permiso_sin_saldo_negativo_no_deja_observaciones(db_session: Session) -> None:
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)

    comando = entorno.vender()

    assert comando.estado == "ACEPTADO"
    assert _observaciones(entorno) == []


def test_d11_el_promedio_no_se_recalcula_al_regularizar_el_negativo(db_session: Session) -> None:
    """La venta sobre saldo negativo congela el promedio vigente y la compra que regulariza no
    la toca (INV-10, `design.md` D11)."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)
    entorno.vender(entorno.linea(cantidad=50))
    entorno.sesion.commit()

    entorno.comprar(entorno.vino_id, 60, "1200")
    entorno.sesion.commit()

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.costo_total == Decimal("52500.00")
    assert entorno.stock() == 58
