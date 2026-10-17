"""Tareas 3.1, 3.2 y 3.3 (change 17): la revisión `d7e8f9a0b1c2` crea `cobranza`,
`cobranza_medio` y `cobranza_anulacion`, siembra los motivos de `ANULACION_COBRANZA` y amplía
`ck_observacion__codigo` con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`
(`design.md` D6, D13, D16, `docs/03-modelo-de-datos.md` §12).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_pagos_proveedor_migracion.py`); que los modelos no se desvíen de la migración lo cubre
`test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-03, INV-05, INV-21, TR-06, SYN-07, COB-01, COB-02, COB-05,
`design.md` D6, D13, D16.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
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
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

REVISION = "d7e8f9a0b1c2"
REVISION_ANTERIOR = "b5c6d7e8f9a0"  # `reglas_de_descuento`, la previa a este change.
MOMENTO = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

AMBITO = "ANULACION_COBRANZA"
MOTIVOS_SEMBRADOS = {"Error de carga", "Pago rechazado o no acreditado", "Otro"}

TABLAS = ("cobranza", "cobranza_medio", "cobranza_anulacion")

CODIGOS_PREVIOS = (
    "STOCK_NEGATIVO",
    "EXCESO_CREDITO_ADVERTIDO",
    "EXCESO_CREDITO_AUTORIZADO_OFFLINE",
    "EXCESO_CREDITO_DETECTADO_SYNC",
    "LISTA_NO_VIGENTE",
    "DESCUENTO_DIFIERE",
    "CLIENTE_NO_HABILITADO",
    "PERMISO_REVOCADO",
    "JORNADA_LIBERADA",
    "ANULACION_COMPRA_SIN_RECALCULO",
)
CODIGOS_NUEVOS = ("MEDIO_INACTIVO", "REFERENCIA_FALTANTE")

FKS_ESPERADAS = {
    "cobranza": {
        "fk_cobranza__cliente": ("cliente_id", "cliente"),
        "fk_cobranza__jornada": ("jornada_id", "jornada"),
        "fk_cobranza__usuario": ("usuario_id", "usuario"),
        "fk_cobranza__dispositivo": ("dispositivo_id", "dispositivo"),
    },
    "cobranza_medio": {
        "fk_cobranza_medio__cobranza": ("cobranza_id", "cobranza"),
        "fk_cobranza_medio__medio_pago": ("medio_pago_id", "medio_pago"),
    },
    "cobranza_anulacion": {
        "fk_cobranza_anulacion__cobranza": ("cobranza_id", "cobranza"),
        "fk_cobranza_anulacion__motivo": ("motivo_id", "motivo"),
        "fk_cobranza_anulacion__usuario": ("usuario_id", "usuario"),
        "fk_cobranza_anulacion__dispositivo": ("dispositivo_id", "dispositivo"),
    },
}

INDICES = {
    "ix_cobranza__occurred_at": "(organizacion_id, occurred_at DESC, id DESC)",
    "ix_cobranza__cliente": "(organizacion_id, cliente_id, occurred_at DESC, id DESC)",
    "ix_cobranza__jornada": "(organizacion_id, jornada_id)",
}

COLUMNAS_NUMERIC_14_2 = {
    ("cobranza", "importe"),
    ("cobranza_medio", "importe"),
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


def _existe_tabla(motor: Engine, tabla: str) -> bool:
    with motor.connect() as conexion:
        return bool(
            conexion.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :t"
                ),
                {"t": tabla},
            ).scalar_one()
        )


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


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


# --- las tres tablas (INV-02, INV-03, D16) ---------------------------------------


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv02_cada_tabla_tiene_organizacion_y_unico_con_id(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02: `organizacion_id NOT NULL` y `UNIQUE (organizacion_id, id)` en cada tabla."""
    columnas = _columnas(_engine_de_sesion, tabla)
    assert columnas["organizacion_id"][1] is False

    unicos = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicos[f"ux_{tabla}__org_id"] == "UNIQUE (organizacion_id, id)"


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv02_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02, D16: cada FK a otra entidad de negocio incluye `organizacion_id`."""
    foraneas = _restricciones(_engine_de_sesion, tabla, "f")
    esperadas = FKS_ESPERADAS[tabla]

    assert set(foraneas) == {f"fk_{tabla}__organizacion", *esperadas}
    for nombre, (columna, destino) in esperadas.items():
        assert foraneas[nombre] == (
            f"FOREIGN KEY (organizacion_id, {columna}) REFERENCES {destino}(organizacion_id, id)"
        )


def test_la_venta_de_la_cobranza_es_nulable_y_no_tiene_clave_foranea(
    _engine_de_sesion: Engine,
) -> None:
    """D16: `venta_id` nulable y sin FK hasta el change 18a (la tabla `venta` no existe)."""
    assert _columnas(_engine_de_sesion, "cobranza")["venta_id"][1] is True
    foraneas = _restricciones(_engine_de_sesion, "cobranza", "f")
    assert not any("venta_id" in definicion for definicion in foraneas.values())


def test_inv02_una_cobranza_no_referencia_un_cliente_de_otra_organizacion(
    db_session: Session,
) -> None:
    """INV-02, INV-21: la FK compuesta rechaza un cliente de otra organización."""
    propio = _armar(db_session)
    ajeno = _armar(db_session)

    _rechaza(
        db_session,
        "cobranza",
        _cobranza(propio, cliente_id=ajeno.cliente_id),
        "fk_cobranza__cliente",
    )


def test_inv02_una_cobranza_no_referencia_la_jornada_de_otra_organizacion(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    jornada_ajena = crear_jornada_sql(
        db_session,
        ajeno.organizacion_id,
        usuario_id=ajeno.usuario_id,
        dispositivo_id=ajeno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(db_session, ajeno.organizacion_id, requiere_toma=True),
    )

    _rechaza(
        db_session,
        "cobranza",
        _cobranza(propio, jornada_id=jornada_ajena),
        "fk_cobranza__jornada",
    )


def test_inv02_un_medio_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    cobranza = _cobranza(propio)
    _insertar(db_session, "cobranza", cobranza)

    _rechaza(
        db_session,
        "cobranza_medio",
        _medio(propio, cobranza["id"], medio_pago_id=ajeno.medio_pago_id),
        "fk_cobranza_medio__medio_pago",
    )


def test_inv02_el_motivo_de_la_anulacion_debe_ser_de_la_misma_organizacion(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    cobranza = _cobranza(propio)
    _insertar(db_session, "cobranza", cobranza)

    _rechaza(
        db_session,
        "cobranza_anulacion",
        _anulacion(propio, cobranza["id"], motivo_id=ajeno.motivo_id),
        "fk_cobranza_anulacion__motivo",
    )


@pytest.mark.parametrize(("tabla", "columna"), sorted(COLUMNAS_NUMERIC_14_2))
def test_inv03_los_importes_son_numeric_14_2(
    _engine_de_sesion: Engine, tabla: str, columna: str
) -> None:
    """INV-03: importe `numeric(14,2)`, nunca punto flotante."""
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": tabla, "c": columna},
        ).one()

    assert tuple(fila) == ("numeric", 14, 2)


def test_la_cobranza_no_se_inserta_con_importe_no_positivo(db_session: Session) -> None:
    """INV-03, COB-01: `importe > 0` en la cabecera y en cada medio."""
    entorno = _armar(db_session)
    for invalido in (0, -1):
        _rechaza(
            db_session, "cobranza", _cobranza(entorno, importe=invalido), "ck_cobranza__importe"
        )

    cobranza = _cobranza(entorno)
    _insertar(db_session, "cobranza", cobranza)
    for invalido in (0, -5):
        _rechaza(
            db_session,
            "cobranza_medio",
            _medio(entorno, cobranza["id"], importe=invalido),
            "ck_cobranza_medio__importe",
        )


def test_el_estado_de_la_cobranza_es_del_catalogo(db_session: Session) -> None:
    entorno = _armar(db_session)
    for estado in ("CONFIRMADA", "ANULADA"):
        _insertar(db_session, "cobranza", _cobranza(entorno, estado=estado))
    for estado in ("PENDIENTE", "confirmada", ""):
        _rechaza(db_session, "cobranza", _cobranza(entorno, estado=estado), "ck_cobranza__estado")


def test_el_origen_es_coherente_con_la_venta(db_session: Session) -> None:
    """COB-01, D16: `VENTA` exige `venta_id`; `INDEPENDIENTE` no lo admite."""
    entorno = _armar(db_session)
    _insertar(db_session, "cobranza", _cobranza(entorno))
    _insertar(db_session, "cobranza", _cobranza(entorno, origen="VENTA", venta_id=uuid4()))

    _rechaza(
        db_session,
        "cobranza",
        _cobranza(entorno, origen="VENTA", venta_id=None),
        "ck_cobranza__origen_venta",
    )
    _rechaza(
        db_session,
        "cobranza",
        _cobranza(entorno, origen="INDEPENDIENTE", venta_id=uuid4()),
        "ck_cobranza__origen_venta",
    )
    _rechaza(db_session, "cobranza", _cobranza(entorno, origen="OTRO"), "ck_cobranza__origen")


def test_la_cobranza_admite_jornada_nula_y_observacion(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "cobranza", _cobranza(entorno, observacion="paga facturas de septiembre"))
    _insertar(db_session, "cobranza", _cobranza(entorno))

    observaciones = db_session.execute(
        text("SELECT observacion FROM cobranza ORDER BY observacion NULLS FIRST")
    ).scalars()
    assert list(observaciones) == [None, "paga facturas de septiembre"]


def test_la_referencia_de_un_medio_es_nulable(db_session: Session) -> None:
    """D13: una referencia faltante se guarda nula."""
    entorno = _armar(db_session)
    cobranza = _cobranza(entorno)
    _insertar(db_session, "cobranza", cobranza)
    _insertar(db_session, "cobranza_medio", _medio(entorno, cobranza["id"], referencia=None))
    _insertar(db_session, "cobranza_medio", _medio(entorno, cobranza["id"], referencia="0042"))


def test_las_posiciones_de_los_medios_no_se_repiten_en_una_cobranza(db_session: Session) -> None:
    entorno = _armar(db_session)
    cobranza = _cobranza(entorno)
    _insertar(db_session, "cobranza", cobranza)
    _insertar(db_session, "cobranza_medio", _medio(entorno, cobranza["id"], orden=0))
    _insertar(db_session, "cobranza_medio", _medio(entorno, cobranza["id"], orden=1))

    _rechaza(
        db_session,
        "cobranza_medio",
        _medio(entorno, cobranza["id"], orden=1),
        "ux_cobranza_medio__cobranza_orden",
    )
    _rechaza(
        db_session,
        "cobranza_medio",
        _medio(entorno, cobranza["id"], orden=-1),
        "ck_cobranza_medio__orden",
    )


def test_una_cobranza_se_anula_una_sola_vez_por_la_base(db_session: Session) -> None:
    """INV-05, TR-06, D16: `cobranza_id` único en `cobranza_anulacion`."""
    entorno = _armar(db_session)
    cobranza = _cobranza(entorno)
    _insertar(db_session, "cobranza", cobranza)
    _insertar(db_session, "cobranza_anulacion", _anulacion(entorno, cobranza["id"]))

    _rechaza(
        db_session,
        "cobranza_anulacion",
        _anulacion(entorno, cobranza["id"]),
        "ux_cobranza_anulacion__cobranza",
    )


@pytest.mark.parametrize(("nombre", "fragmento"), list(INDICES.items()))
def test_los_indices_de_listado_y_de_jornada_existen(
    _engine_de_sesion: Engine, nombre: str, fragmento: str
) -> None:
    assert fragmento in _indice(_engine_de_sesion, nombre)


# --- la observación nueva (D13, SYN-07) ----------------------------------------


@pytest.mark.parametrize("codigo", [*CODIGOS_PREVIOS, *CODIGOS_NUEVOS])
def test_syn07_ck_observacion_codigo_admite_el_catalogo(db_session: Session, codigo: str) -> None:
    """SYN-07: el `CHECK` admite los diez códigos previos y los dos de D13."""
    entorno = _armar(db_session)
    _insertar_observacion(db_session, entorno, codigo=codigo)


@pytest.mark.parametrize("codigo", ["MEDIO_INACTIVOS", "medio_inactivo", "JORNADA_CERRADA", ""])
def test_syn07_ck_observacion_codigo_rechaza_un_codigo_fuera_del_catalogo(
    db_session: Session, codigo: str
) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_observacion(db_session, entorno, codigo=codigo)
    assert "ck_observacion__codigo" in str(error.value)


# --- permisos (INV-05, TR-06) ----------------------------------------------------


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
def test_inv05_app_runtime_solo_lee_e_inserta(app_runtime_engine: Engine, tabla: str) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}


def test_inv05_el_unico_update_es_el_estado_de_la_cobranza(app_runtime_engine: Engine) -> None:
    """TR-06, D16: `UPDATE` solo de `cobranza.estado`; medios y anulaciones, ninguno."""
    assert _columnas_con_update(app_runtime_engine, "cobranza") == {"estado"}
    assert _columnas_con_update(app_runtime_engine, "cobranza_medio") == set()
    assert _columnas_con_update(app_runtime_engine, "cobranza_anulacion") == set()


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv05_app_runtime_no_puede_borrar(app_runtime_engine: Engine, tabla: str) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "columna", "valor"),
    [
        ("cobranza", "importe", "1"),
        ("cobranza", "observacion", "'cambiada'"),
        ("cobranza", "cliente_id", "NULL"),
        ("cobranza_medio", "importe", "1"),
        ("cobranza_medio", "referencia", "'x'"),
        ("cobranza_anulacion", "motivo_id", "NULL"),
        ("cobranza_anulacion", "observacion", "'x'"),
    ],
)
def test_inv05_app_runtime_no_puede_actualizar_nada_mas(
    app_runtime_engine: Engine, tabla: str, columna: str, valor: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = {valor}"))

    assert "permission denied" in str(error.value)


# --- siembra y ciclo de la migración (D6, D16, tarea 3.3) ------------------------


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


# Escenario: "Organización existente"
def test_la_migracion_siembra_los_motivos_una_sola_vez_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D6, D16: "Error de carga", "Pago rechazado o no acreditado" y "Otro" en cada
    organización sin motivos de `ANULACION_COBRANZA` (aunque tenga de otros ámbitos);
    una organización con motivos propios no se toca; `downgrade` y `upgrade` no duplican."""
    with Session(_engine_de_sesion) as sesion:
        vacia = crear_organizacion(sesion).id
        con_otros_ambitos = crear_organizacion(sesion).id
        con_propios = crear_organizacion(sesion).id
        for organizacion_id, ambito, nombre in (
            (con_otros_ambitos, "ANULACION_COMPRA", "Otro de compras"),
            (con_propios, AMBITO, "Motivo propio"),
        ):
            sesion.execute(
                text(
                    "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, "
                    "creado_en, actualizado_en) VALUES (:id, :o, :a, :n, true, :m, :m)"
                ),
                {"id": uuid4(), "o": organizacion_id, "a": ambito, "n": nombre, "m": MOMENTO},
            )
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _motivos_de_ambito(_engine_de_sesion, vacia, AMBITO) == []

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        for organizacion_id in (vacia, con_otros_ambitos):
            sembrados = _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)
            assert set(sembrados) == MOTIVOS_SEMBRADOS
            assert len(sembrados) == 3

        # Una segunda vuelta no duplica nada.
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert len(_motivos_de_ambito(_engine_de_sesion, vacia, AMBITO)) == 3
        assert _motivos_de_ambito(_engine_de_sesion, con_otros_ambitos, "ANULACION_COMPRA") == [
            "Otro de compras"
        ]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4, D16: el ciclo sube y baja limpio sobre una base con clientes con saldo
    inicial, una cobranza y una anulada. Lo que el `downgrade` pierde queda como aserción
    explícita: las tres tablas (las cobranzas y sus medios y anulaciones) y los motivos de
    `ANULACION_COBRANZA`. Lo que no pierde: clientes y su libro de cuenta."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        motivo_id = entorno.motivo_id
        sesion.execute(
            text(
                "INSERT INTO cuenta_movimiento (id, organizacion_id, cuenta_tipo, entidad_id, "
                "tipo, sentido, importe, origen_tipo, origen_id, occurred_at, registered_at, "
                "usuario_id, operation_id, dispositivo_id) VALUES (:id, :o, 'CLIENTE', :c, "
                "'SALDO_INICIAL', 'AUMENTA', 150000, 'SALDO_INICIAL', :c, :m, :m, :u, :op, :d)"
            ),
            {
                "id": uuid4(),
                "o": entorno.organizacion_id,
                "c": entorno.cliente_id,
                "m": MOMENTO,
                "u": entorno.usuario_id,
                "op": uuid4(),
                "d": entorno.dispositivo_id,
            },
        )
        vigente = _cobranza(entorno)
        anulada = _cobranza(entorno, estado="ANULADA")
        _insertar(sesion, "cobranza", vigente)
        _insertar(sesion, "cobranza", anulada)
        _insertar(sesion, "cobranza_medio", _medio(entorno, vigente["id"]))
        _insertar(sesion, "cobranza_medio", _medio(entorno, anulada["id"]))
        _insertar(sesion, "cobranza_anulacion", _anulacion(entorno, anulada["id"]))
        sesion.commit()
        organizacion_id = entorno.organizacion_id

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` pierde, escrito explícito (D16).
        for tabla in TABLAS:
            assert not _existe_tabla(_engine_de_sesion, tabla)
        assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO) == []
        # Lo que no pierde.
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM cliente")).scalar_one() == 1
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM cuenta_movimiento WHERE organizacion_id = :o"),
                    {"o": organizacion_id},
                ).scalar_one()
                == 1
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        for tabla in TABLAS:
            assert _existe_tabla(_engine_de_sesion, tabla)
        # Las cobranzas no vuelven (pérdida de D16) y los motivos se resiembran sin duplicar.
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM cobranza")).scalar_one() == 0
        assert set(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == (
            MOTIVOS_SEMBRADOS
        )
        assert len(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == 3
        assert motivo_id is not None
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


@pytest.mark.parametrize("codigo", CODIGOS_NUEVOS)
def test_el_downgrade_aborta_si_hay_observaciones_con_los_codigos_nuevos(
    database_url: str, _engine_de_sesion: Engine, codigo: str
) -> None:
    """D13 punto 6, SYN-07: volver el `CHECK` atrás con observaciones `MEDIO_INACTIVO` o
    `REFERENCIA_FALTANTE` las dejaría inválidas; el `downgrade` aborta con un mensaje claro y
    no toca nada. Sin esas filas, baja."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar_observacion(sesion, entorno, codigo=codigo)
        sesion.commit()

    try:
        # Una revisión posterior (17b) puede estar encima: se baja primero hasta la de este change.
        escalon = _alembic(database_url, "downgrade", REVISION)
        assert escalon.returncode == 0, escalon.stderr
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert codigo in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION
        for tabla in TABLAS:
            assert _existe_tabla(_engine_de_sesion, tabla)

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM observacion WHERE codigo = :c"), {"c": codigo})
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    cliente_id: UUID
    medio_pago_id: UUID
    motivo_id: UUID


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _armar(sesion: Session) -> Entorno:
    """Organización con usuario, dispositivo, cliente, un medio de pago y un motivo de
    `ANULACION_COBRANZA` propio de la prueba."""
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    medio_pago_id, motivo_id = uuid4(), uuid4()
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
            "id": motivo_id,
            "organizacion_id": organizacion.id,
            "ambito": AMBITO,
            "nombre": f"Motivo de prueba {motivo_id.hex[:6]}",
            "activo": True,
            "creado_en": MOMENTO,
            "actualizado_en": MOMENTO,
        },
    )
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        cliente_id=crear_cliente(sesion, organizacion.id),
        medio_pago_id=medio_pago_id,
        motivo_id=motivo_id,
    )


def _cobranza(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "cliente_id": entorno.cliente_id,
        "origen": "INDEPENDIENTE",
        "importe": 50000,
        "estado": "CONFIRMADA",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _medio(entorno: Entorno, cobranza_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "cobranza_id": cobranza_id,
        "orden": 0,
        "medio_pago_id": entorno.medio_pago_id,
        "importe": 50000,
    }
    if "orden" not in cambios:
        valores["orden"] = uuid4().int % 1_000_000  # evita chocar con otro medio de la prueba
    valores.update(cambios)
    return valores


def _anulacion(entorno: Entorno, cobranza_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "cobranza_id": cobranza_id,
        "motivo_id": entorno.motivo_id,
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _insertar_observacion(sesion: Session, entorno: Entorno, *, codigo: str) -> None:
    """Una observación con su comando mínimo (lo que se prueba es el `CHECK` del código)."""
    comando_id = uuid4()
    _insertar(
        sesion,
        "comando",
        {
            "id": comando_id,
            "organizacion_id": entorno.organizacion_id,
            "operation_id": uuid4(),
            "tipo": "COBRANZA_REGISTRAR",
            "version": 1,
            "modo": "OFFLINE",
            "usuario_id": entorno.usuario_id,
            "dispositivo_id": entorno.dispositivo_id,
            "secuencia": 1,
            "huella": "h",
            "app_version": "1.0.0",
            "estado": "ACEPTADO_CON_OBSERVACIONES",
            "occurred_at": MOMENTO,
            "registered_at": MOMENTO,
        },
    )
    _insertar(
        sesion,
        "observacion",
        {
            "id": uuid4(),
            "organizacion_id": entorno.organizacion_id,
            "comando_id": comando_id,
            "operacion_tipo": "COBRANZA_REGISTRAR",
            "operacion_id": uuid4(),
            "codigo": codigo,
            "estado": "PENDIENTE",
        },
    )


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, tabla, valores)
    assert restriccion in str(error.value)
