"""Tareas 1.1 a 1.4 (change 14): la revisión `f3a4b5c6d7e8` crea `transferencia`,
`transferencia_linea`, `ajuste_stock` y `ajuste_stock_linea`, amplía los ámbitos de
motivo (`ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE`) y da de alta el permiso
`ANULAR_TRANSFERENCIA` (`design.md` D5, D5.3, D8).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_pagos_proveedor_migracion.py`); que el modelo no se desvíe de la migración lo
cubre `test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-03, INV-04, INV-05, INV-21, STK-07, TR-06, TR-09,
`design.md` D1, D5, D5.3, D8.
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
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)

REVISION = "f3a4b5c6d7e8"
REVISION_ANTERIOR = "e2f3a4b5c6d7"  # `listas_de_precios`, la previa a este change.
MOMENTO = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

AMBITOS_ANTERIORES = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "ANULACION_PAGO",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
AMBITOS_NUEVOS = ("ANULACION_TRANSFERENCIA", "ANULACION_AJUSTE")
MOTIVOS_SEMBRADOS = {"Error de carga", "Otro"}
PERMISO = "ANULAR_TRANSFERENCIA"

COLUMNAS_COMUNES = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "estado": ("text", False),
    "anulacion_motivo_id": ("uuid", True),
    "operation_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
    "observacion": ("text", True),
}
COLUMNAS_TRANSFERENCIA = {
    **COLUMNAS_COMUNES,
    "ubicacion_origen_id": ("uuid", False),
    "ubicacion_destino_id": ("uuid", False),
    "anulada_en": ("timestamp with time zone", True),
    "anulada_por_id": ("uuid", True),
}
COLUMNAS_AJUSTE = {
    **COLUMNAS_COMUNES,
    "ubicacion_id": ("uuid", False),
    "motivo_id": ("uuid", False),
    "anulado_en": ("timestamp with time zone", True),
    "anulado_por_id": ("uuid", True),
}
COLUMNAS_LINEA_TRANSFERENCIA = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "transferencia_id": ("uuid", False),
    "orden": ("integer", False),
    "producto_id": ("uuid", False),
    "cantidad_base": ("integer", False),
}
COLUMNAS_LINEA_AJUSTE = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "ajuste_id": ("uuid", False),
    "orden": ("integer", False),
    "producto_id": ("uuid", False),
    "cantidad_base": ("integer", False),
    "costo_unitario": ("numeric", True),
}

COLUMNAS_MUTABLES = {
    "transferencia": {"estado", "anulacion_motivo_id", "anulada_en", "anulada_por_id"},
    "ajuste_stock": {"estado", "anulacion_motivo_id", "anulado_en", "anulado_por_id"},
}

FKS = {
    "transferencia": {
        "fk_transferencia__organizacion",
        "fk_transferencia__origen",
        "fk_transferencia__destino",
        "fk_transferencia__usuario",
        "fk_transferencia__dispositivo",
        "fk_transferencia__anulacion_motivo",
        "fk_transferencia__anulada_por",
    },
    "transferencia_linea": {
        "fk_transferencia_linea__organizacion",
        "fk_transferencia_linea__transferencia",
        "fk_transferencia_linea__producto",
    },
    "ajuste_stock": {
        "fk_ajuste_stock__organizacion",
        "fk_ajuste_stock__ubicacion",
        "fk_ajuste_stock__motivo",
        "fk_ajuste_stock__usuario",
        "fk_ajuste_stock__dispositivo",
        "fk_ajuste_stock__anulacion_motivo",
        "fk_ajuste_stock__anulado_por",
    },
    "ajuste_stock_linea": {
        "fk_ajuste_stock_linea__organizacion",
        "fk_ajuste_stock_linea__ajuste",
        "fk_ajuste_stock_linea__producto",
    },
}

INDICES = {
    "ix_transferencia__fecha": "(organizacion_id, occurred_at DESC, id DESC)",
    "ix_transferencia__origen_fecha": (
        "(organizacion_id, ubicacion_origen_id, occurred_at DESC, id DESC)"
    ),
    "ix_transferencia__destino_fecha": (
        "(organizacion_id, ubicacion_destino_id, occurred_at DESC, id DESC)"
    ),
    "ix_ajuste_stock__fecha": "(organizacion_id, occurred_at DESC, id DESC)",
    "ix_ajuste_stock__ubicacion_fecha": (
        "(organizacion_id, ubicacion_id, occurred_at DESC, id DESC)"
    ),
    "ix_ajuste_stock__motivo_fecha": "(organizacion_id, motivo_id, occurred_at DESC, id DESC)",
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


@pytest.mark.parametrize(
    ("tabla", "esperadas"),
    [
        ("transferencia", COLUMNAS_TRANSFERENCIA),
        ("transferencia_linea", COLUMNAS_LINEA_TRANSFERENCIA),
        ("ajuste_stock", COLUMNAS_AJUSTE),
        ("ajuste_stock_linea", COLUMNAS_LINEA_AJUSTE),
    ],
)
def test_las_columnas_de_cada_tabla_son_las_del_design(
    _engine_de_sesion: Engine, tabla: str, esperadas: dict[str, tuple[str, bool]]
) -> None:
    """D8: columnas de operación `NOT NULL`, `observacion` y `costo_unitario` nulables,
    cantidades `integer` (INV-04) y costo `numeric` (INV-03)."""
    assert _columnas(_engine_de_sesion, tabla) == esperadas


def test_el_costo_de_la_linea_del_ajuste_es_numeric_18_6(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        precision = conexion.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name = 'ajuste_stock_linea' AND column_name = 'costo_unitario'"
            )
        ).one()
    assert tuple(precision) == (18, 6)


@pytest.mark.parametrize("tabla", list(FKS))
def test_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02: toda FK entre entidades de negocio incluye `organizacion_id`."""
    foraneas = _restricciones(_engine_de_sesion, tabla, "f")
    assert set(foraneas) == FKS[tabla]
    for nombre, definicion in foraneas.items():
        if nombre.endswith("__organizacion"):
            continue
        assert "FOREIGN KEY (organizacion_id," in definicion, nombre


