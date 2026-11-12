"""Reglas de margen: validación y resolución por precedencia (PRC-12, PRC-13, `design.md`
D8; spec `precios/reglas-de-margen`).

Funciones puras sobre datos: sin acceso a la base, sin reloj. La unicidad de una regla
activa por lista y alcance (D8) la garantiza la base con sus índices y el handler con el
candado de la lista; acá solo se valida el contenido de una regla y se elige la que le
corresponde a un producto.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from uuid import UUID

from app.core.money import redondear_costo
from app.modules.precios.domain.decimales import rechazar_punto_flotante
from app.modules.precios.domain.errores import AlcanceInvalidoError, MargenInvalidoError

MARKUP = "MARKUP"
MARGEN_BRUTO = "MARGEN_BRUTO"
TIPOS_DE_MARGEN = (MARKUP, MARGEN_BRUTO)

ALCANCE_LISTA = "LISTA"
ALCANCES_CON_ENTIDAD = ("PRODUCTO", "MARCA", "CATEGORIA", "PROVEEDOR")
ALCANCES = (*ALCANCES_CON_ENTIDAD, ALCANCE_LISTA)
"""De la más específica a la más general (PRC-13)."""

_SEIS_DECIMALES = Decimal("0.000001")
_VALOR_MAXIMO = Decimal("999.999999")  # `numeric(9,6)`


@dataclass(frozen=True)
class Regla:
    """Una regla de margen de una lista, tal como la resolución la necesita."""

    id: UUID
    alcance_tipo: str
    alcance_id: UUID | None
    tipo: str
    valor: Decimal
    activo: bool


@dataclass(frozen=True)
class ProductoDeRegla:
    """Lo que el catálogo aporta de un producto para elegir su regla (PRC-13)."""

    producto_id: UUID
    marca_id: UUID | None
    categoria_id: UUID
    proveedor_id: UUID


@dataclass(frozen=True)
class ReglaValidada:
    """Contenido de una regla ya validado y normalizado (valor a seis decimales)."""

    tipo: str
    valor: Decimal
    alcance_tipo: str
    alcance_id: UUID | None


def _valor_exacto(valor: Decimal | str) -> Decimal:
    rechazar_punto_flotante(valor, "El valor del margen")
    try:
        exacto = valor if isinstance(valor, Decimal) else Decimal(valor.strip())
    except (InvalidOperation, AttributeError) as error:
        raise MargenInvalidoError(
            f"El valor del margen {valor!r} no es un decimal exacto (por ejemplo, 0.300000)."
        ) from error
    if not exacto.is_finite():
        raise MargenInvalidoError(f"El valor del margen {valor!r} no es un número finito.")
    return exacto


def validar_regla(
    tipo: str, valor: Decimal | str, alcance_tipo: str, alcance_id: UUID | None
) -> ReglaValidada:
    """Valida el contenido de una regla de margen (PRC-12, PRC-13).

    - `tipo` es `MARKUP` o `MARGEN_BRUTO`.
    - `valor` es una fracción con a lo sumo seis decimales (TR-02, 30% = `0.300000`),
      `>= 0` y, para `MARGEN_BRUTO`, `< 1`; un markup puede superar el 100% (`MARGEN_INVALIDO`
      en cualquier otro caso). Un punto flotante se rechaza (INV-03).
    - `alcance_tipo` es `PRODUCTO`, `MARCA`, `CATEGORIA`, `PROVEEDOR` (con entidad) o
      `LISTA` (sin entidad); lo demás es `ALCANCE_INVALIDO`.
    """
    if tipo not in TIPOS_DE_MARGEN:
        raise MargenInvalidoError(
            f"El tipo de margen {tipo!r} no existe: debe ser {' o '.join(TIPOS_DE_MARGEN)}."
        )
    exacto = _valor_exacto(valor)
    if exacto < 0:
        raise MargenInvalidoError(f"El valor del margen no puede ser negativo (recibido {valor}).")
    if exacto.quantize(_SEIS_DECIMALES, rounding=ROUND_DOWN) != exacto:
        raise MargenInvalidoError(
            f"El valor del margen admite hasta seis decimales (recibido {valor})."
        )
    if exacto > _VALOR_MAXIMO:
        raise MargenInvalidoError(f"El valor del margen no puede superar {_VALOR_MAXIMO}.")
    if tipo == MARGEN_BRUTO and exacto >= 1:
        raise MargenInvalidoError(
            f"Un margen bruto debe ser menor que 1, o sea menor que el 100% (recibido {valor})."
        )

    if alcance_tipo not in ALCANCES:
        raise AlcanceInvalidoError(
            f"El alcance {alcance_tipo!r} no existe: debe ser uno de {', '.join(ALCANCES)}."
        )
    if alcance_tipo == ALCANCE_LISTA and alcance_id is not None:
        raise AlcanceInvalidoError("Una regla de alcance LISTA no lleva entidad.")
    if alcance_tipo != ALCANCE_LISTA and alcance_id is None:
        raise AlcanceInvalidoError(f"Una regla de alcance {alcance_tipo} necesita su entidad.")

    return ReglaValidada(
        tipo=tipo,
        valor=redondear_costo(exacto),
        alcance_tipo=alcance_tipo,
        alcance_id=alcance_id,
    )


def resolver_regla(reglas: Iterable[Regla], producto: ProductoDeRegla) -> Regla | None:
    """La regla activa de alcance más específico que alcanza al producto, en este orden:
    producto, marca, categoría, proveedor, lista (PRC-13). Un producto sin marca no tiene
    regla de marca. `None` si ninguna regla activa lo alcanza.

    Una lista tiene como máximo una regla activa por alcance y entidad (D8), así que cada
    paso de la cadena tiene a lo sumo una candidata."""
    por_alcance: dict[tuple[str, UUID | None], Regla] = {
        (regla.alcance_tipo, regla.alcance_id): regla for regla in reglas if regla.activo
    }
    candidatas = (
        ("PRODUCTO", producto.producto_id),
        ("MARCA", producto.marca_id),
        ("CATEGORIA", producto.categoria_id),
        ("PROVEEDOR", producto.proveedor_id),
        (ALCANCE_LISTA, None),
    )
    for alcance_tipo, entidad_id in candidatas:
        if alcance_tipo != ALCANCE_LISTA and entidad_id is None:
            continue  # un producto sin marca no tiene regla de marca
        regla = por_alcance.get((alcance_tipo, entidad_id))
        if regla is not None:
            return regla
    return None
