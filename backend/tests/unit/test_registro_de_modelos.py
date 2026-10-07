"""Change 13, tarea 2.1/5.x: `app/modelos.py` registra TODOS los modelos en `Base.metadata`.

`cliente` y `configuracion_organizacion` tienen una clave foránea compuesta a `lista_precio`
(`precios`): SQLAlchemy resuelve la tabla destino por nombre al ordenar un `flush`, así que
cualquier proceso que escriba un cliente o la configuración de una organización tiene que
haber importado también `precios.models`. Sin un registro único, `python -m app.seed` o una
prueba de concurrencia fallan con `NoReferencedTableError` según qué módulos importaron.

Cada caso corre en un intérprete limpio (`subprocess`) porque lo que se prueba es lo que
queda en `Base.metadata` al importar solo ese punto de entrada.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

TABLAS_DE_PRECIOS = {
    "lista_precio",
    "regla_margen",
    "redondeo_categoria",
    "lista_version",
    "precio_item",
}


def _en_interprete_limpio(codigo: str) -> str:
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=BACKEND_DIR,
        env={**os.environ, "PYTHONPATH": str(BACKEND_DIR)},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    return resultado.stdout.strip()


@pytest.mark.parametrize("punto_de_entrada", ["app.modelos", "app.seed"])
def test_el_punto_de_entrada_deja_resolver_todas_las_claves_foraneas(
    punto_de_entrada: str,
) -> None:
    """`sorted_tables` resuelve todas las claves foráneas: falla con `NoReferencedTableError`
    si falta alguna tabla destino."""
    salida = _en_interprete_limpio(
        f"import {punto_de_entrada}\n"
        "from app.core.db import Base\n"
        "tablas = {t.name for t in Base.metadata.sorted_tables}\n"
        "print(','.join(sorted(tablas)))\n"
    )

    assert set(salida.split(",")) >= TABLAS_DE_PRECIOS


def test_el_registro_incluye_las_tablas_de_todos_los_modulos() -> None:
    salida = _en_interprete_limpio(
        "import app.modelos\n"
        "from app.core.db import Base\n"
        "print(','.join(sorted(t.name for t in Base.metadata.sorted_tables)))\n"
    )
    tablas = set(salida.split(","))

    assert {"usuario", "producto", "proveedor", "cliente", "cuenta_movimiento", "stock_saldo"} <= (
        tablas
    )
    assert tablas >= TABLAS_DE_PRECIOS
