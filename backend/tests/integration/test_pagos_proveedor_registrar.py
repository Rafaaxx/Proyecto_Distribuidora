"""Change 12, grupo 4, tarea 4.1: `PAGO_PROVEEDOR_REGISTRAR` v1 por el bus, contra
PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio
que `test_compras_confirmar.py`). La cobertura HTTP es de `test_pagos_proveedor_api.py`
(tarea 4.3) y la de anulación, de `test_pagos_proveedor_anular.py` (grupo 5).

Reglas citadas: PAG-01, PAG-02, PAG-03, INV-01, INV-03, INV-06, INV-08, INV-13, INV-21,
CC-02, CC-03, CC-04, CC-05, CC-08, CST-14, TR-04, TR-05, TR-08, TR-09, SEG-06, AUD-01,
ADR-022, ADR-034 y `design.md` D2, D3, D4, D5, D6, D7, D10.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import MOMENTO, PAGAR, PERMISOS_DE_PAGO, RELOJ, Entorno
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.cuentas_corrientes.domain.errores import CuentaConOperacionesError
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores.domain.errores import (
    FechaInvalidaError,
    MedioPagoInactivoError,
    MediosNoSumanImporteError,
    RecursoNoEncontradoError,
    ReferenciaObligatoriaError,
)
from app.modules.stock import service as stock_service
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_PAGO)


def _movimientos_de_pago(entorno: Entorno) -> list[CuentaMovimiento]:
    return [mov for mov in entorno.movimientos_de_cuenta() if mov.tipo == "PAGO"]


# --- el pago y su efecto en la cuenta (PAG-01, PAG-02, CC-03, INV-08) --------------------


def test_pago_con_efectivo_y_transferencia_queda_confirmada_y_cancela_la_deuda(
    entorno: Entorno,
) -> None:
    """Escenario "Pago con efectivo y transferencia" (D6, ADR-043 punto 2)."""
    assert entorno.deuda("152460.00") == Decimal("152460.00")
    operation_id = uuid4()

    comando = entorno.pagar_a_proveedor(operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (pago,) = entorno.pagos()
    assert pago.estado == "CONFIRMADA"
    assert pago.origen == "INDEPENDIENTE"
    assert pago.compra_id is None
    assert pago.importe == Decimal("152460.00")
    assert pago.fecha == date(2026, 5, 10)
    assert pago.observacion is None
    medios = entorno.medios_de_pago()
    assert [(medio.medio_pago_id, medio.importe, medio.referencia) for medio in medios] == [
        (entorno.efectivo_id, Decimal("100000.00"), None),
        (entorno.transferencia_id, Decimal("52460.00"), "0042"),
    ]
    (movimiento,) = _movimientos_de_pago(entorno)
    assert (movimiento.sentido, movimiento.importe) == ("REDUCE", Decimal("152460.00"))
    assert movimiento.origen_tipo == "PAGO"
    assert movimiento.origen_id == pago.id
    assert movimiento.occurred_at == MOMENTO
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert entorno.auditorias(operation_id) == 1


def test_la_observacion_se_guarda_recortada(entorno: Entorno) -> None:
    """Escenario "Pago con un solo medio y observación" (D6, PAG-01)."""
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="100000.00",
            medios=entorno.pagar((entorno.efectivo_id, "100000.00", None)),
            observacion="  paga factura 0001-123  ",
        )
    )

    (pago,) = entorno.pagos()
    assert pago.observacion == "paga factura 0001-123"


def test_el_contenido_con_observacion_de_501_caracteres_se_rechaza_sin_efectos(
    entorno: Entorno,
) -> None:
    """D6: ninguna vía de escritura esquiva el límite (el bus valida el contenido)."""
    from app.commands.errores import ContenidoDeComandoInvalidoError

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.pagar_a_proveedor(entorno.contenido_pago(observacion="a" * 501))

    entorno.sin_efectos()


def test_el_contenido_con_observacion_de_500_caracteres_se_guarda_completa(
    entorno: Entorno,
) -> None:
    entorno.pagar_a_proveedor(entorno.contenido_pago(observacion="b" * 500))

    (pago,) = entorno.pagos()
    assert pago.observacion == "b" * 500


def test_la_observacion_vacia_se_guarda_como_nula(entorno: Entorno) -> None:
    """D6: vacía equivale a no informarla (columna nulable, D9)."""
    entorno.pagar_a_proveedor(entorno.contenido_pago(observacion="   "))

    (pago,) = entorno.pagos()
    assert pago.observacion is None


def test_pago_parcial_deja_el_saldo_pendiente(entorno: Entorno) -> None:
    """Escenario "Pago parcial de una deuda" (PAG-02, CC-04)."""
    assert entorno.deuda("153720.00") == Decimal("153720.00")

    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="100000.00",
            medios=entorno.pagar((entorno.efectivo_id, "100000.00", None)),
        )
    )

    assert entorno.saldo_de_cuenta() == Decimal("53720.00")


def test_pago_mayor_que_la_deuda_deja_saldo_a_nuestro_favor(entorno: Entorno) -> None:
    """Escenario "Pago mayor que la deuda" (`design.md` D3 opción A: se admite, el saldo
    queda a favor de la organización; no existe `PAGO_SUPERA_DEUDA`)."""
    assert entorno.deuda("153720.00") == Decimal("153720.00")

    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="160000.00",
            medios=[
                {
                    "medio_pago_id": str(entorno.efectivo_id),
                    "importe": "100000.00",
                    "referencia": None,
                },
                {
                    "medio_pago_id": str(entorno.transferencia_id),
                    "importe": "60000.00",
                    "referencia": "0042",
                },
            ],
        )
    )

    assert entorno.saldo_de_cuenta() == Decimal("-6280.00")


def test_el_saldo_a_nuestro_favor_lo_compensa_la_compra_siguiente(entorno: Entorno) -> None:
    """Escenario "El saldo a favor se compensa con la compra siguiente" (D3): la próxima
    compra a crédito absorbe el saldo a favor por el saldo general, sin ningún movimiento
    de compensación (CC-03 intacto)."""
    entorno.deuda("153720.00")
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="160000.00",
            medios=entorno.pagar((entorno.efectivo_id, "160000.00", None)),
        )
    )
    movimientos_antes = len(entorno.movimientos_de_cuenta())

    entorno.enviar(entorno.contenido(lineas=[entorno.linea("vino")], total_factura="100000.00"))

    assert entorno.saldo_de_cuenta() == Decimal("93720.00")
    assert len(entorno.movimientos_de_cuenta()) == movimientos_antes + 1


def test_el_pago_no_toca_stock_costo_promedio_ni_historia_de_costo(entorno: Entorno) -> None:
    """Escenario "El pago no toca costos ni stock" (PAG-02, CST-14)."""
    entorno.enviar(entorno.contenido(lineas=[entorno.linea("vino")]))
    promedio = entorno.promedio(entorno.vino_id)
    assert promedio is not None and promedio > 0
    stock = stock_service.obtener_saldo(
        entorno.org, entorno.sesion, producto_id=entorno.vino_id, ubicacion_id=entorno.deposito_id
    )
    historia = len(entorno.historia_de_costo())

    entorno.pagar_a_proveedor()

    assert entorno.promedio(entorno.vino_id) == promedio
    assert (
        stock_service.obtener_saldo(
            entorno.org,
            entorno.sesion,
            producto_id=entorno.vino_id,
            ubicacion_id=entorno.deposito_id,
        )
        == stock
    )
    assert len(entorno.historia_de_costo()) == historia


# --- medios de pago (D6, PAG-01, TR-09, INV-21, INV-08, `01` §4) ---------------------------


def test_medio_inactivo_se_rechaza_indicando_el_medio(entorno: Entorno) -> None:
    """Escenario "Medio inactivo" (TR-09)."""
    inactivo = entorno.crear_medio("Billetera vieja", requiere_referencia=False, activo=False)
    entorno.sesion.commit()

    with pytest.raises(MedioPagoInactivoError) as error:
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(
                importe="100000.00",
                medios=entorno.pagar(
                    (entorno.efectivo_id, "50000.00", None), (inactivo, "50000.00", None)
                ),
            )
        )

    assert error.value.extension == {"medio": 1}
    entorno.sin_efectos()


def test_medio_de_otra_organizacion_responde_404(entorno: Entorno) -> None:
    """Escenario "Medio de otra organización" (INV-21, SEG-07)."""
    ajena = crear_organizacion(entorno.sesion).id
    medio_ajeno = Entorno(entorno.sesion, permisos=PERMISOS_DE_PAGO).crear_medio(
        "Efectivo", requiere_referencia=False, org=ajena
    )
    entorno.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(
                importe="100000.00", medios=entorno.pagar((medio_ajeno, "100000.00", None))
            )
        )

    assert error.value.status_http == 404
    assert error.value.extension == {"medio": 0}
    entorno.sin_efectos()


def test_medio_que_exige_referencia_sin_referencia_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Medio que exige referencia sin referencia" (`01` §4, D6)."""
    with pytest.raises(ReferenciaObligatoriaError) as error:
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(
                importe="100000.00",
                medios=entorno.pagar((entorno.transferencia_id, "100000.00", None)),
            )
        )

    assert error.value.extension == {"medio": 0}
    entorno.sin_efectos()


