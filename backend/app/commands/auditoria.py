"""Dato opcional de auditoría que un handler devuelve como parte de su resultado
(AUD-01, AUD-02, ADR-022, change 14 `design.md` D10, D10.1).

Vive en `app/commands` y no en `app/modules/sync` por la misma razón que
`ObservacionProducida`: el `commands.py` de un módulo de negocio lo usa sin importar `sync`
(contrato `commands-no-modulos`, `02` §5.3). `sync/service.py` lo pasa a
`identidad_service.registrar_auditoria`, de modo que el comando sigue dejando UNA sola fila
de auditoría (ADR-022). Un handler que no lo devuelve deja `motivo_id` nulo."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DatosDeAuditoria:
    """Lo que el handler le pide al bus que copie a SU fila de auditoría.

    `motivo_id` es el motivo de la operación (por ejemplo, el de un ajuste de stock). Solo
    se copia si el comando termina aceptado: un resultado rechazado no deja motivo.

    `observacion` (change 15, `design.md` D8) es la constancia de que el comando movió una
    ubicación tomada por la excepción de `LIBERAR_UBICACION` (STK-09); se copia en las mismas
    condiciones que el motivo."""

    motivo_id: UUID | None = None
    observacion: str | None = None


def observacion_de_ubicacion_tomada(jornadas: Iterable[UUID | None]) -> str | None:
    """La constancia de STK-09 para la fila de auditoría: `ubicación tomada por la jornada <id>`
    (con varias, `<id1>, <id2>`, sin repetir y en orden). Sin el prefijo `STK-09: ` desde el
    2026-10-20 (change 18a, D20); las filas ya guardadas conservan el texto anterior (AUD-03).
    `None` si ninguna ubicación estaba tomada: un movimiento sin excepción no lleva constancia."""
    ids = sorted({str(jornada) for jornada in jornadas if jornada is not None})
    if not ids:
        return None
    return f"ubicación tomada por la jornada {', '.join(ids)}"


def constancia_de_ubicacion_tomada(jornadas: Iterable[UUID | None]) -> DatosDeAuditoria:
    """El dato de auditoría de un comando que solo deja la constancia de STK-09 (sin motivo).
    Los comandos que además llevan motivo construyen `DatosDeAuditoria(motivo_id=...)` ellos
    mismos: así el ratchet del motivo y el de la constancia cuentan cosas distintas."""
    return DatosDeAuditoria(observacion=observacion_de_ubicacion_tomada(jornadas))


SEPARADOR_DE_OBSERVACIONES = "; "


def unir_observaciones(*textos: str | None) -> str | None:
    """Une los textos que un comando deja en la única observación de su fila de auditoría
    (por ejemplo, la lista usada y la constancia de STK-09), uno después del otro y separados
    por `; `. Omite los vacíos; `None` si no queda ninguno."""
    presentes = [texto for texto in textos if texto]
    return SEPARADOR_DE_OBSERVACIONES.join(presentes) if presentes else None
