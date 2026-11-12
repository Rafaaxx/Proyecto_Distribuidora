"""Change 18b, tarea 2.1: pruebas del motor de crédito (`clientes/domain/credito.py`) más allá de
los casos compartidos `cre01` (CRE-01 a CRE-07, INV-03, ADR-032; `design.md` D5, D6, D8)."""

from __future__ import annotations

from decimal import Decimal
from itertools import product
from typing import Any

import pytest

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.credito import Autorizador, evaluar_credito
from app.modules.clientes.domain.errores import (
    AutorizacionCreditoRequeridaError,
    AutorizadorSinPermisoError,
    CreditoExcedidoError,
    ExcesoCreditoSinAceptarError,
    ModoDeCreditoInvalidoError,
    PoliticaCreditoInvalidaError,
    ToleranciaOfflineInvalidaError,
)

D = Decimal


def _evaluar(**cambios: Any) -> Any:
    base: dict[str, Any] = {
        "limite": D("200000.00"),
        "saldo_actual": D("150000.00"),
        "total_venta": D("80000.00"),
        "cobranza": D("20000.00"),
        "politica": "ADVERTIR",
        "tolerancia_tipo": None,
        "tolerancia_valor": None,
        "modo": "CON_CONEXION",
        "acepta_exceso": True,
        "usuario_id": "u-vendedor",
        "permisos_usuario": frozenset(),
        "autorizador": None,
    }
    return evaluar_credito(**{**base, **cambios})


def test_el_motor_se_expone_por_el_service_de_clientes() -> None:
    """D5: la evaluación vive en `clientes/domain` y los otros módulos la usan por `service`."""
    assert clientes_service.evaluar_credito is evaluar_credito
    assert clientes_service.Autorizador is Autorizador


def test_el_ejemplo_de_9_2_da_disponible_resultante_y_exceso() -> None:
    """CRE-01, CRE-02, CRE-03: límite 200.000, saldo 150.000, venta 80.000, cobranza 20.000."""
    resultado = _evaluar()

    assert resultado.disponible == D("50000.00")
    assert resultado.saldo_resultante == D("210000.00")
    assert resultado.exceso == D("10000.00")
    assert resultado.resolucion == "ADVERTENCIA_ACEPTADA"
    assert resultado.autorizador_id is None


def test_los_importes_salen_con_dos_decimales_aunque_entren_sin_ellos() -> None:
    """INV-03: la salida es `numeric(14,2)`; un `Decimal("5")` entra y sale como `5.00`."""
    resultado = _evaluar(limite=D("100"), saldo_actual=D("0"), total_venta=D("40"), cobranza=D("0"))

    assert str(resultado.disponible) == "100.00"
    assert str(resultado.saldo_resultante) == "40.00"
    assert str(resultado.exceso) == "0.00"
    assert str(resultado.tolerancia) == "0.00"


@pytest.mark.parametrize(
    ("total", "cobranza", "esperado"),
    [
        ("30000.00", "30000.00", "0.00"),  # cobrada entera: nunca exceso (D5)
        ("30000.00", "40000.00", "0.00"),  # cobra de más: sigue sin exceso
        ("30000.00", "29999.99", "0.01"),  # un centavo de deuda en un cliente excedido
        ("30000.00", "0.00", "30000.00"),  # toda la venta a cuenta
    ],
)
def test_el_exceso_de_un_cliente_ya_excedido_es_solo_lo_que_la_venta_agrega(
    total: str, cobranza: str, esperado: str
) -> None:
    """D5: `exceso = mín(máx(0, total - cobranza), máx(0, resultante - límite))`."""
    resultado = _evaluar(
        saldo_actual=D("250000.00"), total_venta=D(total), cobranza=D(cobranza), acepta_exceso=True
    )

    assert resultado.exceso == D(esperado)


def test_el_exceso_nunca_supera_la_parte_no_cobrada_ni_es_negativo() -> None:
    """D5, CRE-02: barrido de combinaciones; el exceso está entre cero y lo que queda a cuenta."""
    saldos = [D("-5000.00"), D("0.00"), D("100000.00"), D("199999.99"), D("260000.00")]
    totales = [D("0.00"), D("0.01"), D("50000.00"), D("120000.00")]
    cobranzas = [D("0.00"), D("0.01"), D("50000.00"), D("130000.00")]

    for saldo, total, cobranza in product(saldos, totales, cobranzas):
        resultado = _evaluar(saldo_actual=saldo, total_venta=total, cobranza=cobranza)
        no_cobrado = max(D("0.00"), total - cobranza)
        assert D("0.00") <= resultado.exceso <= no_cobrado
        assert resultado.saldo_resultante == saldo + total - cobranza


