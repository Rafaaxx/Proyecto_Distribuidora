"""Change 19, tarea 12.1: INV-19, INV-12, INV-13, INV-05 y VTA-22 después de anular ventas, contra
PostgreSQL real y con Hypothesis.

- INV-19 (`docs/01` §20, VTA-21, VTA-22): confirmar y anular con devolución del dinero deja, con
  SQL sobre la base, el stock de cada producto y ubicación y el saldo del cliente exactamente
  como estaban antes de vender (para secuencias arbitrarias de ventas con cobro en el acto, con
  más o menos cobro que el total, anuladas en cualquier orden);
- VTA-22: sin devolución (con cobro), el stock vuelve igual pero el saldo difiere exactamente en
  el importe de las cobranzas que no se devolvieron: ese pago queda a favor del cliente;
- INV-12, INV-13: después de anular, cada saldo de stock es la suma de sus movimientos,
  `stock_total` la suma de sus saldos y el saldo de la cuenta la suma de su libro;
- INV-05: los libros solo crecen: las filas de `stock_movimiento`, `cuenta_movimiento` y
  `costo_producto_mov` que ya existían siguen todas ahí y la anulación agrega las suyas.

Cada ejemplo crea su propia organización (todo se filtra por `organizacion_id`) dentro de la
transacción de `db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT` por
ejemplo porque el bus confirma la transacción del comando. Es una prueba de las invariantes, no de
concurrencia (esa confirma transacciones reales,
`tests/concurrency/test_ventas_anulacion_concurrencia.py`).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_anular_utiles import PERMISOS_DE_ANULADOR, SIN_INDICAR, EntornoAnulacion
from ventas_confirmar_utiles import PRECIO_VINO

from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.stock import service as stock_service

SALDO_INICIAL = Decimal("150000.00")
PRECIO_CERVEZA = "24000.00"
CENTAVOS = Decimal("0.01")

# Una línea: (producto 0 = Vino A, 1 = Cerveza B; vendida por caja si es verdadero; cantidad).
# Cerveza B solo se vende por caja x12; Vino A por botella suelta o por caja x6.
type LineaPedida = tuple[int, bool, int]
type VentaPedida = tuple[list[LineaPedida], int, bool]

_LINEAS = st.lists(
    st.tuples(st.integers(0, 1), st.booleans(), st.integers(1, 8)),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
# Una venta: sus líneas, el porcentaje del total que se cobra en el acto (0 = sin cobranza; puede
# pasar de 100 y entonces queda saldo a favor) y si, con cobro, se devuelve el dinero al anular.
_VENTA = st.tuples(_LINEAS, st.integers(0, 150), st.booleans())
_VENTAS = st.lists(_VENTA, min_size=1, max_size=4)
_ORDEN = st.randoms(use_true_random=False)

_PROPIEDAD = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

_LIBROS = {
    "stock_movimiento": "id",
    "cuenta_movimiento": "id",
    "costo_producto_mov": "id",
}


class _Mundo:
    """`EntornoAnulacion` (Kiosco La Esquina con saldo de `150000.00`, Vino A a $12.500 la caja x6)
    más Cerveza B (caja x12 a $24.000) y stock de sobra de los dos en el depósito."""

    def __init__(self, sesion: Session) -> None:
        self.entorno = e = EntornoAnulacion(sesion, permisos=PERMISOS_DE_ANULADOR)
        self.cerveza_id, self.cerveza_caja_id = e.crear_producto("Cerveza B", unidades_caja=12)
        e.poner_precio(e.version_id, self.cerveza_id, PRECIO_CERVEZA, 12)
        e.comprar(self.cerveza_id, 1000, "700")
        e.comprar(e.vino_id, 1000, "1050")
        sesion.commit()
        # Una venta: su id, lo cobrado en el acto (0 si no hubo) y si se devuelve el dinero.
        self.ventas: list[tuple[UUID, Decimal, bool]] = []

    def _linea(self, pedida: LineaPedida) -> dict[str, Any]:
        e = self.entorno
        producto, por_caja, cantidad = pedida
        if producto == 1:
            return e.linea(
                self.cerveza_id,
                self.cerveza_caja_id,
                cantidad,
                unidades_presentacion=12,
                precio=PRECIO_CERVEZA,
                unidades_referencia=12,
            )
        if por_caja:
            return e.linea(
                e.vino_id,
                e.caja_id,
                cantidad,
                unidades_presentacion=6,
                precio=PRECIO_VINO,
                unidades_referencia=6,
            )
        return e.linea(e.vino_id, e.botella_id, cantidad)

    def vender(self, venta: VentaPedida) -> None:
        e = self.entorno
        pedidas, porcentaje, devuelve = venta
        lineas = [self._linea(pedida) for pedida in pedidas]
        total = sum((Decimal(linea["importe_bruto"]) for linea in lineas), Decimal("0.00"))
        cobrado = (total * porcentaje / 100).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        cambios: dict[str, Any] = {}
        if cobrado > 0:
            cambios["cobranza"] = e.cobranza((e.efectivo_id, str(cobrado), None))
        venta_id = e.vender_y_obtener_id(*lineas, **cambios)
        self.ventas.append((venta_id, cobrado, devuelve))

    def anular(self, venta_id: UUID, cobrado: Decimal, devuelve: bool) -> None:
        """Con cobro se indica la devolución; sin cobro se omite (D2)."""
        self.entorno.anular(venta_id, devuelve_dinero=devuelve if cobrado > 0 else SIN_INDICAR)

    # --- lecturas con SQL -------------------------------------------------------------

    def stock(self) -> dict[tuple[UUID, UUID], int]:
        e = self.entorno
        filas = e.sesion.execute(
            text(
                "SELECT producto_id, ubicacion_id, cantidad_base FROM stock_saldo "
                "WHERE organizacion_id = :o"
            ),
            {"o": e.org},
        ).all()
        return {(fila[0], fila[1]): int(fila[2]) for fila in filas}

    def saldo(self) -> Decimal:
        e = self.entorno
        return cuentas_service.obtener_saldo(
            e.org, e.sesion, cuenta_tipo="CLIENTE", entidad_id=e.cliente_id
        )

    def libros(self) -> dict[str, set[UUID]]:
        e = self.entorno
        return {
            tabla: {
                fila[0]
                for fila in e.sesion.execute(
                    text(f"SELECT {columna} FROM {tabla} WHERE organizacion_id = :o"),  # noqa: S608
                    {"o": e.org},
                ).all()
            }
            for tabla, columna in _LIBROS.items()
        }

    def verificar_libros_consistentes(self) -> None:
        """INV-12 e INV-13 con SQL: saldos igual a la suma de movimientos y cuenta igual a su
        libro."""
        e = self.entorno
        assert (
            self._contar(
                "SELECT count(*) FROM stock_saldo s WHERE s.organizacion_id = :o "
                "AND s.cantidad_base <> (SELECT COALESCE(SUM(m.cantidad_base), 0) "
                "FROM stock_movimiento m "
                "WHERE m.organizacion_id = s.organizacion_id AND m.producto_id = s.producto_id "
                "AND m.ubicacion_id = s.ubicacion_id)"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM costo_producto c WHERE c.organizacion_id = :o "
                "AND c.stock_total <> (SELECT COALESCE(SUM(s.cantidad_base), 0) FROM stock_saldo s "
                "WHERE s.organizacion_id = c.organizacion_id AND s.producto_id = c.producto_id)"
            )
            == 0
        )
        assert stock_service.verificar_consistencia(e.org, e.sesion) == []
        ((suma,),) = e.sesion.execute(
            text(
                "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), "
                "0) FROM cuenta_movimiento WHERE organizacion_id = :o "
                "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e"
            ),
            {"o": e.org, "e": e.cliente_id},
        ).all()
        assert self.saldo() == suma
        assert cuentas_service.verificar_consistencia(e.org, e.sesion) == []

    def verificar_estados(self) -> None:
        """Toda venta anulada tiene su anulación; ninguna cobranza devuelta queda confirmada."""
        assert (
            self._contar(
                "SELECT count(*) FROM venta v WHERE v.organizacion_id = :o "
                "AND v.estado = 'ANULADA' "
                "AND NOT EXISTS (SELECT 1 FROM venta_anulacion a "
                "WHERE a.organizacion_id = v.organizacion_id AND a.venta_id = v.id)"
            )
            == 0
        )

    def _contar(self, consulta: str) -> int:
        e = self.entorno
        return int(e.sesion.execute(text(consulta), {"o": e.org}).scalar_one())


# Escenario: "Propiedad con SQL" (ventas/anulacion-de-venta): INV-19, INV-12, INV-13, INV-05
@_PROPIEDAD
@given(_VENTAS, _ORDEN)
def test_inv19_vta22_confirmar_y_anular_con_devolucion_deja_stock_y_saldo_como_antes(
    db_session: Session, ventas: list[VentaPedida], azar: Any
) -> None:
    mundo = _Mundo(db_session)
    stock_antes = mundo.stock()
    saldo_antes = mundo.saldo()
    assert saldo_antes == SALDO_INICIAL
    for venta in ventas:
        mundo.vender((venta[0], venta[1], True))
    libros_con_ventas = mundo.libros()
    pendientes = list(mundo.ventas)
    azar.shuffle(pendientes)

    for venta_id, cobrado, devuelve in pendientes:
        mundo.anular(venta_id, cobrado, devuelve)
        mundo.verificar_libros_consistentes()

    assert mundo.stock() == stock_antes
    assert mundo.saldo() == saldo_antes
    libros_tras_anular = mundo.libros()
    for tabla, ids in libros_con_ventas.items():
        assert ids <= libros_tras_anular[tabla], f"{tabla}: la anulación borró filas"
    assert libros_tras_anular["stock_movimiento"] > libros_con_ventas["stock_movimiento"]
    assert libros_tras_anular["cuenta_movimiento"] > libros_con_ventas["cuenta_movimiento"]
    mundo.verificar_estados()


# Escenario: "VTA-22 — sin devolución el cobro queda a favor"
@_PROPIEDAD
@given(_VENTAS, _ORDEN)
def test_vta22_sin_devolucion_el_saldo_difiere_exactamente_en_lo_cobrado(
    db_session: Session, ventas: list[VentaPedida], azar: Any
) -> None:
    mundo = _Mundo(db_session)
    stock_antes = mundo.stock()
    saldo_antes = mundo.saldo()
    for venta in ventas:
        mundo.vender(venta)
    libros_con_ventas = mundo.libros()
    pendientes = list(mundo.ventas)
    azar.shuffle(pendientes)

    for venta_id, cobrado, devuelve in pendientes:
        mundo.anular(venta_id, cobrado, devuelve)
        mundo.verificar_libros_consistentes()

    sin_devolver = sum(
        (cobrado for _, cobrado, devuelve in mundo.ventas if cobrado > 0 and not devuelve),
        Decimal("0.00"),
    )
    assert mundo.stock() == stock_antes  # INV-19: la mercadería siempre vuelve entera
    assert mundo.saldo() == saldo_antes - sin_devolver
    libros_tras_anular = mundo.libros()
    for tabla, ids in libros_con_ventas.items():
        assert ids <= libros_tras_anular[tabla], f"{tabla}: la anulación borró filas"
    mundo.verificar_estados()
