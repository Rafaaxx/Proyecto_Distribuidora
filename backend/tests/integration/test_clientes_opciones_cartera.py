# ruff: noqa: F811
"""Change 20b, tarea 9.3 (`design.md` D14; spec `clientes/cartera-de-clientes`): las lecturas de
clientes ofrecen primero la cartera.

- `GET /clientes/opciones`: quien llega por `VENDER` o `REGISTRAR_COBRANZA` sin `GESTIONAR_CLIENTES`
  y con clientes asignados recibe sus clientes (y el consumidor final si lo pide); `alcance=todos`
  trae todos; sin cartera, o con `GESTIONAR_CLIENTES`, también todos.
- `GET /clientes`: suma `vendedor_id`, `vendedor_nombre` y `vendedor_valido`, y filtra por vendedor
  y por "sin vendedor".

La cartera ordena lo que se ofrece, no lo que se permite: la venta y la cobranza a un cliente fuera
de la cartera se aceptan (`test_cartera_no_rechaza_operaciones.py`).

Reglas citadas: `01` §19, ADR-052, INV-17, INV-21.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    EntornoUsuarios,
    SesionAbierta,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL_OPCIONES = "/api/v1/clientes/opciones"
URL_CLIENTES = "/api/v1/clientes"
VENDER = frozenset({"VENDER"})
COBRAR = frozenset({"REGISTRAR_COBRANZA"})
GESTIONAR = frozenset({"GESTIONAR_CLIENTES"})


class Escenario:
    """Diez clientes (más el consumidor final) y un vendedor con dos de ellos."""

    def __init__(self, sesion: Session, cliente_http: TestClient) -> None:
        self.entorno = EntornoUsuarios(sesion)
        self.http = cliente_http
        self.clientes = [
            crear_cliente(sesion, self.entorno.org, nombre=f"Cliente {i:02d}") for i in range(10)
        ]
        self.final = crear_cliente(
            sesion, self.entorno.org, nombre="Consumidor final", es_consumidor_final=True
        )
        sesion.commit()
        self.juan = self._usuario("Vendedor", VENDER)
        self.suyos = self.clientes[:2]
        self.asignar(self.juan[0], *self.suyos)

    def _usuario(self, nombre: str, permisos: frozenset[str]) -> tuple[UUID, SesionAbierta]:
        usuario_id, usuario = self.entorno.crear_usuario(self.entorno.crear_rol(nombre, permisos))
        return usuario_id, self.entorno.abrir_sesion(self.http, usuario_id, usuario)

    def usuario(self, nombre: str, permisos: frozenset[str]) -> tuple[UUID, SesionAbierta]:
        return self._usuario(f"{nombre} {uuid4().hex[:4]}", permisos)

    def asignar(self, vendedor_id: UUID | None, *clientes: UUID) -> None:
        self.entorno.sesion.execute(
            text("UPDATE cliente SET vendedor_id = :v WHERE id = ANY(:c)"),
            {"v": vendedor_id, "c": list(clientes)},
        )
        self.entorno.sesion.commit()

    def get(self, quien: SesionAbierta, ruta: str) -> Any:
        return self.entorno.enviar(self.http, "GET", ruta, quien)


def _ids(respuesta: Any) -> set[str]:
    assert respuesta.status_code == 200, respuesta.text
    return {fila["id"] for fila in respuesta.json()["items"]}


def _ids_de_listado(respuesta: Any) -> set[str]:
    return _ids(respuesta)


# --- GET /clientes/opciones -----------------------------------------------------------------


def test_el_vendedor_con_cartera_ve_sus_clientes_y_el_consumidor_final(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19: dos clientes asignados en una organización de diez."""
    e = Escenario(sesion_real, cliente_http)
    _, juan = e.juan

    con_final = e.get(juan, f"{URL_OPCIONES}?incluir_consumidor_final=true")
    sin_final = e.get(juan, URL_OPCIONES)

    assert _ids(con_final) == {str(c) for c in e.suyos} | {str(e.final)}
    assert _ids(sin_final) == {str(c) for c in e.suyos}


