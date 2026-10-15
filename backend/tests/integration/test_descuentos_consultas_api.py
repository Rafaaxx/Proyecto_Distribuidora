"""Change 16, tarea 9.1 (`design.md` D18, spec `descuentos/reglas-de-descuento` requisito "Las
reglas se consultan por organización"): `GET /api/v1/descuentos/reglas` y
`GET /api/v1/descuentos/reglas/{regla_id}`, abiertos SOLO a `GESTIONAR_DESCUENTOS`.

Mismo arnés que `test_descuentos_api.py`: PostgreSQL real y `login` real.

Reglas citadas: DSC-01, INV-03, INV-21, SEG-06, SEG-07, `01` §18 y §19, `02` §10.2, `02` §11.
"""

# Los fixtures se reutilizan importándolos del arnés HTTP de `test_descuentos_api.py`.
# ruff: noqa: F401, F811

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_descuentos_api import (
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    _regla,
    cliente,
    gestor,
    sesion,
)

from app.modules.identidad.domain.permisos import PLANTILLAS_DE_ROL

URL = "/api/v1/descuentos/reglas"


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def _crear(cliente: TestClient, headers: dict[str, str], **cambios: Any) -> dict[str, Any]:
    respuesta = cliente.post(URL, json=_regla(**cambios), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _activar(cliente: TestClient, headers: dict[str, str], regla_id: str) -> None:
    respuesta = cliente.post(f"{URL}/{regla_id}/activacion", headers=_con_op(headers))
    assert respuesta.status_code == 200, respuesta.text


def _pausar(cliente: TestClient, headers: dict[str, str], regla_id: str) -> None:
    respuesta = cliente.post(f"{URL}/{regla_id}/pausa", headers=_con_op(headers))
    assert respuesta.status_code == 200, respuesta.text


def _poner_fin(cliente: TestClient, headers: dict[str, str], regla_id: str, dias: int) -> None:
    fin = (datetime.now(UTC) + timedelta(days=dias)).replace(microsecond=0)
    respuesta = cliente.put(
        f"{URL}/{regla_id}", json={"vigencia_hasta": fin.isoformat()}, headers=_con_op(headers)
    )
    assert respuesta.status_code == 200, respuesta.text


def _una_vencida(cliente: TestClient, headers: dict[str, str], nombre: str = "Vencida") -> str:
    desde = (datetime.now(UTC) - timedelta(days=10)).replace(microsecond=0)
    regla = _crear(cliente, headers, nombre=nombre, vigencia_desde=desde.isoformat())
    _activar(cliente, headers, regla["id"])
    _poner_fin(cliente, headers, regla["id"], -1)
    return str(regla["id"])


# --- listado ---------------------------------------------------------------------------------


def test_el_listado_trae_cada_regla_con_sus_datos_como_string(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Listado de reglas": borrador, activa y pausada; porcentaje `"0.050000"` e
    importe `"1000.00"`."""
    _crear(cliente, gestor, nombre="Borrador")
    activa = _crear(cliente, gestor, nombre="Activa")
    _activar(cliente, gestor, activa["id"])
    pausada = _crear(
        cliente,
        gestor,
        nombre="Importe fijo",
        accion_tipo="IMPORTE_FIJO",
        accion_valor="1000.00",
        tipo="VOLUMEN_ALCANCE",
        alcances=[{"tipo": "MARCA", "entidad_id": str(entorno.marca_id)}],
    )
    _activar(cliente, gestor, pausada["id"])
    _pausar(cliente, gestor, pausada["id"])

    respuesta = cliente.get(URL, headers=gestor)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["siguiente_cursor"] is None
    por_nombre = {r["nombre"]: r for r in cuerpo["items"]}
    assert {n: r["estado"] for n, r in por_nombre.items()} == {
        "Borrador": "BORRADOR",
        "Activa": "ACTIVA",
        "Importe fijo": "PAUSADA",
    }
    assert por_nombre["Activa"]["accion_porcentaje"] == "0.050000"
    assert por_nombre["Activa"]["accion_importe"] is None
    assert por_nombre["Importe fijo"]["accion_importe"] == "1000.00"
    assert por_nombre["Importe fijo"]["accion_porcentaje"] is None
    assert por_nombre["Importe fijo"]["alcances"][0]["nombre"] == "Bodega Norte"
    for campo in ("tipo", "medida", "operador", "umbral", "prioridad", "acumulable"):
        assert campo in por_nombre["Activa"]


def test_el_listado_va_de_la_mas_nueva_a_la_mas_vieja(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    for nombre in ("Uno", "Dos", "Tres"):
        _crear(cliente, gestor, nombre=nombre)

    items = cliente.get(URL, headers=gestor).json()["items"]

    assert [r["nombre"] for r in items] == ["Tres", "Dos", "Uno"]


def test_el_listado_filtra_por_estado(cliente: TestClient, gestor: dict[str, str]) -> None:
    _crear(cliente, gestor, nombre="Borrador")
    activa = _crear(cliente, gestor, nombre="Activa")
    _activar(cliente, gestor, activa["id"])
    pausada = _crear(cliente, gestor, nombre="Pausada")
    _activar(cliente, gestor, pausada["id"])
    _pausar(cliente, gestor, pausada["id"])

    def nombres(estado: str) -> list[str]:
        r = cliente.get(URL, params={"estado": estado}, headers=gestor)
        assert r.status_code == 200, r.text
        return [x["nombre"] for x in r.json()["items"]]

    assert nombres("BORRADOR") == ["Borrador"]
    assert nombres("ACTIVA") == ["Activa"]
    assert nombres("PAUSADA") == ["Pausada"]
    assert nombres("VENCIDA") == []


def test_el_filtro_vencida_trae_solo_las_activas_o_pausadas_con_el_fin_pasado(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    """Escenario "Filtro por vencidas": una activa con el fin pasado y otra vigente; también una
    pausada con el fin pasado. Las vencidas no figuran como `ACTIVA` ni como `PAUSADA`."""
    _una_vencida(cliente, gestor, "Vencida activa")
    vigente = _crear(cliente, gestor, nombre="Vigente")
    _activar(cliente, gestor, vigente["id"])
    pausada_vencida = _una_vencida(cliente, gestor, "Vencida pausada")
    _pausar(cliente, gestor, pausada_vencida)

    def pedir(estado: str) -> list[tuple[str, str]]:
        items = cliente.get(URL, params={"estado": estado}, headers=gestor).json()["items"]
        return sorted((r["nombre"], r["estado"]) for r in items)

    assert pedir("VENCIDA") == [("Vencida activa", "VENCIDA"), ("Vencida pausada", "VENCIDA")]
    assert pedir("ACTIVA") == [("Vigente", "ACTIVA")]
    assert pedir("PAUSADA") == []


def test_un_estado_desconocido_responde_422(cliente: TestClient, gestor: dict[str, str]) -> None:
    assert cliente.get(URL, params={"estado": "BORRADA"}, headers=gestor).status_code == 422


def test_el_listado_se_pagina_por_cursor_sin_repetir_ni_saltear(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    for numero in range(5):
        _crear(cliente, gestor, nombre=f"Regla {numero}")

    primera = cliente.get(URL, params={"limite": 2}, headers=gestor).json()
    segunda = cliente.get(
        URL, params={"limite": 2, "cursor": primera["siguiente_cursor"]}, headers=gestor
    ).json()
    tercera = cliente.get(
        URL, params={"limite": 2, "cursor": segunda["siguiente_cursor"]}, headers=gestor
    ).json()

    nombres = [r["nombre"] for p in (primera, segunda, tercera) for r in p["items"]]
    assert [len(p["items"]) for p in (primera, segunda, tercera)] == [2, 2, 1]
    assert nombres == [f"Regla {n}" for n in (4, 3, 2, 1, 0)]
    assert tercera["siguiente_cursor"] is None


def test_la_paginacion_conserva_el_filtro_de_estado(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    for numero in range(3):
        regla = _crear(cliente, gestor, nombre=f"Activa {numero}")
        _activar(cliente, gestor, regla["id"])
        _crear(cliente, gestor, nombre=f"Borrador {numero}")

    primera = cliente.get(URL, params={"estado": "ACTIVA", "limite": 2}, headers=gestor).json()
    segunda = cliente.get(
        URL,
        params={"estado": "ACTIVA", "limite": 2, "cursor": primera["siguiente_cursor"]},
        headers=gestor,
    ).json()

    nombres = [r["nombre"] for p in (primera, segunda) for r in p["items"]]
    assert nombres == ["Activa 2", "Activa 1", "Activa 0"]


@pytest.mark.parametrize("limite", [0, -1, 101])
def test_un_limite_fuera_de_rango_responde_422(
    cliente: TestClient, gestor: dict[str, str], limite: int
) -> None:
    assert cliente.get(URL, params={"limite": limite}, headers=gestor).status_code == 422


@pytest.mark.parametrize("cursor", ["no-es-un-cursor", "AAAA", "%%%"])
def test_un_cursor_invalido_responde_422_cursor_invalido(
    cliente: TestClient, gestor: dict[str, str], cursor: str
) -> None:
    respuesta = cliente.get(URL, params={"cursor": cursor}, headers=gestor)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CURSOR_INVALIDO"


def test_inv21_el_listado_solo_trae_las_reglas_de_la_organizacion(
    cliente: TestClient, sesion: Session, gestor: dict[str, str]
) -> None:
    ajena = Entorno(sesion)
    ajena.crear_regla_descuento(nombre="Ajena")
    ajena.sesion.commit()
    _crear(cliente, gestor, nombre="Propia")

    items = cliente.get(URL, headers=gestor).json()["items"]

    assert [r["nombre"] for r in items] == ["Propia"]


# --- detalle -----------------------------------------------------------------------------------


def test_el_detalle_trae_los_alcances_con_el_nombre_de_cada_entidad(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    regla = _crear(
        cliente,
        gestor,
        tipo="VOLUMEN_ALCANCE",
        alcances=[
            {"tipo": "MARCA", "entidad_id": str(entorno.marca_id)},
            {"tipo": "PRODUCTO", "entidad_id": str(entorno.vino_id)},
        ],
    )

    respuesta = cliente.get(f"{URL}/{regla['id']}", headers=gestor)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == regla["id"]
    assert {(a["tipo"], a["nombre"]) for a in cuerpo["alcances"]} == {
        ("MARCA", "Bodega Norte"),
        ("PRODUCTO", "Vino A"),
    }
    assert cuerpo["umbral"] == "20.0000"


def test_el_detalle_de_una_vencida_informa_vencida(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    regla_id = _una_vencida(cliente, gestor)

    assert cliente.get(f"{URL}/{regla_id}", headers=gestor).json()["estado"] == "VENCIDA"


def test_inv21_el_detalle_de_una_regla_ajena_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session, gestor: dict[str, str]
) -> None:
    """Escenario "Detalle de una regla ajena" (INV-21, SEG-07)."""
    ajena = Entorno(sesion)
    regla_ajena = ajena.crear_regla_descuento()
    ajena.sesion.commit()

    for regla_id in (regla_ajena, uuid4()):
        respuesta = cliente.get(f"{URL}/{regla_id}", headers=gestor)
        assert respuesta.status_code == 404, regla_id
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


# --- permisos (D18) -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plantilla",
    ["Vendedor/Repartidor", "Supervisor comercial", "Administración", "Consulta/Dirección"],
)
def test_las_plantillas_sin_gestionar_descuentos_no_leen_las_reglas(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str], plantilla: str
) -> None:
    """Escenario "Lectura sin permiso": con los permisos reales de cada plantilla de rol (el
    Vendedor es el del escenario; el resto, los de `01` §19)."""
    permisos = PLANTILLAS_DE_ROL[plantilla]
    assert "GESTIONAR_DESCUENTOS" not in permisos
    regla = _crear(cliente, gestor)
    headers = entorno.usuario_con(cliente, *sorted(permisos))

    listado = cliente.get(URL, headers=headers)
    detalle = cliente.get(f"{URL}/{regla['id']}", headers=headers)

    assert (listado.status_code, detalle.status_code) == (403, 403)
    assert listado.json()["codigo"] == "PERMISO_REQUERIDO"


def test_gestionar_descuentos_alcanza_para_leer(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    solo = entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    assert cliente.get(URL, headers=solo).status_code == 200


def test_otro_permiso_de_listas_no_abre_las_reglas_de_descuento(
    cliente: TestClient, entorno: Entorno
) -> None:
    headers = entorno.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")

    assert cliente.get(URL, headers=headers).status_code == 403


def test_las_lecturas_no_exigen_operation_id_y_exigen_sesion(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    assert cliente.get(URL, headers=gestor).status_code == 200
    assert cliente.get(URL).status_code == 401
