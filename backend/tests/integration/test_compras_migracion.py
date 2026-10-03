"""Tarea 2.1 (change 11): la migración crea `compra`, `compra_linea`, `pago_proveedor`
y `pago_proveedor_medio` según `docs/03-modelo-de-datos.md` §6 y `design.md` D12, y
siembra los motivos de `ANULACION_COMPRA` de D8.

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_importacion_migracion.py`); que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-03, INV-04, INV-05, INV-07 (en el servicio, no en la base),
INV-08 (idem), INV-21, CMP-05, `design.md` D8, D12.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest
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
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

REVISION_ANTERIOR = "b9c0d1e2f3a4"  # `importacion`, la revisión previa a este change.
MOMENTO = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
MOTIVOS_SEMBRADOS = {"Error de carga", "Devolución al proveedor", "Otro"}

OPERACION = {
    "operation_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
}

COLUMNAS: dict[str, dict[str, tuple[str, bool]]] = {
    "compra": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "proveedor_id": ("uuid", False),
        "ubicacion_id": ("uuid", False),
        "fecha": ("date", False),
        "condicion": ("text", False),
        "total_neto": ("numeric", False),
        "total_factura": ("numeric", False),
        "numero_comprobante": ("text", True),
        "observacion": ("text", True),
        "estado": ("text", False),
        "anulacion_motivo_id": ("uuid", True),
        "anulada_en": ("timestamp with time zone", True),
        "anulada_por_id": ("uuid", True),
        **OPERACION,
    },
    "compra_linea": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "compra_id": ("uuid", False),
        "orden": ("integer", False),
        "producto_id": ("uuid", False),
        "presentacion_id": ("uuid", False),
        "unidades_presentacion": ("integer", False),
        "cantidad": ("numeric", False),
        "cantidad_base": ("integer", False),
        "valor_presentacion": ("numeric", False),
        "incluye_iva": ("boolean", False),
        "computa_credito_fiscal": ("boolean", False),
        "bonificacion": ("numeric", False),
        "alicuota_aplicada": ("numeric", False),
        "costo_base": ("numeric", False),
        "importe_neto": ("numeric", False),
    },
    "pago_proveedor": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "proveedor_id": ("uuid", False),
        "fecha": ("date", False),
        "importe": ("numeric", False),
        "estado": ("text", False),
        "origen": ("text", False),
        "compra_id": ("uuid", True),
        "anulado_en": ("timestamp with time zone", True),
        "anulado_por_id": ("uuid", True),
        "anulacion_motivo_id": ("uuid", True),
        **OPERACION,
    },
    "pago_proveedor_medio": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "pago_id": ("uuid", False),
        "medio_pago_id": ("uuid", False),
        "importe": ("numeric", False),
        "referencia": ("text", True),
    },
}

PRECISIONES = {
    ("compra", "total_neto"): (14, 2),
    ("compra", "total_factura"): (14, 2),
    ("compra_linea", "cantidad"): (14, 3),
    ("compra_linea", "valor_presentacion"): (14, 2),
    ("compra_linea", "bonificacion"): (9, 6),
    ("compra_linea", "alicuota_aplicada"): (9, 6),
    ("compra_linea", "costo_base"): (18, 6),
    ("compra_linea", "importe_neto"): (14, 2),
    ("pago_proveedor", "importe"): (14, 2),
    ("pago_proveedor_medio", "importe"): (14, 2),
}

FKS: dict[str, dict[str, str]] = {
    "compra": {
        "fk_compra__organizacion": "organizacion_id",
        "fk_compra__proveedor": "organizacion_id,proveedor_id",
        "fk_compra__ubicacion": "organizacion_id,ubicacion_id",
        "fk_compra__usuario": "organizacion_id,usuario_id",
        "fk_compra__dispositivo": "organizacion_id,dispositivo_id",
        "fk_compra__anulacion_motivo": "organizacion_id,anulacion_motivo_id",
        "fk_compra__anulada_por": "organizacion_id,anulada_por_id",
    },
    "compra_linea": {
        "fk_compra_linea__organizacion": "organizacion_id",
        "fk_compra_linea__compra": "organizacion_id,compra_id",
        "fk_compra_linea__producto": "organizacion_id,producto_id",
        "fk_compra_linea__presentacion": "organizacion_id,presentacion_id",
    },
    "pago_proveedor": {
        "fk_pago_proveedor__organizacion": "organizacion_id",
        "fk_pago_proveedor__proveedor": "organizacion_id,proveedor_id",
        "fk_pago_proveedor__compra": "organizacion_id,compra_id",
        "fk_pago_proveedor__usuario": "organizacion_id,usuario_id",
        "fk_pago_proveedor__dispositivo": "organizacion_id,dispositivo_id",
        "fk_pago_proveedor__anulado_por": "organizacion_id,anulado_por_id",
        "fk_pago_proveedor__anulacion_motivo": "organizacion_id,anulacion_motivo_id",
    },
    "pago_proveedor_medio": {
        "fk_pago_proveedor_medio__organizacion": "organizacion_id",
        "fk_pago_proveedor_medio__pago": "organizacion_id,pago_id",
        "fk_pago_proveedor_medio__medio_pago": "organizacion_id,medio_pago_id",
    },
}

CHECKS: dict[str, set[str]] = {
    "compra": {
        "ck_compra__condicion",
        "ck_compra__estado",
        "ck_compra__total_neto",
        "ck_compra__total_factura",
        "ck_compra__anulacion_coherente",
    },
    "compra_linea": {
        "ck_compra_linea__orden",
        "ck_compra_linea__unidades",
        "ck_compra_linea__cantidad",
        "ck_compra_linea__cantidad_base",
        "ck_compra_linea__valor",
        "ck_compra_linea__bonificacion",
        "ck_compra_linea__alicuota",
        "ck_compra_linea__costo_base",
        "ck_compra_linea__importe_neto",
        "ck_compra_linea__credito_fiscal",
    },
    "pago_proveedor": {
        "ck_pago_proveedor__importe",
        "ck_pago_proveedor__estado",
        "ck_pago_proveedor__origen",
        "ck_pago_proveedor__origen_compra",
        "ck_pago_proveedor__anulacion_coherente",
    },
    "pago_proveedor_medio": {"ck_pago_proveedor_medio__importe"},
}

UNICAS: dict[str, dict[str, str]] = {
    "compra": {"ux_compra__org_id": "UNIQUE (organizacion_id, id)"},
    "compra_linea": {
        "ux_compra_linea__org_id": "UNIQUE (organizacion_id, id)",
        "ux_compra_linea__compra_orden": "UNIQUE (organizacion_id, compra_id, orden)",
    },
    "pago_proveedor": {"ux_pago_proveedor__org_id": "UNIQUE (organizacion_id, id)"},
    "pago_proveedor_medio": {"ux_pago_proveedor_medio__org_id": "UNIQUE (organizacion_id, id)"},
}

INDICES: dict[str, str] = {
    "ix_compra__fecha": "(organizacion_id, fecha DESC, id DESC)",
    "ix_compra__proveedor_fecha": "(organizacion_id, proveedor_id, fecha DESC, id DESC)",
    "ix_compra_linea__presentacion": "(organizacion_id, presentacion_id)",
    "ix_pago_proveedor_medio__pago": "(organizacion_id, pago_id)",
}

TABLAS = list(COLUMNAS)
TABLAS_MUTABLES = {
    "compra": {"estado", "anulacion_motivo_id", "anulada_en", "anulada_por_id"},
    "pago_proveedor": {"estado", "anulado_en", "anulado_por_id", "anulacion_motivo_id"},
}
TABLAS_SOLO_INSERCION = {"compra_linea", "pago_proveedor_medio"}


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


def _restricciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
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


def _indice(motor: Engine, nombre: str) -> str:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": nombre},
        ).scalar_one()


def _existen_las_tablas(motor: Engine) -> bool:
    with motor.connect() as conexion:
        return conexion.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(:tablas)"
            ),
            {"tablas": TABLAS},
        ).scalar_one() == len(TABLAS)


# --- columnas, claves e índices ------------------------------------------------


@pytest.mark.parametrize("tabla", TABLAS)
def test_las_tablas_tienen_las_columnas_de_03_y_d12(_engine_de_sesion: Engine, tabla: str) -> None:
    assert _columnas(_engine_de_sesion, tabla) == COLUMNAS[tabla]


@pytest.mark.parametrize(("tabla", "columna"), list(PRECISIONES))
def test_inv03_importes_y_costos_son_numeric_con_su_precision(
    _engine_de_sesion: Engine, tabla: str, columna: str
) -> None:
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": tabla, "c": columna},
        ).one()

    assert (fila[0], fila[1]) == PRECISIONES[(tabla, columna)]


@pytest.mark.parametrize("tabla", TABLAS)
def test_la_clave_primaria_es_el_id_y_hay_unicidad_por_organizacion(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02: sin `UNIQUE (organizacion_id, id)` ninguna tabla puede referenciar la
    fila con FK compuesta."""
    assert _restricciones(_engine_de_sesion, tabla, "p") == {f"pk_{tabla}": "PRIMARY KEY (id)"}
    assert _restricciones(_engine_de_sesion, tabla, "u") == UNICAS[tabla]


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv21_las_fk_son_compuestas_con_organizacion_id(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    assert _fks(_engine_de_sesion, tabla) == FKS[tabla]


@pytest.mark.parametrize("tabla", TABLAS)
def test_los_check_estan_en_la_base(_engine_de_sesion: Engine, tabla: str) -> None:
    assert set(_restricciones(_engine_de_sesion, tabla, "c")) == CHECKS[tabla]


@pytest.mark.parametrize(("nombre", "fragmento"), list(INDICES.items()))
def test_los_indices_de_d12_existen(_engine_de_sesion: Engine, nombre: str, fragmento: str) -> None:
    assert fragmento in _indice(_engine_de_sesion, nombre)


def test_el_pago_de_una_compra_es_unico_por_compra(_engine_de_sesion: Engine) -> None:
    definicion = _indice(_engine_de_sesion, "ux_pago_proveedor__compra")

    assert "UNIQUE" in definicion
    assert "(organizacion_id, compra_id)" in definicion
    assert "compra_id IS NOT NULL" in definicion


# --- permisos (INV-05) ---------------------------------------------------------


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


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv05_app_runtime_no_tiene_delete_y_solo_update_de_columnas_de_estado(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """D12-A: `SELECT, INSERT` sobre las cuatro tablas; `UPDATE` solo, por columna, de
    estado y anulación en `compra` y `pago_proveedor`; nunca `DELETE`."""
    privilegios = _privilegios_de_tabla(app_runtime_engine, tabla)

    assert privilegios == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == TABLAS_MUTABLES.get(tabla, set())


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv05_app_runtime_no_puede_borrar(app_runtime_engine: Engine, tabla: str) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize("tabla", sorted(TABLAS_SOLO_INSERCION))
def test_inv05_app_runtime_no_puede_actualizar_lineas_ni_medios(
    app_runtime_engine: Engine, tabla: str
) -> None:
    columna = "importe_neto" if tabla == "compra_linea" else "importe"
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = 1"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "columna"), [("compra", "total_factura"), ("pago_proveedor", "importe")]
)
def test_inv05_app_runtime_no_puede_cambiar_importes_de_compra_ni_pago(
    app_runtime_engine: Engine, tabla: str, columna: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = 1"))

    assert "permission denied" in str(error.value)


# --- comportamiento de la base -------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    proveedor_id: UUID
    ubicacion_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    medio_pago_id: UUID
    motivo_id: UUID


def _armar(db_session: Session) -> Entorno:
    organizacion = crear_organizacion(db_session)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, organizacion.id)
    producto_id = crear_producto_sql(db_session, organizacion.id)
    medio_pago_id, motivo_id = uuid4(), uuid4()
    db_session.execute(
        text(
            "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, activo, "
            "creado_en, actualizado_en) VALUES (:id, :org, 'Efectivo', false, true, :m, :m)"
        ),
        {"id": medio_pago_id, "org": organizacion.id, "m": MOMENTO},
    )
    db_session.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', 'Otro prueba', true, :m, :m)"
        ),
        {"id": motivo_id, "org": organizacion.id, "m": MOMENTO},
    )
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        proveedor_id=crear_proveedor(db_session, organizacion.id),
        ubicacion_id=crear_ubicacion_sql(db_session, organizacion.id),
        producto_id=producto_id,
        presentacion_id=crear_presentacion_referencia_sql(db_session, organizacion.id, producto_id),
        medio_pago_id=medio_pago_id,
        motivo_id=motivo_id,
    )


