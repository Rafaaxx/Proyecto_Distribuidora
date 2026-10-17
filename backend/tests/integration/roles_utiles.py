"""Utilidades de las pruebas de roles sin administrador (change 17b, grupos 6 y 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from descuentos_utiles import Entorno as EntornoDeDatos
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria, Rol, Usuario

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-sin-administrador"
ADMIN = "ADMIN_USUARIOS"
AUTORIZACION = frozenset(
    {"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO", "VENDER_CLIENTE_SUSPENDIDO", "USAR_LISTA_ANTERIOR"}
)
CODIGO = "IDENTIDAD_SIN_ADMINISTRADOR"


class Entorno(EntornoDeDatos):
    """Una organización sin ningún administrador de partida: cada prueba arma sus roles y
    usuarios (el usuario base del entorno no tiene `ADMIN_USUARIOS`)."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, permisos=frozenset({"VER_REPORTES"}))
        self.sesion.commit()
        self.slug = sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()

    def crear_rol(self, nombre: str, permisos: frozenset[str], *, activo: bool = True) -> Rol:
        rol = identidad_repository.crear_rol(
            self.org,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=nombre,
            tope_descuento=Decimal("0"),
            activo=activo,
            momento=MOMENTO,
        )
        for codigo in sorted(permisos):
            identidad_repository.asignar_permiso_a_rol(
                self.org, self.sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        self.sesion.commit()
        return rol

    def crear_usuario(
        self, rol: Rol, *, estado: str = "ACTIVO", con_pin: bool = False
    ) -> tuple[UUID, str]:
        nombre_usuario = f"usuario-{uuid4().hex[:8]}"
        usuario = identidad_repository.crear_usuario(
            self.org,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado=estado,
            momento=MOMENTO,
        )
        if con_pin:
            usuario.pin_autorizacion_hash = "hash-de-prueba"
            usuario.pin_autorizacion_sal = "sal-de-prueba"
            usuario.pin_autorizacion_iteraciones = 100_000
        self.sesion.commit()
        return usuario.id, nombre_usuario

    def entrar(self, cliente_http: TestClient, nombre_usuario: str) -> dict[str, str]:
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200, respuesta.text
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def permisos_de(self, rol_id: UUID) -> list[str]:
        return sorted(identidad_repository.listar_permisos_de_rol(self.org, rol_id, self.sesion))

    def pin_vigente(self, usuario_id: UUID) -> bool:
        fila = self.sesion.scalars(
            select(Usuario)
            .where(Usuario.organizacion_id == self.org, Usuario.id == usuario_id)
            .execution_options(populate_existing=True)
        ).one()
        return fila.pin_autorizacion_hash is not None

    def filas_de_auditoria(self) -> int:
        consulta = (
            select(func.count()).select_from(Auditoria).where(Auditoria.organizacion_id == self.org)
        )
        return self.sesion.scalar(consulta) or 0

    def cambiar(
        self,
        cliente_http: TestClient,
        headers: dict[str, str],
        rol: Rol,
        permisos: frozenset[str],
        *,
        operation_id: UUID | None = None,
    ) -> Any:
        return cliente_http.put(
            f"/api/v1/identidad/roles/{rol.id}/permisos",
            json={"permisos": sorted(permisos)},
            headers={**headers, "Operation-Id": str(operation_id or uuid4())},
        )
