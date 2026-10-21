"""Tarea 7.5 (change 18a; spec `ventas/confirmacion-de-venta`, requisitos "La cobranza en el acto
registra su propio crédito" y "El cliente debe estar habilitado"; `design.md` D5, D12): la
cobranza de `VENTA_CONFIRMAR` con conexión, contra PostgreSQL real.

Reglas citadas: VTA-11, CC-05, CC-04, CRE-02, COB-02, INV-08, INV-01, INV-13, CLI-02, CLI-03.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import PERMISOS_DE_SUPERVISOR, PERMISOS_DE_VENTA, EntornoVenta

from app.core.errors import DomainError
from app.modules.cobranzas.domain.errores import MedioPagoInactivoError
from app.modules.configuracion.domain.medios import ReferenciaObligatoriaError
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.ventas.domain.errores import (
    ClienteInactivoError,
    ClienteSuspendidoError,
    ConsumidorFinalContadoError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


def _vender_a_80000(entorno: EntornoVenta, **cambios: object) -> None:
    """Una venta de `80000.00` (un producto de $80.000 la unidad) para el ejemplo de `01` §9.2."""
    producto_id, presentacion_id = entorno.crear_producto("Reserva", unidades_caja=1)
    entorno.poner_precio(entorno.version_id, producto_id, "80000.00", 1)
    entorno.comprar(producto_id, 10, "50000")
    entorno.sesion.commit()
    entorno.vender(
        entorno.linea(
            producto_id,
            presentacion_id,
            1,
            unidades_presentacion=1,
            precio="80000.00",
            unidades_referencia=1,
        ),
        **cambios,
    )


# --- la cobranza en el acto (VTA-11, CC-05, CRE-02) ---------------------------------------------


def test_cc05_el_debito_va_antes_del_credito_y_el_saldo_es_el_del_ejemplo(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Ejemplo de `01` §9.2": saldo $150.000, venta de $80.000 con $20.000 en
    efectivo -> el débito `VENTA` y después el crédito `COBRANZA`; saldo $210.000."""
    _vender_a_80000(entorno, cobranza=entorno.cobranza())

    estado = cuentas_service.estado_de_cuenta(
        entorno.org,
        entorno.sesion,
        cuenta_tipo="CLIENTE",
        entidad_id=entorno.cliente_id,
        desde=None,
        hasta=None,
        cursor=None,
        limite=None,
    )
    assert [(m.tipo, m.importe, m.saldo_acumulado) for m in estado.movimientos] == [
        ("SALDO_INICIAL", Decimal("150000.00"), Decimal("150000.00")),
        ("VENTA", Decimal("80000.00"), Decimal("230000.00")),
        ("COBRANZA", Decimal("20000.00"), Decimal("210000.00")),
    ]
    assert estado.saldo_actual == Decimal("210000.00")


def test_vta11_la_cobranza_lleva_el_origen_la_venta_y_el_mismo_momento(
    entorno: EntornoVenta,
) -> None:
    entorno.vender(cobranza=entorno.cobranza((entorno.efectivo_id, "10000.00", None)))

    (venta,) = entorno.ventas()
    (cobranza,) = entorno.cobranzas()
    assert (cobranza.origen, cobranza.venta_id, cobranza.estado) == (
        "VENTA",
        venta.id,
        "CONFIRMADA",
    )
    assert cobranza.importe == Decimal("10000.00")
    assert cobranza.occurred_at == venta.occurred_at
    assert cobranza.dispositivo_id == venta.dispositivo_id
    (medio,) = entorno.medios_de_cobranza(cobranza.id)
    assert medio.importe == Decimal("10000.00")


def test_vta11_la_cobranza_total_deja_el_saldo_como_estaba(entorno: EntornoVenta) -> None:
    entorno.vender(cobranza=entorno.cobranza((entorno.efectivo_id, "31250.00", None)))

    assert entorno.saldo() == Decimal("150000.00")