def test_buscar_en_todos_trae_todos_los_clientes(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-052: `alcance=todos`."""
    e = Escenario(sesion_real, cliente_http)
    _, juan = e.juan

    todos = e.get(juan, f"{URL_OPCIONES}?alcance=todos")
    todos_con_final = e.get(juan, f"{URL_OPCIONES}?alcance=todos&incluir_consumidor_final=true")

    assert _ids(todos) == {str(c) for c in e.clientes}
    assert _ids(todos_con_final) == {str(c) for c in e.clientes} | {str(e.final)}


def test_el_vendedor_sin_cartera_ve_todos(cliente_http: TestClient, sesion_real: Session) -> None:
    """ADR-052: sin ningún cliente asignado, sus clientes son todos."""
    e = Escenario(sesion_real, cliente_http)
    _, pedro = e.usuario("Pedro", VENDER)

    respuesta = e.get(pedro, URL_OPCIONES)

    assert _ids(respuesta) == {str(c) for c in e.clientes}


def test_quien_cobra_sin_gestionar_clientes_tambien_ve_su_cartera(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = Escenario(sesion_real, cliente_http)
    cobrador_id, cobrador = e.usuario("Cobrador", COBRAR)
    e.asignar(cobrador_id, e.clientes[5])

    assert _ids(e.get(cobrador, URL_OPCIONES)) == {str(e.clientes[5])}


def test_con_gestionar_clientes_ve_todos_aunque_tenga_cartera(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19: la administración de clientes ve todos."""
    e = Escenario(sesion_real, cliente_http)
    gestor_id, gestor = e.usuario("Gestor", GESTIONAR | VENDER)
    e.asignar(gestor_id, e.clientes[7])

    assert _ids(e.get(gestor, URL_OPCIONES)) == {str(c) for c in e.clientes}


def test_la_cartera_pagina_por_cursor_sin_perder_ni_repetir(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = Escenario(sesion_real, cliente_http)
    _, juan = e.juan

    primera = e.get(juan, f"{URL_OPCIONES}?limite=1").json()
    segunda = e.get(juan, f"{URL_OPCIONES}?limite=1&cursor={primera['cursor_siguiente']}").json()

    assert primera["cursor_siguiente"] is not None
    assert segunda["cursor_siguiente"] is None
    vistos = [primera["items"][0]["id"], segunda["items"][0]["id"]]
    assert set(vistos) == {str(c) for c in e.suyos}


def test_la_cartera_no_mezcla_clientes_de_otra_organizacion_ni_alcances_invalidos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21."""
    e = Escenario(sesion_real, cliente_http)
    otra = EntornoUsuarios(sesion_real)
    ajeno = crear_cliente(sesion_real, otra.org, nombre="Ajeno")
    sesion_real.commit()
    _, juan = e.juan
    todos = e.get(juan, f"{URL_OPCIONES}?alcance=todos")
    invalido = e.get(juan, f"{URL_OPCIONES}?alcance=cartera")

    assert str(ajeno) not in _ids(todos)
    assert invalido.status_code == 422


def test_las_opciones_siguen_exigiendo_alguno_de_los_tres_permisos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = Escenario(sesion_real, cliente_http)
    _, sin_permiso = e.usuario("Auditor", frozenset({"VER_REPORTES"}))

    assert e.get(sin_permiso, URL_OPCIONES).status_code == 403


# --- GET /clientes (administración) ------------------------------------------------------------


def _filas_por_id(respuesta: Any) -> dict[str, dict[str, Any]]:
    assert respuesta.status_code == 200, respuesta.text
    return {fila["id"]: fila for fila in respuesta.json()["items"]}


def test_el_listado_de_administracion_muestra_el_vendedor_de_cada_cliente(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19: administración ve todos, con el vendedor de cada uno."""
    e = Escenario(sesion_real, cliente_http)
    _, gestor = e.usuario("Gestor", GESTIONAR)

    filas = _filas_por_id(e.get(gestor, URL_CLIENTES))

    suyo = filas[str(e.suyos[0])]
    assert suyo["vendedor_id"] == str(e.juan[0])
    assert suyo["vendedor_nombre"] is not None
    assert suyo["vendedor_valido"] is True
    sin_vendedor = filas[str(e.clientes[9])]
    assert sin_vendedor["vendedor_id"] is None
    assert sin_vendedor["vendedor_nombre"] is None
    assert sin_vendedor["vendedor_valido"] is None
    assert len(filas) == 11


def test_el_listado_filtra_por_vendedor_y_por_sin_vendedor(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = Escenario(sesion_real, cliente_http)
    _, gestor = e.usuario("Gestor", GESTIONAR)
    pedro_id, _ = e.usuario("Pedro", VENDER)
    e.asignar(pedro_id, e.clientes[3])

    de_juan = _ids_de_listado(e.get(gestor, f"{URL_CLIENTES}?vendedor_id={e.juan[0]}"))
    de_pedro = _ids_de_listado(e.get(gestor, f"{URL_CLIENTES}?vendedor_id={pedro_id}"))
    sin = _ids_de_listado(e.get(gestor, f"{URL_CLIENTES}?sin_vendedor=true"))

    assert de_juan == {str(c) for c in e.suyos}
    assert de_pedro == {str(e.clientes[3])}
    asignados = {*map(str, e.suyos), str(e.clientes[3])}
    todos = {*map(str, e.clientes), str(e.final)}
    assert sin == todos - asignados
    # Un vendedor y "sin vendedor" a la vez no coinciden con ningún cliente.
    assert (
        _ids_de_listado(e.get(gestor, f"{URL_CLIENTES}?vendedor_id={e.juan[0]}&sin_vendedor=true"))
        == set()
    )


def test_el_filtro_por_vendedor_se_combina_con_el_estado_y_no_cruza_organizaciones(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21: un `vendedor_id` de otra organización no devuelve nada."""
    e = Escenario(sesion_real, cliente_http)
    otra = Escenario(sesion_real, cliente_http)
    _, gestor = e.usuario("Gestor", GESTIONAR)
    sesion_real.execute(
        text("UPDATE cliente SET estado = 'SUSPENDIDO' WHERE id = :c"), {"c": e.suyos[0]}
    )
    sesion_real.commit()

    suspendidos = _ids_de_listado(
        e.get(gestor, f"{URL_CLIENTES}?vendedor_id={e.juan[0]}&estado=SUSPENDIDO")
    )
    ajeno = _ids_de_listado(e.get(gestor, f"{URL_CLIENTES}?vendedor_id={otra.juan[0]}"))

    assert suspendidos == {str(e.suyos[0])}
    assert ajeno == set()


def test_el_vendedor_de_baja_o_sin_permiso_se_marca_como_no_valido(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D6, D15: la asignación se conserva y la pantalla marca los clientes a reasignar."""
    e = Escenario(sesion_real, cliente_http)
    _, gestor = e.usuario("Gestor", GESTIONAR)
    baja_id, _ = e.usuario("Baja", VENDER)
    e.asignar(baja_id, e.clientes[4])
    sesion_real.execute(
        text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": baja_id}
    )
    sesion_real.commit()

    filas = _filas_por_id(e.get(gestor, f"{URL_CLIENTES}?vendedor_id={baja_id}"))

    assert filas[str(e.clientes[4])]["vendedor_valido"] is False
    assert filas[str(e.clientes[4])]["vendedor_nombre"] is not None


def test_el_detalle_de_un_cliente_trae_el_vendedor(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = Escenario(sesion_real, cliente_http)
    _, gestor = e.usuario("Gestor", GESTIONAR)

    respuesta = e.get(gestor, f"{URL_CLIENTES}/{e.suyos[0]}")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["vendedor_id"] == str(e.juan[0])
    assert respuesta.json()["vendedor_valido"] is True
