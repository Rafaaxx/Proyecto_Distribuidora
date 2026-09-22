"""Change 04, grupo 12 (tareas 12.1-12.3; `02` §17): contexto de comando en
los registros y sus métricas mínimas.

Nivel unitario, mismo criterio que `test_sync_service_bus.py` (grupo 6):
`sesion` es un `MagicMock` y `sync_service.procesar_idempotente` se
reemplaza con un doble -- lo que se ejercita acá es el CABLEADO de logging
alrededor de `procesar_comando` (contexto propagado, duración medida,
resultado y reintentos informados), no la reserva de idempotencia real
(ya cubierta en integración).

Spec: `sistema/logging-estructurado` (delta de este change), escenarios
"Una petición que ejecuta un comando registra su contexto completo",
"Cada comando de un lote lleva su propio identificador de operación" (acá
triangulado con dos llamadas directas a `procesar_comando`, no con
`procesar_lote` -- ese nivel, con Postgres real, está en
`tests/integration/test_grupo12_logging_lote.py`), "El registro de un
comando informa duración, resultado y reintentos" y "El contenido del
comando no llega a los registros".
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.logging import (
    ComandoContextoFilter,
    JsonFormatter,
    RequestIdFilter,
    comando_contexto_var,
    request_id_var,
)
from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


class _ErrorDeBaseFalso(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"simulado sqlstate={sqlstate}")
        self.orig = SimpleNamespace(sqlstate=sqlstate)


def _sobre(**kwargs: object) -> SobreComando:
    base = dict(
        operation_id=uuid4(),
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=uuid4(),
        usuario_id=uuid4(),
        dispositivo_id=uuid4(),
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={},
    )
    base.update(kwargs)
    return SobreComando(**base)  # type: ignore[arg-type]


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lineas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(self.format(record))


@pytest.fixture
def captura_sync() -> _ListHandler:
    """Adjunta un handler propio a `app.sync` con el mismo formateador y los
    mismos filtros que usa `configurar_logging` en producción, para poder
    leer el JSON tal como saldría por el `StreamHandler` real.

    Descubrimiento (grupo 12): `tests/unit/test_import_linter_bus_de_comandos.py`
    invoca la CLI real de `import-linter`, cuya configuración de logging
    interna usa `logging.config.dictConfig` con `disable_existing_loggers`
    en su valor por defecto (`True`) -- eso pone `.disabled = True` en
    CUALQUIER logger ya existente en `logging.Logger.manager.loggerDict`
    en ese momento, incluido `app.sync` (creado al importar
    `app.modules.sync.service`), y nunca lo revierte. Sobrevive al resto
    de la sesión de pytest si ese archivo se recolecta antes que este. No
    es un bug de esta tarea: se neutraliza acá mismo, forzando
    `disabled = False`, para que esta prueba no dependa del orden de
    recolección de otros archivos."""
    logger = logging.getLogger("app.sync")
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler = _ListHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ComandoContextoFilter())
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.handlers.clear()
        logger.propagate = True
        # A propósito, NO se restaura `disabled` a su valor previo: si
        # `import-linter` lo dejó en `True` antes de esta prueba, revertirlo
        # perpetuaría esa contaminación para cualquier prueba posterior de
        # la misma sesión que use `app.sync` (`caplog` incluido, que no pasa
        # por este fixture) -- se corrige hacia adelante, no se preserva.
        logger.disabled = False


def _procesar_idempotente_directo(sesion, reloj, *, sobre, huella, ejecutar_handler):
    estado, resultado, error_codigo = ejecutar_handler()
    return SimpleNamespace(
        id=uuid4(), estado=estado, resultado=resultado, error_codigo=error_codigo
    )


class TestContextoDeComandoEnLosRegistros:
    """Tareas 12.1/12.2, escenario "Una petición que ejecuta un comando
    registra su contexto completo"."""

    def test_el_registro_de_cierre_lleva_operation_id_organizacion_usuario_y_dispositivo(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_directo)
        sobre = _sobre()

        sync_service.procesar_comando(
            MagicMock(),
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
        )

        assert captura_sync.lineas, "procesar_comando debe emitir al menos un registro"
        registro = json.loads(captura_sync.lineas[-1])
        assert registro["operation_id"] == str(sobre.operation_id)
        assert registro["organizacion_id"] == str(sobre.organizacion_id)
        assert registro["usuario_id"] == str(sobre.usuario_id)
        assert registro["dispositivo_id"] == str(sobre.dispositivo_id)

    def test_fuera_de_la_ejecucion_del_comando_el_contexto_no_queda_pegado(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        """Triangulación: el `ContextVar` se resetea al salir de
        `procesar_comando` -- un registro emitido después, sin comando en
        curso, no hereda el contexto del comando anterior."""
        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_directo)
        sobre = _sobre()
        sync_service.procesar_comando(
            MagicMock(),
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
        )
        assert comando_contexto_var.get() is None

        logging.getLogger("app.sync").info("mensaje posterior, sin comando en curso")
        registro = json.loads(captura_sync.lineas[-1])
        assert registro["operation_id"] is None
        assert registro["organizacion_id"] is None


