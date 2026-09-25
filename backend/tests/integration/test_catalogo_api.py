"""Change 05, grupo 9 (tareas 9.1-9.3): endpoints HTTP de `catalogo`.

Sigue el mismo arnés HTTP que `test_identidad_api_usuarios.py` (Postgres
real, `cliente` con motor propio, login real -- nunca un access token
fabricado a mano). Cubre: los nueve comandos de escritura delegando en el
bus (`Operation-Id` obligatorio, permiso `GESTIONAR_CATALOGO`), las lecturas
paginadas y el detalle de producto, y los tres escenarios de la tarea 9.3
(sin `Operation-Id` -> 400; sin permiso -> `PERMISO_REQUERIDO` sin efectos
ni reserva; con permiso -> se acepta).
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
from app.modules.catalogo import repository as catalogo_repository
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion
from app.modules.proveedores import repository as proveedores_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-catalogo-api"


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


class TestCrearCategoria:
    def test_un_usuario_con_gestionar_catalogo_crea_una_categoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-1")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-cat-1", "admin1")

        respuesta = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["nombre"] == "Vinos"
        assert cuerpo["activo"] is True

    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-2")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-cat-2", "admin1")

        respuesta = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        categorias = catalogo_repository.listar_categorias(organizacion.id, sesion)
        assert categorias == []

    def test_sin_el_permiso_se_rechaza_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Tarea 9.3: un rol sin `GESTIONAR_CATALOGO` (equivalente a
        Vendedor/Repartidor, `01` §19) recibe `PERMISO_REQUERIDO`, sin dejar
        categoría, auditoría ni reserva de `operation_id`."""
        organizacion = _crear_organizacion(sesion, "org-cat-3")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-cat-3", "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(operation_id),
            },
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        categorias = catalogo_repository.listar_categorias(organizacion.id, sesion)
        assert categorias == []
        reserva = sesion.scalar(
            text("select count(*) from comando where operation_id = :oid"),
            {"oid": str(operation_id)},
        )
        assert reserva == 0

    def test_reenvio_del_mismo_operation_id_devuelve_la_misma_categoria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-4")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-cat-4", "admin1")
        operation_id = str(uuid4())
        headers = {"Authorization": f"Bearer {access_token}", "Operation-Id": operation_id}

        primera = cliente.post(
            "/api/v1/catalogo/categorias", json={"nombre": "Vinos"}, headers=headers
        )
        segunda = cliente.post(
            "/api/v1/catalogo/categorias", json={"nombre": "Vinos"}, headers=headers
        )

        assert primera.status_code == 201
        assert segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        assert len(catalogo_repository.listar_categorias(organizacion.id, sesion)) == 1

    def test_el_mismo_nombre_en_otra_organizacion_es_valido(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Spec `categorias-y-marcas`, escenario "El mismo nombre en otra
        organización es válido" (TR-08, INV-02): `Vinos` en A no impide
        `Vinos` en B."""
        organizacion_a = _crear_organizacion(sesion, "org-cat-nombre-a")
        _con_gestionar_catalogo(sesion, organizacion_a.id, nombre_usuario="admin1")
        organizacion_b = _crear_organizacion(sesion, "org-cat-nombre-b")
        _con_gestionar_catalogo(sesion, organizacion_b.id, nombre_usuario="admin1")
        sesion.commit()

        token_a = _login(cliente, "org-cat-nombre-a", "admin1")
        respuesta_a = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {token_a}", "Operation-Id": str(uuid4())},
        )
        assert respuesta_a.status_code == 201

        token_b = _login(cliente, "org-cat-nombre-b", "admin1")
        respuesta_b = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta_b.status_code == 201
        assert respuesta_b.json()["nombre"] == "Vinos"
        assert respuesta_a.json()["id"] != respuesta_b.json()["id"]


class TestModificarCategoria:
    def test_modificar_una_categoria_existente(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-5")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        categoria = catalogo_repository.crear_categoria(
            organizacion.id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        access_token = _login(cliente, "org-cat-5", "admin1")

        respuesta = cliente.put(
            f"/api/v1/catalogo/categorias/{categoria.id}",
            json={"nombre": "Vinos finos", "activo": True},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["nombre"] == "Vinos finos"

    def test_modificar_una_categoria_de_otra_organizacion_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-cat-6a")
        categoria_ajena = catalogo_repository.crear_categoria(
            organizacion_a.id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        organizacion_b = _crear_organizacion(sesion, "org-cat-6b")
        _con_gestionar_catalogo(sesion, organizacion_b.id, nombre_usuario="admin_b")
        sesion.commit()
        access_token = _login(cliente, "org-cat-6b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/categorias/{categoria_ajena.id}",
            json={"nombre": "Robada", "activo": True},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


class TestListarCategorias:
    def test_lista_categorias_paginadas(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-7")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        catalogo_repository.crear_categoria(
            organizacion.id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        catalogo_repository.crear_categoria(
            organizacion.id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Licores",
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        access_token = _login(cliente, "org-cat-7", "admin1")

        respuesta = cliente.get(
            "/api/v1/catalogo/categorias",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert [item["nombre"] for item in cuerpo["items"]] == ["Licores", "Vinos"]
        assert cuerpo["cursor_siguiente"] is None

    def test_listar_categorias_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-cat-8")
        _crear_usuario(sesion, organizacion.id, permisos=frozenset(), nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-cat-8", "vendedor1")

        respuesta = cliente.get(
            "/api/v1/catalogo/categorias",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


class TestMarcas:
    def test_crear_y_modificar_una_marca(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-marca-1")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-marca-1", "admin1")

        alta = cliente.post(
            "/api/v1/catalogo/marcas",
            json={"nombre": "Nacional"},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )
        assert alta.status_code == 201
        marca_id = alta.json()["id"]

        modificacion = cliente.put(
            f"/api/v1/catalogo/marcas/{marca_id}",
            json={"nombre": "Nacional S.A.", "activo": False},
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )
        assert modificacion.status_code == 200
        assert modificacion.json()["activo"] is False

    def test_listar_marcas(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-marca-2")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        catalogo_repository.crear_marca(
            organizacion.id,
            sesion,
            marca_id=nuevo_id(),
            nombre="Nacional",
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        access_token = _login(cliente, "org-marca-2", "admin1")

        respuesta = cliente.get(
            "/api/v1/catalogo/marcas", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert respuesta.status_code == 200
        assert [item["nombre"] for item in respuesta.json()["items"]] == ["Nacional"]


class TestProductosYPresentaciones:
    def _crear_proveedor(self, sesion: Session, organizacion_id: UUID):
        proveedor = proveedores_repository.crear_proveedor(
            organizacion_id,
            sesion,
            proveedor_id=nuevo_id(),
            nombre="Proveedor de prueba",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        return proveedor

    def _crear_producto(
        self, cliente: TestClient, sesion: Session, access_token: str, organizacion_id: UUID
    ) -> tuple[str, str]:
        categoria = catalogo_repository.crear_categoria(
            organizacion_id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        from app.modules.configuracion.models import AlicuotaIva

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
        sesion.commit()
        proveedor = self._crear_proveedor(sesion, organizacion_id)

        respuesta = cliente.post(
            "/api/v1/catalogo/productos",
            json={
                "codigo": "VA-001",
                "nombre": "Vino A",
                "categoria_id": str(categoria.id),
                "marca_id": None,
                "proveedor_id": str(proveedor.id),
                "unidad_base": "botella",
                "alicuota_id": str(alicuota.id),
                "presentaciones": [
                    {
                        "nombre": "Botella",
                        "unidades_base": 1,
                        "usar_en_venta": True,
                        "usar_en_compra": True,
                        "es_referencia": False,
                    },
                    {
                        "nombre": "Caja x6",
                        "unidades_base": 6,
                        "usar_en_venta": True,
                        "usar_en_compra": True,
                        "es_referencia": True,
                    },
                ],
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )
        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert len(cuerpo["presentaciones"]) == 2
        botella = next(p for p in cuerpo["presentaciones"] if p["nombre"] == "Botella")
        return cuerpo["id"], botella["id"]

    def test_alta_completa_y_detalle(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-prod-1")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-prod-1", "admin1")

        producto_id, _ = self._crear_producto(cliente, sesion, access_token, organizacion.id)

        detalle = cliente.get(
            f"/api/v1/catalogo/productos/{producto_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert detalle.status_code == 200
        assert detalle.json()["codigo"] == "VA-001"
        assert len(detalle.json()["presentaciones"]) == 2
        # Change 06, contrato-api.md P1/D13 (aprobado 2026-09-24):
        # `proveedor_id` en el detalle y `proveedor_nombre` resuelto vía
        # el puerto de ADR-025.
        assert detalle.json()["proveedor_id"] is not None
        assert detalle.json()["proveedor_nombre"] == "Proveedor de prueba"

    def test_producto_de_otra_organizacion_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-prod-2a")
        _con_gestionar_catalogo(sesion, organizacion_a.id, nombre_usuario="admin_a")
        sesion.commit()
        token_a = _login(cliente, "org-prod-2a", "admin_a")
        producto_id, _ = self._crear_producto(cliente, sesion, token_a, organizacion_a.id)

        organizacion_b = _crear_organizacion(sesion, "org-prod-2b")
        _con_gestionar_catalogo(sesion, organizacion_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-prod-2b", "admin_b")

        respuesta = cliente.get(
            f"/api/v1/catalogo/productos/{producto_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_agregar_modificar_y_cambiar_referencia_de_presentacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-prod-3")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-prod-3", "admin1")
        producto_id, presentacion_botella_id = self._crear_producto(
            cliente, sesion, access_token, organizacion.id
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        agregada = cliente.post(
            f"/api/v1/catalogo/productos/{producto_id}/presentaciones",
            json={
                "nombre": "Caja x12",
                "unidades_base": 12,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        assert agregada.status_code == 201
        presentacion_id = agregada.json()["id"]

        modificada = cliente.put(
            f"/api/v1/catalogo/presentaciones/{presentacion_id}",
            json={
                "nombre": "Caja x12 (pallet)",
                "unidades_base": 12,
                "usar_en_venta": True,
                "usar_en_compra": False,
                "activo": True,
            },
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        assert modificada.status_code == 200
        assert modificada.json()["nombre"] == "Caja x12 (pallet)"

        referencia = cliente.put(
            f"/api/v1/catalogo/productos/{producto_id}/referencia",
            json={"presentacion_id": presentacion_botella_id},
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        assert referencia.status_code == 200
        assert referencia.json()["id"] == presentacion_botella_id
        assert referencia.json()["es_referencia"] is True

    def test_agregar_presentacion_con_unidades_invalidas_responde_error_de_dominio(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-prod-4")
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-prod-4", "admin1")
        producto_id, _ = self._crear_producto(cliente, sesion, access_token, organizacion.id)

        respuesta = cliente.post(
            f"/api/v1/catalogo/productos/{producto_id}/presentaciones",
            json={
                "nombre": "Inválida",
                "unidades_base": 0,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "UNIDADES_INVALIDAS"
