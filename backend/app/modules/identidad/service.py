"""Interfaz pública de `identidad` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone la lectura de organización y configuración, y el alta de una
organización con su configuración en una sola operación. Sin `commit`: la
transacción la gestiona quien llama (`docs/02-arquitectura.md` §5.2); en
este change, la sesión de la siembra o de la prueba, porque todavía no
existe el bus de comandos (change 04).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.core.ids import nuevo_id
from app.core.seguridad import (
    PIN_AUTORIZACION_ITERACIONES_DEFAULT,
    AccessTokenInvalidoError,
    derivar_hash_refresh_token,
    derivar_pin_autorizacion,
    emitir_access_token,
    generar_refresh_token,
    hashear_password,
    verificar_password,
    verificar_password_o_ficticio,
    verificar_pin_autorizacion,
)
from app.modules.identidad import repository
from app.modules.identidad.domain.clave_intento import clave_de_intento_login
from app.modules.identidad.domain.nota import normalizar_datos_de_nota
from app.modules.identidad.domain.organizacion import (
    normalizar_cuit_de_organizacion,
    normalizar_nombre_de_organizacion,
)
from app.modules.identidad.domain.permisos import (
    ADMINISTRADOR,
    PERMISOS_DEL_CATALOGO,
    PLANTILLAS_DE_ROL,
)
from app.modules.identidad.domain.usuarios import (
    AutorizadorNoEncontradoError,
    AutorizadorSinPermisoError,
    ContrasenaIncorrectaError,
    CorrelativoNoAvanzaError,
    CredencialesInvalidasError,
    LoginBloqueadoPorIntentosError,
    NombreDeRolDuplicadoError,
    PinBloqueadoError,
    PinIncorrectoError,
    RefreshTokenInvalidoError,
    RolConPermisoInexistenteError,
    RolConUsuariosActivosError,
    RolNoEncontradoError,
    RolSinAutorizacionParaPinError,
    TopeDescuentoFueraDeRangoError,
    UsuarioDuplicadoError,
    UsuarioSinRolError,
    debe_borrar_pin,
    normalizar_email,
    normalizar_nombre_de_rol,
    normalizar_nombre_de_usuario,
    queda_administrador,
    rol_confiere_autorizacion_excepcion,
    transicionar_estado_usuario,
    validar_baja_de_usuario,
    validar_contrasena,
    validar_contrasena_nueva,
    validar_formato_pin_autorizacion,
    validar_queda_administrador,
    validar_reactivacion,
    validar_rol_asignable,
    validar_tope_descuento,
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
    validar_tolerancia_offline_de_organizacion,
)
from app.modules.identidad.models import (
    Auditoria,
    ConfiguracionOrganizacion,
    Dispositivo,
    Organizacion,
    Permiso,
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


def configurar_descuento_manual(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    habilitado: bool,
    motivo_obligatorio: bool,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> ConfiguracionOrganizacion | None:
    """`DESCUENTO_MANUAL_CONFIGURAR` (change 18b, D13, DSC-06): fija si la organización habilita
    el descuento manual y si exige motivo. Los dos se escriben juntos y, una vez definido, el
    motivo obligatorio deja de ser nulo. No toca ninguna venta ya confirmada.

    Toma la fila de configuración `FOR UPDATE` para que el `antes` de la auditoría sea el valor
    anterior real (mismo criterio que `cambiar_condicion_iva`). Escribe UNA auditoría con el
    valor anterior y el nuevo (AUD-01, `origen='COMANDO'`, `operation_id` del sobre); la fila
    genérica del comando la deja el bus (ADR-022). Devuelve `None` si la organización no tiene
    configuración. Sin `commit`."""
    configuracion = repository.obtener_configuracion_bloqueada(
        organizacion_id, sesion, exclusivo=True
    )
    if configuracion is None:
        return None

    antes: dict[str, object] = {
        "descuento_manual_habilitado": configuracion.descuento_manual_habilitado,
        "motivo_obligatorio_descuento": configuracion.motivo_obligatorio_descuento,
    }
    momento = reloj.now()
    actualizada = repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=momento,
        actualizado_por_id=actor_id,
        descuento_manual_habilitado=habilitado,
        motivo_obligatorio_descuento=motivo_obligatorio,
    )
    assert actualizada is not None  # la fila existe: se acaba de bloquear.

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="DESCUENTO_MANUAL_CONFIGURAR",
        entidad="configuracion_organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues={
            "descuento_manual_habilitado": habilitado,
            "motivo_obligatorio_descuento": motivo_obligatorio,
        },
        operation_id=operation_id,
        origen="COMANDO",
    )
    return actualizada


def configurar_credito_organizacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    politica: str,
    tolerancia_tipo: str | None,
    tolerancia_valor: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> ConfiguracionOrganizacion | None:
    """`CREDITO_ORGANIZACION_CONFIGURAR` (change 18b, D14, CRE-03, CRE-06): fija la política de
    crédito por defecto y la tolerancia sin conexión de la organización (tipo y valor juntos, o
    los dos vacíos: `TOLERANCIA_OFFLINE_INVALIDA`). Los clientes con política o tolerancia
    propias no cambian: la herencia se resuelve al evaluar el crédito.

    Valida ANTES de bloquear ni escribir. Toma la fila `FOR UPDATE`, escribe UNA auditoría con
    el valor anterior y el nuevo (`origen='COMANDO'`) y devuelve la configuración, o `None` si
    la organización no tiene. Sin `commit`."""
    validar_politica_credito_default(politica)
    tipo, valor = validar_tolerancia_offline_de_organizacion(tolerancia_tipo, tolerancia_valor)

    configuracion = repository.obtener_configuracion_bloqueada(
        organizacion_id, sesion, exclusivo=True
    )
    if configuracion is None:
        return None

    def _importe(importe: Decimal | None) -> str | None:
        return None if importe is None else f"{importe:.2f}"

    antes: dict[str, object] = {
        "politica_credito_default": configuracion.politica_credito_default,
        "tolerancia_offline_tipo": configuracion.tolerancia_offline_tipo,
        "tolerancia_offline_valor": _importe(configuracion.tolerancia_offline_valor),
    }
    momento = reloj.now()
    actualizada = repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=momento,
        actualizado_por_id=actor_id,
        politica_credito_default=politica,
        tolerancia_offline_tipo=tipo,
        tolerancia_offline_valor=valor,
    )
    assert actualizada is not None  # la fila existe: se acaba de bloquear.

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="CREDITO_ORGANIZACION_CONFIGURAR",
        entidad="configuracion_organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues={
            "politica_credito_default": politica,
            "tolerancia_offline_tipo": tipo,
            "tolerancia_offline_valor": _importe(valor),
        },
        operation_id=operation_id,
        origen="COMANDO",
    )
    return actualizada


def configurar_nota_de_venta(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    muestra_saldo: bool,
    domicilio: str | None,
    telefono: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> ConfiguracionOrganizacion | None:
    """`NOTA_VENTA_CONFIGURAR` (change 20, D10, VTA-13): fija si la nota de venta muestra el
    saldo y el domicilio y el teléfono de la organización que se imprimen en ella.

    Normaliza y valida ANTES de bloquear ni escribir (`DATO_DE_NOTA_INVALIDO`). Toma la fila
    `FOR UPDATE`, escribe UNA auditoría con el valor anterior y el nuevo (`origen='COMANDO'`,
    AUD-01) y devuelve la configuración, o `None` si la organización no tiene. Sin `commit`."""
    domicilio_normal, telefono_normal = normalizar_datos_de_nota(domicilio, telefono)

    configuracion = repository.obtener_configuracion_bloqueada(
        organizacion_id, sesion, exclusivo=True
    )
    if configuracion is None:
        return None

    antes: dict[str, object] = {
        "nota_venta_muestra_saldo": configuracion.nota_venta_muestra_saldo,
        "nota_venta_domicilio": configuracion.nota_venta_domicilio,
        "nota_venta_telefono": configuracion.nota_venta_telefono,
    }
    momento = reloj.now()
    actualizada = repository.actualizar_configuracion(
        organizacion_id,
        sesion,
        momento=momento,
        actualizado_por_id=actor_id,
        nota_venta_muestra_saldo=muestra_saldo,
        nota_venta_domicilio=domicilio_normal,
        nota_venta_telefono=telefono_normal,
    )
    assert actualizada is not None  # la fila existe: se acaba de bloquear.

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="NOTA_VENTA_CONFIGURAR",
        entidad="configuracion_organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues={
            "nota_venta_muestra_saldo": muestra_saldo,
            "nota_venta_domicilio": domicilio_normal,
            "nota_venta_telefono": telefono_normal,
        },
        operation_id=operation_id,
        origen="COMANDO",
    )
    return actualizada


def configurar_datos_de_organizacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    cuit: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Organizacion | None:
    """`ORGANIZACION_DATOS_CONFIGURAR` (change 20, D15, VTA-13): fija el nombre y el CUIT de la
    organización.

    Normaliza y valida AMBOS antes de bloquear ni escribir (`NOMBRE_DE_ORGANIZACION_INVALIDO`,
    `CUIT_INVALIDO`): si uno falla no se guarda ninguno. Toma la fila `FOR UPDATE`, escribe UNA
    auditoría con el valor anterior y el nuevo (`origen='COMANDO'`, AUD-01) y devuelve la
    organización, o `None` si no existe. Sin `commit`."""
    nombre_normal = normalizar_nombre_de_organizacion(nombre)
    cuit_normal = normalizar_cuit_de_organizacion(cuit)

    organizacion = repository.obtener_organizacion_bloqueada(organizacion_id, sesion)
    if organizacion is None:
        return None

    antes: dict[str, object] = {"nombre": organizacion.nombre, "cuit": organizacion.cuit}
    momento = reloj.now()
    actualizada = repository.actualizar_datos_de_organizacion(
        organizacion_id, sesion, nombre=nombre_normal, cuit=cuit_normal, momento=momento
    )
    assert actualizada is not None  # la fila existe: se acaba de bloquear.

    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ORGANIZACION_DATOS_CONFIGURAR",
        entidad="organizacion",
        entidad_id=organizacion_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues={"nombre": nombre_normal, "cuit": cuit_normal},
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
    rol = repository.obtener_rol_por_id(organizacion_id, rol_id, sesion)
    if rol is None:
        return None
    # Change 20b, D9: un rol de baja no se asigna, la contraseña cumple la regla común y el nombre
    # de inicio de sesión no se repite en la organización (409 de dominio, no un error de la
    # restricción única). El comando toma antes la exclusión mutua de identidad (D4).
    validar_rol_asignable(rol.activo)
    validar_contrasena(password)
    if repository.obtener_usuario_por_nombre_usuario(organizacion_id, usuario, sesion):
        raise UsuarioDuplicadoError(f"Ya existe un usuario {usuario!r} en la organización.")

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


PERMISO_ADMIN_USUARIOS = "ADMIN_USUARIOS"


def listar_catalogo_de_permisos(sesion: Session) -> list[Permiso]:
    """El catálogo global de permisos (`03` §4) en el orden de `01` §19; un código fuera del
    catálogo del código (no debería haberlo) va al final, por código."""
    orden = {permiso.codigo: posicion for posicion, permiso in enumerate(PERMISOS_DEL_CATALOGO)}
    return sorted(
        repository.listar_permisos(sesion),
        key=lambda fila: (orden.get(fila.codigo, len(orden)), fila.codigo),
    )


def bloquear_organizacion_para_identidad(
    organizacion_id: UUID, sesion: Session, *, actor_id: UUID
) -> None:
    """Exclusión mutua de identidad (change 20b, D4, ADR-053, `02` §7.3): toma
    `configuracion_organizacion FOR UPDATE` y, ya con el bloqueo, revalida que quien ejecuta sigue
    ACTIVO, con rol activo y con `ADMIN_USUARIOS`; si no, `PERMISO_REQUERIDO` (403) sin cambios.

    Orden de bloqueo de toda operación de identidad: configuración -> rol -> usuario ->
    `sesion_refresh`. La toman, primero y antes de leer o escribir nada, `USUARIO_CREAR`,
    `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR` y `ROL_PERMISOS_CAMBIAR` cuando
    quita `ADMIN_USUARIOS`. La revalidación lee la base (no la entidad en caché de la sesión): un
    administrador dado de baja un instante antes ya no completa su comando."""
    repository.obtener_configuracion_bloqueada(organizacion_id, sesion, exclusivo=True)
    if not repository.es_administrador_activo(
        organizacion_id, actor_id, sesion, permiso_codigo=PERMISO_ADMIN_USUARIOS
    ):
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_ADMIN_USUARIOS}.")


def _validar_que_quede_un_administrador(
    organizacion_id: UUID,
    sesion: Session,
    *,
    rol_id: UUID,
    permisos_nuevos: frozenset[str],
    actor_id: UUID,
) -> None:
    """Change 17b, D8, ADR-053: se llama SOLO al quitar `ADMIN_USUARIOS` y ANTES de escribir.
    Toma la exclusión mutua de identidad (D4 del 20b: configuración y revalidación de quien
    ejecuta) para que dos cambios simultáneos sobre roles distintos se serialicen, y recién
    después cuenta en SQL con el conteo general. El rechazo es un error de dominio que el bus
    deshace entero."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    rol = repository.obtener_rol_por_id(organizacion_id, rol_id, sesion)
    assert rol is not None
    validar_queda_administrador(
        administradores_en_otros_roles=repository.contar_administradores(
            organizacion_id,
            sesion,
            permiso_codigo=PERMISO_ADMIN_USUARIOS,
            excluir_rol_id=rol_id,
        ),
        conserva_el_permiso=PERMISO_ADMIN_USUARIOS in permisos_nuevos,
        rol_activo=rol.activo,
        usuarios_activos_del_rol=repository.contar_usuarios_activos_del_rol(
            organizacion_id, rol_id, sesion
        ),
    )


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

    if PERMISO_ADMIN_USUARIOS in permisos_actuales - permisos_nuevos:
        _validar_que_quede_un_administrador(
            organizacion_id,
            sesion,
            rol_id=rol_id,
            permisos_nuevos=permisos_nuevos,
            actor_id=actor_id,
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


def definir_tope_descuento_de_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    tope_nuevo: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Rol | None:
    """`ROL_TOPE_DESCUENTO_DEFINIR` (change 16, D13, DSC-06): fija el tope de descuento manual de
    un rol. Cambia SOLO `rol.tope_descuento`: no toca los permisos del rol, el tope propio de
    ningún usuario ni el PIN.

    El tope llega como cadena y se valida con `validar_tope_descuento` (de 0 a 1) y, además,
    con a lo sumo 6 decimales: un séptimo decimal no se redondea en silencio, se rechaza (TR-02,
    INV-03). Ambos con `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`. Toma el rol `FOR UPDATE` y
    escribe UNA auditoría con el valor anterior y el nuevo (`origen='COMANDO'`, `operation_id`
    del sobre; la fila genérica del comando la deja el bus, ADR-022; mismo patrón que
    `cambiar_condicion_iva`). Devuelve `None` sin escribir nada si el rol no existe en
    `organizacion_id` (INV-21). Sin `commit`: la transacción la gestiona el bus."""
    tope = validar_tope_descuento(tope_nuevo)
    if Decimal(tope_nuevo) != tope:
        raise TopeDescuentoFueraDeRangoError(
            f"El tope de descuento {tope_nuevo} tiene más de 6 decimales."
        )
    rol = repository.obtener_rol_para_actualizar(organizacion_id, rol_id, sesion)
    if rol is None:
        return None

    tope_anterior = rol.tope_descuento
    momento = reloj.now()
    repository.actualizar_tope_de_rol(
        organizacion_id,
        sesion,
        rol,
        tope_descuento=tope,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ROL_TOPE_DESCUENTO_DEFINIR",
        entidad="rol",
        entidad_id=rol_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"tope_descuento": f"{tope_anterior:.6f}"},
        despues={"tope_descuento": f"{tope:.6f}"},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return rol


def listar_permisos_de_un_rol(organizacion_id: UUID, rol_id: UUID, sesion: Session) -> list[str]:
    """Los códigos de permiso del rol (change 20b: el resultado de los comandos de rol)."""
    return list(repository.listar_permisos_de_rol(organizacion_id, rol_id, sesion))


def _tope_de_rol_exacto(tope: str) -> Decimal:
    """Valida el tope como en `definir_tope_descuento_de_rol`: 0 a 1 y a lo sumo seis decimales
    (un séptimo no se redondea en silencio, TR-02, INV-03)."""
    valor = validar_tope_descuento(tope)
    if Decimal(tope) != valor:
        raise TopeDescuentoFueraDeRangoError(
            f"El tope de descuento {tope} tiene más de 6 decimales."
        )
    return valor


def crear_rol_nuevo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    permisos: frozenset[str],
    tope_descuento: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> tuple[Rol, list[str]]:
    """`ROL_CREAR` (change 20b, D10-A; ADR-053). Toma la exclusión mutua de identidad (serializa
    los nombres y revalida a quien ejecuta), valida ANTES de escribir el nombre (1 a 100
    caracteres, recortado, único sin distinguir mayúsculas entre activos y de baja), el tope y que
    cada permiso esté en el catálogo, y crea el rol ACTIVO con sus permisos. Audita `ALTA_ROL`
    (sin estado anterior) con `origen='COMANDO'`. Devuelve el rol y sus permisos ordenados."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    nombre_normalizado = normalizar_nombre_de_rol(nombre)
    tope = _tope_de_rol_exacto(tope_descuento)
    ordenados = sorted(permisos)
    for codigo in ordenados:
        if repository.obtener_permiso_por_codigo(codigo, sesion) is None:
            raise RolConPermisoInexistenteError(
                f"El permiso {codigo!r} no está en el catálogo global (03 §4)."
            )
    if repository.obtener_rol_por_nombre(organizacion_id, nombre_normalizado, sesion):
        raise NombreDeRolDuplicadoError(f"Ya existe un rol {nombre_normalizado!r}.")

    momento = reloj.now()
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre_normalizado,
        tope_descuento=tope,
        activo=True,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    for codigo in ordenados:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="ALTA_ROL",
        entidad="rol",
        entidad_id=rol.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=None,
        despues={
            "nombre": nombre_normalizado,
            "activo": True,
            "tope_descuento": f"{tope:.6f}",
            "permisos": ordenados,
        },
        operation_id=operation_id,
        origen="COMANDO",
    )
    return rol, ordenados


def renombrar_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    nombre: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Rol | None:
    """`ROL_RENOMBRAR` (change 20b, D10-A). Mutex de identidad y rol `FOR UPDATE`; `None` si el
    rol no existe en la organización (INV-21). Mismas reglas de nombre que el alta, sin chocar con
    el propio rol (cambiar solo mayúsculas es válido). El mismo nombre se acepta sin auditoría de
    entidad; si cambia, audita `RENOMBRAR_ROL` con los dos nombres."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    rol = repository.obtener_rol_para_actualizar(organizacion_id, rol_id, sesion)
    if rol is None:
        return None
    nombre_normalizado = normalizar_nombre_de_rol(nombre)
    if repository.obtener_rol_por_nombre(
        organizacion_id, nombre_normalizado, sesion, excluir_rol_id=rol_id
    ):
        raise NombreDeRolDuplicadoError(f"Ya existe un rol {nombre_normalizado!r}.")
    nombre_anterior = rol.nombre
    if nombre_normalizado == nombre_anterior:
        return rol

    momento = reloj.now()
    rol.nombre = nombre_normalizado
    rol.actualizado_en = momento
    rol.actualizado_por_id = actor_id
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="RENOMBRAR_ROL",
        entidad="rol",
        entidad_id=rol_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"nombre": nombre_anterior},
        despues={"nombre": nombre_normalizado},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return rol


