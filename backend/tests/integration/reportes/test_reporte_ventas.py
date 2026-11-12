"""Tareas 3.1 y 3.2 (change 26, spec `reportes/ventas-por-periodo`; `design.md` D1, D2, D3):
`GET /api/v1/reportes/ventas` con el resumen, el desglose por día y por vendedor, el período, el
filtro de vendedor y las ventas anuladas aparte.

PostgreSQL real y login real (mismo arnés que `test_ventas_consultas_api.py`).

Reglas citadas: REP-01, REP-02, REP-05, INV-02, INV-03, INV-14, INV-21, VTA-22, TR-04.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    URL_VENTAS,
    LineaDePrueba,
    anular_venta,
    dia,
    fijar_reloj,
    sembrar_venta,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import otro_usuario, usuario_con

OCTUBRE = {"desde": "2026-10-01", "hasta": "2026-10-31"}
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}


def _pedir(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> dict[str, Any]:
    respuesta = cliente_http.get(URL_VENTAS, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _lector(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)


# --- resumen, por día y por vendedor (REP-01, INV-03, INV-14) ---------------------------------


def test_el_resumen_suma_las_ventas_confirmadas_del_periodo(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Totales del período»: netos 1000 y 500, IVA cero (modo A)."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(11, 3), lineas=[LineaDePrueba(neto="1000.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 4), lineas=[LineaDePrueba(neto="500.00")])
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    resumen = cuerpo["resumen"]
    assert resumen["cantidad_ventas"] == 2
    assert resumen["importe_neto"] == "1500.00"
    assert resumen["importe_iva"] == "0.00"
    assert resumen["total"] == "1500.00"
    assert resumen["importe_bruto"] == "1500.00"
    assert resumen["importe_descuento"] == "0.00"
    (fila,) = cuerpo["por_vendedor"]
    assert fila["vendedor_id"] == str(s.entorno.usuario_id)
    assert (fila["cantidad_ventas"], fila["importe_neto"], fila["total"]) == (
        2,
        "1500.00",
        "1500.00",
    )


def test_el_iva_se_suma_aparte_y_el_total_es_neto_mas_iva(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-14, modo B: neto 1000 + IVA 210 = total 1210 (valores congelados de la venta)."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="1000.00")], iva="210.00")
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="100.00")], iva="21.00")
    headers = _lector(cliente_http, sesion, s)

    resumen = _pedir(cliente_http, headers, **NOVIEMBRE)["resumen"]

    assert (resumen["importe_neto"], resumen["importe_iva"], resumen["total"]) == (
        "1100.00",
        "231.00",
        "1331.00",
    )


def test_el_desglose_por_dia_va_con_el_mas_reciente_primero_y_la_fecha_de_negocio(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(11, 5), lineas=[LineaDePrueba(neto="300.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 2), lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 2, hora=18), lineas=[LineaDePrueba(neto="50.00")])
    headers = _lector(cliente_http, sesion, s)

    por_dia = _pedir(cliente_http, headers, **NOVIEMBRE)["por_dia"]["filas"]

    assert [(f["fecha"], f["cantidad_ventas"], f["importe_neto"]) for f in por_dia] == [
        ("2026-11-05", 1, "300.00"),
        ("2026-11-02", 2, "150.00"),
    ]


def test_el_desglose_por_vendedor_va_por_neto_descendente_con_su_nombre(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    vendedor2 = otro_usuario(sesion, s, "vendedor2", frozenset({"VENDER"}))
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, s, vendedor_id=vendedor2, lineas=[LineaDePrueba(neto="900.00")])
    sembrar_venta(sesion, s, vendedor_id=vendedor2, lineas=[LineaDePrueba(neto="100.00")])
    headers = _lector(cliente_http, sesion, s)

    por_vendedor = _pedir(cliente_http, headers, **NOVIEMBRE)["por_vendedor"]

    assert [(f["vendedor_id"], f["importe_neto"]) for f in por_vendedor] == [
        (str(vendedor2), "1000.00"),
        (str(s.entorno.usuario_id), "100.00"),
    ]
    assert por_vendedor[0]["vendedor_nombre"] == "Persona vendedor2"


def test_el_filtro_de_vendedor_acota_el_resumen_y_los_desgloses(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Filtro por vendedor»."""
    s = Sesion(sesion)
    vendedor2 = otro_usuario(sesion, s, "vendedor2", frozenset({"VENDER"}))
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, s, vendedor_id=vendedor2, lineas=[LineaDePrueba(neto="900.00")])
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, vendedor_id=str(vendedor2), **NOVIEMBRE)

    assert cuerpo["resumen"]["cantidad_ventas"] == 1
    assert cuerpo["resumen"]["importe_neto"] == "900.00"
    assert [f["vendedor_id"] for f in cuerpo["por_vendedor"]] == [str(vendedor2)]
    assert [f["importe_neto"] for f in cuerpo["por_dia"]["filas"]] == ["900.00"]


