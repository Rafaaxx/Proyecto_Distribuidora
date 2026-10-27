"""Triangulacion dominio anulacion (change 19 tarea 2.1)."""

from __future__ import annotations

import pytest

from app.modules.ventas.domain.anulacion import (
    efecto_en_cuenta,
    lineas_de_reingreso,
    validar_devolucion,
    validar_observacion,
    validar_venta_anulable,
)
from app.modules.ventas.domain.errores import (
    ConsumidorFinalSinDevolucionError,
    DevolucionInvalidaError,
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
