"""Tarea 6.5 (change 18a; spec `ventas/confirmacion-de-venta`, requisito de número;
`design.md` D4, D17 nivel 6): `identidad/service.py` expone la numeración del dispositivo de la
sesión (prefijo y último correlativo) y una actualización `max(actual, propuesto)` que nunca
retrocede. `avanzar_correlativo_dispositivo` no cambia.

Reglas citadas: VTA-06 (ADR-008), INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import CorrelativoNoAvanzaError

MOMENTO = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _dispositivo(sesion: Session, organizacion_id, nombre: str = "Tablet"):  # type: ignore[no-untyped-def]
    return identidad_service.registrar_dispositivo(
        organizacion_id, sesion, RELOJ, dispositivo_id=nuevo_id(), nombre=nombre
    )


def _ultimo(sesion: Session, organizacion_id, dispositivo_id) -> int:  # type: ignore[no-untyped-def]
    sesion.expire_all()
    dispositivo = repository.obtener_dispositivo_por_id(organizacion_id, dispositivo_id, sesion)
    assert dispositivo is not None
    return dispositivo.ultimo_correlativo


# --- lectura de la numeración (D4) ----------------------------------------------------------


def test_vta06_la_numeracion_trae_el_prefijo_y_el_ultimo_correlativo_del_dispositivo(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    primero = _dispositivo(db_session, org, "Oficina")
    segundo = _dispositivo(db_session, org, "Camioneta 2")
    identidad_service.registrar_correlativo_maximo(
        org, db_session, dispositivo_id=segundo.id, propuesto=41
    )

    uno = identidad_service.obtener_numeracion_de_dispositivo(
        org, db_session, dispositivo_id=primero.id
    )
    otro = identidad_service.obtener_numeracion_de_dispositivo(
        org, db_session, dispositivo_id=segundo.id
    )

    assert uno is not None
    assert (uno.prefijo, uno.ultimo_correlativo) == (primero.prefijo, 0)
    assert otro is not None
    assert (otro.prefijo, otro.ultimo_correlativo) == (segundo.prefijo, 41)
    assert uno.prefijo != otro.prefijo


def test_inv21_la_numeracion_de_un_dispositivo_ajeno_o_inexistente_es_nula(
    db_session: Session,
) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    dispositivo_ajeno = _dispositivo(db_session, ajena)

    assert (
        identidad_service.obtener_numeracion_de_dispositivo(
            propia, db_session, dispositivo_id=dispositivo_ajeno.id
        )
        is None
    )
    assert (
        identidad_service.obtener_numeracion_de_dispositivo(
            propia, db_session, dispositivo_id=nuevo_id()
        )
        is None
    )


# --- actualización max(actual, propuesto) (D4, D17 nivel 6) -----------------------------------


@pytest.mark.parametrize(
    ("actual", "propuesto", "esperado"),
    [(41, 42, 42), (50, 45, 50), (50, 50, 50), (0, 1, 1)],
)
def test_vta06_el_correlativo_pasa_al_mayor_y_nunca_retrocede(
    db_session: Session, actual: int, propuesto: int, esperado: int
) -> None:
    """Escenarios "Número aceptado" (41 -> 42) y "Un número menor no retrocede" (50 y 45)."""
    org = crear_organizacion(db_session).id
    dispositivo = _dispositivo(db_session, org)
    if actual:
        identidad_service.registrar_correlativo_maximo(
            org, db_session, dispositivo_id=dispositivo.id, propuesto=actual
        )

    resultado = identidad_service.registrar_correlativo_maximo(
        org, db_session, dispositivo_id=dispositivo.id, propuesto=propuesto
    )

    assert resultado == esperado
    assert _ultimo(db_session, org, dispositivo.id) == esperado


def test_vta06_el_mismo_correlativo_dos_veces_no_falla(db_session: Session) -> None:
    """A diferencia de `avanzar_correlativo_dispositivo`, no exige superar al actual."""
    org = crear_organizacion(db_session).id
    dispositivo = _dispositivo(db_session, org)

    assert (
        identidad_service.registrar_correlativo_maximo(
            org, db_session, dispositivo_id=dispositivo.id, propuesto=7
        )
        == 7
    )
    assert (
        identidad_service.registrar_correlativo_maximo(
            org, db_session, dispositivo_id=dispositivo.id, propuesto=7
        )
        == 7
    )


def test_inv21_el_correlativo_de_un_dispositivo_ajeno_no_se_toca(db_session: Session) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    dispositivo_ajeno = _dispositivo(db_session, ajena)

    with pytest.raises(ValueError, match="no encontrado"):
        identidad_service.registrar_correlativo_maximo(
            propia, db_session, dispositivo_id=dispositivo_ajeno.id, propuesto=9
        )

    assert _ultimo(db_session, ajena, dispositivo_ajeno.id) == 0


# --- lo que no cambia ------------------------------------------------------------------------


def test_vta06_avanzar_correlativo_sigue_exigiendo_superar_al_actual(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    dispositivo = _dispositivo(db_session, org)
    identidad_service.registrar_correlativo_maximo(
        org, db_session, dispositivo_id=dispositivo.id, propuesto=5
    )

    with pytest.raises(CorrelativoNoAvanzaError):
        identidad_service.avanzar_correlativo_dispositivo(
            org, db_session, dispositivo_id=dispositivo.id, propuesto=5
        )
    assert (
        identidad_service.avanzar_correlativo_dispositivo(
            org, db_session, dispositivo_id=dispositivo.id, propuesto=6
        )
        == 6
    )
