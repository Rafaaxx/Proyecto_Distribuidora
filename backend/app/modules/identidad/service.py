"""Interfaz pública de `identidad` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone la lectura de organización y configuración, y el alta de una
organización con su configuración en una sola operación. Sin `commit`: la
transacción la gestiona quien llama (`docs/02-arquitectura.md` §5.2); en
este change, la sesión de la siembra o de la prueba, porque todavía no
existe el bus de comandos (change 04).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.core.seguridad import (
    derivar_hash_refresh_token,
    derivar_pin_autorizacion,
    emitir_access_token,
    generar_refresh_token,
    hashear_password,
    verificar_password,
)
from app.modules.identidad import repository
from app.modules.identidad.domain.permisos import ADMINISTRADOR, PLANTILLAS_DE_ROL
from app.modules.identidad.domain.usuarios import (
    CorrelativoNoAvanzaError,
    CredencialesInvalidasError,
    LoginBloqueadoPorIntentosError,
    RefreshTokenInvalidoError,
    RolConPermisoInexistenteError,
    RolSinAutorizacionParaPinError,
    UsuarioSinRolError,
    rol_confiere_autorizacion_excepcion,
    validar_formato_pin_autorizacion,
)
from app.modules.identidad.domain.valores import (
    validar_estado_facturacion_default,
    validar_estado_organizacion,
    validar_modo_impositivo,
    validar_politica_credito_default,
    validar_slug_organizacion,
)
from app.modules.identidad.models import (
    Auditoria,
    ConfiguracionOrganizacion,
    Dispositivo,
    Organizacion,
    Rol,
    Usuario,
)


@dataclass(frozen=True)
class DatosConfiguracionInicial:
    """Parámetros de `configuracion_organizacion` para el alta de una
    organización nueva. Los que `01` §4 marca "a definir al configurar"
    quedan explícitamente en `None` cuando así se los pase (tarea 8.3)."""

    modo_impositivo: str
    politica_credito_default: str
    estado_facturacion_default: str
    intentos_pin_max: int
    descuento_manual_habilitado: bool
    motivo_obligatorio_lista: bool
    lista_precio_default_id: UUID | None = None
    tolerancia_offline_tipo: str | None = None
    tolerancia_offline_valor: Decimal | None = None
    motivo_obligatorio_descuento: bool | None = None
    redondeo_multiplo: Decimal | None = None
    redondeo_direccion: str | None = None
    permite_consumidor_final: bool | None = None
    cliente_consumidor_final_id: UUID | None = None
    modalidad_iva_default: str | None = None
    app_version_minima: str | None = None
    desvio_reloj_max_segundos: int | None = None


def crear_organizacion_con_configuracion(
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    slug: str,
    cuit: str | None,
    moneda: str,
    zona_horaria: str,
    estado: str,
    configuracion: DatosConfiguracionInicial,
) -> Organizacion:
    """Da de alta una organización y su fila de configuración en una sola
    operación. Valida el dominio cerrado de `estado`, `modo_impositivo`,
    `politica_credito_default`, `estado_facturacion_default` y el formato
    de `slug` (`ADR-021`) antes de escribir nada."""
    validar_estado_organizacion(estado)
    validar_slug_organizacion(slug)
    validar_modo_impositivo(configuracion.modo_impositivo)
    validar_politica_credito_default(configuracion.politica_credito_default)
    validar_estado_facturacion_default(configuracion.estado_facturacion_default)

    momento = reloj.now()
    organizacion_id = nuevo_id()

    organizacion = repository.crear_organizacion(
        organizacion_id,
        sesion,
        nombre=nombre,
        slug=slug,
        cuit=cuit,
        moneda=moneda,
        zona_horaria=zona_horaria,
        estado=estado,
        momento=momento,
    )
    repository.crear_configuracion(
        organizacion_id,
        sesion,
        modo_impositivo=configuracion.modo_impositivo,
        politica_credito_default=configuracion.politica_credito_default,
        estado_facturacion_default=configuracion.estado_facturacion_default,
        intentos_pin_max=configuracion.intentos_pin_max,
        descuento_manual_habilitado=configuracion.descuento_manual_habilitado,
        motivo_obligatorio_lista=configuracion.motivo_obligatorio_lista,
        lista_precio_default_id=configuracion.lista_precio_default_id,
        tolerancia_offline_tipo=configuracion.tolerancia_offline_tipo,
        tolerancia_offline_valor=configuracion.tolerancia_offline_valor,
        motivo_obligatorio_descuento=configuracion.motivo_obligatorio_descuento,
        redondeo_multiplo=configuracion.redondeo_multiplo,
        redondeo_direccion=configuracion.redondeo_direccion,
        permite_consumidor_final=configuracion.permite_consumidor_final,
        cliente_consumidor_final_id=configuracion.cliente_consumidor_final_id,
        modalidad_iva_default=configuracion.modalidad_iva_default,
        app_version_minima=configuracion.app_version_minima,
        desvio_reloj_max_segundos=configuracion.desvio_reloj_max_segundos,
        momento=momento,
    )
    return organizacion


def obtener_organizacion(organizacion_id: UUID, sesion: Session) -> Organizacion | None:
    return repository.obtener_organizacion_por_id(organizacion_id, sesion)


def resolver_organizacion_por_slug(slug: str, sesion: Session) -> Organizacion | None:
    """Resuelve `organizacion_id` a partir de `slug` (`ADR-021`, tarea 8.3).
    Uso exclusivo del servicio de login: ninguna ruta autenticada llama a
    esto, porque ya tiene `organizacion_id` del token. Devuelve `None` si el
    slug no existe -- quien llama nunca distingue esto de una contraseña
    incorrecta en la respuesta (mismo mensaje genérico, `ADR-021`)."""
    return repository.obtener_organizacion_por_slug(slug, sesion)


def obtener_configuracion(
    organizacion_id: UUID, sesion: Session
) -> ConfiguracionOrganizacion | None:
    """Lectura de la configuración de `organizacion_id` para otros módulos
    (`design.md`: `identidad.service` expone esta lectura). Nunca devuelve
    la fila de otra organización: el filtro va siempre por `organizacion_id`."""
    return repository.obtener_configuracion(organizacion_id, sesion)


def fecha_de_negocio(organizacion_id: UUID, sesion: Session, reloj: Clock) -> date | None:
    """Deriva la fecha de negocio a partir del momento actual del reloj
    inyectable y la zona horaria de la organización (TR-04). Devuelve `None`
    si la organización no tiene configuración... en realidad la zona horaria
    vive en `organizacion`, no en su configuración: se usa `organizacion.
    zona_horaria` (`docs/03` §4)."""
    organizacion = repository.obtener_organizacion_por_id(organizacion_id, sesion)
    if organizacion is None:
        return None
    momento_utc = reloj.now()
    return momento_utc.astimezone(ZoneInfo(organizacion.zona_horaria)).date()


def registrar_auditoria(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    accion: str,
    entidad: str,
    ocurrido_en: datetime,
    usuario_id: UUID | None = None,
    dispositivo_id: UUID | None = None,
    entidad_id: UUID | None = None,
    antes: dict[str, object] | None = None,
    despues: dict[str, object] | None = None,
    motivo_id: UUID | None = None,
    observacion: str | None = None,
    autorizador_id: UUID | None = None,
    operation_id: UUID | None = None,
) -> Auditoria:
    """Registra un evento de auditoría (AUD-02, tarea 8.1).

    `occurred_at` es `ocurrido_en` (el momento del evento, informado por
    quien llama); `registered_at` es `reloj.now()` (el momento del
    servidor al escribir, TR-05). Sin `commit`: la transacción la gestiona
    quien llama (`02` §5.2) -- si esa transacción se revierte, este
    registro se revierte con ella (INV-01, tarea 8.2).

    `antes`/`despues` quedan `None` si no se pasan: nunca se inventa un
    diccionario vacío para un evento sin cambio de valor.
    """
    return repository.crear_auditoria(
        organizacion_id,
        sesion,
        auditoria_id=nuevo_id(),
        accion=accion,
        entidad=entidad,
        occurred_at=ocurrido_en,
        registered_at=reloj.now(),
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        entidad_id=entidad_id,
        antes=antes,
        despues=despues,
        motivo_id=motivo_id,
        observacion=observacion,
        autorizador_id=autorizador_id,
        operation_id=operation_id,
    )


# --- Alta de usuarios y composición de roles (tarea 8.9) --------------------
#
# NOTA (design.md D6): estas escrituras (alta de usuario, cambio de
# composición de rol, rotación de PIN en el grupo 9) quedan, a propósito,
# fuera del bus de comandos: no hacen `commit` (lo hace quien llama) y no
# tienen `operation_id`. El change 04 las envuelve en comandos; hasta
# entonces, esta es la única forma de escribirlas.


def crear_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario: str,
    nombre: str,
    email: str | None,
    password: str,
    rol_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None = None,
    tope_descuento_override: object | None = None,
) -> Usuario | None:
    """Da de alta un usuario (tarea 8.9). `rol_id` es obligatorio: un
    usuario no puede quedar sin rol (`03` §4). La contraseña se deriva con
    Argon2id (`core/seguridad.py`, tarea 7.1) antes de guardarla; nunca se
    guarda en claro ni se audita.

    Devuelve `None` sin escribir nada si `rol_id` no pertenece a
    `organizacion_id` (INV-21, SEG-07, tarea 12.2: mismo criterio que
    `cambiar_composicion_rol`/`establecer_pin_autorizacion`/
    `revocar_dispositivo` -- "no encontrado", nunca dejar que la FK
    compuesta de `usuario.rol_id` (`03` §2.4) truene como error de
    infraestructura)."""
    if rol_id is None:
        raise UsuarioSinRolError("No se puede crear un usuario sin indicar un rol.")
    if repository.obtener_rol_por_id(organizacion_id, rol_id, sesion) is None:
        return None

    momento = reloj.now()
    fila = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=usuario,
        nombre=nombre,
        email=email,
        password_hash=hashear_password(password),
        rol_id=rol_id,
        estado="ACTIVO",
        momento=momento,
        tope_descuento_override=tope_descuento_override,  # type: ignore[arg-type]
        actualizado_por_id=actor_id,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ALTA_USUARIO",
        entidad="usuario",
        entidad_id=fila.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
    )
    return fila


def cambiar_composicion_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    permisos_nuevos: frozenset[str],
    actor_id: UUID,
    dispositivo_id_actor: UUID | None = None,
) -> Rol | None:
    """Reemplaza el conjunto de permisos de `rol_id` por `permisos_nuevos`
    (tarea 8.9). Valida que todos los códigos existan en el catálogo global
    ANTES de escribir nada (`RolConPermisoInexistenteError`, en vez de dejar
    que una FK violada aparezca como error de infraestructura). Si el rol
    pierde su último permiso de autorización de excepciones, invalida el PIN
    de sus usuarios en la misma transacción (tarea 8.9.a, extensión de
    `ADR-011` confirmada el 2026-09-19).

    Devuelve `None` sin escribir nada si `rol_id` no pertenece a
    `organizacion_id` (INV-21, SEG-07, tarea 10.7: mismo criterio que
    `revocar_dispositivo`/`establecer_pin_autorizacion` -- "no encontrado",
    nunca un error de infraestructura por la FK compuesta)."""
    if repository.obtener_rol_por_id(organizacion_id, rol_id, sesion) is None:
        return None

    for codigo in permisos_nuevos:
        if repository.obtener_permiso_por_codigo(codigo, sesion) is None:
            raise RolConPermisoInexistenteError(
                f"El permiso {codigo!r} no está en el catálogo global (03 §4)."
            )

    momento = reloj.now()
    permisos_actuales = frozenset(
        repository.listar_permisos_de_rol(organizacion_id, rol_id, sesion)
    )

    for codigo in permisos_nuevos - permisos_actuales:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol_id, permiso_codigo=codigo
        )
    for codigo in permisos_actuales - permisos_nuevos:
        repository.quitar_permiso_de_rol(
            organizacion_id, sesion, rol_id=rol_id, permiso_codigo=codigo
        )

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="CAMBIAR_COMPOSICION_ROL",
        entidad="rol",
        entidad_id=rol_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"permisos": sorted(permisos_actuales)},
        despues={"permisos": sorted(permisos_nuevos)},
    )

    perdio_autorizacion = rol_confiere_autorizacion_excepcion(
        permisos_actuales
    ) and not rol_confiere_autorizacion_excepcion(permisos_nuevos)
    if perdio_autorizacion:
        _invalidar_pin_de_usuarios_del_rol(
            organizacion_id,
            sesion,
            reloj,
            rol_id=rol_id,
            actor_id=actor_id,
            dispositivo_id_actor=dispositivo_id_actor,
            momento=momento,
        )

    return repository.obtener_rol_por_id(organizacion_id, rol_id, sesion)


def _invalidar_pin_de_usuarios_del_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    momento: datetime,
) -> None:
    """Tarea 8.9.a: borra `pin_autorizacion_hash`/`_sal`/`_iteraciones` de
    todo usuario de `rol_id` que tuviera PIN definido, auditado sin exponer
    el valor del PIN (ni antes ni después)."""
    for usuario_del_rol in repository.listar_usuarios_por_rol(organizacion_id, rol_id, sesion):
        if usuario_del_rol.pin_autorizacion_hash is None:
            continue
        usuario_del_rol.pin_autorizacion_hash = None
        usuario_del_rol.pin_autorizacion_sal = None
        usuario_del_rol.pin_autorizacion_iteraciones = None
        sesion.flush()
        registrar_auditoria(
            organizacion_id,
            sesion,
            reloj,
            accion="INVALIDAR_PIN_AUTORIZACION",
            entidad="usuario",
            entidad_id=usuario_del_rol.id,
            ocurrido_en=momento,
            usuario_id=actor_id,
            dispositivo_id=dispositivo_id_actor,
            observacion="El rol perdió su último permiso de autorización de excepciones.",
        )


# --- Dispositivos (tareas 8.10, 8.11, 8.12) ---------------------------------
#
# El REGISTRO de un dispositivo, por spec, ocurre "en el primer inicio de
# sesión" (SEG-02) -- `registrar_dispositivo` es la función que ese servicio
# de login (bloqueado esta sesión: falta resolver cómo el login identifica
# la organización antes de que exista un token) va a llamar. El resto de
# `identidad/service.py` de este bloque (listar/revocar/avanzar
# correlativo) es independiente del login.

_PREFIJO_DISPOSITIVO_FORMATO = "V{:02d}"


def _generar_prefijo_dispositivo(organizacion_id: UUID, sesion: Session) -> str:
    """Asigna el próximo prefijo libre de la organización (tarea 8.12: el
    prefijo lo asigna el servidor, nunca el que informe el dispositivo).
    Formato `V01`, `V02`, ... (`02` §7.7, `design.md` Open Questions: "un
    formato sin efecto sobre specs ni tareas, se resuelve al implementar").
    """
    candidato = 1
    while True:
        prefijo = _PREFIJO_DISPOSITIVO_FORMATO.format(candidato)
        if repository.obtener_dispositivo_por_prefijo(organizacion_id, prefijo, sesion) is None:
            return prefijo
        candidato += 1


def registrar_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    dispositivo_id: UUID,
    nombre: str,
    prefijo_informado_por_dispositivo: str | None = None,
) -> Dispositivo:
    """Registra un dispositivo nuevo (tarea 8.10/8.12). `dispositivo_id` lo
    genera el DISPOSITIVO, no el servidor (`03` §4, `02` §12.2): el cliente
    lo crea en su primer arranque y lo guarda en IndexedDB antes de que
    exista ninguna sesión; el login lo envía y esta función lo usa tal cual
    como clave (compuesta con `organizacion_id`, tarea de corrección de
    esquema descubierta al implementar 8.3: ver migración
    `d4e5f6a7b8c9`). `ultimo_correlativo` arranca en `0`, sin nada consumido
    (tarea 8.11). El prefijo lo genera el servidor
    (`_generar_prefijo_dispositivo`); `prefijo_informado_por_dispositivo` se
    recibe únicamente para dejar constancia en la firma de que existe en el
    contrato de entrada y se ignora a propósito -- nunca se usa acá (tarea
    8.12).
    """
    del prefijo_informado_por_dispositivo  # Ignorado a propósito (tarea 8.12).
    momento = reloj.now()
    return repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=dispositivo_id,
        nombre=nombre,
        prefijo=_generar_prefijo_dispositivo(organizacion_id, sesion),
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=momento,
    )


def registrar_o_reutilizar_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    dispositivo_id: UUID,
    nombre: str,
) -> Dispositivo:
    """Usada por el login (tarea 8.3): si `dispositivo_id` ya está
    registrado en `organizacion_id`, lo reutiliza tal cual (conserva su
    prefijo y su estado -- puede devolver uno `REVOCADO`; es
    responsabilidad de quien llama rechazar el login en ese caso, no de
    esta función). Si no existe, lo registra."""
    existente = repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)
    if existente is not None:
        return existente
    return registrar_dispositivo(
        organizacion_id, sesion, reloj, dispositivo_id=dispositivo_id, nombre=nombre
    )


def avanzar_correlativo_dispositivo(
    organizacion_id: UUID, sesion: Session, *, dispositivo_id: UUID, propuesto: int
) -> int:
    """Actualiza `ultimo_correlativo` si `propuesto` es mayor al actual
    (tarea 8.11). Nunca retrocede: un `propuesto` menor o igual se rechaza
    con un error de dominio de código estable."""
    dispositivo = repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)
    if dispositivo is None:
        raise ValueError(f"Dispositivo {dispositivo_id} no encontrado en {organizacion_id}.")
    if propuesto <= dispositivo.ultimo_correlativo:
        raise CorrelativoNoAvanzaError(
            f"El correlativo propuesto ({propuesto}) no supera al actual "
            f"({dispositivo.ultimo_correlativo}): el último correlativo nunca retrocede."
        )
    dispositivo.ultimo_correlativo = propuesto
    sesion.flush()
    return propuesto


def listar_dispositivos(organizacion_id: UUID, sesion: Session) -> list[Dispositivo]:
    """Incluye los revocados (tarea 8.10: "El listado incluye los
    revocados")."""
    return repository.listar_dispositivos(organizacion_id, sesion)


def revocar_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    dispositivo_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None = None,
) -> Dispositivo | None:
    """Revoca un dispositivo e invalida sus refresh tokens (tarea 8.10).
    Devuelve `None` si `dispositivo_id` no pertenece a `organizacion_id`
    (INV-21: nunca se revela ni se toca un dispositivo ajeno). Revocar un
    dispositivo ya revocado no cambia nada y no audita un segundo evento.

    `dispositivo_id_actor` es el dispositivo desde el que el ACTOR está
    autenticado (`ContextoAutenticado.dispositivo_id`, tomado del access
    token -- tarea 10.4, "El dispositivo del contexto es el del token"): es
    quien queda registrado en la auditoría como origen de la operación, y es
    un dato distinto de `dispositivo_id` (el dispositivo que se revoca, el
    recurso objetivo)."""
    dispositivo = repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)
    if dispositivo is None:
        return None
    if dispositivo.estado == "REVOCADO":
        return dispositivo

    momento = reloj.now()
    dispositivo.estado = "REVOCADO"
    dispositivo.revocado_en = momento
    dispositivo.revocado_por_id = actor_id
    sesion.flush()

    repository.revocar_sesiones_refresh_de_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=dispositivo_id,
        momento=momento,
        motivo="DISPOSITIVO_REVOCADO",
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="REVOCAR_DISPOSITIVO",
        entidad="dispositivo",
        entidad_id=dispositivo_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
    )
    return dispositivo


