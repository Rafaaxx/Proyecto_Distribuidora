"""Tarea 7.1 (change 26, spec `reportes/saldos-de-cuentas`; `design.md` D8 = B):
`GET /api/v1/reportes/saldos/clientes` y `/proveedores`: el saldo actual de cada cuenta desde
`saldo_cuenta` (sin fila, cero), con filtros, disponible, totales adeudado y a favor, y la regla de
permisos compuesta de los proveedores (`VER_REPORTES` y además `GESTIONAR_PROVEEDORES`,
`REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`).

PostgreSQL real y login real. Reglas citadas: CC-03, CC-04, CRE-01, INV-13, INV-21, `01` §19,
ADR-033, ADR-060.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    cuentas_del_entorno_en_cero,
    mover_cuenta,
    sembrar_cliente_de_cartera,
    sembrar_proveedor_de_prueba,
    suma_del_libro,
)
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import otro_usuario, usuario_con

from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    CONSULTA_DIRECCION,
    PLANTILLAS_DE_ROL,
    SUPERVISOR_COMERCIAL,
)

URL_CLIENTES = "/api/v1/reportes/saldos/clientes"
URL_PROVEEDORES = "/api/v1/reportes/saldos/proveedores"


def _limpia(sesion: Session) -> Sesion:
    return cuentas_del_entorno_en_cero(sesion, Sesion(sesion))


def _pedir(
    cliente_http: TestClient, headers: dict[str, str], url: str = URL_CLIENTES, **filtros: str
) -> dict[str, Any]:
    respuesta = cliente_http.get(url, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _lector(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)


def _saldos(cuerpo: dict[str, Any], clave: str = "clientes") -> dict[str, str]:
    return {fila["nombre"]: fila["saldo"] for fila in cuerpo[clave]["filas"]}


def _error(cliente_http: TestClient, headers: dict[str, str], url: str) -> tuple[int, str]:
    respuesta = cliente_http.get(url, headers=headers)
    return respuesta.status_code, respuesta.json().get("codigo", "")


# --- saldos de clientes -----------------------------------------------------------------------


def test_el_saldo_es_la_suma_de_los_movimientos_del_libro(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «El saldo es la suma de los movimientos»: venta 1500 y cobranza 500."""
    s = _limpia(sesion)
    cliente = sembrar_cliente_de_cartera(sesion, s, nombre="Kiosco Norte")
    mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", "1500.00")
    mover_cuenta(sesion, s, "CLIENTE", cliente, "COBRANZA", "500.00")

    cuerpo = _pedir(cliente_http, _lector(cliente_http, sesion, s))

    (fila,) = [f for f in cuerpo["clientes"]["filas"] if f["cliente_id"] == str(cliente)]
    assert fila["saldo"] == "1000.00"
    assert suma_del_libro(sesion, s, "CLIENTE", cliente) == 1000  # INV-13: libro = saldo


