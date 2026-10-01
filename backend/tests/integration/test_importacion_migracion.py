"""Tarea 1.1 (change 10): la migración crea `importacion` según `docs/03-modelo-de-
datos.md` §13 más las columnas de operación (`design.md` D9 y D14).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_stock_migracion.py`); que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py` (tarea 2.1).

Reglas citadas: INV-02, INV-03, INV-04, INV-05, INV-21, `design.md` D9 (catálogo de
tipos, con `COSTOS` y `PRECIOS`), D14 (columnas de operación, solo se guardan las
importaciones confirmadas, solo inserción).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

REVISION_ANTERIOR = "a8b9c0d1e2f3"  # `stock_y_costeo`, la revisión previa a este change.
MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

COLUMNAS = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "tipo": ("text", False),
    "archivo_nombre": ("text", False),
    "estado": ("text", False),
    "filas_total": ("integer", False),
    "filas_ok": ("integer", False),
    "filas_error": ("integer", False),
    "errores": ("jsonb", False),
    "operation_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
}

# `03` §13 más `COSTOS` (D9): `PRECIOS` figura aunque no tenga importador hasta el 13.
TIPOS = [
    "PRODUCTOS",
    "CLIENTES",
    "PROVEEDORES",
    "PRECIOS",
    "COSTOS",
    "STOCK_INICIAL",
    "SALDOS_INICIALES",
]


def _columnas(motor: Engine) -> dict[str, tuple[str, bool]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'importacion'
                """
            )
        )
        return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def _restricciones(motor: Engine, tipo: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    """
                    SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = CAST('public.importacion' AS regclass) AND contype = :tipo
                    """
                ),
                {"tipo": tipo},
            ).all()
        )


def _fks(motor: Engine) -> dict[str, str]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT tc.constraint_name,
                       string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position)
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON kcu.constraint_name = tc.constraint_name
                 AND kcu.table_schema = tc.table_schema
                WHERE tc.table_schema = 'public' AND tc.table_name = 'importacion'
                  AND tc.constraint_type = 'FOREIGN KEY'
                GROUP BY tc.constraint_name
                """
            )
        )
        return dict(filas.all())


def _existe_la_tabla(motor: Engine) -> bool:
    with motor.connect() as conexion:
        return (
            conexion.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'importacion'"
                )
            ).scalar_one()
            == 1
        )


# --- columnas, claves e índice ------------------------------------------------


def test_la_tabla_tiene_las_columnas_de_03_y_las_de_operacion(_engine_de_sesion: Engine) -> None:
    """`03` §13 + `design.md` D14 (`operation_id`, `usuario_id`, `dispositivo_id`,
    `occurred_at`, `registered_at`, `03` §2.3)."""
    assert _columnas(_engine_de_sesion) == COLUMNAS


def test_las_filas_son_integer_y_los_momentos_timestamptz(_engine_de_sesion: Engine) -> None:
    """INV-04: toda cantidad es `integer`; `CLAUDE.md` §4: `timestamptz`."""
    columnas = _columnas(_engine_de_sesion)

    assert {columnas[c][0] for c in ("filas_total", "filas_ok", "filas_error")} == {"integer"}
    assert {columnas[c][0] for c in ("occurred_at", "registered_at")} == {
        "timestamp with time zone"
    }


def test_la_clave_primaria_es_el_id_y_hay_unicidad_por_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02: sin `UNIQUE (organizacion_id, id)` ninguna tabla futura puede
    referenciar la fila con FK compuesta."""
    assert _restricciones(_engine_de_sesion, "p") == {"pk_importacion": "PRIMARY KEY (id)"}
    assert _restricciones(_engine_de_sesion, "u") == {
        "ux_importacion__org_id": "UNIQUE (organizacion_id, id)"
    }


def test_las_fk_son_compuestas_con_organizacion_id(_engine_de_sesion: Engine) -> None:
    """INV-21, `03` §2.4: toda FK entre entidades de negocio incluye `organizacion_id`."""
    assert _fks(_engine_de_sesion) == {
        "fk_importacion__organizacion": "organizacion_id",
        "fk_importacion__usuario": "organizacion_id,usuario_id",
        "fk_importacion__dispositivo": "organizacion_id,dispositivo_id",
    }


def test_el_check_de_tipo_declara_el_catalogo_completo_de_d9(_engine_de_sesion: Engine) -> None:
    definicion = _restricciones(_engine_de_sesion, "c")["ck_importacion__tipo"]

    for tipo in TIPOS:
        assert f"'{tipo}'" in definicion


def test_los_check_estan_en_la_base(_engine_de_sesion: Engine) -> None:
    assert set(_restricciones(_engine_de_sesion, "c")) == {
        "ck_importacion__tipo",
        "ck_importacion__estado",
        "ck_importacion__filas_no_negativas",
    }


def test_el_indice_del_historial_ordena_por_momento_descendente(
    _engine_de_sesion: Engine,
) -> None:
    """`design.md` Migration Plan: historial de la organización, lo más reciente
    primero, con `id` de desempate (cursor estable)."""
    with _engine_de_sesion.connect() as conexion:
        definicion = conexion.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'importacion' AND indexname = 'ix_importacion__historial'"
            )
        ).scalar_one()

    assert "(organizacion_id, registered_at DESC, id DESC)" in definicion


# --- permisos (INV-05) ---------------------------------------------------------


