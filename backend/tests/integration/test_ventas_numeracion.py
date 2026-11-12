"""Tarea 7.7 (change 18a; spec `ventas/confirmacion-de-venta`, requisito de número; `design.md`
D4): el número lo propone el dispositivo y el servidor lo valida; el último correlativo pasa a
`max(actual, propuesto)` y nunca retrocede. Contra PostgreSQL real.

Reglas citadas: VTA-06, INV-17, INV-21.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.core.errors import DomainError
from app.modules.ventas import repository as ventas_repository
from app.modules.ventas.domain.errores import NumeroDuplicadoError, NumeroInvalidoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def _numero(entorno: EntornoVenta, correlativo: int, prefijo: str | None = None) -> str:
    return f"{prefijo or entorno.prefijo}-{correlativo:06d}"


def _sin_rastros(entorno: EntornoVenta, correlativo: int) -> None:
    """Un rechazo no deja venta, movimiento de stock ni avance del correlativo."""
    assert entorno.ventas() == []
    assert entorno.movimientos_de_stock() == []
    assert entorno.ultimo_correlativo() == correlativo


def test_vta06_un_numero_del_dispositivo_se_acepta_y_el_correlativo_pasa_a_42(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Número aceptado": el dispositivo con último correlativo 41 envía `PPP-000042`."""
    entorno.sesion.execute(
        text(
            "UPDATE dispositivo SET ultimo_correlativo = 41 WHERE organizacion_id = :o AND id = :d"
        ),
        {"o": entorno.org, "d": entorno.dispositivo_id},
    )

    entorno.vender(numero=_numero(entorno, 42))

    (venta,) = entorno.ventas()
    assert venta.numero == _numero(entorno, 42)
    assert entorno.ultimo_correlativo() == 42


def test_vta06_un_numero_ya_usado_es_numero_duplicado_y_no_deja_rastros(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Número duplicado" (409): el mismo número en otra venta de la organización."""
    entorno.vender(numero=_numero(entorno, 1))
    (primera,) = entorno.ventas()
    entorno.sesion.commit()

    with pytest.raises(NumeroDuplicadoError) as error:
        entorno.vender(numero=_numero(entorno, 1))

    assert (error.value.codigo, error.value.status_http) == ("NUMERO_DUPLICADO", 409)
    assert [venta.id for venta in entorno.ventas()] == [primera.id]
    assert len(entorno.movimientos_de_stock()) == 1
    assert entorno.ultimo_correlativo() == 1


def test_vta06_la_carrera_por_el_mismo_numero_tambien_es_numero_duplicado(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si la lectura previa no ve el número (otra transacción lo confirma entre la lectura y
    el insert), la restricción única `ux_venta__numero` se traduce al mismo código, no a un 500."""
    entorno.vender(numero=_numero(entorno, 1))
    entorno.sesion.commit()
    monkeypatch.setattr(ventas_repository, "existe_numero", lambda *_args, **_kw: False)

    with pytest.raises(NumeroDuplicadoError):
        entorno.vender(numero=_numero(entorno, 1))

    assert len(entorno.ventas()) == 1
    assert entorno.ultimo_correlativo() == 1


@pytest.mark.parametrize(
    "numero",
    ["ZZZ-000001", "000001", "", "{p}-1", "{p}-00000A", "{p}-000000", "{p}000001"],
)
def test_vta06_un_numero_con_prefijo_ajeno_o_formato_malo_es_numero_invalido(
    entorno: EntornoVenta, numero: str
) -> None:
    """Escenario "Prefijo ajeno" (422) y las variantes de formato: se rechaza con todo revertido."""
    with pytest.raises(NumeroInvalidoError) as error:
        entorno.vender(numero=numero.format(p=entorno.prefijo))

    assert (error.value.codigo, error.value.status_http) == ("NUMERO_INVALIDO", 422)
    _sin_rastros(entorno, 0)


def test_inv17_un_numero_menor_no_hace_retroceder_el_correlativo(entorno: EntornoVenta) -> None:
    # Escenario: "Un número menor no retrocede el correlativo"
    """Escenario "Número menor": se acepta (una venta vieja que llega tarde) y `ultimo_correlativo`
    sigue en el máximo."""
    entorno.vender(numero=_numero(entorno, 50))
    entorno.vender(numero=_numero(entorno, 7))

    assert [venta.numero for venta in entorno.ventas()] == [
        _numero(entorno, 50),
        _numero(entorno, 7),
    ]
    assert entorno.ultimo_correlativo() == 50


def test_vta06_el_rechazo_por_numero_no_toca_el_saldo_ni_el_stock(entorno: EntornoVenta) -> None:
    """Triangula: el número inválido es un `DomainError` (el bus lo traduce a Problem Details) y
    el saldo del cliente, el stock y el correlativo quedan como estaban."""
    with pytest.raises(DomainError):
        entorno.vender(numero="ZZZ-000001")

    entorno.sin_efectos_de_venta()
    assert entorno.ultimo_correlativo() == 0
