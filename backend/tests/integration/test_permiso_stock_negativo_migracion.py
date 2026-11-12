"""Change 22a (ADR-063 punto 7): la revision `b7d3f1a9c2e4` actualiza en una base YA migrada la
descripcion del permiso `PERMITIR_STOCK_NEGATIVO` ("Operar con stock negativo online" ->
"Operar con stock negativo"), porque el catalogo se inserta con `ON CONFLICT DO NOTHING`. El
`downgrade` restaura el texto anterior. Regla citada: STK-06.
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from sqlalchemy import Engine, text

REVISION_ANTERIOR = "a9c1e3f5b7d2"  # `catalogos_de_configuracion`, la previa a esta revision.
CODIGO = "PERMITIR_STOCK_NEGATIVO"


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones},
        capture_output=True,
        text=True,
    )


def _descripcion(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT descripcion FROM permiso WHERE codigo = :c"), {"c": CODIGO}
        ).scalar_one()


def test_la_revision_actualiza_la_descripcion_en_una_base_ya_migrada_y_el_downgrade_la_restaura(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    try:
        # Base "vieja": el texto con "online" que ya tienen las bases migradas antes del change.
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _descripcion(_engine_de_sesion) == "Operar con stock negativo online"

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _descripcion(_engine_de_sesion) == "Operar con stock negativo"

        # Otra descripcion distinta de la nueva: el UPDATE es por codigo y no toca al resto.
        with _engine_de_sesion.connect() as conexion:
            otra = conexion.execute(
                text("SELECT descripcion FROM permiso WHERE codigo = 'VENDER'")
            ).scalar_one()
        assert otra != "Operar con stock negativo"
    finally:
        restaurar = _alembic(database_url, "upgrade", "head")
        assert restaurar.returncode == 0, restaurar.stderr
