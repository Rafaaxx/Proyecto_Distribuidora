"""Tarea 8.1 (change 19; spec `ventas/administracion-de-ventas`; `design.md` D14): el detalle de
la venta trae el bloque `anulacion` y `GET /ventas` filtra por `estado`. Mismo arnés que
`test_ventas_consultas_api.py` (PostgreSQL real, login real).

Reglas citadas: VTA-20, VTA-22, REP-02, `01` §19, INV-03, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_anular_api`)

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_ventas_anular_api import (  # noqa: F401
    URL_VENTAS,
    Sesion,
    _con_op,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_anular_utiles import PERMISOS_DE_ANULADOR


def _anular(
    cliente_http: TestClient, s: Sesion, headers: dict[str, str], venta_id: str, **cuerpo: Any
) -> None:
    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id), **cuerpo},
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 200, respuesta.text


def _ids(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> set[str]:
    respuesta = cliente_http.get(URL_VENTAS, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return {i["venta_id"] for i in respuesta.json()["items"]}


def test_vta22_el_detalle_de_una_venta_anulada_trae_el_bloque_de_anulacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Detalle de una venta anulada" (con devolución del dinero)
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    cobranza = s.entorno.cobranza()
    venta_id = s.vender(cliente_http, headers, cobranza=cobranza)
    _anular(
        cliente_http,
        s,
        headers,
        venta_id,
        observacion="se cargó dos veces",
        devuelve_dinero=True,
    )

    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ANULADA"
    anulacion = cuerpo["anulacion"]
    assert anulacion["usuario_id"] == str(s.entorno.usuario_id)
    assert anulacion["usuario_nombre"] == "Persona de prueba"
    assert anulacion["motivo_id"] == str(s.entorno.motivo_anulacion_id)
    assert anulacion["motivo_nombre"] == "Error de carga"
    assert anulacion["observacion"] == "se cargó dos veces"
    assert anulacion["devuelve_dinero"] is True
    assert anulacion["anulada_en"]
    assert cuerpo["cobranza"]["estado"] == "ANULADA"


def test_vta20_el_devuelve_dinero_es_nulo_si_la_venta_no_tenia_cobro(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    _anular(cliente_http, s, headers, venta_id)

    anulacion = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()["anulacion"]

    assert anulacion["devuelve_dinero"] is None
    assert anulacion["observacion"] is None


def test_vta20_el_detalle_de_una_venta_confirmada_trae_la_anulacion_nula(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Detalle de una venta sin anular"
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    cuerpo = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()

    assert cuerpo["estado"] == "CONFIRMADA"
    assert "anulacion" in cuerpo and cuerpo["anulacion"] is None


def test_inv21_el_detalle_de_una_venta_ajena_anulada_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    ajena = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers_ajeno = ajena.entrar(cliente_http)
    venta_ajena = ajena.vender(cliente_http, headers_ajeno)
    _anular(cliente_http, ajena, headers_ajeno, venta_ajena)
    headers = s.entrar(cliente_http)

    assert cliente_http.get(f"{URL_VENTAS}/{venta_ajena}", headers=headers).status_code == 404


def test_rep02_el_filtro_estado_acota_el_listado(cliente_http: TestClient, sesion: Session) -> None:
    # Escenario: "Filtro por estado": tres confirmadas y una anulada.
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR, stock_inicial=200)
    headers = s.entrar(cliente_http)
    confirmadas = [
        s.vender(cliente_http, headers, numero=f"{s.prefijo}-{n:06d}") for n in (1, 2, 3)
    ]
    anulada = s.vender(cliente_http, headers, numero=f"{s.prefijo}-000004")
    _anular(cliente_http, s, headers, anulada)

    assert _ids(cliente_http, headers, estado="ANULADA") == {anulada}
    assert _ids(cliente_http, headers, estado="CONFIRMADA") == set(confirmadas)
    assert _ids(cliente_http, headers) == {*confirmadas, anulada}


@pytest.mark.parametrize("valor", ["OTRO", "anulada", ""])
def test_rep02_un_estado_fuera_del_catalogo_es_422(
    cliente_http: TestClient, sesion: Session, valor: str
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(URL_VENTAS, params={"estado": valor}, headers=headers)

    assert respuesta.status_code == 422


def test_rep02_el_listado_marca_el_estado_anulada_en_cada_item(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    _anular(cliente_http, s, headers, venta_id)

    (item,) = cliente_http.get(URL_VENTAS, params={"estado": "ANULADA"}, headers=headers).json()[
        "items"
    ]

    assert (item["venta_id"], item["estado"]) == (venta_id, "ANULADA")


def test_cli03_el_detalle_marca_si_el_cliente_es_el_consumidor_final(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Apply del lote 4 (change 19, D16): la pantalla de anulación fija la devolución del
    # consumidor final y quien solo tiene `ANULAR_VENTA` no puede leer `/clientes`.
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    normal_id = s.vender(cliente_http, headers)
    final_id = s.entorno.crear_cliente(es_consumidor_final=True, nombre="Consumidor final")
    sesion.commit()
    producto_id, presentacion_id = s.entorno.producto_a("4300.00")
    linea = s.entorno.linea(
        producto_id, presentacion_id, 1, precio="4300.00", unidades_referencia=1
    )
    venta_final_id = s.vender(
        cliente_http,
        headers,
        *[],
        numero=f"{s.prefijo}-000002",
        cliente_id=str(final_id),
        lineas=[linea],
        total="4300.00",
        cobranza=s.entorno.cobranza((s.entorno.efectivo_id, "4300.00", None)),
    )

    normal = cliente_http.get(f"{URL_VENTAS}/{normal_id}", headers=headers).json()
    final = cliente_http.get(f"{URL_VENTAS}/{venta_final_id}", headers=headers).json()

    assert normal["cliente_es_consumidor_final"] is False
    assert final["cliente_es_consumidor_final"] is True
