"""Tarea 7.6 (change 19; spec `ventas/anulacion-de-venta`, requisito "La anulación queda auditada
con su motivo"; `design.md` D15; gobernanza ALTA), contra PostgreSQL real.

Una sola fila de auditoría del comando `VENTA_ANULAR` con el motivo, el usuario, el dispositivo y
el `operation_id`; en su observación, la cobranza anulada si la hubo y la constancia de la
ubicación tomada si se usó la excepción de `LIBERAR_UBICACION`, unidas por `; `. No emite
observaciones nuevas de SYN-07 y las pendientes de la venta siguen pendientes.

Reglas citadas: AUD-01, AUD-02, SYN-08, STK-09, ADR-022.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from ventas_anular_utiles import (
    PERMISOS_DE_ANULADOR,
    PERMISOS_DE_SUPERVISOR_DE_ANULACION,
    EntornoAnulacion,
)

from app.core.errors import DomainError
from app.modules.identidad.models import Auditoria
from app.modules.sync import service as sync_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoAnulacion:
    return EntornoAnulacion(db_session)


def _fila_unica(entorno: EntornoAnulacion, operation_id: UUID) -> Auditoria:
    entorno.sesion.rollback()
    (fila,) = entorno.auditoria_de(operation_id)
    return fila


def _venta_con_cobro(entorno: EntornoAnulacion) -> UUID:
    return entorno.vender_y_obtener_id(cobranza=entorno.cobranza())


def test_aud01_una_anulacion_deja_una_fila_con_motivo_usuario_dispositivo_y_operation_id(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Auditoría con devolución" (sin devolución a propósito: no hay cobranza anulada)
    venta_id = entorno.vender_y_obtener_id()

    comando = entorno.anular(venta_id)

    fila = _fila_unica(entorno, comando.operation_id)
    assert (fila.accion, fila.entidad, fila.origen) == ("VENTA_ANULAR", "comando", "COMANDO")
    assert fila.motivo_id == entorno.motivo_anulacion_id
    assert (fila.usuario_id, fila.dispositivo_id) == (entorno.usuario_id, entorno.dispositivo_id)
    assert fila.operation_id == comando.operation_id
    assert fila.observacion is None


def test_aud02_con_devolucion_la_observacion_nombra_la_cobranza_anulada(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Auditoría con devolución"
    venta_id = _venta_con_cobro(entorno)
    (cobranza,) = entorno.cobranzas()

    comando = entorno.anular(venta_id, devuelve_dinero=True)

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id == entorno.motivo_anulacion_id
    assert fila.observacion == f"cobranza anulada {cobranza.id}"


def test_aud02_sin_devolucion_la_cobranza_no_figura_en_la_observacion(
    entorno: EntornoAnulacion,
) -> None:
    venta_id = _venta_con_cobro(entorno)

    comando = entorno.anular(venta_id, devuelve_dinero=False)

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id == entorno.motivo_anulacion_id
    assert fila.observacion is None


def _camioneta_tomada_por_otro(entorno: EntornoAnulacion) -> tuple[UUID, UUID, UUID]:
    """`(venta_id, camioneta_id, jornada_de_pedro_id)`: venta desde la camioneta 2, que después
    toma Pedro."""
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    entorno.sesion.commit()
    venta_id = entorno.vender_y_obtener_id(
        ubicacion_id=str(camioneta_id), cobranza=entorno.cobranza()
    )
    pedro_id, pedro_dispositivo = entorno.otro_usuario(frozenset({"VENDER"}))
    jornada_id = entorno.crear_jornada(
        usuario_id=pedro_id, dispositivo_id=pedro_dispositivo, ubicacion_id=camioneta_id
    )
    return venta_id, camioneta_id, jornada_id


def test_stk09_la_excepcion_de_ubicacion_tomada_deja_la_constancia_y_la_cobranza_juntas(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Supervisor con `LIBERAR_UBICACION`": la auditoría nombra la jornada de Pedro.
    venta_id, _, jornada_id = _camioneta_tomada_por_otro(entorno)
    (cobranza,) = entorno.cobranzas()
    supervisor_id, supervisor_dispositivo = entorno.otro_usuario(
        PERMISOS_DE_SUPERVISOR_DE_ANULACION
    )

    comando = entorno.anular(
        venta_id,
        usuario_id=supervisor_id,
        dispositivo_id=supervisor_dispositivo,
        devuelve_dinero=True,
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.observacion == (
        f"cobranza anulada {cobranza.id}; ubicación tomada por la jornada {jornada_id}"
    )
    assert fila.usuario_id == supervisor_id


def test_stk09_solo_la_constancia_cuando_no_habia_cobranza(entorno: EntornoAnulacion) -> None:
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 3", requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    entorno.sesion.commit()
    venta_id = entorno.vender_y_obtener_id(ubicacion_id=str(camioneta_id))
    pedro_id, pedro_dispositivo = entorno.otro_usuario(frozenset({"VENDER"}))
    jornada_id = entorno.crear_jornada(
        usuario_id=pedro_id, dispositivo_id=pedro_dispositivo, ubicacion_id=camioneta_id
    )
    supervisor_id, supervisor_dispositivo = entorno.otro_usuario(
        PERMISOS_DE_SUPERVISOR_DE_ANULACION
    )

    comando = entorno.anular(
        venta_id, usuario_id=supervisor_id, dispositivo_id=supervisor_dispositivo
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.observacion == f"ubicación tomada por la jornada {jornada_id}"


def test_aud01_un_rechazo_no_deja_fila_de_auditoria(entorno: EntornoAnulacion) -> None:
    venta_id = entorno.vender_y_obtener_id()

    operation_id = uuid4()

    with pytest.raises(DomainError):
        entorno.anular(venta_id, operation_id=operation_id, observacion="a" * 501)

    entorno.sesion.rollback()
    assert entorno.auditoria_de(operation_id) == []


def test_syn08_las_observaciones_de_la_venta_siguen_pendientes_y_no_se_crean_nuevas(
    db_session: Session,
) -> None:
    # Escenario: "Observaciones de la venta": una venta con `STOCK_NEGATIVO` pendiente.
    entorno = EntornoAnulacion(
        db_session,
        permisos=PERMISOS_DE_ANULADOR | {"PERMITIR_STOCK_NEGATIVO"},
        stock_inicial=10,
    )
    venta_id = entorno.vender_y_obtener_id()  # 15 botellas con 10 en stock: queda en -5
    antes = sync_service.listar_observaciones_de_operacion(
        entorno.org, entorno.sesion, operacion_tipo="VENTA", operacion_id=venta_id
    )
    assert [(o.codigo, o.estado) for o in antes] == [("STOCK_NEGATIVO", "PENDIENTE")]

    entorno.anular(venta_id)

    entorno.sesion.expire_all()
    despues = sync_service.listar_observaciones_de_operacion(
        entorno.org, entorno.sesion, operacion_tipo="VENTA", operacion_id=venta_id
    )
    assert [(o.codigo, o.estado) for o in despues] == [("STOCK_NEGATIVO", "PENDIENTE")]
    assert entorno.observaciones() == ["STOCK_NEGATIVO"]
    assert entorno.stock() == 10
