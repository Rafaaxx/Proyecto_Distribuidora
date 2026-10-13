"""ADR-028 / D9.1-D9.2 a nivel HTTP (grupo 2 del change 06b): con el access
token vigente de un usuario que pasa a `INACTIVO`, o cuyo rol se desactiva,
toda ruta de negocio (lectura o escritura) rechaza en la petición siguiente,
sin esperar a que venza el access token -- misma lógica que ADR-017 para un
permiso quitado.

Login real, nunca un access token fabricado a mano (mismo criterio que el
ratchet de aislamiento INV-21). Usa el patrón `cliente`/`sesion` de
`test_auth_api.py` (dos engines sobre la misma base real, confirmando con
`commit()`), porque necesita mutar `usuario.estado`/`rol.activo` DESPUÉS de
loguearse y que la app (con su propio engine) vea el cambio.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad.models import Auditoria, Organizacion, SesionRefresh, Usuario
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-inactivo-123"
JWT_SECRET = "secreto-de-prueba-sesion-inactivo"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    """Mismo criterio que `test_auth_api.py`: estas pruebas confirman
    transacciones reales, así que limpian explícitamente al terminar."""
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


def _crear_usuario_admin(sesion: Session, organizacion_id, nombre_usuario: str) -> Usuario:
    """Rol con `GESTIONAR_DISPOSITIVOS` y `ADMIN_USUARIOS`, para ejercer
    tanto la lectura (`GET /identidad/dispositivos`) como la escritura
    (`POST /identidad/usuarios`) con el mismo usuario."""
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba D9",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for permiso in ("GESTIONAR_DISPOSITIVOS", "ADMIN_USUARIOS"):
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=permiso
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


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


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


def _crear_usuario_request(rol_id) -> dict[str, object]:
    return {
        "usuario": f"nuevo-{uuid4().hex[:8]}",
        "nombre": "Usuario nuevo",
        "email": None,
        "password": "otra-contrasena-larga-123",
        "rol_id": str(rol_id),
    }


class TestUsuarioInactivo:
    def test_lectura_responde_401_no_403(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-inactivo-lectura-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-inactivo-1")
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, usuario.usuario)

        sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

    def test_escritura_responde_401_y_no_deja_filas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-inactivo-escritura-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-inactivo-2")
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, usuario.usuario)

        sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json=_crear_usuario_request(usuario.rol_id),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

        sesion.expire_all()
        assert (
            sesion.execute(
                select(func.count())
                .select_from(Comando)
                .where(Comando.organizacion_id == organizacion.id)
            ).scalar_one()
            == 0
        )
        assert (
            sesion.execute(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.organizacion_id == organizacion.id, Auditoria.accion == "ALTA_USUARIO"
                )
            ).scalar_one()
            == 0
        )

    def test_reactivar_el_usuario_deja_pasar_el_mismo_access_token(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Triangulación: el efecto es por petición (ADR-017), no una
        marca permanente sobre el token."""
        organizacion = _crear_organizacion(sesion, f"org-inactivo-reactivar-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-inactivo-3")
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, usuario.usuario)

        sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()
        rechazo = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert rechazo.status_code == 401

        sesion.execute(
            text("UPDATE usuario SET estado = 'ACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()

        aceptado = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert aceptado.status_code == 200


class TestRolInactivo:
    def test_lectura_responde_401_con_rol_desactivado(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """ADR-028 D9.4-A: mismo tratamiento que un usuario inactivo."""
        organizacion = _crear_organizacion(sesion, f"org-rol-inactivo-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-rol-1")
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, usuario.usuario)

        sesion.execute(
            text("UPDATE rol SET activo = false WHERE id = :id"), {"id": str(usuario.rol_id)}
        )
        sesion.commit()

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"


def _login_con_cookie(
    cliente: TestClient, slug: str, usuario: str, dispositivo_id: str
) -> tuple[str, str]:
    """`(access_token, cookie_refresh)` de un inicio de sesión real en `dispositivo_id`."""
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": dispositivo_id,
            "nombre_dispositivo": "Tablet",
        },
    )
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"], respuesta.cookies["refresh_token"]


