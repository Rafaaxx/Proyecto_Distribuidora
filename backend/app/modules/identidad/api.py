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

Las tres escrituras de este archivo (alta de usuario, composición de rol,
rotación de PIN) van directo por `identidad/service.py`, fuera del bus de
comandos (`design.md` D6, deuda nominada del change 04): el endpoint hace su
propio `commit`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.core.autenticacion import ContextoAutenticado, requiere_permiso
from app.core.clock import SystemClock
from app.core.errors import DomainError
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service

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
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("GESTIONAR_DISPOSITIVOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """`revocar_dispositivo` del servicio devuelve `None` si `dispositivo_id`
    no pertenece a `contexto.organizacion_id` (INV-21): acá se traduce en
    `RecursoNoEncontradoError` (404, SEG-07), igual que el resto de las
    rutas de este archivo -- nunca un 204 silencioso, que dejaría creer que
    la revocación tuvo efecto sobre un recurso ajeno cuando en realidad no
    tocó nada (spec `dispositivos`, escenario "Revocar un dispositivo de
    otra organización no lo encuentra")."""
    dispositivo = identidad_service.revocar_dispositivo(
        contexto.organizacion_id,
        sesion,
        SystemClock(),
        dispositivo_id=dispositivo_id,
        actor_id=contexto.usuario_id,
        dispositivo_id_actor=contexto.dispositivo_id,
    )
    if dispositivo is None:
        raise RecursoNoEncontradoError(
            f"El dispositivo {dispositivo_id} no existe en esta organización."
        )
    sesion.commit()


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
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> UsuarioResponse:
    """Escenario "Un alta de usuario queda auditada" (`identidad/service.py
    ::crear_usuario`, tarea 8.9): sin envolver en bus de comandos todavía
    (`design.md` D6, deuda nominada del change 04). `RecursoNoEncontradoError`
    si `rol_id` no pertenece a `contexto.organizacion_id` (SEG-07, INV-21,
    tarea 12.2)."""
    usuario = identidad_service.crear_usuario(
        contexto.organizacion_id,
        sesion,
        SystemClock(),
        usuario=datos.usuario,
        nombre=datos.nombre,
        email=datos.email,
        password=datos.password,
        rol_id=datos.rol_id,
        actor_id=contexto.usuario_id,
        dispositivo_id_actor=contexto.dispositivo_id,
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El rol {datos.rol_id} no existe en esta organización.")
    sesion.commit()
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
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> RolResponse:
    """Escenario "Una organización cambia la composición de un rol"
    (tarea 8.9). `RecursoNoEncontradoError` si `rol_id` no pertenece a
    `contexto.organizacion_id` (SEG-07, INV-21, tarea 10.7)."""
    rol = identidad_service.cambiar_composicion_rol(
        contexto.organizacion_id,
        sesion,
        SystemClock(),
        rol_id=rol_id,
        permisos_nuevos=frozenset(datos.permisos),
        actor_id=contexto.usuario_id,
        dispositivo_id_actor=contexto.dispositivo_id,
    )
    if rol is None:
        raise RecursoNoEncontradoError(f"El rol {rol_id} no existe en esta organización.")
    sesion.commit()
    permisos = repository.listar_permisos_de_rol(contexto.organizacion_id, rol_id, sesion)
    return RolResponse(id=rol.id, nombre=rol.nombre, permisos=sorted(permisos))


# --- Rotación de PIN de autorización (tarea 10.7, grupo 9) ------------------


class RotarPinRequest(BaseModel):
    pin: str


@router.post("/usuarios/{usuario_id}/pin", status_code=204)
def rotar_pin_autorizacion(
    usuario_id: UUID,
    datos: RotarPinRequest,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """Escenarios "Rotar el PIN invalida el anterior" y "La rotación queda
    auditada sin exponer el PIN" (grupo 9). `RecursoNoEncontradoError` si
    `usuario_id` no pertenece a `contexto.organizacion_id` (SEG-07, INV-21).
    El PIN nunca aparece en la respuesta (`status_code=204`, sin cuerpo)."""
    usuario = identidad_service.establecer_pin_autorizacion(
        contexto.organizacion_id,
        sesion,
        SystemClock(),
        usuario_id=usuario_id,
        pin=datos.pin,
        actor_id=contexto.usuario_id,
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")
    sesion.commit()


@router.post("/usuarios/{usuario_id}/desbloqueo", status_code=204)
def desbloquear_usuario(
    usuario_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ADMIN_USUARIOS"))],
    sesion: Annotated[Session, Depends(get_session)],
) -> None:
    """Desbloqueo manual de un usuario bloqueado por intentos (tarea 11.4,
    `ADR-018`). `RecursoNoEncontradoError` si `usuario_id` no pertenece a
    `contexto.organizacion_id` (SEG-07, INV-21)."""
    usuario = identidad_service.desbloquear_usuario(
        contexto.organizacion_id,
        sesion,
        SystemClock(),
        usuario_id=usuario_id,
        actor_id=contexto.usuario_id,
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")
    sesion.commit()
