"""Tarea 6.1 (change 26, spec `reportes/ajustes-por-motivo`; `design.md` D10):
`GET /api/v1/reportes/ajustes`: los ajustes `CONFIRMADA` agrupados por motivo y producto (unidades
que entraron y que salieron y, con `VER_COSTOS`, su valor), la fila «Diferencias de rendición»
desde `stock_movimiento` y la cantidad de ajustes anulados.

PostgreSQL real y login real. Reglas citadas: STK-03, RUT-06, TR-03, TR-04, TR-06, INV-21,
`01` §19.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    dia,
    fijar_reloj,
    sembrar_ajuste,
    sembrar_diferencia_de_rendicion,
)
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL = "/api/v1/reportes/ajustes"
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}
CON_COSTOS = frozenset({"VER_REPORTES", "VER_COSTOS"})


def _pedir(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _lector(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)


def _lector_con_costos(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, CON_COSTOS)


def _por_motivo(cuerpo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["motivo_nombre"]: m for m in cuerpo["motivos"]}


def test_las_perdidas_por_rotura_suman_ajustes_unidades_y_valor(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Pérdidas por rotura»: -6 y -3 de un vino a `500.000000`: 2 ajustes, 9 unidades
    salidas y valor de las salidas `4500.00`."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -6, "500.000000")], occurred_at=dia(11, 3)
    )
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -3, "500.000000")], occurred_at=dia(11, 4)
    )
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (rotura,) = cuerpo["motivos"]
    assert rotura["motivo_nombre"] == "Rotura"
    assert (rotura["ajustes"], rotura["entradas"], rotura["salidas"]) == (2, 0, 9)
    assert rotura["valor_de_salidas"] == "4500.00"
    assert rotura["valor_de_entradas"] == "0.00"
    assert rotura["unidades_sin_costo"] == 0
    (producto,) = rotura["productos"]
    assert (producto["producto_id"], producto["nombre"]) == (str(vino), "Vino A")
    assert producto["codigo"]
    assert (producto["entradas"], producto["salidas"], producto["valor_de_salidas"]) == (
        0,
        9,
        "4500.00",
    )
    assert cuerpo["ve_costos"] is True


def test_cada_motivo_se_agrupa_aparte_con_entradas_salidas_y_detalle_por_producto(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: dos motivos, un ajuste con dos productos cuenta como UN ajuste, entradas y
    salidas por separado, y lo sin costo aparte (no suma en el valor)."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    agua = crear_producto_sql(sesion, s.entorno.org, nombre="Agua 500")
    sembrar_ajuste(
        sesion,
        s,
        motivo="Vencimiento",
        lineas=[(vino, -2, "100.250000"), (agua, -4, None)],
        occurred_at=dia(11, 3),
    )
    sembrar_ajuste(
        sesion, s, motivo="Hallazgo", lineas=[(vino, 5, "100.250000")], occurred_at=dia(11, 5)
    )
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert [m["motivo_nombre"] for m in cuerpo["motivos"]] == ["Hallazgo", "Vencimiento"]
    motivos = _por_motivo(cuerpo)
    hallazgo, vencimiento = motivos["Hallazgo"], motivos["Vencimiento"]
    assert (hallazgo["ajustes"], hallazgo["entradas"], hallazgo["salidas"]) == (1, 5, 0)
    assert (hallazgo["valor_de_entradas"], hallazgo["valor_de_salidas"]) == ("501.25", "0.00")
    assert (vencimiento["ajustes"], vencimiento["entradas"], vencimiento["salidas"]) == (1, 0, 6)
    assert vencimiento["valor_de_salidas"] == "200.50"
    assert vencimiento["unidades_sin_costo"] == 4
    por_producto = {p["nombre"]: p for p in vencimiento["productos"]}
    assert set(por_producto) == {"Vino A", "Agua 500"}
    assert (por_producto["Vino A"]["salidas"], por_producto["Vino A"]["valor_de_salidas"]) == (
        2,
        "200.50",
    )
    assert (
        por_producto["Agua 500"]["salidas"],
        por_producto["Agua 500"]["valor_de_salidas"],
        por_producto["Agua 500"]["unidades_sin_costo"],
    ) == (4, "0.00", 4)


def test_el_valor_se_suma_exacto_y_se_redondea_una_sola_vez(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-03: tres salidas de 1 unidad a `0.335000` suman `1.005` exacto = `1.01`; redondear
    cada una daría `1.02`."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    for dia_ in (3, 4, 5):
        sembrar_ajuste(
            sesion, s, motivo="Merma", lineas=[(vino, -1, "0.335000")], occurred_at=dia(11, dia_)
        )
    headers = _lector_con_costos(cliente_http, sesion, s)

    (merma,) = _pedir(cliente_http, headers, **NOVIEMBRE)["motivos"]

    assert merma["valor_de_salidas"] == "1.01"
    assert merma["productos"][0]["valor_de_salidas"] == "1.01"


def test_un_ajuste_anulado_no_suma_y_se_cuenta_aparte(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Ajuste anulado»."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -6, "500.000000")], occurred_at=dia(11, 3)
    )
    sembrar_ajuste(
        sesion,
        s,
        motivo="Rotura",
        lineas=[(vino, -100, "500.000000")],
        occurred_at=dia(11, 4),
        anulado=True,
    )
    sembrar_ajuste(
        sesion,
        s,
        motivo="Error de carga",
        lineas=[(vino, 7, "500.000000")],
        occurred_at=dia(11, 5),
        anulado=True,
    )
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (rotura,) = cuerpo["motivos"]
    assert (rotura["ajustes"], rotura["salidas"], rotura["valor_de_salidas"]) == (1, 6, "3000.00")
    assert cuerpo["ajustes_anulados"] == 2


def test_las_diferencias_de_rendicion_van_en_su_propia_fila(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Diferencias de rendición»: un faltante de 2 unidades es 2 unidades salidas;
    un sobrante, una entrada; no se mezclan con los motivos."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    agua = crear_producto_sql(sesion, s.entorno.org, nombre="Agua 500")
    sembrar_diferencia_de_rendicion(
        sesion, s, vino, -2, costo_unitario="500.000000", occurred_at=dia(11, 3)
    )
    sembrar_diferencia_de_rendicion(
        sesion, s, agua, 1, costo_unitario="80.500000", occurred_at=dia(11, 3, 15)
    )
    sembrar_diferencia_de_rendicion(sesion, s, agua, 3, costo_unitario=None, occurred_at=dia(11, 4))
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert cuerpo["motivos"] == []
    diferencias = cuerpo["diferencias_de_rendicion"]
    assert (diferencias["entradas"], diferencias["salidas"]) == (4, 2)
    assert (diferencias["valor_de_entradas"], diferencias["valor_de_salidas"]) == (
        "80.50",
        "1000.00",
    )
    assert diferencias["unidades_sin_costo"] == 3
    assert {p["nombre"]: (p["entradas"], p["salidas"]) for p in diferencias["productos"]} == {
        "Vino A": (0, 2),
        "Agua 500": (4, 0),
    }


def test_sin_ver_costos_las_unidades_se_informan_y_los_valores_van_en_null(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Sin permiso de costos»."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -6, "500.000000")], occurred_at=dia(11, 3)
    )
    sembrar_diferencia_de_rendicion(
        sesion, s, vino, -2, costo_unitario="500.000000", occurred_at=dia(11, 3)
    )
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert cuerpo["ve_costos"] is False
    (rotura,) = cuerpo["motivos"]
    assert (rotura["ajustes"], rotura["salidas"]) == (1, 6)
    assert rotura["valor_de_salidas"] is None and rotura["valor_de_entradas"] is None
    assert rotura["unidades_sin_costo"] is None
    assert rotura["productos"][0]["valor_de_salidas"] is None
    diferencias = cuerpo["diferencias_de_rendicion"]
    assert diferencias["salidas"] == 2
    assert diferencias["valor_de_salidas"] is None
    assert diferencias["productos"][0]["valor_de_salidas"] is None


def test_lo_que_cae_fuera_del_periodo_no_se_cuenta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-04: el 31/10 a las 23:00 (Mendoza) es de octubre; sin fechas, el mes del reloj."""
    s = Sesion(sesion)
    vino = s.entorno.vino_id
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -1, "10.000000")], occurred_at=dia(10, 31, 23)
    )
    sembrar_ajuste(
        sesion, s, motivo="Rotura", lineas=[(vino, -2, "10.000000")], occurred_at=dia(11, 1, 0)
    )
    sembrar_diferencia_de_rendicion(
        sesion, s, vino, -4, costo_unitario="10.000000", occurred_at=dia(10, 31, 23)
    )
    headers = _lector_con_costos(cliente_http, sesion, s)
    fijar_reloj(cliente_http, dia(11, 15))

    en_noviembre = _pedir(cliente_http, headers)
    en_octubre = _pedir(cliente_http, headers, desde="2026-10-01", hasta="2026-10-31")

    assert en_noviembre["periodo"]["desde"] == "2026-11-01"
    assert [(m["ajustes"], m["salidas"]) for m in en_noviembre["motivos"]] == [(1, 2)]
    assert en_noviembre["diferencias_de_rendicion"]["salidas"] == 0
    assert [(m["ajustes"], m["salidas"]) for m in en_octubre["motivos"]] == [(1, 1)]
    assert en_octubre["diferencias_de_rendicion"]["salidas"] == 4


