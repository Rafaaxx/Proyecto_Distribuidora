"""Change 22c, tarea 1.1 (spec `sync/bootstrap`, requisito "El bootstrap informa la secuencia
procesada de la jornada"; `design.md` D1): `GET /api/v1/sync/bootstrap` con PostgreSQL real y
comandos reales de venta sin conexión procesados por `procesar_lote`.

`sesion.secuencia_procesada` es la mayor secuencia de los comandos registrados de la jornada del
bootstrap, del usuario y del dispositivo de la sesión; nula si no hay ninguno. No mira otra
jornada, otro dispositivo ni otra organización. Un lote cortado por un error transitorio no
registra el comando cortado; un doble envío no cambia la marca ni duplica el stock.

Reglas citadas: SYN-11, SYN-03, CRE-08, RUT-04, INV-06, INV-21, `02` §6.4.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql
from test_sync_bootstrap import (  # noqa: F401  (fixtures y ayudas reutilizadas)
    Escenario,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from test_ventas_offline import Ruta, lote
from ventas_confirmar_utiles import MOMENTO_VENTA, RELOJ_VENTA

from app.commands import registro
from app.commands.sobre import SobreComando
from app.modules.sync import repository as sync_repository
from app.modules.sync import service as sync_service


class _TransitorioSimulado(Exception):
    """Un `DBAPIError` con `sqlstate` de serialización (`02` §6.3): `es_error_transitorio` solo
    mira ese atributo."""

    class _Orig:
        sqlstate = "40001"

    def __init__(self) -> None:
        super().__init__("transitorio simulado")
        self.orig = self._Orig()


class Telefono:
    """El vendedor de la organización con su teléfono (el dispositivo del entorno) y la camioneta
    con 48 botellas, que inicia sesión con ese mismo dispositivo."""

    def __init__(self, cliente_http: TestClient, sesion: Session) -> None:
        self.escenario = Escenario(sesion)
        self.entorno = self.escenario.entorno
        self.escenario.dispositivo_id = self.entorno.dispositivo_id
        self.ruta = Ruta(self.entorno)
        self.headers = self.escenario.entrar(cliente_http)
        self.cliente_http = cliente_http

    def vender(self, *secuencias: int) -> None:
        lote(self.entorno, *(self.ruta.item(secuencia=s) for s in secuencias))

    def _bootstrap(self) -> dict[str, object]:
        return self.escenario.pedir(self.cliente_http, self.headers)

    def marca(self) -> int | None:
        sesion_json = self._bootstrap()["sesion"]
        assert isinstance(sesion_json, dict)
        valor = sesion_json["secuencia_procesada"]
        assert valor is None or isinstance(valor, int)
        return valor

    def stock_del_bootstrap(self) -> int:
        filas = self._bootstrap()["stock"]
        assert isinstance(filas, list)
        (fila,) = [f for f in filas if f["producto_id"] == str(self.entorno.vino_id)]
        return int(fila["cantidad_base"])


@pytest.fixture
def telefono(cliente_http: TestClient, sesion: Session) -> Telefono:
    return Telefono(cliente_http, sesion)


def _reservar(
    sesion: Session,
    *,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    jornada_id: UUID,
    secuencia: int,
) -> None:
    """Un comando registrado ajeno a la jornada del teléfono (el filtro es del servidor, no del
    tipo de comando)."""
    sync_repository.reservar_comando(
        sesion,
        comando_id=uuid4(),
        organizacion_id=organizacion_id,
        operation_id=uuid4(),
        tipo="VENTA_CONFIRMAR",
        version=1,
        modo="OFFLINE",
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        huella="h" * 64,
        app_version="1.0.0",
        occurred_at=MOMENTO_VENTA,
        registered_at=MOMENTO_VENTA,
        secuencia=secuencia,
        jornada_id=jornada_id,
    )
    sesion.commit()


def test_syn11_la_marca_es_la_mayor_secuencia_de_la_jornada(telefono: Telefono) -> None:
    """Escenario "Ventas ya procesadas": 5, 6 y 7 registradas; el stock del bootstrap ya las
    incluye (48 - 3 x 15 = 3)."""
    telefono.vender(5, 6, 7)

    assert telefono.marca() == 7
    assert telefono.stock_del_bootstrap() == 3


def test_syn11_la_marca_no_depende_del_orden_de_llegada(telefono: Telefono) -> None:
    """Triangulación: la 7 llega antes que la 5 y la 6; la marca es 7."""
    telefono.vender(7)
    telefono.vender(5, 6)

    assert telefono.marca() == 7


def test_syn11_sin_comandos_la_marca_es_nula(telefono: Telefono) -> None:
    """Escenario "Jornada sin comandos"."""
    assert telefono.marca() is None


def test_syn03_un_lote_cortado_en_la_9_deja_la_marca_en_8(
    telefono: Telefono, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Lote cortado por un error transitorio": 8, 9 y 10; la 9 falla con un transitorio
    (el lote se corta y su reserva se revierte); la marca es 8 y el reenvío la lleva a 10."""
    original = registro.resolver_handler("VENTA_CONFIRMAR", 1)

    def _falla_en_la_9(
        sobre: SobreComando, contenido: object, *, sesion: object, reloj: object
    ) -> object:
        if sobre.secuencia == 9:
            raise _TransitorioSimulado()
        return original.funcion(sobre, contenido, sesion=sesion, reloj=reloj)  # type: ignore[arg-type]

    monkeypatch.setitem(
        registro._REGISTRO, ("VENTA_CONFIRMAR", 1), replace(original, funcion=_falla_en_la_9)
    )
    items = [telefono.ruta.item(secuencia=s) for s in (8, 9, 10)]

    resultados = sync_service.procesar_lote(
        telefono.entorno.sesion,
        RELOJ_VENTA,
        organizacion_id=telefono.entorno.org,
        usuario_id=telefono.entorno.usuario_id,
        dispositivo_id=telefono.entorno.dispositivo_id,
        items=items,
        config=sync_service.ConfiguracionReintentos(intentos_maximos=1),
    )

    assert [r.estado for r in resultados] == ["ACEPTADO", "ERROR_TRANSITORIO"]
    assert telefono.marca() == 8
    monkeypatch.setitem(registro._REGISTRO, ("VENTA_CONFIRMAR", 1), original)
    lote(telefono.entorno, *items)
    assert telefono.marca() == 10


