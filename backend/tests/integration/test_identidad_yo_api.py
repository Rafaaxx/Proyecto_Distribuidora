"""Grupo 4 del change 06b: `GET /api/v1/yo` sobre Postgres real, HTTP y
login reales (`design.md`, "Contrato de `GET /api/v1/yo`", D1, ADR-027).

Ejercita la ruta end-to-end: login real (nunca `emitir_access_token` a
mano, salvo para los casos de token inválido/vencido, donde no hay usuario
real que loguear) y la forma exacta del contrato aprobada por el usuario el
2026-09-25 (tarea 4.1): usuario, organización y rol (id y nombre), y la
lista de permisos ordenada -- sin email, login, estado ni secretos.
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

from app.api_v1 import sistema
from app.core.clock import FixedClock, SystemClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.catalogo import repository as catalogo_repository
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    ADMINISTRADOR,
    PLANTILLAS_DE_ROL,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
)
from app.modules.identidad.models import Auditoria, Organizacion
from app.modules.proveedores import repository as proveedores_repository
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-yo-api-123"
JWT_SECRET = "secreto-de-prueba-yo-api"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    """Mismo motivo y mecanismo que `test_auth_api.py`: estas pruebas
    confirman transacciones reales contra `database_url` con el motor
    propio de `crear_app`, así que limpian explícitamente al terminar."""
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _crear_organizacion(sesion: Session, slug: str, nombre: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre=nombre,
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


def _crear_usuario_con_plantilla(
    sesion: Session,
    organizacion_id,
    *,
    nombre_plantilla: str,
    login: str,
    nombre_persona: str,
    nombre_rol: str | None = None,
):
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre_rol or nombre_plantilla,
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in PLANTILLAS_DE_ROL[nombre_plantilla]:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=login,
        nombre=nombre_persona,
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario, rol


def _crear_usuario_con_permisos(
    sesion: Session,
    organizacion_id,
    *,
    permisos: frozenset[str],
    login: str,
    nombre_persona: str,
    nombre_rol: str,
):
    """Rol con una composición EXACTA, elegida por la prueba. A diferencia de
    `_crear_usuario_con_plantilla` (que usa las plantillas de `01` §19), acá
    el conjunto de permisos es el que la prueba necesita: hace falta un rol
    con exactamente un permiso, para que "lo que `/yo` informa" y "lo que el
    servidor autoriza" se puedan contrastar sin que otras variables de
    entrada (plantilla, alícuota, superconjuntos) enturbien la comparación.
    Mismo mecanismo `repository.crear_rol` +
    `repository.asignar_permiso_a_rol` que usa el resto del archivo."""
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre_rol,
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
        usuario=login,
        nombre=nombre_persona,
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario, rol


def _crear_producto(sesion: Session, organizacion_id, *, codigo: str, nombre: str):
    """Producto propio de la organización, con su proveedor, su categoría y su
    alícuota -- lo mínimo para que `GET /costos/productos/{id}/vigente`
    responda 200 (`CostoVigenteResponse`: 200 siempre que el producto exista
    en la organización, con `costo: null` cuando no hay costo informado; el
    404 queda solo para un producto inexistente o ajeno, INV-21).

    Mismo patrón que `_crear_producto_con_presentacion_de_compra` de
    `test_inv21_aislamiento_endpoints_proveedores.py`, sin la presentación:
    esta prueba no informa ningún costo, solo necesita que la ruta llegue al
    producto propio. `producto.proveedor_id` es `NOT NULL` (`03` §4), así que
    el proveedor no es opcional."""
    proveedor = proveedores_repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre="Proveedor de coherencia",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=True,
        momento=MOMENTO,
    )
    sesion.flush()
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
        nombre=f"Categoría de {nombre}",
        activo=True,
        momento=MOMENTO,
    )
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    sesion.flush()
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        sesion,
        producto_id=nuevo_id(),
        codigo=codigo,
        nombre=nombre,
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor.id,
        unidad_base="unidad",
        alicuota_id=alicuota.id,
        activo=True,
        momento=MOMENTO,
    )
    return producto


def _contar(sesion: Session, modelo: object) -> int:
    """Recuento de TODA la tabla, sin filtrar por organización.

    Deliberado: para afirmar que una lectura no escribe nada, un filtro por
    `organizacion_id` dejaría pasar filas que la prueba no está mirando. Como
    `comando` y `auditoria` son de solo inserción (`AGENTS.md` §4), el recuento
    solo puede aumentar, así que la igualdad antes/después no deja pasar ni
    una fila propia ni una ajena."""
    return sesion.execute(select(func.count()).select_from(modelo)).scalar_one()  # type: ignore[arg-type]


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    """Mismo patrón que `test_auth_api.py::cliente`: la app arma su propio
    `Engine`, liberado explícitamente al terminar la prueba."""
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
    """Mismo patrón que `test_auth_api.py::sesion`: motor propio con
    `commit` real, visible para el motor de la app."""
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def _login(cliente: TestClient, *, slug: str, usuario: str) -> str:
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Tablet",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return str(respuesta.json()["access_token"])


class TestYoContrato:
    def test_devuelve_la_forma_exacta_del_contrato_para_un_administracion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """200 con la forma exacta del contrato y `permisos` ordenados, para
        un usuario de la plantilla Administración (D1, ADR-027)."""
        organizacion = _crear_organizacion(sesion, "org-yo-api-ges", "Distribuidora de prueba")
        usuario, rol = _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=ADMINISTRACION,
            login="gestion1",
            nombre_persona="Gestión de prueba",
        )
        sesion.commit()

        token = _login(cliente, slug="org-yo-api-ges", usuario="gestion1")
        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo == {
            "usuario": {"id": str(usuario.id), "nombre": "Gestión de prueba"},
            "organizacion": {"id": str(organizacion.id), "nombre": "Distribuidora de prueba"},
            "rol": {"id": str(rol.id), "nombre": ADMINISTRACION},
            "permisos": sorted(PLANTILLAS_DE_ROL[ADMINISTRACION]),
        }
        assert cuerpo["permisos"] == sorted(cuerpo["permisos"])

    def test_devuelve_la_forma_exacta_del_contrato_para_un_administrador(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-yo-api-adm", "Otra distribuidora")
        usuario, rol = _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=ADMINISTRADOR,
            login="admin1",
            nombre_persona="Administrador de prueba",
        )
        sesion.commit()

        token = _login(cliente, slug="org-yo-api-adm", usuario="admin1")
        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["usuario"] == {"id": str(usuario.id), "nombre": "Administrador de prueba"}
        assert cuerpo["organizacion"] == {
            "id": str(organizacion.id),
            "nombre": "Otra distribuidora",
        }
        assert cuerpo["rol"] == {"id": str(rol.id), "nombre": ADMINISTRADOR}
        assert cuerpo["permisos"] == sorted(PLANTILLAS_DE_ROL[ADMINISTRADOR])

    def test_un_vendedor_repartidor_obtiene_200_sin_exigir_ningun_permiso(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """`/yo` no exige ningún permiso (ADR-027): un VEN, sin ninguno de
        los permisos de negocio del catálogo administrativo, igual obtiene
        200 con sus propios datos."""
        organizacion = _crear_organizacion(sesion, "org-yo-api-ven", "Distribuidora VEN")
        _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=VENDEDOR_REPARTIDOR,
            login="vendedor1",
            nombre_persona="Vendedor de prueba",
        )
        sesion.commit()

        token = _login(cliente, slug="org-yo-api-ven", usuario="vendedor1")
        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 200
        assert respuesta.json()["permisos"] == sorted(PLANTILLAS_DE_ROL[VENDEDOR_REPARTIDOR])

    def test_sin_token_da_401_ausente(self, cliente: TestClient) -> None:
        respuesta = cliente.get("/api/v1/yo")
        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_AUSENTE"

    def test_token_con_firma_alterada_da_401_invalido(self, cliente: TestClient) -> None:
        from app.core.seguridad import emitir_access_token

        token_valido = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto=JWT_SECRET,
            kid="1",
            emitido_en=FixedClock(MOMENTO).now(),
        )
        # Se altera el PRIMER carácter de la firma: el último de una firma
        # HS256 en base64url tiene 2 bits de relleno, y cambiarlo (B/C/D <-> A)
        # puede decodificar a los mismos bytes y dejar el token válido.
        cabecera_y_carga, firma = token_valido.rsplit(".", 1)
        token_alterado = f"{cabecera_y_carga}.{'B' if firma[0] == 'A' else 'A'}{firma[1:]}"

        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token_alterado}"})

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

    def test_token_vencido_da_401_expirado(self, cliente: TestClient) -> None:
        from app.core.seguridad import emitir_access_token

        token_vencido = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto=JWT_SECRET,
            kid="1",
            emitido_en=datetime(2020, 1, 1, tzinfo=UTC),
        )

        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token_vencido}"})

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_EXPIRADO"

    def test_usuario_que_paso_a_inactivo_da_401_invalido_no_200(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """(D9) ADR-028 D9.2-A: un access token vigente de un usuario que
        pasó a `INACTIVO` después de emitido rechaza igual que un token
        inválido, nunca un 200 (mismo tratamiento que
        `core.autenticacion.requiere_permiso`, ver `test_auth_api.py`)."""
        organizacion = _crear_organizacion(sesion, "org-yo-api-inactivo", "Distribuidora inactiva")
        usuario, _ = _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=VENDEDOR_REPARTIDOR,
            login="vendedor-inactivo",
            nombre_persona="Vendedor a desactivar",
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-inactivo", usuario="vendedor-inactivo")

        usuario_en_sesion = repository.obtener_usuario_por_id(organizacion.id, usuario.id, sesion)
        assert usuario_en_sesion is not None
        usuario_en_sesion.estado = "INACTIVO"
        sesion.flush()
        sesion.commit()

        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

    def test_rol_desactivado_da_401_invalido_no_200(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """(D9) ADR-028 D9.4-A: un rol con `activo = false` se trata igual
        que un usuario inactivo."""
        organizacion = _crear_organizacion(
            sesion, "org-yo-api-rol-inactivo", "Distribuidora rol inactivo"
        )
        usuario, rol = _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=VENDEDOR_REPARTIDOR,
            login="vendedor-rol-inactivo",
            nombre_persona="Vendedor con rol a desactivar",
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-rol-inactivo", usuario="vendedor-rol-inactivo")

        rol_en_sesion = repository.obtener_rol_por_id(organizacion.id, rol.id, sesion)
        assert rol_en_sesion is not None
        rol_en_sesion.activo = False
        sesion.flush()
        sesion.commit()

        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_INVALIDO"

    def test_la_respuesta_no_expone_secretos_ni_login_ni_estado_ni_tope(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El contrato aprobado en 4.1 no incluye `usuario.usuario` (nombre
        de login), email, estado, `tope_descuento` ni los tres campos del
        PIN de autorización. Probado con un supervisor comercial (confiere
        autorización de excepciones, `01` §19) al que se le define un PIN,
        para que el campo exista en la fila y la ausencia en la respuesta
        no sea casualidad de que nunca se haya llenado."""
        organizacion = _crear_organizacion(sesion, "org-yo-api-sup", "Distribuidora supervisor")
        usuario, _ = _crear_usuario_con_plantilla(
            sesion,
            organizacion.id,
            nombre_plantilla=SUPERVISOR_COMERCIAL,
            login="supervisor-secreto",
            nombre_persona="Supervisor de prueba",
        )
        sesion.commit()

        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            sesion,
            SystemClock(),
            usuario_id=usuario.id,
            pin="123456",
            actor_id=usuario.id,
            auditar=False,
        )
        sesion.commit()

        token = _login(cliente, slug="org-yo-api-sup", usuario="supervisor-secreto")
        respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        cuerpo_como_texto = str(cuerpo)
        assert "supervisor-secreto" not in cuerpo_como_texto  # nombre de login (D1 "No incluye")
        assert "password_hash" not in cuerpo_como_texto
        assert "pin_autorizacion" not in cuerpo_como_texto
        assert "tope_descuento" not in cuerpo_como_texto
        assert "email" not in cuerpo
        assert "estado" not in cuerpo["usuario"]
        assert set(cuerpo["usuario"].keys()) == {"id", "nombre"}


