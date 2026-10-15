"""Change 16, tarea 7.1: validación de una regla de descuento (spec `descuentos/reglas-de-
descuento`, requisitos "Una regla de descuento se crea por comando como borrador" y "El alcance de
una regla es coherente con su tipo"; DSC-01 a DSC-04, TR-02, INV-03, INV-04)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.errores import (
    AccionInvalidaError,
    AlcanceInvalidoError,
    NombreInvalidoError,
    PrioridadInvalidaError,
    ReglaDescuentoInvalidaError,
    UmbralInvalidoError,
    VigenciaInvalidaError,
)
from app.modules.descuentos.domain.reglas import AlcanceNuevo, validar_regla

DESDE = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
HASTA = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
MARCA = "0192b1c2-0000-7000-8000-000000000001"
CATEGORIA = "0192b1c2-0000-7000-8000-000000000002"


def _regla(**cambios: Any) -> dict[str, Any]:
    """Una regla válida de operación: cajas equivalentes >= 20 -> 5%."""
    valores: dict[str, Any] = {
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": "20",
        "accion_tipo": "PORCENTAJE",
        "accion_valor": "0.050000",
        "prioridad": 1,
        "acumulable": False,
        "alcances": (),
        "vigencia_desde": None,
        "vigencia_hasta": None,
    }
    valores.update(cambios)
    return valores


# --- caso feliz y normalización ---------------------------------------------


def test_una_regla_de_operacion_valida_se_normaliza() -> None:
    validada = validar_regla(**_regla(nombre="  Volumen 20 cajas  "))

    assert validada.nombre == "Volumen 20 cajas"
    assert validada.umbral == Decimal("20.0000")
    assert validada.accion_porcentaje == Decimal("0.050000")
    assert validada.accion_importe is None
    assert validada.alcances == ()


def test_una_regla_de_alcance_con_importe_fijo_guarda_el_importe_y_no_el_porcentaje() -> None:
    validada = validar_regla(
        **_regla(
            tipo="VOLUMEN_ALCANCE",
            medida="UNIDADES_BASE",
            operador="GT",
            umbral="60",
            accion_tipo="IMPORTE_FIJO",
            accion_valor="1000.00",
            alcances=(AlcanceNuevo("MARCA", MARCA),),
        )
    )

    assert validada.accion_importe == Decimal("1000.00")
    assert validada.accion_porcentaje is None
    assert validada.alcances == (AlcanceNuevo("MARCA", MARCA),)


# --- listas cerradas (DSC-02 a DSC-04) --------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"tipo": "VOLUMEN_CLIENTE"},
        {"medida": "HISTORIAL_DE_COMPRAS"},
        {"operador": "LT"},
        {"accion_tipo": "BONIFICACION_EN_UNIDADES"},
        {"medida": "cajas_equivalentes"},
    ],
)
def test_un_valor_fuera_de_las_listas_cerradas_se_rechaza(cambios: dict[str, Any]) -> None:
    with pytest.raises(ReglaDescuentoInvalidaError):
        validar_regla(**_regla(**cambios))


# --- nombre -----------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n"])
def test_el_nombre_vacio_se_rechaza(nombre: str) -> None:
    with pytest.raises(NombreInvalidoError) as error:
        validar_regla(**_regla(nombre=nombre))
    assert error.value.codigo == "NOMBRE_INVALIDO"


# --- umbral (DSC-03, INV-04, TR-01) ---------------------------------------------------


@pytest.mark.parametrize(
    ("medida", "umbral"),
    [
        ("UNIDADES_BASE", "10.5"),  # unidades base: entero
        ("CAJAS_EQUIVALENTES", "0"),
        ("CAJAS_EQUIVALENTES", "-1"),
        ("UNIDADES_BASE", "0"),
        ("IMPORTE_BRUTO", "-5.00"),
        ("IMPORTE_BRUTO", "100.005"),  # importe: hasta 2 decimales
        ("CAJAS_EQUIVALENTES", "1.00001"),  # cajas: hasta 4 decimales
        ("CAJAS_EQUIVALENTES", "abc"),
        ("CAJAS_EQUIVALENTES", "NaN"),
        ("IMPORTE_BRUTO", "10000000000"),  # no entra en numeric(14,4)
    ],
)
def test_un_umbral_invalido_para_la_medida_se_rechaza(medida: str, umbral: str) -> None:
    with pytest.raises(UmbralInvalidoError) as error:
        validar_regla(**_regla(medida=medida, umbral=umbral))
    assert error.value.codigo == "UMBRAL_INVALIDO"


@pytest.mark.parametrize(
    ("medida", "umbral", "esperado"),
    [
        ("UNIDADES_BASE", "60", Decimal("60.0000")),
        ("CAJAS_EQUIVALENTES", "19.8333", Decimal("19.8333")),
        ("CAJAS_EQUIVALENTES", "20.5", Decimal("20.5000")),
        ("IMPORTE_BRUTO", "31250.00", Decimal("31250.0000")),
        ("IMPORTE_BRUTO", "200000", Decimal("200000.0000")),
    ],
)
def test_un_umbral_valido_para_la_medida_se_acepta(
    medida: str, umbral: str, esperado: Decimal
) -> None:
    assert validar_regla(**_regla(medida=medida, umbral=umbral)).umbral == esperado


def test_un_umbral_float_se_rechaza_por_inv03() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        validar_regla(**_regla(umbral=20.5))


# --- acción (DSC-04, TR-02, INV-03) -----------------------------------------------------


@pytest.mark.parametrize(
    ("accion_tipo", "valor"),
    [
        ("PORCENTAJE", "0"),
        ("PORCENTAJE", "1.200000"),
        ("PORCENTAJE", "0.1234567"),  # siete decimales
        ("PORCENTAJE", "-0.05"),
        ("PORCENTAJE", "cinco"),
        ("IMPORTE_FIJO", "0"),
        ("IMPORTE_FIJO", "-10.00"),
        ("IMPORTE_FIJO", "10.001"),  # tres decimales
        ("IMPORTE_FIJO", "1000000000000"),  # no entra en numeric(14,2)
    ],
)
def test_una_accion_invalida_se_rechaza(accion_tipo: str, valor: str) -> None:
    with pytest.raises(AccionInvalidaError) as error:
        validar_regla(**_regla(accion_tipo=accion_tipo, accion_valor=valor))
    assert error.value.codigo == "ACCION_INVALIDA"


@pytest.mark.parametrize(
    ("accion_tipo", "valor"),
    [
        ("PORCENTAJE", "1"),
        ("PORCENTAJE", "0.000001"),
        ("PORCENTAJE", "0.125"),
        ("IMPORTE_FIJO", "0.01"),
        ("IMPORTE_FIJO", "1000"),
    ],
)
def test_una_accion_en_el_borde_del_dominio_se_acepta(accion_tipo: str, valor: str) -> None:
    validar_regla(**_regla(accion_tipo=accion_tipo, accion_valor=valor))


@pytest.mark.parametrize("accion_tipo", ["PORCENTAJE", "IMPORTE_FIJO"])
def test_un_valor_de_accion_float_se_rechaza_por_inv03(accion_tipo: str) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        validar_regla(**_regla(accion_tipo=accion_tipo, accion_valor=0.05))


# --- prioridad (D8) ---------------------------------------------------------------------


@pytest.mark.parametrize("prioridad", [0, -1, 1.5, "1", True, 2_147_483_648])
def test_una_prioridad_invalida_se_rechaza(prioridad: Any) -> None:
    with pytest.raises(PrioridadInvalidaError) as error:
        validar_regla(**_regla(prioridad=prioridad))
    assert error.value.codigo == "PRIORIDAD_INVALIDA"


@pytest.mark.parametrize("prioridad", [1, 7, 2_147_483_647])
def test_una_prioridad_entera_desde_1_se_acepta(prioridad: int) -> None:
    assert validar_regla(**_regla(prioridad=prioridad)).prioridad == prioridad


# --- alcances (DSC-02, `03` §11) ----------------------------------------------------------


def test_una_regla_de_operacion_con_alcances_se_rechaza() -> None:
    with pytest.raises(AlcanceInvalidoError) as error:
        validar_regla(**_regla(alcances=(AlcanceNuevo("CATEGORIA", CATEGORIA),)))
    assert error.value.codigo == "ALCANCE_INVALIDO"


def test_una_regla_de_alcance_sin_alcances_se_rechaza() -> None:
    with pytest.raises(AlcanceInvalidoError):
        validar_regla(**_regla(tipo="VOLUMEN_ALCANCE", alcances=()))


def test_un_alcance_repetido_se_rechaza() -> None:
    with pytest.raises(AlcanceInvalidoError):
        validar_regla(
            **_regla(
                tipo="VOLUMEN_ALCANCE",
                alcances=(AlcanceNuevo("MARCA", MARCA), AlcanceNuevo("MARCA", MARCA)),
            )
        )


def test_el_mismo_id_con_otro_tipo_de_alcance_no_es_repetido() -> None:
    validada = validar_regla(
        **_regla(
            tipo="VOLUMEN_ALCANCE",
            alcances=(AlcanceNuevo("MARCA", MARCA), AlcanceNuevo("CATEGORIA", MARCA)),
        )
    )
    assert len(validada.alcances) == 2


def test_un_tipo_de_alcance_desconocido_se_rechaza() -> None:
    with pytest.raises(AlcanceInvalidoError):
        validar_regla(
            **_regla(tipo="VOLUMEN_ALCANCE", alcances=(AlcanceNuevo("PROVEEDOR", MARCA),))
        )


# --- vigencia (D16) ------------------------------------------------------------------------


@pytest.mark.parametrize("hasta", [DESDE, datetime(2026, 10, 1, tzinfo=UTC)])
def test_una_vigencia_hasta_no_posterior_a_la_desde_se_rechaza(hasta: datetime) -> None:
    with pytest.raises(VigenciaInvalidaError) as error:
        validar_regla(**_regla(vigencia_desde=DESDE, vigencia_hasta=hasta))
    assert error.value.codigo == "VIGENCIA_INVALIDA"


def test_una_vigencia_ordenada_o_incompleta_se_acepta() -> None:
    assert (
        validar_regla(**_regla(vigencia_desde=DESDE, vigencia_hasta=HASTA)).vigencia_hasta == HASTA
    )
    assert validar_regla(**_regla(vigencia_desde=DESDE)).vigencia_hasta is None
    assert validar_regla(**_regla(vigencia_hasta=HASTA)).vigencia_desde is None
