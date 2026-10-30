"""Handlers de comandos de `configuracion` (change 17b, `design.md` D1, D2, D4; plantilla de
`stock/commands.py` para los maestros).

Dos tipos, ambos `ONLINE` y `admite_offline=False` (`02` §6.5): exigen `sesion` y `reloj` como
parámetros de palabra clave y escriben en la base del servidor.

- `MEDIO_PAGO_CREAR`: alta de un medio activo (nombre y si pide referencia).
- `MEDIO_PAGO_MODIFICAR`: reemplazo completo (nombre, `requiere_referencia`, `activo`); la baja
  y la reactivación son el cambio de `activo`. Nunca se borra un medio (CAT-05, TR-06).

Permiso `ADMIN_CONFIGURACION` (D1), comprobado primero (por `configuracion/service.py`, único
archivo del módulo que alcanza a `identidad`): un rechazo de permiso no deja
medio, ni reserva del `operation_id`, ni auditoría. Los handlers NO atrapan errores de dominio:
los dejan subir y el bus revierte. La fila de auditoría con `antes`/`despues` (D11) la escribe
`configuracion/service.py` con el `operation_id` del sobre; el bus deja la suya genérica.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commands.catalogo import declarar_tipo
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.modules.configuracion import service as configuracion_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver `catalogo/commands.py` para la
justificación de no importarla de `sync`)."""


class MedioPagoCrearContenidoV1(BaseModel):
    """`nombre` y `requiere_referencia` (D2). `extra="forbid"`: `organizacion_id` sale del token
    y un medio nace activo."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    requiere_referencia: bool


class MedioPagoModificarContenidoV1(BaseModel):
    """Todos los campos editables del medio (D2): reemplazo completo, igual que los `PUT` de los
    demás maestros."""

    model_config = ConfigDict(extra="forbid")

    medio_pago_id: UUID
    nombre: str
    requiere_referencia: bool
    activo: bool


def manejar_medio_pago_crear(
    sobre: SobreComando,
    contenido: MedioPagoCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_medios_pago(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    medio = configuracion_service.crear_medio_pago(
        sobre.organizacion_id,
        sesion,
        reloj,
        nombre=contenido.nombre,
        requiere_referencia=contenido.requiere_referencia,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"medio_pago_id": str(medio.id)}, None


def manejar_medio_pago_modificar(
    sobre: SobreComando,
    contenido: MedioPagoModificarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_medios_pago(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    medio = configuracion_service.modificar_medio_pago(
        sobre.organizacion_id,
        sesion,
        reloj,
        medio_pago_id=contenido.medio_pago_id,
        nombre=contenido.nombre,
        requiere_referencia=contenido.requiere_referencia,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"medio_pago_id": str(medio.id)}, None


registrar_handler("MEDIO_PAGO_CREAR", 1, MedioPagoCrearContenidoV1)(manejar_medio_pago_crear)
declarar_tipo(
    "MEDIO_PAGO_CREAR", admite_online=True, admite_offline=False, permisos=("ADMIN_CONFIGURACION",)
)

registrar_handler("MEDIO_PAGO_MODIFICAR", 1, MedioPagoModificarContenidoV1)(
    manejar_medio_pago_modificar
)
declarar_tipo(
    "MEDIO_PAGO_MODIFICAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- motivos (change 20c, D2, D4) -----------------------------------------------------------


class MotivoCrearContenidoV1(BaseModel):
    """`ambito` y `nombre` (D2). `extra="forbid"`: `organizacion_id` sale del token y un motivo
    nace activo."""

    model_config = ConfigDict(extra="forbid")

    ambito: str
    nombre: str


class MotivoModificarContenidoV1(BaseModel):
    """Nombre y estado del motivo (D2): el ámbito no cambia."""

    model_config = ConfigDict(extra="forbid")

    motivo_id: UUID
    nombre: str
    activo: bool


def manejar_motivo_crear(
    sobre: SobreComando,
    contenido: MotivoCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_administracion(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    motivo = configuracion_service.crear_motivo(
        sobre.organizacion_id,
        sesion,
        reloj,
        ambito=contenido.ambito,
        nombre=contenido.nombre,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"motivo_id": str(motivo.id)}, None


def manejar_motivo_modificar(
    sobre: SobreComando,
    contenido: MotivoModificarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_administracion(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    motivo = configuracion_service.modificar_motivo(
        sobre.organizacion_id,
        sesion,
        reloj,
        motivo_id=contenido.motivo_id,
        nombre=contenido.nombre,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"motivo_id": str(motivo.id)}, None


registrar_handler("MOTIVO_CREAR", 1, MotivoCrearContenidoV1)(manejar_motivo_crear)
declarar_tipo(
    "MOTIVO_CREAR", admite_online=True, admite_offline=False, permisos=("ADMIN_CONFIGURACION",)
)

registrar_handler("MOTIVO_MODIFICAR", 1, MotivoModificarContenidoV1)(manejar_motivo_modificar)
declarar_tipo(
    "MOTIVO_MODIFICAR", admite_online=True, admite_offline=False, permisos=("ADMIN_CONFIGURACION",)
)


# --- alícuotas (change 20c, D6, D7, D8) ----------------------------------------------------


class AlicuotaCrearContenidoV1(BaseModel):
    """`nombre` y `valor` (D6). El valor viaja como string (INV-03): un número JSON se rechaza.
    `extra="forbid"`: `organizacion_id` sale del token y una alícuota nace activa."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    valor: str


class AlicuotaModificarContenidoV1(BaseModel):
    """Reemplazo completo (D6): nombre, valor y estado. El valor tiene que ser el guardado."""

    model_config = ConfigDict(extra="forbid")

    alicuota_id: UUID
    nombre: str
    valor: str
    activo: bool


def manejar_alicuota_crear(
    sobre: SobreComando,
    contenido: AlicuotaCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_administracion(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    alicuota = configuracion_service.crear_alicuota_por_comando(
        sobre.organizacion_id,
        sesion,
        reloj,
        nombre=contenido.nombre,
        valor=contenido.valor,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"alicuota_id": str(alicuota.id)}, None


def manejar_alicuota_modificar(
    sobre: SobreComando,
    contenido: AlicuotaModificarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    configuracion_service.exigir_permiso_de_administracion(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    alicuota = configuracion_service.modificar_alicuota(
        sobre.organizacion_id,
        sesion,
        reloj,
        alicuota_id=contenido.alicuota_id,
        nombre=contenido.nombre,
        valor=contenido.valor,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"alicuota_id": str(alicuota.id)}, None


registrar_handler("ALICUOTA_CREAR", 1, AlicuotaCrearContenidoV1)(manejar_alicuota_crear)
declarar_tipo(
    "ALICUOTA_CREAR", admite_online=True, admite_offline=False, permisos=("ADMIN_CONFIGURACION",)
)

registrar_handler("ALICUOTA_MODIFICAR", 1, AlicuotaModificarContenidoV1)(manejar_alicuota_modificar)
declarar_tipo(
    "ALICUOTA_MODIFICAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)
