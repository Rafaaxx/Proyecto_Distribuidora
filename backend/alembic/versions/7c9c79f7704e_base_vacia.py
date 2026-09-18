"""base vacia

Revision ID: 7c9c79f7704e
Revises:
Create Date: 2026-09-18 13:23:38.924301

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7c9c79f7704e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
