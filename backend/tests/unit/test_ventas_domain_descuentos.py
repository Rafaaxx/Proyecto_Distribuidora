"""Tarea 7.2 (change 18b; spec `ventas/descuentos-en-la-venta`, requisito "Con conexión se
confirma el descuento que vio el usuario"; `design.md` D11): comparación de los descuentos
esperados (los que vio el usuario) con los que calcula el servidor, por línea.

Reglas citadas: DSC-09, DSC-07.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.ventas.domain.descuentos import DescuentoDeLinea, comparar_descuentos
from app.modules.ventas.domain.errores import DescuentoDifiereError

LINEA_VINO = uuid4()
LINEA_CERVEZA = uuid4()
REGLA = uuid4()


def _auto(importe: str = "1562.50", porcentaje: str | None = "0.050000", regla: UUID = REGLA):
    return DescuentoDeLinea("AUTOMATICO", regla, _dec(porcentaje), Decimal(importe))


def _manual(importe: str = "100.00", porcentaje: str | None = "0.100000"):
    return DescuentoDeLinea("MANUAL", None, _dec(porcentaje), Decimal(importe))


def _dec(valor: str | None) -> Decimal | None:
    return None if valor is None else Decimal(valor)


def test_dsc09_descuentos_iguales_no_difieren() -> None:
    esperados = {LINEA_VINO: [_auto(), _manual()], LINEA_CERVEZA: []}
    calculados = {LINEA_VINO: [_auto(), _manual()], LINEA_CERVEZA: []}

    comparar_descuentos(esperados, calculados)  # no lanza


def test_dsc09_el_formato_del_decimal_no_cuenta_solo_el_valor() -> None:
    """`0.05` y `0.050000` son el mismo porcentaje; `1562.5` y `1562.50` el mismo importe."""
    esperados = {
        LINEA_VINO: [DescuentoDeLinea("AUTOMATICO", REGLA, Decimal("0.05"), Decimal("1562.5"))]
    }

    comparar_descuentos(esperados, {LINEA_VINO: [_auto()]})


def test_dsc09_una_linea_sin_descuentos_esperados_difiere_si_el_servidor_calcula() -> None:
    calculados = {LINEA_VINO: [_auto()]}

    with pytest.raises(DescuentoDifiereError) as error:
        comparar_descuentos({}, calculados)

    assert error.value.codigo == "DESCUENTO_DIFIERE"
    assert error.value.status_http == 409
    assert error.value.extension == {
        "lineas": [
            {
                "linea_id": str(LINEA_VINO),
                "descuentos": [
                    {
                        "origen": "AUTOMATICO",
                        "regla_id": str(REGLA),
                        "porcentaje": "0.050000",
                        "importe": "1562.50",
                    }
                ],
            }
        ]
    }


@pytest.mark.parametrize(
    ("esperado", "calculado"),
    [
        pytest.param(_auto("1562.49"), _auto("1562.50"), id="centavo-de-diferencia-DSC-07"),
        pytest.param(_auto(regla=uuid4()), _auto(), id="otra-regla"),
        pytest.param(_auto(porcentaje="0.060000"), _auto(), id="otro-porcentaje"),
        pytest.param(_manual(), _auto(), id="otro-origen"),
        pytest.param(_auto(porcentaje=None), _auto(), id="importe-fijo-contra-porcentaje"),
    ],
)
def test_dsc09_cualquier_campo_distinto_difiere(
    esperado: DescuentoDeLinea, calculado: DescuentoDeLinea
) -> None:
    with pytest.raises(DescuentoDifiereError):
        comparar_descuentos({LINEA_VINO: [esperado]}, {LINEA_VINO: [calculado]})


def test_dsc09_un_descuento_de_mas_o_de_menos_difiere() -> None:
    with pytest.raises(DescuentoDifiereError):
        comparar_descuentos({LINEA_VINO: [_auto(), _manual()]}, {LINEA_VINO: [_auto()]})
    with pytest.raises(DescuentoDifiereError):
        comparar_descuentos({LINEA_VINO: [_auto()]}, {LINEA_VINO: [_auto(), _manual()]})


def test_dsc09_el_orden_de_los_descuentos_de_la_linea_no_importa() -> None:
    comparar_descuentos({LINEA_VINO: [_manual(), _auto()]}, {LINEA_VINO: [_auto(), _manual()]})


def test_dsc09_el_detalle_trae_todas_las_lineas_del_servidor() -> None:
    """Triangula: con dos líneas y diferencia en una, la respuesta trae las dos con lo calculado."""
    esperados = {LINEA_VINO: [_auto("1.00")], LINEA_CERVEZA: [_manual()]}
    calculados = {LINEA_VINO: [_auto()], LINEA_CERVEZA: [_manual()]}

    with pytest.raises(DescuentoDifiereError) as error:
        comparar_descuentos(esperados, calculados)

    lineas = error.value.extension["lineas"]  # type: ignore[index]
    assert [linea["linea_id"] for linea in lineas] == [str(LINEA_VINO), str(LINEA_CERVEZA)]
    assert lineas[1]["descuentos"][0]["regla_id"] is None
