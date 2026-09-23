"""Change 05, grupo 9, tarea 9.7 (D12): `GET /api/v1/configuracion/alicuotas`.

Mismo arnés HTTP que `test_catalogo_api.py` (Postgres real, `cliente` con
motor propio, login real -- nunca un access token fabricado a mano).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.configuracion import repository as configuracion_repository
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-configuracion-api"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    """Cierra explícitamente el `Engine` propio de `crear_app` al terminar
    (recuperado vía `dependency_overrides`): sin esto, el pool de conexiones
    queda vivo hasta que el recolector de ciclos de CPython lo alcance, y una
    corrida completa de la suite agota `max_connections` de Postgres antes
    de eso."""
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
    sesion: Session, organizacion_id: UUID, *, permisos: frozenset[str], nombre_usuario: str
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


def _con_gestionar_catalogo(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset({"GESTIONAR_CATALOGO"}),
        nombre_usuario=nombre_usuario,
    )


class TestListarAlicuotas:
    def test_con_el_permiso_devuelve_activas_e_inactivas_con_valor_como_string(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-conf-1")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        configuracion_repository.crear_alicuota(
            organizacion.id, sesion, nombre="21%", valor=Decimal("0.210000"), momento=MOMENTO
        )
        configuracion_repository.crear_alicuota(
            organizacion.id,
            sesion,
            nombre="27%",
            valor=Decimal("0.270000"),
            momento=MOMENTO,
            activo=False,
        )
        sesion.commit()
        access_token = _login(cliente, "org-conf-1", "admin1")

        respuesta = cliente.get(
            "/api/v1/configuracion/alicuotas",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        items = {item["nombre"]: item for item in cuerpo["items"]}
        assert items["21%"]["activo"] is True
        assert items["21%"]["valor"] == "0.210000"
        assert items["27%"]["activo"] is False
        assert items["27%"]["valor"] == "0.270000"

    def test_sin_el_permiso_se_rechaza_con_403(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-conf-2")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-conf-2", "vendedor1")

        respuesta = cliente.get(
            "/api/v1/configuracion/alicuotas",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_limite_y_cursor_siguiente_recorren_todas_las_paginas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-conf-3")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        for nombre in ("10,5%", "21%", "27%"):
            configuracion_repository.crear_alicuota(
                organizacion.id, sesion, nombre=nombre, valor=Decimal("0.100000"), momento=MOMENTO
            )
        sesion.commit()
        access_token = _login(cliente, "org-conf-3", "admin1")
        headers = {"Authorization": f"Bearer {access_token}"}

        nombres_vistos: list[str] = []
        cursor: str | None = None
        for _ in range(10):
            params = {"limite": 1}
            if cursor is not None:
                params["cursor"] = cursor
            respuesta = cliente.get(
                "/api/v1/configuracion/alicuotas", headers=headers, params=params
            )
            assert respuesta.status_code == 200
            cuerpo = respuesta.json()
            assert len(cuerpo["items"]) == 1
            nombres_vistos.append(cuerpo["items"][0]["nombre"])
            cursor = cuerpo["cursor_siguiente"]
            if cursor is None:
                break

        assert nombres_vistos == ["10,5%", "21%", "27%"]


class TestAislamientoInv21:
    """Tarea 11.5 (change 05, D12): INV-21 -- cada organización lista solo
    sus propias alícuotas, con login real de dos organizaciones. Cubre la
    tupla `("get", "/api/v1/configuracion/alicuotas")` de
    `COBERTURA_DE_AISLAMIENTO` en `test_inv21_ratchet_rutas.py`."""

    def test_cada_organizacion_lista_solo_sus_propias_alicuotas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-conf-inv21-a")
        organizacion_b = _crear_organizacion(sesion, "org-conf-inv21-b")
        _con_gestionar_catalogo(sesion, organizacion_a.id, nombre_usuario="admin-a")
        _con_gestionar_catalogo(sesion, organizacion_b.id, nombre_usuario="admin-b")
        alicuota_a = configuracion_repository.crear_alicuota(
            organizacion_a.id, sesion, nombre="21%", valor=Decimal("0.210000"), momento=MOMENTO
        )
        alicuota_b = configuracion_repository.crear_alicuota(
            organizacion_b.id, sesion, nombre="27%", valor=Decimal("0.270000"), momento=MOMENTO
        )
        sesion.commit()
        access_token_a = _login(cliente, "org-conf-inv21-a", "admin-a")

        respuesta = cliente.get(
            "/api/v1/configuracion/alicuotas",
            headers={"Authorization": f"Bearer {access_token_a}"},
            params={"limite": 100},
        )

        assert respuesta.status_code == 200
        ids_vistos = {item["id"] for item in respuesta.json()["items"]}
        assert str(alicuota_a.id) in ids_vistos
        assert str(alicuota_b.id) not in ids_vistos
