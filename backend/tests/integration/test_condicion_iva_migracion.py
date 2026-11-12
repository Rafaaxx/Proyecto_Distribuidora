"""Tarea 2.1 (change 11b): la migración agrega `configuracion_organizacion.condicion_iva`
(con su `CHECK` de dominio y el de D2) y `computa_credito_fiscal` en `costo_informado` y
`compra_linea` (con el `CHECK` de D3), rellena lo existente según D9 y no cambia los
privilegios de los libros.

Consulta el esquema REAL de PostgreSQL migrado (mismo criterio que
`test_compras_migracion.py`). Que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py`.

Reglas citadas: TR-06 (la historia no se recalcula), CST-06, INV-03, INV-05, `design.md`
D1, D2, D3, D9.
"""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
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
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from stock_utiles import (
    MOMENTO,
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)
from test_compras_migracion import Entorno, _armar, _compra, _insertar, _linea

REVISION_ANTERIOR = "c0d1e2f3a4b5"  # `compras_y_pagos_proveedor`, previa a este change.


def _columna(motor: Engine, tabla: str, columna: str) -> tuple[str, str] | None:
    with motor.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": tabla, "c": columna},
        ).one_or_none()
    return None if fila is None else (fila[0], fila[1])


def _checks(motor: Engine, tabla: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c'"
                ),
                {"t": f"public.{tabla}"},
            ).all()
        )


# --- columnas y restricciones --------------------------------------------------


def test_la_configuracion_tiene_la_condicion_iva_obligatoria_de_tipo_texto(
    _engine_de_sesion: Engine,
) -> None:
    assert _columna(_engine_de_sesion, "configuracion_organizacion", "condicion_iva") == (
        "text",
        "NO",
    )


