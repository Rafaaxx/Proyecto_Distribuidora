# ruff: noqa: F811
"""Tarea 11.2 (change 18b, `design.md` D16; specs `ventas/administracion-de-ventas` y
`clientes/datos-de-credito`): `GET /api/v1/ventas/credito?cliente_id=` con `VENDER` trae el crédito
de un cliente para vender: límite (vacío = sin control), saldo, disponible, política aplicable y
tolerancia aplicable, con la herencia de la organización ya resuelta. Un cliente de otra
organización responde 404. Las lecturas de administración de clientes siguen sin `disponible`.

Reglas citadas: CRE-01, CRE-03, CRE-06, `01` §19, INV-03, INV-21, SEG-06, SEG-07.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL = "/api/v1/ventas/credito"


def _credito(
    cliente_http: TestClient, headers: dict[str, str], cliente_id: object
) -> dict[str, object]:
    respuesta = cliente_http.get(URL, params={"cliente_id": str(cliente_id)}, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, object] = respuesta.json()
    return cuerpo


def test_cre01_el_disponible_y_la_politica_heredada_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Crédito con política heredada": límite $200.000, saldo $150.000, sin política
    propia y la organización con AUTORIZAR."""
    s = Sesion(sesion)
    s.entorno.configurar(politica_credito_default="AUTORIZAR")
    s.entorno.datos_de_credito(limite="200000.00", politica=None)
    headers = s.entrar(cliente_http)

    credito = _credito(cliente_http, headers, s.entorno.cliente_id)

    assert credito == {
        "cliente_id": str(s.entorno.cliente_id),
        "limite": "200000.00",
        "saldo": "150000.00",
        "disponible": "50000.00",
        "politica": "AUTORIZAR",
        "tolerancia_tipo": None,
        "tolerancia_valor": None,
    }


def test_cre03_la_politica_propia_del_cliente_gana_a_la_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: política propia BLOQUEAR sobre la ADVERTIR de la organización; un cliente
    ya excedido tiene disponible negativo (límite menos saldo, CRE-01)."""
    s = Sesion(sesion)
    s.entorno.configurar(politica_credito_default="ADVERTIR")
    s.entorno.datos_de_credito(limite="100000.00", politica="BLOQUEAR")
    headers = s.entrar(cliente_http)

    credito = _credito(cliente_http, headers, s.entorno.cliente_id)

    assert credito["politica"] == "BLOQUEAR"
    assert credito["disponible"] == "-50000.00"
    assert credito["saldo"] == "150000.00"


def test_cre01_sin_limite_no_hay_control_ni_disponible(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    s.entorno.datos_de_credito(limite=None, politica=None)
    headers = s.entrar(cliente_http)

    credito = _credito(cliente_http, headers, s.entorno.cliente_id)

    assert credito["limite"] is None
    assert credito["disponible"] is None
    assert credito["saldo"] == "150000.00"


def test_cre06_la_tolerancia_es_la_del_cliente_o_si_no_tiene_la_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """El par se hereda entero: la del cliente (IMPORTE) gana; sin ella rige la de la
    organización (PORCENTAJE)."""
    s = Sesion(sesion)
    s.entorno.configurar(tolerancia_offline_tipo="PORCENTAJE", tolerancia_offline_valor="5.00")
    s.entorno.datos_de_credito(limite="200000.00", politica="AUTORIZAR")
    headers = s.entrar(cliente_http)

    de_la_organizacion = _credito(cliente_http, headers, s.entorno.cliente_id)
    s.entorno.actualizar_cliente(
        s.entorno.cliente_id, tolerancia_offline_tipo="IMPORTE", tolerancia_offline_valor="20000.00"
    )
    sesion.commit()
    del_cliente = _credito(cliente_http, headers, s.entorno.cliente_id)

    assert (de_la_organizacion["tolerancia_tipo"], de_la_organizacion["tolerancia_valor"]) == (
        "PORCENTAJE",
        "5.00",
    )
    assert (del_cliente["tolerancia_tipo"], del_cliente["tolerancia_valor"]) == (
        "IMPORTE",
        "20000.00",
    )


def test_seg07_el_credito_de_un_cliente_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(
        URL, params={"cliente_id": str(ajena.entorno.cliente_id)}, headers=headers
    )

    assert respuesta.status_code == 404


def test_seg06_exige_vender_y_el_cliente_es_obligatorio(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sin_vender = usuario_con(cliente_http, sesion, s, frozenset({"GESTIONAR_CLIENTES"}))
    vende = s.entrar(cliente_http)

    sin_permiso = cliente_http.get(
        URL, params={"cliente_id": str(s.entorno.cliente_id)}, headers=sin_vender
    )
    sin_sesion = cliente_http.get(URL, params={"cliente_id": str(s.entorno.cliente_id)})
    sin_cliente = cliente_http.get(URL, headers=vende)

    assert sin_permiso.status_code == 403
    assert sin_permiso.json()["codigo"] == "PERMISO_REQUERIDO"
    assert sin_sesion.status_code == 401
    assert sin_cliente.status_code == 422


def test_cre01_las_lecturas_de_administracion_de_clientes_siguen_sin_disponible(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Las consultas no exponen cálculos de crédito": la ficha del cliente trae el
    límite y la política configurada, no el disponible ni la política aplicada."""
    s = Sesion(sesion)
    s.entorno.datos_de_credito(limite="200000.00", politica="AUTORIZAR")
    gestor = usuario_con(cliente_http, sesion, s, frozenset({"GESTIONAR_CLIENTES"}))

    ficha = cliente_http.get(f"/api/v1/clientes/{s.entorno.cliente_id}", headers=gestor)

    assert ficha.status_code == 200
    assert ficha.json()["limite_credito"] == "200000.00"
    for prohibido in ("disponible", "exceso", "politica_aplicada"):
        assert prohibido not in ficha.json()
