"""Interfaz pública de `configuracion` (`CLAUDE.md` §4): alta, listado de
activos, listado por ámbito y desactivación de los tres catálogos
configurables (TR-09).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.configuracion import repository
from app.modules.configuracion.domain.medios import (
    ImporteInvalidoError as ImporteInvalidoError,
)
from app.modules.configuracion.domain.medios import (
    MedioDePago as MedioDePago,
)
from app.modules.configuracion.domain.medios import (
    MediosInvalidosError as MediosInvalidosError,
)
from app.modules.configuracion.domain.medios import (
    MediosNoSumanImporteError as MediosNoSumanImporteError,
)
from app.modules.configuracion.domain.medios import (
    ReferenciaObligatoriaError as ReferenciaObligatoriaError,
)
from app.modules.configuracion.domain.medios import (
    posiciones_sin_referencia as posiciones_sin_referencia,
)
from app.modules.configuracion.domain.medios import (
    validar_medios as validar_medios,
)
from app.modules.configuracion.domain.valores import (
    MedioPagoNoEncontradoError,
    validar_ambito_motivo,
    validar_nombre_medio_pago,
    validar_quedan_medios_activos,
    validar_valor_alicuota,
)
from app.modules.configuracion.models import AlicuotaIva, MedioPago, Motivo
from app.modules.identidad import service as identidad_service

# --- alicuota_iva -----------------------------------------------------------


def crear_alicuota(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, nombre: str, valor: Decimal
) -> AlicuotaIva:
    validar_valor_alicuota(valor)
    return repository.crear_alicuota(
        organizacion_id, sesion, nombre=nombre, valor=valor, momento=reloj.now()
    )


def listar_alicuotas_activas(organizacion_id: UUID, sesion: Session) -> list[AlicuotaIva]:
    return repository.listar_alicuotas_activas(organizacion_id, sesion)


def obtener_alicuota_por_id(
    organizacion_id: UUID, alicuota_id: UUID, sesion: Session
) -> AlicuotaIva | None:
    """Lectura pública de una alícuota por id (change 05, `design.md`:
    "`catalogo` la consume por `configuracion/service.py`", `CLAUDE.md` §4:
    un módulo usa a otro solo a través de su `service.py`). Nunca devuelve
    la fila de otra organización: el filtro va siempre por
    `organizacion_id`."""
    return repository.obtener_alicuota_por_id(organizacion_id, sesion, alicuota_id)


def buscar_alicuotas_por_valor(
    organizacion_id: UUID, valor: Decimal, sesion: Session
) -> list[AlicuotaIva]:
    """Lectura pública para la importación (change 10, `design.md` D4: alícuota por
    porcentaje): las alícuotas de la organización con ese valor exacto (fracción, 21%
    es `0.21`), activas o no; el alta de producto rechaza después una inactiva con
    `ALICUOTA_INACTIVA`. Nunca devuelve las de otra organización."""
    return repository.buscar_alicuotas_por_valor(organizacion_id, sesion, valor)


def desactivar_alicuota(
    organizacion_id: UUID, sesion: Session, reloj: Clock, alicuota_id: UUID
) -> AlicuotaIva | None:
    return repository.desactivar_alicuota(organizacion_id, sesion, alicuota_id, momento=reloj.now())


# --- medio_pago --------------------------------------------------------------


PERMISO_MEDIOS_PAGO = "ADMIN_CONFIGURACION"
"""Quien administra los medios de pago (change 17b, D1)."""


def exigir_permiso_de_medios_pago(organizacion_id: UUID, usuario_id: UUID, sesion: Session) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario no tiene `ADMIN_CONFIGURACION` (INV-01,
    SEG-06). Lo llaman los handlers PRIMERO: un rechazo no puede dejar nada escrito. Vive acá
    porque `service.py` es el único archivo del módulo que alcanza a `identidad`."""
    permitidos = identidad_service.listar_permisos_del_usuario(organizacion_id, usuario_id, sesion)
    if PERMISO_MEDIOS_PAGO not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_MEDIOS_PAGO}.")


def _estado_para_auditoria(medio: MedioPago) -> dict[str, object]:
    """Lo que la auditoría guarda de un medio (D11, AUD-01): nombre, marca y estado."""
    return {
        "nombre": medio.nombre,
        "requiere_referencia": medio.requiere_referencia,
        "activo": medio.activo,
    }


