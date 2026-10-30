"""Tareas 7.1 y 7.2 (change 20b; `design.md` D10, D13; `04` §2.1 punto 4): la revisión de Alembic
sobre `e0f1a2b3c4d5` crea `ux_rol__nombre` (único por organización sin distinguir mayúsculas) y
agrega `cliente.vendedor_id` (uuid nulo, FK compuesta a `usuario` con `organizacion_id` e índice
`ix_cliente__vendedor`). Aborta nombrando la organización y el nombre si hay roles repetidos.

Consulta el esquema REAL de PostgreSQL ya migrado. Reglas citadas: INV-02, INV-21.
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
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

REVISION_ANTERIOR = "e0f1a2b3c4d5"  # `nota_venta_configuracion` (change 20)
MOMENTO = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
INDICE_ROL = "ux_rol__nombre"
INDICE_CLIENTE = "ix_cliente__vendedor"
FK_CLIENTE = "fk_cliente__vendedor"


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


def _insertar_rol(
    sesion: Session, organizacion_id: UUID, nombre: str, *, activo: bool = True
) -> UUID:
    rol_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO rol (id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :n, 0, :a, :m, :m)"
        ),
        {"id": rol_id, "o": organizacion_id, "n": nombre, "a": activo, "m": MOMENTO},
    )
    return rol_id


def _definicion(motor: Engine, indice: str) -> str | None:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": indice},
        ).scalar_one_or_none()


def _columna_vendedor(motor: Engine) -> tuple[str, str] | None:
    with motor.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'cliente' AND column_name = 'vendedor_id'"
            )
        ).one_or_none()
    return None if fila is None else (fila[0], fila[1])


def _vendedor_de(motor: Engine, cliente_id: UUID) -> UUID | None:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT vendedor_id FROM cliente WHERE id = :c"), {"c": cliente_id}
        ).scalar_one()


# --- ux_rol__nombre (D10, INV-02) --------------------------------------------------------


def test_el_indice_de_rol_es_unico_sobre_organizacion_y_nombre_en_minusculas(
    _engine_de_sesion: Engine,
) -> None:
    definicion = _definicion(_engine_de_sesion, INDICE_ROL)

    assert definicion is not None
    assert "CREATE UNIQUE INDEX" in definicion
    assert "(organizacion_id, lower(nombre))" in definicion


def test_inv02_dos_roles_que_solo_difieren_en_mayusculas_se_rechazan_en_la_misma_organizacion(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_rol(db_session, organizacion.id, "Repartidor")

    for repetido in ("repartidor", "REPARTIDOR"):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar_rol(db_session, organizacion.id, repetido)
        assert INDICE_ROL in str(error.value)


def test_el_nombre_repetido_se_rechaza_aunque_el_rol_existente_este_de_baja(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_rol(db_session, organizacion.id, "Chofer", activo=False)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_rol(db_session, organizacion.id, "chofer")
    assert INDICE_ROL in str(error.value)


def test_el_mismo_nombre_de_rol_se_acepta_en_organizaciones_distintas(db_session: Session) -> None:
    una = crear_organizacion(db_session)
    otra = crear_organizacion(db_session)

    _insertar_rol(db_session, una.id, "Vendedor")
    _insertar_rol(db_session, otra.id, "vendedor")


def test_la_migracion_aborta_nombrando_la_organizacion_y_el_nombre_sin_cambiar_nada(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with Session(_engine_de_sesion) as sesion:
            conflictiva = crear_organizacion(sesion).id
            _insertar_rol(sesion, conflictiva, "Repartidor")
            _insertar_rol(sesion, conflictiva, "repartidor")
            sesion.commit()

        abortada = _alembic(database_url, "upgrade", "head")

        assert abortada.returncode != 0
        assert str(conflictiva) in abortada.stderr
        assert "repartidor" in abortada.stderr.lower()
        # No cambió nada: ni índice ni columna.
        assert _definicion(_engine_de_sesion, INDICE_ROL) is None
        assert _columna_vendedor(_engine_de_sesion) is None
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_dos_organizaciones_con_el_mismo_nombre_de_rol_no_abortan_la_migracion(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        with Session(_engine_de_sesion) as sesion:
            for _ in range(2):
                _insertar_rol(sesion, crear_organizacion(sesion).id, "Vendedor")
            sesion.commit()

        subida = _alembic(database_url, "upgrade", "head")

        assert subida.returncode == 0, subida.stderr
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- cliente.vendedor_id (D13, INV-21) ---------------------------------------------------


def test_cliente_tiene_vendedor_id_uuid_nulable_con_indice_y_clave_foranea_compuesta(
    _engine_de_sesion: Engine,
) -> None:
    assert _columna_vendedor(_engine_de_sesion) == ("uuid", "YES")
    assert _definicion(_engine_de_sesion, INDICE_CLIENTE) is not None
    with _engine_de_sesion.connect() as conexion:
        definicion_fk = conexion.execute(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
            {"n": FK_CLIENTE},
        ).scalar_one()
    assert "FOREIGN KEY (organizacion_id, vendedor_id)" in definicion_fk
    assert "REFERENCES usuario(organizacion_id, id)" in definicion_fk


def test_inv21_un_vendedor_de_otra_organizacion_se_rechaza_por_la_clave_foranea(
    db_session: Session,
) -> None:
    propia = crear_organizacion(db_session)
    ajena = crear_organizacion(db_session)
    cliente_id = crear_cliente(db_session, propia.id)
    usuario_ajeno, _ = crear_usuario_y_dispositivo(db_session, ajena.id)
    usuario_propio, _ = crear_usuario_y_dispositivo(db_session, propia.id)
    db_session.flush()

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text("UPDATE cliente SET vendedor_id = :u WHERE id = :c"),
            {"u": usuario_ajeno, "c": cliente_id},
        )
    assert FK_CLIENTE in str(error.value)

    db_session.execute(
        text("UPDATE cliente SET vendedor_id = :u WHERE id = :c"),
        {"u": usuario_propio, "c": cliente_id},
    )


def test_el_ciclo_baja_y_sube_limpio_y_conserva_clientes_y_roles(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4: sube, baja y vuelve a subir sobre una base con datos (el ciclo con
    ventas lo cubre `test_alembic_integracion.py`). El `downgrade` quita índice, clave foránea y
    columna; los clientes y los roles siguen."""
    with Session(_engine_de_sesion) as sesion:
        organizacion = crear_organizacion(sesion).id
        usuario, _ = crear_usuario_y_dispositivo(sesion, organizacion)
        cliente = crear_cliente(sesion, organizacion)
        sesion.execute(
            text("UPDATE cliente SET vendedor_id = :u WHERE id = :c"),
            {"u": usuario, "c": cliente},
        )
        sesion.commit()
    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _columna_vendedor(_engine_de_sesion) is None
        assert _definicion(_engine_de_sesion, INDICE_ROL) is None
        assert _definicion(_engine_de_sesion, INDICE_CLIENTE) is None
        with _engine_de_sesion.connect() as conexion:
            quedan = conexion.execute(
                text("SELECT count(*) FROM cliente WHERE id = :c"), {"c": cliente}
            ).scalar_one()
        assert quedan == 1

        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert _columna_vendedor(_engine_de_sesion) == ("uuid", "YES")
        assert _vendedor_de(_engine_de_sesion, cliente) is None
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
