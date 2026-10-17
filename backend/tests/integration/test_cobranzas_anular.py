"""Change 17, grupo 9, tarea 9.1: `COBRANZA_ANULAR` v1 por el bus en modo `ONLINE`, contra
PostgreSQL real (spec `cobranzas/anulacion-de-cobranzas`).

Reglas citadas: COB-05, CC-02, CC-04, CC-06, INV-01, INV-05, INV-06, INV-21, SEG-06, SEG-07,
TR-06, TR-09, AUD-01, AUD-02, SYN-04 y `design.md` D6, D7, D15, D18. La concurrencia con commits
reales es de `tests/concurrency` (tarea 16.1); el HTTP, de `test_cobranzas_api.py`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import (
    ANULAR,
    MOMENTO,
    PERMISOS_DE_ANULACION,
    PERMISOS_DE_COBRANZA,
    RELOJ,
    Entorno,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.commands.errores import ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas.domain.errores import (
    CobranzaDeVentaError,
    CobranzaYaAnuladaError,
    MotivoInvalidoError,
    RecursoNoEncontradoError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_ANULACION)


# --- la anulación (COB-05, CC-02, CC-04, CC-06, TR-06, INV-05) ---------------------------


def test_anular_con_motivo_y_observacion_devuelve_el_saldo(entorno: Entorno) -> None:
    """Escenario "Cheque rechazado" (COB-05, CC-02, CC-04): saldo 150000 -> cobranza 20000 ->
    130000 -> anulación -> 150000."""
    cobranza_id = entorno.registrar_y_obtener_id(
        importe="20000.00", medios=entorno.medios((entorno.efectivo_id, "20000.00", None))
    )
    assert entorno.saldo() == Decimal("130000.00")

    comando = entorno.anular(cobranza_id, observacion="cheque 1234 sin fondos")

    assert comando.estado == "ACEPTADO"
    assert entorno.estado_de(cobranza_id) == "ANULADA"
    (anulacion,) = entorno.anulaciones()
    assert anulacion.cobranza_id == cobranza_id
    assert anulacion.motivo_id == entorno.motivo_id
    assert anulacion.observacion == "cheque 1234 sin fondos"
    assert anulacion.usuario_id == entorno.usuario_id
    assert anulacion.dispositivo_id == entorno.dispositivo_id
    (movimiento,) = entorno.movimientos("ANULACION_COBRANZA")
    assert (movimiento.sentido, movimiento.importe) == ("AUMENTA", Decimal("20000.00"))
    assert entorno.saldo() == Decimal("150000.00")
    assert comando.resultado is not None
    assert comando.resultado["saldo"] == "150000.00"


def test_anular_otra_cobranza_de_otro_importe_devuelve_ese_importe(entorno: Entorno) -> None:
    """Triangulación de COB-05: el movimiento lleva el importe completo de ESA cobranza."""
    entorno.registrar()  # 50000.00
    segunda = entorno.registrar_y_obtener_id(
        importe="7500.50", medios=entorno.medios((entorno.efectivo_id, "7500.50", None))
    )
    assert entorno.saldo() == Decimal("92499.50")

    entorno.anular(segunda)

    (movimiento,) = entorno.movimientos("ANULACION_COBRANZA")
    assert movimiento.importe == Decimal("7500.50")
    assert entorno.saldo() == Decimal("100000.00")


def test_la_cobranza_original_sigue_a_la_vista(entorno: Entorno) -> None:
    """Escenario "La cobranza original sigue a la vista" (TR-06, INV-05, CC-06)."""
    cobranza_id = entorno.registrar_y_obtener_id()

    entorno.anular(cobranza_id)

    assert len(entorno.movimientos("COBRANZA")) == 1
    assert len(entorno.movimientos("ANULACION_COBRANZA")) == 1
    assert len(entorno.medios_de_cobranza(cobranza_id)) == 2


def test_la_observacion_es_opcional_y_se_guarda_recortada(entorno: Entorno) -> None:
    primera = entorno.registrar_y_obtener_id()
    segunda = entorno.registrar_y_obtener_id()

    entorno.anular(primera)
    entorno.anular(segunda, observacion="  error de carga  ")

    observaciones = {a.cobranza_id: a.observacion for a in entorno.anulaciones()}
    assert observaciones == {primera: None, segunda: "error de carga"}


# --- permiso (COB-05, SEG-06) -----------------------------------------------------------


def test_sin_permiso_de_anulacion_responde_403_sin_efectos(db_session: Session) -> None:
    """Escenario "Sin permiso" (COB-05, SEG-06)."""
    entorno = Entorno(db_session, permisos=PERMISOS_DE_COBRANZA)
    cobranza_id = entorno.registrar_y_obtener_id()

    with pytest.raises(PermisoRequeridoError):
        entorno.anular(cobranza_id)

    entorno.sesion.rollback()
    assert entorno.estado_de(cobranza_id) == "CONFIRMADA"
    assert entorno.anulaciones() == []
    assert entorno.movimientos("ANULACION_COBRANZA") == []


# --- motivo y observación (COB-05, TR-09, D7) --------------------------------------------


@pytest.mark.parametrize("caso", ["otro_ambito", "inactivo"])
def test_motivo_de_otro_ambito_o_inactivo_es_invalido(entorno: Entorno, caso: str) -> None:
    """Escenario "Motivo de otro ámbito o inactivo" (COB-05, TR-09)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    if caso == "otro_ambito":
        motivo = entorno.crear_motivo("ANULACION_PAGO", "Pago equivocado")
    else:
        motivo = entorno.crear_motivo("ANULACION_COBRANZA", "Viejo", activo=False)
    entorno.sesion.commit()

    with pytest.raises(MotivoInvalidoError) as error:
        entorno.anular(cobranza_id, motivo_id=motivo)

    assert error.value.codigo == "MOTIVO_INVALIDO"
    entorno.sesion.rollback()
    assert entorno.estado_de(cobranza_id) == "CONFIRMADA"
    assert entorno.anulaciones() == []


