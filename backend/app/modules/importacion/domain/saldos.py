"""Importación de saldos iniciales: de la fila de planilla a los argumentos del servicio
(`specs/importacion/puesta-en-marcha`, `design.md` D4, D12).

Puro. El importe se lee con coma decimal, sin punto flotante (INV-03), y viaja como
`Decimal` sin redondear: los dos decimales y "mayor que cero" los exige el servicio
(`IMPORTE_INVALIDO`). El sentido acepta los rótulos de ADR-034 punto 8, según el tipo de
cuenta, además de `AUMENTA`/`REDUCE`; cualquier otro texto pasa en mayúsculas para que el
servicio lo rechace con `SENTIDO_INVALIDO` (la misma regla que la pantalla).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.modules.importacion.domain.errores import CuentaTipoInvalidoError
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import obligatorio
from app.modules.importacion.domain.valores import a_decimal

CLIENTE = "CLIENTE"
PROVEEDOR = "PROVEEDOR"

_AUMENTA = "AUMENTA"
_REDUCE = "REDUCE"

# ADR-034 punto 8: rótulos de negocio del sentido, por tipo de cuenta.
_ROTULOS: dict[str, dict[str, str]] = {
    CLIENTE: {"nos debe": _AUMENTA, "saldo a favor": _REDUCE},
    PROVEEDOR: {"le debemos": _AUMENTA, "saldo a nuestro favor": _REDUCE},
}

_DOCUMENTO = re.compile(r"[0-9][0-9 .\-]*")


@dataclass(frozen=True)
class DatosDeSaldo:
    """Una fila de saldos ya leída. `entidad` sigue siendo texto: el importador la
    resuelve contra los datos de la organización (D4)."""

    cuenta_tipo: str
    entidad: str
    importe: Decimal
    sentido: str


def _sentido(cuenta_tipo: str, texto: str) -> str:
    normalizado = " ".join(texto.split()).casefold()
    return _ROTULOS[cuenta_tipo].get(normalizado, normalizado.upper())


def datos_de_saldo(fila: FilaPlanilla) -> DatosDeSaldo:
    """Lee la fila o lanza el `ErrorDeValor` de la primera celda ilegible (con su
    columna)."""
    valores = fila.valores
    cuenta_tipo = valores["cuenta_tipo"].strip().upper()
    if cuenta_tipo not in _ROTULOS:
        raise CuentaTipoInvalidoError(
            f"El tipo de cuenta {valores['cuenta_tipo'].strip()!r} no existe: use CLIENTE "
            "o PROVEEDOR.",
            columna="cuenta_tipo",
        )
    return DatosDeSaldo(
        cuenta_tipo=cuenta_tipo,
        entidad=obligatorio(valores["entidad"], columna="entidad"),
        importe=a_decimal(valores["importe"], columna="importe"),
        sentido=_sentido(cuenta_tipo, valores["sentido"]),
    )


def documento_de_entidad(texto: str) -> str | None:
    """Los dígitos de `texto` si es un documento escrito con o sin separadores (`20-
    12345678-9`, `12.345.678`); `None` si tiene letras u otros caracteres (un código como
    `C001` no se busca como documento, D4)."""
    recortado = texto.strip()
    if _DOCUMENTO.fullmatch(recortado) is None:
        return None
    return "".join(c for c in recortado if c.isdigit())
