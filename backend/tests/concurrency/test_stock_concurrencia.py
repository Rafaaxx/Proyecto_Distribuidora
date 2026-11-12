"""Change 09, tarea 9.6: concurrencia real de `stock` y `costeo` contra PostgreSQL
real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el
mismo arnés que `test_cuentas_corrientes_concurrencia.py`: cada hilo tiene su propia
conexión/sesión, confirma su propia transacción y arranca junto a los otros en una
`threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4).

Escenarios de `specs/stock/libro-de-stock`, `specs/costeo/costo-promedio` y
`specs/stock/ubicaciones`:

- dos o más ingresos simultáneos del mismo producto y ubicación: el saldo, el stock
  total y el promedio son los del cálculo serial (INV-12, CST-11, `design.md` D9);
- la primera fila de saldo y de costo se crea una sola vez (`INSERT ... ON CONFLICT
  DO NOTHING`, D10);
- dos comandos que tocan los mismos productos en orden inverso no se interbloquean
  (orden global de bloqueo, `02` §7.3, ADR-015);
- dos egresos simultáneos sobre un saldo que alcanza para uno: exactamente uno se
  aplica y el saldo no queda negativo (STK-05, `02` §7.4);
- productos distintos en una misma ubicación no se esperan entre sí;
- desactivar una ubicación frente a un ingreso simultáneo se serializa (D8).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.modules.costeo import service as costeo_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    StockInsuficienteError,
    UbicacionConStockError,
    UbicacionInactivaError,
)
from app.modules.stock.service import LineaDeMovimiento
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_producto_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ESPERA_MAXIMA = 30
MEDIO_MILLONESIMO = Decimal("0.0000005")


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones: simula un
    worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


class _Escenario:
    """Una organización confirmada con tres productos, un depósito y un vehículo."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
            self.producto_a = crear_producto_sql(sesion, self.org, nombre="Producto A")
            self.producto_b = crear_producto_sql(sesion, self.org, nombre="Producto B")
            self.producto_c = crear_producto_sql(sesion, self.org, nombre="Producto C")
            self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
            self.vehiculo = crear_ubicacion_sql(
                sesion, self.org, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
            )
            sesion.commit()
        finally:
            sesion.close()

    def ingresar(
        self,
        sesion: Session,
        *lineas: tuple[UUID, int, str],
        ubicacion_id: UUID | None = None,
    ) -> None:
        """Un comando de ingresos: `(producto_id, cantidad, costo)` por línea."""
        self._registrar(
            sesion,
            [
                LineaDeMovimiento(
                    producto_id=producto_id,
                    ubicacion_id=ubicacion_id or self.deposito,
                    cantidad_base=cantidad,
                    tipo="COMPRA",
                    costo_unitario=costo,
                    origen_tipo="COMPRA",
                    origen_id=uuid4(),
                )
                for producto_id, cantidad, costo in lineas
            ],
        )

    def egresar(self, sesion: Session, producto_id: UUID, cantidad: int) -> None:
        self._registrar(
            sesion,
            [
                LineaDeMovimiento(
                    producto_id=producto_id,
                    ubicacion_id=self.deposito,
                    cantidad_base=-cantidad,
                    tipo="VENTA",
                    costo_unitario=None,
                    origen_tipo="VENTA",
                    origen_id=uuid4(),
                )
            ],
        )

    def _registrar(self, sesion: Session, lineas: list[LineaDeMovimiento]) -> None:
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

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def saldo(self, producto_id: UUID, ubicacion_id: UUID | None = None) -> int:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo "
            "WHERE organizacion_id = :o AND producto_id = :p AND ubicacion_id = :u",
            p=producto_id,
            u=ubicacion_id or self.deposito,
        )
        assert isinstance(saldo, int | Decimal)
        return int(saldo)

    def suma_del_libro(self, producto_id: UUID) -> int:
        ((suma,),) = self.leer(
            "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_movimiento "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto_id,
        )
        assert isinstance(suma, int | Decimal)
        return int(suma)

    def stock_total(self, producto_id: UUID) -> int:
        ((total,),) = self.leer(
            "SELECT stock_total FROM costo_producto "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto_id,
        )
        assert isinstance(total, int)
        return total

    def promedio(self, producto_id: UUID) -> Decimal | None:
        sesion = _sesion_independiente(self.database_url)
        try:
            return costeo_service.obtener_promedio(self.org, sesion, producto_id)
        finally:
            sesion.close()

    def cantidad_de_filas(self, tabla: str, producto_id: UUID) -> int:
        ((cantidad,),) = self.leer(
            f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o AND producto_id = :p",  # noqa: S608
            p=producto_id,
        )
        assert isinstance(cantidad, int)
        return cantidad

    def diferencias(self) -> list[object]:
        sesion = _sesion_independiente(self.database_url)
        try:
            return list(stock_service.verificar_consistencia(self.org, sesion))
        finally:
            sesion.close()

    def ubicacion_activa(self, ubicacion_id: UUID) -> bool:
        ((activo,),) = self.leer(
            "SELECT activo FROM ubicacion WHERE organizacion_id = :o AND id = :u", u=ubicacion_id
        )
        assert isinstance(activo, bool)
        return activo


