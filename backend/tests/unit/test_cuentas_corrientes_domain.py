"""Unitarias de `cuentas_corrientes/domain/` (tarea 3.1).

Funciones puras (`CLAUDE.md` §4): ninguna toca la base. Al menos dos casos por
comportamiento, para que una prueba que pasa por el motivo equivocado no deje
hueco.

Reglas citadas: CC-01, CC-02, CC-03, CC-04, CC-05, CLI-03, INV-03 y
`design.md` D3, D4, D12.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.modules.cuentas_corrientes.domain.catalogo import (
    AUMENTA,
    CLIENTE,
    PROVEEDOR,
    REDUCE,
    TIPOS_POR_CUENTA,
    sentido_de_tipo,
    validar_cuenta_tipo,
    validar_sentido,
    validar_tipo_de_movimiento,
)
from app.modules.cuentas_corrientes.domain.errores import (
    ConsumidorFinalSinCuentaError,
    CuentaConOperacionesError,
    CuentaTipoInvalidoError,
    ImporteInvalidoError,
    SentidoInvalidoError,
    TipoMovimientoInvalidoError,
)
from app.modules.cuentas_corrientes.domain.importe import IMPORTE_MAXIMO, validar_importe
from app.modules.cuentas_corrientes.domain.reglas import (
    efecto_sobre_saldo,
    saldo_de,
    validar_cuenta_con_titular,
    validar_saldo_inicial_admitido,
)

# --------------------------------------------------------------------------
# catalogo.py -- tipos por cuenta (CC-02, CC-03, D12)
# --------------------------------------------------------------------------


def test_el_catalogo_de_cliente_es_el_de_cc_02_de_la_etapa_1() -> None:
    """CC-02 sin IVA (D12-A: los tipos de IVA los agrega facturación)."""
    assert TIPOS_POR_CUENTA[CLIENTE] == frozenset(
        {"SALDO_INICIAL", "VENTA", "ANULACION_VENTA", "COBRANZA", "ANULACION_COBRANZA"}
    )


def test_el_catalogo_de_proveedor_es_el_de_cc_03() -> None:
    assert TIPOS_POR_CUENTA[PROVEEDOR] == frozenset(
        {"SALDO_INICIAL", "COMPRA", "ANULACION_COMPRA", "PAGO", "ANULACION_PAGO"}
    )


@pytest.mark.parametrize(
    ("cuenta_tipo", "tipo"),
    [
        ("CLIENTE", "SALDO_INICIAL"),
        ("CLIENTE", "COBRANZA"),
        ("PROVEEDOR", "SALDO_INICIAL"),
        ("PROVEEDOR", "PAGO"),
    ],
)
def test_un_tipo_de_la_cuenta_se_acepta(cuenta_tipo: str, tipo: str) -> None:
    """CC-02, CC-03."""
    assert validar_tipo_de_movimiento(cuenta_tipo, tipo) == tipo


@pytest.mark.parametrize(
    ("cuenta_tipo", "tipo"),
    [
        ("CLIENTE", "COMPRA"),
        ("CLIENTE", "PAGO"),
        ("PROVEEDOR", "VENTA"),
        ("PROVEEDOR", "COBRANZA"),
        ("CLIENTE", "AJUSTE"),
        ("CLIENTE", "IVA_FACTURA"),
        ("CLIENTE", "saldo_inicial"),
    ],
)
def test_un_tipo_que_no_es_de_la_cuenta_se_rechaza(cuenta_tipo: str, tipo: str) -> None:
    """CC-02, CC-03, D12: `TIPO_MOVIMIENTO_INVALIDO`."""
    with pytest.raises(TipoMovimientoInvalidoError) as error:
        validar_tipo_de_movimiento(cuenta_tipo, tipo)
    assert error.value.codigo == "TIPO_MOVIMIENTO_INVALIDO"


def test_un_tipo_de_movimiento_con_cuenta_desconocida_se_rechaza() -> None:
    with pytest.raises(CuentaTipoInvalidoError):
        validar_tipo_de_movimiento("EMPLEADO", "SALDO_INICIAL")


@pytest.mark.parametrize("cuenta_tipo", ["CLIENTE", "PROVEEDOR"])
def test_los_tipos_de_cuenta_validos_pasan(cuenta_tipo: str) -> None:
    assert validar_cuenta_tipo(cuenta_tipo) == cuenta_tipo


@pytest.mark.parametrize("cuenta_tipo", ["EMPLEADO", "cliente", ""])
def test_un_tipo_de_cuenta_fuera_del_catalogo_se_rechaza(cuenta_tipo: str) -> None:
    with pytest.raises(CuentaTipoInvalidoError) as error:
        validar_cuenta_tipo(cuenta_tipo)
    assert error.value.codigo == "CUENTA_TIPO_INVALIDO"


@pytest.mark.parametrize("sentido", ["AUMENTA", "REDUCE"])
def test_los_sentidos_validos_pasan(sentido: str) -> None:
    assert validar_sentido(sentido) == sentido


@pytest.mark.parametrize("sentido", ["SUMA", "aumenta", ""])
def test_un_sentido_fuera_del_catalogo_se_rechaza(sentido: str) -> None:
    """CC-01: `AUMENTA` o `REDUCE`."""
    with pytest.raises(SentidoInvalidoError) as error:
        validar_sentido(sentido)
    assert error.value.codigo == "SENTIDO_INVALIDO"


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        ("VENTA", AUMENTA),
        ("ANULACION_VENTA", REDUCE),
        ("COBRANZA", REDUCE),
        ("ANULACION_COBRANZA", AUMENTA),
        ("COMPRA", AUMENTA),
        ("ANULACION_COMPRA", REDUCE),
        ("PAGO", REDUCE),
        ("ANULACION_PAGO", AUMENTA),
    ],
)
def test_los_tipos_de_operacion_tienen_un_sentido_fijo(tipo: str, esperado: str) -> None:
    """CC-05 (la venta debita, la cobranza acredita) y su anulación al revés."""
    assert sentido_de_tipo(tipo) == esperado


def test_el_saldo_inicial_admite_los_dos_sentidos() -> None:
    """`01` §21: el saldo inicial puede ser + o − (D3)."""
    assert sentido_de_tipo("SALDO_INICIAL") is None


# --------------------------------------------------------------------------
# importe.py -- CC-01, INV-03
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("150000.00", Decimal("150000.00")),
        ("0.01", Decimal("0.01")),
        ("20000", Decimal("20000.00")),
        ("100.5", Decimal("100.50")),
        (Decimal("80000.00"), Decimal("80000.00")),
        (Decimal("5"), Decimal("5.00")),
    ],
)
def test_un_importe_positivo_con_hasta_dos_decimales_se_acepta(
    entrada: str | Decimal, esperado: Decimal
) -> None:
    resultado = validar_importe(entrada)
    assert resultado == esperado
    assert resultado.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "entrada",
    [
        "0.00",
        "0",
        "-100.00",
        "-0.01",
        "100.005",
        "0.001",
        "abc",
        "",
        " 100.00",
        "1_000.00",
        "1e3",
        "NaN",
        "Infinity",
        Decimal("0"),
        Decimal("-1.00"),
        Decimal("100.005"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_un_importe_no_positivo_o_con_mas_de_dos_decimales_se_rechaza(
    entrada: str | Decimal,
) -> None:
    """CC-01, INV-03: sin redondear, `IMPORTE_INVALIDO`."""
    with pytest.raises(ImporteInvalidoError) as error:
        validar_importe(entrada)
    assert error.value.codigo == "IMPORTE_INVALIDO"


@pytest.mark.parametrize("entrada", [150000.5, 100, True, None, ["1.00"]])
def test_un_importe_que_no_es_string_ni_decimal_se_rechaza(entrada: object) -> None:
    """INV-03: un número JSON (float o int) no es dinero exacto."""
    with pytest.raises(ImporteInvalidoError):
        validar_importe(entrada)


def test_el_importe_maximo_es_el_de_numeric_14_2() -> None:
    assert Decimal("999999999999.99") == IMPORTE_MAXIMO
    assert validar_importe("999999999999.99") == IMPORTE_MAXIMO


@pytest.mark.parametrize("entrada", ["1000000000000.00", Decimal("99999999999999.99")])
def test_un_importe_que_no_entra_en_numeric_14_2_se_rechaza(entrada: str | Decimal) -> None:
    with pytest.raises(ImporteInvalidoError):
        validar_importe(entrada)


# --------------------------------------------------------------------------
# reglas.py -- efecto (CC-04), D3, D4
# --------------------------------------------------------------------------


def test_un_movimiento_que_aumenta_suma_su_importe() -> None:
    assert efecto_sobre_saldo(AUMENTA, Decimal("150000.00")) == Decimal("150000.00")


def test_un_movimiento_que_reduce_resta_su_importe() -> None:
    """CC-04: el saldo negativo es saldo a favor (`01` §2)."""
    assert efecto_sobre_saldo(REDUCE, Decimal("20000.00")) == Decimal("-20000.00")


def test_el_efecto_de_un_sentido_desconocido_se_rechaza() -> None:
    with pytest.raises(SentidoInvalidoError):
        efecto_sobre_saldo("SUMA", Decimal("1.00"))


def test_el_saldo_es_lo_que_aumenta_menos_lo_que_reduce() -> None:
    """CC-04: 150.000 − 20.000 = 130.000."""
    movimientos = [(AUMENTA, Decimal("150000.00")), (REDUCE, Decimal("20000.00"))]
    assert saldo_de(movimientos) == Decimal("130000.00")


def test_el_saldo_de_una_cuenta_sin_movimientos_es_cero() -> None:
    assert saldo_de([]) == Decimal("0.00")


def test_el_saldo_solo_con_reducciones_es_negativo() -> None:
    assert saldo_de([(REDUCE, Decimal("20000.00"))]) == Decimal("-20000.00")


def test_el_saldo_inicial_se_admite_sin_movimientos_de_otro_tipo() -> None:
    """D3: varios `SALDO_INICIAL` sí, la corrección es otro en sentido inverso."""
    validar_saldo_inicial_admitido(tiene_movimientos_de_otro_tipo=False)


def test_el_saldo_inicial_se_rechaza_si_la_cuenta_tiene_otras_operaciones() -> None:
    """D3: `CUENTA_CON_OPERACIONES`, la corrección espera a los ajustes."""
    with pytest.raises(CuentaConOperacionesError) as error:
        validar_saldo_inicial_admitido(tiene_movimientos_de_otro_tipo=True)
    assert error.value.codigo == "CUENTA_CON_OPERACIONES"
    assert error.value.status_http == 409


@pytest.mark.parametrize(
    ("cuenta_tipo", "es_consumidor_final"),
    [("CLIENTE", False), ("PROVEEDOR", False), ("PROVEEDOR", True)],
)
def test_una_cuenta_con_titular_identificable_se_acepta(
    cuenta_tipo: str, es_consumidor_final: bool
) -> None:
    """D4: solo el cliente consumidor final queda fuera; un proveedor nunca lo es."""
    validar_cuenta_con_titular(cuenta_tipo, es_consumidor_final=es_consumidor_final)


def test_el_consumidor_final_no_tiene_saldo_inicial() -> None:
    """CLI-03, D4: `CONSUMIDOR_FINAL_SIN_CUENTA`."""
    with pytest.raises(ConsumidorFinalSinCuentaError) as error:
        validar_cuenta_con_titular("CLIENTE", es_consumidor_final=True)
    assert error.value.codigo == "CONSUMIDOR_FINAL_SIN_CUENTA"
    assert error.value.status_http == 422


def test_todos_los_errores_del_modulo_son_errores_de_dominio_con_codigo_propio() -> None:
    errores = [
        TipoMovimientoInvalidoError,
        ImporteInvalidoError,
        CuentaConOperacionesError,
        ConsumidorFinalSinCuentaError,
        CuentaTipoInvalidoError,
        SentidoInvalidoError,
    ]
    codigos = {error.codigo for error in errores}
    assert all(issubclass(error, DomainError) for error in errores)
    assert len(codigos) == len(errores)
