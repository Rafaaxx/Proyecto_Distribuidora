"""Change 07, grupo 4, tareas 4.1 y 4.3: endpoints HTTP de `clientes`
(`design.md` D9, enmienda 2026-09-29).

Mismo arnés HTTP que `test_proveedores_api.py` (Postgres real, `cliente` con
motor propio, login real -- nunca un access token fabricado a mano con
`emitir_access_token`, porque eso no probaría que el flujo de autenticación
real produzca un contexto correcto).

Cubre lo que las tres rutas prometen y nada más:

- `GET /clientes` con permiso: listado de la organización, filtro por texto y
  por estado, insignia de `estado` y `es_consumidor_final` (spec
  `administracion-de-clientes`, escenarios "Buscar un cliente por texto" y
  "Filtrar por estado suspendido"), y paginación por cursor que trae a cada
  cliente exactamente una vez.
- `GET /clientes/{id}`: los tres campos de crédito en **solo lectura** para
  quien tiene `GESTIONAR_CLIENTES` y no `GESTIONAR_CREDITO` (D3, escenario
  "La ficha muestra el crédito en solo lectura"), y los importes como
  **string** (INV-03, `CLAUDE.md` §4).
- `GET /clientes/consumidor-final`: 200 con `habilitado: false` cuando la
  organización no lo habilitó -- NO 404, que es un estado normal y no un
  recurso inexistente -- y 200 con el cliente cuando sí (spec
  `consumidor-final`).
- Las tres rutas con `403 PERMISO_REQUERIDO` sin `GESTIONAR_CLIENTES`,
  incluido el rol que tiene `GESTIONAR_CREDITO` y no `GESTIONAR_CLIENTES`
  (escenario "Permiso de crédito sin permiso de clientes").
- `GET /clientes/consumidor-final` no responde 422: se declara antes que
  `/{cliente_id}` para que FastAPI no intente leer `consumidor-final` como
  un UUID.
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
from app.modules.clientes import repository as clientes_repository
from app.modules.clientes.models import Cliente
from app.modules.identidad import repository
from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-clientes-api"


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
    for codigo in sorted(permisos):
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
    return usuario


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


def _crear_cliente(
    sesion: Session,
    organizacion_id: UUID,
    *,
    nombre: str,
    estado: str = "ACTIVO",
    es_consumidor_final: bool = False,
    limite_credito: Decimal | None = None,
    politica_credito: str | None = None,
    tolerancia_offline_tipo: str | None = None,
    tolerancia_offline_valor: Decimal | None = None,
    codigo: str | None = None,
    documento_tipo: str | None = None,
    documento_numero: str | None = None,
) -> Cliente:
    cliente = clientes_repository.crear_cliente(
        organizacion_id,
        sesion,
        cliente_id=nuevo_id(),
        nombre=nombre,
        codigo=codigo,
        razon_social=None,
        documento_tipo=documento_tipo,
        documento_numero=documento_numero,
        direccion="Av. San Martín 1420",
        contacto="Rocío",
        telefono=None,
        email=None,
        lista_precio_id=None,
        estado_facturacion_default=None,
        es_consumidor_final=es_consumidor_final,
        limite_credito=limite_credito,
        politica_credito=politica_credito,
        tolerancia_offline_tipo=tolerancia_offline_tipo,
        tolerancia_offline_valor=tolerancia_offline_valor,
        estado=estado,
        momento=MOMENTO,
    )
    sesion.flush()
    return cliente


def _organizacion_con_gestionar_clientes(sesion: Session, slug: str) -> tuple[Organizacion, str]:
    organizacion = _crear_organizacion(sesion, slug)
    _crear_usuario(
        sesion,
        organizacion.id,
        permisos=frozenset({"GESTIONAR_CLIENTES"}),
        nombre_usuario="supervisor",
    )
    sesion.commit()
    return organizacion, slug


# --- listado (GET /clientes) -------------------------------------------------


class TestListadoDeClientes:
    def test_lista_los_clientes_de_la_organizacion_con_estado_y_marca(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        _crear_cliente(
            sesion,
            organizacion.id,
            nombre="Kiosco La Esquina",
            estado="ACTIVO",
            limite_credito=Decimal("150000.00"),
        )
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco El Faro", estado="SUSPENDIDO")
        _crear_cliente(
            sesion,
            organizacion.id,
            nombre="Consumidor final",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get("/api/v1/clientes", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert [item["nombre"] for item in cuerpo["items"]] == [
            "Consumidor final",
            "Kiosco El Faro",
            "Kiosco La Esquina",
        ], "El listado ordena por `(nombre, id)` (D1: el nombre no es único)."
        por_nombre = {item["nombre"]: item for item in cuerpo["items"]}
        assert por_nombre["Kiosco La Esquina"]["estado"] == "ACTIVO"
        assert por_nombre["Kiosco El Faro"]["estado"] == "SUSPENDIDO"
        assert por_nombre["Kiosco La Esquina"]["es_consumidor_final"] is False
        assert por_nombre["Consumidor final"]["es_consumidor_final"] is True
        assert por_nombre["Kiosco La Esquina"]["limite_credito"] == "150000.00", (
            "Los importes viajan como string (INV-03, `CLAUDE.md` §4)."
        )
        assert cuerpo["cursor_siguiente"] is None, "Tres clientes con el límite por defecto."

    def test_filtra_por_texto(self, cliente: TestClient, sesion: Session) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina", estado="ACTIVO")
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco El Faro", estado="SUSPENDIDO")
        sesion.commit()
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes",
            params={"texto": "Esquina"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 200
        nombres = [item["nombre"] for item in respuesta.json()["items"]]
        assert nombres == ["Kiosco La Esquina"], (
            "Escenario 'Buscar un cliente por texto': `Esquina` trae `Kiosco La "
            "Esquina` y no trae `Kiosco El Faro`."
        )

    def test_filtra_por_estado(self, cliente: TestClient, sesion: Session) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina", estado="ACTIVO")
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco El Faro", estado="SUSPENDIDO")
        sesion.commit()
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes",
            params={"estado": "SUSPENDIDO"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 200
        nombres = [item["nombre"] for item in respuesta.json()["items"]]
        assert nombres == ["Kiosco El Faro"], "Escenario 'Filtrar por estado suspendido'."

    def test_rechaza_un_estado_fuera_del_catalogo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes",
            params={"estado": "BORRADO"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 422, (
            f"`estado` se valida contra el catálogo cerrado (`01` §18, CLI-02): un "
            f"valor fuera es una petición inválida, no un filtro vacío y no un "
            f"500. Salió {respuesta.status_code}: {respuesta.text}"
        )
        assert respuesta.json()["codigo"] == "ESTADO_INVALIDO"

    def test_la_paginacion_por_cursor_trae_cada_cliente_una_sola_vez(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        for indice in range(5):
            _crear_cliente(sesion, organizacion.id, nombre=f"Kiosco {indice}")
        sesion.commit()
        token = _login(cliente, slug, "supervisor")
        cabeceras = {"Authorization": f"Bearer {token}"}

        vistos: list[str] = []
        cursor: str | None = None
        for _pagina in range(10):  # tope anti-bucle: con 5 filas y límite 2 son 3 páginas
            params: dict[str, str] = {"limite": "2"}
            if cursor is not None:
                params["cursor"] = cursor
            respuesta = cliente.get("/api/v1/clientes", params=params, headers=cabeceras)
            assert respuesta.status_code == 200
            cuerpo = respuesta.json()
            vistos.extend(item["nombre"] for item in cuerpo["items"])
            cursor = cuerpo["cursor_siguiente"]
            if cursor is None:
                break

        assert len(vistos) == len(set(vistos)) == 5, (
            "La paginación por cursor no repite ni saltea clientes."
        )
        assert cursor is None

    def test_sin_permiso_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-a")
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_CREDITO"}),
            nombre_usuario="solo-credito",
        )
        sesion.commit()
        token = _login(cliente, "org-a", "solo-credito")

        respuesta = cliente.get("/api/v1/clientes", headers={"Authorization": f"Bearer {token}"})

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO", (
            "`GESTIONAR_CREDITO` sin `GESTIONAR_CLIENTES` no habilita la sección "
            "de clientes (spec `administracion-de-clientes`, escenario 'Permiso "
            "de crédito sin permiso de clientes'; ADR-028)."
        )


# --- ficha (GET /clientes/{id}) ----------------------------------------------


class TestFichaDeCliente:
    def test_trae_la_ficha_con_el_credito_en_solo_lectura(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        creado = _crear_cliente(
            sesion,
            organizacion.id,
            nombre="Kiosco La Esquina",
            limite_credito=Decimal("150000.00"),
            politica_credito="AUTORIZAR",
            tolerancia_offline_tipo="IMPORTE",
            tolerancia_offline_valor=Decimal("5000.00"),
            codigo="C-001",
            documento_tipo="DNI",
            documento_numero="30111222",
        )
        sesion.commit()
        cliente_id = creado.id
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get(
            f"/api/v1/clientes/{cliente_id}", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["id"] == str(cliente_id)
        assert cuerpo["nombre"] == "Kiosco La Esquina"
        assert cuerpo["codigo"] == "C-001"
        assert cuerpo["documento_tipo"] == "DNI"
        assert cuerpo["documento_numero"] == "30111222"
        assert cuerpo["limite_credito"] == "150000.00"
        assert cuerpo["politica_credito"] == "AUTORIZAR"
        assert cuerpo["tolerancia_offline_tipo"] == "IMPORTE"
        assert cuerpo["tolerancia_offline_valor"] == "5000.00", (
            "Escenario 'La ficha muestra el crédito en solo lectura': un usuario "
            "sin `GESTIONAR_CREDITO` ve los tres campos aunque no pueda editarlos "
            "(D3)."
        )

    def test_trae_el_credito_heredado_como_nulo_y_no_como_cero(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "supervisor")

        cuerpo = cliente.get(
            f"/api/v1/clientes/{creado.id}", headers={"Authorization": f"Bearer {token}"}
        ).json()

        assert cuerpo["limite_credito"] is None, (
            "Un límite nulo significa HEREDA de la organización, no cero ni "
            "ausente (CRE-03, CRE-06, D8). La API lo expone como `null` para que "
            "el formulario distinga la herencia de un límite en cero."
        )
        assert cuerpo["politica_credito"] is None
        assert cuerpo["tolerancia_offline_tipo"] is None
        assert cuerpo["tolerancia_offline_valor"] is None

    def test_un_cliente_inexistente_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _organizacion_con_gestionar_clientes(sesion, "org-a")
        token = _login(cliente, "org-a", "supervisor")

        respuesta = cliente.get(
            f"/api/v1/clientes/{uuid4()}", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_sin_permiso_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-a")
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset(),
            nombre_usuario="vendedor",
        )
        sesion.commit()
        token = _login(cliente, "org-a", "vendedor")

        respuesta = cliente.get(
            f"/api/v1/clientes/{creado.id}", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


# --- consumidor final (GET /clientes/consumidor-final) -----------------------


class TestConsumidorFinal:
    def test_organizacion_sin_consumidor_final_responde_200_sin_cliente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _organizacion_con_gestionar_clientes(sesion, "org-a")
        token = _login(cliente, "org-a", "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes/consumidor-final", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 200, (
            "Escenario 'Organización sin consumidor final': la respuesta es 200 "
            "con `habilitado: false`, NO 404 -- no habilitarlo es un estado "
            "normal de la organización, no un recurso inexistente (spec "
            "`consumidor-final`)."
        )
        cuerpo = respuesta.json()
        assert cuerpo == {"habilitado": False, "cliente": None}

    def test_organizacion_con_consumidor_final_trae_el_cliente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
        creado = _crear_cliente(
            sesion,
            organizacion.id,
            nombre="Consumidor final",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        cliente_id = creado.id
        token = _login(cliente, slug, "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes/consumidor-final", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["habilitado"] is True
        assert cuerpo["cliente"]["id"] == str(cliente_id)
        assert cuerpo["cliente"]["nombre"] == "Consumidor final"
        assert cuerpo["cliente"]["es_consumidor_final"] is True
        assert cuerpo["cliente"]["limite_credito"] == "0.00", (
            "Escenario 'El consumidor final habilitado tiene límite cero' (CLI-03)."
        )

    def test_no_responde_422_por_el_orden_de_declaracion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """`/consumidor-final` se declara ANTES que `/{cliente_id}`: si no,
        FastAPI intenta leer `consumidor-final` como un UUID y responde 422 en
        vez de 200 (mismo criterio que `/proveedores/opciones`)."""
        _organizacion_con_gestionar_clientes(sesion, "org-a")
        token = _login(cliente, "org-a", "supervisor")

        respuesta = cliente.get(
            "/api/v1/clientes/consumidor-final", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 200, (
            f"422 significa que la ruta por id se declaró antes: {respuesta.text}"
        )

    def test_sin_permiso_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        organizacion = _crear_organizacion(sesion, "org-a")
        _crear_usuario(
            sesion,
            organizacion.id,
            permisos=frozenset({"GESTIONAR_CREDITO"}),
            nombre_usuario="solo-credito",
        )
        sesion.commit()
        token = _login(cliente, "org-a", "solo-credito")

        respuesta = cliente.get(
            "/api/v1/clientes/consumidor-final", headers={"Authorization": f"Bearer {token}"}
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO", (
            "Escenario 'Sin permiso de clientes' (spec `consumidor-final`)."
        )

    def test_sin_sesion_responde_401(self, cliente: TestClient) -> None:
        respuesta = cliente.get("/api/v1/clientes/consumidor-final")

        assert respuesta.status_code == 401
        assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_AUSENTE", (
            "La exención de permiso de `/yo` es de PERMISO, nunca de SESIÓN "
            "(ADR-027); lo mismo vale para estas tres rutas."
        )


# --- forma del contrato -------------------------------------------------------


def test_los_importes_de_la_api_viajan_como_string_y_no_como_numero(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-03: ningún importe de la respuesta es un `float` de JSON. Si
    alguno lo fuera, el `1e5` de abajo se compararía distinto y el cliente
    perdería los dos decimales."""
    organizacion, slug = _organizacion_con_gestionar_clientes(sesion, "org-a")
    _crear_cliente(
        sesion,
        organizacion.id,
        nombre="Kiosco La Esquina",
        limite_credito=Decimal("150000.00"),
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("5000.00"),
    )
    sesion.commit()
    token = _login(cliente, slug, "supervisor")

    cuerpo = cliente.get("/api/v1/clientes", headers={"Authorization": f"Bearer {token}"}).json()

    for item in cuerpo["items"]:
        for campo in ("limite_credito", "tolerancia_offline_valor"):
            valor = item[campo]
            assert valor is None or isinstance(valor, str), (
                f"{campo} salió como {type(valor).__name__}, no como string."
            )
    assert cuerpo["items"][0]["limite_credito"] == "150000.00"


