"""Change 11, tareas 9.1 y 9.2: `COMPRA_ANULAR` v1 por el bus, contra PostgreSQL real.

Reglas citadas: CMP-05, CMP-06, CMP-07, CC-03, CST-11, CST-13, STK-05, CAT-05, INV-01,
INV-05, INV-06, INV-12, INV-13, INV-21, SYN-02, SYN-07, SEG-06, AUD-01 y `design.md`
D3, D8, D9, D10, D11, D12, D14.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from compras_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import desactivar_producto_sql

from app.core.errors import DomainError, PermisoRequeridoError
from app.modules.costeo.models import CostoProductoMov
from app.modules.identidad.models import Auditoria
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS_COMPLETOS = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA", "PERMITIR_STOCK_NEGATIVO"})
PERMISOS_SIN_NEGATIVO = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_COMPLETOS)


def _compra_de_vino(entorno: Entorno, *, cantidad: str = "10", valor: str = "6000.00") -> UUID:
    """Crédito: `cantidad` cajas x6 de Vino A a `valor` sin IVA (el total neto con IVA 21%)."""
    neto = Decimal(cantidad) * Decimal(valor)
    previas = {c.id for c in entorno.compras()}
    entorno.enviar(
        entorno.contenido(
            lineas=[entorno.linea("vino", cantidad=cantidad, valor=valor)],
            total_factura=str((neto * Decimal("1.21")).quantize(Decimal("0.01"))),
        )
    )
    (nueva,) = [c for c in entorno.compras() if c.id not in previas]
    return nueva.id


def _compra_de_botellas(entorno: Entorno, cantidad: str, valor: str) -> UUID:
    """Crédito: `cantidad` botellas de Vino A a `valor` (presentación Botella, x1)."""
    previas = {c.id for c in entorno.compras()}
    entorno.enviar(
        entorno.contenido(
            lineas=[
                entorno.linea(
                    "vino",
                    presentacion_id=str(entorno.botella_vino_id),
                    cantidad=cantidad,
                    valor=valor,
                )
            ],
            total_factura=str(
                (Decimal(cantidad) * Decimal(valor) * Decimal("1.21")).quantize(Decimal("0.01"))
            ),
        )
    )
    (nueva,) = [c for c in entorno.compras() if c.id not in previas]
    return nueva.id


def _egresar(entorno: Entorno, cantidad: int) -> None:
    stock_service.registrar_movimientos(
        entorno.org,
        entorno.sesion,
        RELOJ,
        lineas=[
            LineaDeMovimiento(
                producto_id=entorno.vino_id,
                ubicacion_id=entorno.deposito_id,
                cantidad_base=-cantidad,
                tipo="VENTA",
                costo_unitario=None,
                origen_tipo="VENTA",
                origen_id=uuid4(),
            )
        ],
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=MOMENTO,
    )
    entorno.sesion.commit()


def _cuenta(entorno: Entorno) -> list[tuple[str, str, Decimal]]:
    return sorted((m.tipo, m.sentido, m.importe) for m in entorno.movimientos_de_cuenta())


# --- anulación de una compra a crédito (CMP-05) ---------------------------------------


def test_anular_una_compra_a_credito_revierte_stock_y_cuenta(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)

    comando = entorno.anular(compra_id)

    (compra,) = entorno.compras()
    assert compra.estado == "ANULADA"
    assert compra.anulacion_motivo_id == entorno.motivo_id
    assert compra.anulada_por_id == entorno.usuario_id
    assert compra.anulada_en == MOMENTO
    assert entorno.saldo(entorno.vino_id) == 0
    egreso = [m for m in entorno.movimientos_de_stock() if m.tipo == "ANULACION_COMPRA"]
    assert [(m.cantidad_base, m.costo_unitario) for m in egreso] == [(-60, Decimal("1000.000000"))]
    assert (egreso[0].origen_tipo, egreso[0].origen_id) == ("ANULACION_COMPRA", compra_id)
    assert _cuenta(entorno) == [
        ("ANULACION_COMPRA", "REDUCE", Decimal("72600.00")),
        ("COMPRA", "AUMENTA", Decimal("72600.00")),
    ]
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert comando.resultado == {
        "compra_id": str(compra_id),
        "estado": "ANULADA",
        "pago_anulado": False,
        "observaciones": ["ANULACION_COMPRA_SIN_RECALCULO"],
    }


def test_la_anulacion_no_borra_nada_y_deja_las_lineas_inv_05(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)

    entorno.anular(compra_id)

    assert len(entorno.lineas()) == 1
    assert len(entorno.movimientos_de_stock()) == 2
    assert len(entorno.movimientos_de_cuenta()) == 2


def test_la_anulacion_deja_una_sola_auditoria(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)
    operation_id = uuid4()

    entorno.anular(compra_id, operation_id=operation_id)

    assert entorno.auditorias(operation_id) == 1
    # Deuda nominada (D10): el motivo de la anulación sigue sin copiarse a la auditoría.
    filas = entorno.sesion.scalars(
        select(Auditoria).where(
            Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id
        )
    ).all()
    assert [(f.motivo_id, f.observacion) for f in filas] == [(None, None)]


# --- reversión del promedio (CMP-06) ---------------------------------------------------


def test_se_recalcula_el_promedio_al_anular_la_segunda_compra(entorno: Entorno) -> None:
    _compra_de_vino(entorno)  # 60 a 1000
    segunda = _compra_de_botellas(entorno, "60", "1100.00")  # 60 a 1100 -> 1050, 120
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")

    comando = entorno.anular(segunda)

    assert entorno.promedio(entorno.vino_id) == Decimal("1000.000000")
    assert entorno.stock_total(entorno.vino_id) == 60
    assert comando.estado == "ACEPTADO"
    assert entorno.observaciones() == []
    historia = sorted(entorno.historia_de_costo(), key=lambda fila: fila.registered_at)
    reversion = next(h for h in historia if h.origen_tipo == "ANULACION_COMPRA")
    assert (reversion.cantidad, reversion.costo_ingreso) == (-60, Decimal("1100.000000"))
    assert reversion.recalculado is True


def test_con_stock_restante_cero_mantiene_el_promedio_y_observa(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)

    comando = entorno.anular(compra_id)

    assert entorno.stock_total(entorno.vino_id) == 0
    assert entorno.promedio(entorno.vino_id) == Decimal("1000.000000")
    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.observaciones() == ["ANULACION_COMPRA_SIN_RECALCULO"]
    reversion = next(h for h in entorno.historia_de_costo() if h.origen_tipo == "ANULACION_COMPRA")
    assert reversion.recalculado is False
    assert reversion.promedio_nuevo == reversion.promedio_anterior == Decimal("1000.000000")


def test_con_promedio_resultante_no_positivo_mantiene_el_promedio_y_observa(
    entorno: Entorno,
) -> None:
    entorno.sembrar_stock_inicial(entorno.vino_id, 10, "100")
    compra_id = _compra_de_botellas(entorno, "60", "2000.00")
    assert entorno.promedio(entorno.vino_id) == Decimal("1728.571429")
    _egresar(entorno, 5)

    comando = entorno.anular(compra_id)

    assert entorno.stock_total(entorno.vino_id) == 5
    assert entorno.promedio(entorno.vino_id) == Decimal("1728.571429")
    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.observaciones() == ["ANULACION_COMPRA_SIN_RECALCULO"]


def test_las_lineas_se_revierten_en_orden_inverso(entorno: Entorno) -> None:
    """CMP-06: dos líneas del mismo producto; en orden inverso el promedio vuelve a 1000."""
    entorno.enviar(
        entorno.contenido(
            lineas=[
                entorno.linea(
                    "vino",
                    presentacion_id=str(entorno.botella_vino_id),
                    cantidad="60",
                    valor="1000",
                ),
                entorno.linea(
                    "vino",
                    presentacion_id=str(entorno.botella_vino_id),
                    cantidad="60",
                    valor="1100",
                ),
            ],
            total_factura="152460.00",
        )
    )
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")

    entorno.anular(entorno.compras()[0].id)

    assert entorno.promedio(entorno.vino_id) == Decimal("1000.000000")
    assert entorno.stock_total(entorno.vino_id) == 0
    reversiones = sorted(
        (h for h in entorno.historia_de_costo() if h.origen_tipo == "ANULACION_COMPRA"),
        key=lambda fila: fila.stock_anterior,
        reverse=True,
    )
    assert [(h.costo_ingreso, h.recalculado) for h in reversiones] == [
        (Decimal("1100.000000"), True),
        (Decimal("1000.000000"), False),
    ]


# --- stock negativo (CMP-07) -----------------------------------------------------------


def _escenario_de_stock_insuficiente(entorno: Entorno) -> UUID:
    _compra_de_vino(entorno)  # 60 a 1000
    segunda = _compra_de_botellas(entorno, "60", "1100.00")
    _egresar(entorno, 72)  # quedan 48 a 1050
    return segunda


def test_sin_permiso_de_negativo_y_sin_stock_suficiente_se_rechaza(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=PERMISOS_SIN_NEGATIVO)
    segunda = _escenario_de_stock_insuficiente(entorno)

    with pytest.raises(DomainError) as error:
        entorno.anular(segunda)

    assert error.value.codigo == "STOCK_INSUFICIENTE"
    entorno.sesion.rollback()
    assert next(c for c in entorno.compras() if c.id == segunda).estado == "CONFIRMADA"
    assert entorno.saldo(entorno.vino_id) == 48
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert entorno.observaciones() == []


def test_con_permiso_de_negativo_deja_menos_doce_y_observa(entorno: Entorno) -> None:
    segunda = _escenario_de_stock_insuficiente(entorno)

    comando = entorno.anular(segunda)

    assert entorno.saldo(entorno.vino_id) == -12
    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.observaciones() == ["ANULACION_COMPRA_SIN_RECALCULO", "STOCK_NEGATIVO"]


def test_con_permiso_pero_con_stock_suficiente_no_hay_observacion_de_negativo(
    entorno: Entorno,
) -> None:
    _compra_de_vino(entorno)
    segunda = _compra_de_botellas(entorno, "60", "1100.00")

    entorno.anular(segunda)

    assert entorno.observaciones() == []


# --- compra de contado (D3) ------------------------------------------------------------


def _contado(entorno: Entorno) -> UUID:
    entorno.confirmar_contado(
        (entorno.efectivo_id, "100000.00", None), (entorno.transferencia_id, "52460.00", "0042")
    )
    (compra,) = entorno.compras()
    return compra.id


def test_contado_devolviendo_el_pago_anula_el_pago_y_deja_el_saldo_en_cero(
    entorno: Entorno,
) -> None:
    compra_id = _contado(entorno)

    comando = entorno.anular(compra_id, devuelve_pago=True)

    (pago,) = entorno.pagos()
    assert pago.estado == "ANULADA"
    assert pago.anulado_por_id == entorno.usuario_id
    assert pago.anulado_en == MOMENTO
    assert _cuenta(entorno) == [
        ("ANULACION_COMPRA", "REDUCE", Decimal("152460.00")),
        ("ANULACION_PAGO", "AUMENTA", Decimal("152460.00")),
        ("COMPRA", "AUMENTA", Decimal("152460.00")),
        ("PAGO", "REDUCE", Decimal("152460.00")),
    ]
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert comando.resultado is not None
    assert comando.resultado["pago_anulado"] is True
    assert len(entorno.medios_de_pago()) == 2  # los medios no se borran (INV-05)


def test_contado_sin_devolver_el_pago_deja_saldo_a_favor(entorno: Entorno) -> None:
    compra_id = _contado(entorno)

    comando = entorno.anular(compra_id, devuelve_pago=False)

    (pago,) = entorno.pagos()
    assert pago.estado == "CONFIRMADA"
    assert pago.anulado_en is None
    assert _cuenta(entorno) == [
        ("ANULACION_COMPRA", "REDUCE", Decimal("152460.00")),
        ("COMPRA", "AUMENTA", Decimal("152460.00")),
        ("PAGO", "REDUCE", Decimal("152460.00")),
    ]
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")
    assert comando.resultado is not None
    assert comando.resultado["pago_anulado"] is False


def test_contado_sin_indicar_si_devuelve_el_pago_se_rechaza_sin_efectos(
    entorno: Entorno,
) -> None:
    compra_id = _contado(entorno)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id)

    assert error.value.codigo == "CONDICION_INVALIDA"
    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 2


@pytest.mark.parametrize("devuelve_pago", [True, False])
def test_credito_con_devuelve_pago_se_rechaza_sin_efectos(
    entorno: Entorno, devuelve_pago: bool
) -> None:
    compra_id = _compra_de_vino(entorno)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id, devuelve_pago=devuelve_pago)

    assert error.value.codigo == "CONDICION_INVALIDA"
    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"


# --- estados, idempotencia y motivo ----------------------------------------------------


def test_anular_dos_veces_con_otro_operation_id_es_compra_ya_anulada(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)
    entorno.anular(compra_id)
    cuenta = len(entorno.movimientos_de_cuenta())
    stock = len(entorno.movimientos_de_stock())

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id)

    assert error.value.codigo == "COMPRA_YA_ANULADA"
    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert len(entorno.movimientos_de_cuenta()) == cuenta
    assert len(entorno.movimientos_de_stock()) == stock


def test_el_reenvio_con_el_mismo_operation_id_devuelve_el_resultado_original_inv_06(
    entorno: Entorno,
) -> None:
    compra_id = _compra_de_vino(entorno)
    operation_id = uuid4()
    primero = entorno.anular(compra_id, operation_id=operation_id)

    segundo = entorno.anular(compra_id, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len([m for m in entorno.movimientos_de_stock() if m.tipo == "ANULACION_COMPRA"]) == 1
    assert len([m for m in entorno.movimientos_de_cuenta() if m.tipo == "ANULACION_COMPRA"]) == 1


def test_motivo_de_otro_ambito_es_motivo_invalido(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)
    ajuste = entorno.crear_motivo("AJUSTE_STOCK", "Rotura")

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id, motivo_id=ajuste)

    assert error.value.codigo == "MOTIVO_INVALIDO"
    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"


def test_motivo_inactivo_es_motivo_invalido(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)
    entorno.sesion.execute(
        text("UPDATE motivo SET activo = false WHERE organizacion_id = :o AND id = :m"),
        {"o": entorno.org, "m": entorno.motivo_id},
    )

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id)

    assert error.value.codigo == "MOTIVO_INVALIDO"


def test_motivo_de_otra_organizacion_responde_404(entorno: Entorno, db_session: Session) -> None:
    compra_id = _compra_de_vino(entorno)
    otra = Entorno(db_session)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id, motivo_id=otra.motivo_id)

    assert error.value.status_http == 404


def test_motivo_inexistente_responde_404(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id, motivo_id=uuid4())

    assert error.value.status_http == 404


# --- permisos y aislamiento ---------------------------------------------------------------


def test_sin_permiso_de_anulacion_responde_403_y_la_compra_sigue_confirmada(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"REGISTRAR_COMPRA"}))
    compra_id = _compra_de_vino(entorno)

    with pytest.raises(PermisoRequeridoError):
        entorno.anular(compra_id)

    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 1


def test_anular_una_compra_de_otra_organizacion_responde_404_inv_21(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session, permisos=PERMISOS_COMPLETOS)
    compra_ajena = _compra_de_vino(ajena)

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_ajena)

    assert error.value.status_http == 404
    ajena.sesion.rollback()
    assert ajena.compras()[0].estado == "CONFIRMADA"


def test_anular_una_compra_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.anular(uuid4())

    assert error.value.status_http == 404


# --- maestros inactivos (D11) ----------------------------------------------------------------


def test_se_puede_anular_con_el_producto_y_el_proveedor_desactivados_d11(
    entorno: Entorno,
) -> None:
    compra_id = _compra_de_vino(entorno)
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)
    entorno.sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.proveedor_id},
    )
    entorno.sesion.commit()

    entorno.anular(compra_id)

    assert entorno.compras()[0].estado == "ANULADA"
    assert entorno.saldo(entorno.vino_id) == 0


def test_una_ubicacion_inactiva_bloquea_la_anulacion(entorno: Entorno) -> None:
    compra_id = _compra_de_vino(entorno)
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": entorno.deposito_id},
    )
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.anular(compra_id)

    assert error.value.codigo == "UBICACION_INACTIVA"
    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"


# --- INV-01: atomicidad ----------------------------------------------------------------------


def test_una_falla_despues_del_egreso_y_antes_de_la_cuenta_no_deja_efectos_inv_01(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.cuentas_corrientes import service as cuentas_service

    compra_id = _compra_de_vino(entorno)
    historia_previa = len(entorno.historia_de_costo())
    movimientos_previos = len(entorno.movimientos_de_stock())
    cuenta_previa = len(entorno.movimientos_de_cuenta())

    original = cuentas_service.registrar_movimiento

    def _falla_en_la_anulacion(*args: object, **kwargs: object) -> object:
        if kwargs.get("tipo") == "ANULACION_COMPRA":
            raise RuntimeError("falla inyectada en la cuenta")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cuentas_service, "registrar_movimiento", _falla_en_la_anulacion)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.anular(compra_id)

    entorno.sesion.rollback()
    assert entorno.compras()[0].estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_stock()) == movimientos_previos
    assert len(entorno.historia_de_costo()) == historia_previa
    assert len(entorno.movimientos_de_cuenta()) == cuenta_previa
    assert entorno.saldo(entorno.vino_id) == 60
    assert entorno.observaciones() == []
    historia = entorno.sesion.scalars(
        select(CostoProductoMov).where(CostoProductoMov.origen_tipo == "ANULACION_COMPRA")
    ).all()
    assert historia == []


def test_confirmar_y_anular_deja_el_saldo_y_el_stock_como_estaban_inv_12_inv_13(
    entorno: Entorno,
) -> None:
    compra_id = _compra_de_vino(entorno)

    entorno.anular(compra_id)

    assert entorno.saldo(entorno.vino_id) == 0
    assert entorno.stock_total(entorno.vino_id) == 0
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