def _insertar(db_session: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    db_session.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _compra(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "proveedor_id": entorno.proveedor_id,
        "ubicacion_id": entorno.ubicacion_id,
        "fecha": date(2026, 10, 1),
        "condicion": "CREDITO",
        "total_neto": 126000,
        "total_factura": 152460,
        "estado": "CONFIRMADA",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _linea(entorno: Entorno, compra_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "compra_id": compra_id,
        "orden": 1,
        "producto_id": entorno.producto_id,
        "presentacion_id": entorno.presentacion_id,
        "unidades_presentacion": 6,
        "cantidad": 10,
        "cantidad_base": 60,
        "valor_presentacion": 6000,
        "incluye_iva": False,
        "computa_credito_fiscal": True,
        "bonificacion": 0,
        "alicuota_aplicada": 0.21,
        "costo_base": 1000,
        "importe_neto": 60000,
    }
    valores.update(cambios)
    return valores


def _pago(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "proveedor_id": entorno.proveedor_id,
        "fecha": date(2026, 10, 1),
        "importe": 152460,
        "estado": "CONFIRMADA",
        "origen": "INDEPENDIENTE",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _medio(entorno: Entorno, pago_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "pago_id": pago_id,
        "medio_pago_id": entorno.medio_pago_id,
        "importe": 152460,
    }
    valores.update(cambios)
    return valores


def _rechaza(db_session: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, tabla, valores)
    assert restriccion in str(error.value)


def test_una_compra_con_sus_lineas_y_un_pago_de_contado_se_inserta(db_session: Session) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno, condicion="CONTADO")
    _insertar(db_session, "compra", compra)
    _insertar(db_session, "compra_linea", _linea(entorno, compra["id"]))
    _insertar(db_session, "compra_linea", _linea(entorno, compra["id"], orden=2))
    pago = _pago(entorno, origen="COMPRA", compra_id=compra["id"])
    _insertar(db_session, "pago_proveedor", pago)
    _insertar(db_session, "pago_proveedor_medio", _medio(entorno, pago["id"]))

    assert db_session.execute(text("SELECT count(*) FROM compra_linea")).scalar_one() == 2


@pytest.mark.parametrize("condicion", ["CREDITO", "CONTADO"])
def test_cada_condicion_del_catalogo_se_acepta(db_session: Session, condicion: str) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "compra", _compra(entorno, condicion=condicion))


@pytest.mark.parametrize("condicion", ["credito", "MIXTA", ""])
def test_una_condicion_fuera_del_catalogo_se_rechaza(db_session: Session, condicion: str) -> None:
    _rechaza(
        db_session,
        "compra",
        _compra(_armar(db_session), condicion=condicion),
        "ck_compra__condicion",
    )


@pytest.mark.parametrize("estado", ["PENDIENTE", "confirmada", ""])
def test_un_estado_de_compra_fuera_del_catalogo_se_rechaza(
    db_session: Session, estado: str
) -> None:
    _rechaza(db_session, "compra", _compra(_armar(db_session), estado=estado), "ck_compra__estado")


def test_el_total_neto_puede_ser_cero_pero_no_negativo(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "compra", _compra(entorno, total_neto=0))
    _rechaza(db_session, "compra", _compra(entorno, total_neto=-1), "ck_compra__total_neto")


@pytest.mark.parametrize("total", [0, -1])
def test_el_total_de_factura_debe_ser_positivo(db_session: Session, total: int) -> None:
    _rechaza(
        db_session,
        "compra",
        _compra(_armar(db_session), total_factura=total),
        "ck_compra__total_factura",
    )


def test_la_anulacion_de_la_compra_es_coherente(db_session: Session) -> None:
    """D12-A: anulada si y solo si tiene motivo, momento y usuario."""
    entorno = _armar(db_session)
    anulacion: dict[str, object] = {
        "estado": "ANULADA",
        "anulacion_motivo_id": entorno.motivo_id,
        "anulada_en": MOMENTO,
        "anulada_por_id": entorno.usuario_id,
    }
    _insertar(db_session, "compra", _compra(entorno, **anulacion))

    for incompleta in (
        {**anulacion, "anulacion_motivo_id": None},
        {**anulacion, "anulada_en": None},
        {**anulacion, "anulada_por_id": None},
        {"estado": "CONFIRMADA", "anulada_en": MOMENTO},
        {"estado": "CONFIRMADA", "anulacion_motivo_id": entorno.motivo_id},
    ):
        _rechaza(
            db_session, "compra", _compra(entorno, **incompleta), "ck_compra__anulacion_coherente"
        )


@pytest.mark.parametrize(
    ("columna", "valor", "restriccion"),
    [
        ("orden", 0, "ck_compra_linea__orden"),
        ("unidades_presentacion", 0, "ck_compra_linea__unidades"),
        ("cantidad", 0, "ck_compra_linea__cantidad"),
        ("cantidad_base", 0, "ck_compra_linea__cantidad_base"),
        ("valor_presentacion", 0, "ck_compra_linea__valor"),
        ("bonificacion", 1, "ck_compra_linea__bonificacion"),
        ("bonificacion", -0.1, "ck_compra_linea__bonificacion"),
        ("alicuota_aplicada", -0.01, "ck_compra_linea__alicuota"),
        ("costo_base", 0, "ck_compra_linea__costo_base"),
        ("importe_neto", -1, "ck_compra_linea__importe_neto"),
    ],
)
def test_los_rangos_de_la_linea_se_verifican_en_la_base(
    db_session: Session, columna: str, valor: float, restriccion: str
) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)

    _rechaza(
        db_session, "compra_linea", _linea(entorno, compra["id"], **{columna: valor}), restriccion
    )