# --- Puesta en marcha: plantillas de rol y administrador inicial (8.13) ----
#
# `design.md` D8: el catálogo de permisos y las plantillas de rol van por
# migración (dato atado al código, `03` §17); el usuario administrador va
# por la siembra (dato de negocio con organización, mismo criterio que D4
# del change 02). Ningún secreto tiene valor por defecto (`CLAUDE.md` §4):
# la contraseña la exige `password_administrador`, sin default acá.

_TOPE_DESCUENTO_ADMINISTRADOR = Decimal("1.000000")
_TOPE_DESCUENTO_PLANTILLA_DEFAULT = Decimal("0")
NOMBRE_USUARIO_ADMINISTRADOR = "admin"


def crear_plantillas_de_rol_iniciales(
    organizacion_id: UUID, sesion: Session, reloj: Clock
) -> dict[str, Rol]:
    """Crea los cinco roles de `01` §19 (ADM, GES, SUP, VEN, CON) con la
    composición de `PLANTILLAS_DE_ROL` (tarea 4.4). El tope de descuento es
    un punto de partida ajustable por la organización después (`01` §19:
    "los roles son plantillas"): `1.000000` ("sin tope") para el
    Administrador, `0` para el resto -- ninguna cifra de tope concreta para
    Supervisor/Vendedor está fijada en `docs/`, así que no se inventa una."""
    momento = reloj.now()
    roles: dict[str, Rol] = {}
    for nombre, permisos in PLANTILLAS_DE_ROL.items():
        tope = (
            _TOPE_DESCUENTO_ADMINISTRADOR
            if nombre == ADMINISTRADOR
            else _TOPE_DESCUENTO_PLANTILLA_DEFAULT
        )
        rol = repository.crear_rol(
            organizacion_id,
            sesion,
            rol_id=nuevo_id(),
            nombre=nombre,
            tope_descuento=tope,
            activo=True,
            momento=momento,
        )
        for codigo in permisos:
            repository.asignar_permiso_a_rol(
                organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        roles[nombre] = rol
    return roles


def crear_usuario_administrador_inicial(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_administrador_id: UUID,
    password: str,
) -> Usuario:
    """Crea el usuario `admin` inicial (tarea 8.13). Auto-auditado: no hay
    ningún actor previo en una organización recién creada, así que el
    propio usuario administrador figura como quien registró su alta."""
    momento = reloj.now()
    usuario_id = nuevo_id()
    fila = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        usuario=NOMBRE_USUARIO_ADMINISTRADOR,
        nombre="Administrador",
        email=None,
        password_hash=hashear_password(password),
        rol_id=rol_administrador_id,
        estado="ACTIVO",
        momento=momento,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ALTA_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=usuario_id,
    )
    return fila


