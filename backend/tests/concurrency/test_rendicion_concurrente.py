"""Change 24, tarea 17.1: concurrencia real de la rendición, la entrega y el cierre con devolución
contra PostgreSQL real (Testcontainers, `READ COMMITTED`) y con commits reales, con el arnés de
`test_jornadas_concurrencia.py` y `test_venta_anular_offline_concurrencia.py`: cada hilo tiene su
propia sesión, confirma su propia transacción y arranca junto a los otros en una barrera. Nunca hay
rollback externo (`CLAUDE.md` §4).

Spec `stock/rendicion-de-jornada`, requisito "La rendición se serializa con los movimientos de su
ubicación" (`design.md` D3: la rendición y el cierre toman la ubicación `FOR UPDATE` antes que la
jornada y que cualquier saldo, y no toman `saldo_cuenta`). Los escenarios cuyo resultado depende
del orden de llegada se prueban en los DOS órdenes con `_encadenado` (la primera transacción deja
sus bloqueos tomados y sin confirmar; se observa a la segunda esperando en `pg_stat_activity`),
y además en carrera libre con el bus o el lote completos:

- rendición contra venta sin conexión de la misma jornada (INV-01, INV-12);
- rendición contra liberación (RUT-09, INV-01);
- dos rendiciones de la misma jornada (INV-06, INV-12);
- cierre con devolución contra una transferencia al mismo depósito (INV-12, INV-16);
- entrega contra liberación (RUT-05, RUT-09, INV-16).

Reglas citadas: INV-01, INV-12, INV-16, `02` §7.3.
"""

from __future__ import annotations

import gc
import threading
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_anular_utiles import MOMENTO_ANULACION, RELOJ_ANULACION, EntornoAnulacion

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.stock import jornadas_repository
from app.modules.stock import rendicion_commands as _rendicion_commands  # noqa: F401
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import EsperadoDifiereError, JornadaEstadoInvalidoError
from app.modules.stock.service import LineaContada, LineaDeTransferencia
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote
from tests.concurrency.test_jornadas_concurrencia import (
    LIBERAR,
    _Actor,
    _dos_ordenes,
    _Mundo,
)
from tests.concurrency.test_stock_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _sesion_independiente,
)
from tests.concurrency.test_transferencias_ajustes_concurrencia import (
    ESPERA_MAXIMA,
    OK,
    _encadenado,
    _hay_alguien_esperando_un_bloqueo,
)
from tests.concurrency.test_venta_anular_offline_concurrencia import _EscenarioDeRuta
from tests.integration.stock_utiles import crear_ubicacion_sql

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RENDIR = "JORNADA_RENDIR"
CERRAR = "JORNADA_CERRAR"
VENTA = "VENTA_CONFIRMAR"
ESTADO_INVALIDO = JornadaEstadoInvalidoError.__name__
ESPERADO_DIFIERE = EsperadoDifiereError.__name__
REPETICIONES = 6
EXISTENCIA = 100


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()
    # Cada hilo y cada paso de armado abren su propio engine (`_sesion_independiente`) y no lo
    # cierran: sin recolectarlos acá, sus conexiones se acumulan y agotan `max_connections` de
    # PostgreSQL para las pruebas que corren después ("too many clients already").
    gc.collect()


def _interbloqueos(database_url: str) -> int:
    """Los interbloqueos que PostgreSQL detectó en la base de la prueba (`pg_stat_database`). El
    bus reintenta una operación que fue la víctima, así que un ciclo puede pasar inadvertido en
    el resultado de las operaciones: este contador no."""
    sesion = _sesion_independiente(database_url)
    try:
        sesion.execute(text("SELECT pg_stat_clear_snapshot()"))
        return int(
            sesion.scalar(
                text("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")
            )
            or 0
        )
    finally:
        sesion.close()