def test_un_periodo_sin_ventas_trae_ceros_y_desgloses_vacios(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Período sin ventas»."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(11, 3))
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **OCTUBRE)

    resumen = cuerpo["resumen"]
    assert resumen["cantidad_ventas"] == 0
    assert (resumen["importe_bruto"], resumen["importe_neto"], resumen["total"]) == (
        "0.00",
        "0.00",
        "0.00",
    )
    assert resumen["cajas_equivalentes"] == "0.00"
    assert resumen["unidades_base"] == 0
    assert cuerpo["por_dia"]["filas"] == []
    assert cuerpo["por_dia"]["total_filas"] == 0
    assert cuerpo["por_dia"]["paginas"] == 0
    assert cuerpo["por_vendedor"] == []


# --- el período (TR-04, REP-02) ---------------------------------------------------------------


def test_sin_fechas_el_periodo_es_el_mes_en_curso_segun_el_reloj_inyectable(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Mes en curso por defecto»: 2026-11-06 10:00 hora de Mendoza."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(10, 30), lineas=[LineaDePrueba(neto="7.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 2), lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 6, hora=9), lineas=[LineaDePrueba(neto="20.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 7), lineas=[LineaDePrueba(neto="9.00")])
    headers = _lector(cliente_http, sesion, s)
    fijar_reloj(cliente_http, dia(11, 6, hora=10))

    cuerpo = _pedir(cliente_http, headers)

    assert cuerpo["periodo"] == {
        "desde": "2026-11-01",
        "hasta": "2026-11-06",
        "zona_horaria": "America/Argentina/Mendoza",
    }
    assert cuerpo["resumen"]["importe_neto"] == "120.00"


def test_con_solo_desde_el_periodo_llega_hasta_hoy_y_con_solo_hasta_parte_del_dia_uno(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)
    fijar_reloj(cliente_http, dia(11, 6, hora=10))

    solo_desde = _pedir(cliente_http, headers, desde="2026-10-15")["periodo"]
    solo_hasta = _pedir(cliente_http, headers, hasta="2026-09-20")["periodo"]

    assert (solo_desde["desde"], solo_desde["hasta"]) == ("2026-10-15", "2026-11-06")
    assert (solo_hasta["desde"], solo_hasta["hasta"]) == ("2026-09-01", "2026-09-20")


def test_una_venta_cerca_de_la_medianoche_entra_en_el_mes_de_la_zona_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Venta cerca de la medianoche»: 2026-11-01T02:30Z es el 31/10 a las 23:30."""
    s = Sesion(sesion)
    sembrar_venta(
        sesion,
        s,
        occurred_at=datetime(2026, 11, 1, 2, 30, tzinfo=UTC),
        lineas=[LineaDePrueba(neto="300.00")],
    )
    headers = _lector(cliente_http, sesion, s)

    en_noviembre = _pedir(cliente_http, headers, **NOVIEMBRE)
    en_octubre = _pedir(cliente_http, headers, **OCTUBRE)

    assert en_noviembre["resumen"]["cantidad_ventas"] == 0
    assert en_octubre["resumen"]["cantidad_ventas"] == 1
    assert [f["fecha"] for f in en_octubre["por_dia"]["filas"]] == ["2026-10-31"]


def test_un_rango_invertido_responde_422_rango_de_fechas_invalido(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    respuesta = cliente_http.get(
        URL_VENTAS, params={"desde": "2026-11-10", "hasta": "2026-11-01"}, headers=headers
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"


def test_367_dias_responden_422_y_366_se_aceptan(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    largo = cliente_http.get(
        URL_VENTAS, params={"desde": "2025-01-01", "hasta": "2026-01-02"}, headers=headers
    )
    justo = cliente_http.get(
        URL_VENTAS, params={"desde": "2025-01-01", "hasta": "2026-01-01"}, headers=headers
    )

    assert largo.status_code == 422
    assert largo.json()["codigo"] == "PERIODO_DEMASIADO_LARGO"
    assert justo.status_code == 200


# --- permisos, aislamiento y valores congelados ------------------------------------------------


def test_sin_ver_reportes_responde_403_permiso_requerido(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Sin permiso de reportes»: `vendedor` (solo `VENDER`)."""
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, frozenset({"VENDER"}))

    respuesta = cliente_http.get(URL_VENTAS, headers=headers)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_sin_sesion_responde_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL_VENTAS).status_code == 401


