"""Change 09, tarea 9.5: cobertura de aislamiento (INV-21, SEG-07) de las siete
rutas nuevas de `stock` y de `catalogo`:

- escrituras: `POST /stock/ubicaciones`, `PUT /stock/ubicaciones/{id}`,
  `POST /stock/iniciales`;
- lecturas: `GET /stock/ubicaciones`, `GET /stock/ubicaciones/{id}/saldos`,
  `GET /stock/kardex` y `GET /catalogo/productos/{producto_id}/costo`.

Mismo arnés HTTP que `test_stock_api.py` (PostgreSQL real, `login` real de dos
organizaciones, nunca un token fabricado): se reutilizan su `Entorno` y sus
fixtures. Un recurso de otra organización responde 404 (no 403) y no deja rastro:
ni ubicación modificada, ni movimiento, ni fila de saldo o de costo, ni dato del
stock o del costo ajeno en la respuesta.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    ADMIN,
    URL_INICIALES,
    URL_KARDEX,
    URL_UBICACIONES,
    Entorno,
    _con_op,
    _contar,
    _cuerpo_inicial,
    _cuerpo_ubicacion,
    _limpiar_datos_confirmados,
    _params_kardex,
    _url_costo,
    _url_saldos,
    cliente,
    sesion,
)

MARCA_DE_COSTO = "7777.77"
MARCA_DE_CANTIDAD = 424242


def _dos_organizaciones(sesion: Session) -> tuple[Entorno, Entorno]:
    return (
        Entorno(sesion, permisos=ADMIN, nombre_usuario="a1"),
        Entorno(sesion, permisos=ADMIN, nombre_usuario="b1"),
    )


def _sembrar_con_marcas(entorno: Entorno) -> None:
    entorno.sembrar(entorno.producto_id, MARCA_DE_CANTIDAD, MARCA_DE_COSTO)


def _sin_rastro_de_a(sesion: Session, entorno_a: Entorno, entorno_b: Entorno) -> None:
    """Nada nuevo en ninguna de las dos organizaciones, salvo lo sembrado a mano
    en la de A (un movimiento)."""
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 1
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0
    assert _contar(sesion, "stock_saldo", entorno_b.org) == 0
    assert _contar(sesion, "costo_producto", entorno_b.org) == 0


def test_inv21_modificar_una_ubicacion_ajena_es_404_y_no_la_toca(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.put(
        f"{URL_UBICACIONES}/{entorno_a.deposito_id}",
        json={**_cuerpo_ubicacion(nombre="Tomada por B"), "activo": True},
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    nombre = sesion.scalar(
        text("select nombre from ubicacion where id = :i"), {"i": entorno_a.deposito_id}
    )
    assert nombre == "Depósito central"


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_ubicacion(
    cliente: TestClient, sesion: Session
) -> None:
    """`organizacion_id` sale siempre del token: si viene en el cuerpo, el esquema
    estricto lo rechaza y no se crea nada en ninguna de las dos organizaciones."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    antes_a = _contar(sesion, "ubicacion", entorno_a.org)
    antes_b = _contar(sesion, "ubicacion", entorno_b.org)

    respuesta = cliente.post(
        URL_UBICACIONES,
        json=_cuerpo_ubicacion(nombre="Intrusa", organizacion_id=str(entorno_a.org)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "ubicacion", entorno_a.org) == antes_a
    assert _contar(sesion, "ubicacion", entorno_b.org) == antes_b


def test_inv21_una_ubicacion_creada_queda_en_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    headers_a = entorno_a.confirmar_y_entrar(cliente)

    creada = cliente.post(
        URL_UBICACIONES, json=_cuerpo_ubicacion(nombre="Solo de B"), headers=_con_op(headers_b)
    )

    assert creada.status_code == 201
    de_a = cliente.get(URL_UBICACIONES, headers=headers_a).json()["items"]
    de_b = cliente.get(URL_UBICACIONES, headers=headers_b).json()["items"]
    assert "Solo de B" not in [u["nombre"] for u in de_a]
    assert "Solo de B" in [u["nombre"] for u in de_b]


def test_inv21_registrar_stock_inicial_en_una_ubicacion_ajena_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    _sin_rastro_de_a(sesion, entorno_a, entorno_b)


def test_inv21_registrar_stock_inicial_de_un_producto_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    linea = {
        "producto_id": str(entorno_a.producto_id),
        "cantidad_base": 5,
        "costo_unitario": "5",
    }

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, lineas=[linea]),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    _sin_rastro_de_a(sesion, entorno_a, entorno_b)


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_el_stock_inicial(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, organizacion_id=str(entorno_a.org)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 0
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0


def test_inv21_leer_el_stock_de_una_ubicacion_ajena_es_404_y_no_revela_nada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_saldos(entorno_a.deposito_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert str(MARCA_DE_CANTIDAD) not in respuesta.text
    assert MARCA_DE_COSTO not in respuesta.text
    assert "Vino A" not in respuesta.text


def test_inv21_leer_el_kardex_con_una_ubicacion_o_un_producto_ajenos_es_404_y_no_revela_nada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    ubicacion_ajena = cliente.get(
        URL_KARDEX,
        params=_params_kardex(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
        headers=headers_b,
    )
    producto_ajeno = cliente.get(
        URL_KARDEX,
        params=_params_kardex(entorno_b, producto_id=str(entorno_a.producto_id)),
        headers=headers_b,
    )

    for respuesta in (ubicacion_ajena, producto_ajeno):
        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert str(MARCA_DE_CANTIDAD) not in respuesta.text
        assert MARCA_DE_COSTO not in respuesta.text


def test_inv21_leer_el_costo_de_un_producto_ajeno_es_404_y_no_revela_el_promedio(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_costo(entorno_a.producto_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert MARCA_DE_COSTO not in respuesta.text
    assert str(MARCA_DE_CANTIDAD) not in respuesta.text
    # Un producto que no existe en ninguna organización responde igual: el 404 no
    # distingue "ajeno" de "inexistente".
    inexistente = cliente.get(_url_costo(uuid4()), headers=headers_b)
    assert (inexistente.status_code, inexistente.json()["codigo"]) == (
        respuesta.status_code,
        respuesta.json()["codigo"],
    )


def test_inv21_cada_organizacion_ve_solo_su_stock_su_kardex_y_su_costo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.sembrar(entorno_a.producto_id, 111, "1000")
    entorno_b.sembrar(entorno_b.producto_id, 222, "2000")
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    saldos_a = cliente.get(_url_saldos(entorno_a.deposito_id), headers=headers_a).json()
    saldos_b = cliente.get(_url_saldos(entorno_b.deposito_id), headers=headers_b).json()
    kardex_a = cliente.get(URL_KARDEX, params=_params_kardex(entorno_a), headers=headers_a).json()
    kardex_b = cliente.get(URL_KARDEX, params=_params_kardex(entorno_b), headers=headers_b).json()
    costo_b = cliente.get(_url_costo(entorno_b.producto_id), headers=headers_b).json()

    assert [linea["cantidad_base"] for linea in saldos_a["items"]] == [111]
    assert [linea["cantidad_base"] for linea in saldos_b["items"]] == [222]
    assert [m["cantidad_base"] for m in kardex_a["items"]] == [111]
    assert [m["cantidad_base"] for m in kardex_b["items"]] == [222]
    assert costo_b["costo_promedio"] == "2000.000000"
