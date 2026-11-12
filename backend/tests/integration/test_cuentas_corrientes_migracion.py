"""Tarea 1.1: la migración crea `cuenta_movimiento` y `saldo_cuenta` según
`docs/03-modelo-de-datos.md` §12 y `design.md` D6, D11, D12 y D14.

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_clientes_migracion.py`); que los modelos no se desvíen de la migración lo
cubre `test_modelos_coinciden_con_migracion.py` (tarea 2.1).

Reglas citadas: CC-01, CC-04, CC-06, INV-02, INV-03, INV-05, INV-21 y
`design.md` D6 (FK compuestas sobre columnas generadas), D11 (clave de
`saldo_cuenta`), D12 (catálogo de tipos), D14 (`dispositivo_id`).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
    insertar_movimiento_sql,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

REVISION_ANTERIOR = "9c4e1f2a3b4d"  # `clientes`: la revisión que precede a la de este change.

COLUMNAS_DEL_LIBRO = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "cuenta_tipo": ("text", False),
    "entidad_id": ("uuid", False),
    "cliente_id": ("uuid", True),
    "proveedor_id": ("uuid", True),
    "tipo": ("text", False),
    "sentido": ("text", False),
    "importe": ("numeric", False),
    "origen_tipo": ("text", False),
    "origen_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "operation_id": ("uuid", False),
}

COLUMNAS_DEL_SALDO = {
    "organizacion_id": ("uuid", False),
    "cuenta_tipo": ("text", False),
    "entidad_id": ("uuid", False),
    "cliente_id": ("uuid", True),
    "proveedor_id": ("uuid", True),
    "saldo": ("numeric", False),
    "actualizado_en": ("timestamp with time zone", False),
}


def _columnas(motor: Engine, tabla: str) -> dict[str, tuple[str, bool]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :tabla
                """
            ),
            {"tabla": tabla},
        )
        return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def _fks(motor: Engine, tabla: str) -> dict[str, str]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT tc.constraint_name,
                       string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position)
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON kcu.constraint_name = tc.constraint_name
                 AND kcu.table_schema = tc.table_schema
                WHERE tc.table_schema = 'public' AND tc.table_name = :tabla
                  AND tc.constraint_type = 'FOREIGN KEY'
                GROUP BY tc.constraint_name
                """
            ),
            {"tabla": tabla},
        )
        return dict(filas.all())


def _checks(motor: Engine, tabla: str) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = CAST(:tabla AS regclass) AND contype = 'c'
                    """
                ),
                {"tabla": f"public.{tabla}"},
            )
            .scalars()
            .all()
        )


def _definiciones_de_restricciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    """
                    SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = CAST(:tabla AS regclass) AND contype = :tipo
                    """
                ),
                {"tabla": f"public.{tabla}", "tipo": tipo},
            ).all()
        )


# --- columnas y tipos ------------------------------------------------------


def test_el_libro_tiene_las_columnas_de_03_mas_dispositivo_y_las_generadas(
    _engine_de_sesion: Engine,
) -> None:
    """CC-01, `03` §12, D6 (`cliente_id`/`proveedor_id`), D14 (`dispositivo_id`
    `NOT NULL`)."""
    columnas = _columnas(_engine_de_sesion, "cuenta_movimiento")

    assert columnas, "La migración no creó la tabla `cuenta_movimiento`."
    assert columnas == COLUMNAS_DEL_LIBRO


def test_el_libro_no_tiene_columna_de_saldo(_engine_de_sesion: Engine) -> None:
    """CC-04: el saldo se calcula y se materializa aparte, no hay saldo por
    movimiento."""
    assert not {c for c in _columnas(_engine_de_sesion, "cuenta_movimiento") if "saldo" in c}


def test_el_saldo_tiene_las_columnas_de_03_mas_las_generadas(_engine_de_sesion: Engine) -> None:
    columnas = _columnas(_engine_de_sesion, "saldo_cuenta")

    assert columnas, "La migración no creó la tabla `saldo_cuenta`."
    assert columnas == COLUMNAS_DEL_SALDO


@pytest.mark.parametrize(
    ("tabla", "columna"),
    [("cuenta_movimiento", "importe"), ("saldo_cuenta", "saldo")],
)
def test_los_importes_son_numeric_14_2(_engine_de_sesion: Engine, tabla: str, columna: str) -> None:
    """`CLAUDE.md` §4, INV-03: `NUMERIC(14,2)`, nunca punto flotante."""
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                """
                SELECT numeric_precision, numeric_scale FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :tabla AND column_name = :columna
                """
            ),
            {"tabla": tabla, "columna": columna},
        ).one()

    assert tuple(fila) == (14, 2)


