"""identidad: slug de organizacion

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-19 00:20:00.000000

Agrega `organizacion.slug` (`ADR-021`): resuelve la organización en el
login antes de que exista un token, porque `usuario` es único por
`(organizacion_id, usuario)`, no globalmente. `UNIQUE`, obligatorio.

No se agrega `GRANT` nuevo: `organizacion` ya tiene sus permisos de
`app_runtime` otorgados en la migración `568672139155` (change 02).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("organizacion", sa.Column("slug", sa.Text(), nullable=False))
    op.create_unique_constraint("ux_organizacion__slug", "organizacion", ["slug"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ux_organizacion__slug", "organizacion", type_="unique")
    op.drop_column("organizacion", "slug")
