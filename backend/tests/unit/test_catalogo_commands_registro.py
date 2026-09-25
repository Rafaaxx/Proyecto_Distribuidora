"""Change 05, tarea 8.2 (primera mitad): `verificar_catalogo_y_registro`
sigue en verde con los nueve tipos nuevos de `catalogo`, y los nueve
declaran `admite_offline=False` (D3: nunca llegan por el lote `OFFLINE`,
consistente con que sus handlers exigen `sesion`/`reloj` obligatorios)."""

from __future__ import annotations

import pytest

from app.commands import catalogo as catalogo_bus
from app.commands.verificacion import verificar_catalogo_y_registro
from app.modules.catalogo import commands as catalogo_commands  # noqa: F401
from app.modules.identidad import commands as identidad_commands  # noqa: F401

TIPOS_CATALOGO = (
    "CATEGORIA_CREAR",
    "CATEGORIA_MODIFICAR",
    "MARCA_CREAR",
    "MARCA_MODIFICAR",
    "PRODUCTO_CREAR",
    "PRODUCTO_MODIFICAR",
    "PRESENTACION_AGREGAR",
    "PRESENTACION_MODIFICAR",
    "PRESENTACION_REFERENCIA_CAMBIAR",
)


def test_verificar_catalogo_y_registro_en_verde_con_los_nueve_tipos_nuevos() -> None:
    """Importar `catalogo.commands` (arriba) puebla el catálogo y el
    registro con los nueve tipos; junto con `identidad.commands` (ya
    importado en producción), la verificación de arranque no debe
    lanzar."""
    verificar_catalogo_y_registro()  # No debe lanzar.


def test_los_nueve_tipos_de_catalogo_son_online_y_no_admiten_offline() -> None:
    """D3: los nueve tipos son `admite_offline=False` -- nunca llegan por
    el lote `OFFLINE` (`test_bus_lote_sincronizacion.py` ya prueba, de
    forma genérica y exhaustiva contra el mecanismo, que cualquier tipo
    declarado así se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO`; acá se
    confirma que la declaración de catálogo de cada tipo es la esperada)."""
    for tipo in TIPOS_CATALOGO:
        declarado = catalogo_bus.tipo_declarado(tipo)
        assert declarado is not None, f"{tipo} no está declarado en el catálogo de comandos."
        assert declarado.admite_online is True
        assert declarado.admite_offline is False


def test_producto_crear_y_modificar_solo_tienen_handler_en_version_2() -> None:
    """Change 06, tarea 9.2 (`design.md` D6 del 06): v1 se retira -- un
    envío v1 recibe `VersionDeComandoSinHandlerError` (SYN-06, `02` §6.6),
    distinto de `TipoDeComandoDesconocidoError` porque el TIPO existe (con
    handler en v2), solo la versión 1 no tiene handler."""
    from app.commands import registro as registro_bus
    from app.commands.errores import VersionDeComandoSinHandlerError

    for tipo in ("PRODUCTO_CREAR", "PRODUCTO_MODIFICAR"):
        with pytest.raises(VersionDeComandoSinHandlerError):
            registro_bus.resolver_handler(tipo, 1)
        handler_v2 = registro_bus.resolver_handler(tipo, 2)
        assert handler_v2.version == 2
