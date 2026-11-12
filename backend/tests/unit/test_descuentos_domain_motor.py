"""Change 16, tarea 2.3: motor de descuentos (specs `descuentos/motor-de-descuentos` y
`descuentos/descuento-manual`; DSC-05, DSC-06, DSC-07, DSC-08, INV-03; `design.md` D7 a D11)."""

from __future__ import annotations

import itertools
from decimal import Decimal
from typing import Any

import pytest

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.errores import (
    DescuentoManualInvalidoError,
    LineaDescuentoInvalidaError,
    ReglaDescuentoInvalidaError,
)
from app.modules.descuentos.domain.motor import calcular_descuentos
from app.modules.descuentos.domain.tipos import AlcanceRegla, LineaVenta, ReglaDescuento


def _linea(
    id: str,
    bruto: str,
    *,
    cantidad_base: int = 1,
    unidades_referencia: int = 1,
    producto: str | None = None,
    manual: Any = None,
) -> LineaVenta:
    return LineaVenta(
        id=id,
        bruto=Decimal(bruto),
        cantidad_base=cantidad_base,
        unidades_referencia=unidades_referencia,
        producto_id=producto or f"prod-{id}",
        categoria_id="cat",
        marca_id="marca",
        descuento_manual=manual,
    )


def _pct(
    n: int,
    pct: str,
    *,
    prioridad: int = 1,
    acumulable: bool = False,
    medida: str = "UNIDADES_BASE",
    umbral: str = "1",
    alcances: tuple[AlcanceRegla, ...] = (),
) -> ReglaDescuento:
    return ReglaDescuento(
        id=f"{n:08d}",
        tipo="VOLUMEN_ALCANCE" if alcances else "VOLUMEN_OPERACION",
        medida=medida,  # type: ignore[arg-type]
        operador="GTE",
        umbral=Decimal(umbral),
        accion_tipo="PORCENTAJE",
        accion_porcentaje=Decimal(pct),
        accion_importe=None,
        acumulable=acumulable,
        prioridad=prioridad,
        alcances=alcances,
    )


def _fijo(
    n: int,
    importe: str,
    *,
    prioridad: int = 1,
    acumulable: bool = False,
) -> ReglaDescuento:
    return ReglaDescuento(
        id=f"{n:08d}",
        tipo="VOLUMEN_OPERACION",
        medida="UNIDADES_BASE",
        operador="GTE",
        umbral=Decimal("1"),
        accion_tipo="IMPORTE_FIJO",
        accion_porcentaje=None,
        accion_importe=Decimal(importe),
        acumulable=acumulable,
        prioridad=prioridad,
        alcances=(),
    )


def _importes(resultado: Any) -> list[list[str]]:
    return [[str(d.importe) for d in linea.descuentos] for linea in resultado.lineas]


# --- ganador único entre las no acumulables (D7, D8) -------------------------------------------


def test_gana_la_no_acumulable_de_mayor_beneficio_total_y_la_otra_no_se_aplica() -> None:
    a = _linea("a", "150000.00", cantidad_base=72, unidades_referencia=6, producto="pa")
    b = _linea("b", "86000.00", cantidad_base=60, unidades_referencia=6, producto="pb")
    r1 = _pct(1, "0.05", medida="CAJAS_EQUIVALENTES", umbral="20")  # 11800.00
    r2 = _pct(
        2,
        "0.08",
        prioridad=2,
        medida="CAJAS_EQUIVALENTES",
        umbral="10",
        alcances=(AlcanceRegla("PRODUCTO", "pa"),),
    )  # 12000.00

    resultado = calcular_descuentos([a, b], [r1, r2], None)

    assert _importes(resultado) == [["12000.00"], []]
    assert resultado.lineas[0].descuentos[0].regla_id == r2.id
    assert resultado.lineas[1].neto == Decimal("86000.00")


