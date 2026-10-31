"""Change 22a, tarea 3.3 (`design.md` D2; SYN-05, CRE-09, INV-06, SYN-02), contra PostgreSQL real.

El sobre que arma el teléfono (`shared/fixtures/sync/venta-confirmar-offline.json`), con sus
identificadores simbólicos sustituidos por los de una base de prueba (cliente, productos, lista,
regla de volumen, medios, jornada abierta de quien vende en su dispositivo), se envía tal cual a
`POST /api/v1/sync/comandos`: el servidor lo acepta con la observación
`EXCESO_CREDITO_AUTORIZADO_OFFLINE` (no como malformado) y un segundo envío igual devuelve el
resultado original sin registrar otra venta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import test_ventas_offline as _base
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import Sesion

# Fixtures de la suite de ventas sin conexión (cliente HTTP, sesión real y limpieza posterior).
cliente_http = _base.cliente_http
sesion = _base.sesion
_limpiar_datos_confirmados = _base._limpiar_datos_confirmados  # noqa: SLF001

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "venta-confirmar-offline.json"
)
URL_LOTE = "/api/v1/sync/comandos"


def _contar(sesion_bd: Session, tabla: str, organizacion_id: Any) -> int:
    return int(
        sesion_bd.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
            {"o": organizacion_id},
        ).scalar_one()
    )


def _sobre_con_datos_reales(
    s: Sesion, dispositivo_id: Any, jornada_id: Any, regla_id: Any
) -> dict[str, Any]:
    e = s.entorno
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))
    reales = {
        "{{operation_id}}": str(uuid4()),
        "{{usuario_id}}": str(e.usuario_id),
        "{{dispositivo_id}}": str(dispositivo_id),
        "{{jornada_id}}": str(jornada_id),
        "{{numero}}": f"{s.prefijo}-000001",
        "{{venta_id}}": str(uuid4()),
        "{{cliente_id}}": str(e.cliente_id),
        "{{lista_version_id}}": str(e.version_id),
        "{{producto_id}}": str(e.vino_id),
        "{{presentacion_caja_id}}": str(e.caja_id),
        "{{presentacion_botella_id}}": str(e.botella_id),
        "{{linea_caja_id}}": str(uuid4()),
        "{{linea_botella_id}}": str(uuid4()),
        "{{regla_id}}": str(regla_id),
        "{{cobranza_id}}": str(uuid4()),
        "{{medio_efectivo_id}}": str(e.efectivo_id),
        "{{medio_transferencia_id}}": str(e.transferencia_id),
    }
    assert set(reales) == set(crudo["simbolos"]), (
        "el fixture declara símbolos que la prueba no conoce"
    )
    texto = json.dumps(crudo["sobre"])
    for simbolo, valor in reales.items():
        texto = texto.replace(simbolo, valor)
    sobre: dict[str, Any] = json.loads(texto)
    return sobre


def _preparar(
    cliente_http: TestClient, sesion: Session
) -> tuple[Sesion, dict[str, str], dict[str, Any]]:
    s = Sesion(sesion)
    e = s.entorno
    e.configurar(descuento_manual_habilitado=True)
    # El cliente real coincide con lo que vio el teléfono: límite $150.000 y política AUTORIZAR.
    e.datos_de_credito(limite="150000.00", politica="AUTORIZAR")
    # Regla de volumen del 5 % sobre toda la venta (el fixture tiene 2,5 cajas equivalentes).
    regla_id = e.crear_regla(umbral="2")
    headers = s.entrar(cliente_http)
    dispositivo_id = sesion.execute(
        text("SELECT id FROM dispositivo WHERE organizacion_id = :o AND prefijo = :p"),
        {"o": e.org, "p": s.prefijo},
    ).scalar_one()
    camioneta_id = _base._camioneta(e, stock=48)
    jornada_id = e.crear_jornada(ubicacion_id=camioneta_id, dispositivo_id=dispositivo_id)
    return s, headers, _sobre_con_datos_reales(s, dispositivo_id, jornada_id, regla_id)


def test_syn05_el_lote_acepta_el_sobre_del_telefono_y_el_reenvio_no_duplica(
    cliente_http: TestClient,
    sesion: Session,
) -> None:
    s, headers, sobre = _preparar(cliente_http, sesion)
    e = s.entorno

    primera = cliente_http.post(URL_LOTE, json={"items": [sobre]}, headers=headers)

    assert primera.status_code == 200, primera.text
    (resultado,) = primera.json()["resultados"]
    assert resultado["operation_id"] == sobre["operation_id"]
    assert resultado["error_codigo"] is None
    assert resultado["estado"] == "ACEPTADO_CON_OBSERVACIONES"
    codigos = [
        fila[0]
        for fila in sesion.execute(
            text("SELECT codigo FROM observacion WHERE organizacion_id = :o ORDER BY codigo"),
            {"o": e.org},
        ).all()
    ]
    assert codigos == ["EXCESO_CREDITO_AUTORIZADO_OFFLINE"]
    assert _contar(sesion, "venta", e.org) == 1
    assert _contar(sesion, "cobranza", e.org) == 1

    # INV-06, SYN-02: el mismo sobre otra vez devuelve el resultado original, sin otra venta.
    segunda = cliente_http.post(URL_LOTE, json={"items": [sobre]}, headers=headers)

    assert segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert _contar(sesion, "venta", e.org) == 1
    assert _contar(sesion, "cobranza", e.org) == 1


def test_cre09_el_contrato_detecta_un_sobre_incoherente_consigo_mismo(
    cliente_http: TestClient,
    sesion: Session,
) -> None:
    """Contrapunto: con `SIN_EXCESO` y números que dan exceso, el servidor lo rechaza como
    malformado (`CREDITO_INCONSISTENTE`) y no registra ninguna venta; la prueba de arriba no
    pasa por casualidad."""
    s, headers, sobre = _preparar(cliente_http, sesion)
    sobre["contenido"]["credito"]["resolucion"] = "SIN_EXCESO"

    respuesta = cliente_http.post(URL_LOTE, json={"items": [sobre]}, headers=headers)

    (resultado,) = respuesta.json()["resultados"]
    assert (resultado["estado"], resultado["error_codigo"]) == (
        "RECHAZADO",
        "CREDITO_INCONSISTENTE",
    )
    assert _contar(sesion, "venta", s.entorno.org) == 0


def test_adr056_el_lote_rechaza_un_sobre_con_credenciales_sin_guardar_nada(
    cliente_http: TestClient,
    sesion: Session,
) -> None:
    s, headers, sobre = _preparar(cliente_http, sesion)
    sobre["credenciales"] = [{"autorizador_id": str(uuid4()), "pin": "123456"}]

    respuesta = cliente_http.post(URL_LOTE, json={"items": [sobre]}, headers=headers)

    assert respuesta.status_code == 422
    assert _contar(sesion, "venta", s.entorno.org) == 0
