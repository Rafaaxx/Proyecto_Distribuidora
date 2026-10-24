"""identidad: intento_login.clave_intento (bloqueo del login por el nombre escrito, ADR-057)

Revision ID: c8d9e0f1a2b3
Revises: b6c7d8e9f0a1
Create Date: 2026-10-24 00:00:00.000000

Agrega `clave_intento text NULL` (SHA-256 hexadecimal, 64 caracteres, del par escrito
`[slug, usuario]` en JSON) e `ix_intento_login__clave_intento_creado_en (clave_intento,
creado_en)`, igual a los dos índices existentes. Con esa clave el límite de 5 fallos del login
cuenta por par escrito, exista o no la organización o el usuario (ADR-057, enmienda a ADR-018).

Completa `clave_intento` de las filas viejas con `usuario_id` (fallos y marcadores de desbloqueo),
uniendo `usuario` y `organizacion` para obtener el par, para que un bloqueo en curso al desplegar
no se pierda. Las filas viejas con `usuario_id` nulo quedan sin clave: no se puede reconstruir qué
se escribió, y vencen solas a los 15 minutos. El completado lo hace esta migración con el rol
dueño: `app_runtime` sigue con `SELECT, INSERT` sobre `intento_login`, sin `UPDATE` (INV-05); el
`GRANT` de tabla ya cubre la columna nueva. `intento_login` sigue sin `organizacion_id` y exenta de
INV-02 (ADR-057 punto 3).

La clave se calcula acá con la misma codificación que `identidad/domain/clave_intento.py`
(duplicada a propósito: una migración no debe depender del código de la aplicación, que cambia);
`test_alembic_integracion.py` verifica que coinciden.
"""

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICE = "ix_intento_login__clave_intento_creado_en"


def _clave(slug: str, usuario: str) -> str:
    codificado = json.dumps([slug, usuario], ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(codificado).hexdigest()


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("intento_login", sa.Column("clave_intento", sa.Text(), nullable=True))
    op.create_index(INDICE, "intento_login", ["clave_intento", "creado_en"])

    conexion = op.get_bind()
    pares = conexion.execute(
        sa.text(
            "SELECT DISTINCT i.usuario_id, o.slug, u.usuario "
            "FROM intento_login i "
            "JOIN usuario u ON u.id = i.usuario_id "
            "JOIN organizacion o ON o.id = u.organizacion_id"
        )
    ).all()
    for usuario_id, slug, usuario in pares:
        conexion.execute(
            sa.text(
                "UPDATE intento_login SET clave_intento = :clave "
                "WHERE usuario_id = :usuario_id AND clave_intento IS NULL"
            ),
            {"clave": _clave(slug, usuario), "usuario_id": usuario_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(INDICE, table_name="intento_login")
    op.drop_column("intento_login", "clave_intento")
