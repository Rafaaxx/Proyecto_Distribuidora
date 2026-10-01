"""Tarea 1.1: la migración crea `ubicacion`, `costo_producto`,
`costo_producto_mov`, `stock_saldo` y `stock_movimiento` según
`docs/03-modelo-de-datos.md` §7 y §9 y `design.md` D7, D10, D12 y D13.

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_cuentas_corrientes_migracion.py`); que los modelos no se desvíen de la
migración lo cubre `test_modelos_coinciden_con_migracion.py` (tarea 2.1).

Reglas citadas: STK-01, STK-02, STK-03, STK-04, CST-10, CST-13, INV-02, INV-03,
INV-04, INV-05, INV-12, INV-21 y `design.md` D7 (ubicación), D10 (`costo_promedio`
nulo), D12 (columnas y referencias de los libros) y D13 (catálogo de tipos).
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
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from stock_utiles import (
    MOMENTO,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)

REVISION_ANTERIOR = "e6f7a8b9c0d1"  # `cuentas_corrientes`, la revisión previa a este change.

TABLAS = {"ubicacion", "costo_producto", "costo_producto_mov", "stock_saldo", "stock_movimiento"}

COLUMNAS_UBICACION = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "nombre": ("text", False),
    "tipo": ("text", False),
    "requiere_toma": ("boolean", False),
    "activo": ("boolean", False),
    "creado_en": ("timestamp with time zone", False),
    "actualizado_en": ("timestamp with time zone", False),
    "actualizado_por_id": ("uuid", True),
}

COLUMNAS_COSTO_PRODUCTO = {
    "organizacion_id": ("uuid", False),
    "producto_id": ("uuid", False),
    "costo_promedio": ("numeric", True),
    "stock_total": ("integer", False),
    "actualizado_en": ("timestamp with time zone", False),
}

COLUMNAS_COSTO_PRODUCTO_MOV = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "producto_id": ("uuid", False),
    "origen_tipo": ("text", False),
    "origen_id": ("uuid", False),
    "cantidad": ("integer", False),
    "costo_ingreso": ("numeric", False),
    "stock_anterior": ("integer", False),
    "promedio_anterior": ("numeric", True),
    "stock_nuevo": ("integer", False),
    "promedio_nuevo": ("numeric", False),
    "recalculado": ("boolean", False),
    "operation_id": ("uuid", False),
    "registered_at": ("timestamp with time zone", False),
}

COLUMNAS_STOCK_SALDO = {
    "organizacion_id": ("uuid", False),
    "producto_id": ("uuid", False),
    "ubicacion_id": ("uuid", False),
    "cantidad_base": ("integer", False),
    "actualizado_en": ("timestamp with time zone", False),
}

COLUMNAS_STOCK_MOVIMIENTO = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "producto_id": ("uuid", False),
    "ubicacion_id": ("uuid", False),
    "cantidad_base": ("integer", False),
    "tipo": ("text", False),
    "origen_tipo": ("text", False),
    "origen_id": ("uuid", False),
    "costo_unitario": ("numeric", True),
    "jornada_id": ("uuid", True),
    "motivo_id": ("uuid", True),
    "operation_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
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


def _definiciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
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


def _indice(motor: Engine, tabla: str, nombre: str) -> str:
    with motor.connect() as conexion:
        return str(
            conexion.execute(
                text(
                    """
                    SELECT indexdef FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = :tabla AND indexname = :nombre
                    """
                ),
                {"tabla": tabla, "nombre": nombre},
            ).scalar_one()
        )


# --- columnas y tipos ------------------------------------------------------


@pytest.mark.parametrize(
    ("tabla", "esperadas"),
    [
        ("ubicacion", COLUMNAS_UBICACION),
        ("costo_producto", COLUMNAS_COSTO_PRODUCTO),
        ("costo_producto_mov", COLUMNAS_COSTO_PRODUCTO_MOV),
        ("stock_saldo", COLUMNAS_STOCK_SALDO),
        ("stock_movimiento", COLUMNAS_STOCK_MOVIMIENTO),
    ],
)
def test_las_tablas_tienen_las_columnas_de_03_y_de_las_decisiones(
    _engine_de_sesion: Engine, tabla: str, esperadas: dict[str, tuple[str, bool]]
) -> None:
    """`03` §7 y §9; D7 (`actualizado_por_id`), D10 (`costo_promedio` nulo), D12
    (`dispositivo_id` `NOT NULL`, `jornada_id` sin FK)."""
    columnas = _columnas(_engine_de_sesion, tabla)

    assert columnas, f"La migración no creó la tabla `{tabla}`."
    assert columnas == esperadas


@pytest.mark.parametrize(
    ("tabla", "columna"),
    [
        ("costo_producto", "costo_promedio"),
        ("costo_producto_mov", "costo_ingreso"),
        ("costo_producto_mov", "promedio_anterior"),
        ("costo_producto_mov", "promedio_nuevo"),
        ("stock_movimiento", "costo_unitario"),
    ],
)
def test_los_costos_son_numeric_18_6(_engine_de_sesion: Engine, tabla: str, columna: str) -> None:
    """`CLAUDE.md` §4, INV-03: `NUMERIC(18,6)` para costos por unidad base."""
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

    assert tuple(fila) == (18, 6)


def test_las_cantidades_de_stock_son_integer(_engine_de_sesion: Engine) -> None:
    """INV-04, STK-01: toda cantidad en unidad base es `integer`."""
    esperadas = {
        ("stock_movimiento", "cantidad_base"),
        ("stock_saldo", "cantidad_base"),
        ("costo_producto", "stock_total"),
        ("costo_producto_mov", "cantidad"),
        ("costo_producto_mov", "stock_anterior"),
        ("costo_producto_mov", "stock_nuevo"),
    }
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT table_name, column_name, data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN ('stock_movimiento', 'stock_saldo', 'costo_producto',
                                     'costo_producto_mov')
                """
            )
        ).all()

    tipos = {(t, c): tipo for t, c, tipo in filas}
    assert {clave: tipos.get(clave) for clave in esperadas} == dict.fromkeys(esperadas, "integer")


