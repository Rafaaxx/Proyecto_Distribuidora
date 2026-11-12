"""Redondeo del precio final al múltiplo de la lista o de la categoría (PRC-14,
`design.md` D9; spec `precios/calculo-de-precios`).

Funciones puras sobre `Decimal`. El redondeo se aplica al precio calculado SIN redondear
(TR-03) y es el único redondeo del precio final: `ARRIBA` lleva al múltiplo siguiente,
`ABAJO` al anterior y `CERCANO` al más próximo, con el punto medio hacia arriba. El
múltiplo tiene hasta dos decimales (`numeric(14,2)`), así que el resultado es exacto con
dos decimales sin cuantizar de más.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)

from app.core.money import redondear_importe
from app.modules.precios.domain.decimales import rechazar_punto_flotante
from app.modules.precios.domain.errores import PrecioNoPositivoError, RedondeoInvalidoError

ARRIBA = "ARRIBA"
CERCANO = "CERCANO"
ABAJO = "ABAJO"
DIRECCIONES = (ARRIBA, CERCANO, ABAJO)

_PRECISION_INTERMEDIA = 60
_DOS_DECIMALES = Decimal("0.01")
_MULTIPLO_MAXIMO = Decimal("999999999999.99")  # `numeric(14,2)`
_MODO_POR_DIRECCION = {ARRIBA: ROUND_CEILING, ABAJO: ROUND_FLOOR, CERCANO: ROUND_HALF_UP}


@dataclass(frozen=True)
class Redondeo:
    """Un múltiplo (`> 0`, dos decimales) y una dirección: el de una lista o el de la
    sobrescritura de una categoría."""

    multiplo: Decimal
    direccion: str


def validar_redondeo(multiplo: Decimal | str, direccion: str) -> Redondeo:
    """Valida un redondeo (PRC-14, D9) y normaliza el múltiplo a dos decimales.

    El múltiplo es mayor que cero, con a lo sumo dos decimales y dentro de `numeric(14,2)`;
    la dirección es `ARRIBA`, `CERCANO` o `ABAJO` (`REDONDEO_INVALIDO` en otro caso). Un
    múltiplo de punto flotante se rechaza (INV-03)."""
    rechazar_punto_flotante(multiplo, "El múltiplo de redondeo")
    if direccion not in DIRECCIONES:
        raise RedondeoInvalidoError(
            f"La dirección {direccion!r} no existe: debe ser {', '.join(DIRECCIONES)}."
        )
    try:
        exacto = multiplo if isinstance(multiplo, Decimal) else Decimal(multiplo.strip())
    except (InvalidOperation, AttributeError) as error:
        raise RedondeoInvalidoError(
            f"El múltiplo {multiplo!r} no es un decimal exacto (por ejemplo, 100.00)."
        ) from error
    if not exacto.is_finite() or exacto <= 0:
        raise RedondeoInvalidoError(f"El múltiplo debe ser mayor que cero (recibido {multiplo}).")
    if exacto.quantize(_DOS_DECIMALES, rounding=ROUND_DOWN) != exacto:
        raise RedondeoInvalidoError(
            f"El múltiplo admite hasta dos decimales (recibido {multiplo})."
        )
    if exacto > _MULTIPLO_MAXIMO:
        raise RedondeoInvalidoError(f"El múltiplo no puede superar {_MULTIPLO_MAXIMO}.")
    return Redondeo(multiplo=redondear_importe(exacto), direccion=direccion)


def redondeo_aplicable(de_la_lista: Redondeo, sobrescritura_activa: Redondeo | None) -> Redondeo:
    """La sobrescritura activa de la categoría del producto y, si no hay, el de la lista
    (`design.md` D9 punto 2)."""
    return sobrescritura_activa if sobrescritura_activa is not None else de_la_lista


def redondear_al_multiplo(precio_calculado: Decimal, multiplo: Decimal, direccion: str) -> Decimal:
    """El precio llevado al múltiplo en la dirección indicada, con dos decimales; puede dar
    cero (el llamador decide si eso es "sin precio", ver `aplicar_redondeo`)."""
    rechazar_punto_flotante(precio_calculado, "El precio calculado")
    rechazar_punto_flotante(multiplo, "El múltiplo de redondeo")
    modo = _MODO_POR_DIRECCION.get(direccion)
    if modo is None:
        raise RedondeoInvalidoError(
            f"La dirección {direccion!r} no existe: debe ser {', '.join(DIRECCIONES)}."
        )
    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        veces = (precio_calculado / multiplo).to_integral_value(rounding=modo)
        return redondear_importe(veces * multiplo)


def aplicar_redondeo(precio_calculado: Decimal, multiplo: Decimal, direccion: str) -> Decimal:
    """El precio final de `precio_calculado` (PRC-14): redondeado al múltiplo y mayor que
    cero. Si el redondeo da cero (por ejemplo, `ABAJO` con un precio menor que el múltiplo),
    el producto no tiene precio: `PRECIO_NO_POSITIVO` (D9 punto 4)."""
    final = redondear_al_multiplo(precio_calculado, multiplo, direccion)
    if final <= 0:
        raise PrecioNoPositivoError(
            f"El precio {precio_calculado} redondeado a múltiplos de {multiplo} ({direccion}) "
            "da cero: el producto no tiene precio."
        )
    return final