def test_deudores_a_favor_con_saldo_y_todos_con_sus_totales(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Deudores y saldo a favor»: 1000, -200 y una cuenta sin movimientos."""
    s = _limpia(sesion)
    deudor = sembrar_cliente_de_cartera(sesion, s, nombre="Deudor")
    a_favor = sembrar_cliente_de_cartera(sesion, s, nombre="A favor")
    sembrar_cliente_de_cartera(sesion, s, nombre="Sin movimientos")
    mover_cuenta(sesion, s, "CLIENTE", deudor, "VENTA", "1000.00")
    mover_cuenta(sesion, s, "CLIENTE", a_favor, "COBRANZA", "200.00")
    headers = _lector(cliente_http, sesion, s)

    con_saldo = _pedir(cliente_http, headers)  # CON_SALDO es el valor por defecto
    deudores = _pedir(cliente_http, headers, saldo="DEUDORES")
    a_favor_solo = _pedir(cliente_http, headers, saldo="A_FAVOR")
    todos = _pedir(cliente_http, headers, saldo="TODOS")

    assert _saldos(con_saldo) == {"Deudor": "1000.00", "A favor": "-200.00"}
    assert (con_saldo["total_adeudado"], con_saldo["total_a_favor"]) == ("1000.00", "-200.00")
    assert _saldos(deudores) == {"Deudor": "1000.00"}
    assert (deudores["total_adeudado"], deudores["total_a_favor"]) == ("1000.00", "0.00")
    assert _saldos(a_favor_solo) == {"A favor": "-200.00"}
    assert (a_favor_solo["total_adeudado"], a_favor_solo["total_a_favor"]) == (
        "0.00",
        "-200.00",
    )
    assert _saldos(todos)["Sin movimientos"] == "0.00"  # sin fila en `saldo_cuenta`: cero
    assert sum(1 for n in _saldos(todos) if n in {"Deudor", "A favor", "Sin movimientos"}) == 3


def test_los_totales_suman_solo_lo_filtrado_y_el_orden_es_por_saldo_descendente(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = _limpia(sesion)
    chico = sembrar_cliente_de_cartera(sesion, s, nombre="Chico")
    grande = sembrar_cliente_de_cartera(sesion, s, nombre="Grande")
    medio = sembrar_cliente_de_cartera(sesion, s, nombre="Medio", estado="SUSPENDIDO")
    favor = sembrar_cliente_de_cartera(sesion, s, nombre="Favor")
    for cliente, tipo, importe in [
        (chico, "VENTA", "100.50"),
        (grande, "VENTA", "900.25"),
        (medio, "VENTA", "300.00"),
        (favor, "COBRANZA", "40.00"),
    ]:
        mover_cuenta(sesion, s, "CLIENTE", cliente, tipo, importe)
    headers = _lector(cliente_http, sesion, s)

    todos = _pedir(cliente_http, headers)
    suspendidos = _pedir(cliente_http, headers, estado="SUSPENDIDO")

    assert [f["nombre"] for f in todos["clientes"]["filas"]] == [
        "Grande",
        "Medio",
        "Chico",
        "Favor",
    ]
    assert (todos["total_adeudado"], todos["total_a_favor"]) == ("1300.75", "-40.00")
    assert _saldos(suspendidos) == {"Medio": "300.00"}
    assert (suspendidos["total_adeudado"], suspendidos["total_a_favor"]) == ("300.00", "0.00")


def test_limite_y_disponible_con_y_sin_limite(cliente_http: TestClient, sesion: Session) -> None:
    """Escenario «Límite y disponible»: límite 5000 con saldo 1000, y otro sin límite."""
    s = _limpia(sesion)
    con_limite = sembrar_cliente_de_cartera(
        sesion, s, nombre="Con limite", limite_credito="5000.00"
    )
    sin_limite = sembrar_cliente_de_cartera(sesion, s, nombre="Sin limite")
    favor = sembrar_cliente_de_cartera(sesion, s, nombre="Favor", limite_credito="100.00")
    mover_cuenta(sesion, s, "CLIENTE", con_limite, "VENTA", "1000.00")
    mover_cuenta(sesion, s, "CLIENTE", sin_limite, "VENTA", "70.00")
    mover_cuenta(sesion, s, "CLIENTE", favor, "COBRANZA", "30.00")

    cuerpo = _pedir(cliente_http, _lector(cliente_http, sesion, s))

    por_nombre = {f["nombre"]: f for f in cuerpo["clientes"]["filas"]}
    assert (por_nombre["Con limite"]["limite_credito"], por_nombre["Con limite"]["disponible"]) == (
        "5000.00",
        "4000.00",
    )
    assert (por_nombre["Sin limite"]["limite_credito"], por_nombre["Sin limite"]["disponible"]) == (
        None,
        None,
    )
    assert por_nombre["Favor"]["disponible"] == "130.00"  # límite menos saldo (negativo)


def test_filtra_por_vendedor_asignado_y_muestra_su_nombre(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Filtro por vendedor asignado» (ADR-060)."""
    s = _limpia(sesion)
    vendedor_id = otro_usuario(sesion, s, f"ven{uuid4().hex[:6]}", frozenset({"VENDER"}))
    mio = sembrar_cliente_de_cartera(sesion, s, nombre="De vendedor", vendedor_id=vendedor_id)
    suelto = sembrar_cliente_de_cartera(sesion, s, nombre="Sin vendedor")
    mover_cuenta(sesion, s, "CLIENTE", mio, "VENTA", "10.00")
    mover_cuenta(sesion, s, "CLIENTE", suelto, "VENTA", "20.00")
    headers = _lector(cliente_http, sesion, s)

    todos = _pedir(cliente_http, headers)
    filtrado = _pedir(cliente_http, headers, vendedor_id=str(vendedor_id))

    por_nombre = {f["nombre"]: f for f in todos["clientes"]["filas"]}
    assert por_nombre["De vendedor"]["vendedor_id"] == str(vendedor_id)
    assert por_nombre["De vendedor"]["vendedor_nombre"] is not None
    assert por_nombre["Sin vendedor"]["vendedor_id"] is None
    assert por_nombre["Sin vendedor"]["vendedor_nombre"] is None
    assert _saldos(filtrado) == {"De vendedor": "10.00"}
    assert filtrado["total_adeudado"] == "10.00"


def test_busca_por_codigo_nombre_o_razon_social_y_los_comodines_son_literales(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = _limpia(sesion)
    uno = sembrar_cliente_de_cartera(sesion, s, nombre="Almacen Uno", codigo="C-001")
    dos = sembrar_cliente_de_cartera(
        sesion, s, nombre="Dos", codigo="C-002", razon_social="Distribuciones Sur SA"
    )
    tres = sembrar_cliente_de_cartera(sesion, s, nombre="100% Tres")
    for cliente in (uno, dos, tres):
        mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", "10.00")
    headers = _lector(cliente_http, sesion, s)

    assert set(_saldos(_pedir(cliente_http, headers, texto="c-001"))) == {"Almacen Uno"}
    assert set(_saldos(_pedir(cliente_http, headers, texto="almacen"))) == {"Almacen Uno"}
    assert set(_saldos(_pedir(cliente_http, headers, texto="sur sa"))) == {"Dos"}
    assert set(_saldos(_pedir(cliente_http, headers, texto="100%"))) == {"100% Tres"}
    assert _saldos(_pedir(cliente_http, headers, texto="%")) == {"100% Tres": "10.00"}


def test_un_valor_de_filtro_invalido_es_422(cliente_http: TestClient, sesion: Session) -> None:
    headers = _lector(cliente_http, sesion, _limpia(sesion))

    respuesta = cliente_http.get(URL_CLIENTES, params={"saldo": "MUCHO"}, headers=headers)

    assert respuesta.status_code == 422


def test_inv21_no_ve_saldos_de_clientes_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = _limpia(sesion)
    ajena = _limpia(sesion)
    mio = sembrar_cliente_de_cartera(sesion, propia, nombre="Propio")
    ajeno = sembrar_cliente_de_cartera(
        sesion, ajena, nombre="Ajeno", vendedor_id=ajena.entorno.usuario_id
    )
    mover_cuenta(sesion, propia, "CLIENTE", mio, "VENTA", "10.00")
    mover_cuenta(sesion, ajena, "CLIENTE", ajeno, "VENTA", "999.00")
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers)
    filtrado = _pedir(cliente_http, headers, vendedor_id=str(ajena.entorno.usuario_id))

    assert "Ajeno" not in _saldos(cuerpo)
    assert _saldos(cuerpo)["Propio"] == "10.00"
    assert cuerpo["total_adeudado"] == "10.00"
    assert filtrado["clientes"]["filas"] == []


def test_la_lista_de_vendedores_es_completa_y_no_depende_de_la_pagina_ni_del_filtro(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Vendedores del filtro»: los vendedores con clientes asignados, por nombre."""
    s = _limpia(sesion)
    primero = otro_usuario(sesion, s, f"zeta{uuid4().hex[:6]}", frozenset({"VENDER"}))
    segundo = otro_usuario(sesion, s, f"alfa{uuid4().hex[:6]}", frozenset({"VENDER"}))
    sin_clientes = otro_usuario(sesion, s, f"sin{uuid4().hex[:6]}", frozenset({"VENDER"}))
    # Los clientes del primero quedan al final del orden (saldo bajo): fuera de la página 1.
    for i in range(55):
        cliente = sembrar_cliente_de_cartera(sesion, s, nombre=f"A{i:03d}", vendedor_id=segundo)
        mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", f"{500 + i}.00")
    lejano = sembrar_cliente_de_cartera(sesion, s, nombre="Lejano", vendedor_id=primero)
    mover_cuenta(sesion, s, "CLIENTE", lejano, "VENTA", "1.00")
    headers = _lector(cliente_http, sesion, s)

    pagina_1 = _pedir(cliente_http, headers)
    filtrado = _pedir(
        cliente_http, headers, vendedor_id=str(segundo), saldo="DEUDORES", texto="A00"
    )

    assert "Lejano" not in _saldos(pagina_1)
    ids = [v["id"] for v in pagina_1["vendedores"]]
    nombres = [v["nombre"] for v in pagina_1["vendedores"]]
    assert ids == [str(segundo), str(primero)]
    assert nombres == sorted(nombres)
    assert str(sin_clientes) not in ids
    assert filtrado["vendedores"] == pagina_1["vendedores"]


def test_inv21_la_lista_de_vendedores_excluye_a_los_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = _limpia(sesion)
    ajena = _limpia(sesion)
    mio = otro_usuario(sesion, propia, f"mio{uuid4().hex[:6]}", frozenset({"VENDER"}))
    sembrar_cliente_de_cartera(sesion, propia, nombre="Propio", vendedor_id=mio)
    sembrar_cliente_de_cartera(sesion, ajena, nombre="Ajeno", vendedor_id=ajena.entorno.usuario_id)
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers)

    assert [v["id"] for v in cuerpo["vendedores"]] == [str(mio)]


# --- saldos de proveedores --------------------------------------------------------------------


def test_deuda_con_un_proveedor_es_la_suma_de_sus_movimientos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Deuda con un proveedor»: compra a crédito de 8000 y pago de 3000; lo pide
    `consulta` (CC-03)."""
    s = _limpia(sesion)
    proveedor = sembrar_proveedor_de_prueba(sesion, s, nombre="Bodega Sur")
    mover_cuenta(sesion, s, "PROVEEDOR", proveedor, "COMPRA", "8000.00")
    mover_cuenta(sesion, s, "PROVEEDOR", proveedor, "PAGO", "3000.00")
    headers = usuario_con(cliente_http, sesion, s, PLANTILLAS_DE_ROL[CONSULTA_DIRECCION])

    cuerpo = _pedir(cliente_http, headers, URL_PROVEEDORES)

    (fila,) = [f for f in cuerpo["proveedores"]["filas"] if f["proveedor_id"] == str(proveedor)]
    assert (fila["nombre"], fila["estado"], fila["saldo"]) == ("Bodega Sur", "ACTIVO", "5000.00")
    assert suma_del_libro(sesion, s, "PROVEEDOR", proveedor) == 5000
    assert (cuerpo["total_adeudado"], cuerpo["total_a_favor"]) == ("5000.00", "0.00")


def test_proveedores_filtra_por_saldo_estado_y_nombre_con_totales_y_orden(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = _limpia(sesion)
    deudor = sembrar_proveedor_de_prueba(sesion, s, nombre="Deudor SA")
    a_favor = sembrar_proveedor_de_prueba(sesion, s, nombre="Anticipo SRL")
    baja = sembrar_proveedor_de_prueba(sesion, s, nombre="Baja SA", activo=False)
    sembrar_proveedor_de_prueba(sesion, s, nombre="Sin movimientos")
    mover_cuenta(sesion, s, "PROVEEDOR", deudor, "COMPRA", "700.00")
    mover_cuenta(sesion, s, "PROVEEDOR", a_favor, "PAGO", "150.00")
    mover_cuenta(sesion, s, "PROVEEDOR", baja, "COMPRA", "50.00")
    headers = usuario_con(cliente_http, sesion, s, PLANTILLAS_DE_ROL[ADMINISTRACION])

    por_defecto = _pedir(cliente_http, headers, URL_PROVEEDORES)
    inactivos = _pedir(cliente_http, headers, URL_PROVEEDORES, estado="INACTIVO")
    por_nombre = _pedir(cliente_http, headers, URL_PROVEEDORES, texto="anticipo")
    todos = _pedir(cliente_http, headers, URL_PROVEEDORES, saldo="TODOS")
    a_favor_solo = _pedir(cliente_http, headers, URL_PROVEEDORES, saldo="A_FAVOR")

    assert [f["nombre"] for f in por_defecto["proveedores"]["filas"]] == [
        "Deudor SA",
        "Baja SA",
        "Anticipo SRL",
    ]
    assert (por_defecto["total_adeudado"], por_defecto["total_a_favor"]) == ("750.00", "-150.00")
    assert _saldos(inactivos, "proveedores") == {"Baja SA": "50.00"}
    assert inactivos["proveedores"]["filas"][0]["estado"] == "INACTIVO"
    assert _saldos(por_nombre, "proveedores") == {"Anticipo SRL": "-150.00"}
    assert _saldos(todos, "proveedores")["Sin movimientos"] == "0.00"
    assert _saldos(a_favor_solo, "proveedores") == {"Anticipo SRL": "-150.00"}


def test_inv21_no_ve_saldos_de_proveedores_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = _limpia(sesion)
    ajena = _limpia(sesion)
    mio = sembrar_proveedor_de_prueba(sesion, propia, nombre="Propio SA")
    ajeno = sembrar_proveedor_de_prueba(sesion, ajena, nombre="Ajeno SA")
    mover_cuenta(sesion, propia, "PROVEEDOR", mio, "COMPRA", "10.00")
    mover_cuenta(sesion, ajena, "PROVEEDOR", ajeno, "COMPRA", "999.00")
    headers = usuario_con(cliente_http, sesion, propia, PLANTILLAS_DE_ROL[CONSULTA_DIRECCION])

    cuerpo = _pedir(cliente_http, headers, URL_PROVEEDORES)

    assert _saldos(cuerpo, "proveedores") == {"Propio SA": "10.00"}
    assert cuerpo["total_adeudado"] == "10.00"


# --- permisos (D8 = B) ------------------------------------------------------------------------


def test_supervisor_con_la_plantilla_actual_ve_clientes_y_no_proveedores(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Supervisor con la plantilla actual» (`sup01`): clientes 200, proveedores 403."""
    s = _limpia(sesion)
    permisos = PLANTILLAS_DE_ROL[SUPERVISOR_COMERCIAL]
    assert "VER_REPORTES" in permisos
    assert not permisos & {"GESTIONAR_PROVEEDORES", "REGISTRAR_PAGO_PROVEEDOR", "VER_UTILIDAD"}
    headers = usuario_con(cliente_http, sesion, s, permisos)

    assert cliente_http.get(URL_CLIENTES, headers=headers).status_code == 200
    assert _error(cliente_http, headers, URL_PROVEEDORES) == (403, "PERMISO_REQUERIDO")


def test_consulta_direccion_entra_a_proveedores_por_ver_utilidad(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Consulta/Dirección entra por `VER_UTILIDAD`»."""
    s = _limpia(sesion)
    permisos = PLANTILLAS_DE_ROL[CONSULTA_DIRECCION]
    assert not permisos & {"GESTIONAR_PROVEEDORES", "REGISTRAR_PAGO_PROVEEDOR"}
    headers = usuario_con(cliente_http, sesion, s, permisos)

    assert cliente_http.get(URL_PROVEEDORES, headers=headers).status_code == 200
    assert cliente_http.get(URL_CLIENTES, headers=headers).status_code == 200


def test_solo_ver_reportes_no_alcanza_para_proveedores_y_cada_permiso_extra_si(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Solo `VER_REPORTES` no alcanza»; `ges01` (Administración) entra."""
    s = _limpia(sesion)
    solo = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)
    assert _error(cliente_http, solo, URL_PROVEEDORES) == (403, "PERMISO_REQUERIDO")

    for extra in ("REGISTRAR_PAGO_PROVEEDOR", "GESTIONAR_PROVEEDORES", "VER_UTILIDAD"):
        headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES | {extra})
        assert cliente_http.get(URL_PROVEEDORES, headers=headers).status_code == 200, extra

    ges = usuario_con(cliente_http, sesion, s, PLANTILLAS_DE_ROL[ADMINISTRACION])
    assert cliente_http.get(URL_PROVEEDORES, headers=ges).status_code == 200


@pytest.mark.parametrize(
    "permisos",
    [
        frozenset({"VER_UTILIDAD"}),
        frozenset({"GESTIONAR_PROVEEDORES"}),
        frozenset({"REGISTRAR_PAGO_PROVEEDOR", "GESTIONAR_CLIENTES"}),
    ],
)
def test_sin_ver_reportes_ninguna_ruta_de_saldos_responde(
    cliente_http: TestClient, sesion: Session, permisos: frozenset[str]
) -> None:
    """Los tres permisos de proveedores sin `VER_REPORTES` tampoco alcanzan (la regla es «y»)."""
    headers = usuario_con(cliente_http, sesion, _limpia(sesion), permisos)

    assert _error(cliente_http, headers, URL_PROVEEDORES) == (403, "PERMISO_REQUERIDO")
    assert _error(cliente_http, headers, URL_CLIENTES) == (403, "PERMISO_REQUERIDO")


def test_sin_token_los_saldos_responden_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL_CLIENTES).status_code == 401
    assert cliente_http.get(URL_PROVEEDORES).status_code == 401
