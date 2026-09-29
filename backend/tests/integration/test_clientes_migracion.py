"""Tarea 1.1: la migración crea la tabla `cliente` tal como la declara
`clientes/models.py`.

Unitario no alcanza: esto consulta el esquema REAL de PostgreSQL ya migrado
(`alembic upgrade head`, el mismo camino que corre la aplicación), que es
literalmente lo que la tarea pide verificar. El complemento del otro lado --
que el modelo no se desvíe de la migración -- lo da
`test_modelos_coinciden_con_migracion.py` con `alembic revision
--autogenerate`.

Referencias: `docs/03-modelo-de-datos.md` §10, `design.md` D1 (índices únicos
parciales), D2 (`lista_precio_id` sin FK), D5 (sin `condicion_iva`), D6
(`numeric(14,2)`), CLI-03, INV-05 (el usuario de aplicación no puede borrar
un cliente), INV-21 (la unicidad compuesta habilita las FK de `venta`,
`cobranza` y `compra`).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)

COLUMNAS_ESPERADAS = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "codigo": ("text", True),
    "nombre": ("text", False),
    "razon_social": ("text", True),
    "documento_tipo": ("text", True),
    "documento_numero": ("text", True),
    "direccion": ("text", False),
    "contacto": ("text", False),
    "telefono": ("text", True),
    "email": ("text", True),
    "lista_precio_id": ("uuid", True),
    "limite_credito": ("numeric", True),
    "politica_credito": ("text", True),
    "tolerancia_offline_tipo": ("text", True),
    "tolerancia_offline_valor": ("numeric", True),
    "estado_facturacion_default": ("text", True),
    "es_consumidor_final": ("boolean", False),
    "estado": ("text", False),
    "creado_en": ("timestamp with time zone", False),
    "actualizado_en": ("timestamp with time zone", False),
    "actualizado_por_id": ("uuid", True),
}


def _columnas(motor: Engine) -> dict[str, tuple[str, bool]]:
    filas = motor.connect().execute(
        text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'cliente'
            """
        )
    )
    return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def test_la_tabla_cliente_existe_con_sus_columnas_y_tipos(_engine_de_sesion: Engine) -> None:
    columnas = _columnas(_engine_de_sesion)

    assert columnas, "La migración no creó la tabla `cliente`."
    assert columnas == COLUMNAS_ESPERADAS


def test_los_importes_de_credito_y_tolerancia_son_numeric_14_2(
    _engine_de_sesion: Engine,
) -> None:
    """D6: misma precisión que `configuracion_organizacion.tolerancia_offline_
    valor`, así que heredar el valor de la organización es una lectura."""
    filas = (
        _engine_de_sesion.connect()
        .execute(
            text(
                """
            SELECT column_name, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'cliente'
              AND column_name IN ('limite_credito', 'tolerancia_offline_valor')
            ORDER BY column_name
            """
            )
        )
        .all()
    )

    assert filas == [("limite_credito", 14, 2), ("tolerancia_offline_valor", 14, 2)]


def test_los_momentos_son_timestamptz(_engine_de_sesion: Engine) -> None:
    filas = (
        _engine_de_sesion.connect()
        .execute(
            text(
                """
            SELECT column_name, datetime_precision
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'cliente'
              AND column_name IN ('creado_en', 'actualizado_en')
            ORDER BY column_name
            """
            )
        )
        .all()
    )

    assert filas == [("actualizado_en", 6), ("creado_en", 6)]


def test_las_fk_son_compuestas_con_organizacion_id(_engine_de_sesion: Engine) -> None:
    """INV-21: toda FK entre entidades de negocio incluye `organizacion_id`
    (`CLAUDE.md` §4), así que un cliente de otra organización no puede ser
    referenciado ni colarse por una FK simple."""
    filas = (
        _engine_de_sesion.connect()
        .execute(
            text(
                """
            SELECT tc.constraint_name,
                   string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position)
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'public' AND tc.table_name = 'cliente'
              AND tc.constraint_type = 'FOREIGN KEY'
            GROUP BY tc.constraint_name
            ORDER BY tc.constraint_name
            """
            )
        )
        .all()
    )

    assert filas == [
        ("fk_cliente__actualizado_por", "organizacion_id,actualizado_por_id"),
        ("fk_cliente__organizacion", "organizacion_id"),
    ]