class TestCadaComandoDeUnLoteLlevaSuPropioOperationId:
    """Tarea 12.1, escenario "Cada comando de un lote lleva su propio
    identificador de operación" -- acá triangulado con dos llamadas
    directas a `procesar_comando` bajo el mismo `request_id` de petición,
    exactamente lo que hace `procesar_lote` con cada ítem (ese nivel con
    Postgres real y el endpoint HTTP está en
    `tests/integration/test_grupo12_logging_lote.py`)."""

    def test_dos_comandos_bajo_el_mismo_request_id_informan_operation_id_distintos(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_directo)
        token = request_id_var.set("request-del-lote")
        try:
            sobre_1 = _sobre()
            sobre_2 = _sobre()
            for sobre in (sobre_1, sobre_2):
                sync_service.procesar_comando(
                    MagicMock(),
                    FixedClock(MOMENTO),
                    sobre=sobre,
                    huella="huella-1",
                    ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
                )
        finally:
            request_id_var.reset(token)

        assert len(captura_sync.lineas) == 2
        registro_1 = json.loads(captura_sync.lineas[0])
        registro_2 = json.loads(captura_sync.lineas[1])
        assert registro_1["operation_id"] == str(sobre_1.operation_id)
        assert registro_2["operation_id"] == str(sobre_2.operation_id)
        assert registro_1["operation_id"] != registro_2["operation_id"]
        assert registro_1["request_id"] == "request-del-lote"
        assert registro_2["request_id"] == "request-del-lote"


class TestMetricasMinimasDeComando:
    """Tarea 12.3, escenario "El registro de un comando informa duración,
    resultado y reintentos"."""

    def test_un_comando_sin_reintentos_informa_reintentos_cero(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_directo)

        sync_service.procesar_comando(
            MagicMock(),
            FixedClock(MOMENTO),
            sobre=_sobre(),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
        )

        registro = json.loads(captura_sync.lineas[-1])
        assert registro["resultado"] == "ACEPTADO"
        assert registro["reintentos"] == 0
        assert isinstance(registro["duration_ms"], (int, float))
        assert registro["duration_ms"] >= 0

    def test_un_comando_reintentado_una_vez_informa_reintentos_uno_y_su_resultado(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        """Triangulación: distinto resultado (`RECHAZADO`) y un reintento
        transitorio antes de terminar -- `reintentos` debe reflejarlo."""
        llamadas = {"n": 0}

        def _procesar_idempotente_con_un_fallo_transitorio(
            sesion, reloj, *, sobre, huella, ejecutar_handler
        ):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise _ErrorDeBaseFalso("40001")
            estado, resultado, error_codigo = ejecutar_handler()
            return SimpleNamespace(
                id=uuid4(), estado=estado, resultado=resultado, error_codigo=error_codigo
            )

        monkeypatch.setattr(
            sync_service, "procesar_idempotente", _procesar_idempotente_con_un_fallo_transitorio
        )

        sync_service.procesar_comando(
            MagicMock(),
            FixedClock(MOMENTO),
            sobre=_sobre(),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("RECHAZADO", None, "RECHAZADO_DE_PRUEBA"),
            dormir=lambda _segundos: None,
        )

        registro = json.loads(captura_sync.lineas[-1])
        assert registro["resultado"] == "RECHAZADO"
        assert registro["reintentos"] == 1


class TestElContenidoDelComandoNoLlegaALosRegistros:
    """Tarea 12.3, escenario "El contenido del comando no llega a los
    registros": un dato personal en `contenido` no debe aparecer en ningún
    registro de nivel INFO emitido por `procesar_comando`."""

    def test_un_dato_personal_del_contenido_no_aparece_en_ningun_registro(
        self, monkeypatch: pytest.MonkeyPatch, captura_sync: _ListHandler
    ) -> None:
        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_directo)
        dato_personal = "cliente-dni-99887766-marca-de-agua"

        sync_service.procesar_comando(
            MagicMock(),
            FixedClock(MOMENTO),
            sobre=_sobre(contenido={"dni_cliente": dato_personal}),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: (
                "ACEPTADO",
                {"dni_cliente": dato_personal},
                None,
            ),
        )

        for linea in captura_sync.lineas:
            assert dato_personal not in linea
