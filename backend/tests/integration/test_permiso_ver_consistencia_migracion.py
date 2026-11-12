"""Tarea 3.0 (change 28): la revisión `a5c7e9b1d3f4` da de alta el permiso `VER_CONSISTENCIA`
y lo asigna, por nombre, a los roles de plantilla de las organizaciones existentes que lo
incluyen en `PLANTILLAS_DE_ROL` (`design.md` D5, Q2; mismo precedente que `ANULAR_TRANSFERENCIA`,
revisión `f3a4b5c6d7e8`).

Consulta el esquema REAL de PostgreSQL migrado.

Reglas citadas: SEG-06, INV-01 (el `downgrade` no toca datos del negocio), INV-21.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from uuid import UUID, uuid4

from conftest import BACKEND_DIR
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from test_jornadas_migracion import _dejar_en_head
from test_transferencias_ajustes_migracion import _alembic

REVISION = "a5c7e9b1d3f4"
REVISION_ANTERIOR = "f4b6d8a0c2e1"  # la verificación de consistencia, previa a esta revisión.
PERMISO = "VER_CONSISTENCIA"
MOMENTO = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
CON_EL_PERMISO = {"Administrador", "Administración"}


def _crear_rol(sesion: Session, organizacion_id: UUID, nombre: str) -> None:
    sesion.execute(
        text(
            "INSERT INTO rol (id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, :nombre, 0, true, :m, :m)"
        ),
        {"id": uuid4(), "org": organizacion_id, "nombre": nombre, "m": MOMENTO},
    )


def _roles_con_el_permiso(motor: Engine, organizacion_id: UUID) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT r.nombre FROM rol_permiso rp JOIN rol r "
                    "ON r.organizacion_id = rp.organizacion_id AND r.id = rp.rol_id "
                    "WHERE rp.organizacion_id = :o AND rp.permiso_codigo = :p"
                ),
                {"o": organizacion_id, "p": PERMISO},
            ).scalars()
        )


def _asignaciones_del_permiso(motor: Engine) -> int:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT count(*) FROM rol_permiso WHERE permiso_codigo = :p"), {"p": PERMISO}
        ).scalar_one()


def _permiso_en_catalogo(motor: Engine) -> list[tuple[str, str]]:
    with motor.connect() as conexion:
        return [
            (f[0], f[1])
            for f in conexion.execute(
                text("SELECT descripcion, modulo FROM permiso WHERE codigo = :p"), {"p": PERMISO}
            ).all()
        ]


def test_la_revision_esta_en_la_cadena_a_continuacion_de_la_verificacion(
    _engine_de_sesion: Engine,
) -> None:
    archivo = next((BACKEND_DIR / "alembic" / "versions").glob(f"{REVISION}_*.py"))
    especificacion = importlib.util.spec_from_file_location("revision_28_permiso", archivo)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)

    assert modulo.revision == REVISION
    assert modulo.down_revision == REVISION_ANTERIOR


def test_el_permiso_queda_en_el_catalogo_con_su_descripcion(_engine_de_sesion: Engine) -> None:
    assert _permiso_en_catalogo(_engine_de_sesion) == [("Ver el aviso de consistencia", "sistema")]


def test_la_migracion_asigna_el_permiso_solo_a_las_plantillas_que_lo_incluyen(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Triangula: una organización completa, una con un rol renombrado (no lo recibe) y una sin
    el rol `Administración`; el `downgrade` borra el permiso con sus asignaciones y volver a
    subir es idempotente."""
    with Session(_engine_de_sesion) as sesion:
        completa = crear_organizacion(sesion).id
        renombrada = crear_organizacion(sesion).id
        sin_administracion = crear_organizacion(sesion).id
        for nombre in (
            "Administrador",
            "Administración",
            "Supervisor comercial",
            "Vendedor/Repartidor",
            "Consulta/Dirección",
            "Rol a medida",
        ):
            _crear_rol(sesion, completa, nombre)
        for nombre in ("Administrador", "Gestión administrativa", "Supervisor comercial"):
            _crear_rol(sesion, renombrada, nombre)
        for nombre in ("Administrador", "Vendedor/Repartidor"):
            _crear_rol(sesion, sin_administracion, nombre)
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _permiso_en_catalogo(_engine_de_sesion) == []
        assert _asignaciones_del_permiso(_engine_de_sesion) == 0

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _roles_con_el_permiso(_engine_de_sesion, completa) == CON_EL_PERMISO
        assert _roles_con_el_permiso(_engine_de_sesion, renombrada) == {"Administrador"}
        assert _roles_con_el_permiso(_engine_de_sesion, sin_administracion) == {"Administrador"}

        # Idempotencia: otro ciclo no duplica asignaciones (la clave de rol_permiso lo impediría).
        total = _asignaciones_del_permiso(_engine_de_sesion)
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert _asignaciones_del_permiso(_engine_de_sesion) == total == 4
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
