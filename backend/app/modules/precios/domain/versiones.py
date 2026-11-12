"""Versión vigente, estados derivados y reglas de transición de una versión de lista (PRC-02 a
PRC-05, INV-11; spec `precios/versiones-de-lista`; `design.md` D6; `01` §18).

Funciones puras sobre datos: el reloj es un dato de entrada (`momento`) y nada de acá lee la
hora ni la base. El estado almacenado es `BORRADOR`, `PUBLICADA` o `ANULADA`; `PROGRAMADA`,
`VIGENTE` e `HISTORICA` se derivan de las fechas al consultar y no se almacenan (PRC-03).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.precios.domain.errores import (
    VersionNoEsBorradorError,
    VersionNoPublicadaError,
    VersionSinPreciosError,
    VersionYaVigenteError,
    VigenciaDuplicadaError,
    VigenciaInvalidaError,
)

BORRADOR = "BORRADOR"
PUBLICADA = "PUBLICADA"
ANULADA = "ANULADA"

PROGRAMADA = "PROGRAMADA"
VIGENTE = "VIGENTE"
HISTORICA = "HISTORICA"
"""Estados derivados de una versión `PUBLICADA` (`01` §18: HISTÓRICA; el código va sin tilde,
como el resto de los códigos estables)."""


@dataclass(frozen=True)
class VersionDeLista:
    """Lo que las reglas de versiones necesitan de una versión."""

    id: UUID
    numero: int
    estado: str
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None


def _rige_en(version: VersionDeLista, momento: datetime) -> bool:
    """Publicada, ya comenzada (la vigencia desde no supera el momento) y no vencida (la
    vigencia hasta, si existe, es posterior al momento): PRC-03."""
    return (
        version.estado == PUBLICADA
        and version.vigencia_desde is not None
        and version.vigencia_desde <= momento
        and (version.vigencia_hasta is None or version.vigencia_hasta > momento)
    )


def version_vigente(
    versiones: Iterable[VersionDeLista], momento: datetime
) -> VersionDeLista | None:
    """La versión vigente de una lista en `momento` (PRC-03, D6): entre las `PUBLICADA` que ya
    empezaron y no vencieron, la de mayor vigencia desde; `None` si no hay (un borrador o una
    anulada nunca son vigentes). Cuando una versión con vigencia hasta vence, la vigencia
    vuelve a la anterior."""
    candidatas = [version for version in versiones if _rige_en(version, momento)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda version: version.vigencia_desde or momento)


def estado_derivado(
    version: VersionDeLista, vigente: VersionDeLista | None, momento: datetime
) -> str | None:
    """`PROGRAMADA` (publicada cuya vigencia aún no comenzó), `VIGENTE` o `HISTORICA`
    (publicada que ya empezó y no es la vigente) para una versión `PUBLICADA`; `None` para un
    borrador o una anulada (PRC-03)."""
    if version.estado != PUBLICADA:
        return None
    if version.vigencia_desde is not None and version.vigencia_desde > momento:
        return PROGRAMADA
    if vigente is not None and vigente.id == version.id:
        return VIGENTE
    return HISTORICA


def estados_derivados(
    versiones: Collection[VersionDeLista], momento: datetime
) -> dict[UUID, str | None]:
    """El estado derivado de cada versión de una lista en `momento`."""
    vigente = version_vigente(versiones, momento)
    return {version.id: estado_derivado(version, vigente, momento) for version in versiones}


@dataclass(frozen=True)
class VigenciaDePublicacion:
    """La vigencia con que queda una versión publicada."""

    desde: datetime
    hasta: datetime | None


def validar_publicacion(
    version: VersionDeLista,
    *,
    momento: datetime,
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
    vigencias_publicadas: Collection[datetime],
    cantidad_precios: int,
) -> VigenciaDePublicacion:
    """Valida la publicación de un borrador y devuelve su vigencia (PRC-02, PRC-04, D6):

    1. Solo un `BORRADOR` se publica (`VERSION_NO_ES_BORRADOR`): una versión publicada no
       cambia (INV-11).
    2. Sin vigencia desde se usa el momento de la publicación; una vigencia desde anterior al
       momento se rechaza (`VIGENCIA_INVALIDA`: nunca se publica hacia atrás) y la vigencia
       hasta tiene que ser posterior a la desde.
    3. Otra versión publicada con la misma vigencia desde (`VIGENCIA_DUPLICADA`).
    4. Un borrador sin precios (`VERSION_SIN_PRECIOS`).
    """
    if version.estado != BORRADOR:
        raise VersionNoEsBorradorError(
            f"La versión {version.numero} está {version.estado}: solo se publica un borrador."
        )
    desde = momento if vigencia_desde is None else vigencia_desde
    if desde < momento:
        raise VigenciaInvalidaError(
            "La vigencia desde no puede ser anterior al momento de la publicación: "
            "nunca se publica hacia atrás."
        )
    if vigencia_hasta is not None and vigencia_hasta <= desde:
        raise VigenciaInvalidaError(
            "La vigencia hasta tiene que ser posterior a la vigencia desde."
        )
    if desde in vigencias_publicadas:
        raise VigenciaDuplicadaError(
            "Otra versión publicada de la lista tiene la misma vigencia desde."
        )
    if cantidad_precios < 1:
        raise VersionSinPreciosError(
            f"El borrador {version.numero} no tiene ningún precio: no se puede publicar."
        )
    return VigenciaDePublicacion(desde=desde, hasta=vigencia_hasta)


def validar_anulacion(version: VersionDeLista, *, momento: datetime) -> None:
    """Valida la anulación de una versión (PRC-05): solo una `PUBLICADA` (`VERSION_NO_PUBLICADA`
    para un borrador o una ya anulada) cuya vigencia desde es posterior al momento
    (`VERSION_YA_VIGENTE` si ya comenzó, también en el instante exacto)."""
    if version.estado != PUBLICADA:
        raise VersionNoPublicadaError(
            f"La versión {version.numero} está {version.estado}: "
            "solo se anula una versión publicada."
        )
    if version.vigencia_desde is None or version.vigencia_desde <= momento:
        raise VersionYaVigenteError(
            f"La vigencia de la versión {version.numero} ya comenzó: no se puede anular."
        )
