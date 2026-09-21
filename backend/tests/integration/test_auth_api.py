"""Endpoints `/auth` (tarea 10.6) y de dispositivos (tarea 10.7), sobre
Postgres real. Ejercita la dependencia de autenticación y permisos (tareas
10.1, 10.2, 10.4, 10.5) end-to-end vía HTTP.
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

from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Auditoria, IntentoLogin, Organizacion, SesionRefresh

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-http"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    """Estas pruebas confirman transacciones reales contra `database_url`
    (necesario para que el motor propio de `crear_app` las vea, ver fixture
    `sesion`), así que son responsables de su propia limpieza explícita
    (convención documentada en `conftest.py`, docstring del módulo): sin
    esto, las filas quedan confirmadas en la base compartida de la sesión de
    pytest y contaminan otras pruebas que asumen una tabla `organizacion`
    vacía (por ejemplo `test_seed.py`, que usa "existe alguna fila" como
    señal de "ya sembrado"). `TRUNCATE ... CASCADE` alcanza a toda tabla con
    una FK (directa o transitiva) hacia `organizacion`."""
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
def cliente(database_url: str) -> TestClient:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    return TestClient(crear_app(settings))


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion):
    """Sesión con `commit` real (no la transaccional `db_session`): los
    datos deben quedar visibles para el motor propio que arma la app
    (`crear_app` construye su propio `Engine`/`sessionmaker` a partir de
    `database_url`, distinto del de `db_session`) -- una fila que solo
    vive en un SAVEPOINT de `db_session` nunca sería visible ahí. Depende
    de `_engine_de_sesion` únicamente para que las migraciones ya hayan
    corrido (no usa ese motor: abre el suyo propio)."""
    factory = crear_session_factory(crear_engine(database_url))
    with factory() as sesion_real:
        yield sesion_real


def test_login_devuelve_access_token_y_cookie_de_refresh(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenarios "Inicio de sesión con credenciales correctas" y "El
    refresh token no es legible desde la aplicación" (cookie HttpOnly)."""
    organizacion = _crear_organizacion(sesion, "org-http-1")
    _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
    sesion.commit()

    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-1",
            "usuario": "vendedor1",
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Tablet",
        },
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert "access_token" in cuerpo
    assert "refresh_token" not in cuerpo  # nunca en el cuerpo (ADR-017).

    cookie_cruda = respuesta.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie_cruda
    assert "HttpOnly" in cookie_cruda
    assert "Secure" in cookie_cruda
    assert "SameSite=strict" in cookie_cruda.lower().replace("samesite=strict", "SameSite=strict")
    assert "/api/v1/auth" in cookie_cruda


def test_login_con_credenciales_incorrectas_responde_401_con_codigo_estable(
    cliente: TestClient, sesion: Session
) -> None:
    organizacion = _crear_organizacion(sesion, "org-http-2")
    _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
    sesion.commit()

    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-2",
            "usuario": "vendedor1",
            "contrasena": "mal",
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Tablet",
        },
    )

    assert respuesta.status_code == 401
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "IDENTIDAD_CREDENCIALES_INVALIDAS"

    # Grupo 11 (`ADR-018`): el intento fallido tiene que quedar confirmado
    # de verdad -- no alcanza con que `iniciar_sesion` lo agregue a la
    # sesión, porque el endpoint de login sólo hace `commit()` en el camino
    # feliz (`auth.py::login`); si el error se propaga antes de esa línea,
    # `get_session` cierra la sesión sin confirmar nada y la fila se pierde.
    intentos = sesion.execute(select(IntentoLogin)).scalars().all()
    assert len(intentos) == 1, "el intento fallido debe quedar confirmado aunque el login falle"