def _en_paralelo(
    database_url: str, trabajos: list[Callable[[Session], None]]
) -> tuple[dict[int, str], dict[int, BaseException]]:
    """Corre cada trabajo en su hilo y su sesión, todos arrancando juntos. El
    trabajo confirma o levanta; el resultado es `"OK"` o el nombre del error."""
    barrera = threading.Barrier(len(trabajos))
    resultados: dict[int, str] = {}
    errores: dict[int, BaseException] = {}

    def _worker(indice: int) -> None:
        sesion = _sesion_independiente(database_url)
        try:
            barrera.wait(timeout=10)
            trabajos[indice](sesion)
            sesion.commit()
            resultados[indice] = "OK"
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            errores[indice] = error
            resultados[indice] = type(error).__name__
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(len(trabajos))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA)
    assert not any(hilo.is_alive() for hilo in hilos), (
        "Un hilo quedó colgado (posible interbloqueo real)."
    )
    return resultados, errores


class TestIngresosSimultaneosDelMismoProductoYUbicacion:
    """INV-12, CST-11, `design.md` D9: todo ingreso bloquea primero la fila de costo
    del producto y después la de saldo, así que los ingresos simultáneos se
    serializan y el resultado es el del cálculo serial."""

    @pytest.mark.parametrize("cantidad_de_hilos", [2, 6])
    def test_el_saldo_el_total_y_el_promedio_son_los_del_calculo_serial(
        self, database_url: str, _engine_de_sesion, cantidad_de_hilos: int
    ) -> None:
        escenario = _Escenario(database_url)
        # Cada hilo ingresa 10 unidades a un costo distinto: 1000, 1100, 1200, ...
        costos = [Decimal(1000 + 100 * i) for i in range(cantidad_de_hilos)]
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion, costo=costo: escenario.ingresar(
                sesion, (escenario.producto_a, 10, str(costo))
            )
            for costo in costos
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"
        unidades = 10 * cantidad_de_hilos
        assert escenario.saldo(escenario.producto_a) == unidades
        assert escenario.suma_del_libro(escenario.producto_a) == unidades
        assert escenario.stock_total(escenario.producto_a) == unidades
        # Con el mismo peso en cada ingreso, el promedio es el costo medio; el orden
        # de llegada solo puede desviarlo por el redondeo a 6 decimales de cada paso.
        esperado = sum(costos) / cantidad_de_hilos
        promedio = escenario.promedio(escenario.producto_a)
        assert promedio is not None
        assert abs(promedio - esperado) <= cantidad_de_hilos * MEDIO_MILLONESIMO
        assert escenario.cantidad_de_filas("costo_producto_mov", escenario.producto_a) == (
            cantidad_de_hilos
        )
        assert escenario.diferencias() == []

    @pytest.mark.parametrize("cantidad_de_hilos", [2, 8])
    def test_ingresos_simultaneos_en_dos_ubicaciones_dan_un_solo_promedio(
        self, database_url: str, _engine_de_sesion, cantidad_de_hilos: int
    ) -> None:
        """CST-10: el promedio es del producto en la organización, no de la
        ubicación. Los ingresos a la vez en el depósito y en el vehículo no comparten
        fila de saldo: solo la fila de costo los serializa (un promedio perdido lo
        delataría). Con 2 hilos, 60 a 1000 y 60 a 1100: 1050."""
        escenario = _Escenario(database_url)
        costos = [Decimal(1000 + 100 * i) for i in range(cantidad_de_hilos)]
        ubicaciones = [escenario.deposito, escenario.vehiculo]
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion, costo=costo, ubicacion=ubicaciones[i % 2]: escenario.ingresar(
                sesion, (escenario.producto_a, 60, str(costo)), ubicacion_id=ubicacion
            )
            for i, costo in enumerate(costos)
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"
        promedio = escenario.promedio(escenario.producto_a)
        assert promedio is not None
        assert abs(promedio - sum(costos) / cantidad_de_hilos) <= (
            cantidad_de_hilos * MEDIO_MILLONESIMO
        )
        if cantidad_de_hilos == 2:
            assert promedio == Decimal("1050.000000")
        assert escenario.stock_total(escenario.producto_a) == 60 * cantidad_de_hilos
        assert escenario.saldo(escenario.producto_a, escenario.deposito) == (
            60 * cantidad_de_hilos // 2
        )
        assert escenario.saldo(escenario.producto_a, escenario.vehiculo) == (
            60 * cantidad_de_hilos // 2
        )
        assert escenario.diferencias() == []


