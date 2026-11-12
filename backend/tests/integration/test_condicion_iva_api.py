"""Change 11b, tarea 5.1 (HTTP) y 5.2: `POST /api/v1/configuracion/fiscal/condicion-iva`,
`GET /api/v1/configuracion/fiscal` y `GET /api/v1/costos/resumen-regla-iva` por HTTP.

Mismo arnés que `test_compras_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real (nunca un access token fabricado). Cada ruta nueva tiene su prueba de
aislamiento entre organizaciones.

Reglas citadas: CST-03, CST-06, INV-06, INV-21, SEG-06, SEG-07, TR-07, TR-08 y
`design.md` D7, D8, D10.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql, crear_producto_sql

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-condicion-iva"
URL_FISCAL = "/api/v1/configuracion/fiscal"
URL_CAMBIAR = "/api/v1/configuracion/fiscal/condicion-iva"
URL_RESUMEN = "/api/v1/costos/resumen-regla-iva"

ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})
COMPRADOR = frozenset({"REGISTRAR_COMPRA"})


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


class Entorno:
    """Una organización con un usuario con los `permisos` dados."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = ADMINISTRADOR,
        condicion: str = "RESPONSABLE_INSCRIPTO",
        usuario: str = "usuario1",
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.usuario = usuario
        rol = identidad_repository.crear_rol(
            self.org,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        self.usuario_id = nuevo_id()
        identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=self.usuario_id,
            usuario=usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.fijar_condicion(condicion)

    def fijar_condicion(self, condicion: str) -> None:
        self.sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET condicion_iva = :c, modo_impositivo = 'A', "
                "modalidad_iva_default = NULL WHERE organizacion_id = :o"
            ),
            {"c": condicion, "o": self.org},
        )

    def entrar(self, cliente_http: TestClient) -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def condicion_en_base(self) -> str:
        self.sesion.expire_all()
        return str(
            self.sesion.execute(
                text(
                    "SELECT condicion_iva FROM configuracion_organizacion "
                    "WHERE organizacion_id = :o"
                ),
                {"o": self.org},
            ).scalar_one()
        )

    def sembrar_costo(
        self,
        producto_id: UUID,
        presentacion_id: UUID,
        proveedor_id: UUID,
        *,
        computa: bool,
        vigencia: date,
        creado_en: datetime = MOMENTO,
    ) -> None:
        self.sesion.execute(
            text(
                "INSERT INTO costo_informado (id, organizacion_id, proveedor_id, producto_id, "
                "presentacion_id, valor, incluye_iva, computa_credito_fiscal, bonificacion, "
                "alicuota_aplicada, costo_base, vigencia_desde, operation_id, usuario_id, "
                "creado_en) VALUES (:id, :org, :prov, :prod, :pres, 1000, false, :comp, 0, "
                "0.21, 1000, :vig, :op, :usr, :creado)"
            ),
            {
                "id": uuid4(),
                "org": self.org,
                "prov": proveedor_id,
                "prod": producto_id,
                "pres": presentacion_id,
                "comp": computa,
                "vig": vigencia,
                "op": uuid4(),
                "usr": self.usuario_id,
                "creado": creado_en,
            },
        )

    def producto_con_presentacion(self, proveedor_id: UUID, nombre: str) -> tuple[UUID, UUID]:
        producto_id = crear_producto_sql(
            self.sesion, self.org, nombre=nombre, proveedor_id=proveedor_id
        )
        presentacion_id = crear_presentacion_sql(
            self.sesion,
            self.org,
            producto_id,
            nombre="Caja x6",
            unidades_base=6,
            es_referencia=True,
        )
        return producto_id, presentacion_id


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, sql: str, **parametros: object) -> int:
    return int(sesion.execute(text(sql), parametros).scalar_one())


# --- GET /configuracion/fiscal (D8, CST-06, INV-21) --------------------------------------