def test_cc04_una_cobranza_superior_al_total_deja_saldo_a_favor(db_session: Session) -> None:
    """Escenario "Cobranza superior al total": saldo $10.000, venta $31.250 y paga $50.000."""
    entorno = EntornoVenta(db_session, saldo_inicial="10000.00")

    entorno.vender(cobranza=entorno.cobranza((entorno.efectivo_id, "50000.00", None)))

    assert entorno.saldo() == Decimal("-8750.00")


def test_vta11_la_cobranza_con_varios_medios_suma_sus_importes(entorno: EntornoVenta) -> None:
    entorno.vender(
        cobranza=entorno.cobranza(
            (entorno.efectivo_id, "10000.00", None),
            (entorno.transferencia_id, "5000.00", "0042"),
        )
    )

    (cobranza,) = entorno.cobranzas()
    assert cobranza.importe == Decimal("15000.00")
    assert len(entorno.medios_de_cobranza(cobranza.id)) == 2
    assert entorno.saldo() == Decimal("166250.00")


def test_vta11_sin_cobranza_solo_hay_debito(entorno: EntornoVenta) -> None:
    """Escenario "Sin cobranza"."""
    entorno.vender()

    assert entorno.cobranzas() == []
    assert entorno.movimientos("COBRANZA") == []
    assert entorno.saldo() == Decimal("181250.00")


# --- cobranza inválida: la venta no queda (INV-08, COB-02, INV-01) ------------------------------


def test_inv08_una_cobranza_sin_medios_se_rechaza_sin_efectos(entorno: EntornoVenta) -> None:
    """Escenario "Medios que no suman": lista vacía."""
    with pytest.raises(DomainError) as error:
        entorno.vender(cobranza={"cobranza_id": str(entorno.motivo_id), "medios": []})

    assert error.value.codigo in {"MEDIOS_INVALIDOS", "IMPORTE_INVALIDO"}
    entorno.sin_efectos_de_venta()


def test_inv08_mas_de_veinte_medios_o_un_importe_con_tres_decimales_se_rechazan(
    entorno: EntornoVenta,
) -> None:
    veintiuno = entorno.cobranza(*[(entorno.efectivo_id, "10.00", None)] * 21)
    tres_decimales = entorno.cobranza((entorno.efectivo_id, "10.005", None))

    for cobranza, codigos in (
        (veintiuno, {"MEDIOS_INVALIDOS"}),
        (tres_decimales, {"IMPORTE_INVALIDO"}),
    ):
        with pytest.raises(DomainError) as error:
            entorno.vender(cobranza=cobranza)
        assert error.value.codigo in codigos
        entorno.sesion.rollback()

    entorno.sin_efectos_de_venta()


