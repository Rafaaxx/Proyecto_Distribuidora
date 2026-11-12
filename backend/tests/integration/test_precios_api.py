"""Change 13, tarea 5.4: la API de `precios` por HTTP (`/api/v1/precios`): escrituras de
listas, reglas de margen y redondeos por categoría, y las lecturas de listas, detalle, reglas
y opciones.

Mismo arnés que `test_pagos_proveedor_api.py`: PostgreSQL real, motor propio de la aplicación
y `login` real (nunca un access token fabricado). Cubre el contrato HTTP: `Operation-Id`
obligatorio, múltiplos y valores como string, Problem Details con `codigo`, permisos de
escritura y de lectura (`design.md` D12) e idempotencia.

Reglas citadas: PRC-01, PRC-12, PRC-13, PRC-14, INV-02, INV-03, INV-06, INV-21, SEG-06,
SEG-07, TR-07, `design.md` D8, D9, D12.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from precios_utiles import Entorno as EntornoDeDatos
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-precios-api"
URL = "/api/v1/precios"
URL_LISTAS = f"{URL}/listas"


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

    def crear_producto(self, *argumentos: Any, **opciones: Any) -> UUID:
        """Con la aplicación en otra sesión, lo sembrado por SQL se confirma para que se vea."""
        producto_id = super().crear_producto(*argumentos, **opciones)
        self.sesion.commit()
        return producto_id

    def informar_costo(self, *argumentos: Any, **opciones: Any) -> UUID:
        costo_id = super().informar_costo(*argumentos, **opciones)
        self.sesion.commit()
        return costo_id

    def entrar(self, cliente_http: TestClient, nombre_usuario: str) -> dict[str, str]:
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
        return self.entrar(cliente_http, nombre_usuario)


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _lista(**cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "nombre": "General",
        "redondeo_multiplo": "100.00",
        "redondeo_direccion": "ARRIBA",
    }
    cuerpo.update(cambios)
    return cuerpo


def _crear_lista(cliente: TestClient, headers: dict[str, str], **cambios: object) -> dict[str, Any]:
    respuesta = cliente.post(URL_LISTAS, json=_lista(**cambios), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


@pytest.fixture
def gestor(entorno: Entorno, cliente: TestClient) -> dict[str, str]:
    return entorno.usuario_con(cliente, "GESTIONAR_LISTAS")


# --- listas: escritura ----------------------------------------------------------------------


def test_crear_una_lista_devuelve_201_con_los_multiplos_como_string(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    respuesta = cliente.post(URL_LISTAS, json=_lista(), headers=_con_op(gestor))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "General"
    assert cuerpo["redondeo_multiplo"] == "100.00"
    assert cuerpo["redondeo_direccion"] == "ARRIBA"
    assert cuerpo["activo"] is True
    assert cuerpo["version_vigente"] is None
    assert cuerpo["tiene_borrador"] is False
    UUID(cuerpo["id"])


def test_la_escritura_exige_operation_id(cliente: TestClient, gestor: dict[str, str]) -> None:
    respuesta = cliente.post(URL_LISTAS, json=_lista(), headers=gestor)

    assert respuesta.status_code == 400
    assert cliente.get(URL_LISTAS, headers=gestor).json() == {"items": []}


@pytest.mark.parametrize("multiplo", [100, 100.5, None])
def test_inv03_un_multiplo_que_no_es_string_se_rechaza_con_422(
    cliente: TestClient, gestor: dict[str, str], multiplo: object
) -> None:
    respuesta = cliente.post(
        URL_LISTAS, json=_lista(redondeo_multiplo=multiplo), headers=_con_op(gestor)
    )

    assert respuesta.status_code == 422


def test_el_cuerpo_no_acepta_la_organizacion(cliente: TestClient, gestor: dict[str, str]) -> None:
    """INV-21: `organizacion_id` sale siempre del token."""
    respuesta = cliente.post(
        URL_LISTAS, json=_lista(organizacion_id=str(uuid4())), headers=_con_op(gestor)
    )

    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    ("cambios", "estado", "codigo"),
    [
        ({"nombre": "  "}, 422, "NOMBRE_INVALIDO"),
        ({"redondeo_multiplo": "0"}, 422, "REDONDEO_INVALIDO"),
        ({"redondeo_multiplo": "0.005"}, 422, "REDONDEO_INVALIDO"),
        ({"redondeo_direccion": "MITAD"}, 422, "REDONDEO_INVALIDO"),
    ],
)
def test_los_errores_de_dominio_salen_como_problem_details_con_codigo(
    cliente: TestClient, gestor: dict[str, str], cambios: dict[str, Any], estado: int, codigo: str
) -> None:
    respuesta = cliente.post(URL_LISTAS, json=_lista(**cambios), headers=_con_op(gestor))

    assert respuesta.status_code == estado
    assert respuesta.json()["codigo"] == codigo


def test_un_nombre_repetido_responde_409(cliente: TestClient, gestor: dict[str, str]) -> None:
    _crear_lista(cliente, gestor)

    respuesta = cliente.post(URL_LISTAS, json=_lista(nombre=" general "), headers=_con_op(gestor))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"


def test_modificar_una_lista(cliente: TestClient, gestor: dict[str, str]) -> None:
    lista = _crear_lista(cliente, gestor)

    respuesta = cliente.put(
        f"{URL_LISTAS}/{lista['id']}",
        json={
            "nombre": "General 2026",
            "redondeo_multiplo": "50.00",
            "redondeo_direccion": "ABAJO",
            "activo": False,
        },
        headers=_con_op(gestor),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["nombre"], cuerpo["redondeo_multiplo"], cuerpo["redondeo_direccion"]) == (
        "General 2026",
        "50.00",
        "ABAJO",
    )
    assert cuerpo["activo"] is False


def test_el_doble_envio_con_el_mismo_operation_id_no_duplica(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    """INV-06: el reintento devuelve el mismo resultado y la lista existe una sola vez."""
    cabeceras = _con_op(gestor)

    primero = cliente.post(URL_LISTAS, json=_lista(), headers=cabeceras)
    segundo = cliente.post(URL_LISTAS, json=_lista(), headers=cabeceras)
    otro_contenido = cliente.post(URL_LISTAS, json=_lista(nombre="Otra"), headers=cabeceras)

    assert primero.status_code == 201
    assert segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    assert otro_contenido.status_code == 409
    assert otro_contenido.json()["codigo"] == "COMANDO_INCONSISTENTE"
    assert len(cliente.get(URL_LISTAS, headers=gestor).json()["items"]) == 1


# --- reglas y redondeos: escritura ---------------------------------------------------------


def test_crear_y_modificar_una_regla(
    cliente: TestClient, gestor: dict[str, str], entorno: Entorno
) -> None:
    lista = _crear_lista(cliente, gestor)
    url = f"{URL_LISTAS}/{lista['id']}/reglas"

    creada = cliente.post(
        url,
        json={
            "tipo": "MARGEN_BRUTO",
            "valor": "0.300000",
            "alcance_tipo": "CATEGORIA",
            "alcance_id": str(entorno.categoria_id),
        },
        headers=_con_op(gestor),
    )

    assert creada.status_code == 201
    regla = creada.json()
    assert regla["lista_id"] == lista["id"]
    assert (regla["tipo"], regla["valor"], regla["activo"]) == ("MARGEN_BRUTO", "0.300000", True)
    assert regla["alcance_tipo"] == "CATEGORIA"
    assert regla["alcance_id"] == str(entorno.categoria_id)
    assert regla["alcance_nombre"]

    modificada = cliente.put(
        f"{url}/{regla['id']}",
        json={"tipo": "MARKUP", "valor": "0.4", "activo": False},
        headers=_con_op(gestor),
    )

    assert modificada.status_code == 200
    assert (modificada.json()["tipo"], modificada.json()["valor"], modificada.json()["activo"]) == (
        "MARKUP",
        "0.400000",
        False,
    )
    assert modificada.json()["alcance_id"] == str(entorno.categoria_id)


@pytest.mark.parametrize(
    ("cuerpo", "estado", "codigo"),
    [
        ({"tipo": "MARGEN_BRUTO", "valor": "1", "alcance_tipo": "LISTA"}, 422, "MARGEN_INVALIDO"),
        ({"tipo": "MARKUP", "valor": "-0.1", "alcance_tipo": "LISTA"}, 422, "MARGEN_INVALIDO"),
        ({"tipo": "MARKUP", "valor": "0.3", "alcance_tipo": "MARCA"}, 422, "ALCANCE_INVALIDO"),
    ],
)
def test_una_regla_invalida_responde_con_su_codigo(
    cliente: TestClient,
    gestor: dict[str, str],
    cuerpo: dict[str, Any],
    estado: int,
    codigo: str,
) -> None:
    lista = _crear_lista(cliente, gestor)

    respuesta = cliente.post(
        f"{URL_LISTAS}/{lista['id']}/reglas", json=cuerpo, headers=_con_op(gestor)
    )

    assert respuesta.status_code == estado
    assert respuesta.json()["codigo"] == codigo


def test_una_regla_duplicada_responde_409(cliente: TestClient, gestor: dict[str, str]) -> None:
    lista = _crear_lista(cliente, gestor)
    url = f"{URL_LISTAS}/{lista['id']}/reglas"
    cuerpo = {"tipo": "MARKUP", "valor": "0.3", "alcance_tipo": "LISTA"}
    assert cliente.post(url, json=cuerpo, headers=_con_op(gestor)).status_code == 201

    respuesta = cliente.post(url, json=cuerpo, headers=_con_op(gestor))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "REGLA_DUPLICADA"


def test_definir_el_redondeo_de_una_categoria(
    cliente: TestClient, gestor: dict[str, str], entorno: Entorno
) -> None:
    lista = _crear_lista(cliente, gestor)
    url = f"{URL_LISTAS}/{lista['id']}/redondeos-categoria/{entorno.categoria_id}"

    primera = cliente.put(
        url, json={"multiplo": "10.00", "direccion": "ARRIBA"}, headers=_con_op(gestor)
    )
    segunda = cliente.put(
        url, json={"multiplo": "50", "direccion": "ABAJO"}, headers=_con_op(gestor)
    )

    assert primera.status_code == 200
    assert primera.json()["multiplo"] == "10.00"
    assert segunda.json()["id"] == primera.json()["id"]
    assert (segunda.json()["multiplo"], segunda.json()["direccion"]) == ("50.00", "ABAJO")
    assert segunda.json()["categoria_nombre"]
    detalle = cliente.get(f"{URL_LISTAS}/{lista['id']}", headers=gestor).json()
    assert [r["multiplo"] for r in detalle["redondeos_categoria"]] == ["50.00"]


# --- permisos de escritura --------------------------------------------------------------------


def test_las_escrituras_sin_gestionar_listas_responden_403(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    solo_publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    lista = _crear_lista(cliente, gestor)
    regla = cliente.post(
        f"{URL_LISTAS}/{lista['id']}/reglas",
        json={"tipo": "MARKUP", "valor": "0.3", "alcance_tipo": "LISTA"},
        headers=_con_op(gestor),
    ).json()

    intentos = [
        cliente.post(URL_LISTAS, json=_lista(nombre="Otra"), headers=_con_op(solo_publica)),
        cliente.put(
            f"{URL_LISTAS}/{lista['id']}",
            json={**_lista(), "activo": False},
            headers=_con_op(solo_publica),
        ),
        cliente.post(
            f"{URL_LISTAS}/{lista['id']}/reglas",
            json={
                "tipo": "MARKUP",
                "valor": "0.3",
                "alcance_tipo": "PRODUCTO",
                "alcance_id": str(entorno.vino_id),
            },
            headers=_con_op(solo_publica),
        ),
        cliente.put(
            f"{URL_LISTAS}/{lista['id']}/reglas/{regla['id']}",
            json={"tipo": "MARKUP", "valor": "0.9", "activo": True},
            headers=_con_op(solo_publica),
        ),
        cliente.put(
            f"{URL_LISTAS}/{lista['id']}/redondeos-categoria/{entorno.categoria_id}",
            json={"multiplo": "10", "direccion": "ARRIBA"},
            headers=_con_op(solo_publica),
        ),
    ]

    assert [i.status_code for i in intentos] == [403] * 5
    assert {i.json()["codigo"] for i in intentos} == {"PERMISO_REQUERIDO"}
    assert len(cliente.get(URL_LISTAS, headers=gestor).json()["items"]) == 1


# --- lecturas -----------------------------------------------------------------------------------


def test_el_listado_trae_la_version_vigente_y_si_hay_borrador(
    cliente: TestClient, gestor: dict[str, str], entorno: Entorno, sesion: Session
) -> None:
    general = _crear_lista(cliente, gestor, nombre="General")
    _crear_lista(cliente, gestor, nombre="Mayorista")
    ahora = datetime.now(UTC)
    _insertar_version(
        sesion, entorno, UUID(general["id"]), 1, "PUBLICADA", ahora - timedelta(days=30)
    )
    _insertar_version(
        sesion, entorno, UUID(general["id"]), 2, "PUBLICADA", ahora - timedelta(days=1)
    )
    _insertar_version(
        sesion, entorno, UUID(general["id"]), 3, "PUBLICADA", ahora + timedelta(days=5)
    )
    _insertar_version(sesion, entorno, UUID(general["id"]), 4, "BORRADOR", None)
    sesion.commit()

    items = cliente.get(URL_LISTAS, headers=gestor).json()["items"]

    por_nombre = {item["nombre"]: item for item in items}
    assert [item["nombre"] for item in items] == ["General", "Mayorista"]
    assert por_nombre["General"]["version_vigente"] == 2  # la 3 es programada
    assert por_nombre["General"]["tiene_borrador"] is True
    assert por_nombre["Mayorista"]["version_vigente"] is None
    assert por_nombre["Mayorista"]["tiene_borrador"] is False


def _insertar_version(
    sesion: Session,
    entorno: Entorno,
    lista_id: UUID,
    numero: int,
    estado: str,
    vigencia_desde: datetime | None,
) -> None:
    sesion.execute(
        text(
            "INSERT INTO lista_version (id, organizacion_id, lista_id, numero, estado, "
            "vigencia_desde, creado_por_id, creado_en, publicado_por_id, publicado_en, "
            "operation_id) VALUES (:id, :org, :lista, :n, :e, :v, :u, :m, :pu, :pe, :op)"
        ),
        {
            "id": uuid4(),
            "org": entorno.org,
            "lista": lista_id,
            "n": numero,
            "e": estado,
            "v": vigencia_desde,
            "u": entorno.usuario_id,
            "m": MOMENTO,
            "pu": None if estado == "BORRADOR" else entorno.usuario_id,
            "pe": None if estado == "BORRADOR" else MOMENTO,
            "op": uuid4(),
        },
    )


def test_el_detalle_trae_las_sobrescrituras_de_redondeo(
    cliente: TestClient, gestor: dict[str, str], entorno: Entorno
) -> None:
    lista = _crear_lista(cliente, gestor)
    cliente.put(
        f"{URL_LISTAS}/{lista['id']}/redondeos-categoria/{entorno.categoria_id}",
        json={"multiplo": "10.00", "direccion": "ARRIBA"},
        headers=_con_op(gestor),
    )

    detalle = cliente.get(f"{URL_LISTAS}/{lista['id']}", headers=gestor)

    assert detalle.status_code == 200
    cuerpo = detalle.json()
    assert cuerpo["id"] == lista["id"]
    assert cuerpo["redondeo_multiplo"] == "100.00"
    (redondeo,) = cuerpo["redondeos_categoria"]
    assert redondeo["categoria_id"] == str(entorno.categoria_id)
    assert redondeo["multiplo"] == "10.00"
    assert redondeo["activo"] is True


def test_las_reglas_traen_el_nombre_de_la_entidad_del_alcance(
    cliente: TestClient, gestor: dict[str, str], entorno: Entorno
) -> None:
    """Escenario "Listado de reglas": una de lista y una de categoría `Vinos`, con los valores
    como string."""
    lista = _crear_lista(cliente, gestor)
    url = f"{URL_LISTAS}/{lista['id']}/reglas"
    cliente.post(
        url,
        json={"tipo": "MARKUP", "valor": "0.3", "alcance_tipo": "LISTA"},
        headers=_con_op(gestor),
    )
    for alcance, entidad in (
        ("CATEGORIA", entorno.categoria_id),
        ("PRODUCTO", entorno.vino_id),
        ("MARCA", entorno.marca_id),
        ("PROVEEDOR", entorno.proveedor_id),
    ):
        cliente.post(
            url,
            json={
                "tipo": "MARGEN_BRUTO",
                "valor": "0.3",
                "alcance_tipo": alcance,
                "alcance_id": str(entidad),
            },
            headers=_con_op(gestor),
        )

    reglas = cliente.get(url, headers=gestor).json()["items"]

    assert [r["alcance_tipo"] for r in reglas] == [
        "LISTA",
        "CATEGORIA",
        "PRODUCTO",
        "MARCA",
        "PROVEEDOR",
    ]
    nombres = {r["alcance_tipo"]: r["alcance_nombre"] for r in reglas}
    assert nombres["LISTA"] is None
    assert nombres["PRODUCTO"] == "Vino A"
    assert nombres["MARCA"] == "Bodega Norte"
    assert nombres["PROVEEDOR"] == "Bodega Sur"
    assert nombres["CATEGORIA"]
    assert [r["valor"] for r in reglas] == ["0.300000"] * 5


def test_las_opciones_traen_solo_las_activas_con_identificador_y_nombre(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    _crear_lista(cliente, gestor, nombre="General")
    especial = _crear_lista(cliente, gestor, nombre="Especial")
    cliente.put(
        f"{URL_LISTAS}/{especial['id']}",
        json={**_lista(nombre="Especial"), "activo": False},
        headers=_con_op(gestor),
    )

    respuesta = cliente.get(f"{URL_LISTAS}/opciones", headers=gestor)

    assert respuesta.status_code == 200
    (opcion,) = respuesta.json()["items"]
    assert opcion["nombre"] == "General"
    assert set(opcion) == {"id", "nombre"}


@pytest.mark.parametrize(
    "permiso", ["GESTIONAR_LISTAS", "PUBLICAR_LISTAS", "GESTIONAR_CLIENTES", "ADMIN_CONFIGURACION"]
)
def test_las_opciones_se_abren_con_cualquiera_de_los_cuatro_permisos(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str], permiso: str
) -> None:
    """Escenario "Opciones para la ficha del cliente" (D12): `GESTIONAR_CLIENTES` sin
    `GESTIONAR_LISTAS` recibe la lectura reducida."""
    _crear_lista(cliente, gestor, nombre="General")
    otro = entorno.usuario_con(cliente, permiso)

    respuesta = cliente.get(f"{URL_LISTAS}/opciones", headers=otro)

    assert respuesta.status_code == 200
    assert [o["nombre"] for o in respuesta.json()["items"]] == ["General"]


@pytest.mark.parametrize("permiso", ["GESTIONAR_CLIENTES", "ADMIN_CONFIGURACION", "VER_COSTOS"])
def test_el_listado_el_detalle_y_las_reglas_no_se_abren_con_los_permisos_de_opciones(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str], permiso: str
) -> None:
    lista = _crear_lista(cliente, gestor)
    otro = entorno.usuario_con(cliente, permiso)

    respuestas = [
        cliente.get(URL_LISTAS, headers=otro),
        cliente.get(f"{URL_LISTAS}/{lista['id']}", headers=otro),
        cliente.get(f"{URL_LISTAS}/{lista['id']}/reglas", headers=otro),
    ]

    assert [r.status_code for r in respuestas] == [403, 403, 403]


def test_las_lecturas_sin_ningun_permiso_de_precios_responden_403(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista = _crear_lista(cliente, gestor)
    sin_permisos = entorno.usuario_con(cliente, "VER_COSTOS")

    respuestas = [
        cliente.get(URL_LISTAS, headers=sin_permisos),
        cliente.get(f"{URL_LISTAS}/opciones", headers=sin_permisos),
        cliente.get(f"{URL_LISTAS}/{lista['id']}", headers=sin_permisos),
        cliente.get(f"{URL_LISTAS}/{lista['id']}/reglas", headers=sin_permisos),
    ]

    assert [r.status_code for r in respuestas] == [403] * 4
    assert {r.json()["codigo"] for r in respuestas} == {"PERMISO_REQUERIDO"}


def test_las_lecturas_se_abren_con_publicar_listas(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista = _crear_lista(cliente, gestor)
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")

    respuestas = [
        cliente.get(URL_LISTAS, headers=publica),
        cliente.get(f"{URL_LISTAS}/{lista['id']}", headers=publica),
        cliente.get(f"{URL_LISTAS}/{lista['id']}/reglas", headers=publica),
    ]

    assert [r.status_code for r in respuestas] == [200, 200, 200]


def test_sin_sesion_responde_401(cliente: TestClient) -> None:
    assert cliente.get(URL_LISTAS).status_code == 401
    assert cliente.post(URL_LISTAS, json=_lista()).status_code == 401


# --- aislamiento (INV-21) -----------------------------------------------------------------------


def test_inv21_cada_organizacion_ve_solo_sus_listas_y_las_ajenas_responden_404(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    de_a = _crear_lista(cliente, gestor, nombre="General")
    otra = Entorno(sesion)
    de_b_headers = otra.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")
    de_b = _crear_lista(cliente, de_b_headers, nombre="General")

    assert [i["id"] for i in cliente.get(URL_LISTAS, headers=de_b_headers).json()["items"]] == [
        de_b["id"]
    ]
    assert [
        i["id"] for i in cliente.get(f"{URL_LISTAS}/opciones", headers=de_b_headers).json()["items"]
    ] == [de_b["id"]]
    for ruta in (
        ("get", f"{URL_LISTAS}/{de_a['id']}", None),
        ("get", f"{URL_LISTAS}/{de_a['id']}/reglas", None),
        ("put", f"{URL_LISTAS}/{de_a['id']}", {**_lista(), "activo": False}),
        (
            "post",
            f"{URL_LISTAS}/{de_a['id']}/reglas",
            {"tipo": "MARKUP", "valor": "0.3", "alcance_tipo": "LISTA"},
        ),
        (
            "put",
            f"{URL_LISTAS}/{de_a['id']}/redondeos-categoria/{otra.categoria_id}",
            {"multiplo": "10", "direccion": "ARRIBA"},
        ),
    ):
        metodo, url, cuerpo = ruta
        if metodo == "get":
            respuesta = cliente.get(url, headers=de_b_headers)
        else:
            enviar = cliente.put if metodo == "put" else cliente.post
            respuesta = enviar(url, json=cuerpo, headers=_con_op(de_b_headers))
        assert respuesta.status_code == 404, (metodo, url)
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert cliente.get(f"{URL_LISTAS}/{de_a['id']}", headers=gestor).json()["activo"] is True


def test_inv21_una_regla_con_una_entidad_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista = _crear_lista(cliente, gestor)
    otra = Entorno(sesion)
    otra.usuario_con(cliente, "GESTIONAR_LISTAS")

    for alcance, entidad in (
        ("PRODUCTO", otra.vino_id),
        ("MARCA", otra.marca_id),
        ("CATEGORIA", otra.categoria_id),
        ("PROVEEDOR", otra.proveedor_id),
    ):
        respuesta = cliente.post(
            f"{URL_LISTAS}/{lista['id']}/reglas",
            json={
                "tipo": "MARKUP",
                "valor": "0.3",
                "alcance_tipo": alcance,
                "alcance_id": str(entidad),
            },
            headers=_con_op(gestor),
        )
        assert respuesta.status_code == 404, alcance

    assert cliente.get(f"{URL_LISTAS}/{lista['id']}/reglas", headers=gestor).json() == {"items": []}


# --- borrador: generar, fijar precio y consultar (tarea 7.6) --------------------------------------


def _general_con_vino(entorno: Entorno) -> UUID:
    """`General` (margen bruto 30%, redondeo 100 hacia arriba) con Vino A (costo base 1000 por
    unidad, referencia `Caja x6`) y la regla de lista."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")
    return lista_id


