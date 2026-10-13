"""Change 15, tarea 8.1: STK-09 en la puerta del libro, `registrar_movimientos`, contra PostgreSQL
real (spec `stock/toma-de-ubicacion`, requisitos "Una ubicación tomada solo acepta movimientos de
su jornada", "Una ubicación con toma y sin jornada se mueve libremente" y "Quien tiene
`LIBERAR_UBICACION` mueve una ubicación tomada, con auditoría"; `design.md` D6, D7, D9).

La regla se prueba directamente sobre la puerta (`stock/service.py`): los comandos de `stock`,
las compras y la importación pasan el permiso en las tareas 8.2 y 8.3. La constancia en la
auditoría es de la tarea 8.5.

Reglas citadas: STK-09, RUT-02, RUT-08, INV-01, INV-12, INV-16.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_producto_sql, crear_ubicacion_sql

from app.core.clock import FixedClock
from app.modules.stock import service as stock_service
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

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

VENDEDOR = frozenset({"ABRIR_JORNADA", "TRANSFERIR_STOCK"})


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """Vino A con 120 unidades en el depósito y 48 en cada camioneta; "Camioneta 1" tomada por
    la jornada `ABIERTA` de Juan en su teléfono V03 y "Camioneta 2" tomada por la de Pedro;
    "Camioneta 3" con toma y sin jornada; Supervisora (con `LIBERAR_UBICACION` en el
    llamador) y Juan en otro dispositivo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.pedro = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.supervisora = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.juan_en_otro_telefono = Actor(self.juan.usuario_id, self.pedro.dispositivo_id)
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.camioneta_1 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_3 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 3", tipo="VEHICULO", requiere_toma=True
        )
        for ubicacion_id, cantidad in (
            (self.deposito, 120),
            (self.camioneta_1, 48),
            (self.camioneta_2, 48),
            (self.camioneta_3, 48),
        ):
            stock_service.registrar_stock_inicial(
                self.org,
                sesion,
                RELOJ,
                ubicacion_id=ubicacion_id,
                lineas=[LineaDeStockInicial(self.vino, cantidad, "1050")],
                usuario_id=self.juan.usuario_id,
                dispositivo_id=self.juan.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        self.jornada_de_juan = self.jornada(self.juan, self.camioneta_1)
        self.jornada_de_pedro = self.jornada(self.pedro, self.camioneta_2)
        sesion.commit()

    def jornada(self, actor: Actor, ubicacion_id: UUID, estado: str = "ABIERTA") -> UUID:
        return crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            ubicacion_id=ubicacion_id,
            estado=estado,
        )

    def transferencia(
        self, origen: UUID, destino: UUID, cantidad: int = 6, **extra: UUID | None
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
                **extra,
            ),
            LineaDeMovimiento(
                self.vino,
                destino,
                cantidad,
                TRANSFERENCIA_ENTRADA,
                None,
                ORIGEN_TRANSFERENCIA,
                origen_id,
                **extra,
            ),
        ]

    def mover(
        self,
        actor: Actor,
        lineas: list[LineaDeMovimiento],
        **opciones: bool,
    ) -> list[stock_service.ResultadoDeMovimiento]:
        return stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=lineas,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            **opciones,
        )

    def saldo(self, ubicacion_id: UUID) -> int:
        self.sesion.rollback()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=self.vino, ubicacion_id=ubicacion_id
        )

    def cantidad_de_movimientos(self) -> int:
        self.sesion.rollback()
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


def _jornada_de(resultado: stock_service.ResultadoDeMovimiento) -> UUID | None:
    return resultado.movimiento.jornada_id


# --- la jornada mueve su ubicación (STK-09, RUT-04) -----------------------------------------


def test_el_usuario_y_el_dispositivo_de_la_jornada_abierta_mueven_su_ubicacion(
    entorno: Entorno,
) -> None:
    """Escenario "El vendedor de la jornada mueve stock de su vehículo": la línea de la
    camioneta queda con la jornada y la del depósito, sin jornada."""
    salida, entrada = entorno.mover(
        entorno.juan, entorno.transferencia(entorno.camioneta_1, entorno.deposito)
    )

    assert (salida.saldo, entrada.saldo) == (42, 126)
    assert _jornada_de(salida) == entorno.jornada_de_juan
    assert _jornada_de(entrada) is None
    assert (salida.jornada_tomada_id, entrada.jornada_tomada_id) == (None, None)


