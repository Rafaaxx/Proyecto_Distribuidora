"""Tarea 5.1 (change 18a; spec `ventas/composicion-de-venta`, requisito de líneas; `design.md`
D8): dominio puro de la composición de las líneas de una venta.

Reglas citadas: VTA-02, CAT-02, CAT-05, CAT-07, INV-04, INV-07.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.modules.ventas.domain.composicion import (
    MAXIMO_LINEAS,
    LineaPedida,
    cantidad_base,
    validar_lineas,
    validar_producto_y_presentacion,
)
from app.modules.ventas.domain.errores import (
    CantidadInvalidaError,
    LineaDuplicadaError,
    LineasInvalidasError,
    PresentacionNoVendibleError,
    ProductoInactivoError,
    VentaSinLineasError,
)


def _linea(cantidad: int = 1, **cambios: object) -> LineaPedida:
    valores: dict[str, object] = {
        "producto_id": uuid4(),
        "presentacion_id": uuid4(),
        "cantidad": cantidad,
    }
    valores.update(cambios)
    return LineaPedida(**valores)  # type: ignore[arg-type]


# --- de 1 a 200 líneas (INV-07, D8) ----------------------------------------------


def test_inv07_una_venta_sin_lineas_se_rechaza() -> None:
    with pytest.raises(VentaSinLineasError) as error:
        validar_lineas([])
    assert error.value.codigo == "VENTA_SIN_LINEAS"
    assert error.value.status_http == 422


@pytest.mark.parametrize("cantidad_de_lineas", [1, 2, 200])
def test_de_una_a_doscientas_lineas_se_aceptan(cantidad_de_lineas: int) -> None:
    validar_lineas([_linea() for _ in range(cantidad_de_lineas)])


def test_inv07_mas_de_doscientas_lineas_se_rechazan() -> None:
    assert MAXIMO_LINEAS == 200
    with pytest.raises(LineasInvalidasError) as error:
        validar_lineas([_linea() for _ in range(201)])
    assert error.value.codigo == "LINEAS_INVALIDAS"
    assert error.value.status_http == 422


# --- cantidad entera positiva (INV-04) -------------------------------------------


@pytest.mark.parametrize("cantidad", [0, -1, -12])
def test_inv04_la_cantidad_debe_ser_mayor_que_cero(cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError) as error:
        validar_lineas([_linea(), _linea(cantidad)])
    assert error.value.codigo == "CANTIDAD_INVALIDA"
    assert error.value.status_http == 422


@pytest.mark.parametrize("cantidad", [2.5, True, "3"])
def test_inv04_la_cantidad_debe_ser_entera(cantidad: object) -> None:
    """INV-04: ni un decimal, ni un booleano (que en Python es entero), ni un texto."""
    with pytest.raises(CantidadInvalidaError):
        validar_lineas([_linea(cantidad)])  # type: ignore[arg-type]


# --- línea duplicada (VTA-02) -----------------------------------------------------


def test_vta02_el_mismo_producto_y_presentacion_dos_veces_se_rechaza() -> None:
    producto_id, presentacion_id = uuid4(), uuid4()
    lineas = [
        _linea(2, producto_id=producto_id, presentacion_id=presentacion_id),
        _linea(1, producto_id=uuid4(), presentacion_id=uuid4()),
        _linea(3, producto_id=producto_id, presentacion_id=presentacion_id),
    ]

    with pytest.raises(LineaDuplicadaError) as error:
        validar_lineas(lineas)
    assert error.value.codigo == "LINEA_DUPLICADA"
    assert error.value.status_http == 422


def test_vta02_el_mismo_producto_en_dos_presentaciones_son_dos_lineas() -> None:
    """Cajas + unidades sueltas (CAT-07): mismo producto, presentaciones distintas."""
    producto_id = uuid4()
    validar_lineas(
        [
            _linea(2, producto_id=producto_id, presentacion_id=uuid4()),
            _linea(3, producto_id=producto_id, presentacion_id=uuid4()),
        ]
    )


def test_la_misma_presentacion_de_otro_producto_no_es_duplicada() -> None:
    presentacion_id = uuid4()
    validar_lineas(
        [
            _linea(producto_id=uuid4(), presentacion_id=presentacion_id),
            _linea(producto_id=uuid4(), presentacion_id=presentacion_id),
        ]
    )


# --- cantidad base (VTA-02, CAT-07, INV-18) ---------------------------------------


@pytest.mark.parametrize(
    ("cantidad", "unidades", "esperado"),
    [(2, 6, 12), (3, 1, 3), (1, 12, 12), (200, 24, 4800)],
)
def test_la_cantidad_base_es_cantidad_por_unidades_de_la_presentacion(
    cantidad: int, unidades: int, esperado: int
) -> None:
    """Ejemplo de D8: 2 "Caja x6" -> 12 base y 3 "Botella" -> 3 base (15 en total)."""
    assert cantidad_base(cantidad, unidades) == esperado


# --- presentación vendible y producto activo (CAT-02, CAT-05) ----------------------


def test_cat05_un_producto_inactivo_se_rechaza() -> None:
    with pytest.raises(ProductoInactivoError) as error:
        validar_producto_y_presentacion(
            producto_activo=False, presentacion_activa=True, presentacion_usar_en_venta=True
        )
    assert error.value.codigo == "PRODUCTO_INACTIVO"
    assert error.value.status_http == 409


@pytest.mark.parametrize(
    ("activa", "usar_en_venta"),
    [(True, False), (False, True), (False, False)],
)
def test_cat02_una_presentacion_inactiva_o_sin_uso_en_venta_no_es_vendible(
    activa: bool, usar_en_venta: bool
) -> None:
    with pytest.raises(PresentacionNoVendibleError) as error:
        validar_producto_y_presentacion(
            producto_activo=True,
            presentacion_activa=activa,
            presentacion_usar_en_venta=usar_en_venta,
        )
    assert error.value.codigo == "PRESENTACION_NO_VENDIBLE"
    assert error.value.status_http == 409


def test_producto_y_presentacion_activos_y_de_venta_se_aceptan() -> None:
    validar_producto_y_presentacion(
        producto_activo=True, presentacion_activa=True, presentacion_usar_en_venta=True
    )


def test_los_errores_de_composicion_son_errores_de_dominio() -> None:
    for clase in (
        VentaSinLineasError,
        LineasInvalidasError,
        CantidadInvalidaError,
        LineaDuplicadaError,
        PresentacionNoVendibleError,
        ProductoInactivoError,
    ):
        assert issubclass(clase, DomainError)
