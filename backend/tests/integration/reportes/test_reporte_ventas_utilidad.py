"""Tarea 3.4 (change 26, spec `reportes/ventas-por-periodo`, requisito «Costo vendido y utilidad
solo con `VER_UTILIDAD`, sin las líneas sin costo»; `design.md` D5): costo vendido, utilidad y
las líneas sin costo de `GET /api/v1/reportes/ventas`.

La utilidad de una línea es `importe_neto - costo_total - IVA absorbido`, y el IVA absorbido vale
cero mientras no exista el módulo de facturación (`03` §13). Se suma en la base solo sobre las
líneas con costo; las que no lo tienen se informan aparte y no entran en ninguno de los dos.

Reglas citadas: REP-04, REP-02, VTA-05, ADR-054, `01` §19.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    CON_UTILIDAD,
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


def _pedir(
    cliente_http: TestClient, sesion: Session, s: Sesion, permisos: frozenset[str], **filtros: str
) -> dict[str, Any]:
    headers = usuario_con(cliente_http, sesion, s, permisos)
    respuesta = cliente_http.get(URL_VENTAS, params={**NOVIEMBRE, **filtros}, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def test_con_ver_utilidad_el_resumen_informa_costo_vendido_y_utilidad(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Utilidad con permiso»: netos 1000 y 200, costos 700 y 150."""
    s = Sesion(sesion)
    sembrar_venta(
        sesion,
        s,
        lineas=[
            LineaDePrueba(neto="1000.00", costo_total="700.00"),
            LineaDePrueba(neto="200.00", costo_total="150.00"),
        ],
    )

    cuerpo = _pedir(cliente_http, sesion, s, CON_UTILIDAD)

    assert cuerpo["ve_utilidad"] is True
    resumen = cuerpo["resumen"]
    assert resumen["costo_vendido"] == "850.00"
    assert resumen["utilidad"] == "350.00"
    assert resumen["sin_costo"] == {"lineas": 0, "importe_neto": "0.00"}
    assert resumen["importe_neto"] == "1200.00"


