"""INV-16 contra PostgreSQL real, con una máquina de estados de Hypothesis (change 15, tarea 16.1).

INV-16 (`docs/01` §20): una ubicación que requiere toma, un usuario y un dispositivo tienen a lo
sumo una jornada no cerrada (`ABIERTA` o `EN_RENDICION`). Acá se prueba con la base y el servicio
reales: varios usuarios, dispositivos y ubicaciones ejecutan secuencias aleatorias de abrir,
rendir, cerrar y liberar por `stock_service`, contra un modelo de referencia que dice qué debe
pasar en cada paso. Después de cada paso:

- ninguna ubicación, ningún usuario y ningún dispositivo tiene más de una jornada no cerrada;
- el estado de cada jornada en la base es el del modelo;
- toda transición rechazada (`JORNADA_ESTADO_INVALIDO`) deja la fila de la jornada exactamente
  como estaba (INV-01, TR-06), y toda apertura rechazada no deja ninguna jornada nueva.

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la invariante, no
de concurrencia (esa confirma transacciones reales: `tests/concurrency/test_jornadas_
concurrencia.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from hypothesis import HealthCheck, event, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)
from sqlalchemy import text
from sqlalchemy.orm import Session, SessionTransaction

from app.core.clock import FixedClock
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    DispositivoConJornadaError,
    JornadaEstadoInvalidoError,
    UbicacionSinTomaError,
    UbicacionTomadaError,
    UsuarioConJornadaError,
)
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_motivo_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

ABIERTA = "ABIERTA"
EN_RENDICION = "EN_RENDICION"
CERRADA = "CERRADA"
LIBERADA = "LIBERADA"
NO_CERRADAS = (ABIERTA, EN_RENDICION)

CANTIDAD_DE_ACTORES = 3
CANTIDAD_DE_VEHICULOS = 3
INDICE_DEL_DEPOSITO = CANTIDAD_DE_VEHICULOS  # la cuarta ubicación no requiere toma


class _Mundo(RuleBasedStateMachine):
    """Tres usuarios y tres dispositivos (se combinan en cualquier par), tres vehículos con toma y
    un depósito sin toma, dentro de un `SAVEPOINT` por ejemplo."""

    sesion: Session

    def __init__(self) -> None:
        super().__init__()
        self._savepoint: SessionTransaction = self.sesion.begin_nested()
        self.org = crear_organizacion(self.sesion).id
        actores = [
            crear_usuario_y_dispositivo(self.sesion, self.org) for _ in range(CANTIDAD_DE_ACTORES)
        ]
        self.usuarios = [usuario for usuario, _ in actores]
        self.dispositivos = [dispositivo for _, dispositivo in actores]
        self.ubicaciones = [
            crear_ubicacion_sql(
                self.sesion, self.org, nombre=f"Camioneta {i}", tipo="VEHICULO", requiere_toma=True
            )
            for i in range(CANTIDAD_DE_VEHICULOS)
        ] + [crear_ubicacion_sql(self.sesion, self.org, nombre="Depósito")]
        self.motivo = crear_motivo_sql(self.sesion, self.org, ambito="LIBERACION_JORNADA")
        # Modelo de referencia: jornadas en orden de apertura con su estado, usuario, dispositivo
        # y ubicación.
        self.jornadas: list[dict[str, Any]] = []

    def teardown(self) -> None:
        self._savepoint.rollback()

    # --- lo que el modelo espera -----------------------------------------------------

    def _no_cerradas(self) -> list[dict[str, Any]]:
        return [j for j in self.jornadas if j["estado"] in NO_CERRADAS]

    def _rechazos_posibles(self, usuario: UUID, dispositivo: UUID, ubicacion: UUID) -> set[type]:
        """Los errores que puede dar una apertura según el modelo; vacío si debe aceptarse. Con
        más de un choque, la base informa el del primer índice que revisa: se admite cualquiera
        de los que corresponden."""
        if ubicacion == self.ubicaciones[INDICE_DEL_DEPOSITO]:
            return {UbicacionSinTomaError}
        posibles: set[type] = set()
        no_cerradas = self._no_cerradas()
        if any(j["ubicacion"] == ubicacion for j in no_cerradas):
            posibles.add(UbicacionTomadaError)
        if any(j["usuario"] == usuario for j in no_cerradas):
            posibles.add(UsuarioConJornadaError)
        if any(j["dispositivo"] == dispositivo for j in no_cerradas):
            posibles.add(DispositivoConJornadaError)
        return posibles

    def _fila(self, jornada_id: UUID) -> object:
        return self.sesion.execute(
            text(
                "SELECT row_to_json(j)::text FROM jornada j WHERE organizacion_id = :o AND id = :i"
            ),
            {"o": self.org, "i": jornada_id},
        ).scalar_one()

    def _cantidad_en_la_base(self) -> int:
        return int(
            self.sesion.execute(
                text("SELECT count(*) FROM jornada WHERE organizacion_id = :o"), {"o": self.org}
            ).scalar_one()
        )

    # --- reglas -----------------------------------------------------------------------

    @rule(
        usuario=st.integers(0, CANTIDAD_DE_ACTORES - 1),
        dispositivo=st.integers(0, CANTIDAD_DE_ACTORES - 1),
        ubicacion=st.integers(0, CANTIDAD_DE_VEHICULOS),
    )
    def abrir(self, usuario: int, dispositivo: int, ubicacion: int) -> None:
        usuario_id, dispositivo_id = self.usuarios[usuario], self.dispositivos[dispositivo]
        ubicacion_id = self.ubicaciones[ubicacion]
        esperados = self._rechazos_posibles(usuario_id, dispositivo_id, ubicacion_id)
        antes = self._cantidad_en_la_base()
        try:
            with self.sesion.begin_nested():
                jornada = stock_service.abrir_jornada(
                    self.org,
                    self.sesion,
                    RELOJ,
                    ubicacion_id=ubicacion_id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    operation_id=uuid4(),
                    occurred_at=MOMENTO,
                )
        except (
            UbicacionTomadaError,
            UsuarioConJornadaError,
            DispositivoConJornadaError,
            UbicacionSinTomaError,
        ) as rechazo:
            assert type(rechazo) in esperados, (
                f"Rechazo inesperado {type(rechazo).__name__}; el modelo esperaba {esperados}."
            )
            assert self._cantidad_en_la_base() == antes  # INV-01: la rechazada no deja jornada
            event(f"apertura rechazada: {type(rechazo).__name__}")
            return
        event("apertura aceptada")
        assert not esperados, f"La apertura se aceptó pero el modelo esperaba {esperados}."
        assert jornada.estado == ABIERTA
        self.jornadas.append(
            {
                "id": jornada.id,
                "estado": ABIERTA,
                "usuario": usuario_id,
                "dispositivo": dispositivo_id,
                "ubicacion": ubicacion_id,
            }
        )

    def _transicionar(self, indice: int, destino: str, origenes: tuple[str, ...]) -> None:
        jornada = self.jornadas[indice % len(self.jornadas)]
        fila_antes = self._fila(jornada["id"])
        try:
            with self.sesion.begin_nested():
                if destino == EN_RENDICION:
                    stock_service.rendir_jornada(
                        self.org,
                        self.sesion,
                        jornada_id=jornada["id"],
                        usuario_id=self.usuarios[0],
                        occurred_at=MOMENTO,
                    )
                elif destino == CERRADA:
                    stock_service.cerrar_jornada(
                        self.org,
                        self.sesion,
                        jornada_id=jornada["id"],
                        usuario_id=self.usuarios[0],
                        occurred_at=MOMENTO,
                    )
                else:
                    stock_service.liberar_jornada(
                        self.org,
                        self.sesion,
                        jornada_id=jornada["id"],
                        usuario_id=self.usuarios[0],
                        motivo_id=self.motivo,
                        observacion=None,
                        occurred_at=MOMENTO,
                    )
        except JornadaEstadoInvalidoError:
            assert jornada["estado"] not in origenes, "El modelo admitía la transición."
            # TR-06, INV-01: la transición rechazada deja la jornada como estaba.
            assert self._fila(jornada["id"]) == fila_antes
            event(f"{destino} rechazada")
            return
        event(f"{destino} aceptada")
        assert jornada["estado"] in origenes, (
            "El servicio aceptó una transición que el modelo rechaza."
        )
        jornada["estado"] = destino

    @precondition(lambda self: bool(self.jornadas))
    @rule(indice=st.integers(0, 1000))
    def rendir(self, indice: int) -> None:
        self._transicionar(indice, EN_RENDICION, (ABIERTA,))

    @precondition(lambda self: bool(self.jornadas))
    @rule(indice=st.integers(0, 1000))
    def cerrar(self, indice: int) -> None:
        self._transicionar(indice, CERRADA, (EN_RENDICION,))

    @precondition(lambda self: bool(self.jornadas))
    @rule(indice=st.integers(0, 1000))
    def liberar(self, indice: int) -> None:
        self._transicionar(indice, LIBERADA, NO_CERRADAS)

    # --- INV-16, después de cada paso --------------------------------------------------

    @invariant()
    def a_lo_sumo_una_jornada_no_cerrada_por_ubicacion_usuario_y_dispositivo(self) -> None:
        for columna in ("ubicacion_id", "usuario_id", "dispositivo_id"):
            repetidas = self.sesion.execute(
                text(
                    f"SELECT {columna}, count(*) FROM jornada "  # noqa: S608
                    f"WHERE organizacion_id = :o AND estado IN ('ABIERTA', 'EN_RENDICION') "
                    f"GROUP BY {columna} HAVING count(*) > 1"
                ),
                {"o": self.org},
            ).all()
            assert repetidas == [], f"INV-16 violada por {columna}: {repetidas}"

    @invariant()
    def el_estado_de_cada_jornada_es_el_del_modelo(self) -> None:
        for jornada in self.jornadas:
            estado = self.sesion.execute(
                text("SELECT estado FROM jornada WHERE organizacion_id = :o AND id = :i"),
                {"o": self.org, "i": jornada["id"]},
            ).scalar_one()
            assert estado == jornada["estado"]
        assert self._cantidad_en_la_base() == len(self.jornadas)


def test_inv16_ninguna_ubicacion_usuario_ni_dispositivo_tiene_mas_de_una_jornada_no_cerrada(
    db_session: Session,
) -> None:
    """INV-16 con secuencias aleatorias de abrir, rendir, cerrar y liberar de varios usuarios,
    dispositivos y ubicaciones, y toda transición rechazada deja la jornada como estaba."""

    class _MundoDeLaSesion(_Mundo):
        sesion = db_session

    run_state_machine_as_test(
        _MundoDeLaSesion,
        settings=settings(
            max_examples=25,
            stateful_step_count=25,
            deadline=None,
            suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
        ),
    )
