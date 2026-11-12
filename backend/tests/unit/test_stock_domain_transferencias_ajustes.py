"""Tarea 3.3 (change 14, `design.md` D3, D6): reglas puras de transferencias y ajustes.

Valida el contenido de los comandos `STOCK_TRANSFERIR` y `STOCK_AJUSTAR`, los expande en
las líneas del libro (salida antes que entrada, un solo origen) y decide `MOTIVO_INVALIDO`
y `PRODUCTO_SIN_COSTO`. Dominio puro: sin base de datos.

Reglas citadas: STK-07, STK-08, INV-04, INV-15, CST-12, TR-05, TR-09.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.stock.domain.errores import (
    CantidadFueraDeRangoError,
    CantidadInvalidaError,
    LineasInvalidasError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    ProductoRepetidoError,
    ProductoSinCostoError,
    UbicacionesIgualesError,
)
from app.modules.stock.domain.operaciones import (
    MAXIMO_OBSERVACION,
    LineaDeOperacion,
    expandir_ajuste,
    expandir_transferencia,
    validar_ajuste,
    validar_ingreso_con_costo,
    validar_motivo_de_ajuste,
    validar_transferencia,
)

ORIGEN = uuid4()
DESTINO = uuid4()
MOTIVO = uuid4()


def _linea(cantidad: object = 48, producto: UUID | None = None) -> LineaDeOperacion:
    return LineaDeOperacion(
        producto_id=producto or uuid4(),
        cantidad_base=cantidad,  # type: ignore[arg-type]
    )


def _transferencia(lineas: list[LineaDeOperacion], **cambios: object):  # type: ignore[no-untyped-def]
    datos: dict[str, object] = {
        "ubicacion_origen_id": ORIGEN,
        "ubicacion_destino_id": DESTINO,
        "lineas": lineas,
        "observacion": None,
        **cambios,
    }
    return validar_transferencia(**datos)  # type: ignore[arg-type]


def _ajuste(lineas: list[LineaDeOperacion], **cambios: object):  # type: ignore[no-untyped-def]
    datos: dict[str, object] = {
        "ubicacion_id": ORIGEN,
        "motivo_id": MOTIVO,
        "lineas": lineas,
        "observacion": None,
        **cambios,
    }
    return validar_ajuste(**datos)  # type: ignore[arg-type]


# --- validar_transferencia ------------------------------------------------------


def test_una_transferencia_valida_conserva_ubicaciones_y_lineas() -> None:
    lineas = [_linea(48), _linea(24)]

    validada = _transferencia(lineas)

    assert validada.ubicacion_origen_id == ORIGEN
    assert validada.ubicacion_destino_id == DESTINO
    assert validada.lineas == lineas


def test_origen_y_destino_iguales_son_ubicaciones_iguales() -> None:
    with pytest.raises(UbicacionesIgualesError) as error:
        _transferencia([_linea()], ubicacion_destino_id=ORIGEN)

    assert error.value.codigo == "UBICACIONES_IGUALES"
    assert error.value.status_http == 422


@pytest.mark.parametrize("cantidad_de_lineas", [0, 201])
def test_la_transferencia_admite_de_una_a_doscientas_lineas(cantidad_de_lineas: int) -> None:
    with pytest.raises(LineasInvalidasError):
        _transferencia([_linea() for _ in range(cantidad_de_lineas)])


@pytest.mark.parametrize("cantidad_de_lineas", [1, 200])
def test_los_limites_de_lineas_de_la_transferencia_se_aceptan(cantidad_de_lineas: int) -> None:
    assert len(_transferencia([_linea() for _ in range(cantidad_de_lineas)]).lineas) == (
        cantidad_de_lineas
    )


def test_un_producto_repetido_se_rechaza() -> None:
    producto = uuid4()

    with pytest.raises(ProductoRepetidoError):
        _transferencia([_linea(1, producto), _linea(2, producto)])


@pytest.mark.parametrize("cantidad", [0, -5, 1.5, "3", True, None])
def test_la_cantidad_de_una_transferencia_es_un_entero_mayor_que_cero(cantidad: object) -> None:
    """INV-04: `0` y `−5` son `CANTIDAD_INVALIDA`; un `float`, un texto o un `bool` no son
    una cantidad."""
    with pytest.raises(CantidadInvalidaError):
        _transferencia([_linea(cantidad)])


def test_la_cantidad_de_una_transferencia_no_sale_de_integer() -> None:
    with pytest.raises(CantidadFueraDeRangoError):
        _transferencia([_linea(2_147_483_648)])
    assert _transferencia([_linea(2_147_483_647)]).lineas[0].cantidad_base == 2_147_483_647


@pytest.mark.parametrize(
    ("cruda", "esperada"),
    [(None, None), ("", None), ("   ", None), ("  carga del lunes ", "carga del lunes")],
)
def test_la_observacion_se_recorta_y_vacia_es_nula(cruda: str | None, esperada: str | None) -> None:
    assert _transferencia([_linea()], observacion=cruda).observacion == esperada
    assert _ajuste([_linea()], observacion=cruda).observacion == esperada


def test_la_observacion_admite_quinientos_caracteres_y_no_quinientos_uno() -> None:
    assert (
        len(_transferencia([_linea()], observacion="a" * MAXIMO_OBSERVACION).observacion or "")
        == 500
    )
    with pytest.raises(ObservacionInvalidaError) as error:
        _transferencia([_linea()], observacion="a" * (MAXIMO_OBSERVACION + 1))
    assert error.value.codigo == "OBSERVACION_INVALIDA"
    with pytest.raises(ObservacionInvalidaError):
        _ajuste([_linea(1)], observacion="a" * (MAXIMO_OBSERVACION + 1))


def test_el_largo_de_la_observacion_se_mide_despues_de_recortar() -> None:
    assert _transferencia([_linea()], observacion=" " + "a" * 500 + " ").observacion == "a" * 500


@pytest.mark.parametrize("cantidad", [0, -5])
def test_el_error_de_una_cantidad_indica_el_indice_de_su_linea(cantidad: int) -> None:
    """Contrato API P9: un error de línea lleva su índice 0-based en `extension["linea"]`."""
    with pytest.raises(CantidadInvalidaError) as error:
        _transferencia([_linea(1), _linea(2), _linea(cantidad)])

    assert error.value.extension == {"linea": 2}


def test_el_error_de_un_producto_repetido_indica_la_linea_repetida() -> None:
    producto = uuid4()

    with pytest.raises(ProductoRepetidoError) as error:
        _ajuste([_linea(1, producto), _linea(3), _linea(-1, producto)])

    assert error.value.extension == {"linea": 2}


def test_el_error_de_cantidad_fuera_de_rango_indica_su_linea() -> None:
    with pytest.raises(CantidadFueraDeRangoError) as error:
        _ajuste([_linea(1), _linea(2_147_483_648)])

    assert error.value.extension == {"linea": 1}


# --- expandir_transferencia -----------------------------------------------------


def test_la_expansion_pone_la_salida_antes_que_la_entrada_por_producto() -> None:
    vino, agua = uuid4(), uuid4()
    transferencia_id = uuid4()
    validada = _transferencia([_linea(48, vino), _linea(24, agua)])

    movimientos = expandir_transferencia(validada, transferencia_id=transferencia_id)

    assert [(m.producto_id, m.tipo, m.ubicacion_id, m.cantidad_base) for m in movimientos] == [
        (vino, "TRANSFERENCIA_SALIDA", ORIGEN, -48),
        (vino, "TRANSFERENCIA_ENTRADA", DESTINO, 48),
        (agua, "TRANSFERENCIA_SALIDA", ORIGEN, -24),
        (agua, "TRANSFERENCIA_ENTRADA", DESTINO, 24),
    ]
    assert {m.origen_tipo for m in movimientos} == {"TRANSFERENCIA"}
    assert {m.origen_id for m in movimientos} == {transferencia_id}
    assert all(m.costo_unitario is None and m.motivo_id is None for m in movimientos)


@given(
    cantidades=st.lists(st.integers(min_value=1, max_value=2_147_483_647), min_size=1, max_size=20),
)
def test_inv15_la_expansion_de_toda_transferencia_valida_suma_cero_por_producto(
    cantidades: list[int],
) -> None:
    """INV-15: lo que sale del origen entra al destino, producto por producto."""
    validada = _transferencia([_linea(cantidad) for cantidad in cantidades])

    movimientos = expandir_transferencia(validada, transferencia_id=uuid4())

    sumas: dict[UUID, int] = defaultdict(int)
    for movimiento in movimientos:
        sumas[movimiento.producto_id] += movimiento.cantidad_base
    assert set(sumas.values()) == {0}
    assert len(movimientos) == 2 * len(cantidades)


# --- validar_ajuste -------------------------------------------------------------


def test_un_ajuste_admite_signos_mezclados() -> None:
    """D6: un conteo puede dar sobrantes y faltantes en el mismo ajuste."""
    lineas = [_linea(-2), _linea(1)]

    validado = _ajuste(lineas)

    assert validado.lineas == lineas
    assert validado.ubicacion_id == ORIGEN
    assert validado.motivo_id == MOTIVO


@pytest.mark.parametrize("cantidad", [0, 1.5, "3", True, None])
def test_la_cantidad_de_un_ajuste_es_un_entero_distinto_de_cero(cantidad: object) -> None:
    with pytest.raises(CantidadInvalidaError):
        _ajuste([_linea(cantidad)])


@pytest.mark.parametrize("cantidad", [-2_147_483_649, 2_147_483_648])
def test_la_cantidad_de_un_ajuste_no_sale_de_integer(cantidad: int) -> None:
    with pytest.raises(CantidadFueraDeRangoError):
        _ajuste([_linea(cantidad)])


def test_las_reglas_de_lineas_del_ajuste_son_las_de_la_transferencia() -> None:
    producto = uuid4()
    with pytest.raises(LineasInvalidasError):
        _ajuste([])
    with pytest.raises(LineasInvalidasError):
        _ajuste([_linea(1) for _ in range(201)])
    with pytest.raises(ProductoRepetidoError):
        _ajuste([_linea(1, producto), _linea(-1, producto)])


def test_la_expansion_de_un_ajuste_lleva_el_motivo_y_el_origen() -> None:
    vino, agua = uuid4(), uuid4()
    ajuste_id = uuid4()
    validado = _ajuste([_linea(-6, vino), _linea(2, agua)])

    movimientos = expandir_ajuste(validado, ajuste_id=ajuste_id)

    assert [(m.producto_id, m.tipo, m.cantidad_base) for m in movimientos] == [
        (vino, "AJUSTE", -6),
        (agua, "AJUSTE", 2),
    ]
    assert {m.ubicacion_id for m in movimientos} == {ORIGEN}
    assert {m.motivo_id for m in movimientos} == {MOTIVO}
    assert {m.origen_tipo for m in movimientos} == {"AJUSTE_STOCK"}
    assert {m.origen_id for m in movimientos} == {ajuste_id}
    assert all(m.costo_unitario is None for m in movimientos)


# --- validar_motivo_de_ajuste ---------------------------------------------------


def test_un_motivo_activo_del_ambito_de_ajuste_es_valido() -> None:
    validar_motivo_de_ajuste(activo=True, ambito="AJUSTE_STOCK")


@pytest.mark.parametrize(
    ("activo", "ambito"),
    [(False, "AJUSTE_STOCK"), (True, "ANULACION_AJUSTE"), (True, "ANULACION_COMPRA")],
)
def test_un_motivo_inactivo_o_de_otro_ambito_es_motivo_invalido(activo: bool, ambito: str) -> None:
    with pytest.raises(MotivoInvalidoError) as error:
        validar_motivo_de_ajuste(activo=activo, ambito=ambito)

    assert error.value.codigo == "MOTIVO_INVALIDO"
    assert error.value.status_http == 422


# --- validar_ingreso_con_costo --------------------------------------------------


def test_un_ingreso_de_ajuste_sin_promedio_es_producto_sin_costo() -> None:
    """D3: ese stock se carga con stock inicial o compra, que sí fijan costo."""
    with pytest.raises(ProductoSinCostoError) as error:
        validar_ingreso_con_costo(cantidad_base=24, costo_promedio=None)

    assert error.value.codigo == "PRODUCTO_SIN_COSTO"
    assert error.value.status_http == 409


def test_un_ingreso_de_ajuste_con_promedio_se_acepta() -> None:
    validar_ingreso_con_costo(cantidad_base=2, costo_promedio=Decimal("1050.000000"))


def test_un_egreso_sin_promedio_no_exige_costo() -> None:
    """Un ajuste negativo de un producto sin promedio es posible (solo el ingreso exige
    costo): se valoriza nulo."""
    validar_ingreso_con_costo(cantidad_base=-3, costo_promedio=None)


def test_los_errores_nuevos_son_errores_de_dominio_con_codigo_estable() -> None:
    for clase in (
        UbicacionesIgualesError,
        ObservacionInvalidaError,
        MotivoInvalidoError,
        ProductoSinCostoError,
    ):
        assert issubclass(clase, DomainError)
        assert clase.codigo == clase.codigo.upper()
        assert clase.status_http in {409, 422}
