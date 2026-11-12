"""elimina configuracion_organizacion.app_version_minima (columna huerfana)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-22 00:00:00.000000

Change 04 (grupo 12, tarea 12.4): elimina la columna huérfana
`configuracion_organizacion.app_version_minima` (creada en la migración
`568672139155_organizacion_y_configuracion.py`, change 01/02).

Motivo exacto: columna huérfana reemplazada por Settings.app_version_minima,
ver design.md D9 del change 04-pipeline-comandos. La versión mínima de
aplicación admitida para confirmar operaciones nuevas (`docs/02-arquitectura.md`
§6.6) es configuración de DESPLIEGUE, no un dato por organización: D9 decide
que vive en `Settings` (variable de entorno `APP_VERSION_MINIMA`), publicada
por `GET /api/v1/version` (`api_v1/sistema.py::VersionRespuesta`).

Confirmado con grep en `backend/app/`, `frontend/src/` y `backend/tests/`
(seeds/fixtures) antes de esta migración (change 04, grupo 12, tarea 12.4):
la columna solo se ESCRIBÍA al alta de organización
(`identidad/service.py::crear_organizacion_con_configuracion`,
`identidad/repository.py::crear_configuracion`, ambos con `app_version_minima:
str | None = None` de default) y nunca se LEÍA para ninguna decisión de
negocio ni se expuso jamás por `identidad/api.py`. Esta misma revisión quita
el parámetro `app_version_minima` de `DatosConfiguracionInicial`
(`identidad/service.py`), `crear_configuracion` (`identidad/repository.py`)
y la columna mapeada de `ConfiguracionOrganizacion` (`identidad/models.py`)
-- si quedara el `mapped_column` sin la columna real, cualquier `SELECT`
sobre `ConfiguracionOrganizacion` fallaría contra la base ya migrada.

`downgrade`: recrea la columna `nullable=True` (estado original, ninguna
fila pierde información distinta de `NULL` porque nunca se le asignó nada
más que el default). No hace falta rellenar datos: la columna vuelve vacía,
igual que nació.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("configuracion_organizacion", "app_version_minima")


def downgrade() -> None:
    op.add_column(
        "configuracion_organizacion",
        sa.Column("app_version_minima", sa.Text(), nullable=True),
    )
