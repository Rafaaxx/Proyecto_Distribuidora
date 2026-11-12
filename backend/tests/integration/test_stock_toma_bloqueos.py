"""Change 15, tarea 8.4: orden de bloqueo entre la toma y los movimientos (`design.md` D9, `02`
§7.3; spec `stock/toma-de-ubicacion`, requisito "La toma y los movimientos concurrentes se
ordenan"). Dos sesiones reales con commits reales, y limpieza al final.

* La apertura toma la ubicación `FOR UPDATE`: un movimiento simultáneo (que la toma `FOR SHARE`)
  la espera y, cuando la apertura confirma, encuentra la ubicación tomada y responde
  `UBICACION_TOMADA` (STK-09). Nunca queda un movimiento ajeno confirmado después de la toma.
* Un movimiento de la jornada toma la jornada `FOR SHARE` (nivel 5); la liberación la toma
  `FOR UPDATE`: espera al movimiento en curso, termina sin interbloqueo y el saldo sigue igual a
  la suma del libro (INV-12).

La cobertura repetida y con más combinaciones está en `tests/concurrency` (grupo 15, lote 4).

Reglas citadas: STK-09, INV-12, INV-16.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

from app.core.clock import FixedClock
from app.modules.stock import jornadas_commands  # noqa: F401  (registra los handlers)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.stock.domain.movimientos import (
    ORIGEN_TRANSFERENCIA,
    TRANSFERENCIA_ENTRADA,
    TRANSFERENCIA_SALIDA,
    LineaDeMovimiento,
    LineaDeStockInicial,
)
from app.modules.stock.models import Jornada, StockMovimiento

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ESPERA_MAXIMA = 30


class _Escenario:
    """Vino A con 120 en el depósito y 48 en "Camioneta 1" (sin jornada); Juan y Pedro."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        with Session(engine) as sesion:
            self.org = crear_organizacion(sesion).id
            self.juan, self.telefono_de_juan = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"ABRIR_JORNADA", "TRANSFERIR_STOCK"})
            )
            self.pedro, self.telefono_de_pedro = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"ABRIR_JORNADA", "TRANSFERIR_STOCK"})
            )
            self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
            self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
            self.camioneta = crear_ubicacion_sql(
                sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
            )
            self.motivo = crear_motivo_sql(sesion, self.org, ambito="LIBERACION_JORNADA")
            for ubicacion_id, cantidad in ((self.deposito, 120), (self.camioneta, 48)):
                stock_service.registrar_stock_inicial(
                    self.org,
                    sesion,
                    RELOJ,
                    ubicacion_id=ubicacion_id,
                    lineas=[LineaDeStockInicial(self.vino, cantidad, "1050")],
                    usuario_id=self.juan,
                    dispositivo_id=self.telefono_de_juan,
                    operation_id=uuid4(),
                    occurred_at=MOMENTO,
                )
            sesion.commit()

    def jornada_de_juan(self) -> UUID:
        with Session(self.engine) as sesion:
            jornada_id = crear_jornada_sql(
                sesion,
                self.org,
                usuario_id=self.juan,
                dispositivo_id=self.telefono_de_juan,
                ubicacion_id=self.camioneta,
            )
            sesion.commit()
        return jornada_id

    def transferencia(
        self, origen: UUID, destino: UUID, cantidad: int = 6
    ) -> list[LineaDeMovimiento]:
        origen_id = uuid4()
        return [
            LineaDeMovimiento(
                self.vino,
                origen,
                -cantidad,
                TRANSFERENCIA_SALIDA,
                None,
                ORIGEN_TRANSFERENCIA,
                origen_id,
            ),
            LineaDeMovimiento(
                self.vino,
                destino,
                cantidad,
                TRANSFERENCIA_ENTRADA,
                None,
                ORIGEN_TRANSFERENCIA,
                origen_id,
            ),
        ]

    def mover(  # type: ignore[no-untyped-def]
        self,
        sesion: Session,
        usuario: UUID,
        dispositivo: UUID,
        lineas: list[LineaDeMovimiento],
        *,
        por_excepcion: bool = False,
    ):
        return stock_service.registrar_movimientos(
            self.org,
            sesion,
            RELOJ,
            lineas=lineas,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            puede_operar_ubicacion_tomada=por_excepcion,
        )

    def saldo(self, ubicacion_id: UUID) -> int:
        with Session(self.engine) as sesion:
            return stock_service.obtener_saldo(
                self.org, sesion, producto_id=self.vino, ubicacion_id=ubicacion_id
            )

    def cantidad_de_movimientos(self) -> int:
        with Session(self.engine) as sesion:
            return (
                sesion.scalar(
                    select(func.count())
                    .select_from(StockMovimiento)
                    .where(StockMovimiento.organizacion_id == self.org)
                )
                or 0
            )

    def estado_de(self, jornada_id: UUID) -> str:
        with Session(self.engine) as sesion:
            return sesion.scalars(select(Jornada.estado).where(Jornada.id == jornada_id)).one()

    def diferencias(self) -> list[object]:
        with Session(self.engine) as sesion:
            return list(stock_service.verificar_consistencia(self.org, sesion))


