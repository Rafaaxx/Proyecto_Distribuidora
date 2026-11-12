"""Change 08, tarea 8.5: concurrencia real de `cuentas_corrientes` contra
PostgreSQL real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md`
§7.1), con el mismo arnés que `test_clientes_concurrencia.py`: cada hilo tiene su
propia conexión/sesión, confirma su propia transacción y arranca junto a los otros
en una `threading.Barrier`. Nunca hay rollback externo.

Escenarios de `specs/cuentas-corrientes/saldo-de-cuenta` y
`specs/clientes/fichas-de-cliente`:

- dos movimientos simultáneos sobre la misma cuenta: el saldo es la suma de los
  dos (CC-04, INV-13, `design.md` D10);
- la primera fila de saldo se crea una sola vez aunque dos movimientos lleguen a
  la vez (`INSERT ... ON CONFLICT DO NOTHING`);
- cuentas distintas no se esperan entre sí (el bloqueo es por cuenta, no global);
- la reactivación de un cliente `INACTIVO` frente a un saldo inicial simultáneo
  se serializa (CLI-06, ADR-030, `design.md` D8).
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
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import ClienteConOperacionesError
from app.modules.cuentas_corrientes import service
from tests.integration.cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ESPERA_MAXIMA = 30


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones -- simula un
    worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


class _Escenario:
    """Una organización confirmada con dos clientes, un proveedor, su usuario y su
    dispositivo."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
            self.cliente_a = crear_cliente(sesion, self.org, nombre="Cliente A")
            self.cliente_b = crear_cliente(sesion, self.org, nombre="Cliente B")
            self.proveedor = crear_proveedor(sesion, self.org)
            sesion.commit()
        finally:
            sesion.close()

    def mover(
        self,
        sesion: Session,
        *,
        entidad_id: UUID,
        importe: str,
        sentido: str = "AUMENTA",
        cuenta_tipo: str = "CLIENTE",
    ) -> None:
        operation_id = uuid4()
        service.registrar_movimiento(
            self.org,
            sesion,
            RELOJ,
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            tipo="SALDO_INICIAL",
            sentido=sentido,
            importe=importe,
            origen_tipo="SALDO_INICIAL",
            origen_id=operation_id,
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=operation_id,
        )

    def saldo_inicial(self, sesion: Session, *, entidad_id: UUID, importe: str) -> None:
        service.registrar_saldo_inicial(
            self.org,
            sesion,
            RELOJ,
            cuenta_tipo="CLIENTE",
            entidad_id=entidad_id,
            importe=importe,
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def saldo_materializado(self, entidad_id: UUID) -> Decimal:
        (fila,) = self.leer(
            "SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o AND entidad_id = :e",
            e=entidad_id,
        )
        saldo = fila[0]
        assert isinstance(saldo, Decimal)
        return saldo

    def suma_del_libro(self, entidad_id: UUID) -> Decimal:
        ((suma,),) = self.leer(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o AND entidad_id = :e",
            e=entidad_id,
        )
        assert isinstance(suma, Decimal)
        return suma

    def cantidad(self, tabla: str, entidad_id: UUID) -> int:
        ((cantidad,),) = self.leer(
            f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o AND entidad_id = :e",  # noqa: S608
            e=entidad_id,
        )
        assert isinstance(cantidad, int)
        return cantidad

    def diferencias(self) -> list[object]:
        sesion = _sesion_independiente(self.database_url)
        try:
            return list(service.verificar_consistencia(self.org, sesion))
        finally:
            sesion.close()


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


class TestMovimientosSimultaneosSobreLaMismaCuenta:
    """CC-04, INV-13, `design.md` D10: todo movimiento bloquea primero la fila de
    saldo de su cuenta, así que dos movimientos simultáneos se serializan y el
    saldo es la suma de los dos."""

    @pytest.mark.parametrize("cantidad_de_hilos", [2, 6])
    def test_el_saldo_es_la_suma_de_los_movimientos_simultaneos(
        self, database_url: str, _engine_de_sesion, cantidad_de_hilos: int
    ) -> None:
        escenario = _Escenario(database_url)
        # Cada hilo aumenta 100.00 y el último reduce 30.00: el resultado exacto
        # (100 x (n - 1) - 30 + 100) es sensible a cualquier actualización perdida.
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: escenario.mover(sesion, entidad_id=escenario.cliente_a, importe="100.00")
            for _ in range(cantidad_de_hilos - 1)
        ]
        trabajos.append(
            lambda sesion: escenario.mover(
                sesion, entidad_id=escenario.cliente_a, importe="30.00", sentido="REDUCE"
            )
        )

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"
        esperado = Decimal("100.00") * (cantidad_de_hilos - 1) - Decimal("30.00")
        assert escenario.saldo_materializado(escenario.cliente_a) == esperado
        assert escenario.suma_del_libro(escenario.cliente_a) == esperado
        assert escenario.cantidad("cuenta_movimiento", escenario.cliente_a) == cantidad_de_hilos
        assert escenario.diferencias() == []


