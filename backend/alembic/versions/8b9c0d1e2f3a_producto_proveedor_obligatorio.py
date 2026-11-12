"""producto_proveedor_obligatorio: proveedor obligatorio en productos existentes

Revision ID: 8b9c0d1e2f3a
Revises: 70dcb6dce507
Create Date: 2026-09-24 00:00:00.000000

Change 06 (`design.md` Migration Plan punto 2, D2, aprobado por el usuario
2026-09-23; SQL exacto confirmado en `tasks.md` 4.1): cierra CAT-01/CAT-06
completando el dato antes de la restricción (`03` §17).

- Por cada organización con productos de `proveedor_id` nulo, inserta un
  proveedor `"Proveedor a asignar"` (`id` con `app.core.ids.nuevo_id()`
  UUIDv7, `activo = false`, `cuit`/`contacto`/`telefono`/`email` nulos,
  `creado_en`/`actualizado_en = now()` de la base -- la migración corre
  fuera de la aplicación, mismo criterio que los `server_default` de
  `70dcb6dce507` --, `actualizado_por_id = NULL` porque ningún usuario hace
  la acción) y lo asigna a esos productos de la misma organización.
- Luego `ALTER COLUMN producto.proveedor_id SET NOT NULL`.
- Idempotente: una nueva ejecución no encuentra huérfanos, así que no
  inserta ni asigna nada.
- Sin marca ni valor centinela: si una organización ya tiene un proveedor
  llamado exactamente "Proveedor a asignar", `ux_proveedor__nombre` rechaza
  la inserción y la migración falla entera sin dejar estado parcial (no se
  reutiliza el existente para no asignar en silencio un proveedor real).

`downgrade` (variante aprobada 2026-09-23, ver `design.md` D2): hace
ÚNICAMENTE `DROP NOT NULL` sobre `producto.proveedor_id`. Los proveedores
provisorios y sus asignaciones se conservan (son datos válidos, iguales a
los que quedarían en producción); revertir la migración 1
(`fk_producto__proveedor`) sigue siendo lo que borra la FK y las tablas.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "8b9c0d1e2f3a"
down_revision: str | Sequence[str] | None = "70dcb6dce507"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOMBRE_PROVEEDOR_PROVISORIO = "Proveedor a asignar"


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()

    organizaciones_huerfanas = (
        conexion.execute(
            sa.text("SELECT DISTINCT organizacion_id FROM producto WHERE proveedor_id IS NULL")
        )
        .scalars()
        .all()
    )

    for organizacion_id in organizaciones_huerfanas:
        proveedor_id = nuevo_id()
        conexion.execute(
            sa.text(
                "INSERT INTO proveedor "
                "(id, organizacion_id, nombre, cuit, contacto, telefono, email, activo, "
                "creado_en, actualizado_en, actualizado_por_id) "
                "VALUES (:id, :organizacion_id, :nombre, NULL, NULL, NULL, NULL, false, "
                "now(), now(), NULL)"
            ),
            {
                "id": proveedor_id,
                "organizacion_id": organizacion_id,
                "nombre": NOMBRE_PROVEEDOR_PROVISORIO,
            },
        )
        conexion.execute(
            sa.text(
                "UPDATE producto SET proveedor_id = :proveedor_id "
                "WHERE organizacion_id = :organizacion_id AND proveedor_id IS NULL"
            ),
            {"proveedor_id": proveedor_id, "organizacion_id": organizacion_id},
        )

    op.alter_column("producto", "proveedor_id", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("producto", "proveedor_id", nullable=True)
