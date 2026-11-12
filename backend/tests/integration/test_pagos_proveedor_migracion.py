"""Tareas 1.1 y 1.2 (change 12): la revisión `d1e2f3a4b5c6` deja el pago a proveedor
con ámbito de motivo `ANULACION_PAGO`, observación, `CHECK` estricto de anulación e
índices de listado (`design.md` D1, D6, D9 opción A).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_compras_migracion.py`); que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py`, y el catálogo completo de columnas de
`pago_proveedor` sigue en `test_compras_migracion.py` (tarea 1.3).

Reglas citadas: INV-02, INV-03, INV-05, INV-21, PAG-03, TR-06, TR-09, CMP-05,
`design.md` D1, D6, D9.
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
from stock_utiles import crear_ubicacion_sql

REVISION = "d1e2f3a4b5c6"
REVISION_ANTERIOR = "a9c0d1e2f3a4"  # `condicion_iva_organizacion`, la previa a este change.
MOMENTO = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
FECHA = date(2026, 10, 1)

AMBITO = "ANULACION_PAGO"
AMBITOS_ANTERIORES = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
MOTIVOS_SEMBRADOS = {"Error de carga", "Pago rechazado o devuelto", "Otro"}

COLUMNAS_MUTABLES = {"estado", "anulado_en", "anulado_por_id", "anulacion_motivo_id"}

ACTUALIZACIONES_PROHIBIDAS = {
    "importe": "1",
    "observacion": "'cambiada'",
    "fecha": "DATE '2026-10-01'",
    "proveedor_id": "NULL",
    "compra_id": "NULL",
}

INDICES = {
    "ix_pago_proveedor__fecha": "(organizacion_id, fecha DESC, id DESC)",
    "ix_pago_proveedor__proveedor_fecha": "(organizacion_id, proveedor_id, fecha DESC, id DESC)",
}


# --- consultas al esquema real -------------------------------------------------


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


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _cantidad_de_filas(motor: Engine, tabla: str) -> int:
    with motor.connect() as conexion:
        return conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one()


def _motivo_del_pago(motor: Engine, pago_id: object) -> UUID | None:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT anulacion_motivo_id FROM pago_proveedor WHERE id = :id"),
            {"id": pago_id},
        ).scalar_one()


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


def _observaciones_de_los_pagos(motor: Engine) -> list[str | None]:
    """Las observaciones de los cuatro pagos sembrados, en orden de id, para que la
    pérdida del `downgrade` (D9) quede escrita como aserción y no como comentario."""
    with motor.connect() as conexion:
        return list(
            conexion.execute(text("SELECT observacion FROM pago_proveedor ORDER BY id"))
            .scalars()
            .all()
        )


# --- la observación (D6) --------------------------------------------------------


def test_la_observacion_del_pago_existe_y_es_nulable(_engine_de_sesion: Engine) -> None:
    """D6, D9 punto 2: `observacion text` nulable; no entra en el `GRANT UPDATE`."""
    assert _columnas(_engine_de_sesion, "pago_proveedor")["observacion"] == ("text", True)


def test_la_observacion_del_pago_admite_texto_y_nulo(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(
        db_session,
        "pago_proveedor",
        _pago(entorno, observacion="Paga facturas 0001-123 y 0001-124"),
    )
    _insertar(db_session, "pago_proveedor", _pago(entorno))

    observaciones = db_session.execute(
        text("SELECT observacion FROM pago_proveedor ORDER BY observacion NULLS FIRST")
    ).scalars()

    assert list(observaciones) == [None, "Paga facturas 0001-123 y 0001-124"]


# --- el ámbito del motivo (D1) --------------------------------------------------


@pytest.mark.parametrize("ambito", [*AMBITOS_ANTERIORES, AMBITO])
def test_ck_motivo_ambito_admite_el_ambito_del_catalogo(db_session: Session, ambito: str) -> None:
    """D9 punto 1: `ck_motivo__ambito` suma `ANULACION_PAGO` sin perder los previos."""
    entorno = _armar(db_session)
    _insertar(db_session, "motivo", _motivo(entorno, ambito=ambito, nombre=f"Motivo {ambito}"))


@pytest.mark.parametrize("ambito", ["ANULACION_PAGOS", "anulacion_pago", "PAGO", ""])
def test_ck_motivo_ambito_rechaza_un_ambito_desconocido(db_session: Session, ambito: str) -> None:
    entorno = _armar(db_session)
    _rechaza(db_session, "motivo", _motivo(entorno, ambito=ambito), "ck_motivo__ambito")


# --- el CHECK estricto de anulación (D9 punto 3) -------------------------------


def test_el_check_de_anulacion_del_pago_es_el_mismo_que_el_de_la_compra(
    _engine_de_sesion: Engine,
) -> None:
    """D9 punto 3: "anulada ⇔ momento, usuario **y motivo**", la misma regla que
    `ck_compra__anulacion_coherente`.

    `compra` nombra sus columnas `anulada_en`/`anulada_por_id` y `pago_proveedor`
    `anulado_en`/`anulado_por_id` (así las creó el change 11), así que la comparación
    normaliza esos dos nombres en la definición de la compra en vez de exigir un texto
    idéntico: lo que se verifica es que el `CHECK` del pago es el de la compra, no el
    laxo anterior (`motivo` opcional)."""
    checks = _restricciones(_engine_de_sesion, "pago_proveedor", "c")
    de_la_compra = (
        _restricciones(_engine_de_sesion, "compra", "c")["ck_compra__anulacion_coherente"]
        .replace("anulada_en", "anulado_en")
        .replace("anulada_por_id", "anulado_por_id")
    )

    assert checks["ck_pago_proveedor__anulacion_coherente"] == de_la_compra
    # Y que no es el laxo: el laxo admitía el motivo en nulo sin anulación.
    assert "anulacion_motivo_id IS NULL OR" not in checks["ck_pago_proveedor__anulacion_coherente"]


def test_la_anulacion_del_pago_exige_motivo_momento_y_usuario(db_session: Session) -> None:
    entorno = _armar(db_session)
    motivo_id = _motivo_de_pago(sesion=db_session, entorno=entorno)
    _insertar(
        db_session,
        "pago_proveedor",
        _pago(
            entorno,
            estado="ANULADA",
            anulado_en=MOMENTO,
            anulado_por_id=entorno.usuario_id,
            anulacion_motivo_id=motivo_id,
        ),
    )

    for incompleta in (
        {"estado": "ANULADA", "anulado_en": MOMENTO, "anulado_por_id": entorno.usuario_id},
        {
            "estado": "ANULADA",
            "anulado_en": None,
            "anulado_por_id": entorno.usuario_id,
            "anulacion_motivo_id": motivo_id,
        },
        {
            "estado": "ANULADA",
            "anulado_en": MOMENTO,
            "anulado_por_id": None,
            "anulacion_motivo_id": motivo_id,
        },
        {"estado": "CONFIRMADA", "anulacion_motivo_id": motivo_id},
    ):
        _rechaza(
            db_session,
            "pago_proveedor",
            _pago(entorno, **incompleta),
            "ck_pago_proveedor__anulacion_coherente",
        )


def test_el_motivo_de_la_compra_sigue_sirviendo_para_su_pago(db_session: Session) -> None:
    """D1: un pago anulado junto con su compra lleva el motivo de la compra, como hoy; el
    ámbito correcto lo exige el servicio (`MOTIVO_INVALIDO`), no la base."""
    entorno = _armar(db_session)
    _insertar(
        db_session,
        "pago_proveedor",
        _pago(
            entorno,
            estado="ANULADA",
            anulado_en=MOMENTO,
            anulado_por_id=entorno.usuario_id,
            anulacion_motivo_id=entorno.motivo_compra_id,
        ),
    )


# --- índices de listado (D9 punto 4) --------------------------------------------


@pytest.mark.parametrize(("nombre", "fragmento"), list(INDICES.items()))
def test_los_indices_de_listado_del_pago_existen(
    _engine_de_sesion: Engine, nombre: str, fragmento: str
) -> None:
    assert fragmento in _indice(_engine_de_sesion, nombre)


# --- permisos (INV-05) ----------------------------------------------------------


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


def test_inv05_app_runtime_no_tiene_delete_y_solo_update_de_estado_y_anulacion(
    app_runtime_engine: Engine,
) -> None:
    """D9 punto 2: los privilegios de `app_runtime` no cambian y `observacion` es
    inmutable, por eso no entra en el `GRANT UPDATE`."""
    assert _privilegios_de_tabla(app_runtime_engine, "pago_proveedor") == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, "pago_proveedor") == COLUMNAS_MUTABLES


def test_inv05_app_runtime_no_puede_borrar_pagos(app_runtime_engine: Engine) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM pago_proveedor"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(("columna", "valor"), list(ACTUALIZACIONES_PROHIBIDAS.items()))
def test_inv05_app_runtime_no_puede_actualizar_nada_mas_del_pago(
    app_runtime_engine: Engine, columna: str, valor: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE pago_proveedor SET {columna} = {valor}"))

    assert "permission denied" in str(error.value)


# --- siembra y ciclo de la migración (D9, tareas 1.1 y 1.2) ---------------------


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


def test_la_migracion_siembra_los_motivos_una_sola_vez_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D1, D9 punto 1: "Error de carga", "Pago rechazado o devuelto" y "Otro" en cada
    organización sin motivos de `ANULACION_PAGO` (aunque tenga de otros ámbitos);
    `downgrade` y `upgrade` no los duplican (tarea 1.2)."""
    with Session(_engine_de_sesion) as sesion:
        vacia = crear_organizacion(sesion).id
        con_otros_ambitos = crear_organizacion(sesion).id
        for ambito in ("ANULACION_COMPRA", "AJUSTE_STOCK"):
            _insertar(
                sesion,
                "motivo",
                {
                    "id": uuid4(),
                    "organizacion_id": con_otros_ambitos,
                    "ambito": ambito,
                    "nombre": f"Otro de {ambito}",
                    "activo": True,
                    "creado_en": MOMENTO,
                    "actualizado_en": MOMENTO,
                },
            )
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _motivos_de_ambito(_engine_de_sesion, vacia, AMBITO) == []
        assert _motivos_de_ambito(_engine_de_sesion, con_otros_ambitos, AMBITO) == []

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        for organizacion_id in (vacia, con_otros_ambitos):
            sembrados = _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)
            assert set(sembrados) == MOTIVOS_SEMBRADOS
            assert len(sembrados) == 3

        repetida = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert repetida.returncode == 0, repetida.stderr
        reaplicada = _alembic(database_url, "upgrade", "head")
        assert reaplicada.returncode == 0, reaplicada.stderr
        assert len(_motivos_de_ambito(_engine_de_sesion, vacia, AMBITO)) == 3
        assert _motivos_de_ambito(_engine_de_sesion, con_otros_ambitos, "ANULACION_COMPRA") == [
            "Otro de ANULACION_COMPRA"
        ]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos_sembrados(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4 y D9: el ciclo sube y baja limpio sobre una base con datos; la
    aserción explícita es lo que el `downgrade` pierde: los motivos de `ANULACION_PAGO`
    (con el motivo del pago anulado en nulo) y las observaciones."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        motivo_pago_id = _motivo_de_pago(sesion=sesion, entorno=entorno)
        compra_vigente = _compra(entorno)
        compra_anulada = _compra(
            entorno,
            estado="ANULADA",
            anulacion_motivo_id=entorno.motivo_compra_id,
            anulada_en=MOMENTO,
            anulada_por_id=entorno.usuario_id,
        )
        _insertar(sesion, "compra", compra_vigente)
        _insertar(sesion, "compra", compra_anulada)
        _insertar(sesion, "pago_proveedor", _pago(entorno))
        _insertar(
            sesion,
            "pago_proveedor",
            _pago(
                entorno,
                origen="COMPRA",
                compra_id=compra_vigente["id"],
                observacion="Pago de contado",
            ),
        )
        anulado_con_su_compra = _pago(
            entorno,
            origen="COMPRA",
            compra_id=compra_anulada["id"],
            estado="ANULADA",
            anulado_en=MOMENTO,
            anulado_por_id=entorno.usuario_id,
            anulacion_motivo_id=entorno.motivo_compra_id,
            observacion="Anulado junto con su compra",
        )
        _insertar(sesion, "pago_proveedor", anulado_con_su_compra)
        anulado_con_motivo_de_pago = _pago(
            entorno,
            estado="ANULADA",
            anulado_en=MOMENTO,
            anulado_por_id=entorno.usuario_id,
            anulacion_motivo_id=motivo_pago_id,
            observacion="El banco rechazó la transferencia",
        )
        _insertar(sesion, "pago_proveedor", anulado_con_motivo_de_pago)
        sesion.commit()
        organizacion_id = entorno.organizacion_id
        motivo_compra_id = entorno.motivo_compra_id

    # Antes de bajar: las tres observaciones sembradas y el motivo del pago anulado
    # junto con su compra, ambos de `ANULACION_COMPRA`, que el `downgrade` NO toca.
    assert sorted(o for o in _observaciones_de_los_pagos(_engine_de_sesion) if o is not None) == [
        "Anulado junto con su compra",
        "El banco rechazó la transferencia",
        "Pago de contado",
    ]

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` pierde, escrito explícito (D9).
        assert "observacion" not in _columnas(_engine_de_sesion, "pago_proveedor")
        assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO) == []
        assert _motivo_del_pago(_engine_de_sesion, anulado_con_motivo_de_pago["id"]) is None
        # Lo que no pierde: los pagos, sus compras y el motivo de la compra.
        assert _cantidad_de_filas(_engine_de_sesion, "pago_proveedor") == 4
        assert _motivo_del_pago(_engine_de_sesion, anulado_con_su_compra["id"]) == motivo_compra_id

        # Y lo que esa pérdida implica: el `upgrade` NO es automático sobre la base
        # que dejó el `downgrade`, porque el guard de D9 punto 3 aborta al encontrar un
        # pago `ANULADA` sin motivo -- el estado que el propio `downgrade` dejó (el
        # `CHECK` estricto del 12 lo rechaza y por eso no se puede schemear). Es el
        # mismo guard que ejercita `test_el_upgrade_aborta_con_un_mensaje_claro...`.
        abortada = _alembic(database_url, "upgrade", "head")
        assert abortada.returncode != 0
        assert "ANULADA" in abortada.stderr
        assert "anulacion_motivo_id" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR

        # Restituido el motivo con uno que el `downgrade` no borra (el de la compra,
        # de ámbito `ANULACION_COMPRA`), el `upgrade` pasa y no duplica los motivos.
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text("UPDATE pago_proveedor SET anulacion_motivo_id = :m WHERE id = :id"),
                {"m": motivo_compra_id, "id": anulado_con_motivo_de_pago["id"]},
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        assert _columnas(_engine_de_sesion, "pago_proveedor")["observacion"] == ("text", True)
        assert set(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == (
            MOTIVOS_SEMBRADOS
        )
        assert _cantidad_de_filas(_engine_de_sesion, "pago_proveedor") == 4
        # Las observaciones tampoco vuelven: la columna se recrea vacía (pérdida de D9).
        assert _observaciones_de_los_pagos(_engine_de_sesion) == [None, None, None, None]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_upgrade_aborta_con_un_mensaje_claro_si_hay_un_pago_anulado_sin_motivo(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D9 punto 3: el change 11 siempre escribe el motivo, pero la revisión lo verifica
    y aborta con un mensaje claro si encuentra un pago `ANULADA` sin él."""
    bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
    assert bajada.returncode == 0, bajada.stderr

    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        pago = _pago(
            entorno,
            estado="ANULADA",
            anulado_en=MOMENTO,
            anulado_por_id=entorno.usuario_id,
        )
        _insertar(sesion, "pago_proveedor", pago)
        sesion.commit()
        pago_id = pago["id"]
        motivo_compra_id = entorno.motivo_compra_id

    try:
        abortada = _alembic(database_url, "upgrade", "head")
        assert abortada.returncode != 0
        assert "ANULADA" in abortada.stderr
        assert "anulacion_motivo_id" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text("UPDATE pago_proveedor SET anulacion_motivo_id = :m WHERE id = :id"),
                {"m": motivo_compra_id, "id": pago_id},
            )
        reparada = _alembic(database_url, "upgrade", "head")
        assert reparada.returncode == 0, reparada.stderr
        # `head` ya no es esta revisión (cada change agrega la suya): alcanza con que haya
        # subido y con que el `CHECK` estricto de este change esté puesto.
        assert _revision_actual(_engine_de_sesion) != REVISION_ANTERIOR
        assert "observacion" in _columnas(_engine_de_sesion, "pago_proveedor")
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    proveedor_id: UUID
    ubicacion_id: UUID
    medio_pago_id: UUID
    motivo_compra_id: UUID


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _armar(sesion: Session) -> Entorno:
    """Organización, usuario, dispositivo, proveedor, ubicación, medio de pago y un
    motivo de `ANULACION_COMPRA` (el que el change 11 ya sembró). El motivo de
    `ANULACION_PAGO` se agrega aparte con `_motivo_de_pago`, porque antes de la revisión
    en curso `ck_motivo__ambito` todavía no lo admite."""
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    medio_pago_id, motivo_compra_id = uuid4(), uuid4()
    _insertar(
        sesion,
        "medio_pago",
        {
            "id": medio_pago_id,
            "organizacion_id": organizacion.id,
            "nombre": "Efectivo",
            "requiere_referencia": False,
            "activo": True,
            "creado_en": MOMENTO,
            "actualizado_en": MOMENTO,
        },
    )
    _insertar(
        sesion,
        "motivo",
        {
            "id": motivo_compra_id,
            "organizacion_id": organizacion.id,
            "ambito": "ANULACION_COMPRA",
            "nombre": "Otro de prueba",
            "activo": True,
            "creado_en": MOMENTO,
            "actualizado_en": MOMENTO,
        },
    )
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        proveedor_id=crear_proveedor(sesion, organizacion.id),
        ubicacion_id=crear_ubicacion_sql(sesion, organizacion.id),
        medio_pago_id=medio_pago_id,
        motivo_compra_id=motivo_compra_id,
    )


def _motivo(
    entorno: Entorno,
    *,
    ambito: str,
    nombre: str = "Motivo de prueba",
    motivo_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": motivo_id or uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "ambito": ambito,
        "nombre": nombre,
        "activo": True,
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
    }


def _motivo_de_pago(*, sesion: Session, entorno: Entorno) -> UUID:
    motivo_id = uuid4()
    _insertar(sesion, "motivo", _motivo(entorno, ambito=AMBITO, motivo_id=motivo_id))
    return motivo_id


def _compra(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "proveedor_id": entorno.proveedor_id,
        "ubicacion_id": entorno.ubicacion_id,
        "fecha": FECHA,
        "condicion": "CONTADO",
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


def _pago(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "proveedor_id": entorno.proveedor_id,
        "fecha": FECHA,
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


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, tabla, valores)
    assert restriccion in str(error.value)