def dar_de_baja_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Rol | None:
    """`ROL_BAJA` (change 20b, D11-A, D3, D4; ADR-028 D9.4, ADR-053). En este orden: exclusión
    mutua de identidad y revalidación de quien ejecuta; rol `FOR UPDATE` (`None` si no existe en
    la organización, INV-21); si ya está de baja no cambia nada ni audita; se rechaza si tiene
    usuarios ACTIVO (`IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, con la cantidad); defensa en
    profundidad de D3 (que quede un administrador sin contar este rol); recién entonces
    `activo = false` y la auditoría `BAJA_ROL`. Nunca toca sesiones: un rol sin usuarios activos
    no tiene ninguna."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    rol = repository.obtener_rol_para_actualizar(organizacion_id, rol_id, sesion)
    if rol is None:
        return None
    if not rol.activo:
        return rol
    activos = repository.contar_usuarios_activos_del_rol(organizacion_id, rol_id, sesion)
    if activos > 0:
        raise RolConUsuariosActivosError(
            f"El rol tiene {activos} usuario(s) activo(s); cambiales el rol antes de "
            "darlo de baja.",
            extension={"usuarios_activos": activos},
        )
    queda_administrador(
        repository.contar_administradores(
            organizacion_id,
            sesion,
            permiso_codigo=PERMISO_ADMIN_USUARIOS,
            excluir_rol_id=rol_id,
        )
    )
    _cambiar_actividad_de_rol(
        organizacion_id,
        sesion,
        reloj,
        rol,
        activo=False,
        accion="BAJA_ROL",
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
    return rol


def reactivar_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    rol_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Rol | None:
    """`ROL_REACTIVAR` (change 20b, D11-A, D4). Mutex de identidad y rol `FOR UPDATE`; la
    reactivación es libre (D3 no aplica: suma administradores, no resta). Un rol ya activo no
    cambia ni audita. Audita `REACTIVAR_ROL`."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    rol = repository.obtener_rol_para_actualizar(organizacion_id, rol_id, sesion)
    if rol is None:
        return None
    if rol.activo:
        return rol
    _cambiar_actividad_de_rol(
        organizacion_id,
        sesion,
        reloj,
        rol,
        activo=True,
        accion="REACTIVAR_ROL",
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
    return rol


def _cambiar_actividad_de_rol(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    rol: Rol,
    *,
    activo: bool,
    accion: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> None:
    momento = reloj.now()
    anterior = rol.activo
    rol.activo = activo
    rol.actualizado_en = momento
    rol.actualizado_por_id = actor_id
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion=accion,
        entidad="rol",
        entidad_id=rol.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"activo": anterior},
        despues={"activo": activo},
        operation_id=operation_id,
        origen="COMANDO",
    )


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