def test_inv21_el_reporte_no_incluye_ventas_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Datos de otra organización» (INV-02, INV-21): dos organizaciones con ventas."""
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_venta(sesion, propia, lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, ajena, lineas=[LineaDePrueba(neto="5000.00")])
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert cuerpo["resumen"]["cantidad_ventas"] == 1
    assert cuerpo["resumen"]["importe_neto"] == "100.00"
    assert [f["vendedor_id"] for f in cuerpo["por_vendedor"]] == [str(propia.entorno.usuario_id)]


def test_inv21_filtrar_por_un_vendedor_de_otra_organizacion_devuelve_el_reporte_vacio(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Filtro con un vendedor ajeno»: sin error y sin datos ajenos."""
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_venta(sesion, propia, lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, ajena, lineas=[LineaDePrueba(neto="5000.00")])
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, vendedor_id=str(ajena.entorno.usuario_id), **NOVIEMBRE)

    assert cuerpo["resumen"]["cantidad_ventas"] == 0
    assert cuerpo["por_vendedor"] == []


def test_inv21_la_organizacion_no_se_toma_de_la_consulta(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    sembrar_venta(sesion, ajena, lineas=[LineaDePrueba(neto="5000.00")])
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, organizacion_id=str(ajena.entorno.org), **NOVIEMBRE)

    assert cuerpo["resumen"]["cantidad_ventas"] == 0


