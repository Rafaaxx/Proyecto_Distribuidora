"""Entrada REST del bus de comandos: el encabezado `Operation-Id` (change
04, grupo 7, tareas 7.1, 7.2, 7.4, 7.5; `design.md` D4, `02` §6.2, §11).

No hay todavía ningún endpoint de negocio real que pase por el bus (el
grupo 11 -- los tres handlers de maestros -- es el siguiente en la
secuencia y está fuera del alcance de este grupo). Estas pruebas agregan
una ruta ficticia a una instancia real de `crear_app` (mismo patrón que
`tests/integration/test_ratchet_permiso_por_ruta.py`), usando
`requiere_comando_online` (`app.core.autenticacion`),
`construir_sobre_online` (`app.commands.sobre`) y
`sync_service.procesar_comando` (grupo 6) tal como lo haría un endpoint
real -- para probar la dependencia de FastAPI y su composición con
permisos y aislamiento, no la lógica de negocio (que no existe todavía).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands.huella import calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import EntradaComandoOnline, requiere_comando_online
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import DomainError
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-123"
JWT_SECRET = "secreto-de-prueba-entrada-rest"

# Simula la "tabla" de un recurso de negocio para el escenario SEG-07 (7.5):
# cada recurso ficticio pertenece a una organización fija.
_RECURSOS_POR_ORGANIZACION: dict[str, object] = {}


class RecursoNoEncontradoError(DomainError):
    """Mismo patrón que `identidad/api.py::RecursoNoEncontradoError`: un
    recurso de otra organización responde 404, nunca 403 (SEG-07, INV-21)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class _CuerpoEco(BaseModel):
    mensaje: str
    modo: str | None = None


def _endpoint_eco(
    recurso_id: str,
    datos: _CuerpoEco,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online("GESTIONAR_DISPOSITIVOS"))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    """Ruta ficticia de escritura: arma el sobre, calcula la huella y llama
    al bus -- exactamente lo que hará un endpoint real desde el grupo 11."""
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRUEBA_ECO",
        version=1,
        modo=datos.modo or "ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"mensaje": datos.mensaje},
    )
    huella = calcular_huella(sobre.contenido)

    def _verificar_permiso() -> None:
        organizacion_del_recurso = _RECURSOS_POR_ORGANIZACION.get(recurso_id)
        if (
            organizacion_del_recurso is not None
            and organizacion_del_recurso != entrada.contexto.organizacion_id
        ):
            raise RecursoNoEncontradoError(
                f"El recurso {recurso_id} no existe en esta organización."
            )

    def _handler(_sesion: object) -> sync_service.ResultadoHandler:
        return "ACEPTADO", {"mensaje": datos.mensaje}, None

    comando = sync_service.procesar_comando(
        sesion,
        FixedClock(MOMENTO),
        sobre=sobre,
        huella=huella,
        verificar_permiso=_verificar_permiso,
        ejecutar_handler=_handler,
    )
    return {"estado": comando.estado, "resultado": comando.resultado}


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    _RECURSOS_POR_ORGANIZACION.clear()
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _crear_organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba entrada REST",
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


def _crear_usuario(sesion: Session, organizacion_id, *, permisos: frozenset[str], nombre: str):
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in permisos:
        identidad_repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre,
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario


@pytest.fixture
def cliente(database_url: str) -> TestClient:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    app.add_api_route(
        "/api/v1/pruebas-comandos/{recurso_id}/eco",
        _endpoint_eco,
        methods=["POST"],
    )
    return TestClient(app)


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


class TestOperationIdObligatorio:
    """Tareas 7.1 y 7.2."""

    def test_una_escritura_sin_operation_id_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Una escritura sin identificador de operación se
        rechaza": el usuario SÍ tiene el permiso, pero no informa el
        encabezado."""
        organizacion = _crear_organizacion(sesion, f"org-rest-7.1-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}), nombre="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{uuid4()}/eco",
            json={"mensaje": "hola"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_un_operation_id_que_no_es_un_uuid_valido_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Un identificador de operación que no es un
        identificador válido se rechaza"."""
        organizacion = _crear_organizacion(sesion, f"org-rest-7.2-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}), nombre="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{uuid4()}/eco",
            json={"mensaje": "hola"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": "no-es-un-uuid",
            },
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_INVALIDO"

    def test_con_operation_id_valido_la_escritura_se_procesa(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Contraparte positiva: con el encabezado presente y válido, la
        petición llega al bus y se acepta."""
        organizacion = _crear_organizacion(sesion, f"org-rest-7.1b-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}), nombre="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{uuid4()}/eco",
            json={"mensaje": "hola"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["estado"] == "ACEPTADO"


class TestModoOfflineRechazadoPorRest:
    """Tarea 7.4, escenario "Un endpoint REST directo no acepta modo
    OFFLINE"."""

    def test_un_comando_declarado_offline_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rest-7.4-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}), nombre="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{uuid4()}/eco",
            json={"mensaje": "hola", "modo": "OFFLINE"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "MODO_NO_ADMITIDO_POR_REST"


class TestPermisosDelBus:
    """Tarea 7.5: un permiso faltante rechaza antes de que el handler
    produzca efectos, y un recurso de otra organización responde 404."""

    def test_un_usuario_sin_el_permiso_no_ejecuta_el_comando(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Un usuario sin el permiso no ejecuta el comando"
        (SEG-06). La dependencia REST rechaza antes de que la petición
        alcance el bus: ningún `comando` queda registrado."""
        organizacion = _crear_organizacion(sesion, f"org-rest-7.5a-{uuid4().hex[:8]}")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre="vendedor1")
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{uuid4()}/eco",
            json={"mensaje": "hola"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(operation_id),
            },
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        from sqlalchemy import func, select

        from app.modules.sync.models import Comando

        assert (
            sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.operation_id == operation_id)
            )
            == 0
        )

    def test_un_comando_sobre_un_recurso_de_otra_organizacion_no_revela_su_existencia(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Un comando sobre un recurso de otra organización no
        revela su existencia" (SEG-07, INV-21, TR-08): 404, no 403."""
        organizacion_a = _crear_organizacion(sesion, f"org-rest-7.5b-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(sesion, f"org-rest-7.5b-b-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion,
            organizacion_b.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre="admin_b",
        )
        sesion.commit()
        access_token = _login(cliente, organizacion_b.slug, "admin_b")

        recurso_ajeno = str(uuid4())
        _RECURSOS_POR_ORGANIZACION[recurso_ajeno] = organizacion_a.id

        respuesta = cliente.post(
            f"/api/v1/pruebas-comandos/{recurso_ajeno}/eco",
            json={"mensaje": "hola"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
