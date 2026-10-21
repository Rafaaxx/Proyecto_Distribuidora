"""Change 17, tarea 11.1: `GET /api/v1/clientes/opciones` y `GET /api/v1/clientes/{id}/saldo`.

Tabla de permisos aprobada por el usuario el 2026-10-16 (`design.md` D14, opción A): las dos
lecturas se abren con `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`; la ficha, el listado completo
y el estado de cuenta siguen exigiendo `GESTIONAR_CLIENTES` (el Vendedor recibe 403). Mismo
arnés HTTP que `test_cobranzas_api.py` (PostgreSQL real, login real).

Reglas citadas: CLI-02, CLI-03, CC-04, INV-03, INV-21, SEG-06, SEG-07 y `01` §19.
"""
# ruff: noqa: F811

from __future__ import annotations

from uuid import uuid4

from cuentas_corrientes_utiles import crear_cliente
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cobranzas_api import (  # noqa: F401
    Entorno,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)

URL = "/api/v1/clientes"
VENDEDOR = frozenset({"REGISTRAR_COBRANZA"})
ADMINISTRADOR_DE_CLIENTES = frozenset({"GESTIONAR_CLIENTES"})
SIN_PERMISO = frozenset({"GESTIONAR_CREDITO"})


# --- opciones (CLI-02, CLI-03, D14) ------------------------------------------------------


def test_el_vendedor_elige_cliente_sin_credito_ni_documento(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Vendedor elige cliente" (`01` §19, D14): solo identificador, nombre, código y
    estado."""
    entorno = Entorno(sesion, permisos=VENDEDOR)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL}/opciones", headers=headers)

    assert respuesta.status_code == 200
    (item,) = respuesta.json()["items"]
    assert item == {
        "id": str(entorno.cliente_id),
        "nombre": "Kiosco La Esquina",
        "codigo": None,
        "estado": "ACTIVO",
        "es_consumidor_final": False,
    }


def test_con_gestionar_clientes_tambien_se_leen_las_opciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D14: `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA` (triangulación del permiso)."""
    entorno = Entorno(sesion, permisos=ADMINISTRADOR_DE_CLIENTES)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL}/opciones", headers=headers)

    assert respuesta.status_code == 200
    assert [i["nombre"] for i in respuesta.json()["items"]] == ["Kiosco La Esquina"]


def test_el_selector_ofrece_activos_y_suspendidos_y_no_inactivos_ni_consumidor_final(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Requisito "Quien cobra elige el cliente": CLI-02 (estados) y CLI-03 (consumidor final)."""
    entorno = Entorno(sesion, permisos=VENDEDOR)
    crear_cliente(sesion, entorno.org, nombre="Bar El Sol", estado="SUSPENDIDO")
    crear_cliente(sesion, entorno.org, nombre="Almacén Don Pedro", estado="INACTIVO")
    crear_cliente(sesion, entorno.org, nombre="Consumidor final", es_consumidor_final=True)
    headers = entorno.entrar(cliente_http)

    items = cliente_http.get(f"{URL}/opciones", headers=headers).json()["items"]

    assert [(i["nombre"], i["estado"]) for i in items] == [
        ("Bar El Sol", "SUSPENDIDO"),
        ("Kiosco La Esquina", "ACTIVO"),
    ]


def test_con_incluir_consumidor_final_este_aparece_marcado_y_los_demas_no(
    cliente_http: TestClient, sesion: Session
) -> None:
    """CLI-03 y `design.md` D5/D21 (aprobado el 2026-10-20): la pantalla de venta pide el
    consumidor final con `incluir_consumidor_final=true` y lo reconoce por la marca; el selector
    de cobranzas, sin el parámetro, sigue sin ofrecerlo."""
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    crear_cliente(sesion, entorno.org, nombre="Consumidor final", es_consumidor_final=True)
    headers = entorno.entrar(cliente_http)

    con = cliente_http.get(f"{URL}/opciones?incluir_consumidor_final=true", headers=headers).json()
    sin = cliente_http.get(f"{URL}/opciones", headers=headers).json()

    assert [(i["nombre"], i["es_consumidor_final"]) for i in con["items"]] == [
        ("Consumidor final", True),
        ("Kiosco La Esquina", False),
    ]
    assert [i["nombre"] for i in sin["items"]] == ["Kiosco La Esquina"]


def test_las_opciones_se_buscan_por_texto_y_se_paginan(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=VENDEDOR)
    for nombre in ("Almacén Uno", "Almacén Dos", "Bar El Sol"):
        crear_cliente(sesion, entorno.org, nombre=nombre)
    headers = entorno.entrar(cliente_http)

    por_texto = cliente_http.get(f"{URL}/opciones?texto=alma", headers=headers).json()
    primera = cliente_http.get(f"{URL}/opciones?limite=3", headers=headers).json()
    segunda = cliente_http.get(
        f"{URL}/opciones?limite=3&cursor={primera['cursor_siguiente']}", headers=headers
    ).json()

    assert [i["nombre"] for i in por_texto["items"]] == ["Almacén Dos", "Almacén Uno"]
    assert [i["nombre"] for i in primera["items"]] == [
        "Almacén Dos",
        "Almacén Uno",
        "Bar El Sol",
    ]
    assert [i["nombre"] for i in segunda["items"]] == ["Kiosco La Esquina"]
    assert segunda["cursor_siguiente"] is None
    assert cliente_http.get(f"{URL}/opciones?limite=0", headers=headers).status_code == 422


def test_las_opciones_sin_permiso_responden_403_y_sin_sesion_401(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Sin permiso" (SEG-06)."""
    entorno = Entorno(sesion, permisos=SIN_PERMISO)
    headers = entorno.entrar(cliente_http)

    assert cliente_http.get(f"{URL}/opciones", headers=headers).status_code == 403
    assert cliente_http.get(f"{URL}/opciones").status_code == 401


def test_inv21_las_opciones_no_traen_clientes_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=VENDEDOR)
    ajeno = Entorno(sesion, permisos=VENDEDOR, usuario="otro1")
    crear_cliente(sesion, ajeno.org, nombre="Cliente Ajeno")
    headers = entorno.entrar(cliente_http)

    items = cliente_http.get(f"{URL}/opciones", headers=headers).json()["items"]

    assert [i["nombre"] for i in items] == ["Kiosco La Esquina"]