# --- Administración de usuarios (change 20b, D1 a D9, D12) ------------------------------------
#
# Cada función corre dentro del bus (`identidad/commands.py`): sin `commit`, con la auditoría de
# entidad propia (`origen = 'COMANDO'` y el `operation_id` del sobre; la fila genérica del comando
# la deja el bus, ADR-022). Devuelven `None` sin escribir nada cuando el recurso no existe en la
# organización (INV-21, SEG-07). Un rechazo es una excepción de dominio que el bus deshace entera.


def _revocar_sesiones_de_usuario_salvo_jornada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    usuario_id: UUID,
    momento: datetime,
    motivo: str,
    conservar_dispositivos: Collection[UUID] = (),
) -> int:
    """Revoca las familias de refresh vigentes del usuario salvo las de los dispositivos con una
    jornada no cerrada de ese usuario (ADR-028 D9.3-B, SYN-05, SYN-10: no se vara su cola) y las
    de `conservar_dispositivos`. Devuelve cuántas filas revocó."""
    con_jornada = [
        dispositivo_id
        for dispositivo_id in repository.dispositivos_con_sesion_vigente(
            organizacion_id, sesion, usuario_id=usuario_id
        )
        if hay_jornada_no_cerrada(organizacion_id, usuario_id, dispositivo_id, sesion)
    ]
    return repository.revocar_sesiones_refresh_de_usuario(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        momento=momento,
        motivo=motivo,
        excepto_dispositivo_ids=[*con_jornada, *conservar_dispositivos],
    )


def _auditar_revocacion_de_sesiones(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    cantidad: int,
    motivo: str,
    momento: datetime,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> None:
    """`REVOCAR_SESIONES_REFRESH_USUARIO` con `origen = 'COMANDO'`, solo si se revocó alguna
    familia (D17): distingue esta revocación de la que hace la renovación (`origen = 'SISTEMA'`)."""
    if cantidad == 0:
        return
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="REVOCAR_SESIONES_REFRESH_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        despues={"familias_revocadas": cantidad, "motivo": motivo},
        operation_id=operation_id,
        origen="COMANDO",
    )


def _borrar_pin_de_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    usuario: Usuario,
    *,
    motivo: str,
    momento: datetime,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> None:
    """Borra el PIN de autorización del usuario (ADR-011) y lo audita sin exponer su valor. No
    hace nada si el usuario no tenía PIN."""
    if usuario.pin_autorizacion_hash is None:
        return
    usuario.pin_autorizacion_hash = None
    usuario.pin_autorizacion_sal = None
    usuario.pin_autorizacion_iteraciones = None
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="INVALIDAR_PIN_AUTORIZACION",
        entidad="usuario",
        entidad_id=usuario.id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        observacion=motivo,
        operation_id=operation_id,
        origen="COMANDO",
    )


def dar_de_baja_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    observacion: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_BAJA` (change 20b, D2-A, D3, D4, D5-A; ADR-028 D9.5, ADR-053). En una
    transacción y en este orden: 1) exclusión mutua de identidad y revalidación de quien ejecuta
    (D4); 2) el rol del usuario y el usuario `FOR UPDATE` (configuración -> rol -> usuario ->
    `sesion_refresh`); 3) validaciones ANTES de escribir (INV-01): autobaja (`IDENTIDAD_AUTOBAJA`),
    transición ACTIVO -> INACTIVO y que quede otro administrador; 4) estado `INACTIVO`; 5) revoca
    las familias de refresh con `USUARIO_INACTIVO` salvo las de dispositivos con jornada no
    cerrada; 6) borra el PIN; 7) auditoría. La cartera y el tope propio se conservan."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    existente = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if existente is None:
        return None
    repository.obtener_rol_para_actualizar(organizacion_id, existente.rol_id, sesion)
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    assert usuario is not None  # se leyó arriba y la exclusión mutua impide que desaparezca.

    validar_baja_de_usuario(actor_id=actor_id, usuario_id=usuario_id, estado=usuario.estado)
    queda_administrador(
        repository.contar_administradores(
            organizacion_id,
            sesion,
            permiso_codigo=PERMISO_ADMIN_USUARIOS,
            excluir_usuario_id=usuario_id,
        )
    )

    momento = reloj.now()
    estado_anterior = usuario.estado
    usuario.estado = transicionar_estado_usuario(estado_anterior, "INACTIVO")
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    revocadas = _revocar_sesiones_de_usuario_salvo_jornada(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        momento=momento,
        motivo="USUARIO_INACTIVO",
    )
    _borrar_pin_de_usuario(
        organizacion_id,
        sesion,
        reloj,
        usuario,
        motivo="El usuario fue dado de baja.",
        momento=momento,
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="BAJA_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"estado": estado_anterior},
        despues={"estado": usuario.estado},
        observacion=(observacion.strip() or None) if observacion is not None else None,
        operation_id=operation_id,
        origen="COMANDO",
    )
    _auditar_revocacion_de_sesiones(
        organizacion_id,
        sesion,
        reloj,
        usuario_id=usuario_id,
        cantidad=revocadas,
        motivo="USUARIO_INACTIVO",
        momento=momento,
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
    return usuario


def reactivar_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_REACTIVAR` (change 20b, D2-A, D4). Solo vuelve el estado a `ACTIVO` y audita
    `REACTIVAR_USUARIO`; no restituye el PIN que borró la baja ni las sesiones. La regla del último
    administrador no aplica (la reactivación suma uno). Toma la exclusión mutua de identidad (un
    alta, una baja o un cambio de rol simultáneos no se cruzan) y el usuario `FOR UPDATE`. Con el
    rol de baja el usuario queda `ACTIVO` y el inicio de sesión se sigue rechazando (ADR-028
    D9.4)."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    existente = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if existente is None:
        return None
    repository.obtener_rol_para_actualizar(organizacion_id, existente.rol_id, sesion)
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    assert usuario is not None  # se leyó arriba y la exclusión mutua impide que desaparezca.

    validar_reactivacion(usuario.estado)
    momento = reloj.now()
    estado_anterior = usuario.estado
    usuario.estado = transicionar_estado_usuario(estado_anterior, "ACTIVO")
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="REACTIVAR_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"estado": estado_anterior},
        despues={"estado": usuario.estado},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return usuario


