"""Change 20b, tarea 9.3 (`design.md` D14): la cartera ordena lo que se ofrece, no lo permitido.

Una venta y una cobranza con conexión a un cliente asignado a OTRO vendedor, o fuera de la cartera
de quien opera, se aceptan sin rechazo ni observación (el comando no consulta la cartera).

Reglas citadas: `01` §19, SYN-05, INV-17.
"""

from __future__ import annotations

import pytest
from cobranzas_utiles import Entorno as EntornoCobranza
from cuentas_corrientes_utiles import crear_cliente, crear_usuario_y_dispositivo
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def _fuera_de_la_cartera(entorno: EntornoVenta) -> None:
    """El usuario que opera tiene un cliente propio; el cliente del entorno es de otro vendedor."""
    otro_vendedor = entorno.crear_usuario(frozenset({"VENDER"}))
    propio = crear_cliente(entorno.sesion, entorno.org, nombre="Cliente propio")
    entorno.actualizar_cliente(entorno.cliente_id, vendedor_id=otro_vendedor)
    entorno.actualizar_cliente(propio, vendedor_id=entorno.usuario_id)
    entorno.sesion.commit()


def test_la_venta_a_un_cliente_de_otro_vendedor_se_acepta_sin_observacion(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Venta a un cliente fuera de la cartera"."""
    _fuera_de_la_cartera(entorno)

    comando = entorno.vender()

    assert comando.estado == "ACEPTADO"
    assert entorno.observaciones() == []
    (venta,) = entorno.ventas()
    assert venta.cliente_id == entorno.cliente_id


def test_la_cobranza_a_un_cliente_de_otro_vendedor_se_acepta_sin_observacion(
    db_session: Session,
) -> None:
    cobranza = EntornoCobranza(db_session)
    otro_vendedor, _ = crear_usuario_y_dispositivo(
        db_session, cobranza.org, permisos=frozenset({"VENDER"})
    )
    cobranza.sesion.execute(
        text("UPDATE cliente SET vendedor_id = :v WHERE id = :c"),
        {"v": otro_vendedor, "c": cobranza.cliente_id},
    )
    cobranza.sesion.commit()

    comando = cobranza.registrar()

    assert comando.estado == "ACEPTADO"
    assert cobranza.observaciones() == []
    (registrada,) = cobranza.cobranzas()
    assert registrada.cliente_id == cobranza.cliente_id


def test_la_venta_a_un_cliente_sin_vendedor_tambien_se_acepta(entorno: EntornoVenta) -> None:
    propio = crear_cliente(entorno.sesion, entorno.org, nombre="Cliente propio")
    entorno.actualizar_cliente(propio, vendedor_id=entorno.usuario_id)
    entorno.sesion.commit()

    comando = entorno.vender()

    assert comando.estado == "ACEPTADO"
    assert entorno.observaciones() == []
