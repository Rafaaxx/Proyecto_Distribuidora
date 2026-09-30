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

# Lista explícita y enumerable (`design.md` D7, tarea 3.1): catálogos
# globales, sin `organizacion_id`, sincronizados por migración y no editables
# desde la aplicación. Una tabla de negocio nueva NUNCA se agrega acá por
# comodidad: cada entrada tiene que poder justificarse igual que `permiso`
# (`03` §4, `03` §17). `rol_permiso`, aunque referencia este catálogo, sí es
# una tabla de negocio (tarea 3.3): no va en esta lista.
#
# `intento_login` (grupo 11, `ADR-018`) se agrega acá aunque no es un
# catálogo: es una tabla de infraestructura de seguridad transversal a
# organizaciones a propósito (el límite de intentos por IP protege contra
# fuerza bruta repartida entre organizaciones, incluso contra un
# `organizacion_slug` que no existe). Decisión señalada para revisión humana
# en el docstring de la migración `e5f6a7b8c9d0` -- ver ahí el razonamiento
# completo; no se decide en silencio.
TABLAS_GLOBALES_EXENTAS = frozenset({"permiso", "intento_login"})

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
        if nombre not in TABLAS_DE_SISTEMA
        and nombre not in TABLAS_GLOBALES_EXENTAS
        and nombre != TABLA_RAIZ_SIN_ORGANIZACION
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
    if "organizacion_id" in pk:
        # PK = organizacion_id (caso configuracion_organizacion) o PK
        # compuesta que EMPIEZA por organizacion_id (casos rol_permiso, tarea
        # 3.3, y saldo_cuenta, change 08 D11): en ambos casos la base no
        # permite una fila sin organización y el índice de la clave sirve a las
        # consultas por organización.
        if pk[0] != "organizacion_id":
            return (
                f"'{tabla}' tiene una PK compuesta que no empieza por "
                f"organizacion_id: {pk} (docs/03 §2.4)."
            )
        return None

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
        if tabla_destino in TABLAS_GLOBALES_EXENTAS:
            # D7: la FK hacia un catálogo global (`permiso`) es simple a
            # propósito, porque el catálogo no tiene organización.
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


# --- Exención del catálogo global (grupo 3, `design.md` D7) ----------------


def test_la_lista_de_globales_exentas_es_explicita_y_enumerable() -> None:
    """Escenario "El catálogo global de permisos queda exento de forma
    explícita"."""
    assert isinstance(TABLAS_GLOBALES_EXENTAS, frozenset)
    assert {"permiso", "intento_login"} == TABLAS_GLOBALES_EXENTAS


def test_una_tabla_de_negocio_no_declarada_se_verifica_igual(
    _tabla_temporal_sin_organizacion_id: Engine,
) -> None:
    """Escenario "Una tabla de negocio no puede exentarse por omisión": una
    tabla nueva que no está en `TABLAS_GLOBALES_EXENTAS` se revisa como
    cualquier otra tabla de negocio (y por eso el fixture, que la crea sin
    `organizacion_id`, hace que la revisión la marque en rojo)."""
    tablas = _tablas_de_negocio(_tabla_temporal_sin_organizacion_id)
    assert "inv02_negativo_sin_org" in tablas


def test_rol_permiso_si_se_verifica_como_tabla_de_negocio(database_url: str) -> None:
    """Escenario "La relación entre roles y permisos sí pertenece a una
    organización": `rol_permiso` referencia el catálogo global `permiso`
    pero no está exenta -- se revisa y pasa porque su PK compuesta incluye
    `organizacion_id`."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    tablas = _tablas_de_negocio(engine)
    assert "rol_permiso" in tablas
    assert _tabla_declara_organizacion_id_obligatoria(engine, "rol_permiso") is None
    assert _fk_simple_entre_negocio(engine, "rol_permiso") == []


# --- Clave primaria compuesta (change 08, D11) -------------------------------


def test_saldo_cuenta_cumple_inv02_con_su_pk_compuesta_que_empieza_por_organizacion(
    database_url: str,
) -> None:
    """Change 08, D11: `saldo_cuenta` no tiene `id`; su PK es
    `(organizacion_id, cuenta_tipo, entidad_id)` y cumple INV-02 sin `UNIQUE
    (organizacion_id, id)`."""
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)

    assert _columnas_pk(engine, "saldo_cuenta")[0] == "organizacion_id"
    assert _tabla_declara_organizacion_id_obligatoria(engine, "saldo_cuenta") is None


@pytest.fixture
def _tabla_temporal_con_pk_que_no_empieza_por_organizacion(database_url: str) -> Iterator[Engine]:
    aplicar_migraciones(database_url)
    engine = crear_engine(database_url)
    with engine.connect() as conexion:
        conexion.execute(
            text(
                "CREATE TABLE inv02_negativo_pk_desordenada ("
                "organizacion_id uuid NOT NULL REFERENCES organizacion (id), "
                "clave uuid NOT NULL, "
                "PRIMARY KEY (clave, organizacion_id))"
            )
        )
        conexion.commit()
    try:
        yield engine
    finally:
        with engine.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv02_negativo_pk_desordenada"))
            conexion.commit()


def test_inv02_detecta_una_pk_compuesta_que_no_empieza_por_organizacion_id(
    _tabla_temporal_con_pk_que_no_empieza_por_organizacion: Engine,
) -> None:
    mensaje = _tabla_declara_organizacion_id_obligatoria(
        _tabla_temporal_con_pk_que_no_empieza_por_organizacion, "inv02_negativo_pk_desordenada"
    )
    assert mensaje is not None
    assert "inv02_negativo_pk_desordenada" in mensaje
    assert "no empieza por organizacion_id" in mensaje