def crear_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    requiere_referencia: bool,
    actor_id: UUID | None = None,
    dispositivo_id_actor: UUID | None = None,
    operation_id: UUID | None = None,
) -> MedioPago:
    """Alta de un medio activo con el nombre recortado. Un nombre repetido en la organización,
    activo o no y sin distinguir mayúsculas, es `NOMBRE_DUPLICADO` (D3). Con `operation_id`
    (llamada desde `MEDIO_PAGO_CREAR`) deja una fila de auditoría con `despues` (D11); la
    siembra no pasa `operation_id` y no audita. Sin `commit`: la transacción es del bus."""
    nombre_valido = validar_nombre_medio_pago(nombre)
    momento = reloj.now()
    medio = repository.crear_medio_pago(
        organizacion_id,
        sesion,
        nombre=nombre_valido,
        requiere_referencia=requiere_referencia,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    if operation_id is not None:
        identidad_service.registrar_auditoria(
            organizacion_id,
            sesion,
            reloj,
            accion="MEDIO_PAGO_CREAR",
            entidad="medio_pago",
            entidad_id=medio.id,
            ocurrido_en=momento,
            usuario_id=actor_id,
            dispositivo_id=dispositivo_id_actor,
            despues=_estado_para_auditoria(medio),
            operation_id=operation_id,
            origen="COMANDO",
        )
    return medio


def modificar_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    medio_pago_id: UUID,
    nombre: str,
    requiere_referencia: bool,
    activo: bool,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> MedioPago:
    """`MEDIO_PAGO_MODIFICAR` (D2, D4): reemplazo completo de nombre, marca de referencia y
    estado. Bloquea los medios de la organización `FOR UPDATE` ANTES de contar los activos, así
    dos bajas simultáneas no dejan cero (`ULTIMO_MEDIO_ACTIVO`, 409). Un medio ajeno o
    inexistente es 404 (INV-21). Deja UNA fila de auditoría con `antes` y `despues` (D11).
    Sin `commit`: la transacción es del bus."""
    nombre_valido = validar_nombre_medio_pago(nombre)
    medios = repository.bloquear_medios_pago(organizacion_id, sesion)
    medio = next((m for m in medios if m.id == medio_pago_id), None)
    if medio is None:
        raise MedioPagoNoEncontradoError("El medio de pago no existe en esta organización.")

    validar_quedan_medios_activos(
        sum(1 for m in medios if m.activo), medio_activo=medio.activo, activo_nuevo=activo
    )

    antes = _estado_para_auditoria(medio)
    momento = reloj.now()
    repository.actualizar_medio_pago(
        organizacion_id,
        sesion,
        medio,
        nombre=nombre_valido,
        requiere_referencia=requiere_referencia,
        activo=activo,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="MEDIO_PAGO_MODIFICAR",
        entidad="medio_pago",
        entidad_id=medio.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues=_estado_para_auditoria(medio),
        operation_id=operation_id,
        origen="COMANDO",
    )
    return medio


def obtener_medio_pago(
    organizacion_id: UUID, medio_pago_id: UUID, sesion: Session
) -> MedioPago | None:
    """Lectura pública de un medio de pago por id, activo o no (change 11: compras de
    contado). Nunca devuelve la fila de otra organización."""
    return repository.obtener_medio_pago_por_id(organizacion_id, sesion, medio_pago_id)


def listar_medios_pago_activos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    return repository.listar_medios_pago_activos(organizacion_id, sesion)


def listar_medios_pago_todos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    """Todos los medios de la organización, activos o no, por nombre (change 17b, D6)."""
    return repository.listar_medios_pago_todos(organizacion_id, sesion)


def desactivar_medio_pago(
    organizacion_id: UUID, sesion: Session, reloj: Clock, medio_pago_id: UUID
) -> MedioPago | None:
    return repository.desactivar_medio_pago(
        organizacion_id, sesion, medio_pago_id, momento=reloj.now()
    )


# --- motivo -------------------------------------------------------------------


def crear_motivo(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, ambito: str, nombre: str
) -> Motivo:
    validar_ambito_motivo(ambito)
    return repository.crear_motivo(
        organizacion_id, sesion, ambito=ambito, nombre=nombre, momento=reloj.now()
    )


def obtener_motivo(organizacion_id: UUID, motivo_id: UUID, sesion: Session) -> Motivo | None:
    """Lectura pública de un motivo por id, activo o no (change 11: anulación de
    compras). Nunca devuelve la fila de otra organización."""
    return repository.obtener_motivo_por_id(organizacion_id, sesion, motivo_id)


def listar_motivos_activos(organizacion_id: UUID, sesion: Session) -> list[Motivo]:
    return repository.listar_motivos_activos(organizacion_id, sesion)


def listar_motivos_por_ambito(organizacion_id: UUID, sesion: Session, ambito: str) -> list[Motivo]:
    validar_ambito_motivo(ambito)
    return repository.listar_motivos_por_ambito(organizacion_id, sesion, ambito)


def desactivar_motivo(
    organizacion_id: UUID, sesion: Session, reloj: Clock, motivo_id: UUID
) -> Motivo | None:
    return repository.desactivar_motivo(organizacion_id, sesion, motivo_id, momento=reloj.now())
