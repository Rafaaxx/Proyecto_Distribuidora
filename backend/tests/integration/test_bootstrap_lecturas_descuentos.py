"""Change 21, tarea 1.3 (`design.md` D6; spec `sync/bootstrap`, requisito "trae las reglas de
descuento y el contexto de venta"): las reglas `ACTIVA` con vigencia no terminada a un momento, con
nombre, alcances, prioridad, acumulable y vigencia, por `descuentos/service.py`.

Reglas citadas: DSC-01, DSC-02, DSC-05, INV-21.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from descuentos_utiles import MODIFICAR, MOMENTO, Entorno
from sqlalchemy.orm import Session

from app.modules.descuentos import service as descuentos_service
from app.modules.descuentos.service import AlcanceRegla

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DIA = timedelta(days=1)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _activa(entorno: Entorno, **cambios: object) -> UUID:
    regla_id = entorno.crear_regla_descuento(**cambios)
    entorno.activar_regla(regla_id)
    return regla_id


def _no_vencidas(entorno: Entorno, *, org: UUID | None = None, momento=MOMENTO):  # type: ignore[no-untyped-def]
    return descuentos_service.reglas_para_dispositivo(org or entorno.org, entorno.sesion, momento)


def test_dsc01_trae_la_vigente_y_la_que_empieza_mas_tarde_no_la_vencida(entorno: Entorno) -> None:
    """Escenario "Regla programada para la tarde": la que empieza hoy a las 14:00 figura con su
    vigencia; la que terminó ayer no."""
    vigente = _activa(entorno, nombre="Vigente")
    tarde = _activa(
        entorno,
        nombre="De la tarde",
        vigencia_desde=(MOMENTO + timedelta(hours=2)).isoformat(),
    )
    vencida = _activa(entorno, nombre="Vencida", vigencia_desde=(MOMENTO - 10 * DIA).isoformat())
    entorno.enviar(
        MODIFICAR, {"regla_id": str(vencida), "vigencia_hasta": (MOMENTO - DIA).isoformat()}
    )

    reglas = _no_vencidas(entorno)

    assert {r.regla.id for r in reglas} == {str(vigente), str(tarde)}
    de_la_tarde = next(r for r in reglas if r.regla.id == str(tarde))
    assert de_la_tarde.vigencia_desde == MOMENTO + timedelta(hours=2)
    assert de_la_tarde.vigencia_hasta is None


def test_excluye_borradores_y_pausadas(entorno: Entorno) -> None:
    entorno.crear_regla_descuento(nombre="Borrador")
    pausada = _activa(entorno, nombre="Pausada")
    entorno.pausar_regla(pausada)
    activa = _activa(entorno, nombre="Activa")

    assert [r.regla.id for r in _no_vencidas(entorno)] == [str(activa)]


def test_cada_regla_trae_nombre_alcances_prioridad_y_acumulable(entorno: Entorno) -> None:
    regla_id = _activa(
        entorno,
        nombre="Marca del mes",
        tipo="VOLUMEN_ALCANCE",
        alcances=[
            {"tipo": "MARCA", "entidad_id": str(entorno.marca_id)},
            {"tipo": "PRODUCTO", "entidad_id": str(entorno.vino_id)},
        ],
        acumulable=True,
        prioridad=3,
        vigencia_hasta=(MOMENTO + 5 * DIA).isoformat(),
    )

    (regla,) = _no_vencidas(entorno)

    assert regla.nombre == "Marca del mes"
    assert regla.regla.id == str(regla_id)
    assert (regla.regla.acumulable, regla.regla.prioridad) == (True, 3)
    assert regla.regla.accion_porcentaje == Decimal("0.050000")
    assert set(regla.regla.alcances) == {
        AlcanceRegla("MARCA", str(entorno.marca_id)),
        AlcanceRegla("PRODUCTO", str(entorno.vino_id)),
    }
    assert regla.vigencia_hasta == MOMENTO + 5 * DIA


def test_el_extremo_hasta_esta_excluido(entorno: Entorno) -> None:
    """DSC-01: la vigencia es `desde <= momento < hasta`; en el instante `hasta` ya terminó."""
    fin = MOMENTO + 3 * DIA
    regla = _activa(entorno, vigencia_hasta=fin.isoformat())

    assert [r.regla.id for r in _no_vencidas(entorno, momento=fin - timedelta(microseconds=1))] == [
        str(regla)
    ]
    assert _no_vencidas(entorno, momento=fin) == []


def test_las_devuelve_por_prioridad_y_luego_por_antiguedad(entorno: Entorno) -> None:
    segunda = _activa(entorno, nombre="B", prioridad=2)
    primera = _activa(entorno, nombre="A", prioridad=1)

    assert [r.regla.id for r in _no_vencidas(entorno)] == [str(primera), str(segunda)]


def test_inv21_no_trae_reglas_de_otra_organizacion(entorno: Entorno, db_session: Session) -> None:
    propia = _activa(entorno)
    ajeno = Entorno(db_session)
    _activa(ajeno, nombre="Ajena")

    assert [r.regla.id for r in _no_vencidas(entorno)] == [str(propia)]
