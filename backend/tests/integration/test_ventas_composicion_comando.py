"""Tarea 16.1 (change 18a): la composición de la venta por el comando `VENTA_CONFIRMAR`, de punta a
punta contra PostgreSQL real (spec `ventas/composicion-de-venta`, requisitos de líneas, producto y
presentación vendibles). Las reglas puras tienen su prueba en
`tests/unit/test_ventas_domain_composicion.py`; acá se confirma que
el handler las aplica y que no deja efectos (INV-01).

Reglas citadas: VTA-02, CAT-02, CAT-05, INV-01, INV-21.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql
from ventas_confirmar_utiles import EntornoVenta

from app.modules.ventas.domain.errores import (
    CantidadInvalidaError,
    LineaDuplicadaError,
    PresentacionNoVendibleError,
    ProductoInactivoError,
    RecursoNoEncontradoError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def test_vta02_una_linea_repetida_se_rechaza_y_no_deja_efectos(entorno: EntornoVenta) -> None:
    """Escenario "Línea repetida": dos líneas de Vino A en "Caja x6"."""
    with pytest.raises(LineaDuplicadaError) as error:
        entorno.vender(
            entorno.linea(presentacion_id=entorno.caja_id, cantidad=1, unidades_presentacion=6),
            entorno.linea(presentacion_id=entorno.caja_id, cantidad=2, unidades_presentacion=6),
        )

    assert (error.value.codigo, error.value.status_http) == ("LINEA_DUPLICADA", 422)
    entorno.sin_efectos_de_venta()


def test_vta02_la_misma_presentacion_de_otro_producto_no_es_una_linea_repetida(
    entorno: EntornoVenta,
) -> None:
    """Triangula: dos líneas con la misma cantidad y presentación pero de productos distintos
    se aceptan; el rechazo es por (producto, presentación), no por la presentación sola."""
    cerveza_id, caja_cerveza_id = entorno.crear_producto("Cerveza B", unidades_caja=12)
    entorno.poner_precio(entorno.version_id, cerveza_id, "12500.00", 6)
    entorno.comprar(cerveza_id, 24, "500")
    entorno.sesion.commit()

    comando = entorno.vender(
        entorno.linea(cantidad=3),
        entorno.linea(cerveza_id, caja_cerveza_id, cantidad=1, unidades_presentacion=12),
    )

    assert comando.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert len(entorno.lineas_de_venta(venta.id)) == 2


@pytest.mark.parametrize(
    ("usar_en_venta", "activo"),
    [(False, True), (True, False)],
    ids=["sin_uso_en_venta", "inactiva"],
)
def test_cat02_una_presentacion_no_vendible_se_rechaza_con_409(
    entorno: EntornoVenta, usar_en_venta: bool, activo: bool
) -> None:
    """Escenario "Presentación no vendible": "Pallet" con `usar_en_venta = false` y otra
    presentación inactiva; cada venta se rechaza con `PRESENTACION_NO_VENDIBLE`."""
    pallet_id = crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Pallet",
        unidades_base=240,
        usar_en_venta=usar_en_venta,
        activo=activo,
    )
    entorno.sesion.commit()

    with pytest.raises(PresentacionNoVendibleError) as error:
        entorno.vender(
            entorno.linea(presentacion_id=pallet_id, cantidad=1, unidades_presentacion=240)
        )

    assert (error.value.codigo, error.value.status_http) == ("PRESENTACION_NO_VENDIBLE", 409)
    entorno.sin_efectos_de_venta()


def test_cat05_un_producto_inactivo_se_rechaza_con_409_y_uno_ajeno_responde_404(
    entorno: EntornoVenta, db_session: Session
) -> None:
    """Escenario "Producto inactivo o ajeno": el primero con `PRODUCTO_INACTIVO` (409), el
    segundo como inexistente (404, INV-21)."""
    ajeno = EntornoVenta(db_session)
    with pytest.raises(RecursoNoEncontradoError) as ajeno_error:
        entorno.vender(entorno.linea(ajeno.vino_id, ajeno.botella_id))
    assert ajeno_error.value.status_http == 404
    entorno.sin_efectos_de_venta()

    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :i"),
        {"o": entorno.org, "i": entorno.vino_id},
    )
    entorno.sesion.commit()
    with pytest.raises(ProductoInactivoError) as inactivo_error:
        entorno.vender(entorno.linea())

    assert (inactivo_error.value.codigo, inactivo_error.value.status_http) == (
        "PRODUCTO_INACTIVO",
        409,
    )
    entorno.sin_efectos_de_venta()


@pytest.mark.parametrize("cantidad", [0, -3])
def test_inv04_una_cantidad_que_no_es_positiva_se_rechaza_sin_efectos(
    entorno: EntornoVenta, cantidad: int
) -> None:
    """Escenario "Cantidad no entera" (la parte `0` y negativa; el `2.5` lo rechaza el esquema
    HTTP, `test_ventas_api.py::test_inv03_un_numero_json_...`): 422 y ningún efecto."""
    with pytest.raises(CantidadInvalidaError) as error:
        entorno.vender(entorno.linea(cantidad=cantidad, bruto="0.00"))

    assert (error.value.codigo, error.value.status_http) == ("CANTIDAD_INVALIDA", 422)
    entorno.sin_efectos_de_venta()
