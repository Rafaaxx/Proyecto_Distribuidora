"""Change 18a, tarea 2.1: motor de cálculo de la venta, más allá de los casos compartidos
(spec `ventas/calculo-de-venta`; VTA-04, PRC-22, DSC-05, INV-14, INV-03, TR-03; `design.md`
D13 y D14). Los casos de totales viven en `shared/fixtures/calculo/vta-04-totales.json`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.errores import (
    DescuentoManualInvalidoError,
    LineaDescuentoInvalidaError,
)
from app.modules.ventas.domain import calculo
from app.modules.ventas.domain.calculo import LineaCalculo, calcular_venta
from app.modules.ventas.domain.errores import (
    ModoImpositivoNoSoportadoError,
    VentaSinLineasError,
)


def _linea(
    id: str = "l-1",
    *,
    precio: Any = "12500.00",
    unidades_referencia: int = 6,
    cantidad_base: int = 15,
    alicuota: Any = "0.210000",
    manual: Any = None,
) -> LineaCalculo:
    return LineaCalculo(
        id=id,
        precio_referencia=Decimal(precio) if isinstance(precio, str) else precio,
        unidades_referencia=unidades_referencia,
        cantidad_base=cantidad_base,
        alicuota=Decimal(alicuota) if isinstance(alicuota, str) else alicuota,
        producto_id=f"prod-{id}",
        categoria_id="cat",
        marca_id="marca",
        descuento_manual=manual,
    )


# --- modo impositivo (D13) ---------------------------------------------------


@pytest.mark.parametrize("modo", ["B", "C", "Z", "a", ""])
def test_solo_el_modo_a_esta_soportado(modo: str) -> None:
    with pytest.raises(ModoImpositivoNoSoportadoError) as error:
        calcular_venta(modo, [_linea()], [], None)

    assert error.value.codigo == "MODO_IMPOSITIVO_NO_SOPORTADO"
    assert error.value.status_http == 409


def test_el_modo_a_devuelve_iva_cero_y_conserva_la_alicuota_de_cada_linea() -> None:
    resultado = calcular_venta(
        "A",
        [_linea("l-1", alicuota="0.210000"), _linea("l-2", alicuota="0.105000")],
        [],
        None,
    )

    assert [linea.alicuota for linea in resultado.lineas] == [
        Decimal("0.210000"),
        Decimal("0.105000"),
    ]
    assert [linea.importe_iva for linea in resultado.lineas] == [Decimal("0.00")] * 2
    assert resultado.modo_impositivo == "A"
    assert resultado.total_iva == Decimal("0.00")


# --- cero líneas (VTA-02, INV-07) ----------------------------------------------


@pytest.mark.parametrize("lineas", [[], ()])
def test_cero_lineas_no_llega_al_motor_de_descuentos(
    lineas: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_debe_llamarse(*_: Any, **__: Any) -> None:
        raise AssertionError("el motor de descuentos no debe recibir una venta sin líneas")

    monkeypatch.setattr(calculo, "calcular_descuentos", _no_debe_llamarse)

    with pytest.raises(VentaSinLineasError) as error:
        calcular_venta("A", lineas, [], None)

    assert error.value.codigo == "VENTA_SIN_LINEAS"
    assert error.value.status_http == 422


# --- descuentos que dejan el neto en cero ------------------------------------


def test_un_descuento_manual_del_cien_por_ciento_deja_neto_e_iva_en_cero() -> None:
    resultado = calcular_venta("A", [_linea(manual=Decimal("1.000000"))], [], None)

    linea = resultado.lineas[0]
    assert (linea.bruto, linea.descuento_total, linea.neto) == (
        Decimal("31250.00"),
        Decimal("31250.00"),
        Decimal("0.00"),
    )
    assert (resultado.total_neto, resultado.total_iva, resultado.total) == (Decimal("0.00"),) * 3


def test_un_descuento_manual_general_alcanza_a_todas_las_lineas_y_el_total_cierra() -> None:
    resultado = calcular_venta(
        "A",
        [_linea("l-1", cantidad_base=12), _linea("l-2", cantidad_base=3)],
        [],
        Decimal("0.100000"),
    )

    assert [linea.neto for linea in resultado.lineas] == [Decimal("22500.00"), Decimal("5625.00")]
    assert resultado.total_neto == Decimal("28125.00")
    assert resultado.total == resultado.total_neto + resultado.total_iva


def test_el_descuento_manual_propio_reemplaza_al_general_por_linea() -> None:
    resultado = calcular_venta(
        "A",
        [
            _linea("l-1", cantidad_base=12, manual=Decimal("0.500000")),
            _linea("l-2", cantidad_base=3),
        ],
        [],
        Decimal("0.100000"),
    )

    assert [linea.neto for linea in resultado.lineas] == [Decimal("12500.00"), Decimal("5625.00")]
    assert resultado.total == Decimal("18125.00")


# --- orden y entradas inválidas (INV-03, INV-04) -------------------------------


def test_las_lineas_salen_en_el_orden_en_que_entran() -> None:
    resultado = calcular_venta(
        "A", [_linea("z-ultima"), _linea("a-primera", cantidad_base=6)], [], None
    )

    assert [linea.id for linea in resultado.lineas] == ["z-ultima", "a-primera"]


@pytest.mark.parametrize("precio", [12500.0, 12500])
def test_un_precio_de_punto_flotante_o_entero_se_rechaza(precio: Any) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_venta("A", [_linea(precio=precio)], [], None)


@pytest.mark.parametrize("alicuota", [0.21, 21, None, True])
def test_una_alicuota_que_no_es_decimal_exacto_se_rechaza(alicuota: Any) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_venta("A", [_linea(alicuota=alicuota)], [], None)


def test_un_error_del_motor_de_descuentos_se_propaga_sin_resultado_parcial() -> None:
    with pytest.raises(DescuentoManualInvalidoError):
        calcular_venta("A", [_linea("l-1"), _linea("l-2", manual=Decimal("1.5"))], [], None)


def test_una_cantidad_que_no_es_positiva_se_rechaza_con_el_codigo_de_precios() -> None:
    with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
        calcular_venta("A", [_linea(cantidad_base=0)], [], None)

    assert getattr(error.value, "codigo", None) == "CANTIDAD_BASE_INVALIDA"


def test_un_precio_negativo_no_produce_un_neto_negativo() -> None:
    with pytest.raises(LineaDescuentoInvalidaError):
        calcular_venta("A", [_linea(precio="-1.00")], [], None)
