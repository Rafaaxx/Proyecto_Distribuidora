"""Tarea 5.4 (change 18a; spec `ventas/composicion-de-venta`, requisito del momento;
`design.md` D9): el `occurred_at` de una venta con conexión está cerca del reloj del servidor.

Reglas citadas: PRC-20, TR-05.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.ventas.domain.errores import MomentoFueraDeRangoError
from app.modules.ventas.domain.momento import MARGEN_POR_DEFECTO_SEGUNDOS, validar_momento

AHORA = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)


def test_prc20_el_margen_por_defecto_es_de_300_segundos() -> None:
    assert MARGEN_POR_DEFECTO_SEGUNDOS == 300


@pytest.mark.parametrize("segundos", [0, 120, -120, 300, -300])
def test_prc20_dentro_del_margen_por_defecto_se_acepta(segundos: int) -> None:
    """Dos minutos antes (ejemplo de la spec) y justo en el borde de 300 s."""
    validar_momento(AHORA + timedelta(seconds=segundos), AHORA, None, offline=False)


@pytest.mark.parametrize("segundos", [301, -301, -86400, 86400])
def test_prc20_fuera_del_margen_por_defecto_se_rechaza(segundos: int) -> None:
    """Reloj atrasado un día (ejemplo de la spec) o adelantado."""
    with pytest.raises(MomentoFueraDeRangoError) as error:
        validar_momento(AHORA + timedelta(seconds=segundos), AHORA, None, offline=False)
    assert error.value.codigo == "MOMENTO_FUERA_DE_RANGO"
    assert error.value.status_http == 422


def test_prc20_la_configuracion_de_la_organizacion_reemplaza_al_margen_por_defecto() -> None:
    validar_momento(AHORA - timedelta(seconds=600), AHORA, 900, offline=False)
    with pytest.raises(MomentoFueraDeRangoError):
        validar_momento(AHORA - timedelta(seconds=61), AHORA, 60, offline=False)


def test_prc20_la_configuracion_en_cero_exige_el_mismo_instante() -> None:
    """Un margen configurado en 0 es un valor definido (no nulo): no cae al de 300 s."""
    validar_momento(AHORA, AHORA, 0, offline=False)
    with pytest.raises(MomentoFueraDeRangoError):
        validar_momento(AHORA - timedelta(seconds=1), AHORA, 0, offline=False)


def test_tr05_el_detalle_informa_el_margen_aplicado() -> None:
    with pytest.raises(MomentoFueraDeRangoError) as error:
        validar_momento(AHORA - timedelta(days=1), AHORA, None, offline=False)
    assert error.value.extension == {"margen_segundos": 300}


@pytest.mark.parametrize("dias", [-1, 1, -30])
def test_tr05_sin_conexion_el_momento_no_se_valida(dias: int) -> None:
    validar_momento(AHORA + timedelta(days=dias), AHORA, None, offline=True)
