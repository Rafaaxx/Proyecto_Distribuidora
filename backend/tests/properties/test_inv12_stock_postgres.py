"""INV-12 contra PostgreSQL real, con Hypothesis (change 09, tarea 9.2).

INV-12 (`docs/01` §20, STK-04): el stock de cada producto y ubicación es igual a
la suma de sus movimientos. Acá se prueba con la base y el servicio reales: para
secuencias arbitrarias de movimientos de varias líneas sobre dos productos y tres
ubicaciones, registradas por `stock_service.registrar_movimientos`, al final:

- `stock_saldo` es igual a la suma SQL de `stock_movimiento` en cada par;
- `costo_producto.stock_total` es igual a la suma de los saldos del producto;
- ningún saldo es negativo (STK-05: un egreso que no alcanza se rechaza entero);
- `verificar_consistencia` no devuelve diferencias.

Los comandos que se rechazan por `STOCK_INSUFICIENTE` quedan sin efecto alguno
(INV-01): una línea que se aplicó antes de la que falló se deshace con ella.

INV-01: una falla inyectada a mitad de un comando de dos líneas deshace el
movimiento, el saldo y el costo juntos; lo confirmado antes queda intacto.

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la
invariante, no de concurrencia (esa confirma transacciones reales, tarea 9.6). La
contraparte de dominio puro es `test_inv12_stock_dominio.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.costeo import service as costeo_service
from app.modules.stock import repository as stock_repository
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import StockInsuficienteError
from app.modules.stock.service import LineaDeMovimiento
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_producto_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

# (indice de producto, indice de ubicación, cantidad con signo, costo en micro-unidades)
type Linea = tuple[int, int, int, int]

_CANTIDADES = st.integers(min_value=-40, max_value=60).filter(lambda n: n != 0)
_LINEAS = st.tuples(
    st.integers(min_value=0, max_value=1),
    st.integers(min_value=0, max_value=2),
    _CANTIDADES,
    st.integers(min_value=1, max_value=5_000_000_000),
)
_COMANDOS = st.lists(st.lists(_LINEAS, min_size=1, max_size=3), min_size=1, max_size=15)

_PROPIEDAD = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class _FallaInyectada(Exception):
    pass


class _Mundo:
    """Una organización con dos productos y tres ubicaciones, creada dentro del
    `SAVEPOINT` del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.productos = [
            crear_producto_sql(sesion, self.org, nombre=f"Producto {i}") for i in range(2)
        ]
        self.ubicaciones = [
            crear_ubicacion_sql(sesion, self.org, nombre=f"Ubicación {i}") for i in range(3)
        ]

    def lineas(self, comando: list[Linea]) -> list[LineaDeMovimiento]:
        return [
            LineaDeMovimiento(
                producto_id=self.productos[producto],
                ubicacion_id=self.ubicaciones[ubicacion],
                cantidad_base=cantidad,
                tipo="COMPRA" if cantidad > 0 else "VENTA",
                costo_unitario=(Decimal(micro) / 1_000_000) if cantidad > 0 else None,
                origen_tipo="COMPRA" if cantidad > 0 else "VENTA",
                origen_id=uuid4(),
            )
            for producto, ubicacion, cantidad, micro in comando
        ]

    def registrar(self, comando: list[Linea]) -> bool:
        """Registra el comando. `False` si se rechazó por stock insuficiente (sin
        efectos); cualquier otra falla se propaga."""
        try:
            with self.sesion.begin_nested():
                stock_service.registrar_movimientos(
                    self.org,
                    self.sesion,
                    RELOJ,
                    lineas=self.lineas(comando),
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    operation_id=uuid4(),
                    occurred_at=MOMENTO,
                )
        except StockInsuficienteError:
            return False
        return True

    def suma_sql_del_libro(self) -> dict[tuple[UUID, UUID], int]:
        filas = self.sesion.execute(
            text(
                "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
                "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
            ),
            {"o": self.org},
        ).all()
        return {(fila[0], fila[1]): int(fila[2]) for fila in filas}

    def saldos_materializados(self) -> dict[tuple[UUID, UUID], int]:
        filas = self.sesion.execute(
            text(
                "SELECT producto_id, ubicacion_id, cantidad_base FROM stock_saldo "
                "WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        return {(fila[0], fila[1]): int(fila[2]) for fila in filas}

    def verificar_la_invariante(self) -> None:
        libro = self.suma_sql_del_libro()
        materializados = self.saldos_materializados()
        for clave in set(libro) | set(materializados):
            # Un par sin movimientos puede no tener fila de saldo (perezosa): su saldo es 0.
            assert materializados.get(clave, 0) == libro.get(clave, 0)
        assert all(saldo >= 0 for saldo in materializados.values())
        for (producto_id, ubicacion_id), suma in libro.items():
            assert (
                stock_service.obtener_saldo(
                    self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
                )
                == suma
            )
        por_producto: dict[UUID, int] = defaultdict(int)
        for (producto_id, _), suma in libro.items():
            por_producto[producto_id] += suma
        totales = costeo_service.obtener_stock_totales(self.org, self.sesion)
        for producto_id in self.productos:
            assert totales.get(producto_id, 0) == por_producto.get(producto_id, 0)
        assert stock_service.verificar_consistencia(self.org, self.sesion) == []


@_PROPIEDAD
@given(_COMANDOS)
def test_inv12_el_saldo_materializado_es_la_suma_sql_del_libro_en_cada_par(
    db_session: Session, comandos: list[list[Linea]]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for comando in comandos:
            mundo.registrar(comando)

        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()


@_PROPIEDAD
@given(_COMANDOS, st.lists(_LINEAS, min_size=2, max_size=3))
def test_inv12_inv01_una_falla_inyectada_a_mitad_de_un_comando_no_altera_lo_confirmado(
    db_session: Session, confirmados: list[list[Linea]], interrumpido: list[Linea]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for comando in confirmados:
            mundo.registrar(comando)
        antes = (mundo.suma_sql_del_libro(), mundo.saldos_materializados())
        totales_antes = costeo_service.obtener_stock_totales(mundo.org, db_session)

        real = stock_repository.insertar_movimiento
        llamadas = 0

        def _falla_en_la_segunda(*args: object, **kwargs: object) -> object:
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise _FallaInyectada
            return real(*args, **kwargs)  # type: ignore[arg-type]

        # Todas las líneas ingresan: con el primer movimiento ya aplicado (saldo y
        # costo) y el segundo a punto de insertarse, la falla tiene que llevarse
        # también lo primero.
        ingresos = [(p, u, abs(c), m) for p, u, c, m in interrumpido]
        with (
            patch.object(stock_repository, "insertar_movimiento", _falla_en_la_segunda),
            pytest.raises(_FallaInyectada),
            db_session.begin_nested(),
        ):
            stock_service.registrar_movimientos(
                mundo.org,
                db_session,
                RELOJ,
                lineas=mundo.lineas(ingresos),
                usuario_id=mundo.usuario_id,
                dispositivo_id=mundo.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )

        assert llamadas == 2
        assert (mundo.suma_sql_del_libro(), mundo.saldos_materializados()) == antes
        assert costeo_service.obtener_stock_totales(mundo.org, db_session) == totales_antes
        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()
