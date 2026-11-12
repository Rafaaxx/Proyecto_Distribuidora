"""Tarea 2.9 (INV-05, `docs/01-dominio.md` §20; `design.md`, Migration Plan;
`ADR-020`): `app_runtime` no puede borrar filas de `comando`,
`comando_cuarentena` ni `observacion` -- las tres son tablas de libro: el
estado de `comando` pasa de intermedio a final con `UPDATE`, nunca se borra;
`comando_cuarentena` y `observacion` (resuelta por el change 25) tampoco.

Escenarios "La aplicación no puede borrar un registro de cuarentena" y "La
aplicación no puede borrar una observación", más la contraparte de
`comando` por completitud (el mismo criterio que ya cubre `test_inv05_dos_
roles.py` para `auditoria` e `intento_login`).
"""

from __future__ import annotations

import pytest
from conftest import aplicar_migraciones
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError


def test_inv05_app_runtime_no_puede_borrar_un_comando(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no puede borrar un comando". Cita INV-05."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
    ):
        conexion.execute(text("DELETE FROM comando WHERE false"))


def test_inv05_app_runtime_no_puede_borrar_un_registro_de_cuarentena(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no puede borrar un registro de cuarentena".
    Cita INV-05."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
    ):
        conexion.execute(text("DELETE FROM comando_cuarentena WHERE false"))


def test_inv05_app_runtime_no_puede_borrar_una_observacion(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no puede borrar una observación". Cita
    INV-05."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
    ):
        conexion.execute(text("DELETE FROM observacion WHERE false"))


# --- Contraparte positiva: app_runtime SÍ puede UPDATE (a diferencia de
# `auditoria`, estas tres tablas admiten actualizar su estado) ------------


def test_inv05_app_runtime_si_puede_actualizar_el_estado_de_un_comando(
    database_url: str, app_runtime_engine: Engine, _engine_de_sesion: Engine
) -> None:
    """Contraparte positiva: `comando` pasa de `PROCESANDO` a un estado
    final con `UPDATE`, permitido a propósito (a diferencia de `DELETE`)."""
    import uuid
    from datetime import UTC, datetime

    aplicar_migraciones(database_url)
    organizacion_id = uuid.uuid4()
    usuario_id = uuid.uuid4()
    dispositivo_id = uuid.uuid4()
    comando_id = uuid.uuid4()
    rol_id = uuid.uuid4()
    momento = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org de prueba INV-05 comando', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {
                    "id": organizacion_id,
                    "slug": f"inv05-comando-{organizacion_id}",
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO rol "
                    "(id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
                    "actualizado_en, actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Rol prueba 2', 0, true, :momento, "
                    ":momento, NULL)"
                ),
                {"id": rol_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO usuario "
                    "(id, organizacion_id, usuario, nombre, email, password_hash, rol_id, "
                    "tope_descuento_override, estado, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'usuario-inv05-comando', 'Usuario', NULL, "
                    "'hash', :rol_id, NULL, 'ACTIVO', :momento, :momento, NULL)"
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
                    "VALUES (:id, :organizacion_id, 'Dispositivo prueba', 'Z09', 0, 'ACTIVO', "
                    "NULL, NULL, :momento, :momento, NULL)"
                ),
                {"id": dispositivo_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO comando "
                    "(id, organizacion_id, operation_id, tipo, version, modo, usuario_id, "
                    "dispositivo_id, jornada_id, secuencia, huella, app_version, estado, "
                    "resultado, error_codigo, occurred_at, registered_at) "
                    "VALUES (:id, :organizacion_id, :operation_id, 'PRUEBA_INV05', 1, "
                    "'ONLINE', :usuario_id, :dispositivo_id, NULL, 1, 'huella', '1.0.0', "
                    "'PROCESANDO', NULL, NULL, :momento, :momento)"
                ),
                {
                    "id": comando_id,
                    "organizacion_id": organizacion_id,
                    "operation_id": uuid.uuid4(),
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "momento": momento,
                },
            )

        with app_runtime_engine.begin() as conexion:
            conexion.execute(
                text(
                    "UPDATE comando SET estado = 'ACEPTADO' WHERE id = :id AND "
                    "organizacion_id = :organizacion_id"
                ),
                {"id": comando_id, "organizacion_id": organizacion_id},
            )

        with _engine_de_sesion.connect() as conexion:
            estado = conexion.execute(
                text("SELECT estado FROM comando WHERE id = :id"), {"id": comando_id}
            ).scalar_one()
            assert estado == "ACEPTADO"
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM comando WHERE id = :id"), {"id": comando_id})
            conexion.execute(text("DELETE FROM dispositivo WHERE id = :id"), {"id": dispositivo_id})
            conexion.execute(text("DELETE FROM usuario WHERE id = :id"), {"id": usuario_id})
            conexion.execute(
                text("DELETE FROM rol WHERE organizacion_id = :organizacion_id"),
                {"organizacion_id": organizacion_id},
            )
            conexion.execute(
                text("DELETE FROM organizacion WHERE id = :id"), {"id": organizacion_id}
            )
