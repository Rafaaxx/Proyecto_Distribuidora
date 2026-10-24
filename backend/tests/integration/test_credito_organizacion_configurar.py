"""Tarea 5.2 (change 18b; `design.md` D14; spec `organizacion/parametros-de-organizacion`):
`CREDITO_ORGANIZACION_CONFIGURAR` v1 por el bus y por HTTP (`POST` y `GET
/api/v1/configuracion/credito`), contra PostgreSQL real.

Reglas citadas: CRE-03, CRE-06, ADR-032, SEG-06, INV-06, INV-01, INV-21, AUD-01.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from configuracion_http_utiles import (
    JWT_SECRET,
    EntornoHttp,
    como_la_organizacion_sembrada,
    con_operation_id,
)
from cuentas_corrientes_utiles import crear_cliente
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
from app.modules.identidad.domain.valores import ToleranciaOfflineInvalidaError

CONFIGURAR = "CREDITO_ORGANIZACION_CONFIGURAR"
URL = "/api/v1/configuracion/credito"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _contenido(
    politica: str = "AUTORIZAR", tipo: str | None = None, valor: str | None = None
) -> dict[str, Any]:
    return {"politica": politica, "tolerancia_tipo": tipo, "tolerancia_valor": valor}


# --- por el bus -------------------------------------------------------------------------


def _entorno_sembrado(db_session: Session, permisos: frozenset[str] = ADMINISTRADOR) -> Entorno:
    """Como una organización sembrada: política `AUTORIZAR` y tolerancia sin definir."""
    entorno = Entorno(db_session, permisos=permisos)
    como_la_organizacion_sembrada(db_session, entorno.org)
    # Confirmado: un rechazo del bus revierte la transacción y se llevaría el entorno.
    db_session.commit()
    return entorno


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return _entorno_sembrado(db_session)


def _estado(entorno: Entorno) -> tuple[str, str | None, Decimal | None]:
    entorno.sesion.expire_all()
    configuracion = identidad_service.obtener_configuracion(entorno.org, entorno.sesion)
    assert configuracion is not None
    return (
        configuracion.politica_credito_default,
        configuracion.tolerancia_offline_tipo,
        configuracion.tolerancia_offline_valor,
    )


def _auditorias(entorno: Entorno) -> list[Any]:
    return list(
        entorno.sesion.execute(
            text(
                "SELECT antes, despues, usuario_id, operation_id FROM auditoria "
                "WHERE organizacion_id = :o AND accion = :a "
                "AND entidad = 'configuracion_organizacion'"
            ),
            {"o": entorno.org, "a": CONFIGURAR},
        ).all()
    )


def test_cre06_cargar_la_tolerancia_de_la_organizacion_queda_auditada(entorno: Entorno) -> None:
    """Escenario "Cargar la tolerancia de la organización": AUTORIZAR e `IMPORTE` $20.000."""
    comando = entorno.enviar(CONFIGURAR, _contenido("AUTORIZAR", "IMPORTE", "20000.00"))

    assert comando.estado == "ACEPTADO"
    assert _estado(entorno) == ("AUTORIZAR", "IMPORTE", Decimal("20000.00"))
    assert comando.resultado == {
        "politica": "AUTORIZAR",
        "tolerancia_tipo": "IMPORTE",
        "tolerancia_valor": "20000.00",
    }
    (auditoria,) = _auditorias(entorno)
    assert auditoria.antes == {
        "politica_credito_default": "AUTORIZAR",
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }
    assert auditoria.despues == {
        "politica_credito_default": "AUTORIZAR",
        "tolerancia_offline_tipo": "IMPORTE",
        "tolerancia_offline_valor": "20000.00",
    }
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id


def test_cre03_cambiar_la_politica_a_bloquear_con_porcentaje_y_luego_vaciar_la_tolerancia(
    entorno: Entorno,
) -> None:
    entorno.enviar(CONFIGURAR, _contenido("BLOQUEAR", "PORCENTAJE", "5.00"))
    assert _estado(entorno) == ("BLOQUEAR", "PORCENTAJE", Decimal("5.00"))

    comando = entorno.enviar(CONFIGURAR, _contenido("ADVERTIR"))

    assert _estado(entorno) == ("ADVERTIR", None, None)
    assert comando.resultado == {
        "politica": "ADVERTIR",
        "tolerancia_tipo": None,
        "tolerancia_valor": None,
    }
    assert len(_auditorias(entorno)) == 2


def test_cre03_los_clientes_con_valores_propios_no_cambian(db_session: Session) -> None:
    entorno = _entorno_sembrado(db_session)
    propio = crear_cliente(db_session, entorno.org, nombre="Con valores propios")
    heredero = crear_cliente(db_session, entorno.org, nombre="Hereda todo")
    db_session.execute(
        text(
            "UPDATE cliente SET limite_credito = 1000.00, politica_credito = 'BLOQUEAR', "
            "tolerancia_offline_tipo = 'IMPORTE', tolerancia_offline_valor = 500.00 "
            "WHERE id = :id"
        ),
        {"id": propio},
    )

    entorno.enviar(CONFIGURAR, _contenido("ADVERTIR", "PORCENTAJE", "10.00"))

    filas = {
        fila.id: fila
        for fila in db_session.execute(
            text(
                "SELECT id, limite_credito, politica_credito, tolerancia_offline_tipo, "
                "tolerancia_offline_valor FROM cliente WHERE organizacion_id = :o"
            ),
            {"o": entorno.org},
        ).all()
    }
    assert tuple(filas[propio])[1:] == (
        Decimal("1000.00"),
        "BLOQUEAR",
        "IMPORTE",
        Decimal("500.00"),
    )
    assert tuple(filas[heredero])[1:] == (None, None, None, None)


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [
        ("PORCENTAJE", None),
        (None, "10.00"),
        ("IMPORTE", "-1.00"),
        ("IMPORTE", "10.005"),
        ("PORCENTAJE", "abc"),
        ("IMPORTE", "NaN"),
        ("IMPORTE", ""),
    ],
    ids=["tipo_sin_valor", "valor_sin_tipo", "negativo", "tres_decimales", "texto", "nan", "vacio"],
)
def test_cre06_una_tolerancia_incompleta_o_invalida_se_rechaza_y_nada_cambia(
    entorno: Entorno, tipo: str | None, valor: str | None
) -> None:
    """Escenario "Tolerancia incompleta"."""
    with pytest.raises(ToleranciaOfflineInvalidaError) as error:
        entorno.enviar(CONFIGURAR, _contenido("AUTORIZAR", tipo, valor))

    assert error.value.codigo == "TOLERANCIA_OFFLINE_INVALIDA"
    assert error.value.status_http == 422
    assert _estado(entorno) == ("AUTORIZAR", None, None)
    assert _auditorias(entorno) == []


@pytest.mark.parametrize(
    "contenido",
    [
        _contenido("PERMITIR"),
        _contenido("autorizar"),
        _contenido("AUTORIZAR", "MONTO", "10.00"),
        {"politica": "AUTORIZAR", "tolerancia_tipo": "IMPORTE"},
        {"tolerancia_tipo": None, "tolerancia_valor": None},
        {**_contenido(), "organizacion_id": str(uuid4())},
        _contenido("AUTORIZAR", "IMPORTE", 20000),
    ],
    ids=[
        "politica_fuera",
        "minuscula",
        "tipo_fuera",
        "sin_valor",
        "sin_politica",
        "extra",
        "numero",
    ],
)
def test_cre03_un_contenido_fuera_del_esquema_se_rechaza_como_invalido(
    entorno: Entorno, contenido: dict[str, Any]
) -> None:
    """Escenario "Política fuera del catálogo": contenido inválido, nada cambia."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(CONFIGURAR, contenido)

    assert _estado(entorno) == ("AUTORIZAR", None, None)
    assert _auditorias(entorno) == []


