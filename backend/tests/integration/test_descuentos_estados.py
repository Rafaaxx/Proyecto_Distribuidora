"""Change 16, tarea 8.3: `REGLA_DESCUENTO_ACTIVAR` y `REGLA_DESCUENTO_PAUSAR` v1 por el bus,
contra PostgreSQL real (spec `descuentos/reglas-de-descuento`, requisito "Una regla se activa y se
pausa siguiendo su máquina de estados").

Reglas citadas: `01` §18, DSC-01, INV-06, AUD-02, SEG-06, INV-21, `design.md` D16.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from descuentos_utiles import ACTIVAR, MODIFICAR, MOMENTO, PAUSAR, Entorno
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.descuentos.domain.errores import (
    RecursoNoEncontradoError,
    ReglaEstadoInvalidoError,
    VigenciaInvalidaError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_activar_un_borrador_define_la_vigencia_desde_con_el_momento_de_la_activacion(
    entorno: Entorno,
) -> None:
    """Escenario "Activar un borrador"."""
    regla_id = entorno.crear_regla_descuento()
    operation_id = uuid4()

    comando = entorno.activar_regla(regla_id, operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"regla_id": str(regla_id)}
    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.estado, regla.vigencia_desde, regla.vigencia_hasta) == ("ACTIVA", MOMENTO, None)
    assert regla.actualizado_por_id == entorno.usuario_id
    (auditoria,) = entorno.auditorias(ACTIVAR)
    assert auditoria.operation_id == operation_id


def test_activar_un_borrador_con_vigencia_desde_futura_la_respeta(entorno: Entorno) -> None:
    desde = MOMENTO + timedelta(days=7)
    regla_id = entorno.crear_regla_descuento(vigencia_desde=desde.isoformat())

    entorno.activar_regla(regla_id)

    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.estado, regla.vigencia_desde) == ("ACTIVA", desde)


def test_pausar_y_reactivar_conserva_la_misma_vigencia_desde(entorno: Entorno) -> None:
    """Escenario "Pausar y reactivar"."""
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)

    entorno.pausar_regla(regla_id)
    assert entorno.regla_de_descuento(regla_id).estado == "PAUSADA"

    entorno.activar_regla(regla_id)
    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.estado, regla.vigencia_desde) == ("ACTIVA", MOMENTO)
    assert len(entorno.auditorias(ACTIVAR)) == 2
    assert len(entorno.auditorias(PAUSAR)) == 1


def test_pausar_un_borrador_se_rechaza_y_no_deja_auditoria(entorno: Entorno) -> None:
    """Escenario "Pausar un borrador" (AUD-02: nada que auditar de un rechazo)."""
    regla_id = entorno.crear_regla_descuento()
    entorno.sesion.commit()

    with pytest.raises(ReglaEstadoInvalidoError) as error:
        entorno.pausar_regla(regla_id)

    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert entorno.regla_de_descuento(regla_id).estado == "BORRADOR"
    assert entorno.auditorias(PAUSAR) == []


def test_activar_una_regla_ya_activa_con_un_operation_id_nuevo_se_rechaza(
    entorno: Entorno,
) -> None:
    """Escenario "Activar una regla ya activa"."""
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.sesion.commit()

    with pytest.raises(ReglaEstadoInvalidoError):
        entorno.activar_regla(regla_id)

    entorno.sesion.rollback()
    assert len(entorno.auditorias(ACTIVAR)) == 1


def test_pausar_una_regla_ya_pausada_se_rechaza(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)
    entorno.sesion.commit()

    with pytest.raises(ReglaEstadoInvalidoError):
        entorno.pausar_regla(regla_id)


def test_ninguna_regla_vuelve_a_borrador(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)

    assert entorno.regla_de_descuento(regla_id).estado == "PAUSADA"


def test_activar_una_pausada_cuya_vigencia_ya_termino_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Activar una regla cuya vigencia ya terminó": 422 `VIGENCIA_INVALIDA`."""
    regla_id = entorno.crear_regla_descuento(
        vigencia_desde=(MOMENTO - timedelta(days=10)).isoformat()
    )
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)
    entorno.enviar(
        MODIFICAR,
        {"regla_id": str(regla_id), "vigencia_hasta": (MOMENTO - timedelta(days=1)).isoformat()},
    )
    entorno.sesion.commit()

    with pytest.raises(VigenciaInvalidaError) as error:
        entorno.activar_regla(regla_id)

    assert error.value.status_http == 422
    entorno.sesion.rollback()
    assert entorno.regla_de_descuento(regla_id).estado == "PAUSADA"


@pytest.mark.parametrize("comando", ["activar", "pausar"])
def test_sin_gestionar_descuentos_la_transicion_se_rechaza_con_403(
    entorno: Entorno, comando: str
) -> None:
    """Escenario "Activar sin permiso" (SEG-06)."""
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.sesion.commit()
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        if comando == "activar":
            entorno.activar_regla(regla_id)
        else:
            entorno.pausar_regla(regla_id)

    entorno.sesion.rollback()
    assert entorno.regla_de_descuento(regla_id).estado == "ACTIVA"


def test_inv06_el_doble_envio_de_la_activacion_devuelve_el_resultado_original(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío de la activación": sin rechazo por estado."""
    regla_id = entorno.crear_regla_descuento()
    operation_id = uuid4()

    primero = entorno.activar_regla(regla_id, operation_id=operation_id)
    segundo = entorno.activar_regla(regla_id, operation_id=operation_id)

    assert primero.estado == segundo.estado == "ACEPTADO"
    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias(ACTIVAR)) == 1
    assert entorno.regla_de_descuento(regla_id).estado == "ACTIVA"


def test_el_mismo_operation_id_con_otra_regla_es_inconsistente(entorno: Entorno) -> None:
    una = entorno.crear_regla_descuento()
    otra = entorno.crear_regla_descuento(nombre="Otra")
    operation_id = uuid4()
    entorno.activar_regla(una, operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.activar_regla(otra, operation_id=operation_id)


def test_aud02_una_fila_de_auditoria_por_comando_aceptado_y_ninguna_por_uno_rechazado(
    entorno: Entorno,
) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)
    entorno.sesion.commit()
    with pytest.raises(ReglaEstadoInvalidoError):
        entorno.pausar_regla(regla_id)
    entorno.sesion.rollback()

    assert [
        len(entorno.auditorias(tipo)) for tipo in ("REGLA_DESCUENTO_CREAR", ACTIVAR, PAUSAR)
    ] == [
        1,
        1,
        1,
    ]


def test_inv21_una_regla_de_otra_organizacion_responde_404_en_la_transicion(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session)
    regla_ajena = ajena.crear_regla_descuento()
    entorno.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.activar_regla(regla_ajena)

    assert error.value.status_http == 404
    entorno.sesion.rollback()
    assert ajena.regla_de_descuento(regla_ajena).estado == "BORRADOR"
