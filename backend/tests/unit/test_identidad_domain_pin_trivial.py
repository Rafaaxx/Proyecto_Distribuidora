"""Tarea 6.4 (change 18b; `design.md` D21 punto 6, ADR-019): `validar_formato_pin_autorizacion`
rechaza el PIN trivial -- todos los dígitos iguales o una escalera de paso 1, ascendente o
descendente, sin vuelta -- sin poner el valor en el mensaje, y sigue aceptando los PIN que no lo
son.

Reglas citadas: SEG-05, ADR-019 (qué es un PIN trivial), ADR-011.
"""

from __future__ import annotations

import pytest

from app.modules.identidad.domain.usuarios import (
    PinAutorizacionInvalidoError,
    validar_formato_pin_autorizacion,
)


@pytest.mark.parametrize("pin", ["000000", "777777", "999999", "11111111"])
def test_rechaza_todos_los_digitos_iguales(pin: str) -> None:
    with pytest.raises(PinAutorizacionInvalidoError):
        validar_formato_pin_autorizacion(pin)


@pytest.mark.parametrize("pin", ["123456", "012345", "456789", "1234567", "01234567"])
def test_rechaza_las_escaleras_ascendentes_de_paso_uno(pin: str) -> None:
    with pytest.raises(PinAutorizacionInvalidoError):
        validar_formato_pin_autorizacion(pin)


@pytest.mark.parametrize("pin", ["987654", "654321", "543210", "9876543", "76543210"])
def test_rechaza_las_escaleras_descendentes_de_paso_uno(pin: str) -> None:
    with pytest.raises(PinAutorizacionInvalidoError):
        validar_formato_pin_autorizacion(pin)


@pytest.mark.parametrize("pin", ["000000", "123456", "987654", "7777777"])
def test_el_mensaje_del_rechazo_no_contiene_el_valor(pin: str) -> None:
    with pytest.raises(PinAutorizacionInvalidoError) as error:
        validar_formato_pin_autorizacion(pin)

    assert pin not in str(error.value)
    assert error.value.codigo == "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"


@pytest.mark.parametrize(
    "pin",
    [
        "482913",  # sin patrón
        "135792",  # paso 2: no es escalera de paso 1
        "901234",  # la escalera se corta en 9 -> 0 (sin vuelta)
        "123450",  # sube y baja de golpe
        "121212",  # alternado: no es todo igual ni escalera
        "1234568",  # una escalera con un salto al final
    ],
)
def test_acepta_los_pin_que_no_son_triviales(pin: str) -> None:
    assert validar_formato_pin_autorizacion(pin) == pin


@pytest.mark.parametrize("pin", ["12345", "12a456", "", "98765"])
def test_el_formato_basico_sigue_rechazando_lo_corto_y_lo_no_numerico(pin: str) -> None:
    with pytest.raises(PinAutorizacionInvalidoError):
        validar_formato_pin_autorizacion(pin)