@pytest.fixture
def escenario(_engine_de_sesion: Engine):  # type: ignore[no-untyped-def]
    escenario = _Escenario(_engine_de_sesion)
    try:
        yield escenario
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def test_un_movimiento_espera_a_la_apertura_y_responde_ubicacion_tomada(
    escenario: _Escenario, _engine_de_sesion: Engine
) -> None:
    """D9 punto 1: la apertura tiene la ubicación `FOR UPDATE`; el movimiento de Pedro espera y,
    cuando la apertura confirma, encuentra la ubicación tomada por la jornada de Juan."""
    apertura_tomo_la_ubicacion = threading.Event()
    puede_confirmar = threading.Event()
    movimiento_termino = threading.Event()
    resultado: dict[str, object] = {}

    def _abrir() -> None:
        with Session(_engine_de_sesion) as sesion:
            jornada = stock_service.abrir_jornada(
                escenario.org,
                sesion,
                RELOJ,
                ubicacion_id=escenario.camioneta,
                usuario_id=escenario.juan,
                dispositivo_id=escenario.telefono_de_juan,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
            resultado["jornada_id"] = jornada.id
            apertura_tomo_la_ubicacion.set()
            assert puede_confirmar.wait(timeout=ESPERA_MAXIMA)
            sesion.commit()

    def _mover() -> None:
        with Session(_engine_de_sesion) as sesion:
            assert apertura_tomo_la_ubicacion.wait(timeout=10)
            try:
                escenario.mover(
                    sesion,
                    escenario.pedro,
                    escenario.telefono_de_pedro,
                    escenario.transferencia(escenario.deposito, escenario.camioneta),
                )
                sesion.commit()
                resultado["movimiento"] = "OK"
            except UbicacionTomadaError as error:
                sesion.rollback()
                resultado["movimiento"] = error.codigo
            finally:
                movimiento_termino.set()

    hilos = [threading.Thread(target=_abrir), threading.Thread(target=_mover)]
    for hilo in hilos:
        hilo.start()
    assert apertura_tomo_la_ubicacion.wait(timeout=10)

    esperando = not movimiento_termino.wait(timeout=1.5)
    puede_confirmar.set()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA + 10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert esperando, "El movimiento no esperó a la apertura que tenía la ubicación FOR UPDATE."
    assert resultado["movimiento"] == "UBICACION_TOMADA"
    assert escenario.estado_de(resultado["jornada_id"]) == "ABIERTA"  # type: ignore[arg-type]
    assert (escenario.saldo(escenario.deposito), escenario.saldo(escenario.camioneta)) == (120, 48)
    assert escenario.cantidad_de_movimientos() == 2  # solo los dos stocks iniciales
    assert escenario.diferencias() == []


@pytest.mark.parametrize("por_excepcion", [False, True], ids=["de_la_jornada", "por_excepcion"])
def test_la_liberacion_espera_al_movimiento_en_curso_y_termina_sin_interbloqueo(
    escenario: _Escenario, _engine_de_sesion: Engine, por_excepcion: bool
) -> None:
    """D9 punto 3: el movimiento en curso (el de la jornada de Juan, o el de Pedro por la
    excepción de `LIBERAR_UBICACION`, que no guarda `jornada_id` y por eso no se apoya en la FK)
    tiene la jornada `FOR SHARE`; la liberación (`FOR UPDATE`) espera, termina cuando el
    movimiento confirma, y el saldo de la camioneta es igual a la suma de sus movimientos
    (INV-12)."""
    jornada_id = escenario.jornada_de_juan()
    movimiento_tomo_la_jornada = threading.Event()
    puede_confirmar = threading.Event()
    liberacion_termino = threading.Event()
    resultado: dict[str, object] = {}

    def _mover() -> None:
        with Session(_engine_de_sesion) as sesion:
            usuario, dispositivo = (
                (escenario.pedro, escenario.telefono_de_pedro)
                if por_excepcion
                else (escenario.juan, escenario.telefono_de_juan)
            )
            escenario.mover(
                sesion,
                usuario,
                dispositivo,
                escenario.transferencia(escenario.camioneta, escenario.deposito),
                por_excepcion=por_excepcion,
            )
            movimiento_tomo_la_jornada.set()
            assert puede_confirmar.wait(timeout=ESPERA_MAXIMA)
            sesion.commit()

    def _liberar() -> None:
        with Session(_engine_de_sesion) as sesion:
            assert movimiento_tomo_la_jornada.wait(timeout=10)
            try:
                stock_service.liberar_jornada(
                    escenario.org,
                    sesion,
                    jornada_id=jornada_id,
                    usuario_id=escenario.pedro,
                    motivo_id=escenario.motivo,
                    observacion=None,
                    occurred_at=MOMENTO,
                )
                sesion.commit()
                resultado["liberacion"] = "OK"
            finally:
                liberacion_termino.set()

    hilos = [threading.Thread(target=_mover), threading.Thread(target=_liberar)]
    for hilo in hilos:
        hilo.start()
    assert movimiento_tomo_la_jornada.wait(timeout=10)

    esperando = not liberacion_termino.wait(timeout=1.5)
    puede_confirmar.set()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA + 10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert esperando, "La liberación no esperó al movimiento que tenía la jornada FOR SHARE."
    assert resultado["liberacion"] == "OK"
    assert escenario.estado_de(jornada_id) == "LIBERADA"
    assert escenario.saldo(escenario.camioneta) == 42
    assert escenario.diferencias() == []