def test_los_momentos_son_timestamptz(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN ('ubicacion', 'costo_producto', 'costo_producto_mov',
                                     'stock_saldo', 'stock_movimiento')
                  AND (column_name LIKE '%\\_en' OR column_name LIKE '%\\_at')
                  AND data_type <> 'timestamp with time zone'
                """
            )
        ).all()

    assert filas == []


def test_el_saldo_y_el_total_nacen_en_cero_por_defecto(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        valores = dict(
            conexion.execute(
                text(
                    """
                    SELECT table_name, column_default FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND ((table_name = 'stock_saldo' AND column_name = 'cantidad_base')
                        OR (table_name = 'costo_producto' AND column_name = 'stock_total'))
                    """
                )
            ).all()
        )

    assert valores == {"stock_saldo": "0", "costo_producto": "0"}


# --- claves, FK e índices --------------------------------------------------


def test_las_fk_son_compuestas_con_organizacion_id(_engine_de_sesion: Engine) -> None:
    """INV-21, `03` §2.4, D12: toda FK entre entidades de negocio incluye
    `organizacion_id`; `jornada_id` no tiene FK hasta el change 15 (D12)."""
    assert _fks(_engine_de_sesion, "ubicacion") == {
        "fk_ubicacion__organizacion": "organizacion_id",
        "fk_ubicacion__actualizado_por": "organizacion_id,actualizado_por_id",
    }
    assert _fks(_engine_de_sesion, "costo_producto") == {
        "fk_costo_producto__organizacion": "organizacion_id",
        "fk_costo_producto__producto": "organizacion_id,producto_id",
    }
    assert _fks(_engine_de_sesion, "costo_producto_mov") == {
        "fk_costo_producto_mov__organizacion": "organizacion_id",
        "fk_costo_producto_mov__producto": "organizacion_id,producto_id",
    }
    assert _fks(_engine_de_sesion, "stock_saldo") == {
        "fk_stock_saldo__organizacion": "organizacion_id",
        "fk_stock_saldo__producto": "organizacion_id,producto_id",
        "fk_stock_saldo__ubicacion": "organizacion_id,ubicacion_id",
    }
    assert _fks(_engine_de_sesion, "stock_movimiento") == {
        "fk_stock_movimiento__organizacion": "organizacion_id",
        "fk_stock_movimiento__producto": "organizacion_id,producto_id",
        "fk_stock_movimiento__ubicacion": "organizacion_id,ubicacion_id",
        "fk_stock_movimiento__usuario": "organizacion_id,usuario_id",
        "fk_stock_movimiento__dispositivo": "organizacion_id,dispositivo_id",
        "fk_stock_movimiento__motivo": "organizacion_id,motivo_id",
    }


def test_las_tablas_con_id_tienen_unicidad_por_organizacion(_engine_de_sesion: Engine) -> None:
    """INV-02: sin `UNIQUE (organizacion_id, id)` ninguna tabla futura puede
    referenciar la fila con FK compuesta."""
    for tabla in ("ubicacion", "costo_producto_mov", "stock_movimiento"):
        claves = _definiciones(_engine_de_sesion, tabla, "p")
        unicas = _definiciones(_engine_de_sesion, tabla, "u")

        assert claves == {f"pk_{tabla}": "PRIMARY KEY (id)"}
        assert unicas.get(f"ux_{tabla}__org_id") == "UNIQUE (organizacion_id, id)"


def test_los_saldos_tienen_clave_primaria_compuesta_sin_id(_engine_de_sesion: Engine) -> None:
    """ADR-035 punto 6, D10: la organización encabeza la clave y no hay `id`."""
    assert _definiciones(_engine_de_sesion, "costo_producto", "p") == {
        "pk_costo_producto": "PRIMARY KEY (organizacion_id, producto_id)"
    }
    assert _definiciones(_engine_de_sesion, "stock_saldo", "p") == {
        "pk_stock_saldo": "PRIMARY KEY (organizacion_id, producto_id, ubicacion_id)"
    }
    assert "id" not in _columnas(_engine_de_sesion, "costo_producto")
    assert "id" not in _columnas(_engine_de_sesion, "stock_saldo")


def test_el_indice_del_kardex_sigue_a_03_mas_el_id(_engine_de_sesion: Engine) -> None:
    """`03` §9 y §16 + D12: `(organizacion_id, producto_id, ubicacion_id,
    occurred_at, id)`."""
    definicion = _indice(_engine_de_sesion, "stock_movimiento", "ix_stock_movimiento__kardex")

    assert "(organizacion_id, producto_id, ubicacion_id, occurred_at, id)" in definicion


def test_el_indice_de_origen_y_el_de_ubicacion_existen(_engine_de_sesion: Engine) -> None:
    """`03` §9 (reversiones por origen) y §16 (`ix_stock_saldo__ubicacion`)."""
    assert "(organizacion_id, origen_tipo, origen_id)" in _indice(
        _engine_de_sesion, "stock_movimiento", "ix_stock_movimiento__origen"
    )
    assert "(organizacion_id, ubicacion_id)" in _indice(
        _engine_de_sesion, "stock_saldo", "ix_stock_saldo__ubicacion"
    )


def test_el_nombre_de_ubicacion_es_unico_sin_distinguir_mayusculas(
    _engine_de_sesion: Engine,
) -> None:
    """D7: `ux_ubicacion__nombre` único por organización, activas o no; el
    escenario ` depósito central ` contra `Depósito central` exige comparar sin
    distinguir mayúsculas."""
    definicion = _indice(_engine_de_sesion, "ubicacion", "ux_ubicacion__nombre")

    assert "UNIQUE" in definicion
    assert "organizacion_id" in definicion
    assert "lower(nombre)" in definicion
    assert "WHERE" not in definicion


# --- CHECK -----------------------------------------------------------------


def test_los_check_estan_en_la_base(_engine_de_sesion: Engine) -> None:
    """Nombres de los `CHECK` (PostgreSQL 17 registra los `NOT NULL` como
    restricciones aparte, y `contype = 'c'` no los incluye)."""
    assert _checks(_engine_de_sesion, "ubicacion") == {
        "ck_ubicacion__tipo",
        "ck_ubicacion__vehiculo_requiere_toma",
    }
    assert _checks(_engine_de_sesion, "costo_producto") == {"ck_costo_producto__promedio_positivo"}
    assert _checks(_engine_de_sesion, "costo_producto_mov") == {
        "ck_costo_producto_mov__origen_tipo"
    }
    assert _checks(_engine_de_sesion, "stock_saldo") == set()
    assert _checks(_engine_de_sesion, "stock_movimiento") == {
        "ck_stock_movimiento__cantidad_no_cero",
        "ck_stock_movimiento__tipo",
    }


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


@pytest.mark.parametrize("tabla", ["stock_movimiento", "costo_producto_mov"])
def test_app_runtime_solo_lee_e_inserta_en_los_libros(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """INV-05, ADR-020: sin `UPDATE` ni `DELETE`."""
    assert _privilegios(app_runtime_engine, tabla) == {"SELECT", "INSERT"}


@pytest.mark.parametrize("tabla", ["stock_saldo", "costo_producto", "ubicacion"])
def test_app_runtime_actualiza_saldos_y_ubicaciones_pero_no_los_borra(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """`02` §7.2, ADR-020."""
    assert _privilegios(app_runtime_engine, tabla) == {"SELECT", "INSERT", "UPDATE"}


# --- comportamiento de la base ---------------------------------------------


def _armar(db_session: Session) -> dict[str, object]:
    organizacion = crear_organizacion(db_session)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, organizacion.id)
    return {
        "organizacion_id": organizacion.id,
        "usuario_id": usuario_id,
        "dispositivo_id": dispositivo_id,
        "producto_id": crear_producto_sql(db_session, organizacion.id),
        "ubicacion_id": crear_ubicacion_sql(db_session, organizacion.id),
    }


def _insertar(db_session: Session, entorno: dict[str, object], **cambios: object) -> None:
    valores: dict[str, object] = {
        "organizacion_id": entorno["organizacion_id"],
        "producto_id": entorno["producto_id"],
        "ubicacion_id": entorno["ubicacion_id"],
        "usuario_id": entorno["usuario_id"],
        "dispositivo_id": entorno["dispositivo_id"],
        **cambios,
    }
    insertar_stock_movimiento_sql(db_session, **valores)


def test_un_movimiento_valido_entra_con_todos_sus_datos(db_session: Session) -> None:
    """STK-03, `03` §9, D12."""
    entorno = _armar(db_session)
    motivo_id = crear_motivo_sql(db_session, entorno["organizacion_id"])  # type: ignore[arg-type]

    _insertar(db_session, entorno, motivo_id=motivo_id, jornada_id=uuid4())

    fila = db_session.execute(
        text(
            "SELECT cantidad_base, tipo, costo_unitario, motivo_id, jornada_id "
            "FROM stock_movimiento WHERE organizacion_id = :org"
        ),
        {"org": entorno["organizacion_id"]},
    ).one()
    assert fila.cantidad_base == 60
    assert fila.tipo == "STOCK_INICIAL"
    assert fila.costo_unitario == Decimal("1000.000000")
    assert fila.motivo_id == motivo_id
    assert fila.jornada_id is not None  # sin FK hasta el 15 (D12)


def test_la_cantidad_cero_se_rechaza(db_session: Session) -> None:
    """STK-03, `03` §9: `ck_stock_movimiento__cantidad_no_cero`."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, cantidad_base=0)

    assert "ck_stock_movimiento__cantidad_no_cero" in str(error.value)


@pytest.mark.parametrize(
    "tipo",
    [
        "STOCK_INICIAL",
        "COMPRA",
        "ANULACION_COMPRA",
        "VENTA",
        "ANULACION_VENTA",
        "TRANSFERENCIA_SALIDA",
        "TRANSFERENCIA_ENTRADA",
        "AJUSTE",
        "DIFERENCIA_RENDICION",
    ],
)
def test_los_nueve_tipos_de_la_etapa_1_entran(db_session: Session, tipo: str) -> None:
    """STK-03, D13-A: 11, 14, 18a, 19 y 24 no migran el libro."""
    entorno = _armar(db_session)

    _insertar(db_session, entorno, tipo=tipo, origen_tipo=tipo)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM stock_movimiento WHERE tipo = :t"), {"t": tipo}
        ).scalar_one()
        == 1
    )


