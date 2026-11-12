"""Tarea 21.3 (change 26, `design.md` D7, D14; specs `reportes/rendicion-por-vendedor`, «La jornada
más reciente primero, en páginas»; `reportes/area-de-reportes`, «Las páginas no repiten ni pierden
filas»): `GET /api/v1/reportes/rendiciones?pagina=` trae `jornadas` en un sobre de 50 filas por
`abierta_en` descendente (desempate `jornada.id` descendente); `por_vendedor` sigue completo.

PostgreSQL real y login real. Reglas citadas: RUT-07, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    LineaDePrueba,
    crear_vendedor,
    dia,
    sembrar_jornada,
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

URL = "/api/v1/reportes/rendiciones"
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}
JORNADAS = 52


def _pedir(
    cliente_http: TestClient, headers: dict[str, str], **filtros: str | int
) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, params={**NOVIEMBRE, **filtros}, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _sembrar(sesion: Session, s: Sesion) -> str:
    """52 jornadas cerradas de Juan; las dos últimas abren en el mismo instante. La más vieja trae
    una venta sin conexión (queda en la página 2). Devuelve el id de esa jornada más vieja."""
    juan = crear_vendedor(sesion, s, "Juan")
    primera = dia(11, 1, hora=6)
    ids: list[str] = []
    for i in range(JORNADAS):
        minutos = i if i < JORNADAS - 1 else JORNADAS - 2
        ids.append(
            str(
                sembrar_jornada(
                    sesion,
                    s,
                    vendedor=juan,
                    estado="CERRADA",
                    abierta_en=primera + timedelta(minutes=10 * minutos),
                )
            )
        )
    sembrar_venta(
        sesion,
        s,
        vendedor_id=juan.usuario_id,
        occurred_at=primera + timedelta(minutes=5),
        lineas=[LineaDePrueba(neto="700.00")],
        modo_confirmacion="OFFLINE",
        jornada_id=ids[0],  # type: ignore[arg-type]
    )
    return ids[0]


def test_las_jornadas_van_en_paginas_de_cincuenta_con_la_mas_reciente_primero(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenarios «La jornada más reciente primero, en páginas» y «Las páginas no repiten ni
    pierden filas»."""
    s = Sesion(sesion)
    _sembrar(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    primera = _pedir(cliente_http, headers)["jornadas"]
    segunda = _pedir(cliente_http, headers, pagina=2)["jornadas"]

    assert {k: primera[k] for k in ("pagina", "tamano", "total_filas", "paginas")} == {
        "pagina": 1,
        "tamano": 50,
        "total_filas": JORNADAS,
        "paginas": 2,
    }
    assert (len(primera["filas"]), len(segunda["filas"])) == (50, 2)
    filas = primera["filas"] + segunda["filas"]
    assert len({f["jornada_id"] for f in filas}) == JORNADAS
    clave = [(f["abierta_en"], f["jornada_id"]) for f in filas]
    assert clave == sorted(clave, reverse=True)  # abierta_en desc, desempate por id desc


def test_el_dinero_de_la_jornada_de_otra_pagina_y_los_totales_por_vendedor_son_completos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    mas_vieja = _sembrar(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    primera = _pedir(cliente_http, headers)
    segunda = _pedir(cliente_http, headers, pagina=2)

    (vieja,) = [f for f in segunda["jornadas"]["filas"] if f["jornada_id"] == mas_vieja]
    assert vieja["ventas"] == {"cantidad": 1, "total": "700.00"}
    assert all(f["ventas"]["cantidad"] == 0 for f in primera["jornadas"]["filas"])
    for pagina in (primera, segunda):  # por_vendedor sin paginar, sobre todas las jornadas
        (juan,) = pagina["por_vendedor"]
        assert (juan["jornadas"], juan["ventas"]) == (
            JORNADAS,
            {"cantidad": 1, "total": "700.00"},
        )


def test_una_pagina_cero_es_422_y_una_posterior_a_la_ultima_trae_filas_vacias(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sembrar_jornada(sesion, s, vendedor=crear_vendedor(sesion, s, "Ana"), estado="CERRADA")
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    cero = cliente_http.get(URL, params={**NOVIEMBRE, "pagina": 0}, headers=headers)
    lejos = _pedir(cliente_http, headers, pagina=5)

    assert cero.status_code == 422
    assert lejos["jornadas"] == {
        "filas": [],
        "pagina": 5,
        "tamano": 50,
        "total_filas": 1,
        "paginas": 1,
    }
    assert len(lejos["por_vendedor"]) == 1


def test_inv21_las_paginas_no_cuentan_jornadas_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_jornada(
        sesion, propia, vendedor=crear_vendedor(sesion, propia, "Mia"), estado="CERRADA"
    )
    for nombre in ("Uno", "Dos", "Tres"):
        sembrar_jornada(
            sesion, ajena, vendedor=crear_vendedor(sesion, ajena, nombre), estado="CERRADA"
        )
    headers = usuario_con(cliente_http, sesion, propia, ABRIR_REPORTES)

    jornadas = _pedir(cliente_http, headers)["jornadas"]

    assert (jornadas["total_filas"], len(jornadas["filas"])) == (1, 1)
