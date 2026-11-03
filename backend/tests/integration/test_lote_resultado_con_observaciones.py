"""Change 22c, tarea 2.1 (spec `sync/lote-de-comandos`, requisito "El servidor devuelve un resultado
por comando"; `design.md` D3): cada resultado del lote trae las observaciones del propio comando
(código, tipo e identificador de la operación observada y detalle), también en el reenvío.

Nivel de servicio (`procesar_lote`, `db_session`) con ventas reales sin conexión, y un caso por
HTTP (`POST /api/v1/sync/comandos`) para el contrato de la respuesta.

Reglas citadas: SYN-04, SYN-07, SYN-02, INV-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_sync_bootstrap import (  # noqa: F401  (fixtures y ayudas reutilizadas)
    Escenario,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from test_ventas_offline import Ruta, _observaciones, lote
from ventas_confirmar_utiles import EntornoVenta

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def _con_medio_desactivado(entorno: EntornoVenta) -> dict[str, Any]:
    """Una cobranza de $5.000,00 con un medio que la administración desactivó después del
    bootstrap."""
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    entorno.sesion.commit()
    entorno.desactivar_medio(billetera)
    return entorno.cobranza((billetera, "5000.00", None))


def test_syn07_una_venta_con_stock_negativo_y_medio_inactivo_trae_las_dos_observaciones(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Venta sin conexión con observaciones": 8 botellas sobre 5 y un medio dado de
    baja. `STOCK_NEGATIVO` sobre la venta con el producto en el detalle y `MEDIO_INACTIVO` sobre
    la cobranza con el medio y el importe."""
    ruta = Ruta(entorno, stock=5)
    cobranza = _con_medio_desactivado(entorno)
    item = ruta.item(ruta.contenido(entorno.linea(cantidad=8), cobranza=cobranza))

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (cobrada,) = entorno.cobranzas()
    por_codigo = {o.codigo: o for o in resultado.observaciones}
    assert sorted(por_codigo) == ["MEDIO_INACTIVO", "STOCK_NEGATIVO"]
    stock = por_codigo["STOCK_NEGATIVO"]
    assert (stock.operacion_tipo, stock.operacion_id) == ("VENTA", venta.id)
    assert stock.detalle is not None
    assert stock.detalle["producto_id"] == str(entorno.vino_id)
    medio = por_codigo["MEDIO_INACTIVO"]
    assert (medio.operacion_tipo, medio.operacion_id) == ("COBRANZA", cobrada.id)
    assert medio.detalle is not None
    assert medio.detalle["importe"] == "5000.00"


def test_syn04_aceptada_sin_observaciones_y_rechazada_traen_la_lista_vacia(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Resultado sin observaciones": una venta limpia y otra rechazada por totales."""
    ruta = Ruta(entorno)
    limpia = ruta.item(secuencia=1)
    malformada = ruta.item(ruta.contenido(total="1.00"), secuencia=2)

    resultados = lote(entorno, limpia, malformada)

    assert (
        resultados[limpia.operation_id].estado,
        resultados[limpia.operation_id].observaciones,
    ) == (
        "ACEPTADO",
        (),
    )
    rechazada = resultados[malformada.operation_id]
    assert (rechazada.estado, rechazada.error_codigo) == ("RECHAZADO", "TOTALES_INCONSISTENTES")
    assert rechazada.observaciones == ()


def test_syn02_el_reenvio_devuelve_las_mismas_observaciones_y_no_registra_otras(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Reenvío de un comando con observaciones", por INV-06."""
    ruta = Ruta(entorno, stock=5)
    item = ruta.item(ruta.contenido(entorno.linea(cantidad=8)))
    primero = lote(entorno, item)[item.operation_id]

    reenvio = lote(entorno, item)[item.operation_id]

    assert [o.codigo for o in primero.observaciones] == ["STOCK_NEGATIVO"]
    assert reenvio.observaciones == primero.observaciones
    assert len(_observaciones(entorno)) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == -3


def test_syn07_cada_resultado_trae_solo_las_observaciones_de_su_comando(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: dos ventas en el mismo lote, solo la segunda deja stock negativo."""
    ruta = Ruta(entorno, stock=20)
    primera = ruta.item(ruta.contenido(entorno.linea(cantidad=6)), secuencia=1)
    segunda = ruta.item(ruta.contenido(entorno.linea(cantidad=20)), secuencia=2)

    resultados = lote(entorno, primera, segunda)

    assert resultados[primera.operation_id].observaciones == ()
    assert [o.codigo for o in resultados[segunda.operation_id].observaciones] == ["STOCK_NEGATIVO"]
    (observada,) = (v for v in entorno.ventas() if v.operation_id == segunda.operation_id)
    assert resultados[segunda.operation_id].observaciones[0].operacion_id == observada.id


def test_syn04_por_http_la_respuesta_lleva_la_lista_de_observaciones_de_cada_comando(
    cliente_http: TestClient, sesion: Session
) -> None:
    """El contrato de `POST /api/v1/sync/comandos`: `observaciones` en cada ítem de la respuesta
    (vacía donde no hay), con `operacion_tipo`, `operacion_id`, `codigo` y `detalle`."""
    escenario = Escenario(sesion)
    entorno = escenario.entorno
    escenario.dispositivo_id = entorno.dispositivo_id
    ruta = Ruta(entorno, stock=5)
    headers = escenario.entrar(cliente_http)
    observada = ruta.item(ruta.contenido(entorno.linea(cantidad=8)), secuencia=1)
    malformada = ruta.item(ruta.contenido(total="1.00"), secuencia=2)

    respuesta = cliente_http.post(
        "/api/v1/sync/comandos",
        headers=headers,
        json={
            "items": [
                {
                    "operation_id": str(item.operation_id),
                    "tipo": item.tipo,
                    "version": item.version,
                    "modo": item.modo,
                    "usuario_id": str(item.usuario_id),
                    "dispositivo_id": str(item.dispositivo_id),
                    "occurred_at": item.occurred_at.isoformat(),
                    "secuencia": item.secuencia,
                    "app_version": item.app_version,
                    "contenido": item.contenido,
                    "jornada_id": str(item.jornada_id),
                }
                for item in (observada, malformada)
            ]
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    por_operacion = {r["operation_id"]: r for r in respuesta.json()["resultados"]}
    (con_observacion,) = por_operacion[str(observada.operation_id)]["observaciones"]
    assert con_observacion["codigo"] == "STOCK_NEGATIVO"
    assert con_observacion["operacion_tipo"] == "VENTA"
    assert set(con_observacion) == {"codigo", "operacion_tipo", "operacion_id", "detalle"}
    assert por_operacion[str(malformada.operation_id)]["observaciones"] == []