def test_la_jornada_tambien_recibe_stock_en_su_ubicacion(entorno: Entorno) -> None:
    """RUT-02: la carga durante la jornada por el propio vendedor (el destino es la camioneta
    tomada)."""
    salida, entrada = entorno.mover(
        entorno.juan, entorno.transferencia(entorno.deposito, entorno.camioneta_1, 24)
    )

    assert (salida.saldo, entrada.saldo) == (96, 72)
    assert (_jornada_de(salida), _jornada_de(entrada)) == (None, entorno.jornada_de_juan)


# --- lo que se rechaza ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actor", "origen", "destino"),
    [
        ("pedro", "deposito", "camioneta_1"),  # otro usuario hacia el vehículo tomado
        ("pedro", "camioneta_1", "deposito"),  # otro usuario desde el vehículo tomado
        ("juan_en_otro_telefono", "camioneta_1", "deposito"),  # mismo usuario, otro dispositivo
        ("supervisora", "deposito", "camioneta_1"),  # sin el permiso de excepción
    ],
)
def test_stk09_otro_usuario_u_otro_dispositivo_recibe_ubicacion_tomada_sin_escribir_nada(
    entorno: Entorno, actor: str, origen: str, destino: str
) -> None:
    """Escenarios "Otro vendedor intenta mover stock de un vehículo tomado" y "El mismo
    usuario desde otro dispositivo". Sin el parámetro la puerta falla cerrado. INV-01,
    INV-12: ningún movimiento ni saldo cambia."""
    antes = entorno.cantidad_de_movimientos()
    saldos = [entorno.saldo(u) for u in (entorno.deposito, entorno.camioneta_1)]

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.mover(
            getattr(entorno, actor),
            entorno.transferencia(getattr(entorno, origen), getattr(entorno, destino)),
        )

    assert (error.value.codigo, error.value.status_http) == ("UBICACION_TOMADA", 409)
    assert error.value.extension == {"ubicacion_id": str(entorno.camioneta_1)}
    entorno.sesion.rollback()
    assert entorno.cantidad_de_movimientos() == antes
    assert [entorno.saldo(u) for u in (entorno.deposito, entorno.camioneta_1)] == saldos


def test_la_jornada_en_rendicion_ya_no_mueve_stock(entorno: Entorno, db_session: Session) -> None:
    """Escenario "La jornada en rendición ya no mueve stock" (`01` §18, D6 punto 4)."""
    db_session.execute(
        text(
            "UPDATE jornada SET estado = 'EN_RENDICION', rendida_en = now(), "
            "rendida_por_id = usuario_id WHERE id = :id"
        ),
        {"id": entorno.jornada_de_juan},
    )
    db_session.commit()

    with pytest.raises(UbicacionTomadaError):
        entorno.mover(entorno.juan, entorno.transferencia(entorno.camioneta_1, entorno.deposito))


def test_una_jornada_ajena_en_el_sobre_no_habilita_la_ubicacion(entorno: Entorno) -> None:
    """D6 punto 2: si el sobre trae una jornada, tiene que ser la de la ubicación."""
    with pytest.raises(UbicacionTomadaError):
        entorno.mover(
            entorno.juan,
            entorno.transferencia(
                entorno.camioneta_1, entorno.deposito, jornada_id=entorno.jornada_de_pedro
            ),
        )


# --- la excepción de LIBERAR_UBICACION ---------------------------------------------------------


@pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION"])
def test_con_el_permiso_de_excepcion_se_mueve_sin_jornada_y_se_informa(
    entorno: Entorno, db_session: Session, estado: str
) -> None:
    """Escenario "Una supervisora recarga un vehículo tomado": el movimiento queda sin
    jornada y la puerta informa qué línea pasó por excepción y de qué jornada (D6 punto 3)."""
    if estado == "EN_RENDICION":
        db_session.execute(
            text(
                "UPDATE jornada SET estado = 'EN_RENDICION', rendida_en = now(), "
                "rendida_por_id = usuario_id WHERE id = :id"
            ),
            {"id": entorno.jornada_de_juan},
        )
        db_session.commit()

    salida, entrada = entorno.mover(
        entorno.supervisora,
        entorno.transferencia(entorno.deposito, entorno.camioneta_1, 12),
        puede_operar_ubicacion_tomada=True,
    )

    assert (salida.saldo, entrada.saldo) == (108, 60)
    assert (_jornada_de(salida), _jornada_de(entrada)) == (None, None)
    assert (salida.jornada_tomada_id, entrada.jornada_tomada_id) == (
        None,
        entorno.jornada_de_juan,
    )