def _rendicion_a_medias(
    database_url: str,
    paso_1: Callable[[Session], object],
    resto: Callable[[Session], object],
    otro: Callable[[Session], object],
) -> tuple[str, str]:
    """El orden que cierra el ciclo, forzado: la rendición hace su `paso_1` (toma la ubicación) y
    se detiene; `otro` arranca (un comando sin conexión de la misma jornada: reserva su fila de
    `comando`, que referencia a la jornada, y pide la ubicación) y se queda esperando en la base
    (se observa en `pg_stat_activity`, sin dormir); recién entonces la rendición sigue con el
    `resto` (toma la jornada) y confirma. Devuelve el resultado de cada uno."""
    listo = threading.Event()
    soltar = threading.Event()
    otro_termino = threading.Event()
    resultados: dict[str, str] = {}

    def _rendicion() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            paso_1(sesion)
            listo.set()
            assert soltar.wait(timeout=ESPERA_MAXIMA)
            resto(sesion)
            sesion.commit()
            resultados["rendicion"] = OK
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            resultados["rendicion"] = type(error).__name__
        finally:
            listo.set()
            sesion.close()

    def _otro() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            otro(sesion)
            sesion.commit()
            resultados["otro"] = OK
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            resultados["otro"] = type(error).__name__
        finally:
            otro_termino.set()
            sesion.close()

    hilo_rendicion = threading.Thread(target=_rendicion)
    hilo_otro = threading.Thread(target=_otro)
    hilo_rendicion.start()
    assert listo.wait(timeout=ESPERA_MAXIMA)
    hilo_otro.start()
    for _ in range(int(ESPERA_MAXIMA * 50)):
        if otro_termino.is_set() or _hay_alguien_esperando_un_bloqueo(database_url):
            break
        otro_termino.wait(timeout=0.02)
    else:
        soltar.set()
        pytest.fail("El otro comando no terminó ni quedó esperando un bloqueo.")
    soltar.set()
    hilo_rendicion.join(timeout=ESPERA_MAXIMA)
    hilo_otro.join(timeout=ESPERA_MAXIMA)
    assert not (hilo_rendicion.is_alive() or hilo_otro.is_alive()), (
        "Un hilo quedó colgado (posible interbloqueo real)."
    )
    return resultados["rendicion"], resultados["otro"]


# --- la jornada de un vehículo con stock, entregada ----------------------------------------


