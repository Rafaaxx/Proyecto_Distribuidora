"""Tareas 1.1 a 1.5 (change 15): la revisión `a4b5c6d7e8f9` crea `jornada`, le da sus
privilegios, agrega las dos FK heredadas (`stock_movimiento.jornada_id`,
`comando.jornada_id`) y siembra los motivos de `LIBERACION_JORNADA` (`design.md` D3, D10,
D11, D13).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_transferencias_ajustes_migracion.py`); que el modelo no se desvíe de la migración lo
cubre `test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-05, INV-16, INV-21, TR-06, TR-09, RUT-01, RUT-09, `04` §2.1
punto 4, `design.md` D3, D10, D11, D13.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)

REVISION = "a4b5c6d7e8f9"
REVISION_ANTERIOR = "f3a4b5c6d7e8"  # `transferencias_y_ajustes`, la previa a este change.
MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)

AMBITOS = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "ANULACION_PAGO",
    "ANULACION_TRANSFERENCIA",
    "ANULACION_AJUSTE",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
MOTIVOS_SEMBRADOS = {"Dispositivo perdido o averiado", "Vendedor ausente", "Otro"}

COLUMNAS = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "ubicacion_id": ("uuid", False),
    "estado": ("text", False),
    "operation_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
    "creado_en": ("timestamp with time zone", False),
    "abierta_en": ("timestamp with time zone", False),
    "rendida_en": ("timestamp with time zone", True),
    "rendida_por_id": ("uuid", True),
    "cerrada_en": ("timestamp with time zone", True),
    "cerrada_por_id": ("uuid", True),
    "liberada_en": ("timestamp with time zone", True),
    "liberada_por_id": ("uuid", True),
    "motivo_liberacion_id": ("uuid", True),
    "observacion_liberacion": ("text", True),
}
COLUMNAS_MUTABLES = {
    "estado",
    "rendida_en",
    "rendida_por_id",
    "cerrada_en",
    "cerrada_por_id",
    "liberada_en",
    "liberada_por_id",
    "motivo_liberacion_id",
    "observacion_liberacion",
}
FKS = {
    "fk_jornada__organizacion",
    "fk_jornada__usuario",
    "fk_jornada__dispositivo",
    "fk_jornada__ubicacion",
    "fk_jornada__rendida_por",
    "fk_jornada__cerrada_por",
    "fk_jornada__liberada_por",
    "fk_jornada__motivo_liberacion",
}


# --- consultas al esquema real -------------------------------------------------


def _columnas(motor: Engine, tabla: str) -> dict[str, tuple[str, bool]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :tabla"
            ),
            {"tabla": tabla},
        )
        return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def _restricciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:tabla AS regclass) AND contype = :tipo"
                ),
                {"tabla": f"public.{tabla}", "tipo": tipo},
            ).all()
        )


def _indice(motor: Engine, nombre: str) -> str:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": nombre},
        ).scalar_one()


def _privilegios_de_tabla(motor: Engine, tabla: str) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'public' AND table_name = :t AND grantee = 'app_runtime'"
                ),
                {"t": tabla},
            )
            .scalars()
            .all()
        )


def _columnas_con_update(motor: Engine, tabla: str) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE table_schema = 'public' AND table_name = :t "
                    "AND grantee = 'app_runtime' AND privilege_type = 'UPDATE'"
                ),
                {"t": tabla},
            )
            .scalars()
            .all()
        )


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _tablas_existentes(motor: Engine) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def _cantidad_de_filas(motor: Engine, tabla: str) -> int:
    with motor.connect() as conexion:
        return conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one()


def _motivos_de_ambito(motor: Engine, organizacion_id: UUID, ambito: str) -> list[str]:
    with motor.connect() as conexion:
        return list(
            conexion.execute(
                text(
                    "SELECT nombre FROM motivo WHERE organizacion_id = :o "
                    "AND ambito = :a AND activo ORDER BY nombre"
                ),
                {"o": organizacion_id, "a": ambito},
            )
            .scalars()
            .all()
        )


# --- estructura (tarea 1.1) -----------------------------------------------------


def test_las_columnas_de_jornada_son_las_del_design(_engine_de_sesion: Engine) -> None:
    """D10: columnas de operación de la apertura `NOT NULL`; la rendición, el cierre y la
    liberación (con su observación) nulables."""
    assert _columnas(_engine_de_sesion, "jornada") == COLUMNAS


def test_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02: toda FK entre entidades de negocio incluye `organizacion_id`."""
    foraneas = _restricciones(_engine_de_sesion, "jornada", "f")
    assert set(foraneas) == FKS
    for nombre, definicion in foraneas.items():
        if nombre.endswith("__organizacion"):
            continue
        assert "FOREIGN KEY (organizacion_id," in definicion, nombre