def test_el_permiso_de_excepcion_no_cambia_una_ubicacion_libre(entorno: Entorno) -> None:
    """Escenario "Un movimiento sin excepción no lleva esa constancia"."""
    salida, entrada = entorno.mover(
        entorno.supervisora,
        entorno.transferencia(entorno.deposito, entorno.camioneta_3, 12),
        puede_operar_ubicacion_tomada=True,
    )

    assert (salida.jornada_tomada_id, entrada.jornada_tomada_id) == (None, None)
    assert (_jornada_de(salida), _jornada_de(entrada)) == (None, None)


# --- ubicaciones sin toma o sin jornada no cambian ---------------------------------------------


def test_una_ubicacion_con_toma_y_sin_jornada_se_mueve_libremente(entorno: Entorno) -> None:
    """Escenario "Carga del vehículo antes de abrir" (RUT-02)."""
    salida, entrada = entorno.mover(
        entorno.pedro, entorno.transferencia(entorno.deposito, entorno.camioneta_3, 48)
    )

    assert (salida.saldo, entrada.saldo) == (72, 96)


@pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
def test_una_ubicacion_con_la_jornada_terminada_se_mueve_libremente(
    entorno: Entorno, estado: str
) -> None:
    """Escenario "Devolución del remanente después del cierre" (RUT-08, RUT-09)."""
    entorno.jornada(entorno.juan_en_otro_telefono, entorno.camioneta_3, estado)
    entorno.sesion.commit()

    salida, entrada = entorno.mover(
        entorno.pedro, entorno.transferencia(entorno.camioneta_3, entorno.deposito, 12)
    )

    assert (salida.saldo, entrada.saldo) == (36, 132)


def test_una_ubicacion_que_no_requiere_toma_nunca_queda_alcanzada(entorno: Entorno) -> None:
    """Escenario "Un depósito nunca queda tomado"."""
    (resultado,) = entorno.mover(
        entorno.pedro,
        [
            LineaDeMovimiento(
                entorno.vino,
                entorno.deposito,
                -6,
                "AJUSTE",
                None,
                "AJUSTE_STOCK",
                uuid4(),
                motivo_id=None,
            )
        ],
    )

    assert resultado.saldo == 114
    assert resultado.jornada_tomada_id is None


def test_el_sobre_con_jornada_no_marca_una_ubicacion_libre(entorno: Entorno) -> None:
    """Decisión del usuario (2026-10-09): la puerta decide por ubicación. La transferencia de
    un vehículo tomado a un depósito libre trae la jornada de Juan en el sobre; el depósito
    se acepta y su movimiento queda sin jornada (la jornada pertenece a su ubicación)."""
    salida, entrada = entorno.mover(
        entorno.juan,
        entorno.transferencia(
            entorno.camioneta_1, entorno.deposito, jornada_id=entorno.jornada_de_juan
        ),
    )

    assert (_jornada_de(salida), _jornada_de(entrada)) == (entorno.jornada_de_juan, None)


# --- cada ubicación se decide por separado -------------------------------------------------------


def test_en_una_llamada_con_dos_ubicaciones_tomadas_se_decide_cada_una(
    entorno: Entorno,
) -> None:
    """La jornada de Juan no habilita "Camioneta 2" (tomada por Pedro): se rechaza entera y
    no queda ningún movimiento, ni siquiera el de la ubicación propia (INV-01)."""
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.mover(entorno.juan, entorno.transferencia(entorno.camioneta_1, entorno.camioneta_2))

    assert error.value.extension == {"ubicacion_id": str(entorno.camioneta_2)}
    entorno.sesion.rollback()
    assert entorno.cantidad_de_movimientos() == antes
    assert entorno.saldo(entorno.camioneta_1) == 48


def test_con_el_permiso_cada_ubicacion_informa_su_propia_jornada(entorno: Entorno) -> None:
    """El dueño de la jornada de "Camioneta 1" con `LIBERAR_UBICACION` mueve "Camioneta 1" como
    de la jornada y "Camioneta 2" por excepción."""
    salida, entrada = entorno.mover(
        entorno.juan,
        entorno.transferencia(entorno.camioneta_1, entorno.camioneta_2),
        puede_operar_ubicacion_tomada=True,
    )

    assert (_jornada_de(salida), salida.jornada_tomada_id) == (entorno.jornada_de_juan, None)
    assert (_jornada_de(entrada), entrada.jornada_tomada_id) == (
        None,
        entorno.jornada_de_pedro,
    )
