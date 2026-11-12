"""Change 26, tarea 14.1: propiedades (Hypothesis) de los reportes contra PostgreSQL real, con la
base como juez (consultas SQL sobre las tablas, no sobre las estructuras de la prueba).

**REP-01, REP-02, INV-14** (spec `reportes/ventas-por-periodo`): para secuencias aleatorias de
ventas (en línea y sin conexión, con IVA, con líneas con y sin costo, de dos vendedores, dentro y
fuera del período) y de anulaciones:
(a) la cantidad y el total del reporte de ventas son la cantidad y la suma de `venta.total` de las
    `CONFIRMADA` del período, y neto + IVA = total;
(b) el total de las anuladas es la suma de `venta.total` de las `ANULADA` del período (y no entran
    en (a));
**REP-05, INV-10, INV-03** (spec «Las cifras de ventas pasadas no cambian»):
(c) las cifras de ventas pasadas no cambian con costos y precios publicados después (el promedio de
    `costo_producto` y los precios de la lista cambian; el reporte, que usa lo congelado en cada
    línea, queda idéntico);
**INV-13, CC-04** (spec `reportes/saldos-de-cuentas`):
(d) cada saldo del reporte de saldos es la suma en SQL de `cuenta_movimiento` de esa cuenta, con
    ventas, cobranzas y saldos aleatorios.

`00` §9 criterio 11. Cada ejemplo crea su propia organización dentro de la transacción de
`db_session`, que se revierte al terminar la prueba (mismo criterio que
`test_revision_propiedades.py`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from reportes_utiles import (
    LineaDePrueba,
    anular_venta,
    crear_vendedor,
    dia,
    mover_cuenta,
    sembrar_cliente_de_cartera,
    sembrar_jornada,
    sembrar_venta,
    suma_del_libro,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import Sesion

from app.core.clock import FixedClock
from app.modules.reportes import queries

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_PROPIEDAD = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

DESDE, HASTA = date(2026, 11, 1), date(2026, 11, 30)
RELOJ = FixedClock(dia(12, 1))
# El período de noviembre en la zona de la organización (UTC-3): [1/11 03:00Z, 1/12 03:00Z).
INICIO_UTC = dia(11, 1, 0)
FIN_UTC = dia(12, 1, 0)

_CENTAVOS = st.integers(100, 5_000_000)

# (mes, día, hora): dentro de noviembre y también octubre/diciembre, fuera del período.
_MOMENTO = st.tuples(st.sampled_from([10, 11, 11, 11, 12]), st.integers(1, 28), st.integers(0, 23))
_LINEA = st.builds(
    lambda neto, con_costo, cantidad: (neto, con_costo, cantidad),
    _CENTAVOS,
    st.booleans(),
    st.integers(1, 40),
)
_VENTA = st.tuples(
    st.lists(_LINEA, min_size=1, max_size=3),
    _MOMENTO,
    st.integers(0, 1),  # vendedor
    st.booleans(),  # sin conexión
    st.integers(0, 100_000),  # IVA en centavos
    st.booleans(),  # se anula
)


def _importe(centavos: int) -> str:
    return str(Decimal(centavos).scaleb(-2))


def _momento(mes_dia_hora: tuple[int, int, int]) -> Any:
    mes, dia_, hora = mes_dia_hora
    return dia(mes, dia_, hora)


def _sembrar(sesion: Session, s: Sesion, ventas: list[Any]) -> None:
    """Siembra las ventas de dos vendedores y anula las marcadas; lo esperado se pide a la base."""
    ana = crear_vendedor(sesion, s, "Ana")
    vendedores = [ana.usuario_id, s.entorno.usuario_id]
    # Una sola jornada abierta por vendedor: las ventas sin conexión cuelgan de ella.
    jornadas = [
        sembrar_jornada(sesion, s, vendedor=ana, estado="ABIERTA"),
        s.entorno.crear_jornada(),
    ]
    for lineas, momento, vendedor, sin_conexion, iva, se_anula in ventas:
        venta = sembrar_venta(
            sesion,
            s,
            vendedor_id=vendedores[vendedor],
            occurred_at=_momento(momento),
            lineas=[
                LineaDePrueba(
                    neto=_importe(neto),
                    costo_total=_importe(neto // 2) if con_costo else None,
                    cantidad_base=cantidad * 6,
                )
                for neto, con_costo, cantidad in lineas
            ],
            modo_confirmacion="OFFLINE" if sin_conexion else "ONLINE",
            jornada_id=jornadas[vendedor] if sin_conexion else None,
            iva=_importe(iva),
        )
        if se_anula:
            anular_venta(sesion, s, venta.venta_id, anulada_en=_momento(momento))


def _del_periodo(sesion: Session, s: Sesion, estado: str) -> tuple[int, Decimal, Decimal, Decimal]:
    """Cantidad, suma de `venta.total`, de `total_neto` y de `total_iva` de las ventas del estado
    dado en el período (la base como juez)."""
    fila = sesion.execute(
        text(
            "SELECT count(*), COALESCE(sum(total), 0), COALESCE(sum(total_neto), 0), "
            "COALESCE(sum(total_iva), 0) FROM venta WHERE organizacion_id = :o AND estado = :e "
            "AND occurred_at >= :i AND occurred_at < :f"
        ),
        {"o": s.entorno.org, "e": estado, "i": INICIO_UTC, "f": FIN_UTC},
    ).one()
    return int(fila[0]), Decimal(fila[1]), Decimal(fila[2]), Decimal(fila[3])


def _reporte(sesion: Session, s: Sesion) -> Any:
    return queries.obtener_reporte_de_ventas(
        s.entorno.org,
        sesion,
        RELOJ,
        desde=DESDE,
        hasta=HASTA,
        vendedor_id=None,
        ve_utilidad=True,
    )


# Escenario: «El reporte de ventas suma las ventas confirmadas del período» / «Las ventas anuladas
# se excluyen de los totales y se listan aparte».
@_PROPIEDAD
@given(st.lists(_VENTA, min_size=0, max_size=6))
def test_rep01_rep02_inv14_el_reporte_suma_las_confirmadas_y_las_anuladas_van_aparte(
    db_session: Session, ventas: list[Any]
) -> None:
    s = Sesion(db_session)
    _sembrar(db_session, s, ventas)

    reporte = _reporte(db_session, s)

    cantidad, total, neto, iva = _del_periodo(db_session, s, "CONFIRMADA")
    assert reporte.resumen.cantidad_ventas == cantidad
    assert reporte.resumen.total == total
    # INV-14: el total de la venta es neto + IVA, también sumado.
    assert reporte.resumen.importe_neto + reporte.resumen.importe_iva == reporte.resumen.total
    assert (reporte.resumen.importe_neto, reporte.resumen.importe_iva) == (neto, iva)
    # Lo mismo por vendedor y por día: la suma de las partes es el todo.
    assert sum(f.cifras.total for f in reporte.por_dia.filas) == total
    assert sum(f.cifras.total for f in reporte.por_vendedor) == total
    anuladas, total_anuladas, _, _ = _del_periodo(db_session, s, "ANULADA")
    assert reporte.anuladas.cantidad == anuladas
    assert reporte.anuladas.total == total_anuladas
    assert reporte.anuladas.ventas.total_filas == anuladas


# Escenario: «Las cifras de ventas pasadas no cambian con precios ni costos posteriores».
@_PROPIEDAD
@given(
    st.lists(_VENTA, min_size=1, max_size=5),
    st.integers(1, 9_999_999),
    st.integers(1, 9_999_999),
)
def test_rep05_inv10_las_cifras_pasadas_no_cambian_con_costos_ni_precios_posteriores(
    db_session: Session, ventas: list[Any], costo_nuevo: int, precio_nuevo: int
) -> None:
    s = Sesion(db_session)
    _sembrar(db_session, s, ventas)
    antes = _reporte(db_session, s)

    # Después: el costo promedio de todos los productos cambia y se publica un precio nuevo.
    org = s.entorno.org
    db_session.execute(
        text(
            "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
            "stock_total, actualizado_en) "
            "SELECT DISTINCT organizacion_id, producto_id, :c, 10, :m FROM venta_linea "
            "WHERE organizacion_id = :o "
            "ON CONFLICT (organizacion_id, producto_id) DO UPDATE SET costo_promedio = :c"
        ),
        {"o": org, "c": Decimal(costo_nuevo).scaleb(-6), "m": dia(12, 2)},
    )
    db_session.execute(
        text("UPDATE precio_item SET precio_final = :p WHERE organizacion_id = :o"),
        {"o": org, "p": Decimal(precio_nuevo).scaleb(-2)},
    )
    db_session.commit()

    despues = _reporte(db_session, s)

    assert despues.resumen == antes.resumen
    assert despues.por_dia == antes.por_dia
    assert despues.por_vendedor == antes.por_vendedor
    assert despues.por_producto == antes.por_producto
    assert despues.anuladas == antes.anuladas


_MOVIMIENTO = st.tuples(
    st.integers(0, 2),  # cuenta
    st.sampled_from(["VENTA", "COBRANZA"]),
    st.integers(1, 2_000_000),
)


# Escenario: «Cada saldo es la suma de los movimientos de la cuenta» (INV-13, CC-04).
@_PROPIEDAD
@given(st.lists(_MOVIMIENTO, min_size=0, max_size=12))
def test_inv13_cc04_cada_saldo_del_reporte_es_la_suma_de_los_movimientos_de_su_cuenta(
    db_session: Session, movimientos: list[tuple[int, str, int]]
) -> None:
    s = Sesion(db_session)
    clientes: list[UUID] = [s.entorno.cliente_id] + [
        sembrar_cliente_de_cartera(db_session, s, nombre=f"Cliente {uuid4().hex[:6]}")
        for _ in range(2)
    ]
    for indice, tipo, centavos in movimientos:
        mover_cuenta(db_session, s, "CLIENTE", clientes[indice], tipo, _importe(centavos))

    reporte = queries.obtener_saldos_de_clientes(
        s.entorno.org, db_session, saldo="TODOS", vendedor_id=None, estado=None, texto=None
    )

    por_cliente = {fila.cliente_id: fila.saldo for fila in reporte.clientes.filas}
    for cliente_id in clientes:
        assert por_cliente[cliente_id] == suma_del_libro(db_session, s, "CLIENTE", cliente_id)
    # Los totales son las sumas de los saldos positivos y negativos de lo mostrado.
    assert reporte.totales.adeudado == sum((v for v in por_cliente.values() if v > 0), Decimal(0))
    assert reporte.totales.a_favor == sum((v for v in por_cliente.values() if v < 0), Decimal(0))
