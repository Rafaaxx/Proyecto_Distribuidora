"""Verifica que las migraciones aplican y revierten limpio contra
PostgreSQL real (`docs/04-roadmap-changes.md` §2.1, criterio 4).

Este test corre alembic directamente contra la base compartida de la
sesión de pytest (la misma que usan `_engine_de_sesion`/`db_session` en
`conftest.py`), no contra una base propia. Por eso DEBE terminar con la
base en `head`: si terminara en `downgrade base`, cualquier test de
integración que corra después perdería todas las tablas (fallaría con
`relation "organizacion" does not exist` o similar) según el orden de
recolección de pytest.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    NOMBRE_ROL_MIGRACIONES,
    _crear_roles_de_base,
    _url_con_credenciales,
)
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    # Alembic lee `DATABASE_URL_MIGRATIONS` (rol `app_migrations`, dueño del
    # esquema), nunca `DATABASE_URL` (tarea 1.5, `app/core/alembic_url.py`).
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )


@pytest.mark.usefixtures("database_url")
def test_upgrade_head_y_downgrade_base_corren_limpios(database_url: str) -> None:
    # Esta prueba corre alembic directo (sin pasar por `aplicar_migraciones`),
    # así que crea los dos roles de base (tarea 1.4, INV-05) a mano: las
    # migraciones de este change otorgan permisos a `app_runtime` y fallarían
    # con "el rol no existe" si nadie los creó todavía en esta sesión.
    _crear_roles_de_base(database_url)

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    resultado_down = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    # Repetido: debe seguir corriendo limpio sobre una base ya usada.
    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    resultado_down_2 = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down_2.returncode == 0, resultado_down_2.stderr

    # Deja la base en `head`: es compartida con el resto de la sesión de
    # pytest (ver docstring del módulo). Terminar en `base` rompería todos
    # los tests de integración que corran después de este.
    resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_final.returncode == 0, resultado_up_final.stderr


def _sembrar_datos_representativos(database_url: str) -> None:
    """Una fila por cada una de las siete tablas nuevas de este change (más
    `intento_login`, grupo 11), con relaciones reales entre sí, para que la
    tarea 14.4 ejerza el downgrade/upgrade contra una base CON datos, no
    vacía: un `DROP TABLE` con el orden de FK equivocado en un `downgrade`
    solo se manifiesta si hay filas y restricciones que atravesar, nunca
    contra un esquema vacío."""
    from datetime import UTC, datetime
    from uuid import uuid4

    engine = create_engine(database_url)
    momento = datetime(2026, 1, 1, tzinfo=UTC)
    organizacion_id = uuid4()
    rol_id = uuid4()
    usuario_id = uuid4()
    dispositivo_id = uuid4()
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org 14.4', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {"id": organizacion_id, "slug": f"org-144-{organizacion_id}", "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO rol "
                    "(id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
                    "actualizado_en, actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Rol 14.4', 0.100000, true, :momento, "
                    ":momento, NULL)"
                ),
                {"id": rol_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
                    "VALUES (:organizacion_id, :rol_id, 'VENDER')"
                ),
                {"organizacion_id": organizacion_id, "rol_id": rol_id},
            )
            conexion.execute(
                text(
                    "INSERT INTO usuario "
                    "(id, organizacion_id, usuario, nombre, email, password_hash, rol_id, "
                    "tope_descuento_override, estado, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'usuario144', 'Usuario 14.4', NULL, "
                    "'hash-de-prueba', :rol_id, NULL, 'ACTIVO', :momento, :momento, NULL)"
                ),
                {
                    "id": usuario_id,
                    "organizacion_id": organizacion_id,
                    "rol_id": rol_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO dispositivo "
                    "(id, organizacion_id, nombre, prefijo, ultimo_correlativo, estado, "
                    "revocado_en, revocado_por_id, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Dispositivo 14.4', 'V01', 0, 'ACTIVO', "
                    "NULL, NULL, :momento, :momento, NULL)"
                ),
                {"id": dispositivo_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO sesion_refresh "
                    "(id, organizacion_id, usuario_id, dispositivo_id, token_hash, familia_id, "
                    "emitido_en, expira_en, usado_en, revocado_en, motivo_revocacion) "
                    "VALUES (:id, :organizacion_id, :usuario_id, :dispositivo_id, "
                    "'hash-de-refresh-de-prueba', :familia_id, :momento, :momento, NULL, "
                    "NULL, NULL)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "familia_id": uuid4(),
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO auditoria "
                    "(id, organizacion_id, usuario_id, dispositivo_id, accion, entidad, "
                    "entidad_id, antes, despues, motivo_id, observacion, autorizador_id, "
                    "operation_id, occurred_at, registered_at) "
                    "VALUES (:id, :organizacion_id, :usuario_id, :dispositivo_id, "
                    "'INICIO_SESION', 'usuario', NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
                    ":momento, :momento)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO intento_login (id, usuario_id, ip, exito, creado_en) "
                    "VALUES (:id, :usuario_id, '127.0.0.1', true, :momento)"
                ),
                {"id": uuid4(), "usuario_id": usuario_id, "momento": momento},
            )
    finally:
        engine.dispose()


def test_downgrade_y_upgrade_corren_limpios_con_datos_representativos(
    database_url: str,
) -> None:
    """Tarea 14.4 (`04` §2.1, criterio 4): `upgrade head` -> `downgrade
    base` -> `upgrade head` sobre una base CON datos, no vacía, sembrando
    una fila real en cada una de las siete tablas nuevas de este change
    (más `intento_login`) con sus relaciones entre sí, para que un `DROP
    TABLE`/`DROP CONSTRAINT` en el orden equivocado del `downgrade` no
    pueda esconderse detrás de un esquema sin filas ni FKs que atravesar.
    """
    _crear_roles_de_base(database_url)

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    _sembrar_datos_representativos(database_url)

    resultado_down = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    # El catálogo de permisos (sincronizado por migración, tarea 4.2) volvió
    # a poblarse desde cero tras el downgrade -- la migración de catálogo no
    # depende de un estado previo, corre limpia sobre la base recién creada.
    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            cantidad_permisos = conexion.execute(text("SELECT count(*) FROM permiso")).scalar_one()
            # La organización sembrada antes del downgrade no sobrevive: un
            # downgrade a `base` borra las tablas, y con ellas sus filas.
            # Esto es la pérdida de datos ESPERADA de un downgrade completo,
            # no la "inesperada" que pide descartar la tarea 14.4 (que se
            # refiere a errores o corrupción durante el propio ciclo, no a
            # que un downgrade total dilapide lo que había).
            cantidad_organizaciones = conexion.execute(
                text("SELECT count(*) FROM organizacion")
            ).scalar_one()
    finally:
        engine.dispose()

    assert cantidad_permisos == 39
    assert cantidad_organizaciones == 0

    # Deja la base en `head`, compartida con el resto de la sesión de pytest.
    resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_final.returncode == 0, resultado_up_final.stderr


def test_alembic_corre_como_app_migrations_no_como_app_runtime(database_url: str) -> None:
    """Tarea 1.5: confirma que Alembic efectivamente usó `DATABASE_URL_MIGRATIONS`
    (rol `app_migrations`) para correr, no una URL con otro rol: las tablas
    que crea quedan de su propiedad."""
    _crear_roles_de_base(database_url)
    resultado = _alembic("upgrade", "head", database_url=database_url)
    assert resultado.returncode == 0, resultado.stderr

    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            dueno = conexion.execute(
                text("SELECT tableowner FROM pg_tables WHERE tablename = 'auditoria'")
            ).scalar_one()
    finally:
        engine.dispose()

    assert dueno == NOMBRE_ROL_MIGRACIONES