def _generar(cliente: TestClient, headers: dict[str, str], lista_id: UUID) -> Any:
    return cliente.post(f"{URL_LISTAS}/{lista_id}/borrador", headers=_con_op(headers))


def test_generar_el_borrador_devuelve_el_resultado_con_los_productos_sin_precio(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")

    respuesta = _generar(cliente, gestor, lista_id)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["numero"] == 1
    assert cuerpo["regenerado"] is False
    assert cuerpo["cantidad_precios"] == 1
    assert cuerpo["productos_sin_precio"] == [
        {"producto_id": str(gaseosa_id), "producto_nombre": "Gaseosa C", "causa": "SIN_COSTO"}
    ]
    assert cuerpo["precios_con_otra_regla_iva"] == 0
    assert cuerpo["precios_con_costos_distintos"] == 0
    UUID(cuerpo["version_id"])
    assert cliente.get(f"{URL_LISTAS}/{lista_id}", headers=gestor).json()["tiene_borrador"] is True


def test_generar_exige_operation_id_y_gestionar_listas(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")

    sin_operation = cliente.post(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor)
    sin_permiso = _generar(cliente, publica, lista_id)

    assert sin_operation.status_code == 400
    assert sin_permiso.status_code == 403
    assert sin_permiso.json()["codigo"] == "PERMISO_REQUERIDO"
    assert entorno.versiones(lista_id) == []


def test_generar_sobre_una_lista_inactiva_responde_409_y_sobre_una_ajena_404(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    cliente.put(
        f"{URL_LISTAS}/{lista_id}",
        json={**_lista(), "activo": False},
        headers=_con_op(gestor),
    )
    ajena = Entorno(sesion).crear_lista("General")

    inactiva = _generar(cliente, gestor, lista_id)
    de_otra_organizacion = _generar(cliente, gestor, ajena)

    assert (inactiva.status_code, inactiva.json()["codigo"]) == (409, "LISTA_INACTIVA")
    assert de_otra_organizacion.status_code == 404


def test_el_doble_envio_de_generar_devuelve_el_mismo_resultado(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    cabeceras = _con_op(gestor)

    primero = cliente.post(f"{URL_LISTAS}/{lista_id}/borrador", headers=cabeceras)
    segundo = cliente.post(f"{URL_LISTAS}/{lista_id}/borrador", headers=cabeceras)

    assert primero.json() == segundo.json()
    assert len(entorno.versiones(lista_id)) == 1


def _url_precio(lista_id: UUID, version_id: object, producto_id: UUID) -> str:
    return f"{URL_LISTAS}/{lista_id}/versiones/{version_id}/precios/{producto_id}"


def test_fijar_un_precio_manual_y_quitar_la_marca(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, gestor, lista_id).json()["version_id"]
    url = _url_precio(lista_id, version_id, entorno.vino_id)

    fijado = cliente.put(url, json={"precio_final": "9000.00"}, headers=_con_op(gestor))
    quitado = cliente.put(url, json={"precio_final": None}, headers=_con_op(gestor))

    assert fijado.status_code == 200, fijado.text
    assert fijado.json() == {
        "version_id": version_id,
        "producto_id": str(entorno.vino_id),
        "precio_final": "9000.00",
        "manual": True,
    }
    assert quitado.json()["precio_final"] == "8600.00"
    assert quitado.json()["manual"] is False


@pytest.mark.parametrize(
    ("cuerpo", "estado", "codigo"),
    [
        ({"precio_final": "0.00"}, 422, "IMPORTE_INVALIDO"),
        ({"precio_final": "8600.005"}, 422, "IMPORTE_INVALIDO"),
        ({"precio_final": 9000.5}, 422, None),
        ({"precio_final": 9000}, 422, None),
        ({}, 422, None),
        ({"precio_final": "9000.00", "organizacion_id": str(uuid4())}, 422, None),
    ],
)
def test_fijar_con_un_cuerpo_invalido_se_rechaza(
    cliente: TestClient,
    entorno: Entorno,
    gestor: dict[str, str],
    cuerpo: dict[str, Any],
    estado: int,
    codigo: str | None,
) -> None:
    """INV-03: el importe viaja como string; `null` quita la marca y omitirlo no."""
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, gestor, lista_id).json()["version_id"]

    respuesta = cliente.put(
        _url_precio(lista_id, version_id, entorno.vino_id), json=cuerpo, headers=_con_op(gestor)
    )

    assert respuesta.status_code == estado
    if codigo is not None:
        assert respuesta.json()["codigo"] == codigo
    (precio,) = entorno.precios(UUID(version_id)).values()
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)


def test_fijar_sobre_una_version_publicada_o_ajena_o_sin_permiso(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, gestor, lista_id).json()["version_id"]
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    otra = Entorno(sesion)
    otra.usuario_con(cliente, "GESTIONAR_LISTAS")
    url = _url_precio(lista_id, version_id, entorno.vino_id)
    entorno.publicar_por_sql(UUID(version_id))
    sesion.commit()

    publicada = cliente.put(url, json={"precio_final": "9000.00"}, headers=_con_op(gestor))
    sin_permiso = cliente.put(url, json={"precio_final": "9000.00"}, headers=_con_op(publica))
    producto_ajeno = cliente.put(
        _url_precio(lista_id, version_id, otra.vino_id),
        json={"precio_final": "9000.00"},
        headers=_con_op(gestor),
    )

    assert (publicada.status_code, publicada.json()["codigo"]) == (409, "VERSION_NO_ES_BORRADOR")
    assert sin_permiso.status_code == 403
    assert producto_ajeno.status_code in (404, 409)


def test_consultar_el_borrador_con_costos_trae_precio_base_relacion_y_costos(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Consulta con permiso de ver costos": Vino A `9500.00`, en la base `8600.00`,
    relación "cambia", costo de referencia `6600.000000` y valor de margen `0.300000`."""
    lista_id = _general_con_vino(entorno)
    entorno.generar_borrador(lista_id)
    base = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(base.id)
    entorno.informar_costo(
        entorno.vino_id, "1100", creado_en=datetime(2026, 10, 6, 12, 1, tzinfo=UTC)
    )
    entorno.generar_borrador(lista_id)
    con_costos = entorno.usuario_con(cliente, "GESTIONAR_LISTAS", "VER_COSTOS")

    respuesta = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=con_costos)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["version"]["numero"], cuerpo["version"]["estado"]) == (2, "BORRADOR")
    assert cuerpo["version"]["version_base_id"] == str(base.id)
    assert cuerpo["version"]["vigencia_desde"] is None
    assert cuerpo["siguiente_cursor"] is None
    assert cuerpo["productos_sin_precio"] == []
    (vino,) = cuerpo["precios"]
    assert vino["producto_id"] == str(entorno.vino_id)
    assert vino["producto_nombre"] == "Vino A"
    assert vino["unidades_referencia"] == 6
    assert vino["precio_final"] == "9500.00"
    assert vino["manual"] is False
    assert vino["precio_version_base"] == "8600.00"
    assert vino["relacion"] == "CAMBIA"
    assert vino["costo_referencia"] == "6600.000000"
    assert vino["tipo_margen"] == "MARGEN_BRUTO"
    assert vino["valor_margen"] == "0.300000"
    assert vino["precio_calculado"] == "9428.571429"
    assert vino["senales"] == {
        "sin_costo": False,
        "margen_menor": False,
        "costo_otra_regla_iva": False,
        "costos_distintos_por_presentacion": False,
        "presentacion_del_costo_id": str(entorno.vino_presentacion_id),
        "presentacion_del_costo_nombre": "Caja x6",
    }


def test_las_lineas_del_borrador_traen_las_presentaciones_de_venta_sin_ver_costos(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Ajuste B (PRC-22): cada línea trae nombre y unidades de las presentaciones activas de
    venta, de menos unidades a más, para mostrar el precio por presentación sin pedir cada
    producto al catálogo. No lleva costos: se ve con solo `GESTIONAR_LISTAS`."""
    lista_id = _general_con_vino(entorno)
    entorno.crear_presentacion(entorno.vino_id, "Botella", 1)
    crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Pallet",
        unidades_base=72,
        usar_en_venta=False,
    )
    crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Caja x12",
        unidades_base=12,
        activo=False,
    )
    entorno.generar_borrador(lista_id)
    entorno.sesion.commit()

    respuesta = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor)

    assert respuesta.status_code == 200, respuesta.text
    (vino,) = respuesta.json()["precios"]
    assert vino["presentaciones"] == [
        {"nombre": "Botella", "unidades_base": 1},
        {"nombre": "Caja x6", "unidades_base": 6},
    ]
    assert vino["costo_referencia"] is None


