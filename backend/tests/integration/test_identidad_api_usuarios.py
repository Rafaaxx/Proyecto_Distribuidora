"""Tarea 10.7: endpoints de negocio de identidad -- alta de usuarios,
composición de roles y rotación de PIN, cada uno con su permiso declarado
(`ADMIN_USUARIOS`, `01` §19). Tarea 10.8: ninguna respuesta de lectura de
usuario contiene la contraseña ni su derivación.

Sigue el mismo arnés HTTP que `test_auth_api.py` (Postgres real, `cliente`
con motor propio, limpieza explícita porque confirma transacciones)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-usuarios"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
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


def _crear_usuario(
    sesion: Session, organizacion_id, *, permisos: frozenset[str], nombre_usuario: str
):
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in permisos:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = repository.crear_usuario(
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
    return usuario, rol


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


def _login(cliente: TestClient, slug: str, usuario: str) -> str:
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


class TestCrearUsuario:
    def test_un_usuario_con_admin_usuarios_puede_dar_de_alta_un_usuario(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-1")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-1", "admin1")

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor1",
                "nombre": "Vendedor Uno",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["usuario"] == "vendedor1"
        # Tarea 10.8: ninguna respuesta de lectura -- ni de escritura --
        # contiene la contraseña ni su derivación.
        assert "password" not in cuerpo
        assert "password_hash" not in cuerpo
        assert "otra-contrasena-larga-456" not in respuesta.text

    def test_dar_de_alta_un_usuario_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-2")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-2", "vendedor1")

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor2",
                "nombre": "Vendedor Dos",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


class TestListarUsuarios:
    def test_listar_usuarios_nunca_incluye_la_contrasena_ni_su_derivacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "La contraseña no se puede recuperar del sistema"
        (tarea 10.8)."""
        organizacion = _crear_organizacion(sesion, "org-usr-3")
        _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-usr-3", "admin1")

        respuesta = cliente.get(
            "/api/v1/identidad/usuarios",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert len(cuerpo) == 2
        for fila in cuerpo:
            assert "password" not in fila
            assert "password_hash" not in fila
            assert "pin_autorizacion_hash" not in fila
            assert "pin_autorizacion_sal" not in fila
        assert PASSWORD not in respuesta.text

    def test_listar_usuarios_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-4")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-usr-4", "vendedor1")

        respuesta = cliente.get(
            "/api/v1/identidad/usuarios",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403


class TestComposicionDeRol:
    def test_cambiar_la_composicion_de_un_rol(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-5")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-5", "admin1")

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES", "VER_REPORTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 200
        assert set(respuesta.json()["permisos"]) == {"GESTIONAR_CLIENTES", "VER_REPORTES"}

    def test_cambiar_composicion_de_rol_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """SEG-07/INV-21: un rol ajeno responde "no encontrado"."""
        org_a = _crear_organizacion(sesion, "org-usr-6a")
        org_b = _crear_organizacion(sesion, "org-usr-6b")
        rol_ajeno = repository.crear_rol(
            org_a.id,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de A",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        _crear_usuario(
            sesion, org_b.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin_b"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-6b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol_ajeno.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert set(repository.listar_permisos_de_rol(org_a.id, rol_ajeno.id, sesion)) == set()

    def test_cambiar_composicion_de_rol_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-7")
        usuario, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-7", "vendedor1")

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403


class TestRotacionDePin:
    def test_rotar_el_pin_de_un_supervisor(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-8")
        _, rol_admin = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        usuario_supervisor, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"AUTORIZAR_DESCUENTO"}),
            nombre_usuario="supervisor1",
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-8", "admin1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 204
        assert "654321" not in respuesta.text

    def test_rotar_el_pin_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-9")
        usuario_actor, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        usuario_supervisor, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"AUTORIZAR_DESCUENTO"}),
            nombre_usuario="supervisor1",
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-9", "vendedor1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403

    def test_rotar_el_pin_de_un_usuario_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-usr-10a")
        org_b = _crear_organizacion(sesion, "org-usr-10b")
        usuario_supervisor_a, _ = _crear_usuario(
            sesion,
            org_a.id,
            permisos=frozenset({"AUTORIZAR_DESCUENTO"}),
            nombre_usuario="supervisor_a",
        )
        _crear_usuario(
            sesion, org_b.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin_b"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-10b", "admin_b")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_supervisor_a.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404


class TestDesbloqueoManualDeLogin:
    """Tarea 11.4 (segunda mitad), endpoint de `POST .../desbloqueo`."""

    def test_desbloquear_un_usuario_con_admin_usuarios(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-11")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        usuario_bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-11", "admin1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 204

    def test_desbloquear_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-usr-12")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        usuario_objetivo, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor2"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-12", "vendedor1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_objetivo.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403

    def test_desbloquear_un_usuario_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-usr-13a")
        org_b = _crear_organizacion(sesion, "org-usr-13b")
        usuario_a, _ = _crear_usuario(
            sesion, org_a.id, permisos=frozenset(), nombre_usuario="vendedor_a"
        )
        _crear_usuario(
            sesion, org_b.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin_b"
        )
        sesion.commit()
        access_token = _login(cliente, "org-usr-13b", "admin_b")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{usuario_a.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