def test_inv08_los_medios_que_no_suman_el_importe_se_rechazan(entorno: Entorno) -> None:
    """Escenario "INV-08 — medios que no suman el importe": sobrante de un centavo."""
    with pytest.raises(MediosNoSumanImporteError) as error:
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(
                importe="152460.00",
                medios=entorno.pagar(
                    (entorno.efectivo_id, "100000.00", None),
                    (entorno.transferencia_id, "52460.00", "0042"),
                    (entorno.efectivo_id, "0.01", None),
                ),
            )
        )

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"
    entorno.sin_efectos()


def test_el_mismo_medio_puede_repetirse_con_referencias_distintas(entorno: Entorno) -> None:
    """Escenario "El mismo medio dos veces" (D6): dos transferencias distintas del mismo
    medio de pago."""
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="152460.00",
            medios=entorno.pagar(
                (entorno.transferencia_id, "100000.00", "0001"),
                (entorno.transferencia_id, "52460.00", "0002"),
            ),
        )
    )

    assert len(entorno.medios_de_pago()) == 2
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")


# --- proveedor y fecha (D4, D5, INV-21, TR-04) --------------------------------------------


def test_proveedor_de_otra_organizacion_responde_404(entorno: Entorno) -> None:
    """Escenario "Proveedor de otra organización" (INV-21, SEG-07, TR-08)."""
    ajeno = crear_proveedor(entorno.sesion, crear_organizacion(entorno.sesion).id, nombre="Otra")
    entorno.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.pagar_a_proveedor(entorno.contenido_pago(proveedor_id=str(ajeno)))

    assert error.value.status_http == 404
    entorno.sin_efectos()


