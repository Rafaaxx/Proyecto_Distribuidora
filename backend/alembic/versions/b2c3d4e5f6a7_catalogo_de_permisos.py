"""identidad: catalogo de permisos

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 00:10:00.000000

Sincroniza `permiso` con los 39 permisos de `01` §19
(`app.modules.identidad.domain.permisos.PERMISOS_DEL_CATALOGO`), la fuente
única de esta lista (tarea 4.4: la reusan también las plantillas de rol de
la puesta en marcha, tarea 8.13). `ON CONFLICT (codigo) DO NOTHING`: correrla
de nuevo no duplica (`03` §17, tarea 4.3). El `downgrade` borra por código,
así que revertir esta revisión no toca un permiso que otra fila ya referencie
fuera de este conjunto exacto.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.modules.identidad.domain.permisos import PERMISOS_DEL_CATALOGO

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_permiso_tabla = sa.table(
    "permiso",
    sa.column("codigo", sa.Text()),
    sa.column("descripcion", sa.Text()),
    sa.column("modulo", sa.Text()),
)


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()
    for permiso in PERMISOS_DEL_CATALOGO:
        conexion.execute(
            sa.text(
                "INSERT INTO permiso (codigo, descripcion, modulo) "
                "VALUES (:codigo, :descripcion, :modulo) "
                "ON CONFLICT (codigo) DO NOTHING"
            ),
            {
                "codigo": permiso.codigo,
                "descripcion": permiso.descripcion,
                "modulo": permiso.modulo,
            },
        )


def downgrade() -> None:
    """Downgrade schema.

    Hallazgo de la tarea 14.4 (verificación `upgrade`/`downgrade`/`upgrade`
    contra una base CON datos, no vacía): si algún `rol_permiso` referencia
    alguno de estos códigos (caso real en cuanto una organización asigna un
    permiso a un rol), el `DELETE FROM permiso` de abajo fallaba con
    `ForeignKeyViolation` -- `rol_permiso` (creada por `a1b2c3d4e5f6`, la
    revisión anterior a esta) todavía no se dropeó en este punto de la
    cadena de downgrade: su propio `downgrade` corre DESPUÉS del de esta
    revisión. Se borran primero las filas de `rol_permiso` que referencian
    estos códigos: es consistente con lo que ya sigue en la cadena de
    downgrade (`a1b2c3d4e5f6` termina dropeando la tabla `rol_permiso`
    entera), no una excepción nueva a TR-06 (esa regla es sobre operaciones
    de negocio confirmadas, no sobre el downgrade de un esquema que de
    todos modos va a `base`)."""
    codigos = [permiso.codigo for permiso in PERMISOS_DEL_CATALOGO]
    conexion = op.get_bind()
    conexion.execute(
        sa.text("DELETE FROM rol_permiso WHERE permiso_codigo IN :codigos").bindparams(
            sa.bindparam("codigos", expanding=True)
        ),
        {"codigos": codigos},
    )
    op.execute(_permiso_tabla.delete().where(_permiso_tabla.c.codigo.in_(codigos)))