@pytest.mark.parametrize("tabla", ["costo_informado", "compra_linea"])
def test_computa_credito_fiscal_es_booleano_obligatorio(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    assert _columna(_engine_de_sesion, tabla, "computa_credito_fiscal") == ("boolean", "NO")


def test_los_check_de_la_condicion_estan_en_la_base(_engine_de_sesion: Engine) -> None:
    checks = _checks(_engine_de_sesion, "configuracion_organizacion")

    assert "ck_configuracion_organizacion__condicion_iva" in checks
    assert "ck_configuracion_organizacion__no_inscripto_modo_a" in checks


@pytest.mark.parametrize(
    ("tabla", "restriccion"),
    [
        ("costo_informado", "ck_costo_informado__credito_fiscal"),
        ("compra_linea", "ck_compra_linea__credito_fiscal"),
    ],
)
def test_el_check_de_credito_fiscal_esta_en_la_base(
    _engine_de_sesion: Engine, tabla: str, restriccion: str
) -> None:
    assert restriccion in _checks(_engine_de_sesion, tabla)


# --- CHECK de dominio y de D2 sobre la configuración ---------------------------


def _configurar(
    db_session: Session,
    organizacion_id: UUID,
    *,
    condicion: str,
    modo: str,
    modalidad: str | None,
) -> None:
    db_session.execute(
        text(
            "UPDATE configuracion_organizacion SET condicion_iva = :c, modo_impositivo = :m, "
            "modalidad_iva_default = :d WHERE organizacion_id = :o"
        ),
        {"c": condicion, "m": modo, "d": modalidad, "o": organizacion_id},
    )


@pytest.mark.parametrize("condicion", ["RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO"])
def test_cst06_cada_condicion_del_dominio_se_acepta_en_modo_a_sin_modalidad(
    db_session: Session, condicion: str
) -> None:
    organizacion = crear_organizacion(db_session)

    _configurar(db_session, organizacion.id, condicion=condicion, modo="A", modalidad=None)

    guardada = db_session.execute(
        text("SELECT condicion_iva FROM configuracion_organizacion WHERE organizacion_id = :o"),
        {"o": organizacion.id},
    ).scalar_one()
    assert guardada == condicion


@pytest.mark.parametrize("condicion", ["INSCRIPTO", "monotributo", ""])
def test_una_condicion_fuera_del_dominio_se_rechaza(db_session: Session, condicion: str) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _configurar(db_session, organizacion.id, condicion=condicion, modo="A", modalidad=None)

    assert "ck_configuracion_organizacion__condicion_iva" in str(error.value)


@pytest.mark.parametrize("condicion", ["MONOTRIBUTO", "EXENTO"])
@pytest.mark.parametrize(
    ("modo", "modalidad"),
    [("B", None), ("C", None), ("A", "CLIENTE"), ("A", "ABSORBIDO"), ("B", "CLIENTE")],
)
def test_d2_una_organizacion_no_inscripta_exige_modo_a_y_modalidad_nula(
    db_session: Session, condicion: str, modo: str, modalidad: str | None
) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _configurar(
            db_session, organizacion.id, condicion=condicion, modo=modo, modalidad=modalidad
        )

    assert "ck_configuracion_organizacion__no_inscripto_modo_a" in str(error.value)


@pytest.mark.parametrize(
    ("modo", "modalidad"), [("A", None), ("B", "CLIENTE"), ("C", "ABSORBIDO"), ("B", None)]
)
def test_d2_un_responsable_inscripto_conserva_todos_los_modos_y_modalidades(
    db_session: Session, modo: str, modalidad: str | None
) -> None:
    organizacion = crear_organizacion(db_session)

    _configurar(
        db_session,
        organizacion.id,
        condicion="RESPONSABLE_INSCRIPTO",
        modo=modo,
        modalidad=modalidad,
    )


# --- CHECK de D3 sobre costos y líneas -----------------------------------------


def _costo_informado(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "proveedor_id": entorno.proveedor_id,
        "producto_id": entorno.producto_id,
        "presentacion_id": entorno.presentacion_id,
        "valor": 21780,
        "incluye_iva": False,
        "computa_credito_fiscal": False,
        "bonificacion": 0,
        "alicuota_aplicada": 0.21,
        "costo_base": 3630,
        "vigencia_desde": MOMENTO.date(),
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "creado_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _rechaza(db_session: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(db_session, tabla, valores)
    assert restriccion in str(error.value)


@pytest.mark.parametrize(("incluye_iva", "computa"), [(False, False), (False, True), (True, True)])
def test_d3_costo_informado_acepta_las_combinaciones_coherentes(
    db_session: Session, incluye_iva: bool, computa: bool
) -> None:
    entorno = _armar(db_session)

    _insertar(
        db_session,
        "costo_informado",
        _costo_informado(entorno, incluye_iva=incluye_iva, computa_credito_fiscal=computa),
    )


def test_d3_costo_informado_rechaza_incluye_iva_sin_credito_fiscal(db_session: Session) -> None:
    _rechaza(
        db_session,
        "costo_informado",
        _costo_informado(_armar(db_session), incluye_iva=True, computa_credito_fiscal=False),
        "ck_costo_informado__credito_fiscal",
    )


@pytest.mark.parametrize(("incluye_iva", "computa"), [(False, False), (False, True), (True, True)])
def test_d3_compra_linea_acepta_las_combinaciones_coherentes(
    db_session: Session, incluye_iva: bool, computa: bool
) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)

    _insertar(
        db_session,
        "compra_linea",
        _linea(entorno, compra["id"], incluye_iva=incluye_iva, computa_credito_fiscal=computa),
    )


def test_d3_compra_linea_rechaza_incluye_iva_sin_credito_fiscal(db_session: Session) -> None:
    entorno = _armar(db_session)
    compra = _compra(entorno)
    _insertar(db_session, "compra", compra)

    _rechaza(
        db_session,
        "compra_linea",
        _linea(entorno, compra["id"], incluye_iva=True, computa_credito_fiscal=False),
        "ck_compra_linea__credito_fiscal",
    )


# --- permisos (INV-05) ---------------------------------------------------------


def _privilegios(motor: Engine, tabla: str) -> set[str]:
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


@pytest.mark.parametrize("tabla", ["costo_informado", "compra_linea"])
def test_inv05_los_libros_siguen_sin_update_ni_delete_para_app_runtime(
    app_runtime_engine: Engine, tabla: str
) -> None:
    assert _privilegios(app_runtime_engine, tabla) == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == set()


def test_inv05_la_configuracion_sigue_sin_delete_para_app_runtime(
    app_runtime_engine: Engine,
) -> None:
    assert "DELETE" not in _privilegios(app_runtime_engine, "configuracion_organizacion")
    assert "UPDATE" in _privilegios(app_runtime_engine, "configuracion_organizacion")


# --- datos existentes: upgrade, downgrade, upgrade (D9, TR-06) -----------------


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )


