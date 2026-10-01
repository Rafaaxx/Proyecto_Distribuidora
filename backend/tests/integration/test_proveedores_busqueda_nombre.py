"""Change 10, tarea 5.2: búsqueda de proveedores por nombre de `proveedores/service.py`
(`design.md` D4: proveedor por nombre).

Solo lectura, filtrada por la organización (INV-21), sin distinguir mayúsculas ni
espacios al borde, e incluye los inactivos (el alta de producto y de costo rechazan
después con `PROVEEDOR_INACTIVO`).
"""

from __future__ import annotations

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from sqlalchemy.orm import Session

from app.modules.proveedores import service as proveedores_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def test_busca_proveedores_sin_distinguir_mayusculas_ni_espacios(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    sur = crear_proveedor(db_session, org, nombre="Bodega Sur")
    crear_proveedor(db_session, org, nombre="Cervecería Norte")

    encontrados = proveedores_service.buscar_proveedores_por_nombre(
        org, "  BODEGA sur ", db_session
    )

    assert [p.id for p in encontrados] == [sur]


def test_incluye_inactivos_y_devuelve_todas_las_coincidencias(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    activo = crear_proveedor(db_session, org, nombre="Bodega Sur")
    inactivo = crear_proveedor(db_session, org, nombre="BODEGA SUR", activo=False)

    encontrados = proveedores_service.buscar_proveedores_por_nombre(org, "bodega sur", db_session)

    assert {p.id for p in encontrados} == {activo, inactivo}


def test_no_devuelve_los_de_otra_organizacion_y_vacio_no_coincide(db_session: Session) -> None:
    """INV-21: igual que si no existiera en ninguna."""
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    crear_proveedor(db_session, ajena, nombre="Bodega Sur")

    assert proveedores_service.buscar_proveedores_por_nombre(propia, "Bodega Sur", db_session) == []
    assert proveedores_service.buscar_proveedores_por_nombre(propia, "  ", db_session) == []
