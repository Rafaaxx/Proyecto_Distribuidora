"""Change 24, tarea 4.1: `JORNADA_ENTREGAR` v1 por el lote contra PostgreSQL real (spec
`stock/rendicion-de-jornada`, requisito "La entrega del día marca la jornada como entregada";
`design.md` D1).

Se procesa por `sync_service.procesar_lote` porque es un comando solo `OFFLINE`: el lote valida la
jornada del sobre (`JORNADA_AJENA`) antes de reservar y el handler decide el resto.

Reglas citadas: RUT-05, RUT-09, INV-06, INV-21, SEG-06, SYN-02.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.core.clock import FixedClock
from app.modules.stock import jornadas_commands  # noqa: F401  (registra los handlers)
from app.modules.stock.models import Jornada
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)
ORIGEN = MOMENTO - timedelta(hours=2)
RELOJ = FixedClock(MOMENTO)
ENTREGAR = "JORNADA_ENTREGAR"

VENDEDOR = frozenset({"ABRIR_JORNADA"})


class Entorno:
    """Una organización con "Camioneta 1" (con toma), Juan (con `ABRIR_JORNADA`), Pedro (otro
    vendedor, otro dispositivo) y Ana (sin permisos)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan, self.dispositivo_juan = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=VENDEDOR
        )
        self.pedro, self.dispositivo_pedro = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=VENDEDOR
        )
        self.ana, self.dispositivo_ana = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset()
        )
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        sesion.commit()

    def jornada(
        self, estado: str = "ABIERTA", *, quien: str = "juan", ubicacion_id: UUID | None = None
    ) -> UUID:
        usuario, dispositivo = {
            "juan": (self.juan, self.dispositivo_juan),
            "pedro": (self.pedro, self.dispositivo_pedro),
            "ana": (self.ana, self.dispositivo_ana),
        }[quien]
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            ubicacion_id=ubicacion_id
            or crear_ubicacion_sql(self.sesion, self.org, tipo="VEHICULO", requiere_toma=True),
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id

    def entregar(
        self,
        jornada_id: UUID,
        *,
        quien: str = "juan",
        secuencia: int = 12,
        operation_id: UUID | None = None,
        modo: str = "OFFLINE",
    ) -> tuple[ItemLote, sync_service.ResultadoItemLote]:
        usuario, dispositivo = {
            "juan": (self.juan, self.dispositivo_juan),
            "pedro": (self.pedro, self.dispositivo_pedro),
            "ana": (self.ana, self.dispositivo_ana),
        }[quien]
        item = ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=ENTREGAR,
            version=1,
            modo=modo,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            occurred_at=ORIGEN,
            secuencia=secuencia,
            app_version="1.0.0",
            contenido={},
            jornada_id=jornada_id,
        )
        resultados = sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )
        return item, resultados[0]

    def leer(self, jornada_id: UUID) -> Jornada:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(Jornada).where(Jornada.organizacion_id == self.org, Jornada.id == jornada_id)
        ).one()

    def comandos(self, operation_id: UUID) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.organizacion_id == self.org, Comando.operation_id == operation_id)
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _sin_entrega(jornada: Jornada) -> None:
    assert (jornada.entregada_en, jornada.entrega_occurred_at, jornada.entrega_secuencia) == (
        None,
        None,
        None,
    )


# --- catálogo ----------------------------------------------------------------------------


