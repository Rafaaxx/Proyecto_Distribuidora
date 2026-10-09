"""INV-04: las cantidades viajan y se guardan como enteros en unidad base
(`docs/01-dominio.md` §20; `docs/03-modelo-de-datos.md` §2.2; `CLAUDE.md` §4
"Cantidades en unidad base: `integer` siempre"; change 09, tarea 9.3).

Dos capas, cada una con su prueba en negativo:

1. Catálogo de columnas: toda columna cuyo nombre dice que es una cantidad
   (`cantidad`, `unidades_base`, `stock_*`) es un entero (`integer`/`smallint`/
   `bigint`). Una columna `numeric`, `real` o `double precision` con ese nombre
   rompe la prueba y se nombra tabla y columna. Se exige además que el catálogo
   incluya las columnas que este change crea, para que la regla no quede vacía.
2. Contrato de la API: en el OpenAPI generado, toda propiedad de cantidad es de
   tipo `integer`, nunca `number` ni `string`. El rechazo de un valor no entero
   por HTTP se prueba con el arnés de la ruta en
   `test_stock_api.py::TestStockInicialRegistrar`.

Los costos y los importes no son cantidades: viajan como cadena decimal y su
regla es INV-03 (`test_inv03_sin_punto_flotante.py`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.main import crear_app

TIPOS_ENTEROS = ("integer", "smallint", "bigint")
_NOMBRE_DE_CANTIDAD = re.compile(r"(^|_)(cantidad|unidades|stock)(_|$)")

# Las columnas de cantidad que crean los changes 05 y 09: si el catálogo dejara de
# encontrarlas, la regla estaría comprobando un conjunto vacío.
COLUMNAS_QUE_DEBEN_ESTAR = {
    ("presentacion", "unidades_base"),
    ("stock_movimiento", "cantidad_base"),
    ("stock_saldo", "cantidad_base"),
    ("costo_producto", "stock_total"),
    ("costo_producto_mov", "cantidad"),
    ("costo_producto_mov", "stock_anterior"),
    ("costo_producto_mov", "stock_nuevo"),
    # Change 11 (compras): la cantidad base de la línea es entera (INV-04).
    ("compra_linea", "cantidad_base"),
    ("compra_linea", "unidades_presentacion"),
    # Change 14 (transferencias y ajustes): cantidades enteras en unidad base (INV-04).
    ("transferencia_linea", "cantidad_base"),
    ("ajuste_stock_linea", "cantidad_base"),
}

# `03` §2.2: la cantidad EN PRESENTACION es `numeric(14,3)` solo en compras (2,5 cajas);
# la cantidad base derivada es entera y la valida el servicio (`design.md` D5 del
# change 11). Es la única excepción: cualquier otra columna de cantidad decimal rompe
# la prueba, y esta debe seguir siendo exactamente `numeric(14,3)`.
EXCEPCIONES_DE_CANTIDAD_EN_PRESENTACION = {("compra_linea", "cantidad"): (14, 3)}

_CONSULTA = text(
    """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, column_name
    """
)


def _columnas_de_cantidad(engine: Engine) -> list[tuple[str, str, str]]:
    with engine.connect() as conexion:
        filas = conexion.execute(_CONSULTA).all()
    return [
        (tabla, columna, tipo)
        for tabla, columna, tipo in filas
        if _NOMBRE_DE_CANTIDAD.search(columna)
    ]


def test_inv04_toda_columna_de_cantidad_del_esquema_es_entera(_engine_de_sesion: Engine) -> None:
    columnas = _columnas_de_cantidad(_engine_de_sesion)

    infractoras = _infractoras(columnas)

    assert infractoras == [], f"INV-04: columnas de cantidad que no son enteras: {infractoras}"


def _infractoras(columnas: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Columnas de cantidad no enteras, salvo la cantidad en presentación de compras."""
    return [
        fila
        for fila in columnas
        if fila[2].lower() not in TIPOS_ENTEROS
        and (fila[0], fila[1]) not in EXCEPCIONES_DE_CANTIDAD_EN_PRESENTACION
    ]


def test_inv04_la_unica_excepcion_es_la_cantidad_en_presentacion_de_compras(
    _engine_de_sesion: Engine,
) -> None:
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = 'compra_linea' AND column_name = 'cantidad'"
            )
        ).all()

    assert [(f[0], f[1], f[2], (f[3], f[4])) for f in filas] == [
        ("compra_linea", "cantidad", "numeric", (14, 3))
    ]


