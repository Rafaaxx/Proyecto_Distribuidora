"""Tarea 1.1 (change 22d; spec `ventas/anulacion-de-venta`, requisito "Una venta de la jornada en
curso se anula sin conexión", y spec `sync/lote-de-comandos`, requisito "VENTA_ANULAR se acepta
por el lote sin conexión"; `design.md` D1 y D4, aprobadas el 2026-11-03), contra PostgreSQL real y
por `procesar_lote`.

- `VENTA_ANULAR` v1 admite `OFFLINE` solo por el lote; por REST sigue `ONLINE`.
- Sin conexión, la venta debe ser de la jornada del sobre (`JORNADA_AJENA`); una venta que no
  existe en la organización (rechazada antes o de otra organización) es `VENTA_INEXISTENTE`.
- Un rechazo no corta el lote y el reenvío del mismo `operation_id` devuelve el mismo resultado.

Reglas citadas: VTA-24, SYN-03, SYN-06, SYN-10, INV-06, INV-19, INV-21.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, lote
from venta_anular_offline_utiles import anular, item_de_anulacion, rechazada, vender
from ventas_anular_utiles import EntornoAnulacion

from app.commands import catalogo

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

SALDO_ANTES = Decimal("150000.00")
SALDO_CON_LA_VENTA = Decimal("181250.00")  # 15 botellas a $12.500 la caja x6 = $31.250


@pytest.fixture
def entorno(db_session: Session) -> EntornoAnulacion:
    return EntornoAnulacion(db_session)


# --- escenarios de "VENTA_ANULAR se acepta por el lote sin conexión" ------------------------


def test_vta24_el_catalogo_declara_los_dos_modos_y_la_venta_como_operacion_observable() -> None:
    # Escenario: "Anulación sin conexión por el lote"
    """El catálogo de tipos admite `ONLINE` y `OFFLINE` y nombra a la venta como la operación
    sobre la que el bus anota `PERMISO_REVOCADO` y `JORNADA_LIBERADA` (D1)."""
    declarado = catalogo.tipo_declarado("VENTA_ANULAR")

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, True)
    assert declarado.permisos == ("ANULAR_VENTA",)
    assert declarado.operacion_offline == catalogo.OperacionObservable("VENTA", "venta_id")


def test_vta24_una_anulacion_sin_conexion_de_la_jornada_se_acepta_por_el_lote(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación sin conexión por el lote"
    # Escenario: "Anulación sin conexión de una venta de la jornada"
    """VTA-24, VTA-20, VTA-21: la venta de $31.250 confirmada sin conexión en la jornada del
    vendedor se anula por el lote `OFFLINE`: queda `ANULADA`, la mercadería vuelve a la camioneta y
    la cuenta del cliente se acredita; el resultado es el mismo que con conexión."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO"
    assert resultado.resultado == {
        "venta_id": str(venta_id),
        "estado": "ANULADA",
        "saldo": str(SALDO_ANTES),
        "cobranza_id": None,
        "cobranza_anulada": False,
    }
    assert entorno.venta(venta_id).estado == "ANULADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES
    (anulacion,) = entorno.anulaciones_de_venta()
    assert (anulacion.venta_id, anulacion.motivo_id) == (venta_id, entorno.motivo_anulacion_id)