def test_lista_precio_id_no_tiene_fk(_engine_de_sesion: Engine) -> None:
    """D2: la tabla `lista_precio` la crea el change 13; la columna queda sin
    FK para no adelantarla (mismo criterio que `producto.proveedor_id` antes
    del 13, ADR-025)."""
    filas = (
        _engine_de_sesion.connect()
        .execute(
            text(
                """
            SELECT COUNT(*)
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'public' AND tc.table_name = 'cliente'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'lista_precio_id'
            """
            )
        )
        .scalar_one()
    )

    assert filas == 0


def test_los_indices_unicos_son_parciales_sobre_las_columnas_opcionales(
    _engine_de_sesion: Engine,
) -> None:
    """D1: la base --no el handler-- separa dos altas concurrentes con el
    mismo código o documento (`02` §6.3, INV-01)."""
    filas = (
        _engine_de_sesion.connect()
        .execute(
            text(
                """
            SELECT i.relname,
                   pg_get_indexdef(i.oid) AS definicion
            FROM pg_index AS idx
            JOIN pg_class AS t ON t.oid = idx.indrelid
            JOIN pg_class AS i ON i.oid = idx.indexrelid
            JOIN pg_namespace AS n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = 'cliente' AND idx.indisunique
            ORDER BY i.relname
            """
            )
        )
        .all()
    )

    por_nombre = {nombre: definicion for nombre, definicion in filas}
    assert "ux_cliente__codigo" in por_nombre
    assert "WHERE (codigo IS NOT NULL)" in por_nombre["ux_cliente__codigo"]
    assert "(organizacion_id, codigo)" in por_nombre["ux_cliente__codigo"]

    assert "ux_cliente__documento" in por_nombre
    assert "WHERE (documento_numero IS NOT NULL)" in por_nombre["ux_cliente__documento"]
    assert (
        "(organizacion_id, documento_tipo, documento_numero)" in por_nombre["ux_cliente__documento"]
    )


def test_los_checks_de_catalogo_y_de_pareja_estan_en_la_base(
    _engine_de_sesion: Engine,
) -> None:
    """Un valor fuera de los catálogos cerrados no entra ni por un camino que
    se salte el dominio (`01` §18, CLI-02, CLI-05, CRE-03, CRE-06)."""
    nombres = {
        nombre
        for (nombre,) in _engine_de_sesion.connect()
        .execute(
            text(
                """
                SELECT tc.constraint_name
                FROM information_schema.table_constraints AS tc
                WHERE tc.table_schema = 'public' AND tc.table_name = 'cliente'
                  AND tc.constraint_type = 'CHECK'
                  -- PostgreSQL 17 registra cada `NOT NULL` como una restricción
                  -- más y `information_schema` las reporta como `CHECK`, con
                  -- nombre derivado del OID (`2200_16914_1_not_null`).
                  AND tc.constraint_name NOT LIKE '%\\_not_null'
                """
            )
        )
        .all()
    }

    assert nombres == {
        "ck_cliente__estado",
        "ck_cliente__documento_tipo",
        "ck_cliente__documento_pareja",
        "ck_cliente__politica_credito",
        "ck_cliente__tolerancia_tipo",
        "ck_cliente__tolerancia_pareja",
        "ck_cliente__tolerancia_valor",
        "ck_cliente__limite_credito",
        "ck_cliente__estado_facturacion",
    }


def test_el_usuario_de_aplicacion_no_puede_borrar_un_cliente(
    app_runtime_engine: Engine, database_url: str
) -> None:
    """INV-05, CLI-04: un cliente no se elimina, se inactiva (su estado llega
    con `CLIENTE_MODIFICAR`). El permiso se otorga por tabla en cada
    migración (ADR-020)."""
    del database_url
    permisos = set(
        app_runtime_engine.connect()
        .execute(
            text(
                """
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = 'public' AND table_name = 'cliente'
                  AND grantee = 'app_runtime'
                """
            )
        )
        .scalars()
        .all()
    )

    assert permisos == {"SELECT", "INSERT", "UPDATE"}


