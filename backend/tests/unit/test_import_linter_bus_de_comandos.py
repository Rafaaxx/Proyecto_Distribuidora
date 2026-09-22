"""Tareas 1.2/1.3 (`design.md` D3, `02` §5.3): contratos de import-linter que
fijan los límites entre el mecanismo del bus (`app/commands/`) y los módulos
de negocio:

- `app/commands/` no importa ningún `app/modules/*` (el mecanismo no conoce
  los módulos que lo usan).
- Ningún `domain/` de un módulo importa `app/commands/` (el dominio es puro,
  no depende del bus que lo invoca).
- `app/modules/sync/` (dueño de `comando`, `comando_cuarentena` y
  `observacion`, grupo 8) solo alcanza a los demás módulos por su
  `service.py`, nunca por sus modelos, repositorio, api o dominio -- mismo
  criterio que ya rige entre `identidad` y `configuracion`
  (`test_modulos_solo_se_usan_por_service.py`).

Escrita antes de declarar los contratos (tarea 1.2): falla hoy porque
`pyproject.toml` todavía no los tiene. La tarea 1.3 los declara y deja esta
prueba en verde.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from importlinter import cli

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PYPROJECT = BACKEND_DIR / "pyproject.toml"

NOMBRE_CONTRATO_COMMANDS = "commands no importa modulos de negocio"
NOMBRE_CONTRATO_DOMAIN = "domain no importa el bus de comandos"
NOMBRE_CONTRATO_SYNC = "sync solo alcanza a los demas modulos por su service.py"

ID_CONTRATO_COMMANDS = "commands-no-modulos"
ID_CONTRATO_DOMAIN = "domain-no-commands"
ID_CONTRATO_SYNC = "sync-solo-service"


def _contratos_declarados() -> dict[str, dict[str, Any]]:
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contratos = datos["tool"]["importlinter"]["contracts"]
    return {contrato["name"]: contrato for contrato in contratos}


def _correr_contrato(contrato_id: str) -> int:
    # `config_filename=None` deja que import-linter descubra `pyproject.toml`
    # como lo hace `lint-imports` desde la línea de comandos (`CLAUDE.md`
    # §3): pasarle la ruta explícita rompe la resolución de `limit_to_contracts`
    # por `id` (comportamiento de la librería, no de este proyecto).
    return cli.lint_imports(
        limit_to_contracts=(contrato_id,),
        no_cache=True,
    )


def test_contrato_commands_no_importa_modulos_de_negocio_declarado_y_en_verde() -> None:
    contratos = _contratos_declarados()
    assert NOMBRE_CONTRATO_COMMANDS in contratos, (
        "Falta declarar el contrato que impide que app/commands/ importe "
        "app/modules/* (design.md D3)."
    )
    contrato = contratos[NOMBRE_CONTRATO_COMMANDS]
    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.commands"]
    assert "app.modules" in contrato["forbidden_modules"]

    assert _correr_contrato(ID_CONTRATO_COMMANDS) == 0


def test_contrato_domain_no_importa_el_bus_de_comandos_declarado_y_en_verde() -> None:
    contratos = _contratos_declarados()
    assert NOMBRE_CONTRATO_DOMAIN in contratos, (
        "Falta declarar el contrato que impide que domain/ importe "
        "app/commands/ (design.md D3, '02' §5.3)."
    )
    contrato = contratos[NOMBRE_CONTRATO_DOMAIN]
    assert contrato["type"] == "forbidden"
    assert "app.commands" in contrato["forbidden_modules"]
    assert all(fuente.endswith(".domain") for fuente in contrato["source_modules"])
    # Cubre todo domain/ existente, no solo un módulo: si se agrega un
    # módulo nuevo con domain/ sin extender esta lista, esta aserción lo
    # señala.
    modulos_con_domain = sorted(
        p.parent.parent.name for p in (BACKEND_DIR / "app" / "modules").glob("*/domain/__init__.py")
    )
    modulos_cubiertos = sorted(
        fuente.removeprefix("app.modules.").removesuffix(".domain")
        for fuente in contrato["source_modules"]
    )
    assert modulos_cubiertos == modulos_con_domain

    assert _correr_contrato(ID_CONTRATO_DOMAIN) == 0


def test_contrato_sync_solo_alcanza_a_los_demas_modulos_por_su_service_declarado_y_en_verde() -> (
    None
):
    contratos = _contratos_declarados()
    assert NOMBRE_CONTRATO_SYNC in contratos, (
        "Falta declarar el contrato que exige que sync/ solo importe el "
        "service.py de los demás módulos (design.md D3)."
    )
    contrato = contratos[NOMBRE_CONTRATO_SYNC]
    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == ["app.modules.sync"]
    forbidden = contrato["forbidden_modules"]
    for submodulo in ("models", "repository", "api", "domain"):
        assert any(f".identidad.{submodulo}" in f for f in forbidden), (
            f"El contrato de sync no prohíbe identidad.{submodulo}"
        )
        assert any(f".configuracion.{submodulo}" in f for f in forbidden), (
            f"El contrato de sync no prohíbe configuracion.{submodulo}"
        )

    assert _correr_contrato(ID_CONTRATO_SYNC) == 0


# --- Verificación en negativo (triangulación) -------------------------------


def test_contrato_commands_detecta_un_import_real_de_un_modulo() -> None:
    """Escenario negativo: si `app/commands/__init__.py` importara un
    módulo de negocio, el contrato lo detecta y falla."""
    archivo = BACKEND_DIR / "app" / "commands" / "__init__.py"
    original = archivo.read_text(encoding="utf-8")
    try:
        archivo.write_text(
            original + "\nfrom app.modules.identidad import service as _service\n",
            encoding="utf-8",
        )
        assert _correr_contrato(ID_CONTRATO_COMMANDS) == 1
    finally:
        archivo.write_text(original, encoding="utf-8")


def test_contrato_domain_detecta_un_import_real_del_bus_de_comandos() -> None:
    """Escenario negativo: si `identidad/domain/valores.py` importara
    `app.commands`, el contrato lo detecta y falla."""
    archivo = BACKEND_DIR / "app" / "modules" / "identidad" / "domain" / "valores.py"
    original = archivo.read_text(encoding="utf-8")
    try:
        archivo.write_text(
            original + "\nimport app.commands as _commands\n",
            encoding="utf-8",
        )
        assert _correr_contrato(ID_CONTRATO_DOMAIN) == 1
    finally:
        archivo.write_text(original, encoding="utf-8")


def test_contrato_sync_detecta_un_import_real_del_modelo_de_otro_modulo() -> None:
    """Escenario negativo: si `sync/__init__.py` importara
    `identidad.models` directamente (en vez de pasar por `identidad.service`),
    el contrato lo detecta y falla."""
    archivo = BACKEND_DIR / "app" / "modules" / "sync" / "__init__.py"
    original = archivo.read_text(encoding="utf-8")
    try:
        archivo.write_text(
            original + "\nfrom app.modules.identidad import models as _models\n",
            encoding="utf-8",
        )
        assert _correr_contrato(ID_CONTRATO_SYNC) == 1
    finally:
        archivo.write_text(original, encoding="utf-8")


def test_lint_imports_completo_mantiene_los_contratos_previos_en_verde() -> None:
    """Los tres contratos nuevos conviven con los tres que ya existían
    (change 02/03): la corrida completa sigue en 0 -- ningún contrato roto."""
    assert cli.lint_imports(no_cache=True) == 0
