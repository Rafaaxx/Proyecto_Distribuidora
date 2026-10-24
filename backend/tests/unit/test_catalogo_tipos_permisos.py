"""Change 18b, tarea 22.2 (`design.md` D23, ADR-056; antes change 17, D10): todo tipo de comando
declara el permiso (o los permisos, alcanza con cualquiera) que exige, para CUALQUIER modo. Sin
`permisos` (ni la salida justificada `sin_permiso`) la declaración falla al importar: la
aplicación no arranca. El rename `permiso_offline` -> `permisos` generaliza el paso 4 de `02` §6.3.

Reglas citadas: SEG-06, SYN-10, ADR-056, `02` §6.3 paso 4.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401  (importar `app.main` puebla el catálogo real, igual que el arranque)
from app.commands import catalogo
from app.commands.catalogo import (
    TipoSinPermisosError,
    declarar_tipo,
    tipo_declarado,
)

_CATALOGO_REAL = dict(catalogo._CATALOGO)
"""Copia del catálogo que pueblan los módulos de negocio al importar `app.main`, tomada antes de
que las pruebas lo aíslen."""


@pytest.fixture(autouse=True)
def _catalogo_aislado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})


def test_un_tipo_sin_permisos_falla_al_declararlo_en_cualquier_modo() -> None:
    """SEG-06, ADR-056: el arranque falla antes de aceptar un solo comando."""
    with pytest.raises(TipoSinPermisosError, match="VENTA_CONFIRMAR"):
        declarar_tipo("VENTA_CONFIRMAR", admite_online=True, admite_offline=True)
    with pytest.raises(TipoSinPermisosError, match="COBRANZA_ANULAR"):
        declarar_tipo("COBRANZA_ANULAR", admite_online=True, admite_offline=False)

    assert tipo_declarado("VENTA_CONFIRMAR") is None
    assert tipo_declarado("COBRANZA_ANULAR") is None


def test_una_tupla_vacia_o_con_un_permiso_en_blanco_tambien_falla() -> None:
    """Triangulación: un permiso en blanco no es un permiso."""
    with pytest.raises(TipoSinPermisosError):
        declarar_tipo("VENTA_ANULAR", admite_online=True, admite_offline=True, permisos=())
    with pytest.raises(TipoSinPermisosError):
        declarar_tipo("VENTA_ANULAR", admite_online=True, admite_offline=True, permisos=("  ",))


def test_un_tipo_con_permisos_queda_declarado_con_ellos_en_cualquier_modo() -> None:
    offline = declarar_tipo(
        "COBRANZA_REGISTRAR",
        admite_online=True,
        admite_offline=True,
        permisos=("REGISTRAR_COBRANZA",),
    )
    online = declarar_tipo(
        "COBRANZA_ANULAR", admite_online=True, admite_offline=False, permisos=("ANULAR_COBRANZA",)
    )

    assert offline.permisos == ("REGISTRAR_COBRANZA",)
    assert online.permisos == ("ANULAR_COBRANZA",)
    assert tipo_declarado("COBRANZA_REGISTRAR") == offline


def test_un_tipo_puede_declarar_varios_permisos_y_alcanza_con_cualquiera() -> None:
    declarado = declarar_tipo(
        "PIN_AUTORIZACION_PROPIO_DEFINIR",
        admite_online=True,
        admite_offline=False,
        permisos=("AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"),
    )

    assert declarado.permisos == ("AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO")


def test_la_unica_salida_es_sin_permiso_con_una_justificacion() -> None:
    declarado = declarar_tipo(
        "TIPO_ABIERTO",
        admite_online=True,
        admite_offline=False,
        sin_permiso="Lo puede enviar cualquier usuario autenticado (prueba).",
    )
    assert declarado.permisos == ()
    assert declarado.sin_permiso is not None

    with pytest.raises(TipoSinPermisosError):
        declarar_tipo("OTRO_ABIERTO", admite_online=True, admite_offline=False, sin_permiso="  ")
    with pytest.raises(TipoSinPermisosError, match="a la vez"):
        declarar_tipo(
            "OTRO_MAS",
            admite_online=True,
            admite_offline=False,
            permisos=("VENDER",),
            sin_permiso="no hace falta",
        )


def test_un_tipo_offline_no_puede_eximirse_del_permiso() -> None:
    """`PERMISO_REVOCADO` (SYN-10) necesita el permiso: `OFFLINE` no admite `sin_permiso`."""
    with pytest.raises(TipoSinPermisosError, match="OFFLINE"):
        declarar_tipo(
            "TIPO_OFFLINE_ABIERTO",
            admite_online=True,
            admite_offline=True,
            sin_permiso="justificación",
        )


def test_todos_los_tipos_del_catalogo_real_declaran_permisos() -> None:
    """ADR-056: se recorre el catálogo que cargan los módulos de negocio al arrancar."""
    reales = _CATALOGO_REAL
    assert reales, "el catálogo real no se pobló al importar los módulos de negocio"
    sin_permisos = [t.tipo for t in reales.values() if not t.permisos and not t.sin_permiso]
    assert sin_permisos == []
    assert all(t.permisos for t in reales.values() if t.admite_offline)


def test_venta_confirmar_declara_su_permiso_y_su_operacion_observable() -> None:
    """Change 18a, tarea 11.1 (`design.md` D1; spec `sync/lote-de-comandos`): `VENTA_CONFIRMAR`
    admite `ONLINE` y `OFFLINE`, el bus compara `VENDER` (SYN-10, INV-17) y anota sus
    observaciones sobre la venta (`VENTA` / `venta_id`)."""
    declarado = _CATALOGO_REAL["VENTA_CONFIRMAR"]

    assert declarado.admite_online is True
    assert declarado.admite_offline is True
    assert declarado.permisos == ("VENDER",)
    assert declarado.operacion_offline is not None
    assert declarado.operacion_offline.tipo == "VENTA"
    assert declarado.operacion_offline.clave_en_resultado == "venta_id"


def test_cobranza_registrar_sigue_declarando_su_operacion_observable_triangulacion() -> None:
    """Triangulación de 11.1: el precedente del change 17 no cambia."""
    declarado = _CATALOGO_REAL["COBRANZA_REGISTRAR"]

    assert declarado.permisos == ("REGISTRAR_COBRANZA",)
    assert declarado.operacion_offline is not None
    assert declarado.operacion_offline.tipo == "COBRANZA"
    assert declarado.operacion_offline.clave_en_resultado == "cobranza_id"
