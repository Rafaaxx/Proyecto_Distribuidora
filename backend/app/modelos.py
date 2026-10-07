"""Registro único de los modelos en `Base.metadata`.

Varias tablas tienen una clave foránea compuesta hacia una tabla de OTRO módulo (por ejemplo
`cliente` y `configuracion_organizacion` hacia `lista_precio`, de `precios`; `producto`
hacia `proveedor`). SQLAlchemy resuelve la tabla destino por nombre al ordenar un `flush`
(`Base.metadata.sorted_tables`), así que todo proceso que escriba esas filas tiene que haber
importado también los modelos del otro módulo: sin esto, `python -m app.seed` o una prueba
fallan con `NoReferencedTableError` según qué módulos importaron.

Importar este módulo, por efecto secundario, registra todos los modelos. Lo importan los
puntos de entrada que no pasan por `app.main` (`app/seed.py`, el arnés de pruebas de
integración) y `alembic/env.py` conserva su propia lista explícita, la misma. Un módulo nuevo
con modelos se agrega acá, en `app/main.py` y en `alembic/env.py`.
"""

from app.modules.catalogo import models as catalogo_models  # noqa: F401
from app.modules.clientes import models as clientes_models  # noqa: F401
from app.modules.configuracion import models as configuracion_models  # noqa: F401
from app.modules.costeo import models as costeo_models  # noqa: F401
from app.modules.cuentas_corrientes import models as cuentas_corrientes_models  # noqa: F401
from app.modules.identidad import models as identidad_models  # noqa: F401
from app.modules.importacion import models as importacion_models  # noqa: F401
from app.modules.precios import models as precios_models  # noqa: F401
from app.modules.proveedores import models as proveedores_models  # noqa: F401
from app.modules.stock import models as stock_models  # noqa: F401
from app.modules.sync import models as sync_models  # noqa: F401
