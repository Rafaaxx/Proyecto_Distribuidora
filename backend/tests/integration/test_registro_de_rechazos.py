"""Change 25, tarea 7.1 (spec `sync/rechazos-sin-conexion`, requisito "El lote guarda cada rechazo
sin conexión"; `design.md` D6), contra PostgreSQL real y por `procesar_lote`.

- Todo ítem `OFFLINE` que el lote rechaza queda en `comando_rechazado` (transacción aparte), con
  su contenido completo, el código, la jornada (nula si no existe en la organización) y `PENDIENTE`.
- No se guardan: credenciales, un lote entero rechazado por cola ajena, un dispositivo revocado
  (va a la cuarentena) ni un ítem `ONLINE`.
- `ON CONFLICT DO NOTHING`: el reenvío no duplica. Una falla transitoria al guardar corta el lote.

Reglas citadas: SYN-03, SYN-05, SYN-06, INV-06, INV-08, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, lote
from venta_anular_offline_utiles import item_de_anulacion
from ventas_anular_utiles import EntornoAnulacion

from app.core.clock import FixedClock
from app.modules.identidad import service as identidad_service
from app.modules.sync import repository as sync_repository
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, ComandoCuarentena, ComandoRechazado
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _item_cobranza(
    entorno: Entorno,
    *,
    jornada_id: UUID | None,
    secuencia: int = 1,
    operation_id: UUID | None = None,
    modo: str = "OFFLINE",
    contenido: dict[str, Any] | None = None,
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.2.3",
        contenido=contenido if contenido is not None else entorno.contenido(),
        jornada_id=jornada_id,
    )


def _medios_que_no_suman(entorno: Entorno) -> dict[str, Any]:
    """Medios por $40.000 para un importe de $50.000 (INV-08)."""
    return entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None), (entorno.transferencia_id, "10000.00", "42")
        )
    )


def _lote_de_cobranzas(
    entorno: Entorno, *items: ItemLote, **opciones: Any
) -> dict[UUID, sync_service.ResultadoItemLote]:
    resultados = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=list(items),
        **opciones,
    )
    return {r.operation_id: r for r in resultados}


def _rechazos(sesion: Session, organizacion_id: UUID) -> list[ComandoRechazado]:
    sesion.rollback()
    return list(
        sesion.scalars(
            select(ComandoRechazado)
            .where(ComandoRechazado.organizacion_id == organizacion_id)
            .order_by(ComandoRechazado.secuencia)
        ).all()
    )


def _comandos(sesion: Session, operation_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        or 0
    )


# --- escenarios del registro ----------------------------------------------------------------


def test_syn06_una_venta_con_totales_incoherentes_queda_registrada_con_su_contenido(
    db_session: Session,
) -> None:
    """Escenario "Venta con totales incoherentes": RECHAZADO, rechazo `PENDIENTE` con el
    contenido completo, la jornada y el código; sin venta ni fila de comando."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(total="31250.01"), secuencia=7)

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "TOTALES_INCONSISTENTES")
    (rechazo,) = _rechazos(db_session, entorno.org)
    assert rechazo.operation_id == item.operation_id
    assert (rechazo.tipo, rechazo.version, rechazo.modo) == ("VENTA_CONFIRMAR", 1, "OFFLINE")
    assert rechazo.estado == "PENDIENTE"
    assert rechazo.error_codigo == "TOTALES_INCONSISTENTES"
    assert rechazo.jornada_id == ruta.jornada_id
    assert (rechazo.usuario_id, rechazo.dispositivo_id) == (
        entorno.usuario_id,
        entorno.dispositivo_id,
    )
    assert (rechazo.secuencia, rechazo.app_version) == (7, "1.0.0")
    assert rechazo.contenido["venta_id"] == item.contenido["venta_id"]
    assert rechazo.contenido["total"] == "31250.01"
    assert rechazo.recibido_en is not None
    assert (rechazo.resuelto_por_id, rechazo.resuelto_en, rechazo.comentario) == (None, None, None)
    assert entorno.ventas() == []
    assert _comandos(db_session, item.operation_id) == 0


