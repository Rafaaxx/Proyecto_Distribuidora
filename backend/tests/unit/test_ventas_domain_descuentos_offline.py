"""Tarea 10.1 (change 18b; spec `ventas/descuentos-en-la-venta`, requisito "Sin conexión se aceptan
los descuentos del dispositivo", y spec `sync/observaciones`; `design.md` D9, D10): funciones puras
del camino sin conexión de los descuentos. Lo malformado se rechaza (`TOTALES_INCONSISTENTES`); lo
demás se congela y se observa (`DESCUENTO_DIFIERE` con causas, `AUTORIZACION_OFFLINE`).

Reglas citadas: DSC-09, DSC-08, DSC-07, SYN-05, SYN-06, INV-14, INV-17.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.ventas.domain.descuentos import DescuentoDeLinea
from app.modules.ventas.domain.descuentos_offline import (
    LineaEnviada,
    autorizacion_declarada_de_descuento,
    causa_de_rechazo_del_manual,
    detalle_de_causa_del_manual,
    diferencias_de_calculo,
    neto_de_linea,
    observacion_autorizacion_offline,
    observacion_descuento_difiere,
    verificar_descuentos_offline,
)
from app.modules.ventas.domain.errores import TotalesInconsistentesError

LINEA_A = uuid4()
LINEA_B = uuid4()
REGLA = uuid4()
USUARIO = uuid4()
SUPERVISOR = uuid4()


def _auto(importe: str = "1562.50", regla: UUID | None = REGLA) -> DescuentoDeLinea:
    return DescuentoDeLinea("AUTOMATICO", regla, Decimal("0.050000"), Decimal(importe))


def _manual(importe: str = "100.00", regla: UUID | None = None) -> DescuentoDeLinea:
    return DescuentoDeLinea("MANUAL", regla, Decimal("0.100000"), Decimal(importe))


def _linea(linea_id: UUID, bruto: str, *descuentos: DescuentoDeLinea) -> LineaEnviada:
    return LineaEnviada(linea_id, Decimal(bruto), tuple(descuentos))


# --- malformado (paso 0 de D18) ---------------------------------------------------------------


def test_inv14_neto_es_bruto_menos_la_suma_de_descuentos() -> None:
    linea = _linea(LINEA_A, "31250.00", _auto("1562.50"), _manual("100.00"))

    assert neto_de_linea(linea) == Decimal("29587.50")


def test_inv14_total_igual_a_la_suma_de_netos_no_lanza() -> None:
    lineas = [
        _linea(LINEA_A, "31250.00", _auto("1562.50")),
        _linea(LINEA_B, "1000.00"),
    ]

    verificar_descuentos_offline(lineas, Decimal("30687.50"))


def test_inv14_un_total_distinto_de_la_suma_de_netos_se_rechaza() -> None:
    lineas = [_linea(LINEA_A, "31250.00", _auto("1562.50"))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("31250.00"))


@pytest.mark.parametrize("importe", ["0.00", "-5.00"])
def test_dsc07_un_descuento_con_importe_no_positivo_se_rechaza(importe: str) -> None:
    lineas = [_linea(LINEA_A, "100.00", _auto(importe))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("100.00"))


@pytest.mark.parametrize("porcentaje", ["0.000000", "-0.010000", "1.500000"])
def test_dsc07_un_porcentaje_fuera_de_0_a_1_se_rechaza(porcentaje: str) -> None:
    """La base lo exige (`ck_venta_linea_descuento__porcentaje`): un descuento es mayor que cero
    y a lo sumo el cien por ciento."""
    descuento = DescuentoDeLinea("MANUAL", None, Decimal(porcentaje), Decimal("10.00"))

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline([_linea(LINEA_A, "100.00", descuento)], Decimal("90.00"))


def test_dsc07_el_cien_por_ciento_y_un_porcentaje_nulo_son_validos() -> None:
    completo = DescuentoDeLinea("MANUAL", None, Decimal("1.000000"), Decimal("100.00"))
    fijo = DescuentoDeLinea("AUTOMATICO", REGLA, None, Decimal("10.00"))

    verificar_descuentos_offline([_linea(LINEA_A, "100.00", completo)], Decimal("0.00"))
    verificar_descuentos_offline([_linea(LINEA_B, "100.00", fijo)], Decimal("90.00"))


def test_inv03_un_importe_con_mas_de_dos_decimales_se_rechaza() -> None:
    """La columna es `NUMERIC(14,2)`: no se redondea en silencio un importe del dispositivo."""
    descuento = DescuentoDeLinea("MANUAL", None, Decimal("0.100000"), Decimal("10.005"))

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline([_linea(LINEA_A, "100.00", descuento)], Decimal("89.995"))


def test_dsc08_mas_de_un_manual_por_linea_se_rechaza() -> None:
    lineas = [_linea(LINEA_A, "1000.00", _manual("10.00"), _manual("20.00"))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("970.00"))


def test_dsc08_un_manual_en_cada_linea_es_valido() -> None:
    lineas = [
        _linea(LINEA_A, "1000.00", _manual("10.00")),
        _linea(LINEA_B, "1000.00", _manual("20.00")),
    ]

    verificar_descuentos_offline(lineas, Decimal("1970.00"))


def test_dsc08_un_automatico_sin_regla_se_rechaza() -> None:
    lineas = [_linea(LINEA_A, "1000.00", _auto("10.00", regla=None))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("990.00"))


def test_dsc08_un_manual_con_regla_se_rechaza() -> None:
    lineas = [_linea(LINEA_A, "1000.00", _manual("10.00", regla=REGLA))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("990.00"))


def test_inv14_descuentos_que_superan_el_bruto_dejan_un_neto_negativo_y_se_rechazan() -> None:
    lineas = [_linea(LINEA_A, "100.00", _auto("60.00"), _manual("60.00"))]

    with pytest.raises(TotalesInconsistentesError):
        verificar_descuentos_offline(lineas, Decimal("-20.00"))


def test_inv14_descuentos_que_igualan_el_bruto_dejan_neto_cero_y_se_aceptan() -> None:
    verificar_descuentos_offline([_linea(LINEA_A, "100.00", _auto("100.00"))], Decimal("0.00"))


# --- diferencias de cálculo (causa CALCULO) ---------------------------------------------------


def test_dsc09_iguales_no_dan_diferencias_aunque_cambie_el_orden() -> None:
    enviados = {LINEA_A: [_auto(), _manual()]}
    calculados = {LINEA_A: [_manual(), _auto()]}

    assert diferencias_de_calculo(enviados, calculados) == []


def test_dsc09_una_regla_que_el_servidor_no_aplica_da_una_diferencia_por_linea() -> None:
    enviados = {LINEA_A: [_auto()], LINEA_B: []}
    calculados = {LINEA_A: [], LINEA_B: []}

    diferencias = diferencias_de_calculo(enviados, calculados)

    assert [d["causa"] for d in diferencias] == ["CALCULO"]
    assert diferencias[0]["linea_id"] == str(LINEA_A)
    assert diferencias[0]["esperado"] == [
        {
            "origen": "AUTOMATICO",
            "regla_id": str(REGLA),
            "porcentaje": "0.050000",
            "importe": "1562.50",
        }
    ]
    assert diferencias[0]["calculado"] == []


def test_dsc09_un_importe_distinto_es_una_diferencia() -> None:
    diferencias = diferencias_de_calculo(
        {LINEA_A: [_auto("1562.50")]}, {LINEA_A: [_auto("1500.00")]}
    )

    assert len(diferencias) == 1


def test_dsc09_una_linea_solo_en_los_calculados_con_descuento_es_una_diferencia() -> None:
    diferencias = diferencias_de_calculo({}, {LINEA_B: [_auto()]})

    assert [d["linea_id"] for d in diferencias] == [str(LINEA_B)]


# --- causas del descuento manual (D10) --------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "causa"),
    [
        ("AUTORIZACION_REQUERIDA", "TOPE"),
        ("PERMISO_REQUERIDO", "PERMISO"),
        ("DESCUENTO_MANUAL_DESHABILITADO", "DESHABILITADO"),
        ("MOTIVO_REQUERIDO", "MOTIVO"),
        ("AUTORIZADOR_SIN_PERMISO", "AUTORIZADOR_SIN_PERMISO"),
    ],
)
def test_dsc09_cada_rechazo_del_manual_con_conexion_es_una_causa_sin_conexion(
    codigo: str, causa: str
) -> None:
    assert causa_de_rechazo_del_manual(codigo) == causa


def test_dsc09_un_codigo_ajeno_al_manual_no_es_una_causa() -> None:
    assert causa_de_rechazo_del_manual("DESCUENTO_MANUAL_INVALIDO") is None


def test_dsc09_sin_causas_no_hay_observacion() -> None:
    assert observacion_descuento_difiere([]) is None


def test_dsc09_una_sola_observacion_junta_todas_las_causas() -> None:
    causas: list[dict[str, object]] = [
        {"causa": "CALCULO", "linea_id": str(LINEA_A)},
        {"causa": "TOPE"},
    ]

    observacion = observacion_descuento_difiere(causas)

    assert observacion is not None
    assert observacion.codigo == "DESCUENTO_DIFIERE"
    assert observacion.detalle == {"causas": causas}
    assert observacion.sobre_cobranza is False


# --- autorización declarada (decisión 3 y 4 del usuario, 2026-10-23) --------------------------


def test_cre05_otro_autorizador_es_pin_de_supervisor() -> None:
    assert autorizacion_declarada_de_descuento(
        usuario_id=USUARIO,
        autorizador_enviado=SUPERVISOR,
        usuario_puede_autorizar=False,
        porcentaje_maximo=Decimal("0.10"),
        tope=Decimal("0.05"),
    ) == ("PIN_SUPERVISOR", SUPERVISOR)


def test_cre05_otro_autorizador_dentro_del_tope_hoy_igual_es_pin_de_supervisor() -> None:
    """Decisión 4: autorizador enviado y hoy dentro del tope: se observa igual."""
    assert autorizacion_declarada_de_descuento(
        usuario_id=USUARIO,
        autorizador_enviado=SUPERVISOR,
        usuario_puede_autorizar=False,
        porcentaje_maximo=Decimal("0.03"),
        tope=Decimal("0.05"),
    ) == ("PIN_SUPERVISOR", SUPERVISOR)


def test_cre05_el_mismo_usuario_como_autorizador_es_permiso_propio() -> None:
    assert autorizacion_declarada_de_descuento(
        usuario_id=USUARIO,
        autorizador_enviado=USUARIO,
        usuario_puede_autorizar=True,
        porcentaje_maximo=Decimal("0.10"),
        tope=Decimal("0.05"),
    ) == ("PERMISO_PROPIO", USUARIO)


def test_cre05_sin_autorizador_con_permiso_y_sobre_el_tope_es_permiso_propio() -> None:
    assert autorizacion_declarada_de_descuento(
        usuario_id=USUARIO,
        autorizador_enviado=None,
        usuario_puede_autorizar=True,
        porcentaje_maximo=Decimal("0.10"),
        tope=Decimal("0.05"),
    ) == ("PERMISO_PROPIO", USUARIO)


@pytest.mark.parametrize(
    ("puede", "porcentaje"),
    [(True, "0.05"), (True, "0.01"), (False, "0.10")],
)
def test_cre05_sin_autorizador_dentro_del_tope_o_sin_permiso_no_hay_autorizacion(
    puede: bool, porcentaje: str
) -> None:
    assert autorizacion_declarada_de_descuento(
        usuario_id=USUARIO,
        autorizador_enviado=None,
        usuario_puede_autorizar=puede,
        porcentaje_maximo=Decimal(porcentaje),
        tope=Decimal("0.05"),
    ) == (None, None)


# --- AUTORIZACION_OFFLINE (D9) ----------------------------------------------------------------


def test_d9_la_observacion_lleva_tipo_resolucion_autorizador_y_si_conserva_el_permiso() -> None:
    observacion = observacion_autorizacion_offline(
        tipo="DESCUENTO",
        resolucion="PIN_SUPERVISOR",
        autorizador_id=SUPERVISOR,
        autorizador_con_permiso=False,
    )

    assert observacion.codigo == "AUTORIZACION_OFFLINE"
    assert observacion.detalle == {
        "tipo": "DESCUENTO",
        "resolucion": "PIN_SUPERVISOR",
        "autorizador_id": str(SUPERVISOR),
        "autorizador_con_permiso": False,
    }
    assert observacion.sobre_cobranza is False


def test_d9_el_tipo_credito_tambien_se_describe() -> None:
    observacion = observacion_autorizacion_offline(
        tipo="CREDITO",
        resolucion="PERMISO_PROPIO",
        autorizador_id=USUARIO,
        autorizador_con_permiso=True,
    )

    assert observacion.detalle is not None
    assert observacion.detalle["tipo"] == "CREDITO"
    assert observacion.detalle["autorizador_con_permiso"] is True


@pytest.mark.parametrize("causa", ["TOPE", "AUTORIZADOR_SIN_PERMISO"])
def test_d10_las_causas_de_tope_llevan_el_tope_y_el_porcentaje(causa: str) -> None:
    detalle = detalle_de_causa_del_manual(causa, porcentaje=Decimal("0.1"), tope=Decimal("0.05"))

    assert detalle == {"causa": causa, "porcentaje_maximo": "0.100000", "tope": "0.050000"}


@pytest.mark.parametrize("causa", ["PERMISO", "DESHABILITADO", "MOTIVO"])
def test_d10_las_demas_causas_del_manual_no_llevan_datos_de_tope(causa: str) -> None:
    detalle = detalle_de_causa_del_manual(causa, porcentaje=Decimal("0.1"), tope=Decimal("0.05"))

    assert detalle == {"causa": causa}
