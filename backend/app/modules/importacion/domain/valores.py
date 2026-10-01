"""Conversión exacta de texto de planilla a decimal, entero, booleano y fecha
(`design.md` D3, D12; INV-03, INV-04, TR-01, TR-02).

Puro: sin acceso a datos ni a infraestructura. NINGÚN valor pasa por punto
flotante: el texto se valida con una expresión regular y se entrega a `Decimal`
como cadena, así que `1239,669421` es exactamente `Decimal("1239.669421")`.

Formato de números escritos como texto (D12): coma decimal, sin separador de
miles. Un punto se rechaza (`1.500` sería 1,5 o 1500 según quien lo lea). Las
celdas numéricas de Excel las normaliza el lector (`lectores/xlsx_lector.py`) a
este mismo formato antes de llegar acá.

La cantidad de decimales admitida la decide la regla de destino (2 en importes,
6 en costos): acá no se redondea nunca.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.modules.importacion.domain.errores import (
    CantidadInvalidaError,
    FechaInvalidaError,
    NumeroInvalidoError,
    ValorInvalidoError,
)

_DECIMAL = re.compile(r"-?\d+(,\d+)?")
_FECHA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_FECHA_LOCAL = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# Un texto más largo no es un importe ni un costo: se rechaza antes de leerlo
# para que no desborde la columna `NUMERIC` de la base.
LARGO_MAXIMO_DE_NUMERO = 40

_ENTERO_MINIMO = -(2**31)
_ENTERO_MAXIMO = 2**31 - 1

_VERDADEROS = frozenset({"S", "SI", "SÍ"})
_FALSOS = frozenset({"N", "NO"})


def a_decimal(texto: str, *, columna: str) -> Decimal:
    """Texto con coma decimal a `Decimal`, conservando la escala escrita
    (`18000,00` es `Decimal("18000.00")`). `NUMERO_INVALIDO` si el texto está
    vacío, tiene punto, más de un separador, letras o es demasiado largo."""
    recortado = texto.strip()
    if len(recortado) > LARGO_MAXIMO_DE_NUMERO or _DECIMAL.fullmatch(recortado) is None:
        raise NumeroInvalidoError(
            f"El valor {recortado!r} no es un número válido: use coma decimal, "
            "sin separador de miles (por ejemplo 18000,50).",
            columna=columna,
        )
    return Decimal(recortado.replace(",", "."))


def a_entero(texto: str, *, columna: str) -> int:
    """Texto a entero (INV-04). Admite decimales en cero (`10,0`); `10,5`, un
    texto no numérico o un valor fuera del rango de `integer` es
    `CANTIDAD_INVALIDA`."""
    recortado = texto.strip()
    if len(recortado) > LARGO_MAXIMO_DE_NUMERO or _DECIMAL.fullmatch(recortado) is None:
        raise CantidadInvalidaError(
            f"La cantidad {recortado!r} no es un entero válido.", columna=columna
        )
    valor = Decimal(recortado.replace(",", "."))
    if valor != valor.to_integral_value():
        raise CantidadInvalidaError(
            f"La cantidad {recortado!r} debe ser un número entero, sin decimales.",
            columna=columna,
        )
    entero = int(valor)
    if not _ENTERO_MINIMO <= entero <= _ENTERO_MAXIMO:
        raise CantidadInvalidaError(
            f"La cantidad {recortado!r} está fuera del rango admitido.", columna=columna
        )
    return entero


def a_booleano(texto: str, *, columna: str) -> bool:
    """`S`, `SI`, `SÍ` / `N`, `NO`, sin distinguir mayúsculas. Otro valor es
    `VALOR_INVALIDO`."""
    normalizado = texto.strip().upper()
    if normalizado in _VERDADEROS:
        return True
    if normalizado in _FALSOS:
        return False
    raise ValorInvalidoError(
        f"El valor {texto.strip()!r} no es válido: use S o N.", columna=columna
    )


def a_fecha(texto: str, *, columna: str) -> date:
    """`AAAA-MM-DD` o `DD/MM/AAAA`. Otra forma, o una fecha que no existe, es
    `FECHA_INVALIDA`."""
    recortado = texto.strip()
    try:
        iso = _FECHA_ISO.fullmatch(recortado)
        if iso is not None:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        local = _FECHA_LOCAL.fullmatch(recortado)
        if local is not None:
            return date(int(local[3]), int(local[2]), int(local[1]))
    except ValueError:
        pass  # La forma es válida pero el día o el mes no existen.
    raise FechaInvalidaError(
        f"La fecha {recortado!r} no es válida: use AAAA-MM-DD o DD/MM/AAAA.", columna=columna
    )
