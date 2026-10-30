"""Tareas 1.1 a 1.3 (change 20c; `design.md` D3, D7, D10): la revisión de Alembic sobre
`f1a2b3c4d5e6` crea `ux_motivo__nombre`, `ux_alicuota_iva__nombre`, `ux_alicuota_iva__valor`,
`ck_alicuota_iva__valor` y los dos `CHECK` del redondeo por defecto; aborta con un mensaje que
nombra la organización y el dato si ya hay datos repetidos o incoherentes; el ciclo
`upgrade -> downgrade -> upgrade` con datos usados no duplica ni borra filas.

Consulta el esquema REAL de PostgreSQL ya migrado. Reglas citadas: INV-02, INV-03, INV-05,
TR-06, TR-09, CAT-05, PRC-01.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
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

REVISION_ANTERIOR = "f1a2b3c4d5e6"  # `usuarios_roles_y_cartera`, la previa a este change.
MOMENTO = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _insertar_motivo(
    sesion: Session, organizacion_id: UUID, ambito: str, nombre: str, *, activo: bool = True
) -> UUID:
    motivo_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :a, :n, :act, :m, :m)"
        ),
        {
            "id": motivo_id,
            "o": organizacion_id,
            "a": ambito,
            "n": nombre,
            "act": activo,
            "m": MOMENTO,
        },
    )
    return motivo_id


def _insertar_alicuota(
    sesion: Session, organizacion_id: UUID, nombre: str, valor: str, *, activo: bool = True
) -> UUID:
    alicuota_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :n, :v, :act, :m, :m)"
        ),
        {
            "id": alicuota_id,
            "o": organizacion_id,
            "n": nombre,
            "v": Decimal(valor),
            "act": activo,
            "m": MOMENTO,
        },
    )
    return alicuota_id


def _definir_redondeo(
    sesion: Session, organizacion_id: UUID, multiplo: str | None, direccion: str | None
) -> None:
    sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET redondeo_multiplo = :m, "
            "redondeo_direccion = :d WHERE organizacion_id = :o"
        ),
        {
            "m": None if multiplo is None else Decimal(multiplo),
            "d": direccion,
            "o": organizacion_id,
        },
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


def _dejar_en_head(database_url: str, motor: Engine) -> None:
    """La base es compartida con el resto de la sesión: toda prueba que mueve Alembic DEBE
    terminar en `head` y sin filas propias."""
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr


def _existe(motor: Engine, consulta: str, nombre: str) -> bool:
    with motor.connect() as conexion:
        return conexion.execute(text(consulta), {"n": nombre}).scalar_one_or_none() is not None


def _indice(motor: Engine, nombre: str) -> bool:
    return _existe(motor, "SELECT 1 FROM pg_indexes WHERE indexname = :n", nombre)


def _restriccion(motor: Engine, nombre: str) -> bool:
    return _existe(motor, "SELECT 1 FROM pg_constraint WHERE conname = :n", nombre)


# --- motivos: nombre único por organización y ámbito (D3, INV-02) ----------------------


def test_inv02_el_mismo_nombre_se_acepta_en_dos_ambitos_y_se_rechaza_en_el_mismo(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_motivo(db_session, organizacion.id, "AJUSTE_STOCK", "Otro")
    _insertar_motivo(db_session, organizacion.id, "ANULACION_VENTA", "Otro")

    for repetido in ("otro", "OTRO"):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar_motivo(db_session, organizacion.id, "AJUSTE_STOCK", repetido)
        assert "ux_motivo__nombre" in str(error.value)


def test_inv02_rotura_junto_a_rotura_se_rechaza_aunque_el_existente_este_de_baja(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_motivo(db_session, organizacion.id, "AJUSTE_STOCK", "Rotura", activo=False)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_motivo(db_session, organizacion.id, "AJUSTE_STOCK", "rotura")
    assert "ux_motivo__nombre" in str(error.value)


def test_inv02_el_mismo_motivo_se_acepta_en_otra_organizacion(db_session: Session) -> None:
    una = crear_organizacion(db_session)
    otra = crear_organizacion(db_session)

    _insertar_motivo(db_session, una.id, "AJUSTE_STOCK", "Robo")
    _insertar_motivo(db_session, otra.id, "AJUSTE_STOCK", "robo")


# --- alícuotas: nombre y valor únicos, valor en [0, 1) (D7, INV-02, INV-03) -----------------


def test_inv02_la_alicuota_repetida_por_nombre_o_por_valor_se_rechaza(
    db_session: Session,
) -> None:
    organizacion = crear_organizacion(db_session)
    _insertar_alicuota(db_session, organizacion.id, "General", "0.210000", activo=False)

    with pytest.raises(IntegrityError) as por_nombre, db_session.begin_nested():
        _insertar_alicuota(db_session, organizacion.id, "GENERAL", "0.220000")
    assert "ux_alicuota_iva__nombre" in str(por_nombre.value)

    with pytest.raises(IntegrityError) as por_valor, db_session.begin_nested():
        _insertar_alicuota(db_session, organizacion.id, "IVA general", "0.210000")
    assert "ux_alicuota_iva__valor" in str(por_valor.value)


def test_inv02_la_alicuota_se_repite_entre_organizaciones(db_session: Session) -> None:
    una = crear_organizacion(db_session)
    otra = crear_organizacion(db_session)

    _insertar_alicuota(db_session, una.id, "21%", "0.210000")
    _insertar_alicuota(db_session, otra.id, "21%", "0.210000")


@pytest.mark.parametrize("valor", ["1.000000", "-0.010000", "1.500000"])
def test_inv03_el_valor_fuera_de_cero_a_uno_se_rechaza(db_session: Session, valor: str) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_alicuota(db_session, organizacion.id, "Mala", valor)
    assert "ck_alicuota_iva__valor" in str(error.value)


@pytest.mark.parametrize("valor", ["0.000000", "0.999999", "0.105000"])
def test_inv03_el_valor_dentro_de_cero_a_uno_se_acepta(db_session: Session, valor: str) -> None:
    organizacion = crear_organizacion(db_session)

    _insertar_alicuota(db_session, organizacion.id, "Buena", valor)


# --- redondeo por defecto: los dos o ninguno, múltiplo positivo (D10, PRC-01) --------------


@pytest.mark.parametrize(("multiplo", "direccion"), [("100.00", None), (None, "ARRIBA")])
def test_prc01_el_redondeo_a_medias_se_rechaza(
    db_session: Session, multiplo: str | None, direccion: str | None
) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _definir_redondeo(db_session, organizacion.id, multiplo, direccion)
    assert "ck_configuracion_organizacion__redondeo_coherente" in str(error.value)


@pytest.mark.parametrize("multiplo", ["0.00", "-5.00"])
def test_prc01_el_multiplo_no_positivo_se_rechaza(db_session: Session, multiplo: str) -> None:
    organizacion = crear_organizacion(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _definir_redondeo(db_session, organizacion.id, multiplo, "ARRIBA")
    assert "ck_configuracion_organizacion__redondeo_multiplo_positivo" in str(error.value)


def test_prc01_el_redondeo_completo_o_vacio_se_acepta(db_session: Session) -> None:
    organizacion = crear_organizacion(db_session)

    _definir_redondeo(db_session, organizacion.id, "500.00", "ABAJO")
    _definir_redondeo(db_session, organizacion.id, None, None)


# --- datos previos incompatibles: la migración aborta sin cambiar nada (D3, D7, D10) ----------


def _abortar_con(
    database_url: str,
    motor: Engine,
    preparar: Callable[[Session, UUID], None],
    esperado: list[str],
) -> None:
    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        with Session(motor) as sesion:
            organizacion_id = crear_organizacion(sesion).id
            preparar(sesion, organizacion_id)
            sesion.commit()

        abortada = _alembic(database_url, "upgrade", "head")

        assert abortada.returncode != 0
        assert str(organizacion_id) in abortada.stderr
        for fragmento in esperado:
            assert fragmento.lower() in abortada.stderr.lower()
        # No cambió nada: ni índices ni restricciones nuevas.
        assert not _indice(motor, "ux_motivo__nombre")
        assert not _indice(motor, "ux_alicuota_iva__nombre")
        assert not _indice(motor, "ux_alicuota_iva__valor")
        assert not _restriccion(motor, "ck_alicuota_iva__valor")
    finally:
        _dejar_en_head(database_url, motor)


def test_la_migracion_aborta_con_dos_motivos_repetidos_en_un_ambito(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    def preparar(sesion: Session, org: UUID) -> None:
        _insertar_motivo(sesion, org, "AJUSTE_STOCK", "Rotura")
        _insertar_motivo(sesion, org, "AJUSTE_STOCK", "rotura")
        _insertar_motivo(sesion, org, "ANULACION_VENTA", "Rotura")  # otro ámbito: no conflictúa

    _abortar_con(database_url, _engine_de_sesion, preparar, ["AJUSTE_STOCK", "rotura"])


def test_la_migracion_aborta_con_dos_alicuotas_del_mismo_valor(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    def preparar(sesion: Session, org: UUID) -> None:
        _insertar_alicuota(sesion, org, "21%", "0.210000")
        _insertar_alicuota(sesion, org, "IVA general", "0.210000")

    _abortar_con(database_url, _engine_de_sesion, preparar, ["0.210000"])


def test_la_migracion_aborta_con_dos_alicuotas_del_mismo_nombre(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    def preparar(sesion: Session, org: UUID) -> None:
        _insertar_alicuota(sesion, org, "Reducida", "0.105000")
        _insertar_alicuota(sesion, org, "reducida", "0.270000")

    _abortar_con(database_url, _engine_de_sesion, preparar, ["reducida"])


def test_la_migracion_aborta_con_una_alicuota_fuera_de_rango(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    def preparar(sesion: Session, org: UUID) -> None:
        _insertar_alicuota(sesion, org, "Rara", "1.500000")

    _abortar_con(database_url, _engine_de_sesion, preparar, ["Rara", "1.500000"])


def test_la_migracion_aborta_con_un_redondeo_a_medias(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    def preparar(sesion: Session, org: UUID) -> None:
        # Tras el downgrade el CHECK nuevo no existe: el dato a medias se puede cargar.
        _definir_redondeo(sesion, org, "100.00", None)

    _abortar_con(database_url, _engine_de_sesion, preparar, ["multiplo=100.00"])


# --- ciclo upgrade -> downgrade -> upgrade con datos (04 §2.1 punto 4) ---------------------


def test_el_ciclo_sube_y_baja_limpio_con_motivo_y_alicuota_en_uso(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Un motivo propio y una alícuota usada por un producto: el ciclo corre sin errores y no
    duplica ni borra filas. TR-06."""
    from stock_utiles import crear_producto_sql

    with Session(_engine_de_sesion) as sesion:
        organizacion = crear_organizacion(sesion).id
        producto = crear_producto_sql(sesion, organizacion)
        motivo = _insertar_motivo(sesion, organizacion, "AJUSTE_STOCK", "Rotura de prueba")
        sesion.commit()

    def contar(tabla: str) -> int:
        with _engine_de_sesion.connect() as conexion:
            return int(
                conexion.execute(
                    text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),  # noqa: S608
                    {"o": organizacion},
                ).scalar_one()
            )

    antes = {t: contar(t) for t in ("motivo", "alicuota_iva", "producto")}
    try:
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert not _indice(_engine_de_sesion, "ux_motivo__nombre")
        assert not _restriccion(_engine_de_sesion, "ck_alicuota_iva__valor")
        assert {t: contar(t) for t in antes} == antes

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _indice(_engine_de_sesion, "ux_motivo__nombre")
        assert _indice(_engine_de_sesion, "ux_alicuota_iva__nombre")
        assert _indice(_engine_de_sesion, "ux_alicuota_iva__valor")
        assert _restriccion(_engine_de_sesion, "ck_alicuota_iva__valor")
        assert _restriccion(_engine_de_sesion, "ck_configuracion_organizacion__redondeo_coherente")
        assert _restriccion(
            _engine_de_sesion, "ck_configuracion_organizacion__redondeo_multiplo_positivo"
        )
        assert {t: contar(t) for t in antes} == antes
        with _engine_de_sesion.connect() as conexion:
            for tabla, fila in (("motivo", motivo), ("producto", producto)):
                assert (
                    conexion.execute(
                        text(f"SELECT count(*) FROM {tabla} WHERE id = :i"),  # noqa: S608
                        {"i": fila},
                    ).scalar_one()
                    == 1
                )
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- privilegios (INV-05, TR-06) ----------------------------------------------------------


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


@pytest.mark.parametrize("tabla", ["motivo", "alicuota_iva"])
def test_inv05_app_runtime_sigue_sin_delete_sobre_motivo_y_alicuota(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """TR-06, CAT-05: un motivo o una alícuota se da de baja, nunca se borra."""
    privilegios = _privilegios(app_runtime_engine, tabla)

    assert "DELETE" not in privilegios
    assert {"SELECT", "INSERT", "UPDATE"} <= privilegios
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))  # noqa: S608
    assert "permission denied" in str(error.value)
