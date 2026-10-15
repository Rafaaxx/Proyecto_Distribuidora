"""Validación del contenido de una regla de descuento (spec `descuentos/reglas-de-descuento`;
DSC-01 a DSC-04, TR-01, TR-02, INV-03, INV-04; `design.md` D1, D5, D8, D17).

Funciones puras sobre datos: sin acceso a la base ni al reloj. Que los alcances existan en la
organización lo verifica el servicio con `catalogo/service.py`; acá solo se valida que el
conjunto de alcances sea coherente con el tipo de regla.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from uuid import UUID

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.errores import (
    AccionInvalidaError,
    AlcanceInvalidoError,
    NombreInvalidoError,
    PrioridadInvalidaError,
    ReglaDescuentoInvalidaError,
    UmbralInvalidoError,
    VigenciaInvalidaError,
)
from app.modules.descuentos.domain.tipos import (
    ACCIONES,
    MEDIDAS,
    OPERADORES,
    TIPOS_ALCANCE,
    TIPOS_REGLA,
)

_CUATRO_DECIMALES = Decimal("0.0001")
_SEIS_DECIMALES = Decimal("0.000001")
_DOS_DECIMALES = Decimal("0.01")
_UMBRAL_MAXIMO = Decimal("10000000000")  # numeric(14,4): 10 enteros
_IMPORTE_MAXIMO = Decimal("1000000000000")  # numeric(14,2): 12 enteros
_PRIORIDAD_MAXIMA = 2_147_483_647  # integer de PostgreSQL


@dataclass(frozen=True)
class AlcanceNuevo:
    """Un alcance pedido: producto, categoría o marca."""

    tipo: str
    entidad_id: UUID | str


@dataclass(frozen=True)
class ReglaValidada:
    """Contenido de una regla ya validado y normalizado: umbral a cuatro decimales, porcentaje a
    seis o importe a dos, exactamente uno de los dos según la acción."""

    nombre: str
    tipo: str
    medida: str
    operador: str
    umbral: Decimal
    accion_tipo: str
    accion_porcentaje: Decimal | None
    accion_importe: Decimal | None
    prioridad: int
    acumulable: bool
    alcances: tuple[AlcanceNuevo, ...]
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None


def _decimal_exacto(valor: object, nombre: str, error: type[Exception]) -> Decimal:
    """Un `Decimal` finito a partir de un `Decimal` o una cadena; un `float` o un `bool` se
    rechazan por INV-03 (`EntradaNoEsDineroExactoError`) y una cadena que no es un número, con el
    error de la regla (`error`)."""
    if isinstance(valor, bool | float):
        raise EntradaNoEsDineroExactoError(
            f"{nombre} no puede ser un punto flotante binario: {valor!r} "
            "(INV-03: usar Decimal o una cadena numérica exacta)"
        )
    try:
        if isinstance(valor, Decimal):
            exacto = valor
        elif isinstance(valor, str):
            exacto = Decimal(valor.strip())
        else:
            raise error(f"{nombre} {valor!r} no es un decimal exacto.")
    except InvalidOperation as causa:
        raise error(f"{nombre} {valor!r} no es un decimal exacto.") from causa
    if not exacto.is_finite():
        raise error(f"{nombre} {valor!r} no es un número finito.")
    return exacto


def _tiene_a_lo_sumo(exacto: Decimal, paso: Decimal) -> bool:
    return exacto.quantize(paso, rounding=ROUND_DOWN) == exacto


def _validar_umbral(medida: str, umbral: object) -> Decimal:
    exacto = _decimal_exacto(umbral, "El umbral", UmbralInvalidoError)
    if exacto <= 0:
        raise UmbralInvalidoError(f"El umbral debe ser mayor que 0 (recibido {umbral}).")
    if exacto >= _UMBRAL_MAXIMO:
        raise UmbralInvalidoError(f"El umbral debe ser menor que {_UMBRAL_MAXIMO}.")
    if medida == "UNIDADES_BASE" and exacto != exacto.to_integral_value():
        raise UmbralInvalidoError(
            f"El umbral en unidades base es un entero, sin decimales (recibido {umbral})."
        )
    if medida == "CAJAS_EQUIVALENTES" and not _tiene_a_lo_sumo(exacto, _CUATRO_DECIMALES):
        raise UmbralInvalidoError(
            f"El umbral en cajas admite hasta cuatro decimales (recibido {umbral})."
        )
    if medida == "IMPORTE_BRUTO" and not _tiene_a_lo_sumo(exacto, _DOS_DECIMALES):
        raise UmbralInvalidoError(
            f"El umbral en importe admite hasta dos decimales (recibido {umbral})."
        )
    return exacto.quantize(_CUATRO_DECIMALES)


def _validar_accion(accion_tipo: str, valor: object) -> tuple[Decimal | None, Decimal | None]:
    """`(accion_porcentaje, accion_importe)`: exactamente uno de los dos no es nulo."""
    exacto = _decimal_exacto(valor, "El valor de la acción", AccionInvalidaError)
    if exacto <= 0:
        raise AccionInvalidaError(f"El valor de la acción debe ser mayor que 0 (recibido {valor}).")
    if accion_tipo == "PORCENTAJE":
        if exacto > 1:
            raise AccionInvalidaError(
                f"Un porcentaje de descuento es una fracción de hasta 1, o sea 100% "
                f"(recibido {valor})."
            )
        if not _tiene_a_lo_sumo(exacto, _SEIS_DECIMALES):
            raise AccionInvalidaError(
                f"Un porcentaje de descuento admite hasta seis decimales (recibido {valor})."
            )
        return exacto.quantize(_SEIS_DECIMALES), None
    if exacto >= _IMPORTE_MAXIMO:
        raise AccionInvalidaError(f"El importe fijo debe ser menor que {_IMPORTE_MAXIMO}.")
    if not _tiene_a_lo_sumo(exacto, _DOS_DECIMALES):
        raise AccionInvalidaError(f"Un importe fijo admite hasta dos decimales (recibido {valor}).")
    return None, exacto.quantize(_DOS_DECIMALES)


def _validar_prioridad(prioridad: object) -> int:
    if not isinstance(prioridad, int) or isinstance(prioridad, bool):
        raise PrioridadInvalidaError(f"La prioridad debe ser un entero (recibido {prioridad!r}).")
    if prioridad < 1 or prioridad > _PRIORIDAD_MAXIMA:
        raise PrioridadInvalidaError(
            f"La prioridad debe ser un entero entre 1 y {_PRIORIDAD_MAXIMA} (recibido {prioridad})."
        )
    return prioridad


def _validar_alcances(tipo: str, alcances: Sequence[AlcanceNuevo]) -> tuple[AlcanceNuevo, ...]:
    if tipo == "VOLUMEN_OPERACION":
        if alcances:
            raise AlcanceInvalidoError("Una regla de operación completa no lleva alcances.")
        return ()
    if not alcances:
        raise AlcanceInvalidoError("Una regla de alcance necesita al menos un alcance.")
    vistos: set[tuple[str, str]] = set()
    for alcance in alcances:
        if alcance.tipo not in TIPOS_ALCANCE:
            raise AlcanceInvalidoError(
                f"El alcance {alcance.tipo!r} no existe: debe ser uno de "
                f"{', '.join(sorted(TIPOS_ALCANCE))}."
            )
        clave = (alcance.tipo, str(alcance.entidad_id))
        if clave in vistos:
            raise AlcanceInvalidoError(
                f"El alcance {alcance.tipo} {alcance.entidad_id} está repetido en la regla."
            )
        vistos.add(clave)
    return tuple(alcances)


def validar_vigencia(desde: datetime | None, hasta: datetime | None) -> None:
    """La vigencia hasta, si existe, es posterior a la desde cuando también existe (D16)."""
    if desde is not None and hasta is not None and hasta <= desde:
        raise VigenciaInvalidaError(
            f"La vigencia hasta ({hasta.isoformat()}) debe ser posterior a la vigencia desde "
            f"({desde.isoformat()})."
        )


def _validar_catalogo(nombre: str, valor: str, permitidos: frozenset[str]) -> None:
    if valor not in permitidos:
        raise ReglaDescuentoInvalidaError(
            f"{nombre} {valor!r} no existe: debe ser uno de {', '.join(sorted(permitidos))}."
        )


def validar_regla(
    *,
    nombre: str,
    tipo: str,
    medida: str,
    operador: str,
    umbral: object,
    accion_tipo: str,
    accion_valor: object,
    prioridad: object,
    acumulable: bool,
    alcances: Sequence[AlcanceNuevo],
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
) -> ReglaValidada:
    """Valida el contenido de una regla de descuento (DSC-01 a DSC-04).

    - Tipo, medida, operador y acción son listas cerradas (`design.md` D1): lo demás es
      `REGLA_DESCUENTO_INVALIDA`.
    - El nombre se recorta y no queda vacío (`NOMBRE_INVALIDO`).
    - El umbral es mayor que 0 y respeta la medida (`UMBRAL_INVALIDO`, D5).
    - El valor de la acción respeta su tipo (`ACCION_INVALIDA`, TR-02); un punto flotante se
      rechaza (INV-03).
    - La prioridad es un entero desde 1 (`PRIORIDAD_INVALIDA`, D8).
    - Los alcances son coherentes con el tipo (`ALCANCE_INVALIDO`).
    - La vigencia hasta es posterior a la desde (`VIGENCIA_INVALIDA`, D16).
    """
    _validar_catalogo("El tipo de regla", tipo, TIPOS_REGLA)
    _validar_catalogo("La medida", medida, MEDIDAS)
    _validar_catalogo("El operador", operador, OPERADORES)
    _validar_catalogo("La acción", accion_tipo, ACCIONES)

    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise NombreInvalidoError("El nombre de la regla no puede quedar vacío.")

    umbral_validado = _validar_umbral(medida, umbral)
    porcentaje, importe = _validar_accion(accion_tipo, accion_valor)
    prioridad_validada = _validar_prioridad(prioridad)
    alcances_validados = _validar_alcances(tipo, alcances)
    validar_vigencia(vigencia_desde, vigencia_hasta)

    return ReglaValidada(
        nombre=nombre_limpio,
        tipo=tipo,
        medida=medida,
        operador=operador,
        umbral=umbral_validado,
        accion_tipo=accion_tipo,
        accion_porcentaje=porcentaje,
        accion_importe=importe,
        prioridad=prioridad_validada,
        acumulable=acumulable,
        alcances=alcances_validados,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
    )
