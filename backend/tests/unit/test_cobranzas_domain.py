"""Tareas 6.1 y 6.2 (change 17): dominio puro de cobranzas (`cobranzas/domain/`;
`specs/cobranzas/registro-de-cobranzas/spec.md` y `anulacion-de-cobranzas/spec.md`;
COB-01, COB-02, COB-05, TR-01, INV-03, INV-08, SYN-05, SYN-07, INV-17; `design.md` D2, D4, D7,
D13).

La validación de medios es la función compartida de `configuracion/domain/medios.py` (D17); acá
se prueba lo propio de la cobranza: la observación, el consumidor final, las dos formas de
evaluarla (con conexión rechaza; sin conexión solo rechaza lo malformado y observa el resto) y
las reglas de la anulación.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.errors import DomainError
from app.modules.cobranzas.domain.cobranza import (
    CODIGO_CLIENTE_NO_HABILITADO,
    CODIGO_MEDIO_INACTIVO,
    CODIGO_REFERENCIA_FALTANTE,
    ESTADO_ANULADA,
    ESTADO_CONFIRMADA,
    MAXIMO_OBSERVACION,
    ORIGEN_INDEPENDIENTE,
    ORIGEN_VENTA,
    MedioResuelto,
    evaluar_cobranza_offline,
    recortar_observacion,
    validar_cobranza,
    validar_cobranza_a_anular,
    validar_observacion,
)
from app.modules.cobranzas.domain.errores import (
    CobranzaDeVentaError,
    CobranzaYaAnuladaError,
    ConsumidorFinalSinCuentaError,
    ObservacionInvalidaError,
)
from app.modules.configuracion.domain.medios import (
    ImporteInvalidoError,
    MediosInvalidosError,
    MediosNoSumanImporteError,
    ReferenciaObligatoriaError,
)

CLIENTE_ID = UUID("0198f3a0-0000-7000-8000-000000000001")
EFECTIVO_ID = UUID("0198f3a0-0000-7000-8000-0000000000e1")
TRANSFERENCIA_ID = UUID("0198f3a0-0000-7000-8000-0000000000e2")
BILLETERA_ID = UUID("0198f3a0-0000-7000-8000-0000000000e3")


def efectivo(importe: str, *, activo: bool = True) -> MedioResuelto:
    return MedioResuelto(
        medio_pago_id=EFECTIVO_ID,
        nombre="Efectivo",
        importe=Decimal(importe),
        referencia=None,
        requiere_referencia=False,
        activo=activo,
    )


def transferencia(
    importe: str, *, referencia: str | None = "0042", activo: bool = True
) -> MedioResuelto:
    return MedioResuelto(
        medio_pago_id=TRANSFERENCIA_ID,
        nombre="Transferencia",
        importe=Decimal(importe),
        referencia=referencia,
        requiere_referencia=True,
        activo=activo,
    )


def billetera(importe: str, *, activo: bool = False) -> MedioResuelto:
    return MedioResuelto(
        medio_pago_id=BILLETERA_ID,
        nombre="Billetera",
        importe=Decimal(importe),
        referencia=None,
        requiere_referencia=False,
        activo=activo,
    )


# --- 6.1: la observación (D2) ----------------------------------------------------------


def test_la_observacion_se_recorta_y_vacia_es_nula() -> None:
    assert recortar_observacion("  paga facturas de septiembre  ") == "paga facturas de septiembre"
    assert recortar_observacion("   ") is None
    assert recortar_observacion("") is None
    assert recortar_observacion(None) is None


def test_la_observacion_de_exactamente_500_se_acepta_y_la_de_501_se_rechaza() -> None:
    """Spec "Observación demasiado larga": el largo se mide sobre el texto recibido."""
    assert validar_observacion("x" * MAXIMO_OBSERVACION) == "x" * MAXIMO_OBSERVACION
    with pytest.raises(ObservacionInvalidaError) as error:
        validar_observacion("x" * (MAXIMO_OBSERVACION + 1))

    assert error.value.status_http == 422


def test_el_largo_de_la_observacion_se_mide_antes_de_recortar() -> None:
    con_espacios = " " * 10 + "x" * MAXIMO_OBSERVACION
    with pytest.raises(ObservacionInvalidaError):
        validar_observacion(con_espacios)


# --- 6.1: con conexión (ONLINE) --------------------------------------------------------


def test_cobranza_con_efectivo_y_transferencia_es_valida_y_devuelve_la_observacion_recortada() -> (
    None
):
    """Spec "Cobranza con efectivo y transferencia" (COB-01, COB-02, INV-08)."""
    observacion = validar_cobranza(
        Decimal("50000.00"),
        [efectivo("30000.00"), transferencia("20000.00")],
        "  paga facturas de septiembre ",
        es_consumidor_final=False,
    )

    assert observacion == "paga facturas de septiembre"


def test_cobranza_sin_observacion_devuelve_none() -> None:
    assert (
        validar_cobranza(
            Decimal("20000.00"), [efectivo("20000.00")], None, es_consumidor_final=False
        )
        is None
    )


@pytest.mark.parametrize("importe", ["0.00", "-1.00", "50000.001"])
def test_importe_invalido_se_rechaza(importe: str) -> None:
    """Spec "Importe inválido" (TR-01, INV-03)."""
    with pytest.raises(ImporteInvalidoError) as error:
        validar_cobranza(Decimal(importe), [efectivo("50000.00")], None, es_consumidor_final=False)

    assert error.value.codigo == "IMPORTE_INVALIDO"


def test_sin_medios_o_con_veintiuno_se_rechaza_con_medios_invalidos() -> None:
    """Spec "Sin medios o con demasiados"."""
    with pytest.raises(MediosInvalidosError):
        validar_cobranza(Decimal("10.00"), [], None, es_consumidor_final=False)
    with pytest.raises(MediosInvalidosError):
        validar_cobranza(Decimal("21.00"), [efectivo("1.00")] * 21, None, es_consumidor_final=False)


def test_inv08_medios_que_no_suman_el_importe_se_rechazan() -> None:
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_cobranza(
            Decimal("50000.00"),
            [efectivo("30000.00"), transferencia("19000.00")],
            None,
            es_consumidor_final=False,
        )

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


def test_con_conexion_la_referencia_faltante_rechaza_indicando_el_medio() -> None:
    """Spec "Medio que exige referencia sin referencia": la rechaza tal cual el pago."""
    for referencia in (None, "", "   "):
        with pytest.raises(ReferenciaObligatoriaError) as error:
            validar_cobranza(
                Decimal("50000.00"),
                [efectivo("30000.00"), transferencia("20000.00", referencia=referencia)],
                None,
                es_consumidor_final=False,
            )

        assert error.value.extension == {"medio": 1}


def test_el_mismo_medio_puede_repetirse() -> None:
    validar_cobranza(
        Decimal("50000.00"),
        [efectivo("25000.00"), efectivo("25000.00")],
        None,
        es_consumidor_final=False,
    )


def test_el_consumidor_final_no_tiene_cobranza_independiente() -> None:
    """Spec "Consumidor final" (CLI-03, CC-08, D4): 422 `CONSUMIDOR_FINAL_SIN_CUENTA`."""
    with pytest.raises(ConsumidorFinalSinCuentaError) as error:
        validar_cobranza(
            Decimal("20000.00"), [efectivo("20000.00")], None, es_consumidor_final=True
        )

    assert error.value.codigo == "CONSUMIDOR_FINAL_SIN_CUENTA"
    assert error.value.status_http == 422


def test_un_contenido_malformado_se_rechaza_antes_que_el_consumidor_final() -> None:
    with pytest.raises(MediosNoSumanImporteError):
        validar_cobranza(Decimal("20000.00"), [efectivo("1.00")], None, es_consumidor_final=True)


# --- 6.1: sin conexión (OFFLINE, D13-C) ------------------------------------------------


def test_offline_con_todo_en_orden_no_observa_nada() -> None:
    """Spec "Medio activo con su referencia, sin observación"."""
    resultado = evaluar_cobranza_offline(
        Decimal("50000.00"),
        [efectivo("30000.00"), transferencia("20000.00")],
        "  nota ",
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert resultado.observacion == "nota"
    assert resultado.observaciones == ()


def test_offline_un_medio_desactivado_se_acepta_con_medio_inactivo_y_su_detalle() -> None:
    """Spec "INV-17 — medio desactivado después de abrir la jornada" (SYN-05, SYN-07)."""
    resultado = evaluar_cobranza_offline(
        Decimal("10000.00"),
        [billetera("10000.00")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert [(o.codigo, o.detalle) for o in resultado.observaciones] == [
        (
            CODIGO_MEDIO_INACTIVO,
            {
                "medio": 0,
                "medio_pago_id": str(BILLETERA_ID),
                "nombre": "Billetera",
                "importe": "10000.00",
            },
        )
    ]


def test_offline_el_medio_inactivo_en_una_de_varias_lineas_observa_solo_esa_linea() -> None:
    """Spec "Medio inactivo en una de varias líneas"."""
    resultado = evaluar_cobranza_offline(
        Decimal("30000.00"),
        [efectivo("20000.00"), billetera("10000.00")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert [(o.codigo, o.detalle["medio"]) for o in resultado.observaciones] == [
        (CODIGO_MEDIO_INACTIVO, 1)
    ]


def test_offline_dos_lineas_con_el_mismo_medio_inactivo_dan_dos_observaciones() -> None:
    resultado = evaluar_cobranza_offline(
        Decimal("30000.00"),
        [billetera("10000.00"), efectivo("5000.00"), billetera("15000.00")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert [
        (o.codigo, o.detalle["medio"], o.detalle["importe"]) for o in resultado.observaciones
    ] == [
        (CODIGO_MEDIO_INACTIVO, 0, "10000.00"),
        (CODIGO_MEDIO_INACTIVO, 2, "15000.00"),
    ]


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_offline_la_referencia_faltante_se_acepta_con_su_observacion(
    referencia: str | None,
) -> None:
    """Spec "INV-17 — referencia faltante": nula o de solo espacios (SYN-05, SYN-07)."""
    resultado = evaluar_cobranza_offline(
        Decimal("20000.00"),
        [transferencia("20000.00", referencia=referencia)],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert [(o.codigo, o.detalle) for o in resultado.observaciones] == [
        (
            CODIGO_REFERENCIA_FALTANTE,
            {
                "medio": 0,
                "medio_pago_id": str(TRANSFERENCIA_ID),
                "nombre": "Transferencia",
                "importe": "20000.00",
            },
        )
    ]


def test_offline_una_linea_con_medio_inactivo_y_sin_referencia_da_las_dos_observaciones() -> None:
    """Spec "Medio inactivo y sin referencia en la misma línea"."""
    resultado = evaluar_cobranza_offline(
        Decimal("20000.00"),
        [transferencia("20000.00", referencia=None, activo=False)],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert [(o.codigo, o.detalle["medio"]) for o in resultado.observaciones] == [
        (CODIGO_MEDIO_INACTIVO, 0),
        (CODIGO_REFERENCIA_FALTANTE, 0),
    ]


def test_offline_el_consumidor_final_se_acepta_con_cliente_no_habilitado() -> None:
    """Spec "INV-17 — consumidor final"."""
    resultado = evaluar_cobranza_offline(
        Decimal("20000.00"),
        [efectivo("20000.00")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=True,
    )

    assert [(o.codigo, o.detalle) for o in resultado.observaciones] == [
        (CODIGO_CLIENTE_NO_HABILITADO, {"cliente_id": str(CLIENTE_ID)})
    ]


def test_offline_las_observaciones_conviven() -> None:
    resultado = evaluar_cobranza_offline(
        Decimal("30000.00"),
        [billetera("10000.00"), transferencia("20000.00", referencia=None)],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=True,
    )

    assert sorted(o.codigo for o in resultado.observaciones) == sorted(
        [CODIGO_MEDIO_INACTIVO, CODIGO_REFERENCIA_FALTANTE, CODIGO_CLIENTE_NO_HABILITADO]
    )


def test_offline_la_referencia_faltante_guarda_la_linea_sin_referencia() -> None:
    """La referencia de solo espacios se guarda nula (D13 punto 2)."""
    resultado = evaluar_cobranza_offline(
        Decimal("20000.00"),
        [transferencia("20000.00", referencia="   ")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )

    assert resultado.referencias == (None,)
    ok = evaluar_cobranza_offline(
        Decimal("20000.00"),
        [transferencia("20000.00", referencia=" 0042 ")],
        None,
        cliente_id=CLIENTE_ID,
        es_consumidor_final=False,
    )
    assert ok.referencias == ("0042",)


@pytest.mark.parametrize(
    ("importe", "medios", "error"),
    [
        ("50000.00", [efectivo("49000.00")], MediosNoSumanImporteError),
        ("0.00", [efectivo("10.00")], ImporteInvalidoError),
        ("50000.001", [efectivo("50000.001")], ImporteInvalidoError),
        ("21.00", [efectivo("1.00")] * 21, MediosInvalidosError),
        ("10.00", [], MediosInvalidosError),
    ],
)
def test_offline_solo_lo_malformado_rechaza(
    importe: str, medios: list[MedioResuelto], error: type[DomainError]
) -> None:
    """Spec "INV-08 también sin conexión" (SYN-06): esto SIEMPRE se rechaza."""
    with pytest.raises(error):
        evaluar_cobranza_offline(
            Decimal(importe), medios, None, cliente_id=CLIENTE_ID, es_consumidor_final=False
        )


def test_offline_la_observacion_demasiado_larga_se_rechaza() -> None:
    with pytest.raises(ObservacionInvalidaError):
        evaluar_cobranza_offline(
            Decimal("10.00"),
            [efectivo("10.00")],
            "x" * (MAXIMO_OBSERVACION + 1),
            cliente_id=CLIENTE_ID,
            es_consumidor_final=False,
        )


def test_offline_un_cliente_cualquiera_no_agrega_observaciones_por_su_estado() -> None:
    """D4: el estado del cliente no se evalúa en el dominio (cliente inactivo: sin marca)."""
    resultado = evaluar_cobranza_offline(
        Decimal("12000.00"),
        [efectivo("12000.00")],
        None,
        cliente_id=uuid4(),
        es_consumidor_final=False,
    )

    assert resultado.observaciones == ()


# --- 6.2: reglas de la anulación (D7) --------------------------------------------------


def test_se_anula_una_cobranza_confirmada_independiente() -> None:
    validar_cobranza_a_anular(ESTADO_CONFIRMADA, ORIGEN_INDEPENDIENTE)


def test_una_cobranza_anulada_no_se_anula_dos_veces() -> None:
    """Spec "COBRANZA_YA_ANULADA" (COB-05, 409)."""
    with pytest.raises(CobranzaYaAnuladaError) as error:
        validar_cobranza_a_anular(ESTADO_ANULADA, ORIGEN_INDEPENDIENTE)

    assert error.value.codigo == "COBRANZA_YA_ANULADA"
    assert error.value.status_http == 409


def test_una_cobranza_de_venta_no_se_anula_por_separado() -> None:
    """D7 (VTA-22): se anula con la venta."""
    with pytest.raises(CobranzaDeVentaError) as error:
        validar_cobranza_a_anular(ESTADO_CONFIRMADA, ORIGEN_VENTA)

    assert error.value.codigo == "COBRANZA_DE_VENTA"
    assert error.value.status_http == 409


def test_la_cobranza_ya_anulada_se_informa_antes_que_su_origen() -> None:
    """Quien reintenta una anulación ya aplicada ve `COBRANZA_YA_ANULADA`."""
    with pytest.raises(CobranzaYaAnuladaError):
        validar_cobranza_a_anular(ESTADO_ANULADA, ORIGEN_VENTA)


def test_la_observacion_de_la_anulacion_se_recorta_y_admite_hasta_500() -> None:
    assert validar_observacion("  cheque rechazado n.º 0042 ") == "cheque rechazado n.º 0042"
    assert validar_observacion(None) is None
    assert validar_observacion("   ") is None
    with pytest.raises(ObservacionInvalidaError):
        validar_observacion("x" * 501)