def _renovar_http(cliente: TestClient, cookie: str, dispositivo_id: str):
    return cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": cookie},
    )


class TestInactivoConJornadaAbiertaDePuntaAPunta:
    """Change 15, tarea 12.3 (`design.md` D18, D19; ADR-028 D9.3-B): por HTTP y con login real,
    un usuario dado de baja con jornada abierta renueva su sesión, pero el token resultante no
    abre nada salvo el lote de sincronización; al cerrar la jornada la renovación se rechaza."""

    def test_renueva_el_token_no_abre_rutas_de_negocio_y_muere_al_cerrar_la_jornada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-inactivo-jornada-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-jornada-1")
        sesion.commit()
        dispositivo_id = str(uuid4())
        _, cookie = _login_con_cookie(cliente, organizacion.slug, usuario.usuario, dispositivo_id)

        ubicacion_id = crear_ubicacion_sql(
            sesion, organizacion.id, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
        )
        jornada_id = crear_jornada_sql(
            sesion,
            organizacion.id,
            usuario_id=usuario.id,
            dispositivo_id=UUID(dispositivo_id),
            ubicacion_id=ubicacion_id,
        )
        sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()

        # Renueva por la excepción: token nuevo, refresh rotado.
        renovada = _renovar_http(cliente, cookie, dispositivo_id)
        assert renovada.status_code == 200
        token = renovada.json()["access_token"]
        cookie_rotada = renovada.cookies["refresh_token"]
        assert cookie_rotada != cookie
        cabecera = {"Authorization": f"Bearer {token}"}

        # El token no abre `GET /yo` ni una ruta de negocio...
        for ruta in ("/api/v1/yo", "/api/v1/identidad/dispositivos"):
            rechazo = cliente.get(ruta, headers=cabecera)
            assert rechazo.status_code == 401, ruta
            assert rechazo.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"
        # ... y el lote de sincronización no lo rechaza por ruta.
        lote = cliente.post("/api/v1/sync/comandos", json={"items": []}, headers=cabecera)
        assert lote.status_code == 200

        # SEG-01: con credenciales correctas, el inactivo no inicia sesión.
        login = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": organizacion.slug,
                "usuario": usuario.usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": dispositivo_id,
                "nombre_dispositivo": "Tablet",
            },
        )
        assert login.status_code == 401
        assert login.json()["codigo"] == "IDENTIDAD_CREDENCIALES_INVALIDAS"

        # La renovación dejó su auditoría.
        auditorias = sesion.execute(
            select(func.count())
            .select_from(Auditoria)
            .where(
                Auditoria.organizacion_id == organizacion.id,
                Auditoria.accion == "RENOVAR_SESION_CON_JORNADA_PENDIENTE",
            )
        ).scalar_one()
        assert auditorias == 1

        # Al cerrarse la jornada, la renovación siguiente se rechaza y no queda sesión viva.
        sesion.execute(
            text(
                "UPDATE jornada SET estado = 'CERRADA', rendida_en = :m, rendida_por_id = :u, "
                "cerrada_en = :m, cerrada_por_id = :u WHERE id = :id"
            ),
            {"m": MOMENTO, "u": usuario.id, "id": jornada_id},
        )
        sesion.commit()
        rechazada = _renovar_http(cliente, cookie_rotada, dispositivo_id)
        assert rechazada.status_code == 401
        sesion.expire_all()
        vigentes = sesion.execute(
            select(func.count())
            .select_from(SesionRefresh)
            .where(SesionRefresh.usuario_id == usuario.id, SesionRefresh.revocado_en.is_(None))
        ).scalar_one()
        assert vigentes == 0

    def test_sin_jornada_el_inactivo_no_renueva_como_hoy(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-inactivo-sin-jor-{uuid4().hex[:8]}")
        usuario = _crear_usuario_admin(sesion, organizacion.id, "admin-jornada-2")
        sesion.commit()
        dispositivo_id = str(uuid4())
        _, cookie = _login_con_cookie(cliente, organizacion.slug, usuario.usuario, dispositivo_id)
        sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario.id)}
        )
        sesion.commit()

        assert _renovar_http(cliente, cookie, dispositivo_id).status_code == 401
