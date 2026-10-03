"""Change 06, grupo 10, tarea 10.3: endpoints HTTP de `proveedores`
(`contrato-api.md`, aprobado por el usuario 2026-09-24).

Mismo arnés HTTP que `test_catalogo_api.py` (Postgres real, `cliente` con
motor propio, login real -- nunca un access token fabricado a mano). Cubre:
sin `Operation-Id` -> 400; sin el permiso de la ruta -> `PERMISO_REQUERIDO`
sin efectos ni reserva (equivalente a un rol Vendedor/Repartidor para
`/proveedores` y para el historial de costos, y a un rol Supervisor
comercial para `COSTO_INFORMAR` -- ninguno de los dos, por `01` §19, tiene
`GESTIONAR_PROVEEDORES`/`EDITAR_COSTOS`/`VER_COSTOS`, así que un usuario sin
esos permisos alcanza para probar el rechazo); con permiso, alta,
modificación y listado de proveedores; los cuatro ejemplos de CST-02
devueltos como string; el escenario de "vigente" con las tres fechas de la
spec (`costos-informados`, "El costo vigente de un producto se resuelve por
fecha"); y un producto ajeno -> 404 (INV-21)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import agregar_configuracion
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

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-proveedores-api"


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
    agregar_configuracion(sesion, organizacion.id)
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


def _con_gestionar_proveedores(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset({"GESTIONAR_PROVEEDORES"}),
        nombre_usuario=nombre_usuario,
    )


def _con_editar_costos(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset({"EDITAR_COSTOS"}),
        nombre_usuario=nombre_usuario,
    )


def _con_ver_costos(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    return _crear_usuario(
        sesion,
        organizacion_id,
        permisos=frozenset({"VER_COSTOS"}),
        nombre_usuario=nombre_usuario,
    )


def _sin_permisos(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str):
    """Equivalente a Vendedor/Repartidor (`/proveedores`, historial de
    costos) o Supervisor comercial (`COSTO_INFORMAR`): ninguno de esos dos
    roles de `01` §19 tiene `GESTIONAR_PROVEEDORES`/`EDITAR_COSTOS`/
    `VER_COSTOS`, así que un usuario sin ningún permiso alcanza para probar
    el rechazo."""
    return _crear_usuario(
        sesion, organizacion_id, permisos=frozenset(), nombre_usuario=nombre_usuario
    )


def _crear_alicuota(
    sesion: Session, organizacion_id: UUID, *, nombre: str, valor: str = "0"
) -> AlicuotaIva:
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        nombre=nombre,
        valor=valor,
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    sesion.flush()
    return alicuota


def _crear_categoria(sesion: Session, organizacion_id: UUID, *, nombre: str):
    return catalogo_repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
        nombre=nombre,
        activo=True,
        momento=MOMENTO,
    )


def _crear_proveedor(
    sesion: Session,
    organizacion_id: UUID,
    *,
    nombre: str,
    cuit: str | None = None,
    activo: bool = True,
):
    return proveedores_repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre=nombre,
        cuit=cuit,
        contacto=None,
        telefono=None,
        email=None,
        activo=activo,
        momento=MOMENTO,
    )


def _crear_producto_con_presentacion_de_compra(
    sesion: Session,
    organizacion_id: UUID,
    *,
    proveedor_id: UUID,
    codigo: str,
    unidades_base: int = 12,
):
    categoria = _crear_categoria(sesion, organizacion_id, nombre=f"Categoria-{codigo}")
    alicuota = _crear_alicuota(sesion, organizacion_id, nombre=f"Alicuota-{codigo}", valor="0")
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        sesion,
        producto_id=nuevo_id(),
        codigo=codigo,
        nombre="Cerveza B",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota.id,
        activo=True,
        momento=MOMENTO,
    )
    presentacion = catalogo_repository.crear_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Caja x12",
        unidades_base=unidades_base,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        momento=MOMENTO,
    )
    return producto, presentacion


class TestCrearYModificarProveedor:
    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-prov-1")
        _con_gestionar_proveedores(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-prov-1", "admin1")

        respuesta = cliente.post(
            "/api/v1/proveedores",
            json={"nombre": "Bodega Andina"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        proveedores, _ = proveedores_repository.listar_proveedores_paginado(organizacion.id, sesion)
        assert proveedores == []

    def test_sin_el_permiso_se_rechaza_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-prov-2")
        _sin_permisos(sesion, organizacion.id, nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-prov-2", "vendedor1")
        operation_id = uuid4()

        respuesta = cliente.post(
            "/api/v1/proveedores",
            json={"nombre": "Bodega Andina"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(operation_id),
            },
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        proveedores, _ = proveedores_repository.listar_proveedores_paginado(organizacion.id, sesion)
        assert proveedores == []
        reserva = sesion.scalar(
            text("select count(*) from comando where operation_id = :oid"),
            {"oid": str(operation_id)},
        )
        assert reserva == 0

    def test_crear_y_modificar_un_proveedor_con_permiso(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-prov-3")
        _con_gestionar_proveedores(sesion, organizacion.id, nombre_usuario="admin1")
        sesion.commit()
        access_token = _login(cliente, "org-prov-3", "admin1")
        headers = {"Authorization": f"Bearer {access_token}"}

        alta = cliente.post(
            "/api/v1/proveedores",
            json={"nombre": "Bodega Andina", "cuit": "20-12345678-9"},
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        assert alta.status_code == 201, alta.text
        cuerpo = alta.json()
        assert cuerpo["nombre"] == "Bodega Andina"
        assert cuerpo["cuit"] == "20123456789"
        assert cuerpo["activo"] is True
        proveedor_id = cuerpo["id"]

        modificacion = cliente.put(
            f"/api/v1/proveedores/{proveedor_id}",
            json={"nombre": "Bodega Andina S.A.", "cuit": None, "activo": True},
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        assert modificacion.status_code == 200, modificacion.text
        assert modificacion.json()["nombre"] == "Bodega Andina S.A."
        assert modificacion.json()["cuit"] is None

        listado = cliente.get("/api/v1/proveedores", headers=headers)
        assert listado.status_code == 200
        assert [p["nombre"] for p in listado.json()["items"]] == ["Bodega Andina S.A."]

    def test_obtener_un_proveedor_de_otra_organizacion_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-prov-4a")
        proveedor_a = _crear_proveedor(sesion, organizacion_a.id, nombre="Bodega Andina")
        organizacion_b = _crear_organizacion(sesion, "org-prov-4b")
        _con_gestionar_proveedores(sesion, organizacion_b.id, nombre_usuario="admin_b")
        sesion.commit()
        token_b = _login(cliente, "org-prov-4b", "admin_b")

        respuesta = cliente.get(
            f"/api/v1/proveedores/{proveedor_a.id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


class TestOpcionesDeProveedores:
    def test_lista_solo_activos_con_gestionar_catalogo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """D8: `/proveedores/opciones` usa `GESTIONAR_CATALOGO`, no
        `GESTIONAR_PROVEEDORES`."""
        organizacion = _crear_organizacion(sesion, "org-prov-5")
        _crear_proveedor(sesion, organizacion.id, nombre="Activo", activo=True)
        _crear_proveedor(sesion, organizacion.id, nombre="Inactivo", activo=False)
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_CATALOGO"}),
            nombre_usuario="admin1",
        )
        sesion.commit()
        access_token = _login(cliente, "org-prov-5", "admin1")

        respuesta = cliente.get(
            "/api/v1/proveedores/opciones",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        assert [item["nombre"] for item in respuesta.json()["items"]] == ["Activo"]
        assert set(respuesta.json()["items"][0].keys()) == {"id", "nombre"}

    def test_listado_completo_y_detalle_exigen_gestionar_proveedores(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """13.1 -- spec `fichas-de-proveedor`, escenario "El listado
        completo exige permiso de proveedores": `GESTIONAR_CATALOGO` solo
        (D8) alcanza `/proveedores/opciones` pero no `GET /proveedores` ni
        `GET /proveedores/{id}` -- sin prueba antes de 13.1 (la única prueba
        de rechazo existente usaba un usuario sin ningún permiso)."""
        organizacion = _crear_organizacion(sesion, "org-prov-6")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_CATALOGO"}),
            nombre_usuario="admin_catalogo",
        )
        sesion.commit()
        access_token = _login(cliente, "org-prov-6", "admin_catalogo")
        headers = {"Authorization": f"Bearer {access_token}"}

        listado = cliente.get("/api/v1/proveedores", headers=headers)
        detalle = cliente.get(f"/api/v1/proveedores/{proveedor.id}", headers=headers)

        assert listado.status_code == 403
        assert listado.json()["codigo"] == "PERMISO_REQUERIDO"
        assert detalle.status_code == 403
        assert detalle.json()["codigo"] == "PERMISO_REQUERIDO"


class TestInformarCostos:
    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-costo-1")
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="admin1")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        producto, presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-001"
        )
        sesion.commit()
        access_token = _login(cliente, "org-costo-1", "admin1")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor.id),
                "costos": [
                    {
                        "producto_id": str(producto.id),
                        "presentacion_id": str(presentacion.id),
                        "valor": "18000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_sin_el_permiso_se_rechaza_sin_efectos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-costo-2")
        _sin_permisos(sesion, organizacion.id, nombre_usuario="supervisor1")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        producto, presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-002"
        )
        sesion.commit()
        access_token = _login(cliente, "org-costo-2", "supervisor1")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor.id),
                "costos": [
                    {
                        "producto_id": str(producto.id),
                        "presentacion_id": str(presentacion.id),
                        "valor": "18000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        vigente, _ = proveedores_repository.listar_historial_de_producto(
            organizacion.id, producto.id, sesion
        )
        assert vigente == []

    @pytest.mark.parametrize(
        ("valor", "incluye_iva", "alicuota", "bonificacion", "unidades", "costo_base_esperado"),
        [
            ("18000.00", False, "0", "0", 12, "1500.000000"),
            ("1000.00", False, "0", "0", 1, "1000.000000"),
            ("18000.00", True, "0.21", "0", 12, "1239.669421"),
            ("18000.00", False, "0", "0.10", 12, "1350.000000"),
        ],
        ids=[
            "CST02-caja-x12-sin-iva",
            "CST02-botella-sin-iva",
            "CST02-caja-x12-con-iva-21",
            "CST02-caja-x12-con-bonificacion-10",
        ],
    )
    def test_los_cuatro_ejemplos_de_cst02_devuelven_costo_base_como_string(
        self,
        cliente: TestClient,
        sesion: Session,
        valor: str,
        incluye_iva: bool,
        alicuota: str,
        bonificacion: str,
        unidades: int,
        costo_base_esperado: str,
    ) -> None:
        organizacion = _crear_organizacion(sesion, f"org-cst02-{uuid4().hex[:8]}")
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="admin1")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        categoria = _crear_categoria(sesion, organizacion.id, nombre="Cervezas")
        alicuota_iva = _crear_alicuota(sesion, organizacion.id, nombre="IVA", valor=alicuota)
        producto = catalogo_repository.crear_producto(
            organizacion.id,
            sesion,
            producto_id=nuevo_id(),
            codigo="CB-CST02",
            nombre="Cerveza B",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor.id,
            unidad_base="botella",
            alicuota_id=alicuota_iva.id,
            activo=True,
            momento=MOMENTO,
        )
        presentacion = catalogo_repository.crear_presentacion(
            organizacion.id,
            sesion,
            presentacion_id=nuevo_id(),
            producto_id=producto.id,
            nombre="Presentacion de compra",
            unidades_base=unidades,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        access_token = _login(cliente, organizacion.slug, "admin1")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor.id),
                "costos": [
                    {
                        "producto_id": str(producto.id),
                        "presentacion_id": str(presentacion.id),
                        "valor": valor,
                        "incluye_iva": incluye_iva,
                        "bonificacion": bonificacion,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert len(cuerpo["costos"]) == 1
        assert cuerpo["costos"][0]["costo_base"] == costo_base_esperado
        assert isinstance(cuerpo["costos"][0]["costo_base"], str)

    def test_error_en_la_segunda_fila_expone_fila_1_y_no_registra_nada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """contrato-api.md P9 (aprobado 2026-09-24): un error puntual de fila
        expone `fila` (índice 0-based dentro de `costos`) en el problem+json.
        La segunda fila referencia una presentación que no es del producto
        (`PRESENTACION_INVALIDA`); la primera es válida por sí sola. INV-01:
        el lote entero se rechaza, no se registra nada."""
        organizacion = _crear_organizacion(sesion, "org-costo-fila-1")
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="admin1")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        producto, presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-FILA-1"
        )
        otro_producto, _otra_presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-FILA-1B"
        )
        sesion.commit()
        access_token = _login(cliente, "org-costo-fila-1", "admin1")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor.id),
                "costos": [
                    {
                        "producto_id": str(producto.id),
                        "presentacion_id": str(presentacion.id),
                        "valor": "18000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    },
                    {
                        "producto_id": str(otro_producto.id),
                        # presentación de otro producto: PRESENTACION_INVALIDA.
                        "presentacion_id": str(presentacion.id),
                        "valor": "1000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    },
                ],
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "PRESENTACION_INVALIDA"
        assert cuerpo["fila"] == 1
        vigente, _ = proveedores_repository.listar_historial_de_producto(
            organizacion.id, producto.id, sesion
        )
        assert vigente == []
        vigente_otro, _ = proveedores_repository.listar_historial_de_producto(
            organizacion.id, otro_producto.id, sesion
        )
        assert vigente_otro == []

    def test_error_en_la_primera_fila_expone_fila_0(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Triangulación de la prueba anterior: con la fila inválida
        primero, `fila` es `0`, no una constante."""
        organizacion = _crear_organizacion(sesion, "org-costo-fila-0")
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="admin1")
        proveedor = _crear_proveedor(sesion, organizacion.id, nombre="Bodega Andina")
        producto, presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-FILA-0"
        )
        otro_producto, _otra_presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion.id, proveedor_id=proveedor.id, codigo="CB-FILA-0B"
        )
        sesion.commit()
        access_token = _login(cliente, "org-costo-fila-0", "admin1")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor.id),
                "costos": [
                    {
                        "producto_id": str(otro_producto.id),
                        # presentación de otro producto: PRESENTACION_INVALIDA.
                        "presentacion_id": str(presentacion.id),
                        "valor": "1000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    },
                    {
                        "producto_id": str(producto.id),
                        "presentacion_id": str(presentacion.id),
                        "valor": "18000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    },
                ],
            },
            headers={"Authorization": f"Bearer {access_token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "PRESENTACION_INVALIDA"
        assert cuerpo["fila"] == 0

    def test_informar_costos_de_un_producto_ajeno_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-costo-3a")
        proveedor_a = _crear_proveedor(sesion, organizacion_a.id, nombre="Bodega Andina")
        producto_a, presentacion_a = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion_a.id, proveedor_id=proveedor_a.id, codigo="CB-003"
        )
        organizacion_b = _crear_organizacion(sesion, "org-costo-3b")
        _con_editar_costos(sesion, organizacion_b.id, nombre_usuario="admin_b")
        proveedor_b = _crear_proveedor(sesion, organizacion_b.id, nombre="Distribuidora Norte")
        sesion.commit()
        token_b = _login(cliente, "org-costo-3b", "admin_b")

        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor_b.id),
                "costos": [
                    {
                        "producto_id": str(producto_a.id),
                        "presentacion_id": str(presentacion_a.id),
                        "valor": "18000.00",
                        "incluye_iva": False,
                        "vigencia_desde": "2026-09-01",
                    }
                ],
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


