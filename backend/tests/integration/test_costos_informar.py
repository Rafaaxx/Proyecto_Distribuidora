"""Change 11b, tarea 4.3: `COSTO_INFORMAR` v1 según la condición frente al IVA de la
organización, por el bus y contra PostgreSQL real.

Reglas citadas: CST-02, CST-03, CST-06, TR-06, TR-10, INV-01 y `design.md` D1, D3, D4.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.huella import calcular_huella
from app.modules.proveedores import commands as proveedores_commands
from app.modules.proveedores.domain.errores import IncluyeIvaNoAplicaError
from app.modules.proveedores.models import CostoInformado
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

COSTO_INFORMAR = "COSTO_INFORMAR"


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _costo(
    entorno: Entorno, valor: str, *, incluye_iva: bool = False, **cambios: Any
) -> dict[str, Any]:
    costo: dict[str, Any] = {
        "producto_id": str(entorno.vino_id),
        "presentacion_id": str(entorno.caja_x6_id),
        "valor": valor,
        "incluye_iva": incluye_iva,
        "vigencia_desde": date(2026, 5, 1).isoformat(),
    }
    costo.update(cambios)
    return costo


def _informar(
    entorno: Entorno, *costos: dict[str, Any], operation_id: UUID | None = None
) -> Comando:
    sobre = entorno.sobre(
        {"proveedor_id": str(entorno.proveedor_id), "costos": list(costos)},
        operation_id=operation_id,
        tipo=COSTO_INFORMAR,
    )
    huella = calcular_huella(sobre.contenido)
    contenido = proveedores_commands.CostoInformarContenidoV1.model_validate(sobre.contenido)

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return proveedores_commands.manejar_costo_informar(
            sobre, contenido, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        entorno.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def _costos(entorno: Entorno) -> list[CostoInformado]:
    return list(
        entorno.sesion.scalars(
            select(CostoInformado)
            .where(CostoInformado.organizacion_id == entorno.org)
            .order_by(CostoInformado.valor)
        ).all()
    )


# --- monotributo y exento: el valor es el pagado (CST-06, D1, D3) ---------------------------


@pytest.mark.parametrize("condicion", ["MONOTRIBUTO", "EXENTO"])
def test_cst06_una_organizacion_no_inscripta_informa_el_valor_pagado(
    entorno: Entorno, condicion: str
) -> None:
    entorno.fijar_condicion_iva(condicion)

    comando = _informar(entorno, _costo(entorno, "7260.00"))

    (costo,) = _costos(entorno)
    assert costo.costo_base == Decimal("1210.000000"), "7260 / 6 sin dividir por 1,21"
    assert costo.incluye_iva is False
    assert costo.computa_credito_fiscal is False
    assert costo.alicuota_aplicada == Decimal("0.210000")
    assert comando.resultado is not None
    assert comando.resultado["costos_base"] == ["1210.000000"]


def test_cst06_con_bonificacion_el_monotributista_descuenta_solo_la_bonificacion(
    entorno: Entorno,
) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    _informar(entorno, _costo(entorno, "7260.00", bonificacion="0.10"))

    (costo,) = _costos(entorno)
    assert costo.costo_base == Decimal("1089.000000"), "7260 * 0,9 / 6"


def test_d4_incluye_iva_en_una_organizacion_no_inscripta_se_rechaza_sin_registrar_nada(
    entorno: Entorno,
) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")
    operation_id = uuid4()

    with pytest.raises(IncluyeIvaNoAplicaError) as error:
        _informar(
            entorno,
            _costo(entorno, "7260.00"),
            _costo(entorno, "7000.00", incluye_iva=True, vigencia_desde="2026-05-02"),
            operation_id=operation_id,
        )

    assert error.value.codigo == "INCLUYE_IVA_NO_APLICA"
    assert error.value.extension == {"fila": 1}
    assert _costos(entorno) == [], "todo o nada (INV-01)"
    reservas = entorno.sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )
    assert reservas == 0, "el rechazo revierte la reserva y se puede reintentar"


# --- responsable inscripto: sin cambios (CST-02, TR-06) ---------------------------------------


def test_un_inscripto_con_iva_incluido_sigue_descontando_el_iva(entorno: Entorno) -> None:
    _informar(entorno, _costo(entorno, "7260.00", incluye_iva=True))

    (costo,) = _costos(entorno)
    assert costo.costo_base == Decimal("1000.000000"), "7260 / 1,21 / 6"
    assert costo.incluye_iva is True
    assert costo.computa_credito_fiscal is True


def test_un_inscripto_sin_iva_incluido_conserva_el_valor(entorno: Entorno) -> None:
    _informar(entorno, _costo(entorno, "6000.00"))

    (costo,) = _costos(entorno)
    assert costo.costo_base == Decimal("1000.000000")
    assert costo.computa_credito_fiscal is True


def test_tr06_cambiar_la_condicion_no_toca_los_costos_registrados(entorno: Entorno) -> None:
    """Un costo de inscripto con IVA incluido sigue igual cuando la organización pasa a
    monotributo, y el costo nuevo se registra con la otra regla."""
    _informar(entorno, _costo(entorno, "7260.00", incluye_iva=True))
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    _informar(entorno, _costo(entorno, "7260.00", vigencia_desde="2026-05-02"))

    anterior, nuevo = sorted(_costos(entorno), key=lambda costo: costo.vigencia_desde)
    assert (anterior.costo_base, anterior.incluye_iva, anterior.computa_credito_fiscal) == (
        Decimal("1000.000000"),
        True,
        True,
    )
    assert (nuevo.costo_base, nuevo.incluye_iva, nuevo.computa_credito_fiscal) == (
        Decimal("1210.000000"),
        False,
        False,
    )


# --- lectura de la condición con bloqueo (D3) -----------------------------------------------


def test_informar_costos_lee_la_condicion_con_bloqueo_compartido(entorno: Entorno) -> None:
    """Un cambio de condición concurrente (`FOR UPDATE`) espera a este registro."""
    assert entorno.toma_lock_de_configuracion() is False

    _informar(entorno, _costo(entorno, "6000.00"))

    assert entorno.toma_lock_de_configuracion() is True


def test_el_costo_registra_el_momento_del_reloj_inyectado(entorno: Entorno) -> None:
    _informar(entorno, _costo(entorno, "6000.00"))

    (costo,) = _costos(entorno)
    assert costo.creado_en == MOMENTO
