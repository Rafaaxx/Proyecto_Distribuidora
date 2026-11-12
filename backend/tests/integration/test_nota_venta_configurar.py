"""Tarea 5.1 (change 20; `design.md` D10; specs `organizacion/parametros-de-organizacion` y
`sistema/pipeline-de-comandos`): `NOTA_VENTA_CONFIGURAR` v1 por el bus y por HTTP (`POST` y `GET
/api/v1/configuracion/nota-de-venta`), contra PostgreSQL real.

Reglas citadas: VTA-13, AUD-01, SEG-06, ADR-056, INV-06, INV-21.
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
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import PermisoRequeridoError
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.nota import DatoDeNotaInvalidoError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

CONFIGURAR = "NOTA_VENTA_CONFIGURAR"
URL = "/api/v1/configuracion/nota-de-venta"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _contenido(
    muestra_saldo: bool = True, domicilio: str | None = None, telefono: str | None = None
) -> dict[str, Any]:
    return {"muestra_saldo": muestra_saldo, "domicilio": domicilio, "telefono": telefono}


# --- por el bus -------------------------------------------------------------------------


def _entorno_sembrado(db_session: Session, permisos: frozenset[str] = ADMINISTRADOR) -> Entorno:
    entorno = Entorno(db_session, permisos=permisos)
    como_la_organizacion_sembrada(db_session, entorno.org)
    db_session.commit()
    return entorno


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return _entorno_sembrado(db_session)


def _estado(entorno: Entorno) -> tuple[bool, str | None, str | None]:
    entorno.sesion.expire_all()
    configuracion = identidad_service.obtener_configuracion(entorno.org, entorno.sesion)
    assert configuracion is not None
    return (
        configuracion.nota_venta_muestra_saldo,
        configuracion.nota_venta_domicilio,
        configuracion.nota_venta_telefono,
    )


def _auditorias(entorno: Entorno) -> list[Any]:
    return list(
        entorno.sesion.execute(
            text(
                "SELECT antes, despues, usuario_id, operation_id FROM auditoria "
                "WHERE organizacion_id = :o AND accion = :a "
                "AND entidad = 'configuracion_organizacion' ORDER BY id"
            ),
            {"o": entorno.org, "a": CONFIGURAR},
        ).all()
    )


def test_vta13_activar_el_saldo_y_cargar_los_datos_queda_auditado(entorno: Entorno) -> None:
    """Escenario "Activar el saldo y cargar los datos"."""
    comando = entorno.enviar(CONFIGURAR, _contenido(True, "Av. San Martín 1234", "261 555-0000"))

    assert comando.estado == "ACEPTADO"
    assert _estado(entorno) == (True, "Av. San Martín 1234", "261 555-0000")
    assert comando.resultado == {
        "muestra_saldo": True,
        "domicilio": "Av. San Martín 1234",
        "telefono": "261 555-0000",
    }
    (auditoria,) = _auditorias(entorno)
    assert auditoria.antes == {
        "nota_venta_muestra_saldo": False,
        "nota_venta_domicilio": None,
        "nota_venta_telefono": None,
    }
    assert auditoria.despues == {
        "nota_venta_muestra_saldo": True,
        "nota_venta_domicilio": "Av. San Martín 1234",
        "nota_venta_telefono": "261 555-0000",
    }
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id


def test_vta13_un_segundo_cambio_audita_el_valor_anterior_y_vaciar_deja_nulos(
    entorno: Entorno,
) -> None:
    entorno.enviar(CONFIGURAR, _contenido(True, "Calle 1", "123"))

    comando = entorno.enviar(CONFIGURAR, _contenido(False, "   ", ""))

    assert _estado(entorno) == (False, None, None)
    assert comando.resultado == {"muestra_saldo": False, "domicilio": None, "telefono": None}
    auditorias = _auditorias(entorno)
    assert len(auditorias) == 2
    por_antes = {a.antes["nota_venta_domicilio"]: a for a in auditorias}
    assert por_antes["Calle 1"].despues == {
        "nota_venta_muestra_saldo": False,
        "nota_venta_domicilio": None,
        "nota_venta_telefono": None,
    }
    assert por_antes[None].despues["nota_venta_domicilio"] == "Calle 1"


def test_vta13_un_telefono_de_solo_espacios_queda_vacio(entorno: Entorno) -> None:
    """Escenario "Texto vacío"."""
    entorno.enviar(CONFIGURAR, _contenido(False, "Calle 1", "     "))

    assert _estado(entorno) == (False, "Calle 1", None)


@pytest.mark.parametrize(
    ("domicilio", "telefono"),
    [("d" * 201, None), (None, "t" * 51)],
    ids=["domicilio_201", "telefono_51"],
)
def test_vta13_un_texto_demasiado_largo_se_rechaza_y_nada_cambia(
    entorno: Entorno, domicilio: str | None, telefono: str | None
) -> None:
    """Escenario "Texto demasiado largo"."""
    with pytest.raises(DatoDeNotaInvalidoError) as error:
        entorno.enviar(CONFIGURAR, _contenido(True, domicilio, telefono))

    assert error.value.codigo == "DATO_DE_NOTA_INVALIDO"
    assert error.value.status_http == 422
    assert _estado(entorno) == (False, None, None)
    assert _auditorias(entorno) == []


@pytest.mark.parametrize(
    "contenido",
    [
        {**_contenido(), "organizacion_id": str(uuid4())},
        {"domicilio": None, "telefono": None},
        {"muestra_saldo": "si", "domicilio": None, "telefono": None},
        {"muestra_saldo": 1, "domicilio": None, "telefono": None},
        {"muestra_saldo": True, "domicilio": 123, "telefono": None},
    ],
    ids=["extra", "sin_muestra_saldo", "booleano_texto", "booleano_entero", "domicilio_numero"],
)
def test_vta13_un_contenido_fuera_del_esquema_se_rechaza_como_invalido(
    entorno: Entorno, contenido: dict[str, Any]
) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(CONFIGURAR, contenido)

    assert _estado(entorno) == (False, None, None)
    assert _auditorias(entorno) == []


def test_seg06_sin_admin_configuracion_se_rechaza_y_no_cambia_nada(db_session: Session) -> None:
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_CREDITO"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(CONFIGURAR, _contenido(True, "Calle 1"))

    assert _estado(entorno) == (False, None, None)
    assert _auditorias(entorno) == []


def _item_de_lote(entorno: Entorno, *, modo: str) -> ItemLote:
    return ItemLote(
        operation_id=uuid4(),
        tipo=CONFIGURAR,
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=_contenido(True, "Calle 1"),  # type: ignore[arg-type]
    )


def _lote(entorno: Entorno, item: ItemLote) -> sync_service.ResultadoItemLote:
    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        FixedClock(MOMENTO),
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )
    return resultado


def test_adr056_por_el_lote_sin_admin_configuracion_recibe_permiso_requerido(
    db_session: Session,
) -> None:
    """Escenario "Por REST y por el lote" (camino del lote)."""
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_CREDITO"}))

    resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert _estado(entorno) == (False, None, None)


def test_adr056_por_el_lote_con_el_permiso_en_online_se_acepta(entorno: Entorno) -> None:
    """Triangulación: con el permiso el mismo camino aplica el cambio."""
    resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

    assert resultado.estado == "ACEPTADO"
    assert _estado(entorno) == (True, "Calle 1", None)


def test_nota_venta_configurar_en_modo_offline_se_rechaza_como_tipo_sin_ese_modo(
    entorno: Entorno,
) -> None:
    """Escenario "Modo OFFLINE" (`02` §6.5)."""
    resultado = _lote(entorno, _item_de_lote(entorno, modo="OFFLINE"))

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert _estado(entorno) == (False, None, None)


def test_inv06_el_reenvio_devuelve_el_resultado_original_sin_otra_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío"."""
    operation_id = uuid4()
    contenido = _contenido(True, "Calle 1", "123")

    primero = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_auditorias(entorno)) == 1