def test_gana_la_otra_cuando_el_beneficio_se_invierte() -> None:
    # Con Vino A de 100000.00 R2 da 8000.00 y R1 da 5000.00 + 4300.00 = 9300.00: gana R1.
    a = _linea("a", "100000.00", cantidad_base=72, unidades_referencia=6, producto="pa")
    b = _linea("b", "86000.00", cantidad_base=60, unidades_referencia=6, producto="pb")
    r1 = _pct(1, "0.05", medida="CAJAS_EQUIVALENTES", umbral="20")
    r2 = _pct(
        2,
        "0.08",
        prioridad=2,
        medida="CAJAS_EQUIVALENTES",
        umbral="10",
        alcances=(AlcanceRegla("PRODUCTO", "pa"),),
    )

    resultado = calcular_descuentos([a, b], [r2, r1], None)

    assert _importes(resultado) == [["5000.00"], ["4300.00"]]


def test_empate_de_beneficio_gana_la_prioridad_mas_baja_aunque_sea_mas_nueva() -> None:
    linea = _linea("a", "10000.00")
    vieja_prioridad_2 = _pct(1, "0.05", prioridad=2)
    nueva_prioridad_1 = _pct(2, "0.05", prioridad=1)

    resultado = calcular_descuentos([linea], [vieja_prioridad_2, nueva_prioridad_1], None)

    assert resultado.lineas[0].descuentos[0].regla_id == nueva_prioridad_1.id


def test_empate_de_beneficio_y_prioridad_gana_la_creada_primero_en_cualquier_orden() -> None:
    linea = _linea("a", "10000.00")
    primera = _pct(1, "0.05")
    segunda = _pct(2, "0.05")

    for reglas in itertools.permutations([primera, segunda]):
        resultado = calcular_descuentos([linea], list(reglas), None)
        assert resultado.lineas[0].descuentos[0].regla_id == primera.id


def test_una_regla_cuya_condicion_no_se_cumple_no_participa() -> None:
    linea = _linea("a", "10000.00", cantidad_base=10)
    no_cumple = _pct(1, "0.20", umbral="1000")
    cumple = _pct(2, "0.05")

    resultado = calcular_descuentos([linea], [no_cumple, cumple], None)

    assert _importes(resultado) == [["500.00"]]


# --- acumulables (D9) --------------------------------------------------------------------------


def test_acumulable_se_aplica_sobre_el_resultado_de_la_ganadora() -> None:
    a = _linea("a", "150000.00", cantidad_base=72, unidades_referencia=6, producto="pa")
    b = _linea("b", "86000.00", cantidad_base=60, unidades_referencia=6, producto="pb")
    ganadora = _pct(
        2,
        "0.08",
        medida="CAJAS_EQUIVALENTES",
        umbral="10",
        alcances=(AlcanceRegla("PRODUCTO", "pa"),),
    )
    acumulable = _pct(
        3, "0.02", prioridad=3, acumulable=True, medida="IMPORTE_BRUTO", umbral="200000"
    )

    resultado = calcular_descuentos([a, b], [acumulable, ganadora], None)

    assert _importes(resultado) == [["12000.00", "2760.00"], ["1720.00"]]
    assert [x.neto for x in resultado.lineas] == [Decimal("135240.00"), Decimal("84280.00")]
    assert resultado.lineas[0].descuento_total == Decimal("14760.00")


def test_dos_acumulables_se_encadenan_en_orden_de_prioridad_y_no_suman_porcentajes() -> None:
    linea = _linea("a", "10000.00")
    segunda = _pct(1, "0.02", prioridad=2, acumulable=True)
    primera = _pct(2, "0.08", prioridad=1, acumulable=True)

    resultado = calcular_descuentos([linea], [segunda, primera], None)

    assert [d.regla_id for d in resultado.lineas[0].descuentos] == [primera.id, segunda.id]
    assert _importes(resultado) == [["800.00", "184.00"]]
    assert resultado.lineas[0].neto == Decimal("9016.00")


