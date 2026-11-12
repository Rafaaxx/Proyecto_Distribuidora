"""Resolución de referencias por clave natural (`specs/importacion/importacion-de-maestros`,
`design.md` D4).

Puro. Quien llama (el importador) busca los candidatos por el `service.py` del módulo
dueño, ya filtrados por la organización del token (INV-21); acá se decide qué pasa con
lo que volvió: ninguno es `REFERENCIA_NO_ENCONTRADA`, más de uno `REFERENCIA_AMBIGUA`.
El mensaje de "no encontrada" no distingue "no existe" de "existe en otra
organización".

También convierte los porcentajes de la planilla (`21`, `10,5`) a la fracción que usa el
sistema (`0.21`, `0.105`, TR-02) sin pasar por punto flotante.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.modules.importacion.domain.errores import (
    ReferenciaAmbiguaError,
    ReferenciaNoEncontradaError,
    ValorObligatorioError,
)
from app.modules.importacion.domain.valores import a_decimal


def clave_de_texto(texto: str) -> str:
    """Forma comparable de una clave natural: sin espacios al borde y sin distinguir
    mayúsculas (`design.md` D4)."""
    return texto.strip().casefold()


def resolver_unica[T](candidatos: Sequence[T], *, columna: str, valor: str, que: str) -> T:
    """El único candidato que coincide con `valor`. `que` nombra lo buscado en el
    mensaje (por ejemplo `"categoría"`)."""
    recortado = valor.strip()
    if not recortado or not candidatos:
        raise ReferenciaNoEncontradaError(
            f"No existe {que} {recortado!r} en esta organización.", columna=columna
        )
    if len(candidatos) > 1:
        raise ReferenciaAmbiguaError(
            f"Hay más de una {que} que coincide con {recortado!r}: no se puede elegir una.",
            columna=columna,
        )
    return candidatos[0]


def obligatorio(texto: str, *, columna: str) -> str:
    """El texto recortado, o `VALOR_OBLIGATORIO` si la celda está vacía."""
    recortado = texto.strip()
    if not recortado:
        raise ValorObligatorioError(f"La columna {columna} es obligatoria.", columna=columna)
    return recortado


def porcentaje_a_fraccion(texto: str, *, columna: str) -> Decimal:
    """`21` es `0.21`, `10,5` es `0.105`: el corrimiento de la coma es exacto (se baja
    el exponente en dos), nunca una división en punto flotante. `NUMERO_INVALIDO` si el
    texto no es un decimal con coma."""
    signo, digitos, exponente = a_decimal(texto, columna=columna).as_tuple()
    assert isinstance(exponente, int)  # `a_decimal` nunca devuelve NaN ni infinito.
    return Decimal((signo, digitos, exponente - 2))
