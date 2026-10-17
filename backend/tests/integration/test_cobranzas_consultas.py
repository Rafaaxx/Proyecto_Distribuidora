"""Change 17, tarea 10.1: casos de uso de lectura de `cobranzas` (`cobranzas/queries.py`) contra
PostgreSQL real: filtros, cursor, límite, detalle con medios y anulación, y aislamiento por
organización. El contrato HTTP (permisos, 422, 404) es de `test_cobranzas_consultas_api.py`.

Reglas citadas: COB-01, COB-02, COB-05, TR-04, INV-21, SEG-07 y `design.md` D14.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cobranzas_utiles import MOMENTO, PERMISOS_DE_ANULACION, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.cobranzas import queries
from app.modules.cobranzas.domain.errores import (
    CursorInvalidoError,
    RangoDeFechasInvalidoError,
    RecursoNoEncontradoError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_ANULACION)


def _ids(pagina: queries.PaginaDeCobranzas) -> list[object]:
    return [item.cobranza.id for item in pagina.items]


def _mover_en_el_tiempo(entorno: Entorno, cobranza_id: object, momento: datetime) -> None:
    """Las cobranzas son de solo inserción para la aplicación: para armar un historial con
    fechas distintas la prueba escribe con el usuario dueño de la base."""
    entorno.sesion.execute(
        text("UPDATE cobranza SET occurred_at = :m WHERE id = :id"),
        {"m": momento, "id": cobranza_id},
    )
    entorno.sesion.commit()


# Escenario: "Listado del día"
def test_el_listado_va_de_la_mas_reciente_a_la_mas_vieja_con_los_nombres(
    entorno: Entorno,
) -> None:
    """COB-01, TR-04: orden descendente por momento e identificador, con cliente y usuario."""
    vieja = entorno.registrar_y_obtener_id()
    nueva = entorno.registrar_y_obtener_id()
    _mover_en_el_tiempo(entorno, vieja, datetime(2026, 10, 1, 15, 0, tzinfo=UTC))
    _mover_en_el_tiempo(entorno, nueva, datetime(2026, 10, 9, 15, 0, tzinfo=UTC))

    pagina = queries.listar_cobranzas(entorno.org, entorno.sesion)

    assert _ids(pagina) == [nueva, vieja]
    assert pagina.cursor_siguiente is None
    primera = pagina.items[0]
    assert primera.cliente_nombre == "Kiosco La Esquina"
    assert primera.usuario_nombre
    assert primera.cobranza.importe == Decimal("50000.00")


def test_el_cursor_recorre_todas_las_cobranzas_una_sola_vez(entorno: Entorno) -> None:
    """Paginación por cursor `(momento, id)`: sin repetir ni saltear."""
    creadas = [entorno.registrar_y_obtener_id() for _ in range(5)]

    primera = queries.listar_cobranzas(entorno.org, entorno.sesion, limite=2)
    assert len(primera.items) == 2
    assert primera.cursor_siguiente is not None
    segunda = queries.listar_cobranzas(
        entorno.org, entorno.sesion, limite=2, cursor=primera.cursor_siguiente
    )
    tercera = queries.listar_cobranzas(
        entorno.org, entorno.sesion, limite=2, cursor=segunda.cursor_siguiente
    )

    vistas = _ids(primera) + _ids(segunda) + _ids(tercera)
    assert sorted(map(str, vistas)) == sorted(map(str, creadas))
    assert tercera.cursor_siguiente is None


def test_un_cursor_ilegible_es_cursor_invalido(entorno: Entorno) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        queries.listar_cobranzas(entorno.org, entorno.sesion, cursor="no-es-un-cursor")

    assert error.value.codigo == "CURSOR_INVALIDO"
    assert error.value.status_http == 422


def test_filtra_por_cliente_y_por_estado(entorno: Entorno) -> None:
    otro = entorno.crear_cliente(nombre="Almacén Don Pedro")
    entorno.sesion.commit()
    anulada = entorno.registrar_y_obtener_id()
    entorno.anular(anulada)
    vigente = entorno.registrar_y_obtener_id()
    de_otro = entorno.registrar_y_obtener_id(cliente_id=str(otro))

    por_cliente = queries.listar_cobranzas(entorno.org, entorno.sesion, cliente_id=otro)
    por_estado = queries.listar_cobranzas(entorno.org, entorno.sesion, estado="ANULADA")
    vigentes = queries.listar_cobranzas(entorno.org, entorno.sesion, estado="CONFIRMADA")

    assert _ids(por_cliente) == [de_otro]
    assert _ids(por_estado) == [anulada]
    assert sorted(map(str, _ids(vigentes))) == sorted(map(str, [vigente, de_otro]))


def test_filtra_por_usuario_y_por_jornada(entorno: Entorno) -> None:
    jornada = entorno.crear_jornada()
    con_jornada = entorno.registrar_y_obtener_id()  # la jornada abierta del usuario (D8)

    por_usuario = queries.listar_cobranzas(
        entorno.org, entorno.sesion, usuario_id=entorno.usuario_id
    )
    por_otro_usuario = queries.listar_cobranzas(entorno.org, entorno.sesion, usuario_id=uuid4())
    por_jornada = queries.listar_cobranzas(entorno.org, entorno.sesion, jornada_id=jornada)
    por_otra_jornada = queries.listar_cobranzas(entorno.org, entorno.sesion, jornada_id=uuid4())

    assert _ids(por_usuario) == [con_jornada]
    assert por_otro_usuario.items == []
    assert _ids(por_jornada) == [con_jornada]
    assert por_otra_jornada.items == []


def test_las_fechas_son_de_negocio_en_la_zona_de_la_organizacion(entorno: Entorno) -> None:
    """TR-04: `hasta` se incluye entero. 2026-10-10 02:00 UTC es 2026-10-09 en Buenos Aires
    (UTC-3), así que entra en `hasta=2026-10-09` y no en `desde=2026-10-10`."""
    cobranza = entorno.registrar_y_obtener_id()
    _mover_en_el_tiempo(entorno, cobranza, datetime(2026, 10, 10, 2, 0, tzinfo=UTC))

    hasta_el_9 = queries.listar_cobranzas(entorno.org, entorno.sesion, hasta=date(2026, 10, 9))
    desde_el_10 = queries.listar_cobranzas(entorno.org, entorno.sesion, desde=date(2026, 10, 10))
    desde_el_9 = queries.listar_cobranzas(entorno.org, entorno.sesion, desde=date(2026, 10, 9))

    assert _ids(hasta_el_9) == [cobranza]
    assert desde_el_10.items == []
    assert _ids(desde_el_9) == [cobranza]


def test_un_rango_invertido_es_rango_de_fechas_invalido(entorno: Entorno) -> None:
    with pytest.raises(RangoDeFechasInvalidoError) as error:
        queries.listar_cobranzas(
            entorno.org, entorno.sesion, desde=date(2026, 10, 10), hasta=date(2026, 10, 1)
        )

    assert error.value.codigo == "RANGO_DE_FECHAS_INVALIDO"


def test_inv21_el_listado_no_trae_cobranzas_de_otra_organizacion(
    entorno: Entorno, db_session: Session
) -> None:
    ajeno = Entorno(db_session, permisos=PERMISOS_DE_ANULACION)
    ajena = ajeno.registrar_y_obtener_id()
    propia = entorno.registrar_y_obtener_id()

    assert _ids(queries.listar_cobranzas(entorno.org, entorno.sesion)) == [propia]
    assert _ids(queries.listar_cobranzas(ajeno.org, ajeno.sesion)) == [ajena]


def test_el_detalle_trae_los_medios_con_nombre_y_la_referencia(entorno: Entorno) -> None:
    """COB-02: efectivo 30000 y transferencia 20000 con referencia, en el orden cargado."""
    cobranza_id = entorno.registrar_y_obtener_id(observacion="entrega del martes")

    detalle = queries.obtener_detalle_de_cobranza(entorno.org, cobranza_id, entorno.sesion)

    assert detalle.resumen.cobranza.observacion == "entrega del martes"
    assert [(m.medio_nombre, m.importe, m.referencia) for m in detalle.medios] == [
        ("Efectivo", Decimal("30000.00"), None),
        ("Transferencia", Decimal("20000.00"), "0042"),
    ]
    assert detalle.anulacion is None


def test_el_detalle_de_una_anulada_trae_motivo_observacion_y_quien(entorno: Entorno) -> None:
    """COB-05: la anulación con su motivo, observación, usuario y momento."""
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.anular(cobranza_id, observacion="cheque sin fondos")

    detalle = queries.obtener_detalle_de_cobranza(entorno.org, cobranza_id, entorno.sesion)

    assert detalle.resumen.cobranza.estado == "ANULADA"
    anulacion = detalle.anulacion
    assert anulacion is not None
    assert anulacion.motivo_nombre == "Error de carga"
    assert anulacion.observacion == "cheque sin fondos"
    assert anulacion.usuario_id == entorno.usuario_id
    assert anulacion.usuario_nombre
    assert anulacion.anulada_en == MOMENTO


def test_el_detalle_de_otra_organizacion_o_inexistente_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    """INV-21, SEG-07."""
    ajeno = Entorno(db_session, permisos=PERMISOS_DE_ANULACION)
    ajena = ajeno.registrar_y_obtener_id()

    for cobranza_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            queries.obtener_detalle_de_cobranza(entorno.org, cobranza_id, entorno.sesion)
        assert error.value.status_http == 404
