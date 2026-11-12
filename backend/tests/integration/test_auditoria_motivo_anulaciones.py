"""Tarea 3.3 (change 28, spec `auditoria/registro-de-auditoria`; `design.md` D1): la fila de
auditoría de `COMPRA_ANULAR` y de `PAGO_PROVEEDOR_ANULAR` aceptados guarda el motivo elegido en
la anulación, igual que los comandos de stock y de cobranzas; un comando rechazado no lo deja.

Por el bus (`sync_service.procesar_comando`) contra PostgreSQL real. Reglas citadas: AUD-01,
AUD-02, INV-01, INV-06, SYN-02, ADR-022, ADR-070 (deuda 2).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from compras_utiles import PERMISOS_DE_ANULACION_DE_PAGO, Entorno
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.modules.identidad.models import Auditoria

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset(PERMISOS_DE_ANULACION_DE_PAGO | {"REGISTRAR_COMPRA", "ANULAR_COMPRA"})
DEUDA = "152460.00"


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _filas(entorno: Entorno, operation_id: UUID) -> list[Auditoria]:
    return list(
        entorno.sesion.scalars(
            select(Auditoria).where(
                Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id
            )
        )
    )


def _motivos_de_la_organizacion_en_la_auditoria(entorno: Entorno) -> set[UUID | None]:
    return set(
        entorno.sesion.scalars(
            select(Auditoria.motivo_id).where(
                Auditoria.organizacion_id == entorno.org, Auditoria.accion == "COMPRA_ANULAR"
            )
        )
    )


def _compra_de_vino(entorno: Entorno) -> UUID:
    previas = {c.id for c in entorno.compras()}
    entorno.enviar(
        entorno.contenido(
            lineas=[entorno.linea("vino", cantidad="10", valor="6000.00")],
            total_factura="72600.00",
        )
    )
    (nueva,) = [c for c in entorno.compras() if c.id not in previas]
    return nueva.id


def _pago_independiente(entorno: Entorno) -> UUID:
    assert entorno.deuda(DEUDA) == Decimal(DEUDA)
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="52460.00", medios=entorno.pagar((entorno.efectivo_id, "52460.00", None))
        )
    )
    (pago,) = entorno.pagos()
    return pago.id


def test_la_anulacion_de_una_compra_aceptada_guarda_el_motivo_en_la_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario «Anulación de compra con motivo» (AUD-02)."""
    compra_id = _compra_de_vino(entorno)
    operation_id = uuid4()

    entorno.anular(compra_id, operation_id=operation_id)

    (fila,) = _filas(entorno, operation_id)
    assert (fila.accion, fila.motivo_id) == ("COMPRA_ANULAR", entorno.motivo_id)


def test_cada_compra_anulada_guarda_su_propio_motivo(entorno: Entorno) -> None:
    """Triangula con otro motivo del mismo ámbito: la fila copia el que se eligió, no uno fijo."""
    otro_motivo = entorno.crear_motivo("ANULACION_COMPRA", "Otro")
    primera, segunda = _compra_de_vino(entorno), _compra_de_vino(entorno)
    op_primera, op_segunda = uuid4(), uuid4()

    entorno.anular(primera, operation_id=op_primera)
    entorno.anular(segunda, operation_id=op_segunda, motivo_id=otro_motivo)

    assert [_filas(entorno, op)[0].motivo_id for op in (op_primera, op_segunda)] == [
        entorno.motivo_id,
        otro_motivo,
    ]


def test_la_anulacion_de_un_pago_aceptada_guarda_el_motivo_en_la_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario «Anulación de pago con motivo» (AUD-02)."""
    pago_id = _pago_independiente(entorno)
    operation_id = uuid4()

    entorno.anular_pago(pago_id, operation_id=operation_id)

    (fila,) = _filas(entorno, operation_id)
    assert (fila.accion, fila.motivo_id) == ("PAGO_PROVEEDOR_ANULAR", entorno.motivo_pago_id)


def test_una_anulacion_de_compra_rechazada_no_deja_el_motivo_del_intento(
    entorno: Entorno,
) -> None:
    """Escenario «Una anulación rechazada no deja motivo» (AUD-02, INV-01): la compra ya anulada
    rechaza el segundo intento con OTRO motivo; ninguna fila de auditoría lo lleva."""
    otro_motivo = entorno.crear_motivo("ANULACION_COMPRA", "Otro")
    compra_id = _compra_de_vino(entorno)
    entorno.anular(compra_id)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id, motivo_id=otro_motivo)
    entorno.sesion.rollback()

    assert error.value.codigo == "COMPRA_YA_ANULADA"
    assert otro_motivo not in _motivos_de_la_organizacion_en_la_auditoria(entorno)
    assert entorno.motivo_id in _motivos_de_la_organizacion_en_la_auditoria(entorno)


def test_una_anulacion_de_pago_rechazada_no_deja_el_motivo_del_intento(entorno: Entorno) -> None:
    otro_motivo = entorno.crear_motivo("ANULACION_PAGO", "Otro")
    pago_id = _pago_independiente(entorno)
    entorno.anular_pago(pago_id)

    with pytest.raises(DomainError) as error:
        entorno.anular_pago(pago_id, motivo_id=otro_motivo)
    entorno.sesion.rollback()

    assert error.value.codigo == "PAGO_YA_ANULADO"
    motivos = set(
        entorno.sesion.scalars(
            select(Auditoria.motivo_id).where(
                Auditoria.organizacion_id == entorno.org,
                Auditoria.accion == "PAGO_PROVEEDOR_ANULAR",
            )
        )
    )
    assert motivos == {entorno.motivo_pago_id}


def test_inv06_el_doble_envio_deja_un_solo_registro_con_el_motivo(entorno: Entorno) -> None:
    """Escenario «Doble envío de la anulación» (INV-06): se devuelve el resultado original y hay
    un solo registro de auditoría, con el motivo."""
    pago_id = _pago_independiente(entorno)
    operation_id = uuid4()

    primero = entorno.anular_pago(pago_id, operation_id=operation_id)
    segundo = entorno.anular_pago(pago_id, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    (fila,) = _filas(entorno, operation_id)
    assert fila.motivo_id == entorno.motivo_pago_id
