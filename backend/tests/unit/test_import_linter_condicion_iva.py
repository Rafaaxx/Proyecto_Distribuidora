"""Change 11b, tarea 9.1 (`design.md` D1, `02` §5.3): `proveedores` e `importacion` leen la
condición frente al IVA de la organización SOLO por `identidad/service.py`
(`obtener_condicion_iva` / `organizacion_computa_credito_fiscal`), nunca por el modelo
`ConfiguracionOrganizacion` ni por el repositorio de `identidad`.

Los contratos ya existen (`proveedores-solo-por-service-ajeno` e
`importacion-solo-por-service-ajeno`); esta prueba los ata a la lectura de la condición:
declarados con los internos de `identidad` prohibidos, en verde con el código real y, en
negativo, detectando el import del modelo y del repositorio que leerían la condición por fuera
del servicio. Mismo criterio que `test_import_linter_importacion.py`.
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

ID_PROVEEDORES = "proveedores-solo-por-service-ajeno"
ID_IMPORTACION = "importacion-solo-por-service-ajeno"
CONTRATOS_POR_MODULO = {"proveedores": ID_PROVEEDORES, "importacion": ID_IMPORTACION}
INTERNOS_DE_IDENTIDAD = (
    "app.modules.identidad.models",
    "app.modules.identidad.repository",
)
# Lo que leería la condición por fuera de `identidad.service`.
LECTURAS_PROHIBIDAS = (
    "from app.modules.identidad.models import ConfiguracionOrganizacion as _c",
    "from app.modules.identidad.repository import obtener_configuracion as _o",
    "from app.modules.identidad.repository import obtener_configuracion_bloqueada as _b",
)


def _contratos_por_id() -> dict[str, dict[str, Any]]:
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {c["id"]: c for c in datos["tool"]["importlinter"]["contracts"] if "id" in c}


def _correr(contrato_id: str) -> int:
    return cli.lint_imports(limit_to_contracts=(contrato_id,), no_cache=True)


def _con_import_agregado(archivo: Path, linea: str, contrato_id: str) -> int:
    """Corre `contrato_id` con `linea` agregada al final de `archivo` y deja el archivo como
    estaba. Exige que el contrato esté declarado: un identificador desconocido también
    devuelve 1 y haría pasar en falso la prueba en negativo."""
    assert contrato_id in _contratos_por_id(), f"contrato no declarado: {contrato_id}"
    original = archivo.read_bytes()  # bytes: conserva los finales de línea
    try:
        archivo.write_bytes(original + f"\n{linea}\n".encode())
        return _correr(contrato_id)
    finally:
        archivo.write_bytes(original)


@pytest.mark.parametrize("modulo", CONTRATOS_POR_MODULO)
def test_el_contrato_de_cada_modulo_prohibe_los_internos_de_identidad_y_esta_en_verde(
    modulo: str,
) -> None:
    contrato_id = CONTRATOS_POR_MODULO[modulo]
    contrato = _contratos_por_id()[contrato_id]

    assert contrato["source_modules"] == [f"app.modules.{modulo}"]
    assert set(INTERNOS_DE_IDENTIDAD) <= set(contrato["forbidden_modules"])
    assert "app.modules.identidad.service" not in contrato["forbidden_modules"]
    assert _correr(contrato_id) == 0


@pytest.mark.parametrize("modulo", CONTRATOS_POR_MODULO)
def test_leer_la_condicion_por_el_modelo_o_el_repositorio_de_identidad_se_detecta(
    modulo: str,
) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    for linea in LECTURAS_PROHIBIDAS:
        assert _con_import_agregado(archivo, linea, CONTRATOS_POR_MODULO[modulo]) == 1, linea


@pytest.mark.parametrize("modulo", CONTRATOS_POR_MODULO)
def test_leer_la_condicion_por_el_service_de_identidad_no_se_bloquea(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"
    linea = "from app.modules.identidad import service as _identidad_service"

    assert _con_import_agregado(archivo, linea, CONTRATOS_POR_MODULO[modulo]) == 0


@pytest.mark.parametrize("modulo", CONTRATOS_POR_MODULO)
def test_el_codigo_real_lee_la_condicion_solo_por_el_service(modulo: str) -> None:
    """Hay al menos una lectura real por `identidad_service` y ninguna referencia al
    modelo ni a las lecturas del repositorio de `identidad`."""
    fuentes = [
        p.read_text(encoding="utf-8")
        for p in (MODULOS_DIR / modulo).rglob("*.py")
        if "__pycache__" not in p.parts
    ]

    assert any("identidad_service.organizacion_computa_credito_fiscal(" in f for f in fuentes)
    for fuente in fuentes:
        assert "ConfiguracionOrganizacion" not in fuente
        assert "identidad.repository" not in fuente
        assert "identidad import repository" not in fuente