def test_la_bonificacion_cero_y_una_fraccion_son_validas(db_session: Session) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)

    _insertar(db_session, "compra_linea", _linea(entorno, compra["id"], orden=1, bonificacion=0))
    _insertar(
        db_session, "compra_linea", _linea(entorno, compra["id"], orden=2, bonificacion=0.076923)
    )


def test_el_orden_de_la_linea_es_unico_dentro_de_la_compra(db_session: Session) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)
    _insertar(db_session, "compra_linea", _linea(entorno, compra["id"], orden=1))

    _rechaza(
        db_session,
        "compra_linea",
        _linea(entorno, compra["id"], orden=1),
        "ux_compra_linea__compra_orden",
    )


def test_la_cantidad_de_la_linea_admite_tres_decimales(db_session: Session) -> None:
    """`03` §2.2: `numeric(14,3)` solo en compras; la cantidad base sigue entera."""
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)

    _insertar(
        db_session,
        "compra_linea",
        _linea(entorno, compra["id"], cantidad="2.500", cantidad_base=15),
    )

    cantidad = db_session.execute(text("SELECT cantidad FROM compra_linea")).scalar_one()
    assert str(cantidad) == "2.500"


@pytest.mark.parametrize("origen", ["COMPRA", "INDEPENDIENTE"])
def test_el_origen_del_pago_exige_o_prohibe_la_compra(db_session: Session, origen: str) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno, condicion="CONTADO")
    _insertar(db_session, "compra", compra)
    con_compra = origen == "COMPRA"
    _insertar(
        db_session,
        "pago_proveedor",
        _pago(entorno, origen=origen, compra_id=compra["id"] if con_compra else None),
    )

    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(entorno, origen=origen, compra_id=None if con_compra else compra["id"]),
        "ck_pago_proveedor__origen_compra",
    )


