"""Interfaz pública de `configuracion` (`CLAUDE.md` §4): alta, listado de
activos, listado por ámbito y desactivación de los tres catálogos
configurables (TR-09).
"""

from __future__ import annotations

from collections.abc import Callable
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
    AMBITOS_MOTIVO,
    AmbitoInvalidoError,
    MedioPagoNoEncontradoError,
    parsear_valor_alicuota,
    validar_ambito_motivo,
    validar_baja_de_alicuota,
    validar_nombre_alicuota,
    validar_nombre_medio_pago,
    validar_nombre_motivo,
    validar_quedan_medios_activos,
    validar_quedan_motivos_activos,
    validar_valor_alicuota,
    validar_valor_no_cambia,
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


# --- administración de alícuotas (change 20c, D6 a D9, D13) ------------------------------

VerificadorUsoAlicuota = Callable[[UUID, UUID, Session], int]
"""`funcion(organizacion_id, alicuota_id, sesion) -> int` (D9): cuántos productos activos de la
organización usan la alícuota. Lo registra `catalogo` al importar su `service.py` (precedente
ADR-023); `configuracion` nunca importa `catalogo`."""

_VERIFICADORES_USO_ALICUOTA: dict[str, VerificadorUsoAlicuota] = {}


def registrar_verificador_uso_alicuota(nombre: str, funcion: VerificadorUsoAlicuota) -> None:
    """Registra `funcion` bajo el nombre del módulo dueño (un doble registro con el mismo nombre
    reemplaza al anterior, así un error de programación no suma dos veces)."""
    _VERIFICADORES_USO_ALICUOTA[nombre] = funcion


def contar_productos_activos_con_alicuota(
    organizacion_id: UUID, alicuota_id: UUID, sesion: Session
) -> int:
    """Suma lo que cuentan los verificadores registrados; sin ninguno, cero (D8, D9)."""
    return sum(
        funcion(organizacion_id, alicuota_id, sesion)
        for funcion in _VERIFICADORES_USO_ALICUOTA.values()
    )


def obtener_alicuota_para_compartir(
    organizacion_id: UUID, alicuota_id: UUID, sesion: Session
) -> AlicuotaIva | None:
    """Lectura con `FOR SHARE` para el alta y la modificación de un producto (D9): se serializa
    contra la baja de la alícuota (`FOR UPDATE`). Nunca devuelve la de otra organización."""
    return repository.obtener_alicuota_para_compartir(organizacion_id, sesion, alicuota_id)


def _estado_de_alicuota_para_auditoria(alicuota: AlicuotaIva) -> dict[str, object]:
    """Lo que la auditoría guarda de una alícuota (D13, AUD-01); el valor, como string (INV-03)."""
    return {
        "nombre": alicuota.nombre,
        "valor": format(alicuota.valor, ".6f"),
        "activo": alicuota.activo,
    }


