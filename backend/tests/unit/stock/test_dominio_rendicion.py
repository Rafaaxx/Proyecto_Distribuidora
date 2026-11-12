"""Tarea 1.2 (change 24, `design.md` D2, D4; spec `stock/rendicion-de-jornada`): el dominio puro
de la rendición (`stock/domain/rendicion.py`): conjunto a contar, esperado, diferencia y
validación del conteo. Sin infraestructura.

Los casos con los valores de las specs viven en `shared/fixtures/calculo/rut-06-rendicion.json`
y los corre `tests/fixtures_compartidos/test_rut06_rendicion.py`; acá van las propiedades y los
errores con su código y su extensión.

Reglas citadas: RUT-06, RUT-07, STK-04, INV-04.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.stock.domain import rendicion
from app.modules.stock.domain.errores import (
    CantidadInvalidaError,
    ConteoIncompletoError,
    EsperadoDifiereError,
    ProductoRepetidoError,
)
from app.modules.stock.domain.rendicion import LineaContada


def _linea(producto: str, contada: object, esperada: int) -> LineaContada[str]:
    return LineaContada(producto=producto, contada=contada, esperada=esperada)  # type: ignore[arg-type]


# --- conjunto a contar (RUT-06) ----------------------------------------------------------


def test_rut06_el_conjunto_son_los_saldos_distintos_de_cero_y_los_que_tuvieron_movimiento() -> None:
    conjunto = rendicion.conjunto_a_contar(
        {"vino-a": 40, "agua-500": 0, "gaseosa": 0, "soda": -1},
        con_movimiento={"agua-500"},
    )

    assert conjunto == frozenset({"vino-a", "agua-500", "soda"})


def test_rut06_un_movimiento_de_un_producto_sin_saldo_registrado_tambien_lo_incluye() -> None:
    assert rendicion.conjunto_a_contar({}, con_movimiento={"agua-500"}) == frozenset({"agua-500"})
    assert rendicion.conjunto_a_contar({}, con_movimiento=set()) == frozenset()


# --- esperado y diferencia (RUT-07, INV-04) ----------------------------------------------


def test_rut07_el_esperado_es_al_abrir_mas_ingresos_menos_ventas_mas_anulaciones_mas_otros() -> (
    None
):
    assert rendicion.esperado(al_abrir=10, ingresos=36, ventas=8, anulaciones=2, otros=0) == 40
    assert rendicion.esperado(al_abrir=3, ingresos=1, ventas=2, anulaciones=4, otros=-5) == 1


@given(
    st.integers(-1000, 1000),
    st.integers(0, 1000),
    st.integers(0, 1000),
    st.integers(0, 1000),
    st.integers(-1000, 1000),
)
def test_rut07_el_esperado_cumple_la_identidad_del_resumen(
    al_abrir: int, ingresos: int, ventas: int, anulaciones: int, otros: int
) -> None:
    resultado = rendicion.esperado(
        al_abrir=al_abrir, ingresos=ingresos, ventas=ventas, anulaciones=anulaciones, otros=otros
    )

    assert resultado - al_abrir - ingresos + ventas - anulaciones - otros == 0


def test_inv04_la_diferencia_es_contada_menos_esperada_con_signo() -> None:
    assert rendicion.diferencia(contada=37, esperada=40) == -3
    assert rendicion.diferencia(contada=14, esperada=12) == 2
    assert rendicion.diferencia(contada=0, esperada=-4) == 4


# --- validación del conteo (RUT-06) -------------------------------------------------------


def test_rut06_el_conteo_devuelve_una_linea_por_producto_en_el_orden_recibido() -> None:
    lineas = rendicion.validar_conteo(
        conjunto={"vino-a", "agua-500"},
        esperados={"vino-a": 40, "agua-500": 12},
        lineas=[_linea("agua-500", 12, 12), _linea("vino-a", 37, 40)],
    )

    assert [(x.producto, x.esperado, x.contado, x.diferencia) for x in lineas] == [
        ("agua-500", 12, 12, 0),
        ("vino-a", 40, 37, -3),
    ]


def test_rut06_un_producto_fuera_del_conjunto_se_agrega_con_esperado_cero() -> None:
    lineas = rendicion.validar_conteo(
        conjunto=set(),
        esperados={},
        lineas=[_linea("agua-1500", 2, 0)],
    )

    assert [(x.esperado, x.contado, x.diferencia) for x in lineas] == [(0, 2, 2)]


def test_rut06_conteo_incompleto_nombra_todos_los_productos_que_faltan() -> None:
    with pytest.raises(ConteoIncompletoError) as error:
        rendicion.validar_conteo(
            conjunto={"vino-a", "agua-500", "soda"},
            esperados={"vino-a": 40, "agua-500": 12, "soda": 0},
            lineas=[_linea("vino-a", 40, 40)],
        )

    assert error.value.codigo == "CONTEO_INCOMPLETO"
    assert error.value.status_http == 422
    assert error.value.extension == {"productos": ["agua-500", "soda"]}


def test_rut06_esperado_difiere_informa_los_esperados_actuales_y_cuales_cambiaron() -> None:
    with pytest.raises(EsperadoDifiereError) as error:
        rendicion.validar_conteo(
            conjunto={"vino-a", "agua-500"},
            esperados={"vino-a": 34, "agua-500": 12},
            lineas=[_linea("vino-a", 34, 40), _linea("agua-500", 12, 12)],
        )

    assert error.value.codigo == "ESPERADO_DIFIERE"
    assert error.value.status_http == 409
    assert error.value.extension == {
        "distintos": ["vino-a"],
        "esperados": {"vino-a": 34, "agua-500": 12},
    }


def test_inv04_el_producto_repetido_se_rechaza_con_su_codigo() -> None:
    with pytest.raises(ProductoRepetidoError) as error:
        rendicion.validar_conteo(
            conjunto={"vino-a"},
            esperados={"vino-a": 40},
            lineas=[_linea("vino-a", 40, 40), _linea("vino-a", 39, 40)],
        )

    assert error.value.codigo == "PRODUCTO_REPETIDO"


@pytest.mark.parametrize("contada", [-1, 2.5, True, "3", None])
def test_inv04_la_cantidad_contada_debe_ser_un_entero_no_negativo(contada: object) -> None:
    with pytest.raises(CantidadInvalidaError):
        rendicion.validar_conteo(
            conjunto={"vino-a"},
            esperados={"vino-a": 40},
            lineas=[_linea("vino-a", contada, 40)],
        )


def test_inv04_contar_cero_es_valido() -> None:
    lineas = rendicion.validar_conteo(
        conjunto={"vino-a"}, esperados={"vino-a": 5}, lineas=[_linea("vino-a", 0, 5)]
    )

    assert lineas[0].diferencia == -5


def test_rut06_el_orden_de_los_errores_es_forma_primero_despues_completitud() -> None:
    # Cantidad inválida, producto faltante y esperado distinto a la vez: gana la forma.
    with pytest.raises(CantidadInvalidaError):
        rendicion.validar_conteo(
            conjunto={"vino-a", "agua-500"},
            esperados={"vino-a": 40, "agua-500": 12},
            lineas=[_linea("vino-a", -1, 99)],
        )
    # Producto faltante y esperado distinto: gana la completitud.
    with pytest.raises(ConteoIncompletoError):
        rendicion.validar_conteo(
            conjunto={"vino-a", "agua-500"},
            esperados={"vino-a": 40, "agua-500": 12},
            lineas=[_linea("vino-a", 40, 99)],
        )


def test_los_errores_de_la_rendicion_son_errores_de_dominio_con_codigo_estable() -> None:
    assert issubclass(ConteoIncompletoError, DomainError)
    assert issubclass(EsperadoDifiereError, DomainError)
    assert ConteoIncompletoError.codigo == "CONTEO_INCOMPLETO"
    assert EsperadoDifiereError.codigo == "ESPERADO_DIFIERE"


def test_los_productos_faltantes_se_devuelven_en_el_orden_del_conjunto() -> None:
    assert rendicion.productos_faltantes(["c", "a", "b"], contados=["a"]) == ["c", "b"]
    assert rendicion.productos_faltantes(["a"], contados=["a", "z"]) == []
