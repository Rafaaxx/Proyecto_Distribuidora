"""Change 06, tarea 12.1: cobertura de aislamiento (INV-21) de las ocho
rutas nuevas de `proveedores/api.py` -- las que
`test_inv21_ratchet_rutas.py::test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento`
señala como sin cobertura hasta que se agregan a `COBERTURA_DE_AISLAMIENTO`
con su prueba real acá (RED confirmado antes: 8 rutas sin cobertura).

Mismo arnés HTTP que `test_inv21_aislamiento_endpoints_catalogo.py`
(Postgres real, `cliente` con motor propio, login real de dos
organizaciones -- nunca un access token fabricado a mano). Además de
"recurso ajeno -> 404" para cada ruta con id, cubre lo que pide la tarea
explícitamente: una referencia ajena EN EL CONTENIDO de `COSTO_INFORMAR`
(`proveedor_id`, `producto_id`, `presentacion_id` de otra organización) y
de `PRODUCTO_CREAR`/`PRODUCTO_MODIFICAR` v2 (`proveedor_id` de otra
organización -- caso que `test_inv21_aislamiento_endpoints_catalogo.py`
todavía no cubre: sus pruebas de referencia ajena son sobre
categoría/marca/alícuota, no sobre proveedor).

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
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores.models import Proveedor

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento-proveedores"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


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


def _con_gestionar_proveedores(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset(
            {"GESTIONAR_PROVEEDORES", "GESTIONAR_CATALOGO", "EDITAR_COSTOS", "VER_COSTOS"}
        ),
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


def _crear_proveedor(sesion: Session, organizacion_id: UUID, *, nombre: str) -> Proveedor:
    proveedor = proveedores_repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre=nombre,
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=True,
        momento=MOMENTO,
    )
    sesion.flush()
    return proveedor


def _crear_categoria(sesion: Session, organizacion_id: UUID, *, nombre: str):
    return catalogo_repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
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


def _crear_producto_con_presentacion_de_compra(
    sesion: Session, organizacion_id: UUID, *, proveedor_id: UUID, codigo: str
):
    categoria = _crear_categoria(sesion, organizacion_id, nombre=f"Categoria-{codigo}")
    alicuota = _crear_alicuota(sesion, organizacion_id, nombre=f"Alicuota-{codigo}")
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        sesion,
        producto_id=nuevo_id(),
        codigo=codigo,
        nombre="Producto de prueba",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="unidad",
        alicuota_id=alicuota.id,
        activo=True,
        momento=MOMENTO,
    )
    presentacion = catalogo_repository.crear_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Presentación de compra",
        unidades_base=12,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        momento=MOMENTO,
    )
    return producto, presentacion, categoria, alicuota


class TestAislamientoDeProveedores:
    """Rutas `POST/GET /proveedores`, `GET /proveedores/opciones`,
    `GET/PUT /proveedores/{proveedor_id}` (INV-21, SEG-07)."""

    def test_obtener_un_proveedor_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prov-1a")
        org_b = _crear_organizacion(sesion, "org-iso-prov-1b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prov-1b", "admin_b")

        respuesta = cliente.get(
            f"/api/v1/proveedores/{proveedor_a.id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_modificar_un_proveedor_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prov-2a")
        org_b = _crear_organizacion(sesion, "org-iso-prov-2b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prov-2b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/proveedores/{proveedor_a.id}",
            json={"nombre": "Secuestrado", "activo": True},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        # No se modificó nada de `org_a` (aunque el token era de `org_b`,
        # ni siquiera existe la fila para esa organización).
        proveedores_de_a, _ = proveedores_repository.listar_proveedores_paginado(org_a.id, sesion)
        assert proveedores_de_a[0].nombre == "Bodega Andina"

    def test_listar_proveedores_no_incluye_los_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prov-3a")
        org_b = _crear_organizacion(sesion, "org-iso-prov-3b")
        _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prov-3b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/proveedores", headers={"Authorization": f"Bearer {token_b}"}
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["items"] == []

    def test_opciones_de_proveedores_no_incluye_los_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prov-4a")
        org_b = _crear_organizacion(sesion, "org-iso-prov-4b")
        _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prov-4b", "admin_b")

        respuesta = cliente.get(
            "/api/v1/proveedores/opciones", headers={"Authorization": f"Bearer {token_b}"}
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["items"] == []

    def test_crear_proveedor_no_lo_expone_a_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """`POST /proveedores` no tiene un "recurso ajeno" que referenciar
        (crea uno nuevo): el aislamiento se verifica del otro lado, listando
        con el token de la organización que no lo creó."""
        org_a = _crear_organizacion(sesion, "org-iso-prov-5a")
        org_b = _crear_organizacion(sesion, "org-iso-prov-5b")
        _con_gestionar_proveedores(sesion, org_a.id, nombre_usuario="admin_a")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_a = _login(cliente, "org-iso-prov-5a", "admin_a")
        token_b = _login(cliente, "org-iso-prov-5b", "admin_b")

        creado = cliente.post(
            "/api/v1/proveedores",
            json={"nombre": "Bodega Andina"},
            headers={"Authorization": f"Bearer {token_a}", "Operation-Id": str(uuid4())},
        )
        assert creado.status_code == 201, creado.text

        listado_b = cliente.get(
            "/api/v1/proveedores", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert listado_b.json()["items"] == []


class TestAislamientoDeCostos:
    """Rutas `POST /costos`, `GET /costos/productos/{producto_id}/vigente`,
    `GET /costos/productos/{producto_id}/historial` (INV-21, SEG-07).
    Cubre además el caso que pide la tarea 12.1: una referencia ajena EN EL
    CONTENIDO de `COSTO_INFORMAR` -- `proveedor_id`, `producto_id` y
    `presentacion_id`, cada uno por separado."""

    def test_informar_costos_con_proveedor_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-costo-1a")
        org_b = _crear_organizacion(sesion, "org-iso-costo-1b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        proveedor_b = _crear_proveedor(sesion, org_b.id, nombre="Distribuidora Norte")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        producto_b, presentacion_b, _c, _a = _crear_producto_con_presentacion_de_compra(
            sesion, org_b.id, proveedor_id=proveedor_b.id, codigo="CB-ISO-1"
        )
        sesion.commit()
        token_b = _login(cliente, "org-iso-costo-1b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor_a.id),
                "costos": [
                    {
                        "producto_id": str(producto_b.id),
                        "presentacion_id": str(presentacion_b.id),
                        "valor": "1000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_informar_costos_con_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-costo-2a")
        org_b = _crear_organizacion(sesion, "org-iso-costo-2b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        producto_a, presentacion_a, _c, _a = _crear_producto_con_presentacion_de_compra(
            sesion, org_a.id, proveedor_id=proveedor_a.id, codigo="CB-ISO-2A"
        )
        proveedor_b = _crear_proveedor(sesion, org_b.id, nombre="Distribuidora Norte")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-costo-2b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor_b.id),
                "costos": [
                    {
                        "producto_id": str(producto_a.id),
                        "presentacion_id": str(presentacion_a.id),
                        "valor": "1000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_informar_costos_con_presentacion_de_otra_organizacion_no_la_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El producto es propio de `org_b` (y su proveedor corresponde),
        pero la `presentacion_id` del cuerpo pertenece a un producto de
        `org_a`: `catalogo_service.obtener_presentacion` la busca ya
        filtrada por `organizacion_id` (INV-21) y no la encuentra, así que
        `proveedores/service.py::informar_costos` la trata igual que una
        presentación inválida de la propia organización -- 422
        `PRESENTACION_INVALIDA`, no 404. No es un caso distinto de SEG-07:
        no confirma ni niega la existencia de la fila ajena en ningún otro
        lado (ambos casos, ajena o simplemente inválida, dan el mismo
        error), y no hay ningún efecto ni exposición del recurso ajeno."""
        org_a = _crear_organizacion(sesion, "org-iso-costo-3a")
        org_b = _crear_organizacion(sesion, "org-iso-costo-3b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        _producto_a, presentacion_a, _c, _al = _crear_producto_con_presentacion_de_compra(
            sesion, org_a.id, proveedor_id=proveedor_a.id, codigo="CB-ISO-3A"
        )
        proveedor_b = _crear_proveedor(sesion, org_b.id, nombre="Distribuidora Norte")
        producto_b, _presentacion_b, _cb, _ab = _crear_producto_con_presentacion_de_compra(
            sesion, org_b.id, proveedor_id=proveedor_b.id, codigo="CB-ISO-3B"
        )
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-costo-3b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor_b.id),
                "costos": [
                    {
                        "producto_id": str(producto_b.id),
                        "presentacion_id": str(presentacion_a.id),
                        "valor": "1000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "PRESENTACION_INVALIDA"

    def test_costo_vigente_de_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-costo-4a")
        org_b = _crear_organizacion(sesion, "org-iso-costo-4b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        producto_a, _presentacion_a, _c, _al = _crear_producto_con_presentacion_de_compra(
            sesion, org_a.id, proveedor_id=proveedor_a.id, codigo="CB-ISO-4A"
        )
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-costo-4b", "admin_b")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto_a.id}/vigente",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_historial_de_costos_de_un_producto_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-costo-5a")
        org_b = _crear_organizacion(sesion, "org-iso-costo-5b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        producto_a, _presentacion_a, _c, _al = _crear_producto_con_presentacion_de_compra(
            sesion, org_a.id, proveedor_id=proveedor_a.id, codigo="CB-ISO-5A"
        )
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-costo-5b", "admin_b")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto_a.id}/historial",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


class TestReferenciaProveedorAjenaEnProductoV2:
    """`POST/PUT /catalogo/productos` (v2, tarea 9.2): una referencia
    ajena a `proveedor_id` EN EL CONTENIDO -- caso que
    `test_inv21_aislamiento_endpoints_catalogo.py` no cubre (sus pruebas de
    referencia ajena son sobre categoría/marca/alícuota, tarea 11.1 del 05,
    anteriores a que `proveedor_id` existiera en el contrato)."""

    def test_crear_producto_con_proveedor_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prodprov-1a")
        org_b = _crear_organizacion(sesion, "org-iso-prodprov-1b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        categoria_b = _crear_categoria(sesion, org_b.id, nombre="Vinos de B")
        alicuota_b = _crear_alicuota(sesion, org_b.id, nombre="21%")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-iso-prodprov-1b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/catalogo/productos",
            json={
                "codigo": "VA-PROV-1",
                "nombre": "Vino A",
                "categoria_id": str(categoria_b.id),
                "marca_id": None,
                "proveedor_id": str(proveedor_a.id),
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_b.id),
                "presentaciones": [
                    {
                        "nombre": "Botella",
                        "unidades_base": 1,
                        "usar_en_venta": True,
                        "usar_en_compra": True,
                        "es_referencia": True,
                    }
                ],
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        listado = cliente.get(
            "/api/v1/catalogo/productos", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert listado.json()["items"] == []

    def test_modificar_producto_con_proveedor_de_otra_organizacion_no_lo_encuentra(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        org_a = _crear_organizacion(sesion, "org-iso-prodprov-2a")
        org_b = _crear_organizacion(sesion, "org-iso-prodprov-2b")
        proveedor_a = _crear_proveedor(sesion, org_a.id, nombre="Bodega Andina")
        proveedor_b = _crear_proveedor(sesion, org_b.id, nombre="Distribuidora Norte")
        _con_gestionar_proveedores(sesion, org_b.id, nombre_usuario="admin_b")
        producto_b, _presentacion_b, categoria_b, alicuota_b = (
            _crear_producto_con_presentacion_de_compra(
                sesion, org_b.id, proveedor_id=proveedor_b.id, codigo="VA-PROV-2"
            )
        )
        sesion.commit()
        token_b = _login(cliente, "org-iso-prodprov-2b", "admin_b")

        respuesta = cliente.put(
            f"/api/v1/catalogo/productos/{producto_b.id}",
            json={
                "codigo": "VA-PROV-2",
                "nombre": "Producto de prueba",
                "categoria_id": str(categoria_b.id),
                "marca_id": None,
                "proveedor_id": str(proveedor_a.id),
                "unidad_base": "unidad",
                "alicuota_id": str(alicuota_b.id),
                "activo": True,
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
