"""Tarea 2.3 (change 18a, `design.md` D14, `02` §5.3): contratos de import-linter del dominio de
`ventas`.

- Su `domain/` es puro: no importa FastAPI, SQLAlchemy, el bus de comandos ni las capas de
  infraestructura de su propio módulo (`service.py`, modelos, repositorio, api, comandos).
- Su `domain/` no alcanza a ningún otro módulo de negocio salvo dos funciones puras, declaradas
  como `ignore_imports` documentados: `precios.domain.bruto_de_linea` (PRC-22) y
  `descuentos.domain` (el motor, DSC-05).

Los contratos de `ventas` hacia los `service.py` ajenos (tarea 4.2) se prueban en este mismo
archivo cuando existan. Cada contrato se prueba declarado, en verde y, en negativo, detectando un
import real que lo viola (mismo criterio que `test_import_linter_cobranzas.py`).
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
DOMINIO_VENTAS = MODULOS_DIR / "ventas" / "domain"

ID_PURO = "ventas-domain-no-infraestructura"
ID_AJENO = "ventas-domain-solo-dominio-puro-ajeno"
ID_DOMAIN_SIN_BUS = "domain-no-commands"

INTERNOS_DE_VENTAS = ("models", "repository", "service", "api", "commands", "queries")
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
    "cobranzas",
    "sync",
)
EXCEPCIONES = {
    "app.modules.ventas.domain.calculo -> app.modules.precios.domain.bruto_de_linea",
    "app.modules.ventas.domain.calculo -> app.modules.descuentos.domain.*",
}


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
    original = archivo.read_bytes()
    try:
        archivo.write_bytes(original + f"\n{linea}\n".encode())
        return _correr(contrato_id)
    finally:
        archivo.write_bytes(original)


# --- declarados y en verde -------------------------------------------------


def test_el_dominio_es_puro_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_PURO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.ventas.domain"]
    prohibidos = set(contrato["forbidden_modules"])
    assert {"fastapi", "sqlalchemy", "app.commands"} <= prohibidos
    for interno in INTERNOS_DE_VENTAS:
        assert f"app.modules.ventas.{interno}" in prohibidos, interno
    assert _correr(ID_PURO) == 0


def test_el_dominio_esta_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert "app.modules.ventas.domain" in contrato["source_modules"]
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_el_dominio_solo_alcanza_dos_dominios_ajenos_por_excepciones_documentadas() -> None:
    contrato = _contratos_por_id()[ID_AJENO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.ventas.domain"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in (*OTROS_MODULOS, "precios", "descuentos"):
        assert f"app.modules.{modulo}" in prohibidos, modulo
    # Exactamente dos excepciones (D14), ninguna más.
    assert set(contrato["ignore_imports"]) == EXCEPCIONES
    assert _correr(ID_AJENO) == 0


# --- en negativo -----------------------------------------------------------


def test_el_dominio_detecta_un_import_de_sqlalchemy_de_fastapi_y_del_bus() -> None:
    archivo = DOMINIO_VENTAS / "__init__.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_PURO) == 1
    assert _con_import_agregado(archivo, "import fastapi as _fa", ID_PURO) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_PURO) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


@pytest.mark.parametrize("modulo", OTROS_MODULOS)
def test_el_dominio_detecta_un_import_del_service_de_otro_modulo(modulo: str) -> None:
    archivo = DOMINIO_VENTAS / "__init__.py"

    linea = f"from app.modules.{modulo} import service as _s"
    assert _con_import_agregado(archivo, linea, ID_AJENO) == 1, linea


def test_las_excepciones_valen_solo_para_calculo_py() -> None:
    """Las dos funciones puras se alcanzan desde `calculo.py` y desde ningún otro archivo del
    dominio, y de `precios` no se alcanza nada más que `bruto_de_linea`."""
    otro = DOMINIO_VENTAS / "errores.py"

    linea = "from app.modules.precios.domain import bruto_de_linea as _b"
    assert _con_import_agregado(otro, linea, ID_AJENO) == 1
    linea = "from app.modules.descuentos.domain import motor as _m"
    assert _con_import_agregado(otro, linea, ID_AJENO) == 1
    calculo = DOMINIO_VENTAS / "calculo.py"
    linea = "from app.modules.precios import service as _s"
    assert _con_import_agregado(calculo, linea, ID_AJENO) == 1
    linea = "from app.modules.descuentos import service as _s"
    assert _con_import_agregado(calculo, linea, ID_AJENO) == 1


# --- tarea 4.2: ventas hacia los demás módulos (02 §5.3, D17) -----------------------------

ID_SOLO_SERVICE = "ventas-solo-por-service-ajeno"
ID_NADIE = "nadie-importa-ventas"
ID_SYNC_HACIA = "sync-hacia-ventas-solo-por-service"

DEPENDENCIAS = (
    "precios",
    "descuentos",
    "clientes",
    "stock",
    "costeo",
    "cuentas_corrientes",
    "cobranzas",
    "catalogo",
    "configuracion",
    "identidad",
)
INTERNOS_DE_OTROS = ("models", "repository", "domain")
"""Los internos que todo módulo de negocio tiene; los módulos con `api`, `commands` o `queries`
los suman en el contrato."""
MODULOS_FUERA_DE_VENTAS = (
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
)
SERVICE_DE_VENTAS = MODULOS_DIR / "ventas" / "service.py"


def test_ventas_alcanza_a_sus_dependencias_solo_por_service_declarado_y_en_verde() -> None:
    """`02` §5.3: `ventas ──► precios, descuentos, clientes, stock, costeo, cuentas_corrientes,
    cobranzas, catalogo, configuracion, identidad`, solo por `service.py`."""
    contrato = _contratos_por_id()[ID_SOLO_SERVICE]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.ventas"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in DEPENDENCIAS:
        for interno in INTERNOS_DE_OTROS:
            assert f"app.modules.{modulo}.{interno}" in prohibidos, (modulo, interno)
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    # Ningún otro módulo de negocio, completo.
    assert {
        "app.modules.proveedores",
        "app.modules.importacion",
        "app.modules.sync",
    } <= prohibidos
    # Las dos funciones puras de D14 y, desde la tarea 7.8, el bus que llama la api de ventas
    # (`sync.service`, como `cobranzas.api`): ninguna otra.
    assert set(contrato["ignore_imports"]) == EXCEPCIONES | {
        "app.modules.ventas.api -> app.modules.sync.service"
    }
    assert _correr(ID_SOLO_SERVICE) == 0


@pytest.mark.parametrize(
    ("modulo", "interno"), [(m, i) for m in DEPENDENCIAS for i in ("models", "repository")]
)
def test_ventas_detecta_un_import_de_modelos_o_repositorio_ajenos(
    modulo: str, interno: str
) -> None:
    linea = f"from app.modules.{modulo} import {interno} as _x"
    assert _con_import_agregado(SERVICE_DE_VENTAS, linea, ID_SOLO_SERVICE) == 1, linea


@pytest.mark.parametrize("modulo", DEPENDENCIAS)
def test_ventas_puede_importar_el_service_de_sus_dependencias(modulo: str) -> None:
    linea = f"from app.modules.{modulo} import service as _s"
    assert _con_import_agregado(SERVICE_DE_VENTAS, linea, ID_SOLO_SERVICE) == 0, linea


@pytest.mark.parametrize("modulo", ["proveedores", "importacion", "sync"])
def test_ventas_no_alcanza_a_proveedores_importacion_ni_sync_ni_por_su_service(
    modulo: str,
) -> None:
    linea = f"from app.modules.{modulo} import service as _s"
    assert _con_import_agregado(SERVICE_DE_VENTAS, linea, ID_SOLO_SERVICE) == 1, linea


def test_nadie_importa_ventas_declarado_y_en_verde() -> None:
    """`02` §5.3: nadie alcanza `ventas` salvo `sync` y por su `service.py`."""
    contrato = _contratos_por_id()[ID_NADIE]

    assert contrato["type"] == "forbidden"
    assert {m.removeprefix("app.modules.") for m in contrato["source_modules"]} == set(
        MODULOS_FUERA_DE_VENTAS
    )
    assert "app.modules.sync" not in contrato["source_modules"]
    assert contrato["forbidden_modules"] == ["app.modules.ventas"]
    assert _correr(ID_NADIE) == 0


@pytest.mark.parametrize("modulo", MODULOS_FUERA_DE_VENTAS)
def test_ningun_otro_modulo_puede_importar_ventas_ni_por_su_service(modulo: str) -> None:
    # `importacion` no tiene `service.py`: se usa su `commands.py`.
    archivo = MODULOS_DIR / modulo / ("commands.py" if modulo == "importacion" else "service.py")

    linea = "from app.modules.ventas import service as _ventas"
    assert _con_import_agregado(archivo, linea, ID_NADIE) == 1, modulo


def test_sync_alcanza_a_ventas_solo_por_service_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_SYNC_HACIA]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.sync"]
    prohibidos = set(contrato["forbidden_modules"])
    for interno in ("models", "repository", "domain", "api", "commands", "queries"):
        assert f"app.modules.ventas.{interno}" in prohibidos, interno
    assert "app.modules.ventas.service" not in prohibidos
    assert _correr(ID_SYNC_HACIA) == 0


@pytest.mark.parametrize("interno", ["models", "repository", "domain"])
def test_sync_detecta_un_import_de_los_internos_de_ventas(interno: str) -> None:
    """Se prueban los internos que ya existen; `api`, `commands` y `queries` quedan declarados
    en el contrato y se prueban en negativo cuando sus archivos se crean (grupos 7 y 9)."""
    archivo = MODULOS_DIR / "sync" / "service.py"

    linea = f"from app.modules.ventas import {interno} as _x"
    assert _con_import_agregado(archivo, linea, ID_SYNC_HACIA) == 1, linea
