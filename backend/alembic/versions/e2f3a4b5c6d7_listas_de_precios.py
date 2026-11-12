"""listas de precios: lista_precio, regla_margen, redondeo_categoria, lista_version y
precio_item, y las claves foraneas de la lista del cliente y de la predeterminada

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-06 00:00:00.000000

Change 13 (`design.md` D13 opcion A), una sola revision:

1. Las cinco tablas de `03` §8 con los agregados de D13: el redondeo de la lista y de la
   categoria (PRC-14), las columnas generadas de alcance de `regla_margen` con su clave
   foranea compuesta (ADR-035, INV-02), los unicos parciales de D5 (un borrador por lista),
   D6 (vigencia desde entre las publicadas) y D8 (una regla activa por lista y alcance), el
   `CHECK` de coherencia de la publicacion y de la anulacion de la version, y las
   `unidades_referencia` congeladas en cada precio (D1).
2. `cliente (organizacion_id, lista_precio_id)` y
   `configuracion_organizacion (organizacion_id, lista_precio_default_id)` pasan a ser claves
   foraneas compuestas a `lista_precio` (D11, D13 punto 6). Antes de crearlas, la revision
   verifica que ningun valor apunte a una lista inexistente (hoy ninguno puede apuntar a
   otra cosa, porque la tabla no existia) y aborta con un mensaje claro: el error de
   PostgreSQL al agregar la clave seria opaco.
3. Privilegios de `app_runtime` (D13 punto 7): `SELECT, INSERT, UPDATE` en los tres
   maestros (nunca `DELETE`: se desactivan); en `lista_version`, `SELECT, INSERT` y `UPDATE`
   solo por columna del ciclo de vida (estado, vigencias, publicacion, anulacion y
   generacion; el numero y la lista no cambian); en `precio_item`, los cuatro (el borrador
   se regenera). INV-11 se garantiza en el servicio, como dice `03` §8, no en la base.

`downgrade` deja en nulo `cliente.lista_precio_id` y
`configuracion_organizacion.lista_precio_default_id`, quita las dos claves foraneas y borra
las cinco tablas: **pierde listas, reglas, redondeos, versiones y precios por diseno**
(D13; `04` §2.1 punto 4: "sube y baja limpia" es correr sin errores y respetando la
integridad referencial en cada paso, no que los datos de negocio sobrevivan un rollback).
La perdida esta escrita como asercion explicita en
`backend/tests/integration/test_precios_migracion.py` (tarea 1.4).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_DIRECCIONES = "'ARRIBA','CERCANO','ABAJO'"
_TIPOS_MARGEN = "'MARKUP','MARGEN_BRUTO'"
_ALCANCES = "'PRODUCTO','MARCA','CATEGORIA','PROVEEDOR','LISTA'"

_COLUMNAS_MUTABLES_VERSION = (
    "estado, vigencia_desde, vigencia_hasta, publicado_por_id, publicado_en, "
    "anulado_por_id, anulado_en, generado_en, version_base_id"
)

_VALOR_REGLA = "valor >= 0 AND (tipo <> 'MARGEN_BRUTO' OR valor < 1)"


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    """Clave foranea compuesta que incluye `organizacion_id` (INV-02, `03` §2.4)."""
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


def _generada(alcance: str) -> sa.Computed:
    return sa.Computed(f"CASE WHEN alcance_tipo = '{alcance}' THEN alcance_id END", persisted=True)


def upgrade() -> None:
    """Upgrade schema."""
    _verificar_que_ninguna_lista_apunte_a_una_inexistente()

    op.create_table(
        "lista_precio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("redondeo_multiplo", sa.Numeric(14, 2), nullable=False),
        sa.Column("redondeo_direccion", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_lista_precio"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_lista_precio__organizacion"
        ),
        _fk("lista_precio", "actualizado_por", "actualizado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_lista_precio__org_id"),
        sa.CheckConstraint("redondeo_multiplo > 0", name="ck_lista_precio__redondeo_multiplo"),
        sa.CheckConstraint(
            f"redondeo_direccion IN ({_DIRECCIONES})", name="ck_lista_precio__redondeo_direccion"
        ),
    )
    op.create_index(
        "ux_lista_precio__nombre",
        "lista_precio",
        ["organizacion_id", sa.text("lower(nombre)")],
        unique=True,
    )

    op.create_table(
        "regla_margen",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("lista_id", sa.Uuid(), nullable=False),
        sa.Column("alcance_tipo", sa.Text(), nullable=False),
        sa.Column("alcance_id", sa.Uuid(), nullable=True),
        sa.Column("producto_id", sa.Uuid(), _generada("PRODUCTO"), nullable=True),
        sa.Column("marca_id", sa.Uuid(), _generada("MARCA"), nullable=True),
        sa.Column("categoria_id", sa.Uuid(), _generada("CATEGORIA"), nullable=True),
        sa.Column("proveedor_id", sa.Uuid(), _generada("PROVEEDOR"), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("valor", sa.Numeric(9, 6), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_regla_margen"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_regla_margen__organizacion"
        ),
        _fk("regla_margen", "lista", "lista_id", "lista_precio"),
        _fk("regla_margen", "producto", "producto_id", "producto"),
        _fk("regla_margen", "marca", "marca_id", "marca"),
        _fk("regla_margen", "categoria", "categoria_id", "categoria"),
        _fk("regla_margen", "proveedor", "proveedor_id", "proveedor"),
        _fk("regla_margen", "actualizado_por", "actualizado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_regla_margen__org_id"),
        sa.CheckConstraint(f"alcance_tipo IN ({_ALCANCES})", name="ck_regla_margen__alcance_tipo"),
        sa.CheckConstraint(f"tipo IN ({_TIPOS_MARGEN})", name="ck_regla_margen__tipo"),
        sa.CheckConstraint(
            "(alcance_tipo = 'LISTA') = (alcance_id IS NULL)", name="ck_regla_margen__alcance"
        ),
        sa.CheckConstraint(_VALOR_REGLA, name="ck_regla_margen__valor"),
    )
    # D8: una sola regla activa por lista y alcance. El alcance `LISTA` no tiene
    # `alcance_id` y NULL no choca consigo mismo en un unico, asi que son dos indices.
    op.create_index(
        "ux_regla_margen__alcance_activa",
        "regla_margen",
        ["organizacion_id", "lista_id", "alcance_tipo", "alcance_id"],
        unique=True,
        postgresql_where=sa.text("activo AND alcance_id IS NOT NULL"),
    )
    op.create_index(
        "ux_regla_margen__lista_activa",
        "regla_margen",
        ["organizacion_id", "lista_id"],
        unique=True,
        postgresql_where=sa.text("activo AND alcance_tipo = 'LISTA'"),
    )

    op.create_table(
        "redondeo_categoria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("lista_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), nullable=False),
        sa.Column("multiplo", sa.Numeric(14, 2), nullable=False),
        sa.Column("direccion", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_redondeo_categoria"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_redondeo_categoria__organizacion"
        ),
        _fk("redondeo_categoria", "lista", "lista_id", "lista_precio"),
        _fk("redondeo_categoria", "categoria", "categoria_id", "categoria"),
        _fk("redondeo_categoria", "actualizado_por", "actualizado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_redondeo_categoria__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "lista_id",
            "categoria_id",
            name="ux_redondeo_categoria__lista_categoria",
        ),
        sa.CheckConstraint("multiplo > 0", name="ck_redondeo_categoria__multiplo"),
        sa.CheckConstraint(
            f"direccion IN ({_DIRECCIONES})", name="ck_redondeo_categoria__direccion"
        ),
    )

    op.create_table(
        "lista_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("lista_id", sa.Uuid(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("vigencia_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vigencia_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version_base_id", sa.Uuid(), nullable=True),
        sa.Column("generado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por_id", sa.Uuid(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_por_id", sa.Uuid(), nullable=True),
        sa.Column("publicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_por_id", sa.Uuid(), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_lista_version"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_lista_version__organizacion"
        ),
        _fk("lista_version", "lista", "lista_id", "lista_precio"),
        _fk("lista_version", "version_base", "version_base_id", "lista_version"),
        _fk("lista_version", "creado_por", "creado_por_id", "usuario"),
        _fk("lista_version", "publicado_por", "publicado_por_id", "usuario"),
        _fk("lista_version", "anulado_por", "anulado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_lista_version__org_id"),
        sa.CheckConstraint(
            "estado IN ('BORRADOR','PUBLICADA','ANULADA')", name="ck_lista_version__estado"
        ),
        sa.CheckConstraint("numero >= 1", name="ck_lista_version__numero"),
        # Un borrador no tiene vigencia ni publicacion; una version publicada o anulada
        # tiene usuario, momento y vigencia desde (PRC-02, D6).
        sa.CheckConstraint(
            "(estado = 'BORRADOR') = (publicado_en IS NULL) "
            "AND (publicado_en IS NULL) = (publicado_por_id IS NULL) "
            "AND (publicado_en IS NULL) = (vigencia_desde IS NULL) "
            "AND (vigencia_hasta IS NULL OR vigencia_desde IS NOT NULL)",
            name="ck_lista_version__publicacion_coherente",
        ),
        sa.CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL)",
            name="ck_lista_version__anulacion_coherente",
        ),
        sa.CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta > vigencia_desde",
            name="ck_lista_version__vigencia",
        ),
    )
    op.create_index(
        "ux_lista_version__numero",
        "lista_version",
        ["organizacion_id", "lista_id", "numero"],
        unique=True,
    )
    # D5: un solo borrador por lista.
    op.create_index(
        "ux_lista_version__borrador",
        "lista_version",
        ["organizacion_id", "lista_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'BORRADOR'"),
    )
    # D6: dos versiones publicadas de una lista no comparten vigencia desde.
    op.create_index(
        "ux_lista_version__vigencia_desde",
        "lista_version",
        ["organizacion_id", "lista_id", "vigencia_desde"],
        unique=True,
        postgresql_where=sa.text("estado = 'PUBLICADA'"),
    )
    # PRC-03, PRC-20: la version vigente se resuelve por la vigencia desde mas reciente.
    op.create_index(
        "ix_lista_version__resolucion",
        "lista_version",
        ["organizacion_id", "lista_id", sa.text("vigencia_desde DESC")],
    )

    op.create_table(
        "precio_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("unidades_referencia", sa.Integer(), nullable=False),
        sa.Column("costo_informado_id", sa.Uuid(), nullable=True),
        sa.Column("costo_referencia", sa.Numeric(18, 6), nullable=True),
        sa.Column("regla_margen_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_margen", sa.Text(), nullable=True),
        sa.Column("valor_margen", sa.Numeric(9, 6), nullable=True),
        sa.Column("precio_calculado", sa.Numeric(18, 6), nullable=True),
        sa.Column("precio_final", sa.Numeric(14, 2), nullable=False),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_precio_item"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_precio_item__organizacion"
        ),
        _fk("precio_item", "version", "version_id", "lista_version"),
        _fk("precio_item", "producto", "producto_id", "producto"),
        _fk("precio_item", "costo_informado", "costo_informado_id", "costo_informado"),
        _fk("precio_item", "regla_margen", "regla_margen_id", "regla_margen"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_precio_item__org_id"),
        sa.CheckConstraint("unidades_referencia >= 1", name="ck_precio_item__unidades_referencia"),
        sa.CheckConstraint("precio_final > 0", name="ck_precio_item__precio_final"),
        sa.CheckConstraint(
            f"tipo_margen IS NULL OR tipo_margen IN ({_TIPOS_MARGEN})",
            name="ck_precio_item__tipo_margen",
        ),
        # PRC-16, D7: un precio calculado guarda todo su calculo; uno manual puede carecer
        # de costo o de regla (se admite un precio manual sin costo).
        sa.CheckConstraint(
            "manual OR (costo_informado_id IS NOT NULL AND costo_referencia IS NOT NULL "
            "AND regla_margen_id IS NOT NULL AND tipo_margen IS NOT NULL "
            "AND valor_margen IS NOT NULL AND precio_calculado IS NOT NULL)",
            name="ck_precio_item__calculo_coherente",
        ),
    )
    # PRC-10: un unico precio por producto en cada version.
    op.create_index(
        "ux_precio_item__version_producto",
        "precio_item",
        ["organizacion_id", "version_id", "producto_id"],
        unique=True,
    )

    op.create_foreign_key(
        "fk_cliente__lista_precio",
        "cliente",
        "lista_precio",
        ["organizacion_id", "lista_precio_id"],
        ["organizacion_id", "id"],
    )
    op.create_foreign_key(
        "fk_configuracion_organizacion__lista_precio_default",
        "configuracion_organizacion",
        "lista_precio",
        ["organizacion_id", "lista_precio_default_id"],
        ["organizacion_id", "id"],
    )

    for tabla in ("lista_precio", "regla_margen", "redondeo_categoria"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabla} TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT ON lista_version TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ({_COLUMNAS_MUTABLES_VERSION}) ON lista_version TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON precio_item TO {ROL_RUNTIME}")


def _verificar_que_ninguna_lista_apunte_a_una_inexistente() -> None:
    """D13 punto 6: `lista_precio` no existia antes de esta revision, asi que cualquier
    `lista_precio_id` o `lista_precio_default_id` cargado apunta a una lista inexistente. Se
    aborta con un mensaje claro en vez de dejar que `ADD CONSTRAINT` falle sin decir donde."""
    conexion = op.get_bind()
    for tabla, columna in (
        ("cliente", "lista_precio_id"),
        ("configuracion_organizacion", "lista_precio_default_id"),
    ):
        colgadas = conexion.execute(
            sa.text(f"SELECT count(*) FROM {tabla} WHERE {columna} IS NOT NULL")
        ).scalar_one()
        if colgadas:
            raise RuntimeError(
                f"La revisión {revision} no puede crear la clave foránea de {tabla}.{columna} "
                f"(design.md D13 punto 6): hay {colgadas} fila(s) de {tabla} con {columna} "
                "cargado y la tabla lista_precio todavía no existe, así que ninguna lista "
                "puede ser la referenciada. Revisá esas filas "
                f"(SELECT * FROM {tabla} WHERE {columna} IS NOT NULL), ponelas en nulo y "
                "volvé a aplicar la migración; la revisión no las modifica."
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Las claves foraneas se quitan despues de dejar en nulo lo que apuntaba a una lista:
    # el `downgrade` pierde esos valores por diseno (D13).
    op.execute("UPDATE configuracion_organizacion SET lista_precio_default_id = NULL")
    op.execute("UPDATE cliente SET lista_precio_id = NULL")
    op.drop_constraint(
        "fk_configuracion_organizacion__lista_precio_default",
        "configuracion_organizacion",
        type_="foreignkey",
    )
    op.drop_constraint("fk_cliente__lista_precio", "cliente", type_="foreignkey")

    op.drop_table("precio_item")
    op.drop_table("lista_version")
    op.drop_table("redondeo_categoria")
    op.drop_table("regla_margen")
    op.drop_table("lista_precio")
