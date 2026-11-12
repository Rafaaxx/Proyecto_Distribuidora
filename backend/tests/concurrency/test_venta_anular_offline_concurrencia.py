"""Change 22d, tarea 3.1 (spec `ventas/anulacion-de-venta`, escenario "Anulación sin conexión
contra una anulación con conexión"; `design.md` D3 y ADR-058 D10; INV-06, INV-12, INV-13, VTA-20),
contra PostgreSQL real (Testcontainers) y con commits reales, con el arnés de
`test_ventas_anulacion_concurrencia.py`: cada hilo tiene su propia sesión, confirma su propia
transacción y arranca junto a los otros en una barrera. Nunca hay rollback externo.

Es una prueba de caracterización: la anulación `OFFLINE` usa el mismo servicio y el mismo orden de
bloqueo que la `ONLINE` (la venta `FOR UPDATE` primero), así que no hizo falta tocar el orden. Los
dos órdenes de llegada se prueban de forma determinista con `_encadenado` (la primera transacción
deja sus bloqueos tomados y sin confirmar; se observa a la segunda esperando en
`pg_stat_activity`) y la carrera libre con el bus completo.

- una anulación `OFFLINE` por el lote y una `ONLINE` por REST de la misma venta: una se acepta y la
  otra responde `VENTA_YA_ANULADA`; un solo reingreso y una sola acreditación;
- el doble envío simultáneo del mismo `operation_id` por el lote: un solo efecto y el mismo
  resultado para los dos.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from ventas_anular_utiles import MOMENTO_ANULACION, RELOJ_ANULACION, VENTA_ANULAR, EntornoAnulacion

from app.commands import registro
from app.commands.sobre import SobreComando
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote
from tests.concurrency.test_pagos_proveedor_concurrencia import _en_paralelo
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.concurrency.test_ventas_anulacion_concurrencia import (  # noqa: F401 -- fixture y escenario compartidos
    REPETICIONES,
    SALDO_INICIAL,
    VENTA_YA_ANULADA,
    _Escenario,
    _limpiar_datos_confirmados,
)
from tests.integration.stock_utiles import crear_ubicacion_sql

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

CODIGO_VENTA_YA_ANULADA = "VENTA_YA_ANULADA"


class _EscenarioDeRuta(_Escenario):
    """La venta de la jornada J1 de la camioneta (confirmada con la jornada abierta: queda con J1)
    y las formas de anularla: por el lote `OFFLINE` y por el bus `ONLINE`."""

    def venta_de_la_jornada(self) -> tuple[UUID, UUID, UUID]:
        """`(venta_id, camioneta_id, jornada_id)`: 15 botellas de la camioneta con J1 `ABIERTA`."""
        ids: list[UUID] = []

        def _armar(e: Any) -> None:
            assert isinstance(e, EntornoAnulacion)
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            e.sesion.commit()
            jornada_id = e.crear_jornada(ubicacion_id=camioneta_id)
            venta_id = e.vender_y_obtener_id(ubicacion_id=str(camioneta_id))
            ids.extend([venta_id, camioneta_id, jornada_id])

        self.armar(_armar)
        return ids[0], ids[1], ids[2]

    def _item(self, venta_id: UUID, jornada_id: UUID, operation_id: UUID | None = None) -> ItemLote:
        e = self.entorno
        return ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=VENTA_ANULAR,
            version=1,
            modo="OFFLINE",
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=e.contenido_de_anulacion(venta_id),
            jornada_id=jornada_id,
        )

    def anular_por_el_lote(
        self, venta_id: UUID, jornada_id: UUID, operation_id: UUID | None = None
    ) -> Callable[[Session], Any]:
        """El bus completo por el lote (reserva, handler, auditoría y `commit`); devuelve el
        resultado del único ítem."""
        item = self._item(venta_id, jornada_id, operation_id)

        def _enviar(sesion: Session) -> sync_service.ResultadoItemLote:
            (resultado,) = sync_service.procesar_lote(
                sesion,
                RELOJ_ANULACION,
                organizacion_id=self.org,
                usuario_id=self.entorno.usuario_id,
                dispositivo_id=self.entorno.dispositivo_id,
                items=[item],
            )
            return resultado

        return _enviar

    def anular_offline_srv(self, venta_id: UUID, jornada_id: UUID) -> Callable[[Session], object]:
        """El handler `OFFLINE` sobre la sesión del hilo, SIN confirmar (para `_encadenado`)."""
        e = self.entorno
        sobre = SobreComando(
            operation_id=uuid4(),
            tipo=VENTA_ANULAR,
            version=1,
            modo="OFFLINE",
            organizacion_id=self.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=e.contenido_de_anulacion(venta_id),
            jornada_id=jornada_id,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        return lambda sesion: registrado.funcion(
            sobre, validado, sesion=sesion, reloj=RELOJ_ANULACION
        )


def _sin_doble_efecto(escenario: _EscenarioDeRuta, venta_id: UUID, camioneta_id: UUID) -> None:
    """Una sola fila de anulación, un solo reingreso y una sola acreditación; los libros cuadran."""
    assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
    assert escenario.anulaciones() == 1
    assert escenario.cantidad_de("stock_movimiento", "tipo = 'ANULACION_VENTA'") == 1
    assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_VENTA'") == 1
    assert escenario.saldo_de_stock(camioneta_id) == 48
    assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
    escenario.verificar_libros()


class TestAnulacionSinConexionContraAnulacionConConexion:
    """INV-06, INV-12, INV-13, VTA-20, ADR-058 D10: las dos esperan la venta `FOR UPDATE`; la
    segunda la relee `ANULADA` y responde `VENTA_YA_ANULADA`."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv06_en_carrera_libre_una_se_acepta_y_la_otra_responde_venta_ya_anulada(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        # Escenario: "Anulación sin conexión contra una anulación con conexión"
        escenario = _EscenarioDeRuta(database_url)
        venta_id, camioneta_id, jornada_id = escenario.venta_de_la_jornada()
        trabajos: list[Callable[[Session], Any]] = [
            escenario.anular_por_el_lote(venta_id, jornada_id),
            lambda sesion: escenario.anular(sesion, venta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        por_el_lote = resultados[0]
        offline_aceptada = por_el_lote.estado.startswith("ACEPTADO")
        online_aceptada = 1 in resultados
        assert offline_aceptada != online_aceptada, f"{resultados}, errores={errores}"
        if offline_aceptada:
            assert [type(error).__name__ for error in errores.values()] == [VENTA_YA_ANULADA]
        else:
            assert (por_el_lote.estado, por_el_lote.error_codigo) == (
                "RECHAZADO",
                CODIGO_VENTA_YA_ANULADA,
            )
            assert not errores
        _sin_doble_efecto(escenario, venta_id, camioneta_id)

    def test_inv13_con_la_anulacion_sin_conexion_primero_la_otra_espera_y_responde_ya_anulada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        # Escenario: "Anulación sin conexión contra una anulación con conexión"
        escenario = _EscenarioDeRuta(database_url)
        venta_id, camioneta_id, jornada_id = escenario.venta_de_la_jornada()

        primero, segundo = _encadenado(
            database_url,
            escenario.anular_offline_srv(venta_id, jornada_id),
            escenario.anular_srv(venta_id),
        )

        assert (primero, segundo) == (OK, VENTA_YA_ANULADA)
        _sin_doble_efecto(escenario, venta_id, camioneta_id)

    def test_inv13_con_la_anulacion_con_conexion_primero_la_sin_conexion_espera_y_es_rechazada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        # Escenario: "Anulación sin conexión contra una anulación con conexión"
        escenario = _EscenarioDeRuta(database_url)
        venta_id, camioneta_id, jornada_id = escenario.venta_de_la_jornada()

        primero, segundo = _encadenado(
            database_url,
            escenario.anular_srv(venta_id),
            escenario.anular_offline_srv(venta_id, jornada_id),
        )

        assert (primero, segundo) == (OK, VENTA_YA_ANULADA)
        _sin_doble_efecto(escenario, venta_id, camioneta_id)


class TestDobleEnvioSimultaneoDeLaMismaAnulacion:
    """INV-06, SYN-02: dos lotes con el mismo `operation_id` a la vez tienen un solo efecto y los
    dos reciben el mismo resultado."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv06_el_mismo_operation_id_a_la_vez_se_aplica_una_sola_vez(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        # Escenario: "Doble envío"
        escenario = _EscenarioDeRuta(database_url)
        venta_id, camioneta_id, jornada_id = escenario.venta_de_la_jornada()
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            escenario.anular_por_el_lote(venta_id, jornada_id, operation_id),
            escenario.anular_por_el_lote(venta_id, jornada_id, operation_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        primero, segundo = resultados[0], resultados[1]
        assert primero.estado == segundo.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert escenario.cantidad_de("comando", f"operation_id = '{operation_id}'") == 1
        _sin_doble_efecto(escenario, venta_id, camioneta_id)
