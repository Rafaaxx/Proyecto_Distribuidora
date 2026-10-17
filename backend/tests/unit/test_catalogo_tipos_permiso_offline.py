"""Change 17, tarea 12.1 (`design.md` D10; spec `sistema/pipeline-de-comandos`, requisito "Un
permiso faltante rechaza el comando en modo ONLINE", escenario "Todo tipo offline declara su
permiso"): todo tipo de comando que admite `OFFLINE` declara el permiso que exige, y la
aplicación se niega a arrancar (falla al declararlo, en la importación) si alguno no lo declara.

Los tipos solo `ONLINE` no se tocan: no declaran permiso.

Reglas citadas: SEG-06, SYN-10, `02` §6.3 paso 4.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401  (importar `app.main` puebla el catálogo real, igual que el arranque)
from app.commands import catalogo
from app.commands.catalogo import (
    TipoOfflineSinPermisoError,
    declarar_tipo,
    tipo_declarado,
)

_CATALOGO_REAL = dict(catalogo._CATALOGO)
"""Copia del catálogo que pueblan los módulos de negocio al importar `app.main`, tomada antes de
que las pruebas lo aíslen."""


@pytest.fixture(autouse=True)
def _catalogo_aislado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})


def test_un_tipo_offline_sin_permiso_declarado_falla_al_declararlo() -> None:
    """SEG-06: el arranque falla antes de aceptar un solo comando."""
    with pytest.raises(TipoOfflineSinPermisoError, match="VENTA_CONFIRMAR"):
        declarar_tipo("VENTA_CONFIRMAR", admite_online=True, admite_offline=True)

    assert tipo_declarado("VENTA_CONFIRMAR") is None


def test_un_tipo_offline_con_permiso_vacio_tambien_falla() -> None:
    """Triangulación: un permiso en blanco no es un permiso."""
    with pytest.raises(TipoOfflineSinPermisoError):
        declarar_tipo("VENTA_ANULAR", admite_online=True, admite_offline=True, permiso_offline="  ")


def test_un_tipo_offline_con_permiso_queda_declarado_con_el_permiso() -> None:
    declarado = declarar_tipo(
        "COBRANZA_REGISTRAR",
        admite_online=True,
        admite_offline=True,
        permiso_offline="REGISTRAR_COBRANZA",
    )

    assert declarado.permiso_offline == "REGISTRAR_COBRANZA"
    assert tipo_declarado("COBRANZA_REGISTRAR") == declarado


def test_un_tipo_solo_online_no_declara_permiso_y_se_declara_igual() -> None:
    declarado = declarar_tipo("COBRANZA_ANULAR", admite_online=True, admite_offline=False)

    assert declarado.permiso_offline is None


def test_un_tipo_solo_online_que_declara_permiso_offline_es_un_error() -> None:
    """Un permiso `offline` en un tipo que no admite `OFFLINE` es un olvido: se detecta."""
    with pytest.raises(TipoOfflineSinPermisoError, match="no admite OFFLINE"):
        declarar_tipo(
            "COBRANZA_ANULAR",
            admite_online=True,
            admite_offline=False,
            permiso_offline="ANULAR_COBRANZA",
        )


def test_todos_los_tipos_del_catalogo_real_que_admiten_offline_declaran_su_permiso() -> None:
    """Escenario "Todo tipo offline declara su permiso": se recorre el catálogo que cargan los
    módulos de negocio al arrancar la aplicación."""
    reales = _CATALOGO_REAL
    assert reales, "el catálogo real no se pobló al importar los módulos de negocio"
    offline = [t for t in reales.values() if t.admite_offline]
    assert offline, "se esperaba al menos un tipo OFFLINE (COBRANZA_REGISTRAR)"
    assert all(t.permiso_offline for t in offline)
