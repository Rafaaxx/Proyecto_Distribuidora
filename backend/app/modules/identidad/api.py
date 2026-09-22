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
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import SystemClock
from app.core.errors import DomainError
from app.modules.identidad import commands as identidad_commands  # noqa: F401
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_dispositivo_revocar(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj  # type: ignore[arg-type]
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

    model_config = {"from_attributes": True}


class CrearUsuarioRequest(BaseModel):
    usuario: str
    nombre: str
    email: str | None
    password: str
    rol_id: UUID


@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[UsuarioResponse]:
    """Tarea 10.8, escenario "La contraseña no se puede recuperar del
    sistema": ninguna vía de lectura de usuario expone `password_hash`."""
    usuarios = repository.listar_usuarios(contexto.organizacion_id, sesion)
    return [UsuarioResponse.model_validate(u) for u in usuarios]


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
    contenido: dict[str, ContenidoComando] = {
        "usuario": datos.usuario,
        "nombre": datos.nombre,
        "email": datos.email,
        "password": datos.password,
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_usuario_crear(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj  # type: ignore[arg-type]
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_rol_permisos_cambiar(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj  # type: ignore[arg-type]
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


# --- Rotación de PIN de autorización (tarea 10.7, grupo 9) ------------------


class RotarPinRequest(BaseModel):
    pin: str


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
    contenido: dict[str, ContenidoComando] = {"usuario_id": str(usuario_id), "pin": datos.pin}
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_pin_autorizacion_rotar(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj  # type: ignore[arg-type]
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_usuario_desbloquear(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj  # type: ignore[arg-type]
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    if comando.estado == "RECHAZADO":
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")
