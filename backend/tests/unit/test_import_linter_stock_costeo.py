"""Tarea 2.2 (`design.md` D9, `02` §5.3): contratos de import-linter de `stock` y
`costeo`.

- Sus `domain/` no importan infraestructura ni el bus de comandos.
- `costeo` no importa ningún otro módulo de negocio y de `identidad` solo alcanza
  su `service.py` (CST-14: es el único lugar que calcula costos).
- `stock` alcanza a `catalogo` y a `costeo` solo por su `service.py`, y de
  `identidad` solo por su `service.py`; ningún otro módulo de negocio.
- Los demás módulos alcanzan a `stock` y `costeo` solo por su `service.py`.

Cada contrato se prueba declarado, en verde y, en negativo, detectando un import
real que lo viola (mismo criterio que `test_import_linter_cuentas_corrientes.py`).
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

ID_COSTEO_DOMAIN = "costeo-domain-no-infraestructura"
ID_STOCK_DOMAIN = "stock-domain-no-infraestructura"
ID_COSTEO_AJENO = "costeo-solo-por-service-ajeno"
ID_STOCK_AJENO = "stock-solo-por-service-ajeno"
ID_HACIA_STOCK_Y_COSTEO = "modulos-hacia-stock-y-costeo-solo-por-service"
ID_DOMAIN_SIN_BUS = "domain-no-commands"
ID_CATALOGO_AJENO = "catalogo-solo-por-service-ajeno"


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


@pytest.mark.parametrize(
    ("contrato_id", "modulo"), [(ID_COSTEO_DOMAIN, "costeo"), (ID_STOCK_DOMAIN, "stock")]
)
def test_el_dominio_es_puro_declarado_y_en_verde(contrato_id: str, modulo: str) -> None:
    contrato = _contratos_por_id()[contrato_id]

    assert contrato["type"] == "forbidden"
    assert contrato["source_modules"] == [f"app.modules.{modulo}.domain"]
    assert {"fastapi", "sqlalchemy", "app.commands"} <= set(contrato["forbidden_modules"])
    assert _correr(contrato_id) == 0


def test_los_dominios_estan_en_el_contrato_del_bus() -> None:
    contrato = _contratos_por_id()[ID_DOMAIN_SIN_BUS]

    assert {"app.modules.stock.domain", "app.modules.costeo.domain"} <= set(
        contrato["source_modules"]
    )
    assert _correr(ID_DOMAIN_SIN_BUS) == 0


def test_costeo_no_depende_de_ningun_modulo_de_negocio_declarado_y_en_verde() -> None:
    """CST-14, `02` §5.3: `costeo` sin dependencias de negocio."""
    contrato = _contratos_por_id()[ID_COSTEO_AJENO]

    assert contrato["source_modules"] == ["app.modules.costeo"]
    prohibidos = set(contrato["forbidden_modules"])
    assert {
        "app.modules.stock",
        "app.modules.catalogo",
        "app.modules.proveedores",
        "app.modules.clientes",
        "app.modules.cuentas_corrientes",
        "app.modules.configuracion",
        "app.modules.sync",
        "app.modules.identidad.models",
        "app.modules.identidad.repository",
        "app.modules.identidad.api",
        "app.modules.identidad.domain",
    } <= prohibidos
    # `identidad.service` NO está prohibido: es el único alcance permitido.
    assert "app.modules.identidad.service" not in prohibidos
    assert "app.modules.identidad" not in prohibidos
    assert _correr(ID_COSTEO_AJENO) == 0


def test_stock_alcanza_a_catalogo_y_costeo_solo_por_service_declarado_y_en_verde() -> None:
    """`02` §5.3: `stock -> catalogo, costeo`."""
    contrato = _contratos_por_id()[ID_STOCK_AJENO]

    assert contrato["source_modules"] == ["app.modules.stock"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in ("catalogo", "costeo"):
        for interno in ("models", "repository", "domain"):
            assert f"app.modules.{modulo}.{interno}" in prohibidos, f"stock importa {modulo}"
        assert f"app.modules.{modulo}.service" not in prohibidos
        assert f"app.modules.{modulo}" not in prohibidos
    assert {
        "app.modules.proveedores",
        "app.modules.clientes",
        "app.modules.cuentas_corrientes",
        "app.modules.configuracion",
        "app.modules.identidad.models",
        "app.modules.identidad.repository",
    } <= prohibidos
    assert "app.modules.identidad.service" not in prohibidos
    assert _correr(ID_STOCK_AJENO) == 0


def test_los_demas_modulos_alcanzan_a_stock_y_costeo_solo_por_service_declarado() -> None:
    contrato = _contratos_por_id()[ID_HACIA_STOCK_Y_COSTEO]

    assert {
        "app.modules.identidad",
        "app.modules.configuracion",
        "app.modules.catalogo",
        "app.modules.proveedores",
        "app.modules.clientes",
        "app.modules.cuentas_corrientes",
        "app.modules.sync",
    } <= set(contrato["source_modules"])
    assert "app.modules.stock" not in contrato["source_modules"]
    assert "app.modules.costeo" not in contrato["source_modules"]
    prohibidos = set(contrato["forbidden_modules"])
    for modulo in ("stock", "costeo"):
        for interno in ("models", "repository", "domain"):
            assert f"app.modules.{modulo}.{interno}" in prohibidos
        assert f"app.modules.{modulo}.service" not in prohibidos
    # Los comandos de `stock` (grupo 6) tampoco se alcanzan desde otro modulo.
    assert {"app.modules.stock.commands", "app.modules.stock.api"} <= prohibidos
    assert _correr(ID_HACIA_STOCK_Y_COSTEO) == 0


# --- en negativo -----------------------------------------------------------


@pytest.mark.parametrize(
    ("contrato_id", "archivo"),
    [
        (ID_COSTEO_DOMAIN, "costeo/domain/costo_promedio.py"),
        (ID_STOCK_DOMAIN, "stock/domain/movimientos.py"),
    ],
)
def test_el_dominio_detecta_un_import_de_sqlalchemy_y_del_bus(
    contrato_id: str, archivo: str
) -> None:
    ruta = MODULOS_DIR / archivo

    assert _con_import_agregado(ruta, "import sqlalchemy as _sa", contrato_id) == 1
    assert _con_import_agregado(ruta, "import app.commands as _bus", contrato_id) == 1
    assert _con_import_agregado(ruta, "import app.commands as _bus", ID_DOMAIN_SIN_BUS) == 1


def test_costeo_detecta_un_import_de_stock() -> None:
    archivo = MODULOS_DIR / "costeo" / "domain" / "errores.py"

    assert (
        _con_import_agregado(archivo, "from app.modules.stock import models as _m", ID_COSTEO_AJENO)
        == 1
    )


def test_costeo_detecta_un_import_de_los_modelos_de_identidad() -> None:
    archivo = MODULOS_DIR / "costeo" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.identidad import models as _m", ID_COSTEO_AJENO
        )
        == 1
    )


def test_stock_detecta_un_import_de_los_modelos_de_catalogo_y_de_costeo() -> None:
    archivo = MODULOS_DIR / "stock" / "__init__.py"

    for linea in (
        "from app.modules.catalogo import models as _m",
        "from app.modules.costeo import models as _m",
        "from app.modules.costeo.domain import costo_promedio as _c",
    ):
        assert _con_import_agregado(archivo, linea, ID_STOCK_AJENO) == 1, linea


def test_stock_api_es_la_unica_que_alcanza_al_bus_por_sync_service() -> None:
    """`stock.api -> sync.service` (`procesar_comando`) es la excepción declarada;
    el resto de `stock` no alcanza a `sync`."""
    contrato = _contratos_por_id()[ID_STOCK_AJENO]

    assert contrato["ignore_imports"] == ["app.modules.stock.api -> app.modules.sync.service"]
    assert "app.modules.sync" in contrato["forbidden_modules"]
    assert (
        _con_import_agregado(
            MODULOS_DIR / "stock" / "service.py",
            "from app.modules.sync import service as _s",
            ID_STOCK_AJENO,
        )
        == 1
    )


def test_stock_detecta_un_import_de_cuentas_corrientes() -> None:
    archivo = MODULOS_DIR / "stock" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.cuentas_corrientes import service as _s", ID_STOCK_AJENO
        )
        == 1
    )


@pytest.mark.parametrize("modulo", ["proveedores", "clientes", "catalogo", "cuentas_corrientes"])
def test_otro_modulo_detecta_un_import_de_los_modelos_de_stock_y_de_costeo(modulo: str) -> None:
    archivo = MODULOS_DIR / modulo / "__init__.py"

    for linea in (
        "from app.modules.stock import models as _m",
        "from app.modules.stock import commands as _c",
        "from app.modules.stock import api as _a",
        "from app.modules.costeo import models as _m",
    ):
        assert _con_import_agregado(archivo, linea, ID_HACIA_STOCK_Y_COSTEO) == 1, (modulo, linea)


def test_los_caminos_permitidos_no_se_bloquean() -> None:
    """`stock -> costeo.service` y `proveedores -> stock.service` son legítimos
    (`02` §5.3): la verificación en negativo de arriba no bloquea el camino
    correcto."""
    costeo_service = MODULOS_DIR / "costeo" / "service.py"
    stock_service = MODULOS_DIR / "stock" / "service.py"
    creados = [p for p in (costeo_service, stock_service) if not p.exists()]
    for ruta in creados:
        ruta.write_text("", encoding="utf-8")
    try:
        assert (
            _con_import_agregado(
                MODULOS_DIR / "stock" / "__init__.py",
                "from app.modules.costeo import service as _s",
                ID_STOCK_AJENO,
            )
            == 0
        )
        assert (
            _con_import_agregado(
                MODULOS_DIR / "proveedores" / "__init__.py",
                "from app.modules.stock import service as _s",
                ID_HACIA_STOCK_Y_COSTEO,
            )
            == 0
        )
    finally:
        for ruta in creados:
            ruta.unlink()


# --- catalogo -> costeo (enmienda a D3 del 2026-09-30) ------------------------


def test_catalogo_alcanza_a_costeo_solo_por_service_y_no_alcanza_a_stock() -> None:
    """`GET /catalogo/productos/{id}/costo` vive en `catalogo/api.py` y consulta a
    `costeo/service.py`: es la dependencia `catalogo -> costeo` aprobada. `costeo`
    nunca importa `catalogo` y `catalogo` no importa `stock` (`stock -> catalogo`
    ya existe: un ciclo sería un error)."""
    contrato = _contratos_por_id()[ID_CATALOGO_AJENO]

    assert "app.modules.stock" in contrato["forbidden_modules"]
    assert "app.modules.costeo" not in contrato["forbidden_modules"]
    assert _correr(ID_CATALOGO_AJENO) == 0
    archivo = MODULOS_DIR / "catalogo" / "__init__.py"
    assert (
        _con_import_agregado(
            archivo, "from app.modules.stock import service as _s", ID_CATALOGO_AJENO
        )
        == 1
    )
    assert (
        _con_import_agregado(
            archivo, "from app.modules.costeo import models as _m", ID_HACIA_STOCK_Y_COSTEO
        )
        == 1
    )
    assert (
        _con_import_agregado(
            archivo, "from app.modules.costeo import service as _s", ID_HACIA_STOCK_Y_COSTEO
        )
        == 0
    )


def test_costeo_sigue_sin_importar_catalogo() -> None:
    archivo = MODULOS_DIR / "costeo" / "__init__.py"

    assert (
        _con_import_agregado(
            archivo, "from app.modules.catalogo import service as _s", ID_COSTEO_AJENO
        )
        == 1
    )
