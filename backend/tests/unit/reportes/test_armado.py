"""Tarea 1.3 (change 26, `design.md` D5): el armado de una fila según los permisos, puro.

El armado NO suma: las cifras llegan sumadas de la base (REP-01, `02` §14). Solo decide qué se
informa según los permisos (REP-04) y redondea una sola vez las cantidades decimales (TR-03).

Reglas citadas: REP-04, REP-01, TR-03, INV-03.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.reportes.domain.armado import (
    CifrasCrudasDeAjuste,
    CifrasCrudasDeVentas,
    ProductoVendidoCrudo,
    SinCosto,
    armar_cifras_de_ajuste,
    armar_cifras_de_ventas,
    armar_producto_vendido,
    armar_valor_con_costos,
)


def _crudas(**cambios: object) -> CifrasCrudasDeVentas:
    valores: dict[str, object] = {
        "cantidad_ventas": 2,
        "cajas_equivalentes": Decimal("2.5"),
        "unidades_base": 15,
        "importe_bruto": Decimal("1500.00"),
        "importe_descuento": Decimal("0.00"),
        "importe_neto": Decimal("1500.00"),
        "importe_iva": Decimal("0.00"),
        "total": Decimal("1500.00"),
        "costo_vendido": Decimal("850.00"),
        "utilidad": Decimal("350.00"),
        "lineas_sin_costo": 1,
        "neto_sin_costo": Decimal("300.00"),
    }
    valores.update(cambios)
    return CifrasCrudasDeVentas(**valores)  # type: ignore[arg-type]


def test_con_ver_utilidad_informa_costo_utilidad_y_las_lineas_sin_costo() -> None:
    fila = armar_cifras_de_ventas(_crudas(), ve_utilidad=True)

    assert fila.costo_vendido == Decimal("850.00")
    assert fila.utilidad == Decimal("350.00")
    assert fila.sin_costo == SinCosto(lineas=1, importe_neto=Decimal("300.00"))


def test_sin_ver_utilidad_costo_utilidad_y_sin_costo_quedan_en_none() -> None:
    fila = armar_cifras_de_ventas(_crudas(), ve_utilidad=False)

    assert fila.costo_vendido is None
    assert fila.utilidad is None
    assert fila.sin_costo is None


def test_sin_ver_utilidad_las_cantidades_y_los_importes_se_conservan() -> None:
    fila = armar_cifras_de_ventas(_crudas(), ve_utilidad=False)

    assert fila.cantidad_ventas == 2
    assert fila.unidades_base == 15
    assert fila.importe_neto == Decimal("1500.00")
    assert fila.total == Decimal("1500.00")


def test_sin_lineas_sin_costo_el_bloque_vale_cero_con_permiso() -> None:
    fila = armar_cifras_de_ventas(
        _crudas(lineas_sin_costo=0, neto_sin_costo=Decimal("0.00")), ve_utilidad=True
    )

    assert fila.sin_costo == SinCosto(lineas=0, importe_neto=Decimal("0.00"))


def test_las_cajas_equivalentes_se_redondean_una_sola_vez_sobre_la_suma_exacta() -> None:
    # 3 ventas de 1 botella con referencia x6: la suma exacta es 3/6 = 0.5, no 3 x 0.17.
    fila = armar_cifras_de_ventas(
        _crudas(cajas_equivalentes=Decimal(3) / Decimal(6)), ve_utilidad=True
    )

    assert str(fila.cajas_equivalentes) == "0.50"


def test_las_cajas_del_glosario_dan_dos_con_cincuenta() -> None:
    fila = armar_cifras_de_ventas(
        _crudas(cajas_equivalentes=Decimal(15) / Decimal(6)), ve_utilidad=True
    )

    assert str(fila.cajas_equivalentes) == "2.50"


def test_el_armado_no_suma_ni_recalcula_los_importes() -> None:
    # Si el armado recalculara, el total saldria 3: debe devolver lo que vino de la base.
    fila = armar_cifras_de_ventas(
        _crudas(importe_neto=Decimal("1.00"), importe_iva=Decimal("2.00"), total=Decimal("999.00")),
        ve_utilidad=True,
    )

    assert fila.total == Decimal("999.00")
    assert fila.importe_neto == Decimal("1.00")


def test_el_valor_con_costos_se_redondea_una_vez_con_el_permiso() -> None:
    assert armar_valor_con_costos(Decimal("1.005"), ve_costos=True) == Decimal("1.01")
    assert armar_valor_con_costos(Decimal("-1.005"), ve_costos=True) == Decimal("-1.01")


def test_el_valor_con_costos_es_none_sin_el_permiso() -> None:
    assert armar_valor_con_costos(Decimal("1.005"), ve_costos=False) is None


def test_un_valor_ausente_sigue_ausente_aun_con_el_permiso() -> None:
    assert armar_valor_con_costos(None, ve_costos=True) is None


def _producto(**cambios: object) -> ProductoVendidoCrudo:
    valores: dict[str, object] = {
        "cajas_equivalentes": Decimal(15) / Decimal(6),
        "unidades_base": 15,
        "importe_neto": Decimal("1250.00"),
    }
    valores.update(cambios)
    return ProductoVendidoCrudo(**valores)  # type: ignore[arg-type]


def test_el_producto_redondea_sus_cajas_una_sola_vez_y_conserva_el_resto() -> None:
    producto = armar_producto_vendido(_producto())

    assert str(producto.cajas_equivalentes) == "2.50"
    assert producto.unidades_base == 15
    assert producto.importe_neto == Decimal("1250.00")


def test_el_producto_no_suma_cajas_ya_redondeadas() -> None:
    # Tres sextos exactos: 0.50, no tres veces 0.17 = 0.51 (TR-03).
    producto = armar_producto_vendido(_producto(cajas_equivalentes=Decimal(3) / Decimal(6)))

    assert str(producto.cajas_equivalentes) == "0.50"


# --- ajustes de stock por motivo (tarea 6.1; STK-03, TR-03) ---------------------------------


def _ajuste(**cambios: object) -> CifrasCrudasDeAjuste:
    valores: dict[str, object] = {
        "entradas": 4,
        "salidas": 9,
        "valor_de_entradas": Decimal("2000.0005"),
        "valor_de_salidas": Decimal("4500.005"),
        "unidades_sin_costo": 3,
    }
    valores.update(cambios)
    return CifrasCrudasDeAjuste(**valores)  # type: ignore[arg-type]


def test_el_ajuste_con_costos_redondea_cada_valor_una_vez_y_conserva_las_unidades() -> None:
    cifras = armar_cifras_de_ajuste(_ajuste(), ve_costos=True)

    assert (cifras.entradas, cifras.salidas) == (4, 9)
    assert cifras.valor_de_entradas == Decimal("2000.00")
    assert cifras.valor_de_salidas == Decimal("4500.01")
    assert cifras.unidades_sin_costo == 3


def test_el_ajuste_sin_costos_informa_las_unidades_y_deja_los_valores_en_none() -> None:
    cifras = armar_cifras_de_ajuste(_ajuste(), ve_costos=False)

    assert (cifras.entradas, cifras.salidas) == (4, 9)
    assert cifras.valor_de_entradas is None
    assert cifras.valor_de_salidas is None
    assert cifras.unidades_sin_costo is None


def test_el_ajuste_sin_movimientos_en_un_sentido_vale_cero_con_el_permiso() -> None:
    cifras = armar_cifras_de_ajuste(
        _ajuste(entradas=0, valor_de_entradas=Decimal("0"), unidades_sin_costo=0), ve_costos=True
    )

    assert cifras.entradas == 0
    assert cifras.valor_de_entradas == Decimal("0.00")
    assert cifras.unidades_sin_costo == 0