def test_rep05_las_cifras_pasadas_no_cambian_con_precios_posteriores(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Valores congelados»: cambia el precio de la lista y el reporte no se mueve."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="1000.00")])
    headers = _lector(cliente_http, sesion, s)
    antes = _pedir(cliente_http, headers, **NOVIEMBRE)

    sesion.execute(
        text("UPDATE precio_item SET precio_final = 99999.00 WHERE organizacion_id = :o"),
        {"o": s.entorno.org},
    )
    sesion.commit()
    despues = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert despues == antes


# --- ventas anuladas (tarea 3.2; REP-02, VTA-22) -----------------------------------------------


def test_las_anuladas_no_suman_en_el_periodo_y_se_informan_aparte(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Anulada dentro del período»: tres ventas, una anulada por «Error de carga»."""
    s = Sesion(sesion)
    sembrar_venta(sesion, s, occurred_at=dia(11, 2), lineas=[LineaDePrueba(neto="100.00")])
    sembrar_venta(sesion, s, occurred_at=dia(11, 3), lineas=[LineaDePrueba(neto="200.00")])
    anulada = sembrar_venta(
        sesion, s, occurred_at=dia(11, 4), lineas=[LineaDePrueba(neto="700.00")]
    )
    anular_venta(sesion, s, anulada.venta_id, anulada_en=dia(11, 5), devuelve_dinero=True)
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert cuerpo["resumen"]["cantidad_ventas"] == 2
    assert cuerpo["resumen"]["total"] == "300.00"
    assert [f["fecha"] for f in cuerpo["por_dia"]["filas"]] == ["2026-11-03", "2026-11-02"]
    assert cuerpo["por_vendedor"][0]["importe_neto"] == "300.00"
    anuladas = cuerpo["anuladas"]
    assert (anuladas["cantidad"], anuladas["total"]) == (1, "700.00")
    (venta,) = anuladas["ventas"]["filas"]
    assert venta["venta_id"] == str(anulada.venta_id)
    assert venta["numero"] == anulada.numero
    assert venta["cliente_id"] == str(s.entorno.cliente_id)
    assert venta["cliente_nombre"] == "Kiosco La Esquina"
    assert venta["vendedor_id"] == str(s.entorno.usuario_id)
    assert venta["total"] == "700.00"
    assert venta["motivo"] == "Error de carga"
    assert venta["devuelve_dinero"] is True
    assert datetime.fromisoformat(venta["occurred_at"]) == dia(11, 4)
    assert datetime.fromisoformat(venta["anulada_en"]) == dia(11, 5)


def test_una_anulada_despues_del_periodo_queda_en_el_periodo_de_la_venta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Anulada después del período»: vendida el 30/10, anulada el 02/11."""
    s = Sesion(sesion)
    vieja = sembrar_venta(sesion, s, occurred_at=dia(10, 30), lineas=[LineaDePrueba(neto="400.00")])
    anular_venta(sesion, s, vieja.venta_id, anulada_en=dia(11, 2), devuelve_dinero=None)
    headers = _lector(cliente_http, sesion, s)

    octubre = _pedir(cliente_http, headers, **OCTUBRE)
    noviembre = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert octubre["resumen"]["cantidad_ventas"] == 0
    assert octubre["resumen"]["total"] == "0.00"
    (venta,) = octubre["anuladas"]["ventas"]["filas"]
    assert venta["venta_id"] == str(vieja.venta_id)
    assert venta["devuelve_dinero"] is None
    assert datetime.fromisoformat(venta["anulada_en"]) == dia(11, 2)
    assert (noviembre["anuladas"]["cantidad"], noviembre["anuladas"]["total"]) == (0, "0.00")
    assert noviembre["anuladas"]["ventas"]["filas"] == []


def test_el_filtro_de_vendedor_tambien_acota_las_anuladas(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    vendedor2 = otro_usuario(sesion, s, "vendedor2", frozenset({"VENDER"}))
    propia = sembrar_venta(sesion, s, lineas=[LineaDePrueba(neto="10.00")])
    ajena = sembrar_venta(sesion, s, vendedor_id=vendedor2, lineas=[LineaDePrueba(neto="20.00")])
    anular_venta(sesion, s, propia.venta_id, anulada_en=dia(11, 5))
    anular_venta(sesion, s, ajena.venta_id, anulada_en=dia(11, 5))
    headers = _lector(cliente_http, sesion, s)

    todas = _pedir(cliente_http, headers, **NOVIEMBRE)["anuladas"]
    de_vendedor2 = _pedir(cliente_http, headers, vendedor_id=str(vendedor2), **NOVIEMBRE)[
        "anuladas"
    ]
    de_nadie = _pedir(cliente_http, headers, vendedor_id=str(uuid4()), **NOVIEMBRE)["anuladas"]

    assert (todas["cantidad"], todas["total"]) == (2, "30.00")
    assert (de_vendedor2["cantidad"], de_vendedor2["total"]) == (1, "20.00")
    assert (de_nadie["cantidad"], de_nadie["total"]) == (0, "0.00")
    assert de_nadie["ventas"]["filas"] == []