def test_seg06_sin_admin_configuracion_se_rechaza_y_no_cambia_nada(db_session: Session) -> None:
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_CREDITO"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(CONFIGURAR, _contenido("BLOQUEAR", "IMPORTE", "1.00"))

    assert _estado(entorno) == ("AUTORIZAR", None, None)
    assert _auditorias(entorno) == []


def test_inv06_el_reenvio_devuelve_el_resultado_original_sin_otra_auditoria(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    contenido = _contenido("BLOQUEAR", "IMPORTE", "1500.50")

    primero = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_auditorias(entorno)) == 1


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.enviar(CONFIGURAR, _contenido("BLOQUEAR"), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(CONFIGURAR, _contenido("ADVERTIR"), operation_id=operation_id)

    assert _estado(entorno) == ("BLOQUEAR", None, None)


def test_inv01_una_falla_antes_de_la_auditoria_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falla(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("falla inyectada antes de la auditoría")

    monkeypatch.setattr(identidad_service, "registrar_auditoria", _falla)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(CONFIGURAR, _contenido("BLOQUEAR", "IMPORTE", "10.00"))

    monkeypatch.undo()
    assert _estado(entorno) == ("AUTORIZAR", None, None)
    assert _auditorias(entorno) == []


def test_el_cambio_usa_el_reloj_inyectado_y_no_toca_otra_organizacion(
    db_session: Session,
) -> None:
    propia = _entorno_sembrado(db_session)
    ajena = _entorno_sembrado(db_session)

    propia.enviar(CONFIGURAR, _contenido("BLOQUEAR", "IMPORTE", "10.00"))

    assert _estado(ajena) == ("AUTORIZAR", None, None)
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


def test_cre03_http_el_administrador_lee_y_cambia_el_credito_de_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    inicial = cliente.get(URL, headers=headers)
    cambio = cliente.post(
        URL, json=_contenido("ADVERTIR", "IMPORTE", "20000.00"), headers=con_operation_id(headers)
    )
    final = cliente.get(URL, headers=headers)

    assert inicial.status_code == 200
    assert inicial.json() == {
        "politica": "AUTORIZAR",
        "tolerancia_tipo": None,
        "tolerancia_valor": None,
    }
    assert cambio.status_code == 200
    esperado = {
        "politica": "ADVERTIR",
        "tolerancia_tipo": "IMPORTE",
        "tolerancia_valor": "20000.00",
    }
    assert cambio.json() == esperado
    assert final.json() == esperado
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_inv06_http_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))

    primera = cliente.post(URL, json=_contenido("BLOQUEAR"), headers=headers)
    segunda = cliente.post(URL, json=_contenido("BLOQUEAR"), headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_seg06_http_sin_admin_configuracion_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=frozenset({"GESTIONAR_CREDITO"}))
    headers = http.entrar(cliente)

    lectura = cliente.get(URL, headers=headers)
    escritura = cliente.post(URL, json=_contenido("BLOQUEAR"), headers=con_operation_id(headers))

    assert lectura.status_code == escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
    assert http.configuracion()["politica_credito_default"] == "AUTORIZAR"
    assert http.auditorias(CONFIGURAR) == []