def test_los_momentos_son_timestamptz(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT table_name, column_name, datetime_precision
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND ((table_name = 'cuenta_movimiento'
                        AND column_name IN ('occurred_at', 'registered_at'))
                    OR (table_name = 'saldo_cuenta' AND column_name = 'actualizado_en'))
                ORDER BY table_name, column_name
                """
            )
        ).all()

    assert [tuple(f) for f in filas] == [
        ("cuenta_movimiento", "occurred_at", 6),
        ("cuenta_movimiento", "registered_at", 6),
        ("saldo_cuenta", "actualizado_en", 6),
    ]


@pytest.mark.parametrize("tabla", ["cuenta_movimiento", "saldo_cuenta"])
def test_cliente_id_y_proveedor_id_son_columnas_generadas(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """D6-A: las calcula PostgreSQL, nadie las escribe."""
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT column_name, is_generated, generation_expression
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :tabla
                  AND column_name IN ('cliente_id', 'proveedor_id')
                ORDER BY column_name
                """
            ),
            {"tabla": tabla},
        ).all()

    assert [(nombre, generada) for nombre, generada, _ in filas] == [
        ("cliente_id", "ALWAYS"),
        ("proveedor_id", "ALWAYS"),
    ]
    assert "'CLIENTE'" in filas[0][2]
    assert "'PROVEEDOR'" in filas[1][2]


def test_el_saldo_nace_en_cero_por_defecto(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        valor = conexion.execute(
            text(
                """
                SELECT column_default FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'saldo_cuenta'
                  AND column_name = 'saldo'
                """
            )
        ).scalar_one()

    assert Decimal(str(valor).split("::")[0].strip("'() ")) == 0


# --- claves, FK e índices --------------------------------------------------


def test_las_fk_son_compuestas_con_organizacion_id(_engine_de_sesion: Engine) -> None:
    """INV-21, `03` §2.4, D6, D14: toda FK entre entidades de negocio incluye
    `organizacion_id`."""
    assert _fks(_engine_de_sesion, "cuenta_movimiento") == {
        "fk_cuenta_movimiento__organizacion": "organizacion_id",
        "fk_cuenta_movimiento__usuario": "organizacion_id,usuario_id",
        "fk_cuenta_movimiento__dispositivo": "organizacion_id,dispositivo_id",
        "fk_cuenta_movimiento__cliente": "organizacion_id,cliente_id",
        "fk_cuenta_movimiento__proveedor": "organizacion_id,proveedor_id",
    }
    assert _fks(_engine_de_sesion, "saldo_cuenta") == {
        "fk_saldo_cuenta__organizacion": "organizacion_id",
        "fk_saldo_cuenta__cliente": "organizacion_id,cliente_id",
        "fk_saldo_cuenta__proveedor": "organizacion_id,proveedor_id",
    }


def test_el_libro_tiene_clave_primaria_y_unicidad_por_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02: sin `UNIQUE (organizacion_id, id)` ninguna tabla futura puede
    referenciar un movimiento con FK compuesta."""
    claves = _definiciones_de_restricciones(_engine_de_sesion, "cuenta_movimiento", "p")
    unicas = _definiciones_de_restricciones(_engine_de_sesion, "cuenta_movimiento", "u")

    assert claves == {"pk_cuenta_movimiento": "PRIMARY KEY (id)"}
    assert unicas == {"ux_cuenta_movimiento__org_id": "UNIQUE (organizacion_id, id)"}


def test_el_saldo_tiene_clave_primaria_compuesta_sin_id(_engine_de_sesion: Engine) -> None:
    """D11-A: `03` §12, clave `(organizacion_id, cuenta_tipo, entidad_id)`; la
    organización encabeza la clave, que es lo que INV-02 busca."""
    claves = _definiciones_de_restricciones(_engine_de_sesion, "saldo_cuenta", "p")

    assert claves == {"pk_saldo_cuenta": "PRIMARY KEY (organizacion_id, cuenta_tipo, entidad_id)"}
    assert "id" not in _columnas(_engine_de_sesion, "saldo_cuenta")


def test_el_indice_del_estado_de_cuenta_sigue_a_03(_engine_de_sesion: Engine) -> None:
    """`03` §12 y §16: `(organizacion_id, cuenta_tipo, entidad_id, occurred_at,
    id)`."""
    with _engine_de_sesion.connect() as conexion:
        definicion = conexion.execute(
            text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'cuenta_movimiento'
                  AND indexname = 'ix_cuenta_movimiento__estado_de_cuenta'
                """
            )
        ).scalar_one()

    assert "(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)" in definicion