def test_los_precios_de_una_version_publicada_traen_las_presentaciones_de_venta(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _historial(entorno)
    primera = entorno.versiones(lista_id)[0].id
    entorno.crear_presentacion(entorno.vino_id, "Botella", 1)
    entorno.sesion.commit()

    respuesta = cliente.get(_url_version(lista_id, primera, "precios"), headers=gestor)

    (vino,) = respuesta.json()["precios"]
    assert [p["unidades_base"] for p in vino["presentaciones"]] == [1, 6]


def test_consultar_el_borrador_sin_ver_costos_deja_los_costos_en_nulo_y_las_senales(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Consulta sin permiso de ver costos" (D12): precio final y señales sí;
    costo de referencia, margen y precio calculado en nulo."""
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, gestor, lista_id).json()["version_id"]
    cliente.put(
        _url_precio(lista_id, version_id, entorno.vino_id),
        json={"precio_final": "8000.00"},
        headers=_con_op(gestor),
    )

    respuesta = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor)

    assert respuesta.status_code == 200
    (vino,) = respuesta.json()["precios"]
    assert vino["precio_final"] == "8000.00"
    assert vino["manual"] is True
    assert vino["senales"]["margen_menor"] is True
    assert vino["relacion"] == "NUEVO"
    assert vino["precio_version_base"] is None
    for campo in ("costo_referencia", "tipo_margen", "valor_margen", "precio_calculado"):
        assert vino[campo] is None, campo


def test_el_borrador_lista_los_productos_sin_precio_con_su_causa(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")
    _generar(cliente, gestor, lista_id)

    cuerpo = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor).json()

    assert [p["producto_id"] for p in cuerpo["precios"]] == [str(entorno.vino_id)]
    assert cuerpo["productos_sin_precio"] == [
        {"producto_id": str(gaseosa_id), "producto_nombre": "Gaseosa C", "causa": "SIN_COSTO"}
    ]


def test_un_producto_sin_presentacion_de_referencia_se_lista_sin_precio_con_su_causa(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Decisión del 2026-10-06 (D4): el borrador lo informa en `productos_sin_precio` y nunca
    con un precio calculado, aunque tenga costo y regla."""
    lista_id = _general_con_vino(entorno)
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")
    entorno.informar_costo(sin_referencia_id, "500")
    entorno.sesion.commit()

    generado = _generar(cliente, gestor, lista_id)
    cuerpo = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor).json()

    assert [(p["producto_id"], p["causa"]) for p in generado.json()["productos_sin_precio"]] == [
        (str(sin_referencia_id), "SIN_PRESENTACION_DE_REFERENCIA")
    ]
    assert [p["producto_id"] for p in cuerpo["precios"]] == [str(entorno.vino_id)]
    assert cuerpo["productos_sin_precio"] == [
        {
            "producto_id": str(sin_referencia_id),
            "producto_nombre": "Gaseosa sin referencia",
            "causa": "SIN_PRESENTACION_DE_REFERENCIA",
        }
    ]


def test_un_producto_sin_referencia_sigue_con_su_causa_aunque_se_le_informe_un_costo_despues(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """No aparece como `SIN_CALCULAR`: con costo o sin él, sin referencia no hay precio."""
    lista_id = _general_con_vino(entorno)
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")
    _generar(cliente, gestor, lista_id)
    entorno.informar_costo(sin_referencia_id, "500")
    entorno.sesion.commit()

    cuerpo = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor).json()

    assert [(p["producto_id"], p["causa"]) for p in cuerpo["productos_sin_precio"]] == [
        (str(sin_referencia_id), "SIN_PRESENTACION_DE_REFERENCIA")
    ]


def test_fijar_un_precio_manual_a_un_producto_sin_referencia_se_rechaza_con_404(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Pregunta abierta (design no la resuelve): hoy `LISTA_BORRADOR_PRECIO_FIJAR` responde 404
    porque el producto no tiene presentación de referencia; se conserva ese comportamiento."""
    lista_id = _general_con_vino(entorno)
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")
    generado = _generar(cliente, gestor, lista_id)
    version_id = generado.json()["version_id"]

    respuesta = cliente.put(
        _url_precio(lista_id, version_id, sin_referencia_id),
        json={"precio_final": "900.00"},
        headers=_con_op(gestor),
    )

    assert respuesta.status_code == 404, respuesta.text
    borrador = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor).json()
    assert [p["producto_id"] for p in borrador["precios"]] == [str(entorno.vino_id)]


def test_un_producto_que_hoy_podria_calcularse_pero_no_esta_en_el_borrador_se_avisa(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """El borrador es una foto: un producto sin precio al generar al que después se le
    informa un costo aparece como `SIN_CALCULAR` hasta regenerar."""
    lista_id = _general_con_vino(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")
    _generar(cliente, gestor, lista_id)
    entorno.informar_costo(gaseosa_id, "500")
    entorno.sesion.commit()

    cuerpo = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor).json()

    assert [(p["producto_id"], p["causa"]) for p in cuerpo["productos_sin_precio"]] == [
        (str(gaseosa_id), "SIN_CALCULAR")
    ]


def test_los_precios_del_borrador_se_paginan_por_cursor(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _general_con_vino(entorno)
    for numero in range(4):
        producto = entorno.crear_producto(f"Producto {numero}")
        entorno.informar_costo(producto, "100")
    _generar(cliente, gestor, lista_id)
    url = f"{URL_LISTAS}/{lista_id}/borrador"

    primera = cliente.get(url, params={"limite": 2}, headers=gestor).json()
    segunda = cliente.get(
        url, params={"limite": 2, "cursor": primera["siguiente_cursor"]}, headers=gestor
    ).json()
    tercera = cliente.get(
        url, params={"limite": 2, "cursor": segunda["siguiente_cursor"]}, headers=gestor
    ).json()

    ids = [p["producto_id"] for p in primera["precios"] + segunda["precios"] + tercera["precios"]]
    assert [len(primera["precios"]), len(segunda["precios"]), len(tercera["precios"])] == [2, 2, 1]
    assert len(set(ids)) == 5
    assert tercera["siguiente_cursor"] is None
    assert cliente.get(url, params={"limite": 0}, headers=gestor).status_code == 422


def test_consultar_el_borrador_exige_gestionar_o_publicar_y_no_cruza_organizaciones(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenarios "Sin permiso de listas" y "Borrador de otra organización" (INV-21)."""
    lista_id = _general_con_vino(entorno)
    _generar(cliente, gestor, lista_id)
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    sin_permisos = entorno.usuario_con(cliente, "VER_COSTOS")
    otra = Entorno(sesion)
    de_b = otra.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")
    url = f"{URL_LISTAS}/{lista_id}/borrador"

    assert cliente.get(url, headers=publica).status_code == 200
    assert cliente.get(url, headers=sin_permisos).status_code == 403
    assert cliente.get(url, headers=de_b).status_code == 404


def test_una_lista_sin_borrador_responde_404(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = entorno.crear_lista("General")

    respuesta = cliente.get(f"{URL_LISTAS}/{lista_id}/borrador", headers=gestor)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_inv21_fijar_sobre_la_lista_o_la_version_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """INV-21, SEG-07: la lista y la versión de otra organización responden 404 y no cambian."""
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, gestor, lista_id).json()["version_id"]
    otra = Entorno(sesion)
    de_b = otra.usuario_con(cliente, "GESTIONAR_LISTAS")
    lista_de_b = _general_con_vino(otra)
    version_de_b = _generar(cliente, de_b, lista_de_b).json()["version_id"]

    lista_ajena = cliente.put(
        _url_precio(lista_de_b, version_de_b, entorno.vino_id),
        json={"precio_final": "9000.00"},
        headers=_con_op(gestor),
    )
    version_ajena = cliente.put(
        _url_precio(lista_id, version_de_b, entorno.vino_id),
        json={"precio_final": "9000.00"},
        headers=_con_op(gestor),
    )

    assert lista_ajena.status_code == 404
    assert version_ajena.status_code == 404
    assert otra.precios(UUID(version_de_b))[otra.vino_id].manual is False
    assert entorno.precios(UUID(version_id))[entorno.vino_id].manual is False


# --- publicar, anular y consultar versiones (tarea 8.6) -------------------------------------------


def _ahora() -> datetime:
    return datetime.now(UTC)


def _url_version(lista_id: UUID, version_id: object, accion: str = "") -> str:
    base = f"{URL_LISTAS}/{lista_id}/versiones/{version_id}"
    return f"{base}/{accion}" if accion else base


@pytest.fixture
def publicador(entorno: Entorno, cliente: TestClient) -> dict[str, str]:
    return entorno.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")


def _borrador_publicable(
    cliente: TestClient, entorno: Entorno, headers: dict[str, str]
) -> tuple[UUID, str]:
    lista_id = _general_con_vino(entorno)
    version_id = _generar(cliente, headers, lista_id).json()["version_id"]
    return lista_id, version_id


def test_publicar_con_vigencia_inmediata_devuelve_la_version_vigente(
    cliente: TestClient, entorno: Entorno, publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)

    respuesta = cliente.post(
        _url_version(lista_id, version_id, "publicar"),
        json={"vigencia_desde": None, "vigencia_hasta": None},
        headers=_con_op(publicador),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == version_id
    assert (cuerpo["numero"], cuerpo["estado"], cuerpo["estado_derivado"]) == (
        1,
        "PUBLICADA",
        "VIGENTE",
    )
    assert cuerpo["vigencia_hasta"] is None
    assert cuerpo["publicado_por_nombre"] == "Persona de prueba"
    assert cuerpo["publicado_en"] is not None
    detalle = cliente.get(f"{URL_LISTAS}/{lista_id}", headers=publicador).json()
    assert detalle["version_vigente"] == 1


def test_publicar_programada_deriva_programada_y_el_cuerpo_puede_omitir_las_vigencias(
    cliente: TestClient, entorno: Entorno, publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)
    desde, hasta = _ahora() + timedelta(days=3), _ahora() + timedelta(days=33)

    respuesta = cliente.post(
        _url_version(lista_id, version_id, "publicar"),
        json={"vigencia_desde": desde.isoformat(), "vigencia_hasta": hasta.isoformat()},
        headers=_con_op(publicador),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_derivado"] == "PROGRAMADA"
    assert respuesta.json()["vigencia_hasta"] is not None


@pytest.mark.parametrize(
    ("cuerpo", "estado", "codigo"),
    [
        ({"vigencia_desde": "2020-01-01T00:00:00+00:00"}, 422, "VIGENCIA_INVALIDA"),
        (
            {
                "vigencia_desde": "2099-01-01T00:00:00+00:00",
                "vigencia_hasta": "2098-01-01T00:00:00+00:00",
            },
            422,
            "VIGENCIA_INVALIDA",
        ),
        ({"vigencia_desde": "2099-01-01T00:00:00"}, 422, None),  # sin zona horaria
        ({"vigencia_desde": 5}, 422, None),
        ({"organizacion_id": "x"}, 422, None),
    ],
)
def test_publicar_con_un_cuerpo_invalido_se_rechaza(
    cliente: TestClient,
    entorno: Entorno,
    publicador: dict[str, str],
    cuerpo: dict[str, Any],
    estado: int,
    codigo: str | None,
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)

    respuesta = cliente.post(
        _url_version(lista_id, version_id, "publicar"), json=cuerpo, headers=_con_op(publicador)
    )

    assert respuesta.status_code == estado
    if codigo is not None:
        assert respuesta.json()["codigo"] == codigo
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_publicar_exige_operation_id_publicar_listas_y_no_cruza_organizaciones(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, gestor)
    publicador = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    otra = Entorno(sesion)
    de_b = otra.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")
    url = _url_version(lista_id, version_id, "publicar")

    sin_operation = cliente.post(url, json={}, headers=publicador)
    solo_gestionar = cliente.post(url, json={}, headers=_con_op(gestor))
    de_otra_organizacion = cliente.post(url, json={}, headers=_con_op(de_b))

    assert sin_operation.status_code == 400
    assert (solo_gestionar.status_code, solo_gestionar.json()["codigo"]) == (
        403,
        "PERMISO_REQUERIDO",
    )
    assert de_otra_organizacion.status_code == 404
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_publicar_dos_veces_o_sin_precios_responde_con_su_codigo(
    cliente: TestClient, entorno: Entorno, publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)
    sin_precios = entorno.crear_lista("Vacía")
    version_vacia = _generar(cliente, publicador, sin_precios).json()["version_id"]
    url = _url_version(lista_id, version_id, "publicar")

    primera = cliente.post(url, json={}, headers=_con_op(publicador))
    segunda = cliente.post(url, json={}, headers=_con_op(publicador))
    vacia = cliente.post(
        _url_version(sin_precios, version_vacia, "publicar"), json={}, headers=_con_op(publicador)
    )

    assert primera.status_code == 200
    assert (segunda.status_code, segunda.json()["codigo"]) == (409, "VERSION_NO_ES_BORRADOR")
    assert (vacia.status_code, vacia.json()["codigo"]) == (422, "VERSION_SIN_PRECIOS")


def test_anular_una_version_programada(
    cliente: TestClient, entorno: Entorno, publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)
    cliente.post(
        _url_version(lista_id, version_id, "publicar"),
        json={"vigencia_desde": (_ahora() + timedelta(days=3)).isoformat()},
        headers=_con_op(publicador),
    )

    respuesta = cliente.post(
        _url_version(lista_id, version_id, "anular"), headers=_con_op(publicador)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["estado"], cuerpo["estado_derivado"]) == ("ANULADA", None)
    assert cuerpo["anulado_por_nombre"] == "Persona de prueba"
    assert cuerpo["anulado_en"] is not None


def test_anular_una_vigente_un_borrador_o_sin_permiso_se_rechaza(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str], publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)
    url = _url_version(lista_id, version_id, "anular")

    de_un_borrador = cliente.post(url, headers=_con_op(publicador))
    cliente.post(
        _url_version(lista_id, version_id, "publicar"), json={}, headers=_con_op(publicador)
    )
    de_una_vigente = cliente.post(url, headers=_con_op(publicador))
    sin_permiso = cliente.post(url, headers=_con_op(gestor))

    assert (de_un_borrador.status_code, de_un_borrador.json()["codigo"]) == (
        409,
        "VERSION_NO_PUBLICADA",
    )
    assert (de_una_vigente.status_code, de_una_vigente.json()["codigo"]) == (
        409,
        "VERSION_YA_VIGENTE",
    )
    assert sin_permiso.status_code == 403


def test_inv21_anular_la_version_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session, entorno: Entorno, publicador: dict[str, str]
) -> None:
    lista_id, version_id = _borrador_publicable(cliente, entorno, publicador)
    otra = Entorno(sesion)
    de_b = otra.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")

    respuesta = cliente.post(_url_version(lista_id, version_id, "anular"), headers=_con_op(de_b))

    assert respuesta.status_code == 404


def _historial(entorno: Entorno) -> UUID:
    """`General` con cuatro versiones: la n.º 1 histórica (Vino A a `7800.00`), la n.º 2
    vigente (`8600.00`), la n.º 3 anulada y la n.º 4 borrador."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
    ahora = _ahora()
    entorno.informar_costo(entorno.vino_id, "900", vigencia=MOMENTO.date() - timedelta(days=30))
    entorno.generar_borrador(lista_id)
    entorno.publicar_por_sql(entorno.versiones(lista_id)[0].id, desde=ahora - timedelta(days=30))
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.generar_borrador(lista_id)
    entorno.publicar_por_sql(entorno.versiones(lista_id)[1].id, desde=ahora - timedelta(days=10))
    entorno.generar_borrador(lista_id)
    tercera = entorno.versiones(lista_id)[2].id
    entorno.publicar_por_sql(tercera, desde=ahora + timedelta(days=10))
    entorno.sesion.execute(
        text(
            "UPDATE lista_version SET estado = 'ANULADA', anulado_en = :a, anulado_por_id = :u "
            "WHERE id = :v"
        ),
        {"a": ahora, "u": entorno.usuario_id, "v": tercera},
    )
    entorno.generar_borrador(lista_id)
    entorno.sesion.commit()
    return lista_id


def test_el_historial_de_versiones_va_de_la_mas_nueva_a_la_mas_antigua_con_sus_estados(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Historial de versiones": 4, 3, 2, 1 con su estado almacenado y derivado."""
    lista_id = _historial(entorno)

    respuesta = cliente.get(f"{URL_LISTAS}/{lista_id}/versiones", headers=gestor)

    assert respuesta.status_code == 200, respuesta.text
    items = respuesta.json()["items"]
    assert [(v["numero"], v["estado"], v["estado_derivado"]) for v in items] == [
        (4, "BORRADOR", None),
        (3, "ANULADA", None),
        (2, "PUBLICADA", "VIGENTE"),
        (1, "PUBLICADA", "HISTORICA"),
    ]
    assert items[1]["anulado_por_nombre"] == "Persona de prueba"
    assert items[2]["publicado_por_nombre"] == "Persona de prueba"
    assert items[3]["vigencia_hasta"] is None
    assert items[0]["vigencia_desde"] is None


def test_los_precios_de_una_version_historica_se_ven_tal_como_se_publicaron(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Precios de una versión anterior": Vino A a `7800.00` con sus unidades de
    referencia; sin `VER_COSTOS` el costo va en nulo y con él, con su valor."""
    lista_id = _historial(entorno)
    primera = entorno.versiones(lista_id)[0].id
    con_costos = entorno.usuario_con(cliente, "PUBLICAR_LISTAS", "VER_COSTOS")

    sin_costos = cliente.get(_url_version(lista_id, primera, "precios"), headers=gestor)
    con = cliente.get(_url_version(lista_id, primera, "precios"), headers=con_costos)

    assert sin_costos.status_code == 200, sin_costos.text
    cuerpo = sin_costos.json()
    assert cuerpo["version"]["estado_derivado"] == "HISTORICA"
    (vino,) = cuerpo["precios"]
    assert (vino["producto_nombre"], vino["precio_final"], vino["unidades_referencia"]) == (
        "Vino A",
        "7800.00",
        6,
    )
    assert vino["senales"] is None, "las señales son del borrador"
    assert vino["costo_referencia"] is None
    assert con.json()["precios"][0]["costo_referencia"] == "5400.000000"
    assert con.json()["precios"][0]["tipo_margen"] == "MARGEN_BRUTO"


def test_los_precios_de_una_version_anulada_se_ven_y_se_paginan(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _historial(entorno)
    anulada = entorno.versiones(lista_id)[2].id
    url = _url_version(lista_id, anulada, "precios")

    completa = cliente.get(url, headers=gestor).json()
    pagina = cliente.get(url, params={"limite": 1}, headers=gestor).json()

    assert completa["version"]["estado"] == "ANULADA"
    assert [p["precio_final"] for p in completa["precios"]] == ["8600.00"]
    assert len(pagina["precios"]) == 1
    assert pagina["siguiente_cursor"] is None
    assert cliente.get(url, params={"cursor": "###"}, headers=gestor).status_code == 422


def test_las_lecturas_de_versiones_exigen_un_permiso_de_listas_y_no_cruzan_organizaciones(
    cliente: TestClient, sesion: Session, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenarios "Versiones de una lista ajena" y "Sin permiso" (INV-21, SEG-06)."""
    lista_id = _historial(entorno)
    primera = entorno.versiones(lista_id)[0].id
    sin_permisos = entorno.usuario_con(cliente, "VER_COSTOS")
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    otra = Entorno(sesion)
    de_b = otra.usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")
    urls = (
        f"{URL_LISTAS}/{lista_id}/versiones",
        _url_version(lista_id, primera, "precios"),
    )

    assert [cliente.get(url, headers=sin_permisos).status_code for url in urls] == [403, 403]
    assert [cliente.get(url, headers=publica).status_code for url in urls] == [200, 200]
    assert [cliente.get(url, headers=de_b).status_code for url in urls] == [404, 404]
    inexistente = cliente.get(_url_version(lista_id, uuid4(), "precios"), headers=gestor)
    assert inexistente.status_code == 404


# --- resolución de precio: versión vigente por API (tarea 9.2) -----------------------------------


def _url_vigente(lista_id: UUID) -> str:
    return f"{URL_LISTAS}/{lista_id}/vigente"


def test_la_version_vigente_de_la_lista_trae_precios_como_string_y_unidades_como_entero(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Precio vigente de un producto" (PRC-20, PRC-10)."""
    lista_id = _historial(entorno)

    respuesta = cliente.get(_url_vigente(lista_id), headers=gestor)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["numero"] == 2
    assert cuerpo["vigencia_hasta"] is None
    assert cuerpo["precios"] == [
        {"producto_id": str(entorno.vino_id), "precio_final": "8600.00", "unidades_referencia": 6}
    ]
    assert cuerpo["productos_sin_precio"] == []


def test_la_version_vigente_se_pide_a_un_momento_y_devuelve_la_de_entonces(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Se usa la versión vigente al momento pedido": hace 20 días regía la n.º 1."""
    lista_id = _historial(entorno)
    momento = (_ahora() - timedelta(days=20)).isoformat()

    respuesta = cliente.get(_url_vigente(lista_id), params={"momento": momento}, headers=gestor)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["numero"] == 1
    assert respuesta.json()["precios"][0]["precio_final"] == "7800.00"


def test_pedir_productos_distingue_los_que_tienen_precio_de_los_que_no(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Producto sin precio en la versión vigente"."""
    lista_id = _historial(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")

    respuesta = cliente.get(
        _url_vigente(lista_id),
        params={"producto_id": [str(entorno.vino_id), str(gaseosa_id)]},
        headers=gestor,
    )

    cuerpo = respuesta.json()
    assert [p["producto_id"] for p in cuerpo["precios"]] == [str(entorno.vino_id)]
    assert cuerpo["productos_sin_precio"] == [str(gaseosa_id)]


def test_una_lista_sin_version_vigente_responde_409_con_su_codigo(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Lista sin versión vigente": solo un borrador."""
    lista_id = _general_con_vino(entorno)
    _generar(cliente, gestor, lista_id)

    respuesta = cliente.get(_url_vigente(lista_id), headers=gestor)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "LISTA_SIN_VERSION_VIGENTE"


def test_un_momento_sin_zona_horaria_se_rechaza_con_422(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    lista_id = _historial(entorno)

    respuesta = cliente.get(
        _url_vigente(lista_id), params={"momento": "2026-10-02T12:00:00"}, headers=gestor
    )

    assert respuesta.status_code == 422


def test_la_version_vigente_se_lee_con_gestionar_o_con_publicar_y_sin_ninguno_es_403(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "Lectura sin permiso" (D12, SEG-06)."""
    lista_id = _historial(entorno)
    gestiona = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")
    publica = entorno.usuario_con(cliente, "PUBLICAR_LISTAS")
    sin_permiso = entorno.usuario_con(cliente, "GESTIONAR_CLIENTES")

    respuestas = [
        cliente.get(_url_vigente(lista_id), headers=cabeceras).status_code
        for cabeceras in (gestiona, publica, sin_permiso)
    ]
    detalle = cliente.get(_url_vigente(lista_id), headers=sin_permiso).json()

    assert respuestas == [200, 200, 403]
    assert detalle["codigo"] == "PERMISO_REQUERIDO"


def test_inv21_la_version_vigente_de_una_lista_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session, entorno: Entorno
) -> None:
    """Escenario "Versión vigente de una lista ajena"."""
    lista_id = _historial(entorno)
    de_b = Entorno(sesion).usuario_con(cliente, "GESTIONAR_LISTAS", "PUBLICAR_LISTAS")

    respuesta = cliente.get(_url_vigente(lista_id), headers=de_b)

    assert respuesta.status_code == 404


# --- lista asignada al cliente por HTTP (tarea 10.1) ---------------------------------------------

URL_CLIENTES = "/api/v1/clientes"


def _cuerpo_de_cliente(**cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "nombre": "Kiosco El Faro",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
    }
    cuerpo.update(cambios)
    return cuerpo


def test_asignar_una_lista_al_cliente_por_http_y_la_consulta_la_devuelve(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "Asignar una lista al cliente": con `GESTIONAR_CLIENTES` y sin
    `GESTIONAR_LISTAS`."""
    mayorista = entorno.crear_lista("Mayorista")
    entorno.sesion.commit()
    comercial = entorno.usuario_con(cliente, "GESTIONAR_CLIENTES")

    creado = cliente.post(URL_CLIENTES, json=_cuerpo_de_cliente(), headers=_con_op(comercial))
    asignado = cliente.put(
        f"{URL_CLIENTES}/{creado.json()['id']}",
        json=_cuerpo_de_cliente(estado="ACTIVO", lista_precio_id=str(mayorista)),
        headers=_con_op(comercial),
    )
    consultado = cliente.get(f"{URL_CLIENTES}/{creado.json()['id']}", headers=comercial)
    quitado = cliente.put(
        f"{URL_CLIENTES}/{creado.json()['id']}",
        json=_cuerpo_de_cliente(estado="ACTIVO", lista_precio_id=None),
        headers=_con_op(comercial),
    )

    assert creado.status_code == 201, creado.text
    assert creado.json()["lista_precio_id"] is None
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["lista_precio_id"] == str(mayorista)
    assert consultado.json()["lista_precio_id"] == str(mayorista)
    assert quitado.json()["lista_precio_id"] is None


def test_crear_un_cliente_con_lista_inactiva_o_ajena_se_rechaza_por_http(
    cliente: TestClient, sesion: Session, entorno: Entorno
) -> None:
    """Escenarios "Lista inactiva" y "Lista de otra organización" (INV-21, SEG-07)."""
    especial = entorno.crear_lista("Especial")
    entorno.desactivar_lista(especial, "Especial")
    ajena = Entorno(sesion).crear_lista("Mayorista")
    entorno.sesion.commit()
    comercial = entorno.usuario_con(cliente, "GESTIONAR_CLIENTES")

    inactiva = cliente.post(
        URL_CLIENTES,
        json=_cuerpo_de_cliente(lista_precio_id=str(especial)),
        headers=_con_op(comercial),
    )
    de_otra = cliente.post(
        URL_CLIENTES,
        json=_cuerpo_de_cliente(lista_precio_id=str(ajena)),
        headers=_con_op(comercial),
    )

    assert (inactiva.status_code, inactiva.json()["codigo"]) == (409, "LISTA_INACTIVA")
    assert de_otra.status_code == 404
    assert entorno.cantidad("cliente") == 0


# --- lista predeterminada de la organización (tarea 10.3) ----------------------------------------

URL_PREDETERMINADA = f"{URL}/lista-predeterminada"


def test_definir_y_leer_la_lista_predeterminada(cliente: TestClient, entorno: Entorno) -> None:
    """Escenario "Definir la lista General como predeterminada"."""
    general = entorno.crear_lista("General")
    entorno.sesion.commit()
    admin = entorno.usuario_con(cliente, "ADMIN_CONFIGURACION")

    antes = cliente.get(URL_PREDETERMINADA, headers=admin)
    definida = cliente.put(
        URL_PREDETERMINADA, json={"lista_id": str(general)}, headers=_con_op(admin)
    )
    despues = cliente.get(URL_PREDETERMINADA, headers=admin)

    assert antes.status_code == 200, antes.text
    assert antes.json() == {"lista_id": None, "lista_nombre": None, "activa": None}
    assert definida.status_code == 200, definida.text
    assert definida.json() == {"lista_id": str(general), "lista_nombre": "General", "activa": True}
    assert despues.json() == definida.json()
    assert entorno.predeterminada() == general


def test_la_predeterminada_se_lee_con_cualquiera_de_los_tres_permisos(
    cliente: TestClient, entorno: Entorno
) -> None:
    """La lectura de la lista predeterminada: `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o
    `PUBLICAR_LISTAS`; con otro permiso, 403 (D12, SEG-06)."""
    permisos = ("ADMIN_CONFIGURACION", "GESTIONAR_LISTAS", "PUBLICAR_LISTAS", "GESTIONAR_CLIENTES")
    codigos = [
        cliente.get(URL_PREDETERMINADA, headers=entorno.usuario_con(cliente, permiso)).status_code
        for permiso in permisos
    ]

    assert codigos == [200, 200, 200, 403]


def test_definir_la_predeterminada_exige_admin_configuracion_y_operation_id(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenario "Sin permiso de configuración": `GESTIONAR_LISTAS` solo no alcanza."""
    general = entorno.crear_lista("General")
    entorno.sesion.commit()
    admin = entorno.usuario_con(cliente, "ADMIN_CONFIGURACION")

    sin_operation = cliente.put(URL_PREDETERMINADA, json={"lista_id": str(general)}, headers=admin)
    sin_permiso = cliente.put(
        URL_PREDETERMINADA, json={"lista_id": str(general)}, headers=_con_op(gestor)
    )

    assert sin_operation.status_code == 400
    assert (sin_permiso.status_code, sin_permiso.json()["codigo"]) == (403, "PERMISO_REQUERIDO")
    assert entorno.predeterminada() is None


def test_definir_una_lista_inactiva_o_ajena_o_con_organizacion_id_se_rechaza(
    cliente: TestClient, sesion: Session, entorno: Entorno
) -> None:
    """Escenarios "Lista inactiva" y "Lista de otra organización" (INV-21)."""
    especial = entorno.crear_lista("Especial")
    entorno.desactivar_lista(especial, "Especial")
    ajena = Entorno(sesion).crear_lista("General")
    entorno.sesion.commit()
    admin = entorno.usuario_con(cliente, "ADMIN_CONFIGURACION")

    inactiva = cliente.put(
        URL_PREDETERMINADA, json={"lista_id": str(especial)}, headers=_con_op(admin)
    )
    de_otra = cliente.put(URL_PREDETERMINADA, json={"lista_id": str(ajena)}, headers=_con_op(admin))
    con_org = cliente.put(
        URL_PREDETERMINADA,
        json={"lista_id": str(especial), "organizacion_id": str(uuid4())},
        headers=_con_op(admin),
    )

    assert (inactiva.status_code, inactiva.json()["codigo"]) == (409, "LISTA_INACTIVA")
    assert de_otra.status_code == 404
    assert con_org.status_code == 422
    assert entorno.predeterminada() is None


def test_desactivar_la_predeterminada_o_una_asignada_a_un_cliente_responde_409_lista_en_uso(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    """Escenarios "Desactivar la lista predeterminada" y "Desactivar una lista asignada a un
    cliente" por HTTP."""
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")
    entorno.sesion.commit()
    admin = entorno.usuario_con(cliente, "ADMIN_CONFIGURACION", "GESTIONAR_CLIENTES")
    cliente.put(URL_PREDETERMINADA, json={"lista_id": str(general)}, headers=_con_op(admin))
    cliente.post(
        URL_CLIENTES,
        json=_cuerpo_de_cliente(lista_precio_id=str(mayorista)),
        headers=_con_op(admin),
    )

    respuestas = [
        cliente.put(
            f"{URL_LISTAS}/{lista}",
            json=_lista(nombre=nombre, activo=False),
            headers=_con_op(gestor),
        )
        for lista, nombre in ((general, "General"), (mayorista, "Mayorista"))
    ]

    assert [(r.status_code, r.json()["codigo"]) for r in respuestas] == [
        (409, "LISTA_EN_USO"),
        (409, "LISTA_EN_USO"),
    ]