def test_un_origen_de_pago_fuera_del_catalogo_se_rechaza(db_session: Session) -> None:
    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(_armar(db_session), origen="OTRO"),
        "ck_pago_proveedor__origen",
    )


def test_un_estado_de_pago_fuera_del_catalogo_se_rechaza(db_session: Session) -> None:
    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(_armar(db_session), estado="PENDIENTE"),
        "ck_pago_proveedor__estado",
    )


@pytest.mark.parametrize("importe", [0, -1])
def test_el_importe_del_pago_y_de_su_medio_deben_ser_positivos(
    db_session: Session, importe: int
) -> None:
    entorno = _armar(db_session)
    _rechaza(
        db_session, "pago_proveedor", _pago(entorno, importe=importe), "ck_pago_proveedor__importe"
    )
    pago = _pago(entorno)
    _insertar(db_session, "pago_proveedor", pago)
    _rechaza(
        db_session,
        "pago_proveedor_medio",
        _medio(entorno, pago["id"], importe=importe),
        "ck_pago_proveedor_medio__importe",
    )


def test_la_anulacion_del_pago_es_coherente_y_su_motivo_es_opcional(db_session: Session) -> None:
    """D12-A: el motivo del pago lo decide el change 12; anulado exige momento y usuario."""
    entorno = _armar(db_session)
    _insertar(
        db_session,
        "pago_proveedor",
        _pago(entorno, estado="ANULADA", anulado_en=MOMENTO, anulado_por_id=entorno.usuario_id),
    )

    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(entorno, estado="ANULADA", anulado_en=None, anulado_por_id=entorno.usuario_id),
        "ck_pago_proveedor__anulacion_coherente",
    )
    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(entorno, estado="CONFIRMADA", anulado_en=MOMENTO),
        "ck_pago_proveedor__anulacion_coherente",
    )


