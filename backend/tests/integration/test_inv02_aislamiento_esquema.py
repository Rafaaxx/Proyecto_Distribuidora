"""INV-02 (`docs/01-dominio.md` §20): todo dato de negocio pertenece a
exactamente una organización. `02` §15 exige comprobarlo con una prueba
que recorra `information_schema`.

Recorre dinámicamente TODAS las tablas del esquema `public` (menos
`alembic_version`, que no es una tabla de negocio, y `organizacion`, que es
la organización misma y por eso es la única tabla sin `organizacion_id`:
INV-02 la define como el punto de referencia, no como un dato que pertenece
a una). No se mantiene una lista fija de nombres de tabla de negocio: cada
change que agrega una tabla queda cubierto automáticamente (`design.md`,
Risks).

Para cada tabla de negocio exige:
- `organizacion_id` `NOT NULL` (tarea 3.1).
- `UNIQUE (organizacion_id, id)`, o que `organizacion_id` sea la propia PK de
  la tabla (caso `configuracion_organizacion`, `docs/03` §2.4) (tarea 3.1).
- Toda FK saliente hacia otra tabla de negocio incluye `organizacion_id`,
  excepto la referencia de `organizacion_id` a `organizacion (id)` (tarea 3.2).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import aplicar_migraciones
from sqlalchemy import Engine, text

from app.core.db import crear_engine

TABLA_RAIZ_SIN_ORGANIZACION = "organizacion"
TABLAS_DE_SISTEMA = {"alembic_version"}

_CONSULTA_TABLAS = text(
    """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name
    """
)

_CONSULTA_COLUMNAS = text(
    """
    SELECT column_name, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :tabla
    """
)

_CONSULTA_PK = text(
    """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = :tabla
      AND tc.constraint_type = 'PRIMARY KEY'
    ORDER BY kcu.ordinal_position
    """
)

_CONSULTA_UNIQUE = text(
    """
    SELECT tc.constraint_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = :tabla
      AND tc.constraint_type = 'UNIQUE'
    ORDER BY tc.constraint_name, kcu.ordinal_position
    """
)

_CONSULTA_FK = text(
    """
    SELECT
        tc.constraint_name,
        kcu.column_name AS columna_origen,
        ccu.table_name AS tabla_destino
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = :tabla
      AND tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.constraint_name, kcu.ordinal_position
    """
)


def _tablas_de_negocio(engine: Engine) -> list[str]:
    with engine.connect() as conexion:
        nombres = [fila[0] for fila in conexion.execute(_CONSULTA_TABLAS).all()]
    return [
        nombre
        for nombre in nombres
        if nombre not in TABLAS_DE_SISTEMA and nombre != TABLA_RAIZ_SIN_ORGANIZACION
    ]


def _columnas(engine: Engine, tabla: str) -> dict[str, str]:
    with engine.connect() as conexion:
        filas = conexion.execute(_CONSULTA_COLUMNAS, {"tabla": tabla}).all()
    return {nombre: es_nulable for nombre, es_nulable in filas}


def _columnas_pk(engine: Engine, tabla: str) -> list[str]:
    with engine.connect() as conexion:
        return [fila[0] for fila in conexion.execute(_CONSULTA_PK, {"tabla": tabla}).all()]


def _grupos_unique(engine: Engine, tabla: str) -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = {}
    with engine.connect() as conexion:
        for nombre_restriccion, columna in conexion.execute(
            _CONSULTA_UNIQUE, {"tabla": tabla}
        ).all():
            grupos.setdefault(nombre_restriccion, []).append(columna)
    return grupos


def _fks_agrupadas(engine: Engine, tabla: str) -> dict[str, tuple[str, list[str]]]:
    """Devuelve `{nombre_restriccion: (tabla_destino, [columnas_origen])}`."""
    agrupadas: dict[str, tuple[str, list[str]]] = {}
    columnas_por_restriccion: dict[str, list[str]] = {}
    destino_por_restriccion: dict[str, str] = {}
    with engine.connect() as conexion:
        for nombre_restriccion, columna_origen, tabla_destino in conexion.execute(
            _CONSULTA_FK, {"tabla": tabla}
        ).all():
            columnas_por_restriccion.setdefault(nombre_restriccion, []).append(columna_origen)
            destino_por_restriccion[nombre_restriccion] = tabla_destino
    for nombre_restriccion, columnas in columnas_por_restriccion.items():
        agrupadas[nombre_restriccion] = (destino_por_restriccion[nombre_restriccion], columnas)
    return agrupadas


def _tabla_declara_organizacion_id_obligatoria(engine: Engine, tabla: str) -> str | None:
    """Devuelve un mensaje de error si `tabla` no cumple INV-02, o `None`."""
    columnas = _columnas(engine, tabla)
    if "organizacion_id" not in columnas:
        return f"'{tabla}' no tiene columna organizacion_id (INV-02)."
    if columnas["organizacion_id"] != "NO":
        return f"'{tabla}.organizacion_id' admite NULL (INV-02)."

    pk = _columnas_pk(engine, tabla)
    if pk == ["organizacion_id"]:
        return None  # PK = organizacion_id (caso configuracion_organizacion): automático.

    unique_ok = any(
        set(columnas_unique) == {"organizacion_id", "id"}
        for columnas_unique in _grupos_unique(engine, tabla).values()
    )
    if not unique_ok:
        return f"'{tabla}' no declara UNIQUE (organizacion_id, id) (docs/03 §2.4)."
    return None


def _fk_simple_entre_negocio(engine: Engine, tabla: str) -> list[str]:
    """Lista de mensajes de error por cada FK de `tabla` que referencia otra
    tabla de negocio sin incluir `organizacion_id` (excepto la FK de
    `organizacion_id` a `organizacion`)."""
    errores = []
    for nombre_restriccion, (tabla_destino, columnas_origen) in _fks_agrupadas(
        engine, tabla
    ).items():
        if columnas_origen == ["organizacion_id"] and tabla_destino == TABLA_RAIZ_SIN_ORGANIZACION:
            continue
        if "organizacion_id" not in columnas_origen:
            errores.append(
                f"'{tabla}' tiene la FK '{nombre_restriccion}' hacia '{tabla_destino}' "
                f"sin organizacion_id entre sus columnas: {columnas_origen} (docs/03 §2.4)."
            )
    return errores


def test_inv02_toda_tabla_de_negocio_exige_organizacion_id_obligatoria_y_unica(
    database_url: str,
) -> None:
    """Escenario 'Una tabla de negocio sin organización no llega a la base'."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    tablas = _tablas_de_negocio(engine)
    assert tablas, "No se encontraron tablas de negocio: la migración no corrió."

    errores = [
        mensaje
        for tabla in tablas
        if (mensaje := _tabla_declara_organizacion_id_obligatoria(engine, tabla)) is not None
    ]
    assert errores == [], f"INV-02 violado en {len(tablas)} tablas revisadas: {errores}"


