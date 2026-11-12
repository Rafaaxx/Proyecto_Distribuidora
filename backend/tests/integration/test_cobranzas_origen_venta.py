"""Tarea 6.3 (change 18a; spec `cobranzas/registro-de-cobranzas`; `design.md` D12):
`registrar_cobranza` acepta `origen="VENTA"` y `venta_id` (la cobranza de una venta); por defecto
sigue siendo `INDEPENDIENTE`; el comando `COBRANZA_REGISTRAR` no admite venta.

Reglas citadas: COB-01, VTA-11, CC-05, INV-02, ADR-052.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ventas_utiles import sembrar_venta_sql

from app.commands.errores import ContenidoDeComandoInvalidoError
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.service import MedioACobrar

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _sembrar_venta(entorno: Entorno) -> UUID:
    venta = sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=entorno.cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    return venta.venta_id


def _registrar(
    entorno: Entorno, *, importe: str = "20000.00", **opciones: object
) -> cobranzas_service.ResultadoDeCobranza:
    return cobranzas_service.registrar_cobranza(
        entorno.org,
        entorno.sesion,
        RELOJ,
        cobranza_id=uuid4(),
        cliente_id=entorno.cliente_id,
        importe=Decimal(importe),
        medios=[MedioACobrar(entorno.efectivo_id, Decimal(importe), None)],
        observacion=None,
        jornada_del_sobre=None,
        operation_id=uuid4(),
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        **opciones,  # type: ignore[arg-type]
    )


# --- la cobranza de una venta (VTA-11, CC-05) -----------------------------------------------


def test_vta11_la_cobranza_de_una_venta_se_registra_con_su_origen_y_su_venta(
    entorno: Entorno,
) -> None:
    """Escenario "Cobranza con la venta": origen `VENTA`, la venta referenciada, `CONFIRMADA`,
    y el crédito `COBRANZA` en la cuenta del cliente (saldo 150.000 -> 130.000)."""
    venta_id = _sembrar_venta(entorno)

    resultado = _registrar(entorno, origen="VENTA", venta_id=venta_id)

    assert resultado.cobranza.origen == "VENTA"
    assert resultado.cobranza.venta_id == venta_id
    assert resultado.cobranza.estado == "CONFIRMADA"
    assert resultado.cobranza.importe == Decimal("20000.00")
    assert resultado.saldo == Decimal("130000.00")
    (movimiento,) = entorno.movimientos("COBRANZA")
    assert (movimiento.sentido, movimiento.importe) == ("REDUCE", Decimal("20000.00"))
    assert movimiento.origen_id == resultado.cobranza.id


def test_vta11_otra_cobranza_de_otra_venta_conserva_su_propia_venta(entorno: Entorno) -> None:
    """Triangula: dos ventas, cada cobranza apunta a la suya."""
    primera, segunda = _sembrar_venta(entorno), _sembrar_venta(entorno)

    una = _registrar(entorno, importe="5000.00", origen="VENTA", venta_id=primera)
    otra = _registrar(entorno, importe="7000.00", origen="VENTA", venta_id=segunda)

    assert (una.cobranza.venta_id, otra.cobranza.venta_id) == (primera, segunda)
    assert otra.saldo == Decimal("138000.00")


def test_cob01_por_defecto_la_cobranza_sigue_siendo_independiente(entorno: Entorno) -> None:
    """Sin `origen` ni `venta_id` nada cambia respecto del change 17."""
    resultado = _registrar(entorno)

    assert resultado.cobranza.origen == "INDEPENDIENTE"
    assert resultado.cobranza.venta_id is None


@pytest.mark.parametrize(
    "opciones",
    [
        {"origen": "VENTA", "venta_id": None},
        {"origen": "INDEPENDIENTE", "venta_id": uuid4()},
        {"venta_id": uuid4()},
        {"origen": "OTRO", "venta_id": None},
    ],
)
def test_cob01_el_origen_debe_ser_coherente_con_la_venta(
    entorno: Entorno, opciones: dict[str, object]
) -> None:
    """`origen = VENTA` si y solo si hay `venta_id`: una combinación incoherente es un error
    de programación, rechazado antes de escribir nada."""
    with pytest.raises(ValueError, match="origen"):
        _registrar(entorno, **opciones)

    assert entorno.cobranzas() == []
    assert entorno.movimientos("COBRANZA") == []


def test_inv02_la_base_rechaza_una_venta_inexistente(entorno: Entorno) -> None:
    # Escenario: "La base exige que la venta exista"
    with pytest.raises(IntegrityError) as error:
        _registrar(entorno, origen="VENTA", venta_id=uuid4())

    assert "fk_cobranza__venta" in str(error.value)


def test_inv02_la_base_rechaza_la_venta_de_otra_organizacion(
    entorno: Entorno, db_session: Session
) -> None:
    # Escenario: "La base exige que la venta exista"
    ajeno = Entorno(db_session)
    venta_ajena = sembrar_venta_sql(
        db_session,
        ajeno.org,
        cliente_id=ajeno.cliente_id,
        usuario_id=ajeno.usuario_id,
        dispositivo_id=ajeno.dispositivo_id,
    ).venta_id

    with pytest.raises(IntegrityError) as error:
        _registrar(entorno, origen="VENTA", venta_id=venta_ajena)

    assert "fk_cobranza__venta" in str(error.value)


# --- por comando no hay cobranza de venta (ADR-052) ------------------------------------------


@pytest.mark.parametrize("campo", ["venta_id", "origen"])
def test_adr052_el_comando_no_admite_indicar_una_venta(entorno: Entorno, campo: str) -> None:
    """Escenario "Por comando no hay cobranza de venta": el campo no existe en el esquema."""
    valor = str(uuid4()) if campo == "venta_id" else "VENTA"

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.registrar(**{campo: valor})

    assert entorno.cobranzas() == []


# --- la cobranza de una venta al consumidor final (CLI-03, CC-08, change 18a D5) ----------------


def test_cli03_la_cobranza_de_una_venta_al_consumidor_final_se_admite(entorno: Entorno) -> None:
    """Una venta de contado al consumidor final cobra en el acto (`design.md` D5): a diferencia
    de la cobranza independiente (COB-01), la de origen `VENTA` lo admite y su cuenta queda en
    cero. Triangula con dos importes."""
    consumidor_id = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    for importe in ("4300.00", "1200.50"):
        venta = sembrar_venta_sql(
            entorno.sesion,
            entorno.org,
            cliente_id=consumidor_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
        )
        cobranzas_service.registrar_cobranza(
            entorno.org,
            entorno.sesion,
            RELOJ,
            cobranza_id=uuid4(),
            cliente_id=consumidor_id,
            importe=Decimal(importe),
            medios=[MedioACobrar(entorno.efectivo_id, Decimal(importe), None)],
            observacion=None,
            jornada_del_sobre=None,
            operation_id=uuid4(),
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            occurred_at=MOMENTO,
            origen="VENTA",
            venta_id=venta.venta_id,
        )

    assert [c.origen for c in entorno.cobranzas() if c.cliente_id == consumidor_id] == [
        "VENTA",
        "VENTA",
    ]


def test_cli03_la_cobranza_independiente_al_consumidor_final_sigue_rechazada(
    entorno: Entorno,
) -> None:
    from app.modules.cobranzas.domain.errores import ConsumidorFinalSinCuentaError

    consumidor_id = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)

    with pytest.raises(ConsumidorFinalSinCuentaError):
        cobranzas_service.registrar_cobranza(
            entorno.org,
            entorno.sesion,
            RELOJ,
            cobranza_id=uuid4(),
            cliente_id=consumidor_id,
            importe=Decimal("100.00"),
            medios=[MedioACobrar(entorno.efectivo_id, Decimal("100.00"), None)],
            observacion=None,
            jornada_del_sobre=None,
            operation_id=uuid4(),
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            occurred_at=MOMENTO,
        )
