"""Tarea 2.1 (change 10, `design.md` D10, `02` §5.3): contratos de import-linter de
`importacion`.

- Su `domain/` no importa infraestructura ni el bus de comandos.
- `importacion` alcanza a `catalogo`, `proveedores`, `clientes`, `stock`,
  `cuentas_corrientes`, `configuracion` e `identidad` SOLO por su `service.py`
  (nunca por modelos, repositorio, dominio, api ni comandos), y a ningún otro
  módulo de negocio (`costeo` lo usa `stock` por dentro; `sync` solo lo toca la api
  por `procesar_comando`).
- Nadie importa `importacion`: orquesta, no es orquestado.

Cada contrato se prueba declarado, en verde y, en negativo, detectando un import
real que lo viola (mismo criterio que `test_import_linter_stock_costeo.py`).
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

ID_DOMAIN = "importacion-domain-no-infraestructura"
ID_AJENO = "importacion-solo-por-service-ajeno"
ID_NADIE = "nadie-importa-importacion"
ID_DOMAIN_SIN_BUS = "domain-no-commands"

DESTINOS = (
    "catalogo",
    "proveedores",
    "clientes",
    "stock",
    "cuentas_corrientes",
    "configuracion",
    "identidad",
)
OTROS_MODULOS = (
    "identidad",
    "configuracion",
    "catalogo",
    "proveedores",
    "clientes",
    "cuentas_corrientes",
    "costeo",
    "stock",
    "sync",
)


def _contratos_por_id() -> dict[str, dict[str, Any]]:
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {c["id"]: c for c in datos["tool"]["importlinter"]["contracts"] if "id" in c}


def _correr(contrato_id: str) -> int:
    return cli.lint_imports(limit_to_contracts=(contrato_id,), no_cache=True)


def _con_import_agregado(archivo: Path, linea: str, contrato_id: str) -> int:
    """Corre `contrato_id` con `linea` agregada al final de `archivo` y deja el
    archivo como estaba. Exige que el contrato esté declarado: un identificador
    desconocido también devuelve 1 y haría pasar en falso la prueba en negativo."""
    assert contrato_id in _contratos_por_id(), f"contrato no declarado: {contrato_id}"
    original = archivo.read_bytes()  # bytes: conserva los finales de línea
    try:
        archivo.write_bytes(original + f"\n{linea}\n".encode())
        return _correr(contrato_id)
    finally:
        archivo.write_bytes(original)


# --- declarados y en verde -------------------------------------------------


def test_el_dominio_es_puro_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.importacion.domain"]
    assert {"fastapi", "sqlalchemy", "app.commands"} <= set(contrato["forbidden_modules"])
    assert _correr(ID_DOMAIN) == 0


def test_el_dominio_esta_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert "app.modules.importacion.domain" in contrato["source_modules"]
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_importacion_alcanza_a_los_demas_modulos_solo_por_service_declarado_y_en_verde() -> None:
    """`design.md` D10-A: `importacion -> catalogo, proveedores, clientes, stock,
    cuentas_corrientes, configuracion, identidad`, solo por `service.py`."""
    contrato = _contratos_por_id()[ID_AJENO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.importacion"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in DESTINOS:
        for interno in ("models", "repository", "domain", "api", "commands"):
            assert f"app.modules.{modulo}.{interno}" in prohibidos, (modulo, interno)
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    # Sin dependencias de más: `costeo` y `sync` completos (`sync.service` solo por la
    # excepción de la api, declarada cuando existe `api.py`).
    assert {"app.modules.costeo", "app.modules.sync"} <= prohibidos
    assert _correr(ID_AJENO) == 0


def test_nadie_importa_importacion_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_NADIE]

    assert contrato["type"] == "forbidden"
    assert set(OTROS_MODULOS) <= {
        m.removeprefix("app.modules.") for m in contrato["source_modules"]
    }
    assert "app.modules.importacion" not in contrato["source_modules"]
    assert contrato["forbidden_modules"] == ["app.modules.importacion"]
    assert _correr(ID_NADIE) == 0


# --- en negativo -----------------------------------------------------------


def test_el_dominio_detecta_un_import_de_sqlalchemy_de_fastapi_y_del_bus() -> None:
    archivo = MODULOS_DIR / "importacion" / "domain" / "valores.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import fastapi as _fa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


@pytest.mark.parametrize("modulo", DESTINOS)
def test_importacion_detecta_un_import_de_los_internos_de_otro_modulo(modulo: str) -> None:
    archivo = MODULOS_DIR / "importacion" / "__init__.py"

    for interno in ("models", "repository", "domain"):
        linea = f"from app.modules.{modulo} import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


def test_importacion_detecta_un_import_de_costeo_y_de_sync() -> None:
    archivo = MODULOS_DIR / "importacion" / "__init__.py"

    for linea in (
        "from app.modules.costeo import service as _s",
        "from app.modules.sync import models as _m",
    ):
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_otro_modulo_detecta_un_import_de_importacion(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    for linea in (
        "from app.modules.importacion import models as _m",
        "from app.modules.importacion import commands as _c",
        "from app.modules.importacion.domain import planilla as _p",
    ):
        assert _con_import_agregado(archivo, linea, ID_NADIE) == 1, (modulo, linea)


def test_el_camino_permitido_por_service_no_se_bloquea() -> None:
    """`importacion -> proveedores.service` es legítimo (`02` §5.3): la verificación
    en negativo de arriba no bloquea el camino correcto."""
    archivo = MODULOS_DIR / "importacion" / "__init__.py"

    for modulo in ("proveedores", "clientes", "catalogo", "stock", "cuentas_corrientes"):
        linea = f"from app.modules.{modulo} import service as _s"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 0, linea