def test_cst06_cualquier_usuario_lee_la_configuracion_fiscal_de_su_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Un usuario con solo `REGISTRAR_COMPRA` recibe la regla (D8)."""
    entorno = Entorno(sesion, permisos=COMPRADOR, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_FISCAL, headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "condicion_iva": "MONOTRIBUTO",
        "computa_credito_fiscal": False,
        "modo_impositivo": "A",
        "modalidad_iva_default": None,
    }


def test_cst06_un_inscripto_computa_credito_fiscal(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR)
    headers = entorno.entrar(cliente)

    cuerpo = cliente.get(URL_FISCAL, headers=headers).json()

    assert (cuerpo["condicion_iva"], cuerpo["computa_credito_fiscal"]) == (
        "RESPONSABLE_INSCRIPTO",
        True,
    )


def test_inv21_cada_organizacion_lee_solo_su_propia_configuracion_fiscal(
    cliente: TestClient, sesion: Session
) -> None:
    organizacion_a = Entorno(sesion, permisos=COMPRADOR, condicion="MONOTRIBUTO", usuario="ua")
    organizacion_b = Entorno(sesion, permisos=COMPRADOR, usuario="ub")
    headers_a = organizacion_a.entrar(cliente)
    headers_b = organizacion_b.entrar(cliente)

    de_a = cliente.get(URL_FISCAL, headers=headers_a).json()
    de_b = cliente.get(URL_FISCAL, headers=headers_b).json()

    assert de_a["condicion_iva"] == "MONOTRIBUTO"
    assert de_b["condicion_iva"] == "RESPONSABLE_INSCRIPTO"


def test_la_configuracion_fiscal_sin_sesion_responde_401(
    cliente: TestClient, sesion: Session
) -> None:
    assert cliente.get(URL_FISCAL).status_code == 401


def test_la_organizacion_no_se_toma_de_la_peticion(cliente: TestClient, sesion: Session) -> None:
    propia = Entorno(sesion, permisos=COMPRADOR, condicion="MONOTRIBUTO", usuario="ua")
    ajena = Entorno(sesion, permisos=COMPRADOR, usuario="ub")
    headers = propia.entrar(cliente)

    respuesta = cliente.get(URL_FISCAL, params={"organizacion_id": str(ajena.org)}, headers=headers)

    assert respuesta.json()["condicion_iva"] == "MONOTRIBUTO"


# --- POST /configuracion/fiscal/condicion-iva (D7) ---------------------------------------


def test_un_administrador_cambia_la_condicion_y_recibe_la_configuracion_vigente(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "RESPONSABLE_INSCRIPTO"}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "condicion_iva": "RESPONSABLE_INSCRIPTO",
        "computa_credito_fiscal": True,
        "modo_impositivo": "A",
        "modalidad_iva_default": None,
    }
    assert entorno.condicion_en_base() == "RESPONSABLE_INSCRIPTO"
    assert (
        _contar(
            sesion,
            "SELECT count(*) FROM auditoria WHERE organizacion_id = :o "
            "AND accion = 'ORGANIZACION_CONDICION_IVA_CAMBIAR' "
            "AND entidad = 'configuracion_organizacion'",
            o=entorno.org,
        )
        == 1
    )


def test_sin_admin_configuracion_el_cambio_responde_403_y_no_cambia(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "RESPONSABLE_INSCRIPTO"}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert entorno.condicion_en_base() == "MONOTRIBUTO"


def test_un_valor_desconocido_responde_422_y_no_cambia(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "CONSUMIDOR_FINAL"}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert entorno.condicion_en_base() == "MONOTRIBUTO"


def test_el_mismo_valor_responde_409_con_su_codigo(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "MONOTRIBUTO"}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "CONDICION_IVA_SIN_CAMBIO"


@pytest.mark.parametrize(
    "preparacion",
    [
        "modo_impositivo = 'B'",
        "modalidad_iva_default = 'CLIENTE'",
    ],
)
def test_pasar_a_no_inscripto_con_modo_incompatible_responde_409_con_su_codigo(
    cliente: TestClient, sesion: Session, preparacion: str
) -> None:
    """ADR-009 (solo RI), D2/D7: el modo `B` o una modalidad definida impiden pasar a
    `MONOTRIBUTO`. 409 con `MODO_IMPOSITIVO_INCOMPATIBLE` y la condición no cambia."""
    entorno = Entorno(sesion, condicion="RESPONSABLE_INSCRIPTO")
    sesion.execute(
        text(f"UPDATE configuracion_organizacion SET {preparacion} WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "MONOTRIBUTO"}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "MODO_IMPOSITIVO_INCOMPATIBLE"
    assert entorno.condicion_en_base() == "RESPONSABLE_INSCRIPTO"


def test_sin_operation_id_responde_400_y_no_cambia(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "RESPONSABLE_INSCRIPTO"}, headers=headers
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert entorno.condicion_en_base() == "MONOTRIBUTO"


def test_inv06_el_reenvio_devuelve_el_resultado_original(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    headers = _con_op(entorno.entrar(cliente))

    primera = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "RESPONSABLE_INSCRIPTO"}, headers=headers
    )
    segunda = cliente.post(
        URL_CAMBIAR, json={"condicion_iva": "RESPONSABLE_INSCRIPTO"}, headers=headers
    )

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert segunda.json() == primera.json()


def test_inv21_el_cambio_afecta_solo_a_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    propia = Entorno(sesion, condicion="MONOTRIBUTO", usuario="ua")
    ajena = Entorno(sesion, condicion="MONOTRIBUTO", usuario="ub")
    headers = propia.entrar(cliente)

    respuesta = cliente.post(
        URL_CAMBIAR,
        json={"condicion_iva": "RESPONSABLE_INSCRIPTO", "organizacion_id": str(ajena.org)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert propia.condicion_en_base() == "RESPONSABLE_INSCRIPTO"
    assert ajena.condicion_en_base() == "MONOTRIBUTO"


# --- GET /costos/resumen-regla-iva (D10, CST-03, CST-06) ---------------------------------


def _armar_costos(entorno: Entorno) -> date:
    """12 costos vigentes sin crédito fiscal y 3 con (uno por producto y presentación)."""
    proveedor_id = crear_proveedor(entorno.sesion, entorno.org, nombre="Bodega Sur")
    for numero in range(12):
        producto_id, presentacion_id = entorno.producto_con_presentacion(
            proveedor_id, f"Sin crédito {numero}"
        )
        entorno.sembrar_costo(
            producto_id, presentacion_id, proveedor_id, computa=False, vigencia=date(2026, 3, 1)
        )
    for numero in range(3):
        producto_id, presentacion_id = entorno.producto_con_presentacion(
            proveedor_id, f"Con crédito {numero}"
        )
        entorno.sembrar_costo(
            producto_id, presentacion_id, proveedor_id, computa=True, vigencia=date(2026, 7, 1)
        )
    return date(2026, 10, 1)


def test_cst06_el_resumen_cuenta_los_costos_vigentes_por_regla(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, condicion="MONOTRIBUTO")
    fecha = _armar_costos(entorno)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_RESUMEN, params={"fecha": fecha.isoformat()}, headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "fecha": "2026-10-01",
        "con_credito_fiscal": 3,
        "sin_credito_fiscal": 12,
    }


def test_cst03_el_resumen_cuenta_solo_el_ultimo_costo_de_cada_presentacion(
    cliente: TestClient, sesion: Session
) -> None:
    """El vigente es el de mayor vigencia que no supere la fecha: un costo posterior a la
    fecha no cuenta y uno anterior reemplazado por otro tampoco."""
    entorno = Entorno(sesion)
    proveedor_id = crear_proveedor(sesion, entorno.org, nombre="Bodega Sur")
    producto_id, presentacion_id = entorno.producto_con_presentacion(proveedor_id, "Vino A")
    entorno.sembrar_costo(
        producto_id, presentacion_id, proveedor_id, computa=False, vigencia=date(2026, 1, 1)
    )
    entorno.sembrar_costo(
        producto_id, presentacion_id, proveedor_id, computa=True, vigencia=date(2026, 6, 1)
    )
    entorno.sembrar_costo(
        producto_id, presentacion_id, proveedor_id, computa=False, vigencia=date(2027, 1, 1)
    )
    headers = entorno.entrar(cliente)

    a_octubre = cliente.get(URL_RESUMEN, params={"fecha": "2026-10-01"}, headers=headers).json()
    a_marzo = cliente.get(URL_RESUMEN, params={"fecha": "2026-03-01"}, headers=headers).json()

    assert (a_octubre["con_credito_fiscal"], a_octubre["sin_credito_fiscal"]) == (1, 0)
    assert (a_marzo["con_credito_fiscal"], a_marzo["sin_credito_fiscal"]) == (0, 1)


def test_el_resumen_sin_costos_informa_cero_en_ambas(cliente: TestClient, sesion: Session) -> None:
    headers = Entorno(sesion).entrar(cliente)

    cuerpo = cliente.get(URL_RESUMEN, params={"fecha": "2026-10-01"}, headers=headers).json()

    assert (cuerpo["con_credito_fiscal"], cuerpo["sin_credito_fiscal"]) == (0, 0)


@pytest.mark.parametrize("permiso", ["ADMIN_CONFIGURACION", "EDITAR_COSTOS"])
def test_el_resumen_lo_leen_admin_configuracion_o_editar_costos(
    cliente: TestClient, sesion: Session, permiso: str
) -> None:
    headers = Entorno(sesion, permisos=frozenset({permiso})).entrar(cliente)

    respuesta = cliente.get(URL_RESUMEN, params={"fecha": "2026-10-01"}, headers=headers)

    assert respuesta.status_code == 200


def test_el_resumen_sin_permiso_responde_403(cliente: TestClient, sesion: Session) -> None:
    headers = Entorno(sesion, permisos=COMPRADOR).entrar(cliente)

    respuesta = cliente.get(URL_RESUMEN, params={"fecha": "2026-10-01"}, headers=headers)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_inv21_el_resumen_cuenta_solo_los_costos_de_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    propia = Entorno(sesion, usuario="ua")
    ajena = Entorno(sesion, usuario="ub")
    _armar_costos(ajena)
    headers = propia.entrar(cliente)

    cuerpo = cliente.get(URL_RESUMEN, params={"fecha": "2026-10-01"}, headers=headers).json()

    assert (cuerpo["con_credito_fiscal"], cuerpo["sin_credito_fiscal"]) == (0, 0)


def test_el_resumen_sin_fecha_usa_la_fecha_de_negocio_de_hoy(
    cliente: TestClient, sesion: Session
) -> None:
    headers = Entorno(sesion).entrar(cliente)

    respuesta = cliente.get(URL_RESUMEN, headers=headers)

    assert respuesta.status_code == 200
    assert date.fromisoformat(respuesta.json()["fecha"]) <= datetime.now(UTC).date()


def test_el_resumen_con_fecha_invalida_responde_422(cliente: TestClient, sesion: Session) -> None:
    headers = Entorno(sesion).entrar(cliente)

    respuesta = cliente.get(URL_RESUMEN, params={"fecha": "ayer"}, headers=headers)

    assert respuesta.status_code == 422