def test_la_entrega_esta_declarada_solo_offline_con_abrir_jornada() -> None:
    """`02` §6.5, D1: solo por el lote, con el permiso de la jornada del vendedor."""
    declarado = catalogo_bus.tipo_declarado(ENTREGAR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (False, True)
    assert declarado.permisos == ("ABRIR_JORNADA",)
    assert registro.resolver_handler(ENTREGAR, 1).tipo == ENTREGAR


# --- aceptada ----------------------------------------------------------------------------


def test_rut05_la_entrega_guarda_momento_origen_y_secuencia_sin_cambiar_el_estado(
    entorno: Entorno,
) -> None:
    """Escenario "Entrega aceptada": la jornada sigue `ABIERTA` con la entrega registrada."""
    jornada_id = entorno.jornada()

    item, resultado = entorno.entregar(jornada_id, secuencia=12)

    assert resultado.estado == "ACEPTADO"
    jornada = entorno.leer(jornada_id)
    assert jornada.estado == "ABIERTA"
    assert (jornada.entregada_en, jornada.entrega_occurred_at, jornada.entrega_secuencia) == (
        MOMENTO,
        ORIGEN,
        12,
    )
    assert (jornada.rendida_en, jornada.cerrada_en, jornada.liberada_en) == (None, None, None)
    assert resultado.resultado is not None
    assert resultado.resultado["jornada_id"] == str(jornada_id)
    assert resultado.resultado["estado"] == "ABIERTA"
    assert entorno.comandos(item.operation_id) == 1


def test_rut05_otra_jornada_se_entrega_con_su_propia_secuencia(entorno: Entorno) -> None:
    """Triangulación: la secuencia guardada es la del sobre, no una fija."""
    jornada_id = entorno.jornada()

    entorno.entregar(jornada_id, secuencia=3)

    assert entorno.leer(jornada_id).entrega_secuencia == 3


# --- estados -----------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["LIBERADA", "EN_RENDICION", "CERRADA"])
def test_rut09_una_jornada_que_no_esta_abierta_se_rechaza_sin_cambios(
    entorno: Entorno, estado: str
) -> None:
    """Escenario "Entrega de una jornada liberada" y sus hermanas: `JORNADA_ESTADO_INVALIDO`."""
    jornada_id = entorno.jornada(estado)

    item, resultado = entorno.entregar(jornada_id)

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "JORNADA_ESTADO_INVALIDO")
    jornada = entorno.leer(jornada_id)
    assert jornada.estado == estado
    _sin_entrega(jornada)
    assert entorno.comandos(item.operation_id) == 0


def test_rut05_una_segunda_entrega_con_otro_identificador_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Segunda entrega con otro identificador": la original no cambia."""
    jornada_id = entorno.jornada()
    entorno.entregar(jornada_id, secuencia=12)

    _, segunda = entorno.entregar(jornada_id, secuencia=15)

    assert (segunda.estado, segunda.error_codigo) == ("RECHAZADO", "JORNADA_YA_ENTREGADA")
    jornada = entorno.leer(jornada_id)
    assert (jornada.entregada_en, jornada.entrega_secuencia) == (MOMENTO, 12)


# --- dueño, permiso, organización -------------------------------------------------------------


def test_inv21_la_jornada_de_otro_se_rechaza_con_jornada_ajena(entorno: Entorno) -> None:
    """Escenario "Entrega de la jornada de otro": Juan manda la jornada de Pedro."""
    ajena = entorno.jornada(quien="pedro")

    item, resultado = entorno.entregar(ajena, quien="juan")

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "JORNADA_AJENA")
    _sin_entrega(entorno.leer(ajena))
    assert entorno.comandos(item.operation_id) == 0


def test_inv21_una_jornada_inexistente_se_rechaza_con_jornada_inexistente(
    entorno: Entorno,
) -> None:
    """Triangulación: sin jornada en la organización, `JORNADA_INEXISTENTE` y nada escrito."""
    item, resultado = entorno.entregar(uuid4())

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "JORNADA_INEXISTENTE")
    assert entorno.comandos(item.operation_id) == 0


def test_seg06_sin_abrir_jornada_se_rechaza_con_permiso_requerido(entorno: Entorno) -> None:
    """Escenario "Entrega sin permiso": el usuario es dueño de la jornada pero no tiene
    `ABRIR_JORNADA`."""
    jornada_id = entorno.jornada(quien="ana")

    item, resultado = entorno.entregar(jornada_id, quien="ana")

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
    _sin_entrega(entorno.leer(jornada_id))
    assert entorno.comandos(item.operation_id) == 0


# --- doble envío -------------------------------------------------------------------------


def test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_cambiar_la_entrega(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío de la entrega": mismo `operation_id`, mismo resultado."""
    jornada_id = entorno.jornada()
    operation_id = uuid4()
    _, primero = entorno.entregar(jornada_id, secuencia=12, operation_id=operation_id)

    _, segundo = entorno.entregar(jornada_id, secuencia=12, operation_id=operation_id)

    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    jornada = entorno.leer(jornada_id)
    assert (jornada.entregada_en, jornada.entrega_secuencia) == (MOMENTO, 12)
    assert entorno.comandos(operation_id) == 1
