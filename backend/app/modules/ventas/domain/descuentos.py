"""Comparación de los descuentos esperados con los calculados (DSC-09, DSC-07; change 18b,
`design.md` D11). Función pura: sin infraestructura.

Con conexión el servidor recalcula los descuentos de cada línea y rechaza con `DESCUENTO_DIFIERE`
si alguno difiere del que vio el usuario en origen, regla, porcentaje o importe, devolviendo los
suyos. Los decimales se comparan por valor (`0.05` es `0.050000`); el orden de los descuentos de
una línea no cuenta."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.ventas.domain.errores import DescuentoDifiereError


@dataclass(frozen=True)
class DescuentoDeLinea:
    """Un descuento de una línea (DSC-08): `regla_id` nulo en el manual, `porcentaje` nulo en
    una regla de importe fijo."""

    origen: str
    regla_id: UUID | None
    porcentaje: Decimal | None
    importe: Decimal


def _clave(descuento: DescuentoDeLinea) -> tuple[str, str, Decimal, Decimal]:
    # Orden total y estable para comparar sin importar cómo se enumeraron; un porcentaje nulo
    # (importe fijo) se distingue de cualquier porcentaje real con -1.
    return (
        descuento.origen,
        "" if descuento.regla_id is None else str(descuento.regla_id),
        Decimal(-1) if descuento.porcentaje is None else descuento.porcentaje,
        descuento.importe,
    )


def _a_detalle(descuento: DescuentoDeLinea) -> dict[str, object]:
    return {
        "origen": descuento.origen,
        "regla_id": None if descuento.regla_id is None else str(descuento.regla_id),
        "porcentaje": None if descuento.porcentaje is None else str(descuento.porcentaje),
        "importe": str(descuento.importe),
    }


def comparar_descuentos(
    esperados: Mapping[UUID, Sequence[DescuentoDeLinea]],
    calculados: Mapping[UUID, Sequence[DescuentoDeLinea]],
) -> None:
    """D11: las líneas se comparan por identificador; una línea sin descuentos esperados cuenta
    como lista vacía. Cualquier diferencia rechaza con `DESCUENTO_DIFIERE` y los descuentos de
    todas las líneas del servidor en el detalle."""
    iguales = set(esperados) <= set(calculados) and all(
        sorted(map(_clave, esperados.get(linea_id, ()))) == sorted(map(_clave, descuentos))
        for linea_id, descuentos in calculados.items()
    )
    if iguales:
        return
    raise DescuentoDifiereError(
        "Los descuentos difieren de los que vio el usuario: se confirma con los del servidor.",
        extension={
            "lineas": [
                {"linea_id": str(linea_id), "descuentos": [_a_detalle(d) for d in descuentos]}
                for linea_id, descuentos in calculados.items()
            ]
        },
    )
