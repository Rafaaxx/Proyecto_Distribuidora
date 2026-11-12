"""Change 10, tarea 5.2: búsquedas por clave natural de `catalogo/service.py` que usa la
importación (`design.md` D4): categoría y marca por nombre, producto por código.

Solo lectura, filtradas por la organización (INV-21), sin distinguir mayúsculas ni
espacios al borde, e incluyen los inactivos (el servicio de alta rechaza después con el
código de inactivo, `CATEGORIA_INACTIVA`). Devuelven una lista: quien llama decide qué
hacer con la ambigüedad.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.configuracion.models import AlicuotaIva

# Registra el puerto de consulta de proveedor que `crear_producto` exige (D9-A, ADR-025).
from app.modules.proveedores import service as proveedores_service  # noqa: F401

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


def _producto(sesion: Session, org: UUID, codigo: str) -> UUID:
    categoria = catalogo_service.crear_categoria(
        org, sesion, RELOJ, nombre=f"Cat {codigo}", actor_id=None
    )
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=org,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    sesion.flush()
    producto, _ = catalogo_service.crear_producto(
        org,
        sesion,
        RELOJ,
        codigo=codigo,
        nombre="Producto",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=crear_proveedor(sesion, org),
        unidad_base="botella",
        alicuota_id=alicuota.id,
        presentaciones=[DatosPresentacion("Botella", 1, True, True, True)],
        actor_id=None,
    )
    return producto.id


def test_busca_categorias_sin_distinguir_mayusculas_ni_espacios(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    vinos = catalogo_service.crear_categoria(org, db_session, RELOJ, nombre="Vinos", actor_id=None)
    catalogo_service.crear_categoria(org, db_session, RELOJ, nombre="Cervezas", actor_id=None)

    encontradas = catalogo_service.buscar_categorias_por_nombre(org, "  vINos ", db_session)

    assert [c.id for c in encontradas] == [vinos.id]


def test_busca_categorias_devuelve_todas_las_coincidencias_y_los_inactivos(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    activa = catalogo_service.crear_categoria(org, db_session, RELOJ, nombre="Vinos", actor_id=None)
    inactiva = catalogo_service.crear_categoria(
        org, db_session, RELOJ, nombre="VINOS", actor_id=None
    )
    catalogo_service.modificar_categoria(
        org,
        db_session,
        RELOJ,
        categoria_id=inactiva.id,
        nombre="VINOS",
        activo=False,
        actor_id=None,
    )

    encontradas = catalogo_service.buscar_categorias_por_nombre(org, "vinos", db_session)

    assert {c.id for c in encontradas} == {activa.id, inactiva.id}


def test_busca_categorias_nunca_devuelve_las_de_otra_organizacion(db_session: Session) -> None:
    """INV-21."""
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    catalogo_service.crear_categoria(ajena, db_session, RELOJ, nombre="Vinos", actor_id=None)

    assert catalogo_service.buscar_categorias_por_nombre(propia, "Vinos", db_session) == []


def test_busca_categorias_sin_coincidencia_o_con_texto_vacio_da_lista_vacia(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    catalogo_service.crear_categoria(org, db_session, RELOJ, nombre="Vinos", actor_id=None)

    assert catalogo_service.buscar_categorias_por_nombre(org, "Vinoss", db_session) == []
    assert catalogo_service.buscar_categorias_por_nombre(org, "   ", db_session) == []


def test_busca_marcas_con_los_mismos_criterios(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    casa = catalogo_service.crear_marca(org, db_session, RELOJ, nombre="Casa Vieja", actor_id=None)
    catalogo_service.crear_marca(ajena, db_session, RELOJ, nombre="Casa Vieja", actor_id=None)

    encontradas = catalogo_service.buscar_marcas_por_nombre(org, " casa vieja", db_session)

    assert [m.id for m in encontradas] == [casa.id]
    assert catalogo_service.buscar_marcas_por_nombre(org, "Otra", db_session) == []


def test_busca_productos_por_codigo_sin_distinguir_mayusculas(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    producto_id = _producto(db_session, org, "VA-750")
    _producto(db_session, ajena, "VA-750")

    encontrados = catalogo_service.buscar_productos_por_codigo(org, " va-750 ", db_session)

    assert [p.id for p in encontrados] == [producto_id]
    assert catalogo_service.buscar_productos_por_codigo(org, "VA-751", db_session) == []
    assert catalogo_service.buscar_productos_por_codigo(org, "", db_session) == []