def test_pago_a_un_proveedor_inactivo_con_deuda_se_admite(entorno: Entorno) -> None:
    """Escenario "Proveedor inactivo con deuda" (`design.md` D5 opción A, ADR-034 punto 3):
    la deuda existe aunque el proveedor esté dado de baja y se le puede pagar."""
    assert entorno.deuda("80000.00") == Decimal("80000.00")
    entorno.sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.proveedor_id},
    )
    entorno.sesion.commit()

    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="80000.00",
            medios=entorno.pagar((entorno.efectivo_id, "80000.00", None)),
        )
    )

    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert entorno.pagos()[0].estado == "CONFIRMADA"


def test_un_pago_con_fecha_anterior_guarda_esa_fecha_y_el_movimiento_usa_el_momento_del_comando(
    entorno: Entorno,
) -> None:
    """Escenario "Pago con fecha anterior" (PAG-01, TR-05, D4): la `fecha` es la del pago
    real (sin límite hacia atrás) y el `PAGO` se fecha con el `occurred_at` del comando."""
    entorno.deuda("153720.00")

    for fecha in ("2026-05-08", "2025-12-31"):
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(
                fecha=fecha,
                importe="1000.00",
                medios=entorno.pagar((entorno.efectivo_id, "1000.00", None)),
            )
        )

    assert sorted(pago.fecha for pago in entorno.pagos()) == [
        date(2025, 12, 31),
        date(2026, 5, 8),
    ]
    movimientos = _movimientos_de_pago(entorno)
    assert len(movimientos) == 2
    assert {movimiento.occurred_at for movimiento in movimientos} == {MOMENTO}


def test_fecha_posterior_a_hoy_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Fecha futura" (TR-04, D4)."""
    with pytest.raises(FechaInvalidaError) as error:
        entorno.pagar_a_proveedor(entorno.contenido_pago(fecha="2026-05-11"))

    assert error.value.codigo == "FECHA_INVALIDA"
    entorno.sin_efectos()


def test_despues_de_un_pago_la_cuenta_no_admite_saldo_inicial(entorno: Entorno) -> None:
    """Escenario "Después de un pago la cuenta no admite saldo inicial" (CC-08): el pago es
    un movimiento más de la cuenta."""
    entorno.pagar_a_proveedor()

    with pytest.raises(CuentaConOperacionesError):
        cuentas_service.registrar_saldo_inicial(
            entorno.org,
            entorno.sesion,
            RELOJ,
            cuenta_tipo="PROVEEDOR",
            entidad_id=entorno.proveedor_id,
            importe=Decimal("1000.00"),
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            operation_id=uuid4(),
        )

    entorno.sesion.rollback()
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")


# --- modo, idempotencia, permiso y auditoría (CMP-08, INV-06, SYN-02, SEG-06, AUD-01) -----


