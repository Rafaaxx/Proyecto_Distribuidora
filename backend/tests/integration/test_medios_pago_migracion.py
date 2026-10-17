"""Tareas 1.1 a 1.4 (change 17b; `design.md` D3, D5): la revisión de Alembic sobre
`d7e8f9a0b1c2` crea `ux_medio_pago__nombre` (único por organización sin distinguir mayúsculas) y
marca `requiere_referencia = true` en Transferencia, Cheque y Tarjeta de toda organización
existente. El `downgrade` borra el índice y NO revierte las marcas (D5-A).

Consulta el esquema REAL de PostgreSQL ya migrado. Reglas citadas: INV-02, INV-05, TR-06, TR-09,
COB-02, CAT-05.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

REVISION_ANTERIOR = "d7e8f9a0b1c2"  # `cobranzas`, la previa a este change.
MOMENTO = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
INDICE = "ux_medio_pago__nombre"


def _insertar_medio(
    sesion: Session,
    organizacion_id: UUID,
    nombre: str,
    *,
    requiere_referencia: bool = False,
    activo: bool = True,
) -> UUID:
    medio_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, activo, "
            "creado_en, actualizado_en) VALUES (:id, :o, :n, :r, :a, :m, :m)"
        ),
        {
            "id": medio_id,
            "o": organizacion_id,
            "n": nombre,
            "r": requiere_referencia,
            "a": activo,
            "m": MOMENTO,
        },
    )
    return medio_id


def _marcas(motor: Engine, organizacion_id: UUID) -> dict[str, bool]:
    with motor.connect() as conexion:
        return {
            nombre: marca
            for nombre, marca in conexion.execute(
                text(
                    "SELECT nombre, requiere_referencia FROM medio_pago WHERE organizacion_id = :o"
                ),
                {"o": organizacion_id},
            )
        }


def _definicion_del_indice(motor: Engine) -> str | None:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": INDICE},
        ).scalar_one_or_none()


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
    """La base es compartida con el resto de la sesión: toda prueba que mueve Alembic DEBE
    terminar en `head` y sin filas propias."""
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr


# --- el índice único (D3, INV-02) -------------------------------------------------


def test_el_indice_es_unico_sobre_organizacion_y_nombre_en_minusculas(
    _engine_de_sesion: Engine,
) -> None:
    definicion = _definicion_del_indice(_engine_de_sesion)

    assert definicion is not None
    assert "CREATE UNIQUE INDEX" in definicion
    assert "(organizacion_id, lower(nombre))" in definicion


def test_inv02_dos_nombres_que_solo_difieren_en_mayusculas_se_rechazan_en_la_misma_organizacion(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_medio(db_session, organizacion.id, "Mercado Pago")

    for repetido in ("mercado pago", "MERCADO PAGO"):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar_medio(db_session, organizacion.id, repetido)
        assert INDICE in str(error.value)


def test_el_mismo_nombre_se_acepta_en_organizaciones_distintas(db_session: Session) -> None:
    una = crear_organizacion(db_session)
    otra = crear_organizacion(db_session)

    _insertar_medio(db_session, una.id, "Efectivo")
    _insertar_medio(db_session, otra.id, "efectivo")


def test_el_nombre_repetido_se_rechaza_aunque_el_existente_este_de_baja(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_medio(db_session, organizacion.id, "Billetera", activo=False)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_medio(db_session, organizacion.id, "billetera")
    assert INDICE in str(error.value)


# --- valores por defecto en la organización existente (D5-A) --------------------------


def test_la_migracion_marca_referencia_en_transferencia_cheque_y_tarjeta(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D5-A: una organización creada antes de la migración, con sus cinco medios sin
    referencia, queda con Transferencia, Cheque y Tarjeta en `true` (sin distinguir
    mayúsculas); Efectivo, Billetera y cualquier otro nombre no cambian. COB-02."""
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with Session(_engine_de_sesion) as sesion:
            canonica = crear_organizacion(sesion).id
            en_otras_letras = crear_organizacion(sesion).id
            for nombre in ("Efectivo", "Transferencia", "Cheque", "Billetera", "Tarjeta"):
                _insertar_medio(sesion, canonica, nombre)
            _insertar_medio(sesion, en_otras_letras, "TRANSFERENCIA")
            _insertar_medio(sesion, en_otras_letras, "tarjeta")
            _insertar_medio(sesion, en_otras_letras, "Tarjeta de crédito")
            _insertar_medio(sesion, en_otras_letras, "Cheque", activo=False)
            sesion.commit()

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        assert _marcas(_engine_de_sesion, canonica) == {
            "Efectivo": False,
            "Transferencia": True,
            "Cheque": True,
            "Billetera": False,
            "Tarjeta": True,
        }
        assert _marcas(_engine_de_sesion, en_otras_letras) == {
            "TRANSFERENCIA": True,
            "tarjeta": True,
            "Tarjeta de crédito": False,
            "Cheque": True,
        }
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_la_migracion_no_toca_un_medio_que_ya_tenia_la_marca_ni_cambia_otros_valores(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with Session(_engine_de_sesion) as sesion:
            organizacion = crear_organizacion(sesion).id
            _insertar_medio(sesion, organizacion, "Cheque", requiere_referencia=True)
            _insertar_medio(sesion, organizacion, "Mercado Pago", requiere_referencia=True)
            _insertar_medio(sesion, organizacion, "Efectivo", requiere_referencia=False)
            sesion.commit()

        assert _alembic(database_url, "upgrade", "head").returncode == 0

        assert _marcas(_engine_de_sesion, organizacion) == {
            "Cheque": True,
            "Mercado Pago": True,
            "Efectivo": False,
        }
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- nombres repetidos: la migración aborta sin cambiar nada (D3-A) ------------------


def test_la_migracion_aborta_con_un_mensaje_que_nombra_la_organizacion_y_el_nombre(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with Session(_engine_de_sesion) as sesion:
            conflictiva = crear_organizacion(sesion).id
            _insertar_medio(sesion, conflictiva, "Billetera")
            _insertar_medio(sesion, conflictiva, "billetera")
            _insertar_medio(sesion, conflictiva, "Transferencia")
            sesion.commit()

        abortada = _alembic(database_url, "upgrade", "head")

        assert abortada.returncode != 0
        mensaje = abortada.stderr
        assert str(conflictiva) in mensaje
        assert "billetera" in mensaje.lower()
        # No cambió nada: sin índice y sin marcas.
        assert _definicion_del_indice(_engine_de_sesion) is None
        assert _marcas(_engine_de_sesion, conflictiva)["Transferencia"] is False
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_dos_organizaciones_con_el_mismo_nombre_no_abortan_la_migracion(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        with Session(_engine_de_sesion) as sesion:
            for _ in range(2):
                _insertar_medio(sesion, crear_organizacion(sesion).id, "Billetera")
            sesion.commit()

        subida = _alembic(database_url, "upgrade", "head")

        assert subida.returncode == 0, subida.stderr
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- ciclo upgrade -> downgrade -> upgrade con datos (D5-A, 04 §2.1 punto 4) ----------


def test_el_ciclo_sube_y_baja_limpio_y_el_downgrade_no_revierte_las_marcas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Un medio usado en una cobranza y otro en un pago a proveedor: el ciclo corre sin errores y
    no duplica medios; el
    `downgrade` borra el índice y **no** revierte las marcas (D5-A: después del 17b el valor
    pudo haberlo elegido una persona)."""
    from cobranzas_utiles import MOMENTO as MOMENTO_COBRANZA
    from cobranzas_utiles import Entorno as EntornoCobranza
    from cuentas_corrientes_utiles import crear_proveedor

    with Session(_engine_de_sesion) as sesion:
        entorno = EntornoCobranza(sesion)
        organizacion = entorno.org
        transferencia = entorno.transferencia_id
        # Como estaba la organización antes del 17b: Transferencia sin la marca.
        sesion.execute(
            text("UPDATE medio_pago SET requiere_referencia = false WHERE id = :i"),
            {"i": transferencia},
        )
        cobranza = uuid4()
        sesion.execute(
            text(
                "INSERT INTO cobranza (id, organizacion_id, cliente_id, importe, estado, origen, "
                "occurred_at, registered_at, usuario_id, operation_id, dispositivo_id) "
                "VALUES (:id, :o, :c, 100, 'CONFIRMADA', 'INDEPENDIENTE', :m, :m, :u, :op, :d)"
            ),
            {
                "id": cobranza,
                "o": organizacion,
                "c": entorno.cliente_id,
                "m": MOMENTO_COBRANZA,
                "u": entorno.usuario_id,
                "op": uuid4(),
                "d": entorno.dispositivo_id,
            },
        )
        sesion.execute(
            text(
                "INSERT INTO cobranza_medio (id, organizacion_id, cobranza_id, medio_pago_id, "
                "importe, orden) VALUES (:id, :o, :cb, :mp, 100, 0)"
            ),
            {"id": uuid4(), "o": organizacion, "cb": cobranza, "mp": transferencia},
        )
        # Un pago a proveedor (PAG-01) que usa un medio propio de la organización.
        cheque = _insertar_medio(sesion, organizacion, "Cheque propio")
        pago = uuid4()
        sesion.execute(
            text(
                "INSERT INTO pago_proveedor (id, organizacion_id, proveedor_id, fecha, importe, "
                "estado, origen, operation_id, usuario_id, dispositivo_id, occurred_at, "
                "registered_at) VALUES (:id, :o, :p, '2026-10-17', 50, 'CONFIRMADA', "
                "'INDEPENDIENTE', :op, :u, :d, :m, :m)"
            ),
            {
                "id": pago,
                "o": organizacion,
                "p": crear_proveedor(sesion, organizacion, nombre="Bodega Sur"),
                "op": uuid4(),
                "u": entorno.usuario_id,
                "d": entorno.dispositivo_id,
                "m": MOMENTO_COBRANZA,
            },
        )
        sesion.execute(
            text(
                "INSERT INTO pago_proveedor_medio (id, organizacion_id, pago_id, medio_pago_id, "
                "importe) VALUES (:id, :o, :pg, :mp, 50)"
            ),
            {"id": uuid4(), "o": organizacion, "pg": pago, "mp": cheque},
        )
        sesion.commit()
        nombres_antes = sorted(_marcas(_engine_de_sesion, organizacion))

    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _definicion_del_indice(_engine_de_sesion) is None

        # La subida marca Transferencia (la base la tenía en `false`).
        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _definicion_del_indice(_engine_de_sesion) is not None
        assert _marcas(_engine_de_sesion, organizacion)["Transferencia"] is True

        # El `downgrade` borra el índice y NO revierte la marca (D5-A).
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _definicion_del_indice(_engine_de_sesion) is None
        assert _marcas(_engine_de_sesion, organizacion)["Transferencia"] is True

        assert _alembic(database_url, "upgrade", "head").returncode == 0
        # No duplicó medios y la cobranza sigue apuntando a su medio.
        assert sorted(_marcas(_engine_de_sesion, organizacion)) == nombres_antes
        with _engine_de_sesion.connect() as conexion:
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM cobranza_medio WHERE medio_pago_id = :i"),
                    {"i": transferencia},
                ).scalar_one()
                == 1
            )
            # ... y el pago a proveedor también sigue apuntando al suyo, sin duplicarse.
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM pago_proveedor_medio WHERE medio_pago_id = :i"),
                    {"i": cheque},
                ).scalar_one()
                == 1
            )
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM medio_pago WHERE id = :i"), {"i": cheque}
                ).scalar_one()
                == 1
            )
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- privilegios (INV-05, TR-06) ----------------------------------------------------


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


def test_inv05_app_runtime_sigue_sin_delete_sobre_medio_pago(app_runtime_engine: Engine) -> None:
    """TR-06, CAT-05: un medio se da de baja, nunca se borra."""
    privilegios = _privilegios(app_runtime_engine, "medio_pago")

    assert "DELETE" not in privilegios
    assert {"SELECT", "INSERT", "UPDATE"} <= privilegios
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM medio_pago"))
    assert "permission denied" in str(error.value)
