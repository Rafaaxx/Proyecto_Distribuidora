"""Change 13, tareas 5.1 y 11.1: `verificar_catalogo_y_registro` sigue en verde con los diez
tipos de comando de `precios`, y los diez declaran `admite_online=True`, `admite_offline=False`
(`02` §6.5; mismo criterio que `test_proveedores_commands_registro.py`) y tienen su handler
v1 registrado: el catalogo de comandos y el registro de handlers coinciden."""

from __future__ import annotations

from app.commands import catalogo as catalogo_bus
from app.commands import registro as registro_bus
from app.commands.verificacion import verificar_catalogo_y_registro
from app.modules.catalogo import commands as catalogo_commands  # noqa: F401
from app.modules.identidad import commands as identidad_commands  # noqa: F401
from app.modules.precios import commands as precios_commands  # noqa: F401

TIPOS_DE_PRECIOS = (
    "LISTA_PRECIO_CREAR",
    "LISTA_PRECIO_MODIFICAR",
    "REGLA_MARGEN_CREAR",
    "REGLA_MARGEN_MODIFICAR",
    "REDONDEO_CATEGORIA_DEFINIR",
    "LISTA_GENERAR_BORRADOR",
    "LISTA_BORRADOR_PRECIO_FIJAR",
    "LISTA_PUBLICAR",
    "LISTA_ANULAR_VERSION",
    "LISTA_PRECIO_PREDETERMINADA_DEFINIR",
)


def test_verificar_catalogo_y_registro_en_verde_con_los_diez_tipos_de_precios() -> None:
    verificar_catalogo_y_registro()  # No debe lanzar.


def test_los_diez_tipos_son_online_y_no_admiten_offline() -> None:
    for tipo in TIPOS_DE_PRECIOS:
        declarado = catalogo_bus.tipo_declarado(tipo)
        assert declarado is not None, f"{tipo} no está declarado en el catálogo de comandos."
        assert declarado.admite_online is True
        assert declarado.admite_offline is False


def test_los_diez_tipos_tienen_handler_registrado_en_version_1() -> None:
    for tipo in TIPOS_DE_PRECIOS:
        handler = registro_bus.resolver_handler(tipo, 1)
        assert handler.tipo == tipo
        assert handler.version == 1
