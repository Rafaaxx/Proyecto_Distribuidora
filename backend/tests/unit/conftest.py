"""Fixtures compartidas de `tests/unit`.

Las pruebas `test_import_linter_*` invocan la CLI real de import-linter
(`importlinter.cli.lint_imports`). Su configuración de logging interna usa
`logging.config.dictConfig` con `disable_existing_loggers=True` (valor por defecto) y
deja `.disabled = True` en todo logger que ya existe en ese momento -- `app.tareas.aviso`,
`app.sync`, etc. se crean al importar sus módulos, durante la recolección -- y nunca lo
revierte. Después, cualquier prueba que lea `caplog` de un logger `app.*` ve vacío, según el
orden de ejecución (en CI, Linux, fallaba `test_tareas_aviso`). Se restituye antes de cada
prueba para que no dependan del orden en que corren los demás archivos.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _loggers_de_la_app_habilitados() -> Iterator[None]:
    for nombre, logger in list(logging.Logger.manager.loggerDict.items()):
        if nombre.startswith("app") and isinstance(logger, logging.Logger):
            logger.disabled = False
    yield
