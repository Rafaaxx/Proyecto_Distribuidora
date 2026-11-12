"""`sync_service.registrar_observacion`: validación del catálogo de
códigos (change 04, grupo 9, tarea 9.4, SYN-07) sin tocar la base -- la
prueba con PostgreSQL real vive en
`tests/integration/test_observaciones.py::TestCatalogoDeCodigos`.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.commands.errores import CodigoDeObservacionInvalidoError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ObservacionProducida


class TestValidacionDelCatalogo:
    def test_un_codigo_fuera_del_catalogo_no_toca_la_sesion(self) -> None:
        sesion = MagicMock()

        with pytest.raises(CodigoDeObservacionInvalidoError):
            sync_service.registrar_observacion(
                sesion,
                comando_id=uuid4(),
                organizacion_id=uuid4(),
                observacion=ObservacionProducida(
                    codigo="CODIGO_QUE_NO_EXISTE",
                    operacion_tipo="VENTA",
                    operacion_id=uuid4(),
                ),
            )

        sesion.add.assert_not_called()
        sesion.flush.assert_not_called()

    def test_un_codigo_del_catalogo_inserta_la_observacion_pendiente(self) -> None:
        sesion = MagicMock()
        comando_id = uuid4()
        organizacion_id = uuid4()
        operacion_id = uuid4()

        observacion = sync_service.registrar_observacion(
            sesion,
            comando_id=comando_id,
            organizacion_id=organizacion_id,
            observacion=ObservacionProducida(
                codigo="STOCK_NEGATIVO",
                operacion_tipo="VENTA",
                operacion_id=operacion_id,
                detalle={"cantidad_faltante": 3},
            ),
        )

        sesion.add.assert_called_once()
        sesion.flush.assert_called_once()
        agregada = sesion.add.call_args.args[0]
        assert agregada is observacion
        assert observacion.comando_id == comando_id
        assert observacion.organizacion_id == organizacion_id
        assert observacion.operacion_id == operacion_id
        assert observacion.codigo == "STOCK_NEGATIVO"
        assert observacion.estado == "PENDIENTE"
        assert observacion.detalle == {"cantidad_faltante": 3}
