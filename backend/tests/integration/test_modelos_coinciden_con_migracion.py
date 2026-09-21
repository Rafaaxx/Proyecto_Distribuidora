"""Tarea 4.3: los modelos de `identidad` y `configuracion` coinciden
exactamente con lo que crea la migración de Alembic.

Corre `alembic revision --autogenerate` sobre la base migrada, a un archivo
temporal fuera de `alembic/versions/`, y falla si el `upgrade()` generado
contiene algo más que `pass` (es decir, si autogenerate detectó una
diferencia entre `Base.metadata` y el esquema real).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
    aplicar_migraciones,
)

_VERSIONES_DIR = BACKEND_DIR / "alembic" / "versions"


def test_autogenerate_no_detecta_diferencias_entre_modelos_y_migracion(
    database_url: str,
) -> None:
    aplicar_migraciones(database_url)

    marca = uuid.uuid4().hex[:8]
    mensaje = f"verificacion_sin_deriva_{marca}"
    antes = set(_VERSIONES_DIR.glob("*.py"))
    try:
        # Alembic lee `DATABASE_URL_MIGRATIONS` (rol `app_migrations`), no
        # `DATABASE_URL` (tarea 1.5, `app/core/alembic_url.py`).
        url_migraciones = _url_con_credenciales(
            database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
        )
        entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}
        resultado = subprocess.run(
            [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", mensaje],
            cwd=BACKEND_DIR,
            env=entorno,
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, resultado.stderr

        generados = list(set(_VERSIONES_DIR.glob("*.py")) - antes)
        assert len(generados) == 1, (
            f"Se esperaba exactamente un archivo nuevo, se encontraron: {generados}"
        )
        contenido = generados[0].read_text(encoding="utf-8")
    finally:
        for nuevo in set(_VERSIONES_DIR.glob("*.py")) - antes:
            nuevo.unlink()

    cuerpo_upgrade = contenido.split("def upgrade() -> None:")[1].split("def downgrade() -> None:")[
        0
    ]
    lineas_de_codigo = [
        linea.strip()
        for linea in cuerpo_upgrade.splitlines()
        if linea.strip() and not linea.strip().startswith("#") and '"""' not in linea
    ]

    assert lineas_de_codigo == ["pass"], (
        "Los modelos de identidad/configuracion no coinciden con la migracion "
        f"(tarea 4.3). Autogenerate detecto: {lineas_de_codigo}"
    )
