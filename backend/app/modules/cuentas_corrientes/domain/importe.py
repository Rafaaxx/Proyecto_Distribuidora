"""Validación del importe de un movimiento (CC-01, INV-03).

Un importe es un valor decimal exacto, mayor que cero, con a lo sumo dos
decimales y dentro de `numeric(14,2)`. No se redondea: más decimales se
rechazan (`design.md` D5). Un `float`, un `int` o un `bool` no es dinero exacto
y se rechaza aunque el valor sea entero, porque un número JSON es justamente lo
que INV-03 no admite.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.core.money import redondear_importe
from app.modules.cuentas_corrientes.domain.errores import ImporteInvalidoError

IMPORTE_MAXIMO = Decimal("999999999999.99")
"""Mayor valor de `numeric(14,2)`: 12 dígitos enteros y 2 decimales."""

_FORMATO = re.compile(r"[0-9]+(\.[0-9]{1,2})?")


def validar_importe(valor: object) -> Decimal:
    """Devuelve el importe con exactamente dos decimales o levanta
    `IMPORTE_INVALIDO`.

    Solo acepta `str` (`"150000.00"`, `"20000"`, `"100.5"`) y `Decimal`. El
    redondeo a dos decimales que se aplica al final no cambia el valor: antes
    se comprobó que no había dígitos de más (lo único que hace es fijar el
    exponente, y lo hace `core/money.py`, el único lugar que cuantiza dinero).
    """
    if isinstance(valor, str):
        if _FORMATO.fullmatch(valor) is None:
            raise ImporteInvalidoError(
                f"El importe {valor!r} no es un decimal positivo con hasta dos decimales."
            )
        decimal = Decimal(valor)
    elif isinstance(valor, Decimal):
        decimal = valor
    else:
        raise ImporteInvalidoError(
            f"El importe debe ser un string decimal exacto, no {type(valor).__name__}."
        )

    if not decimal.is_finite():
        raise ImporteInvalidoError(f"El importe {valor!r} no es un número finito.")
    exponente = decimal.as_tuple().exponent
    assert isinstance(exponente, int)
    if exponente < -2:
        raise ImporteInvalidoError(f"El importe {valor!r} tiene más de dos decimales.")
    if decimal <= 0:
        raise ImporteInvalidoError(f"El importe {valor!r} tiene que ser mayor que cero.")
    if decimal > IMPORTE_MAXIMO:
        raise ImporteInvalidoError(f"El importe {valor!r} supera el máximo de {IMPORTE_MAXIMO}.")
    return redondear_importe(decimal)