@pytest.mark.parametrize("tabla", list(FKS))
def test_cada_tabla_tiene_unique_organizacion_id(_engine_de_sesion: Engine, tabla: str) -> None:
    unicas = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicas[f"ux_{tabla}__org_id"] == "UNIQUE (organizacion_id, id)"


@pytest.mark.parametrize(("nombre", "fragmento"), list(INDICES.items()))
def test_los_indices_de_listado_existen(
    _engine_de_sesion: Engine, nombre: str, fragmento: str
) -> None:
    assert fragmento in _indice(_engine_de_sesion, nombre)


def test_el_orden_de_la_linea_es_unico_por_cabecera(db_session: Session) -> None:
    entorno = _armar(db_session)
    transferencia = _transferencia(entorno)
    _insertar(db_session, "transferencia", transferencia)
    _insertar(db_session, "transferencia_linea", _linea_t(entorno, transferencia["id"], orden=1))
    _rechaza(
        db_session,
        "transferencia_linea",
        _linea_t(entorno, transferencia["id"], orden=1, producto_id=entorno.producto_2_id),
        "ux_transferencia_linea__transferencia_orden",
    )
    ajuste = _ajuste(entorno)
    _insertar(db_session, "ajuste_stock", ajuste)
    _insertar(db_session, "ajuste_stock_linea", _linea_a(entorno, ajuste["id"], orden=1))
    _rechaza(
        db_session,
        "ajuste_stock_linea",
        _linea_a(entorno, ajuste["id"], orden=1, producto_id=entorno.producto_2_id),
        "ux_ajuste_stock_linea__ajuste_orden",
    )


def test_origen_y_destino_distintos(db_session: Session) -> None:
    """STK-07, `03` §9: `CHECK (ubicacion_origen_id <> ubicacion_destino_id)`."""
    entorno = _armar(db_session)
    _insertar(db_session, "transferencia", _transferencia(entorno))
    _rechaza(
        db_session,
        "transferencia",
        _transferencia(entorno, ubicacion_destino_id=entorno.origen_id),
        "ck_transferencia__ubicaciones_distintas",
    )


@pytest.mark.parametrize("cantidad", [0, -5])
def test_la_cantidad_de_la_linea_de_transferencia_es_positiva(
    db_session: Session, cantidad: int
) -> None:
    """INV-04: `CHECK (cantidad_base > 0)` en la transferencia."""
    entorno = _armar(db_session)
    transferencia = _transferencia(entorno)
    _insertar(db_session, "transferencia", transferencia)
    _rechaza(
        db_session,
        "transferencia_linea",
        _linea_t(entorno, transferencia["id"], cantidad_base=cantidad),
        "ck_transferencia_linea__cantidad_base",
    )


