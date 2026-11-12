"""Tarea 10.1 (change 18b; spec `ventas/credito-en-la-venta`, requisito "Sin conexión el servidor
congela la evaluación del dispositivo y nunca rechaza por crédito"; `design.md` D7): la evaluación
que trae una venta sin conexión se revisa solo contra sí misma (coherencia y forma), con el motor
puro de `clientes/domain/credito.py`. Nunca consulta la política vigente ni la tolerancia: lo que
el dispositivo no pudo saber no rechaza (SYN-05, INV-17).

Reglas citadas: CRE-06, CRE-08, CRE-09, SYN-05, SYN-06, INV-17.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.clientes.domain.credito import (
    calcular_exceso,
    evaluar_credito,
    evaluar_credito_del_dispositivo,
    verificar_forma_del_credito_del_dispositivo,
)
from app.modules.clientes.domain.errores import CreditoInconsistenteError

AUTORIZADOR = uuid4()


def _del_dispositivo(**cambios: object):
    """Ejemplo de `01` §9.2: límite $200.000, saldo $150.000, venta $80.000 con cobranza $20.000:
    resultante $210.000, exceso $10.000."""
    valores: dict[str, object] = {
        "limite": Decimal("200000.00"),
        "saldo_considerado": Decimal("150000.00"),
        "total_venta": Decimal("80000.00"),
        "cobranza": Decimal("20000.00"),
        "politica": "AUTORIZAR",
        "resolucion": "TOLERANCIA_OFFLINE",
        "autorizador_id": None,
    }
    valores.update(cambios)
    return evaluar_credito_del_dispositivo(**valores)  # type: ignore[arg-type]


# --- calcular_exceso (CRE-01, CRE-02, D5) -----------------------------------------------------


def test_cre02_el_ejemplo_de_la_regla_da_resultante_210000_y_exceso_10000() -> None:
    calculo = calcular_exceso(
        limite=Decimal("200000.00"),
        saldo_actual=Decimal("150000.00"),
        total_venta=Decimal("80000.00"),
        cobranza=Decimal("20000.00"),
    )

    assert (calculo.disponible, calculo.saldo_resultante, calculo.exceso) == (
        Decimal("50000.00"),
        Decimal("210000.00"),
        Decimal("10000.00"),
    )


def test_cre07_una_venta_cobrada_entera_no_tiene_exceso_aunque_el_cliente_ya_este_excedido() -> (
    None
):
    calculo = calcular_exceso(
        limite=Decimal("200000.00"),
        saldo_actual=Decimal("210000.00"),
        total_venta=Decimal("30000.00"),
        cobranza=Decimal("30000.00"),
    )

    assert calculo.exceso == Decimal("0.00")
    assert calculo.disponible == Decimal("-10000.00")


def test_cre01_sin_limite_no_hay_disponible_ni_exceso() -> None:
    calculo = calcular_exceso(
        limite=None,
        saldo_actual=Decimal("500000.00"),
        total_venta=Decimal("80000.00"),
        cobranza=Decimal("0.00"),
    )

    assert (calculo.disponible, calculo.exceso) == (None, Decimal("0.00"))


def test_cre02_el_motor_con_conexion_sigue_dando_lo_mismo_tras_extraer_el_calculo() -> None:
    resultado = evaluar_credito(
        limite=Decimal("200000.00"),
        saldo_actual=Decimal("150000.00"),
        total_venta=Decimal("80000.00"),
        cobranza=Decimal("20000.00"),
        politica="AUTORIZAR",
        tolerancia_tipo="IMPORTE",
        tolerancia_valor=Decimal("20000.00"),
        modo="SIN_CONEXION",
        acepta_exceso=False,
        usuario_id="u",
        permisos_usuario=frozenset(),
        autorizador=None,
    )

    assert (resultado.exceso, resultado.resolucion) == (
        Decimal("10000.00"),
        "TOLERANCIA_OFFLINE",
    )


@pytest.mark.parametrize("campo", ["saldo_actual", "total_venta", "cobranza"])
def test_inv03_el_calculo_del_exceso_rechaza_el_punto_flotante(campo: str) -> None:
    valores: dict[str, object] = {
        "limite": Decimal("200000.00"),
        "saldo_actual": Decimal("1.00"),
        "total_venta": Decimal("1.00"),
        "cobranza": Decimal("0.00"),
    }
    valores[campo] = 1.5

    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_exceso(**valores)  # type: ignore[arg-type]


# --- la evaluación del dispositivo se congela (CRE-06, CRE-09) --------------------------------


def test_cre06_la_tolerancia_del_dispositivo_se_congela_con_disponible_y_exceso_del_motor() -> None:
    evaluacion = _del_dispositivo()

    assert evaluacion.resolucion == "TOLERANCIA_OFFLINE"
    assert (evaluacion.disponible, evaluacion.exceso) == (Decimal("50000.00"), Decimal("10000.00"))
    assert evaluacion.autorizador_id is None


def test_cre06_no_se_valida_el_tamano_de_la_tolerancia_que_uso_el_dispositivo() -> None:
    """El dispositivo no manda la tolerancia que usó: un exceso grande con `TOLERANCIA_OFFLINE`
    se acepta; la oficina lo ve por `EXCESO_CREDITO_AUTORIZADO_OFFLINE`."""
    evaluacion = _del_dispositivo(total_venta=Decimal("500000.00"))

    assert evaluacion.exceso > Decimal("10000.00")
    assert evaluacion.resolucion == "TOLERANCIA_OFFLINE"


@pytest.mark.parametrize("resolucion", ["PIN_SUPERVISOR", "PERMISO_PROPIO"])
def test_cre05_pin_o_permiso_propio_conservan_el_autorizador_del_dispositivo(
    resolucion: str,
) -> None:
    evaluacion = _del_dispositivo(resolucion=resolucion, autorizador_id=AUTORIZADOR)

    assert evaluacion.resolucion == resolucion
    assert evaluacion.autorizador_id == str(AUTORIZADOR)


def test_cre06_una_advertencia_aceptada_no_lleva_autorizador_aunque_el_dispositivo_lo_mande() -> (
    None
):
    evaluacion = _del_dispositivo(
        resolucion="ADVERTENCIA_ACEPTADA", politica="ADVERTIR", autorizador_id=AUTORIZADOR
    )

    assert evaluacion.autorizador_id is None


def test_cre09_la_politica_vigente_no_entra_en_la_evaluacion_del_dispositivo() -> None:
    """Política BLOQUEAR en el dispositivo con resolución `TOLERANCIA_OFFLINE`: se acepta tal cual
    (el servidor nunca rechaza por crédito, SYN-05)."""
    evaluacion = _del_dispositivo(politica="BLOQUEAR")

    assert evaluacion.resolucion == "TOLERANCIA_OFFLINE"


# --- coherencia consigo misma (CREDITO_INCONSISTENTE, SYN-06) ---------------------------------


def test_syn06_un_exceso_propio_con_resolucion_sin_exceso_es_incoherente() -> None:
    with pytest.raises(CreditoInconsistenteError) as error:
        _del_dispositivo(resolucion="SIN_EXCESO")

    assert error.value.codigo == "CREDITO_INCONSISTENTE"
    assert error.value.status_http == 422


def test_syn06_sin_exceso_y_sin_exceso_es_coherente() -> None:
    evaluacion = _del_dispositivo(
        saldo_considerado=Decimal("100000.00"),
        total_venta=Decimal("30000.00"),
        cobranza=Decimal("0.00"),
        resolucion="SIN_EXCESO",
    )

    assert (evaluacion.exceso, evaluacion.resolucion) == (Decimal("0.00"), "SIN_EXCESO")


@pytest.mark.parametrize("resolucion", ["ADVERTENCIA_ACEPTADA", "TOLERANCIA_OFFLINE"])
def test_syn05_sin_exceso_propio_una_resolucion_distinta_de_sin_exceso_se_acepta_tal_cual(
    resolucion: str,
) -> None:
    """Decisión del usuario, 2026-10-23: exceso 0 con resolución distinta de `SIN_EXCESO` se
    acepta tal cual (la tolerancia no se valida)."""
    evaluacion = _del_dispositivo(
        saldo_considerado=Decimal("100000.00"),
        total_venta=Decimal("30000.00"),
        cobranza=Decimal("0.00"),
        resolucion=resolucion,
        politica="ADVERTIR",
    )

    assert evaluacion.exceso == Decimal("0.00")
    assert evaluacion.resolucion == resolucion


@pytest.mark.parametrize("resolucion", ["PIN_SUPERVISOR", "PERMISO_PROPIO"])
def test_syn06_pin_o_permiso_propio_sin_autorizador_es_incoherente(resolucion: str) -> None:
    with pytest.raises(CreditoInconsistenteError):
        _del_dispositivo(resolucion=resolucion, autorizador_id=None)


def test_syn06_sin_limite_toda_resolucion_distinta_de_sin_exceso_es_incoherente() -> None:
    """La base lo exige (`ck_venta__credito_sin_control`): sin límite no hay control."""
    with pytest.raises(CreditoInconsistenteError):
        _del_dispositivo(limite=None, resolucion="TOLERANCIA_OFFLINE")


def test_cre01_sin_limite_con_sin_exceso_se_congela_sin_disponible_ni_exceso() -> None:
    evaluacion = _del_dispositivo(limite=None, resolucion="SIN_EXCESO")

    assert (evaluacion.disponible, evaluacion.exceso) == (None, Decimal("0.00"))


def test_d17_el_consumidor_final_no_se_juzga_por_su_exceso_pero_si_por_su_forma() -> None:
    """Límite cero y deuda: la resolución `SIN_EXCESO` no se rechaza (la regla del consumidor
    final es `CONSUMIDOR_FINAL_CON_DEUDA`, no el crédito); `PIN_SUPERVISOR` sin autorizador sí
    (la base lo exige)."""
    evaluacion = _del_dispositivo(
        limite=Decimal("0.00"),
        saldo_considerado=Decimal("0.00"),
        total_venta=Decimal("5000.00"),
        cobranza=Decimal("3000.00"),
        resolucion="SIN_EXCESO",
        coherencia_del_exceso=False,
    )

    assert evaluacion.exceso == Decimal("2000.00")
    with pytest.raises(CreditoInconsistenteError):
        _del_dispositivo(
            limite=Decimal("0.00"),
            resolucion="PIN_SUPERVISOR",
            autorizador_id=None,
            coherencia_del_exceso=False,
        )


# --- la forma (paso 0 de D18: contenido malformado) -------------------------------------------


@pytest.mark.parametrize("faltante", ["saldo_considerado", "politica", "resolucion"])
def test_syn06_un_dato_obligatorio_ausente_es_incoherente(faltante: str) -> None:
    valores: dict[str, object] = {
        "limite": Decimal("200000.00"),
        "saldo_considerado": Decimal("150000.00"),
        "politica": "AUTORIZAR",
        "resolucion": "TOLERANCIA_OFFLINE",
        "autorizador_id": None,
    }
    valores[faltante] = None

    with pytest.raises(CreditoInconsistenteError):
        verificar_forma_del_credito_del_dispositivo(**valores)  # type: ignore[arg-type]


def test_syn06_un_limite_negativo_es_incoherente() -> None:
    with pytest.raises(CreditoInconsistenteError):
        verificar_forma_del_credito_del_dispositivo(
            limite=Decimal("-1.00"),
            saldo_considerado=Decimal("0.00"),
            politica="ADVERTIR",
            resolucion="SIN_EXCESO",
            autorizador_id=None,
        )


def test_syn06_una_politica_o_resolucion_fuera_del_catalogo_es_incoherente() -> None:
    for politica, resolucion in (("OTRA", "SIN_EXCESO"), ("ADVERTIR", "OTRA")):
        with pytest.raises(CreditoInconsistenteError):
            verificar_forma_del_credito_del_dispositivo(
                limite=Decimal("1.00"),
                saldo_considerado=Decimal("0.00"),
                politica=politica,
                resolucion=resolucion,
                autorizador_id=None,
            )


def test_syn06_una_forma_valida_no_lanza() -> None:
    verificar_forma_del_credito_del_dispositivo(
        limite=Decimal("200000.00"),
        saldo_considerado=Decimal("150000.00"),
        politica="AUTORIZAR",
        resolucion="PIN_SUPERVISOR",
        autorizador_id=AUTORIZADOR,
    )


def test_el_error_es_un_error_de_dominio_con_codigo_estable() -> None:
    assert issubclass(CreditoInconsistenteError, DomainError)
    assert CreditoInconsistenteError.codigo == "CREDITO_INCONSISTENTE"
