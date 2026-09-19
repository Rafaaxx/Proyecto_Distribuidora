"""INV-03: ningún importe, costo o porcentaje se representa con punto
flotante binario (`docs/01-dominio.md` §20; `docs/03-modelo-de-datos.md`
§2.2; `docs/04-roadmap-changes.md` §5).

Recorre `information_schema.columns` de la base migrada y falla si aparece
`real`, `double precision`, `float4`/`float8` o `money` en cualquier columna
del esquema de la aplicación, nombrando tabla y columna.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import aplicar_migraciones
from sqlalchemy import Engine, text

from app.core.db import crear_engine

TIPOS_PROHIBIDOS = ("real", "double precision", "money")

_CONSULTA_CATALOGO = text(
    """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, column_name
    """
)


def _columnas_de_punto_flotante(engine: Engine) -> list[tuple[str, str, str]]:
    with engine.connect() as conexion:
        filas = conexion.execute(_CONSULTA_CATALOGO).all()

    return [
        (tabla, columna, tipo) for tabla, columna, tipo in filas if tipo.lower() in TIPOS_PROHIBIDOS
    ]


def test_inv03_la_base_migrada_no_tiene_columnas_de_punto_flotante_binario(
    database_url: str,
) -> None:
    """INV-03: recorre el catálogo de columnas de una base con todas las
    migraciones aplicadas y falla si aparece `real`, `double precision` o
    `money` en cualquier columna de negocio."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    infractoras = _columnas_de_punto_flotante(engine)

    assert infractoras == [], (
        f"INV-03: columnas con punto flotante binario o `money` en el esquema: {infractoras}"
    )


@pytest.fixture
def _tabla_temporal_con_columna_flotante(database_url: str) -> Iterator[Engine]:
    """Crea una tabla temporal con una columna `double precision`, para
    verificar en negativo que la prueba de INV-03 detecta la infracción
    (tarea 6.3: la migración de prueba no persiste, se limpia al final)."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    with engine.connect() as conexion:
        conexion.execute(
            text(
                "CREATE TABLE inv03_negativo_prueba "
                "(id integer PRIMARY KEY, importe_mal_tipado double precision)"
            )
        )
        conexion.commit()

    try:
        yield engine
    finally:
        with engine.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv03_negativo_prueba"))
            conexion.commit()


def test_inv03_detecta_una_columna_double_precision_introducida_por_error(
    _tabla_temporal_con_columna_flotante: Engine,
) -> None:
    """Verificación en negativo (tarea 6.3): si una migración introdujera
    una columna de punto flotante, esta prueba debe identificarla."""
    infractoras = _columnas_de_punto_flotante(_tabla_temporal_con_columna_flotante)

    assert ("inv03_negativo_prueba", "importe_mal_tipado", "double precision") in infractoras