def modificar_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    nombre: str,
    email: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_MODIFICAR` (change 20b, D9-A): reemplazo completo de `nombre` (obligatorio,
    recortado, hasta 200; 422) y `email` (opcional; vacío es nulo). El nombre de inicio de sesión
    (`usuario`) no se edita. Toma el usuario `FOR UPDATE`. El mismo valor se acepta sin escribir
    ni auditar la entidad; si cambia, una fila `MODIFICAR_USUARIO` con antes y después (AUD-01).
    No toca el estado, el rol ni las sesiones."""
    nombre_nuevo = normalizar_nombre_de_usuario(nombre)
    email_nuevo = normalizar_email(email)
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return None
    antes: dict[str, object] = {"nombre": usuario.nombre, "email": usuario.email}
    despues: dict[str, object] = {"nombre": nombre_nuevo, "email": email_nuevo}
    if antes == despues:
        return usuario

    momento = reloj.now()
    usuario.nombre = nombre_nuevo
    usuario.email = email_nuevo
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="MODIFICAR_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes=antes,
        despues=despues,
        operation_id=operation_id,
        origen="COMANDO",
    )
    return usuario


def cambiar_rol_de_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    rol_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_ROL_CAMBIAR` (change 20b, D7-A, D3, D4, D5-A; ADR-053, ADR-011, ADR-017).

    Exclusión mutua de identidad, los dos roles y el usuario `FOR UPDATE` (en ese orden); rol de
    otra organización o inexistente: `RolNoEncontradoError` (404); rol inactivo: 409
    `IDENTIDAD_ROL_INACTIVO`. El mismo rol se acepta sin cambios ni auditoría de entidad. Antes de
    escribir se cuenta, con el rol nuevo, cuántos administradores quedarían
    (`IDENTIDAD_SIN_ADMINISTRADOR`). Si el rol nuevo no tiene ningún permiso de autorización,
    borra el PIN. No revoca sesiones: los permisos se leen en cada petición. Conserva el tope
    propio y la cartera. Auditoría `CAMBIO_ROL_USUARIO` con el rol anterior y el nuevo."""
    bloquear_organizacion_para_identidad(organizacion_id, sesion, actor_id=actor_id)
    existente = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if existente is None:
        return None
    rol_anterior_id = existente.rol_id
    roles = {}
    for id_de_rol in sorted({rol_anterior_id, rol_id}, key=str):
        encontrado = repository.obtener_rol_para_actualizar(organizacion_id, id_de_rol, sesion)
        if encontrado is None and id_de_rol == rol_id:
            raise RolNoEncontradoError(f"El rol {rol_id} no existe en esta organización.")
        roles[id_de_rol] = encontrado
    rol_nuevo = roles[rol_id]
    rol_anterior = roles[rol_anterior_id]
    assert rol_nuevo is not None and rol_anterior is not None
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    assert usuario is not None  # se leyó arriba y la exclusión mutua impide que desaparezca.
    if usuario.rol_id == rol_id:
        return usuario

    validar_rol_asignable(rol_nuevo.activo)
    queda_administrador(
        repository.contar_administradores(
            organizacion_id,
            sesion,
            permiso_codigo=PERMISO_ADMIN_USUARIOS,
            rol_sustituto=(usuario_id, rol_id),
        )
    )

    momento = reloj.now()
    permisos_del_rol_nuevo = repository.listar_permisos_de_rol(organizacion_id, rol_id, sesion)
    usuario.rol_id = rol_id
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    if debe_borrar_pin(permisos_del_rol_nuevo):
        _borrar_pin_de_usuario(
            organizacion_id,
            sesion,
            reloj,
            usuario,
            motivo="El rol nuevo no confiere ningún permiso de autorización de excepciones.",
            momento=momento,
            actor_id=actor_id,
            dispositivo_id_actor=dispositivo_id_actor,
            operation_id=operation_id,
        )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="CAMBIO_ROL_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"rol_id": str(rol_anterior_id), "rol_nombre": rol_anterior.nombre},
        despues={"rol_id": str(rol_id), "rol_nombre": rol_nuevo.nombre},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return usuario


def restablecer_contrasena_de_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    password_nueva: str,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_CONTRASENA_RESTABLECER` (change 20b, D8-A; ADR-018, ADR-056, ADR-057). La
    contraseña nueva llega como dato efímero (nunca se audita ni se guarda en claro) y se valida
    con la regla común ANTES de escribir o revocar (422, INV-01). Toma el usuario `FOR UPDATE` (no
    se cruza con "Mi contraseña" del mismo usuario). En la misma transacción: deriva el hash,
    revoca las familias de refresh con `CONTRASENA_RESTABLECIDA` salvo las de dispositivos con
    jornada no cerrada, inserta el marcador de desbloqueo (quien la restablece para que el usuario
    pueda entrar no debe encontrarlo bloqueado) y audita `RESTABLECER_CONTRASENA` sin la
    contraseña. No toca el PIN. Vale sobre un usuario inactivo y sobre uno mismo."""
    validar_contrasena(password_nueva)
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return None

    momento = reloj.now()
    usuario.password_hash = hashear_password(password_nueva)
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    revocadas = _revocar_sesiones_de_usuario_salvo_jornada(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        momento=momento,
        motivo="CONTRASENA_RESTABLECIDA",
    )
    _registrar_marcador_de_desbloqueo(organizacion_id, sesion, usuario, momento=momento)
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="RESTABLECER_CONTRASENA",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        despues={"familias_revocadas": revocadas},
        operation_id=operation_id,
        origen="COMANDO",
    )
    _auditar_revocacion_de_sesiones(
        organizacion_id,
        sesion,
        reloj,
        usuario_id=usuario_id,
        cantidad=revocadas,
        motivo="CONTRASENA_RESTABLECIDA",
        momento=momento,
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
    return usuario


def definir_tope_descuento_de_usuario(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    tope_nuevo: str | None,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> Usuario | None:
    """`USUARIO_TOPE_DESCUENTO_DEFINIR` (change 20b, D12-A, DSC-06): fija el tope de descuento
    manual PROPIO del usuario (`null` vuelve a regir el del rol). Misma validación y mismo código
    que el tope del rol: de 0 a 1 y a lo sumo 6 decimales, sin redondear en silencio (TR-02,
    INV-03, `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`). Toma el usuario `FOR UPDATE`. Se permite
    aunque su rol no tenga `DESCUENTO_MANUAL` y puede ser mayor o menor que el del rol. Una fila de
    auditoría `TOPE_DESCUENTO_USUARIO` con el valor anterior y el nuevo (AUD-01); el mismo valor
    se acepta sin auditoría de entidad. Cambia SOLO `tope_descuento_override`."""
    tope: Decimal | None = None
    if tope_nuevo is not None:
        tope = validar_tope_descuento(tope_nuevo)
        if Decimal(tope_nuevo) != tope:
            raise TopeDescuentoFueraDeRangoError(
                f"El tope de descuento {tope_nuevo} tiene más de 6 decimales."
            )
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    if usuario is None:
        return None
    anterior = usuario.tope_descuento_override
    if anterior == tope:
        return usuario

    momento = reloj.now()
    usuario.tope_descuento_override = tope
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = actor_id
    sesion.flush()
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="TOPE_DESCUENTO_USUARIO",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id_actor,
        antes={"tope_descuento_override": None if anterior is None else f"{anterior:.6f}"},
        despues={"tope_descuento_override": None if tope is None else f"{tope:.6f}"},
        operation_id=operation_id,
        origen="COMANDO",
    )
    return usuario


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


@dataclass(frozen=True)
class NumeracionDeDispositivo:
    """El prefijo y el último correlativo de un dispositivo (VTA-06, ADR-008): con ellos el
    cliente propone el número de la próxima venta."""

    prefijo: str
    ultimo_correlativo: int


def obtener_numeracion_de_dispositivo(
    organizacion_id: UUID, sesion: Session, *, dispositivo_id: UUID
) -> NumeracionDeDispositivo | None:
    """La numeración del dispositivo de la sesión (change 18a, D4). `None` si el dispositivo no
    existe en la organización (INV-21). Solo lectura."""
    dispositivo = repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)
    if dispositivo is None:
        return None
    return NumeracionDeDispositivo(
        prefijo=dispositivo.prefijo, ultimo_correlativo=dispositivo.ultimo_correlativo
    )


def registrar_correlativo_maximo(
    organizacion_id: UUID, sesion: Session, *, dispositivo_id: UUID, propuesto: int
) -> int:
    """`ultimo_correlativo = max(actual, propuesto)` del dispositivo (change 18a, D4 y D17
    nivel 6): nunca retrocede y, a diferencia de `avanzar_correlativo_dispositivo`, no exige que
    el propuesto supere al actual (una venta sin conexión más vieja no se rechaza). Devuelve el
    último correlativo resultante. La sentencia toma el candado de la fila del dispositivo, el
    último de la transacción de la venta. Un dispositivo inexistente en la organización es un
    error de programación (la sesión autenticada lo garantiza)."""
    ultimo = repository.avanzar_correlativo_al_maximo(
        organizacion_id, dispositivo_id, propuesto, sesion
    )
    if ultimo is None:
        raise ValueError(f"Dispositivo {dispositivo_id} no encontrado en {organizacion_id}.")
    return ultimo


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
    # D21 punto 7: definir el PIN reinicia los dos contadores de D3 con una fila marcador,
    # en la transacción del comando (si el comando se rechaza o se revierte, no queda).
    repository.registrar_marcador_de_pin(
        organizacion_id,
        sesion,
        intento_id=nuevo_id(),
        autorizador_id=usuario_id,
        momento=momento,
    )

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


