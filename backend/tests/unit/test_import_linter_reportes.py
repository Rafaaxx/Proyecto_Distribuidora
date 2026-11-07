"""Tarea 2.1 (change 26, `design.md` D6, `02` §5.2): contratos de import-linter de `reportes`.

- Ningún otro módulo importa `reportes`.
- `reportes` alcanza a los demás módulos solo por su `models` (lectura) y su `service`: nunca por
  `commands`, `repository`, `*_repository`, `*_casos`, `*_commands`, `queries`, `api`, `domain`.
- `reportes.domain` no importa infraestructura ni el bus de comandos ni otro módulo de negocio.

Cada contrato se prueba declarado, en verde y, en negativo, detectando un import real que lo viola
(mismo criterio que `test_import_linter_cobranzas.py`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
from importlinter import cli

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PYPROJECT = BACKEND_DIR / "pyproject.toml"
MODULOS_DIR = BACKEND_DIR / "app" / "modules"

ID_DOMAIN = "reportes-domain-no-infraestructura"
ID_AJENO = "reportes-solo-models-y-service-ajenos"
ID_NADIE = "nadie-importa-reportes"

OTROS_MODULOS = (
    "identidad",
    "configuracion",
    "catalogo",
    "proveedores",
    "clientes",
    "cuentas_corrientes",
    "costeo",
    "stock",
    "importacion",
    "precios",
    "descuentos",
    "cobranzas",
    "ventas",
    "sync",
)


def _contratos_por_id() -> dict[str, dict[str, Any]]:
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {c["id"]: c for c in datos["tool"]["importlinter"]["contracts"] if "id" in c}


def _correr(contrato_id: str) -> int:
    return cli.lint_imports(limit_to_contracts=(contrato_id,), no_cache=True)


def _con_import_agregado(archivo: Path, linea: str, contrato_id: str) -> int:
    """Corre `contrato_id` con `linea` agregada al final de `archivo` y deja el archivo como
    estaba. Exige que el contrato esté declarado: un identificador desconocido también devuelve
    1 y haría pasar en falso la prueba en negativo."""
    assert contrato_id in _contratos_por_id(), f"contrato no declarado: {contrato_id}"
    original = archivo.read_bytes()  # bytes: conserva los finales de línea
    try:
        archivo.write_bytes(original + f"\n{linea}\n".encode())
        return _correr(contrato_id)
    finally:
        archivo.write_bytes(original)


def _internos_de(modulo: str) -> list[str]:
    """Los archivos y paquetes de `modulo` que NO son `models` ni `service` (ni `__init__`)."""
    carpeta = MODULOS_DIR / modulo
    nombres = {p.stem for p in carpeta.iterdir() if p.suffix == ".py" or p.is_dir()}
    return sorted(nombres - {"__init__", "__pycache__", "models", "service"})


# --- declarados y en verde -------------------------------------------------


def test_nadie_importa_reportes_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_NADIE]

    assert contrato["type"] == "forbidden"
    assert {m.removeprefix("app.modules.") for m in contrato["source_modules"]} == set(
        OTROS_MODULOS
    )
    assert contrato["forbidden_modules"] == ["app.modules.reportes"]
    assert _correr(ID_NADIE) == 0


def test_reportes_alcanza_a_los_demas_solo_por_models_y_service_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_AJENO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.reportes"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in OTROS_MODULOS:
        internos = _internos_de(modulo)
        assert internos, modulo
        for interno in internos:
            assert f"app.modules.{modulo}.{interno}" in prohibidos, (modulo, interno)
        assert f"app.modules.{modulo}.models" not in prohibidos
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    assert _correr(ID_AJENO) == 0


def test_el_dominio_de_reportes_es_puro_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.reportes.domain"]
    prohibidos = set(contrato["forbidden_modules"])
    assert {"fastapi", "sqlalchemy", "app.commands"} <= prohibidos
    for modulo in OTROS_MODULOS:
        assert f"app.modules.{modulo}" in prohibidos, modulo
    assert _correr(ID_DOMAIN) == 0


# --- en negativo -----------------------------------------------------------


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_otro_modulo_detecta_cualquier_import_de_reportes(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    for interno in ("domain", "repository"):
        linea = f"from app.modules.reportes import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_NADIE) == 1, (modulo, linea)


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_reportes_detecta_un_import_de_los_internos_de_otro_modulo(modulo: str) -> None:
    archivo = MODULOS_DIR / "reportes" / "__init__.py"

    for interno in _internos_de(modulo):
        linea = f"from app.modules.{modulo} import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_reportes_puede_leer_los_models_y_usar_el_service_de_otro_modulo(modulo: str) -> None:
    """El camino permitido: lectura por `models` y llamadas por `service` no se bloquean."""
    archivo = MODULOS_DIR / "reportes" / "__init__.py"

    permitidos = ["models"] + (
        ["service"] if (MODULOS_DIR / modulo / "service.py").exists() else []
    )
    for parte in permitidos:
        linea = f"from app.modules.{modulo} import {parte} as _m"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 0, linea


def test_el_dominio_de_reportes_detecta_infraestructura_el_bus_y_otros_modulos() -> None:
    archivo = MODULOS_DIR / "reportes" / "domain" / "__init__.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import fastapi as _fa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN) == 1
    assert (
        _con_import_agregado(archivo, "from app.modules.ventas import models as _m", ID_DOMAIN) == 1
    )
