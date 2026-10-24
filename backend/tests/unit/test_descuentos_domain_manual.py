"""Change 16, tarea 12.2: evaluación del descuento manual (spec `descuentos/descuento-manual`,
requisitos "El descuento manual exige que la organización lo habilite y el permiso del usuario" y
"El tope del rol decide si el descuento manual necesita autorización"; DSC-06, TR-02, INV-03;
`design.md` D11, D12). Los casos de la tabla compartida están en
`tests/fixtures_compartidos/test_dsc06_descuento_manual_fixtures.py`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.modules.descuentos.domain.manual import (
    Autorizador,
    evaluar_descuento_manual,
    rechazos_del_descuento_manual,
)
from app.modules.descuentos.domain.motor import calcular_descuentos
from app.modules.descuentos.domain.tipos import LineaVenta

DM = "DESCUENTO_MANUAL"
AU = "AUTORIZAR_DESCUENTO"


def _evaluar(**cambios: Any) -> Any:
    argumentos: dict[str, Any] = {
        "usuario_id": "u-vendedor",
        "descuento_manual_habilitado": True,
        "motivo_obligatorio": None,
        "permisos_usuario": frozenset({DM}),
        "tope_rol": Decimal("0.050000"),
        "tope_propio": None,
        "porcentaje_maximo": Decimal("0.030000"),
        "motivo": None,
        "autorizador": None,
    }
    argumentos.update(cambios)
    return evaluar_descuento_manual(**argumentos)


def _linea(id_: str, bruto: str, manual: str | None = None) -> LineaVenta:
    return LineaVenta(
        id=id_,
        bruto=Decimal(bruto),
        cantidad_base=1,
        unidades_referencia=1,
        producto_id=f"p-{id_}",
        categoria_id="c",
        marca_id="m",
        descuento_manual=None if manual is None else Decimal(manual),
    )


def test_el_resultado_informa_tope_autorizacion_resolucion_y_autorizador() -> None:
    resultado = _evaluar(
        porcentaje_maximo=Decimal("0.100000"),
        autorizador=Autorizador("u-supervisora", frozenset({DM, AU})),
    )

    assert resultado.tope_aplicado == Decimal("0.050000")
    assert resultado.requirio_autorizacion is True
    assert resultado.resolucion == "AUTORIZADO_POR_SUPERVISOR"
    assert resultado.autorizador_id == "u-supervisora"


def test_dentro_del_tope_no_informa_autorizador() -> None:
    resultado = _evaluar()

    assert resultado.requirio_autorizacion is False
    assert resultado.resolucion == "DENTRO_DEL_TOPE"
    assert resultado.autorizador_id is None


def test_el_propio_usuario_sin_permiso_no_se_autoriza_pasandose_como_autorizador() -> None:
    """Un vendedor no se autoriza a sí mismo (SEG-06)."""
    with pytest.raises(Exception) as error:  # noqa: B017
        _evaluar(
            porcentaje_maximo=Decimal("0.100000"),
            autorizador=Autorizador("u-vendedor", frozenset({DM})),
        )

    assert error.value.codigo == "AUTORIZADOR_SIN_PERMISO"  # type: ignore[attr-defined]


def test_el_porcentaje_a_evaluar_es_el_maximo_que_entrega_el_motor() -> None:
    """General 5% y una línea propia de 10%: el máximo del motor es 10% y, con tope 5%, hace
    falta una autorización (D11, D12)."""
    resultado_motor = calcular_descuentos(
        [_linea("a", "135240.00", "0.100000"), _linea("b", "84280.00")],
        [],
        Decimal("0.050000"),
    )
    assert resultado_motor.porcentaje_manual_maximo == Decimal("0.100000")

    with pytest.raises(Exception) as error:  # noqa: B017
        _evaluar(porcentaje_maximo=resultado_motor.porcentaje_manual_maximo)
    assert error.value.codigo == "AUTORIZACION_REQUERIDA"  # type: ignore[attr-defined]

    supervisora = Autorizador("u-supervisora", frozenset({DM, AU}))
    resultado = _evaluar(
        porcentaje_maximo=resultado_motor.porcentaje_manual_maximo, autorizador=supervisora
    )
    assert resultado.resolucion == "AUTORIZADO_POR_SUPERVISOR"


def test_un_propio_menor_que_el_general_no_dispara_la_autorizacion() -> None:
    """General 5% y una línea propia de 3%: el máximo es 5% y está dentro del tope 5%."""
    resultado_motor = calcular_descuentos(
        [_linea("a", "135240.00", "0.030000"), _linea("b", "84280.00")],
        [],
        Decimal("0.050000"),
    )

    resultado = _evaluar(porcentaje_maximo=resultado_motor.porcentaje_manual_maximo)

    assert resultado.resolucion == "DENTRO_DEL_TOPE"


def test_el_general_reemplazado_en_todas_las_lineas_no_cuenta() -> None:
    """General 10% reemplazado en todas las líneas por 3% y 2%: el máximo es 3%, dentro del
    tope 5% aunque el general lo superaba."""
    resultado_motor = calcular_descuentos(
        [_linea("a", "135240.00", "0.030000"), _linea("b", "84280.00", "0.020000")],
        [],
        Decimal("0.100000"),
    )

    resultado = _evaluar(porcentaje_maximo=resultado_motor.porcentaje_manual_maximo)

    assert resultado.resolucion == "DENTRO_DEL_TOPE"
    assert resultado_motor.porcentaje_manual_maximo == Decimal("0.030000")


@pytest.mark.parametrize("invalido", [Decimal("0"), Decimal("-0.01"), Decimal("1.000001"), 0.05])
def test_un_porcentaje_fuera_de_dominio_se_rechaza(invalido: Any) -> None:
    with pytest.raises(Exception) as error:  # noqa: B017
        _evaluar(porcentaje_maximo=invalido)

    assert error.value.codigo == "DESCUENTO_MANUAL_INVALIDO"


# --- rechazos acumulados para la venta sin conexion (change 18b, D10 punto 4, SYN-05, INV-17) ---


def _rechazos(**cambios: Any) -> list[str]:
    argumentos: dict[str, Any] = {
        "descuento_manual_habilitado": True,
        "motivo_obligatorio": None,
        "permisos_usuario": frozenset({DM}),
        "tope_rol": Decimal("0.050000"),
        "tope_propio": None,
        "porcentaje_maximo": Decimal("0.030000"),
        "motivo": None,
        "autorizador": None,
    }
    argumentos.update(cambios)
    return [error.codigo for error in rechazos_del_descuento_manual(**argumentos)]


def test_d10_sin_ningun_rechazo_la_lista_es_vacia() -> None:
    assert _rechazos() == []


def test_d10_tope_y_motivo_se_acumulan_en_el_orden_del_evaluador() -> None:
    """El caso de la prueba manual: 10 % con tope 5 %, sin autorizador y sin motivo exigido."""
    assert _rechazos(porcentaje_maximo=Decimal("0.100000"), motivo_obligatorio=True) == [
        "MOTIVO_REQUERIDO",
        "AUTORIZACION_REQUERIDA",
    ]


def test_d10_permiso_y_motivo_se_acumulan() -> None:
    assert _rechazos(permisos_usuario=frozenset(), motivo_obligatorio=True) == [
        "PERMISO_REQUERIDO",
        "MOTIVO_REQUERIDO",
    ]


def test_d10_deshabilitado_permiso_motivo_y_tope_juntos() -> None:
    assert _rechazos(
        descuento_manual_habilitado=False,
        permisos_usuario=frozenset(),
        motivo_obligatorio=True,
        porcentaje_maximo=Decimal("0.100000"),
    ) == [
        "DESCUENTO_MANUAL_DESHABILITADO",
        "PERMISO_REQUERIDO",
        "MOTIVO_REQUERIDO",
        "AUTORIZACION_REQUERIDA",
    ]


def test_d10_un_autorizador_sin_permiso_da_solo_esa_causa_y_no_tope() -> None:
    assert _rechazos(
        porcentaje_maximo=Decimal("0.100000"), autorizador=Autorizador("u-luis", frozenset({DM}))
    ) == ["AUTORIZADOR_SIN_PERMISO"]


def test_d10_con_permiso_propio_sobre_el_tope_no_hay_rechazo_de_tope() -> None:
    assert (
        _rechazos(permisos_usuario=frozenset({DM, AU}), porcentaje_maximo=Decimal("0.100000")) == []
    )


def test_d10_el_rechazo_unico_sigue_siendo_unico() -> None:
    assert _rechazos(motivo_obligatorio=True) == ["MOTIVO_REQUERIDO"]


def test_d10_el_evaluador_con_conexion_sigue_rechazando_con_el_primer_error() -> None:
    with pytest.raises(Exception) as error:  # noqa: B017
        _evaluar(porcentaje_maximo=Decimal("0.100000"), motivo_obligatorio=True)

    assert error.value.codigo == "MOTIVO_REQUERIDO"


def test_d10_un_porcentaje_fuera_de_dominio_sigue_siendo_excepcion() -> None:
    with pytest.raises(Exception) as error:  # noqa: B017
        _rechazos(porcentaje_maximo=Decimal("0"))

    assert error.value.codigo == "DESCUENTO_MANUAL_INVALIDO"
