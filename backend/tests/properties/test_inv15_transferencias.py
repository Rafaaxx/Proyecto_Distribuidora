"""INV-15 contra PostgreSQL real, con Hypothesis (change 14, tarea 15.1).

INV-15 (`docs/01` §20, STK-07, CST-12): una transferencia no cambia el stock total del producto
ni su costo promedio, y tampoco lo cambia anularla. Acá se prueba con la base y los servicios
reales: para stocks iniciales arbitrarios en tres ubicaciones, secuencias arbitrarias de
transferencias válidas entre las tres y anulaciones de algunas de ellas, al final:

- el `stock_total` de cada producto es el que tenía antes de la primera transferencia;
- el `costo_promedio` de cada producto es el que tenía (sin historia de costo nueva);
- cada `stock_saldo` es la suma SQL de su libro (INV-12) y ninguno es negativo (STK-05);
- `verificar_consistencia` no informa diferencias.

Una transferencia o anulación que el estado no admite (`STOCK_INSUFICIENTE`: origen sin
unidades, o destino ya vaciado por otra transferencia) se descarta: no es válida y no deja
efectos (INV-01), y la propiedad igual tiene que valer para todo lo que sí se aplicó.

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la invariante,
no de concurrencia (esa confirma transacciones reales, `tests/concurrency`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.costeo import service as costeo_service
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import StockInsuficienteError
from app.modules.stock.service import LineaDeMovimiento, LineaDeTransferencia
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import (
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

MOMENTO = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
PERMISOS_DEL_USUARIO = frozenset({"TRANSFERIR_STOCK"})

# Stock inicial de cada (producto, ubicación): 2 productos x 3 ubicaciones, 0..80 unidades,
# a un costo por (producto, ubicación) en pesos enteros para que los promedios sean variados.
_STOCKS = st.lists(
    st.tuples(st.integers(min_value=0, max_value=80), st.integers(min_value=1, max_value=5000)),
    min_size=6,
    max_size=6,
)

# ("T", origen, destino, [(producto, cantidad), ...]) o ("A", índice de transferencia aplicada)
_LINEAS = st.lists(
    st.tuples(st.integers(min_value=0, max_value=1), st.integers(min_value=1, max_value=60)),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
_TRANSFERENCIA = st.tuples(
    st.just("T"),
    st.integers(min_value=0, max_value=2),
    st.integers(min_value=1, max_value=2),
    _LINEAS,
)
_ANULACION = st.tuples(st.just("A"), st.integers(min_value=0, max_value=50))
_OPERACIONES = st.lists(st.one_of(_TRANSFERENCIA, _ANULACION), min_size=1, max_size=14)

_PROPIEDAD = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class _Mundo:
    """Una organización con dos productos y tres ubicaciones, creada dentro del `SAVEPOINT` del
    ejemplo, con el stock inicial ya ingresado por compras."""

    def __init__(self, sesion: Session, stocks: list[tuple[int, int]]) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=PERMISOS_DEL_USUARIO
        )
        self.productos = [
            crear_producto_sql(sesion, self.org, nombre=f"Producto {i}") for i in range(2)
        ]
        self.ubicaciones = [
            crear_ubicacion_sql(sesion, self.org, nombre=f"Ubicación {i}") for i in range(3)
        ]
        self.motivo_anulacion = crear_motivo_sql(sesion, self.org, ambito="ANULACION_TRANSFERENCIA")
        lineas = [
            LineaDeMovimiento(
                producto_id=self.productos[posicion // 3],
                ubicacion_id=self.ubicaciones[posicion % 3],
                cantidad_base=cantidad,
                tipo="COMPRA",
                costo_unitario=str(Decimal(costo)),
                origen_tipo="COMPRA",
                origen_id=uuid4(),
            )
            for posicion, (cantidad, costo) in enumerate(stocks)
            if cantidad > 0
        ]
        if lineas:
            stock_service.registrar_movimientos(
                self.org,
                sesion,
                RELOJ,
                lineas=lineas,
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        self.transferencias: list[UUID] = []

    def transferir(self, origen: int, destino: int, lineas: list[tuple[int, int]]) -> bool:
        """`False` si el estado no la admite (sin efectos); cualquier otra falla se propaga."""
        try:
            with self.sesion.begin_nested():
                resultado = stock_service.transferir(
                    self.org,
                    self.sesion,
                    RELOJ,
                    ubicacion_origen_id=self.ubicaciones[origen],
                    ubicacion_destino_id=self.ubicaciones[destino],
                    lineas=[LineaDeTransferencia(self.productos[p], c) for p, c in lineas],
                    observacion=None,
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    operation_id=uuid4(),
                    occurred_at=MOMENTO,
                )
        except StockInsuficienteError:
            return False
        self.transferencias.append(resultado.transferencia.id)
        return True

    def anular(self, indice: int) -> bool:
        """Anula una de las transferencias aplicadas que sigan confirmadas. `False` si no hay
        ninguna o si el destino ya no tiene las unidades."""
        pendientes = [
            transferencia
            for transferencia in self.transferencias
            if self.estado(transferencia) == "CONFIRMADA"
        ]
        if not pendientes:
            return False
        elegida = pendientes[indice % len(pendientes)]
        try:
            with self.sesion.begin_nested():
                stock_service.anular_transferencia(
                    self.org,
                    self.sesion,
                    RELOJ,
                    transferencia_id=elegida,
                    motivo_id=self.motivo_anulacion,
                    permisos=PERMISOS_DEL_USUARIO,
                    operation_id=uuid4(),
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    occurred_at=MOMENTO,
                )
        except StockInsuficienteError:
            return False
        return True

    def estado(self, transferencia_id: UUID) -> str:
        return str(
            self.sesion.execute(
                text("SELECT estado FROM transferencia WHERE organizacion_id = :o AND id = :t"),
                {"o": self.org, "t": transferencia_id},
            ).scalar_one()
        )

    def totales(self) -> dict[UUID, int]:
        return {
            producto: costeo_service.obtener_stock_totales(self.org, self.sesion).get(producto, 0)
            for producto in self.productos
        }

    def promedios(self) -> dict[UUID, Decimal | None]:
        return {
            producto: costeo_service.obtener_promedio(self.org, self.sesion, producto)
            for producto in self.productos
        }

    def historia_de_costo(self) -> int:
        return int(
            self.sesion.execute(
                text("SELECT count(*) FROM costo_producto_mov WHERE organizacion_id = :o"),
                {"o": self.org},
            ).scalar_one()
        )

    def verificar_saldos(self) -> None:
        libro = {
            (fila[0], fila[1]): int(fila[2])
            for fila in self.sesion.execute(
                text(
                    "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
                    "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
                ),
                {"o": self.org},
            ).all()
        }
        for (producto_id, ubicacion_id), suma in libro.items():
            saldo = stock_service.obtener_saldo(
                self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
            )
            assert saldo == suma  # INV-12
            assert saldo >= 0  # STK-05
        assert stock_service.verificar_consistencia(self.org, self.sesion) == []


@_PROPIEDAD
@given(_STOCKS, _OPERACIONES)
def test_inv15_transferir_y_anular_no_cambian_el_stock_total_ni_el_promedio(
    db_session: Session,
    stocks: list[tuple[int, int]],
    operaciones: list[tuple[object, ...]],
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session, stocks)
        totales_antes = mundo.totales()
        promedios_antes = mundo.promedios()
        historia_antes = mundo.historia_de_costo()

        for operacion in operaciones:
            if operacion[0] == "T":
                _, origen, destino, lineas = operacion
                assert isinstance(origen, int)
                assert isinstance(destino, int)
                assert isinstance(lineas, list)
                # `destino` va de 1 a 2 y se le suma el origen módulo 3: nunca igual al origen.
                aplicada = mundo.transferir(origen, (origen + destino) % 3, lineas)
                event(f"transferencia aplicada={aplicada}")
            else:
                indice = operacion[1]
                assert isinstance(indice, int)
                event(f"anulación aplicada={mundo.anular(indice)}")

        assert mundo.totales() == totales_antes  # INV-15: el stock total no cambia
        assert mundo.promedios() == promedios_antes  # INV-15, CST-12: el promedio no cambia
        assert mundo.historia_de_costo() == historia_antes  # sin historia de costo nueva
        mundo.verificar_saldos()
    finally:
        savepoint.rollback()


def test_inv15_el_arnes_aplica_de_verdad_transferencias_y_anulaciones(
    db_session: Session,
) -> None:
    """Contra una propiedad vacua: con stock suficiente, la transferencia y la anulación se
    aplican (no se descartan) y mueven saldos; el total y el promedio siguen iguales."""
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session, [(50, 1000), (30, 1200), (0, 1), (20, 500), (0, 1), (40, 700)])
        totales_antes = mundo.totales()
        promedios_antes = mundo.promedios()
        assert promedios_antes[mundo.productos[0]] is not None

        assert mundo.transferir(0, 2, [(0, 50), (1, 20)])
        assert (
            stock_service.obtener_saldo(
                mundo.org,
                db_session,
                producto_id=mundo.productos[0],
                ubicacion_id=mundo.ubicaciones[2],
            )
            == 50
        )
        assert mundo.totales() == totales_antes
        assert mundo.anular(0)
        assert (
            stock_service.obtener_saldo(
                mundo.org,
                db_session,
                producto_id=mundo.productos[0],
                ubicacion_id=mundo.ubicaciones[0],
            )
            == 50
        )

        assert mundo.totales() == totales_antes
        assert mundo.promedios() == promedios_antes
        mundo.verificar_saldos()
    finally:
        savepoint.rollback()
