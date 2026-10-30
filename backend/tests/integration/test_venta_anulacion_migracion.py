"""Tarea 3.1 (change 19; spec `ventas/anulacion-de-venta` y `organizacion/catalogos-configurables`;
`design.md` D11, D12): la revisión `d9e0f1a2b3c4` crea `venta_anulacion`, da `SELECT, INSERT` a
`app_runtime` sobre ella y `UPDATE (estado)` sobre `venta`, y siembra los motivos de
`ANULACION_VENTA`.

Consulta el esquema REAL de PostgreSQL ya migrado. Reglas citadas: INV-05, INV-02, VTA-20,
`04` §2.1 punto 4.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
from stock_utiles import crear_motivo_sql
from ventas_utiles import MOMENTO, insertar_sql, sembrar_venta_sql

REVISION = "d9e0f1a2b3c4"
REVISION_ANTERIOR = "c8d9e0f1a2b3"
REVISION_HEAD = "f1a2b3c4d5e6"  # `usuarios_roles_y_cartera` (change 20b), la cabeza actual.
AMBITO = "ANULACION_VENTA"
MOTIVOS_SEMBRADOS = ["Devolución del cliente", "Error de carga", "Otro"]

FKS_ESPERADAS = {
    "fk_venta_anulacion__venta": "FOREIGN KEY (organizacion_id, venta_id) "
    "REFERENCES venta(organizacion_id, id)",
    "fk_venta_anulacion__motivo": "FOREIGN KEY (organizacion_id, motivo_id) "
    "REFERENCES motivo(organizacion_id, id)",
    "fk_venta_anulacion__jornada": "FOREIGN KEY (organizacion_id, jornada_id) "
    "REFERENCES jornada(organizacion_id, id)",
    "fk_venta_anulacion__usuario": "FOREIGN KEY (organizacion_id, usuario_id) "
    "REFERENCES usuario(organizacion_id, id)",
    "fk_venta_anulacion__dispositivo": "FOREIGN KEY (organizacion_id, dispositivo_id) "
    "REFERENCES dispositivo(organizacion_id, id)",
}


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
    """La base es compartida con el resto de la sesión: termina en `head` y sin filas."""
    subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _columnas(motor: Engine, tabla: str) -> dict[str, tuple[str, bool]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": tabla},
        )
        return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def _restricciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:t AS regclass) AND contype = :tipo"
                ),
                {"t": f"public.{tabla}", "tipo": tipo},
            ).all()
        )


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


def _motivos(motor: Engine, organizacion_id: UUID) -> list[str]:
    with motor.connect() as conexion:
        return list(
            conexion.execute(
                text(
                    "SELECT nombre FROM motivo WHERE organizacion_id = :o "
                    "AND ambito = :a AND activo ORDER BY nombre"
                ),
                {"o": organizacion_id, "a": AMBITO},
            )
            .scalars()
            .all()
        )


# --- la tabla (INV-02, D11) --------------------------------------------------------


def test_inv02_venta_anulacion_tiene_sus_columnas_y_nulabilidad(_engine_de_sesion: Engine) -> None:
    """D11: `devuelve_dinero` y `jornada_id` nulables; el resto, `NOT NULL`."""
    columnas = _columnas(_engine_de_sesion, "venta_anulacion")
    assert {nombre: columnas[nombre] for nombre in columnas} == {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "venta_id": ("uuid", False),
        "motivo_id": ("uuid", False),
        "observacion": ("text", True),
        "devuelve_dinero": ("boolean", True),
        "jornada_id": ("uuid", True),
        "operation_id": ("uuid", False),
        "usuario_id": ("uuid", False),
        "dispositivo_id": ("uuid", False),
        "occurred_at": ("timestamp with time zone", False),
        "registered_at": ("timestamp with time zone", False),
    }


def test_inv02_las_claves_foraneas_son_compuestas_con_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    foraneas = _restricciones(_engine_de_sesion, "venta_anulacion", "f")
    for nombre, definicion in FKS_ESPERADAS.items():
        assert foraneas[nombre] == definicion
    assert foraneas["fk_venta_anulacion__organizacion"] == (
        "FOREIGN KEY (organizacion_id) REFERENCES organizacion(id)"
    )


def test_la_venta_se_anula_una_sola_vez_y_hay_unico_con_id_e_indice(
    _engine_de_sesion: Engine,
) -> None:
    """D11: `UNIQUE (organizacion_id, venta_id)`, `UNIQUE (organizacion_id, id)` e índice por
    momento."""
    unicos = _restricciones(_engine_de_sesion, "venta_anulacion", "u")
    assert unicos["ux_venta_anulacion__venta"] == "UNIQUE (organizacion_id, venta_id)"
    assert unicos["ux_venta_anulacion__org_id"] == "UNIQUE (organizacion_id, id)"
    with _engine_de_sesion.connect() as conexion:
        definicion = conexion.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'ix_venta_anulacion__occurred_at'"
            )
        ).scalar_one()
    assert "(organizacion_id, occurred_at DESC, id DESC)" in definicion


def test_una_venta_no_se_puede_anular_dos_veces_en_la_base(db_session: Session) -> None:
    """VTA-20, D11: el segundo `INSERT` de la misma venta viola `ux_venta_anulacion__venta`."""
    organizacion_id = crear_organizacion(db_session).id
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(db_session, organizacion_id)
    cliente_id = crear_cliente(db_session, organizacion_id)
    venta = sembrar_venta_sql(
        db_session,
        organizacion_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
    )
    motivo_id = crear_motivo_sql(db_session, organizacion_id, ambito=AMBITO)

    def fila() -> dict[str, object]:
        return {
            "id": uuid4(),
            "organizacion_id": organizacion_id,
            "venta_id": venta.venta_id,
            "motivo_id": motivo_id,
            "operation_id": uuid4(),
            "usuario_id": usuario_id,
            "dispositivo_id": dispositivo_id,
            "occurred_at": MOMENTO,
            "registered_at": MOMENTO,
        }

    insertar_sql(db_session, "venta_anulacion", fila())
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        insertar_sql(db_session, "venta_anulacion", fila())
    assert "ux_venta_anulacion__venta" in str(error.value)


# --- privilegios (INV-05) ----------------------------------------------------------


def test_inv05_app_runtime_solo_lee_e_inserta_venta_anulacion(app_runtime_engine: Engine) -> None:
    assert _privilegios(app_runtime_engine, "venta_anulacion") == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, "venta_anulacion") == set()


def test_inv05_app_runtime_solo_actualiza_el_estado_de_la_venta(app_runtime_engine: Engine) -> None:
    """D11: `GRANT UPDATE (estado) ON venta`, nada más."""
    assert _columnas_con_update(app_runtime_engine, "venta") == {"estado"}
    assert "DELETE" not in _privilegios(app_runtime_engine, "venta")


@pytest.mark.parametrize("tabla", ["venta_anulacion", "venta"])
def test_inv05_app_runtime_no_puede_borrar(app_runtime_engine: Engine, tabla: str) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))
    assert "permission denied" in str(error.value)


# --- siembra de motivos (VTA-20, D12) -----------------------------------------------


def test_la_migracion_siembra_los_motivos_una_sola_vez_y_respeta_las_organizaciones_con_propios(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D12: sobre organizaciones creadas antes de la migración, la que no tiene motivos del
    ámbito recibe los tres; la que tiene propios no se toca; subir de nuevo no duplica."""
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        with Session(_engine_de_sesion) as sesion:
            vacia = crear_organizacion(sesion).id
            con_propios = crear_organizacion(sesion).id
            crear_motivo_sql(sesion, con_propios, ambito=AMBITO, nombre="Motivo propio")
            sesion.commit()

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _motivos(_engine_de_sesion, vacia) == MOTIVOS_SEMBRADOS
        assert _motivos(_engine_de_sesion, con_propios) == ["Motivo propio"]

        # baja y sube de nuevo (la baja quita los motivos del ámbito que nada referencia):
        # la organización sembrada vuelve a tener exactamente tres, sin duplicados.
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _motivos(_engine_de_sesion, vacia) == []
        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _motivos(_engine_de_sesion, vacia) == MOTIVOS_SEMBRADOS
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- baja y sube (`04` §2.1 punto 4) -------------------------------------------------