# Derivación ficticia contra la que se compara cuando el autorizador no tiene PIN: gasta lo mismo
# que verificar uno real, así el tiempo de respuesta no distingue "sin PIN" de "PIN equivocado".
_SAL_FICTICIA_PIN = "00" * 32
_HASH_FICTICIO_PIN = "00" * 32


# Intentos del PIN de autorización (change 18b, D3 revisada el 2026-10-22, SEG-04, ADR-011).
LIMITE_FALLOS_PIN_POR_AUTORIZADOR = 20
"""Fallos contra el mismo autorizador, sumando todos los usuarios, que bloquean su PIN para
todos. Constante del código, junto a los límites del login: `03` no tiene campo para esto y
`intentos_pin_max` (por par) es el único parámetro de PIN de la organización."""
VENTANA_BLOQUEO_PIN = timedelta(minutes=15)

_MENSAJE_PIN_BLOQUEADO = "Demasiados intentos con el PIN de autorización. Probá más tarde."

logger = logging.getLogger("app.identidad")


def _sesion_aparte(sesion: Session) -> Session:
    """Una sesión nueva sobre el mismo motor, para escribir el contador en una transacción que
    se confirma aunque la del comando se revierta (mismo patrón que `intento_login`)."""
    return Session(bind=sesion.get_bind().engine, autoflush=False, expire_on_commit=False)


def _hasta_del_bloqueo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    autorizador_id: UUID,
    intentante_id: UUID | None,
    limite: int,
    ahora: datetime,
) -> datetime | None:
    """Hasta cuándo rige el bloqueo, o `None` si no hay (`design.md` D3 punto 4): sea F el último
    fallo contado, hay bloqueo si en (F - 15 min, F] hay al menos `limite` fallos y `ahora < F +
    15 min`. Igual para el par (`intentante_id`) y el general (`None`)."""
    ultimo = repository.ultimo_fallo_de_pin(
        organizacion_id, sesion, autorizador_id=autorizador_id, intentante_id=intentante_id
    )
    if ultimo is None:
        return None
    hasta = ultimo + VENTANA_BLOQUEO_PIN
    if ahora >= hasta:
        return None
    cuenta = repository.contar_fallos_de_pin_en_ventana(
        organizacion_id,
        sesion,
        autorizador_id=autorizador_id,
        intentante_id=intentante_id,
        desde_exclusivo=ultimo - VENTANA_BLOQUEO_PIN,
        hasta_inclusivo=ultimo,
    )
    return hasta if cuenta >= limite else None


def _pin_coincide(autorizador: Usuario, pin: str) -> bool:
    """Deriva SIEMPRE una vez (también sin PIN definido) y compara en tiempo constante."""
    tiene_pin = (
        autorizador.pin_autorizacion_hash is not None
        and autorizador.pin_autorizacion_sal is not None
        and autorizador.pin_autorizacion_iteraciones is not None
    )
    if tiene_pin:
        return verificar_pin_autorizacion(
            pin,
            hash_almacenado=autorizador.pin_autorizacion_hash or "",
            sal=autorizador.pin_autorizacion_sal or "",
            iteraciones=autorizador.pin_autorizacion_iteraciones or 0,
        )
    verificar_pin_autorizacion(
        pin,
        hash_almacenado=_HASH_FICTICIO_PIN,
        sal=_SAL_FICTICIA_PIN,
        iteraciones=PIN_AUTORIZACION_ITERACIONES_DEFAULT,
    )
    return False


def verificar_pin_de_autorizacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    autorizador_id: UUID,
    intentante_id: UUID,
    pin: str,
    permiso: str,
    dispositivo_id: UUID | None = None,
) -> Usuario:
    """Verifica `pin` contra la derivación guardada de `autorizador_id` (change 18b, D2, D3
    revisada, SEG-04, SEG-05). Devuelve al autorizador si valida. `intentante_id` es el usuario
    del sobre (quien envía el comando); `dispositivo_id` solo va al log y a la auditoría.

    Orden: 1) `AutorizadorNoEncontradoError` (404) si no existe en la organización (INV-21; no
    cuenta); 2) `AutorizadorSinPermisoError` (403) si le falta `permiso` (no verifica ni cuenta);
    3) `PinBloqueadoError` (429) si rige un bloqueo del par o general, sin verificar, sin contar y
    sin escribir; 4) el PIN. Un PIN equivocado, un autorizador sin PIN, con el PIN invalidado,
    inactivo o con el rol inactivo lanzan el MISMO `PinIncorrectoError` (403), con una derivación
    cada uno, y cuentan como fallo.

    El fallo y la auditoría del bloqueo se escriben en una TRANSACCIÓN APARTE, que se confirma
    aunque la del comando se revierta; con el PIN correcto no se escribe nada. El PIN nunca se
    registra ni se incluye en un mensaje. La sesión recibida nunca se confirma."""
    autorizador = repository.obtener_usuario_por_id(organizacion_id, autorizador_id, sesion)
    if autorizador is None:
        raise AutorizadorNoEncontradoError(
            f"El autorizador {autorizador_id} no existe en esta organización."
        )

    motivo = motivo_de_permiso_faltante(organizacion_id, autorizador_id, permiso, sesion)
    if motivo == "PERMISO_QUITADO":
        raise AutorizadorSinPermisoError(f"El autorizador no tiene el permiso {permiso}.")
    habilitado = motivo is None

    configuracion = repository.obtener_configuracion(organizacion_id, sesion)
    assert configuracion is not None, "toda organización tiene su configuración (02 §3)"
    limite_por_par = configuracion.intentos_pin_max
    ahora = reloj.now()

    aparte = _sesion_aparte(sesion)
    try:
        repository.tomar_candado_de_pin_del_autorizador(
            organizacion_id, aparte, autorizador_id=autorizador_id
        )
        for intentante_del_conteo, limite in (
            (intentante_id, limite_por_par),
            (None, LIMITE_FALLOS_PIN_POR_AUTORIZADOR),
        ):
            hasta = _hasta_del_bloqueo(
                organizacion_id,
                aparte,
                autorizador_id=autorizador_id,
                intentante_id=intentante_del_conteo,
                limite=limite,
                ahora=ahora,
            )
            if hasta is not None:
                logger.warning(
                    "PIN de autorización rechazado por bloqueo: autorizador=%s intentante=%s "
                    "dispositivo=%s",
                    autorizador_id,
                    intentante_id,
                    dispositivo_id,
                )
                raise PinBloqueadoError(_MENSAJE_PIN_BLOQUEADO)

        if _pin_coincide(autorizador, pin) and habilitado:
            return autorizador

        repository.registrar_fallo_de_pin(
            organizacion_id,
            aparte,
            intento_id=nuevo_id(),
            autorizador_id=autorizador_id,
            intentante_id=intentante_id,
            momento=ahora,
        )
        for alcance, intentante_del_conteo, limite in (
            ("USUARIO", intentante_id, limite_por_par),
            ("GENERAL", None, LIMITE_FALLOS_PIN_POR_AUTORIZADOR),
        ):
            cuenta = repository.contar_fallos_de_pin_en_ventana(
                organizacion_id,
                aparte,
                autorizador_id=autorizador_id,
                intentante_id=intentante_del_conteo,
                desde_exclusivo=ahora - VENTANA_BLOQUEO_PIN,
                hasta_inclusivo=ahora,
            )
            if cuenta >= limite:
                registrar_auditoria(
                    organizacion_id,
                    aparte,
                    reloj,
                    accion="PIN_AUTORIZACION_BLOQUEADO",
                    entidad="usuario",
                    entidad_id=autorizador_id,
                    ocurrido_en=ahora,
                    usuario_id=intentante_id,
                    dispositivo_id=dispositivo_id,
                    despues={
                        "alcance": alcance,
                        "intentante_id": str(intentante_id),
                        "hasta": (ahora + VENTANA_BLOQUEO_PIN).isoformat(),
                    },
                )
        aparte.commit()
    finally:
        aparte.close()

    logger.warning(
        "PIN de autorización incorrecto: autorizador=%s intentante=%s dispositivo=%s",
        autorizador_id,
        intentante_id,
        dispositivo_id,
    )
    raise PinIncorrectoError("El PIN de autorización es incorrecto.")


# --- Autenticación (login): tarea 8.3/8.4 (`ADR-021`, `ADR-017`) -----------

REFRESH_TOKEN_TTL_DIAS = 30

# --- Rate limit de login (grupo 11, `ADR-018`) ------------------------------

LIMITE_INTENTOS_FALLIDOS_POR_USUARIO = 5
LIMITE_INTENTOS_FALLIDOS_POR_IP = 20
VENTANA_INTENTOS_LOGIN = timedelta(minutes=15)