def crear_alicuota_por_comando(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    valor: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> AlicuotaIva:
    """`ALICUOTA_CREAR` (D6, D7): alta de una alícuota activa con el nombre recortado. El valor
    llega como texto decimal. Nombre y valor repetidos (activas o no) son `NOMBRE_DUPLICADO` y
    `VALOR_DUPLICADO` (409). Deja una fila de auditoría con `despues` (D13). Sin `commit`."""
    nombre_valido = validar_nombre_alicuota(nombre)
    valor_valido = parsear_valor_alicuota(valor)
    momento = reloj.now()
    alicuota = repository.crear_alicuota(
        organizacion_id,
        sesion,
        nombre=nombre_valido,
        valor=valor_valido,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    sesion.refresh(alicuota)
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ALICUOTA_CREAR",
        entidad="alicuota_iva",
        entidad_id=alicuota.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        despues=_estado_de_alicuota_para_auditoria(alicuota),
        operation_id=operation_id,
        origen="COMANDO",
    )
    return alicuota


def modificar_alicuota(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    alicuota_id: UUID,
    nombre: str,
    valor: str,
    activo: bool,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> AlicuotaIva:
    """`ALICUOTA_MODIFICAR` (D6, D8): reemplazo de nombre y estado; un valor distinto del guardado
    es `VALOR_NO_MODIFICABLE`. Bloquea las alícuotas de la organización `FOR UPDATE` ANTES de
    contar productos y activas, así la baja no se cruza con el alta de un producto ni con otra
    baja (`ALICUOTA_EN_USO`, `ULTIMA_ALICUOTA_ACTIVA`, 409). Solo una baja (activa -> inactiva)
    valida uso y última activa. Ajena o inexistente: 404 (INV-21). Una fila de auditoría con
    `antes` y `despues` (D13). Sin `commit`."""
    nombre_valido = validar_nombre_alicuota(nombre)
    valor_recibido = parsear_valor_alicuota(valor)
    alicuotas = repository.bloquear_alicuotas(organizacion_id, sesion)
    alicuota = next((a for a in alicuotas if a.id == alicuota_id), None)
    if alicuota is None:
        raise MedioPagoNoEncontradoError("La alícuota no existe en esta organización.")

    validar_valor_no_cambia(alicuota.valor, valor_recibido)
    if alicuota.activo and not activo:
        validar_baja_de_alicuota(
            productos_activos=contar_productos_activos_con_alicuota(
                organizacion_id, alicuota.id, sesion
            ),
            activas=sum(1 for a in alicuotas if a.activo),
            activo_nuevo=activo,
        )

    antes = _estado_de_alicuota_para_auditoria(alicuota)
    momento = reloj.now()
    repository.actualizar_alicuota(
        organizacion_id,
        sesion,
        alicuota,
        nombre=nombre_valido,
        activo=activo,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ALICUOTA_MODIFICAR",
        entidad="alicuota_iva",
        entidad_id=alicuota.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues=_estado_de_alicuota_para_auditoria(alicuota),
        operation_id=operation_id,
        origen="COMANDO",
    )
    return alicuota


def desactivar_alicuota(
    organizacion_id: UUID, sesion: Session, reloj: Clock, alicuota_id: UUID
) -> AlicuotaIva | None:
    return repository.desactivar_alicuota(organizacion_id, sesion, alicuota_id, momento=reloj.now())


# --- medio_pago --------------------------------------------------------------


PERMISO_MEDIOS_PAGO = "ADMIN_CONFIGURACION"
"""Quien administra los medios de pago (change 17b, D1)."""


def exigir_permiso_de_administracion(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> None:
    """Igual que `exigir_permiso_de_medios_pago`: `ADMIN_CONFIGURACION` para motivos, alícuotas y
    redondeo por defecto (change 20c, D1)."""
    exigir_permiso_de_medios_pago(organizacion_id, usuario_id, sesion)


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


def _estado_de_motivo_para_auditoria(motivo: Motivo) -> dict[str, object]:
    """Lo que la auditoría guarda de un motivo (change 20c, D13, AUD-01)."""
    return {"ambito": motivo.ambito, "nombre": motivo.nombre, "activo": motivo.activo}


def crear_motivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ambito: str,
    nombre: str,
    actor_id: UUID | None = None,
    dispositivo_id_actor: UUID | None = None,
    operation_id: UUID | None = None,
) -> Motivo:
    """Alta de un motivo activo con el nombre recortado. Con `operation_id` (llamada desde
    `MOTIVO_CREAR`, change 20c) el ámbito fuera de la lista es `AMBITO_INVALIDO` (422), un
    nombre repetido en el ámbito, activo o no y sin distinguir mayúsculas, es `NOMBRE_DUPLICADO`
    (D3) y queda una fila de auditoría con `despues` (D13); la siembra no pasa `operation_id` y
    no audita. Sin `commit`: la transacción es del bus."""
    if operation_id is not None:
        if ambito not in AMBITOS_MOTIVO:
            raise AmbitoInvalidoError(
                f"El ámbito {ambito!r} no es válido. Valores válidos: {', '.join(AMBITOS_MOTIVO)}."
            )
    else:
        validar_ambito_motivo(ambito)
    nombre_valido = validar_nombre_motivo(nombre)
    momento = reloj.now()
    motivo = repository.crear_motivo(
        organizacion_id,
        sesion,
        ambito=ambito,
        nombre=nombre_valido,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    if operation_id is not None:
        identidad_service.registrar_auditoria(
            organizacion_id,
            sesion,
            reloj,
            accion="MOTIVO_CREAR",
            entidad="motivo",
            entidad_id=motivo.id,
            ocurrido_en=momento,
            usuario_id=actor_id,
            dispositivo_id=dispositivo_id_actor,
            despues=_estado_de_motivo_para_auditoria(motivo),
            operation_id=operation_id,
            origen="COMANDO",
        )
    return motivo


def modificar_motivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    motivo_id: UUID,
    nombre: str,
    activo: bool,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Motivo:
    """`MOTIVO_MODIFICAR` (change 20c, D2, D4): reemplazo de nombre y estado; el ámbito no
    cambia. Bloquea los motivos del ámbito `FOR UPDATE` ANTES de contar los activos, así dos
    bajas simultáneas no dejan cero (`ULTIMO_MOTIVO_ACTIVO`, 409). Un motivo ajeno o inexistente
    es 404 (INV-21). Deja UNA fila de auditoría con `antes` y `despues` (D13). Sin `commit`."""
    nombre_valido = validar_nombre_motivo(nombre)
    existente = repository.obtener_motivo_por_id(organizacion_id, sesion, motivo_id)
    if existente is None:
        raise MedioPagoNoEncontradoError("El motivo no existe en esta organización.")
    motivos = repository.bloquear_motivos_del_ambito(organizacion_id, sesion, existente.ambito)
    motivo = next((m for m in motivos if m.id == motivo_id), None)
    if motivo is None:
        raise MedioPagoNoEncontradoError("El motivo no existe en esta organización.")

    validar_quedan_motivos_activos({m.id for m in motivos if m.activo}, motivo.id, activo)

    antes = _estado_de_motivo_para_auditoria(motivo)
    momento = reloj.now()
    repository.actualizar_motivo(
        organizacion_id,
        sesion,
        motivo,
        nombre=nombre_valido,
        activo=activo,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="MOTIVO_MODIFICAR",
        entidad="motivo",
        entidad_id=motivo.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues=_estado_de_motivo_para_auditoria(motivo),
        operation_id=operation_id,
        origen="COMANDO",
    )
    return motivo


def listar_motivos_todos(
    organizacion_id: UUID, sesion: Session, ambito: str | None = None
) -> list[Motivo]:
    """Todos los motivos de la organización, activos o no, por ámbito y nombre (change 20c, D12);
    con `ambito`, solo los de ese ámbito."""
    return repository.listar_motivos_todos(organizacion_id, sesion, ambito)


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