def test_un_periodo_sin_ajustes_devuelve_todo_en_cero(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert cuerpo["motivos"] == []
    assert cuerpo["ajustes_anulados"] == 0
    diferencias = cuerpo["diferencias_de_rendicion"]
    assert (diferencias["entradas"], diferencias["salidas"], diferencias["productos"]) == (0, 0, [])
    assert diferencias["valor_de_salidas"] == "0.00"


def test_el_periodo_demasiado_largo_se_rechaza(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    respuesta = cliente_http.get(
        URL, params={"desde": "2025-01-01", "hasta": "2026-11-01"}, headers=headers
    )

    assert (respuesta.status_code, respuesta.json()["codigo"]) == (422, "PERIODO_DEMASIADO_LARGO")


def test_inv21_no_cuenta_ajustes_ni_diferencias_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_ajuste(
        sesion,
        propia,
        motivo="Rotura",
        lineas=[(propia.entorno.vino_id, -1, "10.000000")],
        occurred_at=dia(11, 3),
    )
    sembrar_ajuste(
        sesion,
        ajena,
        motivo="Rotura",
        lineas=[(ajena.entorno.vino_id, -50, "10.000000")],
        occurred_at=dia(11, 3),
        anulado=True,
    )
    sembrar_ajuste(
        sesion,
        ajena,
        motivo="Ajena",
        lineas=[(ajena.entorno.vino_id, -50, "10.000000")],
        occurred_at=dia(11, 3),
    )
    sembrar_diferencia_de_rendicion(
        sesion, ajena, ajena.entorno.vino_id, -9, costo_unitario="10.000000", occurred_at=dia(11, 3)
    )
    headers = _lector_con_costos(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (rotura,) = cuerpo["motivos"]
    assert (rotura["motivo_nombre"], rotura["ajustes"], rotura["salidas"]) == ("Rotura", 1, 1)
    assert cuerpo["ajustes_anulados"] == 0
    assert cuerpo["diferencias_de_rendicion"]["salidas"] == 0
