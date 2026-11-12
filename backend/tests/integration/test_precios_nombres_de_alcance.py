"""Change 13, tarea 5.4: las lecturas por lote de nombres que `precios` necesita para mostrar
el alcance de una regla (`catalogo/service.py` y `proveedores/service.py`, solo lectura, una
consulta por entidad; `design.md` `Enfoque técnico`).

Cada función filtra por la organización: un identificador de otra organización, o inexistente,
no aparece en el resultado (INV-21), y una lista vacía no consulta la base.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from precios_utiles import Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.proveedores import service as proveedores_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def test_los_nombres_de_productos_marcas_y_categorias(db_session: Session) -> None:
    entorno = Entorno(db_session)
    categoria_nombre = db_session.execute(
        text("SELECT nombre FROM categoria WHERE id = :c"),
        {"c": entorno.categoria_id},
    ).scalar_one()

    productos = catalogo_service.nombres_de_productos(
        entorno.org, [entorno.vino_id, uuid4()], db_session
    )
    marcas = catalogo_service.nombres_de_marcas(entorno.org, [entorno.marca_id], db_session)
    categorias = catalogo_service.nombres_de_categorias(
        entorno.org, [entorno.categoria_id], db_session
    )

    assert productos == {entorno.vino_id: "Vino A"}
    assert marcas == {entorno.marca_id: "Bodega Norte"}
    assert categorias == {entorno.categoria_id: categoria_nombre}


def test_los_nombres_de_proveedores(db_session: Session) -> None:
    entorno = Entorno(db_session)

    nombres = proveedores_service.nombres_de_proveedores(
        entorno.org, [entorno.proveedor_id, uuid4()], db_session
    )

    assert nombres == {entorno.proveedor_id: "Bodega Sur"}


def test_inv21_un_identificador_de_otra_organizacion_no_aparece(db_session: Session) -> None:
    entorno = Entorno(db_session)
    ajena = Entorno(db_session)

    assert catalogo_service.nombres_de_productos(entorno.org, [ajena.vino_id], db_session) == {}
    assert catalogo_service.nombres_de_marcas(entorno.org, [ajena.marca_id], db_session) == {}
    assert (
        catalogo_service.nombres_de_categorias(entorno.org, [ajena.categoria_id], db_session) == {}
    )
    assert (
        proveedores_service.nombres_de_proveedores(entorno.org, [ajena.proveedor_id], db_session)
        == {}
    )


def test_sin_identificadores_no_hay_resultado(db_session: Session) -> None:
    entorno = Entorno(db_session)

    assert catalogo_service.nombres_de_productos(entorno.org, [], db_session) == {}
    assert catalogo_service.nombres_de_marcas(entorno.org, [], db_session) == {}
    assert catalogo_service.nombres_de_categorias(entorno.org, [], db_session) == {}
    assert proveedores_service.nombres_de_proveedores(entorno.org, [], db_session) == {}
