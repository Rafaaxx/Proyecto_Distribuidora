"""Importadores por tipo (`design.md` D10): adaptadores finos sobre los `service.py`
de los demás módulos. `IMPORTADORES` es el registro de los tipos que ya tienen
importador; un tipo que no figura (`PRECIOS` hasta el change 13, y los que aún no se
implementaron) lo rechaza la API con `TIPO_IMPORTACION_INVALIDO`."""

from __future__ import annotations

from app.modules.importacion.importadores.base import Importador
from app.modules.importacion.importadores.clientes import importar_clientes
from app.modules.importacion.importadores.costos import importar_costos
from app.modules.importacion.importadores.productos import importar_productos
from app.modules.importacion.importadores.proveedores import importar_proveedores
from app.modules.importacion.importadores.saldos_iniciales import importar_saldos_iniciales
from app.modules.importacion.importadores.stock_inicial import importar_stock_inicial

IMPORTADORES: dict[str, Importador] = {
    "PROVEEDORES": importar_proveedores,
    "PRODUCTOS": importar_productos,
    "CLIENTES": importar_clientes,
    "COSTOS": importar_costos,
    "STOCK_INICIAL": importar_stock_inicial,
    "SALDOS_INICIALES": importar_saldos_iniciales,
}
