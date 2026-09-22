"""Prueba de concurrencia de la reserva de idempotencia (change 04, grupo
5, tarea 5.6, INV-06, `design.md` Risks: "PostgreSQL bloquea el `INSERT`
hasta que la otra transacción termina").

Dos hilos, cada uno con su propia conexión/sesión (simulando dos workers
distintos, `02` §16.2), envían el MISMO `operation_id` con el MISMO
contenido al mismo tiempo, cada uno confirmando su propia transacción
(nunca `db_session`, que revierte al final -- mismo criterio que
`test_rate_limit_login_concurrencia.py`). La garantía la da la restricción
`UNIQUE (organizacion_id, operation_id)`: el segundo `INSERT ... ON
CONFLICT` se bloquea en la base hasta que el primero confirma, y solo
entonces se resuelve como choque real -- así la operación queda registrada
una sola vez y ambas respuestas informan el mismo resultado (INV-06,
SYN-02)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones --
    simula un worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


def _preparar_organizacion_usuario_dispositivo(database_url: str) -> tuple[UUID, UUID, UUID]:
    sesion = _sesion_independiente(database_url)
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba INV-06 concurrencia",
        slug=f"org-inv06-concurrencia-{uuid4().hex[:8]}",
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
        usuario="vendedor-concurrencia",
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
        prefijo="C01",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.commit()
    ids = (organizacion.id, usuario.id, dispositivo.id)
    sesion.close()
    return ids


def test_dos_envios_simultaneos_del_mismo_comando_producen_un_solo_efecto(
    database_url: str, _engine_de_sesion
) -> None:
    """Escenario "Dos envíos simultáneos del mismo comando producen un solo
    efecto" (INV-06, SYN-02): dos hilos, cada uno confirmando su propia
    transacción, envían el mismo `operation_id` con el mismo contenido al
    mismo tiempo."""
    organizacion_id, usuario_id, dispositivo_id = _preparar_organizacion_usuario_dispositivo(
        database_url
    )
    operation_id = uuid4()
    huella = "huella-concurrencia-1"

    resultados: dict[int, str] = {}
    errores: dict[int, BaseException] = {}

    def _handler_ganador(indice_hilo: int) -> tuple[str, dict[str, object] | None, str | None]:
        # Simula el trabajo del handler antes de persistir el resultado --
        # agranda la ventana en la que el segundo hilo puede chocar contra
        # una fila todavía sin confirmar.
        return "ACEPTADO", {"procesado_por_hilo": indice_hilo}, None

    def _worker(indice_hilo: int) -> None:
        sesion = _sesion_independiente(database_url)
        try:
            sobre = SobreComando(
                operation_id=operation_id,
                tipo="USUARIO_CREAR",
                version=1,
                modo="ONLINE",
                organizacion_id=organizacion_id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                occurred_at=MOMENTO,
                secuencia=1,
                app_version="1.0.0",
                contenido={},
            )
            comando = sync_service.procesar_idempotente(
                sesion,
                FixedClock(MOMENTO),
                sobre=sobre,
                huella=huella,
                ejecutar_handler=lambda: _handler_ganador(indice_hilo),
            )
            sesion.commit()
            resultados[indice_hilo] = comando.resultado["procesado_por_hilo"]  # type: ignore[index]
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            errores[indice_hilo] = error
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert not errores, f"Ningún hilo debía fallar: {errores}"
    assert len(resultados) == 2
    # Las dos respuestas informan el MISMO resultado: el hilo que ganó la
    # reserva es el único cuyo `procesado_por_hilo` quedó persistido, y el
    # otro leyó exactamente ese mismo valor -- nunca el propio.
    valores_informados = set(resultados.values())
    assert len(valores_informados) == 1

    sesion_verificacion = _sesion_independiente(database_url)
    try:
        total_filas = sesion_verificacion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
    finally:
        sesion_verificacion.close()
    assert total_filas == 1
