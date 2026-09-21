"""Tarea 7.5 (`02` §17): ni la contraseña, ni el PIN, ni ningún token
(access, refresh, ni sus derivaciones) aparecen en los registros producidos
por una petición de autenticación real, en ningún nivel.

Depende del servicio de login (tarea 8.3) y del endpoint `/auth` (tarea
10.6), ambos ya implementados: hasta que existieran, esta prueba no podía
escribirse contra una petición HTTP real (solo quedaba disponible a nivel
de mensaje de log aislado, que no es el escenario pedido).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-secreta-999"
JWT_SECRET = "secreto-de-prueba-logs"


@pytest.fixture
def cliente(database_url: str) -> TestClient:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    return TestClient(crear_app(settings))


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion):
    factory = crear_session_factory(crear_engine(database_url))
    with factory() as sesion_real:
        yield sesion_real


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str):
    from sqlalchemy import text

    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _crear_organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=slug,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def _crear_usuario(sesion: Session, organizacion_id, *, nombre_usuario: str):
    from decimal import Decimal

    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    return repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario,
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )


def _texto_completo_de(caplog: pytest.LogCaptureFixture) -> str:
    """Todo lo que un handler de logging podría haber emitido: el mensaje ya
    formateado, más cualquier atributo `extra` adjunto al `LogRecord`. Un dato
    filtrado por `extra` sin aparecer en el mensaje seguiría constituyendo una
    fuga (`02` §17 no distingue el campo)."""
    partes: list[str] = []
    for registro in caplog.records:
        partes.append(registro.getMessage())
        partes.append(repr(registro.__dict__))
    return "\n".join(partes)


class TestLaContrasenaNuncaQuedaRegistrada:
    def test_un_login_exitoso_no_registra_la_contrasena_ni_los_tokens(
        self, cliente: TestClient, sesion: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Escenario "La contraseña nunca queda registrada" (camino
        feliz): ni la contraseña en claro, ni el access token emitido, ni el
        refresh token de la cookie aparecen en ningún registro."""
        organizacion = _crear_organizacion(sesion, "org-logs-1")
        _crear_usuario(sesion, organizacion.id, nombre_usuario="vendedor1")
        sesion.commit()

        with caplog.at_level(logging.DEBUG):
            respuesta = cliente.post(
                "/api/v1/auth/login",
                json={
                    "organizacion_slug": "org-logs-1",
                    "usuario": "vendedor1",
                    "contrasena": PASSWORD,
                    "dispositivo_id": str(uuid4()),
                    "nombre_dispositivo": "Tablet",
                },
            )

        assert respuesta.status_code == 200
        access_token = respuesta.json()["access_token"]
        refresh_token = respuesta.cookies["refresh_token"]

        texto = _texto_completo_de(caplog)
        assert PASSWORD not in texto
        assert access_token not in texto
        assert refresh_token not in texto

    def test_un_login_fallido_tampoco_registra_la_contrasena_provista(
        self, cliente: TestClient, sesion: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Escenario "El PIN nunca queda registrado" tratado por extensión al
        único secreto disponible en este flujo (una contraseña incorrecta):
        el rechazo tampoco debe filtrar el valor recibido, ni en un mensaje
        de error ni en una traza."""
        organizacion = _crear_organizacion(sesion, "org-logs-2")
        _crear_usuario(sesion, organizacion.id, nombre_usuario="vendedor1")
        sesion.commit()
        contrasena_incorrecta_pero_distintiva = "clave-incorrecta-marca-de-agua-777"

        with caplog.at_level(logging.DEBUG):
            respuesta = cliente.post(
                "/api/v1/auth/login",
                json={
                    "organizacion_slug": "org-logs-2",
                    "usuario": "vendedor1",
                    "contrasena": contrasena_incorrecta_pero_distintiva,
                    "dispositivo_id": str(uuid4()),
                    "nombre_dispositivo": "Tablet",
                },
            )

        assert respuesta.status_code == 401
        texto = _texto_completo_de(caplog)
        assert contrasena_incorrecta_pero_distintiva not in texto
