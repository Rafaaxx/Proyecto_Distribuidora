"""Change 21, tarea 3.1 (`design.md` D3; spec `sync/bootstrap`, requisito "El bootstrap es una foto
coherente de la organización"): mientras un bootstrap está leyendo, otra sesión confirma una venta
desde la camioneta; el bootstrap trae saldo y stock AMBOS anteriores o AMBOS posteriores.

Concurrencia real contra PostgreSQL real (Testcontainers, `READ COMMITTED` para el resto del
sistema, `02` §7.1): cada hilo tiene su propia conexión y confirma su propia transacción; nunca hay
rollback externo (`CLAUDE.md` §4). La pausa entre secciones la inyecta el gancho
`entre_secciones` de `generar_bootstrap` con dos `threading.Event`, sin `sleep`.

Sin la transacción `REPEATABLE READ READ ONLY` esta prueba falla de forma determinista: con la
pausa antes del stock, el saldo ya se leyó (anterior a la venta) y el stock se lee después
(posterior). Reglas citadas: INV-12, INV-13.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import RELOJ_VENTA

from app.core.db import crear_engine
from app.modules.sync.bootstrap import generar_bootstrap
from app.modules.sync.schemas import BootstrapResponse
from tests.concurrency.test_pagos_proveedor_concurrencia import _sesion_independiente
from tests.concurrency.test_ventas_concurrencia import _Escenario
from tests.integration.stock_utiles import crear_jornada_sql

SALDO_ANTES, SALDO_DESPUES = Decimal("150000.00"), Decimal("181250.00")
STOCK_ANTES, STOCK_DESPUES = 48, 33  # 15 botellas de la venta de `EntornoVenta.contenido()`
ESPERA = 60


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str, _engine_de_sesion: object) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _con_jornada_abierta(database_url: str) -> _Escenario:
    escenario = _Escenario(database_url)
    sesion = _sesion_independiente(database_url)
    try:
        crear_jornada_sql(
            sesion,
            escenario.org,
            usuario_id=escenario.entorno.usuario_id,
            dispositivo_id=escenario.entorno.dispositivo_id,
            ubicacion_id=escenario.entorno.deposito_id,
        )
        sesion.commit()
    finally:
        sesion.close()
    return escenario


def _saldo_y_stock(respuesta: BootstrapResponse, cliente_id: UUID) -> tuple[Decimal, int]:
    saldo = next(Decimal(c.saldo) for c in respuesta.clientes if c.id == cliente_id)
    (stock,) = respuesta.stock
    return saldo, stock.cantidad_base


def _bootstrap_con_venta_en_medio(
    database_url: str, escenario: _Escenario, pausar_antes_de: str
) -> BootstrapResponse:
    """Corre el bootstrap en un hilo; al llegar a `pausar_antes_de` lo detiene, confirma una venta
    desde otra sesión y lo deja seguir."""
    e = escenario.entorno
    pausado, continuar = threading.Event(), threading.Event()
    resultado: dict[str, Any] = {}

    def _gancho(seccion: str) -> None:
        if seccion == pausar_antes_de:
            pausado.set()
            assert continuar.wait(ESPERA), "el hilo del bootstrap no fue liberado"

    def _leer() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            resultado["respuesta"] = generar_bootstrap(
                sesion,
                RELOJ_VENTA,
                organizacion_id=escenario.org,
                usuario_id=e.usuario_id,
                dispositivo_id=e.dispositivo_id,
                entre_secciones=_gancho,
            )
        except BaseException as error:  # se relanza en el hilo principal
            resultado["error"] = error
        finally:
            sesion.close()

    hilo = threading.Thread(target=_leer)
    hilo.start()
    try:
        assert pausado.wait(ESPERA), "el bootstrap no llegó a la sección de la pausa"
        sesion_venta: Session = _sesion_independiente(database_url)
        try:
            escenario.enviar(sesion_venta, e.contenido())  # el bus confirma (commit real)
        finally:
            sesion_venta.close()
    finally:
        continuar.set()
        hilo.join(ESPERA)
    if "error" in resultado:
        raise resultado["error"]
    return resultado["respuesta"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("pausar_antes_de", ["stock", "clientes", "autorizadores"])
def test_inv12_inv13_la_venta_confirmada_en_medio_no_mezcla_saldo_y_stock(
    database_url: str, pausar_antes_de: str
) -> None:
    """La pausa cae DESPUÉS de leer la jornada (la primera lectura fija la foto): la venta que se
    confirma en medio no se ve ni en el saldo (se lee en `clientes`) ni en el stock."""
    escenario = _con_jornada_abierta(database_url)

    respuesta = _bootstrap_con_venta_en_medio(database_url, escenario, pausar_antes_de)

    assert _saldo_y_stock(respuesta, escenario.entorno.cliente_id) == (SALDO_ANTES, STOCK_ANTES)


def test_inv12_inv13_un_bootstrap_posterior_ve_los_dos_valores_nuevos(database_url: str) -> None:
    """Contraste: confirmada la venta, un bootstrap nuevo trae saldo Y stock posteriores."""
    escenario = _con_jornada_abierta(database_url)
    e = escenario.entorno
    sesion = _sesion_independiente(database_url)
    try:
        escenario.enviar(sesion, e.contenido())
    finally:
        sesion.close()
    sesion = _sesion_independiente(database_url)
    try:
        respuesta = generar_bootstrap(
            sesion,
            RELOJ_VENTA,
            organizacion_id=escenario.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
        )
    finally:
        sesion.close()

    assert _saldo_y_stock(respuesta, e.cliente_id) == (SALDO_DESPUES, STOCK_DESPUES)


def test_inv12_inv13_con_la_pausa_antes_de_la_primera_lectura_ve_los_dos_nuevos(
    database_url: str,
) -> None:
    """Si la venta se confirma antes de que el bootstrap lea nada, la foto es la posterior entera
    (saldo y stock juntos)."""
    escenario = _con_jornada_abierta(database_url)

    respuesta = _bootstrap_con_venta_en_medio(database_url, escenario, "jornada")

    assert _saldo_y_stock(respuesta, escenario.entorno.cliente_id) == (
        SALDO_DESPUES,
        STOCK_DESPUES,
    )