def test_vta24_otra_venta_y_otro_monto_tambien_se_acepta_y_acredita_su_total(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación sin conexión de una venta de la jornada"
    """Triangulación: una venta de 6 botellas ($12.500) se anula por el lote con su observación;
    se acredita su total y vuelven 6 botellas."""
    ruta = Ruta(entorno)
    item, resultado_venta = ruta.enviar(entorno.linea(cantidad=6, bruto="12500.00"))
    assert resultado_venta.estado == "ACEPTADO"
    venta_id = UUID(str(item.contenido["venta_id"]))
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 42
    assert entorno.saldo() == Decimal("162500.00")

    _, resultado = anular(entorno, ruta, venta_id, observacion="Cliente rechazó la entrega")

    assert resultado.estado == "ACEPTADO"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.observacion == "Cliente rechazó la entrega"


def test_syn03_la_venta_y_su_anulacion_en_el_mismo_lote_se_procesan_en_orden(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "La venta y su anulación en el mismo lote"
    """SYN-03, INV-19: la venta (secuencia 7) se acepta primero y la anulación (secuencia 8)
    después, aunque lleguen invertidas en la lista; el stock y el saldo quedan como antes."""
    ruta = Ruta(entorno)
    contenido = ruta.contenido()
    venta = ruta.item(contenido, secuencia=7)
    anulacion = item_de_anulacion(
        entorno, UUID(str(contenido["venta_id"])), jornada_id=ruta.jornada_id, secuencia=8
    )

    resultados = lote(entorno, anulacion, venta)

    assert resultados[venta.operation_id].estado == "ACEPTADO"
    assert resultados[anulacion.operation_id].estado == "ACEPTADO"
    assert entorno.venta(UUID(str(contenido["venta_id"]))).estado == "ANULADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES


def test_syn03_la_anulacion_en_un_lote_posterior_a_su_venta_tambien_se_acepta(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "La venta y su anulación en el mismo lote"
    """Triangulación: los dos comandos en lotes separados dan el mismo estado final."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    assert entorno.saldo() == SALDO_CON_LA_VENTA

    _, resultado = anular(entorno, ruta, venta_id, secuencia=2)

    assert resultado.estado == "ACEPTADO"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES


def test_vta24_la_venta_de_otra_jornada_se_rechaza_con_jornada_ajena(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta de otra jornada"
    """VTA-24, SYN-10, SYN-06: la venta de la jornada de ayer (liberada) no se anula con el sobre
    de la jornada de hoy del mismo vendedor; nada cambia."""
    ayer = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ayer)
    hoy_jornada_id = entorno.crear_jornada()
    item = item_de_anulacion(entorno, venta_id, jornada_id=hoy_jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "JORNADA_AJENA", item, entorno)
    assert entorno.venta(venta_id).estado == "CONFIRMADA"
    assert entorno.anulaciones_de_venta() == []
    assert entorno.stock(ubicacion_id=ayer.camioneta_id) == 33
    assert entorno.saldo() == SALDO_CON_LA_VENTA


def test_vta24_la_venta_confirmada_con_conexion_y_sin_jornada_es_jornada_ajena(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta de otra jornada"
    """Triangulación: una venta confirmada con conexión desde el depósito (sin jornada) no se
    anula sin conexión: la jornada de la venta no es la del sobre."""
    venta_id = entorno.vender_y_obtener_id()
    ruta = Ruta(entorno)
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "JORNADA_AJENA", item, entorno)
    assert entorno.venta(venta_id).estado == "CONFIRMADA"
    assert entorno.anulaciones_de_venta() == []


def test_syn06_la_venta_rechazada_antes_es_venta_inexistente(entorno: EntornoAnulacion) -> None:
    # Escenario: "Venta inexistente"
    """SYN-06: la venta sin conexión que el servidor rechazó (totales inconsistentes) no existe en
    el sistema; su anulación se rechaza con `VENTA_INEXISTENTE` y no deja nada."""
    ruta = Ruta(entorno)
    item_venta, resultado_venta = ruta.enviar(total="1.00")
    assert (resultado_venta.estado, resultado_venta.error_codigo) == (
        "RECHAZADO",
        "TOTALES_INCONSISTENTES",
    )
    venta_id = UUID(str(item_venta.contenido["venta_id"]))
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "VENTA_INEXISTENTE", item, entorno)
    assert entorno.anulaciones_de_venta() == []
    assert entorno.movimientos_de_stock("ANULACION_VENTA") == []


def test_syn06_un_identificador_que_nunca_llego_tambien_es_venta_inexistente(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta inexistente"
    """Triangulación: un `venta_id` cualquiera, sin venta, da el mismo rechazo (no el 404 genérico
    de la anulación con conexión) y el reenvío corregido sigue siendo posible."""
    ruta = Ruta(entorno)
    item = item_de_anulacion(entorno, uuid4(), jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "VENTA_INEXISTENTE", item, entorno)


def test_inv21_la_venta_de_otra_organizacion_es_venta_inexistente_y_no_se_toca(
    entorno: EntornoAnulacion, db_session: Session
) -> None:
    # Escenario: "Venta de otra organización"
    """INV-21, SYN-06: la anulación que nombra una venta de otra organización se rechaza con
    `VENTA_INEXISTENTE`; la venta ajena sigue confirmada y con su saldo."""
    ajena = EntornoAnulacion(db_session)
    venta_ajena_id = ajena.vender_y_obtener_id()
    ruta = Ruta(entorno)
    item = item_de_anulacion(entorno, venta_ajena_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "VENTA_INEXISTENTE", item, entorno)
    assert ajena.venta(venta_ajena_id).estado == "CONFIRMADA"
    assert ajena.anulaciones_de_venta() == []
    assert ajena.stock() == 33
    assert entorno.anulaciones_de_venta() == []


def test_syn10_la_anulacion_sin_jornada_en_el_sobre_se_rechaza_con_jornada_requerida(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Sin jornada"
    """SYN-10, SYN-06: el bus rechaza una anulación `OFFLINE` sin jornada, sin dejar fila."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    item = item_de_anulacion(entorno, venta_id, jornada_id=None)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "JORNADA_REQUERIDA", item, entorno)
    assert entorno.venta(venta_id).estado == "CONFIRMADA"


def test_syn10_la_jornada_de_otro_usuario_se_rechaza_con_jornada_ajena(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Jornada de otro teléfono"
    """SYN-10, SYN-06: el sobre nombra la jornada de otro usuario y dispositivo: `JORNADA_AJENA`."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    jornada_de_otro = entorno.crear_otro_usuario_con_jornada()
    item = item_de_anulacion(entorno, venta_id, jornada_id=jornada_de_otro)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "JORNADA_AJENA", item, entorno)
    assert entorno.venta(venta_id).estado == "CONFIRMADA"


def test_syn04_un_rechazo_no_corta_el_lote(entorno: EntornoAnulacion) -> None:
    # Escenario: "Un rechazo no corta el lote"
    """`02` §6.4, SYN-04: la anulación de una venta ya anulada se rechaza con `VENTA_YA_ANULADA` y
    la venta nueva que viene después se procesa igual."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    anular(entorno, ruta, venta_id, secuencia=2)
    repetida = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, secuencia=3)
    nueva = ruta.item(ruta.contenido(), secuencia=4)

    resultados = lote(entorno, repetida, nueva)

    assert (
        resultados[repetida.operation_id].estado,
        resultados[repetida.operation_id].error_codigo,
    ) == (
        "RECHAZADO",
        "VENTA_YA_ANULADA",
    )
    assert resultados[nueva.operation_id].estado == "ACEPTADO"
    assert len(entorno.anulaciones_de_venta()) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33


def test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_efectos_nuevos(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Doble envío"
    """INV-06, SYN-02: el reenvío del mismo `operation_id` y contenido devuelve el mismo resultado;
    el stock, la cuenta y las anulaciones no cambian otra vez."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    item, primero = anular(entorno, ruta, venta_id)

    segundo = lote(entorno, item)[item.operation_id]

    assert (segundo.estado, segundo.resultado, segundo.error_codigo) == (
        primero.estado,
        primero.resultado,
        primero.error_codigo,
    )
    assert len(entorno.anulaciones_de_venta()) == 1
    assert len(entorno.movimientos_de_stock("ANULACION_VENTA")) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES


def test_inv19_dos_envios_de_anulaciones_distintas_de_la_misma_venta_acreditan_una_vez(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Doble envío"
    """Triangulación (INV-19, VTA-20): dos anulaciones con distinto `operation_id` de la misma
    venta: la segunda es `VENTA_YA_ANULADA` y el saldo sigue en el previo a la venta."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    anular(entorno, ruta, venta_id, secuencia=2)

    _, segunda = anular(entorno, ruta, venta_id, secuencia=3)

    assert (segunda.estado, segunda.error_codigo) == ("RECHAZADO", "VENTA_YA_ANULADA")
    assert entorno.saldo() == SALDO_ANTES
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
