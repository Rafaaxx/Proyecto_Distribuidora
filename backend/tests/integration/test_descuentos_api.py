"""Change 16, tarea 8.4: las escrituras de `descuentos` por HTTP (`/api/v1/descuentos/reglas`):
alta, edición, activación y pausa.

Mismo arnés que `test_precios_api.py`: PostgreSQL real, motor propio de la aplicación y `login`
real (nunca un access token fabricado). Cubre el contrato HTTP: `Operation-Id` obligatorio,
porcentajes e importes como string, Problem Details con `codigo`, permisos, `organizacion_id`
solo del token e idempotencia.

Reglas citadas: DSC-01 a DSC-04, TR-06, TR-07, INV-02, INV-03, INV-06, INV-21, SEG-06, SEG-07,
`design.md` D15, D16, D18.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from descuentos_utiles import Entorno as EntornoDeDatos
from fastapi.testclient import TestClient
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
JWT_SECRET = "secreto-de-prueba-descuentos-api"
URL = "/api/v1/descuentos/reglas"


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
    """Los datos de `descuentos_utiles.Entorno` más usuarios que pueden entrar por `login`."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion)
        self.sesion.commit()
        self.slug = sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()

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


def _regla(**cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": "20",
        "accion_tipo": "PORCENTAJE",
        "accion_valor": "0.050000",
        "prioridad": 1,
        "acumulable": False,
        "alcances": [],
    }
    cuerpo.update(cambios)
    return cuerpo


def _crear(cliente: TestClient, headers: dict[str, str], **cambios: Any) -> dict[str, Any]:
    respuesta = cliente.post(URL, json=_regla(**cambios), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


@pytest.fixture
def gestor(entorno: Entorno, cliente: TestClient) -> dict[str, str]:
    return entorno.usuario_con(cliente, "GESTIONAR_DESCUENTOS")


# --- alta ----------------------------------------------------------------------------------------


def test_crear_una_regla_devuelve_201_con_porcentajes_e_importes_como_string(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    respuesta = cliente.post(URL, json=_regla(), headers=_con_op(gestor))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    UUID(cuerpo["id"])
    assert cuerpo["estado"] == "BORRADOR"
    assert (cuerpo["tipo"], cuerpo["medida"], cuerpo["operador"]) == (
        "VOLUMEN_OPERACION",
        "CAJAS_EQUIVALENTES",
        "GTE",
    )
    assert cuerpo["umbral"] == "20.0000"
    assert cuerpo["accion_tipo"] == "PORCENTAJE"
    assert cuerpo["accion_porcentaje"] == "0.050000"
    assert cuerpo["accion_importe"] is None
    assert (cuerpo["prioridad"], cuerpo["acumulable"]) == (1, False)
    assert cuerpo["alcances"] == []
    assert cuerpo["vigencia_desde"] is None and cuerpo["vigencia_hasta"] is None


def test_crear_una_regla_de_importe_fijo_sobre_una_marca_devuelve_el_alcance_con_su_nombre(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str]
) -> None:
    cuerpo = _crear(
        cliente,
        gestor,
        tipo="VOLUMEN_ALCANCE",
        medida="UNIDADES_BASE",
        operador="GT",
        umbral="60",
        accion_tipo="IMPORTE_FIJO",
        accion_valor="1000.00",
        alcances=[{"tipo": "MARCA", "entidad_id": str(entorno.marca_id)}],
    )

    assert cuerpo["accion_importe"] == "1000.00" and cuerpo["accion_porcentaje"] is None
    assert cuerpo["alcances"] == [
        {"tipo": "MARCA", "entidad_id": str(entorno.marca_id), "nombre": "Bodega Norte"}
    ]


def test_la_escritura_exige_operation_id(cliente: TestClient, gestor: dict[str, str]) -> None:
    respuesta = cliente.post(URL, json=_regla(), headers=gestor)

    assert respuesta.status_code == 400


@pytest.mark.parametrize("campo", ["accion_valor", "umbral"])
@pytest.mark.parametrize("valor", [0.05, 20, None])
def test_inv03_un_valor_que_no_es_string_se_rechaza_con_422(
    cliente: TestClient, gestor: dict[str, str], campo: str, valor: object
) -> None:
    respuesta = cliente.post(URL, json=_regla(**{campo: valor}), headers=_con_op(gestor))

    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    ("cambios", "codigo"),
    [
        ({"medida": "UNIDADES_BASE", "umbral": "10.5"}, "UMBRAL_INVALIDO"),
        ({"accion_valor": "1.200000"}, "ACCION_INVALIDA"),
        ({"prioridad": 0}, "PRIORIDAD_INVALIDA"),
        ({"prioridad": 1.5}, "PRIORIDAD_INVALIDA"),
        ({"nombre": "  "}, "NOMBRE_INVALIDO"),
        ({"tipo": "VOLUMEN_ALCANCE"}, "ALCANCE_INVALIDO"),
        (
            {
                "vigencia_desde": "2026-10-10T00:00:00+00:00",
                "vigencia_hasta": "2026-10-01T00:00:00+00:00",
            },
            "VIGENCIA_INVALIDA",
        ),
    ],
)
def test_un_contenido_invalido_responde_422_con_su_codigo(
    cliente: TestClient, gestor: dict[str, str], cambios: dict[str, Any], codigo: str
) -> None:
    respuesta = cliente.post(URL, json=_regla(**cambios), headers=_con_op(gestor))

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["codigo"] == codigo


