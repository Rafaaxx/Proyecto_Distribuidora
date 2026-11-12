"""Change 13, tarea 11.1: cobertura de aislamiento (INV-21, SEG-07) de TODAS las rutas de
`precios/api.py` -- las diecinueve -- y de la lista asignada en `clientes/api.py`.

Mismo arnés HTTP que `test_inv21_aislamiento_endpoints_proveedores.py`: Postgres real, `cliente`
con motor propio y login real de dos organizaciones (nunca un access token fabricado a mano).
La organización A tiene una lista con su regla, su borrador y un precio; un usuario de B, con
TODOS los permisos de `precios`, ejerce cada ruta sobre los recursos de A y recibe 404 (nunca
403: no se revela si existe) sin ningún efecto sobre A. Las rutas sin recurso por id (alta,
listado, opciones, lista predeterminada) se prueban de la otra forma: B solo ve lo suyo y
nunca puede apuntar a lo de A (la lista predeterminada de otra organización, la categoría de
otra organización en el contenido).

Reglas citadas: INV-21, SEG-07, `CLAUDE.md` §4 (un recurso de otra organización responde 404).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from precios_utiles import Entorno as EntornoDeDatos
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento-precios"
URL = "/api/v1/precios"
URL_LISTAS = f"{URL}/listas"
TODOS = ("GESTIONAR_LISTAS", "PUBLICAR_LISTAS", "ADMIN_CONFIGURACION", "VER_COSTOS")


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
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno(EntornoDeDatos):
    """Los datos de `precios_utiles.Entorno` más usuarios que pueden entrar por `login`."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion)
        self.slug = sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()

    def usuario_con(self, cliente_http: TestClient, *permisos: str) -> dict[str, str]:
        """Alta un usuario de ESTA organización con exactamente esos permisos y entra con él."""
        nombre_usuario = f"usuario-{uuid4().hex[:8]}"
        rol = identidad_repository.crear_rol(
            self.org,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=f"Rol de {nombre_usuario}",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, self.sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        identidad_repository.crear_usuario(
            self.org,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _con_op(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Operation-Id": str(uuid4())}


class Escenario:
    """La organización A con su lista, su regla, su borrador y un precio, y un usuario de B con
    todos los permisos de `precios`."""

    def __init__(self, cliente: TestClient, sesion: Session) -> None:
        self.a = Entorno(sesion)
        self.lista_a, self.version_a = self.a.borrador_de_general("General")
        self.regla_a = self.a.reglas(self.lista_a)[0].id
        self.producto_a = self.a.vino_id
        self.categoria_a = self.a.categoria_id
        self.a.sesion.commit()
        self.de_a = self.a.usuario_con(cliente, *TODOS)

        self.b = Entorno(sesion)
        self.lista_b = self.b.crear_lista("Propia de B")
        self.producto_b = self.b.vino_id
        self.categoria_b = self.b.categoria_id
        self.b.sesion.commit()
        self.de_b = self.b.usuario_con(cliente, *TODOS)

    def estado_de_a(self) -> list[Any]:
        """Todo lo de A que una ruta de B podría tocar, tal como está en la base."""
        consultas = (
            "SELECT * FROM lista_precio WHERE organizacion_id = :o ORDER BY id",
            "SELECT * FROM regla_margen WHERE organizacion_id = :o ORDER BY id",
            "SELECT * FROM redondeo_categoria WHERE organizacion_id = :o ORDER BY id",
            "SELECT * FROM lista_version WHERE organizacion_id = :o ORDER BY id",
            "SELECT * FROM precio_item WHERE organizacion_id = :o ORDER BY id",
            "SELECT lista_precio_default_id FROM configuracion_organizacion "
            "WHERE organizacion_id = :o",
        )
        self.a.sesion.rollback()
        return [
            [tuple(fila) for fila in self.a.sesion.execute(text(sql), {"o": self.a.org})]
            for sql in consultas
        ]


@pytest.fixture
def escenario(cliente: TestClient, sesion: Session) -> Escenario:
    return Escenario(cliente, sesion)


def _rutas_con_recurso_ajeno(e: Escenario) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Cada ruta de `precios` con un id de A en la URL (o en el contenido): `(método, url,
    cuerpo)`."""
    lista, version, regla = e.lista_a, e.version_a, e.regla_a
    return [
        ("get", f"{URL_LISTAS}/{lista}", None),
        (
            "put",
            f"{URL_LISTAS}/{lista}",
            {
                "nombre": "Hackeada",
                "redondeo_multiplo": "1.00",
                "redondeo_direccion": "ABAJO",
                "activo": False,
            },
        ),
        ("get", f"{URL_LISTAS}/{lista}/reglas", None),
        (
            "post",
            f"{URL_LISTAS}/{lista}/reglas",
            {
                "tipo": "MARKUP",
                "valor": "0.500000",
                "alcance_tipo": "CATEGORIA",
                "alcance_id": str(e.categoria_a),
            },
        ),
        (
            "put",
            f"{URL_LISTAS}/{lista}/reglas/{regla}",
            {"tipo": "MARKUP", "valor": "0.900000", "activo": False},
        ),
        (
            "put",
            f"{URL_LISTAS}/{lista}/redondeos-categoria/{e.categoria_a}",
            {"multiplo": "10.00", "direccion": "ARRIBA", "activo": True},
        ),
        ("post", f"{URL_LISTAS}/{lista}/borrador", None),
        ("get", f"{URL_LISTAS}/{lista}/borrador", None),
        (
            "put",
            f"{URL_LISTAS}/{lista}/versiones/{version}/precios/{e.producto_a}",
            {"precio_final": "1.00"},
        ),
        ("post", f"{URL_LISTAS}/{lista}/versiones/{version}/publicar", {}),
        ("post", f"{URL_LISTAS}/{lista}/versiones/{version}/anular", None),
        ("get", f"{URL_LISTAS}/{lista}/versiones", None),
        ("get", f"{URL_LISTAS}/{lista}/versiones/{version}/precios", None),
        ("get", f"{URL_LISTAS}/{lista}/vigente", None),
        ("put", f"{URL}/lista-predeterminada", {"lista_id": str(lista)}),
    ]


def _llamar(
    cliente: TestClient,
    metodo: str,
    url: str,
    cuerpo: dict[str, Any] | None,
    headers: dict[str, str],
) -> Any:
    if metodo == "get":
        return cliente.get(url, headers=headers)
    enviar = {"put": cliente.put, "post": cliente.post}[metodo]
    return enviar(url, json=cuerpo, headers=_con_op(headers))


def test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos(
    cliente: TestClient, escenario: Escenario
) -> None:
    """Las quince rutas con un recurso de A (la lista, la regla, la versión o el producto en la
    URL, o la lista elegida como predeterminada) responden 404 a un usuario de B con todos los
    permisos, y nada de A cambia."""
    antes = escenario.estado_de_a()
    predeterminada_de_b = escenario.b.predeterminada()

    for metodo, url, cuerpo in _rutas_con_recurso_ajeno(escenario):
        respuesta = _llamar(cliente, metodo, url, cuerpo, escenario.de_b)
        assert respuesta.status_code == 404, (metodo, url, respuesta.text)
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO", (metodo, url)

    assert escenario.estado_de_a() == antes
    escenario.b.sesion.rollback()
    assert escenario.b.predeterminada() == predeterminada_de_b


def test_inv21_las_mismas_rutas_funcionan_para_la_organizacion_duena(
    cliente: TestClient, escenario: Escenario
) -> None:
    """Contraste: la lectura de A sobre sus propios recursos responde 200 (los 404 de arriba
    no son por una URL mal armada)."""
    lecturas = [
        f"{URL_LISTAS}/{escenario.lista_a}",
        f"{URL_LISTAS}/{escenario.lista_a}/reglas",
        f"{URL_LISTAS}/{escenario.lista_a}/borrador",
        f"{URL_LISTAS}/{escenario.lista_a}/versiones",
        f"{URL_LISTAS}/{escenario.lista_a}/versiones/{escenario.version_a}/precios",
    ]

    codigos = [cliente.get(url, headers=escenario.de_a).status_code for url in lecturas]

    assert codigos == [200] * len(lecturas)


def test_inv21_una_version_o_un_producto_de_a_con_la_lista_de_b_responde_404(
    cliente: TestClient, escenario: Escenario
) -> None:
    """La lista es de B pero la versión o el producto del recorrido son de A: 404 también."""
    lista_b = escenario.lista_b
    antes = escenario.estado_de_a()

    respuestas = [
        cliente.get(
            f"{URL_LISTAS}/{lista_b}/versiones/{escenario.version_a}/precios",
            headers=escenario.de_b,
        ),
        cliente.post(
            f"{URL_LISTAS}/{lista_b}/versiones/{escenario.version_a}/publicar",
            json={},
            headers=_con_op(escenario.de_b),
        ),
        cliente.post(
            f"{URL_LISTAS}/{lista_b}/versiones/{escenario.version_a}/anular",
            headers=_con_op(escenario.de_b),
        ),
        cliente.put(
            f"{URL_LISTAS}/{lista_b}/versiones/{escenario.version_a}/precios/{escenario.producto_b}",
            json={"precio_final": "1.00"},
            headers=_con_op(escenario.de_b),
        ),
        cliente.put(
            f"{URL_LISTAS}/{lista_b}/redondeos-categoria/{escenario.categoria_a}",
            json={"multiplo": "10.00", "direccion": "ARRIBA", "activo": True},
            headers=_con_op(escenario.de_b),
        ),
        cliente.post(
            f"{URL_LISTAS}/{lista_b}/reglas",
            json={
                "tipo": "MARKUP",
                "valor": "0.500000",
                "alcance_tipo": "PRODUCTO",
                "alcance_id": str(escenario.producto_a),
            },
            headers=_con_op(escenario.de_b),
        ),
    ]

    assert [r.status_code for r in respuestas] == [404] * len(respuestas)
    assert escenario.estado_de_a() == antes


def test_inv21_el_alta_el_listado_y_las_opciones_solo_ven_lo_propio(
    cliente: TestClient, escenario: Escenario
) -> None:
    antes = escenario.estado_de_a()

    creada = cliente.post(
        URL_LISTAS,
        json={
            "nombre": "Nueva de B",
            "redondeo_multiplo": "100.00",
            "redondeo_direccion": "ARRIBA",
        },
        headers=_con_op(escenario.de_b),
    )
    listado = cliente.get(URL_LISTAS, headers=escenario.de_b).json()["items"]
    opciones = cliente.get(f"{URL_LISTAS}/opciones", headers=escenario.de_b).json()["items"]

    assert creada.status_code == 201
    propias = {str(escenario.lista_b), creada.json()["id"]}
    assert {i["id"] for i in listado} == propias
    assert {i["id"] for i in opciones} == propias
    assert str(escenario.lista_a) not in {i["id"] for i in listado + opciones}
    assert escenario.estado_de_a() == antes


def test_inv21_la_lista_predeterminada_leida_es_la_de_la_propia_organizacion(
    cliente: TestClient, escenario: Escenario
) -> None:
    """A define su lista predeterminada; B, que no definió ninguna, no ve la de A."""
    definida = cliente.put(
        f"{URL}/lista-predeterminada",
        json={"lista_id": str(escenario.lista_a)},
        headers=_con_op(escenario.de_a),
    )

    de_a = cliente.get(f"{URL}/lista-predeterminada", headers=escenario.de_a).json()
    de_b = cliente.get(f"{URL}/lista-predeterminada", headers=escenario.de_b).json()

    assert definida.status_code == 200
    assert de_a["lista_id"] == str(escenario.lista_a)
    assert de_b == {"lista_id": None, "lista_nombre": None, "activa": None}


def test_inv21_la_lista_asignada_a_un_cliente_de_otra_organizacion_responde_404(
    cliente: TestClient, escenario: Escenario
) -> None:
    """`CLIENTE_CREAR` y `CLIENTE_MODIFICAR` con la lista de A enviados por un usuario de B."""
    comercial_b = escenario.b.usuario_con(cliente, "GESTIONAR_CLIENTES")
    propio = cliente.post(
        "/api/v1/clientes",
        json={"nombre": "Kiosco B", "direccion": "Calle 1", "contacto": "Ana"},
        headers=_con_op(comercial_b),
    )
    antes = escenario.estado_de_a()

    al_crear = cliente.post(
        "/api/v1/clientes",
        json={
            "nombre": "Kiosco B2",
            "direccion": "Calle 1",
            "contacto": "Ana",
            "lista_precio_id": str(escenario.lista_a),
        },
        headers=_con_op(comercial_b),
    )
    al_modificar = cliente.put(
        f"/api/v1/clientes/{propio.json()['id']}",
        json={
            "nombre": "Kiosco B",
            "direccion": "Calle 1",
            "contacto": "Ana",
            "estado": "ACTIVO",
            "lista_precio_id": str(escenario.lista_a),
        },
        headers=_con_op(comercial_b),
    )

    assert al_crear.status_code == 404
    assert al_modificar.status_code == 404
    assert (
        cliente.get(f"/api/v1/clientes/{propio.json()['id']}", headers=comercial_b).json()[
            "lista_precio_id"
        ]
        is None
    )
    assert escenario.estado_de_a() == antes
    assert UUID(propio.json()["id"])
