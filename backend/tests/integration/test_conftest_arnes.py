"""Unitarias del arnés de Testcontainers de `conftest.py` (no requieren
Docker): verifican el escape de `DATABASE_URL` y el mensaje explícito
cuando no hay motor de contenedores (spec `integracion-continua`, "No hay
motor de contenedores disponible").
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Se carga `conftest.py` por ruta de archivo (en vez de importarlo como
# paquete) porque `tests/` no tiene `__init__.py` y pytest ya gestiona ese
# módulo bajo su propio mecanismo de carga de conftests.
_spec = importlib.util.spec_from_file_location(
    "integracion_conftest_bajo_prueba", Path(__file__).resolve().parent / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
arnes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arnes)


def test_database_url_usa_la_variable_de_entorno_si_esta_definida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host-de-prueba:5432/db")

    generador = arnes.database_url.__wrapped__()
    url = next(generador)

    assert url == "postgresql+psycopg://u:p@host-de-prueba:5432/db"


def test_falla_explicito_si_no_hay_database_url_ni_motor_de_contenedores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(arnes, "_motor_de_contenedores_disponible", lambda: False)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        next(arnes.database_url.__wrapped__())

    mensaje = str(excinfo.value)
    assert "motor de contenedores" in mensaje
    assert "DATABASE_URL" in mensaje
