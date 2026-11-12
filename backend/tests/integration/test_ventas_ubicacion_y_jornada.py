"""Tarea 7.6 (change 18a; spec `ventas/confirmacion-de-venta`, requisito "La venta va a la
ubicación de la jornada del vendedor o a la que se elige"; `design.md` D3): la ubicación y la
jornada de `VENTA_CONFIRMAR` con conexión, contra PostgreSQL real.

Reglas citadas: RUT-04, RUT-07, STK-09, VTA-01, INV-16, INV-21.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from ventas_confirmar_utiles import PERMISOS_DE_VENTA, EntornoVenta

from app.core.errors import DomainError
from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.ventas.domain.errores import JornadaAjenaError, UbicacionRequeridaError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def _camioneta_con_stock(entorno: EntornoVenta, nombre: str = "Camioneta 2") -> UUID:
    """Una ubicación que requiere toma con 48 botellas a $1.050 (el stock entra ANTES de que una
    jornada la tome: una ubicación tomada solo la mueve su jornada, STK-09)."""
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre=nombre, requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    return camioneta_id


def _jornada_propia(entorno: EntornoVenta, camioneta_id: UUID, *, estado: str = "ABIERTA") -> UUID:
    return entorno.crear_jornada(estado=estado, ubicacion_id=camioneta_id)


# --- la jornada abierta del vendedor (RUT-04, RUT-07, STK-09) -----------------------------------


def test_rut04_un_vendedor_con_jornada_abierta_vende_desde_su_ubicacion_y_su_jornada(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Vendedor con jornada abierta": sin indicar ubicación, el stock baja en la
    camioneta y la venta, su movimiento y su cobranza llevan la jornada."""
    camioneta_id = _camioneta_con_stock(entorno)
    jornada_id = _jornada_propia(entorno, camioneta_id)

    entorno.enviar(entorno.contenido(ubicacion_id=None, cobranza=entorno.cobranza()))

    (venta,) = entorno.ventas()
    assert (venta.ubicacion_id, venta.jornada_id) == (camioneta_id, jornada_id)
    (movimiento,) = entorno.movimientos_de_stock()
    assert (movimiento.ubicacion_id, movimiento.jornada_id) == (camioneta_id, jornada_id)
    assert entorno.stock(ubicacion_id=camioneta_id) == 33
    assert entorno.stock() == 48
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada_id


def test_rut04_indicar_la_ubicacion_de_la_propia_jornada_tambien_se_acepta(
    entorno: EntornoVenta,
) -> None:
    camioneta_id = _camioneta_con_stock(entorno)
    jornada_id = _jornada_propia(entorno, camioneta_id)

    entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta_id)), jornada_id=jornada_id)

    (venta,) = entorno.ventas()
    assert (venta.ubicacion_id, venta.jornada_id) == (camioneta_id, jornada_id)


def test_rut04_una_ubicacion_distinta_de_la_de_la_jornada_es_jornada_ajena(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Ubicación distinta de la jornada": Juan, con su jornada abierta, envía la
    venta con "Depósito central"."""
    _jornada_propia(entorno, _camioneta_con_stock(entorno))

    with pytest.raises(JornadaAjenaError) as error:
        entorno.vender(ubicacion_id=str(entorno.deposito_id))

    assert (error.value.codigo, error.value.status_http) == ("JORNADA_AJENA", 409)
    entorno.sesion.rollback()
    assert entorno.ventas() == []
    assert entorno.stock() == 48


def test_rut04_la_jornada_del_sobre_debe_ser_la_propia(entorno: EntornoVenta) -> None:
    _jornada_propia(entorno, _camioneta_con_stock(entorno))
    de_otro = entorno.crear_otro_usuario_con_jornada()

    with pytest.raises(JornadaAjenaError):
        entorno.enviar(entorno.contenido(ubicacion_id=None), jornada_id=de_otro)

    entorno.sesion.rollback()
    assert entorno.ventas() == []


def test_rut04_un_sobre_con_jornada_sin_jornada_abierta_propia_es_jornada_ajena(
    entorno: EntornoVenta,
) -> None:
    de_otro = entorno.crear_otro_usuario_con_jornada()

    with pytest.raises(JornadaAjenaError):
        entorno.enviar(entorno.contenido(), jornada_id=de_otro)

    entorno.sesion.rollback()
    assert entorno.ventas() == []


# --- la venta desde la oficina (VTA-01) ---------------------------------------------------------


def test_vta01_una_venta_sin_jornada_va_al_deposito_elegido_y_queda_sin_jornada(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Venta desde la oficina"."""
    entorno.vender()

    (venta,) = entorno.ventas()
    assert (venta.ubicacion_id, venta.jornada_id) == (entorno.deposito_id, None)
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id is None
    assert entorno.stock() == 33


def test_vta01_sin_jornada_y_sin_ubicacion_se_rechaza(entorno: EntornoVenta) -> None:
    with pytest.raises(UbicacionRequeridaError) as error:
        entorno.vender(ubicacion_id=None)

    assert (error.value.codigo, error.value.status_http) == ("UBICACION_REQUERIDA", 422)
    entorno.sin_efectos_de_venta()


def test_inv21_una_ubicacion_de_otra_organizacion_responde_404(
    entorno: EntornoVenta, db_session: Session
) -> None:
    otra = EntornoVenta(db_session)

    with pytest.raises(DomainError) as error:
        entorno.vender(ubicacion_id=str(otra.deposito_id))

    assert error.value.status_http == 404
    entorno.sin_efectos_de_venta()


# --- ubicación tomada por otra jornada (STK-09) -------------------------------------------------


def test_stk09_una_ubicacion_tomada_por_otra_jornada_se_rechaza_sin_efectos(
    entorno: EntornoVenta, db_session: Session
) -> None:
    """Escenario "Ubicación tomada por otra jornada": la camioneta 2 es de la jornada de Juan y
    Ana, sin `LIBERAR_UBICACION`, vende desde ella."""
    camioneta_id = _camioneta_con_stock(entorno)
    juan_id, juan_dispositivo_id = crear_usuario_y_dispositivo(
        db_session, entorno.org, permisos=PERMISOS_DE_VENTA
    )
    entorno.crear_jornada(
        usuario_id=juan_id, dispositivo_id=juan_dispositivo_id, ubicacion_id=camioneta_id
    )

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.vender(ubicacion_id=str(camioneta_id))

    assert (error.value.codigo, error.value.status_http) == ("UBICACION_TOMADA", 409)
    entorno.sesion.rollback()
    assert entorno.ventas() == []
    assert entorno.stock(ubicacion_id=camioneta_id) == 48


def test_stk09_la_propia_jornada_en_rendicion_ya_no_vende(entorno: EntornoVenta) -> None:
    """Con la jornada `EN_RENDICION` la propia jornada deja de vender: la ubicación sigue
    tomada (`UBICACION_TOMADA`); el depósito, en cambio, queda disponible sin jornada."""
    camioneta_id = _camioneta_con_stock(entorno)
    _jornada_propia(entorno, camioneta_id, estado="EN_RENDICION")

    with pytest.raises(UbicacionTomadaError):
        entorno.vender(ubicacion_id=str(camioneta_id))
    entorno.sesion.rollback()

    entorno.vender(ubicacion_id=str(entorno.deposito_id))

    (venta,) = entorno.ventas()
    assert (venta.ubicacion_id, venta.jornada_id) == (entorno.deposito_id, None)
    assert entorno.saldo() == Decimal("181250.00")
