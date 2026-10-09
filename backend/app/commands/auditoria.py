"""Dato opcional de auditoría que un handler devuelve como parte de su resultado
(AUD-01, AUD-02, ADR-022, change 14 `design.md` D10, D10.1).

Vive en `app/commands` y no en `app/modules/sync` por la misma razón que
`ObservacionProducida`: el `commands.py` de un módulo de negocio lo usa sin importar `sync`
(contrato `commands-no-modulos`, `02` §5.3). `sync/service.py` lo pasa a
`identidad_service.registrar_auditoria`, de modo que el comando sigue dejando UNA sola fila
de auditoría (ADR-022). Un handler que no lo devuelve deja `motivo_id` nulo."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DatosDeAuditoria:
    """Lo que el handler le pide al bus que copie a SU fila de auditoría.

    `motivo_id` es el motivo de la operación (por ejemplo, el de un ajuste de stock). Solo
    se copia si el comando termina aceptado: un resultado rechazado no deja motivo."""

    motivo_id: UUID | None = None