def test_un_motivo_de_otra_organizacion_responde_404(entorno: Entorno, db_session: Session) -> None:
    """INV-21, SEG-07: el motivo de otra organización no existe para esta."""
    ajeno = Entorno(db_session)
    cobranza_id = entorno.registrar_y_obtener_id()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular(cobranza_id, motivo_id=ajeno.motivo_id)

    entorno.sesion.rollback()
    assert entorno.anulaciones() == []


def test_la_observacion_de_501_caracteres_se_rechaza_y_la_de_500_se_acepta(
    entorno: Entorno,
) -> None:
    """Escenario "Observación demasiado larga" (D7)."""
    cobranza_id = entorno.registrar_y_obtener_id()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.anular(cobranza_id, observacion="a" * 501)
    entorno.sesion.rollback()
    assert entorno.estado_de(cobranza_id) == "CONFIRMADA"

    entorno.anular(cobranza_id, observacion="b" * 500)
    assert entorno.estado_de(cobranza_id) == "ANULADA"


# --- una sola vez y entera (COB-05, D7, INV-05) ------------------------------------------


def test_anular_dos_veces_se_rechaza_y_no_hay_un_segundo_movimiento(entorno: Entorno) -> None:
    """Escenario "Anular dos veces" (COB-05, D7)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.anular(cobranza_id)

    with pytest.raises(CobranzaYaAnuladaError) as error:
        entorno.anular(cobranza_id)

    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert len(entorno.movimientos("ANULACION_COBRANZA")) == 1
    assert len(entorno.anulaciones()) == 1


def test_una_cobranza_de_venta_se_rechaza(entorno: Entorno) -> None:
    """Escenario de `COBRANZA_DE_VENTA` (VTA-22, D7), con la fila sembrada por SQL."""
    cobranza_id = entorno.sembrar_cobranza_de_venta()

    with pytest.raises(CobranzaDeVentaError) as error:
        entorno.anular(cobranza_id)

    assert error.value.codigo == "COBRANZA_DE_VENTA"
    entorno.sesion.rollback()
    assert entorno.estado_de(cobranza_id) == "CONFIRMADA"
    assert entorno.anulaciones() == []


def test_una_cobranza_inexistente_o_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Cobranza de otra organización" (INV-21, SEG-07)."""
    ajeno = Entorno(db_session, permisos=PERMISOS_DE_ANULACION)
    ajena_id = ajeno.registrar_y_obtener_id()

    for cobranza_id in (ajena_id, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            entorno.anular(cobranza_id)
        assert error.value.status_http == 404
        entorno.sesion.rollback()

    assert ajeno.estado_de(ajena_id) == "CONFIRMADA"


def test_se_anula_la_cobranza_de_una_jornada_cerrada(entorno: Entorno) -> None:
    """Escenario "Cobranza de una jornada cerrada" (D7)."""
    entorno.crear_jornada()
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.sesion.execute(
        text(
            "UPDATE jornada SET estado = 'CERRADA', rendida_en = :m, rendida_por_id = :u, "
            "cerrada_en = :m, cerrada_por_id = :u WHERE organizacion_id = :o"
        ),
        {"o": entorno.org, "m": MOMENTO, "u": entorno.usuario_id},
    )
    entorno.sesion.commit()

    entorno.anular(cobranza_id)

    assert entorno.estado_de(cobranza_id) == "ANULADA"
    assert entorno.saldo() == Decimal("150000.00")


def test_se_anula_la_cobranza_de_un_cliente_inactivo(entorno: Entorno) -> None:
    """Escenario "Cliente inactivo" (D7)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.sesion.execute(
        text("UPDATE cliente SET estado = 'INACTIVO' WHERE organizacion_id = :o AND id = :c"),
        {"o": entorno.org, "c": entorno.cliente_id},
    )
    entorno.sesion.commit()

    entorno.anular(cobranza_id)

    assert entorno.estado_de(cobranza_id) == "ANULADA"
    assert entorno.saldo() == Decimal("150000.00")


def test_una_segunda_anulacion_escrita_por_fuera_del_servicio_la_rechaza_la_base(
    entorno: Entorno,
) -> None:
    """Escenario "Una segunda anulación escrita por fuera del servicio" (INV-05, D16)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.anular(cobranza_id)

    with pytest.raises(DBAPIError):
        entorno.sesion.execute(
            text(
                "INSERT INTO cobranza_anulacion (id, organizacion_id, cobranza_id, motivo_id, "
                "operation_id, usuario_id, dispositivo_id, occurred_at, registered_at) "
                "VALUES (:id, :o, :c, :m, :op, :u, :d, :t, :t)"
            ),
            {
                "id": uuid4(),
                "o": entorno.org,
                "c": cobranza_id,
                "m": entorno.motivo_id,
                "op": uuid4(),
                "u": entorno.usuario_id,
                "d": entorno.dispositivo_id,
                "t": MOMENTO,
            },
        )
    entorno.sesion.rollback()


# --- modo, idempotencia y auditoría (02 §6.5, INV-06, AUD-01, AUD-02, SYN-04) -------------


def test_la_anulacion_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Anulación sin conexión": un lote `OFFLINE` la rechaza sin efectos."""
    cobranza_id = entorno.registrar_y_obtener_id()
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ANULAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"cobranza_id": str(cobranza_id), "motivo_id": str(entorno.motivo_id)},
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
    assert entorno.estado_de(cobranza_id) == "CONFIRMADA"
    assert entorno.movimientos("ANULACION_COBRANZA") == []