@pytest.mark.parametrize(
    "cambios",
    [
        {"medida": "HISTORIAL_DE_COMPRAS"},
        {"accion_tipo": "BONIFICACION_EN_UNIDADES"},
        {"tipo": "VOLUMEN_CLIENTE"},
        {"operador": "LT"},
    ],
)
def test_un_valor_fuera_de_las_listas_cerradas_responde_422(
    cliente: TestClient, gestor: dict[str, str], cambios: dict[str, Any]
) -> None:
    """Escenario "Tipo, medida, operador o acción desconocidos": la lista cerrada está en el
    esquema de la ruta (DSC-02 a DSC-04, DSC-10 es etapa 2)."""
    respuesta = cliente.post(URL, json=_regla(**cambios), headers=_con_op(gestor))

    assert respuesta.status_code == 422


def test_inv21_un_cuerpo_con_organizacion_id_se_rechaza(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    """`organizacion_id` sale solo del token (INV-02, INV-21)."""
    respuesta = cliente.post(
        URL, json=_regla(organizacion_id=str(uuid4())), headers=_con_op(gestor)
    )

    assert respuesta.status_code == 422


def test_inv21_un_alcance_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session, gestor: dict[str, str]
) -> None:
    ajena = Entorno(sesion)

    respuesta = cliente.post(
        URL,
        json=_regla(
            tipo="VOLUMEN_ALCANCE",
            alcances=[{"tipo": "CATEGORIA", "entidad_id": str(ajena.categoria_id)}],
        ),
        headers=_con_op(gestor),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_sin_gestionar_descuentos_responde_403(cliente: TestClient, entorno: Entorno) -> None:
    sin_permiso = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")

    respuesta = cliente.post(URL, json=_regla(), headers=_con_op(sin_permiso))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_inv06_el_doble_envio_devuelve_la_misma_regla(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    operation_id = uuid4()

    primera = cliente.post(URL, json=_regla(), headers=_con_op(gestor, operation_id))
    segunda = cliente.post(URL, json=_regla(), headers=_con_op(gestor, operation_id))
    otra = cliente.post(URL, json=_regla(umbral="10"), headers=_con_op(gestor, operation_id))

    assert primera.status_code == 201 and segunda.status_code in (200, 201)
    assert primera.json()["id"] == segunda.json()["id"]
    assert otra.status_code == 409
    assert otra.json()["codigo"] == "COMANDO_INCONSISTENTE"


# --- edición -------------------------------------------------------------------------------------


def test_corregir_un_borrador_devuelve_la_regla_corregida(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    regla = _crear(cliente, gestor)

    respuesta = cliente.put(
        f"{URL}/{regla['id']}", json=_regla(umbral="24"), headers=_con_op(gestor)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["umbral"] == "24.0000"
    assert respuesta.json()["estado"] == "BORRADOR"


def test_cambiar_el_porcentaje_de_una_regla_activa_responde_409(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    regla = _crear(cliente, gestor)
    activada = cliente.post(f"{URL}/{regla['id']}/activacion", headers=_con_op(gestor))
    assert activada.status_code == 200, activada.text

    respuesta = cliente.put(
        f"{URL}/{regla['id']}", json=_regla(accion_valor="0.080000"), headers=_con_op(gestor)
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "REGLA_NO_ES_BORRADOR"


def test_ponerle_fin_a_una_regla_activa(cliente: TestClient, gestor: dict[str, str]) -> None:
    regla = _crear(cliente, gestor)
    cliente.post(f"{URL}/{regla['id']}/activacion", headers=_con_op(gestor))
    fin = (datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0)

    respuesta = cliente.put(
        f"{URL}/{regla['id']}", json={"vigencia_hasta": fin.isoformat()}, headers=_con_op(gestor)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert datetime.fromisoformat(cuerpo["vigencia_hasta"]) == fin
    assert cuerpo["estado"] == "ACTIVA"
    assert cuerpo["accion_porcentaje"] == "0.050000"


def test_una_regla_activa_con_el_fin_pasado_se_informa_vencida(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    desde = (datetime.now(UTC) - timedelta(days=10)).replace(microsecond=0)
    regla = _crear(cliente, gestor, vigencia_desde=desde.isoformat())
    cliente.post(f"{URL}/{regla['id']}/activacion", headers=_con_op(gestor))
    fin = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)

    respuesta = cliente.put(
        f"{URL}/{regla['id']}", json={"vigencia_hasta": fin.isoformat()}, headers=_con_op(gestor)
    )

    assert respuesta.json()["estado"] == "VENCIDA"


def test_inv21_modificar_una_regla_ajena_responde_404(
    cliente: TestClient, sesion: Session, gestor: dict[str, str]
) -> None:
    ajena = Entorno(sesion)
    regla_ajena = ajena.crear_regla_descuento()
    ajena.sesion.commit()

    respuesta = cliente.put(f"{URL}/{regla_ajena}", json=_regla(), headers=_con_op(gestor))

    assert respuesta.status_code == 404


# --- activación y pausa --------------------------------------------------------------------------


def test_activar_pausar_y_reactivar(cliente: TestClient, gestor: dict[str, str]) -> None:
    regla = _crear(cliente, gestor)
    url = f"{URL}/{regla['id']}"

    activada = cliente.post(f"{url}/activacion", headers=_con_op(gestor))
    assert activada.status_code == 200
    assert activada.json()["estado"] == "ACTIVA"
    assert activada.json()["vigencia_desde"] is not None

    pausada = cliente.post(f"{url}/pausa", headers=_con_op(gestor))
    assert pausada.status_code == 200
    assert pausada.json()["estado"] == "PAUSADA"

    reactivada = cliente.post(f"{url}/activacion", headers=_con_op(gestor))
    assert reactivada.json()["estado"] == "ACTIVA"
    assert reactivada.json()["vigencia_desde"] == activada.json()["vigencia_desde"]


def test_pausar_un_borrador_responde_409_regla_estado_invalido(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    regla = _crear(cliente, gestor)

    respuesta = cliente.post(f"{URL}/{regla['id']}/pausa", headers=_con_op(gestor))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "REGLA_ESTADO_INVALIDO"


def test_activar_una_regla_con_la_vigencia_terminada_responde_422(
    cliente: TestClient, gestor: dict[str, str]
) -> None:
    desde = (datetime.now(UTC) - timedelta(days=10)).replace(microsecond=0)
    hasta = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)
    regla = _crear(
        cliente, gestor, vigencia_desde=desde.isoformat(), vigencia_hasta=hasta.isoformat()
    )

    respuesta = cliente.post(f"{URL}/{regla['id']}/activacion", headers=_con_op(gestor))

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "VIGENCIA_INVALIDA"


@pytest.mark.parametrize("accion", ["activacion", "pausa"])
def test_las_transiciones_exigen_operation_id_y_permiso(
    cliente: TestClient, entorno: Entorno, gestor: dict[str, str], accion: str
) -> None:
    regla = _crear(cliente, gestor)
    url = f"{URL}/{regla['id']}/{accion}"
    sin_permiso = entorno.usuario_con(cliente, "GESTIONAR_LISTAS")

    assert cliente.post(url, headers=gestor).status_code == 400
    assert cliente.post(url, headers=_con_op(sin_permiso)).status_code == 403


def test_inv21_activar_una_regla_ajena_responde_404(
    cliente: TestClient, sesion: Session, gestor: dict[str, str]
) -> None:
    ajena = Entorno(sesion)
    regla_ajena = ajena.crear_regla_descuento()
    ajena.sesion.commit()

    respuesta = cliente.post(f"{URL}/{regla_ajena}/activacion", headers=_con_op(gestor))

    assert respuesta.status_code == 404


# --- ninguna ruta borra (TR-06) ------------------------------------------------------------------


def test_tr06_ninguna_ruta_de_descuentos_borra_nada(cliente: TestClient) -> None:
    rutas = [
        (ruta, metodo)
        for ruta, operaciones in cliente.app.openapi()["paths"].items()  # type: ignore[attr-defined]
        if ruta.startswith("/api/v1/descuentos")
        for metodo in operaciones
    ]
    assert len(rutas) == 6, rutas  # cuatro escrituras y dos lecturas
    assert [r for r in rutas if r[1].upper() in {"DELETE", "PATCH"}] == []
