"""Tarea 10.1 (change 25; spec `sync/observaciones`, requisito "Una venta sin conexión de un
producto desactivado se acepta con observación"; `design.md` D10), contra PostgreSQL real y por
`procesar_lote`.

Sin conexión, una línea cuyo producto o presentación está inactivo al sincronizar se acepta
(la mercadería ya se entregó, INV-17) con una `PRODUCTO_DESACTIVADO` por línea; con conexión el
rechazo sigue igual y el doble envío no duplica la observación.

Reglas citadas: SYN-05, SYN-07, SYN-02, INV-17, INV-06.
"""

# ruff: noqa: F811  (la fixture importada se pide por nombre de parámetro)

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from test_ventas_offline import Ruta, _observaciones, entorno, lote  # noqa: F401
from ventas_confirmar_utiles import EntornoVenta

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _desactivar(entorno: EntornoVenta, tabla: str, id_: UUID) -> None:
    entorno.sesion.execute(
        text(f"UPDATE {tabla} SET activo = false WHERE organizacion_id = :o AND id = :i"),
        {"o": entorno.org, "i": id_},
    )
    entorno.sesion.commit()


def test_syn07_producto_desactivado_se_acepta_con_una_observacion_por_linea(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    _desactivar(entorno, "producto", entorno.vino_id)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    (obs,) = [o for o in _observaciones(entorno) if o.codigo == "PRODUCTO_DESACTIVADO"]
    assert obs.detalle is not None
    assert obs.detalle["producto_id"] == str(entorno.vino_id)
    assert obs.detalle["presentacion_id"] == str(entorno.botella_id)
    assert obs.detalle["inactivo"] == "PRODUCTO"
    assert "linea_id" in obs.detalle


def test_syn07_presentacion_desactivada_indica_la_presentacion(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    _desactivar(entorno, "presentacion", entorno.botella_id)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (obs,) = [o for o in _observaciones(entorno) if o.codigo == "PRODUCTO_DESACTIVADO"]
    assert obs.detalle is not None and obs.detalle["inactivo"] == "PRESENTACION"


def test_syn07_un_producto_activo_no_observa(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)

    ruta.enviar()

    assert [o for o in _observaciones(entorno) if o.codigo == "PRODUCTO_DESACTIVADO"] == []


def test_syn02_inv06_el_doble_envio_no_duplica_la_observacion(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    _desactivar(entorno, "producto", entorno.vino_id)
    item = ruta.item()

    lote(entorno, item)
    segundo = lote(entorno, item)[item.operation_id]

    assert segundo.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len([o for o in _observaciones(entorno) if o.codigo == "PRODUCTO_DESACTIVADO"]) == 1


def test_inv17_con_conexion_el_producto_desactivado_se_rechaza_igual(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    _desactivar(entorno, "producto", entorno.vino_id)
    item = ruta.item(modo="ONLINE")

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "RECHAZADO"
    assert [o for o in _observaciones(entorno) if o.codigo == "PRODUCTO_DESACTIVADO"] == []