# --- PIN de autorización (grupo 9, `ADR-019`, extensión de `ADR-011`) ------
#
# NOTA DE ALCANCE (ver docstring de `test_identidad_pin_autorizacion_service.
# py`): el rechazo "rotar sin ADMIN_USUARIOS" (tarea 9.3) es responsabilidad
# de la dependencia de permisos del grupo 10, todavía no implementada. Esta
# función audita `actor_id` pero no valida su permiso, igual que
# `cambiar_composicion_rol` y `crear_usuario`.


def establecer_pin_autorizacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    pin: str,
    actor_id: UUID,
) -> Usuario | None:
    """Define o rota el PIN de autorización de `usuario_id` (tareas 9.1 y
    9.2). Devuelve `None` si `usuario_id` no pertenece a `organizacion_id`
    (INV-21, SEG-07: "no encontrado", no un error distinto). Valida el
    formato del PIN y que el rol del usuario confiera algún permiso de
    autorización de excepciones ANTES de tocar nada: un PIN rechazado deja
    el anterior, si había uno, vigente. Nunca audita el valor del PIN."""
    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return None

    validar_formato_pin_autorizacion(pin)

    permisos_del_rol = frozenset(
        repository.listar_permisos_de_rol(organizacion_id, usuario.rol_id, sesion)
    )
    if not rol_confiere_autorizacion_excepcion(permisos_del_rol):
        raise RolSinAutorizacionParaPinError(
            "El rol de este usuario no confiere ningún permiso de autorización "
            "de excepciones: no puede tener PIN de autorización (01 §19)."
        )

    momento = reloj.now()
    accion = (
        "DEFINIR_PIN_AUTORIZACION"
        if usuario.pin_autorizacion_hash is None
        else ("ROTAR_PIN_AUTORIZACION")
    )
    hash_derivado, sal, iteraciones = derivar_pin_autorizacion(pin)
    usuario.pin_autorizacion_hash = hash_derivado
    usuario.pin_autorizacion_sal = sal
    usuario.pin_autorizacion_iteraciones = iteraciones
    sesion.flush()

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion=accion,
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
    )
    return usuario


