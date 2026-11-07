"""Tarea 21.4 (change 26, `design.md` D8, D14; specs `reportes/saldos-de-cuentas`, «Saldos de
clientes» y «Saldos de proveedores»; `reportes/area-de-reportes`, «Más de una página» y «Las páginas
no repiten ni pierden filas»): `GET /api/v1/reportes/saldos/clientes?pagina=` y
`/proveedores?pagina=` traen `clientes` / `proveedores` en un sobre de 50 filas por saldo
descendente (desempate por nombre e id); los totales son los de todo lo filtrado.

PostgreSQL real y login real. Reglas citadas: CC-04, INV-13, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    cuentas_del_entorno_en_cero,
    mover_cuenta,
    sembrar_cliente_de_cartera,
    sembrar_proveedor_de_prueba,
)
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    PLANTILLAS_DE_ROL,
    SUPERVISOR_COMERCIAL,
)

URL_CLIENTES = "/api/v1/reportes/saldos/clientes"
URL_PROVEEDORES = "/api/v1/reportes/saldos/proveedores"
CLIENTES = 120


def _pedir(
    cliente_http: TestClient, headers: dict[str, str], url: str, **filtros: str | int
) -> dict[str, Any]:
    respuesta = cliente_http.get(url, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _sembrar_clientes(sesion: Session, s: Sesion) -> Decimal:
    """120 clientes con saldos 101 a 218 y dos iguales de 100 (para el desempate por nombre);
    devuelve la suma de todos los saldos."""
    total = Decimal(0)
    for i in range(CLIENTES):
        igual = i >= CLIENTES - 2
        nombre = f"Igual {'AB'[i - (CLIENTES - 2)]}" if igual else f"Cliente {i:03d}"
        importe = Decimal(100) if igual else Decimal(101 + i)
        cliente = sembrar_cliente_de_cartera(sesion, s, nombre=nombre)
        mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", f"{importe}.00")
        total += importe
    return total


def test_los_clientes_se_paginan_de_a_cincuenta_con_totales_de_todo_lo_filtrado(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenarios «Más de una página» y «Las páginas no repiten ni pierden filas»."""
    s = cuentas_del_entorno_en_cero(sesion, Sesion(sesion))
    total = _sembrar_clientes(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    paginas = [_pedir(cliente_http, headers, URL_CLIENTES, pagina=n) for n in (1, 2, 3)]

    assert [len(p["clientes"]["filas"]) for p in paginas] == [50, 50, 20]
    assert {
        k: paginas[2]["clientes"][k] for k in ("pagina", "tamano", "total_filas", "paginas")
    } == {
        "pagina": 3,
        "tamano": 50,
        "total_filas": CLIENTES,
        "paginas": 3,
    }
    filas = [f for p in paginas for f in p["clientes"]["filas"]]
    assert len({f["cliente_id"] for f in filas}) == CLIENTES
    saldos = [Decimal(f["saldo"]) for f in filas]
    assert saldos == sorted(saldos, reverse=True)
    assert [f["nombre"] for f in filas[-2:]] == ["Igual A", "Igual B"]  # desempate por nombre
    for pagina in paginas:  # los totales no dependen de la página
        assert pagina["total_adeudado"] == f"{total}.00"
        assert pagina["total_a_favor"] == "0.00"


def test_una_pagina_cero_es_422_y_una_posterior_a_la_ultima_trae_filas_vacias(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = cuentas_del_entorno_en_cero(sesion, Sesion(sesion))
    cliente = sembrar_cliente_de_cartera(sesion, s, nombre="Unico")
    mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", "10.00")
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    assert cliente_http.get(URL_CLIENTES, params={"pagina": 0}, headers=headers).status_code == 422
    lejos = _pedir(cliente_http, headers, URL_CLIENTES, pagina=7)

    assert lejos["clientes"]["filas"] == []
    assert (lejos["clientes"]["total_filas"], lejos["clientes"]["paginas"]) == (1, 1)
    assert lejos["total_adeudado"] == "10.00"


def test_los_proveedores_se_paginan_y_supervisor_sigue_sin_verlos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = cuentas_del_entorno_en_cero(sesion, Sesion(sesion))
    for i in range(52):
        proveedor = sembrar_proveedor_de_prueba(sesion, s, nombre=f"Proveedor {i:02d}")
        mover_cuenta(sesion, s, "PROVEEDOR", proveedor, "COMPRA", f"{100 + i}.00")
    headers = usuario_con(cliente_http, sesion, s, PLANTILLAS_DE_ROL[ADMINISTRACION])

    primera = _pedir(cliente_http, headers, URL_PROVEEDORES)
    segunda = _pedir(cliente_http, headers, URL_PROVEEDORES, pagina=2)

    assert (len(primera["proveedores"]["filas"]), len(segunda["proveedores"]["filas"])) == (50, 2)
    assert (primera["proveedores"]["total_filas"], primera["proveedores"]["paginas"]) == (52, 2)
    filas = primera["proveedores"]["filas"] + segunda["proveedores"]["filas"]
    assert len({f["proveedor_id"] for f in filas}) == 52
    saldos = [Decimal(f["saldo"]) for f in filas]
    assert saldos == sorted(saldos, reverse=True)
    assert primera["total_adeudado"] == segunda["total_adeudado"] == "6526.00"  # 52 x 100 + 1326
    supervisor = usuario_con(cliente_http, sesion, s, PLANTILLAS_DE_ROL[SUPERVISOR_COMERCIAL])
    assert cliente_http.get(URL_PROVEEDORES, headers=supervisor).status_code == 403


def test_inv21_los_conteos_de_saldos_no_incluyen_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = cuentas_del_entorno_en_cero(sesion, Sesion(sesion))
    ajena = cuentas_del_entorno_en_cero(sesion, Sesion(sesion))
    mio = sembrar_cliente_de_cartera(sesion, propia, nombre="Mio")
    mover_cuenta(sesion, propia, "CLIENTE", mio, "VENTA", "10.00")
    for i in range(3):
        otro = sembrar_cliente_de_cartera(sesion, ajena, nombre=f"Ajeno {i}")
        mover_cuenta(sesion, ajena, "CLIENTE", otro, "VENTA", "99.00")
    headers = usuario_con(cliente_http, sesion, propia, ABRIR_REPORTES)

    cuerpo = _pedir(cliente_http, headers, URL_CLIENTES)

    assert cuerpo["clientes"]["total_filas"] == 1
    assert cuerpo["total_adeudado"] == "10.00"