ZONA_HORARIA_POR_DEFECTO_DEL_BLOQUEO = "America/Argentina/Buenos_Aires"
"""Zona con la que se dice la hora de desbloqueo cuando no hay una organización que la dé, y
SIEMPRE en el bloqueo por IP del login: ese límite se evalúa antes de resolver la organización o
el usuario, así que el texto no puede depender de si existen (ADR-018 3b)."""


def _mensaje_de_bloqueo(desbloqueo_en: datetime, zona_horaria: str | None) -> str:
    """Mensaje del 429 por intentos (tarea 11.3: no revela si el usuario o la organización
    existen; `ADR-018` pide informar el momento de desbloqueo). Siempre tiene la misma forma: la
    hora como HH:MM (24 h) en la zona dada, o en `ZONA_HORARIA_POR_DEFECTO_DEL_BLOQUEO` si no hay
    zona: "Demasiados intentos. Probá de nuevo a las 23:45." `desbloqueo_en` nunca es `None`:
    todos los llamadores solo lo invocan con un bloqueo vigente."""
    zona = ZoneInfo(zona_horaria or ZONA_HORARIA_POR_DEFECTO_DEL_BLOQUEO)
    return f"Demasiados intentos. Probá de nuevo a las {desbloqueo_en.astimezone(zona):%H:%M}."


def _registrar_intento_fallido(
    sesion: Session, *, clave_intento: str, usuario_id: UUID | None, ip: str, momento: datetime
) -> None:
    repository.registrar_intento_login(
        sesion,
        intento_id=nuevo_id(),
        usuario_id=usuario_id,
        clave_intento=clave_intento,
        ip=ip,
        exito=False,
        momento=momento,
    )


# --- "Mi PIN": PIN_AUTORIZACION_PROPIO_DEFINIR (change 18b, D21 parte B, D24) -------------------


def _hasta_del_bloqueo_de_login(
    sesion: Session,
    *,
    clave_intento: str | None,
    ip: str | None,
    ahora: datetime,
) -> datetime | None:
    """Hasta cuándo rige el bloqueo del login, o `None` (D24 punto 1, igual a la regla del PIN de
    D3): para cada límite pedido (por par escrito 5, por IP 20), sea F el último fallo contado,
    hay bloqueo si en (F - 15 min, F] hay al menos el límite y `ahora < F + 15 min`. Devuelve el
    desbloqueo más tardío de los límites que rigen. El límite por par cuenta por `clave_intento`
    (ADR-057: el par (slug, usuario) tal como se escribió, exista o no); con `clave_intento=None`
    solo se evalúa la IP, y con `ip=None` solo el par."""
    bloqueos: list[datetime] = []
    sujetos: list[tuple[str | None, str | None, int]] = []
    if clave_intento is not None:
        sujetos.append((clave_intento, None, LIMITE_INTENTOS_FALLIDOS_POR_USUARIO))
    if ip is not None:
        sujetos.append((None, ip, LIMITE_INTENTOS_FALLIDOS_POR_IP))
    for por_clave, por_ip, limite in sujetos:
        ultimo = repository.ultimo_fallo_de_login(sesion, clave_intento=por_clave, ip=por_ip)
        if ultimo is None or ahora >= ultimo + VENTANA_INTENTOS_LOGIN:
            continue
        cuenta = repository.contar_fallos_de_login_en_ventana(
            sesion,
            clave_intento=por_clave,
            ip=por_ip,
            desde_exclusivo=ultimo - VENTANA_INTENTOS_LOGIN,
            hasta_inclusivo=ultimo,
        )
        if cuenta >= limite:
            bloqueos.append(ultimo + VENTANA_INTENTOS_LOGIN)
    return max(bloqueos) if bloqueos else None


def _exigir_contrasena_actual(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario: Usuario,
    password_actual: str,
    ip: str,
    dispositivo_id: UUID | None,
    funcionalidad: str,
) -> None:
    """Reautenticación con la contraseña actual, con el límite del login (D24 del 18b, ADR-018,
    ADR-057): la comparten "Mi PIN" y "Mi contraseña" (change 20b, D20).

    Orden: 1) bloqueo de login (usuario 5 y IP 20, 15 minutos desde el último fallo): 429
    `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, también con la contraseña correcta, sin verificar,
    sin contar y sin escribir; 2) `verificar_password` contra el hash del usuario: si es incorrecta
    se anota un intento fallido en `intento_login` en una TRANSACCIÓN APARTE (se confirma aunque
    el comando se rechace) y se lanza `ContrasenaIncorrectaError` (403). La contraseña nunca se
    registra ni se incluye en un mensaje. `funcionalidad` solo identifica el origen en el log."""
    ahora = reloj.now()
    organizacion = repository.obtener_organizacion_por_id(organizacion_id, sesion)
    assert organizacion is not None  # el usuario existe: su organización también.
    # ADR-057 punto 5: la funcionalidad cuenta con el par guardado del propio usuario, que es
    # exactamente lo que escribe en el login: todos comparten el mismo cupo de 5.
    clave = clave_de_intento_login(organizacion.slug, usuario.usuario)

    desbloqueo = _hasta_del_bloqueo_de_login(sesion, clave_intento=clave, ip=ip, ahora=ahora)
    if desbloqueo is not None:
        logger.warning(
            "'%s' rechazado por bloqueo del login: usuario=%s dispositivo=%s ip=%s",
            funcionalidad,
            usuario.id,
            dispositivo_id,
            ip,
        )
        # Usuario ya autenticado: la hora va en la zona de la organización. Solo el 429 del login
        # usa siempre la zona argentina (ADR-057).
        raise LoginBloqueadoPorIntentosError(
            _mensaje_de_bloqueo(desbloqueo, organizacion.zona_horaria)
        )

    if not verificar_password(password_actual, usuario.password_hash):
        aparte = _sesion_aparte(sesion)
        try:
            _registrar_intento_fallido(
                aparte, clave_intento=clave, usuario_id=usuario.id, ip=ip, momento=ahora
            )
            aparte.commit()
        finally:
            aparte.close()
        logger.warning(
            "Contraseña incorrecta en '%s': usuario=%s dispositivo=%s ip=%s",
            funcionalidad,
            usuario.id,
            dispositivo_id,
            ip,
        )
        raise ContrasenaIncorrectaError("La contraseña no es correcta.")


def definir_pin_propio(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    password_actual: str,
    pin: str,
    ip: str,
    dispositivo_id: UUID | None,
) -> Usuario:
    """ "Mi PIN" (D21 parte B): el propio usuario define su PIN de autorización reautenticándose
    con su contraseña. Todo rechazo LANZA una excepción de dominio (nunca una tupla `RECHAZADO`):
    así no queda fila de `comando` y un reintento con el mismo `Operation-Id` y los datos
    corregidos se procesa.

    Orden: 1) bloqueo de login (D24; usuario 5 y IP 20, 15 minutos desde el último fallo): 429
    `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, también con la contraseña correcta, sin verificar,
    sin contar y sin escribir; 2) contraseña (`verificar_password` contra el hash del usuario): si
    es incorrecta se anota un intento fallido en `intento_login` en una TRANSACCIÓN APARTE (se
    confirma aunque el comando se rechace) y se lanza `ContrasenaIncorrectaError` (403); 3) el
    PIN nuevo (`establecer_pin_autorizacion`: formato, rol con permiso de autorización, marcador
    que reinicia el contador de D3). La contraseña y el PIN nunca se registran ni se incluyen en
    un mensaje. Sin `commit` sobre `sesion`."""
    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        raise AutorizadorNoEncontradoError(f"El usuario {usuario_id} no existe.")
    _exigir_contrasena_actual(
        organizacion_id,
        sesion,
        reloj,
        usuario=usuario,
        password_actual=password_actual,
        ip=ip,
        dispositivo_id=dispositivo_id,
        funcionalidad="Mi PIN",
    )

    actualizado = establecer_pin_autorizacion(
        organizacion_id,
        sesion,
        reloj,
        usuario_id=usuario_id,
        pin=pin,
        actor_id=usuario_id,
        auditar=False,
    )
    assert actualizado is not None  # el usuario existe: se leyó arriba.
    return actualizado


