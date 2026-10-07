"""Tarea 2.2 (change 13, `design.md` D11 y `Enfoque técnico`, `02` §5.3): contratos de
import-linter de `precios`.

- Su `domain/` no importa infraestructura ni el bus de comandos.
- `precios` alcanza a `catalogo`, `proveedores` e `identidad` SOLO por su `service.py`
  (nunca por modelos, repositorio, dominio, api ni comandos) y a ningún otro módulo de
  negocio.
- Los demás módulos alcanzan a `precios` solo por su `service.py` (`clientes` en el
  grupo 10 y `importacion` en el 13b); ninguno de los que `precios` usa lo importa de
  vuelta, para que no haya ciclos (`02` §5.3: `clientes ──► precios`, nunca al revés).

Cada contrato se prueba declarado, en verde y, en negativo, detectando un import real
que lo viola (mismo criterio que `test_import_linter_importacion.py`).
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

ID_DOMAIN = "precios-domain-no-infraestructura"
ID_AJENO = "precios-solo-por-service-ajeno"
ID_HACIA = "modulos-hacia-precios-solo-por-service"
ID_SIN_CICLO = "precios-no-es-alcanzado-por-sus-dependencias"
ID_DOMAIN_SIN_BUS = "domain-no-commands"

DEPENDENCIAS = ("catalogo", "proveedores", "identidad")
INTERNOS = ("models", "repository", "domain", "api", "commands")
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
    "sync",
)
# Los que `precios` usa o con los que no tiene relación: no pueden importarlo ni por
# `service.py`. `clientes` (grupo 10) e `importacion` (13b) sí.
SIN_RUTA_A_PRECIOS = (
    "identidad",
    "configuracion",
    "catalogo",
    "proveedores",
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


def _existe_interno_de_precios(nombre: str) -> bool:
    base = MODULOS_DIR / "precios"
    return (base / f"{nombre}.py").exists() or (base / nombre / "__init__.py").exists()


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
    assert contrato["source_modules"] == ["app.modules.precios.domain"]
    assert {"fastapi", "sqlalchemy", "app.commands"} <= set(contrato["forbidden_modules"])
    assert _correr(ID_DOMAIN) == 0


def test_el_dominio_esta_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert "app.modules.precios.domain" in contrato["source_modules"]
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_precios_alcanza_a_sus_dependencias_solo_por_service_declarado_y_en_verde() -> None:
    """`02` §5.3: `precios ──► catalogo, proveedores, identidad`, solo por `service.py`."""
    contrato = _contratos_por_id()[ID_AJENO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.precios"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in DEPENDENCIAS:
        for interno in INTERNOS:
            assert f"app.modules.{modulo}.{interno}" in prohibidos, (modulo, interno)
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    # Sin dependencias de más: ningún otro módulo de negocio, completo (`sync.service`
    # solo por la excepción de la api, declarada cuando existe `api.py`).
    assert {
        "app.modules.configuracion",
        "app.modules.clientes",
        "app.modules.cuentas_corrientes",
        "app.modules.costeo",
        "app.modules.stock",
        "app.modules.importacion",
        "app.modules.sync",
    } <= prohibidos
    assert _correr(ID_AJENO) == 0


def test_los_demas_modulos_alcanzan_a_precios_solo_por_service_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_HACIA]

    assert contrato["type"] == "forbidden"
    assert set(OTROS_MODULOS) <= {
        m.removeprefix("app.modules.") for m in contrato["source_modules"]
    }
    assert "app.modules.precios" not in contrato["source_modules"]
    prohibidos = set(contrato["forbidden_modules"])
    for interno in (*INTERNOS, "queries"):
        assert f"app.modules.precios.{interno}" in prohibidos, interno
    assert "app.modules.precios.service" not in prohibidos
    assert _correr(ID_HACIA) == 0


def test_las_dependencias_de_precios_no_lo_importan_de_vuelta_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_SIN_CICLO]

    assert contrato["type"] == "forbidden"
    assert {m.removeprefix("app.modules.") for m in contrato["source_modules"]} == set(
        SIN_RUTA_A_PRECIOS
    )
    assert contrato["forbidden_modules"] == ["app.modules.precios"]
    assert _correr(ID_SIN_CICLO) == 0


# --- en negativo -----------------------------------------------------------


def test_el_dominio_detecta_un_import_de_sqlalchemy_de_fastapi_y_del_bus() -> None:
    archivo = MODULOS_DIR / "precios" / "domain" / "__init__.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import fastapi as _fa", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


@pytest.mark.parametrize("modulo", DEPENDENCIAS)
def test_precios_detecta_un_import_de_los_internos_de_otro_modulo(modulo: str) -> None:
    archivo = MODULOS_DIR / "precios" / "__init__.py"

    for interno in ("models", "repository", "domain"):
        linea = f"from app.modules.{modulo} import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize(
    "modulo",
    ["configuracion", "clientes", "cuentas_corrientes", "costeo", "stock", "importacion", "sync"],
)
def test_precios_detecta_un_import_de_un_modulo_que_no_es_su_dependencia(modulo: str) -> None:
    archivo = MODULOS_DIR / "precios" / "__init__.py"

    linea = f"from app.modules.{modulo} import service as _s"
    assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_otro_modulo_detecta_un_import_de_los_internos_de_precios(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    # `from precios import X` solo cuenta como import de `precios.X` si `X` existe; los
    # internos que todavía no se crearon (`repository`, `commands`, `api`, `queries`) los
    # cubre la lista de `forbidden_modules` que verifica el test declarativo de arriba.
    existentes = [i for i in (*INTERNOS, "queries") if _existe_interno_de_precios(i)]
    assert {"models", "domain"} <= set(existentes)
    for interno in existentes:
        linea = f"from app.modules.precios import {interno} as _m"
        assert _con_import_agregado(archivo, linea, ID_HACIA) == 1, (modulo, linea)


@pytest.mark.parametrize("modulo", SIN_RUTA_A_PRECIOS)
def test_una_dependencia_de_precios_detecta_un_import_de_precios_aunque_sea_por_service(
    modulo: str,
) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    linea = "from app.modules.precios import service as _s"
    assert _con_import_agregado(archivo, linea, ID_SIN_CICLO) == 1, (modulo, linea)


def test_los_caminos_permitidos_por_service_no_se_bloquean() -> None:
    """`precios -> catalogo.service` y `clientes -> precios.service` son legítimos
    (`02` §5.3): la verificación en negativo de arriba no bloquea el camino correcto."""
    precios = MODULOS_DIR / "precios" / "__init__.py"
    for modulo in DEPENDENCIAS:
        linea = f"from app.modules.{modulo} import service as _s"
        assert _con_import_agregado(precios, linea, ID_AJENO) == 0, linea

    for modulo in ("clientes", "importacion"):
        archivo = MODULOS_DIR / modulo / "__init__.py"
        linea = "from app.modules.precios import service as _s"
        assert _con_import_agregado(archivo, linea, ID_HACIA) == 0, (modulo, linea)