def test_el_pago_es_solo_online(entorno: Entorno) -> None:
    """`02` §6.5: el pago necesita conexión; un lote `OFFLINE` lo rechaza sin efectos."""
    item = ItemLote(
        operation_id=uuid4(),
        tipo=PAGAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido_pago(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    entorno.sin_efectos()


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    primero = entorno.pagar_a_proveedor(operation_id=operation_id)
    segundo = entorno.pagar_a_proveedor(operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.pagos()) == 1
    assert len(entorno.medios_de_pago()) == 2
    assert len(entorno.movimientos_de_cuenta()) == 1
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.pagar_a_proveedor(operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.pagar_a_proveedor(
            entorno.contenido_pago(importe="160000.00"), operation_id=operation_id
        )

    assert len(entorno.pagos()) == 1
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")


def test_sin_registrar_pago_proveedor_se_rechaza_con_403_y_sin_reserva(
    db_session: Session,
) -> None:
    """`01` §19, SEG-06: `REGISTRAR_PAGO_PROVEEDOR`; sin ella, 403 y nada escrito."""
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.pagar_a_proveedor(operation_id=operation_id)

    assert error.value.status_http == 403
    entorno.sin_efectos()


def test_el_contenido_no_puede_traer_la_organizacion(entorno: Entorno) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token, no del cuerpo."""
    from app.commands.errores import ContenidoDeComandoInvalidoError

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.pagar_a_proveedor(entorno.contenido_pago(organizacion_id=str(uuid4())))

    entorno.sin_efectos()


def test_el_importe_travel_como_string(entorno: Entorno) -> None:
    """INV-03: un número JSON ya degradado por `float` ni siquiera llega al esquema del
    comando; la huella canónica del bus lo rechaza antes."""
    from app.commands.huella import ContenidoNoSerializableError

    with pytest.raises(ContenidoNoSerializableError):
        entorno.pagar_a_proveedor(entorno.contenido_pago(importe=152460.0))

    entorno.sin_efectos()


# --- INV-01: atomicidad (D10) --------------------------------------------------------------


def test_inv01_una_falla_despues_del_pago_y_antes_de_la_cuenta_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "INV-01 — falla después del pago": ni pago, ni medio, ni movimiento de
    cuenta, ni cambio de saldo, ni auditoría. La transacción la maneja el bus (`02` §5.2),
    así que el pago insertado antes de la falla se revierte con ella."""
    insertados: list[UUID] = []
    original_pago = proveedores_repository.insertar_pago

    def insertar_y_contar(*args: Any, **kwargs: Any) -> Any:
        pago = original_pago(*args, **kwargs)
        insertados.append(pago.id)
        return pago

    def falla(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("falla inyectada después del pago y antes de la cuenta")

    monkeypatch.setattr(proveedores_repository, "insertar_pago", insertar_y_contar)
    monkeypatch.setattr(cuentas_service, "registrar_movimiento", falla)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.pagar_a_proveedor(operation_id=operation_id)

    assert len(insertados) == 1  # el pago ya se había escrito cuando falló la cuenta
    entorno.sin_efectos()
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert entorno.auditorias(operation_id) == 0


# --- invariantes de libro (INV-13, PAG-02) ------------------------------------------------


def test_inv13_el_saldo_materializado_coincide_con_el_libro(entorno: Entorno) -> None:
    """INV-13: el saldo del proveedor es la suma de sus movimientos (PAG-02)."""
    entorno.deuda("153720.00")
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe="100000.00",
            medios=entorno.pagar((entorno.efectivo_id, "100000.00", None)),
        )
    )

    libro = sum(
        (
            movimiento.importe if movimiento.sentido == "AUMENTA" else -movimiento.importe
            for movimiento in entorno.sesion.scalars(
                select(CuentaMovimiento)
                .where(CuentaMovimiento.organizacion_id == entorno.org)
                .order_by(CuentaMovimiento.registered_at, CuentaMovimiento.id)
            ).all()
        ),
        Decimal("0.00"),
    )
    assert entorno.saldo_de_cuenta() == libro


def test_un_pago_no_se_imputa_a_ninguna_compra(entorno: Entorno) -> None:
    """PAG-02: el pago no se imputa a compras; `compra_id` queda en `None`."""
    entorno.deuda("153720.00")

    entorno.pagar_a_proveedor()

    (pago,) = [fila for fila in entorno.pagos() if fila.origen == "INDEPENDIENTE"]
    assert pago.compra_id is None
    (movimiento,) = _movimientos_de_pago(entorno)
    assert movimiento.origen_tipo == "PAGO"
    assert movimiento.origen_id == pago.id


def test_audit01_una_sola_fila_de_auditoria_por_pago(entorno: Entorno) -> None:
    """AUD-01, ADR-022: una fila de auditoría con el `operation_id` del comando."""
    operation_id = uuid4()

    entorno.pagar_a_proveedor(operation_id=operation_id)

    assert entorno.auditorias(operation_id) == 1
