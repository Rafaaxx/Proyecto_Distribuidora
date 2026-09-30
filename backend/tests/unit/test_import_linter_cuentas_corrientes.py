"""Tarea 2.2 (`design.md` D7, `02` §5.3): contratos de import-linter de
`cuentas_corrientes`.

- Su `domain/` no importa infraestructura ni el bus de comandos.
- `cuentas_corrientes` no importa ningún otro módulo de negocio (ni `clientes`,
  ni `proveedores`, ni `catalogo`, ni `configuracion`) y de `identidad` solo
  alcanza su `service.py`.
- `clientes` y `proveedores` alcanzan a `cuentas_corrientes` solo por su
  `service.py` (`02` §5.3: `clientes -> cuentas_corrientes`,
  `proveedores -> cuentas_corrientes`).

Cada contrato se prueba declarado, en verde y, en negativo, detectando un
import real que lo viola (mismo criterio que
`test_import_linter_bus_de_comandos.py`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from importlinter import cli

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PYPROJECT = BACKEND_DIR / "pyproject.toml"
MODULOS_DIR = BACKEND_DIR / "app" / "modules"

ID_DOMAIN_PURO = "cuentas-corrientes-domain-no-infraestructura"
ID_SOLO_SERVICE_AJENO = "cuentas-corrientes-solo-por-service-ajeno"
ID_CLIENTES = "clientes-solo-por-service-ajeno"
ID_PROVEEDORES = "proveedores-solo-por-service-ajeno"
ID_DOMAIN_SIN_BUS = "domain-no-commands"


def _contratos_por_id() -> dict[str, dict[str, Any]]:
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {c["id"]: c for c in datos["tool"]["importlinter"]["contracts"] if "id" in c}


def _correr(contrato_id: str) -> int:
    return cli.lint_imports(limit_to_contracts=(contrato_id,), no_cache=True)


def _con_import_agregado(archivo: Path, linea: str, contrato_id: str) -> int:
    """Corre `contrato_id` con `linea` agregada al final de `archivo` y deja el
    archivo como estaba."""
    original = archivo.read_text(encoding="utf-8")
    try:
        archivo.write_text(original + f"\n{linea}\n", encoding="utf-8")
        return _correr(contrato_id)
    finally:
        archivo.write_text(original, encoding="utf-8")


# --- declarados y en verde -------------------------------------------------


def test_el_dominio_de_cuentas_corrientes_es_puro_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_PURO]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.cuentas_corrientes.domain"]
    assert {"fastapi", "sqlalchemy", "app.commands"} <= set(contrato["forbidden_modules"])
    assert _correr(ID_DOMAIN_PURO) == 0


def test_el_dominio_de_cuentas_corrientes_esta_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert "app.modules.cuentas_corrientes.domain" in contrato["source_modules"]
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_cuentas_corrientes_no_depende_de_otros_modulos_de_negocio_declarado_y_en_verde() -> None:
    contrato = _contratos_por_id()[ID_SOLO_SERVICE_AJENO]

    assert contrato["source_modules"] == ["app.modules.cuentas_corrientes"]
    prohibidos = set(contrato["forbidden_modules"])
    assert {
        "app.modules.clientes",
        "app.modules.proveedores",
        "app.modules.catalogo",
        "app.modules.configuracion",
        "app.modules.identidad.models",
        "app.modules.identidad.repository",
        "app.modules.identidad.api",
        "app.modules.identidad.domain",
    } <= prohibidos
    # `identidad.service` NO está prohibido: es el único alcance permitido.
    assert "app.modules.identidad.service" not in prohibidos
    assert "app.modules.identidad" not in prohibidos
    assert _correr(ID_SOLO_SERVICE_AJENO) == 0


def test_clientes_y_proveedores_alcanzan_a_cuentas_corrientes_solo_por_service_declarado() -> None:
    contratos = _contratos_por_id()
    for contrato_id, modulo in ((ID_CLIENTES, "clientes"), (ID_PROVEEDORES, "proveedores")):
        contrato = contratos[contrato_id]
        assert contrato["source_modules"] == [f"app.modules.{modulo}"]
        prohibidos = set(contrato["forbidden_modules"])
        for interno in ("models", "repository", "api", "domain", "commands"):
            assert f"app.modules.cuentas_corrientes.{interno}" in prohibidos, (
                f"{modulo} puede importar cuentas_corrientes.{interno}"
            )
        assert "app.modules.cuentas_corrientes.service" not in prohibidos
        assert _correr(contrato_id) == 0


# --- en negativo -----------------------------------------------------------


def test_el_dominio_detecta_un_import_de_sqlalchemy() -> None:
    archivo = MODULOS_DIR / "cuentas_corrientes" / "domain" / "catalogo.py"

    assert _con_import_agregado(archivo, "import sqlalchemy as _sa", ID_DOMAIN_PURO) == 1


def test_el_dominio_detecta_un_import_del_bus_de_comandos() -> None:
    archivo = MODULOS_DIR / "cuentas_corrientes" / "domain" / "reglas.py"

    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_PURO) == 1
    assert _con_import_agregado(archivo, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


def test_cuentas_corrientes_detecta_un_import_de_clientes() -> None:
    archivo = MODULOS_DIR / "cuentas_corrientes" / "domain" / "errores.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.clientes import service as _s", ID_SOLO_SERVICE_AJENO
        )
        == 1
    )


def test_cuentas_corrientes_detecta_un_import_de_los_modelos_de_identidad() -> None:
    archivo = MODULOS_DIR / "cuentas_corrientes" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.identidad import models as _m", ID_SOLO_SERVICE_AJENO
        )
        == 1
    )


def test_clientes_detecta_un_import_de_los_modelos_de_cuentas_corrientes() -> None:
    archivo = MODULOS_DIR / "clientes" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.cuentas_corrientes import models as _m", ID_CLIENTES
        )
        == 1
    )


def test_proveedores_detecta_un_import_de_los_modelos_de_cuentas_corrientes() -> None:
    archivo = MODULOS_DIR / "proveedores" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.cuentas_corrientes import models as _m", ID_PROVEEDORES
        )
        == 1
    )


def test_clientes_puede_importar_el_service_de_cuentas_corrientes() -> None:
    """El caso permitido: la verificación en negativo de arriba no bloquea el
    camino legítimo (CLI-06, D8)."""
    service = MODULOS_DIR / "cuentas_corrientes" / "service.py"
    archivo = MODULOS_DIR / "clientes" / "__init__.py"
    creado = not service.exists()
    if creado:
        service.write_text("", encoding="utf-8")
    try:
        assert (
            _con_import_agregado(
                archivo, "from app.modules.cuentas_corrientes import service as _s", ID_CLIENTES
            )
            == 0
        )
    finally:
        if creado:
            service.unlink()