# --- Autenticación (login): tarea 8.3/8.4 (`ADR-021`, `ADR-017`) -----------

REFRESH_TOKEN_TTL_DIAS = 30

# --- Rate limit de login (grupo 11, `ADR-018`) ------------------------------

LIMITE_INTENTOS_FALLIDOS_POR_USUARIO = 5
LIMITE_INTENTOS_FALLIDOS_POR_IP = 20
VENTANA_INTENTOS_LOGIN = timedelta(minutes=15)

_MENSAJE_BLOQUEO_GENERICO = "Demasiados intentos. Intentá de nuevo más tarde."


def _mensaje_de_bloqueo(desbloqueo_en: datetime | None) -> str:
    """Mismo mensaje genérico sea cual sea el límite alcanzado (tarea 11.3:
    "el bloqueo no revela si el usuario existe"). `ADR-018` pide "429 con
    momento de desbloqueo": se agrega al mensaje cuando se puede calcular
    (siempre que exista al menos un intento fallido en la ventana, que es
    justo la condición bajo la que este mensaje se emite)."""
    if desbloqueo_en is None:
        return _MENSAJE_BLOQUEO_GENERICO
    return f"{_MENSAJE_BLOQUEO_GENERICO} (desbloqueo: {desbloqueo_en.isoformat()})"


