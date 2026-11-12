"""Change 24, tarea 8.1: lo que llega con la jornada ya rendida se acepta con la observación
`JORNADA_RENDIDA` (spec `sync/observaciones`, requisito "Lo que llega con la jornada ya rendida se
acepta con observación"; `design.md` D7) contra PostgreSQL real y por `procesar_lote`.

Una venta, una anulación de venta o una cobranza SIN CONEXIÓN cuya jornada del sobre está
`EN_RENDICION` o `CERRADA` se acepta (INV-17) con una `JORNADA_RENDIDA` sobre la operación (detalle:
la jornada y el momento de la rendición), además de las que ya correspondan. Con la jornada
`ABIERTA` no se anota; con la `LIBERADA` sigue `JORNADA_LIBERADA` (RUT-09).

Reglas citadas: SYN-02, SYN-05, SYN-07, INV-06, INV-17, VTA-24, STK-09.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO as MOMENTO_DE_COBRANZA
from cobranzas_utiles import RELOJ as RELOJ_DE_COBRANZA
from cobranzas_utiles import Entorno as EntornoDeCobranza
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import MOMENTO as RENDIDA_EN
from test_ventas_offline import Ruta, lote
from venta_anular_offline_utiles import anular, vender
from ventas_anular_utiles import EntornoAnulacion

from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

CODIGO = "JORNADA_RENDIDA"
EN_O_DESPUES_DE_RENDIR = ("EN_RENDICION", "CERRADA")


def _observaciones(sesion: Session, org: UUID) -> list[Observacion]:
    sesion.rollback()
    return list(
        sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == org)
            .order_by(Observacion.codigo, Observacion.id)
        ).all()
    )


def _de_la_jornada_rendida(sesion: Session, org: UUID) -> list[Observacion]:
    return [o for o in _observaciones(sesion, org) if o.codigo == CODIGO]


def _detalle(jornada_id: UUID) -> dict[str, Any]:
    """Jornada y momento de la rendición (`stock_utiles.crear_jornada_sql` y el cambio de estado
    de estas pruebas usan el mismo momento)."""
    return {"jornada_id": str(jornada_id), "rendida_en": RENDIDA_EN.isoformat()}


def _rendir_por_sql(entorno: EntornoAnulacion, jornada_id: UUID, estado: str) -> None:
    """La jornada pasa a `EN_RENDICION` o `CERRADA` después de que el teléfono vendió."""
    valores = "estado = :estado, rendida_en = :m, rendida_por_id = :u"
    if estado == "CERRADA":
        valores += ", cerrada_en = :m, cerrada_por_id = :u"
    entorno.sesion.execute(
        text(f"UPDATE jornada SET {valores} WHERE id = :id"),
        {"estado": estado, "m": RENDIDA_EN, "u": entorno.usuario_id, "id": jornada_id},
    )
    entorno.sesion.commit()


# --- cobranza ----------------------------------------------------------------------------


def _cobrar(
    entorno: EntornoDeCobranza,
    jornada_id: UUID,
    *,
    operation_id: UUID | None = None,
    contenido: dict[str, Any] | None = None,
) -> sync_service.ResultadoItemLote:
    item = ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO_DE_COBRANZA,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido if contenido is not None else entorno.contenido(),
        jornada_id=jornada_id,
    )
    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ_DE_COBRANZA,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )
    return resultado


@pytest.mark.parametrize("estado", EN_O_DESPUES_DE_RENDIR)
def test_una_cobranza_tardia_se_acepta_con_jornada_rendida_y_baja_el_saldo(
    db_session: Session, estado: str
) -> None:
    """INV-17: la cobranza llega con la jornada rendida o cerrada y se registra igual."""
    entorno = EntornoDeCobranza(db_session)
    jornada = entorno.crear_jornada(estado=estado)

    resultado = _cobrar(entorno, jornada)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(db_session, entorno.org)
    assert observacion.codigo == CODIGO
    assert observacion.detalle == _detalle(jornada)
    (cobranza,) = entorno.cobranzas()
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("COBRANZA", cobranza.id)
    assert cobranza.jornada_id == jornada
    assert entorno.saldo() == Decimal("100000.00")


def test_una_cobranza_de_una_jornada_abierta_no_se_observa(db_session: Session) -> None:
    entorno = EntornoDeCobranza(db_session)

    resultado = _cobrar(entorno, entorno.crear_jornada(estado="ABIERTA"))

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(db_session, entorno.org) == []


def test_la_cobranza_tardia_conserva_las_observaciones_que_ya_llevaba(
    db_session: Session,
) -> None:
    """SYN-07: convive con `MEDIO_INACTIVO` y con `PERMISO_REVOCADO`, sin reemplazarlas."""
    entorno = EntornoDeCobranza(db_session)
    entorno.desactivar_medio(entorno.efectivo_id)
    db_session.execute(
        text("DELETE FROM rol_permiso WHERE organizacion_id = :o"), {"o": entorno.org}
    )
    db_session.commit()
    jornada = entorno.crear_jornada(estado="CERRADA")

    resultado = _cobrar(entorno, jornada)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert [o.codigo for o in _observaciones(db_session, entorno.org)] == [
        CODIGO,
        "MEDIO_INACTIVO",
        "PERMISO_REVOCADO",
    ]


def test_la_cobranza_de_una_jornada_liberada_sigue_con_jornada_liberada(
    db_session: Session,
) -> None:
    """Triangulación: la liberación no se confunde con la rendición."""
    entorno = EntornoDeCobranza(db_session)

    _cobrar(entorno, entorno.crear_jornada(estado="LIBERADA"))

    assert [o.codigo for o in _observaciones(db_session, entorno.org)] == ["JORNADA_LIBERADA"]


def test_el_doble_envio_de_la_cobranza_tardia_no_duplica_la_observacion(
    db_session: Session,
) -> None:
    """SYN-02, INV-06: el reenvío devuelve el resultado original y no anota otra observación."""
    entorno = EntornoDeCobranza(db_session)
    jornada = entorno.crear_jornada(estado="CERRADA")
    operation_id = uuid4()
    contenido = entorno.contenido()  # el mismo contenido: la huella del reenvío es la misma

    primero = _cobrar(entorno, jornada, operation_id=operation_id, contenido=contenido)
    segundo = _cobrar(entorno, jornada, operation_id=operation_id, contenido=contenido)

    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert len(_de_la_jornada_rendida(db_session, entorno.org)) == 1
    assert len(entorno.cobranzas()) == 1
    comandos = db_session.scalars(
        select(Comando).where(
            Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
        )
    ).all()
    assert len(comandos) == 1


# --- venta -------------------------------------------------------------------------------


def test_una_venta_tardia_de_una_jornada_en_rendicion_lleva_las_dos_observaciones(
    db_session: Session,
) -> None:
    """SYN-05, STK-09: la propia jornada en rendición tiene tomada la camioneta; la venta se
    acepta con `JORNADA_RENDIDA` y `UBICACION_TOMADA_AL_SINCRONIZAR` y descuenta sin jornada."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno, estado_jornada="EN_RENDICION")

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    observaciones = _observaciones(db_session, entorno.org)
    assert [o.codigo for o in observaciones] == [CODIGO, "UBICACION_TOMADA_AL_SINCRONIZAR"]
    assert observaciones[0].detalle == _detalle(ruta.jornada_id)
    assert {(o.operacion_tipo, o.operacion_id) for o in observaciones} == {("VENTA", venta.id)}
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id is None