# --- CHECK -----------------------------------------------------------------


def test_los_check_del_libro_y_del_saldo_estan_en_la_base(_engine_de_sesion: Engine) -> None:
    """Nombres de los `CHECK` (PostgreSQL 17 registra los `NOT NULL` como
    restricciones aparte, y `contype = 'c'` no los incluye)."""
    assert _checks(_engine_de_sesion, "cuenta_movimiento") == {
        "ck_cuenta_movimiento__importe_positivo",
        "ck_cuenta_movimiento__sentido",
        "ck_cuenta_movimiento__cuenta_tipo",
        "ck_cuenta_movimiento__tipo",
        "ck_cuenta_movimiento__tipo_de_cuenta",
    }
    assert _checks(_engine_de_sesion, "saldo_cuenta") == {"ck_saldo_cuenta__cuenta_tipo"}


# --- permisos --------------------------------------------------------------


def _privilegios(app_runtime_engine: Engine, tabla: str) -> set[str]:
    with app_runtime_engine.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    """
                    SELECT privilege_type FROM information_schema.role_table_grants
                    WHERE table_schema = 'public' AND table_name = :tabla
                      AND grantee = 'app_runtime'
                    """
                ),
                {"tabla": tabla},
            )
            .scalars()
            .all()
        )


def test_app_runtime_solo_lee_e_inserta_en_el_libro(app_runtime_engine: Engine) -> None:
    """CC-06, INV-05, ADR-020: sin `UPDATE` ni `DELETE`."""
    assert _privilegios(app_runtime_engine, "cuenta_movimiento") == {"SELECT", "INSERT"}


def test_app_runtime_actualiza_el_saldo_pero_no_lo_borra(app_runtime_engine: Engine) -> None:
    """`saldo_cuenta` es una materialización verificable (`02` §7.2, ADR-020)."""
    assert _privilegios(app_runtime_engine, "saldo_cuenta") == {"SELECT", "INSERT", "UPDATE"}


# --- comportamiento de la base ---------------------------------------------


def _armar(db_session: Session) -> dict[str, object]:
    organizacion = crear_organizacion(db_session)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, organizacion.id)
    return {
        "organizacion_id": organizacion.id,
        "usuario_id": usuario_id,
        "dispositivo_id": dispositivo_id,
        "cliente_id": crear_cliente(db_session, organizacion.id),
        "proveedor_id": crear_proveedor(db_session, organizacion.id),
    }


def _insertar(db_session: Session, entorno: dict[str, object], **cambios: object) -> None:
    valores: dict[str, object] = {
        "organizacion_id": entorno["organizacion_id"],
        "entidad_id": entorno["cliente_id"],
        "usuario_id": entorno["usuario_id"],
        "dispositivo_id": entorno["dispositivo_id"],
        **cambios,
    }
    insertar_movimiento_sql(db_session, **valores)


def test_un_movimiento_valido_de_cliente_y_de_proveedor_entra_y_calcula_las_columnas_generadas(
    db_session: Session,
) -> None:
    """CC-01, CC-02, CC-03, D6-A."""
    entorno = _armar(db_session)

    _insertar(db_session, entorno)
    _insertar(
        db_session,
        entorno,
        cuenta_tipo="PROVEEDOR",
        entidad_id=entorno["proveedor_id"],
        tipo="COMPRA",
    )

    filas = db_session.execute(
        text(
            """
            SELECT cuenta_tipo, cliente_id, proveedor_id FROM cuenta_movimiento
            WHERE organizacion_id = :org ORDER BY cuenta_tipo
            """
        ),
        {"org": entorno["organizacion_id"]},
    ).all()
    assert [tuple(f) for f in filas] == [
        ("CLIENTE", entorno["cliente_id"], None),
        ("PROVEEDOR", None, entorno["proveedor_id"]),
    ]


