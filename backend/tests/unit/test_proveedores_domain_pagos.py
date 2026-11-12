"""Pruebas unitarias del dominio puro de pagos a proveedores (change 12, grupo 3,
tarea 3.1; `specs/proveedores/pagos-a-proveedores/spec.md`).

`validar_medios(importe, medios)` es la parte compartida con el pago de contado de una
compra (CMP-03, ADR-043 punto 2): de 1 a 20 medios de importe positivo con 2 decimales,
referencia donde el medio la exige y suma exactamente igual al importe (INV-08,
`design.md` D6). Es pura: no consulta la base ni conoce el estado de los medios (eso lo
resuelve el servicio, `MEDIO_PAGO_INACTIVO` e INV-21 son de otra capa).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.proveedores.domain.errores import (
    FechaInvalidaError,
    ImporteInvalidoError,
    MediosInvalidosError,
    MediosNoSumanImporteError,
    PagoDeCompraVigienteError,
    PagoYaAnuladoError,
    ReferenciaObligatoriaError,
)
from app.modules.proveedores.domain.pagos import (
    validar_medios,
    validar_pago_a_anular,
    validar_pago_independiente,
)

HOY = date(2026, 10, 1)
"""Fecha de negocio de hoy en la zona de la organización (1 de octubre, D4)."""

MAXIMO_MEDIOS = 20
"""D6: de 1 a 20 medios por pago."""


@dataclass(frozen=True)
class Medio:
    """El medio tal como llega al dominio: importe, referencia informada y si el medio de
    la organización la exige. Los medios reales del dominio de compras satisfacen este
    mismo contrato (`proveedores.domain.compras.MedioDeEntrada`)."""

    importe: Decimal
    referencia: str | None = None
    requiere_referencia: bool = False


def medio(importe: str, *, referencia: str | None = None, exige: bool = False) -> Medio:
    return Medio(importe=Decimal(importe), referencia=referencia, requiere_referencia=exige)


def medios_de_cheques(cantidad: int, *, importe: str = "100.00") -> list[Medio]:
    return [medio(importe, referencia=f"cheque-{indice}", exige=True) for indice in range(cantidad)]


# --- cantidad de medios (MEDIOS_INVALIDOS) ------------------------------------------------


def test_pago_con_un_solo_medio_que_suma_el_importe_es_valido() -> None:
    validar_medios(Decimal("152460.00"), [medio("152460.00")])


def test_pago_sin_medios_se_rechaza_con_medios_invalidos() -> None:
    """Spec, escenario "Pago sin medios": `MEDIOS_INVALIDOS` (no `MEDIOS_NO_SUMAN_IMPORTE`:
    el pago a proveedor exige de 1 a 20 medios, `design.md` D6)."""
    with pytest.raises(MediosInvalidosError) as error:
        validar_medios(Decimal("152460.00"), [])

    assert error.value.codigo == "MEDIOS_INVALIDOS"


def test_pago_con_veinte_medios_es_valido() -> None:
    """El límite superior es 20 y entra: veinte cheques de $1, cada uno con su referencia."""
    validar_medios(Decimal("20.00"), medios_de_cheques(MAXIMO_MEDIOS, importe="1.00"))


def test_pago_con_veintiuno_medios_se_rechaza_con_medios_invalidos() -> None:
    """Spec, escenario "Más de 20 medios"."""
    with pytest.raises(MediosInvalidosError) as error:
        validar_medios(Decimal("21.00"), medios_de_cheques(MAXIMO_MEDIOS + 1, importe="1.00"))

    assert error.value.codigo == "MEDIOS_INVALIDOS"
    assert "21" in str(error.value)


# --- suma exacta (INV-08, MEDIOS_NO_SUMAN_IMPORTE) ----------------------------------------


def test_efectivo_y_transferencia_que_suman_el_importe_son_validos() -> None:
    """Spec, escenario "Pago con efectivo y transferencia"."""
    validar_medios(
        Decimal("152460.00"),
        [medio("100000.00"), medio("52460.00", referencia="0042", exige=True)],
    )


@pytest.mark.parametrize(
    "importes",
    [
        ["150000.00"],
        ["100000.00", "52460.01"],
        ["152460.00", "0.01"],
    ],
)
def test_inv08_medios_que_suman_menos_se_rechazan(importes: list[str]) -> None:
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_medios(Decimal("152460.00"), [medio(i) for i in importes])

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


def test_inv08_medios_que_suman_mas_se_rechazan() -> None:
    """El caso simétrico del anterior: el sobrante también se rechaza (INV-08 es suma
    exacta, no "suma al menos")."""
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_medios(Decimal("152460.00"), [medio("100000.00"), medio("52460.00"), medio("0.01")])

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


def test_el_mismo_medio_puede_repetirse_con_referencias_distintas() -> None:
    """Spec, escenario "El mismo medio dos veces" (dos cheques)."""
    validar_medios(
        Decimal("152460.00"),
        [
            medio("100000.00", referencia="0001", exige=True),
            medio("52460.00", referencia="0002", exige=True),
        ],
    )


# --- importe del medio y del pago (IMPORTE_INVALIDO, TR-01) -------------------------------


@pytest.mark.parametrize("importe_medio", ["0.00", "-100.00"])
def test_medio_con_importe_no_positivo_se_rechaza(importe_medio: str) -> None:
    with pytest.raises(ImporteInvalidoError) as error:
        validar_medios(Decimal("100.00"), [medio(importe_medio)])

    assert error.value.codigo == "IMPORTE_INVALIDO"


def test_medio_con_tres_decimales_se_rechaza() -> None:
    """Spec, escenario "Importe inválido" (`"100000.001"`)."""
    with pytest.raises(ImporteInvalidoError) as error:
        validar_medios(Decimal("100.00"), [medio("100.001")])

    assert error.value.codigo == "IMPORTE_INVALIDO"


@pytest.mark.parametrize("importe_pago", ["0.00", "-100.00", "100.001"])
def test_importe_del_pago_invalido_se_rechaza(importe_pago: str) -> None:
    """El importe del pago también es mayor que cero con 2 decimales: sin esto, un importe
    inválido solo se detectaría al compararlo con la suma de medios."""
    with pytest.raises(ImporteInvalidoError) as error:
        validar_medios(Decimal(importe_pago), [medio("100.00")])

    assert error.value.codigo == "IMPORTE_INVALIDO"


# --- referencia obligatoria (REFERENCIA_OBLIGATORIA) --------------------------------------


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_medio_que_exige_referencia_sin_referencia_se_rechaza(referencia: str | None) -> None:
    """Spec, escenario "Medio que exige referencia sin referencia" (`01` §4)."""
    with pytest.raises(ReferenciaObligatoriaError) as error:
        validar_medios(Decimal("100.00"), [medio("100.00", referencia=referencia, exige=True)])

    assert error.value.codigo == "REFERENCIA_OBLIGATORIA"


def test_referencia_de_solo_espacios_con_referencia_informada_no_se_rechaza() -> None:
    """Caso simétrico: la referencia se guarda recortada, así que un medio que la exige
    queda satisfecho con espacios alrededor, que se recortan después."""
    validar_medios(Decimal("100.00"), [medio("100.00", referencia=" 0042 ", exige=True)])


# --- errores de dominio (código estable) --------------------------------------------------


@pytest.mark.parametrize(
    "codigo_esperado",
    ["MEDIOS_INVALIDOS", "IMPORTE_INVALIDO", "REFERENCIA_OBLIGATORIA"],
)
def test_los_errores_de_pago_son_domain_error_422(codigo_esperado: str) -> None:
    """Mismo criterio de estado que el resto de `proveedores` (`errores.py`): 422 para
    validaciones de contenido."""
    with pytest.raises(DomainError) as error:
        if codigo_esperado == "MEDIOS_INVALIDOS":
            validar_medios(Decimal("100.00"), [])
        elif codigo_esperado == "IMPORTE_INVALIDO":
            validar_medios(Decimal("100.00"), [medio("0.00")])
        else:
            validar_medios(Decimal("100.00"), [medio("100.00", exige=True)])

    assert error.value.codigo == codigo_esperado
    assert error.value.status_http == 422


# --- INV-08 como propiedad (spec, escenario "INV-08 — propiedad sobre pagos aceptados") ----


def _centavos_a_importe(centavos: int) -> Decimal:
    """Entero a `Decimal` con exactamente 2 decimales, sin pasar por `float`."""
    return Decimal(centavos).scaleb(-2)


@settings(max_examples=200, deadline=None)
@given(
    centavos=st.lists(
        st.integers(min_value=1, max_value=50_000_000), min_size=1, max_size=MAXIMO_MEDIOS
    )
)
def test_inv08_todo_pago_aceptado_tiene_medios_que_suman_su_importe(centavos: list[int]) -> None:
    medios = [Medio(_centavos_a_importe(valor)) for valor in centavos]
    importe = sum((medio.importe for medio in medios), Decimal("0.00"))

    validar_medios(importe, medios)

    assert sum((medio.importe for medio in medios), Decimal("0.00")) == importe


@settings(max_examples=200, deadline=None)
@given(
    centavos=st.lists(
        st.integers(min_value=1, max_value=50_000_000), min_size=1, max_size=MAXIMO_MEDIOS
    )
)
def test_inv08_un_centavo_de_diferencia_se_rechaza_siempre(centavos: list[int]) -> None:
    """La contraparte: si la suma se desvía, el pago se rechaza con
    `MEDIOS_NO_SUMAN_IMPORTE` (INV-08 se verifica, no se supone)."""
    importes = [valor + 1 for valor in centavos]
    medios = [Medio(_centavos_a_importe(valor)) for valor in importes]
    importe_original = sum((_centavos_a_importe(valor) for valor in centavos), Decimal("0.00"))

    with pytest.raises(MediosNoSumanImporteError):
        validar_medios(importe_original, medios)


# --- pago independiente: importe, fecha y observacion (tarea 3.2, D4, D6) -----------------


def test_pago_independiente_valido_devuelve_la_observacion_sin_recortar_nada_mas() -> None:
    """Spec, escenario "Pago con un solo medio y observación"."""
    observacion = validar_pago_independiente(
        Decimal("100000.00"), date(2026, 9, 28), "  paga factura 0001-123  ", hoy=HOY
    )

    assert observacion == "paga factura 0001-123"


@pytest.mark.parametrize("observacion", [None, "", "   "])
def test_pago_independiente_sin_observacion_devuelve_none(observacion: str | None) -> None:
    """D6: la observación vacía equivale a no informarla (columna nulable, D9)."""
    assert (
        validar_pago_independiente(Decimal("100000.00"), date(2026, 9, 28), observacion, hoy=HOY)
        is None
    )


def test_pago_independiente_con_fecha_de_hoy_es_valido() -> None:
    """D4: la fecha del pago real no puede ser futura; hoy sí es válida (no hay límite
    hacia atrás)."""
    assert validar_pago_independiente(Decimal("100000.00"), HOY, None, hoy=HOY) is None


@pytest.mark.parametrize("dias", [1, 10])
def test_pago_independiente_con_fecha_futura_se_rechaza(dias: int) -> None:
    """Spec, escenario "Fecha futura": `FECHA_INVALIDA` (TR-04)."""
    with pytest.raises(FechaInvalidaError) as error:
        validar_pago_independiente(
            Decimal("100000.00"), date(2026, 10, 1) + timedelta(days=dias), None, hoy=HOY
        )

    assert error.value.codigo == "FECHA_INVALIDA"


@pytest.mark.parametrize("importe", ["0.00", "100000.001"])
def test_pago_independiente_con_importe_invalido_se_rechaza(importe: str) -> None:
    """Spec, escenario "Importe inválido": `IMPORTE_INVALIDO` (TR-01)."""
    with pytest.raises(ImporteInvalidoError) as error:
        validar_pago_independiente(Decimal(importe), date(2026, 9, 28), None, hoy=HOY)

    assert error.value.codigo == "IMPORTE_INVALIDO"


# --- reglas puras de la anulacion (tarea 3.2, D2, PAG-03, CMP-05) ----------------------


@pytest.mark.parametrize("origen", ["INDEPENDIENTE", "COMPRA"])
def test_anular_un_pago_ya_anulado_se_rechaza(origen: str) -> None:
    """Spec, escenarios "Pago ya anulado" y "Pago de una compra anulada con devolución":
    los dos caminos llegan al mismo `PAGO_YA_ANULADO`."""
    with pytest.raises(PagoYaAnuladoError) as error:
        validar_pago_a_anular("ANULADA", origen, "ANULADA")

    assert error.value.codigo == "PAGO_YA_ANULADO"
    assert error.value.status_http == 409


def test_anular_el_pago_de_una_compra_confirmada_se_rechaza() -> None:
    """Spec, escenario "Pago de una compra vigente": `PAGO_DE_COMPRA_VIGENTE` (CMP-05, D2)."""
    with pytest.raises(PagoDeCompraVigienteError) as error:
        validar_pago_a_anular("CONFIRMADA", "COMPRA", "CONFIRMADA")

    assert error.value.codigo == "PAGO_DE_COMPRA_VIGENTE"
    assert error.value.status_http == 409


def test_anular_el_pago_de_una_compra_ya_anulada_se_admite() -> None:
    """Spec, escenario "Pago de una compra anulada sin devolución": el proveedor devuelve
    el dinero después y el pago se anula por separado (D2)."""
    validar_pago_a_anular("CONFIRMADA", "COMPRA", "ANULADA")


def test_anular_un_pago_independiente_se_admite() -> None:
    """Spec, escenario "Anulación de un pago independiente": no hay compra que consultar."""
    validar_pago_a_anular("CONFIRMADA", "INDEPENDIENTE", None)


def test_pago_ya_anulado_tiene_prioridad_sobre_la_compra_vigente() -> None:
    """El orden de las reglas no es arbitrario: si el pago ya está `ANULADA`, el código es
    `PAGO_YA_ANULADO` aunque su compra siga `CONFIRMADA` (es el resultado que ve el
    cliente que reintenta, no `PAGO_DE_COMPRA_VIGENTE`)."""
    with pytest.raises(PagoYaAnuladoError):
        validar_pago_a_anular("ANULADA", "COMPRA", "CONFIRMADA")
