"""Tarea 9.3 (change 18a, `design.md` D19): lecturas existentes abiertas a `VENDER`, solo lectura.

Tabla aprobada por el usuario el 2026-10-20: `GET /clientes/opciones`, `GET /clientes/{id}/saldo`,
`GET /precios/listas/opciones` y `GET /stock/ubicaciones` aceptan `VENDER`. Siguen cerradas para
quien solo vende: el estado de cuenta, la administración de listas, los borradores, el kardex y
los saldos de una ubicación.

Precisión 1 del 2026-10-20: cuando el usuario llega a `GET /stock/ubicaciones` solo por `VENDER`
(sin `TRANSFERIR_STOCK` ni `REGISTRAR_COMPRA`), el servidor devuelve SIEMPRE solo las ubicaciones
activas e ignora `activo=false`, en silencio. Precisión 2: la información de jornada y toma sigue
visible para ese usuario.

Reglas citadas: CLI-01, CC-07, PRC-20, STK-09, INV-16, INV-21, SEG-06, SEG-07.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

SOLO_VENDE = frozenset({"VENDER"})
SOLO_GESTIONA_CLIENTES = frozenset({"GESTIONAR_CLIENTES"})


# --- clientes: opciones y saldo se abren a VENDER; el estado de cuenta, no ---------------------


def test_cli01_el_vendedor_lee_las_opciones_de_clientes_y_el_saldo(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Con solo `VENDER`: el selector y el saldo (`150000.00`) responden 200."""
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)

    opciones = cliente_http.get("/api/v1/clientes/opciones", headers=headers)
    saldo = cliente_http.get(f"/api/v1/clientes/{s.entorno.cliente_id}/saldo", headers=headers)

    assert opciones.status_code == 200
    assert [i["nombre"] for i in opciones.json()["items"]] == ["Kiosco La Esquina"]
    assert saldo.status_code == 200
    assert saldo.json() == {"cliente_id": str(s.entorno.cliente_id), "saldo": "150000.00"}


def test_cc07_el_vendedor_no_ve_el_estado_de_cuenta_ni_la_ficha_ni_el_listado_de_clientes(
    cliente_http: TestClient, sesion: Session
) -> None:
    """CC-07, SEG-06: lo que no se abrió sigue en 403 para quien solo tiene `VENDER`."""
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)
    cliente = s.entorno.cliente_id

    assert (
        cliente_http.get(
            f"/api/v1/clientes/{cliente}/cuenta-corriente", headers=headers
        ).status_code
        == 403
    )
    assert cliente_http.get(f"/api/v1/clientes/{cliente}", headers=headers).status_code == 403
    assert cliente_http.get("/api/v1/clientes", headers=headers).status_code == 403


def test_seg07_el_saldo_de_un_cliente_ajeno_responde_404_tambien_con_vender(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)

    respuesta = cliente_http.get(
        f"/api/v1/clientes/{ajena.entorno.cliente_id}/saldo", headers=headers
    )

    assert respuesta.status_code == 404