def test_la_cantidad_de_la_linea_de_ajuste_es_distinta_de_cero(db_session: Session) -> None:
    """INV-04: `CHECK (cantidad_base <> 0)`; los dos signos se admiten y el costo es
    nulable (D3)."""
    entorno = _armar(db_session)
    ajuste = _ajuste(entorno)
    _insertar(db_session, "ajuste_stock", ajuste)
    _rechaza(
        db_session,
        "ajuste_stock_linea",
        _linea_a(entorno, ajuste["id"], cantidad_base=0),
        "ck_ajuste_stock_linea__cantidad_base",
    )
    _insertar(db_session, "ajuste_stock_linea", _linea_a(entorno, ajuste["id"], cantidad_base=-6))
    _insertar(
        db_session,
        "ajuste_stock_linea",
        _linea_a(
            entorno,
            ajuste["id"],
            orden=2,
            producto_id=entorno.producto_2_id,
            cantidad_base=2,
            costo_unitario=None,
        ),
    )


def test_una_referencia_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    """INV-02: una ubicación, un producto o un motivo ajenos violan la FK compuesta."""
    entorno = _armar(db_session)
    ajena = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            "transferencia",
            _transferencia(entorno, ubicacion_destino_id=ajena.origen_id),
        )
    assert "fk_transferencia__destino" in str(error.value)

    transferencia = _transferencia(entorno)
    _insertar(db_session, "transferencia", transferencia)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            "transferencia_linea",
            _linea_t(entorno, transferencia["id"], producto_id=ajena.producto_id),
        )
    assert "fk_transferencia_linea__producto" in str(error.value)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, "ajuste_stock", _ajuste(entorno, motivo_id=ajena.motivo_id))
    assert "fk_ajuste_stock__motivo" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "armar_cabecera", "campos_anulacion"),
    [
        ("transferencia", "_transferencia", ("anulada_en", "anulada_por_id")),
        ("ajuste_stock", "_ajuste", ("anulado_en", "anulado_por_id")),
    ],
)
def test_el_estado_y_la_anulacion_son_coherentes_en_la_base(
    db_session: Session, tabla: str, armar_cabecera: str, campos_anulacion: tuple[str, str]
) -> None:
    """D5 punto 3: las tres columnas de anulación son no nulas si y solo si `ANULADA`."""
    entorno = _armar(db_session)
    cabecera = globals()[armar_cabecera]
    en, por = campos_anulacion
    motivo = entorno.motivo_anulacion_id
    completa = {
        "estado": "ANULADA",
        en: MOMENTO,
        por: entorno.usuario_id,
        "anulacion_motivo_id": motivo,
    }
    _insertar(db_session, tabla, cabecera(entorno, **completa))

    nombre = f"ck_{tabla}__anulacion_coherente"
    for incompleta in (
        {**completa, "anulacion_motivo_id": None},
        {**completa, en: None},
        {**completa, por: None},
        {"estado": "CONFIRMADA", en: MOMENTO},
        {"estado": "CONFIRMADA", "anulacion_motivo_id": motivo},
    ):
        _rechaza(db_session, tabla, cabecera(entorno, **incompleta), nombre)
    _rechaza(db_session, tabla, cabecera(entorno, estado="PENDIENTE"), f"ck_{tabla}__estado")


# --- privilegios (tarea 1.2, INV-05) ----------------------------------------------