def test_jornada_tiene_unique_organizacion_id(_engine_de_sesion: Engine) -> None:
    unicas = _restricciones(_engine_de_sesion, "jornada", "u")
    assert unicas["ux_jornada__org_id"] == "UNIQUE (organizacion_id, id)"


def test_los_indices_unicos_parciales_son_los_de_d3(_engine_de_sesion: Engine) -> None:
    """INV-16 y D3: ubicación, dispositivo y usuario, sobre `ABIERTA` y `EN_RENDICION`."""
    for nombre, columna in (
        ("ux_jornada__ubicacion_abierta", "ubicacion_id"),
        ("ux_jornada__dispositivo_abierta", "dispositivo_id"),
        ("ux_jornada__usuario_abierta", "usuario_id"),
    ):
        definicion = _indice(_engine_de_sesion, nombre)
        assert "CREATE UNIQUE INDEX" in definicion, nombre
        assert f"(organizacion_id, {columna})" in definicion, nombre
        assert "ABIERTA" in definicion and "EN_RENDICION" in definicion, nombre
        assert "CERRADA" not in definicion and "LIBERADA" not in definicion, nombre


def test_el_indice_de_listado_existe(_engine_de_sesion: Engine) -> None:
    assert "(organizacion_id, abierta_en DESC, id DESC)" in _indice(
        _engine_de_sesion, "ix_jornada__abierta_en"
    )


@pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION", "CERRADA", "LIBERADA"])
def test_el_estado_admite_los_cuatro_valores_de_la_maquina(
    db_session: Session, estado: str
) -> None:
    """`01` §18: los cuatro estados de la jornada se aceptan con sus datos coherentes."""
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, estado))


@pytest.mark.parametrize("estado", ["PENDIENTE", "abierta", ""])
def test_el_estado_rechaza_un_valor_inventado(db_session: Session, estado: str) -> None:
    entorno = _armar(db_session)
    _rechaza(db_session, {**_jornada(entorno, "ABIERTA"), "estado": estado}, '"ck_jornada__estado"')


@pytest.mark.parametrize("columna", ["usuario_id", "dispositivo_id", "ubicacion_id", "abierta_en"])
def test_las_columnas_de_la_apertura_son_obligatorias(db_session: Session, columna: str) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, "jornada", {**_jornada(entorno, "ABIERTA"), columna: None})
    assert "not-null" in str(error.value) or "null value" in str(error.value)


def test_una_referencia_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    """INV-02: usuario, dispositivo, ubicación y motivo ajenos violan la FK compuesta."""
    entorno = _armar(db_session)
    ajeno = _armar(db_session)
    _rechaza(
        db_session,
        _jornada(entorno, "ABIERTA", usuario_id=ajeno.usuario_id),
        "fk_jornada__usuario",
    )
    _rechaza(
        db_session,
        _jornada(entorno, "ABIERTA", dispositivo_id=ajeno.dispositivo_id),
        "fk_jornada__dispositivo",
    )
    _rechaza(
        db_session,
        _jornada(entorno, "ABIERTA", ubicacion_id=ajeno.vehiculo_id),
        "fk_jornada__ubicacion",
    )
    _rechaza(
        db_session,
        _jornada(entorno, "LIBERADA", motivo_liberacion_id=ajeno.motivo_id),
        "fk_jornada__motivo_liberacion",
    )
    _rechaza(
        db_session,
        _jornada(entorno, "EN_RENDICION", rendida_por_id=ajeno.usuario_id),
        "fk_jornada__rendida_por",
    )


