"""Change 17, tarea 13.1 (`design.md` D12; spec `sync/lote-de-comandos`, requisito "Un comando sin
conexión pertenece a una jornada del usuario y del dispositivo"): la jornada del sobre de un
comando `OFFLINE`, con `COBRANZA_REGISTRAR` real por `procesar_lote`.

- Sin jornada en el sobre: `JORNADA_REQUERIDA`. De otro usuario o de otro dispositivo:
  `JORNADA_AJENA`. Inexistente (o de otra organización): `JORNADA_INEXISTENTE`. En los tres casos
  `RECHAZADO` sin fila de `comando` ni efecto, y el lote sigue (SYN-06).
- `ABIERTA`: normal. `LIBERADA`: aceptada con `JORNADA_LIBERADA` (jornada y momento de la
  liberación, RUT-09). `EN_RENDICION` y `CERRADA`: aceptada sin observación nueva. En todos los
  casos aceptados la cobranza lleva la jornada del sobre.
- Doble envío: el mismo resultado con la misma observación, sin otra cobranza (INV-06).

Reglas citadas: RUT-09, SYN-05, SYN-06, SYN-07, INV-06, INV-17, INV-21.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import select
from sqlalchemy.orm import Session
from stock_utiles import MOMENTO as MOMENTO_DE_LIBERACION

from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _item(
    entorno: Entorno,
    *,
    jornada_id: UUID | None,
    secuencia: int = 1,
    operation_id: UUID | None = None,
    cobranza_id: UUID | None = None,
    modo: str = "OFFLINE",
) -> ItemLote:
    contenido: dict[str, Any] = entorno.contenido(cobranza_id=str(cobranza_id or uuid4()))
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido=contenido,
        jornada_id=jornada_id,
    )


def _lote(entorno: Entorno, *items: ItemLote) -> dict[UUID, sync_service.ResultadoItemLote]:
    resultados = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=list(items),
    )
    return {r.operation_id: r for r in resultados}


def _comandos(entorno: Entorno, operation_id: UUID) -> list[Comando]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


def _observaciones(entorno: Entorno) -> list[Observacion]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
            .order_by(Observacion.codigo)
        ).all()
    )


def _sin_efectos(entorno: Entorno) -> None:
    entorno.sin_efectos()
    assert entorno.saldo() == Decimal("150000.00")


# --- rechazos antes de reservar (SYN-06) ---------------------------------------------------


def test_syn06_un_comando_offline_sin_jornada_se_rechaza_con_jornada_requerida(
    entorno: Entorno,
) -> None:
    """Escenario "Comando sin conexión sin jornada": sin registro del comando y el lote sigue."""
    sin_jornada = _item(entorno, jornada_id=None, secuencia=1)
    con_jornada = _item(entorno, jornada_id=entorno.crear_jornada(), secuencia=2)

    resultados = _lote(entorno, sin_jornada, con_jornada)

    rechazo = resultados[sin_jornada.operation_id]
    assert (rechazo.estado, rechazo.error_codigo) == ("RECHAZADO", "JORNADA_REQUERIDA")
    assert _comandos(entorno, sin_jornada.operation_id) == []
    assert resultados[con_jornada.operation_id].estado == "ACEPTADO"
    assert len(entorno.cobranzas()) == 1


def test_syn06_un_comando_online_sin_jornada_no_la_necesita(entorno: Entorno) -> None:
    """Triangulación: la jornada obligatoria es del modo `OFFLINE`; con conexión no cambia."""
    item = _item(entorno, jornada_id=None, modo="ONLINE")

    resultados = _lote(entorno, item)

    assert resultados[item.operation_id].estado == "ACEPTADO"


def test_syn06_la_jornada_de_otro_usuario_se_rechaza_con_jornada_ajena(entorno: Entorno) -> None:
    """Escenario "Jornada de otro vendedor": la cola es de ese usuario y ese dispositivo."""
    ajena = entorno.crear_otro_usuario_con_jornada()
    item = _item(entorno, jornada_id=ajena)

    resultados = _lote(entorno, item)

    rechazo = resultados[item.operation_id]
    assert (rechazo.estado, rechazo.error_codigo) == ("RECHAZADO", "JORNADA_AJENA")
    assert _comandos(entorno, item.operation_id) == []
    _sin_efectos(entorno)


def test_syn06_la_jornada_del_mismo_usuario_en_otro_dispositivo_es_ajena(
    entorno: Entorno,
) -> None:
    """Triangulación: mismo usuario, otro dispositivo: también `JORNADA_AJENA`."""
    from cuentas_corrientes_utiles import crear_usuario_y_dispositivo

    _, otro_dispositivo = crear_usuario_y_dispositivo(entorno.sesion, entorno.org)
    entorno.sesion.commit()
    jornada = entorno.crear_jornada(dispositivo_id=otro_dispositivo)
    item = _item(entorno, jornada_id=jornada)

    resultados = _lote(entorno, item)

    assert resultados[item.operation_id].error_codigo == "JORNADA_AJENA"
    _sin_efectos(entorno)


def test_inv21_una_jornada_inexistente_sigue_siendo_jornada_inexistente(entorno: Entorno) -> None:
    item = _item(entorno, jornada_id=uuid4())

    resultados = _lote(entorno, item)

    assert resultados[item.operation_id].error_codigo == "JORNADA_INEXISTENTE"
    _sin_efectos(entorno)


# --- estados de la jornada (RUT-09, SYN-05) --------------------------------------------------


def test_una_jornada_abierta_se_acepta_sin_observacion_y_la_cobranza_la_lleva(
    entorno: Entorno,
) -> None:
    """Escenario "Jornada abierta"."""
    jornada = entorno.crear_jornada()
    item = _item(entorno, jornada_id=jornada)

    resultados = _lote(entorno, item)

    assert resultados[item.operation_id].estado == "ACEPTADO"
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal("100000.00")


def test_rut09_una_jornada_liberada_se_acepta_con_jornada_liberada(entorno: Entorno) -> None:
    """Escenario "Cobranza posterior a una liberación": se acepta con `JORNADA_LIBERADA` (jornada
    y momento de la liberación), el saldo baja y la cobranza queda asociada a esa jornada."""
    jornada = entorno.crear_jornada(estado="LIBERADA")
    item = _item(entorno, jornada_id=jornada)

    resultados = _lote(entorno, item)

    aceptada = resultados[item.operation_id]
    assert aceptada.estado == "ACEPTADO_CON_OBSERVACIONES"
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada
    assert entorno.saldo() == Decimal("100000.00")
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "JORNADA_LIBERADA"
    assert observacion.detalle == {
        "jornada_id": str(jornada),
        "liberada_en": MOMENTO_DE_LIBERACION.isoformat(),
    }
    assert observacion.operacion_tipo == "COBRANZA"
    assert observacion.operacion_id == cobranza.id


@pytest.mark.parametrize("estado", ["EN_RENDICION", "CERRADA"])
def test_syn05_una_jornada_en_rendicion_o_cerrada_se_acepta_sin_observacion(
    entorno: Entorno, estado: str
) -> None:
    """Escenario "Jornada ya cerrada" (D12): el dinero se cobró; sin observación nueva y la
    cobranza lleva la jornada del sobre."""
    jornada = entorno.crear_jornada(estado=estado)
    item = _item(entorno, jornada_id=jornada)

    resultados = _lote(entorno, item)

    assert resultados[item.operation_id].estado == "ACEPTADO"
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal("100000.00")


# --- doble envío (INV-06, SYN-09) ------------------------------------------------------------


def test_inv06_el_doble_envio_de_una_cobranza_liberada_no_duplica_nada(entorno: Entorno) -> None:
    """Escenario "Doble envío de una cobranza offline": el mismo resultado con la misma
    observación, sin segunda cobranza, movimiento ni observación."""
    jornada = entorno.crear_jornada(estado="LIBERADA")
    item = _item(entorno, jornada_id=jornada)

    primero = _lote(entorno, item)[item.operation_id]
    segundo = _lote(entorno, item)[item.operation_id]

    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert len(entorno.cobranzas()) == 1
    assert len(entorno.movimientos("COBRANZA")) == 1
    assert [o.codigo for o in _observaciones(entorno)] == ["JORNADA_LIBERADA"]
    assert entorno.saldo() == Decimal("100000.00")
