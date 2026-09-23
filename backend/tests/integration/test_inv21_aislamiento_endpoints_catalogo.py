"""Tarea 11.1 (change 05, grupo 11): cobertura de aislamiento (INV-21) de
las trece rutas nuevas de `catalogo/api.py` -- las que
`test_inv21_ratchet_rutas.py::test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento`
señala como sin cobertura hasta que se agregan a `COBERTURA_DE_AISLAMIENTO`
con su prueba real acá.

Mismo arnés HTTP que `test_catalogo_api.py`/`test_inv21_aislamiento_endpoints_identidad.py`
(Postgres real, `cliente` con motor propio, login real de dos
organizaciones -- nunca un access token fabricado a mano). Además de "GET
de un recurso ajeno -> 404" para cada ruta con id, cubre el caso que pide
la tarea explícitamente: una referencia ajena EN EL CONTENIDO (categoría,
marca o alícuota de otra organización) al crear o modificar un producto.

Cita INV-21 y SEG-07 en cada escenario cruzado."""

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
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento-catalogo"


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


def _con_gestionar_catalogo(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset({"GESTIONAR_CATALOGO"}),
        nombre_usuario=nombre_usuario,
    )


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


def _crear_categoria(sesion: Session, organizacion_id: UUID, *, nombre: str):
    return catalogo_repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
        nombre=nombre,
        activo=True,
        momento=MOMENTO,
    )


def _crear_marca(sesion: Session, organizacion_id: UUID, *, nombre: str):
    return catalogo_repository.crear_marca(
        organizacion_id,
        sesion,
        marca_id=nuevo_id(),
        nombre=nombre,
        activo=True,
        momento=MOMENTO,
    )


def _crear_alicuota(sesion: Session, organizacion_id: UUID, *, nombre: str) -> AlicuotaIva:
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        nombre=nombre,
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    sesion.flush()
    return alicuota


def _payload_producto(*, codigo: str, categoria_id: UUID, alicuota_id: UUID) -> dict[str, object]:
    return {
        "codigo": codigo,
        "nombre": "Vino A",
        "categoria_id": str(categoria_id),
        "marca_id": None,
        "unidad_base": "botella",
        "alicuota_id": str(alicuota_id),
        "presentaciones": [
            {
                "nombre": "Botella",
                "unidades_base": 1,
                "usar_en_venta": True,
                "usar_en_compra": True,
                "es_referencia": True,
            }
        ],
    }


