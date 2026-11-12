"""Change 10, tarea 7.1: búsqueda de ubicaciones por nombre de `stock/service.py`
(`design.md` D4: ubicación por nombre).

Solo lectura, filtrada por la organización (INV-21), sin distinguir mayúsculas ni
espacios al borde, e incluye las inactivas (el stock inicial rechaza después con
`UBICACION_INACTIVA`).
"""

from __future__ import annotations

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql

from app.modules.stock import service as stock_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def test_busca_ubicaciones_sin_distinguir_mayusculas_ni_espacios(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    deposito = crear_ubicacion_sql(db_session, org, nombre="Depósito Central")
    crear_ubicacion_sql(db_session, org, nombre="Camión 1")

    encontradas = stock_service.buscar_ubicaciones_por_nombre(
        org, "  DEPÓSITO central ", db_session
    )

    assert [u.id for u in encontradas] == [deposito]


def test_incluye_inactivas_y_devuelve_todas_las_coincidencias(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    activa = crear_ubicacion_sql(db_session, org, nombre="Camión 2")
    inactiva = crear_ubicacion_sql(db_session, org, nombre="Camión 2 ", activo=False)

    encontradas = stock_service.buscar_ubicaciones_por_nombre(org, "camión 2", db_session)

    assert {u.id for u in encontradas} == {activa, inactiva}


def test_no_devuelve_las_de_otra_organizacion_y_vacio_no_coincide(db_session: Session) -> None:
    """INV-21: igual que si no existiera en ninguna."""
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    crear_ubicacion_sql(db_session, ajena, nombre="Depósito Central")

    assert stock_service.buscar_ubicaciones_por_nombre(propia, "Depósito Central", db_session) == []
    assert stock_service.buscar_ubicaciones_por_nombre(propia, "  ", db_session) == []