def test_vta13_enviar_los_mismos_valores_se_acepta(entorno: Entorno) -> None:
    entorno.enviar(CONFIGURAR, _contenido(True, "Calle 1"))
    comando = entorno.enviar(CONFIGURAR, _contenido(True, "Calle 1"))

    assert comando.estado == "ACEPTADO"
    assert len(_auditorias(entorno)) == 2


def test_inv21_el_cambio_usa_el_reloj_inyectado_y_no_toca_otra_organizacion(
    db_session: Session,
) -> None:
    """Escenario "Aislamiento"."""
    propia = _entorno_sembrado(db_session)
    ajena = _entorno_sembrado(db_session)

    propia.enviar(CONFIGURAR, _contenido(True, "Calle 1", "123"))

    assert _estado(ajena) == (False, None, None)
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


def test_vta13_http_valores_iniciales_y_cambio_del_administrador(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenarios "Valores iniciales" y "Activar el saldo y cargar los datos"."""
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    inicial = cliente.get(URL, headers=headers)
    cambio = cliente.post(
        URL,
        json=_contenido(True, "  Av. San Martín 1234 ", "261 555-0000"),
        headers=con_operation_id(headers),
    )
    final = cliente.get(URL, headers=headers)

    assert inicial.status_code == 200
    assert inicial.json() == {"muestra_saldo": False, "domicilio": None, "telefono": None}
    assert cambio.status_code == 200
    esperado = {
        "muestra_saldo": True,
        "domicilio": "Av. San Martín 1234",
        "telefono": "261 555-0000",
    }
    assert cambio.json() == esperado
    assert final.json() == esperado
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_inv06_http_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))

    primera = cliente.post(URL, json=_contenido(True, "Calle 1"), headers=headers)
    segunda = cliente.post(URL, json=_contenido(True, "Calle 1"), headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(http.auditorias(CONFIGURAR)) == 1


def test_seg06_http_sin_admin_configuracion_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Sin el permiso" (y "Por REST")."""
    http = EntornoHttp(sesion, permisos=frozenset({"VENDER"}))
    headers = http.entrar(cliente)

    lectura = cliente.get(URL, headers=headers)
    escritura = cliente.post(URL, json=_contenido(True), headers=con_operation_id(headers))

    assert lectura.status_code == escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
    assert http.configuracion()["nota_venta_muestra_saldo"] is False
    assert http.auditorias(CONFIGURAR) == []


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("domicilio", "d" * 201), ("telefono", "t" * 51)],
    ids=["domicilio_201", "telefono_51"],
)
def test_vta13_http_texto_demasiado_largo_responde_422_con_su_codigo(
    cliente: TestClient, sesion: Session, campo: str, valor: str
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(
        URL, json={**_contenido(True), campo: valor}, headers=con_operation_id(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "DATO_DE_NOTA_INVALIDO"
    assert http.configuracion()["nota_venta_muestra_saldo"] is False
    assert http.auditorias(CONFIGURAR) == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"domicilio": None, "telefono": None},
        {"muestra_saldo": "talvez", "domicilio": None, "telefono": None},
    ],
    ids=["sin_muestra_saldo", "booleano_invalido"],
)
def test_vta13_http_un_cuerpo_invalido_responde_422(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert http.configuracion()["nota_venta_muestra_saldo"] is False


def test_sin_operation_id_la_escritura_responde_400(cliente: TestClient, sesion: Session) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)

    respuesta = cliente.post(URL, json=_contenido(True), headers=http.entrar(cliente))

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
        json={**_contenido(True, "Calle 1"), "organizacion_id": str(ajena.org)},
        headers=con_operation_id(headers_propia),
    )

    assert respuesta.status_code == 200
    assert propia.configuracion()["nota_venta_muestra_saldo"] is True
    assert ajena.configuracion()["nota_venta_muestra_saldo"] is False
    assert cliente.get(URL, headers=headers_ajena).json()["muestra_saldo"] is False
