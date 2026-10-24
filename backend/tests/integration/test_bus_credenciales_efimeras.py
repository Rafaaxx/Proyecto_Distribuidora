"""Tarea 6.1 (change 18b, `design.md` D2): las credenciales de autorización (PIN) viajan fuera
del contenido del comando, como dato efímero.

`POST /api/v1/ventas` acepta `credenciales: [{autorizador_id, pin}]` (de 0 a 2). La ruta las
separa antes de armar el contenido y calcular la huella y se las entrega al handler por clausura
como `SecretStr`: nunca se persisten, registran ni devuelven. Un cuerpo inválido responde 422
sin `input` ni `ctx`; el error de contenido inválido no lleva valores; el lote no admite
credenciales.

Reglas citadas: `02` §17, ADR-019, INV-06, SYN-06.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import URL_VENTAS, Sesion

from app.api_v1 import sistema
from app.commands import registro
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app

PIN = "482913"
PIN_INCORRECTO = "937104"
JWT_SECRET = "secreto-de-prueba-credenciales-efimeras"
URL_LOTE = "/api/v1/sync/comandos"


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


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _credenciales(pin: str = PIN) -> list[dict[str, str]]:
    return [{"autorizador_id": str(uuid4()), "pin": pin}]


def _volcado(sesion: Session, tabla: str) -> str:
    """Todo el contenido de la tabla como texto, para buscar un secreto en cualquier columna."""
    sesion.rollback()
    return str(
        sesion.execute(
            text(f"SELECT coalesce(string_agg(to_json(t)::text, ' '), '') FROM {tabla} t")
        ).scalar_one()
    )


def _sin_rastro(sesion: Session, secreto: str) -> None:
    for tabla in ("comando", "comando_cuarentena", "auditoria", "observacion"):
        assert secreto not in _volcado(sesion, tabla), tabla


def _contenido_de(cuerpo: dict[str, object]) -> dict[str, object]:
    """El contenido que la ruta arma a partir del cuerpo, sin las credenciales."""
    return {
        "venta_id": cuerpo["venta_id"],
        "numero": cuerpo["numero"],
        "cliente_id": cuerpo["cliente_id"],
        "ubicacion_id": cuerpo.get("ubicacion_id"),
        "lista_id": cuerpo.get("lista_id"),
        "lista_version_id": cuerpo.get("lista_version_id"),
        "motivo_lista_id": cuerpo.get("motivo_lista_id"),
        "lineas": cuerpo["lineas"],
        "total": cuerpo["total"],
        "cobranza": cuerpo.get("cobranza"),
    }


# --- la huella no depende de las credenciales (INV-06) -------------------------------------


def test_inv06_la_huella_con_y_sin_credenciales_es_la_misma(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = s.cuerpo()
    operacion = uuid4()

    primera = cliente_http.post(
        URL_VENTAS,
        json={**cuerpo, "credenciales": _credenciales()},
        headers=_con_op(headers, operacion),
    )
    segunda = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers, operacion))

    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json() == primera.json()
    huella = sesion.execute(
        text("SELECT huella FROM comando WHERE operation_id = :o"), {"o": operacion}
    ).scalar_one()
    sesion.rollback()
    assert huella == calcular_huella(_contenido_de(cuerpo))  # type: ignore[arg-type]


def test_inv06_dos_pin_distintos_con_el_mismo_operation_id_devuelven_el_resultado_original(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = s.cuerpo()
    operacion = uuid4()
    autorizador = str(uuid4())

    primera = cliente_http.post(
        URL_VENTAS,
        json={**cuerpo, "credenciales": [{"autorizador_id": autorizador, "pin": PIN}]},
        headers=_con_op(headers, operacion),
    )
    segunda = cliente_http.post(
        URL_VENTAS,
        json={**cuerpo, "credenciales": [{"autorizador_id": autorizador, "pin": PIN_INCORRECTO}]},
        headers=_con_op(headers, operacion),
    )

    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json() == primera.json()


# --- 422 sin input ni ctx ni el valor (`02` §17) ---------------------------------------------


@pytest.mark.parametrize(
    "dano",
    [
        {"total": "no-es-un-importe"},
        {"cliente_id": "no-es-un-uuid"},
    ],
)
def test_un_cuerpo_invalido_responde_422_sin_input_ni_ctx_ni_el_pin(
    cliente_http: TestClient, sesion: Session, dano: dict[str, object]
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = {**s.cuerpo(), **dano, "credenciales": _credenciales()}

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert PIN not in respuesta.text
    errores = respuesta.json()["detail"]
    assert errores
    for error in errores:
        assert "input" not in error
        assert "ctx" not in error
        assert {"type", "loc", "msg"} <= set(error)
    _sin_rastro(sesion, PIN)


def test_un_pin_con_forma_invalida_responde_422_sin_el_valor(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = {**s.cuerpo(), "credenciales": [{"autorizador_id": str(uuid4()), "pin": 482913}]}

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert "482913" not in respuesta.text
    assert all("input" not in error for error in respuesta.json()["detail"])


def test_a_lo_sumo_dos_credenciales(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = {**s.cuerpo(), "credenciales": _credenciales() * 3}

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert PIN not in respuesta.text


# --- el contenido inválido no lleva valores (SYN-06) -----------------------------------------


def test_el_error_de_contenido_invalido_no_incluye_el_valor_recibido() -> None:
    handler = registro.resolver_handler("VENTA_CONFIRMAR", 1)

    with pytest.raises(ContenidoDeComandoInvalidoError) as error:
        registro.validar_contenido(
            handler,
            {"total": "valor-secreto-no-numerico", "credenciales": _credenciales()},
        )

    assert "valor-secreto-no-numerico" not in error.value.mensaje
    assert PIN not in error.value.mensaje
    assert "total" in error.value.mensaje


# --- ningún rastro de las credenciales (INV-06, `02` §17) ------------------------------------


@pytest.mark.parametrize("pin", [PIN, PIN_INCORRECTO])
def test_las_credenciales_no_quedan_en_la_base_el_resultado_ni_los_registros(
    cliente_http: TestClient,
    sesion: Session,
    caplog: pytest.LogCaptureFixture,
    pin: str,
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    with caplog.at_level(logging.DEBUG):
        respuesta = cliente_http.post(
            URL_VENTAS,
            json={**s.cuerpo(), "credenciales": _credenciales(pin)},
            headers=_con_op(headers),
        )

    assert respuesta.status_code == 201
    assert pin not in respuesta.text
    assert pin not in caplog.text
    _sin_rastro(sesion, pin)


# --- el lote no admite credenciales (SYN-06) -------------------------------------------------


def _item_de_lote(s: Sesion, sesion: Session, **extra: object) -> dict[str, object]:
    dispositivo = sesion.execute(
        text("SELECT id FROM dispositivo WHERE organizacion_id = :o AND prefijo = :p"),
        {"o": s.entorno.org, "p": s.prefijo},
    ).scalar_one()
    sesion.rollback()
    return {
        "operation_id": str(uuid4()),
        "tipo": "VENTA_CONFIRMAR",
        "version": 1,
        "modo": "ONLINE",
        "usuario_id": str(s.entorno.usuario_id),
        "dispositivo_id": str(dispositivo),
        "occurred_at": "2026-10-18T12:00:00Z",
        "secuencia": 1,
        "app_version": "1.0.0",
        "contenido": s.cuerpo(),
        **extra,
    }


def test_un_item_del_lote_con_credenciales_se_rechaza_sin_guardarlas(
    cliente_http: TestClient, sesion: Session, caplog: pytest.LogCaptureFixture
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    item = _item_de_lote(s, sesion, credenciales=_credenciales())

    with caplog.at_level(logging.DEBUG):
        respuesta = cliente_http.post(URL_LOTE, json={"items": [item]}, headers=headers)

    assert respuesta.status_code == 422
    assert PIN not in respuesta.text
    assert PIN not in caplog.text
    _sin_rastro(sesion, PIN)
    assert _volcado(sesion, "comando") == ""


def test_un_item_con_credenciales_dentro_del_contenido_es_malformado_y_no_se_guarda(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    item = _item_de_lote(s, sesion)
    item["contenido"] = {**s.cuerpo(), "credenciales": _credenciales()}  # type: ignore[dict-item]

    respuesta = cliente_http.post(URL_LOTE, json={"items": [item]}, headers=headers)

    assert respuesta.status_code == 200
    (resultado,) = respuesta.json()["resultados"]
    assert resultado["estado"] == "RECHAZADO"
    assert resultado["error_codigo"] == "CONTENIDO_DE_COMANDO_INVALIDO"
    assert PIN not in respuesta.text
    assert _volcado(sesion, "comando") == ""
    _sin_rastro(sesion, PIN)


def test_un_item_con_credenciales_de_un_dispositivo_revocado_no_va_a_cuarentena(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    item = _item_de_lote(s, sesion)
    item["contenido"] = {**s.cuerpo(), "credenciales": _credenciales()}  # type: ignore[dict-item]
    sesion.execute(
        text("UPDATE dispositivo SET estado = 'REVOCADO' WHERE organizacion_id = :o"),
        {"o": s.entorno.org},
    )
    sesion.commit()

    respuesta = cliente_http.post(URL_LOTE, json={"items": [item]}, headers=headers)

    assert respuesta.status_code == 200
    (resultado,) = respuesta.json()["resultados"]
    assert resultado["estado"] == "RECHAZADO"
    assert PIN not in respuesta.text
    _sin_rastro(sesion, PIN)
