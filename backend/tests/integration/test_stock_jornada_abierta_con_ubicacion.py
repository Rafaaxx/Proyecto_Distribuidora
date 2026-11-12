"""Tarea 7.6 (change 18a; `design.md` D3, D17): `stock.service.jornada_abierta_con_ubicacion_de`,
la lectura SIN bloqueo de la jornada `ABIERTA` del usuario y el dispositivo y de su ubicación.

La venta necesita saber la ubicación de la jornada ANTES de pedir los bloqueos del stock (la
jornada `FOR SHARE` es el nivel 5 del orden global y no se toma antes que los demás); el bloqueo
lo toman después los movimientos de stock. Solo lectura.

Reglas citadas: RUT-04, STK-09, INV-21.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cobranzas_utiles import Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.stock import service as stock_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _leer(entorno: Entorno) -> stock_service.JornadaAbierta | None:
    return stock_service.jornada_abierta_con_ubicacion_de(
        entorno.org,
        entorno.sesion,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )


def test_rut04_devuelve_la_jornada_abierta_y_su_ubicacion(entorno: Entorno) -> None:
    jornada_id = entorno.crear_jornada()

    encontrada = _leer(entorno)

    assert encontrada is not None
    assert encontrada.jornada_id == jornada_id
    assert (
        encontrada.ubicacion_id
        == entorno.sesion.execute(
            text("SELECT ubicacion_id FROM jornada WHERE id = :j"), {"j": jornada_id}
        ).scalar_one()
    )


def test_rut04_sin_jornada_abierta_devuelve_none(entorno: Entorno) -> None:
    assert _leer(entorno) is None


@pytest.mark.parametrize("estado", ["EN_RENDICION", "CERRADA", "LIBERADA"])
def test_rut04_una_jornada_que_no_esta_abierta_no_cuenta(entorno: Entorno, estado: str) -> None:
    entorno.crear_jornada(estado=estado)

    assert _leer(entorno) is None


def test_inv21_la_jornada_de_otro_usuario_o_dispositivo_no_cuenta(entorno: Entorno) -> None:
    entorno.crear_otro_usuario_con_jornada()

    assert _leer(entorno) is None
    assert (
        stock_service.jornada_abierta_con_ubicacion_de(
            entorno.org, entorno.sesion, usuario_id=uuid4(), dispositivo_id=uuid4()
        )
        is None
    )