def test_inv02_ninguna_fk_entre_tablas_de_negocio_es_simple(database_url: str) -> None:
    """Escenario 'El esquema no tiene referencias simples entre entidades de
    negocio'."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    tablas = _tablas_de_negocio(engine)
    errores = [error for tabla in tablas for error in _fk_simple_entre_negocio(engine, tabla)]
    assert errores == [], f"FK simples entre tablas de negocio: {errores}"


# --- Verificación en negativo (tarea 3.3) ----------------------------------


@pytest.fixture
def _tabla_temporal_sin_organizacion_id(database_url: str) -> Iterator[Engine]:
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)
    with engine.connect() as conexion:
        conexion.execute(
            text("CREATE TABLE inv02_negativo_sin_org (id uuid PRIMARY KEY, nombre text)")
        )
        conexion.commit()
    try:
        yield engine
    finally:
        with engine.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv02_negativo_sin_org"))
            conexion.commit()


def test_inv02_detecta_una_tabla_sin_organizacion_id(
    _tabla_temporal_sin_organizacion_id: Engine,
) -> None:
    mensaje = _tabla_declara_organizacion_id_obligatoria(
        _tabla_temporal_sin_organizacion_id, "inv02_negativo_sin_org"
    )
    assert mensaje is not None
    assert "inv02_negativo_sin_org" in mensaje
    assert "organizacion_id" in mensaje


@pytest.fixture
def _tabla_temporal_con_fk_simple(database_url: str) -> Iterator[Engine]:
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)
    with engine.connect() as conexion:
        conexion.execute(
            text(
                "CREATE TABLE inv02_negativo_fk_simple ("
                "id uuid PRIMARY KEY, "
                "organizacion_id uuid NOT NULL REFERENCES organizacion (id), "
                "alicuota_id uuid NOT NULL REFERENCES alicuota_iva (id), "
                "CONSTRAINT ux_inv02_negativo_fk_simple__org_id UNIQUE (organizacion_id, id))"
            )
        )
        conexion.commit()
    try:
        yield engine
    finally:
        with engine.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv02_negativo_fk_simple"))
            conexion.commit()


def test_inv02_detecta_una_fk_simple_entre_tablas_de_negocio(
    _tabla_temporal_con_fk_simple: Engine,
) -> None:
    errores = _fk_simple_entre_negocio(_tabla_temporal_con_fk_simple, "inv02_negativo_fk_simple")
    assert len(errores) == 1
    assert "inv02_negativo_fk_simple" in errores[0]
    assert "alicuota_iva" in errores[0]
