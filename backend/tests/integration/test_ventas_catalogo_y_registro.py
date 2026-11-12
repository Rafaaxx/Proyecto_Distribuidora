"""Tarea 8.1 (change 18a): `VENTA_CONFIRMAR` está en el catálogo de tipos y en el registro de
handlers de la aplicación real, y la escritura `POST /ventas` pasa por el bus.

Reglas citadas: VTA-12, SEG-06, TR-07 y `02` §6.5 (catálogo y registro coinciden exactamente).
"""

from __future__ import annotations

# `app.main` primero: puebla el catálogo y el registro con la cadena completa de módulos.
from app.main import crear_app  # noqa: F401  # isort: skip
from app.commands import registro
from app.commands.catalogo import tipo_declarado, tipos_declarados
from app.commands.verificacion import verificar_catalogo_y_registro


def test_vta12_venta_confirmar_esta_declarada_en_los_dos_modos_con_su_permiso() -> None:
    """Tarea 11.1: `ONLINE` y `OFFLINE`, con `VENDER` como permiso offline."""
    declarado = tipo_declarado("VENTA_CONFIRMAR")

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, True)
    assert declarado.permisos == ("VENDER",)


def test_vta12_venta_confirmar_tiene_su_handler_v1_y_el_catalogo_coincide_con_el_registro() -> None:
    """Un tipo declarado sin handler, o un handler sin declarar, impide arrancar (`02` §6.5)."""
    assert "VENTA_CONFIRMAR" in tipos_declarados()
    assert registro.resolver_handler("VENTA_CONFIRMAR", 1).tipo == "VENTA_CONFIRMAR"

    verificar_catalogo_y_registro()