def _registrar_intento_fallido(
    sesion: Session, *, usuario_id: UUID | None, ip: str, momento: datetime
) -> None:
    repository.registrar_intento_login(
        sesion, intento_id=nuevo_id(), usuario_id=usuario_id, ip=ip, exito=False, momento=momento
    )


# Sentinela, no una IP real: distingue el marcador de desbloqueo manual de
# cualquier intento de login real en `intento_login.ip` (que siempre lleva
# una dirección de origen). Nunca se compara contra un valor de IP real.
_IP_DESBLOQUEO_MANUAL = "admin:desbloqueo-manual"


def desbloquear_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    actor_id: UUID,
) -> Usuario | None:
    """Desbloqueo manual de un usuario bloqueado por intentos (tarea 11.4,
    `ADR-018`: "un usuario con ADMIN_USUARIOS puede desbloquear manualmente
    registrando un intento de desbloqueo"). `ADMIN_USUARIOS` lo valida la
    dependencia de permisos del endpoint, no esta función (mismo criterio
    que `crear_usuario`/`cambiar_composicion_rol`/`establecer_pin_autorizacion`).

    No existe un campo "bloqueado" persistente en `usuario`: el bloqueo es
    una propiedad calculada sobre la ventana de `intento_login`
    (`repository.contar_intentos_fallidos_por_usuario`). Desbloquear
    significa insertar una fila marcador (`exito=True`, `ip` sentinela) que
    esa función trata como el nuevo punto de partida de la ventana --
    ningún intento fallido anterior al marcador vuelve a contarse, sin
    editar ni borrar ninguna fila (tabla de solo inserción, INV-05). Solo
    afecta el límite POR USUARIO, nunca el límite por IP (ver
    `test_desbloquear_no_reinicia_el_bloqueo_por_ip`): desbloquear a una
    persona no borra el historial de abuso de una dirección de origen.

    Devuelve `None` si `usuario_id` no pertenece a `organizacion_id`
    (SEG-07, INV-21)."""
    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return None

    momento = reloj.now()
    repository.registrar_intento_login(
        sesion,
        intento_id=nuevo_id(),
        usuario_id=usuario_id,
        ip=_IP_DESBLOQUEO_MANUAL,
        exito=True,
        momento=momento,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="DESBLOQUEO_MANUAL_LOGIN",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
    )
    return usuario