@pytest.mark.parametrize(
    ("estado", "cambios"),
    [
        # LIBERADA sin motivo, sin usuario o sin momento (RUT-09).
        ("LIBERADA", {"motivo_liberacion_id": None}),
        ("LIBERADA", {"liberada_por_id": None}),
        ("LIBERADA", {"liberada_en": None}),
        # ABIERTA con datos de otra transición.
        ("ABIERTA", {"cerrada_en": MOMENTO}),
        ("ABIERTA", {"rendida_en": MOMENTO}),
        ("ABIERTA", {"liberada_en": MOMENTO}),
        ("ABIERTA", {"observacion_liberacion": "algo"}),
        # EN_RENDICION sin quién rindió, o con cierre.
        ("EN_RENDICION", {"rendida_por_id": None}),
        ("EN_RENDICION", {"rendida_en": None}),
        ("EN_RENDICION", {"cerrada_en": MOMENTO}),
        # CERRADA sin cierre, sin quién cerró o sin rendición.
        ("CERRADA", {"cerrada_en": None}),
        ("CERRADA", {"cerrada_por_id": None}),
        ("CERRADA", {"rendida_en": None, "rendida_por_id": None}),
        ("CERRADA", {"liberada_en": MOMENTO}),
    ],
)
def test_el_estado_incoherente_se_rechaza_en_la_base(
    db_session: Session, estado: str, cambios: dict[str, object]
) -> None:
    """D10: los datos de rendición, cierre y liberación están presentes si y solo si el
    estado los implica."""
    entorno = _armar(db_session)
    valores = _jornada(entorno, estado, **cambios)
    _rechaza(db_session, valores, "ck_jornada__estado_coherente")


def test_una_liberada_desde_una_jornada_abierta_o_en_rendicion_es_coherente(
    db_session: Session,
) -> None:
    """RUT-09: se libera una `ABIERTA` (sin rendición) o una `EN_RENDICION` (con ella)."""
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, "LIBERADA"))
    otra = _armar(db_session)
    _insertar(
        db_session,
        "jornada",
        _jornada(
            otra,
            "LIBERADA",
            rendida_en=MOMENTO,
            rendida_por_id=otra.usuario_id,
            observacion_liberacion="x",
        ),
    )


@pytest.mark.parametrize("largo", [0, 501])
def test_la_observacion_de_la_liberacion_va_de_1_a_500_caracteres(
    db_session: Session, largo: int
) -> None:
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        _jornada(entorno, "LIBERADA", observacion_liberacion="x" * largo),
        "ck_jornada__observacion_liberacion",
    )
    _insertar(
        db_session, "jornada", _jornada(entorno, "LIBERADA", observacion_liberacion="x" * 500)
    )


@pytest.mark.parametrize("ocupa", ["ABIERTA", "EN_RENDICION"])
def test_inv16_una_segunda_jornada_no_cerrada_sobre_la_ubicacion_se_rechaza(
    db_session: Session, ocupa: str
) -> None:
    """INV-16: una segunda fila `ABIERTA` o `EN_RENDICION` sobre la misma ubicación se
    rechaza, sea cual sea el estado de la primera y de la segunda."""
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, ocupa))
    for segunda in ("ABIERTA", "EN_RENDICION"):
        _rechaza(
            db_session,
            _jornada(
                entorno,
                segunda,
                usuario_id=entorno.usuario_2_id,
                dispositivo_id=entorno.dispositivo_2_id,
            ),
            "ux_jornada__ubicacion_abierta",
        )


@pytest.mark.parametrize("terminada", ["CERRADA", "LIBERADA"])
def test_inv16_una_jornada_terminada_no_ocupa_la_ubicacion(
    db_session: Session, terminada: str
) -> None:
    """INV-16: una `CERRADA` o `LIBERADA` no ocupa: puede haber varias y, además, una
    abierta sobre la misma ubicación, el mismo usuario y el mismo dispositivo."""
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, terminada))
    _insertar(db_session, "jornada", _jornada(entorno, terminada))
    _insertar(db_session, "jornada", _jornada(entorno, "ABIERTA"))