def test_acumulables_con_igual_prioridad_se_ordenan_por_antiguedad() -> None:
    linea = _linea("a", "10000.00")
    vieja = _pct(1, "0.08", acumulable=True)
    nueva = _pct(2, "0.02", acumulable=True)

    resultado = calcular_descuentos([linea], [nueva, vieja], None)

    assert [d.regla_id for d in resultado.lineas[0].descuentos] == [vieja.id, nueva.id]


def test_la_condicion_de_una_acumulable_mira_el_bruto_no_lo_ya_descontado() -> None:
    a = _linea("a", "150000.00")
    b = _linea("b", "86000.00")
    ganadora = _fijo(1, "38000.00")  # deja la venta en 198000.00
    acumulable = _pct(
        2, "0.02", prioridad=2, acumulable=True, medida="IMPORTE_BRUTO", umbral="200000"
    )

    resultado = calcular_descuentos([a, b], [ganadora, acumulable], None)

    assert _importes(resultado) == [["24152.54", "2516.95"], ["13847.46", "1443.05"]]


def test_importe_fijo_acumulable_se_reparte_sobre_el_resultado_anterior() -> None:
    a = _linea("a", "135240.00")
    b = _linea("b", "84280.00")
    resultado = calcular_descuentos([a, b], [_fijo(1, "1000.00", acumulable=True)], None)
    assert _importes(resultado) == [["616.07"], ["383.93"]]


def test_descuento_de_importe_cero_no_se_informa() -> None:
    chica = _linea("chica", "0.05")
    grande = _linea("grande", "100.00")

    resultado = calcular_descuentos([chica, grande], [_pct(1, "0.05")], None)

    assert resultado.lineas[0].descuentos == ()
    assert resultado.lineas[0].neto == Decimal("0.05")
    assert _importes(resultado)[1] == ["5.00"]


def test_neto_nunca_negativo_con_importe_fijo_mayor_y_acumulable_posterior() -> None:
    linea = _linea("a", "100.00")
    resultado = calcular_descuentos(
        [linea],
        [_fijo(1, "500.00", acumulable=True), _pct(2, "0.50", prioridad=2, acumulable=True)],
        None,
    )
    assert resultado.lineas[0].neto == Decimal("0.00")
    assert _importes(resultado) == [["100.00"]]


def test_sin_reglas_ni_manual_cada_linea_queda_en_su_bruto() -> None:
    lineas = [_linea("a", "100.00"), _linea("b", "250.50")]
    resultado = calcular_descuentos(lineas, [], None)
    assert [x.neto for x in resultado.lineas] == [Decimal("100.00"), Decimal("250.50")]
    assert [x.descuento_total for x in resultado.lineas] == [Decimal("0.00"), Decimal("0.00")]
    assert resultado.porcentaje_manual_maximo is None


# --- detalle por línea (DSC-08) ----------------------------------------------------------------


def test_el_detalle_lleva_origen_regla_porcentaje_e_importe() -> None:
    linea = _linea("a", "10000.00")
    resultado = calcular_descuentos(
        [linea], [_pct(1, "0.05"), _fijo(2, "100.00", prioridad=2, acumulable=True)], None
    )

    porcentual, fijo = resultado.lineas[0].descuentos
    assert (porcentual.origen, porcentual.regla_id, porcentual.porcentaje, porcentual.importe) == (
        "AUTOMATICO",
        "00000001",
        Decimal("0.050000"),
        Decimal("500.00"),
    )
    assert (fijo.origen, fijo.regla_id, fijo.porcentaje, fijo.importe) == (
        "AUTOMATICO",
        "00000002",
        None,
        Decimal("100.00"),
    )


# --- descuento manual, paso 5 (D11) ------------------------------------------------------------


def test_manual_general_se_aplica_sobre_el_resultado_de_los_automaticos() -> None:
    a = _linea("a", "135240.00")
    b = _linea("b", "84280.00")
    resultado = calcular_descuentos([a, b], [], Decimal("0.10"))
    assert _importes(resultado) == [["13524.00"], ["8428.00"]]
    assert [x.neto for x in resultado.lineas] == [Decimal("121716.00"), Decimal("75852.00")]
    assert resultado.porcentaje_manual_maximo == Decimal("0.100000")


