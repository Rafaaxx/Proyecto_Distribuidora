"""Change 06, tarea 6.4: `validar_lote_de_costos` (`design.md` D12, CST-05).

1..200 costos, sin repetidos `(producto, presentación, vigencia)`, `valor`
`> 0` con `<= 2` decimales, bonificación en `[0, 1)` con `<= 6` decimales.
Puro: no valida existencia/actividad de proveedor/producto/presentación
(eso lo hace el servicio, tarea 8.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    CostosInvalidosError,
    ValorInvalidoError,
)
from app.modules.proveedores.domain.lote import CostoDelLote, validar_lote_de_costos

_PRODUCTO_A = uuid4()
_PRODUCTO_B = uuid4()
_PRESENTACION_A = uuid4()
_PRESENTACION_B = uuid4()
_HOY = date(2026, 9, 1)


def _costo(
    *,
    producto_id: object = _PRODUCTO_A,
    presentacion_id: object = _PRESENTACION_A,
    valor: Decimal = Decimal("18000.00"),
    bonificacion: Decimal = Decimal("0"),
    vigencia_desde: date = _HOY,
) -> CostoDelLote:
    return CostoDelLote(
        producto_id=producto_id,  # type: ignore[arg-type]
        presentacion_id=presentacion_id,  # type: ignore[arg-type]
        valor=valor,
        incluye_iva=False,
        bonificacion=bonificacion,
        vigencia_desde=vigencia_desde,
        observacion=None,
    )


def test_lote_valido_de_un_costo_no_levanta() -> None:
    validar_lote_de_costos([_costo()])


def test_lote_de_dos_costos_de_productos_distintos_es_valido() -> None:
    validar_lote_de_costos([_costo(), _costo(producto_id=_PRODUCTO_B)])


def test_lote_vacio_es_costos_invalidos() -> None:
    with pytest.raises(CostosInvalidosError):
        validar_lote_de_costos([])


def test_lote_de_mas_de_doscientos_costos_es_costos_invalidos() -> None:
    costos = [_costo(producto_id=uuid4(), presentacion_id=uuid4()) for _ in range(201)]
    with pytest.raises(CostosInvalidosError):
        validar_lote_de_costos(costos)


def test_lote_de_exactamente_doscientos_costos_es_valido() -> None:
    costos = [_costo(producto_id=uuid4(), presentacion_id=uuid4()) for _ in range(200)]
    validar_lote_de_costos(costos)


def test_dos_costos_mismo_producto_presentacion_y_vigencia_es_costos_invalidos() -> None:
    with pytest.raises(CostosInvalidosError):
        validar_lote_de_costos([_costo(), _costo()])


def test_mismo_producto_y_presentacion_con_vigencia_distinta_es_valido() -> None:
    validar_lote_de_costos([_costo(vigencia_desde=_HOY), _costo(vigencia_desde=date(2026, 10, 1))])


@pytest.mark.parametrize("valor", [Decimal("0.00"), Decimal("-5.00")])
def test_valor_no_positivo_es_valor_invalido(valor: Decimal) -> None:
    with pytest.raises(ValorInvalidoError):
        validar_lote_de_costos([_costo(valor=valor)])


def test_valor_con_mas_de_dos_decimales_es_valor_invalido() -> None:
    with pytest.raises(ValorInvalidoError):
        validar_lote_de_costos([_costo(valor=Decimal("18000.123"))])


@pytest.mark.parametrize("bonificacion", [Decimal("1.000000"), Decimal("-0.000001")])
def test_bonificacion_fuera_de_rango_es_bonificacion_invalida(bonificacion: Decimal) -> None:
    with pytest.raises(BonificacionInvalidaError):
        validar_lote_de_costos([_costo(bonificacion=bonificacion)])


def test_bonificacion_con_mas_de_seis_decimales_es_bonificacion_invalida() -> None:
    with pytest.raises(BonificacionInvalidaError):
        validar_lote_de_costos([_costo(bonificacion=Decimal("0.1000001"))])


# --- contrato-api.md P9 (aprobado 2026-09-24): `fila` en `DomainError.extension` --


def test_valor_invalido_en_la_segunda_fila_expone_fila_1() -> None:
    with pytest.raises(ValorInvalidoError) as excinfo:
        validar_lote_de_costos(
            [
                _costo(producto_id=_PRODUCTO_A),
                _costo(producto_id=_PRODUCTO_B, valor=Decimal("0.00")),
            ]
        )
    assert excinfo.value.extension == {"fila": 1}


def test_valor_invalido_en_la_primera_fila_expone_fila_0() -> None:
    """Triangulación: el índice depende de la posición real, no de una
    constante -- con la fila inválida primero, `fila` es `0`."""
    with pytest.raises(ValorInvalidoError) as excinfo:
        validar_lote_de_costos(
            [
                _costo(producto_id=_PRODUCTO_A, valor=Decimal("0.00")),
                _costo(producto_id=_PRODUCTO_B),
            ]
        )
    assert excinfo.value.extension == {"fila": 0}


def test_bonificacion_invalida_expone_fila() -> None:
    with pytest.raises(BonificacionInvalidaError) as excinfo:
        validar_lote_de_costos(
            [
                _costo(producto_id=_PRODUCTO_A),
                _costo(producto_id=_PRODUCTO_B, bonificacion=Decimal("1.000000")),
            ]
        )
    assert excinfo.value.extension == {"fila": 1}


def test_lote_vacio_no_expone_fila() -> None:
    """Error de lote completo (no de una fila puntual): sin `extension`."""
    with pytest.raises(CostosInvalidosError) as excinfo:
        validar_lote_de_costos([])
    assert excinfo.value.extension is None


def test_costo_duplicado_expone_fila_de_la_segunda_ocurrencia() -> None:
    with pytest.raises(CostosInvalidosError) as excinfo:
        validar_lote_de_costos([_costo(), _costo()])
    assert excinfo.value.extension == {"fila": 1}