@pytest.mark.parametrize("tipo", ["DEVOLUCION", "RECUENTO", "OTRO"])
def test_un_tipo_fuera_del_catalogo_se_rechaza(db_session: Session, tipo: str) -> None:
    """STK-03 (DEVOLUCION y RECUENTO son de la etapa 2), D13."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, tipo=tipo)

    violada = re.search(r'violates check constraint "(\w+)"', str(error.value))
    assert violada is not None, str(error.value)
    assert violada.group(1) == "ck_stock_movimiento__tipo"


def test_un_producto_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    """INV-02: la FK compuesta lo rechaza."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    producto_ajeno = crear_producto_sql(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, producto_id=producto_ajeno)

    assert "fk_stock_movimiento__producto" in str(error.value)


def test_una_ubicacion_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    ubicacion_ajena = crear_ubicacion_sql(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, ubicacion_id=ubicacion_ajena)

    assert "fk_stock_movimiento__ubicacion" in str(error.value)


def test_un_dispositivo_o_usuario_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    """D12, INV-02."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    usuario_ajeno, dispositivo_ajeno = crear_usuario_y_dispositivo(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, dispositivo_id=dispositivo_ajeno)
    assert "fk_stock_movimiento__dispositivo" in str(error.value)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, usuario_id=usuario_ajeno)
    assert "fk_stock_movimiento__usuario" in str(error.value)


def test_un_motivo_ajeno_se_rechaza(db_session: Session) -> None:
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    motivo_ajeno = crear_motivo_sql(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, motivo_id=motivo_ajeno)

    assert "fk_stock_movimiento__motivo" in str(error.value)


def test_el_dispositivo_es_obligatorio(db_session: Session) -> None:
    """D12: `dispositivo_id uuid NOT NULL`."""
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, entorno, dispositivo_id=None)

    assert "dispositivo_id" in str(error.value)
    assert "not-null" in str(error.value)


def test_una_ubicacion_vehiculo_sin_toma_se_rechaza(db_session: Session) -> None:
    """STK-02, D7: `ck_ubicacion__vehiculo_requiere_toma`."""
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        crear_ubicacion_sql(db_session, organizacion.id, tipo="VEHICULO", requiere_toma=False)

    assert "ck_ubicacion__vehiculo_requiere_toma" in str(error.value)


@pytest.mark.parametrize(
    ("tipo", "requiere_toma"),
    [("VEHICULO", True), ("DEPOSITO", False), ("DEPOSITO", True), ("OTRO", False), ("OTRO", True)],
)
def test_las_combinaciones_validas_de_tipo_y_toma_entran(
    db_session: Session, tipo: str, requiere_toma: bool
) -> None:
    organizacion = crear_organizacion(db_session)

    crear_ubicacion_sql(db_session, organizacion.id, tipo=tipo, requiere_toma=requiere_toma)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM ubicacion WHERE organizacion_id = :o"),
            {"o": organizacion.id},
        ).scalar_one()
        == 1
    )


def test_un_tipo_de_ubicacion_fuera_del_catalogo_se_rechaza(db_session: Session) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        crear_ubicacion_sql(db_session, organizacion.id, tipo="CAMION")

    assert "ck_ubicacion__tipo" in str(error.value)


def test_el_nombre_de_ubicacion_no_se_repite_en_la_organizacion_pero_si_entre_organizaciones(
    db_session: Session,
) -> None:
    """D7: activas o no; sin distinguir mayúsculas; otra organización puede
    repetirlo (TR-08)."""
    organizacion = crear_organizacion(db_session)
    otra = crear_organizacion(db_session)
    crear_ubicacion_sql(db_session, organizacion.id, nombre="Depósito central")

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        crear_ubicacion_sql(db_session, organizacion.id, nombre="depósito central", activo=False)
    assert "ux_ubicacion__nombre" in str(error.value)

    crear_ubicacion_sql(db_session, otra.id, nombre="Depósito central")


def test_el_promedio_no_puede_ser_cero_ni_negativo_pero_si_nulo(db_session: Session) -> None:
    """D10: `CHECK (costo_promedio IS NULL OR costo_promedio > 0)`."""
    organizacion = crear_organizacion(db_session)
    producto_id = crear_producto_sql(db_session, organizacion.id)
    insertar = text(
        "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
        "actualizado_en) VALUES (:org, :prod, :promedio, :m)"
    )

    for promedio in (Decimal("0"), Decimal("-1.5")):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            db_session.execute(
                insertar,
                {"org": organizacion.id, "prod": producto_id, "promedio": promedio, "m": MOMENTO},
            )
        assert "ck_costo_producto__promedio_positivo" in str(error.value)

    db_session.execute(
        insertar, {"org": organizacion.id, "prod": producto_id, "promedio": None, "m": MOMENTO}
    )
    fila = db_session.execute(
        text("SELECT costo_promedio, stock_total FROM costo_producto WHERE producto_id = :p"),
        {"p": producto_id},
    ).one()
    assert fila.costo_promedio is None
    assert fila.stock_total == 0


def test_no_puede_haber_dos_filas_de_saldo_ni_de_costo_para_lo_mismo(
    db_session: Session,
) -> None:
    """D10: la clave primaria compuesta separa la carrera de la primera fila."""
    entorno = _armar(db_session)
    saldo = text(
        "INSERT INTO stock_saldo (organizacion_id, producto_id, ubicacion_id, actualizado_en) "
        "VALUES (:org, :prod, :ubi, :m)"
    )
    costo = text(
        "INSERT INTO costo_producto (organizacion_id, producto_id, actualizado_en) "
        "VALUES (:org, :prod, :m)"
    )
    parametros = {
        "org": entorno["organizacion_id"],
        "prod": entorno["producto_id"],
        "ubi": entorno["ubicacion_id"],
        "m": MOMENTO,
    }
    db_session.execute(saldo, parametros)
    db_session.execute(costo, parametros)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(saldo, parametros)
    assert "pk_stock_saldo" in str(error.value)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(costo, parametros)
    assert "pk_costo_producto" in str(error.value)


def test_el_saldo_y_el_costo_de_otra_organizacion_se_rechazan(db_session: Session) -> None:
    """INV-02: FK compuestas de los saldos."""
    entorno = _armar(db_session)
    otra = crear_organizacion(db_session)
    producto_ajeno = crear_producto_sql(db_session, otra.id)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text(
                "INSERT INTO stock_saldo (organizacion_id, producto_id, ubicacion_id, "
                "actualizado_en) VALUES (:org, :prod, :ubi, :m)"
            ),
            {
                "org": entorno["organizacion_id"],
                "prod": producto_ajeno,
                "ubi": entorno["ubicacion_id"],
                "m": MOMENTO,
            },
        )
    assert "fk_stock_saldo__producto" in str(error.value)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text(
                "INSERT INTO costo_producto (organizacion_id, producto_id, actualizado_en) "
                "VALUES (:org, :prod, :m)"
            ),
            {"org": entorno["organizacion_id"], "prod": producto_ajeno, "m": MOMENTO},
        )
    assert "fk_costo_producto__producto" in str(error.value)


def _insertar_historia(db_session: Session, entorno: dict[str, object], **cambios: object) -> None:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno["organizacion_id"],
        "producto_id": entorno["producto_id"],
        "origen_tipo": "STOCK_INICIAL",
        "origen_id": uuid4(),
        "cantidad": 60,
        "costo_ingreso": Decimal("1100.000000"),
        "stock_anterior": 60,
        "promedio_anterior": Decimal("1000.000000"),
        "stock_nuevo": 120,
        "promedio_nuevo": Decimal("1050.000000"),
        "recalculado": True,
        "operation_id": uuid4(),
        "registered_at": MOMENTO,
        **cambios,
    }
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{c}" for c in valores)
    db_session.execute(
        text(f"INSERT INTO costo_producto_mov ({columnas}) VALUES ({marcadores})"), valores
    )


@pytest.mark.parametrize(
    "origen_tipo", ["COMPRA", "ANULACION_COMPRA", "STOCK_INICIAL", "ANULACION_VENTA"]
)
def test_la_historia_de_costo_admite_los_cuatro_origenes_de_03(
    db_session: Session, origen_tipo: str
) -> None:
    """CST-13, D13-A: `03` §7."""
    entorno = _armar(db_session)

    _insertar_historia(db_session, entorno, origen_tipo=origen_tipo)

    assert (
        db_session.execute(
            text("SELECT count(*) FROM costo_producto_mov WHERE origen_tipo = :t"),
            {"t": origen_tipo},
        ).scalar_one()
        == 1
    )


def test_un_origen_de_historia_fuera_de_catalogo_se_rechaza(db_session: Session) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_historia(db_session, entorno, origen_tipo="VENTA")

    assert "ck_costo_producto_mov__origen_tipo" in str(error.value)


def test_el_primer_ingreso_de_la_historia_no_tiene_promedio_anterior(
    db_session: Session,
) -> None:
    """D10: el promedio anterior es nulo hasta el primer ingreso con costo."""
    entorno = _armar(db_session)

    _insertar_historia(
        db_session,
        entorno,
        stock_anterior=0,
        promedio_anterior=None,
        stock_nuevo=60,
        promedio_nuevo=Decimal("1000.000000"),
    )

    assert (
        db_session.execute(
            text("SELECT promedio_anterior FROM costo_producto_mov WHERE stock_anterior = 0")
        ).scalar_one()
        is None
    )


# --- ciclo de la migración -------------------------------------------------


def _tablas_de_stock(motor: Engine) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('ubicacion', 'costo_producto', 'costo_producto_mov',
                                         'stock_saldo', 'stock_movimiento')
                    """
                )
            )
            .scalars()
            .all()
        )


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


