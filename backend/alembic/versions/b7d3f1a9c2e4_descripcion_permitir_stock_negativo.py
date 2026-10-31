"""identidad: descripcion corta de PERMITIR_STOCK_NEGATIVO

Revision ID: b7d3f1a9c2e4
Revises: a9c1e3f5b7d2
Create Date: 2026-10-31 00:00:00.000000

Change 22a (ADR-063 punto 7, decision del usuario 2026-10-31): la descripcion del permiso pasa
de "Operar con stock negativo online" a "Operar con stock negativo" (etiqueta corta de la
pantalla de Roles); el detalle de que tambien rige en el telefono sin conexion vive en `01`
STK-06. El catalogo se inserta con `ON CONFLICT DO NOTHING` (`b2c3d4e5f6a7`), asi que las bases
ya migradas conservan el texto viejo: esta revision lo actualiza. `permiso` es un catalogo
global, sin `organizacion_id`. `downgrade` restaura el texto anterior.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3f1a9c2e4"
down_revision: str | Sequence[str] | None = "a9c1e3f5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODIGO = "PERMITIR_STOCK_NEGATIVO"
_DESCRIPCION_ANTERIOR = "Operar con stock negativo online"
_DESCRIPCION_NUEVA = "Operar con stock negativo"


def _actualizar(descripcion: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE permiso SET descripcion = :descripcion WHERE codigo = :codigo"),
        {"descripcion": descripcion, "codigo": _CODIGO},
    )


def upgrade() -> None:
    _actualizar(_DESCRIPCION_NUEVA)


def downgrade() -> None:
    _actualizar(_DESCRIPCION_ANTERIOR)
