"""Change 13, tarea 5.5 (`design.md` D12, spec `precios/reglas-de-margen` requisito "Las reglas
de una lista se consultan con su fórmula", escenario "Elegir el alcance con solo el permiso de
listas"): las lecturas que alimentan el selector de alcance de una regla --productos,
categorías, marcas y opciones de proveedor-- responden también con solo `GESTIONAR_LISTAS`,
solo en lectura.

Siguen respondiendo con los permisos anteriores (`GESTIONAR_CATALOGO`, `REGISTRAR_COMPRA`,
`GESTIONAR_PROVEEDORES`...) y las escrituras siguen dando 403 con `GESTIONAR_LISTAS`: el
permiso de listas no abre nada de catálogo ni de proveedores más allá de leerlo (SEG-06).

Reglas citadas: SEG-06, SEG-07, `01` §19, ADR-043, `design.md` D12.
"""

# Los fixtures `cliente`, `sesion` y el autouse de limpieza se reutilizan importándolos del
# arnés HTTP de `test_precios_api.py`: pytest los resuelve por nombre, y ruff los ve como
# importaciones sin uso o redefinidas.
# ruff: noqa: F401, F811

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_precios_api import (
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
    "/api/v1/proveedores/opciones",
)


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def test_las_cuatro_lecturas_responden_con_solo_gestionar_listas(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")

    respuestas = {url: cliente.get(url, headers=headers) for url in LECTURAS}

    assert {url: r.status_code for url, r in respuestas.items()} == dict.fromkeys(LECTURAS, 200)
    productos = respuestas["/api/v1/catalogo/productos"].json()["items"]
    assert [p["nombre"] for p in productos] == ["Vino A"]
    assert [m["nombre"] for m in respuestas["/api/v1/catalogo/marcas"].json()["items"]] == [
        "Bodega Norte"
    ]
    assert [p["nombre"] for p in respuestas["/api/v1/proveedores/opciones"].json()["items"]] == [
        "Bodega Sur"
    ]
    assert respuestas["/api/v1/catalogo/categorias"].json()["items"]


def test_el_detalle_de_un_producto_responde_con_solo_gestionar_listas(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{entorno.vino_id}", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Vino A"


@pytest.mark.parametrize(
    ("permiso", "urls"),
    [
        ("GESTIONAR_CATALOGO", LECTURAS[:3]),
        ("REGISTRAR_COMPRA", ("/api/v1/catalogo/productos", "/api/v1/proveedores/opciones")),
        ("REGISTRAR_PAGO_PROVEEDOR", ("/api/v1/proveedores/opciones",)),
    ],
)
def test_las_lecturas_siguen_respondiendo_con_los_permisos_anteriores(
    cliente: TestClient, entorno: Entorno, permiso: str, urls: tuple[str, ...]
) -> None:
    headers = entorno.usuario_con(cliente, permiso)

    for url in urls:
        assert cliente.get(url, headers=headers).status_code == 200, (permiso, url)


def test_sin_gestionar_listas_ni_los_permisos_anteriores_siguen_dando_403(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "VER_COSTOS")

    estados = {url: cliente.get(url, headers=headers).status_code for url in LECTURAS}

    assert estados == dict.fromkeys(LECTURAS, 403)


def test_las_escrituras_siguen_dando_403_con_solo_gestionar_listas(
    cliente: TestClient, entorno: Entorno
) -> None:
    """`GESTIONAR_LISTAS` abre la lectura, nunca la escritura de catálogo ni de proveedores."""
    headers = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")
    escrituras: list[tuple[str, str, dict[str, Any]]] = [
        ("post", "/api/v1/catalogo/categorias", {"nombre": "Nueva"}),
        ("post", "/api/v1/catalogo/marcas", {"nombre": "Nueva"}),
        (
            "put",
            f"/api/v1/catalogo/productos/{entorno.vino_id}/referencia",
            {"presentacion_id": str(uuid4())},
        ),
        ("post", "/api/v1/proveedores", {"nombre": "Nuevo"}),
    ]

    for metodo, url, cuerpo in escrituras:
        enviar = cliente.post if metodo == "post" else cliente.put
        respuesta = enviar(url, json=cuerpo, headers=_con_op(headers))
        assert respuesta.status_code == 403, (metodo, url)
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_el_listado_de_proveedores_completo_sigue_exigiendo_gestionar_proveedores(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Solo las opciones se abren a `GESTIONAR_LISTAS`: el listado y la ficha del proveedor no
    (D12)."""
    headers = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")

    listado = cliente.get("/api/v1/proveedores", headers=headers)
    ficha = cliente.get(f"/api/v1/proveedores/{entorno.proveedor_id}", headers=headers)

    assert (listado.status_code, ficha.status_code) == (403, 403)