def _desbloqueo_por_ip(sesion: Session, *, ip: str, desde_ventana: datetime) -> datetime | None:
    mas_antiguo = repository.obtener_intento_fallido_mas_antiguo_en_ventana_por_ip(
        sesion, ip=ip, desde=desde_ventana
    )
    return None if mas_antiguo is None else mas_antiguo + VENTANA_INTENTOS_LOGIN


def _desbloqueo_por_usuario(
    sesion: Session, *, usuario_id: UUID, desde_ventana: datetime
) -> datetime | None:
    mas_antiguo = repository.obtener_intento_fallido_mas_antiguo_en_ventana_por_usuario(
        sesion, usuario_id=usuario_id, desde=desde_ventana
    )
    return None if mas_antiguo is None else mas_antiguo + VENTANA_INTENTOS_LOGIN


@dataclass(frozen=True)
class ResultadoLogin:
    access_token: str
    refresh_token: str
    usuario_id: UUID
    organizacion_id: UUID
    dispositivo_id: UUID


def iniciar_sesion(
    sesion: Session,
    reloj: Clock,
    *,
    organizacion_slug: str,
    nombre_usuario: str,
    password: str,
    dispositivo_id: UUID | None,
    nombre_dispositivo: str,
    jwt_secreto: str,
    jwt_kid: str,
    ip: str,
) -> ResultadoLogin:
    """Inicia sesión (tarea 8.3): resuelve la organización por `slug`
    (`ADR-021`) ANTES de validar credenciales, verifica usuario y
    contraseña, registra o reutiliza el dispositivo, emite access y refresh
    token, y audita.

    Todo rechazo (slug inexistente, usuario inexistente, contraseña
    incorrecta, usuario inactivo, sin dispositivo, dispositivo revocado) es
    el mismo `CredencialesInvalidasError`, mismo mensaje (tarea 8.4): nunca
    revela cuál de esas condiciones ocurrió. Un slug inexistente no se
    audita (no hay organización a la que asociar el registro, INV-02); el
    resto sí, con `usuario_id` cuando hay un usuario resuelto.

    Rate limit de login (grupo 11, `ADR-018`): el límite por IP se verifica
    ANTES de tocar `organizacion`/`usuario` (protege incluso contra un
    `organizacion_slug` inexistente, que de otro modo no dejaría ningún
    rastro). El límite por usuario se verifica apenas se resuelve un
    `usuario` real. Ambos levantan `LoginBloqueadoPorIntentosError` (429),
    con el mismo mensaje genérico sea cual sea el límite alcanzado (tarea
    11.3). Cada intento fallido -- incluido uno bloqueado -- se registra en
    `intento_login` (tabla de solo inserción, sin `organizacion_id`); un
    intento exitoso no se registra ahí (`ADR-018`: "un INSERT por intento
    fallido").
    """
    momento = reloj.now()
    desde_ventana = momento - VENTANA_INTENTOS_LOGIN

    if (
        repository.contar_intentos_fallidos_por_ip(sesion, ip=ip, desde=desde_ventana)
        >= LIMITE_INTENTOS_FALLIDOS_POR_IP
    ):
        _registrar_intento_fallido(sesion, usuario_id=None, ip=ip, momento=momento)
        desbloqueo_en = _desbloqueo_por_ip(sesion, ip=ip, desde_ventana=desde_ventana)
        raise LoginBloqueadoPorIntentosError(_mensaje_de_bloqueo(desbloqueo_en))

    organizacion = repository.obtener_organizacion_por_slug(organizacion_slug, sesion)
    usuario = (
        repository.obtener_usuario_por_nombre_usuario(organizacion.id, nombre_usuario, sesion)
        if organizacion is not None
        else None
    )

    if usuario is not None and (
        repository.contar_intentos_fallidos_por_usuario(
            sesion, usuario_id=usuario.id, desde=desde_ventana
        )
        >= LIMITE_INTENTOS_FALLIDOS_POR_USUARIO
    ):
        _registrar_intento_fallido(sesion, usuario_id=usuario.id, ip=ip, momento=momento)
        assert organizacion is not None  # si hay usuario, hay organización que lo resolvió.
        registrar_auditoria(
            organizacion.id,
            sesion,
            reloj,
            accion="LOGIN_BLOQUEADO_POR_INTENTOS",
            entidad="usuario",
            entidad_id=usuario.id,
            ocurrido_en=momento,
            usuario_id=usuario.id,
        )
        desbloqueo_en = _desbloqueo_por_usuario(
            sesion, usuario_id=usuario.id, desde_ventana=desde_ventana
        )
        raise LoginBloqueadoPorIntentosError(_mensaje_de_bloqueo(desbloqueo_en))

    if organizacion is None:
        _registrar_intento_fallido(sesion, usuario_id=None, ip=ip, momento=momento)
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")

    credenciales_validas = (
        usuario is not None
        and usuario.estado == "ACTIVO"
        and verificar_password(password, usuario.password_hash)
    )
    if not credenciales_validas:
        _registrar_intento_fallido(
            sesion,
            usuario_id=usuario.id if usuario is not None else None,
            ip=ip,
            momento=momento,
        )
        registrar_auditoria(
            organizacion.id,
            sesion,
            reloj,
            accion="INICIO_SESION_FALLIDO",
            entidad="usuario",
            entidad_id=usuario.id if usuario is not None else None,
            ocurrido_en=momento,
            usuario_id=usuario.id if usuario is not None else None,
        )
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")
    assert usuario is not None  # para mypy: ya lo verificó `credenciales_validas`.

    if dispositivo_id is None:
        _registrar_intento_fallido(sesion, usuario_id=usuario.id, ip=ip, momento=momento)
        registrar_auditoria(
            organizacion.id,
            sesion,
            reloj,
            accion="INICIO_SESION_FALLIDO",
            entidad="usuario",
            entidad_id=usuario.id,
            ocurrido_en=momento,
            usuario_id=usuario.id,
        )
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")

    dispositivo_existente = repository.obtener_dispositivo_por_id(
        organizacion.id, dispositivo_id, sesion
    )
    if dispositivo_existente is not None and dispositivo_existente.estado == "REVOCADO":
        _registrar_intento_fallido(sesion, usuario_id=usuario.id, ip=ip, momento=momento)
        registrar_auditoria(
            organizacion.id,
            sesion,
            reloj,
            accion="INICIO_SESION_FALLIDO",
            entidad="usuario",
            entidad_id=usuario.id,
            ocurrido_en=momento,
            usuario_id=usuario.id,
            dispositivo_id=dispositivo_id,
        )
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")

    dispositivo = registrar_o_reutilizar_dispositivo(
        organizacion.id,
        sesion,
        reloj,
        dispositivo_id=dispositivo_id,
        nombre=nombre_dispositivo,
    )

    access_token = emitir_access_token(
        usuario_id=usuario.id,
        organizacion_id=organizacion.id,
        dispositivo_id=dispositivo.id,
        secreto=jwt_secreto,
        kid=jwt_kid,
        emitido_en=momento,
    )
    refresh_token_claro = generar_refresh_token()
    repository.crear_sesion_refresh(
        organizacion.id,
        sesion,
        sesion_refresh_id=nuevo_id(),
        usuario_id=usuario.id,
        dispositivo_id=dispositivo.id,
        token_hash=derivar_hash_refresh_token(refresh_token_claro),
        familia_id=nuevo_id(),
        emitido_en=momento,
        expira_en=momento + timedelta(days=REFRESH_TOKEN_TTL_DIAS),
    )

    registrar_auditoria(
        organizacion.id,
        sesion,
        reloj,
        accion="INICIO_SESION",
        entidad="usuario",
        entidad_id=usuario.id,
        ocurrido_en=momento,
        usuario_id=usuario.id,
        dispositivo_id=dispositivo.id,
    )

    return ResultadoLogin(
        access_token=access_token,
        refresh_token=refresh_token_claro,
        usuario_id=usuario.id,
        organizacion_id=organizacion.id,
        dispositivo_id=dispositivo.id,
    )