def test_inv06_el_doble_envio_devuelve_el_resultado_original(entorno: Entorno) -> None:
    """Escenario "Doble envío" (INV-06, SYN-02)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    operation_id = uuid4()

    primero = entorno.anular(cobranza_id, operation_id=operation_id)
    segundo = entorno.anular(cobranza_id, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.movimientos("ANULACION_COBRANZA")) == 1
    assert len(entorno.anulaciones()) == 1
    assert len(entorno.auditoria_de(operation_id)) == 1


def test_aud02_la_anulacion_aceptada_deja_una_fila_con_el_motivo(entorno: Entorno) -> None:
    """Escenario "Fila con motivo" (AUD-01, AUD-02, D15)."""
    cobranza_id = entorno.registrar_y_obtener_id()
    otro_motivo = entorno.crear_motivo("ANULACION_COBRANZA", "Pago rechazado o no acreditado")
    entorno.sesion.commit()
    operation_id = uuid4()

    entorno.anular(cobranza_id, motivo_id=otro_motivo, operation_id=operation_id)

    (fila,) = entorno.auditoria_de(operation_id)
    assert fila.accion == ANULAR
    assert fila.motivo_id == otro_motivo
    assert fila.usuario_id == entorno.usuario_id
    assert fila.dispositivo_id == entorno.dispositivo_id


def test_aud02_syn04_el_rechazo_no_deja_fila_con_motivo(entorno: Entorno) -> None:
    """Escenario "Rechazo sin fila" (AUD-02, SYN-04): `COBRANZA_YA_ANULADA` no deja nada."""
    cobranza_id = entorno.registrar_y_obtener_id()
    entorno.anular(cobranza_id)
    operation_id: UUID = uuid4()

    with pytest.raises(CobranzaYaAnuladaError):
        entorno.anular(cobranza_id, operation_id=operation_id)

    entorno.sesion.rollback()
    assert [f.motivo_id for f in entorno.auditoria_de(operation_id)] == []