def test_d3_un_usuario_y_un_dispositivo_tienen_una_sola_jornada_no_cerrada(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, "ABIERTA"))
    _rechaza(
        db_session,
        _jornada(
            entorno,
            "ABIERTA",
            ubicacion_id=entorno.vehiculo_2_id,
            dispositivo_id=entorno.dispositivo_2_id,
        ),
        "ux_jornada__usuario_abierta",
    )
    _rechaza(
        db_session,
        _jornada(
            entorno,
            "ABIERTA",
            ubicacion_id=entorno.vehiculo_2_id,
            usuario_id=entorno.usuario_2_id,
        ),
        "ux_jornada__dispositivo_abierta",
    )
    # Con otro usuario, otro dispositivo y otra ubicación, sí se puede.
    _insertar(
        db_session,
        "jornada",
        _jornada(
            entorno,
            "ABIERTA",
            ubicacion_id=entorno.vehiculo_2_id,
            usuario_id=entorno.usuario_2_id,
            dispositivo_id=entorno.dispositivo_2_id,
        ),
    )


# --- privilegios (tarea 1.2, INV-05, TR-06) -----------------------------------------


def test_inv05_app_runtime_solo_tiene_select_e_insert_en_jornada(
    app_runtime_engine: Engine,
) -> None:
    """Sin `DELETE`; el `UPDATE` es solo por columna (abajo), no de tabla."""
    assert _privilegios_de_tabla(app_runtime_engine, "jornada") == {"SELECT", "INSERT"}


def test_inv05_app_runtime_solo_actualiza_el_estado_y_las_columnas_de_transicion(
    app_runtime_engine: Engine,
) -> None:
    assert _columnas_con_update(app_runtime_engine, "jornada") == COLUMNAS_MUTABLES


def test_inv05_app_runtime_no_puede_borrar_una_jornada(app_runtime_engine: Engine) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM jornada"))
    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("ubicacion_id", "ubicacion_id"),
        ("usuario_id", "usuario_id"),
        ("dispositivo_id", "dispositivo_id"),
        ("abierta_en", "now()"),
        ("operation_id", "operation_id"),
        ("organizacion_id", "organizacion_id"),
    ],
)
def test_inv05_app_runtime_no_puede_reescribir_los_datos_de_la_apertura(
    app_runtime_engine: Engine, columna: str, valor: str
) -> None:
    """TR-06: un `UPDATE` de ubicación, usuario, dispositivo o momento de apertura se
    rechaza por falta de privilegios, aun sobre una tabla vacía."""
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE jornada SET {columna} = {valor}"))
    assert "permission denied" in str(error.value)