def test_una_compra_tiene_a_lo_sumo_un_pago(db_session: Session) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno, condicion="CONTADO")
    _insertar(db_session, "compra", compra)
    _insertar(db_session, "pago_proveedor", _pago(entorno, origen="COMPRA", compra_id=compra["id"]))

    _rechaza(
        db_session,
        "pago_proveedor",
        _pago(entorno, origen="COMPRA", compra_id=compra["id"]),
        "ux_pago_proveedor__compra",
    )


def test_los_pagos_independientes_no_chocan_entre_si(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "pago_proveedor", _pago(entorno))
    _insertar(db_session, "pago_proveedor", _pago(entorno))


def test_inv21_las_referencias_deben_ser_de_la_misma_organizacion(db_session: Session) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)

    for columna, restriccion in (
        ("proveedor_id", "fk_compra__proveedor"),
        ("ubicacion_id", "fk_compra__ubicacion"),
        ("usuario_id", "fk_compra__usuario"),
        ("dispositivo_id", "fk_compra__dispositivo"),
    ):
        _rechaza(
            db_session,
            "compra",
            _compra(propio, **{columna: getattr(ajeno, columna)}),
            restriccion,
        )

    compra = _compra(propio)
    _insertar(db_session, "compra", compra)
    _rechaza(
        db_session,
        "compra_linea",
        _linea(propio, compra["id"], producto_id=ajeno.producto_id),
        "fk_compra_linea__producto",
    )
    _rechaza(
        db_session,
        "compra_linea",
        _linea(propio, compra["id"], presentacion_id=ajeno.presentacion_id),
        "fk_compra_linea__presentacion",
    )
    pago = _pago(propio)
    _insertar(db_session, "pago_proveedor", pago)
    _rechaza(
        db_session,
        "pago_proveedor_medio",
        _medio(propio, pago["id"], medio_pago_id=ajeno.medio_pago_id),
        "fk_pago_proveedor_medio__medio_pago",
    )
    _rechaza(
        db_session,
        "compra",
        _compra(
            propio,
            estado="ANULADA",
            anulacion_motivo_id=ajeno.motivo_id,
            anulada_en=MOMENTO,
            anulada_por_id=propio.usuario_id,
        ),
        "fk_compra__anulacion_motivo",
    )


