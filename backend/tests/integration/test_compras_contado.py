"""Change 11, tarea 8.1: `COMPRA_CONFIRMAR` de contado por el bus, contra PostgreSQL real.

Reglas citadas: CMP-01, CMP-03, CC-05, PAG-01, INV-01, INV-08, INV-21, AUD-01 y
`design.md` D2, D14.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from compras_utiles import MOMENTO, Entorno
from sqlalchemy.orm import Session

from app.core.errors import DomainError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _movimientos_de_cuenta(entorno: Entorno) -> set[tuple[str, str, Decimal]]:
    return {(m.tipo, m.sentido, m.importe) for m in entorno.movimientos_de_cuenta()}


def test_contado_con_efectivo_y_transferencia_registra_compra_y_pago_cc_05(
    entorno: Entorno,
) -> None:
    """CC-05, PAG-01, INV-08: la cuenta recibe `COMPRA` y `PAGO` por separado y el
    saldo no cambia."""
    comando = entorno.confirmar_contado(
        (entorno.efectivo_id, "100000.00", None),
        (entorno.transferencia_id, "52460.00", "0042"),
    )

    (compra,) = entorno.compras()
    assert compra.condicion == "CONTADO"
    (pago,) = entorno.pagos()
    assert pago.origen == "COMPRA"
    assert pago.compra_id == compra.id
    assert pago.proveedor_id == entorno.proveedor_id
    assert pago.importe == Decimal("152460.00")
    assert pago.estado == "CONFIRMADA"
    assert pago.fecha == date(2026, 5, 10)
    assert pago.operation_id == comando.operation_id
    assert pago.usuario_id == entorno.usuario_id
    assert pago.dispositivo_id == entorno.dispositivo_id
    assert pago.occurred_at == MOMENTO
    medios = entorno.medios_de_pago()
    assert [(m.medio_pago_id, m.importe, m.referencia) for m in medios] == [
        (entorno.efectivo_id, Decimal("100000.00"), None),
        (entorno.transferencia_id, Decimal("52460.00"), "0042"),
    ]
    assert all(m.pago_id == pago.id for m in medios)
    assert _movimientos_de_cuenta(entorno) == {
        ("COMPRA", "AUMENTA", Decimal("152460.00")),
        ("PAGO", "REDUCE", Decimal("152460.00")),
    }
    pago_en_cuenta = next(m for m in entorno.movimientos_de_cuenta() if m.tipo == "PAGO")
    assert (pago_en_cuenta.origen_tipo, pago_en_cuenta.origen_id) == ("PAGO", pago.id)
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert entorno.saldo(entorno.vino_id) == 60
    assert comando.resultado is not None
    assert comando.resultado["pago_id"] == str(pago.id)


def test_contado_con_un_solo_medio(entorno: Entorno) -> None:
    entorno.confirmar_contado((entorno.efectivo_id, "152460.00", None))

    (medio,) = entorno.medios_de_pago()
    assert medio.importe == Decimal("152460.00")
    assert entorno.saldo_de_cuenta() == Decimal("0.00")


def test_el_pago_usa_el_total_de_factura_informado_y_no_el_sugerido(entorno: Entorno) -> None:
    """D1, D2: la deuda y el pago son `total_factura`."""
    entorno.confirmar_contado((entorno.efectivo_id, "153720.00", None), total_factura="153720.00")

    (pago,) = entorno.pagos()
    assert pago.importe == Decimal("153720.00")
    assert _movimientos_de_cuenta(entorno) == {
        ("COMPRA", "AUMENTA", Decimal("153720.00")),
        ("PAGO", "REDUCE", Decimal("153720.00")),
    }


def test_el_contado_no_cambia_un_saldo_previo(entorno: Entorno) -> None:
    """CC-05: el saldo previo del proveedor queda igual."""
    entorno.enviar(entorno.contenido(total_factura="1000.00", lineas=[entorno.linea("cerveza")]))
    assert entorno.saldo_de_cuenta() == Decimal("1000.00")

    entorno.confirmar_contado((entorno.efectivo_id, "152460.00", None))

    assert entorno.saldo_de_cuenta() == Decimal("1000.00")


def test_contado_queda_con_una_sola_auditoria(entorno: Entorno) -> None:
    comando = entorno.confirmar_contado((entorno.efectivo_id, "152460.00", None))

    assert entorno.auditorias(comando.operation_id) == 1


# --- INV-08: los medios suman el importe ----------------------------------------


def test_medios_que_no_suman_el_total_se_rechazan_sin_efectos_inv_08(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado(
            (entorno.efectivo_id, "100000.00", None),
            (entorno.transferencia_id, "50000.00", "0042"),
        )

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"
    entorno.sin_efectos()


def test_medios_que_suman_de_mas_se_rechazan_sin_efectos_inv_08(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado((entorno.efectivo_id, "152460.01", None))

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"
    entorno.sin_efectos()


def test_contado_sin_medios_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(condicion="CONTADO"))

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"
    entorno.sin_efectos()


@pytest.mark.parametrize("importe", ["0.00", "-10.00", "10.005"])
def test_un_medio_con_importe_invalido_se_rechaza_sin_efectos(
    entorno: Entorno, importe: str
) -> None:
    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado(
            (entorno.efectivo_id, "152460.00", None), (entorno.efectivo_id, importe, None)
        )

    assert error.value.codigo == "IMPORTE_INVALIDO"
    entorno.sin_efectos()


# --- medios de pago: estado y pertenencia ------------------------------------


def test_un_medio_inactivo_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    inactivo = entorno.crear_medio("Cheque", requiere_referencia=False, activo=False)

    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado((inactivo, "152460.00", None))

    assert error.value.codigo == "MEDIO_PAGO_INACTIVO"
    assert error.value.status_http == 422
    entorno.sin_efectos()


def test_un_medio_de_otra_organizacion_responde_404_inv_21(
    entorno: Entorno, db_session: Session
) -> None:
    otra = Entorno(db_session)
    ajeno = otra.crear_medio("Efectivo ajeno", requiere_referencia=False)

    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado((ajeno, "152460.00", None))

    assert error.value.codigo == "RECURSO_NO_ENCONTRADO"
    assert error.value.status_http == 404
    entorno.sin_efectos()


def test_un_medio_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado((uuid4(), "152460.00", None))

    assert error.value.status_http == 404
    entorno.sin_efectos()


# --- referencia obligatoria ----------------------------------------------------


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_un_medio_que_exige_referencia_sin_ella_se_rechaza_sin_efectos(
    entorno: Entorno, referencia: str | None
) -> None:
    with pytest.raises(DomainError) as error:
        entorno.confirmar_contado(
            (entorno.efectivo_id, "100000.00", None),
            (entorno.transferencia_id, "52460.00", referencia),
        )

    assert error.value.codigo == "REFERENCIA_OBLIGATORIA"
    entorno.sin_efectos()


def test_un_medio_sin_referencia_obligatoria_la_acepta_y_la_guarda(entorno: Entorno) -> None:
    entorno.confirmar_contado((entorno.efectivo_id, "152460.00", "recibo 7"))

    (medio,) = entorno.medios_de_pago()
    assert medio.referencia == "recibo 7"


# --- crédito: sin medios --------------------------------------------------------


def test_credito_con_medios_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(
            entorno.contenido(medios=entorno.pagar((entorno.efectivo_id, "152460.00", None)))
        )

    assert error.value.codigo == "CONDICION_INVALIDA"
    entorno.sin_efectos()


def test_credito_no_crea_pago(entorno: Entorno) -> None:
    entorno.enviar()

    assert entorno.pagos() == []
    assert entorno.medios_de_pago() == []


# --- INV-01: atomicidad ---------------------------------------------------------


def test_una_falla_despues_del_stock_no_deja_pago_ni_compra_inv_01(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: si falla el registro del pago, nada de la compra queda escrito."""
    from app.modules.proveedores import repository

    def _falla(*args: object, **kwargs: object) -> None:
        raise RuntimeError("falla inyectada en el pago")

    monkeypatch.setattr(repository, "insertar_pago_de_compra", _falla)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.confirmar_contado((entorno.efectivo_id, "152460.00", None))

    entorno.sin_efectos()
