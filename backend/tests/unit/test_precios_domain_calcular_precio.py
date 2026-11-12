"""Change 13, tarea 4.4: `calcular_precio` junta costo de referencia, margen y redondeo y
devuelve todo lo que PRC-16 pide guardar, o la causa de no tener precio
(`precios/domain/precio.py`; spec `precios/calculo-de-precios`; PRC-11 a PRC-16, D2, D3, D9).

Reglas citadas: PRC-11, PRC-12, PRC-14, PRC-15 (modo C), PRC-16, TR-03, INV-03.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.precios.domain.errores import ModoImpositivoNoSoportadoError
from app.modules.precios.domain.precio import (
    PRECIO_NO_POSITIVO,
    SIN_COSTO,
    SIN_PRESENTACION_DE_REFERENCIA,
    SIN_REGLA,
    PrecioCalculado,
    SinPrecio,
    calcular_precio,
    exigir_modo_impositivo_soportado,
)
from app.modules.precios.domain.redondeo import Redondeo
from app.modules.precios.domain.reglas import Regla

CIEN_ARRIBA = Redondeo(Decimal("100.00"), "ARRIBA")


def _regla(tipo: str = "MARGEN_BRUTO", valor: str = "0.300000") -> Regla:
    return Regla(
        id=uuid4(),
        alcance_tipo="CATEGORIA",
        alcance_id=uuid4(),
        tipo=tipo,
        valor=Decimal(valor),
        activo=True,
    )


def _precio(**cambios: object) -> PrecioCalculado | SinPrecio:
    argumentos: dict[str, object] = {
        "costo_base": Decimal("1000.000000"),
        "unidades_referencia": 6,
        "regla": _regla(),
        "redondeo": CIEN_ARRIBA,
        "modo_impositivo": "A",
    }
    argumentos.update(cambios)
    return calcular_precio(**argumentos)  # type: ignore[arg-type]


# --- lo que PRC-16 pide guardar -------------------------------------------------------------


def test_un_precio_calculado_devuelve_todo_lo_que_prc_16_pide_guardar() -> None:
    """Vino A: costo base `1000.000000`, referencia `Caja x6`, margen bruto 30%, redondeo
    `100.00` hacia arriba (`01` §7.2)."""
    regla = _regla()

    resultado = _precio(regla=regla)

    assert isinstance(resultado, PrecioCalculado)
    assert str(resultado.costo_referencia) == "6000.000000"
    assert resultado.regla_id == regla.id
    assert resultado.tipo_margen == "MARGEN_BRUTO"
    assert str(resultado.valor_margen) == "0.300000"
    assert str(resultado.precio_calculado) == "8571.428571"
    assert str(resultado.precio_final) == "8600.00"
    assert resultado.unidades_referencia == 6


def test_markup_del_treinta_por_ciento_da_el_ejemplo_de_siete_mil_ochocientos() -> None:
    resultado = _precio(regla=_regla("MARKUP"))

    assert isinstance(resultado, PrecioCalculado)
    assert (str(resultado.precio_calculado), str(resultado.precio_final)) == (
        "7800.000000",
        "7800.00",
    )


@pytest.mark.parametrize(
    ("costo_base", "unidades", "tipo", "valor", "redondeo", "calculado", "final"),
    [
        # D2: costo tomado de la `Caja x12` (950 por botella), referencia x6.
        (
            "950.000000",
            6,
            "MARKUP",
            "0.3",
            Redondeo(Decimal("100"), "CERCANO"),
            "7410.000000",
            "7400.00",
        ),
        # D3: Cerveza B con IVA como costo, `Caja x12`, markup 30%, más cercano a 100.
        (
            "1815.000000",
            12,
            "MARKUP",
            "0.3",
            Redondeo(Decimal("100"), "CERCANO"),
            "28314.000000",
            "28300.00",
        ),
        # D4: Vino A con el costo nuevo, referencia x6, margen bruto 30%, arriba.
        ("1100.000000", 6, "MARGEN_BRUTO", "0.3", CIEN_ARRIBA, "9428.571429", "9500.00"),
        # D4: margen subido a 35% sobre Cerveza B.
        ("1815.000000", 12, "MARGEN_BRUTO", "0.35", CIEN_ARRIBA, "33507.692308", "33600.00"),
        # Múltiplo de un centavo.
        (
            "1000.000000",
            6,
            "MARGEN_BRUTO",
            "0.3",
            Redondeo(Decimal("0.01"), "CERCANO"),
            "8571.428571",
            "8571.43",
        ),
    ],
)
def test_los_ejemplos_del_diseno(
    costo_base: str,
    unidades: int,
    tipo: str,
    valor: str,
    redondeo: Redondeo,
    calculado: str,
    final: str,
) -> None:
    resultado = _precio(
        costo_base=Decimal(costo_base),
        unidades_referencia=unidades,
        regla=_regla(tipo, valor),
        redondeo=redondeo,
    )

    assert isinstance(resultado, PrecioCalculado)
    assert (str(resultado.precio_calculado), str(resultado.precio_final)) == (calculado, final)


def test_el_redondeo_parte_del_valor_exacto_y_no_del_calculado_a_seis_decimales() -> None:
    """TR-03: los valores intermedios no se redondean. `0.400000 x (1 + 0.000001) =
    0.4000004` se registra como `0.400000`, pero hacia arriba al múltiplo `0.40` es `0.80`
    porque el valor exacto supera al múltiplo."""
    resultado = _precio(
        costo_base=Decimal("0.400000"),
        unidades_referencia=1,
        regla=_regla("MARKUP", "0.000001"),
        redondeo=Redondeo(Decimal("0.40"), "ARRIBA"),
    )

    assert isinstance(resultado, PrecioCalculado)
    assert str(resultado.precio_calculado) == "0.400000"
    assert str(resultado.precio_final) == "0.80"


def test_el_resultado_es_inmutable() -> None:
    resultado = _precio()

    with pytest.raises(FrozenInstanceError):
        resultado.precio_final = Decimal("1")  # type: ignore[union-attr,misc]


# --- las causas de no tener precio ------------------------------------------------------------


def test_un_producto_sin_costo_informado_vigente_no_tiene_precio() -> None:
    resultado = _precio(costo_base=None)

    assert resultado == SinPrecio(causa=SIN_COSTO)
    assert SIN_COSTO == "SIN_COSTO"


def test_un_producto_sin_presentacion_de_referencia_no_tiene_precio() -> None:
    """Decisión del 2026-10-06 (D4): sin unidades de referencia no hay costo de referencia."""
    resultado = _precio(unidades_referencia=None)

    assert resultado == SinPrecio(causa=SIN_PRESENTACION_DE_REFERENCIA)
    assert SIN_PRESENTACION_DE_REFERENCIA == "SIN_PRESENTACION_DE_REFERENCIA"


def test_sin_presentacion_de_referencia_se_informa_aunque_falten_costo_y_regla() -> None:
    """Es la causa más básica: sin referencia el costo ni la regla alcanzan para dar precio."""
    resultado = _precio(unidades_referencia=None, costo_base=None, regla=None)

    assert resultado == SinPrecio(causa=SIN_PRESENTACION_DE_REFERENCIA)


def test_sin_presentacion_de_referencia_el_modo_c_se_sigue_rechazando() -> None:
    with pytest.raises(ModoImpositivoNoSoportadoError):
        _precio(unidades_referencia=None, modo_impositivo="C")


def test_un_producto_sin_regla_aplicable_no_tiene_precio() -> None:
    resultado = _precio(regla=None)

    assert resultado == SinPrecio(causa=SIN_REGLA)
    assert SIN_REGLA == "SIN_REGLA"


def test_sin_costo_y_sin_regla_la_causa_es_la_falta_de_costo() -> None:
    assert _precio(costo_base=None, regla=None) == SinPrecio(causa=SIN_COSTO)


def test_un_redondeo_que_da_cero_no_tiene_precio() -> None:
    """Hacia abajo, un precio calculado menor que el múltiplo da cero (D9 punto 4)."""
    resultado = _precio(
        costo_base=Decimal("10.000000"),
        unidades_referencia=8,  # costo de referencia 80
        regla=_regla("MARKUP", "0"),
        redondeo=Redondeo(Decimal("100.00"), "ABAJO"),
    )

    assert resultado == SinPrecio(causa=PRECIO_NO_POSITIVO)
    assert PRECIO_NO_POSITIVO == "PRECIO_NO_POSITIVO"


# --- el modo impositivo (PRC-15) -----------------------------------------------------------------


@pytest.mark.parametrize("modo", ["A", "B"])
def test_en_modos_a_y_b_el_redondeo_se_aplica_al_precio_neto(modo: str) -> None:
    resultado = _precio(modo_impositivo=modo)

    assert isinstance(resultado, PrecioCalculado)
    assert str(resultado.precio_final) == "8600.00"


def test_el_modo_c_no_soportado_se_rechaza_antes_de_calcular_nada() -> None:
    with pytest.raises(ModoImpositivoNoSoportadoError) as error:
        _precio(modo_impositivo="C")
    assert error.value.codigo == "MODO_IMPOSITIVO_NO_SOPORTADO"
    assert isinstance(error.value, DomainError)

    # También si el producto no tiene costo ni regla: la organización entera no soporta C.
    with pytest.raises(ModoImpositivoNoSoportadoError):
        _precio(modo_impositivo="C", costo_base=None, regla=None)


# --- INV-03 y los invariantes del llamador ------------------------------------------------------


def test_inv03_el_costo_base_no_puede_ser_punto_flotante() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        _precio(costo_base=1000.5)


def test_las_unidades_de_referencia_menores_que_uno_son_un_defecto_del_llamador() -> None:
    with pytest.raises(ValueError, match="unidades de referencia"):
        _precio(unidades_referencia=0)


@pytest.mark.parametrize("modo", ["A", "B"])
def test_exigir_modo_impositivo_soportado_acepta_a_y_b(modo: str) -> None:
    exigir_modo_impositivo_soportado(modo)


@pytest.mark.parametrize("modo", ["C", "", "a"])
def test_exigir_modo_impositivo_soportado_rechaza_el_resto_prc_15(modo: str) -> None:
    with pytest.raises(ModoImpositivoNoSoportadoError):
        exigir_modo_impositivo_soportado(modo)
