"""Triangulacion dominio anulacion (change 19 tarea 2.1)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.ventas.domain.anulacion import (
    efecto_en_cuenta,
    lineas_de_reingreso,
    validar_devolucion,
    validar_jornada_en_curso,
    validar_motivo_de_anulacion,
    validar_observacion,
    validar_venta_anulable,
)
from app.modules.ventas.domain.errores import (
    ConsumidorFinalSinDevolucionError,
    DevolucionInvalidaError,
    JornadaAjenaError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    VentaYaAnuladaError,
)


def test_validar_venta_anulable_lanza_si_anulada() -> None:
    with pytest.raises(VentaYaAnuladaError):
        validar_venta_anulable("ANULADA")


def test_validar_venta_anulable_no_lanza_si_confirmada() -> None:
    validar_venta_anulable("CONFIRMADA")


def test_validar_devolucion_consumidor_final_con_cobro_y_sin_devolucion() -> None:
    with pytest.raises(ConsumidorFinalSinDevolucionError):
        validar_devolucion(True, False, True)


def test_validar_devolucion_sin_cobro_con_devolucion() -> None:
    with pytest.raises(DevolucionInvalidaError):
        validar_devolucion(False, True, False)


def test_validar_devolucion_consumidor_final_con_cobro_y_con_devolucion_ok() -> None:
    validar_devolucion(True, True, True)


def test_validar_devolucion_consumidor_final_sin_cobro() -> None:
    validar_devolucion(False, None, True)


def test_efecto_en_cuenta_cobro_mayor_que_total() -> None:
    r = efecto_en_cuenta("80000.00", "100000.00", True)
    assert [m.tipo for m in r.movimientos] == ["ANULACION_VENTA", "ANULACION_COBRANZA"]
    assert r.movimientos[1].importe == "100000.00"
    assert r.saldo_final_relativo == "0.00"


def test_efecto_en_cuenta_sin_cobro_y_sin_devolucion_iguales() -> None:
    r = efecto_en_cuenta("50000.00", None, None)
    assert [m.tipo for m in r.movimientos] == ["ANULACION_VENTA"]
    assert r.saldo_final_relativo == "-50000.00"


def test_lineas_de_reingreso_conserva_orden_y_costo_nulo() -> None:
    lineas = [
        {
            "producto_id": "p1",
            "presentacion_id": "pr1",
            "cantidad_unidad_base": 2,
            "costo_unitario": "1.050000",
        },
        {
            "producto_id": "p2",
            "presentacion_id": "pr2",
            "cantidad_unidad_base": 1,
            "costo_unitario": None,
        },
    ]
    res = lineas_de_reingreso(lineas)
    assert res[0].producto_id == "p1"
    assert res[0].costo_unitario == "1.050000"
    assert res[1].costo_unitario is None


def test_validar_devolucion_con_cobro_sin_indicar_es_invalido_en_cualquier_cliente() -> None:
    # VTA-22: "falta la indicación"
    with pytest.raises(DevolucionInvalidaError):
        validar_devolucion(True, None, False)
    with pytest.raises(DevolucionInvalidaError):
        validar_devolucion(True, None, True)


def test_validar_devolucion_sin_cobro_con_cualquier_indicacion_es_invalido() -> None:
    # VTA-22: "sobra la indicación", también con falso
    with pytest.raises(DevolucionInvalidaError):
        validar_devolucion(False, False, False)
    validar_devolucion(False, None, False)


def test_validar_devolucion_con_cobro_acepta_devolver_o_no_en_un_cliente_comun() -> None:
    validar_devolucion(True, True, False)
    validar_devolucion(True, False, False)


def test_validar_observacion_acepta_500_recorta_y_rechaza_501() -> None:
    # VTA-20, D1
    assert validar_observacion(None) is None
    assert validar_observacion("   ") is None
    assert validar_observacion("  error de carga ") == "error de carga"
    assert validar_observacion("a" * 500) == "a" * 500
    with pytest.raises(ObservacionInvalidaError):
        validar_observacion("a" * 501)


def test_lineas_de_reingreso_conserva_los_seis_decimales_del_costo() -> None:
    # D5: el costo congelado de 6 decimales, no el redondeado a 2
    (linea,) = lineas_de_reingreso(
        [
            {
                "producto_id": "p",
                "presentacion_id": "pr",
                "cantidad_unidad_base": 1,
                "costo_unitario": "1133.333333",
            }
        ]
    )
    assert linea.costo_unitario == "1133.333333"


# --- Change 22d, tarea 1.1: la jornada en curso (VTA-24, SYN-10; design D1) ---------------------


def test_vta24_la_venta_de_la_jornada_del_sobre_se_puede_anular_sin_conexion() -> None:
    jornada_id = uuid4()
    validar_jornada_en_curso(jornada_de_la_venta=jornada_id, jornada_del_sobre=jornada_id)


def test_vta24_la_venta_de_otra_jornada_es_jornada_ajena() -> None:
    with pytest.raises(JornadaAjenaError):
        validar_jornada_en_curso(jornada_de_la_venta=uuid4(), jornada_del_sobre=uuid4())


def test_vta24_la_venta_sin_jornada_es_jornada_ajena() -> None:
    with pytest.raises(JornadaAjenaError):
        validar_jornada_en_curso(jornada_de_la_venta=None, jornada_del_sobre=uuid4())


def test_vta24_un_sobre_sin_jornada_es_jornada_ajena() -> None:
    with pytest.raises(JornadaAjenaError):
        validar_jornada_en_curso(jornada_de_la_venta=uuid4(), jornada_del_sobre=None)


# --- Change 22d, tarea 2.1: el motivo de la anulación sin conexión (VTA-24, ADR-063; D2) ---------


def test_vta24_con_conexion_el_motivo_inactivo_se_rechaza() -> None:
    with pytest.raises(MotivoInvalidoError):
        validar_motivo_de_anulacion(ambito="ANULACION_VENTA", activo=False, sin_conexion=False)


def test_vta24_sin_conexion_el_motivo_dado_de_baja_despues_del_bootstrap_se_acepta() -> None:
    validar_motivo_de_anulacion(ambito="ANULACION_VENTA", activo=False, sin_conexion=True)


def test_vta24_el_motivo_de_otro_ambito_se_rechaza_con_y_sin_conexion() -> None:
    for sin_conexion in (False, True):
        with pytest.raises(MotivoInvalidoError):
            validar_motivo_de_anulacion(
                ambito="ANULACION_COBRANZA", activo=True, sin_conexion=sin_conexion
            )


def test_vta24_el_motivo_activo_del_ambito_se_acepta_con_y_sin_conexion() -> None:
    for sin_conexion in (False, True):
        validar_motivo_de_anulacion(
            ambito="ANULACION_VENTA", activo=True, sin_conexion=sin_conexion
        )
