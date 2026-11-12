"""Change 14, grupo 14 (tareas 14.1 y 14.2): concurrencia real de transferencias, ajustes y
sus anulaciones contra PostgreSQL real (Testcontainers, `READ COMMITTED`, `02` §7.1), con el
arnés de `test_stock_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su
propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay rollback
externo (`CLAUDE.md` §4) y cada prueba limpia lo confirmado al terminar.

Además de las carreras libres, los escenarios cuyo resultado depende del orden de llegada se
prueban en los DOS órdenes de forma determinista: `_encadenado` deja a la primera transacción
con sus bloqueos tomados y SIN confirmar, lanza la segunda, espera a que PostgreSQL la
muestre esperando un bloqueo (`pg_stat_activity`) y recién entonces confirma la primera. No
hay `sleep` para "dar tiempo": se espera una condición observable.

Escenarios de `specs/stock/transferencias`, `specs/stock/ajustes-de-stock`,
`specs/stock/administracion-de-stock` y `specs/costeo/costo-promedio`:

- INV-12, INV-15: transferencias opuestas con productos en orden inverso, sin interbloqueo;
  el saldo de cada par es la suma de su libro y el stock total no cambia;
- STK-05, `02` §7.4: dos transferencias por las últimas unidades, una aceptada y una
  `STOCK_INSUFICIENTE`, saldo nunca negativo;
- CST-12, CST-11: un ajuste y una compra del mismo producto, el ajuste no altera el promedio;
- STK-02, D8, ADR-038 punto 4: transferir hacia una ubicación que se desactiva;
- INV-06: el mismo `Operation-Id` en paralelo tiene un solo efecto;
- CAT-05, D4.2: desactivar un producto sin stock contra un movimiento que le ingresa unidades;
- D5 punto 8: dos anulaciones de la misma transferencia, anulación contra otra transferencia
  que saca las mismas unidades del destino, anulación de un ajuste contra una compra.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import ProductoConStockError
from app.modules.identidad import repository as identidad_repository
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import commands as stock_commands  # noqa: F401  (registra los handlers)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    ProductoInactivoError,
    StockInsuficienteError,
    TransferenciaYaAnuladaError,
    UbicacionConStockError,
    UbicacionInactivaError,
)
from app.modules.stock.service import LineaDeAjuste, LineaDeTransferencia
from app.modules.sync import service as sync_service
from tests.concurrency.test_stock_concurrencia import (
    ESPERA_MAXIMA,
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _Escenario,
    _sesion_independiente,
)
from tests.integration.stock_utiles import crear_motivo_sql, crear_producto_sql

PERMISOS_ADMINISTRADOR = frozenset(
    {"TRANSFERIR_STOCK", "AJUSTAR_STOCK", "ANULAR_TRANSFERENCIA", "PERMITIR_STOCK_NEGATIVO"}
)
PERMISOS_VENDEDOR = frozenset({"TRANSFERIR_STOCK"})
OK = "OK"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Mundo(_Escenario):
    """El escenario de stock (organización, tres productos, depósito y vehículo) más un
    usuario con permisos de transferir y ajustar, los motivos de los tres ámbitos y las
    operaciones de este change sobre una sesión dada (la transacción la confirma quien llama)."""

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            # El usuario del escenario base recibe los permisos del change (un segundo
            # `crear_usuario_y_dispositivo` en la misma organización puede chocar en el prefijo
            # de dispositivo, de solo dos caracteres hexadecimales al azar).
            self.admin_id = self.usuario_id
            self.admin_dispositivo_id = self.dispositivo_id
            ((rol_id,),) = sesion.execute(
                text("SELECT rol_id FROM usuario WHERE organizacion_id = :o AND id = :u"),
                {"o": self.org, "u": self.usuario_id},
            ).all()
            for permiso in sorted(PERMISOS_ADMINISTRADOR):
                identidad_repository.asignar_permiso_a_rol(
                    self.org, sesion, rol_id=rol_id, permiso_codigo=permiso
                )
            self.motivo_ajuste = crear_motivo_sql(sesion, self.org, ambito="AJUSTE_STOCK")
            self.motivo_anula_transferencia = crear_motivo_sql(
                sesion, self.org, ambito="ANULACION_TRANSFERENCIA"
            )
            self.motivo_anula_ajuste = crear_motivo_sql(sesion, self.org, ambito="ANULACION_AJUSTE")
            sesion.commit()
        finally:
            sesion.close()

    # --- armado de la situación (cada paso confirma en su propia sesión) --------------

    def sembrar(self, producto_id: UUID, ubicacion_id: UUID, cantidad: int, costo: str) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            self.ingresar(sesion, (producto_id, cantidad, costo), ubicacion_id=ubicacion_id)
            sesion.commit()
        finally:
            sesion.close()

    def vender(self, producto_id: UUID, cantidad: int) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            self.egresar(sesion, producto_id, cantidad)
            sesion.commit()
        finally:
            sesion.close()

    def producto_nuevo(self, nombre: str) -> UUID:
        sesion = _sesion_independiente(self.database_url)
        try:
            producto_id = crear_producto_sql(sesion, self.org, nombre=nombre)
            sesion.commit()
            return producto_id
        finally:
            sesion.close()

    def con_promedio_sin_saldo(self, producto_id: UUID, promedio: str) -> None:
        """Un producto con promedio vigente y SIN ninguna fila de saldo: su primer movimiento
        crea la primera fila de saldo (D4.2: el verificador de stock no la vería)."""
        sesion = _sesion_independiente(self.database_url)
        try:
            sesion.execute(
                text(
                    "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
                    "stock_total, actualizado_en) VALUES (:o, :p, :c, 0, :m)"
                ),
                {"o": self.org, "p": producto_id, "c": Decimal(promedio), "m": MOMENTO},
            )
            sesion.commit()
        finally:
            sesion.close()

    # --- operaciones del change, sobre la sesión del hilo ------------------------------

    def transferir(
        self,
        sesion: Session,
        origen: UUID,
        destino: UUID,
        *lineas: tuple[UUID, int],
        permitir_negativo: bool = False,
    ) -> UUID:
        resultado = stock_service.transferir(
            self.org,
            sesion,
            RELOJ,
            ubicacion_origen_id=origen,
            ubicacion_destino_id=destino,
            lineas=[LineaDeTransferencia(p, c) for p, c in lineas],
            observacion=None,
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            permitir_negativo=permitir_negativo,
        )
        return resultado.transferencia.id

    def ajustar(self, sesion: Session, ubicacion: UUID, *lineas: tuple[UUID, int]) -> UUID:
        resultado = stock_service.ajustar(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=ubicacion,
            motivo_id=self.motivo_ajuste,
            lineas=[LineaDeAjuste(p, c) for p, c in lineas],
            observacion=None,
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )
        return resultado.ajuste.id

    def anular_transferencia(self, sesion: Session, transferencia_id: UUID) -> None:
        stock_service.anular_transferencia(
            self.org,
            sesion,
            RELOJ,
            transferencia_id=transferencia_id,
            motivo_id=self.motivo_anula_transferencia,
            permisos=PERMISOS_ADMINISTRADOR,
            operation_id=uuid4(),
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            occurred_at=MOMENTO,
        )

    def anular_ajuste(self, sesion: Session, ajuste_id: UUID) -> None:
        stock_service.anular_ajuste(
            self.org,
            sesion,
            RELOJ,
            ajuste_id=ajuste_id,
            motivo_id=self.motivo_anula_ajuste,
            permitir_negativo=False,
            operation_id=uuid4(),
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            occurred_at=MOMENTO,
        )

    def desactivar_ubicacion(self, sesion: Session, ubicacion_id: UUID) -> None:
        stock_service.modificar_ubicacion(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=ubicacion_id,
            nombre="Camioneta",
            tipo="VEHICULO",
            requiere_toma=True,
            activo=False,
            actor_id=None,
        )

    def desactivar_producto(self, sesion: Session, producto_id: UUID) -> None:
        """`PRODUCTO_MODIFICAR` con `activo = false` y el resto del estado como está."""
        ((codigo, nombre, categoria, marca, proveedor, unidad, alicuota),) = sesion.execute(
            text(
                "SELECT codigo, nombre, categoria_id, marca_id, proveedor_id, unidad_base, "
                "alicuota_id FROM producto WHERE organizacion_id = :o AND id = :p"
            ),
            {"o": self.org, "p": producto_id},
        ).all()
        catalogo_service.modificar_producto(
            self.org,
            sesion,
            RELOJ,
            producto_id=producto_id,
            codigo=codigo,
            nombre=nombre,
            categoria_id=categoria,
            marca_id=marca,
            proveedor_id=proveedor,
            unidad_base=unidad,
            alicuota_id=alicuota,
            activo=False,
            actor_id=None,
        )

    # --- lecturas confirmadas -----------------------------------------------------------

    def producto_activo(self, producto_id: UUID) -> bool:
        ((activo,),) = self.leer(
            "SELECT activo FROM producto WHERE organizacion_id = :o AND id = :p", p=producto_id
        )
        assert isinstance(activo, bool)
        return activo

    def saldos_negativos(self) -> int:
        ((cuantos,),) = self.leer(
            "SELECT count(*) FROM stock_saldo WHERE organizacion_id = :o AND cantidad_base < 0"
        )
        assert isinstance(cuantos, int)
        return cuantos

    def cantidad(self, consulta: str, **parametros: object) -> int:
        ((cuantos,),) = self.leer(consulta, **parametros)
        assert isinstance(cuantos, int)
        return cuantos

    def movimientos_de_origen(self, origen_tipo: str, producto_id: UUID | None = None) -> int:
        if producto_id is None:
            return self.cantidad(
                "SELECT count(*) FROM stock_movimiento "
                "WHERE organizacion_id = :o AND origen_tipo = :t",
                t=origen_tipo,
            )
        return self.cantidad(
            "SELECT count(*) FROM stock_movimiento "
            "WHERE organizacion_id = :o AND origen_tipo = :t AND producto_id = :p",
            t=origen_tipo,
            p=producto_id,
        )

    def saldos_iguales_al_libro(self) -> None:
        """INV-12: cada par `stock_saldo` es la suma de su libro y cada `stock_total` la suma
        de los saldos del producto; `verificar_consistencia` no informa diferencias."""
        libro = self.leer(
            "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
            "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
        )
        for producto_id, ubicacion_id, suma in libro:
            assert isinstance(producto_id, UUID)
            assert isinstance(ubicacion_id, UUID)
            assert self.saldo(producto_id, ubicacion_id) == int(suma), (  # type: ignore[arg-type]
                "El saldo materializado difiere de la suma del libro."
            )
        productos = {fila[0] for fila in libro}
        for producto_id in productos:
            assert isinstance(producto_id, UUID)
            ((suma_saldos,),) = self.leer(
                "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo "
                "WHERE organizacion_id = :o AND producto_id = :p",
                p=producto_id,
            )
            assert self.stock_total(producto_id) == int(suma_saldos)  # type: ignore[arg-type]
        assert self.diferencias() == []


# --- arnés de órdenes de llegada deterministas ---------------------------------------


def _hay_alguien_esperando_un_bloqueo(database_url: str) -> bool:
    sesion = _sesion_independiente(database_url)
    try:
        cuantos = sesion.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
            )
        )
        return bool(cuantos)
    finally:
        sesion.close()


def _encadenado(
    database_url: str,
    primero: Callable[[Session], object],
    segundo: Callable[[Session], object],
) -> tuple[str, str]:
    """Orden de llegada forzado: `primero` toma sus bloqueos y NO confirma; `segundo` arranca y
    se queda esperando en la base (se observa en `pg_stat_activity`, sin dormir); entonces
    `primero` confirma. Devuelve el resultado de cada uno (`"OK"` o el nombre del error)."""
    primero_listo = threading.Event()
    soltar_al_primero = threading.Event()
    segundo_termino = threading.Event()
    resultados: dict[str, str] = {}

    def _hilo_primero() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            primero(sesion)
            primero_listo.set()
            assert soltar_al_primero.wait(timeout=ESPERA_MAXIMA)
            sesion.commit()
            resultados["primero"] = OK
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            resultados["primero"] = type(error).__name__
        finally:
            primero_listo.set()
            sesion.close()

    def _hilo_segundo() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            segundo(sesion)
            sesion.commit()
            resultados["segundo"] = OK
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            resultados["segundo"] = type(error).__name__
        finally:
            segundo_termino.set()
            sesion.close()

    hilo_primero = threading.Thread(target=_hilo_primero)
    hilo_segundo = threading.Thread(target=_hilo_segundo)
    hilo_primero.start()
    assert primero_listo.wait(timeout=ESPERA_MAXIMA)
    hilo_segundo.start()
    # El segundo, o bien queda esperando un bloqueo de la primera transacción, o bien termina
    # sin esperar (y la aserción de la prueba lo delatará). Nunca se libera al primero antes.
    for _ in range(int(ESPERA_MAXIMA * 50)):
        if segundo_termino.is_set() or _hay_alguien_esperando_un_bloqueo(database_url):
            break
        segundo_termino.wait(timeout=0.02)
    else:
        soltar_al_primero.set()
        pytest.fail("El segundo no terminó ni quedó esperando un bloqueo.")
    soltar_al_primero.set()
    hilo_primero.join(timeout=ESPERA_MAXIMA)
    hilo_segundo.join(timeout=ESPERA_MAXIMA)
    assert not (hilo_primero.is_alive() or hilo_segundo.is_alive()), (
        "Un hilo quedó colgado (posible interbloqueo real)."
    )
    return resultados["primero"], resultados["segundo"]


# --- 14.1 -----------------------------------------------------------------------------


class TestTransferenciasOpuestasSinInterbloqueo:
    """INV-12, INV-15, `02` §7.3, ADR-015, D9: `transferir` llama UNA vez a la puerta del libro,
    que ordena productos y saldos antes de bloquear; dos transferencias opuestas con los mismos
    dos productos pedidos en orden inverso no se esperan en círculo."""

    @pytest.mark.parametrize("repeticiones", [1, 6])
    def test_transferencias_opuestas_con_dos_productos_en_orden_inverso_terminan_y_cierran(
        self, database_url: str, _engine_de_sesion, repeticiones: int
    ) -> None:
        mundo = _Mundo(database_url)
        a, b = mundo.producto_a, mundo.producto_b
        for producto, costo in ((a, "1000"), (b, "2000")):
            mundo.sembrar(producto, mundo.deposito, 300, costo)
            mundo.sembrar(producto, mundo.vehiculo, 300, costo)

        for _ in range(repeticiones):
            trabajos: list[Callable[[Session], None]] = []
            for _ in range(2):
                trabajos.append(
                    lambda sesion: mundo.transferir(
                        sesion, mundo.deposito, mundo.vehiculo, (a, 10), (b, 10)
                    )
                )
                trabajos.append(
                    lambda sesion: mundo.transferir(
                        sesion, mundo.vehiculo, mundo.deposito, (b, 10), (a, 10)
                    )
                )

            resultados, errores = _en_paralelo(database_url, trabajos)

            assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"

        # Dos transferencias en cada sentido por ronda: el neto de cada ubicación es cero.
        for producto, promedio in ((a, "1000.000000"), (b, "2000.000000")):
            assert mundo.stock_total(producto) == 600  # INV-15
            assert mundo.promedio(producto) == Decimal(promedio)  # INV-15
            assert mundo.saldo(producto, mundo.deposito) == 300
            assert mundo.saldo(producto, mundo.vehiculo) == 300
        assert mundo.saldos_negativos() == 0
        mundo.saldos_iguales_al_libro()  # INV-12


class TestUltimasUnidadesDelOrigen:
    """STK-05, `02` §7.4, INV-12: el `UPDATE ... WHERE cantidad_base >= :q` decide con la fila
    bloqueada, así que de dos transferencias de 8 sobre un origen de 10 se acepta una y la
    otra es `STOCK_INSUFICIENTE`."""

    @pytest.mark.parametrize("hilos", [2, 5])
    def test_una_sola_transferencia_se_acepta_y_el_saldo_nunca_queda_negativo(
        self, database_url: str, _engine_de_sesion, hilos: int
    ) -> None:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 10, "1000")
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.transferir(
                sesion, mundo.deposito, mundo.vehiculo, (mundo.producto_a, 8)
            )
            for _ in range(hilos)
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted(
            [OK] + [StockInsuficienteError.__name__] * (hilos - 1)
        ), f"{resultados}, errores={errores}"
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == 2
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 8
        assert mundo.stock_total(mundo.producto_a) == 10
        assert mundo.saldos_negativos() == 0
        assert mundo.movimientos_de_origen("TRANSFERENCIA") == 2  # un solo par
        mundo.saldos_iguales_al_libro()


def _promedio_esperado(stock: int, promedio: str, cantidad: int, costo: str) -> Decimal:
    """CST-11 a mano: `(stock * promedio + cantidad * costo) / (stock + cantidad)` a 6 decimales."""
    bruto = (stock * Decimal(promedio) + cantidad * Decimal(costo)) / (stock + cantidad)
    return bruto.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class TestAjusteYCompraDelMismoProducto:
    """CST-12, CST-11, INV-12, D3: el ajuste mueve unidades al promedio vigente y no lo
    recalcula ni deja historia de costo; solo la compra lo hace. Como la compra pondera con el
    stock que ve, el resultado depende de quién llegó primero; en los dos órdenes el promedio
    final es el de la compra calculada sobre el stock que vio, y el ajuste nunca lo mueve."""

    def _escenario(self, database_url: str) -> _Mundo:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 100, "1000")
        return mundo

    def _verificar(self, mundo: _Mundo, delta: int, *, compra_primero: bool | None) -> None:
        a = mundo.producto_a
        filas = mundo.leer(
            "SELECT stock_anterior, promedio_nuevo FROM costo_producto_mov "
            "WHERE organizacion_id = :o AND producto_id = :p AND origen_tipo = 'COMPRA' "
            "AND stock_anterior > 0",
            p=a,
        )
        assert len(filas) == 1  # el ajuste no dejó historia de costo (CST-12)
        ((stock_visto, promedio_de_la_compra),) = filas
        assert stock_visto in {100, 100 + delta}
        if compra_primero is not None:
            assert (stock_visto == 100) is compra_primero
        assert promedio_de_la_compra == _promedio_esperado(int(stock_visto), "1000", 20, "1200")  # type: ignore[arg-type]
        assert mundo.promedio(a) == promedio_de_la_compra  # el ajuste no lo alteró
        if stock_visto == 100:  # la compra "como si hubiera sido sola"
            assert mundo.promedio(a) == Decimal("1033.333333")
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM costo_producto_mov "
                "WHERE organizacion_id = :o AND producto_id = :p",
                p=a,
            )
            == 2
        )  # stock inicial y compra
        assert mundo.stock_total(a) == 100 + delta + 20
        assert mundo.saldo(a, mundo.deposito) == 100 + delta + 20
        mundo.saldos_iguales_al_libro()

    def _una_carrera(self, database_url: str, delta: int) -> None:
        mundo = self._escenario(database_url)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.ajustar(sesion, mundo.deposito, (mundo.producto_a, delta)),
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        self._verificar(mundo, delta, compra_primero=None)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_en_carrera_el_promedio_es_el_de_la_compra_sobre_el_stock_que_vio(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        for _ in range(5):
            self._una_carrera(database_url, delta)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_llega_primero_el_ajuste(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        mundo = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.ajustar(sesion, mundo.deposito, (mundo.producto_a, delta)),
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
        )

        assert resultados == (OK, OK)
        self._verificar(mundo, delta, compra_primero=False)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_llega_primero_la_compra(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        mundo = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
            lambda sesion: mundo.ajustar(sesion, mundo.deposito, (mundo.producto_a, delta)),
        )

        assert resultados == (OK, OK)
        self._verificar(mundo, delta, compra_primero=True)


class TestTransferenciaHaciaUnaUbicacionQueSeDesactiva:
    """STK-02, D8, ADR-038 punto 4: desactivar la ubicación toma su fila `FOR UPDATE` y la
    transferencia la toma `FOR SHARE`: o la transferencia falla con `UBICACION_INACTIVA` o la
    desactivación con `UBICACION_CON_STOCK`; nunca queda stock en una ubicación inactiva."""

    def _escenario(self, database_url: str) -> _Mundo:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 50, "1000")
        return mundo

    def _una_carrera(self, database_url: str) -> None:
        mundo = self._escenario(database_url)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.desactivar_ubicacion(sesion, mundo.vehiculo),
            lambda sesion: mundo.transferir(
                sesion, mundo.deposito, mundo.vehiculo, (mundo.producto_a, 10)
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        inactiva = not mundo.ubicacion_activa(mundo.vehiculo)
        stock = mundo.saldo(mundo.producto_a, mundo.vehiculo)
        assert not (inactiva and stock > 0), f"{resultados}, errores={errores}"
        if inactiva:
            assert resultados == {0: OK, 1: UbicacionInactivaError.__name__}
            assert stock == 0
            assert mundo.saldo(mundo.producto_a, mundo.deposito) == 50
        else:
            assert resultados == {0: UbicacionConStockError.__name__, 1: OK}
            assert stock == 10
        mundo.saldos_iguales_al_libro()

    def test_en_carrera_nunca_queda_stock_en_una_ubicacion_inactiva(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        for _ in range(8):
            self._una_carrera(database_url)

    def test_si_llega_primero_la_transferencia_la_desactivacion_se_rechaza(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.transferir(
                sesion, mundo.deposito, mundo.vehiculo, (mundo.producto_a, 10)
            ),
            lambda sesion: mundo.desactivar_ubicacion(sesion, mundo.vehiculo),
        )

        assert resultados == (OK, UbicacionConStockError.__name__)
        assert mundo.ubicacion_activa(mundo.vehiculo)
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 10

    def test_si_llega_primero_la_desactivacion_la_transferencia_se_rechaza(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.desactivar_ubicacion(sesion, mundo.vehiculo),
            lambda sesion: mundo.transferir(
                sesion, mundo.deposito, mundo.vehiculo, (mundo.producto_a, 10)
            ),
        )

        assert resultados == (OK, UbicacionInactivaError.__name__)
        assert not mundo.ubicacion_activa(mundo.vehiculo)
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == 50
        mundo.saldos_iguales_al_libro()


class TestMismoOperationIdEnParalelo:
    """INV-06, SYN-02: el mismo `Operation-Id` con el mismo contenido, enviado a la vez por el
    bus completo (`procesar_comando`) desde dos conexiones, tiene un solo efecto y las dos
    respuestas informan lo mismo."""

    def test_dos_envios_de_la_misma_transferencia_la_aplican_una_sola_vez(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 100, "1000")
        operation_id = uuid4()
        contenido = {
            "ubicacion_origen_id": str(mundo.deposito),
            "ubicacion_destino_id": str(mundo.vehiculo),
            "lineas": [{"producto_id": str(mundo.producto_a), "cantidad_base": 30}],
        }
        resultados_del_comando: dict[int, object] = {}

        def _enviar(indice: int) -> Callable[[Session], None]:
            def _trabajo(sesion: Session) -> None:
                sobre = SobreComando(
                    operation_id=operation_id,
                    tipo="STOCK_TRANSFERIR",
                    version=1,
                    modo="ONLINE",
                    organizacion_id=mundo.org,
                    usuario_id=mundo.admin_id,
                    dispositivo_id=mundo.admin_dispositivo_id,
                    occurred_at=MOMENTO,
                    secuencia=1,
                    app_version="1.0.0",
                    contenido=contenido,
                )
                registrado = registro.resolver_handler(sobre.tipo, sobre.version)
                validado = registro.validar_contenido(registrado, sobre.contenido)

                def _ejecutar(sesion_protegida: object) -> object:
                    return registrado.funcion(  # type: ignore[call-arg]
                        sobre, validado, sesion=sesion_protegida, reloj=RELOJ
                    )

                comando = sync_service.procesar_comando(
                    sesion,
                    RELOJ,
                    sobre=sobre,
                    huella=calcular_huella(sobre.contenido),
                    ejecutar_handler=_ejecutar,  # type: ignore[arg-type]
                )
                resultados_del_comando[indice] = comando.resultado

            return _trabajo

        resultados, errores = _en_paralelo(database_url, [_enviar(0), _enviar(1)])

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert resultados_del_comando[0] == resultados_del_comando[1]
        assert mundo.cantidad("SELECT count(*) FROM transferencia WHERE organizacion_id = :o") == 1
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM comando WHERE organizacion_id = :o AND operation_id = :op",
                op=operation_id,
            )
            == 1
        )
        assert mundo.movimientos_de_origen("TRANSFERENCIA") == 2
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == 70
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 30
        mundo.saldos_iguales_al_libro()


# --- 14.2 -----------------------------------------------------------------------------


class TestDesactivarUnProductoSinStockContraUnMovimientoQueLeIngresa:
    """CAT-05, D4.2, D5 punto 8, INV-12: la desactivación toma el producto `FOR UPDATE` y todo
    movimiento lo toma `FOR SHARE` antes de tocar costo y saldos; o la desactivación falla con
    `PRODUCTO_CON_STOCK` o el movimiento con `PRODUCTO_INACTIVO`; nunca un producto inactivo
    con stock. Un ajuste positivo y una transferencia (que solo puede ingresar unidades a un
    producto sin stock con `PERMITIR_STOCK_NEGATIVO`, D1: sale del origen vacío), con el
    producto ya con historia de saldo (en cero) y con su PRIMER movimiento (sin ninguna fila de
    saldo que el verificador pueda leer)."""

    def _escenario(self, database_url: str, *, primer_movimiento: bool) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        producto = mundo.producto_nuevo("Producto sin stock")
        if primer_movimiento:
            mundo.con_promedio_sin_saldo(producto, "1000")
        else:
            mundo.sembrar(producto, mundo.deposito, 10, "1000")
            mundo.vender(producto, 10)
            assert mundo.saldo(producto, mundo.deposito) == 0
            assert mundo.promedio(producto) is not None
        return mundo, producto

    @staticmethod
    def _movimiento(mundo: _Mundo, tipo: str, producto: UUID) -> Callable[[Session], object]:
        if tipo == "ajuste_positivo":
            return lambda sesion: mundo.ajustar(sesion, mundo.deposito, (producto, 7))
        return lambda sesion: mundo.transferir(
            sesion, mundo.deposito, mundo.vehiculo, (producto, 7), permitir_negativo=True
        )

    @staticmethod
    def _sin_producto_inactivo_con_stock(mundo: _Mundo, producto: UUID, detalle: str) -> None:
        saldos = mundo.leer(
            "SELECT COALESCE(SUM(ABS(cantidad_base)), 0) FROM stock_saldo "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto,
        )
        hay_stock = int(saldos[0][0]) != 0  # type: ignore[arg-type]
        assert not (hay_stock and not mundo.producto_activo(producto)), detalle
        mundo.saldos_iguales_al_libro()

    @pytest.mark.parametrize("primer_movimiento", [False, True])
    @pytest.mark.parametrize("tipo", ["ajuste_positivo", "transferencia"])
    def test_si_llega_primero_el_movimiento_la_desactivacion_se_rechaza(
        self, database_url: str, _engine_de_sesion, tipo: str, primer_movimiento: bool
    ) -> None:
        mundo, producto = self._escenario(database_url, primer_movimiento=primer_movimiento)

        resultados = _encadenado(
            database_url,
            self._movimiento(mundo, tipo, producto),
            lambda sesion: mundo.desactivar_producto(sesion, producto),
        )

        assert resultados == (OK, ProductoConStockError.__name__)
        assert mundo.producto_activo(producto)
        assert mundo.saldo(producto, mundo.deposito) != 0
        self._sin_producto_inactivo_con_stock(mundo, producto, str(resultados))

    @pytest.mark.parametrize("primer_movimiento", [False, True])
    @pytest.mark.parametrize("tipo", ["ajuste_positivo", "transferencia"])
    def test_si_llega_primero_la_desactivacion_el_movimiento_se_rechaza(
        self, database_url: str, _engine_de_sesion, tipo: str, primer_movimiento: bool
    ) -> None:
        mundo, producto = self._escenario(database_url, primer_movimiento=primer_movimiento)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.desactivar_producto(sesion, producto),
            self._movimiento(mundo, tipo, producto),
        )

        assert resultados == (OK, ProductoInactivoError.__name__)
        assert not mundo.producto_activo(producto)
        assert mundo.saldo(producto, mundo.deposito) == 0
        assert mundo.saldo(producto, mundo.vehiculo) == 0
        self._sin_producto_inactivo_con_stock(mundo, producto, str(resultados))

    def _una_carrera(self, database_url: str, tipo: str, primer_movimiento: bool) -> None:
        mundo, producto = self._escenario(database_url, primer_movimiento=primer_movimiento)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.desactivar_producto(sesion, producto),
            lambda sesion: self._movimiento(mundo, tipo, producto)(sesion),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        self._sin_producto_inactivo_con_stock(mundo, producto, f"{resultados} {errores}")
        if mundo.producto_activo(producto):
            assert resultados == {0: ProductoConStockError.__name__, 1: OK}
        else:
            assert resultados == {0: OK, 1: ProductoInactivoError.__name__}

    @pytest.mark.parametrize("primer_movimiento", [False, True])
    @pytest.mark.parametrize("tipo", ["ajuste_positivo", "transferencia"])
    def test_en_carrera_nunca_queda_un_producto_inactivo_con_stock(
        self, database_url: str, _engine_de_sesion, tipo: str, primer_movimiento: bool
    ) -> None:
        for _ in range(6):
            self._una_carrera(database_url, tipo, primer_movimiento)


class TestDosAnulacionesSimultaneasDeLaMismaTransferencia:
    """D5 punto 8, TR-06: las dos anulaciones toman la cabecera `FOR UPDATE` antes de todo lo
    demás; la que llega segunda ve la transferencia `ANULADA` y falla con
    `TRANSFERENCIA_YA_ANULADA`. Un solo par de inversos por línea (INV-12, INV-15)."""

    def _escenario(self, database_url: str) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 100, "1000")
        mundo.sembrar(mundo.producto_b, mundo.deposito, 100, "2000")
        sesion = _sesion_independiente(database_url)
        try:
            transferencia = mundo.transferir(
                sesion,
                mundo.deposito,
                mundo.vehiculo,
                (mundo.producto_a, 40),
                (mundo.producto_b, 25),
            )
            sesion.commit()
        finally:
            sesion.close()
        return mundo, transferencia

    def _verificar(self, mundo: _Mundo) -> None:
        # Dos líneas: dos movimientos de la transferencia por línea y dos inversos por línea.
        assert mundo.movimientos_de_origen("TRANSFERENCIA") == 4
        assert mundo.movimientos_de_origen("ANULACION_TRANSFERENCIA") == 4
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM transferencia "
                "WHERE organizacion_id = :o AND estado = 'ANULADA'"
            )
            == 1
        )
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == 100
        assert mundo.saldo(mundo.producto_b, mundo.deposito) == 100
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        assert mundo.stock_total(mundo.producto_a) == 100
        assert mundo.promedio(mundo.producto_a) == Decimal("1000.000000")
        assert mundo.promedio(mundo.producto_b) == Decimal("2000.000000")
        assert mundo.saldos_negativos() == 0
        mundo.saldos_iguales_al_libro()

    @pytest.mark.parametrize("hilos", [2, 4])
    def test_en_carrera_una_se_acepta_y_las_otras_ya_estan_anuladas(
        self, database_url: str, _engine_de_sesion, hilos: int
    ) -> None:
        mundo, transferencia = self._escenario(database_url)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.anular_transferencia(sesion, transferencia) for _ in range(hilos)
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted(
            [OK] + [TransferenciaYaAnuladaError.__name__] * (hilos - 1)
        ), f"{resultados}, errores={errores}"
        self._verificar(mundo)

    def test_la_segunda_que_espera_la_cabecera_ve_la_transferencia_anulada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo, transferencia = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.anular_transferencia(sesion, transferencia),
            lambda sesion: mundo.anular_transferencia(sesion, transferencia),
        )

        assert resultados == (OK, TransferenciaYaAnuladaError.__name__)
        self._verificar(mundo)


class TestAnulacionContraOtraTransferenciaQueSacaDelDestino:
    """D5 punto 8, STK-05, `02` §7.4: la anulación de una transferencia necesita sacar las
    unidades del destino; otra transferencia que saca las mismas unidades de ahí compite por
    ellas. Una de las dos es `STOCK_INSUFICIENTE` (sin `PERMITIR_STOCK_NEGATIVO`) y el saldo
    nunca queda negativo."""

    def _escenario(self, database_url: str) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 100, "1000")
        sesion = _sesion_independiente(database_url)
        try:
            transferencia = mundo.transferir(
                sesion, mundo.deposito, mundo.vehiculo, (mundo.producto_a, 60)
            )
            sesion.commit()
        finally:
            sesion.close()
        return mundo, transferencia

    def _anular_sin_negativo(self, mundo: _Mundo, transferencia: UUID) -> Callable[[Session], None]:
        def _trabajo(sesion: Session) -> None:
            stock_service.anular_transferencia(
                mundo.org,
                sesion,
                RELOJ,
                transferencia_id=transferencia,
                motivo_id=mundo.motivo_anula_transferencia,
                permisos=PERMISOS_VENDEDOR,  # propia, sin PERMITIR_STOCK_NEGATIVO
                operation_id=uuid4(),
                usuario_id=mundo.admin_id,
                dispositivo_id=mundo.admin_dispositivo_id,
                occurred_at=MOMENTO,
            )

        return _trabajo

    def _sacar_del_destino(self, mundo: _Mundo) -> Callable[[Session], object]:
        return lambda sesion: mundo.transferir(
            sesion, mundo.vehiculo, mundo.deposito, (mundo.producto_a, 60)
        )

    def _verificar(
        self, mundo: _Mundo, resultados: dict[str, str] | dict[int, str], anulacion_gano: bool
    ) -> None:
        assert mundo.saldos_negativos() == 0, str(resultados)
        assert mundo.stock_total(mundo.producto_a) == 100
        assert mundo.promedio(mundo.producto_a) == Decimal("1000.000000")
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == 100
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        estado = mundo.leer("SELECT estado FROM transferencia WHERE organizacion_id = :o")
        assert (("ANULADA",) in estado) is anulacion_gano
        mundo.saldos_iguales_al_libro()

    def _una_carrera(self, database_url: str) -> None:
        mundo, transferencia = self._escenario(database_url)
        trabajos: list[Callable[[Session], None]] = [
            self._anular_sin_negativo(mundo, transferencia),
            lambda sesion: self._sacar_del_destino(mundo)(sesion),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted([OK, StockInsuficienteError.__name__]), (
            f"{resultados}, errores={errores}"
        )
        # Cualquiera de las dos gana; en las dos el stock vuelve al depósito y el
        # vehículo queda en cero.
        self._verificar(mundo, resultados, anulacion_gano=resultados[0] == OK)

    def test_en_carrera_una_de_las_dos_es_stock_insuficiente(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        for _ in range(5):
            self._una_carrera(database_url)

    def test_si_llega_primero_la_anulacion_la_otra_transferencia_es_stock_insuficiente(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo, transferencia = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            self._anular_sin_negativo(mundo, transferencia),
            self._sacar_del_destino(mundo),
        )

        assert resultados == (OK, StockInsuficienteError.__name__)
        self._verificar(mundo, {0: resultados[0], 1: resultados[1]}, anulacion_gano=True)

    def test_si_llega_primero_la_otra_transferencia_la_anulacion_es_stock_insuficiente(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo, transferencia = self._escenario(database_url)

        resultados = _encadenado(
            database_url,
            self._sacar_del_destino(mundo),
            self._anular_sin_negativo(mundo, transferencia),
        )

        assert resultados == (OK, StockInsuficienteError.__name__)
        self._verificar(mundo, {0: resultados[0], 1: resultados[1]}, anulacion_gano=False)


class TestAnulacionDeUnAjusteContraUnaCompra:
    """CST-12, CST-11, D5 punto 8: anular un ajuste devuelve unidades al promedio vigente y no
    lo recalcula ni deja historia de costo; solo la compra lo hace. El promedio final es el de
    la compra sobre el stock que vio, en los dos órdenes."""

    def _escenario(self, database_url: str, delta: int) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.producto_a, mundo.deposito, 100, "1000")
        sesion = _sesion_independiente(database_url)
        try:
            ajuste = mundo.ajustar(sesion, mundo.deposito, (mundo.producto_a, delta))
            sesion.commit()
        finally:
            sesion.close()
        return mundo, ajuste

    def _verificar(self, mundo: _Mundo, delta: int, *, compra_primero: bool | None) -> None:
        a = mundo.producto_a
        # Antes de la compra el stock es 100 + delta (ajuste vigente) o 100 (ya anulado).
        filas = mundo.leer(
            "SELECT stock_anterior, promedio_nuevo FROM costo_producto_mov "
            "WHERE organizacion_id = :o AND producto_id = :p AND origen_tipo = 'COMPRA' "
            "AND stock_anterior > 0",
            p=a,
        )
        assert len(filas) == 1
        ((stock_visto, promedio_de_la_compra),) = filas
        assert stock_visto in {100, 100 + delta}
        if compra_primero is not None:
            assert (stock_visto == 100 + delta) is compra_primero
        assert promedio_de_la_compra == _promedio_esperado(int(stock_visto), "1000", 20, "1200")  # type: ignore[arg-type]
        assert mundo.promedio(a) == promedio_de_la_compra
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM costo_producto_mov "
                "WHERE organizacion_id = :o AND producto_id = :p",
                p=a,
            )
            == 2
        )  # stock inicial y compra: ni el ajuste ni su anulación dejan historia
        assert mundo.stock_total(a) == 100 + 20
        assert mundo.saldo(a, mundo.deposito) == 100 + 20
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM ajuste_stock "
                "WHERE organizacion_id = :o AND estado = 'ANULADA'"
            )
            == 1
        )
        mundo.saldos_iguales_al_libro()

    def _una_carrera(self, database_url: str, delta: int) -> None:
        mundo, ajuste = self._escenario(database_url, delta)
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: mundo.anular_ajuste(sesion, ajuste),
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        self._verificar(mundo, delta, compra_primero=None)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_en_carrera_el_promedio_es_el_de_la_compra_sobre_el_stock_que_vio(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        for _ in range(5):
            self._una_carrera(database_url, delta)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_llega_primero_la_anulacion(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        mundo, ajuste = self._escenario(database_url, delta)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.anular_ajuste(sesion, ajuste),
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
        )

        assert resultados == (OK, OK)
        self._verificar(mundo, delta, compra_primero=False)

    @pytest.mark.parametrize("delta", [5, -5])
    def test_llega_primero_la_compra(
        self, database_url: str, _engine_de_sesion, delta: int
    ) -> None:
        mundo, ajuste = self._escenario(database_url, delta)

        resultados = _encadenado(
            database_url,
            lambda sesion: mundo.ingresar(sesion, (mundo.producto_a, 20, "1200")),
            lambda sesion: mundo.anular_ajuste(sesion, ajuste),
        )

        assert resultados == (OK, OK)
        self._verificar(mundo, delta, compra_primero=True)
