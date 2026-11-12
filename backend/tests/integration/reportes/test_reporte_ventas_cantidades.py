"""Tarea 3.3 (change 26, spec `reportes/ventas-por-periodo`, requisito «Las cantidades se informan
en cajas equivalentes, unidades base y por presentación»; `design.md` D3, D4): el desglose por
producto de `GET /api/v1/reportes/ventas`.

Las cajas equivalentes de cada línea salen de su `cantidad_base` y de las `unidades_referencia`
congeladas; se suman exactas en la base y se redondean una sola vez a 2 decimales.

Reglas citadas: REP-03, REP-05, TR-03, PRC-23, VTA-02, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from typing import Any

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
from ventas_lecturas_utiles import otro_usuario, usuario_con

NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}


def _botellas(cantidad: int, *, referencia: int = 6, neto: str = "100.00") -> LineaDePrueba:
    """Botellas sueltas del vino (presentación de 1 unidad) con la referencia congelada dada."""
    return LineaDePrueba(
        neto=neto,
        costo_total=None,
        presentacion="botella",
        unidades_presentacion=1,
        cantidad_base=cantidad,
        unidades_referencia=referencia,
    )


def _cajas(cantidad: int, *, neto: str = "100.00") -> LineaDePrueba:
    """Cajas x6 del vino: `cantidad` cajas, `6 x cantidad` unidades base."""
    return LineaDePrueba(
        neto=neto,
        costo_total=None,
        presentacion="caja",
        unidades_presentacion=6,
        cantidad_base=6 * cantidad,
        unidades_referencia=6,
    )


def _por_producto(
    cliente_http: TestClient, sesion: Session, s: Sesion, **filtros: str
) -> list[dict[str, Any]]:
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)
    respuesta = cliente_http.get(URL_VENTAS, params={**NOVIEMBRE, **filtros}, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["por_producto"]["filas"]  # type: ignore[no-any-return]


def test_15_botellas_de_un_vino_x6_son_2_con_50_cajas_equivalentes(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Cajas equivalentes del glosario»."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[_botellas(15)])

    (producto,) = _por_producto(cliente_http, sesion, s)

    assert producto["producto_id"] == str(s.entorno.vino_id)
    assert producto["nombre"] == "Vino A"
    assert producto["codigo"]
    assert producto["cajas_equivalentes"] == "2.50"
    assert producto["unidades_base"] == 15
    assert producto["importe_neto"] == "100.00"


def test_el_detalle_por_presentacion_separa_cajas_y_botellas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Detalle por presentación»: 2 cajas x6 y 3 botellas del mismo vino."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[_cajas(2), _botellas(3)])

    (producto,) = _por_producto(cliente_http, sesion, s)

    assert producto["unidades_base"] == 15
    assert producto["cajas_equivalentes"] == "2.50"
    assert [
        (d["nombre"], d["unidades_presentacion"], d["cantidad"], d["unidades_base"])
        for d in producto["presentaciones"]
    ] == [("Caja x6", 6, 2, 12), ("Botella", 1, 3, 3)]
    assert producto["presentaciones"][0]["presentacion_id"] == str(s.entorno.caja_id)


def test_el_detalle_suma_la_misma_presentacion_de_varias_ventas(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[_cajas(1)])
    sembrar_venta(sesion, s, lineas=[_cajas(4)])

    (producto,) = _por_producto(cliente_http, sesion, s)

    (detalle,) = producto["presentaciones"]
    assert (detalle["cantidad"], detalle["unidades_base"]) == (5, 30)
    assert producto["cajas_equivalentes"] == "5.00"


def test_la_referencia_congelada_de_cada_linea_manda_aunque_cambie_despues(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «La referencia cambió entre ventas»: 6 botellas con x6 y 6 con x12."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(11, 2), lineas=[_botellas(6, referencia=6)])
    sembrar_venta(sesion, s, occurred_at=dia(11, 3), lineas=[_botellas(6, referencia=12)])

    (producto,) = _por_producto(cliente_http, sesion, s)

    assert producto["cajas_equivalentes"] == "1.50"
    assert producto["unidades_base"] == 12


def test_el_redondeo_se_hace_una_sola_vez_sobre_la_suma_exacta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Redondeo una sola vez»: tres ventas de 1 botella con referencia x6."""
    s = Sesion(sesion)
    for dia_ in (2, 3, 4):
        sembrar_venta(sesion, s, occurred_at=dia(11, dia_), lineas=[_botellas(1)])
    headers = usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)

    cuerpo = cliente_http.get(URL_VENTAS, params=NOVIEMBRE, headers=headers).json()

    assert cuerpo["por_producto"]["filas"][0]["cajas_equivalentes"] == "0.50"
    assert cuerpo["resumen"]["cajas_equivalentes"] == "0.50"
    assert [f["cajas_equivalentes"] for f in cuerpo["por_dia"]["filas"]] == [
        "0.17",
        "0.17",
        "0.17",
    ]