def test_app_runtime_actualiza_el_estado_de_una_jornada_con_su_transicion(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """Control positivo: lo que sí puede cambiar el runtime (la rendición) funciona."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        jornada = _jornada(entorno, "ABIERTA")
        _insertar(sesion, "jornada", jornada)
        sesion.commit()
    try:
        with app_runtime_engine.begin() as conexion:
            actualizadas = conexion.execute(
                text(
                    "UPDATE jornada SET estado = 'EN_RENDICION', rendida_en = :m, "
                    "rendida_por_id = :u WHERE organizacion_id = :o AND id = :id"
                ),
                {
                    "m": OTRO_MOMENTO,
                    "u": entorno.usuario_id,
                    "o": entorno.organizacion_id,
                    "id": jornada["id"],
                },
            ).rowcount
        assert actualizadas == 1
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


@pytest.mark.parametrize(
    ("tabla", "esperados"),
    [
        ("stock_movimiento", {"SELECT", "INSERT"}),
        ("auditoria", {"SELECT", "INSERT"}),
        ("comando", {"SELECT", "INSERT", "UPDATE"}),
    ],
)
def test_los_libros_conservan_sus_privilegios(
    app_runtime_engine: Engine, tabla: str, esperados: set[str]
) -> None:
    """Tarea 1.2: ni `stock_movimiento`, ni `comando` ni `auditoria` ganan `DELETE` ni
    pierden lo que tenían (INV-05)."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == esperados


# --- FK heredadas (tarea 1.3, D11) --------------------------------------------------


def test_las_dos_fk_heredadas_son_compuestas_a_jornada(_engine_de_sesion: Engine) -> None:
    for tabla, nombre in (
        ("stock_movimiento", "fk_stock_movimiento__jornada"),
        ("comando", "fk_comando__jornada"),
    ):
        definicion = _restricciones(_engine_de_sesion, tabla, "f")[nombre]
        assert "FOREIGN KEY (organizacion_id, jornada_id)" in definicion
        assert "REFERENCES jornada(organizacion_id, id)" in definicion
        with _engine_de_sesion.connect() as conexion:
            validada = conexion.execute(
                text("SELECT convalidated FROM pg_constraint WHERE conname = :n"), {"n": nombre}
            ).scalar_one()
        assert validada is True, nombre


def test_inv02_un_movimiento_con_una_jornada_inexistente_o_ajena_se_rechaza(
    db_session: Session,
) -> None:
    """INV-02, INV-21: la base rechaza una jornada que no existe y una de otra
    organización; con `jornada_id` nulo se acepta."""
    entorno = _armar(db_session)
    ajeno = _armar(db_session)
    jornada_ajena = _jornada(ajeno, "ABIERTA")
    _insertar(db_session, "jornada", jornada_ajena)

    for jornada_id in (uuid4(), jornada_ajena["id"]):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            insertar_stock_movimiento_sql(
                db_session,
                organizacion_id=entorno.organizacion_id,
                producto_id=entorno.producto_id,
                ubicacion_id=entorno.vehiculo_id,
                usuario_id=entorno.usuario_id,
                dispositivo_id=entorno.dispositivo_id,
                jornada_id=jornada_id,
            )
        assert "fk_stock_movimiento__jornada" in str(error.value)

    propia = _jornada(entorno, "ABIERTA")
    _insertar(db_session, "jornada", propia)
    for jornada_id in (propia["id"], None):
        insertar_stock_movimiento_sql(
            db_session,
            organizacion_id=entorno.organizacion_id,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.vehiculo_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            jornada_id=jornada_id,
        )


def test_inv21_un_comando_con_una_jornada_inexistente_o_ajena_se_rechaza(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    ajeno = _armar(db_session)
    jornada_ajena = _jornada(ajeno, "ABIERTA")
    _insertar(db_session, "jornada", jornada_ajena)

    for jornada_id in (uuid4(), jornada_ajena["id"]):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar_comando(db_session, entorno, jornada_id)
        assert "fk_comando__jornada" in str(error.value)

    propia = _jornada(entorno, "ABIERTA")
    _insertar(db_session, "jornada", propia)
    _insertar_comando(db_session, entorno, propia["id"])
    _insertar_comando(db_session, entorno, None)


@pytest.mark.parametrize("tabla_huerfana", ["stock_movimiento", "comando"])
def test_la_migracion_aborta_sin_tocar_nada_si_hay_filas_con_jornada(
    database_url: str, _engine_de_sesion: Engine, tabla_huerfana: str
) -> None:
    """D11: con una fila con `jornada_id` no nulo en cualquiera de las dos tablas, el
    `upgrade` falla con un mensaje que dice la tabla y la cantidad, sin haber modificado
    ninguna fila (TR-06) y sin dejar la tabla `jornada`."""
    bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
    assert bajada.returncode == 0, bajada.stderr
    huerfana = uuid4()
    try:
        with Session(_engine_de_sesion) as sesion:
            entorno = _armar_sin_jornadas(sesion)
            if tabla_huerfana == "stock_movimiento":
                for _ in range(2):
                    insertar_stock_movimiento_sql(
                        sesion,
                        organizacion_id=entorno.organizacion_id,
                        producto_id=entorno.producto_id,
                        ubicacion_id=entorno.vehiculo_id,
                        usuario_id=entorno.usuario_id,
                        dispositivo_id=entorno.dispositivo_id,
                        jornada_id=huerfana,
                    )
            else:
                _insertar_comando(sesion, entorno, huerfana)
            sesion.commit()

        subida = _alembic(database_url, "upgrade", "head")

        assert subida.returncode != 0
        esperado = "2" if tabla_huerfana == "stock_movimiento" else "1"
        assert tabla_huerfana in subida.stderr
        assert f"{esperado} fila" in subida.stderr
        assert "jornada" not in _tablas_existentes(_engine_de_sesion)
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(
                text(f"SELECT count(*) FROM {tabla_huerfana} WHERE jornada_id = :j"),
                {"j": huerfana},
            ).scalar_one() == int(esperado)
            assert (
                conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == REVISION_ANTERIOR
            )
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        _dejar_en_head(database_url, _engine_de_sesion)


# --- motivos sembrados (tarea 1.4, D13) -----------------------------------------------


def test_la_migracion_siembra_los_motivos_de_liberacion_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D13: una organización sin motivos de `LIBERACION_JORNADA` recibe los tres; una que ya
    tiene alguno no recibe duplicados ni los sembrados (idempotente); `ck_motivo__ambito` no
    cambia (TR-09)."""
    with Session(_engine_de_sesion) as sesion:
        vacia = crear_organizacion(sesion).id
        con_propios = crear_organizacion(sesion).id
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'LIBERACION_JORNADA', 'Propio', true, :m, :m)"
            ),
            {"id": uuid4(), "org": con_propios, "m": MOMENTO},
        )
        sesion.commit()

    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        assert set(_motivos_de_ambito(_engine_de_sesion, vacia, "LIBERACION_JORNADA")) == (
            MOTIVOS_SEMBRADOS
        )
        assert _motivos_de_ambito(_engine_de_sesion, con_propios, "LIBERACION_JORNADA") == [
            "Propio"
        ]
        # Idempotencia: otro ciclo no duplica.
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert len(_motivos_de_ambito(_engine_de_sesion, vacia, "LIBERACION_JORNADA")) == 3
        assert _motivos_de_ambito(_engine_de_sesion, con_propios, "LIBERACION_JORNADA") == [
            "Propio"
        ]
        definicion = _restricciones(_engine_de_sesion, "motivo", "c")["ck_motivo__ambito"]
        assert all(f"'{ambito}'" in definicion for ambito in AMBITOS)
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_sembrado_es_idempotente_al_ejecutarse_dos_veces(_engine_de_sesion: Engine) -> None:
    """D13: se ejecuta la función de siembra de la revisión dos veces sobre la base ya
    migrada, como lo hace `upgrade` sobre las organizaciones existentes."""
    archivo = next((BACKEND_DIR / "alembic" / "versions").glob(f"{REVISION}_*.py"))
    especificacion = importlib.util.spec_from_file_location("revision_15", archivo)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)

    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        sesion.commit()
    try:
        for _ in range(2):
            with (
                _engine_de_sesion.begin() as conexion,
                Operations.context(MigrationContext.configure(conexion)),
            ):
                modulo._sembrar_motivos()
        assert sorted(
            _motivos_de_ambito(_engine_de_sesion, organizacion_id, "LIBERACION_JORNADA")
        ) == sorted(MOTIVOS_SEMBRADOS)
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


# --- ciclo (tarea 1.5) ------------------------------------------------------------


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4 y D11: sube y baja limpio con stock inicial, una compra, una
    transferencia, un ajuste y tres jornadas (abierta, cerrada y liberada), sin ninguna fila de
    `stock_movimiento` ni de `comando` con `jornada_id`. No modifica ninguna fila de los libros
    ni de `comando`. El `downgrade` pierde, por diseño, las jornadas, las dos FK y los motivos
    sembrados de `LIBERACION_JORNADA`. Con filas que sí llevan `jornada_id`, ver
    `test_el_downgrade_conserva_el_jornada_id_y_la_subida_siguiente_aborta`."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar_sin_jornadas(sesion)
        proveedor_id = crear_proveedor(sesion, entorno.organizacion_id)
        stock_inicial = insertar_stock_movimiento_sql(
            sesion,
            organizacion_id=entorno.organizacion_id,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.deposito_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            cantidad_base=120,
            costo_unitario=Decimal("1050.000000"),
        )
        assert stock_inicial is not None
        _insertar(
            sesion,
            "compra",
            {
                "id": uuid4(),
                "organizacion_id": entorno.organizacion_id,
                "proveedor_id": proveedor_id,
                "ubicacion_id": entorno.deposito_id,
                "fecha": MOMENTO.date(),
                "condicion": "CONTADO",
                "total_neto": Decimal("100.00"),
                "total_factura": Decimal("121.00"),
                "estado": "CONFIRMADA",
                **_operacion(entorno),
            },
        )
        transferencia = {
            "id": uuid4(),
            "organizacion_id": entorno.organizacion_id,
            "ubicacion_origen_id": entorno.deposito_id,
            "ubicacion_destino_id": entorno.vehiculo_id,
            "estado": "CONFIRMADA",
            **_operacion(entorno),
        }
        _insertar(sesion, "transferencia", transferencia)
        _insertar(
            sesion,
            "ajuste_stock",
            {
                "id": uuid4(),
                "organizacion_id": entorno.organizacion_id,
                "ubicacion_id": entorno.deposito_id,
                "motivo_id": crear_motivo_sql(sesion, entorno.organizacion_id),
                "estado": "CONFIRMADA",
                **_operacion(entorno),
            },
        )
        abierta = _jornada(entorno, "ABIERTA")
        cerrada = _jornada(
            entorno,
            "CERRADA",
            ubicacion_id=entorno.vehiculo_2_id,
            usuario_id=entorno.usuario_2_id,
            dispositivo_id=entorno.dispositivo_2_id,
        )
        liberada = _jornada(entorno, "LIBERADA", ubicacion_id=entorno.vehiculo_2_id)
        for fila in (abierta, cerrada, liberada):
            _insertar(sesion, "jornada", fila)
        _insertar_comando(sesion, entorno, None)
        sesion.commit()
        organizacion_id = entorno.organizacion_id

    def instantanea() -> dict[str, list[tuple[object, ...]]]:
        with _engine_de_sesion.connect() as conexion:
            return {
                "stock_movimiento": [
                    tuple(f)
                    for f in conexion.execute(
                        text(
                            "SELECT id, cantidad_base, costo_unitario, tipo, origen_id, "
                            "operation_id, occurred_at, jornada_id "
                            "FROM stock_movimiento ORDER BY id"
                        )
                    )
                ],
                "comando": [
                    tuple(f)
                    for f in conexion.execute(
                        text(
                            "SELECT id, tipo, huella, estado, secuencia, jornada_id "
                            "FROM comando ORDER BY id"
                        )
                    )
                ],
                "auditoria": [
                    tuple(f) for f in conexion.execute(text("SELECT id FROM auditoria ORDER BY id"))
                ],
            }

    antes = instantanea()
    assert antes["stock_movimiento"] and antes["comando"]

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` pierde, escrito explícito (D11, D13).
        assert "jornada" not in _tablas_existentes(_engine_de_sesion)
        assert "fk_stock_movimiento__jornada" not in _restricciones(
            _engine_de_sesion, "stock_movimiento", "f"
        )
        assert "fk_comando__jornada" not in _restricciones(_engine_de_sesion, "comando", "f")
        assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, "LIBERACION_JORNADA") == []
        # Lo que NO toca: ninguna fila de los libros ni de `comando`.
        assert instantanea() == antes

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert "jornada" in _tablas_existentes(_engine_de_sesion)
        assert _cantidad_de_filas(_engine_de_sesion, "jornada") == 0
        assert set(
            _motivos_de_ambito(_engine_de_sesion, organizacion_id, "LIBERACION_JORNADA")
        ) == (MOTIVOS_SEMBRADOS)
        assert instantanea() == antes
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_conserva_el_jornada_id_y_la_subida_siguiente_aborta(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D11 y Migration Plan de `design.md`: el `downgrade` NO modifica filas de
    `stock_movimiento` ni de `comando` (TR-06): los movimientos y comandos conservan su
    `jornada_id`, ahora sin referencia. Subir de nuevo con esas filas presentes aborta con el
    mensaje del conteo (tabla y cantidad) y no cambia nada."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar_sin_jornadas(sesion)
        jornada = _jornada(entorno, "ABIERTA")
        _insertar(sesion, "jornada", jornada)
        for _ in range(2):
            insertar_stock_movimiento_sql(
                sesion,
                organizacion_id=entorno.organizacion_id,
                producto_id=entorno.producto_id,
                ubicacion_id=entorno.vehiculo_id,
                usuario_id=entorno.usuario_id,
                dispositivo_id=entorno.dispositivo_id,
                cantidad_base=10,
                jornada_id=jornada["id"],
            )
        _insertar_comando(sesion, entorno, jornada["id"])
        sesion.commit()
        jornada_id = jornada["id"]

    def con_jornada() -> dict[str, list[object]]:
        with _engine_de_sesion.connect() as conexion:
            return {
                tabla: sorted(
                    conexion.execute(
                        text(f"SELECT id, jornada_id FROM {tabla} WHERE jornada_id IS NOT NULL")
                    ).all()
                )
                for tabla in ("stock_movimiento", "comando")
            }

    antes = con_jornada()
    assert [len(filas) for filas in antes.values()] == [2, 1]
    assert {fila[1] for filas in antes.values() for fila in filas} == {jornada_id}

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert "jornada" not in _tablas_existentes(_engine_de_sesion)
        # Mismos ids y mismo `jornada_id`: el `downgrade` no modificó ninguna fila.
        assert con_jornada() == antes

        subida = _alembic(database_url, "upgrade", "head")

        assert subida.returncode != 0
        assert "stock_movimiento: 2 fila(s)" in subida.stderr
        assert "comando: 1 fila(s)" in subida.stderr
        assert "jornada" not in _tablas_existentes(_engine_de_sesion)
        assert con_jornada() == antes
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        _dejar_en_head(database_url, _engine_de_sesion)


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    usuario_2_id: UUID
    dispositivo_2_id: UUID
    deposito_id: UUID
    vehiculo_id: UUID
    vehiculo_2_id: UUID
    producto_id: UUID
    motivo_id: UUID


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones},
        capture_output=True,
        text=True,
    )


def _dejar_en_head(database_url: str, motor: Engine) -> None:
    """La base es compartida con el resto de la sesión: toda prueba que mueve Alembic
    DEBE terminar en `head` y sin filas propias."""
    subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _armar_sin_jornadas(sesion: Session) -> Entorno:
    """Una organización con dos usuarios con su dispositivo, un depósito, dos vehículos
    (requieren toma), un producto y un motivo de `LIBERACION_JORNADA`. Sirve también cuando
    la tabla `jornada` todavía no existe: no la toca."""
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    usuario_2_id, dispositivo_2_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        usuario_2_id=usuario_2_id,
        dispositivo_2_id=dispositivo_2_id,
        deposito_id=crear_ubicacion_sql(sesion, organizacion.id),
        vehiculo_id=crear_ubicacion_sql(
            sesion, organizacion.id, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        ),
        vehiculo_2_id=crear_ubicacion_sql(
            sesion, organizacion.id, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        ),
        producto_id=crear_producto_sql(sesion, organizacion.id),
        motivo_id=crear_motivo_sql(
            sesion, organizacion.id, ambito="LIBERACION_JORNADA", nombre="Otro"
        ),
    )


_armar = _armar_sin_jornadas


def _operacion(entorno: Entorno) -> dict[str, object]:
    return {
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }


def _jornada(entorno: Entorno, estado: str, **cambios: object) -> dict[str, object]:
    """Una jornada coherente con su estado; `cambios` pisa cualquier columna."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "ubicacion_id": entorno.vehiculo_id,
        "estado": estado,
        "operation_id": uuid4(),
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
        "creado_en": MOMENTO,
        "abierta_en": MOMENTO,
    }
    if estado in {"EN_RENDICION", "CERRADA"}:
        valores.update(rendida_en=OTRO_MOMENTO, rendida_por_id=entorno.usuario_2_id)
    if estado == "CERRADA":
        valores.update(cerrada_en=OTRO_MOMENTO, cerrada_por_id=entorno.usuario_2_id)
    if estado == "LIBERADA":
        valores.update(
            liberada_en=OTRO_MOMENTO,
            liberada_por_id=entorno.usuario_2_id,
            motivo_liberacion_id=entorno.motivo_id,
        )
    valores.update(cambios)
    return valores


def _insertar_comando(sesion: Session, entorno: Entorno, jornada_id: object) -> None:
    sesion.execute(
        text(
            "INSERT INTO comando (id, organizacion_id, operation_id, tipo, version, modo, "
            "usuario_id, dispositivo_id, jornada_id, secuencia, huella, app_version, estado, "
            "resultado, error_codigo, occurred_at, registered_at) VALUES (:id, :org, :op, "
            "'PRUEBA_15', 1, 'ONLINE', :u, :d, :j, 1, :h, '1.0.0', 'ACEPTADO', NULL, NULL, "
            ":m, :m)"
        ),
        {
            "id": uuid4(),
            "org": entorno.organizacion_id,
            "op": uuid4(),
            "u": entorno.usuario_id,
            "d": entorno.dispositivo_id,
            "j": jornada_id,
            "h": f"huella-{uuid4().hex}",
            "m": MOMENTO,
        },
    )


def _rechaza(sesion: Session, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, "jornada", valores)
    assert restriccion in str(error.value)