@pytest.mark.parametrize("tabla", list(FKS))
def test_inv05_app_runtime_solo_tiene_select_e_insert(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """INV-05, TR-06: ningún `DELETE`; `UPDATE` solo por columna (abajo)."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}


@pytest.mark.parametrize("tabla", ["transferencia", "ajuste_stock"])
def test_inv05_app_runtime_solo_actualiza_estado_y_anulacion(
    app_runtime_engine: Engine, tabla: str
) -> None:
    assert _columnas_con_update(app_runtime_engine, tabla) == COLUMNAS_MUTABLES[tabla]


@pytest.mark.parametrize("tabla", ["transferencia_linea", "ajuste_stock_linea"])
def test_inv05_las_lineas_no_se_actualizan(app_runtime_engine: Engine, tabla: str) -> None:
    assert _columnas_con_update(app_runtime_engine, tabla) == set()


@pytest.mark.parametrize("tabla", list(FKS))
def test_inv05_app_runtime_no_puede_borrar(app_runtime_engine: Engine, tabla: str) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))
    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "columna", "valor"),
    [
        ("transferencia", "observacion", "'cambiada'"),
        ("transferencia", "ubicacion_destino_id", "ubicacion_origen_id"),
        ("transferencia", "usuario_id", "usuario_id"),
        ("ajuste_stock", "observacion", "'cambiada'"),
        ("ajuste_stock", "motivo_id", "motivo_id"),
        ("ajuste_stock", "ubicacion_id", "ubicacion_id"),
        ("transferencia_linea", "cantidad_base", "1"),
        ("ajuste_stock_linea", "cantidad_base", "1"),
        ("ajuste_stock_linea", "costo_unitario", "1"),
    ],
)
def test_inv05_app_runtime_no_puede_actualizar_nada_mas(
    app_runtime_engine: Engine, tabla: str, columna: str, valor: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = {valor}"))
    assert "permission denied" in str(error.value)


@pytest.mark.parametrize("tabla", ["stock_movimiento", "costo_producto_mov", "auditoria"])
def test_los_libros_conservan_sus_privilegios(app_runtime_engine: Engine, tabla: str) -> None:
    """Tarea 1.2: `stock_movimiento`, `costo_producto_mov` y `auditoria` siguen de solo
    inserción (INV-05)."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == set()


# --- catálogos (tarea 1.3) ----------------------------------------------------------


@pytest.mark.parametrize("ambito", [*AMBITOS_ANTERIORES, *AMBITOS_NUEVOS])
def test_ck_motivo_ambito_admite_el_catalogo(db_session: Session, ambito: str) -> None:
    """D5: suma los dos ámbitos sin perder los previos (TR-09)."""
    entorno = _armar(db_session)
    _insertar(db_session, "motivo", _motivo(entorno.organizacion_id, ambito, f"M {ambito}"))


@pytest.mark.parametrize("ambito", ["ANULACION_TRANSFERENCIAS", "anulacion_ajuste", "AJUSTE", ""])
def test_ck_motivo_ambito_rechaza_un_ambito_inventado(db_session: Session, ambito: str) -> None:
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        "motivo",
        _motivo(entorno.organizacion_id, ambito, "Inventado"),
        "ck_motivo__ambito",
    )


def test_el_permiso_anular_transferencia_esta_en_el_catalogo(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text("SELECT descripcion, modulo FROM permiso WHERE codigo = :c"), {"c": PERMISO}
        ).one()
    assert tuple(fila) == ("Anular transferencias de otros usuarios", "stock")


# --- siembra y ciclo (tareas 1.3 y 1.4) ------------------------------------------------


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


def _crear_rol(sesion: Session, organizacion_id: UUID, nombre: str) -> UUID:
    rol_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO rol (id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, :nombre, 0, true, :m, :m)"
        ),
        {"id": rol_id, "org": organizacion_id, "nombre": nombre, "m": MOMENTO},
    )
    return rol_id


def _roles_con_el_permiso(motor: Engine, organizacion_id: UUID) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT r.nombre FROM rol_permiso rp JOIN rol r "
                    "ON r.organizacion_id = rp.organizacion_id AND r.id = rp.rol_id "
                    "WHERE rp.organizacion_id = :o AND rp.permiso_codigo = :p"
                ),
                {"o": organizacion_id, "p": PERMISO},
            ).scalars()
        )


