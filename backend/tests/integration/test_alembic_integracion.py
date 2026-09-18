"""Verifica que la revisión base vacía aplica y revierte limpia contra
PostgreSQL real (`docs/04-roadmap-changes.md` §2.1, criterio 4).
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
