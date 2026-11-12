"""Change 16, tarea 4.1: propiedades del motor de descuentos con Hypothesis (sin base de datos;
`docs/02-arquitectura.md` §15). Citan DSC-05, DSC-06, DSC-07, INV-03.

Para ventas y reglas válidas generadas: ningún neto negativo y todo importe con 2 decimales (a);
neto = bruto menos sus descuentos (b); a lo sumo una no acumulable en el resultado (c); el
resultado no cambia al permutar las reglas ni sus alcances (d); un importe fijo reparte
exactamente lo aplicado y nunca más que las líneas (e); una línea no elegible conserva su bruto
(f, g); a lo sumo un descuento `MANUAL` por línea, el último, con el porcentaje que corresponde
(h); `porcentaje_manual_maximo` es el mayor de los `MANUAL` informados (i); agregar un porcentaje
propio a una línea no cambia a las demás (j)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.descuentos.domain.acciones import repartir_importe_fijo
from app.modules.descuentos.domain.condicion import cumple_condicion, lineas_elegibles
from app.modules.descuentos.domain.motor import calcular_descuentos
from app.modules.descuentos.domain.tipos import (
    AlcanceRegla,
    LineaVenta,
    ReglaDescuento,
)

_DOS = Decimal("0.01")

_BRUTOS = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("99999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)
_PORCENTAJES = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)
_MANUAL = st.one_of(st.none(), _PORCENTAJES)
_IMPORTES_FIJOS = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("60000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

_ALCANCES = st.lists(
    st.one_of(
        st.builds(AlcanceRegla, st.just("PRODUCTO"), st.sampled_from(["p1", "p2", "p3"])),
        st.builds(AlcanceRegla, st.just("CATEGORIA"), st.sampled_from(["c1", "c2"])),
        st.builds(AlcanceRegla, st.just("MARCA"), st.sampled_from(["m1", "m2"])),
    ),
    min_size=1,
    max_size=3,
)


@st.composite
def _lineas(draw: Any, con_manual_propio: bool = True) -> list[LineaVenta]:
    cantidad = draw(st.integers(min_value=1, max_value=6))
    lineas = []
    for i in range(cantidad):
        lineas.append(
            LineaVenta(
                id=f"l{i}",
                bruto=draw(_BRUTOS),
                cantidad_base=draw(st.integers(min_value=1, max_value=200)),
                unidades_referencia=draw(st.sampled_from([1, 6, 12])),
                producto_id=draw(st.sampled_from(["p1", "p2", "p3"])),
                categoria_id=draw(st.sampled_from(["c1", "c2"])),
                marca_id=draw(st.sampled_from(["m1", "m2"])),
                descuento_manual=draw(_MANUAL) if con_manual_propio else None,
            )
        )
    return lineas


@st.composite
def _regla(draw: Any, indice: int) -> ReglaDescuento:
    medida = draw(st.sampled_from(["CAJAS_EQUIVALENTES", "UNIDADES_BASE", "IMPORTE_BRUTO"]))
    if medida == "UNIDADES_BASE":
        umbral = Decimal(draw(st.integers(min_value=1, max_value=300)))
    elif medida == "IMPORTE_BRUTO":
        umbral = draw(
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=Decimal("200000.00"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            )
        )
    else:
        umbral = draw(
            st.decimals(
                min_value=Decimal("0.0001"),
                max_value=Decimal("60"),
                allow_nan=False,
                allow_infinity=False,
                places=4,
            )
        )
    es_alcance = draw(st.booleans())
    accion = draw(st.sampled_from(["PORCENTAJE", "IMPORTE_FIJO"]))
    return ReglaDescuento(
        id=f"{indice:04d}",
        tipo="VOLUMEN_ALCANCE" if es_alcance else "VOLUMEN_OPERACION",
        medida=medida,
        operador=draw(st.sampled_from(["GTE", "GT"])),
        umbral=umbral,
        accion_tipo=accion,
        accion_porcentaje=draw(_PORCENTAJES) if accion == "PORCENTAJE" else None,
        accion_importe=draw(_IMPORTES_FIJOS) if accion == "IMPORTE_FIJO" else None,
        acumulable=draw(st.booleans()),
        prioridad=draw(st.integers(min_value=1, max_value=3)),
        alcances=tuple(draw(_ALCANCES)) if es_alcance else (),
    )


@st.composite
def _reglas(draw: Any) -> list[ReglaDescuento]:
    cantidad = draw(st.integers(min_value=0, max_value=5))
    return [draw(_regla(i)) for i in range(cantidad)]


def _dos_decimales(valor: Decimal) -> bool:
    return valor == valor.quantize(_DOS) and valor.as_tuple().exponent == -2


@settings(deadline=None)
@given(lineas=_lineas(), reglas=_reglas(), general=_MANUAL)
def test_dsc05_a_b_neto_no_negativo_con_dos_decimales_y_es_bruto_menos_descuentos(
    lineas: list[LineaVenta], reglas: list[ReglaDescuento], general: Decimal | None
) -> None:
    resultado = calcular_descuentos(lineas, reglas, general)

    assert [x.id for x in resultado.lineas] == [x.id for x in lineas]
    for linea, salida in zip(lineas, resultado.lineas, strict=True):
        assert salida.neto >= 0
        assert _dos_decimales(salida.neto)
        assert _dos_decimales(salida.descuento_total)
        assert all(_dos_decimales(d.importe) and d.importe > 0 for d in salida.descuentos)
        # (b) neto = bruto - suma de sus descuentos
        assert salida.neto == linea.bruto - sum((d.importe for d in salida.descuentos), Decimal(0))
        assert salida.descuento_total == sum((d.importe for d in salida.descuentos), Decimal(0))


@settings(deadline=None)
@given(lineas=_lineas(), reglas=_reglas(), general=_MANUAL)
def test_dsc05_c_a_lo_sumo_una_no_acumulable_figura_en_el_resultado(
    lineas: list[LineaVenta], reglas: list[ReglaDescuento], general: Decimal | None
) -> None:
    resultado = calcular_descuentos(lineas, reglas, general)
    no_acumulables = {r.id for r in reglas if not r.acumulable}

    aplicadas = {
        d.regla_id
        for salida in resultado.lineas
        for d in salida.descuentos
        if d.regla_id in no_acumulables
    }
    assert len(aplicadas) <= 1


@settings(deadline=None)
@given(
    lineas=_lineas(),
    reglas=_reglas(),
    general=_MANUAL,
    datos=st.data(),
)
def test_dsc05_d_el_resultado_no_cambia_al_permutar_reglas_ni_alcances(
    lineas: list[LineaVenta],
    reglas: list[ReglaDescuento],
    general: Decimal | None,
    datos: st.DataObject,
) -> None:
    referencia = calcular_descuentos(lineas, reglas, general)

    permutadas = datos.draw(st.permutations(reglas))
    con_alcances_permutados = [
        replace(r, alcances=tuple(datos.draw(st.permutations(list(r.alcances)))))
        for r in permutadas
    ]

    assert calcular_descuentos(lineas, con_alcances_permutados, general) == referencia


@given(
    importes=st.lists(
        st.decimals(
            min_value=Decimal("0.00"),
            max_value=Decimal("99999.99"),
            allow_nan=False,
            allow_infinity=False,
            places=2,
        ),
        min_size=1,
        max_size=8,
    ),
    fijo=_IMPORTES_FIJOS,
)
def test_dsc07_e_importe_fijo_reparte_exactamente_lo_aplicado_sin_pasarse_de_las_lineas(
    importes: list[Decimal], fijo: Decimal
) -> None:
    partes = repartir_importe_fijo(importes, fijo)

    total = sum(importes, Decimal(0))
    assert sum(partes, Decimal(0)) == min(fijo, total)
    assert sum(partes, Decimal(0)) <= total
    for parte, importe in zip(partes, importes, strict=True):
        assert _dos_decimales(parte)
        assert 0 <= parte <= importe


@settings(deadline=None)
@given(lineas=_lineas(con_manual_propio=False), regla=_regla(0))
def test_dsc05_e_una_regla_de_importe_fijo_en_el_motor_descuenta_lo_aplicado(
    lineas: list[LineaVenta], regla: ReglaDescuento
) -> None:
    fija = replace(
        regla, accion_tipo="IMPORTE_FIJO", accion_porcentaje=None, accion_importe=Decimal("1234.56")
    )

    resultado = calcular_descuentos(lineas, [fija], None)

    descontado = sum((s.descuento_total for s in resultado.lineas), Decimal(0))
    if cumple_condicion(fija, lineas):
        elegibles = sum((x.bruto for x in lineas_elegibles(fija, lineas)), Decimal(0))
        assert descontado == min(Decimal("1234.56"), elegibles)
    else:
        assert descontado == 0


@settings(deadline=None)
@given(lineas=_lineas(con_manual_propio=False), reglas=_reglas())
def test_dsc05_f_una_linea_solo_recibe_descuentos_de_reglas_que_la_cubren(
    lineas: list[LineaVenta], reglas: list[ReglaDescuento]
) -> None:
    resultado = calcular_descuentos(lineas, reglas, None)
    por_id = {r.id: r for r in reglas}

    for linea, salida in zip(lineas, resultado.lineas, strict=True):
        for descuento in salida.descuentos:
            regla = por_id[descuento.regla_id or ""]
            assert cumple_condicion(regla, lineas)
            assert linea in lineas_elegibles(regla, lineas)
        cubierta = any(
            cumple_condicion(r, lineas) and linea in lineas_elegibles(r, lineas) for r in reglas
        )
        if not cubierta:
            assert salida.neto == linea.bruto
            assert salida.descuentos == ()


@given(lineas=_lineas(con_manual_propio=False))
def test_dsc05_g_sin_reglas_ni_manual_el_neto_es_el_bruto(lineas: list[LineaVenta]) -> None:
    resultado = calcular_descuentos(lineas, [], None)

    assert [s.neto for s in resultado.lineas] == [x.bruto for x in lineas]
    assert all(s.descuentos == () for s in resultado.lineas)
    assert resultado.porcentaje_manual_maximo is None


@settings(deadline=None)
@given(lineas=_lineas(), reglas=_reglas(), general=_MANUAL)
def test_dsc05_h_i_un_solo_manual_por_linea_ultimo_con_el_porcentaje_que_corresponde(
    lineas: list[LineaVenta], reglas: list[ReglaDescuento], general: Decimal | None
) -> None:
    resultado = calcular_descuentos(lineas, reglas, general)

    informados: list[Decimal] = []
    for linea, salida in zip(lineas, resultado.lineas, strict=True):
        manuales = [d for d in salida.descuentos if d.origen == "MANUAL"]
        assert len(manuales) <= 1
        if manuales:
            assert salida.descuentos[-1] is manuales[0]
            esperado = linea.descuento_manual if linea.descuento_manual is not None else general
            assert esperado is not None
            assert manuales[0].regla_id is None
            assert manuales[0].porcentaje == esperado
            informados.append(manuales[0].porcentaje or Decimal(0))
    # (i) el máximo es el mayor de los MANUAL informados, o nulo si no hay ninguno
    assert resultado.porcentaje_manual_maximo == (max(informados) if informados else None)


@settings(deadline=None)
@given(
    lineas=_lineas(),
    reglas=_reglas(),
    general=_MANUAL,
    propio=_PORCENTAJES,
    posicion=st.integers(min_value=0, max_value=5),
)
def test_dsc05_j_agregar_un_propio_a_una_linea_no_cambia_a_las_demas(
    lineas: list[LineaVenta],
    reglas: list[ReglaDescuento],
    general: Decimal | None,
    propio: Decimal,
    posicion: int,
) -> None:
    elegida = posicion % len(lineas)
    antes = calcular_descuentos(lineas, reglas, general)
    modificadas = [
        replace(linea, descuento_manual=propio) if i == elegida else linea
        for i, linea in enumerate(lineas)
    ]

    despues = calcular_descuentos(modificadas, reglas, general)

    for i, (antigua, nueva) in enumerate(zip(antes.lineas, despues.lineas, strict=True)):
        if i != elegida:
            assert nueva == antigua
