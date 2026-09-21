"""INV-05 (`docs/01-dominio.md` §20; `docs/03-modelo-de-datos.md` §2.5;
`ADR-020`): las tablas de libro son de solo inserción y el usuario de
aplicación (`app_runtime`) no tiene `UPDATE` ni `DELETE` sobre ellas -- una
propiedad de la base, no del código, verificada por prueba (`design.md` D3).

Tareas 1.1, 1.2, 1.3.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import NOMBRE_ROL_RUNTIME, aplicar_migraciones
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

# Lista explícita y enumerable (mismo criterio que el ratchet de rutas del
# change 02 y la exención de catálogo global de la tarea 3.1): las tablas de
# libro declaradas hasta este change. `cuenta_movimiento`, `stock_movimiento`
# y `costo_producto_mov` llegan con changes posteriores y se agregan acá
# cuando existan.
TABLAS_DE_LIBRO_DECLARADAS = frozenset({"auditoria", "intento_login"})

# Tablas de sistema que Alembic administra y que no son de negocio: no
# reciben grants de `app_runtime` (no las consulta la aplicación).
TABLAS_DE_SISTEMA = frozenset({"alembic_version"})

_PRIVILEGIOS_POR_TABLA = text(
    """
    SELECT table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE grantee = :rol AND table_schema = 'public'
    """
)

_TODAS_LAS_TABLAS = text(
    """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """
)


def _privilegios_de_app_runtime(engine: Engine) -> dict[str, set[str]]:
    """`{tabla: {privilegios otorgados a app_runtime}}`. Una tabla sin fila
    en `information_schema.role_table_grants` para `app_runtime` no aparece
    en el resultado (así se detecta el olvido de un `GRANT`)."""
    resultado: dict[str, set[str]] = {}
    with engine.connect() as conexion:
        for tabla, privilegio in conexion.execute(
            _PRIVILEGIOS_POR_TABLA, {"rol": NOMBRE_ROL_RUNTIME}
        ).all():
            resultado.setdefault(tabla, set()).add(privilegio)
    return resultado


def test_inv05_app_runtime_no_puede_actualizar_una_tabla_de_libro(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no puede modificar un registro de
    auditoría". Cita INV-05."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
    ):
        conexion.execute(text("UPDATE auditoria SET accion = 'x' WHERE false"))


def test_inv05_app_runtime_no_puede_borrar_una_tabla_de_libro(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no puede borrar un registro de auditoría".
    Cita INV-05."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
    ):
        conexion.execute(text("DELETE FROM auditoria WHERE false"))


def test_inv05_app_runtime_si_puede_insertar_y_leer_una_tabla_de_libro(
    database_url: str, app_runtime_engine: Engine, _engine_de_sesion: Engine
) -> None:
    """Escenario "La aplicación sí puede insertar y leer": contraparte
    positiva de los dos rechazos de arriba -- `app_runtime` sí puede
    insertar un registro de auditoría y volver a leerlo, cita AUD-01/INV-05."""
    import uuid
    from datetime import UTC, datetime

    aplicar_migraciones(database_url)
    organizacion_id = uuid.uuid4()
    auditoria_id = uuid.uuid4()
    momento = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org de prueba INV-05', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {"id": organizacion_id, "slug": f"inv05-{organizacion_id}", "momento": momento},
            )

        with app_runtime_engine.connect() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO auditoria "
                    "(id, organizacion_id, usuario_id, dispositivo_id, accion, entidad, "
                    "entidad_id, antes, despues, motivo_id, observacion, autorizador_id, "
                    "operation_id, occurred_at, registered_at) "
                    "VALUES (:id, :organizacion_id, NULL, NULL, 'PRUEBA_INV05', 'auditoria', "
                    "NULL, NULL, NULL, NULL, NULL, NULL, NULL, :momento, :momento)"
                ),
                {"id": auditoria_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.commit()

            fila = conexion.execute(
                text("SELECT accion FROM auditoria WHERE id = :id"), {"id": auditoria_id}
            ).one()
            assert fila.accion == "PRUEBA_INV05"
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM auditoria WHERE id = :id"), {"id": auditoria_id})
            conexion.execute(
                text("DELETE FROM organizacion WHERE id = :id"), {"id": organizacion_id}
            )


def test_inv05_ninguna_tabla_de_libro_tiene_update_ni_delete_para_app_runtime(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Escenario "Toda tabla de libro tiene sus permisos restringidos"."""
    privilegios = _privilegios_de_app_runtime(_engine_de_sesion)

    errores = [
        f"'{tabla}' declarada de libro pero app_runtime tiene "
        f"{privilegios.get(tabla, set()) & {'UPDATE', 'DELETE'}}"
        for tabla in TABLAS_DE_LIBRO_DECLARADAS
        if privilegios.get(tabla, set()) & {"UPDATE", "DELETE"}
    ]
    assert errores == [], errores


