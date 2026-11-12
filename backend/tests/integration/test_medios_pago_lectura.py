"""Tarea 5.1 (change 17b; `design.md` D6): `GET /api/v1/configuracion/medios-pago/todos` lee los
medios activos e inactivos para la administración; `GET /configuracion/medios-pago` queda igual
(solo activos, cualquier sesión). Reglas citadas: TR-08, INV-21, SEG-06, CAT-05.
"""

from __future__ import annotations

import medios_pago_utiles as utiles
from fastapi.testclient import TestClient
from medios_pago_utiles import (
    URL_MEDIOS,
    Entorno,
)
from sqlalchemy.orm import Session

# Las fixtures viven en `medios_pago_utiles.py`; se enlazan por asignación (no por `import`) para
# que pytest las encuentre sin que `ruff` las vea como redefiniciones.
_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion


URL_TODOS = f"{URL_MEDIOS}/todos"


def test_la_administracion_lee_activos_e_inactivos_ordenados_por_nombre(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.dar_de_baja_en_sql("Billetera")
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.get(URL_TODOS, headers=headers)

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert [m["nombre"] for m in items] == [
        "Billetera",
        "Cheque",
        "Efectivo",
        "Tarjeta",
        "Transferencia",
    ]
    por_nombre = {m["nombre"]: m for m in items}
    assert por_nombre["Billetera"]["activo"] is False
    assert por_nombre["Efectivo"]["activo"] is True
    assert por_nombre["Transferencia"]["requiere_referencia"] is True
    assert por_nombre["Efectivo"]["requiere_referencia"] is False
    assert all(m["actualizado_en"] for m in items)
    assert all("organizacion_id" not in m for m in items)


def test_solo_lee_los_medios_de_la_organizacion_del_token(
    cliente_http: TestClient, sesion: Session
) -> None:
    # INV-21: la organización sale del token.
    propia = Entorno(sesion)
    ajena = Entorno(sesion, con_medios=False)
    ajena.crear_medio("Solo de la otra", requiere_referencia=False)
    headers = propia.entrar(cliente_http)

    items = cliente_http.get(URL_TODOS, headers=headers).json()["items"]

    assert len(items) == 5
    assert "Solo de la otra" not in [m["nombre"] for m in items]


def test_sin_admin_configuracion_responde_403(cliente_http: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion)

    for usuario in ("cobrador1", "nadie1"):
        headers = entorno.entrar(cliente_http, usuario)
        respuesta = cliente_http.get(URL_TODOS, headers=headers)
        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_sin_sesion_responde_401(cliente_http: TestClient, sesion: Session) -> None:
    Entorno(sesion)

    assert cliente_http.get(URL_TODOS).status_code == 401


def test_la_lectura_de_activos_sigue_igual_para_cualquier_sesion(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.dar_de_baja_en_sql("Billetera")
    headers = entorno.entrar(cliente_http, "nadie1")

    respuesta = cliente_http.get(URL_MEDIOS, headers=headers)

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert [m["nombre"] for m in items] == ["Cheque", "Efectivo", "Tarjeta", "Transferencia"]
    assert set(items[0]) == {"id", "nombre", "requiere_referencia"}
