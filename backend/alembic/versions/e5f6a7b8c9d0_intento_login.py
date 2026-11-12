"""identidad: intento_login (rate limit de login, ADR-018)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 00:00:00.000000

Crea `intento_login` (grupo 11, tarea 11.1): `usuario_id` (nulo si el nombre
de usuario informado no corresponde a ningún usuario), `ip`, `exito` y
`creado_en`, exactamente como fija `ADR-018`.

Decisión de alcance registrada acá porque no es obvia y requiere revisión
humana si se está en desacuerdo (no bloquea el resto del grupo 11, que puede
seguir con esta interpretación): `ADR-018` fija esta tabla SIN
`organizacion_id` -- el límite por IP es, por diseño, transversal a
organizaciones (protege contra enumeración de `organizacion_slug` y fuerza
bruta distribuida entre organizaciones desde un mismo origen), y el límite
por usuario ya identifica unívocamente la fila de `usuario` (que sí tiene
organización) sin necesitar una columna redundante. Esto choca en la letra
con `CLAUDE.md` §4 ("Todo dato de negocio tiene `organizacion_id`") e INV-02
(`docs/01-dominio.md` §20, verificado por
`tests/integration/test_inv02_aislamiento_esquema.py`, que recorre TODAS las
tablas automáticamente). Se resuelve tratando `intento_login` como una tabla
de infraestructura de seguridad transversal, en la misma categoría que el
catálogo global `permiso` (D7): se agrega a `TABLAS_GLOBALES_EXENTAS` en
`test_inv02_aislamiento_esquema.py`. Es una aplicación literal de lo que
`ADR-018` ya fijó, no una decisión de negocio nueva, pero al estirar el
sentido original de esa lista (pensada para catálogos, no logs) queda
señalada para que un humano la revise si no está de acuerdo.

Tabla de solo inserción (INV-05, ADR-020, igual criterio que `auditoria`):
`app_runtime` recibe `SELECT, INSERT` únicamente. Índices por
`(usuario_id, creado_en)` y `(ip, creado_en)` para la consulta de conteo por
ventana deslizante (`creado_en >= now() - interval '15 minutes'`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "intento_login",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("exito", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_intento_login"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_intento_login__usuario"),
    )
    op.create_index(
        "ix_intento_login__usuario_id_creado_en",
        "intento_login",
        ["usuario_id", "creado_en"],
    )
    op.create_index(
        "ix_intento_login__ip_creado_en",
        "intento_login",
        ["ip", "creado_en"],
    )
    op.execute(f"GRANT SELECT, INSERT ON intento_login TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT ON intento_login FROM {ROL_RUNTIME}")
    op.drop_index("ix_intento_login__ip_creado_en", table_name="intento_login")
    op.drop_index("ix_intento_login__usuario_id_creado_en", table_name="intento_login")
    op.drop_table("intento_login")