def test_downgrade_elimina_las_cinco_tablas_y_upgrade_las_recrea(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`alembic downgrade` y `alembic upgrade head` limpios. La base es
    compartida con el resto de la sesión: la prueba DEBE terminar en `head`."""
    assert _tablas_de_stock(_engine_de_sesion) == TABLAS
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _tablas_de_stock(_engine_de_sesion) == set()
    finally:
        subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr
    assert _tablas_de_stock(_engine_de_sesion) == TABLAS


def test_el_ciclo_de_migracion_con_datos_sube_baja_y_sube_sin_tocar_lo_ajeno(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`docs/04` §2.1 punto 4 (tarea 9.7): la migración sube y baja limpia sobre una
    base CON datos. Con movimientos, saldos, costo e historia confirmados,
    `upgrade head -> downgrade -1 -> upgrade head` termina en `head`, la bajada solo
    se lleva las cinco tablas del change (el producto, el usuario, el dispositivo y
    su organización quedan intactos) y la subida las recrea vacías y utilizables."""

    def contar(tabla: str) -> int:
        with _engine_de_sesion.connect() as conexion:
            return int(conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one())  # noqa: S608

    # Datos confirmados de verdad (la migración corre en otras conexiones).
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(sesion, entorno)
        _insertar(sesion, entorno, cantidad_base=-12, tipo="VENTA", origen_tipo="VENTA")
        _insertar_historia(sesion, entorno)
        parametros = {
            "org": entorno["organizacion_id"],
            "prod": entorno["producto_id"],
            "ubi": entorno["ubicacion_id"],
            "m": MOMENTO,
        }
        sesion.execute(
            text(
                "INSERT INTO stock_saldo (organizacion_id, producto_id, ubicacion_id, "
                "cantidad_base, actualizado_en) VALUES (:org, :prod, :ubi, 48, :m)"
            ),
            parametros,
        )
        sesion.execute(
            text(
                "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
                "stock_total, actualizado_en) VALUES (:org, :prod, 1050.000000, 48, :m)"
            ),
            parametros,
        )
        sesion.commit()

    try:
        assert contar("stock_movimiento") == 2
        assert contar("costo_producto_mov") == 1
        assert contar("stock_saldo") == 1
        assert contar("costo_producto") == 1
        assert contar("ubicacion") >= 1

        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _tablas_de_stock(_engine_de_sesion) == set()
        # Lo que no es de este change sigue ahí.
        assert contar("producto") >= 1
        assert contar("usuario") >= 1
        assert contar("dispositivo") >= 1
        assert contar("organizacion") >= 1
    finally:
        subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr

    try:
        assert _tablas_de_stock(_engine_de_sesion) == TABLAS
        for tabla in TABLAS:
            assert contar(tabla) == 0
        # Las tablas recreadas aceptan datos nuevos con sus restricciones.
        with Session(_engine_de_sesion) as sesion:
            nueva = crear_ubicacion_sql(sesion, entorno["organizacion_id"], nombre="Nueva")  # type: ignore[arg-type]
            _insertar(sesion, {**entorno, "ubicacion_id": nueva})
            sesion.commit()
        assert contar("stock_movimiento") == 1
        assert contar("ubicacion") == 1
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