def test_inv05_ninguna_tabla_queda_sin_permisos_declarados(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Escenario "Toda tabla de libro tiene sus permisos restringidos"
    (parte "ninguna tabla queda sin permisos declarados", ADR-020: "si se
    agrega una tabla nueva y se olvida el GRANT... CI falla")."""
    with _engine_de_sesion.connect() as conexion:
        todas = {fila[0] for fila in conexion.execute(_TODAS_LAS_TABLAS).all()}
    tablas_de_negocio = todas - TABLAS_DE_SISTEMA

    privilegios = _privilegios_de_app_runtime(_engine_de_sesion)
    sin_permisos = sorted(tabla for tabla in tablas_de_negocio if tabla not in privilegios)
    assert sin_permisos == [], f"Tablas sin GRANT para app_runtime: {sin_permisos}"


def test_inv05_app_runtime_no_puede_alterar_la_estructura(
    database_url: str, app_runtime_engine: Engine
) -> None:
    """Escenario "La aplicación no es dueña del esquema": `app_runtime` no
    puede alterar la estructura de una tabla."""
    aplicar_migraciones(database_url)

    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(ProgrammingError, match="(?i)must be owner"),
    ):
        conexion.execute(text("ALTER TABLE auditoria ADD COLUMN columna_intrusa text"))


# --- Verificación en negativo (tarea 1.2) -----------------------------------


@pytest.fixture
def _tabla_temporal_mal_otorgada(database_url: str, _engine_de_sesion: Engine) -> Iterator[Engine]:
    """Una tabla real con `UPDATE` y `DELETE` otorgados a `app_runtime` a
    propósito, para probar que la verificación de la tarea 1.1/1.2
    efectivamente detecta el caso que dice detectar."""
    aplicar_migraciones(database_url)
    with _engine_de_sesion.connect() as conexion:
        conexion.execute(text("CREATE TABLE inv05_negativo_mal_otorgada (id uuid PRIMARY KEY)"))
        conexion.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON inv05_negativo_mal_otorgada "
                f"TO {NOMBRE_ROL_RUNTIME}"
            )
        )
        conexion.commit()
    try:
        yield _engine_de_sesion
    finally:
        with _engine_de_sesion.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS inv05_negativo_mal_otorgada"))
            conexion.commit()


def test_inv05_detecta_una_tabla_de_libro_mal_otorgada(
    _tabla_temporal_mal_otorgada: Engine,
) -> None:
    privilegios = _privilegios_de_app_runtime(_tabla_temporal_mal_otorgada)
    tablas_de_libro_bajo_prueba = TABLAS_DE_LIBRO_DECLARADAS | {"inv05_negativo_mal_otorgada"}

    errores = [
        tabla
        for tabla in tablas_de_libro_bajo_prueba
        if privilegios.get(tabla, set()) & {"UPDATE", "DELETE"}
    ]
    assert "inv05_negativo_mal_otorgada" in errores