class TestVigenteYHistorial:
    def _sembrar_dos_costos(self, sesion: Session, organizacion_id: UUID):
        """Spec `costos-informados`, escenario "El costo vigente de un
        producto se resuelve por fecha": `Cerveza B` con vigencia
        `2026-09-01` (costo base `"1500.000000"`) y `2026-10-01` (costo
        base `"1350.000000"`)."""
        proveedor = _crear_proveedor(sesion, organizacion_id, nombre="Bodega Andina")
        producto, presentacion = _crear_producto_con_presentacion_de_compra(
            sesion, organizacion_id, proveedor_id=proveedor.id, codigo="CB-VIG"
        )
        sesion.commit()
        return proveedor, producto, presentacion

    def _informar(
        self,
        cliente: TestClient,
        access_token: str,
        *,
        proveedor_id: UUID,
        producto_id: UUID,
        presentacion_id: UUID,
        valor: str,
        bonificacion: str,
        vigencia_desde: str,
    ) -> None:
        respuesta = cliente.post(
            "/api/v1/costos",
            json={
                "proveedor_id": str(proveedor_id),
                "costos": [
                    {
                        "producto_id": str(producto_id),
                        "presentacion_id": str(presentacion_id),
                        "valor": valor,
                        "incluye_iva": False,
                        "bonificacion": bonificacion,
                        "vigencia_desde": vigencia_desde,
                    }
                ],
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Operation-Id": str(uuid4()),
            },
        )
        assert respuesta.status_code == 201, respuesta.text

    def test_vigente_sin_el_permiso_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-vig-1")
        proveedor, producto, _ = self._sembrar_dos_costos(sesion, organizacion.id)
        _sin_permisos(sesion, organizacion.id, nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-vig-1", "vendedor1")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_vigente_con_las_tres_fechas_del_escenario(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-vig-2")
        proveedor, producto, presentacion = self._sembrar_dos_costos(sesion, organizacion.id)
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="editor1")
        _con_ver_costos(sesion, organizacion.id, nombre_usuario="lector1")
        sesion.commit()
        token_editor = _login(cliente, "org-vig-2", "editor1")
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion.id,
            valor="18000.00",
            bonificacion="0",
            vigencia_desde="2026-09-01",
        )
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion.id,
            valor="18000.00",
            bonificacion="0.10",
            vigencia_desde="2026-10-01",
        )
        token_lector = _login(cliente, "org-vig-2", "lector1")
        headers = {"Authorization": f"Bearer {token_lector}"}

        vigente_15_sep = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente?fecha=2026-09-15", headers=headers
        )
        vigente_01_oct = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente?fecha=2026-10-01", headers=headers
        )
        vigente_31_ago = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente?fecha=2026-08-31", headers=headers
        )

        assert vigente_15_sep.status_code == 200
        assert vigente_15_sep.json()["costo"]["costo_base"] == "1500.000000"
        # `contrato-api.md` P10 (aprobado en la verificación manual 13.5):
        # `CostoInformadoResponse` (compartida con el historial) suma
        # `usuario_nombre` también en `/vigente`.
        assert vigente_15_sep.json()["costo"]["usuario_nombre"] == "Persona de prueba"
        assert vigente_01_oct.status_code == 200
        assert vigente_01_oct.json()["costo"]["costo_base"] == "1350.000000"
        assert vigente_31_ago.status_code == 200
        assert vigente_31_ago.json()["costo"] is None
        assert vigente_31_ago.json()["fecha"] == "2026-08-31"

    def test_vigente_de_un_producto_ajeno_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-vig-3a")
        _proveedor, producto_a, _presentacion = self._sembrar_dos_costos(sesion, organizacion_a.id)
        organizacion_b = _crear_organizacion(sesion, "org-vig-3b")
        _con_ver_costos(sesion, organizacion_b.id, nombre_usuario="lector_b")
        sesion.commit()
        token_b = _login(cliente, "org-vig-3b", "lector_b")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto_a.id}/vigente",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_vigente_incluye_ultimo_costo_por_presentacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """P11 (`contrato-api.md`, aprobado en la verificación manual
        13.5, opción B): `GET .../vigente` suma `por_presentacion`, el
        último costo (D4) de cada presentación con costo a la fecha -- una
        presentación sin costo se omite, y una vigencia futura no se
        considera."""
        organizacion = _crear_organizacion(sesion, "org-vig-4")
        proveedor, producto, presentacion_caja = self._sembrar_dos_costos(sesion, organizacion.id)
        presentacion_botella = catalogo_repository.crear_presentacion(
            organizacion.id,
            sesion,
            presentacion_id=nuevo_id(),
            producto_id=producto.id,
            nombre="Botella",
            unidades_base=1,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=False,
            activo=True,
            momento=MOMENTO,
        )
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="editor1")
        _con_ver_costos(sesion, organizacion.id, nombre_usuario="lector1")
        sesion.commit()
        token_editor = _login(cliente, "org-vig-4", "editor1")
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion_caja.id,
            valor="18000.00",
            bonificacion="0",
            vigencia_desde="2026-09-01",
        )
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion_botella.id,
            valor="1000.00",
            bonificacion="0",
            vigencia_desde="2026-08-01",
        )
        # Un tercer costo futuro sobre la caja no debe aparecer (D4/P11).
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion_caja.id,
            valor="99999.00",
            bonificacion="0",
            vigencia_desde="2027-01-01",
        )
        token_lector = _login(cliente, "org-vig-4", "lector1")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente?fecha=2026-09-15",
            headers={"Authorization": f"Bearer {token_lector}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["costo"]["costo_base"] == "1500.000000"
        por_presentacion = cuerpo["por_presentacion"]
        assert len(por_presentacion) == 2
        # Ordenado por `presentacion_nombre` (P11): "Botella" < "Caja x12".
        assert [item["presentacion_nombre"] for item in por_presentacion] == [
            "Botella",
            "Caja x12",
        ]
        caja = next(item for item in por_presentacion if item["presentacion_nombre"] == "Caja x12")
        assert caja["id"] == cuerpo["costo"]["id"]
        assert caja["valor"] == "18000.00"
        botella = next(
            item for item in por_presentacion if item["presentacion_nombre"] == "Botella"
        )
        assert botella["valor"] == "1000.00"
        assert botella["usuario_nombre"] == "Persona de prueba"

    def test_vigente_sin_costos_por_presentacion_es_lista_vacia(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-vig-5")
        _proveedor, producto, _presentacion = self._sembrar_dos_costos(sesion, organizacion.id)
        _con_ver_costos(sesion, organizacion.id, nombre_usuario="lector1")
        sesion.commit()
        token_lector = _login(cliente, "org-vig-5", "lector1")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/vigente",
            headers={"Authorization": f"Bearer {token_lector}"},
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["costo"] is None
        assert respuesta.json()["por_presentacion"] == []

    def test_historial_sin_el_permiso_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion, "org-hist-1")
        _proveedor, producto, _presentacion = self._sembrar_dos_costos(sesion, organizacion.id)
        _sin_permisos(sesion, organizacion.id, nombre_usuario="vendedor1")
        sesion.commit()
        access_token = _login(cliente, "org-hist-1", "vendedor1")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/historial",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_historial_incluye_nombres_de_proveedor_y_presentacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Contrato-api.md P4 (aprobado 2026-09-24): el historial suma
        `proveedor_nombre` y `presentacion_nombre`, no solo ids."""
        organizacion = _crear_organizacion(sesion, "org-hist-2")
        proveedor, producto, presentacion = self._sembrar_dos_costos(sesion, organizacion.id)
        _con_editar_costos(sesion, organizacion.id, nombre_usuario="editor1")
        _con_ver_costos(sesion, organizacion.id, nombre_usuario="lector1")
        sesion.commit()
        token_editor = _login(cliente, "org-hist-2", "editor1")
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion.id,
            valor="18000.00",
            bonificacion="0",
            vigencia_desde="2026-09-01",
        )
        self._informar(
            cliente,
            token_editor,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion.id,
            valor="18000.00",
            bonificacion="0.10",
            vigencia_desde="2026-10-01",
        )
        token_lector = _login(cliente, "org-hist-2", "lector1")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto.id}/historial",
            headers={"Authorization": f"Bearer {token_lector}"},
        )

        assert respuesta.status_code == 200
        items = respuesta.json()["items"]
        assert len(items) == 2
        # Orden `vigencia_desde DESC` (D4): primero `2026-10-01`.
        assert items[0]["vigencia_desde"] == "2026-10-01"
        assert items[0]["costo_base"] == "1350.000000"
        assert items[1]["vigencia_desde"] == "2026-09-01"
        assert items[1]["costo_base"] == "1500.000000"
        for item in items:
            assert item["proveedor_nombre"] == "Bodega Andina"
            assert item["presentacion_nombre"] == "Caja x12"
            assert UUID(item["usuario_id"])
            # `contrato-api.md` P10 (aprobado en la verificación manual
            # 13.5): suma `usuario_nombre`, el nombre para mostrar de quien
            # registró el costo (`Usuario.nombre`, vía `identidad.service`,
            # nunca `identidad.models`/`repository` directamente).
            assert item["usuario_nombre"] == "Persona de prueba"
            assert item["creado_en"]

    def test_historial_de_un_producto_ajeno_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-hist-3a")
        _proveedor, producto_a, _presentacion = self._sembrar_dos_costos(sesion, organizacion_a.id)
        organizacion_b = _crear_organizacion(sesion, "org-hist-3b")
        _con_ver_costos(sesion, organizacion_b.id, nombre_usuario="lector_b")
        sesion.commit()
        token_b = _login(cliente, "org-hist-3b", "lector_b")

        respuesta = cliente.get(
            f"/api/v1/costos/productos/{producto_a.id}/historial",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
