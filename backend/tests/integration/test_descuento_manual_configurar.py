"""Tarea 5.1 (change 18b; `design.md` D13; spec `descuentos/descuento-manual`):
`DESCUENTO_MANUAL_CONFIGURAR` v1 por el bus y por HTTP (`POST` y `GET
/api/v1/configuracion/descuento-manual`), contra PostgreSQL real.

Reglas citadas: DSC-06, AUD-01, SEG-06, INV-06, INV-01, INV-21.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from configuracion_http_utiles import (
    JWT_SECRET,
    EntornoHttp,
    como_la_organizacion_sembrada,
    con_operation_id,
)
from fastapi.testclient import TestClient
from precios_utiles import MOMENTO, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import PermisoRequeridoError
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad import service as identidad_service

CONFIGURAR = "DESCUENTO_MANUAL_CONFIGURAR"
URL = "/api/v1/configuracion/descuento-manual"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


# --- por el bus -------------------------------------------------------------------------


def _entorno_sembrado(db_session: Session, permisos: frozenset[str] = ADMINISTRADOR) -> Entorno:
    """Como una organización sembrada: descuento habilitado y motivo sin definir."""
    entorno = Entorno(db_session, permisos=permisos)
    como_la_organizacion_sembrada(db_session, entorno.org)
    # Confirmado: un rechazo del bus revierte la transacción y se llevaría el entorno.
    db_session.commit()
    return entorno


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return _entorno_sembrado(db_session)


def _estado(entorno: Entorno) -> tuple[bool, bool | None]:
    entorno.sesion.expire_all()
    configuracion = identidad_service.obtener_configuracion(entorno.org, entorno.sesion)
    assert configuracion is not None
    return configuracion.descuento_manual_habilitado, configuracion.motivo_obligatorio_descuento


def _auditorias(entorno: Entorno) -> list[Any]:
    return list(
        entorno.sesion.execute(
            text(
                "SELECT antes, despues, usuario_id, operation_id, entidad_id FROM auditoria "
                "WHERE organizacion_id = :o AND accion = :a "
                "AND entidad = 'configuracion_organizacion'"
            ),
            {"o": entorno.org, "a": CONFIGURAR},
        ).all()
    )


def test_dsc06_exigir_motivo_deja_la_configuracion_y_una_auditoria_con_antes_y_despues(
    entorno: Entorno,
) -> None:
    """Escenario "Exigir motivo": la organización nace con el descuento habilitado y el motivo
    sin definir (nulo); el comando fija los dos."""
    assert _estado(entorno) == (True, None)

    comando = entorno.enviar(CONFIGURAR, {"habilitado": True, "motivo_obligatorio": True})

    assert comando.estado == "ACEPTADO"
    assert _estado(entorno) == (True, True)
    assert comando.resultado == {"habilitado": True, "motivo_obligatorio": True}
    (auditoria,) = _auditorias(entorno)
    assert auditoria.antes == {
        "descuento_manual_habilitado": True,
        "motivo_obligatorio_descuento": None,
    }
    assert auditoria.despues == {
        "descuento_manual_habilitado": True,
        "motivo_obligatorio_descuento": True,
    }
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id
    assert auditoria.entidad_id == entorno.org


def test_dsc06_deshabilitar_y_no_exigir_motivo_y_volver_a_habilitar(entorno: Entorno) -> None:
    """Triangula con otros valores: el antes de la segunda auditoría es el después de la primera."""
    primero, segundo = uuid4(), uuid4()
    entorno.enviar(
        CONFIGURAR, {"habilitado": False, "motivo_obligatorio": False}, operation_id=primero
    )
    assert _estado(entorno) == (False, False)

    entorno.enviar(
        CONFIGURAR, {"habilitado": True, "motivo_obligatorio": False}, operation_id=segundo
    )

    assert _estado(entorno) == (True, False)
    por_operacion = {fila.operation_id: fila for fila in _auditorias(entorno)}
    assert len(por_operacion) == 2
    assert por_operacion[segundo].antes == {
        "descuento_manual_habilitado": False,
        "motivo_obligatorio_descuento": False,
    }
    assert por_operacion[segundo].despues == {
        "descuento_manual_habilitado": True,
        "motivo_obligatorio_descuento": False,
    }


def test_seg06_sin_admin_configuracion_se_rechaza_y_no_cambia_nada(db_session: Session) -> None:
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_DESCUENTOS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(CONFIGURAR, {"habilitado": False, "motivo_obligatorio": True})

    assert _estado(entorno) == (True, None)
    assert _auditorias(entorno) == []


@pytest.mark.parametrize(
    "contenido",
    [
        {"habilitado": True, "motivo_obligatorio": "true"},
        {"habilitado": True, "motivo_obligatorio": None},
        {"habilitado": True, "motivo_obligatorio": 1},
        {"habilitado": "si", "motivo_obligatorio": True},
        {"habilitado": True},
        {"motivo_obligatorio": True},
        {"habilitado": True, "motivo_obligatorio": True, "organizacion_id": str(uuid4())},
    ],
    ids=["texto", "nulo", "entero", "habilitado_texto", "sin_motivo", "sin_habilitado", "extra"],
)
def test_dsc06_un_contenido_que_no_son_dos_booleanos_se_rechaza_como_invalido(
    entorno: Entorno, contenido: dict[str, Any]
) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(CONFIGURAR, contenido)

    assert _estado(entorno) == (True, None)
    assert _auditorias(entorno) == []


def test_inv06_el_reenvio_devuelve_el_resultado_original_con_una_sola_auditoria(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    contenido = {"habilitado": True, "motivo_obligatorio": True}

    primero = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_auditorias(entorno)) == 1


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.enviar(
        CONFIGURAR, {"habilitado": True, "motivo_obligatorio": True}, operation_id=operation_id
    )

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            CONFIGURAR,
            {"habilitado": False, "motivo_obligatorio": True},
            operation_id=operation_id,
        )

    assert _estado(entorno) == (True, True)


def test_inv01_una_falla_antes_de_la_auditoria_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falla(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("falla inyectada antes de la auditoría")

    monkeypatch.setattr(identidad_service, "registrar_auditoria", _falla)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(CONFIGURAR, {"habilitado": False, "motivo_obligatorio": True})

    monkeypatch.undo()
    assert _estado(entorno) == (True, None)
    assert _auditorias(entorno) == []


def test_el_cambio_usa_el_reloj_inyectado_y_no_toca_otra_organizacion(
    db_session: Session,
) -> None:
    propia = _entorno_sembrado(db_session)
    ajena = _entorno_sembrado(db_session)

    propia.enviar(CONFIGURAR, {"habilitado": False, "motivo_obligatorio": True})

    assert _estado(propia) == (False, True)
    assert _estado(ajena) == (True, None)
    configuracion = identidad_service.obtener_configuracion(propia.org, propia.sesion)
    assert configuracion is not None
    assert configuracion.actualizado_en == MOMENTO
    assert configuracion.actualizado_por_id == propia.usuario_id


# --- por HTTP ----------------------------------------------------------------------------


@pytest.fixture
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str, _limpiar_datos_confirmados: None) -> Iterator[TestClient]:
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
def sesion(database_url: str) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def test_dsc06_http_el_administrador_lee_y_cambia_el_descuento_manual(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    inicial = cliente.get(URL, headers=headers)
    cambio = cliente.post(
        URL,
        json={"habilitado": True, "motivo_obligatorio": True},
        headers=con_operation_id(headers),
    )
    final = cliente.get(URL, headers=headers)

    assert inicial.status_code == 200
    assert inicial.json() == {"habilitado": True, "motivo_obligatorio": False}
    assert cambio.status_code == 200
    assert cambio.json() == {"habilitado": True, "motivo_obligatorio": True}
    assert final.json() == {"habilitado": True, "motivo_obligatorio": True}
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_inv06_http_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))
    cuerpo = {"habilitado": False, "motivo_obligatorio": True}

    primera = cliente.post(URL, json=cuerpo, headers=headers)
    segunda = cliente.post(URL, json=cuerpo, headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_seg06_http_sin_admin_configuracion_responde_403_en_la_lectura_y_la_escritura(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=frozenset({"VENDER"}))
    headers = http.entrar(cliente)

    lectura = cliente.get(URL, headers=headers)
    escritura = cliente.post(
        URL,
        json={"habilitado": False, "motivo_obligatorio": True},
        headers=con_operation_id(headers),
    )

    assert lectura.status_code == escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
    assert http.configuracion()["descuento_manual_habilitado"] is True
    assert http.auditorias(CONFIGURAR) == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"habilitado": True, "motivo_obligatorio": "true"},
        {"habilitado": True, "motivo_obligatorio": None},
        {"habilitado": True},
    ],
    ids=["texto", "nulo", "incompleto"],
)
def test_dsc06_http_un_valor_que_no_es_booleano_responde_422_sin_efectos(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert http.configuracion()["motivo_obligatorio_descuento"] is None
    assert http.auditorias(CONFIGURAR) == []


def test_sin_operation_id_la_escritura_responde_400(cliente: TestClient, sesion: Session) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)

    respuesta = cliente.post(
        URL,
        json={"habilitado": True, "motivo_obligatorio": True},
        headers=http.entrar(cliente),
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    """Un `organizacion_id` ajeno en el cuerpo se ignora; la organización sale del token."""
    propia = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ua")
    ajena = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ub")
    headers_propia = propia.entrar(cliente)
    headers_ajena = ajena.entrar(cliente)

    respuesta = cliente.post(
        URL,
        json={
            "habilitado": False,
            "motivo_obligatorio": True,
            "organizacion_id": str(ajena.org),
        },
        headers=con_operation_id(headers_propia),
    )

    assert respuesta.status_code == 200
    assert propia.configuracion()["descuento_manual_habilitado"] is False
    assert ajena.configuracion()["descuento_manual_habilitado"] is True
    assert ajena.configuracion()["motivo_obligatorio_descuento"] is None
    assert cliente.get(URL, headers=headers_ajena).json() == {
        "habilitado": True,
        "motivo_obligatorio": False,
    }