def test_inv21_no_mira_otra_jornada_ni_otro_dispositivo(telefono: Telefono) -> None:
    """Escenario "Comandos de otra jornada o de otro teléfono": 20 de una jornada anterior del
    mismo usuario y dispositivo, y 30 de otro usuario y otro dispositivo: la marca sigue nula."""
    entorno = telefono.entorno
    anterior = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=telefono.ruta.camioneta_id,
        estado="CERRADA",
    )
    ajena = entorno.crear_otro_usuario_con_jornada()
    otro_usuario, otro_dispositivo = entorno.sesion.execute(
        text("SELECT usuario_id, dispositivo_id FROM jornada WHERE id = :j"), {"j": ajena}
    ).one()
    entorno.sesion.commit()
    _reservar(
        entorno.sesion,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        jornada_id=anterior,
        secuencia=20,
    )
    _reservar(
        entorno.sesion,
        organizacion_id=entorno.org,
        usuario_id=otro_usuario,
        dispositivo_id=otro_dispositivo,
        jornada_id=ajena,
        secuencia=30,
    )

    assert telefono.marca() is None


def test_inv21_no_mira_otra_organizacion(telefono: Telefono, sesion: Session) -> None:
    """Triangulación: un comando de secuencia 40 de otra organización no mueve la marca."""
    otra = Escenario(sesion)
    lote(otra.entorno, Ruta(otra.entorno).item(secuencia=40))

    assert telefono.marca() is None


def test_inv06_un_doble_envio_deja_la_marca_en_7_y_el_stock_una_vez(telefono: Telefono) -> None:
    """Escenario "Doble envío antes del bootstrap": la venta 7 enviada dos veces."""
    item = telefono.ruta.item(secuencia=7)
    lote(telefono.entorno, item)
    lote(telefono.entorno, item)

    assert telefono.marca() == 7
    assert telefono.stock_del_bootstrap() == 33
