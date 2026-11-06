"""Change 25, tarea 19.1: concurrencia real de la revisión de observaciones y rechazos contra
PostgreSQL real (Testcontainers, `READ COMMITTED`) y con commits reales, con el arnés de
`test_rendicion_concurrente.py`: cada hilo tiene su propia sesión, confirma su propia transacción
y arranca junto a los otros en una barrera. Nunca hay rollback externo (`CLAUDE.md` §4).

Specs `sync/revision-de-observaciones` ("Dos personas resuelven a la vez"),
`sync/rechazos-sin-conexion` ("Dos resoluciones a la vez") y `stock/rendicion-de-jornada`
("Resolución y rendición a la vez"; `design.md` D1, D7, D9 = B, precisión 5):

- dos resoluciones de la misma observación: una se acepta y la otra es `OBSERVACION_YA_RESUELTA`;
- dos resoluciones en bloque con listas cruzadas: sin interbloqueo (`FOR UPDATE` en orden de `id`);
- dos resoluciones del mismo rechazo: una se acepta y la otra es `RECHAZO_YA_RESUELTO`;
- dos lotes simultáneos que registran el mismo rechazo dejan un solo registro (SYN-02);
- resolver el último rechazo y rendir la jornada a la vez: sin interbloqueo; la rendición se acepta
  solo si vio el rechazo resuelto, y un rechazo que se registra a la vez nunca deja una rendición
  aceptada que no haya visto un rechazo confirmado antes de su consulta.

Reglas citadas: SYN-02, SYN-08, RUT-05, INV-01, INV-06.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from revision_utiles import sembrar_cuarentena, sembrar_observaciones, sembrar_rechazo
from sqlalchemy.orm import Session
from ventas_anular_utiles import MOMENTO_ANULACION, RELOJ_ANULACION

from app.modules.sync import revision_casos as casos
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote
from tests.concurrency.test_jornadas_concurrencia import _dos_ordenes
from tests.concurrency.test_rendicion_concurrente import (
    REPETICIONES,
    _EscenarioDeRendicionYVenta,
    _interbloqueos,
)
from tests.concurrency.test_stock_concurrencia import _en_paralelo
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.concurrency.test_ventas_anulacion_concurrencia import (  # noqa: F401 -- fixture compartida
    _limpiar_datos_confirmados,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

OBSERVACION_YA_RESUELTA = "ObservacionYaResueltaError"
RECHAZO_YA_RESUELTO = "RechazoYaResueltoError"
RECHAZOS_PENDIENTES = "RechazosPendientesError"


class _EscenarioDeRevision(_EscenarioDeRendicionYVenta):
    """La camioneta con su jornada entregada (heredada) más lo que se revisa."""

    def sembrar_observaciones(self, *codigos: str) -> list[UUID]:
        ids: list[UUID] = []

        def _armar(e: Any) -> None:
            ids.extend(
                sembrar_observaciones(
                    e.sesion,
                    e.org,
                    usuario_id=e.usuario_id,
                    dispositivo_id=e.dispositivo_id,
                    codigos=codigos,
                ).observaciones
            )

        self.armar(_armar)
        return ids

    def sembrar_rechazo(self) -> UUID:
        ids: list[UUID] = []

        def _armar(e: Any) -> None:
            ids.append(
                sembrar_rechazo(
                    e.sesion,
                    e.org,
                    usuario_id=e.usuario_id,
                    dispositivo_id=e.dispositivo_id,
                    jornada_id=self.jornada_id,
                )
            )

        self.armar(_armar)
        return ids[0]

    def sembrar_cuarentena(self) -> UUID:
        ids: list[UUID] = []

        def _armar(e: Any) -> None:
            ids.append(
                sembrar_cuarentena(
                    e.sesion, e.org, usuario_id=e.usuario_id, dispositivo_id=e.dispositivo_id
                )
            )

        self.armar(_armar)
        return ids[0]

    def resolver_observaciones(self, ids: list[UUID]) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: casos.resolver_observaciones(
            self.org,
            sesion,
            RELOJ_ANULACION,
            usuario_id=e.usuario_id,
            observaciones=ids,
            comentario="Revisado",
        )

    def resolver_rechazo(
        self, rechazo_id: UUID, origen: str = "RECHAZO"
    ) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: casos.resolver_rechazo(
            self.org,
            sesion,
            RELOJ_ANULACION,
            usuario_id=e.usuario_id,
            origen=origen,
            rechazo_id=rechazo_id,
            comentario="Revisado",
            vinculo_tipo=None,
            vinculo_id=None,
        )

    def lote_rechazado(self, operation_id: UUID) -> Callable[[Session], Any]:
        """El lote con una venta de totales incoherentes (`TOTALES_INCONSISTENTES`)."""
        e = self.entorno
        contenido = self._contenido_de_venta()
        contenido["total"] = "31250.01"
        item = ItemLote(
            operation_id=operation_id,
            tipo="VENTA_CONFIRMAR",
            version=1,
            modo="OFFLINE",
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=self.jornada_id,
        )

        def _enviar(sesion: Session) -> sync_service.ResultadoItemLote:
            (resultado,) = sync_service.procesar_lote(
                sesion,
                RELOJ_ANULACION,
                organizacion_id=self.org,
                usuario_id=e.usuario_id,
                dispositivo_id=e.dispositivo_id,
                items=[item],
            )
            return resultado

        return _enviar

    def insertar_rechazo(self) -> Callable[[Session], object]:
        """El `INSERT` del registro de un rechazo de la jornada, SIN confirmar."""
        e = self.entorno

        def _insertar(sesion: Session) -> None:
            sembrar_rechazo(
                sesion,
                self.org,
                usuario_id=e.usuario_id,
                dispositivo_id=e.dispositivo_id,
                jornada_id=self.jornada_id,
            )

        return _insertar

    # --- lecturas confirmadas -----------------------------------------------------------

    def observaciones_resueltas(self) -> int:
        return self.cantidad_de("observacion", "estado = 'RESUELTA'")

    def rechazos(self, estado: str | None = None) -> int:
        donde = "true" if estado is None else f"estado = '{estado}'"
        return self.cantidad_de("comando_rechazado", donde)


class TestDosPersonasResuelvenLaMismaObservacion:
    """SYN-08, INV-01, D1: la fila se toma `FOR UPDATE`; la segunda espera, ve la resolución de la
    primera y es `OBSERVACION_YA_RESUELTA`, sin escribir nada."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_una_se_acepta_y_la_otra_ya_estaba_resuelta(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        (observacion,) = escenario.sembrar_observaciones("STOCK_NEGATIVO")
        trabajos: list[Callable[[Session], Any]] = [
            escenario.resolver_observaciones([observacion]),
            escenario.resolver_observaciones([observacion]),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted([OK, OBSERVACION_YA_RESUELTA]), (
            f"{resultados}, errores={errores}"
        )
        assert escenario.observaciones_resueltas() == 1

    def test_la_segunda_espera_la_fila_de_la_primera(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        (observacion,) = escenario.sembrar_observaciones("STOCK_NEGATIVO")
        resolver = escenario.resolver_observaciones([observacion])

        resultado = _encadenado(database_url, lambda s: resolver(s), lambda s: resolver(s))

        assert resultado == (OK, OBSERVACION_YA_RESUELTA)
        assert escenario.observaciones_resueltas() == 1


class TestResolucionesEnBloqueConListasCruzadas:
    """SYN-08, INV-01, D1: `[a, b, c]` contra `[c, b, a]` toman las filas en orden de `id`: una
    gana las tres, la otra es `OBSERVACION_YA_RESUELTA` y PostgreSQL no detecta un interbloqueo."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_sin_interbloqueo_y_todo_o_nada(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        a, b, c = escenario.sembrar_observaciones(
            "STOCK_NEGATIVO", "VENTA_SIN_COSTO", "DESCUENTO_DIFIERE"
        )
        antes = _interbloqueos(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.resolver_observaciones([a, b, c]),
            escenario.resolver_observaciones([c, b, a]),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted([OK, OBSERVACION_YA_RESUELTA]), (
            f"{resultados}, errores={errores}"
        )
        threading.Event().wait(timeout=2)  # las estadísticas de PostgreSQL se asientan tarde
        assert _interbloqueos(database_url) == antes
        assert escenario.observaciones_resueltas() == 3  # las tres de una sola resolución (INV-01)


class TestDosPersonasResuelvenElMismoRechazo:
    """SYN-08, INV-01, D7: el rechazo (o la cuarentena) se toma `FOR UPDATE`; el segundo es
    `RECHAZO_YA_RESUELTO` y no pisa el comentario ni el momento del primero."""

    @pytest.mark.parametrize("origen", ["RECHAZO", "CUARENTENA"])
    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_uno_se_acepta_y_el_otro_ya_estaba_resuelto(
        self, database_url: str, _engine_de_sesion, ronda: int, origen: str
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        rechazo = (
            escenario.sembrar_rechazo() if origen == "RECHAZO" else escenario.sembrar_cuarentena()
        )
        trabajos: list[Callable[[Session], Any]] = [
            escenario.resolver_rechazo(rechazo, origen),
            escenario.resolver_rechazo(rechazo, origen),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert sorted(resultados.values()) == sorted([OK, RECHAZO_YA_RESUELTO]), (
            f"{resultados}, errores={errores}"
        )
        tabla = "comando_rechazado" if origen == "RECHAZO" else "comando_cuarentena"
        columna = "resuelto_en" if origen == "RECHAZO" else "revisado_en"
        assert escenario.cantidad_de(tabla, f"{columna} IS NOT NULL") == 1


class TestDosLotesRegistranElMismoRechazo:
    """SYN-02, D6: `INSERT ... ON CONFLICT DO NOTHING` sobre `(organizacion_id, operation_id)`:
    dos lotes con la misma operación rechazada dejan un solo registro."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_el_reenvio_simultaneo_deja_un_solo_registro(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        operacion = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            escenario.lote_rechazado(operacion),
            escenario.lote_rechazado(operacion),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert escenario.rechazos() == 1
        assert escenario.cantidad_de("venta") == 0


class TestResolucionContraRendicion:
    """RUT-05, INV-01, D9 = B, precisión 5: la rendición toma la jornada (`FOR NO KEY UPDATE`) y
    solo LEE los rechazos; la resolución toma el rechazo y no toca la jornada. No hay ciclo posible
    y la rendición se acepta solo si vio el rechazo ya resuelto."""

    @pytest.mark.parametrize("resolucion_primero", _dos_ordenes("resolucion", "rendicion"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, resolucion_primero: bool
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        rechazo = escenario.sembrar_rechazo()
        resolver = escenario.resolver_rechazo(rechazo)
        rendir = escenario.rendir_srv()

        if resolucion_primero:
            # La resolución sin confirmar: la rendición lee lo confirmado, no la ve y no espera.
            resultado = _encadenado(database_url, lambda s: resolver(s), lambda s: rendir(s))
            assert resultado == (OK, RECHAZOS_PENDIENTES)
        else:
            # La rendición toma la jornada y no bloquea al rechazo; ve el rechazo pendiente.
            resultado = _encadenado(database_url, lambda s: rendir(s), lambda s: resolver(s))
            assert resultado == (RECHAZOS_PENDIENTES, OK)
        assert escenario.rendiciones() == 0  # el rechazo no dejó escrito nada
        assert escenario.rechazos("RESUELTO") == 1

    def test_la_rendicion_reintentada_despues_de_resolver_se_acepta(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        rechazo = escenario.sembrar_rechazo()
        resolver = escenario.resolver_rechazo(rechazo)
        rendir = escenario.rendir_srv()

        primera, _ = _en_paralelo(database_url, [lambda s: rendir(s)])
        assert primera[0] == RECHAZOS_PENDIENTES
        _en_paralelo(database_url, [lambda s: resolver(s)])
        segunda, errores = _en_paralelo(database_url, [lambda s: rendir(s)])

        assert segunda[0] == OK, f"{segunda}, errores={errores}"
        assert escenario.rendiciones() == 1

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo_y_la_rendicion_solo_ve_lo_resuelto(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        rechazo = escenario.sembrar_rechazo()
        antes = _interbloqueos(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.resolver_rechazo(rechazo),
            escenario.rendir_srv(),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        assert resultados[1] in {OK, RECHAZOS_PENDIENTES}, f"{resultados}, errores={errores}"
        threading.Event().wait(timeout=2)
        assert _interbloqueos(database_url) == antes
        assert escenario.rechazos("RESUELTO") == 1
        # Una rendición aceptada vio el rechazo ya resuelto: el único que había.
        assert escenario.rendiciones() == (1 if resultados[1] == OK else 0)


class TestRegistroDeUnRechazoContraRendicion:
    """RUT-05, INV-01, D9 = B: el `INSERT` de un rechazo de la jornada toma la jornada con
    `FOR KEY SHARE` (la clave foránea) y la rendición, `FOR NO KEY UPDATE`: no se esperan. La
    rendición lee lo confirmado: nunca queda aceptada una rendición que no vio un rechazo que ya
    estaba confirmado antes de su consulta."""

    def test_un_rechazo_confirmado_antes_de_la_consulta_la_bloquea(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        escenario.sembrar_rechazo()  # confirmado
        rendir = escenario.rendir_srv()

        resultados, errores = _en_paralelo(database_url, [lambda s: rendir(s)])

        assert resultados[0] == RECHAZOS_PENDIENTES, f"{resultados}, errores={errores}"
        assert escenario.rendiciones() == 0

    @pytest.mark.parametrize("insercion_primero", _dos_ordenes("insercion", "rendicion"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, insercion_primero: bool
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        insertar = escenario.insertar_rechazo()
        rendir = escenario.rendir_srv()
        antes = _interbloqueos(database_url)

        if insercion_primero:
            # El rechazo sin confirmar todavía no existe para la rendición (lee lo confirmado).
            resultado = _encadenado(database_url, lambda s: insertar(s), lambda s: rendir(s))
        else:
            resultado = _encadenado(database_url, lambda s: rendir(s), lambda s: insertar(s))

        assert resultado == (OK, OK)  # ninguna espera a la otra: no hay ciclo
        threading.Event().wait(timeout=2)
        assert _interbloqueos(database_url) == antes
        assert escenario.rendiciones() == 1
        assert escenario.rechazos("PENDIENTE") == 1

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        escenario = _EscenarioDeRevision(database_url)
        antes = _interbloqueos(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.insertar_rechazo(),
            escenario.rendir_srv(),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        # Si el rechazo se confirmó antes de la consulta de la rendición, la rendición lo vio y se
        # rechazó; si no, se aceptó sin él. Nunca se acepta habiendo un rechazo ya confirmado.
        assert resultados[1] in {OK, RECHAZOS_PENDIENTES}, f"{resultados}, errores={errores}"
        threading.Event().wait(timeout=2)
        assert _interbloqueos(database_url) == antes
        assert escenario.rechazos("PENDIENTE") == 1
        assert escenario.rendiciones() == (1 if resultados[1] == OK else 0)
