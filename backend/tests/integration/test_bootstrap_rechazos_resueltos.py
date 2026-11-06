"""Tarea 11.1 (change 25; spec `sync/bootstrap`, requisito "El bootstrap informa los rechazos
resueltos"; `design.md` D8): `GET /api/v1/sync/bootstrap` con PostgreSQL real.

`rechazos_resueltos` trae los `operation_id` de los rechazos RESUELTOS de la jornada del bootstrap,
del usuario y del dispositivo de la sesión, en la misma foto; vacío si no hay; nunca el comentario
ni el vínculo. No mira rechazos pendientes, de otra jornada, de otro usuario ni de otra
organización.

Reglas citadas: SYN-11, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from revision_utiles import sembrar_rechazo
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import MOMENTO, crear_jornada_sql
from test_bootstrap_secuencia_procesada import Telefono
from test_sync_bootstrap import Escenario, cliente_http, sesion  # noqa: F401
from test_ventas_offline import Ruta

from app.modules.sync import revision_repository

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def telefono(cliente_http: TestClient, sesion: Session) -> Telefono:
    return Telefono(cliente_http, sesion)


def _rechazo(
    telefono: Telefono,
    *,
    jornada_id: UUID | None = None,
    usuario_id: UUID | None = None,
    dispositivo_id: UUID | None = None,
    resuelto: bool = True,
    vinculo: bool = False,
) -> UUID:
    entorno = telefono.entorno
    operacion = uuid4()
    rechazo_id = sembrar_rechazo(
        entorno.sesion,
        entorno.org,
        usuario_id=usuario_id or entorno.usuario_id,
        dispositivo_id=dispositivo_id or entorno.dispositivo_id,
        jornada_id=jornada_id or telefono.ruta.jornada_id,
        operation_id=operacion,
    )
    if resuelto:
        revision_repository.marcar_rechazo_resuelto(
            entorno.org,
            entorno.sesion,
            rechazo_id,
            usuario_id=entorno.usuario_id,
            momento=MOMENTO,
            comentario="Cargada a mano",
            vinculo_tipo="VENTA" if vinculo else None,
            vinculo_id=uuid4() if vinculo else None,
        )
    entorno.sesion.commit()
    return operacion


def _resueltos(telefono: Telefono) -> list[str]:
    cuerpo = telefono.escenario.pedir(telefono.cliente_http, telefono.headers)
    valor = cuerpo["rechazos_resueltos"]
    assert isinstance(valor, list)
    return valor


def test_syn11_trae_el_operation_id_de_la_venta_rechazada_resuelta(telefono: Telefono) -> None:
    operacion = _rechazo(telefono)

    assert _resueltos(telefono) == [str(operacion)]


def test_syn11_sin_rechazos_la_lista_es_vacia(telefono: Telefono) -> None:
    assert _resueltos(telefono) == []


def test_syn11_trae_varios_ordenados_y_sin_comentario_ni_vinculo(telefono: Telefono) -> None:
    uno = _rechazo(telefono, vinculo=True)
    dos = _rechazo(telefono)

    cuerpo = telefono.escenario.pedir(telefono.cliente_http, telefono.headers)

    assert cuerpo["rechazos_resueltos"] == sorted([str(uno), str(dos)])
    assert "Cargada a mano" not in str(cuerpo["rechazos_resueltos"])


def test_syn11_el_doble_pedido_devuelve_la_misma_lista(telefono: Telefono) -> None:
    _rechazo(telefono)
    _rechazo(telefono)

    assert _resueltos(telefono) == _resueltos(telefono)


def test_syn11_un_rechazo_pendiente_no_va(telefono: Telefono) -> None:
    _rechazo(telefono, resuelto=False)

    assert _resueltos(telefono) == []


def test_inv21_no_mira_otra_jornada_otro_usuario_ni_otra_organizacion(
    telefono: Telefono, sesion: Session
) -> None:
    entorno = telefono.entorno
    anterior = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=telefono.ruta.camioneta_id,
        estado="CERRADA",
    )
    ajena = entorno.crear_otro_usuario_con_jornada()
    otro_usuario, otro_dispositivo = entorno.sesion.execute(
        text("SELECT usuario_id, dispositivo_id FROM jornada WHERE id = :j"), {"j": ajena}
    ).one()
    entorno.sesion.commit()
    _rechazo(telefono, jornada_id=anterior)
    _rechazo(telefono, jornada_id=ajena, usuario_id=otro_usuario, dispositivo_id=otro_dispositivo)
    otra = Escenario(sesion)
    otra_ruta = Ruta(otra.entorno)
    sembrar_rechazo(
        otra.entorno.sesion,
        otra.entorno.org,
        usuario_id=otra.entorno.usuario_id,
        dispositivo_id=otra.entorno.dispositivo_id,
        jornada_id=otra_ruta.jornada_id,
    )
    otra.entorno.sesion.commit()

    assert _resueltos(telefono) == []