def test_syn06_una_anulacion_de_una_venta_inexistente_queda_registrada(
    db_session: Session,
) -> None:
    """Escenario "Rechazo con fila de comando" (ADR-066): `VENTA_INEXISTENTE` queda registrada
    con el tipo `VENTA_ANULAR` y el `venta_id` que envió el teléfono."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    venta_id = uuid4()
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "VENTA_INEXISTENTE")
    (rechazo,) = _rechazos(db_session, entorno.org)
    assert (rechazo.tipo, rechazo.error_codigo) == ("VENTA_ANULAR", "VENTA_INEXISTENTE")
    assert rechazo.contenido["venta_id"] == str(venta_id)


def test_inv08_una_cobranza_con_medios_que_no_suman_queda_registrada(entorno: Entorno) -> None:
    """Escenario "Cobranza con medios que no suman" (INV-08)."""
    jornada = entorno.crear_jornada()
    item = _item_cobranza(
        entorno, jornada_id=jornada, contenido=_medios_que_no_suman(entorno), secuencia=3
    )

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "MEDIOS_NO_SUMAN_IMPORTE")
    (rechazo,) = _rechazos(entorno.sesion, entorno.org)
    assert (rechazo.tipo, rechazo.error_codigo) == ("COBRANZA_REGISTRAR", "MEDIOS_NO_SUMAN_IMPORTE")
    assert rechazo.jornada_id == jornada
    assert rechazo.contenido["importe"] == "50000.00"
    assert len(rechazo.contenido["medios"]) == 2  # type: ignore[arg-type]


def test_inv21_una_jornada_inexistente_se_registra_sin_jornada(entorno: Entorno) -> None:
    """Escenario "Jornada inexistente": `JORNADA_INEXISTENTE` y el rechazo sin jornada."""
    item = _item_cobranza(entorno, jornada_id=uuid4())

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert resultado.error_codigo == "JORNADA_INEXISTENTE"
    (rechazo,) = _rechazos(entorno.sesion, entorno.org)
    assert rechazo.jornada_id is None
    assert rechazo.error_codigo == "JORNADA_INEXISTENTE"


def test_syn06_una_jornada_ajena_del_mismo_lote_se_registra_con_esa_jornada(
    entorno: Entorno,
) -> None:
    """Triangulación: `JORNADA_AJENA` existe en la organización, así que el rechazo la lleva."""
    ajena = entorno.crear_otro_usuario_con_jornada()
    item = _item_cobranza(entorno, jornada_id=ajena)

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert resultado.error_codigo == "JORNADA_AJENA"
    (rechazo,) = _rechazos(entorno.sesion, entorno.org)
    assert rechazo.jornada_id == ajena


def test_syn03_el_rechazo_no_corta_el_lote(entorno: Entorno) -> None:
    """Escenario "El rechazo no corta el lote": la cobranza válida de después se acepta y queda
    un solo rechazo."""
    jornada = entorno.crear_jornada()
    mala = _item_cobranza(
        entorno, jornada_id=jornada, contenido=_medios_que_no_suman(entorno), secuencia=1
    )
    buena = _item_cobranza(entorno, jornada_id=jornada, secuencia=2)

    resultados = _lote_de_cobranzas(entorno, mala, buena)

    assert resultados[mala.operation_id].estado == "RECHAZADO"
    assert resultados[buena.operation_id].estado == "ACEPTADO"
    assert [r.operation_id for r in _rechazos(entorno.sesion, entorno.org)] == [mala.operation_id]


def test_syn06_un_dispositivo_revocado_va_solo_a_la_cuarentena(entorno: Entorno) -> None:
    """Escenario "Dispositivo revocado y credenciales" (primera mitad)."""
    jornada = entorno.crear_jornada()
    identidad_service.revocar_dispositivo(
        entorno.org,
        entorno.sesion,
        FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
        dispositivo_id=entorno.dispositivo_id,
        actor_id=entorno.usuario_id,
    )
    entorno.sesion.commit()
    item = _item_cobranza(entorno, jornada_id=jornada)

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert resultado.error_codigo == "DISPOSITIVO_REVOCADO"
    assert _rechazos(entorno.sesion, entorno.org) == []
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(ComandoCuarentena)
            .where(ComandoCuarentena.operation_id == item.operation_id)
        )
        == 1
    )


def test_adr056_un_item_con_credenciales_no_se_guarda_en_ningun_lado(entorno: Entorno) -> None:
    """Escenario "Dispositivo revocado y credenciales" (segunda mitad): el PIN no se almacena."""
    jornada = entorno.crear_jornada()
    contenido = entorno.contenido(credenciales={"pin": "1234"})
    item = _item_cobranza(entorno, jornada_id=jornada, contenido=contenido)

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "CONTENIDO_DE_COMANDO_INVALIDO",
    )
    assert _rechazos(entorno.sesion, entorno.org) == []
    assert (
        entorno.sesion.scalar(
            text("SELECT count(*) FROM comando_rechazado WHERE contenido::text LIKE '%1234%'")
        )
        == 0
    )


def test_syn05_un_item_online_rechazado_no_se_guarda(entorno: Entorno) -> None:
    """Solo se registran los ítems `OFFLINE`: un rechazo con conexión lo ve quien lo envió."""
    item = _item_cobranza(
        entorno, jornada_id=None, modo="ONLINE", contenido=_medios_que_no_suman(entorno)
    )

    resultado = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert resultado.estado == "RECHAZADO"
    assert _rechazos(entorno.sesion, entorno.org) == []


def test_syn03_un_lote_de_cola_ajena_se_rechaza_entero_y_no_se_guarda(entorno: Entorno) -> None:
    """Un lote entero rechazado por `COLA_AJENA` no registra nada."""
    jornada = entorno.crear_jornada()
    ajeno = ItemLote(
        operation_id=uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo="OFFLINE",
        usuario_id=uuid4(),
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido(),
        jornada_id=jornada,
    )

    with pytest.raises(sync_service.ColaAjenaError):
        _lote_de_cobranzas(entorno, ajeno)

    assert _rechazos(entorno.sesion, entorno.org) == []


def test_syn02_el_doble_envio_del_rechazado_no_duplica_el_registro(entorno: Entorno) -> None:
    """Escenario "Doble envío del rechazado" (INV-06): el mismo rechazo y un solo registro."""
    jornada = entorno.crear_jornada()
    item = _item_cobranza(entorno, jornada_id=jornada, contenido=_medios_que_no_suman(entorno))

    primero = _lote_de_cobranzas(entorno, item)[item.operation_id]
    segundo = _lote_de_cobranzas(entorno, item)[item.operation_id]

    assert (primero.estado, primero.error_codigo) == (segundo.estado, segundo.error_codigo)
    assert len(_rechazos(entorno.sesion, entorno.org)) == 1


def test_inv21_el_rechazo_es_de_la_organizacion_del_token(
    entorno: Entorno, db_session: Session
) -> None:
    """INV-21: el rechazo lleva la organización del lote, nunca otra."""
    otro = Entorno(db_session)
    jornada = entorno.crear_jornada()
    item = _item_cobranza(entorno, jornada_id=jornada, contenido=_medios_que_no_suman(entorno))

    _lote_de_cobranzas(entorno, item)

    assert len(_rechazos(entorno.sesion, entorno.org)) == 1
    assert _rechazos(entorno.sesion, otro.org) == []


class _ErrorTransitorioSimulado(Exception):
    class _Orig:
        sqlstate = "40001"

    def __init__(self) -> None:
        super().__init__("error transitorio simulado")
        self.orig = self._Orig()


def test_syn09_una_falla_transitoria_al_guardar_es_error_transitorio_y_corta_el_lote(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Error transitorio al guardar": ese ítem vuelve `ERROR_TRANSITORIO`, los
    siguientes no se procesan y el teléfono reintenta con el mismo `operation_id`."""
    jornada = entorno.crear_jornada()
    mala = _item_cobranza(
        entorno, jornada_id=jornada, contenido=_medios_que_no_suman(entorno), secuencia=1
    )
    buena = _item_cobranza(entorno, jornada_id=jornada, secuencia=2)
    llamadas: list[int] = []

    def _falla(*args: object, **kwargs: object) -> object:
        llamadas.append(1)
        raise _ErrorTransitorioSimulado()

    monkeypatch.setattr(sync_repository, "crear_rechazo", _falla)

    resultados = _lote_de_cobranzas(entorno, mala, buena, dormir=lambda _segundos: None)

    assert resultados[mala.operation_id].estado == "ERROR_TRANSITORIO"
    assert resultados[mala.operation_id].error_codigo == "ERROR_TRANSITORIO"
    assert buena.operation_id not in resultados
    assert len(llamadas) == 3  # los reintentos de la configuración por defecto
    assert _comandos(entorno.sesion, buena.operation_id) == 0
    monkeypatch.undo()
    reintento = _lote_de_cobranzas(entorno, mala, buena)
    assert reintento[mala.operation_id].estado == "RECHAZADO"
    assert reintento[buena.operation_id].estado == "ACEPTADO"
    assert len(_rechazos(entorno.sesion, entorno.org)) == 1