def cambiar_contrasena_propia(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    password_actual: str,
    password_nueva: str,
    ip: str,
    dispositivo_id: UUID,
    operation_id: UUID,
) -> Usuario:
    """`CONTRASENA_PROPIA_CAMBIAR` ("Mi contraseña", change 20b, D20; ADR-018, ADR-056, ADR-057).

    El usuario sale del token y se toma `FOR NO KEY UPDATE`: un cambio propio y un restablecimiento
    del administrador sobre el mismo usuario se serializan, y los intentos fallidos que se
    confirman en una transacción aparte (clave foránea a `usuario`) no quedan bloqueados. Todo
    rechazo LANZA una excepción de dominio (sin fila de `comando`): el reintento con el mismo
    `Operation-Id` y datos corregidos se procesa.

    Orden: 1) contraseña actual con el límite del login (`_exigir_contrasena_actual`: 429 o 403, y
    el fallo cuenta); 2) la nueva cumple la regla común y es distinta de la actual (422, no cuenta
    como intento); 3) deriva el hash; 4) revoca las familias de refresh de los demás dispositivos
    (`CONTRASENA_CAMBIADA`), conserva la del dispositivo de la sesión actual y las de dispositivos
    con jornada no cerrada; 5) auditoría `CAMBIAR_CONTRASENA_PROPIA` sin ninguna contraseña. Un
    cambio exitoso no borra los intentos fallidos previos ni toca el PIN."""
    usuario = repository.obtener_usuario_para_actualizar(organizacion_id, usuario_id, sesion)
    if usuario is None:
        raise AutorizadorNoEncontradoError(f"El usuario {usuario_id} no existe.")
    _exigir_contrasena_actual(
        organizacion_id,
        sesion,
        reloj,
        usuario=usuario,
        password_actual=password_actual,
        ip=ip,
        dispositivo_id=dispositivo_id,
        funcionalidad="Mi contraseña",
    )
    validar_contrasena_nueva(password_actual, password_nueva)

    momento = reloj.now()
    usuario.password_hash = hashear_password(password_nueva)
    usuario.actualizado_en = momento
    usuario.actualizado_por_id = usuario_id
    sesion.flush()
    revocadas = _revocar_sesiones_de_usuario_salvo_jornada(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        momento=momento,
        motivo="CONTRASENA_CAMBIADA",
        conservar_dispositivos=[dispositivo_id],
    )
    registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="CAMBIAR_CONTRASENA_PROPIA",
        entidad="usuario",
        entidad_id=usuario_id,
        ocurrido_en=momento,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        despues={"familias_revocadas": revocadas},
        operation_id=operation_id,
        origen="COMANDO",
    )
    _auditar_revocacion_de_sesiones(
        organizacion_id,
        sesion,
        reloj,
        usuario_id=usuario_id,
        cantidad=revocadas,
        motivo="CONTRASENA_CAMBIADA",
        momento=momento,
        actor_id=usuario_id,
        dispositivo_id_actor=dispositivo_id,
        operation_id=operation_id,
    )
    return usuario


# Sentinela, no una IP real: distingue el marcador de desbloqueo manual de
# cualquier intento de login real en `intento_login.ip` (que siempre lleva
# una dirección de origen). Nunca se compara contra un valor de IP real.
_IP_DESBLOQUEO_MANUAL = "admin:desbloqueo-manual"


