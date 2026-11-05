"""Change 24, tarea 18.1: propiedades de la rendición contra PostgreSQL real, con Hypothesis.

Para secuencias aleatorias de cargas al vehículo, ventas, anulaciones y una rendición con un
conteo arbitrario (lo que falte, lo que sobre y un producto fuera del conjunto), calculadas con SQL
en la base, al final:

- INV-12 (STK-04): el stock de cada producto contado es EXACTAMENTE lo contado, igual a la suma de
  sus movimientos en ese par; ningún saldo es negativo y `verificar_consistencia` no informa
  diferencias; sin diferencia no se escribe movimiento (RUT-06);
- RUT-07: el resumen cuadra: en cada línea `esperado = al_abrir + ingresos - ventas +
  anulaciones + otros`, y esos cinco números son los que el modelo de la secuencia calculó por su
  cuenta; `diferencia = contado - esperado`;
- INV-05: los libros solo crecen: después de cada paso, los movimientos de antes siguen estando
  con la misma cantidad (la rendición agrega, no cambia nada), y `rendicion` y `rendicion_linea`
  tienen una fila por rendición y por línea.

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la invariante, no de
concurrencia (esa confirma transacciones reales: `tests/concurrency/test_rendicion_concurrente.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.cobranzas import service as _cobranzas_service  # noqa: F401  (lector del resumen)
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import queries as stock_queries
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import StockInsuficienteError
from app.modules.stock.service import LineaContada, LineaDeMovimiento, LineaDeTransferencia
from app.modules.ventas import service as _ventas_service  # noqa: F401  (lector del resumen)
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_producto_sql, crear_ubicacion_sql

INICIO = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
CANTIDAD_DE_PRODUCTOS = 3  # el tercero queda fuera del conjunto salvo que algo lo toque
EXISTENCIA_DEL_DEPOSITO = 500

_PRODUCTO = st.integers(min_value=0, max_value=CANTIDAD_DE_PRODUCTOS - 1)
_OPERACION = st.one_of(
    st.tuples(st.just("carga"), _PRODUCTO, st.integers(1, 40)),
    st.tuples(st.just("venta"), _PRODUCTO, st.integers(1, 40)),
    st.tuples(st.just("anulacion"), _PRODUCTO, st.integers(1, 40)),
)
_SECUENCIA = st.lists(_OPERACION, min_size=0, max_size=12)
_APERTURA = st.lists(
    st.integers(0, 60), min_size=CANTIDAD_DE_PRODUCTOS, max_size=CANTIDAD_DE_PRODUCTOS
)
# Cómo se cuenta cada producto: igual al esperado, menos (faltante), más (sobrante).
_CONTEO = st.lists(
    st.tuples(st.sampled_from(["igual", "falta", "sobra"]), st.integers(1, 15)),
    min_size=CANTIDAD_DE_PRODUCTOS,
    max_size=CANTIDAD_DE_PRODUCTOS,
)

_PROPIEDAD = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class _RelojQueAvanza:
    """Un reloj que avanza un segundo en cada lectura: la ventana de la jornada separa lo
    anterior a su apertura de lo posterior (con un reloj fijo todo caería en el mismo instante)."""

    def __init__(self) -> None:
        self._momento = INICIO

    def now(self) -> datetime:
        self._momento += timedelta(seconds=1)
        return self._momento


class _Ruta:
    """Una organización con tres productos, un depósito con existencia, la camioneta con la
    apertura sembrada y la jornada de Juan abierta y entregada, y el modelo de lo que pasó."""

    def __init__(self, sesion: Session, apertura: list[int]) -> None:
        self.sesion = sesion
        self.reloj = _RelojQueAvanza()
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.productos = [
            crear_producto_sql(sesion, self.org, nombre=f"Producto {i}")
            for i in range(CANTIDAD_DE_PRODUCTOS)
        ]
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
        )
        for indice, cantidad in enumerate(apertura):
            self._ingresar(self.deposito, indice, EXISTENCIA_DEL_DEPOSITO)
            if cantidad:
                self._ingresar(self.camioneta, indice, cantidad)
        self.al_abrir = list(apertura)
        self.ingresos = [0] * CANTIDAD_DE_PRODUCTOS
        self.ventas = [0] * CANTIDAD_DE_PRODUCTOS
        self.anulaciones = [0] * CANTIDAD_DE_PRODUCTOS
        self.jornada_id = stock_service.abrir_jornada(
            self.org,
            sesion,
            self.reloj,
            ubicacion_id=self.camioneta,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=self.reloj.now(),
        ).id
        stock_service.entregar_jornada(
            self.org,
            sesion,
            self.reloj,
            jornada_id=self.jornada_id,
            occurred_at=INICIO,
            secuencia=1,
        )

    def _ingresar(self, ubicacion_id: UUID, producto: int, cantidad: int) -> None:
        stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            self.reloj,
            lineas=[
                LineaDeMovimiento(
                    producto_id=self.productos[producto],
                    ubicacion_id=ubicacion_id,
                    cantidad_base=cantidad,
                    tipo="COMPRA",
                    costo_unitario=Decimal("1000.000000"),
                    origen_tipo="COMPRA",
                    origen_id=uuid4(),
                )
            ],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=INICIO,
        )

    def _linea_de_venta(
        self, producto: int, cantidad_con_signo: int, tipo: str
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=self.productos[producto],
            ubicacion_id=self.camioneta,
            cantidad_base=cantidad_con_signo,
            tipo=tipo,
            costo_unitario=None if cantidad_con_signo < 0 else Decimal("1000"),
            origen_tipo="VENTA",
            origen_id=uuid4(),
        )

    def aplicar(self, operacion: tuple[str, int, int]) -> bool:
        """Aplica la operación en un `SAVEPOINT`; `False` si el libro la rechazó por falta de
        stock (sin efectos, INV-01)."""
        nombre, producto, cantidad = operacion
        try:
            with self.sesion.begin_nested():
                if nombre == "carga":
                    stock_service.transferir(
                        self.org,
                        self.sesion,
                        self.reloj,
                        ubicacion_origen_id=self.deposito,
                        ubicacion_destino_id=self.camioneta,
                        lineas=[LineaDeTransferencia(self.productos[producto], cantidad)],
                        observacion=None,
                        usuario_id=self.usuario_id,
                        dispositivo_id=self.dispositivo_id,
                        operation_id=uuid4(),
                        occurred_at=INICIO,
                    )
                else:
                    firmada = -cantidad if nombre == "venta" else cantidad
                    stock_service.registrar_movimientos(
                        self.org,
                        self.sesion,
                        self.reloj,
                        lineas=[
                            self._linea_de_venta(
                                producto,
                                firmada,
                                "VENTA" if nombre == "venta" else "ANULACION_VENTA",
                            )
                        ],
                        usuario_id=self.usuario_id,
                        dispositivo_id=self.dispositivo_id,
                        operation_id=uuid4(),
                        occurred_at=INICIO,
                    )
        except StockInsuficienteError:
            event(f"{nombre} rechazada")
            return False
        event(f"{nombre} aplicada")
        {"carga": self.ingresos, "venta": self.ventas, "anulacion": self.anulaciones}[nombre][
            producto
        ] += cantidad
        return True

    # --- lecturas SQL -------------------------------------------------------------------

    def libro(self) -> dict[UUID, tuple[UUID, int]]:
        """`id -> (ubicación, cantidad)` de todo el libro de la organización."""
        filas = self.sesion.execute(
            text(
                "SELECT id, ubicacion_id, cantidad_base FROM stock_movimiento "
                "WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        return {fila[0]: (fila[1], int(fila[2])) for fila in filas}

    def saldo_del_libro(self, producto: int, ubicacion_id: UUID) -> int:
        ((suma,),) = self.sesion.execute(
            text(
                "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_movimiento "
                "WHERE organizacion_id = :o AND producto_id = :p AND ubicacion_id = :u"
            ),
            {"o": self.org, "p": self.productos[producto], "u": ubicacion_id},
        ).all()
        return int(suma)

    def saldo_materializado(self, producto: int, ubicacion_id: UUID) -> int:
        fila = self.sesion.execute(
            text(
                "SELECT cantidad_base FROM stock_saldo WHERE organizacion_id = :o "
                "AND producto_id = :p AND ubicacion_id = :u"
            ),
            {"o": self.org, "p": self.productos[producto], "u": ubicacion_id},
        ).first()
        return 0 if fila is None else int(fila[0])

    def contar(self) -> int:
        ((cuantas,),) = self.sesion.execute(
            text("SELECT count(*) FROM rendicion WHERE organizacion_id = :o"), {"o": self.org}
        ).all()
        return int(cuantas)


def _conteo_de(ruta: _Ruta, forma: list[tuple[str, int]]) -> list[int]:
    """Lo contado de cada producto a partir de lo esperado (el saldo del libro) y de la forma."""
    contado: list[int] = []
    for producto, (como, cantidad) in enumerate(forma):
        esperado = ruta.saldo_del_libro(producto, ruta.camioneta)
        if como == "falta":
            contado.append(max(0, esperado - cantidad))
        elif como == "sobra":
            contado.append(esperado + cantidad)
        else:
            contado.append(esperado)
    return contado


@_PROPIEDAD
@given(_APERTURA, _SECUENCIA, _CONTEO)
def test_inv12_rut07_inv05_el_stock_es_lo_contado_el_resumen_cuadra_y_los_libros_solo_crecen(
    db_session: Session,
    apertura: list[int],
    secuencia: list[tuple[str, int, int]],
    forma: list[tuple[str, int]],
) -> None:
    savepoint = db_session.begin_nested()
    try:
        ruta = _Ruta(db_session, apertura)
        anterior = ruta.libro()
        for operacion in secuencia:
            ruta.aplicar(operacion)
            ahora = ruta.libro()
            # INV-05: lo que ya estaba sigue estando, igual (el libro solo se escribe de a filas).
            assert all(ahora.get(clave) == valor for clave, valor in anterior.items())
            anterior = ahora

        esperados = [ruta.saldo_del_libro(p, ruta.camioneta) for p in range(CANTIDAD_DE_PRODUCTOS)]
        contados = _conteo_de(ruta, forma)
        stock_service.rendir_jornada(
            ruta.org,
            db_session,
            ruta.reloj,
            jornada_id=ruta.jornada_id,
            usuario_id=ruta.usuario_id,
            dispositivo_id=ruta.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=INICIO,
            lineas=[
                LineaContada(ruta.productos[p], contados[p], esperados[p])
                for p in range(CANTIDAD_DE_PRODUCTOS)
            ],
            observacion=None,
        )

        # INV-12 y la rendición: el stock de cada producto contado ES lo contado, y es la suma de
        # sus movimientos; no queda ningún saldo negativo ni diferencia de consistencia.
        for producto in range(CANTIDAD_DE_PRODUCTOS):
            assert ruta.saldo_materializado(producto, ruta.camioneta) == contados[producto]
            assert ruta.saldo_del_libro(producto, ruta.camioneta) == contados[producto]
        assert stock_service.verificar_consistencia(ruta.org, db_session) == []
        con_diferencia = sum(1 for p in range(CANTIDAD_DE_PRODUCTOS) if contados[p] != esperados[p])
        agregados = [
            fila
            for fila in db_session.execute(
                text(
                    "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o "
                    "AND tipo = 'DIFERENCIA_RENDICION'"
                ),
                {"o": ruta.org},
            ).all()
        ]
        assert int(agregados[0][0]) == con_diferencia  # solo lo que difiere escribe en el libro
        assert ruta.contar() == 1  # INV-05: una rendición por jornada

        # RUT-07: el resumen cuadra y es el del modelo de la secuencia.
        resumen = stock_queries.obtener_resumen_de_jornada(
            ruta.org, db_session, jornada_id=ruta.jornada_id, con_costos=True
        )
        assert resumen.con_conteo
        por_producto = {linea.producto_id: linea for linea in resumen.lineas}
        for producto in range(CANTIDAD_DE_PRODUCTOS):
            linea = por_producto.get(ruta.productos[producto])
            if linea is None:  # fuera del conjunto: sin saldo y sin movimientos en la ventana
                assert esperados[producto] == 0
                assert ruta.al_abrir[producto] == 0
                continue
            assert linea.esperado == (
                linea.al_abrir + linea.ingresos - linea.ventas + linea.anulaciones + linea.otros
            )
            assert linea.al_abrir == ruta.al_abrir[producto]
            assert linea.ingresos == ruta.ingresos[producto]
            assert linea.ventas == ruta.ventas[producto]
            assert linea.anulaciones == ruta.anulaciones[producto]
            assert linea.esperado == esperados[producto]
            assert linea.contado == contados[producto]
            assert linea.diferencia == contados[producto] - esperados[producto]

        # INV-05: la rendición ya escrita no se vuelve a escribir y el libro solo creció.
        final = ruta.libro()
        assert all(final.get(clave) == valor for clave, valor in anterior.items())
    finally:
        savepoint.rollback()
