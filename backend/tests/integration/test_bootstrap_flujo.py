"""Change 21, tarea 17.1: el flujo completo del bootstrap por HTTP, con PostgreSQL real.

`vendedor` abre la jornada por el comando `JORNADA_ABRIR`, pide el bootstrap y recibe la jornada,
el stock cargado antes en la ubicación, su cartera y la versión de lista vigente; una versión
programada que se publica llega en el pedido siguiente; liberada la jornada, el bootstrap
responde `JORNADA_REQUERIDA`.

Reglas citadas: RUT-03, RUT-04, SYN-11, PRC-20, INV-21, ADR-006, ADR-062.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_ubicacion_sql
from test_sync_bootstrap import (  # noqa: F401  (fixtures y ayudas reutilizadas)
    URL,
    Escenario,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)


def _con_op(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Operation-Id": str(uuid4())}


def test_rut03_flujo_abrir_pedir_publicar_version_y_liberar(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario = Escenario(sesion)
    e = escenario.entorno
    e.permitir("ABRIR_JORNADA", "LIBERAR_UBICACION")
    camioneta = crear_ubicacion_sql(
        sesion, escenario.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    e.comprar(e.vino_id, 120, "1000", ubicacion_id=camioneta)  # stock cargado antes de abrir
    motivo = crear_motivo_sql(sesion, escenario.org, ambito="LIBERACION_JORNADA")
    sesion.commit()
    headers = escenario.entrar(cliente_http)

    # sin jornada: el bootstrap no responde datos
    assert cliente_http.get(URL, headers=headers).json()["codigo"] == "JORNADA_REQUERIDA"

    # abrir por el comando y pedir el bootstrap
    abierta = cliente_http.post(
        "/api/v1/stock/jornadas",
        json={"ubicacion_id": str(camioneta)},
        headers=_con_op(headers),
    )
    assert abierta.status_code == 201, abierta.text
    primero = escenario.pedir(cliente_http, headers)

    assert primero["sesion"]["jornada"]["id"] == abierta.json()["id"]
    assert primero["sesion"]["jornada"]["ubicacion_nombre"] == "Camioneta 1"
    assert primero["stock"] == [{"producto_id": str(e.vino_id), "cantidad_base": 120}]
    assert primero["sesion"]["usuario"]["id"] == str(escenario.usuario_id)
    assert len(primero["clientes"]) >= 1
    lista = next(item for item in primero["listas"] if item["id"] == str(e.lista_id))
    assert [v["numero"] for v in lista["versiones"]] == [1]

    # se publica una versión programada: el bootstrap siguiente la trae
    e.crear_version(
        e.lista_id,
        2,
        datetime.now(UTC) + timedelta(days=2),
        precio_vino="9999",
    )
    sesion.commit()
    segundo = escenario.pedir(cliente_http, headers)
    lista = next(item for item in segundo["listas"] if item["id"] == str(e.lista_id))
    assert [v["numero"] for v in lista["versiones"]] == [1, 2]

    # se libera la jornada: el bootstrap responde JORNADA_REQUERIDA
    liberada = cliente_http.post(
        f"/api/v1/stock/jornadas/{abierta.json()['id']}/liberacion",
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )
    assert liberada.status_code == 200, liberada.text
    respuesta = cliente_http.get(URL, headers=headers)
    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "JORNADA_REQUERIDA"