def test_baja_y_sube_limpia_sobre_una_base_con_ventas_confirmadas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4: con ventas `CONFIRMADA` el `downgrade` corre, quita la tabla y el
    `UPDATE`, y el `upgrade` la deja de nuevo; la venta no se toca."""
    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion_id)
        venta = sembrar_venta_sql(
            sesion,
            organizacion_id,
            cliente_id=crear_cliente(sesion, organizacion_id),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(
                text("SELECT to_regclass('public.venta_anulacion') IS NULL")
            ).scalar_one()
            assert (
                conexion.execute(
                    text("SELECT estado FROM venta WHERE id = :i"), {"i": venta.venta_id}
                ).scalar_one()
                == "CONFIRMADA"
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM venta_anulacion")).scalar_one() == 0
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_con_mensaje_claro_si_hay_una_venta_anulada(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D11: borrar la tabla dejaría una venta `ANULADA` sin su anulación; aborta y no toca
    nada. Sin ventas anuladas, baja."""
    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion_id)
        venta = sembrar_venta_sql(
            sesion,
            organizacion_id,
            cliente_id=crear_cliente(sesion, organizacion_id),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            estado="ANULADA",
        )
        motivo_id = crear_motivo_sql(sesion, organizacion_id, ambito=AMBITO)
        insertar_sql(
            sesion,
            "venta_anulacion",
            {
                "id": uuid4(),
                "organizacion_id": organizacion_id,
                "venta_id": venta.venta_id,
                "motivo_id": motivo_id,
                "operation_id": uuid4(),
                "usuario_id": usuario_id,
                "dispositivo_id": dispositivo_id,
                "occurred_at": MOMENTO,
                "registered_at": MOMENTO,
            },
        )
        sesion.commit()

    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "ANULADA" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM venta_anulacion")).scalar_one() == 1

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
