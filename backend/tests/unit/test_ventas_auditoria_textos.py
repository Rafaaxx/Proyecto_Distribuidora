"""Tarea 10.1 (change 18a, D20): los textos puros de la auditoría de una venta.

Reglas citadas: AUD-01, AUD-02, STK-09.
"""

from __future__ import annotations

import pytest

from app.commands.auditoria import unir_observaciones
from app.modules.ventas.domain.auditoria import observacion_de_lista


def test_otra_lista_con_version_vigente_nombra_lista_y_version() -> None:
    texto = observacion_de_lista(
        lista_nombre="Mayorista", version_numero=3, otra_lista=True, version_no_vigente=False
    )

    assert texto == (
        'Lista "Mayorista", versión 3: lista distinta de la que le corresponde al cliente'
    )


def test_version_anterior_de_la_lista_del_cliente() -> None:
    texto = observacion_de_lista(
        lista_nombre="General", version_numero=1, otra_lista=False, version_no_vigente=True
    )

    assert texto == 'Lista "General", versión 1: versión no vigente'


def test_las_dos_razones_se_unen_con_una_y() -> None:
    texto = observacion_de_lista(
        lista_nombre="Mayorista", version_numero=1, otra_lista=True, version_no_vigente=True
    )

    assert texto == (
        'Lista "Mayorista", versión 1: lista distinta de la que le corresponde al cliente '
        "y versión no vigente"
    )


def test_sin_ninguna_razon_no_hay_observacion() -> None:
    texto = observacion_de_lista(
        lista_nombre="General", version_numero=2, otra_lista=False, version_no_vigente=False
    )

    assert texto is None


@pytest.mark.parametrize(
    ("textos", "esperado"),
    [
        (("A", "B"), "A; B"),
        (("A", None), "A"),
        ((None, "B"), "B"),
        ((None, None), None),
        ((), None),
        (("A", "", "C"), "A; C"),
    ],
)
def test_unir_observaciones_separa_con_punto_y_coma_y_omite_lo_vacio(
    textos: tuple[str | None, ...], esperado: str | None
) -> None:
    assert unir_observaciones(*textos) == esperado
