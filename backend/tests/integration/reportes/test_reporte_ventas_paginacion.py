"""Tarea 21.2 (change 26, `design.md` D14; specs `reportes/area-de-reportes`, escenarios
«Cada lista del reporte de ventas se pagina por su lado» y «Página fuera de rango»;
`reportes/ventas-por-periodo`, «Por día, el más reciente primero» y «Anuladas en páginas, la más
reciente primero»): las tres listas largas de `GET /api/v1/reportes/ventas` viajan en un sobre de
50 filas, cada una por su lado.

PostgreSQL real y login real. Se siembran 52 días con 52 productos distintos (una venta por día) y
52 ventas anuladas aparte; cuatro de ellas en el mismo instante para el desempate por `venta.id`.

Reglas citadas: REP-01, REP-02, INV-03, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    URL_VENTAS,
    LineaDePrueba,
    anular_venta,
    dia,
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

PERIODO = {"desde": "2026-09-01", "hasta": "2026-12-31"}
DIAS = 52


def _pedir(
    cliente_http: TestClient, headers: dict[str, str], **filtros: str | int
) -> dict[str, Any]:
    respuesta = cliente_http.get(URL_VENTAS, params={**PERIODO, **filtros}, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _sembrar_confirmadas(sesion: Session, s: Sesion) -> None:
    """Una venta por día durante 52 días, cada una de un producto distinto."""
    for i in range(DIAS):
        sembrar_venta(
            sesion,
            s,
            occurred_at=dia(9, 1) + timedelta(days=i),
            lineas=[LineaDePrueba(neto=f"{100 + i}.00", producto="otro")],
        )


def _sembrar_anuladas(sesion: Session, s: Sesion) -> None:
    """52 anuladas: las 48 primeras en días distintos y las 4 últimas en el mismo instante."""
    for i in range(DIAS):
        momento = dia(9, 1) + timedelta(days=i if i < DIAS - 4 else DIAS - 4)
        venta = sembrar_venta(
            sesion, s, occurred_at=momento, lineas=[LineaDePrueba(neto="10.00", producto="otro")]
        )
        anular_venta(sesion, s, venta.venta_id, anulada_en=momento + timedelta(days=1))


def test_por_dia_trae_cincuenta_filas_con_el_sobre_y_la_fecha_mas_reciente_primero(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenarios «Por día, el más reciente primero» y «Cada lista se pagina por su lado»."""
    s = Sesion(sesion)
    _sembrar_confirmadas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    primera = _pedir(cliente_http, headers)["por_dia"]
    segunda = _pedir(cliente_http, headers, pagina_por_dia=2)["por_dia"]

    assert {k: primera[k] for k in ("pagina", "tamano", "total_filas", "paginas")} == {
        "pagina": 1,
        "tamano": 50,
        "total_filas": 52,
        "paginas": 2,
    }
    assert (segunda["pagina"], segunda["total_filas"], segunda["paginas"]) == (2, 52, 2)
    fechas = [f["fecha"] for f in primera["filas"] + segunda["filas"]]
    assert (len(primera["filas"]), len(segunda["filas"])) == (50, 2)
    assert fechas == sorted(fechas, reverse=True)
    assert len(set(fechas)) == DIAS  # sin repetir ni perder


