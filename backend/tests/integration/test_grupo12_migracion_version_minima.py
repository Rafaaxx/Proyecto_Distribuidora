"""Change 04, grupo 12, tarea 12.4 (`design.md` D9): elimina la columna
huérfana `configuracion_organizacion.app_version_minima`.

Confirmado con grep en `backend/app/`, `frontend/src/` y `backend/tests/`
(seeds/fixtures) antes de esta migración: la columna solo se escribía al
alta de organización (`identidad/service.py::crear_organizacion_con_
configuracion`, `identidad/repository.py::crear_configuracion`), nunca se
leía para ninguna decisión de negocio ni se exponía por `identidad/api.py`.
La versión mínima de aplicación (`02` §6.6) es configuración de despliegue
(`Settings.app_version_minima`), no por organización (`design.md` D9).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def test_la_columna_huerfana_ya_no_existe_en_configuracion_organizacion(
    db_session: Session,
) -> None:
    columnas = (
        db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'configuracion_organizacion'"
            )
        )
        .scalars()
        .all()
    )
    assert "app_version_minima" not in columnas


def test_el_resto_de_las_columnas_de_configuracion_sigue_intacto(db_session: Session) -> None:
    """Triangulación: la migración borra SOLO esa columna, no arrastra
    ninguna otra por error."""
    columnas = set(
        db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'configuracion_organizacion'"
            )
        )
        .scalars()
        .all()
    )
    assert {"organizacion_id", "modo_impositivo", "intentos_pin_max"} <= columnas