def test_manual_va_despues_de_los_automaticos_y_es_el_ultimo_de_la_linea() -> None:
    linea = _linea("a", "10000.00")
    resultado = calcular_descuentos([linea], [_pct(1, "0.05")], Decimal("0.10"))
    origenes = [d.origen for d in resultado.lineas[0].descuentos]
    assert origenes == ["AUTOMATICO", "MANUAL"]
    manual = resultado.lineas[0].descuentos[1]
    assert (manual.regla_id, manual.porcentaje, manual.importe) == (
        None,
        Decimal("0.100000"),
        Decimal("950.00"),
    )


def test_propio_de_la_linea_reemplaza_al_general_mayor() -> None:
    a = _linea("a", "135240.00", manual=Decimal("0.10"))
    b = _linea("b", "84280.00")
    resultado = calcular_descuentos([a, b], [], Decimal("0.05"))
    assert _importes(resultado) == [["13524.00"], ["4214.00"]]
    assert resultado.porcentaje_manual_maximo == Decimal("0.100000")
    assert len(resultado.lineas[0].descuentos) == 1


def test_propio_menor_que_el_general_tambien_lo_reemplaza() -> None:
    a = _linea("a", "135240.00")
    b = _linea("b", "84280.00", manual=Decimal("0.03"))
    resultado = calcular_descuentos([a, b], [], Decimal("0.10"))
    assert _importes(resultado) == [["13524.00"], ["2528.40"]]
    assert resultado.lineas[1].neto == Decimal("81751.60")
    assert resultado.porcentaje_manual_maximo == Decimal("0.100000")


def test_solo_propio_sin_general_deja_las_demas_lineas_sin_manual() -> None:
    a = _linea("a", "135240.00", manual=Decimal("0.10"))
    b = _linea("b", "84280.00")
    resultado = calcular_descuentos([a, b], [], None)
    assert _importes(resultado) == [["13524.00"], []]
    assert resultado.porcentaje_manual_maximo == Decimal("0.100000")


def test_general_reemplazado_en_todas_las_lineas_no_cuenta_para_el_maximo() -> None:
    a = _linea("a", "135240.00", manual=Decimal("0.03"))
    b = _linea("b", "84280.00", manual=Decimal("0.02"))
    resultado = calcular_descuentos([a, b], [], Decimal("0.10"))
    assert _importes(resultado) == [["4057.20"], ["1685.60"]]
    assert resultado.porcentaje_manual_maximo == Decimal("0.030000")


def test_sin_general_ni_propios_el_maximo_es_nulo() -> None:
    resultado = calcular_descuentos([_linea("a", "100.00")], [_pct(1, "0.05")], None)
    assert resultado.porcentaje_manual_maximo is None
    assert [d.origen for d in resultado.lineas[0].descuentos] == ["AUTOMATICO"]


def test_manual_de_importe_cero_no_se_informa_ni_cuenta_para_el_maximo() -> None:
    cero = _linea("cero", "0.00")
    cien = _linea("cien", "100.00")
    resultado = calcular_descuentos([cero, cien], [], Decimal("0.05"))
    assert resultado.lineas[0].descuentos == ()
    assert _importes(resultado) == [[], ["5.00"]]
    assert resultado.porcentaje_manual_maximo == Decimal("0.050000")


@pytest.mark.parametrize(
    "invalido",
    [
        Decimal("0"),
        Decimal("-0.05"),
        Decimal("1.000001"),
        Decimal("0.0500001"),
        0.05,
        1,
        "0.05",
        True,
    ],
)
def test_general_fuera_de_dominio_se_rechaza(invalido: Any) -> None:
    with pytest.raises(DescuentoManualInvalidoError) as error:
        calcular_descuentos([_linea("a", "100.00")], [], invalido)
    assert error.value.codigo == "DESCUENTO_MANUAL_INVALIDO"


