"""Change 04, grupo 11 y grupo 14 (`design.md` D7, ADR-022): los cinco
handlers de maestros de `identidad/commands.py` (`USUARIO_CREAR`,
`DISPOSITIVO_REVOCAR`, `PIN_AUTORIZACION_ROTAR` -- grupo 11 -- y
`ROL_PERMISOS_CAMBIAR`, `USUARIO_DESBLOQUEAR` -- grupo 14, decisión del
usuario 2026-09-22, `tasks.md` 14.3-14.6) y los endpoints que ahora delegan
en el bus (`identidad/api.py`).

Mismo arnés HTTP que `test_bus_entrada_rest.py`/`test_identidad_api_usuarios.py`
(Postgres real, `cliente` con motor propio). Cada clase cubre los 5
escenarios comunes:

1. Sin `Operation-Id` se rechaza.
2. Reenvío idéntico (misma huella) no duplica el efecto ni la auditoría.
3. Reenvío con contenido distinto -> `COMANDO_INCONSISTENTE`.
4. Sin permiso se rechaza sin efectos.
5. Queda auditado con su `operation_id` (una sola fila, ADR-022).

Más los extras propios de cada operación: dispositivos corta la sesión al
revocar; PIN nunca aparece en claro en ningún error ni resultado guardado;
cambio de composición de rol deja los permisos exactamente como se pidió;
desbloqueo permite iniciar sesión de nuevo.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad.models import Auditoria, Organizacion
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-123"
JWT_SECRET = "secreto-de-prueba-comandos-maestros"


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
        nombre=f"Rol de {nombre_usuario}",
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


def _contar_auditoria(sesion: Session, organizacion_id, *, accion: str) -> int:
    return sesion.execute(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.organizacion_id == organizacion_id, Auditoria.accion == accion)
    ).scalar_one()


def _contar_comandos(sesion: Session, operation_id) -> int:
    return sesion.execute(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    ).scalar_one()


class TestUsuarioCrear:
    def test_sin_operation_id_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-uc-1-{uuid4().hex[:8]}")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor1",
                "nombre": "Vendedor Uno",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert (
            repository.obtener_usuario_por_nombre_usuario(organizacion.id, "vendedor1", sesion)
            is None
        )

    def test_reenviar_el_alta_no_crea_un_segundo_usuario(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-uc-2-{uuid4().hex[:8]}")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())
        cuerpo = {
            "usuario": "vendedor2",
            "nombre": "Vendedor Dos",
            "email": None,
            "password": "otra-contrasena-larga-456",
            "rol_id": str(rol.id),
        }

        primera = cliente.post(
            "/api/v1/identidad/usuarios",
            json=cuerpo,
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.post(
            "/api/v1/identidad/usuarios",
            json=cuerpo,
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 201
        assert segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        usuarios = [
            u
            for u in repository.listar_usuarios(organizacion.id, sesion)
            if u.usuario == "vendedor2"
        ]
        assert len(usuarios) == 1

    def test_reenviar_con_otro_contenido_se_rechaza_como_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-uc-3-{uuid4().hex[:8]}")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor3",
                "nombre": "Vendedor Tres",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor-distinto",
                "nombre": "Vendedor Tres",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 201
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert (
            repository.obtener_usuario_por_nombre_usuario(
                organizacion.id, "vendedor-distinto", sesion
            )
            is None
        )

    def test_sin_permiso_se_rechaza_sin_efectos(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-uc-4-{uuid4().hex[:8]}")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor4",
                "nombre": "Vendedor Cuatro",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert (
            repository.obtener_usuario_por_nombre_usuario(organizacion.id, "vendedor4", sesion)
            is None
        )
        assert _contar_comandos(sesion, operation_id) == 0

    def test_el_alta_queda_auditada_con_su_operation_id_una_sola_vez(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-uc-5-{uuid4().hex[:8]}")
        _, rol = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = uuid4()

        respuesta = cliente.post(
            "/api/v1/identidad/usuarios",
            json={
                "usuario": "vendedor5",
                "nombre": "Vendedor Cinco",
                "email": None,
                "password": "otra-contrasena-larga-456",
                "rol_id": str(rol.id),
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 201
        # ADR-022: una sola fila -- la del bus (`accion=sobre.tipo`), no la
        # interna del servicio (que quedó desactivada con `auditar=False`).
        assert _contar_auditoria(sesion, organizacion.id, accion="USUARIO_CREAR") == 1
        assert _contar_auditoria(sesion, organizacion.id, accion="ALTA_USUARIO") == 0
        fila = sesion.execute(
            select(Auditoria).where(
                Auditoria.organizacion_id == organizacion.id, Auditoria.accion == "USUARIO_CREAR"
            )
        ).scalar_one()
        assert fila.operation_id == operation_id
        assert fila.origen == "COMANDO"


class TestDispositivoRevocar:
    def test_sin_operation_id_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-dr-1-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin1",
        )
        from app.core.clock import FixedClock
        from app.modules.identidad import service as identidad_service

        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo.id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        sesion.refresh(dispositivo)
        assert dispositivo.estado == "ACTIVO"

    def test_reenviar_la_revocacion_devuelve_el_resultado_original_y_una_sola_auditoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-dr-2-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin1",
        )
        from app.core.clock import FixedClock
        from app.modules.identidad import service as identidad_service

        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 204
        assert segunda.status_code == 204
        assert _contar_auditoria(sesion, organizacion.id, accion="DISPOSITIVO_REVOCAR") == 1

    def test_la_revocacion_por_comando_sigue_cortando_la_sesion_del_dispositivo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-dr-3-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin1",
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        dispositivo_del_vendedor = str(uuid4())
        login_vendedor = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": organizacion.slug,
                "usuario": "admin1",
                "contrasena": PASSWORD,
                "dispositivo_id": dispositivo_del_vendedor,
                "nombre_dispositivo": "Tablet del vendedor",
            },
        )
        assert login_vendedor.status_code == 200
        # El refresh token viaja como cookie httpOnly (`app/api_v1/auth.py`),
        # no en el cuerpo -- el login del dispositivo del vendedor deja esa
        # cookie puesta en el mismo `cliente` (jar compartido).

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_del_vendedor}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )
        assert respuesta.status_code == 204

        renovacion = cliente.post(
            "/api/v1/auth/refresh", json={"dispositivo_id": dispositivo_del_vendedor}
        )
        assert renovacion.status_code == 401

    def test_reenviar_con_otro_contenido_se_rechaza_como_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-dr-4-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin1",
        )
        from app.core.clock import FixedClock
        from app.modules.identidad import service as identidad_service

        dispositivo_1 = identidad_service.registrar_dispositivo(
            organizacion.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="T1"
        )
        dispositivo_2 = identidad_service.registrar_dispositivo(
            organizacion.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="T2"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_1.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        # El mismo `operation_id`, pero apuntando a otro recurso -- otro
        # contenido de comando, misma huella esperada distinta.
        segunda = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo_2.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 204
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        sesion.refresh(dispositivo_2)
        assert dispositivo_2.estado == "ACTIVO"

    def test_sin_permiso_se_rechaza_sin_efectos(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-dr-5-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        from app.core.clock import FixedClock
        from app.modules.identidad import service as identidad_service

        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, sesion, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")

        respuesta = cliente.delete(
            f"/api/v1/identidad/dispositivos/{dispositivo.id}",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        sesion.refresh(dispositivo)
        assert dispositivo.estado == "ACTIVO"


class TestPinAutorizacionRotar:
    def _crear_supervisor(self, sesion: Session, organizacion_id):
        _crear_usuario(
            sesion,
            organizacion_id,
            permisos=frozenset({"AUTORIZAR_DESCUENTO"}),
            nombre_usuario="supervisor1",
        )
        return repository.obtener_usuario_por_nombre_usuario(organizacion_id, "supervisor1", sesion)

    def test_sin_operation_id_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-1-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert "654321" not in respuesta.text

    def test_reenviar_la_rotacion_no_vuelve_a_derivar_el_pin(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-2-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        sesion.refresh(supervisor)
        hash_despues_de_la_primera = supervisor.pin_autorizacion_hash

        segunda = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        sesion.refresh(supervisor)

        assert primera.status_code == 204
        assert segunda.status_code == 204
        assert supervisor.pin_autorizacion_hash == hash_despues_de_la_primera
        assert _contar_auditoria(sesion, organizacion.id, accion="PIN_AUTORIZACION_ROTAR") == 1

    def test_reenviar_con_otro_contenido_se_rechaza_como_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-3-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "111222"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 204
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert "111222" not in segunda.text
        assert "654321" not in segunda.text

    def test_sin_permiso_se_rechaza_sin_efectos(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-4-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        sesion.refresh(supervisor)
        assert supervisor.pin_autorizacion_hash is None

    def test_la_rotacion_queda_auditada_con_su_operation_id_una_sola_vez(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-5-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = uuid4()

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": "654321"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 204
        assert _contar_auditoria(sesion, organizacion.id, accion="PIN_AUTORIZACION_ROTAR") == 1
        assert _contar_auditoria(sesion, organizacion.id, accion="DEFINIR_PIN_AUTORIZACION") == 0
        fila = sesion.execute(
            select(Auditoria).where(
                Auditoria.organizacion_id == organizacion.id,
                Auditoria.accion == "PIN_AUTORIZACION_ROTAR",
            )
        ).scalar_one()
        assert fila.operation_id == operation_id

    def test_el_resultado_del_comando_no_contiene_el_pin_ni_su_derivacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-pin-6-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = uuid4()
        pin = "917253"

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": pin},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )
        assert respuesta.status_code == 204
        assert pin not in respuesta.text

        comando = sesion.execute(
            select(Comando).where(Comando.operation_id == operation_id)
        ).scalar_one()
        assert pin not in str(comando.resultado)
        sesion.refresh(supervisor)
        assert pin not in str(supervisor.pin_autorizacion_hash)

        filas_auditoria = (
            sesion.execute(select(Auditoria).where(Auditoria.organizacion_id == organizacion.id))
            .scalars()
            .all()
        )
        for fila in filas_auditoria:
            assert pin not in (fila.observacion or "")
            assert pin not in str(fila.antes or "")
            assert pin not in str(fila.despues or "")

    def test_un_pin_invalido_por_longitud_nunca_aparece_en_claro_en_el_error(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Riesgo señalado del change: un PIN de longitud incorrecta se
        rechaza (`identidad/domain/usuarios.py::
        validar_formato_pin_autorizacion`, vía `establecer_pin_autorizacion`)
        SIN que el valor del PIN aparezca en ningún texto de la respuesta de
        error -- ni el mensaje de `ContenidoDeComandoInvalidoError` (que sí
        expondría el PIN si el esquema tuviera un validador de longitud a
        nivel de Pydantic, ver docstring de `PinAutorizacionRotarContenidoV1`)
        ni el de `PinAutorizacionInvalidoError` (dominio, ya sin el valor
        por diseño existente)."""
        organizacion = _crear_organizacion(sesion, f"org-pin-7-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        supervisor = self._crear_supervisor(sesion, organizacion.id)
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        pin_invalido_por_longitud = "12"

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{supervisor.id}/pin",
            json={"pin": pin_invalido_por_longitud},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code != 204
        assert pin_invalido_por_longitud not in respuesta.text
        sesion.refresh(supervisor)
        assert supervisor.pin_autorizacion_hash is None


class TestRolPermisosCambiar:
    """Grupo 14 (decisión del usuario 2026-09-22, `tasks.md` 14.3/14.4):
    `PUT /identidad/roles/{rol_id}/permisos` delega en el bus
    (`ROL_PERMISOS_CAMBIAR`). Los 5 escenarios comunes más "los permisos del
    rol quedan como se pidió" (triangulación propia de esta operación, mismo
    criterio que `TestDispositivoRevocar` con "sigue cortando la sesión")."""

    def _crear_rol_con_permisos(
        self, sesion: Session, organizacion_id, *, permisos: frozenset[str], nombre: str
    ):
        rol = repository.crear_rol(
            organizacion_id,
            sesion,
            rol_id=nuevo_id(),
            nombre=nombre,
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            repository.asignar_permiso_a_rol(
                organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        return rol

    def test_sin_operation_id_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rpc-1-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion, organizacion.id, permisos=frozenset(), nombre="Rol objetivo"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert repository.listar_permisos_de_rol(organizacion.id, rol_objetivo.id, sesion) == []

    def test_reenviar_el_cambio_no_duplica_el_efecto_ni_la_auditoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rpc-2-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion, organizacion.id, permisos=frozenset(), nombre="Rol objetivo"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())
        cuerpo = {"permisos": ["GESTIONAR_CLIENTES", "VER_REPORTES"]}

        primera = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json=cuerpo,
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json=cuerpo,
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 200
        assert segunda.status_code == 200
        assert set(repository.listar_permisos_de_rol(organizacion.id, rol_objetivo.id, sesion)) == {
            "GESTIONAR_CLIENTES",
            "VER_REPORTES",
        }
        assert _contar_auditoria(sesion, organizacion.id, accion="ROL_PERMISOS_CAMBIAR") == 1

    def test_reenviar_con_otro_contenido_se_rechaza_como_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rpc-3-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion, organizacion.id, permisos=frozenset(), nombre="Rol objetivo"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["VER_REPORTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 200
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert repository.listar_permisos_de_rol(organizacion.id, rol_objetivo.id, sesion) == [
            "GESTIONAR_CLIENTES"
        ]

    def test_sin_permiso_se_rechaza_sin_efectos(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rpc-4-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion, organizacion.id, permisos=frozenset(), nombre="Rol objetivo"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert repository.listar_permisos_de_rol(organizacion.id, rol_objetivo.id, sesion) == []
        assert _contar_comandos(sesion, operation_id) == 0

    def test_el_cambio_queda_auditado_con_su_operation_id_una_sola_vez(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-rpc-5-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion, organizacion.id, permisos=frozenset(), nombre="Rol objetivo"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = uuid4()

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["GESTIONAR_CLIENTES"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 200
        # ADR-022: una sola fila -- la del bus (`accion=sobre.tipo`), no la
        # interna del servicio (que quedó desactivada con `auditar=False`).
        assert _contar_auditoria(sesion, organizacion.id, accion="ROL_PERMISOS_CAMBIAR") == 1
        assert _contar_auditoria(sesion, organizacion.id, accion="CAMBIAR_COMPOSICION_ROL") == 0
        fila = sesion.execute(
            select(Auditoria).where(
                Auditoria.organizacion_id == organizacion.id,
                Auditoria.accion == "ROL_PERMISOS_CAMBIAR",
            )
        ).scalar_one()
        assert fila.operation_id == operation_id
        assert fila.origen == "COMANDO"

    def test_los_permisos_del_rol_quedan_exactamente_como_se_pidio(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Triangulación de negocio (no de los 5 genéricos): el comando deja
        el conjunto de permisos EXACTO del pedido -- agrega lo nuevo y quita
        lo que ya no está, no solo agrega."""
        organizacion = _crear_organizacion(sesion, f"org-rpc-6-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        rol_objetivo = self._crear_rol_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_CLIENTES", "VER_REPORTES"}),
            nombre="Rol objetivo",
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.put(
            f"/api/v1/identidad/roles/{rol_objetivo.id}/permisos",
            json={"permisos": ["VER_REPORTES", "ADMIN_USUARIOS"]},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 200
        assert set(repository.listar_permisos_de_rol(organizacion.id, rol_objetivo.id, sesion)) == {
            "VER_REPORTES",
            "ADMIN_USUARIOS",
        }


class TestUsuarioDesbloquear:
    """Grupo 14 (decisión del usuario 2026-09-22, `tasks.md` 14.5/14.6):
    `POST /identidad/usuarios/{usuario_id}/desbloqueo` delega en el bus
    (`USUARIO_DESBLOQUEAR`). Los 5 escenarios comunes más "el usuario
    efectivamente queda desbloqueado" (triangulación propia de esta
    operación)."""

    def _bloquear_usuario(self, cliente: TestClient, organizacion_slug: str, usuario: str) -> None:
        for _ in range(5):
            respuesta = cliente.post(
                "/api/v1/auth/login",
                json={
                    "organizacion_slug": organizacion_slug,
                    "usuario": usuario,
                    "contrasena": "contrasena-incorrecta",
                    "dispositivo_id": str(uuid4()),
                    "nombre_dispositivo": "PC",
                },
            )
            assert respuesta.status_code == 401

    def test_sin_operation_id_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-ud-1-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_reenviar_el_desbloqueo_no_duplica_el_efecto_ni_la_auditoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-ud-2-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        segunda = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 204
        assert segunda.status_code == 204
        assert _contar_auditoria(sesion, organizacion.id, accion="USUARIO_DESBLOQUEAR") == 1

    def test_reenviar_con_otro_contenido_se_rechaza_como_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-ud-3-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        bloqueado_1, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        bloqueado_2, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor2"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = str(uuid4())

        primera = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado_1.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )
        # El mismo `operation_id`, pero apuntando a otro usuario -- otro
        # contenido de comando, misma huella esperada distinta.
        segunda = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado_2.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id},
        )

        assert primera.status_code == 204
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"

    def test_sin_permiso_se_rechaza_sin_efectos(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, f"org-ud-4-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor2"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _contar_comandos(sesion, operation_id) == 0

    def test_el_desbloqueo_queda_auditado_con_su_operation_id_una_sola_vez(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-ud-5-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")
        operation_id = uuid4()

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 204
        assert _contar_auditoria(sesion, organizacion.id, accion="USUARIO_DESBLOQUEAR") == 1
        assert _contar_auditoria(sesion, organizacion.id, accion="DESBLOQUEO_MANUAL_LOGIN") == 0
        fila = sesion.execute(
            select(Auditoria).where(
                Auditoria.organizacion_id == organizacion.id,
                Auditoria.accion == "USUARIO_DESBLOQUEAR",
            )
        ).scalar_one()
        assert fila.operation_id == operation_id
        assert fila.origen == "COMANDO"

    def test_el_usuario_efectivamente_queda_desbloqueado_tras_el_comando(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Triangulación de negocio (no de los 5 genéricos), mismo criterio
        que `TestDispositivoRevocar::
        test_la_revocacion_por_comando_sigue_cortando_la_sesion_del_dispositivo`:
        el comando no solo audita y responde 204 -- efectivamente reinicia
        la ventana de intentos fallidos del usuario, que puede volver a
        iniciar sesión."""
        organizacion = _crear_organizacion(sesion, f"org-ud-6-{uuid4().hex[:8]}")
        _, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset({"ADMIN_USUARIOS"}), nombre_usuario="admin1"
        )
        bloqueado, _ = _crear_usuario(
            sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1"
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        self._bloquear_usuario(cliente, organizacion.slug, "vendedor1")
        login_bloqueado = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": organizacion.slug,
                "usuario": "vendedor1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert login_bloqueado.status_code == 429

        respuesta = cliente.post(
            f"/api/v1/identidad/usuarios/{bloqueado.id}/desbloqueo",
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )
        assert respuesta.status_code == 204

        login_desbloqueado = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": organizacion.slug,
                "usuario": "vendedor1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert login_desbloqueado.status_code == 200
