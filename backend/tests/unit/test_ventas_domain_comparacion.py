"""Tarea 5.5 (change 18a; spec `ventas/composicion-de-venta`, requisitos "Con conexión se
confirma el precio que vio el usuario" y "El precio sale de la lista aplicable"; `design.md`
D2, D7): comparación de lo esperado con lo resuelto.

Reglas citadas: PRC-20, PRC-23, TR-10, VTA-10, INV-14, SYN-06, SYN-07.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.ventas.domain.comparacion import (
    ProductoSinPrecio,
    ValoresDeLinea,
    comparar_con_esperado,
    observacion_lista_no_vigente,
    verificar_productos_con_precio,
    verificar_totales_offline,
    verificar_unidades_de_referencia,
    verificar_version_uniforme,
)
from app.modules.ventas.domain.errores import (
    PrecioDifiereError,
    ProductoSinPrecioError,
    TotalesInconsistentesError,
    VersionNoPermitidaError,
)

VERSION_3 = uuid4()
VERSION_4 = uuid4()
LINEA_VINO = uuid4()
LINEA_CERVEZA = uuid4()


def _valores(
    linea_id: UUID = LINEA_VINO,
    *,
    version: UUID = VERSION_4,
    precio: str = "12500.00",
    unidades: int = 6,
    bruto: str = "31250.00",
) -> ValoresDeLinea:
    return ValoresDeLinea(
        linea_id=linea_id,
        lista_version_id=version,
        precio_referencia=Decimal(precio),
        unidades_referencia=unidades,
        importe_bruto=Decimal(bruto),
    )


# --- con conexión: PRECIO_DIFIERE (D2) ---------------------------------------------


def test_tr10_lo_esperado_igual_a_lo_resuelto_se_acepta() -> None:
    esperado = [_valores(), _valores(LINEA_CERVEZA, precio="9000.00", bruto="4500.00")]
    resuelto = [_valores(), _valores(LINEA_CERVEZA, precio="9000.00", bruto="4500.00")]

    comparar_con_esperado(esperado, resuelto, Decimal("35750.00"), Decimal("35750.00"))


def test_tr10_el_precio_cambiado_entre_la_pantalla_y_la_confirmacion_se_rechaza() -> None:
    """Ejemplo de D2: la pantalla mostró $12.500 (bruto 31.250,00); el servidor resuelve
    $13.000 (bruto 32.500,00) y devuelve sus valores."""
    esperado = [_valores()]
    resuelto = [_valores(precio="13000.00", bruto="32500.00")]

    with pytest.raises(PrecioDifiereError) as error:
        comparar_con_esperado(esperado, resuelto, Decimal("31250.00"), Decimal("32500.00"))

    assert error.value.codigo == "PRECIO_DIFIERE"
    assert error.value.status_http == 409
    assert error.value.extension == {
        "lineas": [
            {
                "linea_id": str(LINEA_VINO),
                "lista_version_id": str(VERSION_4),
                "precio_referencia": "13000.00",
                "unidades_referencia": 6,
                "importe_bruto": "32500.00",
            }
        ],
        "total": "32500.00",
    }


@pytest.mark.parametrize(
    "cambios",
    [
        {"version": VERSION_3},
        {"unidades": 12},
        {"bruto": "31250.01"},
        {"precio": "12500.01"},
    ],
)
def test_prc23_cualquier_valor_distinto_de_una_linea_se_rechaza(cambios: dict[str, object]) -> None:
    """La versión, las unidades de referencia, el precio o el bruto: cada uno por separado."""
    with pytest.raises(PrecioDifiereError):
        comparar_con_esperado(
            [_valores()],
            [_valores(**cambios)],
            Decimal("31250.00"),
            Decimal("31250.00"),  # type: ignore[arg-type]
        )


def test_tr10_un_total_manipulado_se_rechaza_aunque_las_lineas_coincidan() -> None:
    """Spec: total esperado `1.00` para un bruto de `31250.00`."""
    with pytest.raises(PrecioDifiereError) as error:
        comparar_con_esperado([_valores()], [_valores()], Decimal("1.00"), Decimal("31250.00"))

    assert error.value.extension is not None
    assert error.value.extension["total"] == "31250.00"


def test_tr10_se_comparan_las_lineas_por_identificador_no_por_posicion() -> None:
    esperado = [_valores(), _valores(LINEA_CERVEZA, precio="9000.00", bruto="4500.00")]
    resuelto = [_valores(LINEA_CERVEZA, precio="9000.00", bruto="4500.00"), _valores()]

    comparar_con_esperado(esperado, resuelto, Decimal("35750.00"), Decimal("35750.00"))


def test_tr10_una_linea_sin_valores_esperados_se_rechaza() -> None:
    with pytest.raises(PrecioDifiereError):
        comparar_con_esperado([], [_valores()], Decimal("31250.00"), Decimal("31250.00"))


# --- producto sin precio (D7) ------------------------------------------------------


def test_vta10_sin_productos_sin_precio_se_acepta() -> None:
    verificar_productos_con_precio([])


def test_vta10_un_producto_sin_precio_rechaza_la_venta_entera_con_la_lista() -> None:
    cerveza = ProductoSinPrecio(producto_id=uuid4(), nombre="Cerveza B")
    with pytest.raises(ProductoSinPrecioError) as error:
        verificar_productos_con_precio([cerveza])

    assert error.value.codigo == "PRODUCTO_SIN_PRECIO"
    assert error.value.status_http == 409
    assert error.value.extension == {
        "productos": [{"producto_id": str(cerveza.producto_id), "nombre": "Cerveza B"}]
    }


def test_vta10_el_detalle_nombra_a_todos_los_productos_sin_precio() -> None:
    uno, otro = ProductoSinPrecio(uuid4(), "Cerveza B"), ProductoSinPrecio(uuid4(), "Vino C")
    with pytest.raises(ProductoSinPrecioError) as error:
        verificar_productos_con_precio([uno, otro])

    assert error.value.extension is not None
    assert [p["nombre"] for p in error.value.extension["productos"]] == ["Cerveza B", "Vino C"]


# --- sin conexión: TOTALES_INCONSISTENTES (D2, SYN-06) ------------------------------------


def test_syn06_los_brutos_y_el_total_enviados_coinciden_con_el_motor() -> None:
    enviadas = [_valores(), _valores(LINEA_CERVEZA, precio="9000.00", bruto="4500.00")]
    brutos_del_motor = {LINEA_VINO: Decimal("31250.00"), LINEA_CERVEZA: Decimal("4500.00")}

    verificar_totales_offline(enviadas, brutos_del_motor, Decimal("35750.00"), Decimal("35750.00"))


def test_syn06_un_bruto_enviado_distinto_del_que_da_el_motor_es_inconsistente() -> None:
    """Spec: "bruto enviado no es `precio × cantidad base / unidades` redondeado"."""
    enviadas = [_valores(bruto="31000.00")]

    with pytest.raises(TotalesInconsistentesError) as error:
        verificar_totales_offline(
            enviadas, {LINEA_VINO: Decimal("31250.00")}, Decimal("31000.00"), Decimal("31250.00")
        )

    assert error.value.codigo == "TOTALES_INCONSISTENTES"
    assert error.value.status_http == 422


def test_inv14_un_total_enviado_distinto_del_calculado_es_inconsistente() -> None:
    with pytest.raises(TotalesInconsistentesError):
        verificar_totales_offline(
            [_valores()], {LINEA_VINO: Decimal("31250.00")}, Decimal("31250.00"), Decimal("1.00")
        )


def test_syn06_el_motor_no_calculo_una_linea_enviada_es_inconsistente() -> None:
    with pytest.raises(TotalesInconsistentesError):
        verificar_totales_offline([_valores()], {}, Decimal("31250.00"), Decimal("31250.00"))


# --- LISTA_NO_VIGENTE sin conexión (D7) ------------------------------------------------


def test_syn07_la_version_enviada_vigente_no_se_observa() -> None:
    assert observacion_lista_no_vigente(VERSION_4, VERSION_4) is None


def test_syn07_la_version_enviada_que_no_es_la_vigente_se_observa_una_vez() -> None:
    observacion = observacion_lista_no_vigente(VERSION_3, VERSION_4)

    assert observacion is not None
    assert observacion.codigo == "LISTA_NO_VIGENTE"
    assert observacion.detalle == {
        "version_enviada_id": str(VERSION_3),
        "version_vigente_id": str(VERSION_4),
    }


def test_syn07_sin_version_vigente_la_enviada_se_observa() -> None:
    observacion = observacion_lista_no_vigente(VERSION_3, None)

    assert observacion is not None
    assert observacion.detalle == {
        "version_enviada_id": str(VERSION_3),
        "version_vigente_id": None,
    }


# --- unidades de referencia sin conexión (tarea 11.2, SYN-06) -----------------------------------


def test_unidades_de_referencia_de_uno_en_adelante_no_se_rechazan() -> None:
    verificar_unidades_de_referencia([_valores(unidades=1), _valores(LINEA_CERVEZA, unidades=12)])


@pytest.mark.parametrize("unidades", [0, -6])
def test_unidades_de_referencia_menores_que_uno_son_totales_inconsistentes(unidades: int) -> None:
    """Un comando malformado (la base lo prohíbe): se rechaza nombrando la línea."""
    with pytest.raises(TotalesInconsistentesError) as error:
        verificar_unidades_de_referencia([_valores(), _valores(LINEA_CERVEZA, unidades=unidades)])

    assert error.value.extension == {"linea_id": str(LINEA_CERVEZA)}


def test_prc23_versiones_uniformes_en_lineas_y_cabecera_no_se_rechazan() -> None:
    """Decisión del usuario, 2026-10-20: una sola versión en todo el comando sin conexión."""
    verificar_version_uniforme(VERSION_3, [VERSION_3, VERSION_3])
    verificar_version_uniforme(None, [VERSION_4, VERSION_4])


def test_prc23_lineas_con_versiones_distintas_son_version_no_permitida() -> None:
    with pytest.raises(VersionNoPermitidaError):
        verificar_version_uniforme(None, [VERSION_3, VERSION_4])


def test_prc23_la_cabecera_distinta_de_las_lineas_es_version_no_permitida() -> None:
    with pytest.raises(VersionNoPermitidaError):
        verificar_version_uniforme(VERSION_4, [VERSION_3, VERSION_3])
