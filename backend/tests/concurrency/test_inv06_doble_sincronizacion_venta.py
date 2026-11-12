"""Change 22b, tarea 13.1 (`design.md` D12; specs `sync/motor-de-sincronizacion`, escenario
"Dos lotes simultáneos con la misma venta"; INV-06, SYN-02; `00` §9 criterio 8), contra PostgreSQL
real (Testcontainers) y con commits reales.

Dos hilos (dos "pestañas" o dos reintentos del teléfono) envían a la vez
`POST /api/v1/sync/comandos` con el mismo sobre del fixture de contrato
(`shared/fixtures/sync/venta-confirmar-offline.json`, identificadores sustituidos por los de la
base). Cada hilo tiene su propio cliente HTTP y su propia transacción en el servidor; no hay
rollback externo: lo que se compara es lo confirmado, leído desde una sesión nueva.

Es una prueba de caracterización: el servidor ya garantiza INV-06 (idempotencia por `operation_id`
bajo la clave única de `comando`, change 18a/22a); no hizo falta tocar código de producción.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_contrato_sobre_venta_offline import URL_LOTE, _preparar
from test_ventas_offline import _limpiar_datos_confirmados, cliente_http, sesion

__all__ = ["_limpiar_datos_confirmados", "cliente_http", "sesion"]

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

ESPERA_MAXIMA = 60
REPETICIONES = 3


def _uno(sesion_bd: Session, sql: str, **parametros: Any) -> Any:
    return sesion_bd.execute(text(sql), parametros).scalar_one()


def _enviar_a_la_vez(
    cliente_http: TestClient, headers: dict[str, str], sobre: dict[str, Any]
) -> list[dict[str, Any]]:
    """Dos hilos, cada uno con su cliente, arrancan juntos con el mismo sobre."""
    barrera = threading.Barrier(2)
    respuestas: dict[int, dict[str, Any]] = {}
    errores: dict[int, BaseException] = {}

    def _worker(indice: int) -> None:
        cliente = TestClient(cliente_http.app)
        try:
            barrera.wait(timeout=10)
            respuesta = cliente.post(URL_LOTE, json={"items": [sobre]}, headers=headers)
            assert respuesta.status_code == 200, respuesta.text
            respuestas[indice] = respuesta.json()
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            errores[indice] = error

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA)
    assert not any(hilo.is_alive() for hilo in hilos), "Un hilo quedó colgado."
    assert not errores, errores
    return [respuestas[0], respuestas[1]]


@pytest.mark.parametrize("repeticion", range(REPETICIONES))
def test_inv06_syn02_dos_lotes_simultaneos_con_la_misma_venta_tienen_un_solo_efecto(
    cliente_http: TestClient, sesion: Session, repeticion: int
) -> None:
    s, headers, sobre = _preparar(cliente_http, sesion)
    sesion.commit()  # el armado queda confirmado: los hilos lo ven desde sus conexiones
    e = s.entorno
    org = e.org

    primera, segunda = _enviar_a_la_vez(cliente_http, headers, sobre)

    # Los dos envíos reciben el mismo resultado (el original).
    assert primera == segunda
    (resultado,) = primera["resultados"]
    assert resultado["operation_id"] == sobre["operation_id"]
    assert resultado["estado"] == "ACEPTADO_CON_OBSERVACIONES"
    assert resultado["error_codigo"] is None

    # Una sola fila de venta, de comando y de cobranza.
    sesion.expire_all()
    assert _uno(sesion, "SELECT count(*) FROM venta WHERE organizacion_id = :o", o=org) == 1
    assert (
        _uno(
            sesion,
            "SELECT count(*) FROM comando WHERE organizacion_id = :o AND operation_id = :op",
            o=org,
            op=sobre["operation_id"],
        )
        == 1
    )
    assert _uno(sesion, "SELECT count(*) FROM cobranza WHERE organizacion_id = :o", o=org) == 1

    # El stock de la camioneta baja una sola vez: 2 cajas x6 + 3 botellas = 15 (de 48 a 33).
    assert (
        _uno(
            sesion,
            "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o AND tipo = 'VENTA'",
            o=org,
        )
        == 2
    )
    assert (
        _uno(
            sesion,
            "SELECT cantidad_base FROM stock_saldo WHERE organizacion_id = :o AND producto_id = :p "
            "AND ubicacion_id = (SELECT ubicacion_id FROM jornada WHERE organizacion_id = :o)",
            o=org,
            p=e.vino_id,
        )
        == 33
    )

    # El saldo del cliente sube una sola vez: 150000.00 + 29687.50 - 20000.00.
    assert _uno(
        sesion,
        "SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o AND cliente_id = :c",
        o=org,
        c=e.cliente_id,
    ) == Decimal("159687.50")

    # Costo congelado y utilidad de un solo envío: 12 y 3 unidades a $1.050.
    costos = sorted(
        sesion.execute(
            text(
                "SELECT costo_unitario, costo_total FROM venta_linea "
                "WHERE organizacion_id = :o ORDER BY costo_total"
            ),
            {"o": org},
        ).all()
    )
    assert [(c.costo_unitario, c.costo_total) for c in costos] == [
        (Decimal("1050.000000"), Decimal("3150.00")),
        (Decimal("1050.000000"), Decimal("12600.00")),
    ]
    total_neto = _uno(sesion, "SELECT total_neto FROM venta WHERE organizacion_id = :o", o=org)
    costo = _uno(
        sesion, "SELECT sum(costo_total) FROM venta_linea WHERE organizacion_id = :o", o=org
    )
    assert costo == Decimal("15750.00")
    assert total_neto - costo == Decimal("29687.50") - Decimal("15750.00")