def test_inv04_el_catalogo_incluye_las_columnas_de_cantidad_de_los_changes(
    _engine_de_sesion: Engine,
) -> None:
    encontradas = {
        (tabla, columna) for tabla, columna, _ in _columnas_de_cantidad(_engine_de_sesion)
    }

    assert encontradas >= COLUMNAS_QUE_DEBEN_ESTAR


@pytest.fixture
def _tabla_temporal_con_cantidad_decimal(_engine_de_sesion: Engine) -> Iterator[Engine]:
    with _engine_de_sesion.connect() as conexion:
        conexion.execute(
            text(
                "CREATE TABLE inv04_negativo_prueba "
                "(id integer PRIMARY KEY, cantidad_base numeric(14,2))"
            )
        )
        conexion.commit()
    try:
        yield _engine_de_sesion
    finally:
        with _engine_de_sesion.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv04_negativo_prueba"))
            conexion.commit()


def test_inv04_detecta_una_columna_de_cantidad_decimal(
    _tabla_temporal_con_cantidad_decimal: Engine,
) -> None:
    """En negativo: la prueba de arriba falla si aparece una cantidad `numeric`."""
    columnas = _columnas_de_cantidad(_tabla_temporal_con_cantidad_decimal)

    infractoras = _infractoras(columnas)

    assert infractoras == [("inv04_negativo_prueba", "cantidad_base", "numeric")]


def _propiedades_de_cantidad(openapi: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    esquemas: dict[str, Any] = openapi.get("components", {}).get("schemas", {})
    encontradas = []
    for nombre, esquema in esquemas.items():
        for propiedad, definicion in esquema.get("properties", {}).items():
            if _NOMBRE_DE_CANTIDAD.search(propiedad):
                encontradas.append((nombre, propiedad, definicion))
    return encontradas


def _tipos_de(definicion: dict[str, Any]) -> set[str]:
    """Los tipos JSON que admite una propiedad, resolviendo `anyOf` (campos
    opcionales, que admiten `null`)."""
    if "type" in definicion:
        return {definicion["type"]}
    return {tipo for alternativa in definicion.get("anyOf", []) for tipo in _tipos_de(alternativa)}


# La cantidad EN PRESENTACION de una línea de compra (2,5 cajas) viaja como string decimal
# (nunca como `number`: INV-03) porque `03` §2.2 la admite fraccionaria; la cantidad base
# derivada es entera y la devuelve el servidor (`design.md` D5 del change 11). Es la única
# excepción por esquema y propiedad (la petición y el detalle de la compra, lote 2); debe
# ser `string`.
EXCEPCIONES_DE_CANTIDAD_EN_PRESENTACION_OPENAPI = frozenset(
    {("CompraLineaRequest", "cantidad"), ("CompraLineaResponse", "cantidad")}
)


def test_inv04_toda_propiedad_de_cantidad_del_openapi_es_integer() -> None:
    app = crear_app(Settings(_env_file=None, database_url="postgresql+psycopg://x/x"))
    propiedades = _propiedades_de_cantidad(app.openapi())

    assert propiedades, "El OpenAPI no expone ninguna propiedad de cantidad."
    infractoras = [
        (esquema, propiedad, sorted(_tipos_de(definicion) - {"null"}))
        for esquema, propiedad, definicion in propiedades
        if _tipos_de(definicion) - {"null"} != {"integer"}
        and (esquema, propiedad) not in EXCEPCIONES_DE_CANTIDAD_EN_PRESENTACION_OPENAPI
    ]
    assert infractoras == [], f"INV-04: propiedades de cantidad que no son integer: {infractoras}"


def test_inv04_la_cantidad_en_presentacion_de_compra_viaja_como_string_nunca_number() -> None:
    app = crear_app(Settings(_env_file=None, database_url="postgresql+psycopg://x/x"))
    propiedades = {
        (esquema, propiedad): definicion
        for esquema, propiedad, definicion in _propiedades_de_cantidad(app.openapi())
    }

    for clave in EXCEPCIONES_DE_CANTIDAD_EN_PRESENTACION_OPENAPI:
        assert _tipos_de(propiedades[clave]) == {"string"}, clave


def test_inv04_detecta_una_propiedad_de_cantidad_numerica_en_el_openapi() -> None:
    """En negativo: un esquema con `cantidad_base: number` sería una infracción."""
    openapi = {
        "components": {
            "schemas": {
                "Mala": {"properties": {"cantidad_base": {"type": "number"}}},
                "Buena": {"properties": {"cantidad_base": {"type": "integer"}}},
            }
        }
    }

    propiedades = _propiedades_de_cantidad(openapi)
    infractoras = [
        nombre for nombre, _, definicion in propiedades if _tipos_de(definicion) != {"integer"}
    ]

    assert infractoras == ["Mala"]
