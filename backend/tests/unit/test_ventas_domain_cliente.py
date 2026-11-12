"""Tarea 5.2 (change 18a; spec `ventas/confirmacion-de-venta`, requisito "El cliente debe estar
habilitado"; `design.md` D5): cliente habilitado y consumidor final de contado.

Reglas citadas: CLI-02, CLI-03, SYN-05, SYN-07, INV-17.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.ventas.domain.cliente import (
    CODIGO_CLIENTE_NO_HABILITADO,
    CODIGO_CONSUMIDOR_FINAL_CON_DEUDA,
    evaluar_cliente,
)
from app.modules.ventas.domain.errores import (
    ClienteInactivoError,
    ClienteSuspendidoError,
    ConsumidorFinalContadoError,
)
from app.modules.ventas.domain.observaciones import ObservacionDeVenta

CLIENTE_ID = uuid4()
TOTAL = Decimal("4300.00")


def _evaluar(estado: str = "ACTIVO", **cambios: object) -> ObservacionDeVenta | None:
    valores: dict[str, object] = {
        "cliente_id": CLIENTE_ID,
        "estado": estado,
        "es_consumidor_final": False,
        "puede_vender_suspendido": False,
        "total": TOTAL,
        "cobranza": None,
        "offline": False,
    }
    valores.update(cambios)
    return evaluar_cliente(**valores)  # type: ignore[arg-type]


# --- con conexión ----------------------------------------------------------------


def test_cli02_un_cliente_activo_se_vende_sin_observacion() -> None:
    assert _evaluar("ACTIVO") is None


def test_cli02_un_suspendido_sin_el_permiso_se_rechaza() -> None:
    with pytest.raises(ClienteSuspendidoError) as error:
        _evaluar("SUSPENDIDO")
    assert error.value.codigo == "CLIENTE_SUSPENDIDO"
    assert error.value.status_http == 409


def test_cli02_un_suspendido_con_el_permiso_se_vende() -> None:
    assert _evaluar("SUSPENDIDO", puede_vender_suspendido=True) is None


@pytest.mark.parametrize("puede_vender_suspendido", [False, True])
def test_cli02_un_inactivo_no_se_vende_ni_con_el_permiso(puede_vender_suspendido: bool) -> None:
    with pytest.raises(ClienteInactivoError) as error:
        _evaluar("INACTIVO", puede_vender_suspendido=puede_vender_suspendido)
    assert error.value.codigo == "CLIENTE_INACTIVO"
    assert error.value.status_http == 409


def test_cli03_el_consumidor_final_se_vende_solo_de_contado() -> None:
    assert _evaluar(es_consumidor_final=True, cobranza=Decimal("4300.00")) is None


@pytest.mark.parametrize(
    "cobranza", [None, Decimal("4000.00"), Decimal("4300.01"), Decimal("0.00")]
)
def test_cli03_el_consumidor_final_con_otra_cobranza_se_rechaza(cobranza: Decimal | None) -> None:
    """D5-A: la cobranza en el acto debe ser igual al total (ni menos ni más)."""
    with pytest.raises(ConsumidorFinalContadoError) as error:
        _evaluar(es_consumidor_final=True, cobranza=cobranza)
    assert error.value.codigo == "CONSUMIDOR_FINAL_CONTADO"
    assert error.value.status_http == 422


def test_el_estado_del_cliente_se_evalua_antes_que_el_contado() -> None:
    with pytest.raises(ClienteInactivoError):
        _evaluar("INACTIVO", es_consumidor_final=True, cobranza=None)


# --- sin conexión (SYN-05, INV-17) ---------------------------------------------------


@pytest.mark.parametrize("estado", ["INACTIVO", "SUSPENDIDO"])
def test_syn05_sin_conexion_un_cliente_no_habilitado_se_acepta_con_observacion(
    estado: str,
) -> None:
    observacion = _evaluar(estado, offline=True)

    assert observacion is not None
    assert observacion.codigo == CODIGO_CLIENTE_NO_HABILITADO == "CLIENTE_NO_HABILITADO"
    assert observacion.detalle == {"cliente_id": str(CLIENTE_ID), "estado": estado}


def test_syn05_sin_conexion_un_suspendido_con_el_permiso_no_se_observa() -> None:
    assert _evaluar("SUSPENDIDO", offline=True, puede_vender_suspendido=True) is None


def test_syn05_sin_conexion_un_activo_no_se_observa() -> None:
    assert _evaluar("ACTIVO", offline=True) is None


@pytest.mark.parametrize(
    "cobranza", [None, Decimal("0.00"), Decimal("4000.00"), Decimal("4300.01")]
)
def test_syn05_sin_conexion_el_consumidor_final_a_credito_se_acepta_con_su_observacion(
    cobranza: Decimal | None,
) -> None:
    """D5 (decisión del usuario, 2026-10-19): el consumidor final con cobranza distinta del
    total se acepta con `CONSUMIDOR_FINAL_CON_DEUDA` (no con `CLIENTE_NO_HABILITADO`)."""
    observacion = _evaluar(es_consumidor_final=True, cobranza=cobranza, offline=True)

    assert observacion is not None
    assert observacion.codigo == CODIGO_CONSUMIDOR_FINAL_CON_DEUDA == "CONSUMIDOR_FINAL_CON_DEUDA"
    assert observacion.detalle == {
        "cliente_id": str(CLIENTE_ID),
        "total": "4300.00",
        "cobranza": None if cobranza is None else str(cobranza),
    }


def test_syn05_sin_conexion_el_consumidor_final_inactivo_conserva_cliente_no_habilitado() -> None:
    """El estado manda: un cliente no habilitado sigue observándose como tal (D5)."""
    observacion = _evaluar("INACTIVO", es_consumidor_final=True, cobranza=None, offline=True)

    assert observacion is not None
    assert observacion.codigo == "CLIENTE_NO_HABILITADO"


def test_syn05_sin_conexion_el_consumidor_final_de_contado_no_se_observa() -> None:
    assert _evaluar(es_consumidor_final=True, cobranza=TOTAL, offline=True) is None
