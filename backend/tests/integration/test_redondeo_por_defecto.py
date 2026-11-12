"""Tareas 5.2 y 5.3 (change 20c; `design.md` D10, D11, D13; specs
`organizacion/parametros-de-organizacion` y `sistema/pipeline-de-comandos`):
`REDONDEO_POR_DEFECTO_DEFINIR` v1 por el bus y por HTTP (`POST` y `GET
/api/v1/configuracion/redondeo-por-defecto`), contra PostgreSQL real.

Reglas citadas: PRC-01, PRC-14, AUD-01, SEG-06, ADR-056, INV-03, INV-06, INV-21 y ADR-061.
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
    con_operation_id,
)
from fastapi.testclient import TestClient
from precios_utiles import MOMENTO, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import PermisoRequeridoError
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad.domain.valores import RedondeoDireccionInvalidaError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

DEFINIR = "REDONDEO_POR_DEFECTO_DEFINIR"
URL = "/api/v1/configuracion/redondeo-por-defecto"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION"})
LISTAS = frozenset({"GESTIONAR_LISTAS"})


def _contenido(multiplo: str | None = "500.00", direccion: str | None = "ABAJO") -> dict[str, Any]:
    return {"multiplo": multiplo, "direccion": direccion}


# --- por el bus -------------------------------------------------------------------------


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    # Se confirma: un rechazo del bus revierte la transacción y se llevaría el entorno.
    nuevo = Entorno(db_session, permisos=ADMINISTRADOR | LISTAS)
    db_session.commit()
    return nuevo


def _estado(entorno: Entorno) -> tuple[Decimal | None, str | None]:
    entorno.sesion.expire_all()
    fila = entorno.sesion.execute(
        text(
            "SELECT redondeo_multiplo, redondeo_direccion FROM configuracion_organizacion "
            "WHERE organizacion_id = :o"
        ),
        {"o": entorno.org},
    ).one()
    return fila.redondeo_multiplo, fila.redondeo_direccion


def _auditorias(entorno: Entorno) -> list[Any]:
    return list(
        entorno.sesion.execute(
            text(
                "SELECT antes, despues, usuario_id, operation_id, origen FROM auditoria "
                "WHERE organizacion_id = :o AND accion = :a "
                "AND entidad = 'configuracion_organizacion' ORDER BY id"
            ),
            {"o": entorno.org, "a": DEFINIR},
        ).all()
    )


@pytest.mark.usefixtures("_engine_de_sesion")
class TestPorElBus:
    def test_prc01_definir_guarda_los_dos_valores_y_devuelve_el_estado(
        self, entorno: Entorno
    ) -> None:
        comando = entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        assert comando.estado == "ACEPTADO"
        assert comando.resultado == {"multiplo": "500.00", "direccion": "ABAJO"}
        assert _estado(entorno) == (Decimal("500.00"), "ABAJO")

    def test_prc01_un_segundo_valor_reemplaza_al_primero(self, entorno: Entorno) -> None:
        entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))
        comando = entorno.enviar(DEFINIR, _contenido("0.50", "CERCANO"))

        assert comando.resultado == {"multiplo": "0.50", "direccion": "CERCANO"}
        assert _estado(entorno) == (Decimal("0.50"), "CERCANO")

    def test_prc01_quitar_con_los_dos_nulos_vuelve_a_sin_definir(self, entorno: Entorno) -> None:
        entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        comando = entorno.enviar(DEFINIR, _contenido(None, None))

        assert comando.estado == "ACEPTADO"
        assert comando.resultado == {"multiplo": None, "direccion": None}
        assert _estado(entorno) == (None, None)

    @pytest.mark.parametrize(
        ("multiplo", "direccion"),
        [
            ("0.00", "ARRIBA"),
            ("10.005", "ARRIBA"),
            ("-1", "ARRIBA"),
            ("100.00", "MEDIO"),
            ("100.00", None),
            (None, "ARRIBA"),
        ],
    )
    def test_prc14_los_valores_invalidos_se_rechazan_y_no_cambian_nada(
        self, entorno: Entorno, multiplo: str | None, direccion: str | None
    ) -> None:
        entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        with pytest.raises(RedondeoDireccionInvalidaError) as error:
            entorno.enviar(DEFINIR, _contenido(multiplo, direccion))

        assert error.value.codigo == "REDONDEO_INVALIDO"
        assert _estado(entorno) == (Decimal("500.00"), "ABAJO")
        assert len(_auditorias(entorno)) == 1

    def test_prc01_una_lista_existente_y_su_version_vigente_no_cambian(
        self, entorno: Entorno
    ) -> None:
        # D10: el redondeo por defecto solo precarga el formulario; no toca listas ni precios.
        lista_id = entorno.crear_lista("General", multiplo="100.00", direccion="ARRIBA")
        antes = entorno.sesion.execute(
            text(
                "SELECT redondeo_multiplo, redondeo_direccion, actualizado_en FROM lista_precio "
                "WHERE id = :l"
            ),
            {"l": lista_id},
        ).one()

        entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        entorno.sesion.expire_all()
        despues = entorno.sesion.execute(
            text(
                "SELECT redondeo_multiplo, redondeo_direccion, actualizado_en FROM lista_precio "
                "WHERE id = :l"
            ),
            {"l": lista_id},
        ).one()
        assert tuple(despues) == tuple(antes)
        assert (despues.redondeo_multiplo, despues.redondeo_direccion) == (
            Decimal("100.00"),
            "ARRIBA",
        )

    def test_seg06_sin_admin_configuracion_recibe_permiso_requerido_sin_efectos(
        self, entorno: Entorno
    ) -> None:
        entorno.actuar_con_permisos(LISTAS)

        with pytest.raises(PermisoRequeridoError):
            entorno.enviar(DEFINIR, _contenido())

        assert _estado(entorno) == (None, None)
        assert _auditorias(entorno) == []

    def test_inv06_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo_sin_otra_auditoria(
        self, entorno: Entorno
    ) -> None:
        operation_id = uuid4()

        primero = entorno.enviar(DEFINIR, _contenido(), operation_id=operation_id)
        segundo = entorno.enviar(DEFINIR, _contenido(), operation_id=operation_id)

        assert segundo.resultado == primero.resultado
        assert len(_auditorias(entorno)) == 1

    def test_aud01_la_auditoria_guarda_antes_y_despues_con_el_actor_y_el_operation_id(
        self, entorno: Entorno
    ) -> None:
        entorno.enviar(DEFINIR, _contenido("100.00", "ARRIBA"))
        comando = entorno.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        primera, segunda = _auditorias(entorno)
        assert primera.antes == {"redondeo_multiplo": None, "redondeo_direccion": None}
        assert primera.despues == {"redondeo_multiplo": "100.00", "redondeo_direccion": "ARRIBA"}
        assert segunda.antes == {"redondeo_multiplo": "100.00", "redondeo_direccion": "ARRIBA"}
        assert segunda.despues == {"redondeo_multiplo": "500.00", "redondeo_direccion": "ABAJO"}
        assert segunda.usuario_id == entorno.usuario_id
        assert segunda.operation_id == comando.operation_id
        assert segunda.origen == "COMANDO"

    def test_inv21_define_solo_la_organizacion_del_sobre(self, db_session: Session) -> None:
        propia = Entorno(db_session, permisos=ADMINISTRADOR)
        ajena = Entorno(db_session, permisos=ADMINISTRADOR)
        db_session.commit()

        propia.enviar(DEFINIR, _contenido("500.00", "ABAJO"))

        assert _estado(propia) == (Decimal("500.00"), "ABAJO")
        assert _estado(ajena) == (None, None)


def _item_de_lote(entorno: Entorno, *, modo: str) -> ItemLote:
    return ItemLote(
        operation_id=uuid4(),
        tipo=DEFINIR,
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=_contenido(),  # type: ignore[arg-type]
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


@pytest.mark.usefixtures("_engine_de_sesion")
class TestPorElLote:
    def test_adr056_en_modo_online_se_comporta_igual_que_por_rest(self, entorno: Entorno) -> None:
        resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

        assert resultado.estado == "ACEPTADO"
        assert _estado(entorno) == (Decimal("500.00"), "ABAJO")

    def test_adr056_sin_admin_configuracion_responde_permiso_requerido(
        self, entorno: Entorno
    ) -> None:
        entorno.actuar_con_permisos(LISTAS)

        resultado = _lote(entorno, _item_de_lote(entorno, modo="ONLINE"))

        assert resultado.estado == "RECHAZADO"
        assert resultado.error_codigo == "PERMISO_REQUERIDO"
        assert _estado(entorno) == (None, None)

    def test_02_6_5_en_modo_offline_se_rechaza_como_tipo_sin_ese_modo(
        self, entorno: Entorno
    ) -> None:
        resultado = _lote(entorno, _item_de_lote(entorno, modo="OFFLINE"))

        assert resultado.estado == "RECHAZADO"
        assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
        assert _estado(entorno) == (None, None)

    def test_el_tipo_esta_declarado_solo_online(self) -> None:
        from app.commands.catalogo import tipo_declarado

        declarado = tipo_declarado(DEFINIR)

        assert declarado is not None
        assert (declarado.admite_online, declarado.admite_offline) == (True, False)
        assert declarado.permisos == ("ADMIN_CONFIGURACION",)


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


def test_prc01_http_sin_definir_la_lectura_devuelve_los_dos_nulos(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)

    respuesta = cliente.get(URL, headers=http.entrar(cliente))

    assert respuesta.status_code == 200
    assert respuesta.json() == {"multiplo": None, "direccion": None}


def test_prc01_http_definir_y_leer_devuelven_el_multiplo_como_string(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    cambio = cliente.post(URL, json=_contenido("500", "ABAJO"), headers=con_operation_id(headers))
    lectura = cliente.get(URL, headers=headers)

    assert cambio.status_code == 200, cambio.text
    assert cambio.json() == {"multiplo": "500.00", "direccion": "ABAJO"}
    assert lectura.json() == {"multiplo": "500.00", "direccion": "ABAJO"}
    assert len(http.auditorias(DEFINIR)) == 1


def test_prc01_http_quitar_vuelve_a_sin_definir(cliente: TestClient, sesion: Session) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)
    cliente.post(URL, json=_contenido(), headers=con_operation_id(headers))

    quitar = cliente.post(URL, json=_contenido(None, None), headers=con_operation_id(headers))

    assert quitar.status_code == 200
    assert quitar.json() == {"multiplo": None, "direccion": None}
    assert cliente.get(URL, headers=headers).json() == {"multiplo": None, "direccion": None}


def test_d11_http_administracion_con_gestionar_listas_puede_leerlo_pero_no_definirlo(
    cliente: TestClient, sesion: Session
) -> None:
    gestor = EntornoHttp(sesion, permisos=LISTAS, usuario="gestor1")
    sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET redondeo_multiplo = 250, "
            "redondeo_direccion = 'CERCANO' WHERE organizacion_id = :o"
        ),
        {"o": gestor.org},
    )
    headers_gestor = gestor.entrar(cliente)

    lectura = cliente.get(URL, headers=headers_gestor)
    escritura = cliente.post(URL, json=_contenido(), headers=con_operation_id(headers_gestor))

    assert lectura.status_code == 200
    assert lectura.json() == {"multiplo": "250.00", "direccion": "CERCANO"}
    assert escritura.status_code == 403
    assert escritura.json()["codigo"] == "PERMISO_REQUERIDO"
    assert gestor.configuracion()["redondeo_multiplo"] == Decimal("250.00")


def test_seg06_http_un_vendedor_sin_ninguno_de_los_dos_permisos_recibe_403(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=frozenset({"VENDER"}))
    headers = http.entrar(cliente)

    lectura = cliente.get(URL, headers=headers)
    escritura = cliente.post(URL, json=_contenido(), headers=con_operation_id(headers))

    assert lectura.status_code == escritura.status_code == 403
    assert http.configuracion()["redondeo_multiplo"] is None
    assert http.auditorias(DEFINIR) == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"multiplo": "0.00", "direccion": "ARRIBA"},
        {"multiplo": "10.005", "direccion": "ARRIBA"},
        {"multiplo": "100.00", "direccion": "MEDIO"},
        {"multiplo": "100.00", "direccion": None},
        {"multiplo": None, "direccion": "ARRIBA"},
    ],
)
def test_prc14_http_un_redondeo_invalido_responde_422_redondeo_invalido(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "REDONDEO_INVALIDO"
    assert http.configuracion()["redondeo_multiplo"] is None
    assert http.auditorias(DEFINIR) == []


@pytest.mark.parametrize(
    "cuerpo",
    [{"multiplo": 500, "direccion": "ABAJO"}, {"direccion": "ABAJO"}, {}],
    ids=["numero_json", "sin_multiplo", "vacio"],
)
def test_inv03_http_un_multiplo_numerico_o_ausente_se_rechaza_con_422(
    cliente: TestClient, sesion: Session, cuerpo: dict[str, Any]
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = http.entrar(cliente)

    respuesta = cliente.post(URL, json=cuerpo, headers=con_operation_id(headers))

    assert respuesta.status_code == 422
    assert http.configuracion()["redondeo_multiplo"] is None


def test_inv06_http_el_reenvio_con_el_mismo_operation_id_deja_una_sola_auditoria(
    cliente: TestClient, sesion: Session
) -> None:
    http = EntornoHttp(sesion, permisos=ADMINISTRADOR)
    headers = con_operation_id(http.entrar(cliente))

    primera = cliente.post(URL, json=_contenido(), headers=headers)
    segunda = cliente.post(URL, json=_contenido(), headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(http.auditorias(DEFINIR)) == 1


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

    respuesta = cliente.post(
        URL,
        json={**_contenido(), "organizacion_id": str(ajena.org)},
        headers=con_operation_id(headers_propia),
    )

    assert respuesta.status_code == 200
    assert propia.configuracion()["redondeo_multiplo"] == Decimal("500.00")
    assert ajena.configuracion()["redondeo_multiplo"] is None
    assert cliente.get(URL, headers=headers_ajena).json() == {"multiplo": None, "direccion": None}
