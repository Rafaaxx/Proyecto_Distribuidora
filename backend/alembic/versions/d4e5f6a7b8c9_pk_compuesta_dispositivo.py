"""identidad: PK compuesta de dispositivo

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-19 00:30:00.000000

Corrige la clave primaria de `dispositivo`: pasa de `PRIMARY KEY (id)` a
`PRIMARY KEY (organizacion_id, id)`.

`03` §4 dice explícitamente que `dispositivo.id` es "generado por el
dispositivo" (el cliente lo crea antes del primer login y lo guarda en
IndexedDB, `02` §12.2), no por el servidor con `core/ids.py`. Con `id` como
único componente de la clave primaria, el mismo valor no podía repetirse
entre organizaciones -- pero la spec `identidad/dispositivos` exige
exactamente eso: "Un identificador de dispositivo de otra organización no
se reutiliza: se registra un dispositivo nuevo en la organización B" (con
el MISMO identificador que el de la organización A). Solo es posible si la
clave primaria incluye `organizacion_id`, igual que el resto de las tablas
de negocio (`03` §2.4: `UNIQUE (organizacion_id, id)` -- acá, directamente
como clave primaria, porque `id` por sí solo ya no alcanza para ser único).

La `UNIQUE (organizacion_id, id)` (`ux_dispositivo__org_id`) se conserva tal
cual, aunque quede redundante con la nueva clave primaria: las FK
compuestas hacia `dispositivo` (`fk_sesion_refresh__dispositivo`,
`fk_auditoria__dispositivo`) ya la usan como respaldo, y borrarla exige
recrearlas -- más riesgo que el de dejar un índice único de más.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("pk_dispositivo", "dispositivo", type_="primary")
    op.create_primary_key("pk_dispositivo", "dispositivo", ["organizacion_id", "id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("pk_dispositivo", "dispositivo", type_="primary")
    op.create_primary_key("pk_dispositivo", "dispositivo", ["id"])
