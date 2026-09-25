"""Change 06, tarea 9.1: `verificar_catalogo_y_registro` sigue en verde con
los tres tipos nuevos de `proveedores`, y los tres declaran
`admite_offline=False` (mismo criterio que `test_catalogo_commands_
registro.py` del change 05, D3 del 04)."""

from __future__ import annotations

from app.commands import catalogo as catalogo_bus
from app.commands.verificacion import verificar_catalogo_y_registro
from app.modules.catalogo import commands as catalogo_commands  # noqa: F401
from app.modules.identidad import commands as identidad_commands  # noqa: F401
from app.modules.proveedores import commands as proveedores_commands  # noqa: F401

TIPOS_PROVEEDORES = (
    "PROVEEDOR_CREAR",
    "PROVEEDOR_MODIFICAR",
    "COSTO_INFORMAR",
)


def test_verificar_catalogo_y_registro_en_verde_con_los_tres_tipos_nuevos() -> None:
    """Importar `proveedores.commands` (arriba), junto con `catalogo.
    commands` e `identidad.commands` (ya importados en producción), puebla
    el catálogo y el registro con los tres tipos nuevos; la verificación de
    arranque no debe lanzar."""
    verificar_catalogo_y_registro()  # No debe lanzar.


def test_los_tres_tipos_de_proveedores_son_online_y_no_admiten_offline() -> None:
    for tipo in TIPOS_PROVEEDORES:
        declarado = catalogo_bus.tipo_declarado(tipo)
        assert declarado is not None, f"{tipo} no está declarado en el catálogo de comandos."
        assert declarado.admite_online is True
        assert declarado.admite_offline is False


def test_los_tres_tipos_tienen_handler_registrado_en_version_1() -> None:
    from app.commands import registro as registro_bus

    for tipo in TIPOS_PROVEEDORES:
        handler = registro_bus.resolver_handler(tipo, 1)
        assert handler.tipo == tipo
        assert handler.version == 1
