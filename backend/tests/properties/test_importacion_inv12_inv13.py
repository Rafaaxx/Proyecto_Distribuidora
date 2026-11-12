"""INV-12 e INV-13 después de una importación de puesta en marcha, contra PostgreSQL real
y con Hypothesis (change 10, tarea 7.3).

INV-12 (`docs/01` §20, STK-04): el stock de cada producto y ubicación es igual a la suma de
sus movimientos. INV-13 (CC-04): el saldo de cada cuenta es igual a la suma de sus
movimientos. Acá se prueba que los importadores de `STOCK_INICIAL` y `SALDOS_INICIALES`,
que escriben solo por los servicios de `stock` y `cuentas_corrientes`, mantienen ambas
invariantes para archivos arbitrarios: con ingresos, correcciones negativas, saldos de
clientes y proveedores en los dos sentidos, y también cuando algunas filas se rechazan
(`STOCK_INSUFICIENTE`: la fila rechazada no deja efecto parcial, su savepoint se revierte).

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la
invariante, no de concurrencia (esa confirma transacciones reales,
`tests/concurrency/test_importacion_concurrencia.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.clientes import service as clientes_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.importadores.base import ContextoDeImportacion
from app.modules.importacion.importadores.saldos_iniciales import importar_saldos_iniciales
from app.modules.importacion.importadores.stock_inicial import importar_stock_inicial
from app.modules.stock import service as stock_service
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_producto_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

# (producto, ubicación, cantidad con signo distinta de cero, costo en micro-unidades)
type LineaDeStock = tuple[int, int, int, int]
# (cuenta: 0-1 clientes, 2-3 proveedores; importe en centavos; sentido)
type LineaDeSaldo = tuple[int, int, bool]

_STOCK = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=1),
        st.integers(min_value=0, max_value=2),
        st.integers(min_value=-40, max_value=60).filter(lambda n: n != 0),
        st.integers(min_value=1, max_value=5_000_000_000),
    ),
    min_size=1,
    max_size=20,
)
_SALDOS = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=3),
        st.integers(min_value=1, max_value=99_999_999_999),
        st.booleans(),
    ),
    min_size=1,
    max_size=20,
)

_PROPIEDAD = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _con_coma(valor: Decimal) -> str:
    return format(valor, "f").replace(".", ",")


class _Mundo:
    """Una organización con dos productos, tres ubicaciones, dos clientes y dos
    proveedores, creada dentro del `SAVEPOINT` del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.productos = [
            crear_producto_sql(sesion, self.org, nombre=f"Producto {i}") for i in range(2)
        ]
        for i, producto_id in enumerate(self.productos):
            sesion.execute(
                text("UPDATE producto SET codigo = :c WHERE id = :id"),
                {"c": f"P{i}", "id": producto_id},
            )
        self.ubicaciones = [
            crear_ubicacion_sql(sesion, self.org, nombre=f"Ubicación {i}") for i in range(3)
        ]
        self.clientes = [
            clientes_service.crear_cliente(
                self.org,
                sesion,
                RELOJ,
                nombre=f"Cliente {i}",
                codigo=f"C{i}",
                razon_social=None,
                documento_tipo=None,
                documento_numero=None,
                direccion="San Martín 123",
                contacto="Pepe",
                telefono=None,
                email=None,
                estado_facturacion_default=None,
                actor_id=None,
            ).id
            for i in range(2)
        ]
        self.proveedores = [
            crear_proveedor(sesion, self.org, nombre=f"Proveedor {i}") for i in range(2)
        ]

    def contexto(self) -> ContextoDeImportacion:
        return ContextoDeImportacion(
            organizacion_id=self.org,
            sesion=self.sesion,
            reloj=RELOJ,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    def importar_stock(self, lineas: list[LineaDeStock]) -> None:
        filas = [
            FilaPlanilla(
                fila=numero,
                valores={
                    "ubicacion": f"Ubicación {ubicacion}",
                    "producto_codigo": f"P{producto}",
                    "cantidad_base": str(cantidad),
                    "costo_unitario": (
                        _con_coma(Decimal(micro).scaleb(-6)) if cantidad > 0 else ""
                    ),
                },
            )
            for numero, (producto, ubicacion, cantidad, micro) in enumerate(lineas, start=2)
        ]
        importar_stock_inicial(self.contexto(), filas)

    def importar_saldos(self, lineas: list[LineaDeSaldo]) -> None:
        filas = []
        for numero, (cuenta, centavos, aumenta) in enumerate(lineas, start=2):
            es_cliente = cuenta < 2
            filas.append(
                FilaPlanilla(
                    fila=numero,
                    valores={
                        "cuenta_tipo": "CLIENTE" if es_cliente else "PROVEEDOR",
                        "entidad": f"C{cuenta}" if es_cliente else f"Proveedor {cuenta - 2}",
                        "importe": _con_coma(Decimal(centavos).scaleb(-2)),
                        "sentido": "AUMENTA" if aumenta else "REDUCE",
                    },
                )
            )
        importar_saldos_iniciales(self.contexto(), filas)

    def verificar_inv12(self) -> None:
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
            assert (
                stock_service.obtener_saldo(
                    self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
                )
                == suma
            )
            assert suma >= 0
        assert stock_service.verificar_consistencia(self.org, self.sesion) == []

    def verificar_inv13(self) -> None:
        libro: dict[tuple[str, UUID], Decimal] = {
            (fila[0], fila[1]): fila[2]
            for fila in self.sesion.execute(
                text(
                    "SELECT cuenta_tipo, entidad_id, SUM(CASE sentido WHEN 'AUMENTA' "
                    "THEN importe ELSE -importe END) FROM cuenta_movimiento "
                    "WHERE organizacion_id = :o GROUP BY cuenta_tipo, entidad_id"
                ),
                {"o": self.org},
            ).all()
        }
        for (cuenta_tipo, entidad_id), suma in libro.items():
            assert (
                cuentas_service.obtener_saldo(
                    self.org, self.sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
                )
                == suma
            )
        assert cuentas_service.verificar_consistencia(self.org, self.sesion) == []


@_PROPIEDAD
@given(_STOCK)
def test_inv12_tras_importar_stock_el_saldo_es_la_suma_sql_del_libro(
    db_session: Session, lineas: list[LineaDeStock]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)

        mundo.importar_stock(lineas)

        mundo.verificar_inv12()
    finally:
        savepoint.rollback()


@_PROPIEDAD
@given(_SALDOS)
def test_inv13_tras_importar_saldos_el_saldo_es_la_suma_sql_de_los_movimientos(
    db_session: Session, lineas: list[LineaDeSaldo]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)

        mundo.importar_saldos(lineas)

        mundo.verificar_inv13()
    finally:
        savepoint.rollback()


@_PROPIEDAD
@given(_STOCK, _SALDOS)
def test_inv12_inv13_se_mantienen_con_las_dos_importaciones_juntas(
    db_session: Session, stock: list[LineaDeStock], saldos: list[LineaDeSaldo]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)

        mundo.importar_stock(stock)
        mundo.importar_saldos(saldos)

        mundo.verificar_inv12()
        mundo.verificar_inv13()
    finally:
        savepoint.rollback()


def test_el_mundo_de_la_propiedad_importa_de_verdad_y_no_vacuamente(db_session: Session) -> None:
    """Guarda contra una propiedad vacua: con filas válidas, las importaciones sí dejan
    movimientos y saldos, y las invariantes se verifican sobre ellos."""
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)

        mundo.importar_stock([(0, 0, 60, 1_000_000_000), (0, 0, -12, 1)])
        mundo.importar_saldos([(0, 15_000_000, True), (2, 8_000_000, True), (2, 500, False)])

        assert (
            stock_service.obtener_saldo(
                mundo.org,
                db_session,
                producto_id=mundo.productos[0],
                ubicacion_id=mundo.ubicaciones[0],
            )
            == 48
        )
        assert cuentas_service.obtener_saldo(
            mundo.org, db_session, cuenta_tipo="CLIENTE", entidad_id=mundo.clientes[0]
        ) == Decimal("150000.00")
        assert cuentas_service.obtener_saldo(
            mundo.org, db_session, cuenta_tipo="PROVEEDOR", entidad_id=mundo.proveedores[0]
        ) == Decimal("79995.00")
        mundo.verificar_inv12()
        mundo.verificar_inv13()
    finally:
        savepoint.rollback()
