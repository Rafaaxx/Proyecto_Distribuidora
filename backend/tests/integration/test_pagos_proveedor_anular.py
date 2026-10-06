"""Change 12, grupo 5 (tareas 5.1, 5.2 y 5.3): `PAGO_PROVEEDOR_ANULAR` v1 por el bus,
contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio
que `test_compras_anular.py`). El registro del pago está en
`test_pagos_proveedor_registrar.py` (grupo 4) y el endpoint HTTP, en
`test_pagos_proveedor_api.py` (tarea 5.4).

Escenarios de `specs/proveedores/anulacion-de-pagos/spec.md`: "Anulación de un pago
independiente", "Pago ya anulado", "Motivo de otro ámbito", "Sin permiso de anular",
"Pago de otra organización", "Proveedor inactivo", "Anulación solo con conexión",
"INV-01 — falla antes de la cuenta", "INV-05 — nada se borra", "Doble envío de la
anulación", "Pago de una compra vigente", "El proveedor devuelve el dinero después de
anular la compra" y "Pago ya anulado junto con su compra".

Reglas citadas: PAG-03, CMP-03, CMP-05, CC-01, CC-03, CC-04, CC-05, CC-06, INV-01, INV-05,
INV-06, INV-13, INV-21, TR-06, TR-09, SEG-06, SEG-07, SYN-02, AUD-01, ADR-022 y
`design.md` D1, D2, D5, D10.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import (
    ANULAR_PAGO,
    MOMENTO,
    PERMISOS_DE_ANULACION_DE_PAGO,
    RELOJ,
    Entorno,
)
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.errors import PermisoRequeridoError
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores.domain.errores import (
    MotivoInvalidoError,
    PagoDeCompraVigienteError,
    PagoYaAnuladoError,
    RecursoNoEncontradoError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DEUDA = "152460.00"
"""El saldo que toma como punto de partida el escenario "Anulación de un pago
independiente": una compra a crédito de ese total deja al proveedor debiéndolo (PAG-02)."""

IMPORTE_DEL_PAGO = "52460.00"
"""El pago del mismo escenario: deja el saldo en `"100000.00"` y la anulación lo
devuelve a `"152460.00"`."""


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_ANULACION_DE_PAGO)


def _pago_independiente(entorno: Entorno, *, importe: str = IMPORTE_DEL_PAGO) -> UUID:
    """Una compra a crédito que deja al proveedor debiendo `DEUDA` y, encima, un pago
    independiente de `importe`: el escenario "Anulación de un pago independiente"."""
    assert entorno.deuda(DEUDA) == Decimal(DEUDA)
    entorno.pagar_a_proveedor(
        entorno.contenido_pago(
            importe=importe, medios=entorno.pagar((entorno.efectivo_id, importe, None))
        )
    )
    (pago,) = entorno.pagos()
    return pago.id


def _cuenta(entorno: Entorno) -> list[tuple[str, str, Decimal]]:
    return sorted((m.tipo, m.sentido, m.importe) for m in entorno.movimientos_de_cuenta())


def _movimientos_de_anulacion(entorno: Entorno) -> list[tuple[str, UUID]]:
    """`(origen_tipo, origen_id)` de los movimientos `ANULACION_PAGO`, que deben apuntar al
    pago (CC-01: la operación origen del movimiento es el pago)."""
    return [
        (m.origen_tipo, m.origen_id)
        for m in entorno.movimientos_de_cuenta()
        if m.tipo == "ANULACION_PAGO"
    ]


# --- anulación de un pago independiente (PAG-03, CC-03, CC-04) -----------------------------