def test_refresh_rota_el_token_y_logout_revoca_la_cookie(
    cliente: TestClient, sesion: Session
) -> None:
    """Tarea 10.6: endpoints `/auth/refresh` y `/auth/logout` sobre el
    servicio del grupo 8. Escenarios "Renovar la sesión rota el refresh
    token" y "Después de cerrar sesión no se puede renovar", ejercidos acá a
    nivel HTTP (ya cubiertos a nivel de servicio en 8.5/8.8)."""
    organizacion = _crear_organizacion(sesion, "org-http-7")
    _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
    sesion.commit()
    dispositivo_id = str(uuid4())

    login = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-7",
            "usuario": "vendedor1",
            "contrasena": PASSWORD,
            "dispositivo_id": dispositivo_id,
            "nombre_dispositivo": "Tablet",
        },
    )
    assert login.status_code == 200
    cookie_refresh_original = login.cookies["refresh_token"]

    renovada = cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": cookie_refresh_original},
    )
    assert renovada.status_code == 200
    assert renovada.json()["access_token"]  # el endpoint emite uno nuevo (no reusa el anterior)
    cookie_refresh_rotada = renovada.cookies["refresh_token"]
    # El refresh token SÍ debe rotar siempre (es el contrato de seguridad de
    # 8.5/8.6): a diferencia del access token -- cuyo contenido puede
    # coincidir byte a byte si login y refresh caen en el mismo segundo,
    # porque sus claims no incluyen un nonce -- el refresh es aleatorio
    # (`generar_refresh_token`, entropía de 32 bytes) y nunca se repite.
    assert cookie_refresh_rotada != cookie_refresh_original

    cierre = cliente.post("/api/v1/auth/logout", cookies={"refresh_token": cookie_refresh_rotada})
    assert cierre.status_code == 204

    renovar_tras_cierre = cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": cookie_refresh_rotada},
    )
    assert renovar_tras_cierre.status_code == 401


