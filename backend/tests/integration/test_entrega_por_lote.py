"""Change 24, tarea 5.1 (spec `sync/lote-de-comandos`, requisito "La entrega del día se procesa
detrás de todo lo anterior del dispositivo"; `design.md` D1, CRÍTICO): `JORNADA_ENTREGAR` por
`procesar_lote` con ventas y una cobranza reales de la misma jornada.

El lote ya procesa por secuencia y se corta ante un error transitorio, así que la entrega nunca
se procesa antes que lo anterior ni con un comando anterior sin resultado: no hace falta tocar el
lote.

Reglas citadas: RUT-05, SYN-02, SYN-03, SYN-06, INV-06.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import Entorno as EntornoDeCobranzas
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta
from ventas_confirmar_utiles import MOMENTO_VENTA, RELOJ_VENTA, EntornoVenta

from app.modules.stock import jornadas_commands  # noqa: F401  (registra JORNADA_ENTREGAR)
from app.modules.stock.models import Jornada
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote
from app.modules.ventas import service as ventas_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"VENDER", "REGISTRAR_COBRANZA", "ABRIR_JORNADA"})


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session, permisos=PERMISOS)


@pytest.fixture
def ruta(entorno: EntornoVenta) -> Ruta:
    return Ruta(entorno)


class _ErrorTransitorioSimulado(Exception):
    """Un `DBAPIError` con `.orig.sqlstate = "40001"`: lo único que mira el bus."""

    class _Orig:
        sqlstate = "40001"

    def __init__(self) -> None:
        super().__init__("error transitorio simulado")
        self.orig = self._Orig()


def _item(
    entorno: EntornoVenta,
    ruta: Ruta,
    tipo: str,
    contenido: dict[str, Any],
    secuencia: int,
    *,
    modo: str = "OFFLINE",
    operation_id: UUID | None = None,
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo=tipo,
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO_VENTA,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido=contenido,
        jornada_id=ruta.jornada_id,
    )


def _venta(entorno: EntornoVenta, ruta: Ruta, secuencia: int, **cambios: object) -> ItemLote:
    return _item(entorno, ruta, "VENTA_CONFIRMAR", ruta.contenido(**cambios), secuencia)


def _cobranza(entorno: EntornoVenta, ruta: Ruta, secuencia: int) -> ItemLote:
    contenido = EntornoDeCobranzas.contenido(entorno)
    return _item(entorno, ruta, "COBRANZA_REGISTRAR", contenido, secuencia)


def _entrega(
    entorno: EntornoVenta, ruta: Ruta, secuencia: int, *, modo: str = "OFFLINE"
) -> ItemLote:
    return _item(entorno, ruta, "JORNADA_ENTREGAR", {}, secuencia, modo=modo)


def _lote(
    entorno: EntornoVenta,
    *items: ItemLote,
    config: sync_service.ConfiguracionReintentos | None = None,
) -> list[sync_service.ResultadoItemLote]:
    entorno.sesion.rollback()
    return sync_service.procesar_lote(
        entorno.sesion,
        RELOJ_VENTA,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=list(items),
        config=config,
    )


def _jornada(entorno: EntornoVenta, ruta: Ruta) -> Jornada:
    entorno.sesion.rollback()
    entorno.sesion.expire_all()
    return entorno.sesion.scalars(
        select(Jornada).where(Jornada.organizacion_id == entorno.org, Jornada.id == ruta.jornada_id)
    ).one()


def _comandos(entorno: EntornoVenta, operation_id: UUID) -> int:
    entorno.sesion.rollback()
    return len(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


def test_rut05_la_entrega_se_procesa_detras_de_las_ventas_y_la_cobranza(
    entorno: EntornoVenta, ruta: Ruta
) -> None:
    """Escenario "Entrega detrás de ventas y cobranzas": cuatro resultados, en orden de
    secuencia aunque el teléfono los haya enviado desordenados, y la entrega con la 13."""
    venta_1 = _venta(entorno, ruta, 10)
    venta_2 = _venta(entorno, ruta, 11)
    cobranza = _cobranza(entorno, ruta, 12)
    entrega = _entrega(entorno, ruta, 13)

    resultados = _lote(entorno, entrega, cobranza, venta_2, venta_1)

    assert [r.operation_id for r in resultados] == [
        venta_1.operation_id,
        venta_2.operation_id,
        cobranza.operation_id,
        entrega.operation_id,
    ]
    assert [r.estado for r in resultados] == ["ACEPTADO"] * 4
    jornada = _jornada(entorno, ruta)
    assert (jornada.estado, jornada.entrega_secuencia) == ("ABIERTA", 13)
    assert len(entorno.ventas()) == 2
    assert len(entorno.cobranzas()) == 1


def test_syn03_un_error_transitorio_anterior_deja_la_entrega_sin_procesar(
    entorno: EntornoVenta, ruta: Ruta, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Error transitorio antes de la entrega": el lote se corta en la secuencia 11 y
    la jornada sigue sin entrega; el reenvío la procesa (SYN-03, `02` §6.4)."""
    original = ventas_service.confirmar_venta
    llamadas = {"n": 0}

    def _transitorio_en_la_segunda(*args: Any, **kwargs: Any) -> Any:
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise _ErrorTransitorioSimulado()
        return original(*args, **kwargs)

    monkeypatch.setattr(ventas_service, "confirmar_venta", _transitorio_en_la_segunda)
    venta_1 = _venta(entorno, ruta, 10)
    venta_2 = _venta(entorno, ruta, 11)
    entrega = _entrega(entorno, ruta, 12)

    resultados = _lote(
        entorno,
        venta_1,
        venta_2,
        entrega,
        config=sync_service.ConfiguracionReintentos(intentos_maximos=1),
    )

    assert [r.estado for r in resultados] == ["ACEPTADO", "ERROR_TRANSITORIO"]
    assert entrega.operation_id not in {r.operation_id for r in resultados}
    assert _comandos(entorno, entrega.operation_id) == 0
    assert _jornada(entorno, ruta).entrega_secuencia is None

    # Triangulación: reenviado el lote completo, sin el fallo, todo queda procesado en orden.
    monkeypatch.setattr(ventas_service, "confirmar_venta", original)
    reenvio = _lote(entorno, venta_1, venta_2, entrega)
    assert [r.estado for r in reenvio] == ["ACEPTADO"] * 3
    assert _jornada(entorno, ruta).entrega_secuencia == 12


