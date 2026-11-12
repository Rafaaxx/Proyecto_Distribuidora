"""Tarea 7.8 (change 18a): `POST /api/v1/ventas` (`VENTA_CONFIRMAR`) por HTTP.

Mismo arnés que `test_cobranzas_api.py`: PostgreSQL real, motor propio de la aplicación y `login`
real. Cubre el contrato HTTP: 201 con la venta, el número y el saldo resultante; `Operation-Id`
obligatorio; importes como string; Problem Details con un código estable por regla; permiso;
idempotencia; la organización solo del token y el aislamiento (INV-21).

Reglas citadas: VTA-06, VTA-11, VTA-12, INV-03, INV-06, INV-21, SEG-06, SEG-07, TR-07, TR-08.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.seguridad import hashear_password
from app.main import crear_app

PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-ventas-api"
URL_VENTAS = "/api/v1/ventas"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str) -> Iterator[TestClient]:
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


class Sesion:
    """Un `EntornoVenta` con un usuario que puede iniciar sesión: devuelve los encabezados y el
    cuerpo de una venta con el número del dispositivo con el que se entró."""

    def __init__(self, sesion: Session, **opciones: Any) -> None:
        self.entorno = EntornoVenta(sesion, **opciones)
        self.sesion = sesion
        self.usuario = str(
            sesion.execute(
                text("SELECT usuario FROM usuario WHERE organizacion_id = :o AND id = :u"),
                {"o": self.entorno.org, "u": self.entorno.usuario_id},
            ).scalar_one()
        )
        sesion.execute(
            text("UPDATE usuario SET password_hash = :h WHERE organizacion_id = :o AND id = :u"),
            {"h": hashear_password(PASSWORD), "o": self.entorno.org, "u": self.entorno.usuario_id},
        )
        sesion.commit()
        self.prefijo = ""

    def entrar(self, cliente_http: TestClient) -> dict[str, str]:
        slug = self.sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.entorno.org}
        ).scalar_one()
        dispositivo_id = uuid4()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": slug,
                "usuario": self.usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(dispositivo_id),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        self.sesion.expire_all()
        self.prefijo = str(
            self.sesion.execute(
                text("SELECT prefijo FROM dispositivo WHERE organizacion_id = :o AND id = :d"),
                {"o": self.entorno.org, "d": dispositivo_id},
            ).scalar_one()
        )
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def cuerpo(self, *, correlativo: int = 1, **cambios: object) -> dict[str, Any]:
        cambios.setdefault("numero", f"{self.prefijo}-{correlativo:06d}")
        return self.entorno.contenido(**cambios)


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    return int(
        sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"), {"o": organizacion_id}
        ).scalar_one()
    )


# --- 201 con la venta, el número y el saldo resultante (VTA-06, VTA-11, INV-03) ---------------


def test_vta12_confirmar_una_venta_responde_201_con_numero_y_saldo_como_string(
    cliente_http: TestClient, sesion: Session
) -> None:
    """15 botellas a $12.500 la caja x6 = `31250.00` sobre un saldo de `150000.00`."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = s.cuerpo()

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "venta_id": cuerpo["venta_id"],
        "numero": f"{s.prefijo}-000001",
        "estado": "CONFIRMADA",
        "total": "31250.00",
        "saldo": "181250.00",
        "cobranza_id": None,
    }
    assert _contar(sesion, "venta", s.entorno.org) == 1
    assert _contar(sesion, "venta_linea", s.entorno.org) == 1


