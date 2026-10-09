"""Tarea 4.3: dominio puro de `stock` (STK-01 a STK-05, INV-04, INV-12,
`design.md` D4 a D8, D11, D13).

Funciones puras (`CLAUDE.md` §4): ninguna toca la base ni importa
infraestructura. El saldo real lo calcula la base con SQL; acá se prueba la
definición contra la que INV-12 se verifica y las reglas que deciden antes de
escribir.

Reglas citadas: STK-01, STK-02, STK-03, STK-04, STK-05, INV-04, INV-12,
`design.md` D4 (corrección y `PRODUCTO_CON_OPERACIONES`), D5 (forma del comando),
D6 (costo), D7 (ubicación), D8 (desactivación), D11 (kardex), D13 (tipos).
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.errors import DomainError
from app.modules.stock.domain.errores import (
    CantidadFueraDeRangoError,
    CantidadInvalidaError,
    CostoInvalidoError,
    CursorInvalidoError,
    LineasInvalidasError,
    NombreInvalidoError,
    ProductoConOperacionesError,
    ProductoInactivoError,
    ProductoRepetidoError,
    RangoDeFechasInvalidoError,
    StockInsuficienteError,
    TipoDeMovimientoInvalidoError,
    TipoDeUbicacionInvalidoError,
    UbicacionConStockError,
    UbicacionInactivaError,
    VehiculoRequiereTomaError,
)
from app.modules.stock.domain.kardex import (
    LIMITE_DEFAULT,
    LIMITE_MAXIMO,
    codificar_cursor,
    codificar_cursor_de_producto,
    decodificar_cursor,
    decodificar_cursor_de_producto,
    limite_efectivo,
    rango_de_instantes,
)
from app.modules.stock.domain.movimientos import (
    STOCK_INICIAL,
    TIPOS_DE_MOVIMIENTO,
    TIPOS_QUE_INGRESAN_CON_COSTO,
    LineaDeMovimiento,
    LineaDeStockInicial,
    aplicar_movimiento,
    diferencias_de_stock_total,
    productos_que_exigen_estar_activos,
    puede_quedar_negativo,
    saldo_de,
    validar_correccion,
    validar_lineas_de_movimiento,
    validar_lineas_de_stock_inicial,
    validar_producto_activo,
    validar_stock_inicial_admitido,
    validar_tipo_de_movimiento,
    validar_ubicacion_activa,
)
from app.modules.stock.domain.ubicaciones import (
    normalizar_nombre,
    validar_desactivacion,
    validar_tipo_de_ubicacion,
    validar_ubicacion,
)

MENDOZA = "America/Argentina/Mendoza"

# --- ubicación (STK-02, D7) ---------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("Depósito central", "Depósito central"),
        ("  Depósito central  ", "Depósito central"),
        ("\tCamión 1\n", "Camión 1"),
    ],
)
def test_el_nombre_de_la_ubicacion_se_recorta(crudo: str, esperado: str) -> None:
    assert normalizar_nombre(crudo) == esperado


@pytest.mark.parametrize("crudo", ["", "   ", "\t\n"])
def test_un_nombre_vacio_se_rechaza(crudo: str) -> None:
    with pytest.raises(NombreInvalidoError) as error:
        normalizar_nombre(crudo)

    assert error.value.codigo == "NOMBRE_INVALIDO"


@pytest.mark.parametrize("tipo", ["DEPOSITO", "VEHICULO", "OTRO"])
def test_los_tipos_de_ubicacion_de_stk_02_son_validos(tipo: str) -> None:
    assert validar_tipo_de_ubicacion(tipo) == tipo


@pytest.mark.parametrize("tipo", ["CAMION", "deposito", "", "VEHÍCULO"])
def test_un_tipo_fuera_del_catalogo_se_rechaza(tipo: str) -> None:
    with pytest.raises(TipoDeUbicacionInvalidoError) as error:
        validar_tipo_de_ubicacion(tipo)

    assert error.value.codigo == "TIPO_UBICACION_INVALIDO"


def test_un_vehiculo_requiere_toma() -> None:
    """STK-02, D7."""
    with pytest.raises(VehiculoRequiereTomaError) as error:
        validar_ubicacion(nombre="Camión 1", tipo="VEHICULO", requiere_toma=False)

    assert error.value.codigo == "VEHICULO_REQUIERE_TOMA"


@pytest.mark.parametrize(
    ("tipo", "requiere_toma"),
    [("VEHICULO", True), ("DEPOSITO", False), ("DEPOSITO", True), ("OTRO", False), ("OTRO", True)],
)
def test_las_combinaciones_validas_de_tipo_y_toma_se_aceptan(
    tipo: str, requiere_toma: bool
) -> None:
    """D7: para `DEPOSITO`/`OTRO` la toma es libre."""
    datos = validar_ubicacion(nombre="  Lugar  ", tipo=tipo, requiere_toma=requiere_toma)

    assert (datos.nombre, datos.tipo, datos.requiere_toma) == ("Lugar", tipo, requiere_toma)


def test_una_ubicacion_valida_no_admite_una_toma_que_no_es_booleana() -> None:
    with pytest.raises(VehiculoRequiereTomaError):
        validar_ubicacion(nombre="Camión", tipo="VEHICULO", requiere_toma=None)  # type: ignore[arg-type]


# --- desactivación (D8) -------------------------------------------------------


def test_una_ubicacion_con_stock_no_se_desactiva() -> None:
    with pytest.raises(UbicacionConStockError) as error:
        validar_desactivacion(tiene_saldos_distintos_de_cero=True)

    assert error.value.codigo == "UBICACION_CON_STOCK"


def test_una_ubicacion_sin_stock_se_desactiva() -> None:
    validar_desactivacion(tiene_saldos_distintos_de_cero=False)


# --- catálogo de movimientos (STK-03, D13) ------------------------------------


def test_el_catalogo_tiene_los_nueve_tipos_de_la_etapa_1() -> None:
    nueve = {
        "STOCK_INICIAL",
        "COMPRA",
        "ANULACION_COMPRA",
        "VENTA",
        "ANULACION_VENTA",
        "TRANSFERENCIA_SALIDA",
        "TRANSFERENCIA_ENTRADA",
        "AJUSTE",
        "DIFERENCIA_RENDICION",
    }
    assert set(TIPOS_DE_MOVIMIENTO) == nueve
    assert STOCK_INICIAL in TIPOS_DE_MOVIMIENTO


@pytest.mark.parametrize("tipo", sorted({"STOCK_INICIAL", "AJUSTE", "DIFERENCIA_RENDICION"}))
def test_un_tipo_del_catalogo_es_valido(tipo: str) -> None:
    assert validar_tipo_de_movimiento(tipo) == tipo


@pytest.mark.parametrize("tipo", ["DEVOLUCION", "RECUENTO", "", "stock_inicial"])
def test_un_tipo_de_la_etapa_2_o_desconocido_se_rechaza(tipo: str) -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError) as error:
        validar_tipo_de_movimiento(tipo)

    assert error.value.codigo == "TIPO_MOVIMIENTO_INVALIDO"


# --- líneas del stock inicial (D5, D6) ----------------------------------------


def _linea(
    cantidad: object, costo: object = "1000", producto_id: object = None
) -> LineaDeStockInicial:
    return LineaDeStockInicial(
        producto_id=producto_id or uuid4(),  # type: ignore[arg-type]
        cantidad_base=cantidad,  # type: ignore[arg-type]
        costo_unitario=costo,  # type: ignore[arg-type]
    )


def test_una_linea_positiva_con_costo_es_valida() -> None:
    linea = _linea(60, "1000.000000")

    assert validar_lineas_de_stock_inicial([linea]) == [linea]


def test_una_linea_negativa_sin_costo_es_valida() -> None:
    """D4-A: la corrección negativa egresa al promedio vigente, sin costo."""
    linea = _linea(-12, None)

    assert validar_lineas_de_stock_inicial([linea]) == [linea]


def test_varias_lineas_de_productos_distintos_son_validas() -> None:
    lineas = [_linea(60), _linea(-5, None), _linea(1, "0.5")]

    assert validar_lineas_de_stock_inicial(lineas) == lineas


@pytest.mark.parametrize("cantidad_de_lineas", [0, 201, 500])
def test_el_comando_admite_de_una_a_doscientas_lineas(cantidad_de_lineas: int) -> None:
    with pytest.raises(LineasInvalidasError) as error:
        validar_lineas_de_stock_inicial([_linea(1) for _ in range(cantidad_de_lineas)])

    assert error.value.codigo == "LINEAS_INVALIDAS"


@pytest.mark.parametrize("cantidad_de_lineas", [1, 200])
def test_los_limites_de_lineas_se_aceptan(cantidad_de_lineas: int) -> None:
    lineas = [_linea(1) for _ in range(cantidad_de_lineas)]

    assert len(validar_lineas_de_stock_inicial(lineas)) == cantidad_de_lineas


def test_un_producto_no_se_repite_en_el_comando() -> None:
    producto_id = uuid4()

    with pytest.raises(ProductoRepetidoError) as error:
        validar_lineas_de_stock_inicial(
            [_linea(10, producto_id=producto_id), _linea(-2, None, producto_id=producto_id)]
        )

    assert error.value.codigo == "PRODUCTO_REPETIDO"


@pytest.mark.parametrize("cantidad", [0, 1.5, "60", None, True, False])
def test_la_cantidad_es_un_entero_distinto_de_cero(cantidad: object) -> None:
    """INV-04, D5: cantidad entera y no cero."""
    with pytest.raises(CantidadInvalidaError) as error:
        validar_lineas_de_stock_inicial([_linea(cantidad)])

    assert error.value.codigo == "CANTIDAD_INVALIDA"


@pytest.mark.parametrize("cantidad", [2_147_483_648, -2_147_483_649])
def test_la_cantidad_no_puede_salir_de_un_integer(cantidad: int) -> None:
    with pytest.raises(CantidadFueraDeRangoError) as error:
        validar_lineas_de_stock_inicial([_linea(cantidad)])

    assert error.value.codigo == "CANTIDAD_FUERA_DE_RANGO"


@pytest.mark.parametrize("cantidad", [2_147_483_647, -2_147_483_648])
def test_la_cantidad_puede_llegar_al_limite_de_integer(cantidad: int) -> None:
    costo = "1" if cantidad > 0 else None

    assert len(validar_lineas_de_stock_inicial([_linea(cantidad, costo)])) == 1


def test_una_linea_positiva_exige_costo() -> None:
    """D5-A: obligatorio si la cantidad es positiva."""
    with pytest.raises(CostoInvalidoError) as error:
        validar_lineas_de_stock_inicial([_linea(60, None)])

    assert error.value.codigo == "COSTO_INVALIDO"


def test_una_linea_negativa_no_admite_costo() -> None:
    """D5-A: prohibido si la cantidad es negativa."""
    with pytest.raises(CostoInvalidoError) as error:
        validar_lineas_de_stock_inicial([_linea(-60, "1000")])

    assert error.value.codigo == "COSTO_INVALIDO"


# --- líneas de un movimiento genérico (STK-03, D9) ----------------------------


def _movimiento(
    cantidad: object = 10,
    costo: object = "5",
    tipo: str = "COMPRA",
    producto_id: object = None,
    ubicacion_id: object = None,
    origen_tipo: str | None = None,
) -> LineaDeMovimiento:
    return LineaDeMovimiento(
        producto_id=producto_id or uuid4(),  # type: ignore[arg-type]
        ubicacion_id=ubicacion_id or uuid4(),  # type: ignore[arg-type]
        cantidad_base=cantidad,  # type: ignore[arg-type]
        tipo=tipo,
        costo_unitario=costo,  # type: ignore[arg-type]
        origen_tipo=origen_tipo or tipo,
        origen_id=uuid4(),
    )


def test_un_ingreso_con_costo_y_un_egreso_sin_costo_son_lineas_validas() -> None:
    lineas = [_movimiento(10, "5"), _movimiento(-3, None, tipo="AJUSTE")]

    assert validar_lineas_de_movimiento(lineas) == lineas


def test_un_movimiento_sin_lineas_se_rechaza() -> None:
    with pytest.raises(LineasInvalidasError):
        validar_lineas_de_movimiento([])


def test_el_mismo_par_puede_repetirse_en_un_movimiento_generico() -> None:
    """Una compra o una rendición pueden tocar el mismo producto y ubicación
    dos veces; la unicidad por producto es solo del stock inicial (D5)."""
    producto_id, ubicacion_id = uuid4(), uuid4()
    lineas = [
        _movimiento(10, "5", producto_id=producto_id, ubicacion_id=ubicacion_id),
        _movimiento(-2, None, producto_id=producto_id, ubicacion_id=ubicacion_id),
    ]

    assert validar_lineas_de_movimiento(lineas) == lineas


def test_un_tipo_de_movimiento_fuera_del_catalogo_se_rechaza_en_la_linea() -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(tipo="DEVOLUCION")])


@pytest.mark.parametrize("cantidad", [0, 1.5, "1", None, True])
def test_una_cantidad_invalida_se_rechaza_en_la_linea(cantidad: object) -> None:
    with pytest.raises(CantidadInvalidaError):
        validar_lineas_de_movimiento([_movimiento(cantidad)])


def test_un_ingreso_sin_costo_y_un_egreso_con_costo_se_rechazan_en_la_linea() -> None:
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(10, None)])
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(-10, "5")])


def test_solo_los_tres_tipos_de_ingreso_con_costo_pueden_ingresar_stock() -> None:
    """CST-11: compra, stock inicial y anulación de venta recalculan el promedio.
    Los demás ingresos (ajuste, transferencia, rendición) no tienen reglas de costo
    en este change; `ANULACION_COMPRA` es un egreso (change 11)."""
    assert frozenset({"STOCK_INICIAL", "COMPRA", "ANULACION_VENTA"}) == TIPOS_QUE_INGRESAN_CON_COSTO


@pytest.mark.parametrize("tipo", ["DIFERENCIA_RENDICION", "VENTA", "ANULACION_COMPRA"])
def test_un_ingreso_de_un_tipo_sin_reglas_de_costo_se_rechaza(tipo: str) -> None:
    """`DIFERENCIA_RENDICION` sigue sin reglas hasta el change 24 (ADR-039, RUT-06)."""
    with pytest.raises(TipoDeMovimientoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(10, "5", tipo=tipo)])
    with pytest.raises(TipoDeMovimientoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(10, None, tipo=tipo)])


@pytest.mark.parametrize(
    "tipo", ["AJUSTE", "VENTA", "TRANSFERENCIA_SALIDA", "DIFERENCIA_RENDICION"]
)
def test_un_egreso_de_cualquier_tipo_del_catalogo_es_valido(tipo: str) -> None:
    linea = _movimiento(-5, None, tipo=tipo)

    assert validar_lineas_de_movimiento([linea]) == [linea]


# --- corrección y stock inicial admitido (D4) ---------------------------------


@pytest.mark.parametrize(("saldo", "egreso"), [(10, 10), (10, 1), (60, 12), (1, 1)])
def test_un_egreso_que_alcanza_no_se_rechaza(saldo: int, egreso: int) -> None:
    validar_correccion(saldo_actual=saldo, cantidad_a_egresar=egreso)


@pytest.mark.parametrize(("saldo", "egreso"), [(10, 11), (0, 1), (-3, 1), (5, 100)])
def test_un_egreso_mayor_que_el_saldo_es_stock_insuficiente(saldo: int, egreso: int) -> None:
    """STK-05, D4: sin excepción por `PERMITIR_STOCK_NEGATIVO`."""
    with pytest.raises(StockInsuficienteError) as error:
        validar_correccion(saldo_actual=saldo, cantidad_a_egresar=egreso)

    assert error.value.codigo == "STOCK_INSUFICIENTE"


def test_el_stock_inicial_se_admite_sin_operaciones_de_otro_tipo() -> None:
    validar_stock_inicial_admitido(tiene_movimientos_de_otro_tipo=False)


def test_el_stock_inicial_no_se_admite_con_operaciones_de_otro_tipo() -> None:
    with pytest.raises(ProductoConOperacionesError) as error:
        validar_stock_inicial_admitido(tiene_movimientos_de_otro_tipo=True)

    assert error.value.codigo == "PRODUCTO_CON_OPERACIONES"


# --- estados activos (D8, CAT-05) ---------------------------------------------


def test_una_ubicacion_inactiva_no_recibe_movimientos() -> None:
    with pytest.raises(UbicacionInactivaError) as error:
        validar_ubicacion_activa(activo=False)

    assert error.value.codigo == "UBICACION_INACTIVA"
    validar_ubicacion_activa(activo=True)


def test_un_producto_inactivo_no_recibe_movimientos() -> None:
    with pytest.raises(ProductoInactivoError) as error:
        validar_producto_activo(activo=False)

    assert error.value.codigo == "PRODUCTO_INACTIVO"
    validar_producto_activo(activo=True)


# --- saldo = suma de movimientos (STK-04, INV-12) -----------------------------


def test_el_saldo_es_la_suma_de_los_movimientos() -> None:
    assert saldo_de([60, 60, -12]) == 108


def test_sin_movimientos_el_saldo_es_cero() -> None:
    assert saldo_de([]) == 0


def test_el_saldo_no_depende_del_orden() -> None:
    movimientos = [60, -12, 30, -3, 100]

    assert saldo_de(movimientos) == saldo_de(list(reversed(movimientos))) == 175


def test_aplicar_un_movimiento_suma_su_cantidad_con_signo() -> None:
    assert aplicar_movimiento(60, 60) == 120
    assert aplicar_movimiento(120, -72) == 48


def test_aplicar_uno_por_uno_da_la_suma() -> None:
    saldo = 0
    for cantidad in (60, -12, 7):
        saldo = aplicar_movimiento(saldo, cantidad)

    assert saldo == saldo_de([60, -12, 7])


def test_aplicar_un_movimiento_no_puede_salir_de_integer() -> None:
    with pytest.raises(CantidadFueraDeRangoError):
        aplicar_movimiento(2_147_483_647, 1)


def test_sin_diferencias_el_stock_total_coincide() -> None:
    p1, p2 = uuid4(), uuid4()

    assert diferencias_de_stock_total({p1: 10, p2: 0}, {p1: 10}) == []


def test_un_stock_total_distinto_de_la_suma_de_los_saldos_se_informa() -> None:
    """INV-12, `02` §7.6: sin fila de costo o sin saldos cuenta como cero."""
    p1, p2, p3 = sorted([uuid4(), uuid4(), uuid4()])

    diferencias = diferencias_de_stock_total({p1: 59, p2: 5}, {p1: 60, p3: 7})

    assert [
        (d.producto_id, d.ubicacion_id, d.valor_materializado, d.valor_esperado)
        for d in diferencias
    ] == [
        (p1, None, 59, 60),
        (p2, None, 5, 0),
        (p3, None, 0, 7),
    ]


# --- kardex: límite, cursor y rango (D11, TR-04) ------------------------------


def test_los_limites_de_pagina_son_los_de_d11() -> None:
    assert (LIMITE_DEFAULT, LIMITE_MAXIMO) == (50, 200)


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [(None, 50), (10, 10), (200, 200), (201, 200), (100000, 200), (0, 1), (-5, 1)],
)
def test_el_limite_se_acota_al_rango_permitido(pedido: int | None, esperado: int) -> None:
    assert limite_efectivo(pedido) == esperado


@pytest.mark.parametrize(
    "momento",
    [
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 9, 29, 23, 59, 59, 123456, tzinfo=UTC),
        datetime(2026, 3, 1, 8, 30, tzinfo=ZoneInfo(MENDOZA)),
    ],
)
def test_el_cursor_recupera_exactamente_el_momento_y_el_id(momento: datetime) -> None:
    id_ = uuid4()

    recuperado_momento, recuperado_id = decodificar_cursor(codificar_cursor(momento, id_))

    assert recuperado_momento == momento
    assert recuperado_id == id_


def test_el_cursor_es_opaco() -> None:
    cursor = codificar_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())

    assert "2026" not in cursor
    assert "|" not in cursor


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "no-es-base64!!",
        base64.urlsafe_b64encode(b"sin-separador").decode(),
        base64.urlsafe_b64encode(b"2026-01-01T00:00:00+00:00|no-es-uuid").decode(),
        base64.urlsafe_b64encode(f"basura|{uuid4()}".encode()).decode(),
        base64.urlsafe_b64encode(f"2026-01-01T00:00:00|{uuid4()}".encode()).decode(),
    ],
)
def test_un_cursor_ilegible_o_sin_zona_horaria_es_invalido(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        decodificar_cursor(cursor)

    assert error.value.codigo == "CURSOR_INVALIDO"


def test_el_cursor_de_producto_recupera_el_id_y_es_opaco() -> None:
    producto_id = uuid4()

    cursor = codificar_cursor_de_producto(producto_id)

    assert decodificar_cursor_de_producto(cursor) == producto_id
    assert str(producto_id) not in cursor


@pytest.mark.parametrize("cursor", ["", "no-es-base64!!", base64.urlsafe_b64encode(b"x").decode()])
def test_un_cursor_de_producto_ilegible_es_invalido(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError):
        decodificar_cursor_de_producto(cursor)


def test_sin_fechas_no_hay_rango() -> None:
    assert rango_de_instantes(None, None, MENDOZA) == (None, None)


def test_hasta_se_incluye_entero() -> None:
    zona = ZoneInfo(MENDOZA)

    inicio, fin = rango_de_instantes(date(2026, 3, 1), date(2026, 3, 31), MENDOZA)

    assert inicio == datetime(2026, 3, 1, tzinfo=zona)
    assert fin == datetime(2026, 4, 1, tzinfo=zona)


def test_un_solo_extremo_deja_el_otro_abierto() -> None:
    zona = ZoneInfo(MENDOZA)

    assert rango_de_instantes(date(2026, 3, 1), None, MENDOZA) == (
        datetime(2026, 3, 1, tzinfo=zona),
        None,
    )
    assert rango_de_instantes(None, date(2026, 3, 1), MENDOZA) == (
        None,
        datetime(2026, 3, 2, tzinfo=zona),
    )


def test_la_misma_fecha_en_desde_y_hasta_es_un_dia_completo() -> None:
    inicio, fin = rango_de_instantes(date(2026, 3, 5), date(2026, 3, 5), MENDOZA)

    assert inicio is not None and fin is not None
    assert fin - inicio == timedelta(days=1)


def test_desde_posterior_a_hasta_se_rechaza() -> None:
    with pytest.raises(RangoDeFechasInvalidoError) as error:
        rango_de_instantes(date(2026, 3, 2), date(2026, 3, 1), MENDOZA)

    assert error.value.codigo == "RANGO_DE_FECHAS_INVALIDO"


# --- todos los errores son errores de dominio ----------------------------------


@pytest.mark.parametrize(
    "clase",
    [
        CantidadFueraDeRangoError,
        CantidadInvalidaError,
        CostoInvalidoError,
        CursorInvalidoError,
        LineasInvalidasError,
        NombreInvalidoError,
        ProductoConOperacionesError,
        ProductoInactivoError,
        ProductoRepetidoError,
        RangoDeFechasInvalidoError,
        StockInsuficienteError,
        TipoDeMovimientoInvalidoError,
        TipoDeUbicacionInvalidoError,
        UbicacionConStockError,
        UbicacionInactivaError,
        VehiculoRequiereTomaError,
    ],
)
def test_los_errores_de_stock_heredan_de_domain_error_con_codigo_estable(clase: type) -> None:
    assert issubclass(clase, DomainError)
    assert clase.codigo == clase.codigo.upper()  # type: ignore[attr-defined]
    assert clase.status_http in {409, 422}  # type: ignore[attr-defined]


# --- reversión de compra (change 11, D9, D10, D11) ----------------------------


def test_un_egreso_anulacion_compra_exige_costo_cmp_06() -> None:
    """CMP-06, D9: el egreso `ANULACION_COMPRA` lleva el costo base de la línea."""
    linea = _movimiento(-60, "1100", tipo="ANULACION_COMPRA")

    assert validar_lineas_de_movimiento([linea]) == [linea]
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(-60, None, tipo="ANULACION_COMPRA")])


@pytest.mark.parametrize("tipo", ["AJUSTE", "VENTA", "TRANSFERENCIA_SALIDA"])
def test_un_egreso_de_otro_tipo_con_costo_sigue_rechazado(tipo: str) -> None:
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(-5, "5", tipo=tipo)])


def test_solo_anulacion_compra_puede_dejar_negativo_con_permiso_d10() -> None:
    reversion = _movimiento(-60, "1100", tipo="ANULACION_COMPRA")
    venta = _movimiento(-60, None, tipo="VENTA")

    assert puede_quedar_negativo(reversion, permitir_negativo=True) is True
    assert puede_quedar_negativo(reversion, permitir_negativo=False) is False
    assert puede_quedar_negativo(venta, permitir_negativo=True) is False


def test_solo_anulacion_compra_admite_producto_inactivo_d11() -> None:
    producto_reversion, producto_mixto, producto_compra = uuid4(), uuid4(), uuid4()
    lineas = [
        _movimiento(-1, "5", tipo="ANULACION_COMPRA", producto_id=producto_reversion),
        _movimiento(-1, "5", tipo="ANULACION_COMPRA", producto_id=producto_mixto),
        _movimiento(-1, None, tipo="VENTA", producto_id=producto_mixto),
        _movimiento(1, "5", tipo="COMPRA", producto_id=producto_compra),
    ]

    assert productos_que_exigen_estar_activos(lineas) == {producto_mixto, producto_compra}


# --- transferencias y ajustes (change 14, D1, D3, D4, D5.2, D9) ---------------------


@pytest.mark.parametrize(
    ("tipo", "origen"), [("TRANSFERENCIA_ENTRADA", "TRANSFERENCIA"), ("AJUSTE", "AJUSTE_STOCK")]
)
def test_un_ingreso_de_transferencia_o_ajuste_se_admite_sin_costo(tipo: str, origen: str) -> None:
    """CST-12, D9: no recalcula el promedio, así que no lleva costo de entrada."""
    linea = _movimiento(48, None, tipo=tipo, origen_tipo=origen)

    assert validar_lineas_de_movimiento([linea]) == [linea]


@pytest.mark.parametrize(
    ("tipo", "origen"), [("TRANSFERENCIA_ENTRADA", "TRANSFERENCIA"), ("AJUSTE", "AJUSTE_STOCK")]
)
@pytest.mark.parametrize("costo", ["1000.000000", "1"])
def test_un_ingreso_de_transferencia_o_ajuste_con_costo_es_costo_invalido(
    tipo: str, origen: str, costo: str
) -> None:
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(48, costo, tipo=tipo, origen_tipo=origen)])


def test_un_ingreso_de_rendicion_sigue_siendo_tipo_invalido() -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(5, None, tipo="DIFERENCIA_RENDICION")])


@pytest.mark.parametrize("tipo", ["STOCK_INICIAL", "COMPRA", "ANULACION_VENTA"])
def test_los_ingresos_que_recalculan_siguen_exigiendo_costo(tipo: str) -> None:
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento([_movimiento(5, None, tipo=tipo)])


@pytest.mark.parametrize(
    ("cantidad", "tipo", "origen"),
    [
        (48, "TRANSFERENCIA_ENTRADA", "ANULACION_TRANSFERENCIA"),
        (-48, "TRANSFERENCIA_SALIDA", "ANULACION_TRANSFERENCIA"),
        (6, "AJUSTE", "ANULACION_AJUSTE_STOCK"),
        (-6, "AJUSTE", "ANULACION_AJUSTE_STOCK"),
    ],
)
@pytest.mark.parametrize("costo", ["1050.000000", None])
def test_un_inverso_de_anulacion_lleva_el_costo_original_o_nulo(
    cantidad: int, tipo: str, origen: str, costo: str | None
) -> None:
    """D5.2: con origen de anulación la línea lleva el costo del movimiento original (que
    puede ser nulo) y la puerta lo guarda tal cual."""
    linea = _movimiento(cantidad, costo, tipo=tipo, origen_tipo=origen)

    assert validar_lineas_de_movimiento([linea]) == [linea]


@pytest.mark.parametrize(
    ("cantidad", "tipo", "origen"),
    [
        (-6, "TRANSFERENCIA_SALIDA", "TRANSFERENCIA"),
        (-6, "AJUSTE", "AJUSTE_STOCK"),
        (-6, "TRANSFERENCIA_SALIDA", "ANULACION_AJUSTE_STOCK"),  # origen que no le corresponde
        (6, "AJUSTE", "ANULACION_TRANSFERENCIA"),
    ],
)
def test_con_cualquier_otro_origen_el_costo_sigue_siendo_invalido(
    cantidad: int, tipo: str, origen: str
) -> None:
    with pytest.raises(CostoInvalidoError):
        validar_lineas_de_movimiento(
            [_movimiento(cantidad, "1050.000000", tipo=tipo, origen_tipo=origen)]
        )


@pytest.mark.parametrize(
    ("tipo", "origen", "esperado"),
    [
        ("ANULACION_COMPRA", "ANULACION_COMPRA", True),
        ("TRANSFERENCIA_SALIDA", "TRANSFERENCIA", True),
        ("TRANSFERENCIA_SALIDA", "ANULACION_TRANSFERENCIA", True),
        ("AJUSTE", "ANULACION_AJUSTE_STOCK", True),
        ("AJUSTE", "AJUSTE_STOCK", False),  # D1 = B: un ajuste nunca deja negativo
        ("STOCK_INICIAL", "STOCK_INICIAL", False),  # STK-10
        ("VENTA", "VENTA", False),
    ],
)
def test_puede_quedar_negativo_solo_en_los_tipos_y_origenes_previstos(
    tipo: str, origen: str, esperado: bool
) -> None:
    linea = _movimiento(
        -5, "1" if tipo == "ANULACION_COMPRA" else None, tipo=tipo, origen_tipo=origen
    )

    assert puede_quedar_negativo(linea, permitir_negativo=True) is esperado


@pytest.mark.parametrize(
    ("tipo", "origen"),
    [
        ("ANULACION_COMPRA", "ANULACION_COMPRA"),
        ("TRANSFERENCIA_SALIDA", "TRANSFERENCIA"),
        ("AJUSTE", "ANULACION_AJUSTE_STOCK"),
    ],
)
def test_sin_permiso_ningun_egreso_puede_quedar_negativo(tipo: str, origen: str) -> None:
    linea = _movimiento(
        -5, "1" if tipo == "ANULACION_COMPRA" else None, tipo=tipo, origen_tipo=origen
    )

    assert puede_quedar_negativo(linea, permitir_negativo=False) is False


def test_los_productos_de_transferencias_y_ajustes_exigen_estar_activos_de_cualquier_signo() -> (
    None
):
    """D4: `productos_que_exigen_estar_activos` no cambia; solo queda afuera el producto
    cuyas líneas son todas `ANULACION_COMPRA`."""
    transferido, ajustado_neg, ajustado_pos, solo_anulacion = uuid4(), uuid4(), uuid4(), uuid4()
    lineas = [
        _movimiento(-5, None, tipo="TRANSFERENCIA_SALIDA", producto_id=transferido),
        _movimiento(5, None, tipo="TRANSFERENCIA_ENTRADA", producto_id=transferido),
        _movimiento(-5, None, tipo="AJUSTE", producto_id=ajustado_neg),
        _movimiento(5, None, tipo="AJUSTE", producto_id=ajustado_pos),
        _movimiento(-5, "1", tipo="ANULACION_COMPRA", producto_id=solo_anulacion),
    ]

    assert productos_que_exigen_estar_activos(lineas) == {transferido, ajustado_neg, ajustado_pos}