# --- Renovación y cierre de sesión: tareas 8.5-8.8 (`ADR-017`) -------------


def renovar_sesion(
    sesion: Session,
    reloj: Clock,
    *,
    refresh_token_claro: str,
    dispositivo_id: UUID,
    jwt_secreto: str,
    jwt_kid: str,
) -> ResultadoLogin:
    """Rota el refresh token (tarea 8.5): emite un par nuevo, marca el
    anterior como usado, renueva el vencimiento a 30 días desde la
    rotación (deslizante, ADR-017).

    Detecta reuso (tarea 8.6): si el token presentado ya estaba marcado
    como usado, revoca TODA su familia (todas las rotaciones que salieron
    de un mismo login), audita el motivo, y rechaza -- sin afectar la
    familia de otro dispositivo del mismo usuario, porque cada login tiene
    la suya.

    Rechaza (tarea 8.7, mismo `RefreshTokenInvalidoError`): token
    inexistente, de otro dispositivo, vencido, o de una sesión ya cerrada
    (`revocado_en` no nulo sin ser un reuso -- logout o revocación de
    dispositivo)."""
    momento = reloj.now()
    hash_presentado = derivar_hash_refresh_token(refresh_token_claro)
    fila = repository.obtener_sesion_refresh_por_token_hash_global(hash_presentado, sesion)

    if fila is None or fila.dispositivo_id != dispositivo_id:
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    if fila.usado_en is not None and fila.revocado_en is None:
        # Reuso: un token que YA se había rotado (usado_en seteado) vuelve
        # a presentarse. Corta toda la familia antes de rechazar.
        repository.revocar_familia_refresh(
            fila.organizacion_id,
            sesion,
            familia_id=fila.familia_id,
            momento=momento,
            motivo="REUSO_DETECTADO",
        )
        registrar_auditoria(
            fila.organizacion_id,
            sesion,
            reloj,
            accion="REVOCAR_FAMILIA_REFRESH",
            entidad="usuario",
            entidad_id=fila.usuario_id,
            ocurrido_en=momento,
            usuario_id=fila.usuario_id,
            dispositivo_id=fila.dispositivo_id,
            observacion="Reuso de refresh token detectado: familia revocada.",
        )
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    if fila.revocado_en is not None:
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    if fila.expira_en <= momento:
        raise RefreshTokenInvalidoError("El refresh token venció.")

    fila.usado_en = momento
    sesion.flush()

    refresh_token_nuevo_claro = generar_refresh_token()
    repository.crear_sesion_refresh(
        fila.organizacion_id,
        sesion,
        sesion_refresh_id=nuevo_id(),
        usuario_id=fila.usuario_id,
        dispositivo_id=fila.dispositivo_id,
        token_hash=derivar_hash_refresh_token(refresh_token_nuevo_claro),
        familia_id=fila.familia_id,
        emitido_en=momento,
        expira_en=momento + timedelta(days=REFRESH_TOKEN_TTL_DIAS),
    )
    access_token = emitir_access_token(
        usuario_id=fila.usuario_id,
        organizacion_id=fila.organizacion_id,
        dispositivo_id=fila.dispositivo_id,
        secreto=jwt_secreto,
        kid=jwt_kid,
        emitido_en=momento,
    )

    return ResultadoLogin(
        access_token=access_token,
        refresh_token=refresh_token_nuevo_claro,
        usuario_id=fila.usuario_id,
        organizacion_id=fila.organizacion_id,
        dispositivo_id=fila.dispositivo_id,
    )