def test_sin_limite_no_hay_disponible_ni_exceso_con_cualquier_politica() -> None:
    """CRE-01: límite vacío significa sin control, aun con BLOQUEAR."""
    for politica in ("ADVERTIR", "AUTORIZAR", "BLOQUEAR"):
        resultado = _evaluar(limite=None, politica=politica, acepta_exceso=False)
        assert resultado.disponible is None
        assert resultado.exceso == D("0.00")
        assert resultado.resolucion == "SIN_EXCESO"


def test_sin_limite_la_tolerancia_porcentual_vale_cero() -> None:
    """D8: el porcentaje se calcula sobre el límite; sin límite no hay sobre qué."""
    resultado = _evaluar(
        limite=None, tolerancia_tipo="PORCENTAJE", tolerancia_valor=D("5.00"), modo="SIN_CONEXION"
    )

    assert resultado.tolerancia == D("0.00")


def test_los_codigos_y_estados_de_los_rechazos_son_estables() -> None:
    """D6: 409 para exceso sin aceptar y crédito excedido; 403 para autorización."""
    esperados = [
        (ExcesoCreditoSinAceptarError, "EXCESO_CREDITO_SIN_ACEPTAR", 409),
        (CreditoExcedidoError, "CREDITO_EXCEDIDO", 409),
        (AutorizacionCreditoRequeridaError, "AUTORIZACION_CREDITO_REQUERIDA", 403),
        (AutorizadorSinPermisoError, "AUTORIZADOR_SIN_PERMISO", 403),
        (ModoDeCreditoInvalidoError, "MODO_CREDITO_INVALIDO", 422),
    ]
    for clase, codigo, estado in esperados:
        assert issubclass(clase, DomainError)
        assert (clase.codigo, clase.status_http) == (codigo, estado)


def test_advertir_sin_aceptar_se_rechaza_y_aceptando_se_confirma() -> None:
    """CRE-04, D6."""
    with pytest.raises(ExcesoCreditoSinAceptarError):
        _evaluar(acepta_exceso=False)

    assert _evaluar(acepta_exceso=True).resolucion == "ADVERTENCIA_ACEPTADA"


def test_advertir_sin_exceso_no_pide_aceptacion() -> None:
    """CRE-04: sin exceso no hay nada que aceptar."""
    resultado = _evaluar(cobranza=D("80000.00"), acepta_exceso=False)

    assert resultado.resolucion == "SIN_EXCESO"


def test_bloquear_no_admite_excepcion_ni_con_permiso_ni_con_autorizador() -> None:
    """CRE-07, D6: BLOQUEAR rechaza aunque quien vende tenga SUPERAR_CREDITO."""
    supervisor = Autorizador("u-sup", frozenset({"SUPERAR_CREDITO"}))
    with pytest.raises(CreditoExcedidoError):
        _evaluar(
            politica="BLOQUEAR",
            permisos_usuario=frozenset({"SUPERAR_CREDITO"}),
            autorizador=supervisor,
        )


def test_autorizar_con_otro_permiso_no_cuenta_solo_superar_credito() -> None:
    """CRE-05: AUTORIZAR_DESCUENTO no autoriza un exceso de crédito."""
    with pytest.raises(AutorizacionCreditoRequeridaError):
        _evaluar(politica="AUTORIZAR", permisos_usuario=frozenset({"AUTORIZAR_DESCUENTO"}))

    con_permiso_ajeno = Autorizador("u-sup", frozenset({"AUTORIZAR_DESCUENTO"}))
    with pytest.raises(AutorizadorSinPermisoError):
        _evaluar(politica="AUTORIZAR", autorizador=con_permiso_ajeno)


def test_sin_conexion_el_exceso_igual_a_la_tolerancia_pasa_y_un_centavo_mas_no() -> None:
    """D8: se confirma con tolerancia si `exceso <= tolerancia`."""
    pasa = _evaluar(
        politica="AUTORIZAR",
        modo="SIN_CONEXION",
        tolerancia_tipo="IMPORTE",
        tolerancia_valor=D("10000.00"),
    )
    assert pasa.resolucion == "TOLERANCIA_OFFLINE"

    with pytest.raises(CreditoExcedidoError):
        _evaluar(
            politica="AUTORIZAR",
            modo="SIN_CONEXION",
            tolerancia_tipo="IMPORTE",
            tolerancia_valor=D("9999.99"),
        )