def test_el_desglose_por_producto_no_trae_costo_ni_utilidad(
    cliente_http: TestClient, sesion: Session
) -> None:
    """REP-06 es de la etapa 2: ni siquiera con permiso de utilidad."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="1000.00", costo_total="700.00")])
    headers = usuario_con(cliente_http, sesion, s, frozenset({"VER_REPORTES", "VER_UTILIDAD"}))

    producto = cliente_http.get(URL_VENTAS, params=NOVIEMBRE, headers=headers).json()[
        "por_producto"
    ]["filas"][0]

    assert set(producto) == {
        "producto_id",
        "codigo",
        "nombre",
        "cajas_equivalentes",
        "unidades_base",
        "importe_neto",
        "presentaciones",
    }
    assert set(producto["presentaciones"][0]) == {
        "presentacion_id",
        "nombre",
        "unidades_presentacion",
        "cantidad",
        "unidades_base",
    }


def test_los_productos_van_por_neto_descendente(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    sembrar_venta(
        sesion,
        s,
        lineas=[_cajas(1, neto="100.00"), LineaDePrueba(neto="900.00", producto="otro")],
    )

    productos = _por_producto(cliente_http, sesion, s)

    assert [(p["nombre"], p["importe_neto"]) for p in productos] == [
        ("Gaseosa", "900.00"),
        ("Vino A", "100.00"),
    ]


def test_las_anuladas_y_las_ventas_de_otro_vendedor_no_entran_en_el_producto(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    vendedor2 = otro_usuario(sesion, s, "vendedor2", frozenset({"VENDER"}))
    sembrar_venta(sesion, s, lineas=[_cajas(1)])
    anulada = sembrar_venta(sesion, s, lineas=[_cajas(10)])
    anular_venta(sesion, s, anulada.venta_id, anulada_en=dia(11, 5))
    sembrar_venta(sesion, s, vendedor_id=vendedor2, lineas=[_cajas(2)])

    todos = _por_producto(cliente_http, sesion, s)
    del_vendedor2 = _por_producto(cliente_http, sesion, s, vendedor_id=str(vendedor2))

    assert [p["unidades_base"] for p in todos] == [18]
    assert [p["unidades_base"] for p in del_vendedor2] == [12]


def test_inv21_los_productos_de_otra_organizacion_no_aparecen(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_venta(sesion, propia, lineas=[_cajas(1)])
    sembrar_venta(sesion, ajena, lineas=[_cajas(50)])

    productos = _por_producto(cliente_http, sesion, propia)

    assert [p["producto_id"] for p in productos] == [str(propia.entorno.vino_id)]
    assert productos[0]["unidades_base"] == 6


def test_un_periodo_sin_ventas_no_trae_productos(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)

    assert _por_producto(cliente_http, sesion, s) == []
