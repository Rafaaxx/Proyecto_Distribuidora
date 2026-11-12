"""Tarea 7.5 (change 19): `POST /api/v1/ventas/{venta_id}/anulacion` (`VENTA_ANULAR`) por HTTP.

Mismo arnés que `test_ventas_api.py` y `test_cobranzas_api.py`: PostgreSQL real, motor propio de la
aplicación y `login` real. Cubre el contrato HTTP: 200 con el saldo como string y la cobranza,
403 sin `ANULAR_VENTA`, 404 de otra organización, 409 `VENTA_YA_ANULADA`, 422 por motivo,
observación, indicación del dinero o campo extra, `Operation-Id` obligatorio e idempotencia.

Reglas citadas: VTA-20, VTA-22, INV-03, INV-06, INV-21, SEG-06, SEG-07, TR-07, TR-08, TR-09.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_anular_utiles import PERMISOS_DE_ANULADOR, EntornoAnulacion

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.seguridad import hashear_password
from app.main import crear_app

PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-ventas-anular-api"
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
    """Un `EntornoAnulacion` con un usuario que puede iniciar sesión."""

    def __init__(self, sesion: Session, **opciones: Any) -> None:
        self.entorno = EntornoAnulacion(sesion, **opciones)
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

    def vender(self, cliente_http: TestClient, headers: dict[str, str], **cambios: Any) -> str:
        """Confirma una venta de 15 botellas por REST y devuelve su identificador."""
        cambios.setdefault("numero", f"{self.prefijo}-000001")
        cuerpo = self.entorno.contenido(**cambios)
        respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))
        assert respuesta.status_code == 201
        return str(cuerpo["venta_id"])


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    return int(
        sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"), {"o": organizacion_id}
        ).scalar_one()
    )


def test_vta20_anular_una_venta_responde_200_con_el_saldo_como_string(
    cliente_http: TestClient, sesion: Session
) -> None:
    """15 botellas = `31250.00` sobre un saldo de `150000.00`: anular lo devuelve a `150000.00`."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id), "observacion": "error de carga"},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "venta_id": venta_id,
        "estado": "ANULADA",
        "saldo": "150000.00",
        "cobranza_id": None,
        "cobranza_anulada": False,
    }
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 1


def test_vta22_anular_con_devolucion_responde_la_cobranza_anulada(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-22: la venta con cobro de `20000.00`, anulada con devolución, deja el saldo inicial."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    cobranza = s.entorno.cobranza()
    venta_id = s.vender(cliente_http, headers, cobranza=cobranza)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id), "devuelve_dinero": True},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["saldo"] == "150000.00"
    assert respuesta.json()["cobranza_id"] == cobranza["cobranza_id"]
    assert respuesta.json()["cobranza_anulada"] is True


def test_inv06_el_reintento_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    url = f"{URL_VENTAS}/{venta_id}/anulacion"
    cuerpo = {"motivo_id": str(s.entorno.motivo_anulacion_id)}
    operation_id = uuid4()

    primera = cliente_http.post(url, json=cuerpo, headers=_con_op(headers, operation_id))
    repetida = cliente_http.post(url, json=cuerpo, headers=_con_op(headers, operation_id))

    assert (primera.status_code, repetida.status_code) == (200, 200)
    assert repetida.json() == primera.json()
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 1


def test_vta20_anular_dos_veces_con_otro_operation_id_responde_409(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    url = f"{URL_VENTAS}/{venta_id}/anulacion"
    cuerpo = {"motivo_id": str(s.entorno.motivo_anulacion_id)}

    primera = cliente_http.post(url, json=cuerpo, headers=_con_op(headers))
    otra = cliente_http.post(url, json=cuerpo, headers=_con_op(headers))

    assert primera.status_code == 200
    assert otra.status_code == 409
    assert otra.json()["codigo"] == "VENTA_YA_ANULADA"
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 1


def test_seg06_sin_anular_venta_responde_403_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=frozenset({"VENDER"}))
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 0


def test_inv21_una_venta_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    ajena = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers_ajeno = ajena.entrar(cliente_http)
    venta_ajena = ajena.vender(cliente_http, headers_ajeno)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_ajena}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id)},
        headers=_con_op(headers),
    )
    con_motivo_ajeno = cliente_http.post(
        f"{URL_VENTAS}/{s.vender(cliente_http, headers)}/anulacion",
        json={"motivo_id": str(ajena.entorno.motivo_anulacion_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert con_motivo_ajeno.status_code == 404
    assert _contar(sesion, "venta_anulacion", ajena.entorno.org) == 0
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 0


@pytest.mark.parametrize(
    ("cuerpo_extra", "codigo"),
    [
        ({"observacion": "a" * 501}, "OBSERVACION_INVALIDA"),
        ({"devuelve_dinero": True}, "DEVOLUCION_INVALIDA"),
        ({"devuelve_dinero": "si"}, None),
        ({"organizacion_id": str(uuid4())}, None),
    ],
)
def test_vta20_un_contenido_invalido_responde_422_y_no_deja_efectos(
    cliente_http: TestClient, sesion: Session, cuerpo_extra: dict[str, Any], codigo: str | None
) -> None:
    """TR-08: la organización no viaja en el cuerpo; VTA-22: la indicación sobra en una venta sin
    cobro; D1: observación de hasta 500 caracteres y `devuelve_dinero` booleano estricto."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id), **cuerpo_extra},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    if codigo is not None:
        assert respuesta.json()["codigo"] == codigo
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 0


def test_tr09_un_motivo_de_otro_ambito_responde_422_motivo_invalido(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    ajeno = s.entorno.crear_motivo("ANULACION_COBRANZA", "Otro ámbito")
    sesion.commit()
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(ajeno)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MOTIVO_INVALIDO"
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 0


def test_tr07_sin_operation_id_se_rechaza_con_400_y_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id)},
        headers=headers,
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _contar(sesion, "venta_anulacion", s.entorno.org) == 0