def test_una_cliente_inexistente_por_id_responde_404_y_no_422(
    cliente: TestClient, sesion: Session
) -> None:
    """Un id que no es UUID es 422 de validación de ruta; uno que es UUID y no
    existe es 404 de recurso. Son dos cosas distintas y no se mezclan."""
    _organizacion_con_gestionar_clientes(sesion, "org-a")
    token = _login(cliente, "org-a", "supervisor")
    cabeceras = {"Authorization": f"Bearer {token}"}

    no_uuid = cliente.get("/api/v1/clientes/no-es-un-uuid", headers=cabeceras)
    no_existe = cliente.get(f"/api/v1/clientes/{UUID(int=0)}", headers=cabeceras)

    assert no_uuid.status_code == 422
    assert no_existe.status_code == 404


# --- escrituras (tarea 4.3, `design.md` D9 enmienda 2026-09-29) --------------
#
# Cuatro rutas dedicadas, una por comando `ONLINE`, mismo patrón que
# `proveedores/api.py`: `Operation-Id` obligatorio (400 sin él), permiso por
# ruta (403 `PERMISO_REQUERIDO` sin efectos ni reserva), 404 para un recurso
# ajeno, y el mismo `operation_id` reenviado devuelve el mismo resultado sin
# duplicar la fila (SYN-02/INV-06).


