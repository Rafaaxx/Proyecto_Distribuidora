"""Tarea 1.2: `clientes/models.py` declara `cliente` exactamente como la
crea la migración, sin carga diferida.

Unitario a propósito: no toca PostgreSQL (eso lo cubre
`tests/integration/test_modelos_coinciden_con_migracion.py`, que corre
`alembic revision --autogenerate` contra la base migrada y falla si el
generado no es un `pass`). Acá se fija la forma declarativa -- columnas,
tipos, nulabilidad, `CHECK`, FKs, unicidades e índices -- que es lo que el
autogenerate compara con el esquema real.

Referencias: `docs/03-modelo-de-datos.md` §10, `design.md` D1 (código y
documento únicos con índice parcial), D2 (`lista_precio_id` sin FK),
D5 (`condicion_iva` no se crea), D6 (`tolerancia_offline_valor` en
`numeric(14,2)`), CLI-03 (marca de consumidor final), INV-21/INV-05.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import class_mapper

from app.core.db import Base
from app.modules.clientes.models import Cliente

COLUMNAS_ESPERADAS = (
    "id",
    "organizacion_id",
    "codigo",
    "nombre",
    "razon_social",
    "documento_tipo",
    "documento_numero",
    "direccion",
    "contacto",
    "telefono",
    "email",
    "lista_precio_id",
    "limite_credito",
    "politica_credito",
    "tolerancia_offline_tipo",
    "tolerancia_offline_valor",
    "estado_facturacion_default",
    "es_consumidor_final",
    "estado",
    "creado_en",
    "actualizado_en",
    "actualizado_por_id",
)

NOMBRES_DE_CHECK = {
    "ck_cliente__estado",
    "ck_cliente__documento_tipo",
    "ck_cliente__documento_pareja",
    "ck_cliente__tolerancia_tipo",
    "ck_cliente__tolerancia_pareja",
    "ck_cliente__tolerancia_valor",
    "ck_cliente__limite_credito",
    "ck_cliente__politica_credito",
    "ck_cliente__estado_facturacion",
}

NOMBRES_DE_FK = {"fk_cliente__organizacion", "fk_cliente__actualizado_por"}

NOMBRES_DE_INDICE = {
    "ux_cliente__codigo",
    "ux_cliente__documento",
    "ix_cliente__org_nombre",
    "ix_cliente__org_estado_nombre",
    "ix_cliente__org_documento",
}


def _columna(nombre: str):  # type: ignore[no-untyped-def]
    columna = Cliente.__table__.columns.get(nombre)
    assert columna is not None, f"Falta la columna {nombre!r} en `cliente`."
    return columna


def _restricciones(tipo: type) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        str(restriccion.name)
        for restriccion in Cliente.__table__.constraints
        if isinstance(restriccion, tipo) and restriccion.name is not None
    }


def _indices() -> dict[str, Index]:
    return {indice.name: indice for indice in Cliente.__table__.indexes}


def test_la_tabla_se_llama_cliente_y_esta_registrada_en_la_metadata() -> None:
    assert Cliente.__tablename__ == "cliente"
    assert Base.metadata.tables["cliente"] is Cliente.__table__


def test_tiene_exactamente_las_columnas_de_03_mas_los_momentos() -> None:
    assert tuple(Cliente.__table__.columns.keys()) == COLUMNAS_ESPERADAS


def test_no_tiene_la_columna_condicion_iva_que_reserva_el_change_de_facturacion() -> None:
    """D5: `03` §10 lista `condicion_iva`, pero `01` §16 y FAC-04 no definen su
    dominio; el change de facturación la agrega junto con su catálogo."""
    assert "condicion_iva" not in Cliente.__table__.columns


@pytest.mark.parametrize(
    "nombre",
    ["organizacion_id", "nombre", "direccion", "contacto", "estado", "es_consumidor_final"],
)
def test_las_columnas_obligatorias_no_aceptan_nulo(nombre: str) -> None:
    assert _columna(nombre).nullable is False


def test_credito_y_tolerancia_usan_numeric_14_2_y_admiten_nulo() -> None:
    """D6: `numeric(14,2)` como en `configuracion_organizacion`; el nulo
    significa "hereda el de la organización" (CRE-03, CRE-06) y para el
    límite "sin control" (CRE-01)."""
    for nombre in ("limite_credito", "tolerancia_offline_valor"):
        columna = _columna(nombre)
        assert isinstance(columna.type, Numeric)
        assert (columna.type.precision, columna.type.scale) == (14, 2)
        assert columna.nullable is True


def test_lista_precio_id_no_tiene_clave_foranea_hasta_el_change_13() -> None:
    """D2: la columna existe (la declara `03` §10 y PRC-20 la consume) pero sin
    FK, como `producto.proveedor_id` antes del change 13 (ADR-025)."""
    columna = _columna("lista_precio_id")
    assert columna.nullable is True
    assert not columna.foreign_keys


def test_las_fk_son_compuestas_y_usan_organizacion_id() -> None:
    assert _restricciones(ForeignKeyConstraint) == NOMBRES_DE_FK
    organizacion = next(
        restriccion
        for restriccion in Cliente.__table__.constraints
        if isinstance(restriccion, ForeignKeyConstraint)
        and restriccion.name == "fk_cliente__organizacion"
    )
    assert [columna.name for columna in organizacion.columns] == ["organizacion_id"]
    assert [elemento.target_fullname for elemento in organizacion.elements] == ["organizacion.id"]
    actualizado_por = next(
        restriccion
        for restriccion in Cliente.__table__.constraints
        if isinstance(restriccion, ForeignKeyConstraint)
        and restriccion.name == "fk_cliente__actualizado_por"
    )
    assert [columna.name for columna in actualizado_por.columns] == [
        "organizacion_id",
        "actualizado_por_id",
    ]
    assert [elemento.target_fullname for elemento in actualizado_por.elements] == [
        "usuario.organizacion_id",
        "usuario.id",
    ]


def test_tiene_la_unicidad_compuesta_que_habilita_las_fk_de_los_changes_siguientes() -> None:
    """`UNIQUE (organizacion_id, id)`: sin ella, `venta`, `cobranza` y
    `compra` no pueden referenciar al cliente con FK compuesta (INV-21)."""
    assert _restricciones(UniqueConstraint) == {"ux_cliente__org_id"}
    uniques = next(
        restriccion
        for restriccion in Cliente.__table__.constraints
        if isinstance(restriccion, UniqueConstraint) and restriccion.name == "ux_cliente__org_id"
    )
    assert [columna.name for columna in uniques.columns] == ["organizacion_id", "id"]


def test_los_checks_de_catalogo_y_de_pareja_estan_declarados() -> None:
    """Los catálogos cerrados viven también en la base: un valor fuera de
    ellos no entra ni por un camino que se salte el dominio."""
    assert _restricciones(CheckConstraint) == NOMBRES_DE_CHECK


def test_codigo_y_documento_son_unicos_por_organizacion_con_indice_parcial() -> None:
    """D1: la unicidad la garantiza la base (índice parcial, `WHERE ... IS NOT
    NULL`), no solo el handler: dos requests concurrentes pueden pasar la
    validación y el índice es lo que los separa."""
    indices = _indices()
    assert set(indices) >= NOMBRES_DE_INDICE

    codigo = indices["ux_cliente__codigo"]
    assert codigo.unique is True
    assert [columna.name for columna in codigo.columns] == ["organizacion_id", "codigo"]
    assert str(codigo.dialect_options["postgresql"]["where"]) == "codigo IS NOT NULL"

    documento = indices["ux_cliente__documento"]
    assert documento.unique is True
    assert [columna.name for columna in documento.columns] == [
        "organizacion_id",
        "documento_tipo",
        "documento_numero",
    ]
    assert str(documento.dialect_options["postgresql"]["where"]) == "documento_numero IS NOT NULL"


def test_los_indices_de_listado_cubren_organizacion_estado_y_texto() -> None:
    """El listado filtra por texto (nombre, razón social, código o documento) y
    por estado, y pagina por `nombre` (`02` §11)."""
    indices = _indices()
    assert [columna.name for columna in indices["ix_cliente__org_nombre"].columns] == [
        "organizacion_id",
        "nombre",
    ]
    assert [columna.name for columna in indices["ix_cliente__org_estado_nombre"].columns] == [
        "organizacion_id",
        "estado",
        "nombre",
    ]
    assert [columna.name for columna in indices["ix_cliente__org_documento"].columns] == [
        "organizacion_id",
        "documento_numero",
    ]


def test_no_declara_ninguna_relacion_orm() -> None:
    """`CLAUDE.md` §4: la carga diferida implícita está desactivada; este módulo
    no declara `relationship()` alguna, como `proveedores/models.py`. Toda
    lectura pasa por consultas explícitas de `clientes/repository.py`."""
    mapper = class_mapper(Cliente)
    assert list(mapper.relationships) == []


def test_es_consumidor_final_no_tiene_valor_por_defecto() -> None:
    """La marca solo la asigna el comando de habilitación (CLI-03, D4): si el
    modelo trajera un `default`, un alta común podría nacer marcada."""
    columna = _columna("es_consumidor_final")
    assert columna.default is None
    assert columna.server_default is None
