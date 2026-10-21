"""Tarea 9.1 (change 18a, `design.md` D19): `GET /api/v1/ventas` y `GET /api/v1/ventas/{id}`.

Tabla de permisos aprobada por el usuario el 2026-10-20: `VENDER` o `ANULAR_VENTA`, todas las
ventas de la organización; el costo de cada línea solo con `VER_COSTOS` (nulo sin él) y la
utilidad no se expone (REP-04: es de los reportes; ajuste aprobado el 2026-10-20); una venta de
otra organización responde 404. Mismo arnés que `test_ventas_api.py` (PostgreSQL real, login
real).

Reglas citadas: VTA-05, VTA-06, VTA-11, INV-03, INV-21, SEG-06, SEG-07, STK-05, SYN-07, TR-04.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    URL_VENTAS,
    Sesion,
    _con_op,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_confirmar_utiles import PERMISOS_DE_SUPERVISOR
from ventas_lecturas_utiles import sembrar, usuario_con

SOLO_ANULA = frozenset({"ANULAR_VENTA"})
VENDE_Y_VE_COSTOS = frozenset({"VENDER", "VER_COSTOS"})
ID_INEXISTENTE = "00000000-0000-4000-8000-000000000000"


def _dia(dia: int) -> datetime:
    return datetime(2026, 10, dia, 12, 0, tzinfo=UTC)


def _vender(cliente_http: TestClient, s: Sesion, headers: dict[str, str], **cambios: Any) -> str:
    """Confirma una venta real por HTTP y devuelve su identificador."""
    respuesta = cliente_http.post(URL_VENTAS, json=s.cuerpo(**cambios), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["venta_id"])


def _ids(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> set[str]:
    respuesta = cliente_http.get(URL_VENTAS, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return {i["venta_id"] for i in respuesta.json()["items"]}


# --- listado: contenido, orden y filtros (VTA-06, INV-03, TR-04) ------------------------------


def test_el_listado_trae_las_ventas_mas_recientes_primero_con_importes_como_string(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-06, INV-03: número, cliente con nombre, total como string y estado."""
    s = Sesion(sesion)
    vieja = sembrar(sesion, s, occurred_at=_dia(3))
    nueva = sembrar(sesion, s, occurred_at=_dia(5))
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(URL_VENTAS, headers=headers)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["cursor_siguiente"] is None
    assert [i["venta_id"] for i in cuerpo["items"]] == [str(nueva.venta_id), str(vieja.venta_id)]
    primero = cuerpo["items"][0]
    assert primero["numero"] == nueva.numero
    assert primero["cliente_id"] == str(s.entorno.cliente_id)
    assert primero["cliente_nombre"] == "Kiosco La Esquina"
    assert primero["usuario_nombre"]
    assert primero["total"] == "37500.00"
    assert primero["estado"] == "CONFIRMADA"
    assert primero["ubicacion_id"] == str(nueva.ubicacion_id)


