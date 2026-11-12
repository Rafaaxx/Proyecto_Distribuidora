"""Change 22c, tarea 3.1 (spec `sistema/logging-estructurado`, requisito "Métricas mínimas de
comando en los registros", escenarios de cierre del lote; `design.md` D7; `02` §17, §18, INV-06).

Nivel unitario: `procesar_lote` con el procesamiento de cada ítem reemplazado por un doble (la
orquestación del lote y su registro de cierre son lo que se ejercita; los comandos reales por el
lote están en `tests/integration`). El registro de cierre trae tamaño, procesados, aceptados, con
observaciones, rechazados, si hubo corte y duración; nunca el contenido ni el detalle de las
observaciones.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.clock import FixedClock
from app.core.errors import DomainError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ConfiguracionReintentos, ErrorTransitorioAgotadoError, ItemLote

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
ORG, USUARIO, DISPOSITIVO = uuid4(), uuid4(), uuid4()
NOMBRE_DEL_CLIENTE = "Kiosco La Esquina de Marta Gómez"
MENSAJE_DE_CIERRE = "Lote de sincronización cerrado"


class _Rechazo(DomainError):
    codigo = "TOTALES_INCONSISTENTES"
    status_http = 422


class _Capturador(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.registros: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append(record)


@pytest.fixture
def capturador() -> Iterator[_Capturador]:
    logger = logging.getLogger("app.sync")
    deshabilitado, nivel = logger.disabled, logger.level
    logger.disabled = False
    logger.setLevel(logging.INFO)
    handler = _Capturador()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.disabled = deshabilitado
    logger.setLevel(nivel)


def _item(secuencia: int) -> ItemLote:
    return ItemLote(
        operation_id=uuid4(),
        tipo="VENTA_CONFIRMAR",
        version=1,
        modo="OFFLINE",
        usuario_id=USUARIO,
        dispositivo_id=DISPOSITIVO,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido={"cliente": NOMBRE_DEL_CLIENTE},
    )


def _correr(
    monkeypatch: pytest.MonkeyPatch, items: list[ItemLote], destino: dict[int, str]
) -> list[sync_service.ResultadoItemLote]:
    """`destino` dice qué pasa con cada secuencia: `ACEPTADO`, `CON_OBSERVACIONES`, `RECHAZADO`
    (error de dominio) o `TRANSITORIO` (agota los reintentos y corta el lote)."""
    monkeypatch.setattr(sync_service.identidad_service, "obtener_dispositivo", lambda *a, **k: None)

    def _procesar_item(_s: object, _r: object, *, sobre: object, **_k: object) -> object:
        accion = destino[sobre.secuencia]  # type: ignore[attr-defined]
        if accion == "RECHAZADO":
            raise _Rechazo("los importes no cierran")
        if accion == "TRANSITORIO":
            raise ErrorTransitorioAgotadoError("agotado", intentos=1)
        return SimpleNamespace(
            id=uuid4(),
            operation_id=sobre.operation_id,  # type: ignore[attr-defined]
            estado="ACEPTADO" if accion == "ACEPTADO" else "ACEPTADO_CON_OBSERVACIONES",
            resultado={"cliente": NOMBRE_DEL_CLIENTE},
            error_codigo=None,
        )

    observacion = SimpleNamespace(
        codigo="CLIENTE_NO_HABILITADO",
        operacion_tipo="VENTA",
        operacion_id=uuid4(),
        detalle={"nombre": NOMBRE_DEL_CLIENTE},
    )
    monkeypatch.setattr(sync_service, "_procesar_item_de_lote", _procesar_item)
    monkeypatch.setattr(
        sync_service.repository, "listar_observaciones_de_comando", lambda *a, **k: [observacion]
    )
    return sync_service.procesar_lote(
        MagicMock(),
        FixedClock(MOMENTO),
        organizacion_id=ORG,
        usuario_id=USUARIO,
        dispositivo_id=DISPOSITIVO,
        items=items,
        config=ConfiguracionReintentos(intentos_maximos=1),
    )


def _cierre(capturador: _Capturador) -> dict[str, object]:
    (registro,) = [r for r in capturador.registros if r.getMessage() == MENSAJE_DE_CIERRE]
    return {k: v for k, v in vars(registro).items() if k.startswith("lote_")}


def test_02_17_el_cierre_informa_el_reparto_por_resultado(
    monkeypatch: pytest.MonkeyPatch, capturador: _Capturador
) -> None:
    """Escenario "El cierre del lote informa el reparto por resultado": uno aceptado, uno con
    observaciones, uno rechazado y uno aceptado."""
    destino = {1: "ACEPTADO", 2: "CON_OBSERVACIONES", 3: "RECHAZADO", 4: "ACEPTADO"}

    _correr(monkeypatch, [_item(s) for s in destino], destino)

    cierre = _cierre(capturador)
    assert {k: cierre[k] for k in cierre if k != "lote_duracion_ms"} == {
        "lote_tamano": 4,
        "lote_procesados": 4,
        "lote_aceptados": 2,
        "lote_con_observaciones": 1,
        "lote_rechazados": 1,
        "lote_cortado": False,
    }
    duracion = cierre["lote_duracion_ms"]
    assert isinstance(duracion, float) and duracion >= 0


def test_02_17_el_cierre_informa_el_corte_por_un_error_transitorio(
    monkeypatch: pytest.MonkeyPatch, capturador: _Capturador
) -> None:
    """Escenario "El cierre del lote informa el corte": tres comandos, se corta en el segundo:
    tamaño 3, procesados 1 (el cortado no se procesó), y el corte."""
    destino = {1: "ACEPTADO", 2: "TRANSITORIO", 3: "ACEPTADO"}

    _correr(monkeypatch, [_item(s) for s in destino], destino)

    cierre = _cierre(capturador)
    assert (cierre["lote_tamano"], cierre["lote_procesados"], cierre["lote_cortado"]) == (
        3,
        1,
        True,
    )
    assert (cierre["lote_aceptados"], cierre["lote_rechazados"]) == (1, 0)


def test_02_17_un_lote_vacio_cierra_en_cero_y_sin_corte(
    monkeypatch: pytest.MonkeyPatch, capturador: _Capturador
) -> None:
    """Triangulación: el lote vacío también informa su cierre, con todo en cero."""
    _correr(monkeypatch, [], {})

    cierre = _cierre(capturador)
    assert [cierre[k] for k in ("lote_tamano", "lote_procesados", "lote_cortado")] == [0, 0, False]


def test_inv06_el_reenvio_del_mismo_lote_informa_los_mismos_resultados(
    monkeypatch: pytest.MonkeyPatch, capturador: _Capturador
) -> None:
    """Escenario "Reenvío del mismo lote": el servidor responde igual a un lote ya procesado
    (el doble devuelve el comando guardado), así que los dos cierres coinciden."""
    destino = {1: "ACEPTADO", 2: "CON_OBSERVACIONES", 3: "RECHAZADO"}
    items = [_item(s) for s in destino]

    _correr(monkeypatch, items, destino)
    _correr(monkeypatch, items, destino)

    cierres = [
        {k: v for k, v in vars(r).items() if k.startswith("lote_") and k != "lote_duracion_ms"}
        for r in capturador.registros
        if r.getMessage() == MENSAJE_DE_CIERRE
    ]
    assert len(cierres) == 2 and cierres[0] == cierres[1]
    assert cierres[0]["lote_aceptados"] == 1 and cierres[0]["lote_con_observaciones"] == 1


def test_02_18_el_cierre_no_lleva_el_contenido_ni_el_detalle_de_las_observaciones(
    monkeypatch: pytest.MonkeyPatch, capturador: _Capturador
) -> None:
    """Escenario "El contenido del comando no llega a los registros": ni el contenido del comando
    ni el detalle de sus observaciones (con el nombre del cliente) aparecen en ningún registro."""
    destino = {1: "CON_OBSERVACIONES", 2: "ACEPTADO"}

    _correr(monkeypatch, [_item(s) for s in destino], destino)

    assert capturador.registros
    for registro in capturador.registros:
        assert NOMBRE_DEL_CLIENTE not in registro.getMessage()
        assert NOMBRE_DEL_CLIENTE not in repr(vars(registro))
