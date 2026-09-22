"""Tarea 12.2 (cierre de INV-21 para el grupo 10.7): cobertura de
aislamiento de los endpoints de `identidad` que `test_identidad_api_usuarios.py`
todavía no ejercita con dos organizaciones reales -- listado y revocación de
dispositivos, listado de usuarios, y alta de usuario con un `rol_id` de otra
organización.

Mismo arnés HTTP que `test_auth_api.py`/`test_identidad_api_usuarios.py`
(Postgres real, `cliente` con motor propio, limpieza explícita porque
confirma transacciones) y mismo criterio: dos organizaciones, cada una con
su propio usuario autenticado por un login real (nunca un access token
fabricado a mano) -- `design.md` D1 del change 02, tarea 12.1.

Cita INV-21 y SEG-07 en cada escenario cruzado, como pide la tarea 12.2.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento"


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


class TestAislamientoDeDispositivos:
    """Escenarios "Leer un recurso ajeno responde como inexistente",
    "Modificar un recurso ajeno no lo cambia" y "Revocar un dispositivo de
    otra organización no lo encuentra" (spec `dispositivos` y
    `aislamiento-multiorganizacion`). Regla: INV-21, SEG-07."""

    def test_listar_dispositivos_no_incluye_los_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-1a")
        org_b = _crear_organizacion(sesion, "org-iso-1b")
        identidad_service.registrar_dispositivo(
            org_a.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet A"
        )
        _crear_usuario(
            sesion,
            org_b.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin_b",
        )
        sesion.commit()
        # El propio login de `admin_b` registra un dispositivo en `org_b`
        # (SEG-02, tarea 8.3): la lista de `org_b` no queda vacía, pero debe
        # excluir "Tablet A" (de `org_a`) por completo.
        access_token = _login(cliente, "org-iso-1b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        nombres = {fila["nombre"] for fila in respuesta.json()}
        assert "Tablet A" not in nombres
        assert nombres == {"PC"}

    def test_revocar_un_dispositivo_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """SEG-07/INV-21: un dispositivo ajeno responde "no encontrado" y
        sigue activo -- no un 204 silencioso (spec `dispositivos`, escenario
        homónimo)."""
        org_a = _crear_organizacion(sesion, "org-iso-2a")
        org_b = _crear_organizacion(sesion, "org-iso-2b")
        dispositivo_a = identidad_service.registrar_dispositivo(
            org_a.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet A"
        )
        _crear_usuario(
            sesion,
            org_b.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin_b",
        )
        sesion.commit()
        access_token = _login(cliente, "org-iso-2b", "admin_b")

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_a.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        sesion.refresh(dispositivo_a)
        assert dispositivo_a.estado == "ACTIVO"


class TestAislamientoDeUsuarios:
    """Escenarios "Leer un recurso ajeno responde como inexistente" y
    "Modificar un recurso ajeno no lo cambia" sobre `/identidad/usuarios`.
    Regla: INV-21, SEG-07."""

    def test_listar_usuarios_no_incluye_los_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-3a")
        org_b = _crear_organizacion(sesion, "org-iso-3b")
        _crear_usuario(sesion, org_a.id, permisos=frozenset(), nombre_usuario="vendedor_a")
        _crear_usuario(
            sesion, org_b.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin_b"
        )
        sesion.commit()
        access_token = _login(cliente, "org-iso-3b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/identidad/usuarios",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        nombres = {fila["usuario"] for fila in respuesta.json()}
        assert nombres == {"admin_b"}

    def test_dar_de_alta_un_usuario_con_un_rol_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Un `rol_id` que pertenece a la organización A, informado por un
        actor de la organización B: la FK compuesta (`03` §2.4) impediría
        la escritura en la base, pero la respuesta debe ser "no encontrado"
        (SEG-07), nunca un error de infraestructura -- mismo criterio que
        `cambiar_composicion_rol`/`establecer_pin_autorizacion`/
        `revocar_dispositivo` (tarea 10.7)."""
        org_a = _crear_organizacion(sesion, "org-iso-4a")
        org_b = _crear_organizacion(sesion, "org-iso-4b")
        rol_de_a = repository.crear_rol(
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
        access_token = _login(cliente, "org-iso-4b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "intruso",
                "nombre": "Intruso",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol_de_a.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        # No debe quedar creado ningún usuario "intruso" en ninguna organización.
        assert repository.obtener_usuario_por_nombre_usuario(org_a.id, "intruso", sesion) is None
        assert repository.obtener_usuario_por_nombre_usuario(org_b.id, "intruso", sesion) is None


class TestLaFaltaDePermisoSeDistingueDeUnRecursoAjeno:
    """Escenario "La falta de permiso se distingue de un recurso ajeno"
    (tarea 12.3, spec `autorizacion-por-permiso`): la ocultación es por
    organización (404), no por permiso (403) -- un usuario sin el permiso
    requerido sobre un recurso de SU PROPIA organización debe enterarse de
    que le falta el permiso, no creer que el recurso no existe. Regla:
    SEG-06, SEG-07."""

    def test_sin_permiso_sobre_recurso_propio_es_403_no_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-iso-5")
        usuario_sin_permiso, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        dispositivo_propio = identidad_service.registrar_dispositivo(
            organizacion.id,
            sesion,
            FixedClock(MOMENTO),
            dispositivo_id=nuevo_id(),
            nombre="Tablet propia",
        )
        sesion.commit()
        access_token = _login(cliente, "org-iso-5", "vendedor1")

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_propio.id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        sesion.refresh(dispositivo_propio)
        assert dispositivo_propio.estado == "ACTIVO"

    def test_con_permiso_sobre_recurso_ajeno_es_404_no_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """La mitad simétrica del caso anterior, con el mismo par de
        organizaciones que estructura la spec: un usuario CON el permiso
        pero sobre un recurso AJENO también debe ser 404, nunca 403 (la
        ocultación es por organización, no por permiso)."""
        org_a = _crear_organizacion(sesion, "org-iso-6a")
        org_b = _crear_organizacion(sesion, "org-iso-6b")
        dispositivo_a = identidad_service.registrar_dispositivo(
            org_a.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet A"
        )
        _crear_usuario(
            sesion,
            org_b.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin_b",
        )
        sesion.commit()
        access_token = _login(cliente, "org-iso-6b", "admin_b")

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_a.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