def test_cre06_http_tolerancia_incompleta_responde_422_con_su_codigo(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(
        URL, json=_contenido("AUTORIZAR", "PORCENTAJE", None), headers=con_operation_id(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "TOLERANCIA_OFFLINE_INVALIDA"
    assert http.auditorias(CONFIGURAR) == []


@pytest.mark.parametrize(
    "cuerpo",
    [_contenido("PERMITIR"), {"politica": "AUTORIZAR"}, _contenido("AUTORIZAR", "MONTO", "1.00")],
    ids=["politica_fuera", "incompleto", "tipo_fuera"],
)
def test_cre03_http_una_politica_o_un_tipo_fuera_del_catalogo_responde_422(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert http.configuracion()["politica_credito_default"] == "AUTORIZAR"


def test_sin_operation_id_la_escritura_responde_400(cliente: TestClient, sesion: Session) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)

    respuesta = cliente.post(URL, json=_contenido("BLOQUEAR"), headers=http.entrar(cliente))

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    propia = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ua")
    ajena = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ub")
    headers_propia = propia.entrar(cliente)
    headers_ajena = ajena.entrar(cliente)

    respuesta = cliente.post(
        URL,
        json={**_contenido("BLOQUEAR", "IMPORTE", "10.00"), "organizacion_id": str(ajena.org)},
        headers=con_operation_id(headers_propia),
    )

    assert respuesta.status_code == 200
    assert propia.configuracion()["politica_credito_default"] == "BLOQUEAR"
    assert ajena.configuracion()["politica_credito_default"] == "AUTORIZAR"
    assert cliente.get(URL, headers=headers_ajena).json()["politica"] == "AUTORIZAR"
