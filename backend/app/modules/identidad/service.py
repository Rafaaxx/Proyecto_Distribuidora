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
    AccessTokenInvalidoError,
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
    CondicionIvaSinCambioError,
    computa_credito_fiscal,
    validar_compatibilidad_de_condicion,
    validar_condicion_iva,
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

    condicion_iva: str
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
    validar_condicion_iva(configuracion.condicion_iva)
    validar_modo_impositivo(configuracion.modo_impositivo)
    validar_compatibilidad_de_condicion(
        configuracion.condicion_iva,
        configuracion.modo_impositivo,
        configuracion.modalidad_iva_default,
    )
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
        condicion_iva=configuracion.condicion_iva,
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


def obtener_condicion_iva(
    organizacion_id: UUID, sesion: Session, *, para_compartir: bool = False
) -> str | None:
    """Condición frente al IVA de `organizacion_id` (11b, D1), o `None` si la
    organización no tiene configuración. Con `para_compartir`, la lee `FOR SHARE`: un
    registro de costo o compra y el cambio de condición (`FOR UPDATE`) no se cruzan, así
    que una compra usa una sola regla de punta a punta (D3). `proveedores` e `importacion`
    leen la condición solo por acá (import-linter)."""
    if para_compartir:
        configuracion = repository.obtener_configuracion_bloqueada(
            organizacion_id, sesion, exclusivo=False
        )
    else:
        configuracion = repository.obtener_configuracion(organizacion_id, sesion)
    return None if configuracion is None else configuracion.condicion_iva


def organizacion_computa_credito_fiscal(
    organizacion_id: UUID, sesion: Session, *, para_compartir: bool = False
) -> bool | None:
    """CST-06: si `organizacion_id` computa crédito fiscal de IVA en compras (solo un
    responsable inscripto), o `None` si la organización no tiene configuración. Es la
    única forma en que `proveedores` e `importacion` conocen la regla (`design.md` D1)."""
    condicion = obtener_condicion_iva(organizacion_id, sesion, para_compartir=para_compartir)
    return None if condicion is None else computa_credito_fiscal(condicion)


def cambiar_condicion_iva(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    condicion_nueva: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> ConfiguracionOrganizacion | None:
    """`ORGANIZACION_CONDICION_IVA_CAMBIAR` (11b, D7, CST-06): cambia la condición frente
    al IVA de la organización. Sin efecto retroactivo: no toca ningún costo, compra ni
    promedio ya registrado (TR-06); rige para lo que se registre después.

    Toma la fila de configuración `FOR UPDATE`: `COSTO_INFORMAR` y `COMPRA_CONFIRMAR` la leen
    `FOR SHARE`, así que un registro en curso termina con la regla anterior y el siguiente ve
    la nueva, sin interbloqueo (la configuración es lo único que este cambio bloquea).

    `CONDICION_IVA_SIN_CAMBIO` si el valor es el mismo; `MODO_IMPOSITIVO_INCOMPATIBLE` si se
    pasa a no inscripta con modo distinto de `A` o con modalidad de IVA definida (D2). Escribe
    UNA auditoría con el valor anterior y el nuevo (`origen='COMANDO'`, `operation_id` del
    sobre); la fila genérica del comando la deja el bus (ADR-022, mismo patrón que
    `clientes/service.py::modificar_credito`). Devuelve `None` si la organización no tiene
    configuración. Sin `commit`: la transacción la gestiona el bus."""
    validar_condicion_iva(condicion_nueva)
    configuracion = repository.obtener_configuracion_bloqueada(
        organizacion_id, sesion, exclusivo=True
    )
    if configuracion is None:
        return None

    condicion_anterior = configuracion.condicion_iva
    if condicion_nueva == condicion_anterior:
        raise CondicionIvaSinCambioError(
            f"La organización ya tiene la condición frente al IVA {condicion_nueva}."
        )
    validar_compatibilidad_de_condicion(
        condicion_nueva, configuracion.modo_impositivo, configuracion.modalidad_iva_default
    )

    momento = reloj.now()
    actualizada = repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=momento,
        actualizado_por_id=actor_id,
        condicion_iva=condicion_nueva,
    )
    assert actualizada is not None  # la fila existe: se acaba de bloquear.

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ORGANIZACION_CONDICION_IVA_CAMBIAR",
        entidad="configuracion_organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"condicion_iva": condicion_anterior},
        despues={"condicion_iva": condicion_nueva},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return actualizada