# --- saldo (CC-04, INV-03, INV-21, D14) --------------------------------------------------


def test_el_vendedor_ve_el_saldo_como_string(cliente_http: TestClient, sesion: Session) -> None:
    """Escenario "Vendedor elige cliente" (D14, CC-04, INV-03)."""
    entorno = Entorno(sesion, permisos=VENDEDOR)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL}/{entorno.cliente_id}/saldo", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"cliente_id": str(entorno.cliente_id), "saldo": "150000.00"}


def test_un_cliente_sin_movimientos_tiene_saldo_cero(
    cliente_http: TestClient, sesion: Session
) -> None:
    """CC-04: sin movimientos el saldo es `0.00`, con `GESTIONAR_CLIENTES`."""
    entorno = Entorno(sesion, permisos=ADMINISTRADOR_DE_CLIENTES)
    nuevo = crear_cliente(sesion, entorno.org, nombre="Cliente Nuevo")
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL}/{nuevo}/saldo", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json()["saldo"] == "0.00"


def test_el_saldo_sin_permiso_responde_403(cliente_http: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=SIN_PERMISO)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL}/{entorno.cliente_id}/saldo", headers=headers)

    assert respuesta.status_code == 403


def test_inv21_el_saldo_de_un_cliente_ajeno_o_inexistente_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Saldo de un cliente ajeno" (INV-21, SEG-07)."""
    entorno = Entorno(sesion, permisos=VENDEDOR)
    ajeno = Entorno(sesion, permisos=VENDEDOR, usuario="otro1")
    headers = entorno.entrar(cliente_http)

    de_otra_organizacion = cliente_http.get(f"{URL}/{ajeno.cliente_id}/saldo", headers=headers)
    inexistente = cliente_http.get(f"{URL}/{uuid4()}/saldo", headers=headers)

    assert de_otra_organizacion.status_code == 404
    assert inexistente.status_code == 404
    assert "150000" not in de_otra_organizacion.text


# --- lo que sigue exigiendo GESTIONAR_CLIENTES (D14) -------------------------------------


def test_el_vendedor_no_abre_la_cuenta_corriente_ni_la_ficha_ni_el_listado(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Vendedor no abre la cuenta corriente" (`01` §19)."""
    entorno = Entorno(sesion, permisos=VENDEDOR)
    headers = entorno.entrar(cliente_http)
    cliente_id = entorno.cliente_id

    assert (
        cliente_http.get(f"{URL}/{cliente_id}/cuenta-corriente", headers=headers).status_code == 403
    )
    assert cliente_http.get(f"{URL}/{cliente_id}", headers=headers).status_code == 403
    assert cliente_http.get(URL, headers=headers).status_code == 403