class TestLoInformadoCoincideConLoAutorizado:
    """Escenario "Lo informado coincide con lo que el servidor autoriza"
    (spec `permisos-efectivos`, segunda Requirement): la lista de `/yo` sale
    de `identidad_service.listar_permisos_del_usuario`, la misma función que
    `requiere_permiso` usa para autorizar cada petición. Estas pruebas no
    comparan la lista contra una lista esperada: la contrastan con la
    respuesta real del servidor a una ruta que exige ese permiso y a otra que
    exige el que la lista no trae.

    Si algún día `/yo` leyera los permisos de otro lado (una caché, el token,
    un permiso sobreescrito a mano), estas pruebas se pondrían rojas.
    Regla: SEG-06, ADR-027."""

    def test_un_permiso_que_informa_es_el_que_el_servidor_autoriza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """GIVEN un usuario cuya `/yo` incluye `VER_COSTOS` y no incluye
        `GESTIONAR_DISPOSITIVOS`: el costo vigente responde con éxito y el
        listado de dispositivos se rechaza con `PERMISO_REQUERIDO`."""
        organizacion = _crear_organizacion(
            sesion, "org-yo-api-coherencia-costos", "Distribuidora de coherencia"
        )
        _crear_usuario_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"VER_COSTOS"}),
            login="consulta1",
            nombre_persona="Consulta de prueba",
            nombre_rol="Consulta",
        )
        producto = _crear_producto(
            sesion, organizacion.id, codigo="COH-1", nombre="Producto de coherencia"
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-coherencia-costos", usuario="consulta1")

        yo = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
        assert yo.status_code == 200
        assert yo.json()["permisos"] == ["VER_COSTOS"]

        vigente = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert vigente.status_code == 200
        assert vigente.json()["costo"] is None

        dispositivos = cliente.get(
            "/api/v1/identidad/dispositivos", headers={"Authorization": f"Bearer {token}"}
        )
        assert dispositivos.status_code == 403
        assert dispositivos.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_el_contrario_tambien_coincide(self, cliente: TestClient, sesion: Session) -> None:
        """Triangulación con la mitad simétrica: un usuario cuya `/yo` incluye
        `GESTIONAR_DISPOSITIVOS` y no `VER_COSTOS` obtiene el listado de
        dispositivos y NO el costo vigente. Con las dos mitades se descarta
        que el 200/403 se deba a otra cosa (por ejemplo, a que el usuario de la
        prueba anterior no tuviera ningún permiso)."""
        organizacion = _crear_organizacion(
            sesion, "org-yo-api-coherencia-dispositivos", "Distribuidora de dispositivos"
        )
        _crear_usuario_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}),
            login="supervisor1",
            nombre_persona="Supervisor de coherencia",
            nombre_rol="Supervisor de prueba",
        )
        producto = _crear_producto(
            sesion, organizacion.id, codigo="COH-2", nombre="Producto sin ver"
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-coherencia-dispositivos", usuario="supervisor1")

        yo = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
        assert yo.status_code == 200
        assert yo.json()["permisos"] == ["GESTIONAR_DISPOSITIVOS"]

        dispositivos = cliente.get(
            "/api/v1/identidad/dispositivos", headers={"Authorization": f"Bearer {token}"}
        )
        # 200 con el dispositivo que registró el propio login (SEG-02).
        assert dispositivos.status_code == 200
        assert [fila["nombre"] for fila in dispositivos.json()] == ["Tablet"]

        vigente = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert vigente.status_code == 403
        assert vigente.json()["codigo"] == "PERMISO_REQUERIDO"


class TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente:
    """Escenarios "Quitar un permiso al rol se refleja en la consulta
    siguiente" y "Agregar un permiso al rol se refleja en la consulta
    siguiente" (spec `permisos-efectivos`). La composición del rol se cambia
    con la ruta real (`PUT /identidad/roles/{rol_id}/permisos`, que exige
    `Operation-Id` y pasa por el bus de comandos, `ROL_PERMISOS_CAMBIAR`) y
    después se vuelve a consultar `/yo` con el MISMO access token: sin
    renovar y sin volver a iniciar sesión.

    El usuario que cambia la composición es el mismo cuya sesión se consulta
    (es el lectura literal del escenario, y tiene `ADMIN_USUARIOS` para
    poder hacerlo). Regla: ADR-017, ADR-027, SEG-06."""

    def test_quitar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-yo-api-revocar", "Distribuidora que revoca")
        _usuario, rol = _crear_usuario_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"ADMIN_USUARIOS", "GESTIONAR_PROVEEDORES"}),
            login="gestion1",
            nombre_persona="Gestión que pierde el permiso",
            nombre_rol="Gestión",
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-revocar", usuario="gestion1")
        assert cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"}).json()[
            "permisos"
        ] == ["ADMIN_USUARIOS", "GESTIONAR_PROVEEDORES"]

        cambio = cliente.put(
            f"/api/v1/identidad/roles/{rol.id}/permisos",
            json={"permisos": ["ADMIN_USUARIOS"]},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )
        assert cambio.status_code == 200

        # Mismo access token, sin renovar: la siguiente consulta ya no lo trae.
        despues = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
        assert despues.status_code == 200
        assert despues.json()["permisos"] == ["ADMIN_USUARIOS"]
        assert "GESTIONAR_PROVEEDORES" not in despues.json()["permisos"]

        # Y la revocación también la respeta la autorización, no solo la
        # consulta: la ruta que exigía ese permiso ahora rechaza. Que la
        # prueba siga vivo es lo que confirma que se quitó SOLO ese permiso.
        assert (
            cliente.get(
                "/api/v1/identidad/usuarios", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )
        assert (
            cliente.get(
                "/api/v1/proveedores", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 403
        )

    def test_agregar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-yo-api-otorgar", "Distribuidora que otorga")
        _usuario, rol = _crear_usuario_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"ADMIN_USUARIOS"}),
            login="gestion2",
            nombre_persona="Gestión que recibe el permiso",
            nombre_rol="Gestión",
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-otorgar", usuario="gestion2")
        antes = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
        assert antes.json()["permisos"] == ["ADMIN_USUARIOS"]

        cambio = cliente.put(
            f"/api/v1/identidad/roles/{rol.id}/permisos",
            json={"permisos": ["ADMIN_USUARIOS", "GESTIONAR_DISPOSITIVOS"]},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )
        assert cambio.status_code == 200

        # Mismo access token, sin volver a iniciar sesión: la siguiente
        # consulta ya lo trae.
        despues = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
        assert despues.status_code == 200
        assert despues.json()["permisos"] == ["ADMIN_USUARIOS", "GESTIONAR_DISPOSITIVOS"]

        # Y la autorización también, desde la petición siguiente.
        assert (
            cliente.get(
                "/api/v1/identidad/dispositivos", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )


class TestLaConsultaDeLaSesionNoEscribe:
    """Escenario "Consultar la sesión no escribe nada" (spec
    `permisos-efectivos`; ADR-027, lectura sin bus de comandos; ADR-022).
    Regla: ADR-022, ADR-027, SEG-06."""

    def test_tres_consultas_no_crean_filas_de_comando_ni_de_auditoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(
            sesion, "org-yo-api-sin-escritura", "Distribuidora de lecturas"
        )
        _crear_usuario_con_permisos(
            sesion,
            organizacion.id,
            permisos=frozenset({"VER_COSTOS"}),
            login="lector1",
            nombre_persona="Lector de prueba",
            nombre_rol="Lector",
        )
        sesion.commit()
        token = _login(cliente, slug="org-yo-api-sin-escritura", usuario="lector1")

        sesion.expire_all()
        comandos_antes = _contar(sesion, Comando)
        auditoria_antes = _contar(sesion, Auditoria)

        # No vacuidad: el login escribe (una fila de auditoría
        # `INICIO_SESION`), así que "no escribió nada" es una afirmación con
        # contenido y no el resultado trivial de contar sobre tablas vacías.
        assert comandos_antes == 0
        assert auditoria_antes == 1
        acciones = sesion.execute(select(Auditoria.accion)).scalars().all()
        assert acciones == ["INICIO_SESION"]

        for _ in range(3):
            respuesta = cliente.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
            assert respuesta.status_code == 200

        sesion.expire_all()
        assert _contar(sesion, Comando) == comandos_antes
        assert _contar(sesion, Auditoria) == auditoria_antes
