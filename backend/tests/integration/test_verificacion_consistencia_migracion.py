"""Tarea 1.2 (change 28): la revisión `f4b6d8a0c2e1` crea `verificacion_consistencia`, otorga
`SELECT` a `app_runtime` y `INSERT, SELECT` a `app_mantenimiento`, y le da a `app_mantenimiento`
solo lo que necesitan sus tareas (`SELECT` de los saldos y libros que compara la verificación,
`SELECT` y `DELETE` de `intento_login`). Falla, nombrando el paso del runbook, si el rol no existe
(`design.md` D3, D5; spec `sistema/despliegue` «Migrar sin el rol creado»).

Consulta el esquema REAL de PostgreSQL migrado; que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-01 (la base queda como estaba), INV-02, INV-05, ADR-018, ADR-020.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from conftest import NOMBRE_ROL_MANTENIMIENTO, aplicar_migraciones
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from test_jornadas_migracion import (
    _alembic,
    _columnas,
    _dejar_en_head,
    _indice,
    _privilegios_de_tabla,
    _restricciones,
    _revision_actual,
    _tablas_existentes,
)

REVISION_ANTERIOR = "e3a5c7d9f1b2"  # `revision_de_observaciones_y_rechazos`, previa al change 28.
MOMENTO = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)

COLUMNAS = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "ejecutada_en": ("timestamp with time zone", False),
    "resultado": ("text", False),
    "diferencias": ("jsonb", False),
    "registered_at": ("timestamp with time zone", False),
}
LEIDAS_POR_LA_VERIFICACION = {
    "organizacion",
    "saldo_cuenta",
    "cuenta_movimiento",
    "stock_saldo",
    "stock_movimiento",
    "costo_producto",
    "costo_producto_mov",
}


def _privilegios(motor: Engine, rol: str) -> dict[str, set[str]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE table_schema = 'public' AND grantee = :rol"
            ),
            {"rol": rol},
        ).all()
    resultado: dict[str, set[str]] = {}
    for tabla, privilegio in filas:
        resultado.setdefault(tabla, set()).add(privilegio)
    return resultado


def _insertar_resultado(sesion: Session, organizacion_id: UUID, **cambios: object) -> None:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": organizacion_id,
        "ejecutada_en": MOMENTO,
        "resultado": "SIN_DIFERENCIAS",
        "diferencias": "[]",
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    sesion.execute(
        text(
            "INSERT INTO verificacion_consistencia (id, organizacion_id, ejecutada_en, resultado, "
            "diferencias, registered_at) VALUES (:id, :organizacion_id, :ejecutada_en, "
            ":resultado, CAST(:diferencias AS jsonb), :registered_at)"
        ),
        valores,
    )


def _insertar_intento_de_login(sesion: Session, ip: str) -> None:
    sesion.execute(
        text("INSERT INTO intento_login (id, ip, exito, creado_en) VALUES (:id, :ip, false, :t)"),
        {"id": uuid4(), "ip": ip, "t": MOMENTO},
    )


# --- estructura ------------------------------------------------------------------------------


def test_las_columnas_son_las_del_design(_engine_de_sesion: Engine) -> None:
    assert _columnas(_engine_de_sesion, "verificacion_consistencia") == COLUMNAS


def test_la_organizacion_tiene_clave_foranea_y_el_indice_es_por_organizacion_y_momento(
    _engine_de_sesion: Engine,
) -> None:
    claves = _restricciones(_engine_de_sesion, "verificacion_consistencia", "f")
    assert set(claves) == {"fk_verificacion_consistencia__organizacion"}
    assert "organizacion(id)" in claves["fk_verificacion_consistencia__organizacion"]
    definicion = _indice(_engine_de_sesion, "ix_verificacion_consistencia__org_ejecutada_en")
    assert "(organizacion_id, ejecutada_en" in definicion


def test_inv02_una_organizacion_inexistente_se_rechaza(db_session: Session) -> None:
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_resultado(db_session, uuid4())
    assert "fk_verificacion_consistencia__organizacion" in str(error.value)


@pytest.mark.parametrize("resultado", ["SIN_DIFERENCIAS", "CON_DIFERENCIAS"])
def test_el_resultado_admite_los_dos_valores(db_session: Session, resultado: str) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_resultado(db_session, organizacion.id, resultado=resultado)


@pytest.mark.parametrize("resultado", ["ERROR", "sin_diferencias", ""])
def test_el_resultado_rechaza_un_valor_inventado(db_session: Session, resultado: str) -> None:
    organizacion = crear_organizacion(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_resultado(db_session, organizacion.id, resultado=resultado)
    assert "ck_verificacion_consistencia__resultado" in str(error.value)


# --- permisos (INV-05, D3) -------------------------------------------------------------------


def test_inv05_app_runtime_solo_lee_los_resultados(_engine_de_sesion: Engine) -> None:
    assert _privilegios_de_tabla(_engine_de_sesion, "verificacion_consistencia") == {"SELECT"}


def test_app_mantenimiento_inserta_y_lee_los_resultados_y_nada_mas_en_la_tabla(
    _engine_de_sesion: Engine,
) -> None:
    privilegios = _privilegios(_engine_de_sesion, NOMBRE_ROL_MANTENIMIENTO)
    assert privilegios["verificacion_consistencia"] == {"INSERT", "SELECT"}


def test_app_mantenimiento_lee_lo_que_compara_la_verificacion_y_borra_solo_intentos_de_login(
    _engine_de_sesion: Engine,
) -> None:
    privilegios = _privilegios(_engine_de_sesion, NOMBRE_ROL_MANTENIMIENTO)
    esperados = {tabla: {"SELECT"} for tabla in LEIDAS_POR_LA_VERIFICACION}
    esperados["intento_login"] = {"SELECT", "DELETE"}
    esperados["verificacion_consistencia"] = {"INSERT", "SELECT"}
    assert privilegios == esperados


def test_inv05_la_aplicacion_sigue_sin_borrar_intentos_de_login(
    _engine_de_sesion: Engine,
) -> None:
    assert _privilegios_de_tabla(_engine_de_sesion, "intento_login") == {"SELECT", "INSERT"}


def test_app_mantenimiento_conectado_inserta_un_resultado_y_borra_un_intento(
    database_url: str, _engine_de_sesion: Engine, app_mantenimiento_engine: Engine
) -> None:
    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        _insertar_intento_de_login(sesion, "10.0.0.1")
        sesion.commit()
    try:
        with app_mantenimiento_engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO verificacion_consistencia (id, organizacion_id, ejecutada_en, "
                    "resultado, diferencias, registered_at) VALUES (:id, :o, :t, "
                    "'SIN_DIFERENCIAS', '[]'::jsonb, :t)"
                ),
                {"id": uuid4(), "o": organizacion_id, "t": MOMENTO},
            )
            borradas = conexion.execute(text("DELETE FROM intento_login")).rowcount
        assert borradas >= 1
        with pytest.raises(ProgrammingError), app_mantenimiento_engine.begin() as conexion:
            conexion.execute(text("DELETE FROM verificacion_consistencia"))
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- ciclo y falta del rol -------------------------------------------------------------------


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Sube y baja limpio con una organización y un intento de login: ninguna fila previa cambia
    y la tabla vuelve a existir, vacía (sus resultados se regeneran en la corrida siguiente)."""
    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        _insertar_intento_de_login(sesion, "10.0.0.2")
        _insertar_resultado(sesion, organizacion_id)
        sesion.commit()
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert "verificacion_consistencia" not in _tablas_existentes(_engine_de_sesion)
        assert _privilegios(_engine_de_sesion, NOMBRE_ROL_MANTENIMIENTO) == {}
        with _engine_de_sesion.connect() as c:
            assert c.execute(text("SELECT count(*) FROM intento_login")).scalar_one() == 1
            assert (
                c.execute(
                    text("SELECT count(*) FROM organizacion WHERE id = :o"),
                    {"o": organizacion_id},
                ).scalar_one()
                == 1
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert "verificacion_consistencia" in _tablas_existentes(_engine_de_sesion)
        assert _privilegios(_engine_de_sesion, NOMBRE_ROL_MANTENIMIENTO)["intento_login"] == {
            "SELECT",
            "DELETE",
        }
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_sin_el_rol_la_migracion_falla_nombrando_el_paso_del_runbook_y_no_cambia_nada(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Escenario «Migrar sin el rol creado» (INV-01): un entorno existente donde todavía no se
    creó `app_mantenimiento`. La migración falla con un mensaje que nombra el rol y el paso del
    runbook, y la base queda como estaba."""
    bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
    assert bajada.returncode == 0, bajada.stderr
    with _engine_de_sesion.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f"ALTER ROLE {NOMBRE_ROL_MANTENIMIENTO} RENAME TO rol_ausente_de_prueba"))
    try:
        tablas_antes = _tablas_existentes(_engine_de_sesion)
        fallida = _alembic(database_url, "upgrade", "head")

        assert fallida.returncode != 0
        assert NOMBRE_ROL_MANTENIMIENTO in fallida.stderr
        assert "puesta-en-marcha" in fallida.stderr
        assert "Crear el rol de mantenimiento" in fallida.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert _tablas_existentes(_engine_de_sesion) == tablas_antes
        assert "verificacion_consistencia" not in tablas_antes
    finally:
        with _engine_de_sesion.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(
                text(f"ALTER ROLE rol_ausente_de_prueba RENAME TO {NOMBRE_ROL_MANTENIMIENTO}")
            )
        _dejar_en_head(database_url, _engine_de_sesion)


def test_los_arneses_crean_el_rol_antes_de_migrar(database_url: str) -> None:
    """`aplicar_migraciones` (arnés de integración y de concurrencia) crea `app_mantenimiento`
    igual que lo crea el script de inicialización en un volumen nuevo: con ingreso y sin
    atributos de administración."""
    aplicar_migraciones(database_url)
    motor = create_engine(database_url)
    try:
        with motor.connect() as c:
            fila = c.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles "
                    "WHERE rolname = :r"
                ),
                {"r": NOMBRE_ROL_MANTENIMIENTO},
            ).one()
        assert tuple(fila) == (True, False, False, False)
    finally:
        motor.dispose()