def test_app_runtime_solo_lee_e_inserta(app_runtime_engine: Engine) -> None:
    """D14-A y INV-05: el registro de importaciones es de solo inserción."""
    with app_runtime_engine.connect() as conexion:
        privilegios = set(
            conexion.execute(
                text(
                    """
                    SELECT privilege_type FROM information_schema.role_table_grants
                    WHERE table_schema = 'public' AND table_name = 'importacion'
                      AND grantee = 'app_runtime'
                    """
                )
            )
            .scalars()
            .all()
        )

    assert privilegios == {"SELECT", "INSERT"}


@pytest.mark.parametrize(
    "sentencia", ["UPDATE importacion SET filas_ok = 1", "DELETE FROM importacion"]
)
def test_inv05_app_runtime_no_puede_actualizar_ni_borrar(
    app_runtime_engine: Engine, sentencia: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(sentencia))

    assert "permission denied" in str(error.value)


# --- comportamiento de la base -------------------------------------------------


def _armar(db_session: Session) -> tuple[UUID, UUID, UUID]:
    organizacion = crear_organizacion(db_session)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, organizacion.id)
    return organizacion.id, usuario_id, dispositivo_id


def _insertar(db_session: Session, entorno: tuple[UUID, UUID, UUID], **cambios: object) -> None:
    organizacion_id, usuario_id, dispositivo_id = entorno
    valores: dict[str, object] = {
        "id": uuid4(),
        "org": organizacion_id,
        "tipo": "PROVEEDORES",
        "archivo": "proveedores.csv",
        "estado": "CONFIRMADA",
        "total": 2,
        "ok": 2,
        "error": 0,
        "operacion": uuid4(),
        "usuario": usuario_id,
        "dispositivo": dispositivo_id,
        "momento": MOMENTO,
    }
    valores.update(cambios)
    db_session.execute(
        text(
            """
            INSERT INTO importacion (id, organizacion_id, tipo, archivo_nombre, estado,
                filas_total, filas_ok, filas_error, operation_id, usuario_id,
                dispositivo_id, occurred_at, registered_at)
            VALUES (:id, :org, :tipo, :archivo, :estado, :total, :ok, :error, :operacion,
                :usuario, :dispositivo, :momento, :momento)
            """
        ),
        valores,
    )


@pytest.mark.parametrize("tipo", TIPOS)
def test_cada_tipo_del_catalogo_se_acepta(db_session: Session, tipo: str) -> None:
    _insertar(db_session, _armar(db_session), tipo=tipo)

    assert db_session.execute(text("SELECT tipo FROM importacion")).scalar_one() == tipo


@pytest.mark.parametrize("tipo", ["VENTAS", "proveedores", "", "LISTAS"])
def test_un_tipo_fuera_del_catalogo_se_rechaza(db_session: Session, tipo: str) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, tipo=tipo)

    assert "ck_importacion__tipo" in str(error.value)


@pytest.mark.parametrize("estado", ["PARCIAL", "confirmada", ""])
def test_un_estado_fuera_del_catalogo_se_rechaza(db_session: Session, estado: str) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, estado=estado)

    assert "ck_importacion__estado" in str(error.value)


@pytest.mark.parametrize("columna", ["total", "ok", "error"])
def test_las_filas_no_pueden_ser_negativas(db_session: Session, columna: str) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, **{columna: -1})

    assert "ck_importacion__filas_no_negativas" in str(error.value)


def test_el_cero_es_una_cantidad_de_filas_valida(db_session: Session) -> None:
    _insertar(db_session, _armar(db_session), total=0, ok=0, error=0)


def test_los_errores_nacen_como_arreglo_vacio_por_defecto(db_session: Session) -> None:
    """D14-A: con el modo todo o nada solo se guardan importaciones exitosas:
    `errores` = `[]`."""
    _insertar(db_session, _armar(db_session))

    assert db_session.execute(text("SELECT errores FROM importacion")).scalar_one() == []


def test_inv21_el_usuario_y_el_dispositivo_deben_ser_de_la_misma_organizacion(
    db_session: Session,
) -> None:
    org_a, usuario_a, dispositivo_a = _armar(db_session)
    _, usuario_b, dispositivo_b = _armar(db_session)

    with pytest.raises(IntegrityError) as error_usuario, db_session.begin_nested():
        _insertar(db_session, (org_a, usuario_b, dispositivo_a))
    assert "fk_importacion__usuario" in str(error_usuario.value)

    with pytest.raises(IntegrityError) as error_dispositivo, db_session.begin_nested():
        _insertar(db_session, (org_a, usuario_a, dispositivo_b))
    assert "fk_importacion__dispositivo" in str(error_dispositivo.value)


# --- ciclo de la migración -----------------------------------------------------


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones},
        capture_output=True,
        text=True,
    )


def test_downgrade_elimina_la_tabla_y_upgrade_la_recrea_vacia_y_utilizable(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`alembic downgrade -1` y `alembic upgrade head` limpios, sobre una base CON
    datos (`docs/04` §2.1 punto 4). La base es compartida con el resto de la
    sesión: la prueba DEBE terminar en `head`."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(sesion, entorno)
        sesion.commit()
    assert _existe_la_tabla(_engine_de_sesion)

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert not _existe_la_tabla(_engine_de_sesion)
    finally:
        subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr

    try:
        assert _existe_la_tabla(_engine_de_sesion)
        with Session(_engine_de_sesion) as sesion:
            assert sesion.execute(text("SELECT count(*) FROM importacion")).scalar_one() == 0
            _insertar(sesion, _armar(sesion))
            sesion.commit()
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
