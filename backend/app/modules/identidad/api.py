"""Endpoints de negocio de `identidad`: dispositivos, usuarios, composición
de roles y rotación de PIN (tarea 10.7).

Cada ruta declara su permiso (`design.md` D5, tarea 10.2/10.3): sin eso, el
ratchet de permiso por ruta (`tests/integration/test_ratchet_permiso_por_ruta.py`)
no deja que exista. `organizacion_id` viene siempre de `ContextoAutenticado`
(el token), nunca de la petición (tarea 10.4).

`UsuarioResponse` (tarea 10.8) nunca incluye `password_hash` ni las tres
columnas del PIN de autorización: son campos que Pydantic simplemente no
declara, no campos que se excluyan al serializar (`model_config
from_attributes`, `03` §4, `02` §17).

Alta de usuario, revocación de dispositivo, rotación de PIN (change 04,
grupo 11, `design.md` D7), cambio de composición de rol y desbloqueo manual
de usuario (change 04, grupo 14, decisión del usuario 2026-09-22, `tasks.md`
14.3-14.6) pasan a delegar en el bus de comandos: exigen `Operation-Id`
(`requiere_comando_online`) y llaman a `sync_service.procesar_comando`, que
hace su propio `commit`. El import de `app.modules.identidad.commands` (sin
uso directo en este archivo) puebla el registro de handlers al arrancar la
aplicación (`registro.py`, docstring: "el arranque puebla este registro
importando los módulos de negocio que declaran sus handlers") -- sin él,
`USUARIO_CREAR`, `DISPOSITIVO_REVOCAR`, `PIN_AUTORIZACION_ROTAR`,
`ROL_PERMISOS_CAMBIAR` y `USUARIO_DESBLOQUEAR` serían tipos "nunca
importados", indistinguibles de un tipo que no existe (`registro.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, SecretStr, StrictBool
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import SobreComando, construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    obtener_contexto_autenticado,
    requiere_comando_online,
    requiere_comando_online_algun_permiso,
    requiere_permiso,
    requiere_sesion,
)
from app.core.clock import SystemClock
from app.core.errors import DomainError
from app.modules.identidad import commands as identidad_commands  # noqa: F401
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import PERMISOS_AUTORIZACION_EXCEPCION
from app.modules.identidad.domain.valores import computa_credito_fiscal
from app.modules.sync import service as sync_service

router = APIRouter(prefix="/identidad", tags=["identidad"])


class RecursoNoEncontradoError(DomainError):
    """SEG-07/INV-21: un recurso de otra organización responde como
    inexistente (`CLAUDE.md` §4: "Un recurso de otra organización responde
    404, no 403"). Traducido a Problem Details por el manejador genérico de
    `DomainError` (`app/main.py`), igual que cualquier otro error de
    dominio: nunca un `HTTPException` crudo sin `codigo` estable."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class DispositivoResponse(BaseModel):
    id: UUID
    nombre: str
    prefijo: str
    estado: str
    ultimo_correlativo: int
    revocado_en: datetime | None

    model_config = {"from_attributes": True}


@router.get("/dispositivos", response_model=list[DispositivoResponse])
def listar_dispositivos(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("GESTIONAR_DISPOSITIVOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[DispositivoResponse]:
    """Escenario "El listado incluye solo los dispositivos propios": la
    organización es la del token, no puede pedirse otra (tarea 10.4)."""
    dispositivos = identidad_service.listar_dispositivos(contexto.organizacion_id, sesion)
    return [DispositivoResponse.model_validate(d) for d in dispositivos]


@router.delete("/dispositivos/{dispositivo_id}", status_code=204)
def revocar_dispositivo(
    dispositivo_id: UUID,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("GESTIONAR_DISPOSITIVOS"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """Change 04, grupo 11 (`design.md` D7): delega en el bus de comandos
    (`DISPOSITIVO_REVOCAR`, `identidad/commands.py`). `RecursoNoEncontradoError`
    (404, SEG-07) si el handler rechaza porque `dispositivo_id` no pertenece
    a `entrada.contexto.organizacion_id` (INV-21) -- nunca un 204 silencioso
    (spec `dispositivos`, escenario "Revocar un dispositivo de otra
    organización no lo encuentra")."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"dispositivo_id": str(dispositivo_id)}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="DISPOSITIVO_REVOCAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_dispositivo_revocar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(
            f"El dispositivo {dispositivo_id} no existe en esta organización."
        )


# --- Usuarios (tarea 10.7/10.8) --------------------------------------------


class UsuarioResponse(BaseModel):
    """Tarea 10.8: sin `password_hash` ni las tres columnas del PIN de
    autorización -- Pydantic solo serializa los campos declarados acá, así
    que omitirlos de este modelo es la garantía, no un filtro posterior."""

    id: UUID
    usuario: str
    nombre: str
    email: str | None
    rol_id: UUID
    estado: str
    tiene_pin_autorizacion: bool = False
    """D21 (change 18b), ADR-011: solo si hay PIN definido, nunca su derivación (que sigue sin
    declararse en este modelo)."""

    model_config = {"from_attributes": True}


class CrearUsuarioRequest(BaseModel):
    """`password: SecretStr`, sin validadores (D2): el valor no aparece en un error."""

    usuario: str
    nombre: str
    email: str | None
    password: SecretStr
    rol_id: UUID


@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[UsuarioResponse]:
    """Tarea 10.8, escenario "La contraseña no se puede recuperar del
    sistema": ninguna vía de lectura de usuario expone `password_hash`."""
    usuarios = repository.listar_usuarios(contexto.organizacion_id, sesion)
    return [
        UsuarioResponse.model_validate(u).model_copy(
            update={"tiene_pin_autorizacion": u.pin_autorizacion_hash is not None}
        )
        for u in usuarios
    ]


@router.post("/usuarios", response_model=UsuarioResponse, status_code=201)
def crear_usuario(
    datos: CrearUsuarioRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> UsuarioResponse:
    """Change 04, grupo 11 (`design.md` D7): delega en el bus de comandos
    (`USUARIO_CREAR`, `identidad/commands.py`) en vez de llamar directo a
    `identidad_service.crear_usuario` (deuda nominada por el change 03, D6).
    `RecursoNoEncontradoError` si `rol_id` no pertenece a
    `entrada.contexto.organizacion_id` (SEG-07, INV-21, tarea 12.2). Un
    reenvío idéntico (mismo `Operation-Id`, mismo contenido) resuelve el
    mismo usuario ya creado -- se relee de la base para que la respuesta
    sea el estado real, no un valor cacheado del primer intento."""
    reloj = SystemClock()
    # La contraseña no entra al contenido ni a la huella: llega al handler por clausura (D2).
    contenido: dict[str, ContenidoComando] = {
        "usuario": datos.usuario,
        "nombre": datos.nombre,
        "email": datos.email,
        "rol_id": str(datos.rol_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_usuario_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
            password=datos.password,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(f"El rol {datos.rol_id} no existe en esta organización.")
    assert comando.resultado is not None
    usuario_id = UUID(str(comando.resultado["usuario_id"]))
    usuario = repository.obtener_usuario_por_id(
        entrada.contexto.organizacion_id, usuario_id, sesion
    )
    assert usuario is not None
    return UsuarioResponse.model_validate(usuario)


# --- Composición de roles (tarea 10.7) --------------------------------------


class ComposicionRolRequest(BaseModel):
    permisos: list[str]


class RolResponse(BaseModel):
    id: UUID
    nombre: str
    permisos: list[str]


class PermisoCatalogoResponse(BaseModel):
    codigo: str
    descripcion: str
    modulo: str


@router.get("/permisos", response_model=list[PermisoCatalogoResponse])
def listar_catalogo_de_permisos(
    _contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[PermisoCatalogoResponse]:
    """El catálogo global de permisos (`01` §19, `03` §4) con código, descripción y módulo, en el
    orden del documento. No depende de la organización (change 17b, D7, D9)."""
    return [
        PermisoCatalogoResponse(
            codigo=fila.codigo, descripcion=fila.descripcion, modulo=fila.modulo
        )
        for fila in identidad_service.listar_catalogo_de_permisos(sesion)
    ]


@router.put("/roles/{rol_id}/permisos", response_model=RolResponse)
def cambiar_composicion_rol(
    rol_id: UUID,
    datos: ComposicionRolRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> RolResponse:
    """Change 04, grupo 14 (decisión del usuario 2026-09-22, `tasks.md`
    14.3/14.4): delega en el bus de comandos (`ROL_PERMISOS_CAMBIAR`,
    `identidad/commands.py`) en vez de llamar directo a
    `identidad_service.cambiar_composicion_rol` (deuda encontrada por la
    tarea 14.2). `RecursoNoEncontradoError` si `rol_id` no pertenece a
    `entrada.contexto.organizacion_id` (SEG-07, INV-21, tarea 10.7). Un
    reenvío idéntico resuelve el mismo rol ya modificado -- se relee de la
    base para que la respuesta sea el estado real (mismo criterio que
    `crear_usuario`)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "rol_id": str(rol_id),
        "permisos": list(datos.permisos),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="ROL_PERMISOS_CAMBIAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_rol_permisos_cambiar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(f"El rol {rol_id} no existe en esta organización.")
    rol = repository.obtener_rol_por_id(entrada.contexto.organizacion_id, rol_id, sesion)
    assert rol is not None
    permisos = repository.listar_permisos_de_rol(entrada.contexto.organizacion_id, rol_id, sesion)
    return RolResponse(id=rol.id, nombre=rol.nombre, permisos=sorted(permisos))


# --- Tope de descuento de un rol (change 16, tarea 13.2, `design.md` D13) ---------------
#
# Cambia SOLO `rol.tope_descuento`: no toca los permisos del rol, el tope propio de los usuarios,
# el PIN, el token ni `GET /yo`. Escritura por el bus (`ROL_TOPE_DESCUENTO_DEFINIR`, `ONLINE`) y
# lectura de los roles de la organización con su tope como cadena (INV-03); ambas con
# `ADMIN_USUARIOS`.


class TopeDescuentoRolRequest(BaseModel):
    """Solo el tope, como cadena con hasta 6 decimales: un número JSON responde 422 (INV-03).
    Sin `organizacion_id`: sale del token (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    tope_descuento: str


class RolConTopeResponse(BaseModel):
    id: UUID
    nombre: str
    activo: bool
    tope_descuento: str


class RolConTopeYPermisosResponse(RolConTopeResponse):
    """La lectura suma los permisos del rol (códigos ordenados) para que la pantalla "Topes por
    rol" avise solo donde el tope 0 % importa (DSC-06). La escritura no los devuelve."""

    permisos: list[str]
    usuarios_activos: int


@router.get("/roles", response_model=list[RolConTopeYPermisosResponse])
def listar_roles(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[RolConTopeYPermisosResponse]:
    """Los roles de la organización del token, con nombre, estado, tope y permisos (una consulta
    para todos los permisos, sin N+1). Ningún rol ajeno (INV-21)."""
    permisos_por_rol = repository.listar_permisos_de_todos_los_roles(
        contexto.organizacion_id, sesion
    )
    activos_por_rol = repository.contar_usuarios_activos_por_rol(contexto.organizacion_id, sesion)
    return [
        RolConTopeYPermisosResponse(
            id=rol.id,
            nombre=rol.nombre,
            activo=rol.activo,
            tope_descuento=f"{rol.tope_descuento:.6f}",
            permisos=permisos_por_rol.get(rol.id, []),
            usuarios_activos=activos_por_rol.get(rol.id, 0),
        )
        for rol in repository.listar_roles(contexto.organizacion_id, sesion)
    ]


@router.put("/roles/{rol_id}/tope-descuento", response_model=RolConTopeResponse)
def definir_tope_descuento_de_rol(
    rol_id: UUID,
    datos: TopeDescuentoRolRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> RolConTopeResponse:
    """`ROL_TOPE_DESCUENTO_DEFINIR` (D13). La respuesta sale de `comando.resultado`, no de una
    relectura: un reenvío idempotente devuelve exactamente lo mismo (INV-06). Un rol que no está
    en la organización del token responde 404 (INV-21, SEG-07)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "rol_id": str(rol_id),
        "tope_descuento": datos.tope_descuento,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="ROL_TOPE_DESCUENTO_DEFINIR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_rol_tope_descuento_definir(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError(f"El rol {rol_id} no existe en esta organización.")
    resultado = comando.resultado
    return RolConTopeResponse(
        id=UUID(str(resultado["rol_id"])),
        nombre=str(resultado["nombre"]),
        activo=bool(resultado["activo"]),
        tope_descuento=str(resultado["tope_descuento"]),
    )


# --- Rotación de PIN de autorización (tarea 10.7, grupo 9) ------------------


class RotarPinRequest(BaseModel):
    """`pin: SecretStr`, sin validadores (D2): el valor no aparece en un error."""

    pin: SecretStr


@router.post("/usuarios/{usuario_id}/pin", status_code=204)
def rotar_pin_autorizacion(
    usuario_id: UUID,
    datos: RotarPinRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """Change 04, grupo 11 (`design.md` D7): delega en el bus de comandos
    (`PIN_AUTORIZACION_ROTAR`, `identidad/commands.py`). El PIN viaja en el
    contenido del comando como texto (igual que en el cuerpo HTTP que ya
    recibía) -- `identidad_commands.PinAutorizacionRotarContenidoV1` lo
    envuelve en `SecretStr` recién al validarlo contra el esquema
    (`registro.validar_contenido`); `RecursoNoEncontradoError` si
    `usuario_id` no pertenece a `entrada.contexto.organizacion_id` (SEG-07,
    INV-21). El PIN nunca aparece en la respuesta (`status_code=204`, sin
    cuerpo)."""
    reloj = SystemClock()
    # El PIN no entra al contenido ni a la huella: llega al handler por clausura (D2).
    contenido: dict[str, ContenidoComando] = {"usuario_id": str(usuario_id)}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PIN_AUTORIZACION_ROTAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_pin_autorizacion_rotar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
            pin=datos.pin,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")


@router.post("/usuarios/{usuario_id}/desbloqueo", status_code=204)
def desbloquear_usuario(
    usuario_id: UUID,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """Desbloqueo manual de un usuario bloqueado por intentos (tarea 11.4,
    `ADR-018`). Change 04, grupo 14 (decisión del usuario 2026-09-22,
    `tasks.md` 14.5/14.6): delega en el bus de comandos
    (`USUARIO_DESBLOQUEAR`, `identidad/commands.py`). `RecursoNoEncontradoError`
    si `usuario_id` no pertenece a `entrada.contexto.organizacion_id`
    (SEG-07, INV-21)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"usuario_id": str(usuario_id)}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="USUARIO_DESBLOQUEAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_usuario_desbloquear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")


# --- `GET /api/v1/yo` (change 06b, grupo 4, D1) -----------------------------
#
# Sin prefijo (`design.md` D1-A: `GET /api/v1/yo`, no `/api/v1/identidad/yo`):
# router aparte, agregado en `api_v1/__init__.py` junto al de `identidad`.
# Exenta de permiso en `RUTAS_EXENTAS_DE_PERMISO`
# (`tests/integration/test_ratchet_permiso_por_ruta.py`, ADR-027): exige
# sesión (`obtener_contexto_autenticado`) pero ningún permiso en particular,
# porque su propósito es informar cuáles tiene el usuario.

router_yo = APIRouter(tags=["identidad"])


class UsuarioYoResponse(BaseModel):
    id: UUID
    nombre: str


class OrganizacionYoResponse(BaseModel):
    id: UUID
    nombre: str


class RolYoResponse(BaseModel):
    id: UUID
    nombre: str


class YoResponse(BaseModel):
    """Forma exacta del contrato aprobado el 2026-09-25 (tarea 4.1,
    `design.md` "Contrato de `GET /api/v1/yo`"): usuario, organización y rol
    (id y nombre), y la lista de permisos vigentes en orden alfabético
    ascendente. Nunca `usuario.usuario` (nombre de login), email, estado,
    secretos ni tope de descuento -- son campos que esta clase simplemente
    no declara, no campos excluidos al serializar (mismo criterio que
    `UsuarioResponse` más arriba)."""

    usuario: UsuarioYoResponse
    organizacion: OrganizacionYoResponse
    rol: RolYoResponse
    permisos: list[str]


@router_yo.get("/yo", response_model=YoResponse)
def obtener_yo(
    contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
    sesion: Annotated[Session, Depends(get_session)],
) -> YoResponse:
    """Datos de la propia sesión (D1, ADR-027). Delega enteramente en
    `identidad_service.obtener_yo`: ninguna lógica de permisos o de sesión
    habilitada se duplica acá. `AccessTokenInvalidoError` (usuario
    inexistente, `INACTIVO`, o con rol inactivo -- ADR-028 D9) se propaga
    tal cual; el manejador genérico de `DomainError` la traduce a 401
    `IDENTIDAD_ACCESS_TOKEN_INVALIDO` (D1)."""
    datos = identidad_service.obtener_yo(contexto.organizacion_id, contexto.usuario_id, sesion)
    return YoResponse(
        usuario=UsuarioYoResponse(id=datos.usuario.id, nombre=datos.usuario.nombre),
        organizacion=OrganizacionYoResponse(
            id=datos.organizacion.id, nombre=datos.organizacion.nombre
        ),
        rol=RolYoResponse(id=datos.rol.id, nombre=datos.rol.nombre),
        permisos=datos.permisos,
    )


# --- "Mi PIN": definir el propio PIN de autorización (change 18b, D21 parte B) -----------------


class MiPinRequest(BaseModel):
    """`POST /yo/pin-autorizacion`. `extra="forbid"`: el usuario sale del token, nunca del cuerpo
    (un `usuario_id` es un 422 sin eco del valor). Los dos secretos son `SecretStr` y no tienen
    validadores (D2, D21 punto 3): la ruta los separa antes de armar el contenido y la huella."""

    model_config = ConfigDict(extra="forbid")

    pin: SecretStr
    password_actual: SecretStr


class MiPinEstadoResponse(BaseModel):
    """`GET /yo/pin-autorizacion`: dos booleanos y nada más (ADR-011): ni derivación ni sal."""

    puede_definir: bool
    tiene_pin_autorizacion: bool


@router_yo.get("/yo/pin-autorizacion", response_model=MiPinEstadoResponse)
def obtener_estado_de_mi_pin(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_sesion)],
    sesion: Annotated[Session, Depends(get_session)],
) -> MiPinEstadoResponse:
    """Change 18b, tarea 11.5 (D21 punto 1): si el usuario del token puede definir su PIN de
    autorización y si ya lo tiene. Cualquier sesión habilitada (la pantalla decide si ofrece "Mi
    PIN"); todo sale del token. `GET /yo` no cambia."""
    estado = identidad_service.obtener_estado_de_mi_pin(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    return MiPinEstadoResponse(
        puede_definir=estado.puede_definir,
        tiene_pin_autorizacion=estado.tiene_pin_autorizacion,
    )


@router_yo.post("/yo/pin-autorizacion", status_code=204)
def definir_mi_pin(
    datos: MiPinRequest,
    request: Request,
    entrada: Annotated[
        EntradaComandoOnline,
        Depends(requiere_comando_online_algun_permiso(*sorted(PERMISOS_AUTORIZACION_EXCEPCION))),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """`PIN_AUTORIZACION_PROPIO_DEFINIR` (D21 parte B). Exige alguno de los permisos de
    autorización de excepciones (403 `PERMISO_REQUERIDO` antes de tocar la base). Delega en el
    bus; el PIN, la contraseña y la IP del cliente (`request.client.host`, la misma que usa el
    login) llegan al handler por clausura, no por el contenido. Respuesta 204 sin cuerpo."""
    reloj = SystemClock()
    ip = request.client.host if request.client is not None else "desconocida"
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PIN_AUTORIZACION_PROPIO_DEFINIR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido={},
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_pin_autorizacion_propio_definir(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
            password_actual=datos.password_actual,
            pin=datos.pin,
            ip=ip,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )


# --- configuración fiscal (change 11b, `design.md` D7, D8, CST-06) ---------------------
#
# `GET /configuracion/fiscal` la lee cualquier usuario autenticado de la organización:
# la consumen las pantallas de compras y de carga de costos para ocultar la casilla de IVA
# y elegir el total sugerido, cada una con su propio permiso de negocio. Exige sesión
# válida y habilitada (`requiere_sesion`), no un permiso: figura en la lista de exenciones
# del ratchet de permiso por ruta, igual que los medios de pago y los motivos.
# `POST .../condicion-iva` exige `ADMIN_CONFIGURACION` y delega en el bus. La organización
# sale siempre del token (INV-21).

router_fiscal = APIRouter(prefix="/configuracion/fiscal", tags=["configuracion"])


class ConfiguracionFiscalResponse(BaseModel):
    condicion_iva: Literal["RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO"]
    computa_credito_fiscal: bool
    modo_impositivo: str
    modalidad_iva_default: str | None


class CondicionIvaCambiarRequest(BaseModel):
    """Solo la condición nueva: `organizacion_id` nunca aparece (sale del token). Un valor
    fuera del dominio cerrado responde 422."""

    model_config = ConfigDict(extra="ignore")

    condicion_iva: Literal["RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO"]


@router_fiscal.get("", response_model=ConfiguracionFiscalResponse)
def obtener_configuracion_fiscal(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_sesion)],
    sesion: Annotated[Session, Depends(get_session)],
) -> ConfiguracionFiscalResponse:
    configuracion = identidad_service.obtener_configuracion(contexto.organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return ConfiguracionFiscalResponse(
        condicion_iva=configuracion.condicion_iva,  # type: ignore[arg-type]
        computa_credito_fiscal=computa_credito_fiscal(configuracion.condicion_iva),
        modo_impositivo=configuracion.modo_impositivo,
        modalidad_iva_default=configuracion.modalidad_iva_default,
    )


@router_fiscal.post("/condicion-iva", response_model=ConfiguracionFiscalResponse)
def cambiar_condicion_iva(
    datos: CondicionIvaCambiarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_CONFIGURACION"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ConfiguracionFiscalResponse:
    """`ORGANIZACION_CONDICION_IVA_CAMBIAR` (D7). La respuesta sale de `comando.resultado`,
    no de una relectura: un reenvío idempotente devuelve exactamente lo mismo (INV-06)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"condicion_iva": datos.condicion_iva}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="ORGANIZACION_CONDICION_IVA_CAMBIAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_organizacion_condicion_iva_cambiar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return ConfiguracionFiscalResponse.model_validate(comando.resultado)


# --- parámetros de la organización: descuento manual y crédito (change 18b, D13, D14) ----
#
# Las dos lecturas y las dos escrituras exigen `ADMIN_CONFIGURACION` (SEG-06). Las lecturas son
# para la pantalla de "Configuración": quien vende recibe estos mismos valores por el contexto
# de venta (D15), con su propio permiso. La organización sale siempre del token (INV-21).

router_parametros = APIRouter(prefix="/configuracion", tags=["configuracion"])


def _preparar_comando_online(
    entrada: EntradaComandoOnline,
    tipo: str,
    contenido: dict[str, ContenidoComando],
    reloj: SystemClock,
) -> tuple[SobreComando, str, registro.HandlerRegistrado, object]:
    """El sobre, la huella y el contenido ya validado de un comando REST de la organización. La
    llamada a `procesar_comando` queda en cada ruta (el ratchet de cobertura del bus la busca en
    la función del endpoint)."""
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo=tipo,
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)
    return sobre, calcular_huella(sobre.contenido), handler_registrado, contenido_validado


class DescuentoManualResponse(BaseModel):
    habilitado: bool
    motivo_obligatorio: bool


class DescuentoManualConfigurarRequest(BaseModel):
    """Los dos booleanos estrictos y obligatorios: un texto, un número o un nulo responden 422."""

    model_config = ConfigDict(extra="ignore")

    habilitado: StrictBool
    motivo_obligatorio: StrictBool


@router_parametros.get("/descuento-manual", response_model=DescuentoManualResponse)
def obtener_descuento_manual(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_CONFIGURACION"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> DescuentoManualResponse:
    """Si la organización habilita el descuento manual y si exige motivo (DSC-06). Un motivo
    obligatorio sin definir (nulo) se informa como `false`: no se exige."""
    configuracion = identidad_service.obtener_configuracion(contexto.organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return DescuentoManualResponse(
        habilitado=configuracion.descuento_manual_habilitado,
        motivo_obligatorio=bool(configuracion.motivo_obligatorio_descuento),
    )


@router_parametros.post("/descuento-manual", response_model=DescuentoManualResponse)
def configurar_descuento_manual(
    datos: DescuentoManualConfigurarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_CONFIGURACION"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> DescuentoManualResponse:
    """`DESCUENTO_MANUAL_CONFIGURAR` (D13). La respuesta sale de `comando.resultado`, no de una
    relectura: un reenvío idempotente devuelve exactamente lo mismo (INV-06)."""
    reloj = SystemClock()
    sobre, huella, handler_registrado, contenido_validado = _preparar_comando_online(
        entrada,
        "DESCUENTO_MANUAL_CONFIGURAR",
        {"habilitado": datos.habilitado, "motivo_obligatorio": datos.motivo_obligatorio},
        reloj,
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_descuento_manual_configurar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return DescuentoManualResponse.model_validate(comando.resultado)


class CreditoOrganizacionResponse(BaseModel):
    politica: Literal["ADVERTIR", "AUTORIZAR", "BLOQUEAR"]
    tolerancia_tipo: Literal["IMPORTE", "PORCENTAJE"] | None
    tolerancia_valor: str | None


class CreditoOrganizacionConfigurarRequest(BaseModel):
    """Política y tolerancia, los tres obligatorios (la tolerancia vacía son los dos `null`). La
    política o el tipo fuera del catálogo responden 422; la pareja a medias, el dominio, con
    `TOLERANCIA_OFFLINE_INVALIDA`."""

    model_config = ConfigDict(extra="ignore")

    politica: Literal["ADVERTIR", "AUTORIZAR", "BLOQUEAR"]
    tolerancia_tipo: Literal["IMPORTE", "PORCENTAJE"] | None
    tolerancia_valor: str | None


@router_parametros.get("/credito", response_model=CreditoOrganizacionResponse)
def obtener_credito_de_la_organizacion(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_CONFIGURACION"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> CreditoOrganizacionResponse:
    """La política de crédito por defecto y la tolerancia sin conexión de la organización
    (CRE-03, CRE-06)."""
    configuracion = identidad_service.obtener_configuracion(contexto.organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    valor = configuracion.tolerancia_offline_valor
    return CreditoOrganizacionResponse(
        politica=configuracion.politica_credito_default,  # type: ignore[arg-type]
        tolerancia_tipo=configuracion.tolerancia_offline_tipo,  # type: ignore[arg-type]
        tolerancia_valor=None if valor is None else f"{valor:.2f}",
    )


@router_parametros.post("/credito", response_model=CreditoOrganizacionResponse)
def configurar_credito_de_la_organizacion(
    datos: CreditoOrganizacionConfigurarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_CONFIGURACION"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CreditoOrganizacionResponse:
    """`CREDITO_ORGANIZACION_CONFIGURAR` (D14). La respuesta sale de `comando.resultado`
    (INV-06)."""
    reloj = SystemClock()
    sobre, huella, handler_registrado, contenido_validado = _preparar_comando_online(
        entrada,
        "CREDITO_ORGANIZACION_CONFIGURAR",
        {
            "politica": datos.politica,
            "tolerancia_tipo": datos.tolerancia_tipo,
            "tolerancia_valor": datos.tolerancia_valor,
        },
        reloj,
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_credito_organizacion_configurar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return CreditoOrganizacionResponse.model_validate(comando.resultado)


class NotaVentaConfiguracionResponse(BaseModel):
    muestra_saldo: bool
    domicilio: str | None
    telefono: str | None


class NotaVentaConfigurarRequest(BaseModel):
    """`muestra_saldo` booleano estricto; domicilio y teléfono obligatorios (vacíos son `null` o
    texto en blanco). El largo se valida en el dominio: `DATO_DE_NOTA_INVALIDO` (422)."""

    model_config = ConfigDict(extra="ignore")

    muestra_saldo: StrictBool
    domicilio: str | None
    telefono: str | None


@router_parametros.get("/nota-de-venta", response_model=NotaVentaConfiguracionResponse)
def obtener_nota_de_venta_de_la_organizacion(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_CONFIGURACION"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> NotaVentaConfiguracionResponse:
    """Los parámetros de la nota de venta de la organización (VTA-13)."""
    configuracion = identidad_service.obtener_configuracion(contexto.organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return NotaVentaConfiguracionResponse(
        muestra_saldo=configuracion.nota_venta_muestra_saldo,
        domicilio=configuracion.nota_venta_domicilio,
        telefono=configuracion.nota_venta_telefono,
    )


@router_parametros.post("/nota-de-venta", response_model=NotaVentaConfiguracionResponse)
def configurar_nota_de_venta_de_la_organizacion(
    datos: NotaVentaConfigurarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_CONFIGURACION"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> NotaVentaConfiguracionResponse:
    """`NOTA_VENTA_CONFIGURAR` (D10). La respuesta sale de `comando.resultado` (INV-06)."""
    reloj = SystemClock()
    sobre, huella, handler_registrado, contenido_validado = _preparar_comando_online(
        entrada,
        "NOTA_VENTA_CONFIGURAR",
        {
            "muestra_saldo": datos.muestra_saldo,
            "domicilio": datos.domicilio,
            "telefono": datos.telefono,
        },
        reloj,
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_nota_venta_configurar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    return NotaVentaConfiguracionResponse.model_validate(comando.resultado)


class OrganizacionDatosResponse(BaseModel):
    nombre: str
    cuit: str | None


class OrganizacionDatosConfigurarRequest(BaseModel):
    """`nombre` y `cuit` obligatorios en el cuerpo (el CUIT vacío es `null` o texto en blanco).
    La normalización y el largo se validan en el dominio: `NOMBRE_DE_ORGANIZACION_INVALIDO` y
    `CUIT_INVALIDO` (422)."""

    model_config = ConfigDict(extra="ignore")

    nombre: str
    cuit: str | None


@router_parametros.get("/organizacion", response_model=OrganizacionDatosResponse)
def obtener_datos_de_la_organizacion(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_CONFIGURACION"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> OrganizacionDatosResponse:
    """El nombre y el CUIT de la organización del token (VTA-13)."""
    organizacion = identidad_service.obtener_organizacion(contexto.organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    return OrganizacionDatosResponse(nombre=organizacion.nombre, cuit=organizacion.cuit)


@router_parametros.post("/organizacion", response_model=OrganizacionDatosResponse)
def configurar_datos_de_la_organizacion(
    datos: OrganizacionDatosConfigurarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("ADMIN_CONFIGURACION"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> OrganizacionDatosResponse:
    """`ORGANIZACION_DATOS_CONFIGURAR` (D15). La respuesta sale de `comando.resultado` (INV-06)."""
    reloj = SystemClock()
    sobre, huella, handler_registrado, contenido_validado = _preparar_comando_online(
        entrada,
        "ORGANIZACION_DATOS_CONFIGURAR",
        {"nombre": datos.nombre, "cuit": datos.cuit},
        reloj,
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_organizacion_datos_configurar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO" or comando.resultado is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    return OrganizacionDatosResponse.model_validate(comando.resultado)
