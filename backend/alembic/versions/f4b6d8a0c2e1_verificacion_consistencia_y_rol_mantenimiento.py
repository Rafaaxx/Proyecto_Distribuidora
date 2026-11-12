"""verificacion de consistencia: tabla `verificacion_consistencia` y permisos del rol
`app_mantenimiento`

Revision ID: f4b6d8a0c2e1
Revises: e3a5c7d9f1b2
Create Date: 2026-11-10 12:00:00.000000

Change 28 (`design.md` D3, D5; ADR-018, ADR-020, `03` §2.5), una sola revision:

- `verificacion_consistencia` (D5): el resultado de cada corrida diaria de la verificacion de
  saldos contra sus libros, por organizacion. `resultado` en (`SIN_DIFERENCIAS`,
  `CON_DIFERENCIAS`), `diferencias` `jsonb` con identificadores e importes como texto, `FK`
  a `organizacion` e indice por organizacion y momento (el aviso lee el ultimo de cada una).
  De solo insercion: la escribe el servicio `tareas`, que no es una operacion de negocio (no la
  origina un usuario, no tiene `operation_id`, no cambia ningun dato del negocio), igual que el
  `INSERT` de `intento_login` del login.
- `app_runtime` (INV-05): solo `SELECT` de `verificacion_consistencia` (el endpoint del aviso).
- `app_mantenimiento` (D3): `USAGE` del esquema; `SELECT` de las tablas que compara la
  verificacion (`organizacion`, `saldo_cuenta`, `cuenta_movimiento`, `stock_saldo`,
  `stock_movimiento`, `costo_producto`, `costo_producto_mov`); `INSERT, SELECT` de
  `verificacion_consistencia`; `SELECT, DELETE` de `intento_login` (la limpieza de los de mas de
  24 horas, ADR-018 / ADR-057 punto 9). Nada mas: no puede insertar, modificar ni borrar en
  ninguna otra tabla.

El rol NO lo crea esta migracion: lo crea el script de inicializacion del volumen
(`infra/postgres/30-init-mantenimiento-role.sh`) o, en un entorno ya en uso, el paso del runbook
«Crear el rol de mantenimiento» (`docs/runbook/puesta-en-marcha.md`), antes de migrar. Si no
existe, la migracion FALLA al empezar, sin tocar nada, nombrando ese paso (`CLAUDE.md` §4: nada se
saltea en silencio).

`downgrade` quita los permisos del rol y la tabla. **Pierde por diseno** los resultados de
verificaciones guardados (son derivados: la corrida siguiente los regenera); no toca ningun dato
del negocio. No exige que el rol exista: si ya no esta, no hay permisos que quitar.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b6d8a0c2e1"
down_revision: str | Sequence[str] | None = "e3a5c7d9f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"
ROL_MANTENIMIENTO = "app_mantenimiento"

LEIDAS_POR_LA_VERIFICACION = (
    "organizacion",
    "saldo_cuenta",
    "cuenta_movimiento",
    "stock_saldo",
    "stock_movimiento",
    "costo_producto",
    "costo_producto_mov",
)


def _el_rol_existe() -> bool:
    return (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :rol"), {"rol": ROL_MANTENIMIENTO})
        .scalar()
        is not None
    )


def upgrade() -> None:
    """Upgrade schema."""
    if not _el_rol_existe():
        raise RuntimeError(
            f"Falta el rol de base de datos '{ROL_MANTENIMIENTO}': esta migracion le otorga "
            "permisos y no lo crea. Creelo antes de migrar siguiendo el paso «Crear el rol de "
            "mantenimiento» de docs/runbook/puesta-en-marcha.md (un volumen nuevo lo crea solo "
            "con infra/postgres/30-init-mantenimiento-role.sh) y vuelva a correr las migraciones."
        )

    op.create_table(
        "verificacion_consistencia",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("ejecutada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=False),
        sa.Column("diferencias", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_verificacion_consistencia"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_verificacion_consistencia__organizacion",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_verificacion_consistencia__org_id"),
        sa.CheckConstraint(
            "resultado IN ('SIN_DIFERENCIAS', 'CON_DIFERENCIAS')",
            name="ck_verificacion_consistencia__resultado",
        ),
    )
    op.create_index(
        "ix_verificacion_consistencia__org_ejecutada_en",
        "verificacion_consistencia",
        ["organizacion_id", sa.text("ejecutada_en DESC")],
    )

    op.execute(f"GRANT SELECT ON verificacion_consistencia TO {ROL_RUNTIME}")

    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROL_MANTENIMIENTO}")
    for tabla in LEIDAS_POR_LA_VERIFICACION:
        op.execute(f"GRANT SELECT ON {tabla} TO {ROL_MANTENIMIENTO}")
    op.execute(f"GRANT INSERT, SELECT ON verificacion_consistencia TO {ROL_MANTENIMIENTO}")
    op.execute(f"GRANT SELECT, DELETE ON intento_login TO {ROL_MANTENIMIENTO}")


def downgrade() -> None:
    """Downgrade schema."""
    if _el_rol_existe():
        op.execute(f"REVOKE SELECT, DELETE ON intento_login FROM {ROL_MANTENIMIENTO}")
        op.execute(f"REVOKE INSERT, SELECT ON verificacion_consistencia FROM {ROL_MANTENIMIENTO}")
        for tabla in LEIDAS_POR_LA_VERIFICACION:
            op.execute(f"REVOKE SELECT ON {tabla} FROM {ROL_MANTENIMIENTO}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROL_MANTENIMIENTO}")

    op.execute(f"REVOKE SELECT ON verificacion_consistencia FROM {ROL_RUNTIME}")
    op.drop_index(
        "ix_verificacion_consistencia__org_ejecutada_en", table_name="verificacion_consistencia"
    )
    op.drop_table("verificacion_consistencia")
