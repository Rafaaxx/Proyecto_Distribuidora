"""Verifica que las migraciones aplican y revierten limpio contra
PostgreSQL real (`docs/04-roadmap-changes.md` §2.1, criterio 4).

Este test corre alembic directamente contra la base compartida de la
sesión de pytest (la misma que usan `_engine_de_sesion`/`db_session` en
`conftest.py`), no contra una base propia. Por eso DEBE terminar con la
base en `head`: si terminara en `downgrade base`, cualquier test de
integración que corra después perdería todas las tablas (fallaría con
`relation "organizacion" does not exist` o similar) según el orden de
recolección de pytest.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    entorno = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )


@pytest.mark.usefixtures("database_url")
def test_upgrade_head_y_downgrade_base_corren_limpios(database_url: str) -> None:
    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    resultado_down = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    # Repetido: debe seguir corriendo limpio sobre una base ya usada.
    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    resultado_down_2 = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down_2.returncode == 0, resultado_down_2.stderr

    # Deja la base en `head`: es compartida con el resto de la sesión de
    # pytest (ver docstring del módulo). Terminar en `base` rompería todos
    # los tests de integración que corran después de este.
    resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_final.returncode == 0, resultado_up_final.stderr