def test_anular_un_pago_independiente_devuelve_el_saldo_y_deja_el_pago_anulada(
    entorno: Entorno,
) -> None:
    """Escenario "Anulación de un pago independiente": el pago queda `ANULADA` con motivo,
    usuario y momento, la cuenta tiene `ANULACION_PAGO` `AUMENTA` del importe del pago y
    el saldo vuelve al que había antes de pagarlo."""
    pago_id = _pago_independiente(entorno)
    assert entorno.saldo_de_cuenta() == Decimal("100000.00")

    comando = entorno.anular_pago(pago_id)

    pago = entorno.pago(pago_id)
    assert pago.estado == "ANULADA"
    assert pago.anulacion_motivo_id == entorno.motivo_pago_id
    assert pago.anulado_por_id == entorno.usuario_id
    assert pago.anulado_en == MOMENTO
    assert _cuenta(entorno) == [
        ("ANULACION_PAGO", "AUMENTA", Decimal(IMPORTE_DEL_PAGO)),
        ("COMPRA", "AUMENTA", Decimal(DEUDA)),
        ("PAGO", "REDUCE", Decimal(IMPORTE_DEL_PAGO)),
    ]
    assert _movimientos_de_anulacion(entorno) == [("ANULACION_PAGO", pago_id)]
    assert entorno.saldo_de_cuenta() == Decimal(DEUDA)
    assert comando.resultado == {
        "pago_id": str(pago_id),
        "estado": "ANULADA",
        "saldo": DEUDA,
    }


def test_anular_un_pago_independiente_no_toca_nada_mas_inv_05_tr_06(entorno: Entorno) -> None:
    """Escenario "INV-05 — nada se borra": el pago, sus medios y el movimiento `PAGO`
    original siguen intactos (CC-06: los movimientos no se editan ni se borran)."""
    pago_id = _pago_independiente(entorno)

    entorno.anular_pago(pago_id)

    assert len(entorno.pagos()) == 1
    assert len(entorno.medios_de_pago()) == 1
    original = [m for m in entorno.movimientos_de_cuenta() if m.tipo == "PAGO"]
    assert len(original) == 1
    assert (original[0].sentido, original[0].importe) == ("REDUCE", Decimal(IMPORTE_DEL_PAGO))
    assert len(entorno.movimientos_de_cuenta()) == 3


# --- pago ya anulado (PAG-03) ---------------------------------------------------------------


def test_anular_un_pago_ya_anulado_es_pago_ya_anulado_sin_segundo_movimiento(
    entorno: Entorno,
) -> None:
    """Escenario "Pago ya anulado": con otro `Operation-Id` se rechaza con
    `PAGO_YA_ANULADO` y no se registra un segundo `ANULACION_PAGO`."""
    pago_id = _pago_independiente(entorno)
    entorno.anular_pago(pago_id)
    cuenta = len(entorno.movimientos_de_cuenta())

    with pytest.raises(PagoYaAnuladoError) as error:
        entorno.anular_pago(pago_id)

    assert error.value.codigo == "PAGO_YA_ANULADO"
    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert len(entorno.movimientos_de_cuenta()) == cuenta
    assert len(_movimientos_de_anulacion(entorno)) == 1


# --- el motivo (PAG-03, TR-09, D1) --------------------------------------------------------


def test_motivo_de_otro_ambito_es_motivo_invalido(entorno: Entorno) -> None:
    """Escenario "Motivo de otro ámbito": un motivo de `ANULACION_COMPRA` no sirve para
    anular un pago (D1: la anulación de un pago solo admite `ANULACION_PAGO`)."""
    pago_id = _pago_independiente(entorno)

    with pytest.raises(MotivoInvalidoError) as error:
        entorno.anular_pago(pago_id, motivo_id=entorno.motivo_id)

    assert error.value.codigo == "MOTIVO_INVALIDO"
    assert error.value.status_http == 422
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 2


def test_motivo_inactivo_es_motivo_invalido(entorno: Entorno) -> None:
    pago_id = _pago_independiente(entorno)
    entorno.desactivar_motivo(entorno.motivo_pago_id)

    with pytest.raises(MotivoInvalidoError):
        entorno.anular_pago(pago_id)

    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"


def test_motivo_de_otra_organizacion_responde_404(entorno: Entorno, db_session: Session) -> None:
    """El motivo ajeno no existe en esta organización: 404, no `MOTIVO_INVALIDO`
    (INV-21, SEG-07)."""
    pago_id = _pago_independiente(entorno)
    ajena = Entorno(db_session, permisos=PERMISOS_DE_ANULACION_DE_PAGO)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.anular_pago(pago_id, motivo_id=ajena.motivo_pago_id)

    assert error.value.status_http == 404
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"


