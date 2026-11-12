"""Change 15, tarea 10.2: el listado de ubicaciones y el stock por ubicación indican cuáles están
tomadas y por quién (`design.md` D15: "el listado de ubicaciones (`TRANSFERIR_STOCK`) indica
cuáles están tomadas y por quién"; spec `stock/administracion-de-stock`). No agrega ningún
permiso: las dos lecturas conservan los que ya tenían.

Mismo arnés HTTP que `test_jornadas_api.py`.

Reglas citadas: RUT-01, STK-09, INV-16, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from test_jornadas_api import _jornada_en, _preparar
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

LECTOR = frozenset({"TRANSFERIR_STOCK"})


def _por_id(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in items}


def test_el_listado_indica_la_jornada_el_usuario_y_el_momento_de_cada_ubicacion_tomada(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario del listado: la tomada trae su jornada, quién la tiene y desde cuándo; las
    demás, `null`. Una jornada `EN_RENDICION` sigue tomando la ubicación (INV-16)."""
    entorno = _preparar(sesion, permisos=LECTOR)
    jornada_1 = _jornada_en(entorno, "ABIERTA", entorno.camioneta_1)
    pedro, telefono = crear_usuario_y_dispositivo(
        sesion, entorno.org, permisos=frozenset({"ABRIR_JORNADA"})
    )
    jornada_2 = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=pedro,
        dispositivo_id=telefono,
        ubicacion_id=entorno.camioneta_2,
        estado="EN_RENDICION",
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get("/api/v1/stock/ubicaciones", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    ubicaciones = _por_id(respuesta.json()["items"])
    tomada_1 = ubicaciones[str(entorno.camioneta_1)]["jornada"]
    assert isinstance(tomada_1, dict)
    assert tomada_1["id"] == str(jornada_1)
    assert tomada_1["usuario_id"] == str(entorno.usuario_id)
    assert tomada_1["usuario_nombre"] == "Persona de prueba"
    assert tomada_1["estado"] == "ABIERTA"
    assert tomada_1["abierta_en"]
    tomada_2 = ubicaciones[str(entorno.camioneta_2)]["jornada"]
    assert isinstance(tomada_2, dict)
    assert (tomada_2["id"], tomada_2["estado"]) == (str(jornada_2), "EN_RENDICION")
    assert ubicaciones[str(entorno.camioneta_inactiva)]["jornada"] is None
    assert ubicaciones[str(entorno.deposito_id)]["jornada"] is None


@pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
def test_una_jornada_terminada_no_marca_la_ubicacion(
    cliente: TestClient, sesion: Session, estado: str
) -> None:
    entorno = _preparar(sesion, permisos=LECTOR)
    _jornada_en(entorno, estado, entorno.camioneta_1)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get("/api/v1/stock/ubicaciones", headers=headers)

    ubicaciones = _por_id(respuesta.json()["items"])
    assert ubicaciones[str(entorno.camioneta_1)]["jornada"] is None


def test_inv21_la_jornada_de_otra_organizacion_no_aparece(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LECTOR)
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(
        sesion, otra_org, permisos=frozenset({"ABRIR_JORNADA"})
    )
    ajena = crear_ubicacion_sql(
        sesion, otra_org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    crear_jornada_sql(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=ajena,
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get("/api/v1/stock/ubicaciones", headers=headers)

    ubicaciones = _por_id(respuesta.json()["items"])
    assert str(ajena) not in ubicaciones
    assert ubicaciones[str(entorno.camioneta_1)]["jornada"] is None


def test_el_stock_por_ubicacion_indica_la_jornada_de_la_ubicacion_tomada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LECTOR)
    jornada_id = _jornada_en(entorno, "ABIERTA", entorno.camioneta_1)
    headers = entorno.confirmar_y_entrar(cliente)

    tomada = cliente.get(f"/api/v1/stock/ubicaciones/{entorno.camioneta_1}/saldos", headers=headers)
    libre = cliente.get(f"/api/v1/stock/ubicaciones/{entorno.camioneta_2}/saldos", headers=headers)

    assert (tomada.status_code, libre.status_code) == (200, 200)
    cuerpo = tomada.json()["jornada"]
    assert cuerpo["id"] == str(jornada_id)
    assert cuerpo["usuario_nombre"] == "Persona de prueba"
    assert "jornada" in libre.json()
    assert libre.json()["jornada"] is None


def test_la_ubicacion_de_una_respuesta_de_alta_no_trae_jornada(
    cliente: TestClient, sesion: Session
) -> None:
    """El alta devuelve `jornada: null` (una ubicación nueva nunca está tomada)."""
    entorno = _preparar(sesion, permisos=frozenset({"ADMIN_CONFIGURACION"}))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        "/api/v1/stock/ubicaciones",
        json={"nombre": "Camioneta 9", "tipo": "VEHICULO", "requiere_toma": True},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["jornada"] is None
