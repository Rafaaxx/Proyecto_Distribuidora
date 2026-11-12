"""Número de la venta: prefijo del dispositivo y correlativo (VTA-06, ADR-008; `design.md` D4).

Formato `PPP-NNNNNN`: el prefijo del dispositivo de la sesión, un guion y el correlativo con
seis dígitos como mínimo (el formato admite más sin cambiar la regla)."""

from __future__ import annotations

import re

from app.modules.ventas.domain.errores import NumeroInvalidoError

_DIGITOS = re.compile(r"[0-9]{6,}")


def correlativo_de(numero: str, prefijo: str) -> int:
    """El correlativo del `numero`, que debe empezar con `prefijo` y un guion (`NUMERO_INVALIDO`
    si el formato o el prefijo no coinciden, o el correlativo es cero)."""
    inicio = f"{prefijo}-"
    if not numero.startswith(inicio):
        raise NumeroInvalidoError(
            f"El número {numero!r} tiene que empezar con el prefijo {prefijo!r} del dispositivo."
        )
    digitos = numero[len(inicio) :]
    if _DIGITOS.fullmatch(digitos) is None or int(digitos) < 1:
        raise NumeroInvalidoError(
            f"El número {numero!r} no tiene el formato {prefijo}-NNNNNN (correlativo desde 1)."
        )
    return int(digitos)


def armar_numero(prefijo: str, correlativo: int) -> str:
    """`PPP-NNNNNN` con seis dígitos como mínimo."""
    return f"{prefijo}-{correlativo:06d}"


def nuevo_ultimo_correlativo(actual: int, propuesto: int) -> int:
    """`max(actual, propuesto)`: el último correlativo del dispositivo nunca retrocede; no se
    exige que el propuesto lo supere (una venta sin conexión más vieja no se rechaza)."""
    return max(actual, propuesto)
