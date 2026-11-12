"""Tarea 4.2 (change 17, `design.md` D17, `02` §5.3): contratos de import-linter de `cobranzas`.

- Su `domain/` no importa infraestructura ni el bus de comandos.
- `cobranzas` alcanza a `cuentas_corrientes`, `clientes`, `configuracion`, `stock` (la jornada) e
  `identidad` (los permisos) SOLO por su `service.py` (nunca por modelos, repositorio, dominio,
  api ni comandos) y a ningún otro módulo de negocio.
- Nadie alcanza a `cobranzas` salvo `sync` (y `ventas` en el futuro, change 18a), y solo por su
  `service.py`.

Cada contrato se prueba declarado, en verde y, en negativo, detectando un import real que lo
viola (mismo criterio que `test_import_linter_descuentos.py`).
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

ID_DOMAIN = "cobranzas-domain-no-infraestructura"
ID_AJENO = "cobranzas-solo-por-service-ajeno"
ID_NADIE = "nadie-importa-cobranzas"
ID_HACIA = "sync-hacia-cobranzas-solo-por-service"
ID_DOMAIN_SIN_BUS = "domain-no-commands"

DEPENDENCIAS = ("cuentas_corrientes", "clientes", "configuracion", "stock", "identidad")
INTERNOS_DE_OTROS = ("models", "repository", "domain", "api", "commands")
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
)
INTERNOS_DE_COBRANZAS = ("models", "repository", "domain", "api", "commands", "queries")


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


# --- declarados y en verde -------------------------------------------------


def test_el_dominio_es_puro_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.cobranzas.domain"]
    assert {"fastapi", "sqlalchemy", "app.commands"} <= set(contrato["forbidden_modules"])
    assert _correr(ID_DOMAIN) == 0


def test_el_dominio_esta_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert "app.modules.cobranzas.domain" in contrato["source_modules"]
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_cobranzas_alcanza_a_sus_dependencias_solo_por_service_declarado_y_en_verde() -> None:
    """`02` §5.3 (D17): `cobranzas ──► cuentas_corrientes, clientes, configuracion, stock,
    identidad`, solo por `service.py`."""
    contrato = _contratos_por_id()[ID_AJENO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.cobranzas"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in DEPENDENCIAS:
        for interno in INTERNOS_DE_OTROS:
            assert f"app.modules.{modulo}.{interno}" in prohibidos, (modulo, interno)
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    # Ningún otro módulo de negocio, completo (`sync.service` solo por la excepción de la api,
    # declarada cuando existe `api.py`).
    assert {
        "app.modules.catalogo",
        "app.modules.proveedores",
        "app.modules.costeo",
        "app.modules.importacion",
        "app.modules.precios",
        "app.modules.descuentos",
        "app.modules.sync",
    } <= prohibidos
    assert _correr(ID_AJENO) == 0


def test_nadie_importa_cobranzas_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_NADIE]

    assert contrato["type"] == "forbidden"
    assert set(OTROS_MODULOS) == {
        m.removeprefix("app.modules.") for m in contrato["source_modules"]
    }
    assert "app.modules.sync" not in contrato["source_modules"]
    assert contrato["forbidden_modules"] == ["app.modules.cobranzas"]
    assert _correr(ID_NADIE) == 0


def test_sync_alcanza_a_cobranzas_solo_por_service_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_HACIA]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.sync"]
    prohibidos = set(contrato["forbidden_modules"])
    for interno in INTERNOS_DE_COBRANZAS:
        assert f"app.modules.cobranzas.{interno}" in prohibidos, interno
    assert "app.modules.cobranzas.service" not in prohibidos
    assert _correr(ID_HACIA) == 0


# --- en negativo -----------------------------------------------------------


def test_el_dominio_detecta_un_import_de_sqlalchemy_de_fastapi_y_del_bus() -> None:
    archivo = MODULOS_DIR / "cobranzas" / "domain" / "__init__.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import fastapi as _fa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


@pytest.mark.parametrize("modulo", DEPENDENCIAS)
def test_cobranzas_detecta_un_import_de_los_internos_de_otro_modulo(modulo: str) -> None:
    archivo = MODULOS_DIR / "cobranzas" / "__init__.py"

    for interno in ("models", "repository", "domain"):
        linea = f"from app.modules.{modulo} import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize(
    "modulo",
    ["catalogo", "proveedores", "costeo", "importacion", "precios", "descuentos", "sync"],
)
def test_cobranzas_detecta_un_import_de_un_modulo_que_no_es_su_dependencia(modulo: str) -> None:
    archivo = MODULOS_DIR / "cobranzas" / "__init__.py"

    linea = f"from app.modules.{modulo} import service as _s"
    assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_otro_modulo_detecta_cualquier_import_de_cobranzas(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    for interno in ("models", "domain"):
        linea = f"from app.modules.cobranzas import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_NADIE) == 1, (modulo, linea)


def test_sync_detecta_un_import_de_los_internos_de_cobranzas() -> None:
    archivo = MODULOS_DIR / "sync" / "__init__.py"

    for interno in ("models", "domain"):
        linea = f"from app.modules.cobranzas import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_HACIA) == 1, linea


def test_los_caminos_permitidos_por_service_no_se_bloquean() -> None:
    """`02` §5.3: `cobranzas -> <dependencia>.service` es legítimo; la verificación en negativo
    de arriba no bloquea el camino correcto. (El camino `sync -> cobranzas.service` se prueba
    cuando exista `cobranzas/service.py`, tarea 7.1.)"""
    cobranzas = MODULOS_DIR / "cobranzas" / "__init__.py"
    for modulo in DEPENDENCIAS:
        linea = f"from app.modules.{modulo} import service as _s"
        assert _con_import_agregado(cobranzas, linea, ID_AJENO) == 0, linea