def test_cob02_un_medio_que_exige_referencia_sin_ella_rechaza_la_venta(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Referencia faltante con conexión": la venta no queda (INV-01)."""
    with pytest.raises(ReferenciaObligatoriaError) as error:
        entorno.vender(cobranza=entorno.cobranza((entorno.transferencia_id, "5000.00", None)))

    assert error.value.codigo == "REFERENCIA_OBLIGATORIA"
    entorno.sin_efectos_de_venta()


def test_cob02_un_medio_inactivo_rechaza_la_venta(entorno: EntornoVenta) -> None:
    entorno.desactivar_medio(entorno.efectivo_id)

    with pytest.raises(MedioPagoInactivoError) as error:
        entorno.vender(cobranza=entorno.cobranza())

    assert (error.value.codigo, error.value.status_http) == ("MEDIO_PAGO_INACTIVO", 422)
    entorno.sin_efectos_de_venta()


# --- el cliente habilitado (CLI-02) -------------------------------------------------------------


def test_cli02_un_cliente_suspendido_sin_el_permiso_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Suspendido sin permiso"."""
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")
    entorno.sesion.commit()

    with pytest.raises(ClienteSuspendidoError) as error:
        entorno.vender()

    assert (error.value.codigo, error.value.status_http) == ("CLIENTE_SUSPENDIDO", 409)
    entorno.sin_efectos_de_venta()


def test_cli02_un_suspendido_con_vender_cliente_suspendido_se_vende(db_session: Session) -> None:
    """Escenario "Suspendido con permiso"."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")

    assert entorno.vender().estado == "ACEPTADO"


@pytest.mark.parametrize("permisos", [PERMISOS_DE_VENTA, PERMISOS_DE_SUPERVISOR])
def test_cli02_un_cliente_inactivo_no_se_vende_ni_con_el_permiso(
    db_session: Session, permisos: frozenset[str]
) -> None:
    """Escenario "Inactivo"."""
    entorno = EntornoVenta(db_session, permisos=permisos)
    entorno.actualizar_cliente(entorno.cliente_id, estado="INACTIVO")
    entorno.sesion.commit()

    with pytest.raises(ClienteInactivoError) as error:
        entorno.vender()

    assert (error.value.codigo, error.value.status_http) == ("CLIENTE_INACTIVO", 409)
    entorno.sin_efectos_de_venta()


# --- el consumidor final de contado (CLI-03, CC-08, D5) -----------------------------------------


def _consumidor_final(entorno: EntornoVenta) -> str:
    consumidor = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    entorno.sesion.commit()
    return str(consumidor)


def _linea_de_4300(entorno: EntornoVenta) -> dict[str, object]:
    """Una línea de `4300.00`: una "Gaseosa" de $4.300 la unidad."""
    producto_id, presentacion_id = entorno.crear_producto("Gaseosa", unidades_caja=1)
    entorno.poner_precio(entorno.version_id, producto_id, "4300.00", 1)
    entorno.comprar(producto_id, 10, "2000")
    entorno.sesion.commit()
    return entorno.linea(
        producto_id,
        presentacion_id,
        1,
        unidades_presentacion=1,
        precio="4300.00",
        unidades_referencia=1,
    )


def test_cli03_el_consumidor_final_de_contado_se_vende_y_su_saldo_queda_en_cero(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Consumidor final de contado": $4.300,00 con `4300.00` en efectivo."""
    consumidor = _consumidor_final(entorno)

    entorno.vender(
        _linea_de_4300(entorno),
        cliente_id=consumidor,
        cobranza=entorno.cobranza((entorno.efectivo_id, "4300.00", None)),
    )

    (venta,) = entorno.ventas()
    (cobranza,) = entorno.cobranzas()
    assert (cobranza.origen, cobranza.venta_id, cobranza.importe) == (
        "VENTA",
        venta.id,
        Decimal("4300.00"),
    )
    assert entorno.saldo(venta.cliente_id) == Decimal("0.00")
    assert entorno.saldo() == Decimal("150000.00")


@pytest.mark.parametrize("pagado", ["4000.00", "4300.01"])
def test_cli03_el_consumidor_final_con_otra_cobranza_se_rechaza_sin_efectos(
    entorno: EntornoVenta, pagado: str
) -> None:
    """La segunda venta del escenario: $4.300,00 con `4000.00` (y, triangulando, con más)."""
    consumidor = _consumidor_final(entorno)
    linea = _linea_de_4300(entorno)

    with pytest.raises(ConsumidorFinalContadoError) as error:
        entorno.vender(
            linea,
            cliente_id=consumidor,
            cobranza=entorno.cobranza((entorno.efectivo_id, pagado, None)),
        )

    assert (error.value.codigo, error.value.status_http) == ("CONSUMIDOR_FINAL_CONTADO", 422)
    entorno.sesion.rollback()
    assert entorno.ventas() == []
    assert entorno.cobranzas() == []


def test_cli03_el_consumidor_final_sin_cobranza_se_rechaza(entorno: EntornoVenta) -> None:
    consumidor = _consumidor_final(entorno)

    with pytest.raises(ConsumidorFinalContadoError):
        entorno.vender(_linea_de_4300(entorno), cliente_id=consumidor)

    entorno.sesion.rollback()
    assert entorno.ventas() == []