def test_la_migracion_siembra_motivos_y_asigna_el_permiso_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D5.3 y D5 punto 5: "Error de carga" y "Otro" en cada ámbito nuevo de cada
    organización que no tenga ninguno (idempotente) y el permiso asignado a los roles de
    plantilla Administrador y Administración; Supervisor y Vendedor no lo reciben."""
    with Session(_engine_de_sesion) as sesion:
        vacia = crear_organizacion(sesion).id
        con_propios = crear_organizacion(sesion).id
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'AJUSTE_STOCK', 'Rotura', true, :m, :m)"
            ),
            {"id": uuid4(), "org": con_propios, "m": MOMENTO},
        )
        for organizacion_id in (vacia, con_propios):
            for nombre in (
                "Administrador",
                "Administración",
                "Supervisor comercial",
                "Vendedor/Repartidor",
                "Consulta/Dirección",
                "Rol a medida",
            ):
                _crear_rol(sesion, organizacion_id, nombre)
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        # Una organización con motivos propios de un ámbito nuevo (sembrados a mano
        # después del downgrade no es posible: el CHECK anterior los rechaza), así que
        # se prueba la idempotencia con un segundo ciclo.
        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        for organizacion_id in (vacia, con_propios):
            for ambito in AMBITOS_NUEVOS:
                assert set(_motivos_de_ambito(_engine_de_sesion, organizacion_id, ambito)) == (
                    MOTIVOS_SEMBRADOS
                )
            assert _roles_con_el_permiso(_engine_de_sesion, organizacion_id) == {
                "Administrador",
                "Administración",
            }
        assert _motivos_de_ambito(_engine_de_sesion, con_propios, "AJUSTE_STOCK") == ["Rotura"]

        # Idempotencia: repetir el ciclo no duplica motivos.
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        for ambito in AMBITOS_NUEVOS:
            assert len(_motivos_de_ambito(_engine_de_sesion, vacia, ambito)) == 2
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_sembrado_no_duplica_en_una_organizacion_que_ya_tiene_motivos_del_ambito(
    _engine_de_sesion: Engine,
) -> None:
    """D5.3: una organización que ya tiene algún motivo de un ámbito nuevo no recibe los
    sembrados de ESE ámbito (sí los del otro). Se ejecuta la función de siembra de la
    revisión sobre la base ya migrada, igual que lo hace `upgrade` sobre las existentes."""
    archivo = next((BACKEND_DIR / "alembic" / "versions").glob(f"{REVISION}_*.py"))
    especificacion = importlib.util.spec_from_file_location("revision_14", archivo)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)

    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'ANULACION_AJUSTE', 'Propio', true, :m, :m)"
            ),
            {"id": uuid4(), "org": organizacion_id, "m": MOMENTO},
        )
        sesion.commit()
    try:
        with (
            _engine_de_sesion.begin() as conexion,
            Operations.context(MigrationContext.configure(conexion)),
        ):
            modulo._sembrar_motivos()
            modulo._sembrar_motivos()  # idempotente

        assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, "ANULACION_AJUSTE") == [
            "Propio"
        ]
        assert set(
            _motivos_de_ambito(_engine_de_sesion, organizacion_id, "ANULACION_TRANSFERENCIA")
        ) == (MOTIVOS_SEMBRADOS)
        assert (
            len(_motivos_de_ambito(_engine_de_sesion, organizacion_id, "ANULACION_TRANSFERENCIA"))
            == 2
        )
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos_sembrados(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4 y D8: sube y baja limpio sobre una base con stock inicial, una
    compra-equivalente, una transferencia, un ajuste y una anulación. NO toca
    `stock_movimiento`, `costo_producto_mov` ni `auditoria`; restaura `ck_motivo__ambito`.
    La aserción explícita es lo que el `downgrade` pierde: las transferencias, los
    ajustes, sus anulaciones, los motivos de los dos ámbitos y el permiso con sus
    asignaciones (los movimientos quedan en el libro)."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(
            sesion,
            "motivo",
            _motivo(entorno.organizacion_id, "ANULACION_TRANSFERENCIA", "Error de carga X"),
        )
        rol_id = _crear_rol(sesion, entorno.organizacion_id, "Administrador")
        sesion.execute(
            text(
                "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
                "VALUES (:o, :r, :p)"
            ),
            {"o": entorno.organizacion_id, "r": rol_id, "p": PERMISO},
        )
        stock_inicial = insertar_stock_movimiento_sql(
            sesion,
            organizacion_id=entorno.organizacion_id,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.origen_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            cantidad_base=120,
            costo_unitario=Decimal("1050.000000"),
        )
        transferencia = _transferencia(entorno)
        anulada = _transferencia(
            entorno,
            estado="ANULADA",
            anulada_en=MOMENTO,
            anulada_por_id=entorno.usuario_id,
            anulacion_motivo_id=entorno.motivo_anulacion_id,
        )
        for cabecera in (transferencia, anulada):
            _insertar(sesion, "transferencia", cabecera)
            _insertar(sesion, "transferencia_linea", _linea_t(entorno, cabecera["id"]))
        ajuste = _ajuste(entorno)
        _insertar(sesion, "ajuste_stock", ajuste)
        _insertar(sesion, "ajuste_stock_linea", _linea_a(entorno, ajuste["id"]))
        sesion.commit()
        organizacion_id = entorno.organizacion_id

    libros_antes = {
        tabla: _cantidad_de_filas(_engine_de_sesion, tabla)
        for tabla in ("stock_movimiento", "costo_producto_mov", "auditoria")
    }
    assert libros_antes["stock_movimiento"] >= 1
    assert stock_inicial is not None

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` pierde, escrito explícito (D8).
        tablas = _tablas_existentes(_engine_de_sesion)
        assert tablas.isdisjoint(
            {"transferencia", "transferencia_linea", "ajuste_stock", "ajuste_stock_linea"}
        )
        for ambito in AMBITOS_NUEVOS:
            assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, ambito) == []
        with _engine_de_sesion.connect() as conexion:
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM permiso WHERE codigo = :c"), {"c": PERMISO}
                ).scalar_one()
                == 0
            )
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM rol_permiso WHERE permiso_codigo = :c"),
                    {"c": PERMISO},
                ).scalar_one()
                == 0
            )
        # Lo que NO toca: los libros.
        for tabla, filas in libros_antes.items():
            assert _cantidad_de_filas(_engine_de_sesion, tabla) == filas, tabla
        # Y `ck_motivo__ambito` vuelve a rechazar los ámbitos nuevos.
        with pytest.raises(IntegrityError), Session(_engine_de_sesion) as sesion:
            _insertar(
                sesion, "motivo", _motivo(organizacion_id, "ANULACION_TRANSFERENCIA", "Rechazado")
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _cantidad_de_filas(_engine_de_sesion, "transferencia") == 0
        assert _cantidad_de_filas(_engine_de_sesion, "ajuste_stock") == 0
        for ambito in AMBITOS_NUEVOS:
            assert set(_motivos_de_ambito(_engine_de_sesion, organizacion_id, ambito)) == (
                MOTIVOS_SEMBRADOS
            )
        for tabla, filas in libros_antes.items():
            assert _cantidad_de_filas(_engine_de_sesion, tabla) == filas, tabla
        assert _revision_actual(_engine_de_sesion) != REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    origen_id: UUID
    destino_id: UUID
    producto_id: UUID
    producto_2_id: UUID
    motivo_id: UUID
    motivo_anulacion_id: UUID


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _motivo(organizacion_id: UUID, ambito: str, nombre: str) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organizacion_id": organizacion_id,
        "ambito": ambito,
        "nombre": nombre,
        "activo": True,
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
    }


def _armar(sesion: Session) -> Entorno:
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    motivo_anulacion = _motivo(organizacion.id, "ANULACION_TRANSFERENCIA", "Error de carga")
    _insertar(sesion, "motivo", motivo_anulacion)
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        origen_id=crear_ubicacion_sql(sesion, organizacion.id),
        destino_id=crear_ubicacion_sql(
            sesion, organizacion.id, tipo="VEHICULO", requiere_toma=True
        ),
        producto_id=crear_producto_sql(sesion, organizacion.id),
        producto_2_id=crear_producto_sql(sesion, organizacion.id, nombre="Agua 500"),
        motivo_id=crear_motivo_sql(sesion, organizacion.id),
        motivo_anulacion_id=motivo_anulacion["id"],  # type: ignore[arg-type]
    )


def _operacion(entorno: Entorno) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "estado": "CONFIRMADA",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }


def _transferencia(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        **_operacion(entorno),
        "ubicacion_origen_id": entorno.origen_id,
        "ubicacion_destino_id": entorno.destino_id,
    }
    valores.update(cambios)
    return valores


def _ajuste(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        **_operacion(entorno),
        "ubicacion_id": entorno.origen_id,
        "motivo_id": entorno.motivo_id,
    }
    valores.update(cambios)
    return valores


def _linea_t(entorno: Entorno, transferencia_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "transferencia_id": transferencia_id,
        "orden": 1,
        "producto_id": entorno.producto_id,
        "cantidad_base": 48,
    }
    valores.update(cambios)
    return valores


def _linea_a(entorno: Entorno, ajuste_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "ajuste_id": ajuste_id,
        "orden": 1,
        "producto_id": entorno.producto_id,
        "cantidad_base": -6,
        "costo_unitario": Decimal("1050.000000"),
    }
    valores.update(cambios)
    return valores


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, tabla, valores)
    assert restriccion in str(error.value)
