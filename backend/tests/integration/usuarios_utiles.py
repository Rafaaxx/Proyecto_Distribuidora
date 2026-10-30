"""Utilidades de las pruebas de administración de usuarios (change 20b, grupos 3 a 5).

Extiende el entorno de las pruebas de roles (`roles_utiles.Entorno`: una organización sin
administradores de partida, roles y usuarios por prueba) con lo que hace falta para ejercitar los
comandos de usuario de punta a punta por HTTP: sesiones reales con su cookie de refresh y su
dispositivo, familias de refresh, auditoría y el estado confirmado de un usuario.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from roles_utiles import ADMIN, JWT_SECRET, PASSWORD, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)

__all__ = [
    "ADMIN",
    "PASSWORD",
    "EntornoUsuarios",
    "SesionAbierta",
    "cliente_http",
    "limpiar_datos_confirmados",
    "sesion_real",
]

URL_USUARIOS = "/api/v1/identidad/usuarios"


@dataclass(frozen=True)
class SesionAbierta:
    """Un inicio de sesión real: el access token, la cookie de refresh y el dispositivo."""

    usuario_id: UUID
    nombre_usuario: str
    dispositivo_id: UUID
    access_token: str
    cookie: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture
def limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str) -> Iterator[TestClient]:
    """Cada prueba entra desde una IP propia: las contraseñas incorrectas cuentan por IP (20 en
    15 minutos) y `intento_login` no se limpia entre pruebas."""
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    ip = f"10.{random.randint(1, 250)}.{random.randint(1, 250)}.{random.randint(1, 250)}"
    try:
        yield TestClient(app, client=(ip, 50000))
    finally:
        engine.dispose()


@pytest.fixture
def sesion_real(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion:
            yield sesion
    finally:
        engine.dispose()


class EntornoUsuarios(Entorno):
    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion)
        self.administradores = self.crear_rol("Administrador", frozenset({ADMIN}))

    # --- sesiones --------------------------------------------------------------------------

    def abrir_sesion(
        self,
        cliente: TestClient,
        usuario_id: UUID,
        nombre_usuario: str,
        *,
        dispositivo_id: UUID | None = None,
        password: str = PASSWORD,
    ) -> SesionAbierta:
        dispositivo = dispositivo_id or uuid4()
        respuesta = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": nombre_usuario,
                "contrasena": password,
                "dispositivo_id": str(dispositivo),
                "nombre_dispositivo": "Equipo",
            },
        )
        assert respuesta.status_code == 200, respuesta.text
        return SesionAbierta(
            usuario_id=usuario_id,
            nombre_usuario=nombre_usuario,
            dispositivo_id=dispositivo,
            access_token=respuesta.json()["access_token"],
            cookie=respuesta.cookies["refresh_token"],
        )

    def administrador(self, cliente: TestClient) -> SesionAbierta:
        """Un administrador activo con una sesión abierta en un dispositivo propio."""
        usuario_id, nombre = self.crear_usuario(self.administradores)
        return self.abrir_sesion(cliente, usuario_id, nombre)

    def renovar(self, cliente: TestClient, abierta: SesionAbierta) -> Any:
        return cliente.post(
            "/api/v1/auth/refresh",
            json={"dispositivo_id": str(abierta.dispositivo_id)},
            cookies={"refresh_token": abierta.cookie},
        )

    # --- pedidos ---------------------------------------------------------------------------

    def enviar(
        self,
        cliente: TestClient,
        metodo: str,
        ruta: str,
        abierta: SesionAbierta,
        cuerpo: dict[str, object] | None = None,
        *,
        operation_id: UUID | None = None,
    ) -> Any:
        return cliente.request(
            metodo,
            ruta,
            json=cuerpo,
            headers={**abierta.headers, "Operation-Id": str(operation_id or uuid4())},
        )

    # --- lecturas del estado confirmado ----------------------------------------------------

    def fila(self, sql: str, **parametros: object) -> list[dict[str, Any]]:
        self.sesion.rollback()
        resultado = self.sesion.execute(text(sql), parametros)
        return [dict(fila._mapping) for fila in resultado]

    def usuario(self, usuario_id: UUID) -> dict[str, Any]:
        (fila,) = self.fila(
            "SELECT id, usuario, nombre, email, rol_id, estado, tope_descuento_override, "
            "password_hash, pin_autorizacion_hash FROM usuario WHERE id = :u",
            u=usuario_id,
        )
        return fila

    def familias(self, usuario_id: UUID) -> list[dict[str, Any]]:
        return self.fila(
            "SELECT dispositivo_id, familia_id, revocado_en, motivo_revocacion "
            "FROM sesion_refresh WHERE usuario_id = :u ORDER BY emitido_en",
            u=usuario_id,
        )

    def familias_vigentes(self, usuario_id: UUID) -> set[UUID]:
        return {f["dispositivo_id"] for f in self.familias(usuario_id) if f["revocado_en"] is None}

    def auditorias(self, accion: str, *, entidad_id: UUID | None = None) -> list[dict[str, Any]]:
        if entidad_id is None:
            return self.fila(
                "SELECT accion, entidad, entidad_id, antes, despues, observacion, origen, "
                "operation_id, usuario_id FROM auditoria "
                "WHERE organizacion_id = :o AND accion = :a ORDER BY registered_at, id",
                o=self.org,
                a=accion,
            )
        return self.fila(
            "SELECT accion, entidad, entidad_id, antes, despues, observacion, origen, "
            "operation_id, usuario_id FROM auditoria "
            "WHERE organizacion_id = :o AND accion = :a AND entidad_id = :e "
            "ORDER BY registered_at, id",
            o=self.org,
            a=accion,
            e=entidad_id,
        )

    def comandos(self, tipo: str) -> int:
        (fila,) = self.fila(
            "SELECT count(*) AS n FROM comando WHERE organizacion_id = :o AND tipo = :t",
            o=self.org,
            t=tipo,
        )
        return int(fila["n"])

    def total_auditoria(self) -> int:
        (fila,) = self.fila(
            "SELECT count(*) AS n FROM auditoria WHERE organizacion_id = :o", o=self.org
        )
        return int(fila["n"])

    # --- rastro de un secreto ---------------------------------------------------------------

    def volcado(self, tabla: str) -> str:
        self.sesion.rollback()
        return str(
            self.sesion.execute(
                text(f"SELECT coalesce(string_agg(to_json(t)::text, ' '), '') FROM {tabla} t")
            ).scalar_one()
        )

    def sin_rastro(self, secreto: str) -> None:
        """El secreto no figura en el comando (huella y resultado incluidos), la cuarentena, la
        auditoría ni las observaciones."""
        for tabla in ("comando", "comando_cuarentena", "auditoria", "observacion"):
            assert secreto not in self.volcado(tabla), tabla