def _registrar_marcador_de_desbloqueo(
    organizacion_id: UUID, sesion: Session, usuario: Usuario, *, momento: datetime
) -> None:
    """Inserta el marcador que neutraliza los fallos anteriores del par (slug, usuario) del
    usuario (ADR-057 punto 6): no toca el límite por IP. Lo usan el desbloqueo manual y el
    restablecimiento de contraseña (change 20b, D8)."""
    organizacion = repository.obtener_organizacion_por_id(organizacion_id, sesion)
    assert organizacion is not None  # el usuario existe: su organización también.
    repository.registrar_intento_login(
        sesion,
        intento_id=nuevo_id(),
        usuario_id=usuario.id,
        clave_intento=clave_de_intento_login(organizacion.slug, usuario.usuario),
        ip=_IP_DESBLOQUEO_MANUAL,
        exito=True,
        momento=momento,
    )


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
    (`repository.ultimo_fallo_de_login`). Desbloquear
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
    _registrar_marcador_de_desbloqueo(organizacion_id, sesion, usuario, momento=momento)
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

    Rate limit de login (grupo 11, `ADR-018` y su enmienda, `design.md` D24, `ADR-057`): orden IP
    (20), después par escrito (5; la clave es el SHA-256 de `[slug, usuario]` sin normalizar, exista
    o no la organización o el usuario), después credenciales. Rige `_hasta_del_bloqueo_de_login`:
    15 minutos desde el ÚLTIMO fallo contado. Ambos levantan `LoginBloqueadoPorIntentosError` (429)
    con el mismo mensaje genérico (tarea 11.3) y la hora SIEMPRE en la zona de Buenos Aires.
    Todo rechazo de credenciales verifica la contraseña (contra un hash ficticio si no hay usuario
    utilizable). Cada intento fallido que NO fue rechazado por el bloqueo se registra en
    `intento_login` con su `clave_intento` (tabla de solo inserción, sin `organizacion_id`); un
    intento bloqueado no se escribe: su rastro queda en el log y, solo si el par resuelve un
    usuario real, en la auditoría `LOGIN_BLOQUEADO_POR_INTENTOS`. Uno exitoso tampoco se escribe.
    """
    momento = reloj.now()
    clave = clave_de_intento_login(organizacion_slug, nombre_usuario)

    organizacion = repository.obtener_organizacion_por_slug(organizacion_slug, sesion)

    desbloqueo_en = _hasta_del_bloqueo_de_login(sesion, clave_intento=None, ip=ip, ahora=momento)
    if desbloqueo_en is not None:
        logger.warning("Login rechazado por bloqueo de la IP: ip=%s", ip)
        # El bloqueo por IP no mira la organización: dice lo mismo exista o no (ADR-018 3b).
        raise LoginBloqueadoPorIntentosError(_mensaje_de_bloqueo(desbloqueo_en, None))

    usuario = (
        repository.obtener_usuario_por_nombre_usuario(organizacion.id, nombre_usuario, sesion)
        if organizacion is not None
        else None
    )

    # ADR-057 punto 4: el límite por par escrito se evalúa ANTES de mirar si el usuario existe y
    # rige igual para un par que no corresponde a nadie; el 429 es indistinguible en los dos casos.
    desbloqueo_en = _hasta_del_bloqueo_de_login(sesion, clave_intento=clave, ip=None, ahora=momento)
    if desbloqueo_en is not None:
        if usuario is not None:
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
            logger.warning("Login rechazado por bloqueo: usuario=%s ip=%s", usuario.id, ip)
        else:
            # Sin usuario no hay a quién ligar la auditoría (y con slug inexistente tampoco
            # organización, INV-02): solo el log, con el resumen de la clave y nunca el texto
            # escrito ni la contraseña (ADR-057 punto 8, confirmado el 2026-10-24).
            logger.warning(
                "Login rechazado por bloqueo de un par sin usuario: clave=%s ip=%s", clave[:8], ip
            )
        # Siempre la zona argentina, exista o no la organización (ADR-057, 2026-10-24).
        raise LoginBloqueadoPorIntentosError(_mensaje_de_bloqueo(desbloqueo_en, None))

    rol_del_usuario = (
        repository.obtener_rol_por_id(organizacion.id, usuario.rol_id, sesion)
        if organizacion is not None and usuario is not None
        else None
    )
    # ADR-028 D9.1 último punto: un rol con `activo = false` se suma al mismo rechazo genérico que
    # un usuario inactivo. ADR-057 punto 7: sin usuario utilizable (slug o usuario inexistentes,
    # usuario o rol inactivos) la contraseña se verifica IGUAL, contra un hash ficticio, para que
    # el tiempo de respuesta no revele cuál de los casos ocurrió.
    hash_utilizable = (
        usuario.password_hash
        if usuario is not None
        and usuario.estado == "ACTIVO"
        and rol_del_usuario is not None
        and rol_del_usuario.activo
        else None
    )
    credenciales_validas = verificar_password_o_ficticio(password, hash_utilizable)
    if not credenciales_validas:
        _registrar_intento_fallido(
            sesion,
            clave_intento=clave,
            usuario_id=usuario.id if usuario is not None else None,
            ip=ip,
            momento=momento,
        )
        if organizacion is not None:
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
        # Un slug inexistente no se audita (no hay organización a la que asociar el registro).
        raise CredencialesInvalidasError("Usuario o contraseña incorrectos.")
    assert organizacion is not None  # para mypy: sin organización no hay credenciales válidas.
    assert usuario is not None  # para mypy: ya lo verificó `credenciales_validas`.

    if dispositivo_id is None:
        _registrar_intento_fallido(
            sesion, clave_intento=clave, usuario_id=usuario.id, ip=ip, momento=momento
        )
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
        _registrar_intento_fallido(
            sesion, clave_intento=clave, usuario_id=usuario.id, ip=ip, momento=momento
        )
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

    # ADR-028 D9.3-B / change 15 (D18, D19): si el usuario o su rol dejaron de estar activos,
    # la renovación se rechaza y se revocan las familias de refresh del usuario, SALVO que ese
    # dispositivo tenga una jornada no cerrada del usuario (`ABIERTA` o `EN_RENDICION`): ahí se
    # renueva, rotando el token como siempre y auditando cada renovación. La revocación en
    # bloque también respeta a los dispositivos con jornada no cerrada, para que rechazar la
    # renovación desde otro dispositivo no cierre el canal de la cola. Verificación DESPUÉS de
    # validar el token (reuso, revocación, vencimiento ya quedaron descartados arriba). El
    # usuario activo no consulta el puerto; sin consulta registrada no hay excepción (D19).
    usuario_con_rol = repository.obtener_usuario_con_rol(
        fila.organizacion_id, fila.usuario_id, sesion
    )
    motivo_sesion_deshabilitada = (
        "USUARIO_INACTIVO"
        if usuario_con_rol is None
        else _motivo_sesion_deshabilitada(*usuario_con_rol)
    )
    if motivo_sesion_deshabilitada is not None:
        if hay_jornada_no_cerrada(
            fila.organizacion_id, fila.usuario_id, fila.dispositivo_id, sesion
        ):
            registrar_auditoria(
                fila.organizacion_id,
                sesion,
                reloj,
                accion="RENOVAR_SESION_CON_JORNADA_PENDIENTE",
                entidad="usuario",
                entidad_id=fila.usuario_id,
                ocurrido_en=momento,
                usuario_id=fila.usuario_id,
                dispositivo_id=fila.dispositivo_id,
                observacion=(
                    f"Sesión deshabilitada ({motivo_sesion_deshabilitada}) renovada porque el "
                    "dispositivo tiene una jornada no cerrada (ADR-028 D9.3-B)."
                ),
                origen="SISTEMA",
            )
        else:
            dispositivos_con_jornada = [
                dispositivo_id
                for dispositivo_id in repository.dispositivos_con_sesion_vigente(
                    fila.organizacion_id, sesion, usuario_id=fila.usuario_id
                )
                if hay_jornada_no_cerrada(
                    fila.organizacion_id, fila.usuario_id, dispositivo_id, sesion
                )
            ]
            repository.revocar_sesiones_refresh_de_usuario(
                fila.organizacion_id,
                sesion,
                usuario_id=fila.usuario_id,
                momento=momento,
                motivo=motivo_sesion_deshabilitada,
                excepto_dispositivo_ids=dispositivos_con_jornada,
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


# --- D19/ADR-028 D9.3-B: puerto de consulta de jornada no cerrada ----------

ConsultaJornadaNoCerrada = Callable[[UUID, UUID, UUID, Session], bool]
"""`funcion(organizacion_id, usuario_id, dispositivo_id, sesion) -> bool` (change 15, D19):
verdadero si el usuario tiene una jornada `ABIERTA` o `EN_RENDICION` en ese dispositivo."""

_CONSULTA_JORNADA_NO_CERRADA: ConsultaJornadaNoCerrada | None = None


def registrar_consulta_jornada_no_cerrada(funcion: ConsultaJornadaNoCerrada) -> None:
    """`stock` la registra al importar su `service.py` (mismo patrón que ADR-023, ADR-025).
    Sin ciclo: `identidad` nunca importa `stock` (`02` §5.3; contrato de import-linter)."""
    global _CONSULTA_JORNADA_NO_CERRADA
    _CONSULTA_JORNADA_NO_CERRADA = funcion


def hay_jornada_no_cerrada(
    organizacion_id: UUID, usuario_id: UUID, dispositivo_id: UUID, sesion: Session
) -> bool:
    """Falla cerrado hacia el corte (D19): sin consulta registrada responde que no hay jornada,
    y la renovación del usuario inactivo se rechaza y revoca como en ADR-028 D9.3-A."""
    if _CONSULTA_JORNADA_NO_CERRADA is None:
        return False
    return _CONSULTA_JORNADA_NO_CERRADA(organizacion_id, usuario_id, dispositivo_id, sesion)


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


PERMISOS_DE_VENDEDOR: frozenset[str] = frozenset({"VENDER", "REGISTRAR_COBRANZA"})
"""Con alguno de estos permisos un usuario puede tener clientes asignados (change 20b, D15)."""


def es_vendedor_valido(organizacion_id: UUID, usuario_id: UUID, sesion: Session) -> bool:
    """Si `usuario_id` puede figurar como vendedor de la cartera (change 20b, D15): usuario
    `ACTIVO` de la organización, con rol activo y con `VENDER` o `REGISTRAR_COBRANZA`. Un usuario
    inexistente o de otra organización no es válido (INV-21); quien necesite distinguirlo para
    responder 404 lo consulta con `obtener_nombres_de_usuarios`. Nunca lanza."""
    permisos = listar_permisos_del_usuario(organizacion_id, usuario_id, sesion)
    return not PERMISOS_DE_VENDEDOR.isdisjoint(permisos)


def listar_vendedores_elegibles(organizacion_id: UUID, sesion: Session) -> list[tuple[UUID, str]]:
    """`(id, nombre)` de los usuarios que pueden figurar como vendedor de la cartera (change 20b,
    D15): la misma regla que `es_vendedor_valido`, calculada en SQL para toda la organización y
    ordenada por nombre. Sin datos sensibles."""
    return repository.listar_vendedores_elegibles(organizacion_id, PERMISOS_DE_VENDEDOR, sesion)


def motivo_de_permiso_faltante(
    organizacion_id: UUID, usuario_id: UUID, permiso_codigo: str, sesion: Session
) -> str | None:
    """`motivo_de_permisos_faltantes` para un solo permiso (change 17)."""
    return motivo_de_permisos_faltantes(organizacion_id, usuario_id, (permiso_codigo,), sesion)


def motivo_de_permisos_faltantes(
    organizacion_id: UUID, usuario_id: UUID, permisos_codigos: tuple[str, ...], sesion: Session
) -> str | None:
    """Por qué `usuario_id` no tiene NINGUNO de `permisos_codigos` hoy, o `None` si tiene al menos
    uno (change 17 y 18b, `design.md` D10, D11, D23; SYN-10, ADR-028 D9.3-B y D9.4-A, ADR-056). Es
    la lectura del paso 4 de `02` §6.3, en cualquier modo, contra los permisos vigentes (sin foto
    en el servidor):

    - `USUARIO_INACTIVO`: el usuario está inactivo (o no existe en la organización, INV-21);
    - `ROL_INACTIVO`: el usuario está activo pero su rol tiene `activo = false`;
    - `PERMISO_QUITADO`: ambos activos y el rol no tiene el permiso.

    Un usuario o rol inactivo se evalúa como "sin permisos": nunca se rechaza. Nunca lanza."""
    usuario_con_rol = repository.obtener_usuario_con_rol(organizacion_id, usuario_id, sesion)
    if usuario_con_rol is None:
        return "USUARIO_INACTIVO"
    usuario, rol = usuario_con_rol
    motivo_sesion = _motivo_sesion_deshabilitada(usuario, rol)
    if motivo_sesion is not None:
        return motivo_sesion
    permisos = repository.listar_permisos_de_rol(organizacion_id, usuario.rol_id, sesion)
    return None if any(codigo in permisos for codigo in permisos_codigos) else "PERMISO_QUITADO"


@dataclass(frozen=True)
class DatosParaDescuentoManual:
    """Lo que `descuentos` necesita de un usuario para evaluar un descuento manual (change 16,
    DSC-06): sus permisos vigentes y los topes de descuento (`design.md` D12, D19)."""

    usuario_id: UUID
    permisos: frozenset[str]
    tope_rol: Decimal
    tope_propio: Decimal | None


def obtener_datos_para_descuento_manual(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> DatosParaDescuentoManual | None:
    """Lectura de solo lectura para `descuentos/service.py::evaluar_descuento_manual` (change
    16, tarea 12.4): los permisos vigentes de `usuario_id` (vacíos si el usuario o su rol están
    inactivos, igual que `listar_permisos_del_usuario`) y su tope de descuento propio y el de su
    rol, o `None` si no existe en `organizacion_id` (INV-21: el de otra organización tampoco).
    No escribe nada y no expone secretos."""
    usuario_con_rol = repository.obtener_usuario_con_rol(organizacion_id, usuario_id, sesion)
    if usuario_con_rol is None:
        return None
    usuario, rol = usuario_con_rol
    permisos = listar_permisos_del_usuario(organizacion_id, usuario_id, sesion)
    return DatosParaDescuentoManual(
        usuario_id=usuario.id,
        permisos=permisos,
        tope_rol=rol.tope_descuento,
        tope_propio=usuario.tope_descuento_override,
    )


@dataclass(frozen=True)
class AutorizadorDisponible:
    """Una persona a la que quien vende puede pedirle autorización con su PIN (change 18b, D15)."""

    usuario_id: UUID
    nombre: str
    puede_autorizar_descuento: bool
    puede_superar_credito: bool


def listar_autorizadores_disponibles(
    organizacion_id: UUID, sesion: Session, *, excluir_usuario_id: UUID
) -> list[AutorizadorDisponible]:
    """Los usuarios activos con rol activo, PIN definido y `AUTORIZAR_DESCUENTO` o
    `SUPERAR_CREDITO`, sin `excluir_usuario_id` (quien vende) y sin datos de otra organización
    (INV-21). Nunca expone la derivación del PIN (ADR-011). Solo lee."""
    encontrados = repository.listar_autorizadores_con_pin(
        organizacion_id,
        sesion,
        permisos=("AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"),
        excluir_usuario_id=excluir_usuario_id,
    )
    return [
        AutorizadorDisponible(
            usuario_id=usuario_id,
            nombre=nombre,
            puede_autorizar_descuento="AUTORIZAR_DESCUENTO" in permisos,
            puede_superar_credito="SUPERAR_CREDITO" in permisos,
        )
        for usuario_id, nombre, permisos in encontrados
    ]


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


@dataclass(frozen=True)
class EstadoDeMiPin:
    """`GET /api/v1/yo/pin-autorizacion` (change 18b, tarea 11.5, D21 punto 1): lo que la pantalla
    "Mi PIN" necesita saber. Nunca la derivación, la sal ni las iteraciones (ADR-011)."""

    puede_definir: bool
    tiene_pin_autorizacion: bool


def obtener_estado_de_mi_pin(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> EstadoDeMiPin:
    """Si el rol del usuario confiere algún permiso de autorización (`puede_definir`, la misma
    regla que exige la ruta de definición) y si ya tiene un PIN definido. Exige la sesión
    habilitada (ADR-028 D9). Solo lee."""
    exigir_sesion_habilitada(organizacion_id, usuario_id, sesion)
    usuario = repository.obtener_usuario_por_id(organizacion_id, usuario_id, sesion)
    if usuario is None:
        raise AccessTokenInvalidoError("El usuario del token no existe.")
    permisos = listar_permisos_del_usuario(organizacion_id, usuario_id, sesion)
    return EstadoDeMiPin(
        puede_definir=rol_confiere_autorizacion_excepcion(permisos),
        tiene_pin_autorizacion=usuario.pin_autorizacion_hash is not None,
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