class TestPrimeraFilaDeSaldoBajoConcurrencia:
    """`INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE` (D10): dos
    primeros movimientos simultáneos de una cuenta nueva no chocan en la clave de
    `saldo_cuenta` y dejan una sola fila."""

    def test_la_primera_fila_de_saldo_se_crea_una_sola_vez(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        assert escenario.cantidad("saldo_cuenta", escenario.proveedor) == 0
        trabajos: list[Callable[[Session], None]] = [
            lambda sesion: escenario.mover(
                sesion,
                entidad_id=escenario.proveedor,
                cuenta_tipo="PROVEEDOR",
                importe="10.00",
            ),
            lambda sesion: escenario.mover(
                sesion,
                entidad_id=escenario.proveedor,
                cuenta_tipo="PROVEEDOR",
                importe="20.00",
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {"OK"}, f"{resultados}, errores={errores}"
        assert escenario.cantidad("saldo_cuenta", escenario.proveedor) == 1
        assert escenario.saldo_materializado(escenario.proveedor) == Decimal("30.00")
        assert escenario.cantidad("cuenta_movimiento", escenario.proveedor) == 2
        assert escenario.diferencias() == []


class TestCuentasDistintasNoSeEsperan:
    """El bloqueo es por cuenta: una transacción abierta con la fila de saldo de
    una cuenta tomada no frena a otra cuenta de la misma organización."""

    def test_un_movimiento_sobre_otra_cuenta_no_espera_a_una_transaccion_abierta(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        a_tomo_su_cuenta = threading.Event()
        b_confirmo = threading.Event()
        resultado_de_b: dict[str, object] = {}

        def _hilo_a() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                escenario.mover(sesion, entidad_id=escenario.cliente_a, importe="100.00")
                a_tomo_su_cuenta.set()
                # Mantiene la transacción abierta hasta que B haya terminado.
                resultado_de_b["b_termino_antes_que_a_confirmara"] = b_confirmo.wait(
                    timeout=ESPERA_MAXIMA
                )
                sesion.commit()
            finally:
                a_tomo_su_cuenta.set()
                sesion.close()

        def _hilo_b() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                assert a_tomo_su_cuenta.wait(timeout=10)
                escenario.mover(sesion, entidad_id=escenario.cliente_b, importe="40.00")
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
            "B tuvo que esperar a A: el bloqueo no es por cuenta."
        )
        assert escenario.saldo_materializado(escenario.cliente_a) == Decimal("100.00")
        assert escenario.saldo_materializado(escenario.cliente_b) == Decimal("40.00")
        assert escenario.diferencias() == []


class TestReactivacionDeClienteContraSaldoInicial:
    """CLI-06, ADR-030, `design.md` D8: reactivar un cliente `INACTIVO` mientras se
    le registra un saldo inicial se serializa. Hay dos órdenes posibles y los dos
    son correctos; el que no puede ocurrir es reactivar habiendo un movimiento ya
    confirmado. Se repite para ejercer las dos entradas de la carrera."""

    @staticmethod
    def _reactivar(escenario: _Escenario, sesion: Session, cliente_id: UUID) -> None:
        clientes_service.modificar_cliente(
            escenario.org,
            sesion,
            RELOJ,
            cliente_id=cliente_id,
            nombre="Cliente reactivado",
            codigo=None,
            razon_social=None,
            documento_tipo=None,
            documento_numero=None,
            direccion="Av. San Martín 1420",
            contacto="Rocío",
            telefono=None,
            email=None,
            estado_facturacion_default=None,
            lista_precio_id=None,
            estado="ACTIVO",
            actor_id=escenario.usuario_id,
            verificar_operaciones=lambda: service.cuenta_tiene_movimientos(
                escenario.org, sesion, cuenta_tipo="CLIENTE", entidad_id=cliente_id
            ),
        )

    def test_la_reactivacion_y_el_saldo_inicial_simultaneos_quedan_en_un_orden_valido(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        salidas: list[tuple[str, str, int]] = []

        for _ in range(8):
            cliente_id = self._crear_cliente_inactivo(escenario)

            resultados, errores = _en_paralelo(
                database_url,
                [
                    lambda sesion, c=cliente_id: self._reactivar(escenario, sesion, c),
                    lambda sesion, c=cliente_id: escenario.saldo_inicial(
                        sesion, entidad_id=c, importe="500.00"
                    ),
                ],
            )

            # El saldo inicial se admite en cualquier estado (D4): siempre entra.
            assert resultados[1] == "OK", f"{resultados}, errores={errores}"
            assert resultados[0] in {"OK", ClienteConOperacionesError.__name__}, (
                f"{resultados}, errores={errores}"
            )
            estado = str(
                escenario.leer(
                    "SELECT estado FROM cliente WHERE organizacion_id = :o AND id = :c",
                    c=cliente_id,
                )[0][0]
            )
            movimientos = escenario.cantidad("cuenta_movimiento", cliente_id)
            salidas.append((resultados[0], estado, movimientos))

            # Coherencia entre lo que respondió la reactivación y lo que quedó.
            if resultados[0] == "OK":
                assert estado == "ACTIVO"
            else:
                assert estado == "INACTIVO"
            assert movimientos == 1
            assert escenario.saldo_materializado(cliente_id) == Decimal("500.00")

        assert escenario.diferencias() == []
        # Ninguna corrida terminó con dos respuestas contradictorias con el estado.
        assert all(
            (resultado == "OK" and estado == "ACTIVO")
            or (resultado == ClienteConOperacionesError.__name__ and estado == "INACTIVO")
            for resultado, estado, _ in salidas
        )

    def test_un_saldo_inicial_ya_confirmado_impide_la_reactivacion(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """El orden determinista: con el movimiento confirmado, la reactivación se
        rechaza (CLI-06)."""
        escenario = _Escenario(database_url)
        cliente_id = self._crear_cliente_inactivo(escenario)
        sesion = _sesion_independiente(database_url)
        try:
            escenario.saldo_inicial(sesion, entidad_id=cliente_id, importe="500.00")
            sesion.commit()
        finally:
            sesion.close()

        resultados, _ = _en_paralelo(
            database_url, [lambda s: self._reactivar(escenario, s, cliente_id)]
        )

        assert resultados[0] == ClienteConOperacionesError.__name__

    @staticmethod
    def _crear_cliente_inactivo(escenario: _Escenario) -> UUID:
        sesion = _sesion_independiente(escenario.database_url)
        try:
            cliente_id = crear_cliente(sesion, escenario.org, estado="INACTIVO", nombre="Inactivo")
            sesion.commit()
            return cliente_id
        finally:
            sesion.close()
