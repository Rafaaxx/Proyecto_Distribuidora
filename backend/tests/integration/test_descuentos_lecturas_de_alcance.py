"""Change 16, tarea 9.2 (`design.md` D18, spec `descuentos/reglas-de-descuento` escenario "Elegir el
alcance con solo el permiso de descuentos"): las cuatro lecturas de `catalogo/api.py` que alimentan
el selector de alcance de una regla -- categorías, marcas, productos y el detalle de un producto --
responden también con solo `GESTIONAR_DESCUENTOS`, solo en lectura.

Siguen respondiendo con los permisos anteriores y las escrituras de catálogo siguen dando 403 con
`GESTIONAR_DESCUENTOS`: el permiso de descuentos no abre nada de catálogo más allá de leerlo
(SEG-06). Mismo criterio que `test_precios_lecturas_de_alcance.py` (ADR-047 punto 16).

Reglas citadas: SEG-06, SEG-07, `01` §19, `design.md` D18.
"""

# Los fixtures se reutilizan importándolos del arnés HTTP de `test_descuentos_api.py`.
# ruff: noqa: F401, F811

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_descuentos_api import (
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

LECTURAS = (
    "/api/v1/catalogo/categorias",
    "/api/v1/catalogo/marcas",
    "/api/v1/catalogo/productos",
)


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def test_las_lecturas_de_alcance_responden_con_solo_gestionar_descuentos(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    respuestas = {url: cliente.get(url, headers=headers) for url in LECTURAS}

    assert {url: r.status_code for url, r in respuestas.items()} == dict.fromkeys(LECTURAS, 200)
    assert [p["nombre"] for p in respuestas["/api/v1/catalogo/productos"].json()["items"]] == [
        "Vino A"
    ]
    assert [m["nombre"] for m in respuestas["/api/v1/catalogo/marcas"].json()["items"]] == [
        "Bodega Norte"
    ]
    assert respuestas["/api/v1/catalogo/categorias"].json()["items"]


def test_el_detalle_de_un_producto_responde_con_solo_gestionar_descuentos(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{entorno.vino_id}", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Vino A"


@pytest.mark.parametrize(
    ("permiso", "urls"),
    [
        ("GESTIONAR_CATALOGO", LECTURAS),
        ("GESTIONAR_LISTAS", LECTURAS),
        ("REGISTRAR_COMPRA", ("/api/v1/catalogo/productos",)),
    ],
)
def test_las_lecturas_siguen_respondiendo_con_los_permisos_anteriores(
    cliente: TestClient, entorno: Entorno, permiso: str, urls: tuple[str, ...]
) -> None:
    headers = entorno.usuario_con(cliente, permiso)

    for url in urls:
        assert cliente.get(url, headers=headers).status_code == 200, (permiso, url)


def test_sin_gestionar_descuentos_ni_los_permisos_anteriores_dan_403(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "VER_COSTOS")

    urls = (*LECTURAS, f"/api/v1/catalogo/productos/{entorno.vino_id}")
    estados = {url: cliente.get(url, headers=headers).status_code for url in urls}

    assert estados == dict.fromkeys(urls, 403)


def test_las_escrituras_de_catalogo_siguen_dando_403_con_solo_gestionar_descuentos(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")
    escrituras: list[tuple[str, str, dict[str, Any]]] = [
        ("post", "/api/v1/catalogo/categorias", {"nombre": "Nueva"}),
        ("put", f"/api/v1/catalogo/categorias/{entorno.categoria_id}", {"nombre": "X"}),
        ("post", "/api/v1/catalogo/marcas", {"nombre": "Nueva"}),
        ("put", f"/api/v1/catalogo/marcas/{entorno.marca_id}", {"nombre": "X"}),
        ("post", "/api/v1/catalogo/productos", {"nombre": "Nuevo"}),
        (
            "put",
            f"/api/v1/catalogo/productos/{entorno.vino_id}/referencia",
            {"presentacion_id": str(uuid4())},
        ),
    ]

    for metodo, url, cuerpo in escrituras:
        enviar = cliente.post if metodo == "post" else cliente.put
        respuesta = enviar(url, json=cuerpo, headers=_con_op(headers))
        assert respuesta.status_code == 403, (metodo, url)
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_las_demas_lecturas_de_otros_modulos_no_se_abren_a_gestionar_descuentos(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Solo las cuatro lecturas de catálogo: proveedores y listas de precios siguen cerrados."""
    headers = entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    urls = ("/api/v1/proveedores/opciones", "/api/v1/proveedores", "/api/v1/precios/listas")
    assert {u: cliente.get(u, headers=headers).status_code for u in urls} == dict.fromkeys(
        urls, 403
    )
