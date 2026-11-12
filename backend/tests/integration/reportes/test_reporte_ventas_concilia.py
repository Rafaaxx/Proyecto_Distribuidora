"""Tarea 15.1 (change 26, spec `reportes/ventas-por-periodo`, escenario «Concilia con las ventas
registradas»; cita REP-01, `00` §9 criterio 11): el reporte de ventas del período y el listado de
ventas confirmadas (`GET /api/v1/ventas?estado=CONFIRMADA&desde=…&hasta=…`, recorriendo todas sus
páginas) dan la misma cantidad y el mismo total.

PostgreSQL real y login real. Las ventas se siembran por SQL; hay una anulada, una de otro mes y
una de otro vendedor para que el filtro de estado y el de período importen. El listado se pagina
de a 2 para recorrer varias páginas.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from reportes_utiles import (
    URL_VENTAS,
    LineaDePrueba,
    anular_venta,
    crear_vendedor,
    dia,
    fijar_reloj,
    sembrar_venta,
)
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL_LISTADO = "/api/v1/ventas"
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}
# Quien lee los dos reportes: el de ventas pide `VER_REPORTES` y el listado, `VENDER`.
LECTOR = frozenset({"VER_REPORTES", "VENDER"})


def _listado_completo(cliente_http: TestClient, headers: dict[str, str]) -> list[dict[str, str]]:
    """Todas las ventas confirmadas del período, página por página."""
    items: list[dict[str, str]] = []
    cursor: str | None = None
    while True:
        params = {"estado": "CONFIRMADA", "limite": "2", **NOVIEMBRE}
        if cursor is not None:
            params["cursor"] = cursor
        respuesta = cliente_http.get(URL_LISTADO, params=params, headers=headers)
        assert respuesta.status_code == 200, respuesta.text
        pagina = respuesta.json()
        items.extend(pagina["items"])
        cursor = pagina["cursor_siguiente"]
        if cursor is None:
            return items


def test_rep01_el_reporte_concilia_con_el_listado_de_ventas_confirmadas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Concilia con las ventas registradas»."""
    s = Sesion(sesion)
    otro = crear_vendedor(sesion, s, "Ana")
    sembrar_venta(sesion, s, occurred_at=dia(11, 2), lineas=[LineaDePrueba(neto="1000.00")])
    sembrar_venta(
        sesion,
        s,
        occurred_at=dia(11, 9),
        lineas=[LineaDePrueba(neto="250.50"), LineaDePrueba(neto="300.25", costo_total=None)],
        iva="63.00",
    )
    sembrar_venta(
        sesion,
        s,
        vendedor_id=otro.usuario_id,
        occurred_at=dia(11, 15),
        lineas=[LineaDePrueba(neto="480.00")],
        modo_confirmacion="OFFLINE",
    )
    sembrar_venta(sesion, s, occurred_at=dia(11, 30, 22), lineas=[LineaDePrueba(neto="75.10")])
    sembrar_venta(sesion, s, occurred_at=dia(10, 31, 22), lineas=[LineaDePrueba(neto="9999.00")])
    anulada = sembrar_venta(
        sesion, s, occurred_at=dia(11, 12), lineas=[LineaDePrueba(neto="5000.00")]
    )
    anular_venta(sesion, s, anulada.venta_id, anulada_en=dia(11, 13))
    headers = usuario_con(cliente_http, sesion, s, LECTOR)
    fijar_reloj(cliente_http, dia(12, 1))

    reporte = cliente_http.get(URL_VENTAS, params=NOVIEMBRE, headers=headers)
    assert reporte.status_code == 200, reporte.text
    resumen = reporte.json()["resumen"]
    listado = _listado_completo(cliente_http, headers)

    assert len(listado) > 2, "el listado tuvo que recorrer más de una página"
    assert resumen["cantidad_ventas"] == len(listado) == 4
    assert Decimal(resumen["total"]) == sum((Decimal(v["total"]) for v in listado), Decimal(0))
    assert resumen["total"] == "2168.85"
