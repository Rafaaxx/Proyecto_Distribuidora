"""Change 07, tarea 6.4: concurrencia real de `clientes` contra PostgreSQL
real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1),
mismo arnés que `test_proveedores_concurrencia.py`: dos hilos, cada uno con
su propia conexión/sesión que confirma su propia transacción.

`design.md` D1 exige que las dos unicidades (código, documento) se
sostengan en la base, no solo en el handler, porque dos requests
concurrentes pueden pasar la validación en Python y llegar juntas al
`INSERT`. Estas pruebas confirman las dos unicidades con commits reales:

- dos `CLIENTE_CREAR` con el mismo documento -> uno `ACEPTADO`, el otro
  `DOCUMENTO_DUPLICADO` (`ux_cliente_documento`).
- dos `CLIENTE_CREAR` con el mismo código -> uno `ACEPTADO`, el otro
  `CODIGO_DUPLICADO` (`ux_cliente_codigo`).

Spec `fichas-de-cliente`, escenario "Dos altas concurrentes con el mismo
documento" (`design.md` D1; INV-01)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import CodigoDuplicadoError, DocumentoDuplicadoError
from app.modules.clientes.models import Cliente
from app.modules.identidad.models import Organizacion

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


def _preparar_organizacion(database_url: str) -> UUID:
    sesion = _sesion_independiente(database_url)
    try:
        organizacion = Organizacion(
            id=nuevo_id(),
            nombre="Organización de prueba clientes concurrencia",
            slug=f"org-cli-concurrencia-{uuid4().hex[:8]}",
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
        sesion.commit()
        return organizacion.id
    finally:
        sesion.close()


def _crear_cliente_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "nombre": f"Kiosco {uuid4().hex[:8]}",
        "codigo": None,
        "razon_social": None,
        "documento_tipo": None,
        "documento_numero": None,
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "telefono": None,
        "email": None,
        "estado_facturacion_default": None,
        "actor_id": None,
    }
    base.update(overrides)
    return base


class TestDosAltasConcurrentesConElMismoDocumento:
    """Tarea 6.4: dos `CLIENTE_CREAR` simultáneos con el mismo documento ->
    uno `ACEPTADO`, el otro `DOCUMENTO_DUPLICADO` (`design.md` D1,
    `ux_cliente_documento`)."""

    def test_dos_altas_simultaneas_con_el_mismo_documento_una_aceptada_una_rechazada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)

        barrera = threading.Barrier(2)
        resultados: dict[int, str] = {}
        errores: dict[int, BaseException] = {}

        def _worker(indice_hilo: int) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                clientes_service.crear_cliente(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    **_crear_cliente_kwargs(
                        documento_tipo="DNI",
                        documento_numero="30111222",
                    ),
                )
                sesion.commit()
                resultados[indice_hilo] = "ACEPTADO"
            except DocumentoDuplicadoError as error:
                sesion.rollback()
                resultados[indice_hilo] = "DOCUMENTO_DUPLICADO"
                errores[indice_hilo] = error
            except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
                sesion.rollback()
                errores[indice_hilo] = error
                resultados[indice_hilo] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        assert not any(hilo.is_alive() for hilo in hilos), (
            "Un hilo quedó colgado (posible interbloqueo real)."
        )
        assert set(resultados.values()) == {"ACEPTADO", "DOCUMENTO_DUPLICADO"}, (
            f"Un hilo debía terminar ACEPTADO y el otro DOCUMENTO_DUPLICADO: "
            f"{resultados}, errores={errores}"
        )
        indice_duplicado = next(i for i, r in resultados.items() if r == "DOCUMENTO_DUPLICADO")
        assert isinstance(errores[indice_duplicado], DocumentoDuplicadoError)

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            cantidad = sesion_verificacion.scalar(
                select(func.count())
                .select_from(Cliente)
                .where(
                    Cliente.organizacion_id == organizacion_id,
                    Cliente.documento_numero == "30111222",
                )
            )
        finally:
            sesion_verificacion.close()
        # Exactamente un cliente con ese documento quedó persistido -- el
        # segundo hilo nunca llegó a escribir (INV-01).
        assert cantidad == 1


class TestDosAltasConcurrentesConElMismoCodigo:
    """Tarea 6.4: dos `CLIENTE_CREAR` simultáneos con el mismo código ->
    uno `ACEPTADO`, el otro `CODIGO_DUPLICADO` (`design.md` D1,
    `ux_cliente_codigo`)."""

    def test_dos_altas_simultaneas_con_el_mismo_codigo_una_aceptada_una_rechazada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        codigo_compartido = f"K-{uuid4().hex[:8]}"

        barrera = threading.Barrier(2)
        resultados: dict[int, str] = {}
        errores: dict[int, BaseException] = {}

        def _worker(indice_hilo: int) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                clientes_service.crear_cliente(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    **_crear_cliente_kwargs(codigo=codigo_compartido),
                )
                sesion.commit()
                resultados[indice_hilo] = "ACEPTADO"
            except CodigoDuplicadoError as error:
                sesion.rollback()
                resultados[indice_hilo] = "CODIGO_DUPLICADO"
                errores[indice_hilo] = error
            except BaseException as error:  # noqa: BLE001
                sesion.rollback()
                errores[indice_hilo] = error
                resultados[indice_hilo] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        assert not any(hilo.is_alive() for hilo in hilos), (
            "Un hilo quedó colgado (posible interbloqueo real)."
        )
        assert set(resultados.values()) == {"ACEPTADO", "CODIGO_DUPLICADO"}, (
            f"Un hilo debía terminar ACEPTADO y el otro CODIGO_DUPLICADO: "
            f"{resultados}, errores={errores}"
        )
        indice_duplicado = next(i for i, r in resultados.items() if r == "CODIGO_DUPLICADO")
        assert isinstance(errores[indice_duplicado], CodigoDuplicadoError)

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            cantidad = sesion_verificacion.scalar(
                select(func.count())
                .select_from(Cliente)
                .where(
                    Cliente.organizacion_id == organizacion_id,
                    Cliente.codigo == codigo_compartido,
                )
            )
        finally:
            sesion_verificacion.close()
        # Exactamente un cliente con ese código quedó persistido.
        assert cantidad == 1