def test_los_filtros_de_cliente_usuario_ubicacion_y_jornada_acotan_el_listado(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D19: filtros de cliente, usuario, jornada y ubicación (cada uno con dos casos)."""
    s = Sesion(sesion)
    otro_cliente = s.entorno.crear_cliente(nombre="Almacén Don Pepe")
    jornada = s.entorno.crear_jornada()
    del_cliente = sembrar(sesion, s, cliente_id=otro_cliente)
    con_jornada = sembrar(sesion, s, jornada_id=jornada)
    comun = sembrar(sesion, s)
    headers = s.entrar(cliente_http)

    assert _ids(cliente_http, headers, cliente_id=str(otro_cliente)) == {str(del_cliente.venta_id)}
    assert _ids(cliente_http, headers, cliente_id=str(s.entorno.cliente_id)) == {
        str(con_jornada.venta_id),
        str(comun.venta_id),
    }
    assert _ids(cliente_http, headers, jornada_id=str(jornada)) == {str(con_jornada.venta_id)}
    assert _ids(cliente_http, headers, ubicacion_id=str(comun.ubicacion_id)) == {
        str(comun.venta_id)
    }
    assert _ids(cliente_http, headers, ubicacion_id=str(del_cliente.ubicacion_id)) == {
        str(del_cliente.venta_id)
    }
    assert _ids(cliente_http, headers, usuario_id=str(s.entorno.usuario_id)) == {
        str(del_cliente.venta_id),
        str(con_jornada.venta_id),
        str(comun.venta_id),
    }
    assert _ids(cliente_http, headers, usuario_id=ID_INEXISTENTE) == set()


def test_tr04_las_fechas_de_negocio_son_inclusivas_y_acotan_el_listado(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-04: `desde` y `hasta` incluyen el día entero."""
    s = Sesion(sesion)
    d3 = sembrar(sesion, s, occurred_at=_dia(3))
    d5 = sembrar(sesion, s, occurred_at=_dia(5))
    d8 = sembrar(sesion, s, occurred_at=_dia(8))
    headers = s.entrar(cliente_http)

    assert _ids(cliente_http, headers, desde="2026-10-05", hasta="2026-10-05") == {str(d5.venta_id)}
    assert _ids(cliente_http, headers, desde="2026-10-04") == {str(d5.venta_id), str(d8.venta_id)}
    assert _ids(cliente_http, headers, hasta="2026-10-05") == {str(d3.venta_id), str(d5.venta_id)}


def test_la_pagina_devuelve_cursor_y_la_siguiente_completa_el_listado(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    creadas = {str(sembrar(sesion, s, occurred_at=_dia(d)).venta_id) for d in (2, 3, 4)}
    headers = s.entrar(cliente_http)

    primera = cliente_http.get(f"{URL_VENTAS}?limite=2", headers=headers).json()
    segunda = cliente_http.get(
        f"{URL_VENTAS}?limite=2&cursor={primera['cursor_siguiente']}", headers=headers
    ).json()

    vistas = [i["venta_id"] for i in primera["items"] + segunda["items"]]
    assert len(vistas) == 3 and set(vistas) == creadas
    assert primera["cursor_siguiente"] is not None
    assert segunda["cursor_siguiente"] is None


def test_un_limite_fuera_de_rango_es_422_y_un_cursor_ilegible_es_cursor_invalido(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    assert cliente_http.get(f"{URL_VENTAS}?limite=0", headers=headers).status_code == 422
    assert cliente_http.get(f"{URL_VENTAS}?limite=201", headers=headers).status_code == 422
    ilegible = cliente_http.get(f"{URL_VENTAS}?cursor=xx", headers=headers)
    assert ilegible.status_code == 422
    assert ilegible.json()["codigo"] == "CURSOR_INVALIDO"
    invertido = cliente_http.get(f"{URL_VENTAS}?desde=2026-10-10&hasta=2026-10-01", headers=headers)
    assert invertido.status_code == 422
    assert invertido.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"


# --- permisos y aislamiento (SEG-06, SEG-07, INV-21) -------------------------------------------


def test_seg06_sin_vender_ni_anular_venta_responde_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Sin permiso y ajena"
    s = Sesion(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
    venta = sembrar(sesion, s)
    headers = s.entrar(cliente_http)

    assert cliente_http.get(URL_VENTAS, headers=headers).status_code == 403
    assert cliente_http.get(f"{URL_VENTAS}/{venta.venta_id}", headers=headers).status_code == 403


def test_sin_sesion_responde_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL_VENTAS).status_code == 401


def test_con_solo_anular_venta_tambien_se_leen_todas_las_ventas_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D19: `VENDER` o `ANULAR_VENTA`, y todas las de la organización, no solo las propias."""
    s = Sesion(sesion)
    venta = sembrar(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, SOLO_ANULA)

    lista = cliente_http.get(URL_VENTAS, headers=headers)
    detalle = cliente_http.get(f"{URL_VENTAS}/{venta.venta_id}", headers=headers)

    assert [i["venta_id"] for i in lista.json()["items"]] == [str(venta.venta_id)]
    assert detalle.status_code == 200


def test_inv21_las_ventas_de_otra_organizacion_no_aparecen_y_su_detalle_es_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Sin permiso y ajena"
    """INV-21, SEG-07: ni en el listado ni por identificador."""
    s = Sesion(sesion)
    otra_organizacion = Sesion(sesion)
    propia = sembrar(sesion, s)
    ajena = sembrar(sesion, otra_organizacion)
    headers = s.entrar(cliente_http)

    lista = cliente_http.get(URL_VENTAS, headers=headers).json()
    detalle = cliente_http.get(f"{URL_VENTAS}/{ajena.venta_id}", headers=headers)

    assert [i["venta_id"] for i in lista["items"]] == [str(propia.venta_id)]
    assert detalle.status_code == 404


def test_un_identificador_inexistente_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    assert cliente_http.get(f"{URL_VENTAS}/{ID_INEXISTENTE}", headers=headers).status_code == 404


# --- detalle (VTA-05, VTA-11, SYN-07, STK-05) -------------------------------------------------


def test_vta05_el_detalle_sin_ver_costos_trae_los_costos_en_nulo_y_no_trae_utilidad(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-05, `01` §19, REP-04: el Vendedor ve líneas, totales y cobranza, no costos; la utilidad
    no es un campo del detalle."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    venta_id = _vender(cliente_http, s, headers)

    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers)

    assert respuesta.status_code == 200
    detalle = respuesta.json()
    assert detalle["total"] == "31250.00"
    assert detalle["numero"] == f"{s.prefijo}-000001"
    (linea,) = detalle["lineas"]
    assert linea["producto_nombre"] == "Vino A"
    assert linea["presentacion_nombre"] == "Botella"
    assert linea["cantidad"] == 15
    assert linea["cantidad_base"] == 15
    assert linea["precio_referencia"] == "12500.00"
    assert linea["importe_bruto"] == "31250.00"
    assert linea["costo_unitario"] is None
    assert linea["costo_total"] is None
    assert "utilidad" not in linea


def test_vta05_el_detalle_con_ver_costos_trae_el_costo_congelado_pero_no_la_utilidad(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-05, CST-11, REP-04: costo `1050.000000` por botella, 15 botellas = `15750.00`. La
    utilidad (neto - costo) NO se expone ni con `VER_COSTOS`: pertenece a los reportes, que
    además asignan el IVA absorbido (ajuste aprobado el 2026-10-20)."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    venta_id = _vender(cliente_http, s, headers)
    con_costos = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=con_costos)

    (linea,) = respuesta.json()["lineas"]
    assert linea["costo_unitario"] == "1050.000000"
    assert linea["costo_total"] == "15750.00"
    assert "utilidad" not in linea
    assert "utilidad" not in respuesta.text


def test_vta11_el_detalle_trae_la_cobranza_enlazada_la_lista_y_la_version(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-11: la cobranza en el acto con su id e importe; la lista y la versión usadas."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cobranza = s.entorno.cobranza()
    venta_id = _vender(cliente_http, s, headers, cobranza=cobranza)

    detalle = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()

    assert detalle["cobranza"]["cobranza_id"] == cobranza["cobranza_id"]
    assert detalle["cobranza"]["importe"] == "20000.00"
    assert detalle["cobranza"]["estado"] == "CONFIRMADA"
    assert detalle["lista_id"] == str(s.entorno.lista_id)
    assert detalle["lista_nombre"].startswith("General")
    assert detalle["version_id"] == str(s.entorno.version_id)
    assert detalle["version_numero"] == 1
    assert detalle["motivo_lista"] is None
    assert detalle["cliente_nombre"] == "Kiosco La Esquina"
    assert detalle["ubicacion_nombre"] == "Depósito central"


def test_vta11_una_venta_sin_cobranza_la_trae_en_nulo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    venta_id = _vender(cliente_http, s, headers)

    detalle = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()

    assert detalle["cobranza"] is None


def test_el_detalle_muestra_la_lista_otra_y_el_motivo_elegido(
    cliente_http: TestClient, sesion: Session
) -> None:
    """PRC-21: otra lista con motivo; el detalle trae el motivo con su nombre."""
    s = Sesion(sesion, permisos=PERMISOS_DE_SUPERVISOR)
    otra = s.entorno.crear_lista("Mayorista")
    version = s.entorno.crear_version(
        otra, 1, datetime(2026, 10, 1, tzinfo=UTC), precio_vino="11000.00"
    )
    s.sesion.commit()
    headers = s.entrar(cliente_http)
    linea = s.entorno.linea(precio="11000.00", version_id=version)
    venta_id = _vender(
        cliente_http,
        s,
        headers,
        lineas=[linea],
        total=linea["importe_bruto"],
        lista_id=str(otra),
        lista_version_id=str(version),
        motivo_lista_id=str(s.entorno.motivo_lista_id),
    )

    detalle = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()

    assert detalle["lista_nombre"] == "Mayorista"
    assert detalle["version_id"] == str(version)
    assert detalle["motivo_lista"]["motivo_id"] == str(s.entorno.motivo_lista_id)
    assert detalle["motivo_lista"]["nombre"]


def test_syn07_el_detalle_trae_las_observaciones_de_la_venta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """SYN-07, STK-05: vender 60 con 48 de stock deja `STOCK_NEGATIVO` junto a su línea."""
    s = Sesion(sesion, permisos=PERMISOS_DE_SUPERVISOR)
    headers = s.entrar(cliente_http)
    linea = s.entorno.linea(cantidad=60)
    venta_id = _vender(cliente_http, s, headers, lineas=[linea], total=linea["importe_bruto"])

    detalle = cliente_http.get(f"{URL_VENTAS}/{venta_id}", headers=headers).json()

    (observacion,) = detalle["observaciones"]
    assert observacion["codigo"] == "STOCK_NEGATIVO"
    assert observacion["detalle"]["linea_id"] == linea["linea_id"]
    assert observacion["detalle"]["saldo_resultante"] == -12


def test_la_ubicacion_de_una_venta_historica_se_muestra_aunque_hoy_este_inactiva(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Decidido el 2026-10-20: lo histórico no se oculta por el estado actual de la ubicación."""
    s = Sesion(sesion)
    venta = sembrar(sesion, s)
    sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": s.entorno.org, "u": venta.ubicacion_id},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    lista = cliente_http.get(URL_VENTAS, headers=headers).json()
    detalle = cliente_http.get(f"{URL_VENTAS}/{venta.venta_id}", headers=headers).json()

    assert lista["items"][0]["ubicacion_id"] == str(venta.ubicacion_id)
    assert detalle["ubicacion_id"] == str(venta.ubicacion_id)
    assert detalle["ubicacion_nombre"]
