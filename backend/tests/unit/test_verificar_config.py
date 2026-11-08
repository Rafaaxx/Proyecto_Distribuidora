"""Verificación previa de la configuración (change 27a, paso 0; D6).

El contenedor de producción corre `python -m app.core.verificar_config` antes de
uvicorn: si la configuración está mal armada sale con código distinto de cero y
nombra la variable, nunca su valor (`02` §17).
"""

import importlib
import sys

import pytest

SECRETO_VALIDO = "s" * 32
URL = "postgresql+psycopg://u:p@localhost:5432/db"


def _entorno(monkeypatch, **vars_: str) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("JWT_SECRET", SECRETO_VALIDO)
    monkeypatch.setenv("APP_VERSION", "1.0.0")
    monkeypatch.setenv("ENVIRONMENT", "production")
    for nombre, valor in vars_.items():
        monkeypatch.setenv(nombre.upper(), valor)


def test_configuracion_valida_sale_con_cero(monkeypatch, capsys):
    from app.core.verificar_config import main

    _entorno(monkeypatch)
    assert main() == 0


def test_version_sin_forma_sale_distinto_de_cero_y_nombra_la_variable(monkeypatch, capsys):
    from app.core.verificar_config import main

    _entorno(monkeypatch, app_version="dev")
    assert main() != 0
    salida = capsys.readouterr()
    assert "APP_VERSION" in salida.err + salida.out


def test_secreto_corto_nombra_la_variable_y_no_repite_el_valor(monkeypatch, capsys):
    from app.core.verificar_config import main

    corto = "secreto-corto-unico-xyz"
    _entorno(monkeypatch, jwt_secret=corto)
    assert main() != 0
    salida = capsys.readouterr()
    texto = salida.err + salida.out
    assert "JWT_SECRET" in texto
    assert corto not in texto


def test_variable_faltante_se_nombra_en_mayusculas(monkeypatch, capsys):
    from app.core.verificar_config import main

    _entorno(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")
    assert main() != 0
    salida = capsys.readouterr()
    assert "DATABASE_URL" in salida.err + salida.out


def test_main_py_en_produccion_no_silencia_la_configuracion_invalida(monkeypatch):
    _entorno(monkeypatch, app_version="dev")
    sys.modules.pop("app.main", None)
    with pytest.raises(Exception) as excinfo:
        importlib.import_module("app.main")
    assert "APP_VERSION" in str(excinfo.value)
    sys.modules.pop("app.main", None)


def test_main_py_fuera_de_produccion_sigue_dejando_app_en_none(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.chdir("/")  # sin .env que complete la configuración
    sys.modules.pop("app.main", None)
    modulo = importlib.import_module("app.main")
    assert modulo.app is None
    sys.modules.pop("app.main", None)