def test_el_reuso_de_un_refresh_token_revoca_la_familia_de_verdad(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Reusar un refresh token corta toda su familia" (tarea 8.6):
    igual que el intento fallido de login, la revocación que dispara la
    detección de reuso ocurre justo antes de lanzar `RefreshTokenInvalidoError`
    -- sin el `commit` en el camino de error de `auth.py::refresh`, esa
    revocación se perdía (mismo bug que el de login, corregido en la misma
    sesión)."""
    organizacion = _crear_organizacion(sesion, "org-http-8")
    _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
    sesion.commit()
    dispositivo_id = str(uuid4())

    login = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-8",
            "usuario": "vendedor1",
            "contrasena": PASSWORD,
            "dispositivo_id": dispositivo_id,
            "nombre_dispositivo": "Tablet",
        },
    )
    cookie_original = login.cookies["refresh_token"]

    primera_renovacion = cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": cookie_original},
    )
    assert primera_renovacion.status_code == 200

    # Reuso: se presenta de nuevo el token YA rotado por la línea anterior.
    reuso = cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": cookie_original},
    )
    assert reuso.status_code == 401

    sesion.expire_all()
    familia_revocada = sesion.execute(
        select(func.count())
        .select_from(SesionRefresh)
        .where(
            SesionRefresh.organizacion_id == organizacion.id,
            SesionRefresh.motivo_revocacion == "REUSO_DETECTADO",
        )
    ).scalar_one()
    assert familia_revocada > 0, "la familia debe quedar revocada de verdad, no solo en memoria"

    auditoria_reuso = (
        sesion.execute(
            select(Auditoria).where(
                Auditoria.organizacion_id == organizacion.id,
                Auditoria.accion == "REVOCAR_FAMILIA_REFRESH",
            )
        )
        .scalars()
        .all()
    )
    assert len(auditoria_reuso) == 1

    # Con la familia revocada, ni siquiera el token recién rotado sirve.
    tercer_intento = cliente.post(
        "/api/v1/auth/refresh",
        json={"dispositivo_id": dispositivo_id},
        cookies={"refresh_token": primera_renovacion.cookies["refresh_token"]},
    )
    assert tercer_intento.status_code == 401


class TestDependenciaDePermisos:
    def test_una_peticion_sin_token_no_llega_al_negocio(self, cliente: TestClient) -> None:
        """Escenario "Una petición sin token no llega al negocio"."""
        respuesta = cliente.get("/api/v1/identidad/dispositivos")
        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_AUSENTE"

    def test_un_access_token_vencido_no_da_acceso(self, cliente: TestClient) -> None:
        """Escenario "Un access token vencido no da acceso" (tarea 10.1): la
        dependencia deja propagar `AccessTokenExpiradoError` (`core/seguridad.py`)
        sin atraparla, y el manejador genérico de `DomainError` la traduce a
        401 con su código estable."""
        from app.core.seguridad import emitir_access_token

        token_vencido = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto=JWT_SECRET,
            kid="1",
            emitido_en=datetime(2020, 1, 1, tzinfo=UTC),
        )

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {token_vencido}"},
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_EXPIRADO"

    def test_un_access_token_con_firma_alterada_no_da_acceso(self, cliente: TestClient) -> None:
        """Escenario "Un access token con firma alterada no da acceso"
        (tarea 10.1). `emitido_en` sale de `FixedClock` (`core/clock.py`),
        nunca de una fecha suelta: esta prueba ejercita la verificación de
        FIRMA, no de vencimiento (`verificar_access_token` valida la firma
        antes de comparar `exp`), así que un `MOMENTO` fijo que envejece
        respecto del reloj real del sistema no debería importarle -- pero
        una fecha suelta sin pasar por el reloj inyectable es, igual, el
        mismo patrón frágil que el resto de la suite evita (`CLAUDE.md` §4:
        "el backend obtiene la hora desde un componente de reloj
        inyectable")."""
        from app.core.seguridad import emitir_access_token

        token_valido = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto=JWT_SECRET,
            kid="1",
            emitido_en=FixedClock(MOMENTO).now(),
        )
        token_con_firma_alterada = token_valido[:-1] + ("A" if token_valido[-1] != "A" else "B")

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {token_con_firma_alterada}"},
        )

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

    def test_con_el_permiso_la_operacion_procede(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Con el permiso, la operación procede"."""
        organizacion = _crear_organizacion(sesion, "org-http-3")
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            nombre_usuario="admin1",
        )
        sesion.commit()
        login = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": "org-http-3",
                "usuario": "admin1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        access_token = login.json()["access_token"]

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        assert isinstance(respuesta.json(), list)

    def test_sin_el_permiso_se_rechaza_con_codigo_estable(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Sin el permiso, la operación se rechaza con un código
        estable"."""
        organizacion = _crear_organizacion(sesion, "org-http-4")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        login = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": "org-http-4",
                "usuario": "vendedor1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "Tablet",
            },
        )
        access_token = login.json()["access_token"]

        respuesta = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_la_revocacion_de_un_permiso_corta_el_acceso_en_la_peticion_siguiente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Quitar un permiso corta el acceso en la petición
        siguiente" (tarea 10.5, `design.md` D5: sin caché)."""
        organizacion = _crear_organizacion(sesion, "org-http-5")
        rol = repository.crear_rol(
            organizacion.id,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        repository.asignar_permiso_a_rol(
            organizacion.id, sesion, rol_id=rol.id, permiso_codigo="GESTIONAR_DISPOSITIVOS"
        )
        usuario = repository.crear_usuario(
            organizacion.id,
            sesion,
            usuario_id=nuevo_id(),
            usuario="admin1",
            nombre="Admin",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        sesion.commit()
        login = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": "org-http-5",
                "usuario": "admin1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        access_token = login.json()["access_token"]

        primera = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert primera.status_code == 200

        # Quita el permiso, en una sesión/transacción aparte, ya confirmada.
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            sesion,
            FixedClock(MOMENTO),
            rol_id=rol.id,
            permisos_nuevos=frozenset(),
            actor_id=usuario.id,
        )
        sesion.commit()

        segunda = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert segunda.status_code == 403

    def test_agregar_un_permiso_habilita_en_la_peticion_siguiente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Agregar un permiso habilita en la petición siguiente"
        (tarea 10.5, `design.md` D5: sin caché) -- la mitad simétrica del
        caso anterior."""
        organizacion = _crear_organizacion(sesion, "org-http-8")
        rol = repository.crear_rol(
            organizacion.id,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        usuario = repository.crear_usuario(
            organizacion.id,
            sesion,
            usuario_id=nuevo_id(),
            usuario="admin1",
            nombre="Admin",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        sesion.commit()
        login = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": "org-http-8",
                "usuario": "admin1",
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        access_token = login.json()["access_token"]

        primera = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert primera.status_code == 403

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            sesion,
            FixedClock(MOMENTO),
            rol_id=rol.id,
            permisos_nuevos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            actor_id=usuario.id,
        )
        sesion.commit()

        segunda = cliente.get(
            "/api/v1/identidad/dispositivos",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert segunda.status_code == 200


def test_el_dispositivo_del_contexto_es_el_del_token(cliente: TestClient, sesion: Session) -> None:
    """Escenario "El dispositivo del contexto es el del token" (tarea 10.4,
    spec `autorizacion-por-permiso`): revocar un dispositivo audita el
    dispositivo desde el que el actor está autenticado (D1, el del access
    token), nunca uno declarado en la petición (D2, informado en la
    consulta -- mismo patrón que
    `test_ninguna_organizacion_informada_en_la_peticion_se_usa`: el endpoint
    ni siquiera declara ese parámetro, así que informarlo no tiene efecto).
    """
    organizacion = _crear_organizacion(sesion, "org-http-9")
    _crear_usuario(
        sesion,
        organizacion.id,
        permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
        nombre_usuario="admin1",
    )
    sesion.commit()

    dispositivo_actor_id = str(uuid4())  # D1: el dispositivo del login, el del token.
    login = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-9",
            "usuario": "admin1",
            "contrasena": PASSWORD,
            "dispositivo_id": dispositivo_actor_id,
            "nombre_dispositivo": "PC del admin",
        },
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    dispositivo_objetivo = identidad_service.registrar_dispositivo(
        organizacion.id,
        sesion,
        FixedClock(MOMENTO),
        dispositivo_id=nuevo_id(),
        nombre="Tablet del vendedor",
    )
    sesion.commit()

    dispositivo_declarado_en_la_peticion = str(uuid4())  # D2: ajeno, se informa y debe ignorarse.
    respuesta = cliente.delete(
        f"/api/v1/identidad/dispositivos/{dispositivo_objetivo.id}"
        f"?dispositivo_id={dispositivo_declarado_en_la_peticion}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert respuesta.status_code == 204

    fila_auditoria = sesion.execute(
        select(Auditoria).where(
            Auditoria.organizacion_id == organizacion.id,
            Auditoria.accion == "REVOCAR_DISPOSITIVO",
        )
    ).scalar_one()
    assert str(fila_auditoria.dispositivo_id) == dispositivo_actor_id
    assert str(fila_auditoria.dispositivo_id) != dispositivo_declarado_en_la_peticion


def test_ninguna_organizacion_informada_en_la_peticion_se_usa(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Una organización informada en la petición se ignora":
    ninguna ruta de negocio recibe `organizacion_id` como parámetro de
    consulta o encabezado -- la única fuente es el token (tarea 10.4). Este
    endpoint (`listar_dispositivos`) ni siquiera declara ese parámetro,
    así que informarlo en la query no tiene ningún efecto."""
    organizacion = _crear_organizacion(sesion, "org-http-6")
    _crear_usuario(
        sesion,
        organizacion.id,
        permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
        nombre_usuario="admin1",
    )
    sesion.commit()
    login = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": "org-http-6",
            "usuario": "admin1",
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )
    access_token = login.json()["access_token"]

    respuesta = cliente.get(
        f"/api/v1/identidad/dispositivos?organizacion_id={uuid4()}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert respuesta.status_code == 200