def _crear_producto_por_http(
    cliente: TestClient,
    access_token: str,
    *,
    codigo: str,
    categoria_id: UUID,
    alicuota_id: UUID,
) -> dict[str, object]:
    respuesta = cliente.post(
        "/api/v1/catalogo/productos",
        json=_payload_producto(codigo=codigo, categoria_id=categoria_id, alicuota_id=alicuota_id),
        headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


class TestAislamientoDeCategorias:
    """Rutas `POST/GET /catalogo/categorias`, `PUT
    /catalogo/categorias/{categoria_id}` (INV-21, SEG-07)."""

    def test_crear_categoria_es_independiente_por_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Alta sin id destino: el aislamiento se prueba con dos
        organizaciones creando el MISMO nombre -- si la unicidad no
        estuviera acotada por `organizacion_id`, la segunda alta chocaría
        contra la primera."""
        org_a = _crear_organizacion(sesion, "org-iso-cat-1a")
        org_b = _crear_organizacion(sesion, "org-iso-cat-1b")
        _con_gestionar_catalogo(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_a = _login(cliente, "org-iso-cat-1a", "admin_a")
        token_b = _login(cliente, "org-iso-cat-1b", "admin_b")

        respuesta_a = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {token_a}", "Operation-Id": str(uuid4())},
        )
        respuesta_b = cliente.post(
            "/api/v1/catalogo/categorias",
            json={"nombre": "Vinos"},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta_a.status_code == 201, respuesta_a.text
        assert respuesta_b.status_code == 201, respuesta_b.text
        assert respuesta_a.json()["id"] != respuesta_b.json()["id"]

    def test_listar_categorias_no_incluye_las_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-cat-2a")
        org_b = _crear_organizacion(sesion, "org-iso-cat-2b")
        _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-cat-2b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/catalogo/categorias", headers={"Authorization": f"Bearer {token_b}"}
        )

        assert respuesta.status_code == 200
        nombres = {item["nombre"] for item in respuesta.json()["items"]}
        assert "Vinos de A" not in nombres

    def test_modificar_una_categoria_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """SEG-07/INV-21: una categoría ajena responde "no encontrada" y
        no cambia."""
        org_a = _crear_organizacion(sesion, "org-iso-cat-3a")
        org_b = _crear_organizacion(sesion, "org-iso-cat-3b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-cat-3b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/categorias/{categoria_a.id}",
            json={"nombre": "Secuestrada", "activo": True},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        sesion.refresh(categoria_a)
        assert categoria_a.nombre == "Vinos de A"


class TestAislamientoDeMarcas:
    """Rutas `POST/GET /catalogo/marcas`, `PUT /catalogo/marcas/{marca_id}`
    (INV-21, SEG-07)."""

    def test_crear_marca_es_independiente_por_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-marca-1a")
        org_b = _crear_organizacion(sesion, "org-iso-marca-1b")
        _con_gestionar_catalogo(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_a = _login(cliente, "org-iso-marca-1a", "admin_a")
        token_b = _login(cliente, "org-iso-marca-1b", "admin_b")

        respuesta_a = cliente.post(
            "/api/v1/catalogo/marcas",
            json={"nombre": "Nacional"},
            headers={"Authorization": f"Bearer {token_a}", "Operation-Id": str(uuid4())},
        )
        respuesta_b = cliente.post(
            "/api/v1/catalogo/marcas",
            json={"nombre": "Nacional"},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta_a.status_code == 201, respuesta_a.text
        assert respuesta_b.status_code == 201, respuesta_b.text
        assert respuesta_a.json()["id"] != respuesta_b.json()["id"]

    def test_listar_marcas_no_incluye_las_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-marca-2a")
        org_b = _crear_organizacion(sesion, "org-iso-marca-2b")
        _crear_marca(sesion, org_a.id, nombre="Marca de A")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-marca-2b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/catalogo/marcas", headers={"Authorization": f"Bearer {token_b}"}
        )

        assert respuesta.status_code == 200
        nombres = {item["nombre"] for item in respuesta.json()["items"]}
        assert "Marca de A" not in nombres

    def test_modificar_una_marca_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-marca-3a")
        org_b = _crear_organizacion(sesion, "org-iso-marca-3b")
        marca_a = _crear_marca(sesion, org_a.id, nombre="Marca de A")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-marca-3b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/marcas/{marca_a.id}",
            json={"nombre": "Secuestrada", "activo": True},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        sesion.refresh(marca_a)
        assert marca_a.nombre == "Marca de A"


class TestAislamientoDeProductos:
    """Rutas `POST/GET /catalogo/productos`, `GET/PUT
    /catalogo/productos/{producto_id}` (INV-21, SEG-07). Cubre además el
    caso que pide la tarea 11.1: una referencia ajena EN EL CONTENIDO
    (categoría, marca o alícuota de otra organización)."""

    def test_crear_producto_con_categoria_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prod-1a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-1b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        alicuota_b = _crear_alicuota(sesion, org_b.id, nombre="21%")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prod-1b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/catalogo/productos",
            json=_payload_producto(
                codigo="VA-001", categoria_id=categoria_a.id, alicuota_id=alicuota_b.id
            ),
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        # Ningún producto quedó creado en `org_b` (el handler lanzó antes de
        # escribir nada, INV-01: la transacción se revierte entera).
        listado = cliente.get(
            "/api/v1/catalogo/productos", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert listado.json()["items"] == []

    def test_crear_producto_con_marca_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prod-2a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-2b")
        marca_a = _crear_marca(sesion, org_a.id, nombre="Marca de A")
        categoria_b = _crear_categoria(sesion, org_b.id, nombre="Vinos de B")
        alicuota_b = _crear_alicuota(sesion, org_b.id, nombre="21%")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prod-2b", "admin_b")

        payload = _payload_producto(
            codigo="VA-002", categoria_id=categoria_b.id, alicuota_id=alicuota_b.id
        )
        payload["marca_id"] = str(marca_a.id)

        respuesta = cliente.post(
            "/api/v1/catalogo/productos",
            json=payload,
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_crear_producto_con_alicuota_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prod-3a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-3b")
        alicuota_a = _crear_alicuota(sesion, org_a.id, nombre="21%")
        categoria_b = _crear_categoria(sesion, org_b.id, nombre="Vinos de B")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prod-3b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/catalogo/productos",
            json=_payload_producto(
                codigo="VA-003", categoria_id=categoria_b.id, alicuota_id=alicuota_a.id
            ),
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_listar_productos_no_incluye_los_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prod-4a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-4b")
        _con_gestionar_catalogo(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        alicuota_a = _crear_alicuota(sesion, org_a.id, nombre="21%")
        sesion.commit()
        token_a = _login(cliente, "org-iso-prod-4a", "admin_a")
        token_b = _login(cliente, "org-iso-prod-4b", "admin_b")
        _crear_producto_por_http(
            cliente,
            token_a,
            codigo="VA-004",
            categoria_id=categoria_a.id,
            alicuota_id=alicuota_a.id,
        )

        respuesta = cliente.get(
            "/api/v1/catalogo/productos", headers={"Authorization": f"Bearer {token_b}"}
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["items"] == []

    def test_obtener_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prod-5a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-5b")
        _con_gestionar_catalogo(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        alicuota_a = _crear_alicuota(sesion, org_a.id, nombre="21%")
        sesion.commit()
        token_a = _login(cliente, "org-iso-prod-5a", "admin_a")
        token_b = _login(cliente, "org-iso-prod-5b", "admin_b")
        producto_a = _crear_producto_por_http(
            cliente,
            token_a,
            codigo="VA-005",
            categoria_id=categoria_a.id,
            alicuota_id=alicuota_a.id,
        )

        respuesta = cliente.get(
            f"/api/v1/catalogo/productos/{producto_a['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_modificar_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El `producto_id` ajeno se detecta ANTES de resolver
        categoría/marca/alícuota (`service.modificar_producto`)."""
        org_a = _crear_organizacion(sesion, "org-iso-prod-6a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-6b")
        _con_gestionar_catalogo(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        alicuota_a = _crear_alicuota(sesion, org_a.id, nombre="21%")
        categoria_b = _crear_categoria(sesion, org_b.id, nombre="Vinos de B")
        alicuota_b = _crear_alicuota(sesion, org_b.id, nombre="21%")
        sesion.commit()
        token_a = _login(cliente, "org-iso-prod-6a", "admin_a")
        token_b = _login(cliente, "org-iso-prod-6b", "admin_b")
        producto_a = _crear_producto_por_http(
            cliente,
            token_a,
            codigo="VA-006",
            categoria_id=categoria_a.id,
            alicuota_id=alicuota_a.id,
        )

        respuesta = cliente.put(
            f"/api/v1/catalogo/productos/{producto_a['id']}",
            json={
                "codigo": "SECUESTRADO",
                "nombre": "Secuestrado",
                "categoria_id": str(categoria_b.id),
                "marca_id": None,
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_b.id),
                "activo": True,
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_modificar_un_producto_propio_con_categoria_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El `producto_id` es propio de `org_b`, pero la `categoria_id`
        del cuerpo pertenece a `org_a`: también responde 404 (SEG-07)."""
        org_a = _crear_organizacion(sesion, "org-iso-prod-7a")
        org_b = _crear_organizacion(sesion, "org-iso-prod-7b")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        categoria_a = _crear_categoria(sesion, org_a.id, nombre="Vinos de A")
        categoria_b = _crear_categoria(sesion, org_b.id, nombre="Vinos de B")
        alicuota_b = _crear_alicuota(sesion, org_b.id, nombre="21%")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prod-7b", "admin_b")
        producto_b = _crear_producto_por_http(
            cliente,
            token_b,
            codigo="VA-007",
            categoria_id=categoria_b.id,
            alicuota_id=alicuota_b.id,
        )

        respuesta = cliente.put(
            f"/api/v1/catalogo/productos/{producto_b['id']}",
            json={
                "codigo": "VA-007",
                "nombre": "Vino A",
                "categoria_id": str(categoria_a.id),
                "marca_id": None,
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_b.id),
                "activo": True,
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


class TestAislamientoDePresentaciones:
    """Rutas `POST /catalogo/productos/{producto_id}/presentaciones`, `PUT
    /catalogo/presentaciones/{presentacion_id}` y `PUT
    /catalogo/productos/{producto_id}/referencia` (INV-21, SEG-07)."""

    def _crear_producto_de(
        self, cliente: TestClient, sesion: Session, slug: str, nombre_usuario: str, codigo: str
    ) -> tuple[Organizacion, str, dict[str, object]]:
        organizacion = _crear_organizacion(sesion, slug)
        _con_gestionar_catalogo(sesion, organizacion.id, nombre_usuario=nombre_usuario)
        categoria = _crear_categoria(sesion, organizacion.id, nombre=f"Categoria-{codigo}")
        alicuota = _crear_alicuota(sesion, organizacion.id, nombre="21%")
        sesion.commit()
        token = _login(cliente, slug, nombre_usuario)
        producto = _crear_producto_por_http(
            cliente, token, codigo=codigo, categoria_id=categoria.id, alicuota_id=alicuota.id
        )
        return organizacion, token, producto

    def test_agregar_presentacion_a_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _, _, producto_a = self._crear_producto_de(
            cliente, sesion, "org-iso-pres-1a", "admin_a", "VA-P01"
        )
        org_b = _crear_organizacion(sesion, "org-iso-pres-1b")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-pres-1b", "admin_b")

        respuesta = cliente.post(
            f"/api/v1/catalogo/productos/{producto_a['id']}/presentaciones",
            json={
                "nombre": "Caja x12",
                "unidades_base": 12,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_modificar_una_presentacion_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _, _, producto_a = self._crear_producto_de(
            cliente, sesion, "org-iso-pres-2a", "admin_a", "VA-P02"
        )
        presentacion_a_id = producto_a["presentaciones"][0]["id"]
        org_b = _crear_organizacion(sesion, "org-iso-pres-2b")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-pres-2b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/presentaciones/{presentacion_a_id}",
            json={
                "nombre": "Secuestrada",
                "unidades_base": 1,
                "usar_en_venta": True,
                "usar_en_compra": True,
                "activo": True,
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_cambiar_la_referencia_de_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _, _, producto_a = self._crear_producto_de(
            cliente, sesion, "org-iso-pres-3a", "admin_a", "VA-P03"
        )
        presentacion_a_id = producto_a["presentaciones"][0]["id"]
        org_b = _crear_organizacion(sesion, "org-iso-pres-3b")
        _con_gestionar_catalogo(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-pres-3b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/productos/{producto_a['id']}/referencia",
            json={"presentacion_id": presentacion_a_id},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_cambiar_la_referencia_con_una_presentacion_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El `producto_id` es propio de `org_b`, pero la
        `presentacion_id` del cuerpo pertenece a un producto de `org_a`:
        también responde 404 (`service.cambiar_referencia`: la presentación
        no existe en ESTA organización)."""
        _, _, producto_a = self._crear_producto_de(
            cliente, sesion, "org-iso-pres-4a", "admin_a", "VA-P04"
        )
        presentacion_a_id = producto_a["presentaciones"][0]["id"]
        _, token_b, producto_b = self._crear_producto_de(
            cliente, sesion, "org-iso-pres-4b", "admin_b", "VA-P04"
        )

        respuesta = cliente.put(
            f"/api/v1/catalogo/productos/{producto_b['id']}/referencia",
            json={"presentacion_id": presentacion_a_id},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