def test_la_utilidad_tambien_viene_por_dia_y_por_vendedor(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    vendedor2 = otro_usuario(sesion, s, "vendedor2", frozenset({"VENDER"}))
    sembrar_venta(
        sesion,
        s,
        occurred_at=dia(11, 2),
        lineas=[LineaDePrueba(neto="1000.00", costo_total="700.00")],
    )
    sembrar_venta(
        sesion,
        s,
        vendedor_id=vendedor2,
        occurred_at=dia(11, 3),
        lineas=[LineaDePrueba(neto="400.00", costo_total="100.00")],
    )

    cuerpo = _pedir(cliente_http, sesion, s, CON_UTILIDAD)

    assert [
        (f["fecha"], f["costo_vendido"], f["utilidad"]) for f in cuerpo["por_dia"]["filas"]
    ] == [
        ("2026-11-03", "100.00", "300.00"),
        ("2026-11-02", "700.00", "300.00"),
    ]
    assert {
        f["vendedor_id"]: (f["costo_vendido"], f["utilidad"]) for f in cuerpo["por_vendedor"]
    } == {
        str(s.entorno.usuario_id): ("700.00", "300.00"),
        str(vendedor2): ("100.00", "300.00"),
    }


def test_sin_ver_utilidad_costo_utilidad_y_lineas_sin_costo_vienen_en_null(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Sin permiso de utilidad»: `sup01` (`VER_REPORTES`, sin `VER_UTILIDAD`)."""
    s = Sesion(sesion)
    sembrar_venta(
        sesion,
        s,
        lineas=[
            LineaDePrueba(neto="1000.00", costo_total="700.00"),
            LineaDePrueba(neto="300.00", costo_total=None),
        ],
    )

    cuerpo = _pedir(cliente_http, sesion, s, ABRIR_REPORTES)

    assert cuerpo["ve_utilidad"] is False
    for fila in [cuerpo["resumen"], *cuerpo["por_dia"]["filas"], *cuerpo["por_vendedor"]]:
        assert fila["costo_vendido"] is None
        assert fila["utilidad"] is None
        assert fila["sin_costo"] is None
    # Cantidades e importes siguen ahí.
    assert cuerpo["resumen"]["cantidad_ventas"] == 1
    assert cuerpo["resumen"]["importe_neto"] == "1300.00"
    assert cuerpo["resumen"]["total"] == "1300.00"


def test_consulta_direccion_ve_la_utilidad_sin_necesitar_ver_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Consulta/Dirección»: `VER_REPORTES` y `VER_UTILIDAD`, sin `VER_COSTOS` (D5)."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="500.00", costo_total="200.00")])

    resumen = _pedir(cliente_http, sesion, s, frozenset({"VER_REPORTES", "VER_UTILIDAD"}))[
        "resumen"
    ]

    assert (resumen["costo_vendido"], resumen["utilidad"]) == ("200.00", "300.00")


def test_ver_utilidad_sin_ver_reportes_no_alcanza_para_pedir_el_reporte(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, frozenset({"VER_UTILIDAD"}))

    respuesta = cliente_http.get(URL_VENTAS, headers=headers)

    assert respuesta.status_code == 403


def test_una_linea_sin_costo_queda_fuera_del_costo_y_de_la_utilidad_y_se_informa_aparte(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Línea vendida sin costo»: una venta sin conexión con netos 300 (sin costo) y
    1000 (costo 700)."""
    s = Sesion(sesion)
    sembrar_venta(
        sesion,
        s,
        modo_confirmacion="OFFLINE",
        lineas=[
            LineaDePrueba(neto="300.00", costo_total=None),
            LineaDePrueba(neto="1000.00", costo_total="700.00"),
        ],
    )

    cuerpo = _pedir(cliente_http, sesion, s, CON_UTILIDAD)

    resumen = cuerpo["resumen"]
    assert resumen["costo_vendido"] == "700.00"
    assert resumen["utilidad"] == "300.00"
    assert resumen["sin_costo"] == {"lineas": 1, "importe_neto": "300.00"}
    assert resumen["importe_neto"] == "1300.00"
    # Mismo criterio en cada nivel donde hay utilidad.
    assert cuerpo["por_dia"]["filas"][0]["sin_costo"] == {"lineas": 1, "importe_neto": "300.00"}
    assert cuerpo["por_vendedor"][0]["sin_costo"] == {"lineas": 1, "importe_neto": "300.00"}
    assert cuerpo["por_vendedor"][0]["utilidad"] == "300.00"


def test_las_lineas_sin_costo_de_varias_ventas_se_suman_en_la_base(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    for neto in ("100.00", "250.00"):
        sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto=neto, costo_total=None)])
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="400.00", costo_total="300.00")])

    resumen = _pedir(cliente_http, sesion, s, CON_UTILIDAD)["resumen"]

    assert resumen["sin_costo"] == {"lineas": 2, "importe_neto": "350.00"}
    assert (resumen["costo_vendido"], resumen["utilidad"]) == ("300.00", "100.00")
    assert resumen["importe_neto"] == "750.00"


def test_las_anuladas_no_suman_costo_ni_utilidad(cliente_http: TestClient, sesion: Session) -> None:
    """Escenario «Las anuladas no suman utilidad»."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="1000.00", costo_total="700.00")])
    anulada = sembrar_venta(
        sesion, s, lineas=[LineaDePrueba(neto="5000.00", costo_total="4000.00")]
    )
    anular_venta(sesion, s, anulada.venta_id, anulada_en=dia(11, 5))

    cuerpo = _pedir(cliente_http, sesion, s, CON_UTILIDAD)

    assert (cuerpo["resumen"]["costo_vendido"], cuerpo["resumen"]["utilidad"]) == (
        "700.00",
        "300.00",
    )
    assert cuerpo["anuladas"]["total"] == "5000.00"


def test_un_periodo_sin_ventas_con_permiso_trae_ceros_en_lugar_de_null(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)

    resumen = _pedir(cliente_http, sesion, s, CON_UTILIDAD)["resumen"]

    assert (resumen["costo_vendido"], resumen["utilidad"]) == ("0.00", "0.00")
    assert resumen["sin_costo"] == {"lineas": 0, "importe_neto": "0.00"}


def test_el_bruto_y_los_descuentos_salen_de_las_lineas_congeladas(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="900.00", importe_descuento="100.00")])

    resumen = _pedir(cliente_http, sesion, s, ABRIR_REPORTES)["resumen"]

    assert (resumen["importe_bruto"], resumen["importe_descuento"], resumen["importe_neto"]) == (
        "1000.00",
        "100.00",
        "900.00",
    )
