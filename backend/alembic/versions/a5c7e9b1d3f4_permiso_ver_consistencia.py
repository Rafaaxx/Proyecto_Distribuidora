"""permiso VER_CONSISTENCIA

Revision ID: a5c7e9b1d3f4
Revises: f4b6d8a0c2e1
Create Date: 2026-11-10 13:00:00.000000

Change 28 (`design.md` D5, Q2; `01` §19): permiso de solo lectura para ver el aviso de
consistencia en `/admin` y leer el ultimo resultado de la verificacion (`GET
/api/v1/sistema/consistencia`). Mismo patron que `ANULAR_TRANSFERENCIA` (revision
`f3a4b5c6d7e8`): se inserta en `permiso` (idempotente) y se asigna, en las organizaciones
existentes, a los roles de plantilla cuya composicion en `PLANTILLAS_DE_ROL` lo incluye
(`Administrador` y `Administracion`). Los roles de plantilla se reconocen por su NOMBRE: una
organizacion que renombro un rol no lo recibe y lo asigna a mano. La lista de roles NO vive
aca: se deriva de la fuente unica `app.modules.identidad.domain.permisos`, la que usa tambien la
siembra.

`downgrade` borra el permiso con sus asignaciones; no toca ningun dato del negocio.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.modules.identidad.domain.permisos import PERMISOS_DEL_CATALOGO, PLANTILLAS_DE_ROL

# revision identifiers, used by Alembic.
revision: str = "a5c7e9b1d3f4"
down_revision: str | Sequence[str] | None = "f4b6d8a0c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISO = "VER_CONSISTENCIA"


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()
    permiso = next(p for p in PERMISOS_DEL_CATALOGO if p.codigo == PERMISO)
    conexion.execute(
        sa.text(
            "INSERT INTO permiso (codigo, descripcion, modulo) "
            "VALUES (:codigo, :descripcion, :modulo) ON CONFLICT (codigo) DO NOTHING"
        ),
        {"codigo": permiso.codigo, "descripcion": permiso.descripcion, "modulo": permiso.modulo},
    )
    for nombre_rol in [n for n, permisos in PLANTILLAS_DE_ROL.items() if PERMISO in permisos]:
        conexion.execute(
            sa.text(
                "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
                "SELECT r.organizacion_id, r.id, :permiso FROM rol r WHERE r.nombre = :rol "
                "ON CONFLICT DO NOTHING"
            ),
            {"permiso": PERMISO, "rol": nombre_rol},
        )


def downgrade() -> None:
    """Downgrade schema."""
    conexion = op.get_bind()
    conexion.execute(
        sa.text("DELETE FROM rol_permiso WHERE permiso_codigo = :permiso"), {"permiso": PERMISO}
    )
    conexion.execute(sa.text("DELETE FROM permiso WHERE codigo = :permiso"), {"permiso": PERMISO})