@pytest.mark.parametrize("importe", [Decimal("0.00"), Decimal("-10.00")])
def test_el_importe_no_positivo_se_rechaza(db_session: Session, importe: Decimal) -> None:
    """CC-01: `ck_cuenta_movimiento__importe_positivo`."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, importe=importe)

    assert "ck_cuenta_movimiento__importe_positivo" in str(error.value)


CASOS_DE_CHECK = [
    pytest.param({"sentido": "SUMA"}, "ck_cuenta_movimiento__sentido", id="sentido"),
    pytest.param(
        {"cuenta_tipo": "EMPLEADO"}, "ck_cuenta_movimiento__cuenta_tipo", id="cuenta_tipo"
    ),
    pytest.param({"tipo": "AJUSTE"}, "ck_cuenta_movimiento__tipo", id="tipo_fuera_de_catalogo"),
    pytest.param(
        {"tipo": "COMPRA"}, "ck_cuenta_movimiento__tipo_de_cuenta", id="proveedor_en_cliente"
    ),
    pytest.param(
        {"tipo": "VENTA", "cuenta_tipo": "PROVEEDOR", "entidad_id": "PROVEEDOR"},
        "ck_cuenta_movimiento__tipo_de_cuenta",
        id="cliente_en_proveedor",
    ),
]


@pytest.mark.parametrize(("cambios", "check"), CASOS_DE_CHECK)
def test_la_base_rechaza_un_valor_fuera_de_catalogo_o_incoherente(
    db_session: Session, cambios: dict[str, object], check: str
) -> None:
    """D12: la coherencia `cuenta_tipo` x `tipo` queda en la base desde el
    primer día. Búsqueda exacta: `ck_cuenta_movimiento__tipo` es prefijo de
    `ck_cuenta_movimiento__tipo_de_cuenta`."""
    entorno = _armar(db_session)
    if cambios.get("entidad_id") == "PROVEEDOR":
        cambios = {**cambios, "entidad_id": entorno["proveedor_id"]}

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, **cambios)

    violada = re.search(r'violates check constraint "(\w+)"', str(error.value))
    assert violada is not None, str(error.value)
    assert violada.group(1) == check


def test_un_cliente_de_otra_organizacion_no_puede_ser_titular_de_la_cuenta(
    db_session: Session,
) -> None:
    """INV-02, INV-21, D6: la FK compuesta lo rechaza."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    cliente_ajeno = crear_cliente(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, entidad_id=cliente_ajeno)

    assert "fk_cuenta_movimiento__cliente" in str(error.value)


def test_el_id_de_un_proveedor_no_sirve_como_cuenta_de_cliente(db_session: Session) -> None:
    """D6: entidad inexistente para el tipo de cuenta pedido."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, entidad_id=entorno["proveedor_id"])

    assert "fk_cuenta_movimiento__cliente" in str(error.value)


def test_un_proveedor_de_otra_organizacion_no_puede_ser_titular_de_la_cuenta(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    proveedor_ajeno = crear_proveedor(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            entorno,
            cuenta_tipo="PROVEEDOR",
            tipo="COMPRA",
            entidad_id=proveedor_ajeno,
        )

    assert "fk_cuenta_movimiento__proveedor" in str(error.value)


def test_el_dispositivo_es_obligatorio(db_session: Session) -> None:
    """D14: `dispositivo_id uuid NOT NULL`."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, dispositivo_id=None)

    assert "dispositivo_id" in str(error.value)
    assert "not-null" in str(error.value)


def test_un_dispositivo_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    """D14, INV-02: la FK compuesta a `dispositivo`."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    _, dispositivo_ajeno = crear_usuario_y_dispositivo(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, dispositivo_id=dispositivo_ajeno)

    assert "fk_cuenta_movimiento__dispositivo" in str(error.value)


def test_un_dispositivo_inexistente_se_rechaza(db_session: Session) -> None:
    """D14: la FK compuesta a `dispositivo` rechaza también un id que no existe."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, dispositivo_id=uuid4())

    assert "fk_cuenta_movimiento__dispositivo" in str(error.value)


