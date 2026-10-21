"""Change 18a, tarea 1.2: ejecuta contra `app.modules.ventas.domain.calculo` los casos compartidos
de `shared/fixtures/calculo/vta-04-totales.json` cuya entrada declara `"motor": "vta04"`
(VTA-04, PRC-22, DSC-05, INV-14, TR-03; `design.md` D13 y D14; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/vta04.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.descuentos.domain.tipos import AlcanceRegla, ReglaDescuento
from app.modules.ventas.domain.calculo import LineaCalculo, calcular_venta

_CASOS_VTA04 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "vta04"]

if not _CASOS_VTA04:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "vta04" en '
        "shared/fixtures/calculo/ -- el arnés del motor de venta quedaría mudo"
    )


def _decimal_o_crudo(valor: Any) -> Any:
    """Una cadena entra como `Decimal` exacto; todo lo demás (nulo, número JSON) entra tal cual,
    para que el motor rechace un punto flotante (INV-03)."""
    return Decimal(valor) if isinstance(valor, str) else valor


def _linea(bruto: dict[str, Any]) -> LineaCalculo:
    return LineaCalculo(
        id=bruto["id"],
        precio_referencia=_decimal_o_crudo(bruto["precio_referencia"]),
        unidades_referencia=bruto["unidades_referencia"],
        cantidad_base=bruto["cantidad_base"],
        alicuota=_decimal_o_crudo(bruto["alicuota"]),
        producto_id=bruto["producto_id"],
        categoria_id=bruto["categoria_id"],
        marca_id=bruto["marca_id"],
        descuento_manual=_decimal_o_crudo(bruto["descuento_manual"]),
    )


def _regla(bruto: dict[str, Any]) -> ReglaDescuento:
    return ReglaDescuento(
        id=bruto["id"],
        tipo=bruto["tipo"],
        medida=bruto["medida"],
        operador=bruto["operador"],
        umbral=Decimal(bruto["umbral"]),
        accion_tipo=bruto["accion_tipo"],
        accion_porcentaje=_decimal_o_crudo(bruto["accion_porcentaje"]),
        accion_importe=_decimal_o_crudo(bruto["accion_importe"]),
        acumulable=bruto["acumulable"],
        prioridad=bruto["prioridad"],
        alcances=tuple(AlcanceRegla(a["tipo"], a["entidad_id"]) for a in bruto["alcances"]),
    )


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    resultado = calcular_venta(
        entrada["modo_impositivo"],
        [_linea(linea) for linea in entrada["lineas"]],
        [_regla(regla) for regla in entrada["reglas_descuento"]],
        _decimal_o_crudo(entrada["descuento_manual_general"]),
    )
    return {
        "lineas": [
            {
                "id": linea.id,
                "bruto": f"{linea.bruto:.2f}",
                "descuento_total": f"{linea.descuento_total:.2f}",
                "neto": f"{linea.neto:.2f}",
                "alicuota": f"{linea.alicuota:.6f}",
                "iva": f"{linea.importe_iva:.2f}",
            }
            for linea in resultado.lineas
        ],
        "total_neto": f"{resultado.total_neto:.2f}",
        "total_iva": f"{resultado.total_iva:.2f}",
        "total": f"{resultado.total:.2f}",
    }


def _verificar(entrada: dict[str, Any], salida_esperada: dict[str, Any]) -> None:
    """La comparación de cada caso compartido: lo que calcula el motor debe ser EXACTAMENTE la
    salida esperada del caso (o fallar con el error que el caso declara)."""
    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(entrada) == salida_esperada


# Escenario: "Una línea en modo A"
# Escenario: "La orquestación aplica las reglas que recibe"
# Escenario: "Modos B y C no soportados"
@pytest.mark.parametrize("caso", _CASOS_VTA04, ids=[caso.id for caso in _CASOS_VTA04])
def test_caso_compartido_de_vta04(caso: Any) -> None:
    """Escenarios "Una línea en modo A" (`VTA04-una-linea-modo-a-quince-botellas`), "La
    orquestación aplica las reglas que recibe" (`VTA04-regla-de-cinco-por-ciento-...`), "Modos B y
    C no soportados" (`VTA04-modo-b-...` y `VTA04-modo-c-...`) y "Ambas suites ejecutan los
    casos": cada caso `vta04` es una prueba identificable por su `id` (ADR-016)."""
    _verificar(caso.entrada, caso.salida_esperada)


def test_los_casos_vta04_tienen_id_unico_y_estan_los_de_la_spec() -> None:
    """Escenario "Ambas suites ejecutan los casos": el `id` identifica a cada caso (sin
    repetirse, porque dos pruebas con el mismo nombre ocultarían una) y están los de la spec."""
    ids = [caso.id for caso in _CASOS_VTA04]

    assert len(ids) == len(set(ids))
    assert {
        "VTA04-una-linea-modo-a-quince-botellas",
        "VTA04-regla-de-cinco-por-ciento-pasa-por-el-motor-de-descuentos",
        "VTA04-modo-b-no-soportado",
        "VTA04-modo-c-no-soportado",
    } <= set(ids)


def test_una_divergencia_entre_lo_esperado_y_lo_calculado_hace_fallar_la_suite() -> None:
    """Escenario "Una divergencia hace fallar CI": un caso `vta04` cuyo total esperado no
    coincide con lo que calcula el motor falla, y el mismo caso con el total correcto pasa."""
    caso = next(c for c in _CASOS_VTA04 if c.id == "VTA04-una-linea-modo-a-quince-botellas")
    esperada = caso.salida_esperada
    divergente = {**esperada, "total": "31250.01"}

    _verificar(caso.entrada, esperada)
    with pytest.raises(AssertionError):
        _verificar(caso.entrada, divergente)
    con_error_distinto = {"error": "MODO_IMPOSITIVO_NO_SOPORTADO"}
    with pytest.raises(pytest.fail.Exception):  # el motor no lanzó el error que el caso espera
        _verificar(caso.entrada, con_error_distinto)
