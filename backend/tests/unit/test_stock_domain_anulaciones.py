"""Tarea 9.1 (change 14, `design.md` D5, D5.1, D5.2, D5.4): reglas puras de la anulación de
transferencias y ajustes.

`validar_anulable`, `puede_anular_transferencia`, `validar_motivo_de_anulacion` y la expansión
inversa de una transferencia y de un ajuste en las líneas del libro (mismos tipos, otro
origen, costo del movimiento original). Dominio puro: sin base de datos.

Reglas citadas: STK-03, STK-07, STK-08, CST-12, TR-06, TR-09, INV-12, INV-15.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.stock.domain.anulaciones import (
    LineaDeAjusteOriginal,
    MovimientoOriginal,
    expandir_anulacion_ajuste,
    expandir_anulacion_transferencia,
    puede_anular_transferencia,
    validar_anulable,
    validar_motivo_de_anulacion,
)
from app.modules.stock.domain.errores import (
    AjusteYaAnuladoError,
    CostoInvalidoError,
    MotivoInvalidoError,
    TransferenciaYaAnuladaError,
)
from app.modules.stock.domain.movimientos import (
    AJUSTE,
    ORIGEN_AJUSTE,
    ORIGEN_ANULACION_AJUSTE,
    ORIGEN_ANULACION_TRANSFERENCIA,
    ORIGEN_TRANSFERENCIA,
    TRANSFERENCIA_ENTRADA,
    TRANSFERENCIA_SALIDA,
    LineaDeMovimiento,
    puede_quedar_negativo,
    validar_lineas_de_movimiento,
)
from app.modules.stock.domain.operaciones import (
    LineaDeOperacion,
    expandir_ajuste,
    expandir_transferencia,
    validar_ajuste,
    validar_transferencia,
)

DEPOSITO = uuid4()
CAMIONETA = uuid4()
MOTIVO_DEL_AJUSTE = uuid4()
MOTIVO_DE_ANULACION = uuid4()
VINO = uuid4()
AGUA = uuid4()

TRANSFERIR = "TRANSFERIR_STOCK"
ANULAR_AJENAS = "ANULAR_TRANSFERENCIA"


# --- validar_anulable ---------------------------------------------------------------------


@pytest.mark.parametrize("operacion", ["TRANSFERENCIA", "AJUSTE"])
def test_una_operacion_confirmada_se_puede_anular(operacion: str) -> None:
    validar_anulable("CONFIRMADA", operacion=operacion)


def test_una_transferencia_anulada_no_se_anula_dos_veces() -> None:
    with pytest.raises(TransferenciaYaAnuladaError) as error:
        validar_anulable("ANULADA", operacion="TRANSFERENCIA")

    assert (error.value.codigo, error.value.status_http) == ("TRANSFERENCIA_YA_ANULADA", 409)


def test_un_ajuste_anulado_no_se_anula_dos_veces() -> None:
    with pytest.raises(AjusteYaAnuladoError) as error:
        validar_anulable("ANULADA", operacion="AJUSTE")

    assert (error.value.codigo, error.value.status_http) == ("AJUSTE_YA_ANULADO", 409)


# --- puede_anular_transferencia (D5 punto 5, D5.4) ----------------------------------------


def test_el_creador_con_transferir_stock_anula_la_propia() -> None:
    yo = uuid4()
    assert puede_anular_transferencia(yo, yo, {TRANSFERIR}) is True


def test_con_transferir_stock_no_se_anula_la_de_otro() -> None:
    assert puede_anular_transferencia(uuid4(), uuid4(), {TRANSFERIR}) is False


def test_con_el_permiso_de_anular_ajenas_se_anula_la_de_otro() -> None:
    assert puede_anular_transferencia(uuid4(), uuid4(), {TRANSFERIR, ANULAR_AJENAS}) is True


def test_anular_ajenas_sin_transferir_stock_no_alcanza_ni_para_la_ajena_ni_para_la_propia() -> None:
    """D5.4: `TRANSFERIR_STOCK` es siempre necesario; el otro permiso solo agrega alcance."""
    yo = uuid4()
    assert puede_anular_transferencia(uuid4(), uuid4(), {ANULAR_AJENAS}) is False
    assert puede_anular_transferencia(yo, yo, {ANULAR_AJENAS}) is False


def test_sin_permisos_no_se_anula_ni_la_propia() -> None:
    yo = uuid4()
    assert puede_anular_transferencia(yo, yo, frozenset()) is False


# --- validar_motivo_de_anulacion (TR-09) --------------------------------------------------


def test_el_motivo_activo_del_ambito_correcto_pasa() -> None:
    validar_motivo_de_anulacion(
        activo=True, ambito="ANULACION_TRANSFERENCIA", ambito_esperado="ANULACION_TRANSFERENCIA"
    )
    validar_motivo_de_anulacion(
        activo=True, ambito="ANULACION_AJUSTE", ambito_esperado="ANULACION_AJUSTE"
    )


@pytest.mark.parametrize(
    ("activo", "ambito", "esperado"),
    [
        (False, "ANULACION_TRANSFERENCIA", "ANULACION_TRANSFERENCIA"),
        (True, "AJUSTE_STOCK", "ANULACION_AJUSTE"),
        (True, "ANULACION_AJUSTE", "ANULACION_TRANSFERENCIA"),
        (True, "ANULACION_TRANSFERENCIA", "ANULACION_AJUSTE"),
    ],
)
def test_un_motivo_inactivo_o_de_otro_ambito_es_invalido(
    activo: bool, ambito: str, esperado: str
) -> None:
    with pytest.raises(MotivoInvalidoError) as error:
        validar_motivo_de_anulacion(activo=activo, ambito=ambito, ambito_esperado=esperado)

    assert (error.value.codigo, error.value.status_http) == ("MOTIVO_INVALIDO", 422)


# --- expansión inversa de una transferencia (D5.1, D5.2) ----------------------------------


def _salida(producto: UUID, cantidad: int, costo: str | None) -> MovimientoOriginal:
    return MovimientoOriginal(
        producto_id=producto,
        ubicacion_id=DEPOSITO,
        cantidad_base=-cantidad,
        tipo=TRANSFERENCIA_SALIDA,
        costo_unitario=None if costo is None else Decimal(costo),
    )


def _entrada(producto: UUID, cantidad: int, costo: str | None) -> MovimientoOriginal:
    return MovimientoOriginal(
        producto_id=producto,
        ubicacion_id=CAMIONETA,
        cantidad_base=cantidad,
        tipo=TRANSFERENCIA_ENTRADA,
        costo_unitario=None if costo is None else Decimal(costo),
    )


def test_la_anulacion_saca_del_destino_y_devuelve_al_origen_al_costo_original() -> None:
    inversos = expandir_anulacion_transferencia(
        transferencia_id=(transferencia := uuid4()),
        lineas=[LineaDeOperacion(VINO, 48)],
        originales=[_salida(VINO, 48, "1050.000000"), _entrada(VINO, 48, "1050.000000")],
    )

    assert inversos == [
        LineaDeMovimiento(
            producto_id=VINO,
            ubicacion_id=CAMIONETA,
            cantidad_base=-48,
            tipo=TRANSFERENCIA_SALIDA,
            costo_unitario=Decimal("1050.000000"),
            origen_tipo=ORIGEN_ANULACION_TRANSFERENCIA,
            origen_id=transferencia,
        ),
        LineaDeMovimiento(
            producto_id=VINO,
            ubicacion_id=DEPOSITO,
            cantidad_base=48,
            tipo=TRANSFERENCIA_ENTRADA,
            costo_unitario=Decimal("1050.000000"),
            origen_tipo=ORIGEN_ANULACION_TRANSFERENCIA,
            origen_id=transferencia,
        ),
    ]


def test_cada_inverso_lleva_el_costo_de_su_propio_original_y_nulo_si_era_nulo() -> None:
    """Dos líneas con costos distintos, una de ellas sin costo (producto sin promedio):
    el orden es el de las líneas y cada movimiento repite el suyo."""
    inversos = expandir_anulacion_transferencia(
        transferencia_id=uuid4(),
        lineas=[LineaDeOperacion(AGUA, 24), LineaDeOperacion(VINO, 6)],
        originales=[
            _salida(VINO, 6, "1050.000000"),
            _entrada(VINO, 6, "1050.000000"),
            _salida(AGUA, 24, None),
            _entrada(AGUA, 24, None),
        ],
    )

    assert [(m.producto_id, m.ubicacion_id, m.cantidad_base) for m in inversos] == [
        (AGUA, CAMIONETA, -24),
        (AGUA, DEPOSITO, 24),
        (VINO, CAMIONETA, -6),
        (VINO, DEPOSITO, 6),
    ]
    assert [m.costo_unitario for m in inversos] == [
        None,
        None,
        Decimal("1050.000000"),
        Decimal("1050.000000"),
    ]
    assert {m.origen_tipo for m in inversos} == {ORIGEN_ANULACION_TRANSFERENCIA}


def test_una_transferencia_sin_sus_movimientos_en_el_libro_es_un_error_interno() -> None:
    with pytest.raises(ValueError, match="movimientos originales"):
        expandir_anulacion_transferencia(
            transferencia_id=uuid4(),
            lineas=[LineaDeOperacion(VINO, 48)],
            originales=[],
        )


# --- expansión inversa de un ajuste (D5.1, D5.2) ------------------------------------------


def test_la_anulacion_de_un_ajuste_tiene_signo_contrario_y_el_motivo_de_la_anulacion() -> None:
    ajuste = uuid4()

    inversos = expandir_anulacion_ajuste(
        ajuste_id=ajuste,
        ubicacion_id=DEPOSITO,
        motivo_anulacion_id=MOTIVO_DE_ANULACION,
        lineas=[
            LineaDeAjusteOriginal(VINO, -6, Decimal("1050.000000")),
            LineaDeAjusteOriginal(AGUA, 3, None),
        ],
    )

    assert inversos == [
        LineaDeMovimiento(
            producto_id=VINO,
            ubicacion_id=DEPOSITO,
            cantidad_base=6,
            tipo=AJUSTE,
            costo_unitario=Decimal("1050.000000"),
            origen_tipo=ORIGEN_ANULACION_AJUSTE,
            origen_id=ajuste,
            motivo_id=MOTIVO_DE_ANULACION,
        ),
        LineaDeMovimiento(
            producto_id=AGUA,
            ubicacion_id=DEPOSITO,
            cantidad_base=-3,
            tipo=AJUSTE,
            costo_unitario=None,
            origen_tipo=ORIGEN_ANULACION_AJUSTE,
            origen_id=ajuste,
            motivo_id=MOTIVO_DE_ANULACION,
        ),
    ]


# --- una línea con origen de anulación admite costo (D5.2) --------------------------------


@pytest.mark.parametrize(
    ("tipo", "origen", "cantidad"),
    [
        (TRANSFERENCIA_ENTRADA, ORIGEN_ANULACION_TRANSFERENCIA, 6),
        (TRANSFERENCIA_SALIDA, ORIGEN_ANULACION_TRANSFERENCIA, -6),
        (AJUSTE, ORIGEN_ANULACION_AJUSTE, 6),
        (AJUSTE, ORIGEN_ANULACION_AJUSTE, -6),
    ],
)
def test_un_inverso_de_anulacion_admite_el_costo_original_y_tambien_nulo(
    tipo: str, origen: str, cantidad: int
) -> None:
    for costo in (Decimal("1050.000000"), None):
        linea = LineaDeMovimiento(VINO, DEPOSITO, cantidad, tipo, costo, origen, uuid4())
        assert validar_lineas_de_movimiento([linea]) == [linea]


@pytest.mark.parametrize(
    ("tipo", "origen", "cantidad"),
    [
        (TRANSFERENCIA_ENTRADA, ORIGEN_TRANSFERENCIA, 6),
        (TRANSFERENCIA_SALIDA, ORIGEN_TRANSFERENCIA, -6),
        (AJUSTE, ORIGEN_AJUSTE, 6),
        (AJUSTE, ORIGEN_AJUSTE, -6),
        (AJUSTE, ORIGEN_ANULACION_TRANSFERENCIA, 6),  # el origen de anulación es por tipo
        (TRANSFERENCIA_ENTRADA, ORIGEN_ANULACION_AJUSTE, 6),
    ],
)
def test_con_otro_origen_un_costo_en_transferencia_o_ajuste_sigue_siendo_invalido(
    tipo: str, origen: str, cantidad: int
) -> None:
    linea = LineaDeMovimiento(VINO, DEPOSITO, cantidad, tipo, Decimal("1050"), origen, uuid4())

    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([linea])


# --- puede_quedar_negativo (D1 = B, D5 punto 6) -------------------------------------------


def _linea_de(tipo: str, origen: str, cantidad: int = -6) -> LineaDeMovimiento:
    return LineaDeMovimiento(VINO, DEPOSITO, cantidad, tipo, None, origen, uuid4())


def test_el_inverso_de_un_ajuste_puede_dejar_negativo_solo_con_permiso() -> None:
    inverso = _linea_de(AJUSTE, ORIGEN_ANULACION_AJUSTE)

    assert puede_quedar_negativo(inverso, permitir_negativo=True) is True
    assert puede_quedar_negativo(inverso, permitir_negativo=False) is False


def test_un_ajuste_comun_nunca_queda_negativo_ni_con_permiso() -> None:
    assert puede_quedar_negativo(_linea_de(AJUSTE, ORIGEN_AJUSTE), permitir_negativo=True) is False


def test_la_salida_inversa_de_una_transferencia_puede_dejar_negativo_con_permiso() -> None:
    salida = _linea_de(TRANSFERENCIA_SALIDA, ORIGEN_ANULACION_TRANSFERENCIA)

    assert puede_quedar_negativo(salida, permitir_negativo=True) is True
    assert puede_quedar_negativo(salida, permitir_negativo=False) is False


# --- INV-12, INV-15: original más inverso suman cero ---------------------------------------

_cantidades = st.integers(min_value=1, max_value=10_000)
_costos = st.one_of(st.none(), st.decimals(min_value=1, max_value=100_000, places=6))


def _sumas(lineas: list[LineaDeMovimiento]) -> dict[tuple[UUID, UUID], int]:
    sumas: dict[tuple[UUID, UUID], int] = defaultdict(int)
    for linea in lineas:
        sumas[(linea.producto_id, linea.ubicacion_id)] += linea.cantidad_base
    return sumas


@given(cantidades=st.lists(_cantidades, min_size=1, max_size=20), costo=_costos)
def test_inv15_transferencia_mas_su_anulacion_suman_cero_por_producto_y_ubicacion(
    cantidades: list[int], costo: Decimal | None
) -> None:
    productos = [uuid4() for _ in cantidades]
    lineas = [LineaDeOperacion(p, c) for p, c in zip(productos, cantidades, strict=True)]
    validada = validar_transferencia(
        ubicacion_origen_id=DEPOSITO,
        ubicacion_destino_id=CAMIONETA,
        lineas=lineas,
        observacion=None,
    )
    transferencia = uuid4()
    originales_lineas = expandir_transferencia(validada, transferencia_id=transferencia)
    originales = [
        MovimientoOriginal(m.producto_id, m.ubicacion_id, m.cantidad_base, m.tipo, costo)
        for m in originales_lineas
    ]

    inversos = expandir_anulacion_transferencia(
        transferencia_id=transferencia, lineas=lineas, originales=originales
    )

    assert set(_sumas(originales_lineas + inversos).values()) == {0}
    assert len(inversos) == len(originales_lineas)


@given(
    cantidades=st.lists(
        st.integers(min_value=-10_000, max_value=10_000).filter(lambda c: c != 0),
        min_size=1,
        max_size=20,
    ),
    costo=_costos,
)
def test_inv12_ajuste_mas_su_anulacion_suman_cero_por_producto_y_ubicacion(
    cantidades: list[int], costo: Decimal | None
) -> None:
    productos = [uuid4() for _ in cantidades]
    validado = validar_ajuste(
        ubicacion_id=DEPOSITO,
        motivo_id=MOTIVO_DEL_AJUSTE,
        lineas=[LineaDeOperacion(p, c) for p, c in zip(productos, cantidades, strict=True)],
        observacion=None,
    )
    ajuste = uuid4()
    originales = expandir_ajuste(validado, ajuste_id=ajuste)

    inversos = expandir_anulacion_ajuste(
        ajuste_id=ajuste,
        ubicacion_id=DEPOSITO,
        motivo_anulacion_id=MOTIVO_DE_ANULACION,
        lineas=[LineaDeAjusteOriginal(m.producto_id, m.cantidad_base, costo) for m in originales],
    )

    assert set(_sumas(originales + inversos).values()) == {0}
    assert {m.motivo_id for m in inversos} == {MOTIVO_DE_ANULACION}
