"""Prueba de concurrencia del reintento transitorio (change 04, grupo 6,
tarea 6.7, `docs/02-arquitectura.md` §6.3, INV-06): dos hilos, cada uno con
su propia conexión/sesión, provocan un fallo de serialización REAL de
PostgreSQL (SQLSTATE `40001`) leyendo y escribiendo la misma fila bajo
aislamiento `SERIALIZABLE`, y confirman que `sync_service.procesar_comando`
lo reintenta hasta que el comando termina con estado final y sus efectos
quedan registrados una sola vez.

`02` §7.1 fija `READ COMMITTED` como aislamiento por defecto del sistema,
donde dos `UPDATE` concurrentes sobre la misma fila se BLOQUEAN entre sí en
vez de abortar con `40001` (ese bloqueo es justamente el mecanismo de la
reserva de idempotencia, ya probado en
`test_inv06_reserva_idempotencia_concurrencia.py`). Para ejercer el OTRO
camino -- un aborto real por conflicto de serialización, que es lo que este
grupo reintenta -- esta prueba eleva el aislamiento de la transacción de
cada comando a `SERIALIZABLE` explícitamente (patrón estándar de
PostgreSQL para reproducir `40001` de forma determinística: ambas
transacciones leen la misma fila antes de que cualquiera escriba, con una
barrera que fuerza el solape). Esto es un detalle de la PRUEBA, no del
pipeline: `02` §7.1 sigue rigiendo el nivel de aislamiento real de la
aplicación."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_serializable(database_url: str) -> Session:
    """Conexión/sesión propia, con aislamiento `SERIALIZABLE` (ver docstring
    del módulo), que confirma sus propias transacciones -- simula un worker
    de FastAPI distinto (`02` §16.2)."""
    engine = crear_engine(database_url).execution_options(isolation_level="SERIALIZABLE")
    factory = crear_session_factory(engine)
    return factory()


def _preparar_organizacion_usuario_dispositivo(database_url: str) -> tuple[UUID, UUID, UUID]:
    factory = crear_session_factory(crear_engine(database_url))
    sesion = factory()
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba bus concurrencia",
        slug=f"org-bus-concurrencia-{uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    rol = identidad_repository.crear_rol(
        organizacion.id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion.id,
        sesion,
        usuario_id=nuevo_id(),
        usuario="vendedor-bus-concurrencia",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion.id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo="D01",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.commit()
    ids = (organizacion.id, usuario.id, dispositivo.id)
    sesion.close()
    return ids


def test_un_fallo_de_serializacion_se_reintenta_y_el_comando_termina_aceptado(
    database_url: str, _engine_de_sesion
) -> None:
    """Escenario "Un fallo de serialización se reintenta y el comando
    termina aceptado" (`02` §6.3, INV-06): dos hilos, cada uno con su propia
    transacción `SERIALIZABLE`, leen y después escriben la MISMA fila de
    `organizacion` -- PostgreSQL aborta a uno de los dos con `40001` en el
    momento del `COMMIT`, y `procesar_comando` lo reintenta."""
    organizacion_id, usuario_id, dispositivo_id = _preparar_organizacion_usuario_dispositivo(
        database_url
    )
    barrera = threading.Barrier(2)
    resultados: dict[int, str] = {}
    errores: dict[int, BaseException] = {}
    intentos_por_hilo: dict[int, int] = {0: 0, 1: 0}

    def _handler(indice_hilo: int, sesion: object) -> sync_service.ResultadoHandler:
        intentos_por_hilo[indice_hilo] += 1
        # Ambos hilos leen la fila ANTES de que cualquiera escriba (fuerza
        # el solape que produce el conflicto de serialización real). Solo en
        # el PRIMER intento de cada hilo: en un reintento, el otro hilo bien
        # puede haber terminado ya, y esperar de nuevo bloquearía para
        # siempre (la `Barrier` se reinicia automáticamente tras usarse,
        # pero necesita que ambas partes la usen la misma cantidad de veces).
        sesion.execute(  # type: ignore[attr-defined]
            select(Organizacion.nombre).where(Organizacion.id == organizacion_id)
        ).scalar_one()
        if intentos_por_hilo[indice_hilo] == 1:
            barrera.wait(timeout=10)
        sesion.execute(  # type: ignore[attr-defined]
            update(Organizacion)
            .where(Organizacion.id == organizacion_id)
            .values(nombre=f"actualizado-por-hilo-{indice_hilo}")
        )
        return "ACEPTADO", {"hilo": indice_hilo}, None

    def _worker(indice_hilo: int) -> None:
        sesion = _sesion_serializable(database_url)
        try:
            sobre = SobreComando(
                operation_id=uuid4(),
                tipo="USUARIO_CREAR",
                version=1,
                modo="ONLINE",
                organizacion_id=organizacion_id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                occurred_at=MOMENTO,
                secuencia=indice_hilo,
                app_version="1.0.0",
                contenido={},
            )
            comando = sync_service.procesar_comando(
                sesion,
                FixedClock(MOMENTO),
                sobre=sobre,
                huella=f"huella-hilo-{indice_hilo}",
                ejecutar_handler=lambda s, i=indice_hilo: _handler(i, s),
                config=sync_service.ConfiguracionReintentos(
                    intentos_maximos=5, espera_base_segundos=0.005, espera_techo_segundos=0.05
                ),
            )
            resultados[indice_hilo] = comando.estado
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            errores[indice_hilo] = error
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert not errores, f"Ningún hilo debía fallar tras los reintentos: {errores}"
    assert resultados == {0: "ACEPTADO", 1: "ACEPTADO"}
    # Sanidad de que la prueba ejerció de verdad el camino de reintento: al
    # menos uno de los dos hilos necesitó más de un intento (el que
    # PostgreSQL abortó con 40001 en su primer `commit`).
    assert max(intentos_por_hilo.values()) > 1, (
        f"Ningún hilo reintentó: la prueba no ejerció un conflicto de serialización real "
        f"(intentos={intentos_por_hilo})."
    )

    sesion_verificacion = _sesion_serializable(database_url)
    try:
        nombre_final = sesion_verificacion.execute(
            select(Organizacion.nombre).where(Organizacion.id == organizacion_id)
        ).scalar_one()
    finally:
        sesion_verificacion.close()
    # El valor final es el de UNO solo de los dos hilos -- nunca una mezcla
    # ni el valor original -- confirmando que los efectos quedaron
    # registrados una sola vez, de forma consistente.
    assert nombre_final in {"actualizado-por-hilo-0", "actualizado-por-hilo-1"}