# --- permiso y aislamiento (SEG-06, SEG-07, INV-21) ---------------------------------------


def test_sin_anular_pago_proveedor_se_rechaza_con_403_y_el_pago_sigue_confirmada(
    db_session: Session,
) -> None:
    """Escenario "Sin permiso de anular": `REGISTRAR_PAGO_PROVEEDOR` no alcanza, hace
    falta `ANULAR_PAGO_PROVEEDOR` (PAG-03, `01` §19)."""
    entorno = Entorno(
        db_session, permisos=frozenset({"REGISTRAR_COMPRA", "REGISTRAR_PAGO_PROVEEDOR"})
    )
    pago_id = _pago_independiente(entorno)
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.anular_pago(pago_id, operation_id=operation_id)

    assert error.value.status_http == 403
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 2
    assert entorno.auditorias(operation_id) == 0


def test_anular_un_pago_de_otra_organizacion_responde_404_inv_21(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Pago de otra organización": en los dos sentidos -- ni el usuario de A
    anula el pago de B, ni el de B el de A -- y el pago ajeno no cambia (INV-21, SEG-07)."""
    ajena = Entorno(db_session, permisos=PERMISOS_DE_ANULACION_DE_PAGO)
    pago_ajeno = _pago_independiente(ajena)
    propio = _pago_independiente(entorno)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.anular_pago(pago_ajeno)
    con_pago_ajeno = error.value

    with pytest.raises(RecursoNoEncontradoError) as error:
        ajena.anular_pago(propio)
    con_pago_propio = error.value

    assert con_pago_ajeno.status_http == 404
    assert con_pago_propio.status_http == 404
    ajena.sesion.rollback()
    assert ajena.pago(pago_ajeno).estado == "CONFIRMADA"
    assert entorno.pago(propio).estado == "CONFIRMADA"


def test_anular_un_pago_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.anular_pago(uuid4())

    assert error.value.status_http == 404


# --- proveedor inactivo (D5) ---------------------------------------------------------------


def test_se_puede_anular_el_pago_de_un_proveedor_inactivo_d5(entorno: Entorno) -> None:
    """Escenario "Proveedor inactivo": la anulación se admite aunque el proveedor se haya
    desactivado después (`design.md` D5, opción A)."""
    pago_id = _pago_independiente(entorno)
    entorno.desactivar_proveedor()

    entorno.anular_pago(pago_id)

    assert entorno.pago(pago_id).estado == "ANULADA"
    assert _movimientos_de_anulacion(entorno) == [("ANULACION_PAGO", pago_id)]
    assert entorno.saldo_de_cuenta() == Decimal(DEUDA)


# --- modo, idempotencia y auditoría (`02` §6.5, INV-06, AUD-01) ----------------------------


def test_la_anulacion_del_pago_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Anulación solo con conexión": un lote `OFFLINE` la rechaza sin dejar
    ningún efecto (`02` §6.5)."""
    pago_id = _pago_independiente(entorno)
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ANULAR_PAGO,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"pago_id": str(pago_id), "motivo_id": str(entorno.motivo_pago_id)},
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
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 2


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica_la_anulacion(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío de la anulación" (INV-06, SYN-02)."""
    pago_id = _pago_independiente(entorno)
    operation_id = uuid4()

    primero = entorno.anular_pago(pago_id, operation_id=operation_id)
    segundo = entorno.anular_pago(pago_id, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_movimientos_de_anulacion(entorno)) == 1
    assert entorno.saldo_de_cuenta() == Decimal(DEUDA)
    assert entorno.auditorias(operation_id) == 1


def test_la_anulacion_deja_una_sola_auditoria(entorno: Entorno) -> None:
    """Escenario "Auditoría de la anulación" (AUD-01, AUD-02, ADR-022)."""
    pago_id = _pago_independiente(entorno)
    operation_id = uuid4()

    entorno.anular_pago(pago_id, operation_id=operation_id)

    assert entorno.auditorias(operation_id) == 1


def test_el_contenido_no_puede_traer_la_organizacion(entorno: Entorno) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token, no del cuerpo del comando."""
    from app.commands.errores import ContenidoDeComandoInvalidoError

    pago_id = _pago_independiente(entorno)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.anular_pago(pago_id, organizacion_id=str(uuid4()))

    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"


# --- invariante de libro (INV-13, PAG-03) ---------------------------------------------------


def test_inv13_el_saldo_materializado_coincide_con_el_libro_tras_registrar_y_anular(
    entorno: Entorno,
) -> None:
    """Escenario "Propiedad — registrar y anular deja el saldo como estaba" (INV-13,
    PAG-03): sin movimientos intermedios, el saldo vuelve al inicial."""
    pago_id = _pago_independiente(entorno)

    entorno.anular_pago(pago_id)

    libro = sum(
        (
            movimiento.importe if movimiento.sentido == "AUMENTA" else -movimiento.importe
            for movimiento in entorno.movimientos_de_cuenta()
        ),
        Decimal("0.00"),
    )
    assert entorno.saldo_de_cuenta() == libro == Decimal(DEUDA)


# --- pago de una compra de contado (`design.md` D2, CMP-03, CMP-05) ------------------------

TOTAL_DEL_CONTADO = "152460.00"


def _contado(entorno: Entorno) -> tuple[UUID, UUID]:
    """Una compra de contado de `TOTAL_DEL_CONTADO` con su pago de contado, y el id de esa
    compra (CMP-03: la compra de contado siempre nace con su pago)."""
    entorno.confirmar_contado(
        (entorno.efectivo_id, "100000.00", None),
        (entorno.transferencia_id, "52460.00", "0042"),
    )
    (compra,) = entorno.compras()
    (pago,) = entorno.pagos()
    return compra.id, pago.id


def test_el_pago_de_una_compra_confirmada_es_pago_de_compra_vigiente_d2(entorno: Entorno) -> None:
    """Escenario "Pago de una compra vigente" (D2, CMP-05): el pago de una compra
    `CONFIRMADA` no se anula por separado, se anula junto con la compra."""
    _compra_id, pago_id = _contado(entorno)

    with pytest.raises(PagoDeCompraVigienteError) as error:
        entorno.anular_pago(pago_id)

    assert error.value.codigo == "PAGO_DE_COMPRA_VIGENTE"
    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"
    assert entorno.compras()[0].estado == "CONFIRMADA"
    assert len(entorno.movimientos_de_cuenta()) == 2


def test_anular_el_pago_tras_anular_la_compra_sin_devolver_el_pago_deja_el_saldo_en_cero(
    entorno: Entorno,
) -> None:
    """Escenario "El proveedor devuelve el dinero después de anular la compra" (D2): la
    compra se anuló con `devuelve_pago = false`, así que su pago sigue `CONFIRMADA` con el
    saldo a favor de la organización; anularlo por separado lo devuelve a `"0.00"`."""
    compra_id, pago_id = _contado(entorno)
    entorno.anular(compra_id, devuelve_pago=False)
    assert entorno.saldo_de_cuenta() == Decimal("-152460.00")

    comando = entorno.anular_pago(pago_id)

    pago = entorno.pago(pago_id)
    assert pago.estado == "ANULADA"
    assert pago.anulacion_motivo_id == entorno.motivo_pago_id
    assert pago.anulado_por_id == entorno.usuario_id
    assert pago.anulado_en == MOMENTO
    assert _movimientos_de_anulacion(entorno) == [("ANULACION_PAGO", pago_id)]
    assert entorno.saldo_de_cuenta() == Decimal("0.00")
    assert comando.resultado == {
        "pago_id": str(pago_id),
        "estado": "ANULADA",
        "saldo": "0.00",
    }


def test_el_pago_ya_anulado_con_su_compra_es_pago_ya_anulado_d2(entorno: Entorno) -> None:
    """Escenario "Pago ya anulado junto con su compra" (CMP-05, PAG-03): con
    `devuelve_pago = true` la compra ya anuló su pago, así que anularlo otra vez se rechaza
    y no agrega un segundo `ANULACION_PAGO`."""
    compra_id, pago_id = _contado(entorno)
    entorno.anular(compra_id, devuelve_pago=True)
    cuenta = len(entorno.movimientos_de_cuenta())

    with pytest.raises(PagoYaAnuladoError) as error:
        entorno.anular_pago(pago_id)

    assert error.value.codigo == "PAGO_YA_ANULADO"
    entorno.sesion.rollback()
    assert len(entorno.movimientos_de_cuenta()) == cuenta
    assert len(_movimientos_de_anulacion(entorno)) == 1
    assert entorno.saldo_de_cuenta() == Decimal("0.00")


# --- INV-01: atomicidad (`02` §5.2) --------------------------------------------------------


def test_inv01_una_falla_despues_de_marcar_el_pago_y_antes_del_movimiento_no_deja_efectos(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "INV-01 — falla antes de la cuenta".

    La falla se inyecta en el punto exacto que nombra la spec: con el pago YA marcado
    `ANULADA` en la transacción y todavía sin el movimiento de cuenta. Al virar atrás, el
    pago sigue `CONFIRMADA`: la transacción la maneja el bus (`02` §5.2), así que la marca
    se revierte con ella. No queda movimiento ni cambio de saldo, ni auditoría."""
    pago_id = _pago_independiente(entorno)
    marcados: list[UUID] = []
    original_marcar = proveedores_repository.marcar_pago_anulado
    original_registrar = cuentas_service.registrar_movimiento

    def marcar_y_contar(*args: Any, **kwargs: Any) -> Any:
        original_marcar(*args, **kwargs)
        # El `flush` asegura que el UPDATE de estado llegó a la base: la falla inyectada
        # tiene que caer DESPUÉS de la marca, no antes.
        entorno.sesion.flush()
        marcados.append(kwargs["pago"].id)

    def falla(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("tipo") == "ANULACION_PAGO":
            raise RuntimeError("falla inyectada entre la marca del pago y el movimiento")
        return original_registrar(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(proveedores_repository, "marcar_pago_anulado", marcar_y_contar)
    monkeypatch.setattr(cuentas_service, "registrar_movimiento", falla)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.anular_pago(pago_id, operation_id=operation_id)

    assert marcados == [pago_id], "la falla tiene que caer después de marcar el pago"
    entorno.sesion.rollback()
    assert entorno.pago(pago_id).estado == "CONFIRMADA"
    assert entorno.pago(pago_id).anulacion_motivo_id is None
    assert entorno.pago(pago_id).anulado_en is None
    assert len(entorno.movimientos_de_cuenta()) == 2
    assert _movimientos_de_anulacion(entorno) == []
    assert entorno.saldo_de_cuenta() == Decimal("100000.00")
    assert entorno.auditorias(operation_id) == 0


# --- INV-05: nada se borra ni se edita (`02` §12, TR-06) ----------------------------------


def test_inv05_app_runtime_no_puede_borrar_ni_editar_el_pago_tras_anularlo(
    app_runtime_engine: Engine,
) -> None:
    """Escenario "INV-05 — nada se borra", en los dos frentes.

    El privilegio lo decide la base, no el código: después de anular, `app_runtime` sigue
    sin `DELETE` sobre `pago_proveedor` ni `pago_proveedor_medio`, y sin `UPDATE` de sus
    importes. Por eso la anulación solo puede ser un `UPDATE` de las columnas de estado y
    anulación (`TABLAS_MUTABLES` de la migración) más un movimiento nuevo en el libro."""
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM pago_proveedor"))
    assert "permission denied" in str(error.value)

    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM pago_proveedor_medio"))
    assert "permission denied" in str(error.value)

    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("UPDATE pago_proveedor SET importe = 1"))
    assert "permission denied" in str(error.value)

    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("UPDATE pago_proveedor_medio SET importe = 1"))
    assert "permission denied" in str(error.value)
