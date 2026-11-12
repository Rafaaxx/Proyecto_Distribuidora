"""Máquina de estados y vigencia de una regla de descuento (spec `descuentos/reglas-de-descuento`;
`01` §18, DSC-01, DSC-05 paso 2, TR-05; `design.md` D15, D16).

`BORRADOR → ACTIVA ↔ PAUSADA`; ninguna regla vuelve a `BORRADOR`. `VENCIDA` es derivado y no se
almacena: una regla activa o pausada cuya vigencia hasta ya pasó. Funciones puras: el momento
siempre llega como argumento (`core/clock.py` lo inyecta quien llama)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.descuentos.domain.errores import (
    ReglaEstadoInvalidoError,
    ReglaNoEsBorradorError,
    VigenciaInvalidaError,
)
from app.modules.descuentos.domain.reglas import validar_vigencia

BORRADOR = "BORRADOR"
ACTIVA = "ACTIVA"
PAUSADA = "PAUSADA"
ESTADO_VENCIDA = "VENCIDA"


class ConVigencia(Protocol):
    """Lo mínimo que estas funciones necesitan de una regla (guardada o ya cargada)."""

    @property
    def estado(self) -> str: ...

    @property
    def vigencia_desde(self) -> datetime | None: ...

    @property
    def vigencia_hasta(self) -> datetime | None: ...


def activar(
    estado: str,
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
    ahora: datetime,
) -> tuple[str, datetime]:
    """`BORRADOR → ACTIVA` y `PAUSADA → ACTIVA`; devuelve el estado nuevo y la vigencia desde
    efectiva: la que ya tenía o, si es la primera activación sin ella, `ahora` (D16). Cualquier
    otro estado es `REGLA_ESTADO_INVALIDO`; una regla cuya vigencia hasta ya pasó
    (`vigencia_hasta <= ahora`, extremo excluido) no se activa (`VIGENCIA_INVALIDA`)."""
    if estado not in (BORRADOR, PAUSADA):
        raise ReglaEstadoInvalidoError(
            f"Una regla {estado} no se puede activar: solo se activa un borrador o una pausada."
        )
    if vigencia_hasta is not None and vigencia_hasta <= ahora:
        raise VigenciaInvalidaError(
            f"La regla no se puede activar: su vigencia terminó el {vigencia_hasta.isoformat()}."
        )
    desde = vigencia_desde if vigencia_desde is not None else ahora
    validar_vigencia(desde, vigencia_hasta)
    return ACTIVA, desde


def pausar(estado: str) -> str:
    """`ACTIVA → PAUSADA`; cualquier otro estado es `REGLA_ESTADO_INVALIDO`."""
    if estado != ACTIVA:
        raise ReglaEstadoInvalidoError(f"Una regla {estado} no se puede pausar: solo una activa.")
    return PAUSADA


def exigir_borrador(estado: str) -> None:
    """Una regla se edita completa solo mientras es borrador (D15, TR-06)."""
    if estado != BORRADOR:
        raise ReglaNoEsBorradorError(
            f"La regla está {estado}: solo se edita un borrador. Para cambiar su condición, "
            "acción, alcance, prioridad o acumulabilidad, pausala y creá otra."
        )


def validar_fin_de_vigencia(
    vigencia_desde: datetime | None, vigencia_hasta: datetime | None
) -> None:
    """Fijar o mover la vigencia hasta de una regla activada (D15, D16): posterior a la desde."""
    validar_vigencia(vigencia_desde, vigencia_hasta)


def aplica_en(regla: ConVigencia, momento: datetime) -> bool:
    """La regla aplica en `momento` si está `ACTIVA` y `desde <= momento < hasta` (D16, mismo
    criterio que las versiones de lista, PRC-02): desde incluida, hasta excluida."""
    if regla.estado != ACTIVA or regla.vigencia_desde is None:
        return False
    if momento < regla.vigencia_desde:
        return False
    return regla.vigencia_hasta is None or momento < regla.vigencia_hasta


def estado_derivado(regla: ConVigencia, ahora: datetime) -> str:
    """El estado que se informa: `VENCIDA` para una regla activa o pausada cuya vigencia hasta
    ya pasó (`01` §18); el almacenado en cualquier otro caso."""
    if (
        regla.estado in (ACTIVA, PAUSADA)
        and regla.vigencia_hasta is not None
        and regla.vigencia_hasta <= ahora
    ):
        return ESTADO_VENCIDA
    return regla.estado