def configurar_consumidor_final(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cliente_consumidor_final_id: UUID,
    actor_id: UUID | None = None,
) -> ConfiguracionOrganizacion | None:
    """Setter de `permite_consumidor_final` y `cliente_consumidor_final_id`
    (change 07, tarea 2.3, `design.md` D4, ADR-029).

    Existe como setter acá y no en `clientes/service.py` porque la fila es de
    este módulo: `clientes` alcanza a `identidad` solo por su `service.py`
    (contrato de import-linter, el mismo que ya existe para `configuracion`).

    Los dos campos se escriben juntos porque `03` §4 los declara como un par:
    `permite_consumidor_final` en `true` sin `cliente_consumidor_final_id`
    apuntaría a nada, y un identificador sin el permiso en `true` no
    significaría nada para el bootstrap del change 21 (SYN-11).

    Devuelve `None` sin tocar nada si la organización no tiene fila de
    configuración: es el mismo criterio que `obtener_configuracion` y que
    `repository.actualizar_configuracion`, que nunca buscan la fila de otra
    organización. Sin `commit`: la transacción la gestiona quien llama -- el bus
    de comandos, que comparte la transacción con la creación del cliente
    (`design.md` D4: no existe estado intermedio)."""
    return repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
        permite_consumidor_final=True,
        cliente_consumidor_final_id=cliente_consumidor_final_id,
    )