def test_vta11_la_cobranza_en_el_acto_baja_el_saldo_de_la_respuesta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-11: `31250.00` de venta y `20000.00` cobrados dejan `161250.00`."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cobranza = s.entorno.cobranza()

    respuesta = cliente_http.post(
        URL_VENTAS, json=s.cuerpo(cobranza=cobranza), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["saldo"] == "161250.00"
    assert respuesta.json()["cobranza_id"] == cobranza["cobranza_id"]


def test_inv06_el_reintento_con_el_mismo_operation_id_devuelve_lo_mismo_sin_duplicar(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _con_op(s.entrar(cliente_http))
    cuerpo = s.cuerpo()

    primera = cliente_http.post(URL_VENTAS, json=cuerpo, headers=headers)
    segunda = cliente_http.post(URL_VENTAS, json=cuerpo, headers=headers)

    assert primera.status_code == 201
    assert segunda.json() == primera.json()
    assert _contar(sesion, "venta", s.entorno.org) == 1


# --- contrato HTTP (TR-07, INV-03, SEG-06, INV-21, TR-08) -----------------------------------


def test_tr07_sin_operation_id_se_rechaza_con_400_y_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(URL_VENTAS, json=s.cuerpo(), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _contar(sesion, "venta", s.entorno.org) == 0


def test_sin_sesion_responde_401(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    s.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_VENTAS, json=s.cuerpo(), headers={"Operation-Id": str(uuid4())}
    )

    assert respuesta.status_code == 401


def test_seg06_sin_vender_responde_403_sin_efectos_ni_reserva(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
    headers = s.entrar(cliente_http)
    operation_id = uuid4()

    respuesta = cliente_http.post(
        URL_VENTAS, json=s.cuerpo(), headers=_con_op(headers, operation_id)
    )

    assert respuesta.status_code == 403
    assert _contar(sesion, "venta", s.entorno.org) == 0
    assert (
        sesion.execute(
            text("SELECT count(*) FROM comando WHERE operation_id = :id"), {"id": operation_id}
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("campo", ["total", "importe_bruto", "cantidad"])
def test_inv03_un_numero_json_en_lugar_de_un_string_o_un_entero_se_rechaza(
    cliente_http: TestClient, sesion: Session, campo: str
) -> None:
    # Escenario: "Cantidad no entera"
    """INV-03: los importes viajan como string; INV-04: la cantidad es un entero."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = s.cuerpo()
    if campo == "total":
        cuerpo["total"] = 31250.0
    elif campo == "importe_bruto":
        cuerpo["lineas"][0]["importe_bruto"] = 31250.0
    else:
        cuerpo["lineas"][0]["cantidad"] = 2.5

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert _contar(sesion, "venta", s.entorno.org) == 0


def test_tr08_el_cuerpo_no_elige_la_organizacion(cliente_http: TestClient, sesion: Session) -> None:
    """Un campo extra se ignora en el cuerpo HTTP y NUNCA llega al contenido del comando."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_VENTAS, json=s.cuerpo(organizacion_id=str(uuid4())), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201
    organizacion = sesion.execute(
        text("SELECT organizacion_id FROM venta WHERE id = :id"),
        {"id": respuesta.json()["venta_id"]},
    ).scalar_one()
    assert organizacion == s.entorno.org


# --- Problem Details por código (VTA-06, VTA-12, INV-21) -----------------------------------


@pytest.mark.parametrize(
    ("cambios", "codigo", "estado"),
    [
        ({"numero": "ZZZ-000001"}, "NUMERO_INVALIDO", 422),
        ({"total": "1.00"}, "PRECIO_DIFIERE", 409),
    ],
)
def test_un_rechazo_de_dominio_responde_su_codigo_estable_y_sin_efectos(
    cliente_http: TestClient,
    sesion: Session,
    cambios: dict[str, Any],
    codigo: str,
    estado: int,
) -> None:
    """Cada regla tiene su código y su estado HTTP, y un rechazo no deja venta."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(URL_VENTAS, json=s.cuerpo(**cambios), headers=_con_op(headers))

    assert respuesta.status_code == estado
    assert respuesta.json()["codigo"] == codigo
    assert _contar(sesion, "venta", s.entorno.org) == 0


def test_vta06_un_numero_repetido_responde_409_numero_duplicado(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    assert (
        cliente_http.post(URL_VENTAS, json=s.cuerpo(), headers=_con_op(headers)).status_code == 201
    )

    respuesta = cliente_http.post(URL_VENTAS, json=s.cuerpo(), headers=_con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "NUMERO_DUPLICADO"
    assert _contar(sesion, "venta", s.entorno.org) == 1


# Escenario: "Un comando sobre un recurso de otra organización no revela su existencia"
def test_inv21_un_cliente_de_otra_organizacion_responde_404_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ajeno = EntornoVenta(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_VENTAS, json=s.cuerpo(cliente_id=str(ajeno.cliente_id)), headers=_con_op(headers)
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "venta", s.entorno.org) == 0
    assert _contar(sesion, "venta", ajeno.org) == 0
