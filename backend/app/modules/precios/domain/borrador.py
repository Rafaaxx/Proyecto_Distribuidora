"""Reglas puras del borrador de una lista: el precio manual, la relación de un precio con el de
la versión base y las señales que lo acompañan (PRC-16, PRC-17; spec
`precios/borrador-de-lista`; `design.md` D2, D3, D4, D7).

Funciones sobre datos: sin acceso a la base ni reloj. El servicio decide qué productos entran,
con qué costo y con qué regla; acá se valida un importe manual, se arma lo que se guarda con
él y se decide qué señales lleva un precio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.money import redondear_importe
from app.modules.precios.domain.calculo import (
    calcular_costo_de_referencia,
    calcular_precio_sin_redondear,
)
from app.modules.precios.domain.decimales import rechazar_punto_flotante
from app.modules.precios.domain.errores import ImporteInvalidoError
from app.modules.precios.domain.reglas import Regla

NUEVO = "NUEVO"
CAMBIA = "CAMBIA"
IGUAL = "IGUAL"
"""Relación de un precio del borrador con el del mismo producto en la versión base (PRC-17)."""

_IMPORTE_MAXIMO = Decimal("999999999999.99")  # `numeric(14,2)`
_FORMATO = re.compile(r"[0-9]+(\.[0-9]{1,2})?")


def validar_precio_manual(valor: str | Decimal) -> Decimal:
    """El precio final fijado a mano (D7): un decimal exacto mayor que cero, con a lo sumo dos
    decimales y dentro de `numeric(14,2)`, devuelto con dos decimales. Más decimales NO se
    redondean: se rechazan (`IMPORTE_INVALIDO`, TR-01). Un `float` o un `bool` no es dinero
    exacto (INV-03); un entero tampoco entra: el importe viaja como string."""
    rechazar_punto_flotante(valor, "El precio manual")
    if isinstance(valor, str):
        if _FORMATO.fullmatch(valor) is None:
            raise ImporteInvalidoError(
                f"El precio {valor!r} no es un decimal positivo con hasta dos decimales."
            )
        exacto = Decimal(valor)
    elif isinstance(valor, Decimal):
        exacto = valor
    else:
        raise ImporteInvalidoError(
            f"El precio debe enviarse como string o Decimal, no como {type(valor).__name__}."
        )
    if not exacto.is_finite() or exacto <= 0:
        raise ImporteInvalidoError(f"El precio debe ser mayor que cero (recibido {valor}).")
    if exacto > _IMPORTE_MAXIMO:
        raise ImporteInvalidoError(f"El precio no puede superar {_IMPORTE_MAXIMO}.")
    if exacto != exacto.quantize(Decimal("0.01")):
        raise ImporteInvalidoError(f"El precio admite hasta dos decimales (recibido {valor}).")
    return redondear_importe(exacto)


@dataclass(frozen=True)
class ReferenciaDeCalculo:
    """Lo que se guarda junto a un precio manual (PRC-16): el costo de referencia, la regla
    aplicable y el precio calculado sin redondear de ese momento; nulos lo que no existe."""

    costo_referencia: Decimal | None
    regla_id: UUID | None
    tipo_margen: str | None
    valor_margen: Decimal | None
    precio_calculado: Decimal | None


def referencia_de_precio_manual(
    costo_base: Decimal | None, unidades_referencia: int, regla: Regla | None
) -> ReferenciaDeCalculo:
    """El cálculo que acompaña a un precio manual (D7): sin costo informado vigente no hay
    nada; con costo y sin regla solo el costo de referencia; con ambos, el costo de
    referencia, la regla y el precio calculado a seis decimales. El precio manual no se
    redondea, así que el precio final es el que el usuario fijó (PRC-16)."""
    if costo_base is None:
        return ReferenciaDeCalculo(None, None, None, None, None)
    costo_referencia = calcular_costo_de_referencia(costo_base, unidades_referencia)
    if regla is None:
        return ReferenciaDeCalculo(costo_referencia, None, None, None, None)
    return ReferenciaDeCalculo(
        costo_referencia=costo_referencia,
        regla_id=regla.id,
        tipo_margen=regla.tipo,
        valor_margen=regla.valor,
        precio_calculado=calcular_precio_sin_redondear(costo_referencia, regla.tipo, regla.valor),
    )


def relacion_con_la_base(precio_final: Decimal, precio_base: Decimal | None) -> str:
    """`NUEVO` si el producto no tenía precio en la versión base (o no hay versión base),
    `IGUAL` si tiene el mismo y `CAMBIA` si tiene otro (PRC-17)."""
    rechazar_punto_flotante(precio_final, "El precio final")
    if precio_base is None:
        return NUEVO
    return IGUAL if precio_final == precio_base else CAMBIA


@dataclass(frozen=True)
class Senales:
    """Las señales de un precio del borrador (`design.md` D2, D3, D7)."""

    sin_costo: bool
    margen_menor: bool
    costo_otra_regla_iva: bool
    costos_distintos_por_presentacion: bool


def calcular_senales(
    *,
    manual: bool,
    precio_final: Decimal,
    precio_calculado: Decimal | None,
    computa_credito_fiscal_del_costo: bool | None,
    computa_credito_fiscal_actual: bool,
    costos_distintos_por_presentacion: bool,
) -> Senales:
    """Qué señales lleva un precio.

    - `sin_costo`: un precio manual sin precio calculado (sin costo o sin regla): no se puede
      comparar con nada (D7).
    - `margen_menor`: un precio manual menor que el calculado sin redondear con la regla
      aplicable (PRC-17). Un precio calculado nunca la lleva: su diferencia es el redondeo.
    - `costo_otra_regla_iva`: el costo informado usado se registró con una regla de crédito
      fiscal distinta de la actual de la organización (CST-06, D3).
    - `costos_distintos_por_presentacion`: D2, solo si el precio salió de un costo.
    """
    rechazar_punto_flotante(precio_final, "El precio final")
    if precio_calculado is not None:
        rechazar_punto_flotante(precio_calculado, "El precio calculado")
    con_costo = computa_credito_fiscal_del_costo is not None
    return Senales(
        sin_costo=manual and precio_calculado is None,
        margen_menor=manual and precio_calculado is not None and precio_final < precio_calculado,
        costo_otra_regla_iva=(
            con_costo and computa_credito_fiscal_del_costo != computa_credito_fiscal_actual
        ),
        costos_distintos_por_presentacion=con_costo and costos_distintos_por_presentacion,
    )
