"""Change 24, tarea 9.1: el destino de la devolución del remanente es una regla pura (RUT-08,
STK-09; `design.md` D6)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.stock.domain.errores import (
    UbicacionConTomaError,
    UbicacionesIgualesError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.jornadas import validar_destino_de_devolucion


def test_un_deposito_activo_y_distinto_es_un_destino_valido() -> None:
    validar_destino_de_devolucion(
        origen_id=uuid4(), destino_id=uuid4(), activa=True, requiere_toma=False
    )


@pytest.mark.parametrize(
    ("activa", "requiere_toma", "error"),
    [
        (False, False, UbicacionInactivaError),
        (True, True, UbicacionConTomaError),
    ],
)
def test_un_destino_inactivo_o_con_toma_se_rechaza(
    activa: bool, requiere_toma: bool, error: type[Exception]
) -> None:
    with pytest.raises(error):
        validar_destino_de_devolucion(
            origen_id=uuid4(), destino_id=uuid4(), activa=activa, requiere_toma=requiere_toma
        )


def test_el_mismo_vehiculo_es_ubicaciones_iguales_aunque_tenga_toma() -> None:
    """El origen es un vehículo con toma: igual se informa `UBICACIONES_IGUALES`, no la toma."""
    mismo = uuid4()

    with pytest.raises(UbicacionesIgualesError):
        validar_destino_de_devolucion(
            origen_id=mismo, destino_id=mismo, activa=True, requiere_toma=True
        )