# --- motivos de anulación de compra (D8) ----------------------------------------


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


def _motivos_de_compra(motor: Engine, organizacion_id: UUID) -> list[str]:
    with motor.connect() as conexion:
        return list(
            conexion.execute(
                text(
                    "SELECT nombre FROM motivo WHERE organizacion_id = :o "
                    "AND ambito = 'ANULACION_COMPRA' AND activo ORDER BY nombre"
                ),
                {"o": organizacion_id},
            )
            .scalars()
            .all()
        )


def test_la_migracion_siembra_los_motivos_una_sola_vez_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D8, CMP-05: organizaciones previas sin motivos de `ANULACION_COMPRA` los reciben;
    una que ya tiene uno propio no se toca; `downgrade` y `upgrade` no duplican. La
    base es compartida con el resto de la sesión: la prueba DEBE terminar en `head`."""
    with Session(_engine_de_sesion) as sesion:
        sin_motivos = crear_organizacion(sesion).id
        con_motivo = crear_organizacion(sesion).id
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', 'Mi motivo', true, :m, :m)"
            ),
            {"id": uuid4(), "org": con_motivo, "m": MOMENTO},
        )
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert not _existen_las_tablas(_engine_de_sesion)
        assert _motivos_de_compra(_engine_de_sesion, sin_motivos) == []
        assert _motivos_de_compra(_engine_de_sesion, con_motivo) == ["Mi motivo"]
    finally:
        subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr

    try:
        assert _existen_las_tablas(_engine_de_sesion)
        assert set(_motivos_de_compra(_engine_de_sesion, sin_motivos)) == MOTIVOS_SEMBRADOS
        assert len(_motivos_de_compra(_engine_de_sesion, sin_motivos)) == 3
        assert _motivos_de_compra(_engine_de_sesion, con_motivo) == ["Mi motivo"]

        repetida = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert repetida.returncode == 0, repetida.stderr
        reaplicada = _alembic(database_url, "upgrade", "head")
        assert reaplicada.returncode == 0, reaplicada.stderr
        assert len(_motivos_de_compra(_engine_de_sesion, sin_motivos)) == 3
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