def test_por_producto_pagina_sin_repetir_ni_perder_y_trae_el_detalle_de_la_pagina(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    _sembrar_confirmadas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    primera = _pedir(cliente_http, headers)["por_producto"]
    segunda = _pedir(cliente_http, headers, pagina_por_producto=2)["por_producto"]

    assert (len(primera["filas"]), len(segunda["filas"])) == (50, 2)
    assert (primera["total_filas"], primera["paginas"]) == (52, 2)
    filas = primera["filas"] + segunda["filas"]
    assert len({f["producto_id"] for f in filas}) == DIAS
    netos = [float(f["importe_neto"]) for f in filas]
    assert netos == sorted(netos, reverse=True)
    assert all(len(f["presentaciones"]) == 1 for f in filas)  # el detalle viaja en cada fila


def test_las_anuladas_se_paginan_con_la_mas_reciente_primero_y_desempate_por_id(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Anuladas en páginas, la más reciente primero»."""
    s = Sesion(sesion)
    _sembrar_anuladas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    primera = _pedir(cliente_http, headers)["anuladas"]
    segunda = _pedir(cliente_http, headers, pagina_anuladas=2)["anuladas"]

    assert (primera["cantidad"], primera["total"]) == (52, "520.00")
    assert (segunda["cantidad"], segunda["total"]) == (52, "520.00")
    assert (primera["ventas"]["total_filas"], primera["ventas"]["paginas"]) == (52, 2)
    filas = primera["ventas"]["filas"] + segunda["ventas"]["filas"]
    assert (len(primera["ventas"]["filas"]), len(segunda["ventas"]["filas"])) == (50, 2)
    clave = [(f["occurred_at"], f["venta_id"]) for f in filas]
    assert clave == sorted(clave, reverse=True)
    assert len({f["venta_id"] for f in filas}) == DIAS


def test_cada_lista_se_pagina_por_su_lado(cliente_http: TestClient, sesion: Session) -> None:
    """Pedir la página 2 de una lista no mueve las otras."""
    s = Sesion(sesion)
    _sembrar_confirmadas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    base = _pedir(cliente_http, headers)
    solo_dia = _pedir(cliente_http, headers, pagina_por_dia=2)

    assert solo_dia["por_dia"]["pagina"] == 2
    assert solo_dia["por_producto"] == base["por_producto"]
    assert solo_dia["anuladas"] == base["anuladas"]


def test_los_totales_no_dependen_de_la_pagina(cliente_http: TestClient, sesion: Session) -> None:
    """Resumen, «Por vendedor», líneas sin costo y anuladas son los de todo el período."""
    s = Sesion(sesion)
    _sembrar_confirmadas(sesion, s)
    _sembrar_anuladas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES | {"VER_UTILIDAD"})

    base = _pedir(cliente_http, headers)
    lejos = _pedir(
        cliente_http, headers, pagina_por_dia=2, pagina_por_producto=2, pagina_anuladas=2
    )

    assert base["resumen"]["cantidad_ventas"] == DIAS
    assert base["resumen"]["importe_neto"] == "6526.00"  # 52 x 100 + (0 + 1 + ... + 51)
    for clave in ("resumen", "por_vendedor"):
        assert lejos[clave] == base[clave]
    assert (lejos["anuladas"]["cantidad"], lejos["anuladas"]["total"]) == (52, "520.00")


@pytest.mark.parametrize("lista", ["pagina_por_dia", "pagina_por_producto", "pagina_anuladas"])
def test_una_pagina_cero_es_un_error_de_validacion(
    cliente_http: TestClient, sesion: Session, lista: str
) -> None:
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    respuesta = cliente_http.get(URL_VENTAS, params={**PERIODO, lista: 0}, headers=headers)

    assert respuesta.status_code == 422


def test_una_pagina_fuera_de_rango_trae_filas_vacias_con_los_totales_reales(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Página fuera de rango»: no es error."""
    s = Sesion(sesion)
    _sembrar_confirmadas(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    cuerpo = _pedir(cliente_http, headers, pagina_por_dia=9, pagina_por_producto=7)

    assert cuerpo["por_dia"] == {
        "filas": [],
        "pagina": 9,
        "tamano": 50,
        "total_filas": 52,
        "paginas": 2,
    }
    assert cuerpo["por_producto"]["filas"] == []
    assert cuerpo["por_producto"]["total_filas"] == 52


def test_inv21_las_filas_y_los_conteos_no_incluyen_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_venta(sesion, propia, lineas=[LineaDePrueba(neto="100.00", producto="otro")])
    for i in range(3):
        venta = sembrar_venta(
            sesion, ajena, occurred_at=dia(11, 3 + i), lineas=[LineaDePrueba(producto="otro")]
        )
        anular_venta(sesion, ajena, venta.venta_id, anulada_en=dia(11, 20))
    headers = usuario_con(cliente_http, sesion, propia, ABRIR_REPORTES)

    cuerpo = _pedir(cliente_http, headers)

    assert (cuerpo["por_dia"]["total_filas"], cuerpo["por_producto"]["total_filas"]) == (1, 1)
    assert cuerpo["anuladas"]["ventas"]["total_filas"] == 0
    assert cuerpo["anuladas"]["cantidad"] == 0
