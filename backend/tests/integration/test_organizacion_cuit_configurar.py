"""Tarea 12.3 (change 20; `design.md` D15; specs `organizacion/parametros-de-organizacion` y
`sistema/pipeline-de-comandos`): `ORGANIZACION_DATOS_CONFIGURAR` v1 (nombre y CUIT de la
organización) por el bus y por HTTP (`POST` y `GET /api/v1/configuracion/organizacion`), contra
PostgreSQL real.

Reglas citadas: VTA-13, AUD-01, SEG-06, ADR-056, INV-06, INV-21.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

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
from app.modules.identidad.domain.organizacion import (
    CuitInvalidoError,
    NombreDeOrganizacionInvalidoError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

CONFIGURAR = "ORGANIZACION_DATOS_CONFIGURAR"
URL = "/api/v1/configuracion/organizacion"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _contenido(nombre: str = "Distribuidora Sur", cuit: str | None = None) -> dict[str, Any]:
    return {"nombre": nombre, "cuit": cuit}


def _datos(sesion: Session, organizacion_id: UUID) -> tuple[str, str | None]:
    sesion.expire_all()
    fila = sesion.execute(
        text("SELECT nombre, cuit FROM organizacion WHERE id = :o"), {"o": organizacion_id}
    ).one()
    return fila.nombre, fila.cuit


def _auditorias(sesion: Session, organizacion_id: UUID) -> list[Any]:
    sesion.expire_all()
    return list(
        sesion.execute(
            text(
                "SELECT antes, despues, usuario_id, operation_id, origen, entidad_id "
                "FROM auditoria WHERE organizacion_id = :o AND accion = :a "
                "AND entidad = 'organizacion' ORDER BY id"
            ),
            {"o": organizacion_id, "a": CONFIGURAR},
        ).all()
    )


# --- por el bus -------------------------------------------------------------------------


def _entorno_sembrado(db_session: Session, permisos: frozenset[str] = ADMINISTRADOR) -> Entorno:
    entorno = Entorno(db_session, permisos=permisos)
    como_la_organizacion_sembrada(db_session, entorno.org)
    db_session.commit()
    return entorno


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return _entorno_sembrado(db_session)


def test_vta13_cargar_nombre_y_cuit_normaliza_y_deja_una_auditoria(entorno: Entorno) -> None:
    """Escenario "Cargar el nombre y el CUIT"."""
    nombre_inicial, cuit_inicial = _datos(entorno.sesion, entorno.org)

    comando = entorno.enviar(CONFIGURAR, _contenido("  Distribuidora Sur SRL ", "30-71234567-8"))

    assert comando.estado == "ACEPTADO"
    assert _datos(entorno.sesion, entorno.org) == ("Distribuidora Sur SRL", "30712345678")
    assert comando.resultado == {"nombre": "Distribuidora Sur SRL", "cuit": "30712345678"}
    (auditoria,) = _auditorias(entorno.sesion, entorno.org)
    assert auditoria.antes == {"nombre": nombre_inicial, "cuit": cuit_inicial}
    assert auditoria.despues == {"nombre": "Distribuidora Sur SRL", "cuit": "30712345678"}
    assert auditoria.origen == "COMANDO"
    assert auditoria.entidad_id == entorno.org
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id


def test_vta13_un_segundo_cambio_audita_el_anterior_y_vaciar_el_cuit_lo_deja_nulo(
    entorno: Entorno,
) -> None:
    entorno.enviar(CONFIGURAR, _contenido("Uno", "30 71234567 8"))

    comando = entorno.enviar(CONFIGURAR, _contenido("Dos", "   "))

    assert _datos(entorno.sesion, entorno.org) == ("Dos", None)
    assert comando.resultado == {"nombre": "Dos", "cuit": None}
    auditorias = _auditorias(entorno.sesion, entorno.org)
    assert len(auditorias) == 2
    por_nombre_anterior = {a.antes["nombre"]: a for a in auditorias}
    assert por_nombre_anterior["Uno"].antes["cuit"] == "30712345678"
    assert por_nombre_anterior["Uno"].despues == {"nombre": "Dos", "cuit": None}


@pytest.mark.parametrize("nombre", ["", "   ", "n" * 201], ids=["vacio", "espacios", "201"])
def test_vta13_un_nombre_invalido_rechaza_todo_y_el_cuit_enviado_tampoco_se_guarda(
    entorno: Entorno, nombre: str
) -> None:
    """Escenario "Nombre inválido" (atomicidad)."""
    antes = _datos(entorno.sesion, entorno.org)

    with pytest.raises(NombreDeOrganizacionInvalidoError) as error:
        entorno.enviar(CONFIGURAR, _contenido(nombre, "30-71234567-8"))

    assert error.value.codigo == "NOMBRE_DE_ORGANIZACION_INVALIDO"
    assert error.value.status_http == 422
    assert _datos(entorno.sesion, entorno.org) == antes
    assert _auditorias(entorno.sesion, entorno.org) == []


@pytest.mark.parametrize(
    "cuit",
    ["3071234567", "307123456789", "30-7123456A-8", "30.71234567.8"],
    ids=["diez", "doce", "letra", "puntos"],
)
def test_vta13_un_cuit_invalido_rechaza_todo_sin_cambios_ni_auditoria(
    entorno: Entorno, cuit: str
) -> None:
    """Escenario "CUIT inválido"."""
    antes = _datos(entorno.sesion, entorno.org)

    with pytest.raises(CuitInvalidoError) as error:
        entorno.enviar(CONFIGURAR, _contenido("Nombre nuevo", cuit))

    assert error.value.codigo == "CUIT_INVALIDO"
    assert error.value.status_http == 422
    assert _datos(entorno.sesion, entorno.org) == antes
    assert _auditorias(entorno.sesion, entorno.org) == []


def test_vta13_enviar_los_mismos_valores_se_acepta(entorno: Entorno) -> None:
    entorno.enviar(CONFIGURAR, _contenido("Igual", "30712345678"))
    comando = entorno.enviar(CONFIGURAR, _contenido("Igual", "30712345678"))

    assert comando.estado == "ACEPTADO"
    assert len(_auditorias(entorno.sesion, entorno.org)) == 2


@pytest.mark.parametrize(
    "contenido",
    [
        {**_contenido(), "organizacion_id": str(uuid4())},
        {"cuit": None},
        {"nombre": "X"},
        {"nombre": 123, "cuit": None},
        {"nombre": "X", "cuit": 30712345678},
    ],
    ids=["extra", "sin_nombre", "sin_cuit", "nombre_numero", "cuit_numero"],
)
def test_vta13_un_contenido_fuera_del_esquema_se_rechaza_como_invalido(
    entorno: Entorno, contenido: dict[str, Any]
) -> None:
    antes = _datos(entorno.sesion, entorno.org)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(CONFIGURAR, contenido)

    assert _datos(entorno.sesion, entorno.org) == antes
    assert _auditorias(entorno.sesion, entorno.org) == []


def test_seg06_sin_admin_configuracion_se_rechaza_y_no_cambia_nada(db_session: Session) -> None:
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_CREDITO"}))
    antes = _datos(entorno.sesion, entorno.org)

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(CONFIGURAR, _contenido("Otro", "30712345678"))

    assert _datos(entorno.sesion, entorno.org) == antes
    assert _auditorias(entorno.sesion, entorno.org) == []


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
        contenido=_contenido("Por lote", "30712345678"),  # type: ignore[arg-type]
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
    entorno = _entorno_sembrado(db_session, frozenset({"GESTIONAR_CREDITO"}))
    antes = _datos(entorno.sesion, entorno.org)

    resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert _datos(entorno.sesion, entorno.org) == antes


def test_adr056_por_el_lote_con_el_permiso_en_online_se_acepta(entorno: Entorno) -> None:
    resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

    assert resultado.estado == "ACEPTADO"
    assert _datos(entorno.sesion, entorno.org) == ("Por lote", "30712345678")


def test_organizacion_datos_configurar_en_modo_offline_se_rechaza(entorno: Entorno) -> None:
    antes = _datos(entorno.sesion, entorno.org)

    resultado = _lote(entorno, _item_de_lote(entorno, modo="OFFLINE"))

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert _datos(entorno.sesion, entorno.org) == antes


def test_inv06_el_reenvio_devuelve_el_resultado_original_sin_otra_auditoria(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    contenido = _contenido("Una vez", "30712345678")

    primero = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(CONFIGURAR, contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_auditorias(entorno.sesion, entorno.org)) == 1


def test_inv21_el_cambio_usa_el_reloj_inyectado_y_no_toca_otra_organizacion(
    db_session: Session,
) -> None:
    propia = _entorno_sembrado(db_session)
    ajena = _entorno_sembrado(db_session)
    ajena_antes = _datos(ajena.sesion, ajena.org)

    propia.enviar(CONFIGURAR, _contenido("Propia", "30712345678"))

    assert _datos(propia.sesion, propia.org) == ("Propia", "30712345678")
    assert _datos(ajena.sesion, ajena.org) == ajena_antes
    assert _auditorias(ajena.sesion, ajena.org) == []
    actualizado_en = propia.sesion.execute(
        text("SELECT actualizado_en FROM organizacion WHERE id = :o"), {"o": propia.org}
    ).scalar_one()
    assert actualizado_en == MOMENTO


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


def test_vta13_http_lectura_y_cambio_del_administrador(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)
    nombre_inicial, cuit_inicial = _datos(sesion, http.org)

    inicial = cliente.get(URL, headers=headers)
    cambio = cliente.post(
        URL,
        json=_contenido("  Distribuidora Norte ", "30-71234567-8"),
        headers=con_operation_id(headers),
    )
    final = cliente.get(URL, headers=headers)

    assert inicial.status_code == 200
    assert inicial.json() == {"nombre": nombre_inicial, "cuit": cuit_inicial}
    esperado = {"nombre": "Distribuidora Norte", "cuit": "30712345678"}
    assert cambio.status_code == 200
    assert cambio.json() == esperado
    assert final.json() == esperado
    assert len(_auditorias(sesion, http.org)) == 1


def test_inv06_http_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))

    primera = cliente.post(URL, json=_contenido("Una", "30712345678"), headers=headers)
    segunda = cliente.post(URL, json=_contenido("Una", "30712345678"), headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(_auditorias(sesion, http.org)) == 1


def test_inv06_http_el_mismo_operation_id_con_otro_contenido_es_conflicto(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))

    primera = cliente.post(URL, json=_contenido("Primero"), headers=headers)
    segunda = cliente.post(URL, json=_contenido("Segundo"), headers=headers)

    assert primera.status_code == 200
    assert segunda.status_code == 409
    assert _datos(sesion, http.org)[0] == "Primero"


def test_seg06_http_sin_admin_configuracion_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=frozenset({"VENDER"}))
    headers = http.entrar(cliente)
    antes = _datos(sesion, http.org)

    lectura = cliente.get(URL, headers=headers)
    escritura = cliente.post(URL, json=_contenido("Otro"), headers=con_operation_id(headers))

    assert lectura.status_code == escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _datos(sesion, http.org) == antes
    assert _auditorias(sesion, http.org) == []


def test_sin_token_la_lectura_y_la_escritura_responden_401(cliente: TestClient) -> None:
    assert cliente.get(URL).status_code == 401
    assert cliente.post(URL, json=_contenido()).status_code == 401


@pytest.mark.parametrize(
    ("cuerpo", "codigo"),
    [
        (_contenido("Nombre", "3071234567"), "CUIT_INVALIDO"),
        (_contenido("Nombre", "30.71234567.8"), "CUIT_INVALIDO"),
        (_contenido("   ", "30712345678"), "NOMBRE_DE_ORGANIZACION_INVALIDO"),
        (_contenido("n" * 201, None), "NOMBRE_DE_ORGANIZACION_INVALIDO"),
    ],
    ids=["cuit_diez", "cuit_puntos", "nombre_vacio", "nombre_201"],
)
def test_vta13_http_un_dato_invalido_responde_422_con_su_codigo_sin_guardar_nada(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any], codigo: str
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)
    antes = _datos(sesion, http.org)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == codigo
    assert _datos(sesion, http.org) == antes
    assert _auditorias(sesion, http.org) == []


@pytest.mark.parametrize(
    "cuerpo",
    [{"cuit": None}, {"nombre": "X"}, {"nombre": 5, "cuit": None}],
    ids=["sin_nombre", "sin_cuit", "nombre_numero"],
)
def test_vta13_http_un_cuerpo_invalido_responde_422(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)
    antes = _datos(sesion, http.org)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert _datos(sesion, http.org) == antes


def test_sin_operation_id_la_escritura_responde_400(cliente: TestClient, sesion: Session) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)

    respuesta = cliente.post(URL, json=_contenido(), headers=http.entrar(cliente))

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    propia = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ua")
    ajena = EntornoHttp(sesion, permisos=ADMINISTRADOR, usuario="ub")
    headers_propia = propia.entrar(cliente)
    headers_ajena = ajena.entrar(cliente)
    ajena_antes = _datos(sesion, ajena.org)

    respuesta = cliente.post(
        URL,
        json={**_contenido("Propia", "30712345678"), "organizacion_id": str(ajena.org)},
        headers=con_operation_id(headers_propia),
    )

    assert respuesta.status_code == 200
    assert _datos(sesion, propia.org) == ("Propia", "30712345678")
    assert _datos(sesion, ajena.org) == ajena_antes
    assert cliente.get(URL, headers=headers_ajena).json() == {
        "nombre": ajena_antes[0],
        "cuit": ajena_antes[1],
    }
