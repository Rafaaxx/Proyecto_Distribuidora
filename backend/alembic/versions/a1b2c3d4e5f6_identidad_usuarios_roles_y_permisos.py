"""identidad: usuarios, roles, permisos, dispositivos, sesiones y auditoria

Revision ID: a1b2c3d4e5f6
Revises: 568672139155
Create Date: 2026-09-19 00:00:00.000000

Crea las siete tablas de `03` §4 y §13 (change 03): `permiso` (catálogo
global, sin `organizacion_id`, D7), `rol`, `usuario`, `rol_permiso`,
`dispositivo`, `sesion_refresh` y `auditoria`.

Otorga en la misma revisión (`design.md` D3, `ADR-020`) los permisos del rol
`app_runtime` tabla por tabla: `SELECT, INSERT, UPDATE` en las tablas
maestras (`rol`, `usuario`, `dispositivo`), `SELECT` únicamente en el
catálogo global `permiso` (no editable desde la aplicación, `03` §17),
`SELECT, INSERT, DELETE` en la relación `rol_permiso` (agregar/quitar un
permiso de un rol es alta/baja, no hay columnas para actualizar),
`SELECT, INSERT, UPDATE` en `sesion_refresh` (se marca usada/revocada, nunca
se borra) y **solo** `SELECT, INSERT` en `auditoria` (tabla de libro, INV-05).

También otorga (retroactivo, tarea 1.2: "ninguna tabla queda sin permisos
declarados") `SELECT, INSERT, UPDATE` a `app_runtime` sobre las cinco tablas
maestras creadas en el change 02 (`organizacion`, `configuracion_organizacion`,
`alicuota_iva`, `medio_pago`, `motivo`), que no tenían ningún `GRANT` porque
el rol `app_runtime` no existía todavía. Necesario para que la verificación
comprensiva de INV-05 (tarea 1.2) no falle sobre tablas anteriores a este
change; no es una decisión de negocio nueva, es la aplicación mecánica de la
clasificación de `ADR-020` a tablas ya existentes.

`auditoria.operation_id` queda nulable hasta el change 04 (nada lo genera
todavía): el change 04 lo hace obligatorio (tarea 2.6).

Deuda anotada (mismo patrón que `568672139155`, D3 de esa migración):
`rol.actualizado_por_id` y `dispositivo.actualizado_por_id` referencian
`usuario`, que se crea en esta misma migración después que `rol`; sus Fks se
agregan con `op.create_foreign_key` una vez que `usuario` existe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "568672139155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_TABLAS_MAESTRAS_EXISTENTES = (
    "organizacion",
    "configuracion_organizacion",
    "alicuota_iva",
    "medio_pago",
    "motivo",
)


def upgrade() -> None:
    """Upgrade schema."""
    # --- permiso (catálogo global, D7) -------------------------------
    op.create_table(
        "permiso",
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("modulo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("codigo", name="pk_permiso"),
    )

    # --- rol -----------------------------------------------------------
    op.create_table(
        "rol",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tope_descuento", sa.Numeric(9, 6), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        # Sin FK todavia: `usuario` no existe hasta mas abajo en esta misma
        # migracion (ver docstring del modulo).
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_rol"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_rol__organizacion"
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_rol__org_id"),
        sa.CheckConstraint(
            "tope_descuento >= 0 AND tope_descuento <= 1", name="ck_rol__tope_descuento"
        ),
    )

    # --- usuario ---------------------------------------------------------
    op.create_table(
        "usuario",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("usuario", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("tope_descuento_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("pin_autorizacion_hash", sa.Text(), nullable=True),
        sa.Column("pin_autorizacion_sal", sa.Text(), nullable=True),
        sa.Column("pin_autorizacion_iteraciones", sa.Integer(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_usuario"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_usuario__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "rol_id"],
            ["rol.organizacion_id", "rol.id"],
            name="fk_usuario__rol",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_usuario__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_usuario__org_id"),
        sa.UniqueConstraint("organizacion_id", "usuario", name="ux_usuario__org_usuario"),
        sa.CheckConstraint("estado IN ('ACTIVO', 'INACTIVO')", name="ck_usuario__estado"),
        sa.CheckConstraint(
            "tope_descuento_override IS NULL "
            "OR (tope_descuento_override >= 0 AND tope_descuento_override <= 1)",
            name="ck_usuario__tope_descuento_override",
        ),
    )

    # Ahora que `usuario` existe, se completa la FK pendiente de `rol`.
    op.create_foreign_key(
        "fk_rol__actualizado_por",
        "rol",
        "usuario",
        ["organizacion_id", "actualizado_por_id"],
        ["organizacion_id", "id"],
    )

    # --- rol_permiso (D7: FK simple hacia el catalogo global) -----------
    op.create_table(
        "rol_permiso",
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("permiso_codigo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "organizacion_id", "rol_id", "permiso_codigo", name="pk_rol_permiso"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "rol_id"],
            ["rol.organizacion_id", "rol.id"],
            name="fk_rol_permiso__rol",
        ),
        sa.ForeignKeyConstraint(
            ["permiso_codigo"], ["permiso.codigo"], name="fk_rol_permiso__permiso"
        ),
    )

    # --- dispositivo -------------------------------------------------
    op.create_table(
        "dispositivo",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("prefijo", sa.Text(), nullable=False),
        sa.Column("ultimo_correlativo", sa.Integer(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("revocado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocado_por_id", sa.Uuid(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_dispositivo"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_dispositivo__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "revocado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_dispositivo__revocado_por",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_dispositivo__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_dispositivo__org_id"),
        sa.UniqueConstraint("organizacion_id", "prefijo", name="ux_dispositivo__org_prefijo"),
        sa.CheckConstraint("estado IN ('ACTIVO', 'REVOCADO')", name="ck_dispositivo__estado"),
    )

    # --- sesion_refresh --------------------------------------------------
    op.create_table(
        "sesion_refresh",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("familia_id", sa.Uuid(), nullable=False),
        sa.Column("emitido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revocacion", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sesion_refresh"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_sesion_refresh__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_sesion_refresh__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_sesion_refresh__dispositivo",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_sesion_refresh__org_id"),
    )
    op.create_index("ix_sesion_refresh__token_hash", "sesion_refresh", ["token_hash"], unique=True)

    # --- auditoria (tabla de libro, INV-05) -------------------------------
    op.create_table(
        "auditoria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=True),
        sa.Column("accion", sa.Text(), nullable=False),
        sa.Column("entidad", sa.Text(), nullable=False),
        sa.Column("entidad_id", sa.Uuid(), nullable=True),
        sa.Column("antes", JSONB(), nullable=True),
        sa.Column("despues", JSONB(), nullable=True),
        sa.Column("motivo_id", sa.Uuid(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("autorizador_id", sa.Uuid(), nullable=True),
        # Nulable hasta el change 04 (tarea 2.6): nada lo genera todavia.
        # El change 04 lo hace obligatorio.
        sa.Column("operation_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_auditoria__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_auditoria__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_auditoria__dispositivo",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "autorizador_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_auditoria__autorizador",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_auditoria__org_id"),
    )

    # --- Permisos de app_runtime (design.md D3, ADR-020) -----------------
    op.execute(f"GRANT SELECT ON permiso TO {ROL_RUNTIME}")
    for tabla in ("rol", "usuario", "dispositivo"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabla} TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON rol_permiso TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON sesion_refresh TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT ON auditoria TO {ROL_RUNTIME}")  # INV-05: sin UPDATE/DELETE

    # Retroactivo sobre las tablas maestras del change 02 (ver docstring).
    for tabla in _TABLAS_MAESTRAS_EXISTENTES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabla} TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    for tabla in _TABLAS_MAESTRAS_EXISTENTES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {tabla} FROM {ROL_RUNTIME}")

    op.drop_table("auditoria")
    op.drop_index("ix_sesion_refresh__token_hash", table_name="sesion_refresh")
    op.drop_table("sesion_refresh")
    op.drop_table("dispositivo")
    op.drop_table("rol_permiso")
    op.drop_constraint("fk_rol__actualizado_por", "rol", type_="foreignkey")
    op.drop_table("usuario")
    op.drop_table("rol")
    op.drop_table("permiso")