def cerrar_sesion(sesion: Session, reloj: Clock, *, refresh_token_claro: str | None) -> None:
    """Cierra sesión (tarea 8.8): revoca el refresh token vigente. Sin
    cookie de refresh, o con una que ya no corresponde a nada, responde
    igual (sin fallar, sin revelar si había una sesión, `02` §18)."""
    if refresh_token_claro is None:
        return
    hash_presentado = derivar_hash_refresh_token(refresh_token_claro)
    fila = repository.obtener_sesion_refresh_por_token_hash_global(hash_presentado, sesion)
    if fila is None or fila.revocado_en is not None:
        return
    fila.revocado_en = reloj.now()
    fila.motivo_revocacion = "LOGOUT"
    sesion.flush()


def listar_permisos_del_usuario(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> frozenset[str]:
    """Permisos vigentes de `usuario_id`, tomados de su rol, sin caché
    (`design.md` D5, tarea 10.2). Único punto de lectura de permisos: la
    dependencia de permisos de `core/autenticacion.py` llama acá, nunca al
    repositorio directamente (`CLAUDE.md` §4: un módulo se usa solo a
    través de su `service.py`). Devuelve conjunto vacío si el usuario no
    existe en esa organización (INV-21): nunca lanza."""
    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return frozenset()
    return frozenset(repository.listar_permisos_de_rol(organizacion_id, usuario.rol_id, sesion))