def test_seg06_sin_vender_ni_los_permisos_previos_las_opciones_y_el_saldo_siguen_en_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: `GESTIONAR_CREDITO` no abre el selector; los permisos previos lo siguen
    abriendo (`GESTIONAR_CLIENTES` y `REGISTRAR_COBRANZA`)."""
    s = Sesion(sesion)
    sin = usuario_con(cliente_http, sesion, s, frozenset({"GESTIONAR_CREDITO"}))
    gestor = usuario_con(cliente_http, sesion, s, SOLO_GESTIONA_CLIENTES)
    cobrador = usuario_con(cliente_http, sesion, s, frozenset({"REGISTRAR_COBRANZA"}))

    assert cliente_http.get("/api/v1/clientes/opciones", headers=sin).status_code == 403
    assert cliente_http.get("/api/v1/clientes/opciones", headers=gestor).status_code == 200
    assert cliente_http.get("/api/v1/clientes/opciones", headers=cobrador).status_code == 200


# --- listas de precios: solo las opciones ------------------------------------------------------


def test_prc20_el_vendedor_lee_las_opciones_de_listas_pero_no_administra_listas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """PRC-20: `GET /precios/listas/opciones` responde 200; el listado de administración, el
    detalle, las reglas, el borrador y las versiones siguen en 403."""
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)
    lista = s.entorno.lista_id

    opciones = cliente_http.get("/api/v1/precios/listas/opciones", headers=headers)

    assert opciones.status_code == 200
    assert str(lista) in {i["id"] for i in opciones.json()["items"]}
    for ruta in (
        "/api/v1/precios/listas",
        f"/api/v1/precios/listas/{lista}",
        f"/api/v1/precios/listas/{lista}/reglas",
        f"/api/v1/precios/listas/{lista}/borrador",
        f"/api/v1/precios/listas/{lista}/versiones",
        f"/api/v1/precios/listas/{lista}/vigente",
    ):
        assert cliente_http.get(ruta, headers=headers).status_code == 403, ruta


# --- ubicaciones: solo activas para quien llega por VENDER -------------------------------------


def _inactiva(sesion: Session, s: Sesion, nombre: str) -> str:
    ubicacion = crear_ubicacion_sql(sesion, s.entorno.org, nombre=nombre, activo=False)
    sesion.commit()
    return str(ubicacion)


def test_stk09_con_solo_vender_las_ubicaciones_son_siempre_solo_las_activas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Precisión 1: `activo=false` se ignora en silencio (sin error) y no devuelve las inactivas."""
    s = Sesion(sesion)
    inactiva = _inactiva(sesion, s, "Depósito cerrado")
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)

    sin_filtro = cliente_http.get("/api/v1/stock/ubicaciones", headers=headers)
    pidiendo_inactivas = cliente_http.get(
        "/api/v1/stock/ubicaciones", params={"activo": "false"}, headers=headers
    )

    assert sin_filtro.status_code == 200
    assert pidiendo_inactivas.status_code == 200
    for respuesta in (sin_filtro, pidiendo_inactivas):
        items = respuesta.json()["items"]
        assert items and all(i["activo"] for i in items)
        assert inactiva not in {i["id"] for i in items}
        assert str(s.entorno.deposito_id) in {i["id"] for i in items}


def test_stk09_quien_tiene_transferir_stock_o_registrar_compra_conserva_el_comportamiento_actual(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación de la precisión 1: con alguno de los dos permisos de siempre, `activo=false`
    sigue devolviendo las inactivas, aunque además tenga `VENDER`."""
    s = Sesion(sesion)
    inactiva = _inactiva(sesion, s, "Depósito cerrado")
    transfiere = usuario_con(cliente_http, sesion, s, frozenset({"TRANSFERIR_STOCK"}))
    compra_y_vende = usuario_con(cliente_http, sesion, s, frozenset({"REGISTRAR_COMPRA", "VENDER"}))

    for headers in (transfiere, compra_y_vende):
        respuesta = cliente_http.get(
            "/api/v1/stock/ubicaciones", params={"activo": "false"}, headers=headers
        )
        assert respuesta.status_code == 200
        assert [i["id"] for i in respuesta.json()["items"]] == [inactiva]


def test_inv16_la_toma_de_la_ubicacion_sigue_visible_para_quien_solo_vende(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Precisión 2: quién tiene tomada cada ubicación se ve igual."""
    s = Sesion(sesion)
    jornada = s.entorno.crear_jornada()
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)

    items = cliente_http.get("/api/v1/stock/ubicaciones", headers=headers).json()["items"]

    tomadas = [i for i in items if i["jornada"] is not None]
    assert [t["jornada"]["id"] for t in tomadas] == [str(jornada)]
    assert tomadas[0]["jornada"]["estado"] == "ABIERTA"


def test_seg06_el_vendedor_no_lee_saldos_kardex_ni_el_resto_del_stock(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Quedan cerrados: `/stock/ubicaciones/{id}/saldos`, el kardex, transferencias y ajustes."""
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_VENDE)
    deposito = s.entorno.deposito_id

    assert (
        cliente_http.get(
            f"/api/v1/stock/ubicaciones/{deposito}/saldos", headers=headers
        ).status_code
        == 403
    )
    assert (
        cliente_http.get(
            "/api/v1/stock/kardex",
            params={"producto_id": str(s.entorno.vino_id), "ubicacion_id": str(deposito)},
            headers=headers,
        ).status_code
        == 403
    )
    assert cliente_http.get("/api/v1/stock/transferencias", headers=headers).status_code == 403
    assert cliente_http.get("/api/v1/stock/ajustes", headers=headers).status_code == 403


def test_seg06_sin_vender_las_ubicaciones_siguen_en_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_GESTIONA_CLIENTES)

    assert cliente_http.get("/api/v1/stock/ubicaciones", headers=headers).status_code == 403
