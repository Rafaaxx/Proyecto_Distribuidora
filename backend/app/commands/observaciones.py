"""Observación que un handler produce como parte de su resultado (SYN-04, SYN-07).

Vive en `app/commands` y no en `app/modules/sync` para que el `commands.py` de un
módulo de negocio la use sin importar `sync` (contratos `*-solo-por-service-ajeno`,
`02` §5.3): `sync/service.py` la registra y la re-exporta."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ObservacionProducida:
    """Una observación que un handler produce como parte de su resultado
    (`design.md`, Goals: "un handler ... devuelve resultado y observaciones"; change 04,
    grupo 9, SYN-04, SYN-07, SYN-08).

    `operacion_tipo`/`operacion_id` identifican la operación de negocio sobre la que
    recae la observación -- no necesariamente el comando mismo (`comando_id` la asocia
    por separado): un handler de venta puede observar la venta que él mismo crea."""

    codigo: str
    operacion_tipo: str
    operacion_id: UUID
    detalle: dict[str, object] | None = None