def _organizacion_con_permisos(
    sesion: Session,
    slug: str,
    *,
    permisos: frozenset[str],
    nombre_usuario: str = "admin",
    con_configuracion: bool = False,
) -> tuple[Organizacion, str]:
    organizacion = _crear_organizacion(sesion, slug)
    if con_configuracion:
        # `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` escribe
        # `configuracion_organizacion` (D4): sin esta fila,
        # `identidad_service.configurar_consumidor_final` devuelve `None` y
        # `clientes_service` lo traduce en `ConfiguracionDeOrganizacionAusenteError`.
        sesion.add(
            ConfiguracionOrganizacion(
                organizacion_id=organizacion.id,
                modo_impositivo="B",
                lista_precio_default_id=None,
                politica_credito_default="ADVERTIR",
                tolerancia_offline_tipo=None,
                tolerancia_offline_valor=None,
                descuento_manual_habilitado=False,
                motivo_obligatorio_descuento=None,
                motivo_obligatorio_lista=True,
                redondeo_multiplo=None,
                redondeo_direccion=None,
                permite_consumidor_final=None,
                cliente_consumidor_final_id=None,
                estado_facturacion_default="PENDIENTE",
                modalidad_iva_default="CLIENTE",
                intentos_pin_max=3,
                desvio_reloj_max_segundos=None,
                creado_en=MOMENTO,
                actualizado_en=MOMENTO,
                actualizado_por_id=None,
            )
        )
        sesion.flush()
    _crear_usuario(sesion, organizacion.id, permisos=permisos, nombre_usuario=nombre_usuario)
    sesion.commit()
    return organizacion, slug


