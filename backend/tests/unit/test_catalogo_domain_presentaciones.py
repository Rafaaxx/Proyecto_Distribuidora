"""Change 05, tareas 4.3/4.4/4.5: validación pura del conjunto de
presentaciones de un alta (CAT-02, CAT-03) y de la decisión de modificar
una presentación existente (CAT-04, INV-18)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.catalogo.domain.errores import (
    ProductoSinPresentacionesError,
    ReferenciaInvalidaError,
    UnidadesCongeladasError,
    UnidadesInvalidasError,
)
from app.modules.catalogo.domain.presentaciones import (
    DatosPresentacion,
    validar_alta_presentaciones,
    validar_modificacion_presentacion,
    validar_nueva_referencia,
    validar_unidades_base,
)

_BOTELLA = DatosPresentacion(
    nombre="Botella", unidades_base=1, usar_en_venta=True, usar_en_compra=True, es_referencia=False
)
_CAJA_X6_REFERENCIA = DatosPresentacion(
    nombre="Caja x6", unidades_base=6, usar_en_venta=True, usar_en_compra=True, es_referencia=True
)


# --- validar_unidades_base (CAT-02, INV-04) -------------------------------


@pytest.mark.parametrize("unidades", [1, 6, 24, 1000])
def test_cat02_unidades_base_entero_positivo_es_valido(unidades: int) -> None:
    validar_unidades_base(unidades)  # No lanza.


@pytest.mark.parametrize("unidades", [0, -1, -6])
def test_cat02_unidades_base_menor_a_uno_es_invalida(unidades: int) -> None:
    with pytest.raises(UnidadesInvalidasError):
        validar_unidades_base(unidades)


def test_inv04_unidades_no_enteras_son_invalidas() -> None:
    with pytest.raises(UnidadesInvalidasError):
        validar_unidades_base(2.5)  # type: ignore[arg-type]


def test_unidades_base_booleana_es_invalida() -> None:
    """`bool` es subclase de `int` en Python: `True` no es una cantidad de
    unidades válida aunque `isinstance(True, int)` sea cierto."""
    with pytest.raises(UnidadesInvalidasError):
        validar_unidades_base(True)  # type: ignore[arg-type]


# --- validar_alta_presentaciones (CAT-02, CAT-03) -------------------------


def test_cat02_cat03_alta_con_una_referencia_de_venta_es_valida() -> None:
    validar_alta_presentaciones([_BOTELLA, _CAJA_X6_REFERENCIA])  # No lanza.


def test_cat02_alta_sin_presentaciones_es_invalida() -> None:
    with pytest.raises(ProductoSinPresentacionesError):
        validar_alta_presentaciones([])


def test_cat03_alta_sin_ninguna_referencia_es_invalida() -> None:
    solo_botella = DatosPresentacion(
        nombre="Botella",
        unidades_base=1,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=False,
    )
    with pytest.raises(ReferenciaInvalidaError):
        validar_alta_presentaciones([solo_botella])


def test_cat03_alta_con_dos_referencias_es_invalida() -> None:
    otra_referencia = DatosPresentacion(
        nombre="Caja x12",
        unidades_base=12,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
    )
    with pytest.raises(ReferenciaInvalidaError):
        validar_alta_presentaciones([_CAJA_X6_REFERENCIA, otra_referencia])


def test_cat03_referencia_que_no_se_usa_en_venta_es_invalida() -> None:
    referencia_sin_venta = DatosPresentacion(
        nombre="Pack x24",
        unidades_base=24,
        usar_en_venta=False,
        usar_en_compra=True,
        es_referencia=True,
    )
    with pytest.raises(ReferenciaInvalidaError):
        validar_alta_presentaciones([referencia_sin_venta])


def test_una_falla_de_unidades_en_una_presentacion_no_referencia_se_reporta() -> None:
    """Spec productos-y-presentaciones, escenario "Una falla en una
    presentación no deja el producto a medias": la segunda presentación
    con 0 unidades se rechaza con `UNIDADES_INVALIDAS`, no con un error de
    referencia (INV-01, CAT-02)."""
    presentacion_invalida = DatosPresentacion(
        nombre="Media docena",
        unidades_base=0,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=False,
    )
    with pytest.raises(UnidadesInvalidasError):
        validar_alta_presentaciones([_CAJA_X6_REFERENCIA, presentacion_invalida])


# --- validar_nueva_referencia (CAT-03) ------------------------------------


def test_cat03_nueva_referencia_activa_y_de_venta_es_valida() -> None:
    validar_nueva_referencia(activo=True, usar_en_venta=True)  # No lanza.


@pytest.mark.parametrize(
    ("activo", "usar_en_venta"), [(True, False), (False, True), (False, False)]
)
def test_cat03_nueva_referencia_inactiva_o_sin_venta_es_invalida(
    activo: bool, usar_en_venta: bool
) -> None:
    with pytest.raises(ReferenciaInvalidaError):
        validar_nueva_referencia(activo=activo, usar_en_venta=usar_en_venta)


# --- validar_modificacion_presentacion (CAT-03, CAT-04, INV-18) -----------


def test_cat04_cambiar_unidades_sin_uso_es_valido() -> None:
    validar_modificacion_presentacion(
        es_referencia=False,
        unidades_base_actual=6,
        unidades_base_nueva=12,
        usar_en_venta_nuevo=True,
        activo_nuevo=True,
        fue_usada=False,
    )  # No lanza.


def test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado() -> None:
    with pytest.raises(UnidadesCongeladasError):
        validar_modificacion_presentacion(
            es_referencia=False,
            unidades_base_actual=6,
            unidades_base_nueva=12,
            usar_en_venta_nuevo=True,
            activo_nuevo=True,
            fue_usada=True,
        )


def test_cat04_presentacion_usada_puede_renombrarse_o_desactivarse_sin_cambiar_unidades() -> None:
    """Spec: "una presentación usada sí puede renombrarse o desactivarse"
    -- mismas unidades, `activo=False`, con `fue_usada=True`, no lanza."""
    validar_modificacion_presentacion(
        es_referencia=False,
        unidades_base_actual=6,
        unidades_base_nueva=6,
        usar_en_venta_nuevo=True,
        activo_nuevo=False,
        fue_usada=True,
    )  # No lanza.


def test_cat03_referencia_no_puede_desactivarse() -> None:
    with pytest.raises(ReferenciaInvalidaError):
        validar_modificacion_presentacion(
            es_referencia=True,
            unidades_base_actual=6,
            unidades_base_nueva=6,
            usar_en_venta_nuevo=True,
            activo_nuevo=False,
            fue_usada=False,
        )


def test_cat03_referencia_no_puede_dejar_de_usarse_en_venta() -> None:
    with pytest.raises(ReferenciaInvalidaError):
        validar_modificacion_presentacion(
            es_referencia=True,
            unidades_base_actual=6,
            unidades_base_nueva=6,
            usar_en_venta_nuevo=False,
            activo_nuevo=True,
            fue_usada=False,
        )


def test_unidades_invalidas_en_modificacion_se_reporta_como_tal() -> None:
    with pytest.raises(UnidadesInvalidasError):
        validar_modificacion_presentacion(
            es_referencia=False,
            unidades_base_actual=6,
            unidades_base_nueva=0,
            usar_en_venta_nuevo=True,
            activo_nuevo=True,
            fue_usada=False,
        )


# --- Tarea 4.5: propiedad Hypothesis (CAT-03) -----------------------------

_st_presentacion_no_referencia = st.builds(
    DatosPresentacion,
    nombre=st.text(min_size=1, max_size=20),
    unidades_base=st.integers(min_value=1, max_value=10_000),
    usar_en_venta=st.booleans(),
    usar_en_compra=st.booleans(),
    es_referencia=st.just(False),
)
_st_presentacion_referencia = st.builds(
    DatosPresentacion,
    nombre=st.text(min_size=1, max_size=20),
    unidades_base=st.integers(min_value=1, max_value=10_000),
    usar_en_venta=st.just(True),
    usar_en_compra=st.booleans(),
    es_referencia=st.just(True),
)


@given(
    otras=st.lists(_st_presentacion_no_referencia, max_size=5),
    referencia=_st_presentacion_referencia,
    posicion=st.integers(min_value=0, max_value=5),
)
def test_propiedad_todo_conjunto_aceptado_tiene_exactamente_una_referencia_de_venta(
    otras: list[DatosPresentacion], referencia: DatosPresentacion, posicion: int
) -> None:
    """CAT-03: para cualquier conjunto de presentaciones que
    `validar_alta_presentaciones` acepta, hay exactamente una referencia y
    es de venta."""
    indice = min(posicion, len(otras))
    presentaciones = [*otras[:indice], referencia, *otras[indice:]]

    validar_alta_presentaciones(presentaciones)  # No debe lanzar (se construyó válido).

    referencias = [p for p in presentaciones if p.es_referencia]
    assert len(referencias) == 1
    assert referencias[0].usar_en_venta is True
