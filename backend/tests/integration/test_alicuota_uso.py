"""Tarea 4.3 (change 20c; `design.md` D8, D9): el puerto con el que `configuracion` sabe cuántos
productos activos usan una alícuota sin importar `catalogo`. Citan CAT-01, CAT-05 e INV-21.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql

from app.modules.configuracion import repository as configuracion_repository
from app.modules.configuracion import service as configuracion_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _alicuota(
    db_session: Session, organizacion_id: uuid.UUID, nombre: str, valor: str
) -> uuid.UUID:
    return configuracion_repository.crear_alicuota(
        organizacion_id, db_session, nombre=nombre, valor=Decimal(valor), momento=_MOMENTO
    ).id


def _producto(
    db_session: Session, organizacion_id: uuid.UUID, alicuota_id: uuid.UUID, *, activo: bool = True
) -> None:
    producto_id = crear_producto_sql(db_session, organizacion_id)
    db_session.execute(
        text("UPDATE producto SET alicuota_id = :a, activo = :act WHERE id = :p"),
        {"a": alicuota_id, "act": activo, "p": producto_id},
    )


def test_sin_verificadores_registrados_el_puerto_cuenta_cero(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = crear_organizacion(db_session).id
    alicuota = _alicuota(db_session, org, "21%", "0.21")
    monkeypatch.setattr(configuracion_service, "_VERIFICADORES_USO_ALICUOTA", {})

    assert (
        configuracion_service.contar_productos_activos_con_alicuota(org, alicuota, db_session) == 0
    )


def test_los_verificadores_registrados_se_suman(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = crear_organizacion(db_session).id
    alicuota = _alicuota(db_session, org, "21%", "0.21")
    monkeypatch.setattr(configuracion_service, "_VERIFICADORES_USO_ALICUOTA", {})

    configuracion_service.registrar_verificador_uso_alicuota("uno", lambda o, a, s: 2)
    configuracion_service.registrar_verificador_uso_alicuota("dos", lambda o, a, s: 3)

    assert (
        configuracion_service.contar_productos_activos_con_alicuota(org, alicuota, db_session) == 5
    )


def test_cat01_catalogo_se_registra_solo_y_cuenta_productos_activos_de_la_alicuota(
    db_session: Session,
) -> None:
    # El registro ocurre al importar `catalogo/service.py` (precedente ADR-023).
    import app.modules.catalogo.service  # noqa: F401

    org = crear_organizacion(db_session).id
    general = _alicuota(db_session, org, "21%", "0.21")
    reducida = _alicuota(db_session, org, "10,5%", "0.105")
    _producto(db_session, org, general)
    _producto(db_session, org, general)
    _producto(db_session, org, reducida)

    assert (
        configuracion_service.contar_productos_activos_con_alicuota(org, general, db_session) == 2
    )
    assert (
        configuracion_service.contar_productos_activos_con_alicuota(org, reducida, db_session) == 1
    )


def test_cat05_los_productos_inactivos_no_cuentan(db_session: Session) -> None:
    import app.modules.catalogo.service  # noqa: F401

    org = crear_organizacion(db_session).id
    cero = _alicuota(db_session, org, "0%", "0")
    _producto(db_session, org, cero, activo=False)
    _producto(db_session, org, cero, activo=False)
    _producto(db_session, org, cero, activo=True)

    assert configuracion_service.contar_productos_activos_con_alicuota(org, cero, db_session) == 1


def test_inv21_los_productos_de_otra_organizacion_no_cuentan(db_session: Session) -> None:
    import app.modules.catalogo.service  # noqa: F401

    una = crear_organizacion(db_session).id
    otra = crear_organizacion(db_session).id
    de_una = _alicuota(db_session, una, "21%", "0.21")
    de_otra = _alicuota(db_session, otra, "21%", "0.21")
    _producto(db_session, otra, de_otra)

    assert configuracion_service.contar_productos_activos_con_alicuota(una, de_una, db_session) == 0
    # Ni siquiera preguntando por la alícuota de la otra con el id de organización propio.
    assert (
        configuracion_service.contar_productos_activos_con_alicuota(una, de_otra, db_session) == 0
    )
    assert (
        configuracion_service.contar_productos_activos_con_alicuota(otra, de_otra, db_session) == 1
    )
