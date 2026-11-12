"""Precio de referencia de un producto en una lista: costo, margen y redondeo juntos
(PRC-11 a PRC-16; spec `precios/calculo-de-precios`; `design.md` D2, D3, D9).

`calcular_precio` es pura: recibe el costo base del costo informado vigente (CST-03), las
unidades de la presentación de referencia, la regla aplicable (PRC-13), el redondeo
aplicable (D9) y el modo impositivo de la organización, y devuelve todo lo que PRC-16 pide
guardar en el precio, o la causa de no tener precio. El costo informado vigente y la
regla los eligen el servicio y `resolver_regla`; la señal de otra regla de IVA (D3) y la
de costos distintos por presentación (D2) las arma el servicio con lo que sabe de los
costos y no cambian este cálculo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.money import redondear_costo
from app.modules.precios.domain.calculo import aplicar_margen, calcular_costo_de_referencia
from app.modules.precios.domain.errores import (
    ModoImpositivoNoSoportadoError,
    PrecioNoPositivoError,
)
from app.modules.precios.domain.redondeo import Redondeo, aplicar_redondeo
from app.modules.precios.domain.reglas import Regla

SIN_PRESENTACION_DE_REFERENCIA = "SIN_PRESENTACION_DE_REFERENCIA"
SIN_COSTO = "SIN_COSTO"
SIN_REGLA = "SIN_REGLA"
PRECIO_NO_POSITIVO = "PRECIO_NO_POSITIVO"

MODOS_IMPOSITIVOS_SOPORTADOS = ("A", "B")
"""En los modos A y B el redondeo se aplica al precio neto (PRC-15); el modo C es de la
etapa 4."""


@dataclass(frozen=True)
class PrecioCalculado:
    """Todo lo que PRC-16 pide guardar de un precio calculado, más las unidades de la
    referencia vigentes al calcularlo (D1)."""

    costo_referencia: Decimal
    regla_id: UUID
    tipo_margen: str
    valor_margen: Decimal
    precio_calculado: Decimal
    precio_final: Decimal
    unidades_referencia: int


@dataclass(frozen=True)
class SinPrecio:
    """El producto no recibe precio en la lista; `causa` es `SIN_PRESENTACION_DE_REFERENCIA`,
    `SIN_COSTO`, `SIN_REGLA` o `PRECIO_NO_POSITIVO` (D4)."""

    causa: str


def exigir_modo_impositivo_soportado(modo_impositivo: str) -> None:
    """Rechaza con `MODO_IMPOSITIVO_NO_SOPORTADO` un modo que no es `A` ni `B` (PRC-15). Se
    llama antes de calcular el primer precio, así un borrador de una organización en modo `C`
    se rechaza entero aunque ningún producto llegue a calcularse."""
    if modo_impositivo not in MODOS_IMPOSITIVOS_SOPORTADOS:
        raise ModoImpositivoNoSoportadoError(
            f"No se generan precios con modo impositivo {modo_impositivo!r}: el redondeo "
            "sobre el precio con IVA incluido (modo C) llega en la etapa 4 (PRC-15)."
        )


def calcular_precio(
    *,
    costo_base: Decimal | None,
    unidades_referencia: int | None,
    regla: Regla | None,
    redondeo: Redondeo,
    modo_impositivo: str,
) -> PrecioCalculado | SinPrecio:
    """El precio de un producto en una lista, o la causa de no tenerlo.

    - Modo impositivo `C` (o cualquiera que no sea `A` o `B`): se rechaza con
      `MODO_IMPOSITIVO_NO_SOPORTADO` antes de calcular nada (PRC-15).
    - Sin presentación de referencia (`unidades_referencia` nulo): `SIN_PRESENTACION_DE_REFERENCIA`
      (decisión del 2026-10-06): sin ella no hay costo de referencia (PRC-10, PRC-11).
    - Sin costo informado vigente (`costo_base` nulo): `SIN_COSTO`; sin regla aplicable:
      `SIN_REGLA` (la falta de costo se informa primero).
    - Costo de referencia = costo base x unidades (PRC-11); precio calculado = margen
      aplicado con decimales exactos (PRC-12); precio final = el calculado exacto llevado
      al múltiplo (PRC-14, TR-03: no se redondea nada antes). El calculado se registra a
      seis decimales (PRC-16). Si el redondeo da cero, `PRECIO_NO_POSITIVO`.
    """
    exigir_modo_impositivo_soportado(modo_impositivo)
    if unidades_referencia is None:
        return SinPrecio(causa=SIN_PRESENTACION_DE_REFERENCIA)
    if costo_base is None:
        return SinPrecio(causa=SIN_COSTO)
    if regla is None:
        return SinPrecio(causa=SIN_REGLA)

    costo_referencia = calcular_costo_de_referencia(costo_base, unidades_referencia)
    calculado_exacto = aplicar_margen(costo_referencia, regla.tipo, regla.valor)
    try:
        precio_final = aplicar_redondeo(calculado_exacto, redondeo.multiplo, redondeo.direccion)
    except PrecioNoPositivoError:
        return SinPrecio(causa=PRECIO_NO_POSITIVO)

    return PrecioCalculado(
        costo_referencia=costo_referencia,
        regla_id=regla.id,
        tipo_margen=regla.tipo,
        valor_margen=regla.valor,
        precio_calculado=redondear_costo(calculado_exacto),
        precio_final=precio_final,
        unidades_referencia=unidades_referencia,
    )