class _MundoDeRendicion(_Mundo):
    """El mundo de las jornadas con 100 botellas de Vino A en "Camioneta" y en el depósito, y la
    jornada de Juan abierta; lo que pide cada escenario (entrega, rendición) se confirma aparte."""

    def jornada_de_juan(self) -> UUID:
        self.sembrar(self.vehiculo, EXISTENCIA)
        self.sembrar(self.deposito, EXISTENCIA)
        return self.abrir(self.juan)

    def entregar(self, jornada_id: UUID) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            stock_service.entregar_jornada(
                self.org, sesion, RELOJ, jornada_id=jornada_id, occurred_at=MOMENTO, secuencia=1
            )
            sesion.commit()
        finally:
            sesion.close()

    def conteo_exacto(self, cantidad: int = EXISTENCIA) -> list[dict[str, Any]]:
        return [
            {
                "producto_id": str(self.producto_a),
                "cantidad_contada": cantidad,
                "cantidad_esperada": EXISTENCIA,
            }
        ]

    def enviar_v2(
        self, sesion: Session, tipo: str, actor: _Actor, contenido: dict[str, Any]
    ) -> Comando:
        """El bus completo (versión 2 de la rendición y del cierre) sobre la sesión del hilo."""
        sobre = SobreComando(
            operation_id=uuid4(),
            tipo=tipo,
            version=2,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def rendir_por_el_bus(self, jornada_id: UUID) -> Callable[[Session], object]:
        contenido = {"jornada_id": str(jornada_id), "lineas": self.conteo_exacto()}
        return lambda sesion: self.enviar_v2(sesion, RENDIR, self.sofia, contenido)

    def rendir_srv(self, jornada_id: UUID) -> Callable[[Session], object]:
        """La rendición por el servicio, SIN confirmar (para `_encadenado`)."""
        return lambda sesion: stock_service.rendir_jornada(
            self.org,
            sesion,
            RELOJ,
            jornada_id=jornada_id,
            usuario_id=self.sofia.usuario_id,
            dispositivo_id=self.sofia.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            lineas=[LineaContada(self.producto_a, EXISTENCIA, EXISTENCIA)],
            observacion=None,
        )

    def entregar_srv(self, jornada_id: UUID) -> Callable[[Session], object]:
        return lambda sesion: stock_service.entregar_jornada(
            self.org, sesion, RELOJ, jornada_id=jornada_id, occurred_at=MOMENTO, secuencia=1
        )

    def devolver_srv(self, jornada_id: UUID, cantidad: int) -> Callable[[Session], object]:
        """El cierre con devolución del remanente al depósito, SIN confirmar."""
        return lambda sesion: stock_service.cerrar_jornada_con_devolucion(
            self.org,
            sesion,
            RELOJ,
            jornada_id=jornada_id,
            usuario_id=self.sofia.usuario_id,
            dispositivo_id=self.sofia.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            destino_id=self.deposito,
            lineas=[LineaDeTransferencia(self.producto_a, cantidad)],
        )

    def devolver_por_el_bus(self, jornada_id: UUID, cantidad: int) -> Callable[[Session], object]:
        contenido = {
            "jornada_id": str(jornada_id),
            "devolucion": {
                "ubicacion_destino_id": str(self.deposito),
                "lineas": [{"producto_id": str(self.producto_a), "cantidad_base": cantidad}],
            },
        }
        return lambda sesion: self.enviar_v2(sesion, CERRAR, self.sofia, contenido)

    # --- lecturas confirmadas -----------------------------------------------------------

    def rendiciones(self) -> int:
        return self.cantidad("SELECT count(*) FROM rendicion WHERE organizacion_id = :o")

    def diferencias_de_rendicion(self) -> int:
        return self.cantidad(
            "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o "
            "AND tipo = 'DIFERENCIA_RENDICION'"
        )

    def entregada(self, jornada_id: UUID) -> bool:
        ((entregada_en,),) = self.leer(
            "SELECT entregada_en FROM jornada WHERE organizacion_id = :o AND id = :j",
            j=jornada_id,
        )
        return entregada_en is not None


# --- rendición contra una venta sin conexión de la misma jornada ---------------------------


class _EscenarioDeRendicionYVenta(_EscenarioDeRuta):
    """La camioneta con 48 botellas y su jornada `ABIERTA` y entregada, sin ventas todavía: la
    venta sin conexión (15 botellas) y la rendición (que cuenta las 48) compiten por ella."""

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        self.camioneta_id, self.jornada_id = self._armar_la_ruta()

    def _armar_la_ruta(self) -> tuple[UUID, UUID]:
        ids: list[UUID] = []

        def _armar(e: Any) -> None:
            assert isinstance(e, EntornoAnulacion)
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            e.sesion.commit()
            jornada_id = e.crear_jornada(ubicacion_id=camioneta_id)
            stock_service.entregar_jornada(
                e.org, e.sesion, RELOJ, jornada_id=jornada_id, occurred_at=MOMENTO, secuencia=1
            )
            ids.extend([camioneta_id, jornada_id])

        self.armar(_armar)
        return ids[0], ids[1]

    def _contenido_de_venta(self) -> dict[str, Any]:
        e = self.entorno
        return e.contenido(ubicacion_id=None, credito=e.credito_offline())

    def _sobre(self) -> SobreComando:
        e = self.entorno
        return SobreComando(
            operation_id=uuid4(),
            tipo=VENTA,
            version=1,
            modo="OFFLINE",
            organizacion_id=self.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=self._contenido_de_venta(),
            jornada_id=self.jornada_id,
        )

    def vender_por_el_lote(self) -> Callable[[Session], Any]:
        """El bus completo por el lote (reserva, handler, observaciones y `commit`)."""
        sobre = self._sobre()
        item = ItemLote(
            operation_id=sobre.operation_id,
            tipo=VENTA,
            version=1,
            modo="OFFLINE",
            usuario_id=sobre.usuario_id,
            dispositivo_id=sobre.dispositivo_id,
            occurred_at=sobre.occurred_at,
            secuencia=1,
            app_version="1.0.0",
            contenido=sobre.contenido,
            jornada_id=self.jornada_id,
        )

        def _enviar(sesion: Session) -> sync_service.ResultadoItemLote:
            (resultado,) = sync_service.procesar_lote(
                sesion,
                RELOJ_ANULACION,
                organizacion_id=self.org,
                usuario_id=sobre.usuario_id,
                dispositivo_id=sobre.dispositivo_id,
                items=[item],
            )
            return resultado

        return _enviar

    def vender_srv(self) -> Callable[[Session], object]:
        """El handler de la venta sin conexión sobre la sesión del hilo, SIN confirmar."""
        sobre = self._sobre()
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        return lambda sesion: registrado.funcion(
            sobre, validado, sesion=sesion, reloj=RELOJ_ANULACION
        )

    def rendir_srv(self, esperada: int = 48) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: stock_service.rendir_jornada(
            self.org,
            sesion,
            RELOJ,
            jornada_id=self.jornada_id,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            lineas=[LineaContada(e.vino_id, esperada, esperada)],
            observacion=None,
        )

    def rendiciones(self) -> int:
        return self.cantidad_de("rendicion")

    def estado_de_la_jornada(self) -> str:
        ((estado,),) = self.leer(
            "SELECT estado FROM jornada WHERE organizacion_id = :o AND id = :j",
            j=self.jornada_id,
        )
        return str(estado)

    def observaciones_de_jornada_rendida(self) -> int:
        return self.cantidad_de("observacion", "codigo = 'JORNADA_RENDIDA'")

    def ventas(self) -> int:
        return self.cantidad_de("venta")


class TestRendicionContraVentaSinConexion:
    """INV-01, INV-12, `02` §7.3, D3: la rendición toma la ubicación `FOR UPDATE` y la venta la
    toma `FOR SHARE`: o la venta termina antes (y la rendición que no la incluía es
    `ESPERADO_DIFIERE`, sin escribir nada), o espera, llega con la jornada rendida y deja el
    stock en lo contado menos esa venta."""

    @pytest.mark.parametrize("rendicion_primero", _dos_ordenes("rendicion", "venta"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, rendicion_primero: bool
    ) -> None:
        escenario = _EscenarioDeRendicionYVenta(database_url)
        rendir = escenario.rendir_srv()
        vender = escenario.vender_srv()

        if rendicion_primero:
            resultado = _encadenado(database_url, lambda s: rendir(s), lambda s: vender(s))
            assert resultado == (OK, OK)  # la venta esperó y llegó con la jornada rendida
            assert escenario.rendiciones() == 1
            assert escenario.estado_de_la_jornada() == "EN_RENDICION"
            assert escenario.cantidad_de("venta") == 1
        else:
            resultado = _encadenado(database_url, lambda s: vender(s), lambda s: rendir(s))
            assert resultado == (OK, ESPERADO_DIFIERE)  # el esperado enviado ya no era ese
            assert escenario.rendiciones() == 0  # no escribió nada
            assert escenario.estado_de_la_jornada() == "ABIERTA"
        assert escenario.saldo_de_stock(escenario.camioneta_id) == 48 - 15  # INV-01
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'DIFERENCIA_RENDICION'") == 0

    def test_con_la_venta_esperando_la_ubicacion_la_rendicion_toma_la_jornada_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """INV-12, `02` §7.3, D3: la fila de `comando` de una operación sin conexión referencia a
        la jornada y le toma un bloqueo de clave (`FOR KEY SHARE`) ANTES de pedir la ubicación; si
        la rendición tomara la jornada `FOR UPDATE` (que choca con ese bloqueo) quedaría esperando
        a la venta mientras la venta espera la ubicación de la rendición: un ciclo. La rendición
        toma la jornada `FOR NO KEY UPDATE` (no choca con ese bloqueo y sí con el `FOR SHARE` de
        los movimientos), así que la venta espera, la rendición termina y la venta llega rendida."""
        escenario = _EscenarioDeRendicionYVenta(database_url)
        e = escenario.entorno
        rendir = escenario.rendir_srv()
        antes = _interbloqueos(database_url)

        resultado = _rendicion_a_medias(
            database_url,
            lambda sesion: jornadas_repository.bloquear_ubicacion(
                escenario.org, sesion, ubicacion_id=escenario.camioneta_id
            ),
            lambda sesion: rendir(sesion),
            escenario.vender_por_el_lote(),
        )

        assert resultado == (OK, OK), f"{resultado}, usuario={e.usuario_id}"
        # PostgreSQL informa sus estadísticas con un pequeño retraso: se espera a que se asienten.
        threading.Event().wait(timeout=2)
        assert _interbloqueos(database_url) == antes  # ni uno solo, aunque el bus reintente
        assert escenario.rendiciones() == 1
        assert escenario.estado_de_la_jornada() == "EN_RENDICION"
        assert escenario.observaciones_de_jornada_rendida() == 1  # la venta llegó rendida (INV-17)
        assert escenario.saldo_de_stock(escenario.camioneta_id) == 48 - 15  # INV-01

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRendicionYVenta(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.vender_por_el_lote(),
            escenario.rendir_srv(),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        assert resultados[1] in {OK, ESPERADO_DIFIERE}, f"{resultados}, errores={errores}"
        assert escenario.ventas() == 1
        assert escenario.saldo_de_stock(escenario.camioneta_id) == 48 - 15  # INV-01
        if resultados[1] == OK:
            # La venta llegó con la jornada rendida: se aceptó con la observación (INV-17).
            assert escenario.rendiciones() == 1
            assert escenario.estado_de_la_jornada() == "EN_RENDICION"
            assert escenario.observaciones_de_jornada_rendida() == 1
        else:
            assert escenario.rendiciones() == 0
            assert escenario.estado_de_la_jornada() == "ABIERTA"
            assert escenario.observaciones_de_jornada_rendida() == 0


# --- rendición contra liberación ------------------------------------------------------------


class TestRendicionContraLiberacion:
    """RUT-09, INV-01, D3: o la liberación gana y la rendición es `JORNADA_ESTADO_INVALIDO` sin
    escribir nada, o la rendición queda completa y la liberación pasa la jornada a `LIBERADA` sin
    tocar el stock."""

    @pytest.mark.parametrize("rendicion_primero", _dos_ordenes("rendicion", "liberacion"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, rendicion_primero: bool
    ) -> None:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        mundo.entregar(jornada_id)
        rendir = mundo.rendir_srv(jornada_id)
        liberar = mundo.liberar_srv(jornada_id)

        if rendicion_primero:
            resultado = _encadenado(database_url, lambda s: rendir(s), lambda s: liberar(s))
            assert resultado == (OK, OK)
            assert mundo.rendiciones() == 1  # completa: la liberación no la deshizo
        else:
            resultado = _encadenado(database_url, lambda s: liberar(s), lambda s: rendir(s))
            assert resultado == (OK, ESTADO_INVALIDO)
            assert mundo.rendiciones() == 0  # sin escribir nada
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == EXISTENCIA  # no toca el stock
        assert mundo.diferencias_de_rendicion() == 0
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        mundo.entregar(jornada_id)
        trabajos: list[Callable[[Session], object]] = [
            mundo.rendir_por_el_bus(jornada_id),
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, jornada_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert resultados[1] == OK, f"{resultados}, errores={errores}"
        assert resultados[0] in {OK, ESTADO_INVALIDO}, f"{resultados}, errores={errores}"
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.rendiciones() == (1 if resultados[0] == OK else 0)
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == EXISTENCIA
        mundo.saldos_iguales_al_libro()  # INV-12


# --- dos rendiciones de la misma jornada ----------------------------------------------------


class TestDosRendicionesDeLaMismaJornada:
    """INV-06, INV-12, D3: la segunda espera la ubicación y la jornada, la ve ya `EN_RENDICION` y
    es `JORNADA_ESTADO_INVALIDO`; queda una sola rendición."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_una_se_acepta_y_la_otra_es_estado_invalido(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        mundo.entregar(jornada_id)
        trabajos: list[Callable[[Session], object]] = [
            mundo.rendir_por_el_bus(jornada_id),
            mundo.rendir_por_el_bus(jornada_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert sorted(resultados.values()) == sorted([OK, ESTADO_INVALIDO]), (
            f"{resultados}, errores={errores}"
        )
        assert mundo.estado_de(jornada_id) == "EN_RENDICION"
        assert mundo.rendiciones() == 1
        assert (
            mundo.cantidad("SELECT count(*) FROM rendicion_linea WHERE organizacion_id = :o") == 1
        )
        assert mundo.diferencias_de_rendicion() == 0  # sin efectos dobles
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_con_diferencia_el_libro_recibe_una_sola_diferencia(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        """INV-12: dos rendiciones con un faltante de 3, una sola `DIFERENCIA_RENDICION` y el
        stock es lo contado."""
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        mundo.entregar(jornada_id)
        contenido = {"jornada_id": str(jornada_id), "lineas": mundo.conteo_exacto(EXISTENCIA - 3)}
        trabajos: list[Callable[[Session], object]] = [
            lambda sesion: mundo.enviar_v2(sesion, RENDIR, mundo.sofia, contenido),
            lambda sesion: mundo.enviar_v2(sesion, RENDIR, mundo.sofia, contenido),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert sorted(resultados.values()) == sorted([OK, ESTADO_INVALIDO]), (
            f"{resultados}, errores={errores}"
        )
        assert mundo.diferencias_de_rendicion() == 1
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == EXISTENCIA - 3
        mundo.saldos_iguales_al_libro()  # INV-12


# --- cierre con devolución contra una transferencia al mismo depósito -----------------------


class TestCierreConDevolucionContraTransferencia:
    """INV-12, INV-16, `02` §7.3: el cierre toma las ubicaciones de la devolución en orden y la
    transferencia ajena también (`registrar_movimientos` ordena); no se esperan en círculo, los
    dos se aplican y los saldos son la suma del libro."""

    def _mundo(self, database_url: str) -> tuple[_MundoDeRendicion, UUID]:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        mundo.rendir(jornada_id)
        return mundo, jornada_id

    @pytest.mark.parametrize("cierre_primero", _dos_ordenes("cierre", "transferencia"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, cierre_primero: bool
    ) -> None:
        mundo, jornada_id = self._mundo(database_url)
        cierre = mundo.devolver_srv(jornada_id, EXISTENCIA)
        ajena = mundo.transferir_srv(mundo.sofia, mundo.deposito, mundo.vehiculo_2, 30)

        if cierre_primero:
            resultado = _encadenado(database_url, lambda s: cierre(s), lambda s: ajena(s))
        else:
            resultado = _encadenado(database_url, lambda s: ajena(s), lambda s: cierre(s))

        assert resultado == (OK, OK)
        assert mundo.estado_de(jornada_id) == "CERRADA"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo_2) == 30
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == EXISTENCIA + EXISTENCIA - 30
        assert mundo.no_cerradas_en(mundo.vehiculo) == 0  # INV-16: la ubicación quedó libre
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo, jornada_id = self._mundo(database_url)
        trabajos: list[Callable[[Session], object]] = [
            mundo.devolver_por_el_bus(jornada_id, EXISTENCIA),
            mundo.transferir_por_el_bus(mundo.sofia, mundo.deposito, mundo.vehiculo_2, 30),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        assert resultados[1] == OK, f"{resultados}, errores={errores}"
        assert mundo.estado_de(jornada_id) == "CERRADA"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo_2) == 30
        assert mundo.saldo(mundo.producto_a, mundo.deposito) == EXISTENCIA + EXISTENCIA - 30
        mundo.saldos_iguales_al_libro()  # INV-12


# --- entrega contra liberación --------------------------------------------------------------


class TestEntregaContraLiberacion:
    """RUT-05, RUT-09, INV-16, D1: la entrega toma la jornada `FOR UPDATE`, igual que la
    liberación. Si la entrega llega primero se registra y la liberación cierra la jornada; si
    llega después ve la jornada `LIBERADA` y es `JORNADA_ESTADO_INVALIDO` sin marca."""

    @pytest.mark.parametrize("entrega_primero", _dos_ordenes("entrega", "liberacion"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, entrega_primero: bool
    ) -> None:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        entrega = mundo.entregar_srv(jornada_id)
        liberar = mundo.liberar_srv(jornada_id)

        if entrega_primero:
            resultado = _encadenado(database_url, lambda s: entrega(s), lambda s: liberar(s))
            assert resultado == (OK, OK)
            assert mundo.entregada(jornada_id)
        else:
            resultado = _encadenado(database_url, lambda s: liberar(s), lambda s: entrega(s))
            assert resultado == (OK, ESTADO_INVALIDO)
            assert not mundo.entregada(jornada_id)
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.no_cerradas_en(mundo.vehiculo) == 0  # INV-16
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == EXISTENCIA
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo = _MundoDeRendicion(database_url)
        jornada_id = mundo.jornada_de_juan()
        trabajos: list[Callable[[Session], object]] = [
            mundo.entregar_srv(jornada_id),
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, jornada_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert resultados[1] == OK, f"{resultados}, errores={errores}"
        assert resultados[0] in {OK, ESTADO_INVALIDO}, f"{resultados}, errores={errores}"
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.entregada(jornada_id) == (resultados[0] == OK)
        assert mundo.no_cerradas_en(mundo.vehiculo) == 0  # INV-16