class TestPrimeraFilaDeSaldoYDeCostoBajoConcurrencia:
    """`INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE` (D10): dos
    primeros ingresos simultáneos de un producto y una ubicación nuevos no chocan en
    las claves de `costo_producto` ni de `stock_saldo` y dejan una sola fila de
    cada una."""

    def test_la_primera_fila_de_saldo_y_la_de_costo_se_crean_una_sola_vez(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        assert escenario.cantidad_de_filas("stock_saldo", escenario.producto_a) == 0
        assert escenario.cantidad_de_filas("costo_producto", escenario.producto_a) == 0
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: escenario.ingresar(sesion, (escenario.producto_a, 10, "1000")),
            lambda sesion: escenario.ingresar(sesion, (escenario.producto_a, 20, "1000")),
            lambda sesion: escenario.ingresar(sesion, (escenario.producto_a, 30, "1000")),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de_filas("stock_saldo", escenario.producto_a) == 1
        assert escenario.cantidad_de_filas("costo_producto", escenario.producto_a) == 1
        assert escenario.saldo(escenario.producto_a) == 60
        assert escenario.promedio(escenario.producto_a) == Decimal("1000.000000")
        assert escenario.cantidad_de_filas("stock_movimiento", escenario.producto_a) == 3
        assert escenario.diferencias() == []


class TestProductosEnOrdenInversoSinInterbloqueo:
    """`02` §7.3, ADR-015, `design.md` D9: `stock` ordena los productos antes de
    bloquear, así que dos comandos que tocan los mismos productos en orden inverso
    no se esperan en círculo."""

    @pytest.mark.parametrize("repeticiones", [1, 5])
    def test_dos_comandos_con_los_mismos_productos_en_orden_inverso_terminan(
        self, database_url: str, _engine_de_sesion, repeticiones: int
    ) -> None:
        escenario = _Escenario(database_url)
        a, b = escenario.producto_a, escenario.producto_b

        for _ in range(repeticiones):
            trabajos: list[Callable[[Session], None]] = [
                lambda sesion: escenario.ingresar(sesion, (a, 10, "1000"), (b, 10, "2000")),
                lambda sesion: escenario.ingresar(sesion, (b, 10, "2000"), (a, 10, "1000")),
                lambda sesion: escenario.ingresar(sesion, (a, 10, "1000"), (b, 10, "2000")),
                lambda sesion: escenario.ingresar(sesion, (b, 10, "2000"), (a, 10, "1000")),
            ]

            resultados, errores = _en_paralelo(database_url, trabajos)

            assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"

        total = 40 * repeticiones
        assert escenario.saldo(a) == total
        assert escenario.saldo(b) == total
        assert escenario.stock_total(a) == total
        assert escenario.promedio(a) == Decimal("1000.000000")
        assert escenario.promedio(b) == Decimal("2000.000000")
        assert escenario.diferencias() == []


class TestEgresosSimultaneosSobreUnSaldoQueAlcanzaParaUno:
    """STK-05, `02` §7.4: el `UPDATE ... WHERE cantidad_base >= :q` decide con la
    fila bloqueada, así que de dos egresos de 60 sobre un saldo de 100 se aplica
    exactamente uno y el saldo no queda negativo."""

    def test_se_aplica_uno_solo_y_el_otro_se_rechaza(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            escenario.ingresar(sesion, (escenario.producto_a, 100, "1000"))
            sesion.commit()
        finally:
            sesion.close()
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: escenario.egresar(sesion, escenario.producto_a, 60),
            lambda sesion: escenario.egresar(sesion, escenario.producto_a, 60),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == ["OK", StockInsuficienteError.__name__], (
            f"{resultados}, errores={errores}"
        )
        assert escenario.saldo(escenario.producto_a) == 40
        assert escenario.stock_total(escenario.producto_a) == 40
        assert escenario.suma_del_libro(escenario.producto_a) == 40
        assert escenario.promedio(escenario.producto_a) == Decimal("1000.000000")
        assert escenario.diferencias() == []


class TestProductosDistintosNoSeEsperan:
    """El bloqueo es por producto y ubicación: una transacción abierta con las filas
    de un producto tomadas no frena el ingreso de otro producto en la misma
    ubicación (la ubicación se toma `FOR SHARE`, que no choca con otra igual)."""

    def test_un_ingreso_de_otro_producto_no_espera_a_una_transaccion_abierta(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        a_tomo_sus_filas = threading.Event()
        b_confirmo = threading.Event()
        resultado_de_b: dict[str, object] = {}

        def _hilo_a() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                escenario.ingresar(sesion, (escenario.producto_a, 10, "1000"))
                a_tomo_sus_filas.set()
                # Mantiene la transacción abierta hasta que B haya terminado.
                resultado_de_b["b_termino_antes_que_a_confirmara"] = b_confirmo.wait(
                    timeout=ESPERA_MAXIMA
                )
                sesion.commit()
            finally:
                a_tomo_sus_filas.set()
                sesion.close()

        def _hilo_b() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                assert a_tomo_sus_filas.wait(timeout=10)
                escenario.ingresar(sesion, (escenario.producto_b, 20, "2000"))
                sesion.commit()
                b_confirmo.set()
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_hilo_a), threading.Thread(target=_hilo_b)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=ESPERA_MAXIMA + 10)

        assert not any(hilo.is_alive() for hilo in hilos)
        assert resultado_de_b["b_termino_antes_que_a_confirmara"] is True, (
            "B tuvo que esperar a A: el bloqueo no es por producto."
        )
        assert escenario.saldo(escenario.producto_a) == 10
        assert escenario.saldo(escenario.producto_b) == 20
        assert escenario.diferencias() == []


class TestDesactivarUnaUbicacionContraUnIngresoSimultaneo:
    """STK-02, D8: desactivar una ubicación toma la fila `FOR UPDATE` y un ingreso la
    toma `FOR SHARE`, así que se serializan. Hay dos órdenes posibles y los dos son
    correctos; el que no puede ocurrir es una ubicación inactiva con stock. Se repite
    para ejercer las dos entradas de la carrera."""

    @staticmethod
    def _desactivar(escenario: _Escenario, sesion: Session) -> None:
        stock_service.modificar_ubicacion(
            escenario.org,
            sesion,
            RELOJ,
            ubicacion_id=escenario.vehiculo,
            nombre="Camioneta",
            tipo="VEHICULO",
            requiere_toma=True,
            activo=False,
            actor_id=None,
        )

    def test_nunca_queda_una_ubicacion_inactiva_con_stock(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        for _ in range(8):
            self._una_vez(database_url)

    def _una_vez(self, database_url: str) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: self._desactivar(escenario, sesion),
            lambda sesion: escenario.ingresar(
                sesion, (escenario.producto_a, 10, "1000"), ubicacion_id=escenario.vehiculo
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        inactiva = not escenario.ubicacion_activa(escenario.vehiculo)
        stock = escenario.saldo(escenario.producto_a, escenario.vehiculo)
        assert not (inactiva and stock > 0), f"{resultados}, errores={errores}"
        if inactiva:
            # Ganó la desactivación: el ingreso se rechazó sin dejar rastro.
            assert resultados == {0: "OK", 1: UbicacionInactivaError.__name__}
            assert stock == 0
        else:
            # Ganó el ingreso: la desactivación se rechazó por tener stock.
            assert resultados == {0: UbicacionConStockError.__name__, 1: "OK"}
            assert stock == 10
        assert escenario.diferencias() == []