def definir_lista_precio_default(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_precio_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> UUID | None:
    """`LISTA_PRECIO_PREDETERMINADA_DEFINIR` (change 13, D11 punto 2): escribe
    `configuracion_organizacion.lista_precio_default_id` y devuelve el valor ANTERIOR.

    Existe como setter acá porque la fila es de este módulo (`precios` la alcanza solo por
    `identidad/service.py`). Que la lista exista en la organización y esté activa lo valida
    quien llama (`precios`), con el candado de la lista (D14); la clave foránea compuesta de la
    base es la garantía final. Toma la fila de configuración `FOR UPDATE` para que el `antes`
    de la auditoría sea el valor anterior real (mismo criterio que `cambiar_condicion_iva`).
    Escribe UNA auditoría con el valor anterior y el nuevo (AUD-01, `origen='COMANDO'`,
    `operation_id` del sobre); la fila genérica del comando la deja el bus. No toca ninguna
    versión de lista ni la lista asignada de ningún cliente. Sin `commit`.

    Una organización sin fila de configuración es un error de datos: se falla en voz alta."""
    configuracion = repository.obtener_configuracion_bloqueada(
        organizacion_id, sesion, exclusivo=True
    )
    if configuracion is None:
        raise RuntimeError(
            f"La organización {organizacion_id} no tiene configuración: no se puede definir "
            "su lista de precios predeterminada."
        )
    anterior = configuracion.lista_precio_default_id
    momento = reloj.now()
    repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=momento,
        actualizado_por_id=actor_id,
        lista_precio_default_id=lista_precio_id,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="LISTA_PRECIO_PREDETERMINADA_DEFINIR",
        entidad="configuracion_organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"lista_precio_default_id": None if anterior is None else str(anterior)},
        despues={"lista_precio_default_id": str(lista_precio_id)},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return anterior


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
    origen: str = "SISTEMA",
) -> Auditoria:
    """Registra un evento de auditoría (AUD-02, tarea 8.1).

    `occurred_at` es `ocurrido_en` (el momento del evento, informado por
    quien llama); `registered_at` es `reloj.now()` (el momento del
    servidor al escribir, TR-05). Sin `commit`: la transacción la gestiona
    quien llama (`02` §5.2) -- si esa transacción se revierte, este
    registro se revierte con ella (INV-01, tarea 8.2).

    `antes`/`despues` quedan `None` si no se pasan: nunca se inventa un
    diccionario vacío para un evento sin cambio de valor.

    `origen` (change 04, tarea 10.5, D2): `'COMANDO'` (con `operation_id`)
    para lo que sale del bus de comandos, `'SISTEMA'` (sin `operation_id`)
    para todo lo demás. Login y refresh (`iniciar_sesion`/`renovar_sesion`,
    más abajo) lo declaran explícito; el default queda para el resto de
    las escrituras de este módulo que todavía no pasan por el bus
    (`design.md` D6).
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
        origen=origen,
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
    auditar: bool = True,
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
    if auditar:
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
    auditar: bool = True,
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

    if auditar:
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


def obtener_dispositivo(
    organizacion_id: UUID, sesion: Session, dispositivo_id: UUID
) -> Dispositivo | None:
    """Lectura pública de un dispositivo por su clave compuesta (change 04,
    grupo 8, tarea 8.7): `sync/service.py` la usa para saber si el
    dispositivo que envía un lote está `REVOCADO` (SYN-06), sin importar el
    modelo ni el repositorio de `identidad` directamente (`CLAUDE.md` §4,
    contrato `sync-solo-service`)."""
    return repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)


def revocar_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    dispositivo_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None = None,
    auditar: bool = True,
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
    if auditar:
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
    auditar: bool = True,
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

    if auditar:
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
    auditar: bool = True,
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
    if auditar:
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
            origen="SISTEMA",
            usuario_id=usuario.id,
        )
        desbloqueo_en = _desbloqueo_por_usuario(
            sesion, usuario_id=usuario.id, desde_ventana=desde_ventana
        )
        raise LoginBloqueadoPorIntentosError(_mensaje_de_bloqueo(desbloqueo_en))

    if organizacion is None:
        _registrar_intento_fallido(sesion, usuario_id=None, ip=ip, momento=momento)
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")

    rol_del_usuario = (
        repository.obtener_rol_por_id(organizacion.id, usuario.rol_id, sesion)
        if usuario is not None
        else None
    )
    credenciales_validas = (
        usuario is not None
        and usuario.estado == "ACTIVO"
        # ADR-028 D9.1 último punto: un rol con `activo = false` se suma al
        # mismo rechazo genérico que un usuario inactivo (mismo criterio de
        # `01` §19: "los roles son plantillas" de la organización, nunca
        # `None` para un usuario ya creado -- pero se verifica `is not None`
        # de todos modos, defensa en profundidad en vez de asumir la FK).
        and rol_del_usuario is not None
        and rol_del_usuario.activo
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
            origen="SISTEMA",
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
            origen="SISTEMA",
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
            origen="SISTEMA",
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
        origen="SISTEMA",
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
            origen="SISTEMA",
        )
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    if fila.revocado_en is not None:
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    if fila.expira_en <= momento:
        raise RefreshTokenInvalidoError("El refresh token venció.")

    # ADR-028 D9.3-B (grupo 2 del change 06b): sin jornadas todavía (change
    # 15), la excepción de D9.3-B no puede cumplirse -- se comporta igual
    # que un corte total (D9.3-A). Verificación DESPUÉS de validar el token
    # (reuso, revocación, vencimiento ya quedaron descartados arriba): si el
    # usuario o su rol dejaron de estar activos, se revocan TODAS las
    # familias de refresh del usuario (no solo la de este dispositivo,
    # simétrico a `revocar_dispositivo`) y se audita antes de rechazar.
    usuario_con_rol = repository.obtener_usuario_con_rol(
        fila.organizacion_id, fila.usuario_id, sesion
    )
    motivo_sesion_deshabilitada = (
        "USUARIO_INACTIVO"
        if usuario_con_rol is None
        else _motivo_sesion_deshabilitada(*usuario_con_rol)
    )
    if motivo_sesion_deshabilitada is not None:
        repository.revocar_sesiones_refresh_de_usuario(
            fila.organizacion_id,
            sesion,
            usuario_id=fila.usuario_id,
            momento=momento,
            motivo=motivo_sesion_deshabilitada,
        )
        registrar_auditoria(
            fila.organizacion_id,
            sesion,
            reloj,
            accion="REVOCAR_SESIONES_REFRESH_USUARIO",
            entidad="usuario",
            entidad_id=fila.usuario_id,
            ocurrido_en=momento,
            usuario_id=fila.usuario_id,
            dispositivo_id=fila.dispositivo_id,
            observacion=(
                f"Sesión deshabilitada ({motivo_sesion_deshabilitada}): "
                "se revocan sus familias de refresh (ADR-028)."
            ),
            origen="SISTEMA",
        )
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

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


# --- Sesión con usuario y rol activos (grupo 2, D9, ADR-028) ---------------


def _motivo_sesion_deshabilitada(usuario: Usuario, rol: Rol) -> str | None:
    """ADR-028 D9.1/D9.4-A: motivo por el que la sesión de `usuario` (con su
    `rol`) no está habilitada, o `None` si ambos están activos. Un usuario
    `INACTIVO` se distingue de un rol con `activo = false` solo para el
    `motivo_revocacion` que audita `renovar_sesion` (texto libre, sin
    catálogo) -- el código de error que ve el cliente es siempre el mismo
    (D9.2-A, SEG-06: nunca revela la causa)."""
    if usuario.estado != "ACTIVO":
        return "USUARIO_INACTIVO"
    if not rol.activo:
        return "ROL_INACTIVO"
    return None


def exigir_sesion_habilitada(organizacion_id: UUID, usuario_id: UUID, sesion: Session) -> None:
    """ADR-028 D9.1 ("Punto técnico de implementación" de `design.md` D9):
    rechaza con `AccessTokenInvalidoError` (401 `IDENTIDAD_ACCESS_TOKEN_
    INVALIDO`, D9.2-A) si `usuario_id` no existe en `organizacion_id`, está
    `INACTIVO`, o su rol tiene `activo = false` (D9.4-A). Falla cerrada:
    nunca distingue el motivo en la excepción (SEG-06). La usan
    `requiere_permiso` (`core/autenticacion.py`, antes de leer los
    permisos) y `obtener_yo` (grupo 3); `renovar_sesion` (más abajo) no la
    llama directo porque necesita el motivo para auditar la revocación de
    las familias de refresh, y su propio 401 es `RefreshTokenInvalidoError`
    (D9.2-A), no este."""
    usuario_con_rol = repository.obtener_usuario_con_rol(organizacion_id, usuario_id, sesion)
    if usuario_con_rol is None:
        raise AccessTokenInvalidoError("El usuario del token no existe.")
    usuario, rol = usuario_con_rol
    if _motivo_sesion_deshabilitada(usuario, rol) is not None:
        raise AccessTokenInvalidoError("La sesión no está habilitada.")


def listar_permisos_del_usuario(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> frozenset[str]:
    """Permisos vigentes de `usuario_id`, tomados de su rol, sin caché
    (`design.md` D5, tarea 10.2). Único punto de lectura de permisos: la
    dependencia de permisos de `core/autenticacion.py` llama acá, nunca al
    repositorio directamente (`CLAUDE.md` §4: un módulo se usa solo a
    través de su `service.py`). Devuelve conjunto vacío si el usuario no
    existe en esa organización (INV-21), está `INACTIVO`, o su rol tiene
    `activo = false` (ADR-028 D9.1: falla cerrada, defensa en profundidad
    para cualquier consumidor futuro que no llame a
    `exigir_sesion_habilitada`): nunca lanza."""
    usuario_con_rol = repository.obtener_usuario_con_rol(organizacion_id, usuario_id, sesion)
    if usuario_con_rol is None:
        return frozenset()
    usuario, rol = usuario_con_rol
    if _motivo_sesion_deshabilitada(usuario, rol) is not None:
        return frozenset()
    return frozenset(repository.listar_permisos_de_rol(organizacion_id, usuario.rol_id, sesion))


# --- `GET /api/v1/yo` (grupo 3, D1) ----------------------------------------


@dataclass(frozen=True)
class UsuarioYo:
    id: UUID
    nombre: str


@dataclass(frozen=True)
class OrganizacionYo:
    id: UUID
    nombre: str


@dataclass(frozen=True)
class RolYo:
    id: UUID
    nombre: str


@dataclass(frozen=True)
class DatosYo:
    """Forma exacta del contrato de `GET /api/v1/yo` (`design.md`, "Contrato
    de `GET /api/v1/yo`"): usuario, organización y rol (id y nombre), más
    los permisos vigentes en orden alfabético ascendente."""

    usuario: UsuarioYo
    organizacion: OrganizacionYo
    rol: RolYo
    permisos: list[str]


def obtener_yo(organizacion_id: UUID, usuario_id: UUID, sesion: Session) -> DatosYo:
    """Datos de la propia sesión para `GET /api/v1/yo` (D1, ADR-027).

    Exige la sesión habilitada (`exigir_sesion_habilitada`, ADR-028 D9)
    antes de leer nada: un usuario `INACTIVO`, un rol inactivo, o un
    usuario inexistente en `organizacion_id`, rechazan con
    `AccessTokenInvalidoError` (401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO`) y
    nunca llegan a devolver datos parciales.

    Los permisos salen **solo** de `listar_permisos_del_usuario` (nunca del
    repositorio directo), para que lo que informa esta función coincida,
    por construcción, con lo que autoriza el servidor (ADR-027)."""
    exigir_sesion_habilitada(organizacion_id, usuario_id, sesion)

    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        raise AccessTokenInvalidoError("El usuario del token no existe.")

    organizacion = repository.obtener_organizacion_por_id(organizacion_id, sesion)
    if organizacion is None:
        raise AccessTokenInvalidoError("La organización del token no existe.")

    rol = repository.obtener_rol_por_id(organizacion_id, usuario.rol_id, sesion)
    if rol is None:
        raise AccessTokenInvalidoError("El rol del usuario del token no existe.")

    permisos = sorted(listar_permisos_del_usuario(organizacion_id, usuario_id, sesion))

    return DatosYo(
        usuario=UsuarioYo(id=usuario.id, nombre=usuario.nombre),
        organizacion=OrganizacionYo(id=organizacion.id, nombre=organizacion.nombre),
        rol=RolYo(id=rol.id, nombre=rol.nombre),
        permisos=permisos,
    )


def obtener_nombres_de_usuarios(
    organizacion_id: UUID, usuario_ids: set[UUID] | frozenset[UUID], sesion: Session
) -> dict[UUID, str]:
    """Nombre para mostrar de cada `usuario_id` (`Usuario.nombre`), por
    lote (change 06, tarea 14.4, `contrato-api.md` P4 enmendado): quien
    necesita mostrar "quién registró" un dato (por ejemplo, `proveedores`
    en el historial de costos informados) no importa `identidad.models` ni
    `identidad.repository` (`CLAUDE.md` §4) -- pasa por este único punto,
    que resuelve todos los ids pedidos en una sola consulta en vez de una
    por id (evita N+1). Un id que no pertenece a `organizacion_id`
    (INV-21) o que no existe simplemente no aparece en el resultado."""
    usuarios = repository.listar_usuarios_por_ids(organizacion_id, frozenset(usuario_ids), sesion)
    return {usuario.id: usuario.nombre for usuario in usuarios}
