"""Change 24, tarea 10.2 (`design.md` D9, `01` §19): la lista de productos de `catalogo/api.py` que
alimenta «Agregar producto» de la rendición responde también con solo `RENDIR_JORNADA`, solo en
lectura.

Siguen respondiendo los permisos anteriores; el detalle, las demás lecturas de catálogo y las
escrituras siguen dando 403 con `RENDIR_JORNADA`: el permiso de rendir no abre nada de catálogo
más allá de listar productos (SEG-06). Mismo criterio que `test_descuentos_lecturas_de_alcance.py`.

Reglas citadas: SEG-06, SEG-07, RUT-06, `01` §19, `design.md` D9.
"""

# Los fixtures se reutilizan importándolos del arnés HTTP de `test_descuentos_api.py`.
# ruff: noqa: F401, F811

from __future__ import annotations

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

LISTA = "/api/v1/catalogo/productos"


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def test_la_lista_de_productos_activos_responde_con_solo_rendir_jornada(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "RENDIR_JORNADA")

    respuesta = cliente.get(f"{LISTA}?activo=true", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    assert [p["nombre"] for p in respuesta.json()["items"]] == ["Vino A"]


@pytest.mark.parametrize(
    "permiso",
    ["GESTIONAR_CATALOGO", "GESTIONAR_LISTAS", "GESTIONAR_DESCUENTOS", "REGISTRAR_COMPRA"],
)
def test_la_lista_sigue_respondiendo_con_los_permisos_anteriores(
    cliente: TestClient, entorno: Entorno, permiso: str
) -> None:
    headers = entorno.usuario_con(cliente, permiso)

    assert cliente.get(LISTA, headers=headers).status_code == 200


def test_sin_rendir_jornada_ni_los_permisos_anteriores_da_403(
    cliente: TestClient, entorno: Entorno
) -> None:
    for permiso in ("VER_COSTOS", "ABRIR_JORNADA"):
        headers = entorno.usuario_con(cliente, permiso)

        assert cliente.get(LISTA, headers=headers).status_code == 403, permiso


def test_rendir_jornada_no_abre_el_detalle_ni_las_demas_lecturas_ni_las_escrituras(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Solo la lista de productos: categorías, marcas, el detalle y las escrituras siguen
    cerrados (SEG-06)."""
    headers = entorno.usuario_con(cliente, "RENDIR_JORNADA")

    cerradas = (
        "/api/v1/catalogo/categorias",
        "/api/v1/catalogo/marcas",
        f"{LISTA}/{entorno.vino_id}",
        "/api/v1/proveedores/opciones",
    )
    assert {u: cliente.get(u, headers=headers).status_code for u in cerradas} == dict.fromkeys(
        cerradas, 403
    )
    escritura = cliente.post(LISTA, json={"nombre": "Nuevo"}, headers=_con_op(headers))
    assert escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