def test_una_venta_tardia_de_una_jornada_cerrada_lleva_solo_jornada_rendida(
    db_session: Session,
) -> None:
    """La ubicación ya quedó libre al cerrar: no hay `UBICACION_TOMADA_AL_SINCRONIZAR`."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno, estado_jornada="CERRADA")

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert [o.codigo for o in _observaciones(db_session, entorno.org)] == [CODIGO]
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33


def test_una_venta_de_una_jornada_abierta_no_se_observa(db_session: Session) -> None:
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(db_session, entorno.org) == []


def test_una_venta_tardia_con_cobranza_en_el_acto_anota_una_sola_jornada_rendida(
    db_session: Session,
) -> None:
    """La `JORNADA_RENDIDA` queda sobre la venta; la de la cobranza en el acto no se repite
    (como `JORNADA_LIBERADA`)."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno, estado_jornada="CERRADA")

    _, resultado = ruta.enviar(cobranza=entorno.cobranza())

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len(_de_la_jornada_rendida(db_session, entorno.org)) == 1
    assert _de_la_jornada_rendida(db_session, entorno.org)[0].operacion_tipo == "VENTA"


def test_el_doble_envio_de_la_venta_tardia_no_duplica_la_observacion(
    db_session: Session,
) -> None:
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno, estado_jornada="CERRADA")
    item = ruta.item()

    primero = lote(entorno, item)[item.operation_id]
    segundo = lote(entorno, item)[item.operation_id]

    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert len(_de_la_jornada_rendida(db_session, entorno.org)) == 1
    assert len(entorno.ventas()) == 1


# --- anulación de venta ------------------------------------------------------------------


@pytest.mark.parametrize("estado", EN_O_DESPUES_DE_RENDIR)
def test_una_anulacion_tardia_se_acepta_con_jornada_rendida(
    db_session: Session, estado: str
) -> None:
    """VTA-24, SYN-07: la venta se hizo con la jornada abierta; la anulación llega rendida."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    assert _observaciones(db_session, entorno.org) == []
    _rendir_por_sql(entorno, ruta.jornada_id, estado)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.venta(venta_id).estado == "ANULADA"
    observaciones = _de_la_jornada_rendida(db_session, entorno.org)
    assert [(o.operacion_tipo, o.operacion_id) for o in observaciones] == [("VENTA", venta_id)]
    assert observaciones[0].detalle == _detalle(ruta.jornada_id)


def test_la_anulacion_de_una_venta_de_una_jornada_abierta_no_se_observa(
    db_session: Session,
) -> None:
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(db_session, entorno.org) == []


def test_la_anulacion_tardia_conserva_ubicacion_tomada_al_sincronizar(
    db_session: Session,
) -> None:
    """Con la jornada `EN_RENDICION` la camioneta sigue tomada: conviven las dos observaciones."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    _rendir_por_sql(entorno, ruta.jornada_id, "EN_RENDICION")

    anular(entorno, ruta, venta_id)

    assert sorted(o.codigo for o in _observaciones(db_session, entorno.org)) == [
        CODIGO,
        "UBICACION_TOMADA_AL_SINCRONIZAR",
    ]