def test_un_cliente_de_otra_organizacion_no_puede_apuntar_a_un_documento_repetido(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02: los índices únicos son por organización, así que el mismo
    documento puede existir en A y en B."""
    definiciones = {
        nombre: definicion
        for nombre, definicion in _engine_de_sesion.connect()
        .execute(
            text(
                """
                SELECT i.relname, pg_get_indexdef(i.oid)
                FROM pg_index AS idx
                JOIN pg_class AS t ON t.oid = idx.indrelid
                JOIN pg_class AS i ON i.oid = idx.indexrelid
                JOIN pg_namespace AS n ON n.oid = t.relnamespace
                -- El `LEFT JOIN` deja fuera los índices que respaldan una
                -- restricción (`pk_cliente`, `ux_cliente__org_id`): lo que se
                -- prueba aquí son los índices únicos creados a propósito.
                LEFT JOIN pg_constraint AS c ON c.conindid = idx.indexrelid
                WHERE n.nspname = 'public' AND t.relname = 'cliente'
                  AND idx.indisunique AND NOT idx.indisprimary
                  AND c.oid IS NULL
                """
            )
        )
        .all()
    }

    assert set(definiciones) == {"ux_cliente__codigo", "ux_cliente__documento"}
    for definicion in definiciones.values():
        assert definicion.startswith("CREATE UNIQUE INDEX")
        assert "organizacion_id" in definicion


def _organizacion(conexion: Connection) -> UUID:
    """Una organización real: sin ella la `FK` a `organizacion` rechazaría la
    fila y la prueba pasaría por el motivo equivocado."""
    organizacion_id = uuid4()
    conexion.execute(
        text(
            """
            INSERT INTO organizacion (
                id, nombre, slug, cuit, moneda, zona_horaria, estado,
                creado_en, actualizado_en
            ) VALUES (
                :id, 'Organización de prueba clientes', :slug, NULL, 'ARS',
                'America/Argentina/Mendoza', 'ACTIVA', now(), now()
            )
            """
        ),
        {"id": organizacion_id, "slug": f"org-clientes-{uuid4().hex[:8]}"},
    )
    return organizacion_id


def _insertar_cliente(conexion: Connection, organizacion_id: UUID, **extra: object) -> UUID:
    """Inserta un cliente mínimo y devuelve su id. Lo que la prueba quiere
    cambiar se pasa en `extra`, así ningún `INSERT` repite una columna."""
    cliente_id = uuid4()
    valores: dict[str, object] = {
        "id": cliente_id,
        "organizacion_id": organizacion_id,
        "nombre": "Kiosco La Esquina",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "es_consumidor_final": False,
        "estado": "ACTIVO",
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
        **extra,
    }
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    conexion.execute(
        text(f"INSERT INTO cliente ({columnas}) VALUES ({marcadores})"),
        valores,
    )
    return cliente_id


# Columnas extra del `INSERT` por `CHECK` catalogado. Las que van en pareja
# (`documento_tipo`, `tolerancia_offline_tipo`) se insertan con su compañera
# válida: si el par quedara a medias saltaría antes el `CHECK` `*_pareja` y la
# prueba pasaría sin comprobar lo que dice comprobar.
CASOS_FUERA_DE_CATALOGO: dict[str, dict[str, object]] = {
    "ck_cliente__estado": {"estado": "ACTIVO_OLD"},
    "ck_cliente__documento_tipo": {"documento_tipo": "PASAPORTE", "documento_numero": "30111222"},
    "ck_cliente__politica_credito": {"politica_credito": "IGNORAR"},
    "ck_cliente__tolerancia_tipo": {
        "tolerancia_offline_tipo": "CUALQUIERA",
        "tolerancia_offline_valor": "10.00",
    },
    "ck_cliente__limite_credito": {"limite_credito": "-1"},
    "ck_cliente__estado_facturacion": {"estado_facturacion_default": "FACTURADA"},
}


@pytest.mark.parametrize("nombre_del_check", list(CASOS_FUERA_DE_CATALOGO))
def test_la_base_rechaza_un_valor_fuera_del_catalogo(
    _engine_de_sesion: Engine, nombre_del_check: str
) -> None:
    """Triangulación de los `CHECK` en la base real: no alcanza con que el
    dominio los valide, la fila tampoco se puede escribir saltándoselo."""
    with (
        pytest.raises(IntegrityError) as error,
        _engine_de_sesion.connect() as conexion,
        conexion.begin(),
    ):
        organizacion_id = _organizacion(conexion)
        _insertar_cliente(conexion, organizacion_id, **CASOS_FUERA_DE_CATALOGO[nombre_del_check])

    # Búsqueda exacta y no por subcadena: `ck_cliente__estado` es prefijo de
    # `ck_cliente__estado_facturacion` y haría pasar la prueba equivocada.
    violada = re.search(r'violates check constraint "(ck_cliente__\w+)"', str(error.value))
    assert violada is not None, str(error.value)
    assert violada.group(1) == nombre_del_check


def test_la_base_rechaza_un_documento_a_medias(_engine_de_sesion: Engine) -> None:
    """El documento es opcional "como pareja" (CLI-01, D1): un tipo sin número
    no entra, igual que un número sin tipo."""
    with (
        pytest.raises(IntegrityError) as error,
        _engine_de_sesion.connect() as conexion,
        conexion.begin(),
    ):
        organizacion_id = _organizacion(conexion)
        _insertar_cliente(conexion, organizacion_id, documento_tipo="DNI")

    assert "ck_cliente__documento_pareja" in str(error.value)


def test_la_base_rechaza_una_tolerancia_a_medias(_engine_de_sesion: Engine) -> None:
    """CRE-06, D6: tipo y valor van juntos o no van (mismo criterio que la
    restricción de la organización)."""
    with (
        pytest.raises(IntegrityError) as error,
        _engine_de_sesion.connect() as conexion,
        conexion.begin(),
    ):
        organizacion_id = _organizacion(conexion)
        _insertar_cliente(conexion, organizacion_id, tolerancia_offline_tipo="IMPORTE")

    assert "ck_cliente__tolerancia_pareja" in str(error.value)


def test_el_mismo_documento_puede_existir_en_dos_organizaciones(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02, D1: los índices únicos son por organización, así que
    `DNI 30111222` puede existir en A y en B a la vez (el mismo nombre en otra
    organización también es válido: TR-08)."""
    with _engine_de_sesion.connect() as conexion, conexion.begin():
        ids = [
            _insertar_cliente(
                conexion,
                _organizacion(conexion),
                documento_tipo="DNI",
                documento_numero="30111222",
            )
            for _ in range(2)
        ]

    assert len(set(ids)) == 2


def test_un_documento_repetido_en_la_misma_organizacion_no_entra(
    _engine_de_sesion: Engine,
) -> None:
    """D1: la base separa dos altas concurrentes con el mismo documento aunque
    las dos hayan pasado la validación del dominio (INV-01)."""
    with (
        pytest.raises(IntegrityError) as error,
        _engine_de_sesion.connect() as conexion,
        conexion.begin(),
    ):
        organizacion_id = _organizacion(conexion)
        for _ in range(2):
            _insertar_cliente(
                conexion, organizacion_id, documento_tipo="DNI", documento_numero="30111222"
            )

    assert "ux_cliente__documento" in str(error.value)


def test_un_codigo_repetido_en_la_misma_organizacion_no_entra(
    _engine_de_sesion: Engine,
) -> None:
    """D1, igual que el documento pero del otro índice único parcial."""
    with (
        pytest.raises(IntegrityError) as error,
        _engine_de_sesion.connect() as conexion,
        conexion.begin(),
    ):
        organizacion_id = _organizacion(conexion)
        for _ in range(2):
            _insertar_cliente(conexion, organizacion_id, codigo="CLI-0001")

    assert "ux_cliente__codigo" in str(error.value)


def test_varios_clientes_sin_codigo_ii_documento_conviven(
    _engine_de_sesion: Engine,
) -> None:
    """Los índices únicos son PARCIALES justamente para esto: sin `WHERE`, el
    `NULL` de la primera fila colisionaría con el de la segunda."""
    with _engine_de_sesion.connect() as conexion, conexion.begin():
        organizacion_id = _organizacion(conexion)
        ids = [_insertar_cliente(conexion, organizacion_id) for _ in range(3)]

    assert len(set(ids)) == 3