def _limpiar_datos_confirmados(motor: Engine) -> None:
    """Esta prueba confirma datos reales en la base compartida de la sesión: los quita
    como el resto de las pruebas que confirman (`TRUNCATE ... CASCADE`), porque otras
    asumen una tabla `organizacion` vacía (por ejemplo `test_seed.py`)."""
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def _sembrar_con_commit(database_url: str) -> tuple[UUID, UUID, UUID]:
    """Una organización con un costo y una compra confirmados, ya commiteados (la base
    es la de la sesión de pytest: el `downgrade` no ve nada sin commit)."""
    motor = create_engine(database_url)
    try:
        with sessionmaker(motor, expire_on_commit=False)() as sesion:
            organizacion = crear_organizacion(sesion)
            usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
            proveedor_id = crear_proveedor(sesion, organizacion.id)
            producto_id = crear_producto_sql(sesion, organizacion.id, proveedor_id=proveedor_id)
            entorno = Entorno(
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                proveedor_id=proveedor_id,
                ubicacion_id=crear_ubicacion_sql(sesion, organizacion.id),
                producto_id=producto_id,
                presentacion_id=crear_presentacion_referencia_sql(
                    sesion, organizacion.id, producto_id
                ),
                medio_pago_id=uuid4(),
                motivo_id=uuid4(),
            )
            costo = _costo_informado(
                entorno, computa_credito_fiscal=True, incluye_iva=True, costo_base=1500
            )
            _insertar(sesion, "costo_informado", costo)
            compra = _compra(entorno)
            _insertar(sesion, "compra", compra)
            linea = _linea(entorno, compra["id"], computa_credito_fiscal=True, costo_base=1000)
            _insertar(sesion, "compra_linea", linea)
            sesion.commit()
            return organizacion.id, costo["id"], linea["id"]  # type: ignore[return-value]
    finally:
        motor.dispose()


def test_tr06_el_ciclo_upgrade_downgrade_upgrade_conserva_los_datos_existentes(
    database_url: str,
) -> None:
    """D9: lo que existía antes de la migración queda como `RESPONSABLE_INSCRIPTO` y con
    `computa_credito_fiscal = true`, con el mismo costo base (TR-06: nada se recalcula)."""
    organizacion_id, costo_id, linea_id = _sembrar_con_commit(database_url)
    try:
        bajada = _alembic("downgrade", REVISION_ANTERIOR, database_url=database_url)
        assert bajada.returncode == 0, bajada.stderr
        subida = _alembic("upgrade", "head", database_url=database_url)
        assert subida.returncode == 0, subida.stderr
    finally:
        _alembic("upgrade", "head", database_url=database_url)

    motor = create_engine(database_url)
    try:
        with motor.connect() as conexion:
            condicion = conexion.execute(
                text(
                    "SELECT condicion_iva FROM configuracion_organizacion "
                    "WHERE organizacion_id = :o"
                ),
                {"o": organizacion_id},
            ).scalar_one()
            costo = conexion.execute(
                text(
                    "SELECT computa_credito_fiscal, costo_base FROM costo_informado WHERE id = :i"
                ),
                {"i": costo_id},
            ).one()
            linea = conexion.execute(
                text("SELECT computa_credito_fiscal, costo_base FROM compra_linea WHERE id = :i"),
                {"i": linea_id},
            ).one()
    finally:
        _limpiar_datos_confirmados(motor)
        motor.dispose()

    assert condicion == "RESPONSABLE_INSCRIPTO"
    assert (costo[0], costo[1]) == (True, Decimal("1500.000000"))
    assert (linea[0], linea[1]) == (True, Decimal("1000.000000"))


def test_el_downgrade_quita_las_columnas_nuevas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        bajada = _alembic("downgrade", REVISION_ANTERIOR, database_url=database_url)
        assert bajada.returncode == 0, bajada.stderr
        sin_columnas = (
            _columna(_engine_de_sesion, "configuracion_organizacion", "condicion_iva") is None
            and _columna(_engine_de_sesion, "costo_informado", "computa_credito_fiscal") is None
            and _columna(_engine_de_sesion, "compra_linea", "computa_credito_fiscal") is None
        )
    finally:
        subida = _alembic("upgrade", "head", database_url=database_url)

    assert sin_columnas
    assert subida.returncode == 0, subida.stderr