class TestCrearCliente:
    def test_crea_un_cliente_con_gestionar_clientes(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        _organizacion_con_permisos(sesion, "org-crear", permisos=frozenset({"GESTIONAR_CLIENTES"}))
        token = _login(cliente, "org-crear", "admin")

        respuesta = cliente.post(
            "/api/v1/clientes",
            json={
                "nombre": "Kiosco La Esquina",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
            },
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["nombre"] == "Kiosco La Esquina"
        assert cuerpo["estado"] == "ACTIVO", "D7: el cliente nace ACTIVO."
        assert cuerpo["es_consumidor_final"] is False

    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-crear-400", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        token = _login(cliente, slug, "admin")

        respuesta = cliente.post(
            "/api/v1/clientes",
            json={
                "nombre": "Kiosco La Esquina",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_sin_permiso_se_rechaza_sin_crear_nada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-crear-403", permisos=frozenset()
        )
        token = _login(cliente, slug, "admin")

        respuesta = cliente.post(
            "/api/v1/clientes",
            json={
                "nombre": "Kiosco La Esquina",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
            },
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        items, _ = clientes_repository.listar_clientes_paginado(organizacion.id, sesion, limite=10)
        assert items == []

    def test_reenvio_del_mismo_operation_id_devuelve_el_mismo_cliente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-crear-idem", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        token = _login(cliente, slug, "admin")
        operation_id = str(uuid4())
        headers = {"Authorization": f"Bearer {token}", "Operation-Id": operation_id}
        cuerpo_pedido = {
            "nombre": "Kiosco La Esquina",
            "direccion": "Av. San Martín 1420",
            "contacto": "Rocío",
        }

        primera = cliente.post("/api/v1/clientes", json=cuerpo_pedido, headers=headers)
        segunda = cliente.post("/api/v1/clientes", json=cuerpo_pedido, headers=headers)

        assert primera.status_code == 201
        assert segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        items, _ = clientes_repository.listar_clientes_paginado(organizacion.id, sesion, limite=10)
        assert len(items) == 1

    def test_mismo_operation_id_con_contenido_distinto_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Spec `fichas-de-cliente`, escenario "Mismo operation_id con
        contenido distinto" (SYN-02): la huella del segundo envío no
        coincide con la reservada por el primero, así que se rechaza con
        `COMANDO_INCONSISTENTE` y `Kiosco El Faro` nunca se crea."""
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-crear-inconsistente", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        token = _login(cliente, slug, "admin")
        operation_id = str(uuid4())
        headers = {"Authorization": f"Bearer {token}", "Operation-Id": operation_id}

        primera = cliente.post(
            "/api/v1/clientes",
            json={
                "nombre": "Kiosco La Esquina",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
            },
            headers=headers,
        )
        segunda = cliente.post(
            "/api/v1/clientes",
            json={
                "nombre": "Kiosco El Faro",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
            },
            headers=headers,
        )

        assert primera.status_code == 201
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        items, _ = clientes_repository.listar_clientes_paginado(organizacion.id, sesion, limite=10)
        assert [item.nombre for item in items] == ["Kiosco La Esquina"]


class TestModificarCliente:
    def test_modifica_la_ficha_y_el_estado(self, cliente: TestClient, sesion: Session) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-modificar", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{creado.id}",
            json={
                "nombre": "Kiosco La Esquina S.A.",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
                "estado": "SUSPENDIDO",
            },
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["nombre"] == "Kiosco La Esquina S.A."
        assert cuerpo["estado"] == "SUSPENDIDO"

    def test_un_cliente_ajeno_responde_404(self, cliente: TestClient, sesion: Session) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-mod-a")
        ajeno = _crear_cliente(sesion, organizacion_a.id, nombre="Kiosco La Esquina")
        organizacion_b, slug_b = _organizacion_con_permisos(
            sesion, "org-mod-b", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        sesion.commit()
        token_b = _login(cliente, slug_b, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{ajeno.id}",
            json={
                "nombre": "Robado",
                "direccion": "Otra dirección",
                "contacto": "Nadie",
                "estado": "ACTIVO",
            },
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_sin_permiso_se_rechaza_sin_modificar_nada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(sesion, "org-mod-403", permisos=frozenset())
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{creado.id}",
            json={
                "nombre": "Otro nombre",
                "direccion": "Otra dirección",
                "contacto": "Otro",
                "estado": "ACTIVO",
            },
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


class TestModificarCredito:
    def test_un_usuario_con_gestionar_credito_modifica_el_limite(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-credito", permisos=frozenset({"GESTIONAR_CREDITO"})
        )
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{creado.id}/credito",
            json={"limite_credito": "150000.00", "politica_credito": "AUTORIZAR"},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["limite_credito"] == "150000.00"
        assert cuerpo["politica_credito"] == "AUTORIZAR"

    def test_solo_gestionar_clientes_sin_credito_responde_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-credito-403", permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{creado.id}/credito",
            json={"limite_credito": "150000.00"},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO", (
            "D3: `GESTIONAR_CLIENTES` no alcanza para escribir el crédito."
        )

    def test_mismo_operation_id_con_contenido_distinto_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Spec `datos-de-credito`, escenario "Mismo operation_id con
        contenido distinto": el límite reservado por la primera huella
        (`"150000.00"`) no se pisa con el segundo envío."""
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-credito-inconsistente", permisos=frozenset({"GESTIONAR_CREDITO"})
        )
        creado = _crear_cliente(sesion, organizacion.id, nombre="Kiosco La Esquina")
        sesion.commit()
        token = _login(cliente, slug, "admin")
        operation_id = str(uuid4())
        headers = {"Authorization": f"Bearer {token}", "Operation-Id": operation_id}

        primera = cliente.put(
            f"/api/v1/clientes/{creado.id}/credito",
            json={"limite_credito": "150000.00"},
            headers=headers,
        )
        segunda = cliente.put(
            f"/api/v1/clientes/{creado.id}/credito",
            json={"limite_credito": "90000.00"},
            headers=headers,
        )

        assert primera.status_code == 200
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        sesion.expire_all()
        actual = clientes_repository.obtener_cliente_por_id(organizacion.id, creado.id, sesion)
        assert actual is not None
        assert actual.limite_credito == Decimal("150000.00")

    def test_un_cliente_ajeno_responde_404(self, cliente: TestClient, sesion: Session) -> None:
        organizacion_a = _crear_organizacion(sesion, "org-credito-a")
        ajeno = _crear_cliente(
            sesion, organizacion_a.id, nombre="Kiosco La Esquina", limite_credito=Decimal("100.00")
        )
        organizacion_b, slug_b = _organizacion_con_permisos(
            sesion, "org-credito-b", permisos=frozenset({"GESTIONAR_CREDITO"})
        )
        sesion.commit()
        token_b = _login(cliente, slug_b, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{ajeno.id}/credito",
            json={"limite_credito": "999999.00"},
            headers={"Authorization": f"Bearer {token_b}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    def test_el_consumidor_final_no_admite_credito_propio(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-credito-cf", permisos=frozenset({"GESTIONAR_CREDITO"})
        )
        consumidor_final = _crear_cliente(
            sesion,
            organizacion.id,
            nombre="Consumidor final",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        token = _login(cliente, slug, "admin")

        respuesta = cliente.put(
            f"/api/v1/clientes/{consumidor_final.id}/credito",
            json={"limite_credito": "50000.00"},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "CONSUMIDOR_FINAL_SIN_CREDITO"


class TestConfigurarConsumidorFinal:
    def test_un_admin_habilita_el_consumidor_final(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion,
            "org-cf-hab",
            permisos=frozenset({"ADMIN_CONFIGURACION"}),
            con_configuracion=True,
        )
        token = _login(cliente, slug, "admin")

        respuesta = cliente.post(
            "/api/v1/clientes/consumidor-final",
            json={"nombre": "Consumidor final"},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["nombre"] == "Consumidor final"
        assert cuerpo["es_consumidor_final"] is True
        assert cuerpo["limite_credito"] == "0.00"

    def test_sin_admin_configuracion_responde_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion, "org-cf-403", permisos=frozenset({"GESTIONAR_CLIENTES"}), con_configuracion=True
        )
        token = _login(cliente, slug, "admin")

        respuesta = cliente.post(
            "/api/v1/clientes/consumidor-final",
            json={"nombre": "Consumidor final"},
            headers={"Authorization": f"Bearer {token}", "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO", (
            "D4: solo `ADMIN_CONFIGURACION` puede habilitarlo."
        )

    def test_habilitar_dos_veces_se_rechaza(self, cliente: TestClient, sesion: Session) -> None:
        organizacion, slug = _organizacion_con_permisos(
            sesion,
            "org-cf-doble",
            permisos=frozenset({"ADMIN_CONFIGURACION"}),
            con_configuracion=True,
        )
        token = _login(cliente, slug, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        primera = cliente.post(
            "/api/v1/clientes/consumidor-final",
            json={"nombre": "Consumidor final"},
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        segunda = cliente.post(
            "/api/v1/clientes/consumidor-final",
            json={"nombre": "Consumidor final"},
            headers={**headers, "Operation-Id": str(uuid4())},
        )

        assert primera.status_code == 201
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "CONSUMIDOR_FINAL_YA_HABILITADO"