def test_la_tolerancia_gana_al_permiso_propio_cuando_alcanza() -> None:
    """CRE-06: dentro de la tolerancia la venta se confirma como `TOLERANCIA_OFFLINE`, sin
    registrar un autorizador que no hizo falta."""
    resultado = _evaluar(
        politica="AUTORIZAR",
        modo="SIN_CONEXION",
        tolerancia_tipo="IMPORTE",
        tolerancia_valor=D("10000.00"),
        permisos_usuario=frozenset({"SUPERAR_CREDITO"}),
    )

    assert resultado.resolucion == "TOLERANCIA_OFFLINE"
    assert resultado.autorizador_id is None


@pytest.mark.parametrize(
    "campo",
    ["limite", "saldo_actual", "total_venta", "cobranza", "tolerancia_valor"],
)
@pytest.mark.parametrize("invalido", [1.5, True])
def test_un_importe_de_punto_flotante_o_booleano_se_rechaza(campo: str, invalido: Any) -> None:
    """INV-03: ningún importe entra como `float` ni `bool`."""
    cambios: dict[str, Any] = {campo: invalido}
    if campo == "tolerancia_valor":
        cambios["tolerancia_tipo"] = "IMPORTE"

    with pytest.raises(EntradaNoEsDineroExactoError) as error:
        _evaluar(**cambios)
    assert error.value.codigo == "ENTRADA_NO_ES_DINERO_EXACTO"


def test_una_politica_fuera_del_catalogo_se_rechaza() -> None:
    """CRE-03: el motor recibe la política ya resuelta; vacía o desconocida es un error."""
    for politica in ("PERMITIR", "", None):
        with pytest.raises(PoliticaCreditoInvalidaError):
            _evaluar(politica=politica)


def test_un_modo_fuera_del_catalogo_se_rechaza() -> None:
    with pytest.raises(ModoDeCreditoInvalidoError):
        _evaluar(modo="HIBRIDO")


def test_una_tolerancia_a_medias_o_negativa_se_rechaza() -> None:
    """CRE-06: el par tipo/valor se informa completo y no es negativo."""
    with pytest.raises(ToleranciaOfflineInvalidaError):
        _evaluar(tolerancia_tipo="IMPORTE", tolerancia_valor=None)
    with pytest.raises(ToleranciaOfflineInvalidaError):
        _evaluar(tolerancia_tipo="PORCENTAJE", tolerancia_valor=D("-1.00"))


@pytest.mark.parametrize(
    ("cambios", "clase"),
    [
        ({"politica": "ADVERTIR", "acepta_exceso": False}, ExcesoCreditoSinAceptarError),
        ({"politica": "BLOQUEAR"}, CreditoExcedidoError),
        ({"politica": "AUTORIZAR"}, AutorizacionCreditoRequeridaError),
        (
            {"politica": "AUTORIZAR", "autorizador": Autorizador("u-marta", frozenset())},
            AutorizadorSinPermisoError,
        ),
    ],
)
def test_cada_rechazo_trae_la_evaluacion_para_mostrarla_d6(
    cambios: dict[str, Any], clase: type[DomainError]
) -> None:
    """D6 (change 18b, lote 3): límite, saldo considerado, disponible, exceso y política viajan en
    la extensión del error, como texto (INV-03)."""
    with pytest.raises(clase) as error:
        _evaluar(**cambios)

    assert error.value.extension == {
        "limite": "200000.00",
        "saldo_considerado": "150000.00",
        "disponible": "50000.00",
        "exceso": "10000.00",
        "politica": cambios["politica"],
    }


def test_la_evaluacion_del_rechazo_sigue_los_valores_de_la_venta() -> None:
    """Triangula con otros importes: límite $100.000, saldo $90.000, venta $50.000 sin cobranza."""
    with pytest.raises(CreditoExcedidoError) as error:
        _evaluar(
            limite=D("100000"),
            saldo_actual=D("90000"),
            total_venta=D("50000"),
            cobranza=D("0"),
            politica="BLOQUEAR",
        )

    assert error.value.extension == {
        "limite": "100000.00",
        "saldo_considerado": "90000.00",
        "disponible": "10000.00",
        "exceso": "40000.00",
        "politica": "BLOQUEAR",
    }