def test_syn06_un_rechazo_anterior_no_impide_la_entrega(entorno: EntornoVenta, ruta: Ruta) -> None:
    """Escenario "Un rechazo anterior no impide la entrega": la venta de la secuencia 11 vuelve
    rechazada (totales inconsistentes) y la entrega igual se procesa (RUT-05: el rechazo es un
    resultado)."""
    venta_1 = _venta(entorno, ruta, 10)
    venta_mala = _venta(entorno, ruta, 11, total="1.00")
    entrega = _entrega(entorno, ruta, 12)

    resultados = _lote(entorno, venta_1, venta_mala, entrega)

    assert [r.estado for r in resultados] == ["ACEPTADO", "RECHAZADO", "ACEPTADO"]
    assert resultados[1].error_codigo == "TOTALES_INCONSISTENTES"
    assert _jornada(entorno, ruta).entrega_secuencia == 12


def test_syn06_la_entrega_en_modo_online_se_rechaza_sin_cambios(
    entorno: EntornoVenta, ruta: Ruta
) -> None:
    """Escenario "Entrega en modo ONLINE": `MODO_NO_ADMITIDO_PARA_TIPO`, sin comando ni
    entrega."""
    entrega = _entrega(entorno, ruta, 10, modo="ONLINE")

    (resultado,) = _lote(entorno, entrega)

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    assert _comandos(entorno, entrega.operation_id) == 0
    assert _jornada(entorno, ruta).entrega_secuencia is None


def test_inv06_la_doble_sincronizacion_devuelve_los_resultados_originales(
    entorno: EntornoVenta, ruta: Ruta
) -> None:
    """Escenario "Doble sincronización de la entrega": el mismo lote dos veces no duplica
    ventas ni cambia la entrega."""
    venta = _venta(entorno, ruta, 10)
    entrega = _entrega(entorno, ruta, 11)
    primero = _lote(entorno, venta, entrega)
    entregada_en = _jornada(entorno, ruta).entregada_en

    segundo = _lote(entorno, venta, entrega)

    assert [(r.operation_id, r.estado, r.resultado) for r in segundo] == [
        (r.operation_id, r.estado, r.resultado) for r in primero
    ]
    assert len(entorno.ventas()) == 1
    jornada = _jornada(entorno, ruta)
    assert (jornada.entrega_secuencia, jornada.entregada_en) == (11, entregada_en)
    assert _comandos(entorno, entrega.operation_id) == 1
