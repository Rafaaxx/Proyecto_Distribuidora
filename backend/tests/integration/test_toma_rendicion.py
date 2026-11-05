"""Change 24, tarea 6.1: la rendición mueve la ubicación tomada por su jornada (spec
`stock/toma-de-ubicacion`, requisito "La rendición mueve la ubicación tomada por su jornada";
`design.md` D3, D6) contra PostgreSQL real.

La excepción es el parámetro `rendicion_de_jornada` de `registrar_movimientos`: falla cerrado y
solo alcanza a las líneas de la ubicación de esa jornada.

Reglas citadas: STK-09, STK-05, RUT-06, RUT-08, INV-01, INV-16.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_producto_sql, crear_ubicacion_sql

from app.core.clock import FixedClock
from app.modules.stock import service
from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.stock.domain.movimientos import (
    ORIGEN_TRANSFERENCIA,
    TRANSFERENCIA_ENTRADA,
    TRANSFERENCIA_SALIDA,
    LineaDeMovimiento,
    LineaDeStockInicial,
)
from app.modules.stock.models import StockMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
DIFERENCIA = "DIFERENCIA_RENDICION"


class Entorno:
    """ "Camioneta 1" (48 de Vino A) tomada por la jornada de Juan; una Supervisora sin
    `LIBERAR_UBICACION`; el depósito libre."""

    def __init__(self, sesion: Session, estado: str = "ABIERTA") -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan, self.telefono_de_juan = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"ABRIR_JORNADA"})
        )
        self.supervisora, self.equipo = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"RENDIR_JORNADA"})
        )
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        for ubicacion_id, cantidad in ((self.deposito, 120), (self.camioneta, 48)):
            service.registrar_stock_inicial(
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
        self.jornada = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.juan,
            dispositivo_id=self.telefono_de_juan,
            ubicacion_id=self.camioneta,
            estado=estado,
        )

    def mover(
        self, *lineas: LineaDeMovimiento, rendicion_de_jornada: UUID | None = None
    ) -> list[service.ResultadoDeMovimiento]:
        """Siempre quien llama es la Supervisora (sin `LIBERAR_UBICACION`)."""
        return service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=list(lineas),
            usuario_id=self.supervisora,
            dispositivo_id=self.equipo,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            rendicion_de_jornada=rendicion_de_jornada,
        )

    def diferencia(self, cantidad: int, *, ubicacion_id: UUID | None = None) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=self.vino,
            ubicacion_id=ubicacion_id or self.camioneta,
            cantidad_base=cantidad,
            tipo=DIFERENCIA,
            costo_unitario=None,
            origen_tipo="RENDICION",
            origen_id=uuid4(),
        )

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

    def saldo(self, ubicacion_id: UUID) -> int:
        return service.obtener_saldo(
            self.org, self.sesion, producto_id=self.vino, ubicacion_id=ubicacion_id
        )

    def jornada_de(self, movimiento_id: UUID) -> UUID | None:
        return self.sesion.scalar(
            select(StockMovimiento.jornada_id).where(StockMovimiento.id == movimiento_id)
        )

    def movimientos(self) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


@pytest.mark.parametrize("cantidad", [-3, 2])
def test_la_rendicion_escribe_sobre_el_vehiculo_tomado_con_la_jornada(
    entorno: Entorno, cantidad: int
) -> None:
    """STK-09, RUT-06: faltante y sobrante quedan con el `jornada_id` de Juan."""
    (resultado,) = entorno.mover(entorno.diferencia(cantidad), rendicion_de_jornada=entorno.jornada)

    assert entorno.jornada_de(resultado.movimiento.id) == entorno.jornada
    assert entorno.saldo(entorno.camioneta) == 48 + cantidad


def test_sin_el_parametro_la_diferencia_falla_cerrada(entorno: Entorno) -> None:
    """STK-09: sin `rendicion_de_jornada` la Supervisora recibe `UBICACION_TOMADA`."""
    antes = entorno.movimientos()

    with pytest.raises(UbicacionTomadaError):
        entorno.mover(entorno.diferencia(-3))

    assert entorno.movimientos() == antes


def test_la_excepcion_no_alcanza_a_una_transferencia_comun(db_session: Session) -> None:
    """Con la jornada `EN_RENDICION`, una transferencia común desde el vehículo sigue siendo
    `UBICACION_TOMADA` y no escribe nada."""
    entorno = Entorno(db_session, estado="EN_RENDICION")
    antes = entorno.movimientos()

    with pytest.raises(UbicacionTomadaError):
        entorno.mover(*entorno.transferencia(entorno.camioneta, entorno.deposito))

    assert entorno.movimientos() == antes


def test_con_el_parametro_de_otra_jornada_falla_cerrado(entorno: Entorno) -> None:
    """Fail-closed: el parámetro tiene que ser la jornada que tomó esa ubicación."""
    with pytest.raises(UbicacionTomadaError):
        entorno.mover(entorno.diferencia(-3), rendicion_de_jornada=uuid4())


def test_la_excepcion_no_alcanza_a_otra_ubicacion_tomada(db_session: Session) -> None:
    """Una segunda ubicación tomada por otra jornada no se mueve con el parámetro de la primera."""
    entorno = Entorno(db_session)
    otra = crear_ubicacion_sql(
        db_session, entorno.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
    )
    pedro, telefono_de_pedro = crear_usuario_y_dispositivo(db_session, entorno.org)
    crear_jornada_sql(
        db_session,
        entorno.org,
        usuario_id=pedro,
        dispositivo_id=telefono_de_pedro,
        ubicacion_id=otra,
    )

    with pytest.raises(UbicacionTomadaError):
        entorno.mover(
            entorno.diferencia(-1),
            entorno.diferencia(1, ubicacion_id=otra),
            rendicion_de_jornada=entorno.jornada,
        )


def test_la_devolucion_del_cierre_sale_del_vehiculo_tomado(db_session: Session) -> None:
    """RUT-08: con la jornada `EN_RENDICION`, la salida de la camioneta queda con la jornada de
    Juan y la entrada del depósito, sin jornada."""
    entorno = Entorno(db_session, estado="EN_RENDICION")

    salida, entrada = entorno.mover(
        *entorno.transferencia(entorno.camioneta, entorno.deposito),
        rendicion_de_jornada=entorno.jornada,
    )

    assert entorno.jornada_de(salida.movimiento.id) == entorno.jornada
    assert entorno.jornada_de(entrada.movimiento.id) is None
    assert entorno.saldo(entorno.camioneta) == 42