@pytest.mark.parametrize(
    "invalido",
    [Decimal("0"), Decimal("-0.05"), Decimal("1.000001"), Decimal("0.0500001"), 0.05],
)
def test_propio_fuera_de_dominio_se_rechaza_para_toda_la_venta(invalido: Any) -> None:
    lineas = [_linea("a", "100.00", manual=invalido), _linea("b", "100.00")]
    with pytest.raises(DescuentoManualInvalidoError):
        calcular_descuentos(lineas, [], Decimal("0.05"))


@pytest.mark.parametrize(
    "valido", [Decimal("1"), Decimal("1.000000"), Decimal("0.000001"), Decimal("0.123456")]
)
def test_los_extremos_del_dominio_del_manual_se_aceptan(valido: Decimal) -> None:
    resultado = calcular_descuentos([_linea("a", "1000000.00")], [], valido)
    assert resultado.porcentaje_manual_maximo == valido


# --- entradas inválidas y determinismo ---------------------------------------------------------


def test_bruto_de_punto_flotante_se_rechaza() -> None:
    linea = _linea("a", "100.00")
    flotante = LineaVenta(**{**linea.__dict__, "bruto": 31250.5})
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_descuentos([flotante], [], None)


@pytest.mark.parametrize("campo", ["cantidad_base", "unidades_referencia"])
@pytest.mark.parametrize("valor", [0, -1, 1.5, True])
def test_cantidad_y_unidades_de_referencia_deben_ser_enteros_positivos(
    campo: str, valor: Any
) -> None:
    linea = _linea("a", "100.00")
    mala = LineaVenta(**{**linea.__dict__, campo: valor})
    with pytest.raises(LineaDescuentoInvalidaError):
        calcular_descuentos([mala], [], None)


def test_porcentaje_de_regla_de_punto_flotante_se_rechaza() -> None:
    regla = _pct(1, "0.05")
    flotante = ReglaDescuento(**{**regla.__dict__, "accion_porcentaje": 0.05})
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_descuentos([_linea("a", "100.00")], [flotante], None)


def test_regla_con_tipo_desconocido_se_rechaza() -> None:
    regla = _pct(1, "0.05")
    rara = ReglaDescuento(**{**regla.__dict__, "medida": "HISTORIAL_DE_COMPRAS"})
    with pytest.raises(ReglaDescuentoInvalidaError):
        calcular_descuentos([_linea("a", "100.00")], [rara], None)


def test_el_resultado_no_depende_del_orden_de_las_reglas_ni_de_los_alcances() -> None:
    a = _linea("a", "150000.00", cantidad_base=72, unidades_referencia=6, producto="pa")
    b = _linea("b", "86000.00", cantidad_base=60, unidades_referencia=6, producto="pb")
    alcances = (AlcanceRegla("PRODUCTO", "pa"), AlcanceRegla("MARCA", "marca-x"))
    reglas = [
        _pct(1, "0.05", medida="CAJAS_EQUIVALENTES", umbral="20"),
        _pct(2, "0.08", prioridad=2, medida="CAJAS_EQUIVALENTES", umbral="10", alcances=alcances),
        _pct(3, "0.02", prioridad=3, acumulable=True, medida="IMPORTE_BRUTO", umbral="200000"),
        _fijo(5, "1000.00", prioridad=4, acumulable=True),
    ]
    referencia = calcular_descuentos([a, b], reglas, Decimal("0.05"))

    for orden in itertools.permutations(reglas):
        assert calcular_descuentos([a, b], list(orden), Decimal("0.05")) == referencia

    inversa = [
        ReglaDescuento(**{**r.__dict__, "alcances": tuple(reversed(r.alcances))}) for r in reglas
    ]
    assert calcular_descuentos([a, b], inversa, Decimal("0.05")) == referencia
