"""Tarea 7.2 (change 19; spec `ventas/anulacion-de-venta`; `design.md` D1 a D10, D15): el comando
`VENTA_ANULAR` contra PostgreSQL real, por el bus, un caso por escenario.

Reglas citadas: VTA-20, VTA-21, VTA-22, INV-01, INV-06, INV-10, INV-13, INV-19, INV-21, CLI-03,
STK-09, CST-11, CST-12, ADR-058.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql, desactivar_producto_sql
from ventas_anular_utiles import (
    MOMENTO_ANULACION,
    PERMISOS_DE_SUPERVISOR_DE_ANULACION,
    RELOJ_ANULACION,
    EntornoAnulacion,
)

from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import UbicacionInactivaError, UbicacionTomadaError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote
from app.modules.ventas import repository as ventas_repository
from app.modules.ventas.domain.errores import (
    ConsumidorFinalSinDevolucionError,
    DevolucionInvalidaError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    RecursoNoEncontradoError,
    VentaYaAnuladaError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoAnulacion:
    return EntornoAnulacion(db_session)


def _venta_de_80000(entorno: EntornoAnulacion, *, cobro: str | None = None) -> tuple[UUID, UUID]:
    """La venta del ejemplo de `01` §9.2: 80 unidades a $1.000 = `80000.00` (saldo `230000.00`,
    o `210000.00` con un cobro de `20000.00`). Devuelve `(venta_id, producto_id)`."""
    producto_id, presentacion_id = entorno.producto_a("1000.00")
    linea = entorno.linea(producto_id, presentacion_id, 80, precio="1000.00", unidades_referencia=1)
    cambios: dict[str, Any] = {}
    if cobro is not None:
        cambios["cobranza"] = entorno.cobranza((entorno.efectivo_id, cobro, None))
    return entorno.vender_y_obtener_id(linea, **cambios), producto_id


def _cobranza_de(entorno: EntornoAnulacion) -> UUID:
    (cobranza,) = entorno.cobranzas()
    return cobranza.id


# --- anulación sin cobro (VTA-20, VTA-21, INV-03, INV-13) -----------------------------------


def test_vta20_anula_una_venta_sin_cobro_y_acredita_el_total(entorno: EntornoAnulacion) -> None:
    # Escenario: "Anulación de una venta sin cobro"
    venta_id = entorno.vender_y_obtener_id()
    assert entorno.stock() == 33 and entorno.saldo() == Decimal("181250.00")

    comando = entorno.anular(venta_id)

    assert comando.resultado == {
        "venta_id": str(venta_id),
        "estado": "ANULADA",
        "saldo": "150000.00",
        "cobranza_id": None,
        "cobranza_anulada": False,
    }
    assert entorno.venta(venta_id).estado == "ANULADA"
    (movimiento,) = entorno.movimientos("ANULACION_VENTA")
    assert (movimiento.sentido, movimiento.importe) == ("REDUCE", Decimal("31250.00"))
    assert movimiento.origen_id == venta_id
    assert entorno.saldo() == Decimal("150000.00")
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.motivo_id == entorno.motivo_anulacion_id
    assert anulacion.devuelve_dinero is None


def test_vta21_el_stock_vuelve_a_la_ubicacion_de_la_venta_al_costo_congelado(
    entorno: EntornoAnulacion,
) -> None:
    # INV-19: el stock y el promedio quedan como antes de la venta.
    venta_id = entorno.vender_y_obtener_id()

    entorno.anular(venta_id)

    assert entorno.stock() == 48
    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert (reingreso.cantidad_base, reingreso.origen_id) == (15, venta_id)
    assert reingreso.costo_unitario == Decimal("1050.000000")
    assert reingreso.ubicacion_id == entorno.deposito_id
    assert entorno.costo().costo_promedio == Decimal("1050.000000")


def test_vta21_cajas_y_botellas_del_mismo_producto_son_dos_ingresos_en_orden(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Cajas y unidades del mismo producto" (VTA-02, INV-04)
    venta_id = entorno.vender_y_obtener_id(
        entorno.linea(entorno.vino_id, entorno.caja_id, 2, unidades_presentacion=6),
        entorno.linea(entorno.vino_id, entorno.botella_id, 3),
    )

    entorno.anular(venta_id)

    cantidades = [m.cantidad_base for m in entorno.movimientos_de_stock("ANULACION_VENTA")]
    assert cantidades == [12, 3]
    assert entorno.stock() == 48


# --- reingreso al costo congelado (CST-11, CST-12) ------------------------------------------


def test_cst11_el_reingreso_recalcula_el_promedio_del_ejemplo(db_session: Session) -> None:
    # Escenario: "Reingreso que recalcula el promedio": 72 a $1.050, compra de 60 a $1.200.
    entorno = EntornoAnulacion(db_session, stock_inicial=120)
    venta_id = entorno.vender_y_obtener_id(entorno.linea(cantidad=72))
    entorno.comprar(entorno.vino_id, 60, "1200")
    db_session.commit()
    assert entorno.costo().costo_promedio == Decimal("1133.333333")

    entorno.anular(venta_id)

    costo = entorno.costo()
    assert costo.costo_promedio == Decimal("1100.000000")
    assert costo.stock_total == 180
    assert entorno.historia_de_costo("ANULACION_VENTA") == 1


def test_cst11_con_stock_total_en_cero_el_promedio_pasa_al_costo_de_la_venta(
    db_session: Session,
) -> None:
    # Escenario: "Stock total previo en cero"
    entorno = EntornoAnulacion(db_session, stock_inicial=72)
    venta_id = entorno.vender_y_obtener_id(entorno.linea(cantidad=72))
    assert entorno.stock() == 0

    entorno.anular(venta_id)

    assert entorno.stock() == 72
    assert entorno.costo().costo_promedio == Decimal("1050.000000")


def test_cst12_una_linea_vendida_sin_costo_ingresa_sin_recalcular_ni_historia(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Línea vendida sin costo" (INV-10: el costo no se completa)
    venta_id = entorno.vender_y_obtener_id()
    entorno.sesion.execute(
        text(
            "UPDATE venta_linea SET costo_unitario = NULL, costo_total = NULL WHERE venta_id = :v"
        ),
        {"v": venta_id},
    )
    entorno.sesion.commit()
    antes = entorno.costo().costo_promedio
    historia_antes = entorno.historia_de_costo("ANULACION_VENTA")

    entorno.anular(venta_id)

    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.costo_unitario is None
    assert entorno.stock() == 48
    assert entorno.costo().costo_promedio == antes
    assert entorno.historia_de_costo("ANULACION_VENTA") == historia_antes


# --- el dinero cobrado (VTA-22, COB-05, INV-19) ---------------------------------------------


def test_vta22_con_devolucion_anula_la_cobranza_y_el_saldo_vuelve_al_inicial(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Con devolución"
    venta_id, _ = _venta_de_80000(entorno, cobro="20000.00")
    cobranza_id = _cobranza_de(entorno)
    assert entorno.saldo() == Decimal("210000.00")

    comando = entorno.anular(venta_id, observacion="cliente se arrepintió", devuelve_dinero=True)

    assert comando.resultado == {
        "venta_id": str(venta_id),
        "estado": "ANULADA",
        "saldo": "150000.00",
        "cobranza_id": str(cobranza_id),
        "cobranza_anulada": True,
    }
    assert entorno.estado_de_cobranza(cobranza_id) == "ANULADA"
    (de_la_venta,) = entorno.movimientos("ANULACION_VENTA")
    (de_la_cobranza,) = entorno.movimientos("ANULACION_COBRANZA")
    assert (de_la_venta.sentido, de_la_venta.importe) == ("REDUCE", Decimal("80000.00"))
    assert (de_la_cobranza.sentido, de_la_cobranza.importe) == ("AUMENTA", Decimal("20000.00"))
    (anulacion,) = entorno.anulaciones()
    assert anulacion.motivo_id == entorno.motivo_anulacion_id
    assert anulacion.observacion == "cliente se arrepintió"
    (de_la_venta_anulada,) = entorno.anulaciones_de_venta()
    assert de_la_venta_anulada.devuelve_dinero is True


def test_vta22_sin_devolucion_la_cobranza_queda_y_su_importe_queda_a_favor(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación de la venta sin devolución" (cobranzas/anulacion-de-cobranzas)
    # Escenario: "Sin devolución" (CC-05)
    venta_id, _ = _venta_de_80000(entorno, cobro="20000.00")
    cobranza_id = _cobranza_de(entorno)

    comando = entorno.anular(venta_id, devuelve_dinero=False)

    assert comando.resultado is not None
    assert comando.resultado["saldo"] == "130000.00"
    assert comando.resultado["cobranza_anulada"] is False
    assert entorno.estado_de_cobranza(cobranza_id) == "CONFIRMADA"
    assert entorno.movimientos("ANULACION_COBRANZA") == []
    assert entorno.saldo() == Decimal("130000.00")
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.devuelve_dinero is False


def test_vta22_una_cobranza_mayor_que_el_total_se_anula_completa(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Cobranza mayor que el total" (VTA-11)
    venta_id, _ = _venta_de_80000(entorno, cobro="100000.00")
    assert entorno.saldo() == Decimal("130000.00")

    entorno.anular(venta_id, devuelve_dinero=True)

    (de_la_cobranza,) = entorno.movimientos("ANULACION_COBRANZA")
    assert de_la_cobranza.importe == Decimal("100000.00")
    assert entorno.saldo() == Decimal("150000.00")


def test_vta22_con_cobranza_sin_indicar_o_sin_cobranza_con_indicacion_es_invalido(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Falta o sobra la indicación" (los dos sentidos)
    con_cobro, _ = _venta_de_80000(entorno, cobro="20000.00")
    sin_cobro = entorno.vender_y_obtener_id()

    with pytest.raises(DevolucionInvalidaError):
        entorno.anular(con_cobro)
    entorno.sesion.rollback()
    with pytest.raises(DevolucionInvalidaError):
        entorno.anular(sin_cobro, devuelve_dinero=True)
    entorno.sesion.rollback()
    with pytest.raises(DevolucionInvalidaError):
        entorno.anular(sin_cobro, devuelve_dinero=False)

    entorno.sesion.rollback()
    assert entorno.venta(con_cobro).estado == "CONFIRMADA"
    assert entorno.venta(sin_cobro).estado == "CONFIRMADA"
    assert entorno.anulaciones_de_venta() == []
    assert entorno.movimientos("ANULACION_VENTA") == []


def test_cli03_consumidor_final_no_admite_no_devolver_el_dinero(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Consumidor final"
    final_id = entorno.crear_cliente(es_consumidor_final=True, nombre="Consumidor final")
    entorno.sesion.commit()
    producto_id, presentacion_id = entorno.producto_a("4300.00")
    linea = entorno.linea(producto_id, presentacion_id, 1, precio="4300.00", unidades_referencia=1)
    venta_id = entorno.vender_y_obtener_id(
        linea,
        cliente_id=str(final_id),
        cobranza=entorno.cobranza((entorno.efectivo_id, "4300.00", None)),
    )
    assert entorno.saldo(final_id) == Decimal("0.00")

    with pytest.raises(ConsumidorFinalSinDevolucionError):
        entorno.anular(venta_id, devuelve_dinero=False)
    entorno.sesion.rollback()
    assert entorno.venta(venta_id).estado == "CONFIRMADA"

    entorno.anular(venta_id, devuelve_dinero=True)

    assert entorno.venta(venta_id).estado == "ANULADA"
    assert entorno.estado_de_cobranza(_cobranza_de(entorno)) == "ANULADA"
    assert entorno.saldo(final_id) == Decimal("0.00")


# --- una sola vez, entera (VTA-20, INV-05, INV-06) ------------------------------------------


def test_vta20_la_segunda_anulacion_responde_venta_ya_anulada_sin_movimientos_nuevos(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Segunda anulación"
    venta_id = entorno.vender_y_obtener_id()
    entorno.anular(venta_id)

    with pytest.raises(VentaYaAnuladaError):
        entorno.anular(venta_id)

    entorno.sesion.rollback()
    assert len(entorno.movimientos("ANULACION_VENTA")) == 1
    assert len(entorno.movimientos_de_stock("ANULACION_VENTA")) == 1
    assert len(entorno.anulaciones_de_venta()) == 1


def test_inv06_el_doble_envio_devuelve_el_resultado_original_con_un_solo_juego_de_movimientos(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Doble envío"
    venta_id = entorno.vender_y_obtener_id()
    operation_id = uuid4()

    primero = entorno.anular(venta_id, operation_id=operation_id)
    segundo = entorno.anular(venta_id, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.movimientos("ANULACION_VENTA")) == 1
    assert len(entorno.movimientos_de_stock("ANULACION_VENTA")) == 1


def test_inv10_la_anulacion_no_toca_lineas_descuentos_ni_snapshot_de_credito(
    db_session: Session,
) -> None:
    # Escenario: "Valores congelados intactos"
    entorno = EntornoAnulacion(db_session, stock_inicial=500)
    regla = entorno.crear_regla()  # 5 % desde 20 cajas equivalentes
    descuento = {
        "origen": "AUTOMATICO",
        "regla_id": str(regla),
        "porcentaje": "0.050000",
        "importe": "12500.00",
    }
    venta_id = entorno.vender_y_obtener_id(
        entorno.linea(cantidad=120, descuentos=[descuento]), total="237500.00"
    )
    entorno.sesion.expire_all()
    antes_venta = {c: v for c, v in vars(entorno.venta(venta_id)).items() if not c.startswith("_")}
    antes_lineas = [
        {c: v for c, v in vars(linea).items() if not c.startswith("_")}
        for linea in entorno.lineas_de_venta(venta_id)
    ]
    antes_descuentos = [
        (d.venta_linea_id, d.porcentaje, d.importe) for d in entorno.descuentos_de_venta()
    ]
    assert antes_descuentos, "la venta del caso tiene que tener un descuento"

    entorno.anular(venta_id)

    entorno.sesion.expire_all()
    despues_venta = {
        c: v for c, v in vars(entorno.venta(venta_id)).items() if not c.startswith("_")
    }
    assert {c: v for c, v in despues_venta.items() if c != "estado"} == {
        c: v for c, v in antes_venta.items() if c != "estado"
    }
    assert despues_venta["estado"] == "ANULADA"
    assert [
        {c: v for c, v in vars(linea).items() if not c.startswith("_")}
        for linea in entorno.lineas_de_venta(venta_id)
    ] == antes_lineas
    assert [
        (d.venta_linea_id, d.porcentaje, d.importe) for d in entorno.descuentos_de_venta()
    ] == antes_descuentos


# --- permiso, contenido y organización (SEG-06, TR-09, INV-21) ------------------------------


def test_seg06_sin_anular_venta_responde_permiso_requerido_y_nada_cambia(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Sin permiso"
    venta_id = entorno.vender_y_obtener_id()
    vendedor_id, vendedor_dispositivo = entorno.otro_usuario(frozenset({"VENDER"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.anular(venta_id, usuario_id=vendedor_id, dispositivo_id=vendedor_dispositivo)

    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


def test_tr09_un_motivo_de_otro_ambito_o_inactivo_es_motivo_invalido(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Motivo de otro ámbito o inactivo"
    venta_id = entorno.vender_y_obtener_id()
    de_cobranza = entorno.crear_motivo("ANULACION_COBRANZA", "Otro ámbito")
    inactivo = entorno.crear_motivo("ANULACION_VENTA", "Desactivado", activo=False)
    entorno.sesion.commit()

    for motivo in (de_cobranza, inactivo):
        with pytest.raises(MotivoInvalidoError):
            entorno.anular(venta_id, motivo_id=motivo)
        entorno.sesion.rollback()

    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


def test_vta20_una_observacion_de_501_caracteres_es_observacion_invalida(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Observación demasiado larga"; con 500 se acepta.
    venta_id = entorno.vender_y_obtener_id()

    with pytest.raises(ObservacionInvalidaError):
        entorno.anular(venta_id, observacion="a" * 501)
    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")

    entorno.anular(venta_id, observacion="a" * 500)

    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.observacion == "a" * 500


def test_inv21_una_venta_o_un_motivo_de_otra_organizacion_responde_404(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta de otra organización"
    ajeno = EntornoAnulacion(entorno.sesion)
    venta_ajena = ajeno.vender_y_obtener_id()
    venta_propia = entorno.vender_y_obtener_id()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular(venta_ajena)
    entorno.sesion.rollback()
    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular(venta_propia, motivo_id=ajeno.motivo_anulacion_id)

    entorno.sesion.rollback()
    assert ajeno.venta(venta_ajena).estado == "CONFIRMADA"
    assert entorno.venta(venta_propia).estado == "CONFIRMADA"
    assert ajeno.anulaciones_de_venta() == [] and entorno.anulaciones_de_venta() == []


def test_vta24_un_lote_offline_lo_rechaza_como_tipo_que_no_admite_ese_modo(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Modo sin conexión todavía no admitido" (02 §6.5, SYN-06)
    venta_id = entorno.vender_y_obtener_id()
    item = ItemLote(
        operation_id=uuid4(),
        tipo="VENTA_ANULAR",
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO_ANULACION,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido_de_anulacion(venta_id),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ_ANULACION,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


def test_seg06_un_lote_online_sin_anular_venta_responde_permiso_requerido_sin_efectos(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Por REST y por el lote" (REST: `test_ventas_anular_api.py`; ADR-056, SEG-06)
    venta_id = entorno.vender_y_obtener_id()
    vendedor_id, vendedor_dispositivo = entorno.otro_usuario(frozenset({"VENDER"}))
    item = ItemLote(
        operation_id=uuid4(),
        tipo="VENTA_ANULAR",
        version=1,
        modo="ONLINE",
        usuario_id=vendedor_id,
        dispositivo_id=vendedor_dispositivo,
        occurred_at=MOMENTO_ANULACION,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido_de_anulacion(venta_id),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ_ANULACION,
        organizacion_id=entorno.org,
        usuario_id=vendedor_id,
        dispositivo_id=vendedor_dispositivo,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


# --- ubicación: toma, jornada e inactividad (STK-09, RUT-04, STK-02) ------------------------


def _venta_en_camioneta(entorno: EntornoAnulacion) -> tuple[UUID, UUID]:
    """Camioneta 2 con 48 botellas y una venta de 15 hecha desde ella antes de que nadie la
    tome; devuelve `(venta_id, camioneta_id)`."""
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    entorno.sesion.commit()
    venta_id = entorno.vender_y_obtener_id(ubicacion_id=str(camioneta_id))
    return venta_id, camioneta_id


def _tomar_por_otro_vendedor(entorno: EntornoAnulacion, camioneta_id: UUID) -> UUID:
    pedro_id, pedro_dispositivo = entorno.otro_usuario(frozenset({"VENDER"}))
    return entorno.crear_jornada(
        usuario_id=pedro_id, dispositivo_id=pedro_dispositivo, ubicacion_id=camioneta_id
    )


def test_stk09_una_ubicacion_tomada_por_otra_jornada_rechaza_a_quien_no_puede_liberarla(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Camioneta tomada por otro vendedor" (`ges01`)
    venta_id, camioneta_id = _venta_en_camioneta(entorno)
    _tomar_por_otro_vendedor(entorno, camioneta_id)

    with pytest.raises(UbicacionTomadaError):
        entorno.anular(venta_id)

    entorno.sesion.rollback()
    assert entorno.venta(venta_id).estado == "CONFIRMADA"
    assert entorno.stock(ubicacion_id=camioneta_id) == 33
    assert entorno.anulaciones_de_venta() == []


def test_stk09_con_liberar_ubicacion_el_reingreso_va_sin_jornada(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Supervisor con `LIBERAR_UBICACION`" (`sup01`)
    venta_id, camioneta_id = _venta_en_camioneta(entorno)
    _tomar_por_otro_vendedor(entorno, camioneta_id)
    supervisor_id, supervisor_dispositivo = entorno.otro_usuario(
        PERMISOS_DE_SUPERVISOR_DE_ANULACION
    )

    entorno.anular(venta_id, usuario_id=supervisor_id, dispositivo_id=supervisor_dispositivo)

    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.jornada_id is None
    assert entorno.stock(ubicacion_id=camioneta_id) == 48
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id is None


def test_rut04_con_jornada_propia_abierta_el_reingreso_y_la_anulacion_llevan_la_jornada(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Jornada propia abierta"
    venta_id, camioneta_id = _venta_en_camioneta(entorno)
    propia_id = entorno.crear_jornada(ubicacion_id=camioneta_id)

    entorno.anular(venta_id)

    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.jornada_id == propia_id
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id == propia_id


def test_vta20_una_venta_de_una_jornada_cerrada_se_anula_sin_jornada(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta de una jornada cerrada con la ubicación libre" (D8)
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    jornada_id = entorno.crear_jornada(ubicacion_id=camioneta_id)
    comando = entorno.enviar(
        entorno.contenido(ubicacion_id=str(camioneta_id)), jornada_id=jornada_id
    )
    assert comando.resultado is not None
    venta_id = UUID(str(comando.resultado["venta_id"]))
    entorno.sesion.execute(
        text(
            "UPDATE jornada SET estado = 'CERRADA', rendida_en = :m, rendida_por_id = :u, "
            "cerrada_en = :m, cerrada_por_id = :u WHERE organizacion_id = :o AND id = :j"
        ),
        {"m": MOMENTO_ANULACION, "u": entorno.usuario_id, "o": entorno.org, "j": jornada_id},
    )
    entorno.sesion.commit()
    assert entorno.venta(venta_id).jornada_id == jornada_id

    entorno.anular(venta_id)

    assert entorno.venta(venta_id).estado == "ANULADA"
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id is None


def test_stk02_una_ubicacion_inactiva_rechaza_la_anulacion(entorno: EntornoAnulacion) -> None:
    # Escenario: "Ubicación inactiva"
    venta_id = entorno.vender_y_obtener_id()
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": entorno.deposito_id},
    )
    entorno.sesion.commit()

    with pytest.raises(UbicacionInactivaError):
        entorno.anular(venta_id)

    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


# --- maestros inactivos (CAT-05, CLI-02) ----------------------------------------------------


def test_cat05_se_anula_aunque_el_producto_este_desactivado(entorno: EntornoAnulacion) -> None:
    # Escenario: "Producto desactivado"
    venta_id = entorno.vender_y_obtener_id()
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)
    entorno.sesion.commit()

    entorno.anular(venta_id)

    assert entorno.venta(venta_id).estado == "ANULADA"
    assert entorno.stock() == 48


def test_cli02_se_anula_aunque_el_cliente_este_inactivo(entorno: EntornoAnulacion) -> None:
    # Escenario: "Cliente inactivo"
    venta_id = entorno.vender_y_obtener_id()
    entorno.actualizar_cliente(entorno.cliente_id, estado="INACTIVO")
    entorno.sesion.commit()

    entorno.anular(venta_id)

    assert entorno.venta(venta_id).estado == "ANULADA"
    (movimiento,) = entorno.movimientos("ANULACION_VENTA")
    assert movimiento.cliente_id == entorno.cliente_id


# --- atómica (INV-01) y precedencia (D10) ---------------------------------------------------


def _fallar_despues_de(
    monkeypatch: pytest.MonkeyPatch, modulo: object, nombre: str, mensaje: str
) -> None:
    original = getattr(modulo, nombre)

    def _con_falla(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        raise RuntimeError(mensaje)

    monkeypatch.setattr(modulo, nombre, _con_falla)


@pytest.mark.parametrize(
    ("modulo", "nombre"),
    [
        (stock_service, "registrar_movimientos"),
        (cobranzas_service, "anular_cobranza_de_venta"),
        (ventas_repository, "insertar_anulacion"),
        (ventas_repository, "marcar_venta_anulada"),
        (sync_service.identidad_service, "registrar_auditoria"),
    ],
)
def test_inv01_una_falla_despues_de_cada_efecto_no_deja_nada_y_se_puede_reintentar(
    entorno: EntornoAnulacion, monkeypatch: pytest.MonkeyPatch, modulo: object, nombre: str
) -> None:
    venta_id, _ = _venta_de_80000(entorno, cobro="20000.00")
    cobranza_id = _cobranza_de(entorno)
    operation_id = uuid4()
    with monkeypatch.context() as parche:
        _fallar_despues_de(parche, modulo, nombre, f"después de {nombre}")
        with pytest.raises(RuntimeError, match=nombre):
            entorno.anular(venta_id, operation_id=operation_id, devuelve_dinero=True)

    entorno.sin_efectos_de_anulacion(venta_id, stock=48, saldo="210000.00")
    assert entorno.estado_de_cobranza(cobranza_id) == "CONFIRMADA"

    entorno.anular(venta_id, operation_id=operation_id, devuelve_dinero=True)

    assert entorno.venta(venta_id).estado == "ANULADA"


def test_inv01_una_falla_despues_del_movimiento_de_cuenta_no_deja_nada(
    entorno: EntornoAnulacion, monkeypatch: pytest.MonkeyPatch
) -> None:
    venta_id = entorno.vender_y_obtener_id()
    original = cuentas_service.registrar_movimiento

    def _falla_tras_la_anulacion(*args: object, **kwargs: object) -> object:
        resultado = original(*args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("tipo") == "ANULACION_VENTA":
            raise RuntimeError("después de la cuenta")
        return resultado

    monkeypatch.setattr(cuentas_service, "registrar_movimiento", _falla_tras_la_anulacion)

    with pytest.raises(RuntimeError, match="después de la cuenta"):
        entorno.anular(venta_id)

    entorno.sin_efectos_de_anulacion(venta_id, stock=33, saldo="181250.00")


def test_d10_precedencia_venta_ya_anulada_antes_que_motivo_y_devolucion(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Precedencia": contenido, venta, motivo, devolución, ubicación.
    venta_id = entorno.vender_y_obtener_id()
    entorno.anular(venta_id)
    de_cobranza = entorno.crear_motivo("ANULACION_COBRANZA", "Otro ámbito")
    entorno.sesion.commit()

    with pytest.raises(VentaYaAnuladaError):
        entorno.anular(venta_id, motivo_id=de_cobranza, devuelve_dinero=True)


def test_d10_precedencia_contenido_antes_que_venta_inexistente(
    entorno: EntornoAnulacion,
) -> None:
    with pytest.raises(ObservacionInvalidaError):
        entorno.anular(uuid4(), observacion="a" * 501)


def test_d10_precedencia_motivo_antes_que_devolucion_y_devolucion_antes_que_ubicacion(
    entorno: EntornoAnulacion,
) -> None:
    venta_id = entorno.vender_y_obtener_id()
    de_cobranza = entorno.crear_motivo("ANULACION_COBRANZA", "Otro ámbito")
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": entorno.deposito_id},
    )
    entorno.sesion.commit()

    with pytest.raises(MotivoInvalidoError):
        entorno.anular(venta_id, motivo_id=de_cobranza, devuelve_dinero=True)
    entorno.sesion.rollback()
    with pytest.raises(DevolucionInvalidaError):
        entorno.anular(venta_id, devuelve_dinero=True)
    entorno.sesion.rollback()
    with pytest.raises(UbicacionInactivaError):
        entorno.anular(venta_id)