def test_el_saldo_de_una_cuenta_se_puede_crear_y_su_titular_es_un_cliente_de_la_organizacion(
    db_session: Session,
) -> None:
    """D6, D11: la fila de saldo también tiene FK compuestas."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    cliente_ajeno = crear_cliente(db_session, otra.id)

    db_session.execute(
        text(
            """
            INSERT INTO saldo_cuenta (organizacion_id, cuenta_tipo, entidad_id, actualizado_en)
            VALUES (:org, 'CLIENTE', :entidad, now())
            """
        ),
        {"org": entorno["organizacion_id"], "entidad": entorno["cliente_id"]},
    )
    saldo = db_session.execute(
        text("SELECT saldo FROM saldo_cuenta WHERE entidad_id = :entidad"),
        {"entidad": entorno["cliente_id"]},
    ).scalar_one()
    assert saldo == Decimal("0.00")

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text(
                """
                INSERT INTO saldo_cuenta (organizacion_id, cuenta_tipo, entidad_id, actualizado_en)
                VALUES (:org, 'CLIENTE', :entidad, now())
                """
            ),
            {"org": entorno["organizacion_id"], "entidad": cliente_ajeno},
        )
    assert "fk_saldo_cuenta__cliente" in str(error.value)


def test_no_puede_haber_dos_filas_de_saldo_para_la_misma_cuenta(db_session: Session) -> None:
    """D10, D11: la clave primaria compuesta separa la carrera de la primera
    fila."""
    entorno = _armar(db_session)
    consulta = text(
        """
        INSERT INTO saldo_cuenta (organizacion_id, cuenta_tipo, entidad_id, actualizado_en)
        VALUES (:org, 'CLIENTE', :entidad, now())
        """
    )
    parametros = {"org": entorno["organizacion_id"], "entidad": entorno["cliente_id"]}
    db_session.execute(consulta, parametros)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(consulta, parametros)

    assert "pk_saldo_cuenta" in str(error.value)


# --- ciclo de la migración -------------------------------------------------


def _tablas_de_cuentas(motor: Engine) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('cuenta_movimiento', 'saldo_cuenta')
                    """
                )
            )
            .scalars()
            .all()
        )


def test_downgrade_elimina_ambas_tablas_y_upgrade_las_recrea(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`alembic downgrade -1` y `alembic upgrade head` limpios. La base es
    compartida con el resto de la sesión: la prueba DEBE terminar en `head`
    (mismo criterio que `test_alembic_integracion.py`)."""
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}

    def alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=entorno,
            capture_output=True,
            text=True,
        )

    assert _tablas_de_cuentas(_engine_de_sesion) == {"cuenta_movimiento", "saldo_cuenta"}
    try:
        bajada = alembic("downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _tablas_de_cuentas(_engine_de_sesion) == set()
    finally:
        subida = alembic("upgrade", "head")
    assert subida.returncode == 0, subida.stderr
    assert _tablas_de_cuentas(_engine_de_sesion) == {"cuenta_movimiento", "saldo_cuenta"}


def test_el_ciclo_de_migracion_con_datos_sube_baja_y_sube_sin_tocar_lo_ajeno(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`docs/04` §2.1 punto 4: la migración sube y baja limpia sobre una base CON
    datos. Con movimientos y saldos confirmados, `upgrade head -> downgrade -1 ->
    upgrade head` termina en `head`, la bajada solo se lleva las dos tablas del
    change (el cliente, el proveedor y su organización quedan intactos) y la
    subida las recrea vacías y utilizables."""
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno_os = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}

    def alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=entorno_os,
            capture_output=True,
            text=True,
        )

    def contar(tabla: str) -> int:
        with _engine_de_sesion.connect() as conexion:
            return int(conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one())  # noqa: S608

    # Datos confirmados de verdad (la migración corre en otras conexiones).
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(sesion, entorno)
        _insertar(sesion, entorno, sentido="REDUCE", importe=Decimal("20000.00"))
        _insertar(
            sesion,
            entorno,
            cuenta_tipo="PROVEEDOR",
            tipo="COMPRA",
            entidad_id=entorno["proveedor_id"],
        )
        sesion.execute(
            text(
                "INSERT INTO saldo_cuenta (organizacion_id, cuenta_tipo, entidad_id, saldo, "
                "actualizado_en) VALUES (:o, 'CLIENTE', :e, 130000.00, now())"
            ),
            {"o": entorno["organizacion_id"], "e": entorno["cliente_id"]},
        )
        sesion.commit()

    try:
        assert contar("cuenta_movimiento") == 3
        assert contar("saldo_cuenta") == 1

        bajada = alembic("downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _tablas_de_cuentas(_engine_de_sesion) == set()
        # Lo que no es de este change sigue ahí.
        assert contar("cliente") >= 1
        assert contar("proveedor") >= 1
        assert contar("organizacion") >= 1
    finally:
        subida = alembic("upgrade", "head")
    assert subida.returncode == 0, subida.stderr

    try:
        assert _tablas_de_cuentas(_engine_de_sesion) == {"cuenta_movimiento", "saldo_cuenta"}
        assert contar("cuenta_movimiento") == 0
        assert contar("saldo_cuenta") == 0
        # Las tablas recreadas aceptan datos nuevos con sus restricciones.
        with Session(_engine_de_sesion) as sesion:
            _insertar(sesion, entorno)
            sesion.commit()
        assert contar("cuenta_movimiento") == 1
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text("TRUNCATE TABLE organizacion CASCADE"),
            )
