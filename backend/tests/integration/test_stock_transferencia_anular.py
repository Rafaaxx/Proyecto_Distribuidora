"""Change 14, tareas 9.3 y 9.5: `STOCK_TRANSFERENCIA_ANULAR` v1 por el bus contra PostgreSQL
real (spec `stock/transferencias`, requisitos "Anular una transferencia", "Quién puede anular
una transferencia", "La anulación respeta el stock y los inactivos" y "se audita con su
motivo"; `design.md` D5, D5.1, D5.2, D5.4, D10).

La cobertura por HTTP es de `test_stock_transferencias_api.py`.

Reglas citadas: STK-05, STK-07, TR-06, TR-09, CST-12, CST-13, CAT-05, SEG-06, SYN-02, SYN-07,
INV-01, INV-05, INV-06, INV-12, INV-15, INV-21, AUD-02.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from anulaciones_utiles import (
    ADMINISTRACION,
    ANULAR_TRANSFERENCIA,
    MOMENTO,
    RELOJ,
    TRANSFERIR,
    VENDEDOR,
    Entorno,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, desactivar_producto_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    MotivoInvalidoError,
    ProductoInactivoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    TransferenciaYaAnuladaError,
    UbicacionInactivaError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _con_promedio_de_hoy_en_1100(entorno: Entorno) -> None:
    """Una compra de 120 a 1150 en otro depósito lleva el promedio de Vino A de 1050 a 1100."""
    entorno.compra(entorno.vino_id, 120, "1150", entorno.otro_deposito_id)
    assert entorno.promedio(entorno.vino_id) == Decimal("1100.000000")


# --- catálogo --------------------------------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5."""
    declarado = catalogo_bus.tipo_declarado(ANULAR_TRANSFERENCIA)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(ANULAR_TRANSFERENCIA, 1).tipo == ANULAR_TRANSFERENCIA


# --- escenarios felices ----------------------------------------------------------------------


def test_anular_una_transferencia_propia_mal_cargada(db_session: Session) -> None:
    """Escenario "Anular una transferencia mal cargada" (TR-06, INV-15, CST-12): inversos al
    costo original aunque el promedio de hoy sea otro; stock total y promedio sin cambios."""
    entorno = Entorno(db_session, permisos=VENDEDOR)
    marta = entorno.admin
    transferencia_id = entorno.transferir([(entorno.vino_id, 60)], usuario=marta)
    _con_promedio_de_hoy_en_1100(entorno)
    stock_total, historia = entorno.stock_total(entorno.vino_id), entorno.historia_de_costo()

    comando = entorno.anular_transferencia(transferencia_id, usuario=marta)

    assert comando.estado == "ACEPTADO"
    salida, entrada = entorno.movimientos("ANULACION_TRANSFERENCIA")
    assert (salida.tipo, salida.ubicacion_id, salida.cantidad_base) == (
        "TRANSFERENCIA_SALIDA",
        entorno.camioneta_id,
        -60,
    )
    assert (entrada.tipo, entrada.ubicacion_id, entrada.cantidad_base) == (
        "TRANSFERENCIA_ENTRADA",
        entorno.deposito_id,
        60,
    )
    assert salida.costo_unitario == entrada.costo_unitario == Decimal("1050.000000")
    assert salida.origen_id == entrada.origen_id == transferencia_id
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 0
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.stock_total(entorno.vino_id) == stock_total
    assert entorno.promedio(entorno.vino_id) == Decimal("1100.000000")
    assert entorno.historia_de_costo() == historia
    cabecera = entorno.transferencia(transferencia_id)
    assert cabecera.estado == "ANULADA"
    assert cabecera.anulacion_motivo_id == entorno.error_de_carga_id
    assert cabecera.anulada_por_id == marta.id
    assert cabecera.anulada_en == MOMENTO


def test_el_resultado_trae_la_operacion_anulada_y_los_saldos_resultantes(
    entorno: Entorno,
) -> None:
    transferencia_id = entorno.transferir([(entorno.vino_id, 60)])

    comando = entorno.anular_transferencia(transferencia_id)

    assert comando.resultado is not None
    assert comando.resultado["estado"] == "ANULADA"
    assert comando.resultado["transferencia_id"] == str(transferencia_id)
    assert comando.resultado["anulacion"] == {
        "motivo_id": str(entorno.error_de_carga_id),
        "anulada_en": MOMENTO.isoformat(),
        "anulada_por_id": str(entorno.admin.id),
    }
    assert comando.resultado["lineas"] == [
        {
            "producto_id": str(entorno.vino_id),
            "cantidad_base": 60,
            "saldo_origen": 120,
            "saldo_destino": 0,
        }
    ]
    assert comando.resultado["observaciones"] == []
    assert "costo" not in str(comando.resultado)


def test_cada_inverso_repite_el_costo_de_su_propia_linea(entorno: Entorno) -> None:
    """Varias líneas con costos distintos (1050 y 400), en el orden de las líneas."""
    transferencia_id = entorno.transferir([(entorno.agua_id, 10), (entorno.vino_id, 24)])
    entorno.compra(entorno.agua_id, 10, "900", entorno.otro_deposito_id)

    entorno.anular_transferencia(transferencia_id)

    inversos = entorno.movimientos("ANULACION_TRANSFERENCIA")
    assert [(m.producto_id, m.cantidad_base, m.costo_unitario) for m in inversos] == [
        (entorno.agua_id, -10, Decimal("400.000000")),
        (entorno.agua_id, 10, Decimal("400.000000")),
        (entorno.vino_id, -24, Decimal("1050.000000")),
        (entorno.vino_id, 24, Decimal("1050.000000")),
    ]
    assert entorno.stock_total(entorno.vino_id) == 120
    assert entorno.saldo(entorno.agua_id, entorno.camioneta_id) == 0


def test_el_inverso_de_un_movimiento_sin_costo_queda_nulo(db_session: Session) -> None:
    """D3: una transferencia de un producto sin promedio (solo con stock negativo) guarda
    costo nulo; su anulación también."""
    entorno = Entorno(db_session)
    sin_costo = crear_producto_sql(db_session, entorno.org, nombre="Agua 1500")
    db_session.commit()
    transferencia_id = entorno.transferir([(sin_costo, 5)])

    entorno.anular_transferencia(transferencia_id)

    assert [m.costo_unitario for m in entorno.movimientos("ANULACION_TRANSFERENCIA")] == [
        None,
        None,
    ]
    assert entorno.saldo(sin_costo, entorno.deposito_id) == 0


# --- segunda anulación, motivo, aislamiento --------------------------------------------------


def test_segunda_anulacion_es_transferencia_ya_anulada_y_no_escribe_nada(
    entorno: Entorno,
) -> None:
    transferencia_id = entorno.transferir()
    entorno.anular_transferencia(transferencia_id)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(TransferenciaYaAnuladaError):
        entorno.anular_transferencia(transferencia_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.transferencia(transferencia_id).estado == "ANULADA"


def test_motivo_de_otro_ambito_o_inactivo_es_motivo_invalido_sin_efectos(
    entorno: Entorno,
) -> None:
    transferencia_id = entorno.transferir()
    movimientos = entorno.total_de_movimientos()
    inactivo = entorno.motivo("ANULACION_TRANSFERENCIA", activo=False)

    for motivo_id in (entorno.motivo_ajuste_id, entorno.error_de_carga_ajuste_id, inactivo):
        with pytest.raises(MotivoInvalidoError):
            entorno.anular_transferencia(transferencia_id, motivo_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


def test_motivo_de_otra_organizacion_o_inexistente_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session)
    transferencia_id = entorno.transferir()

    for motivo_id in (ajena.error_de_carga_id, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.anular_transferencia(transferencia_id, motivo_id)

    entorno.sesion.rollback()
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


def test_inv21_la_transferencia_de_otra_organizacion_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Transferencia de otra organización": igual que un id inexistente."""
    ajena = Entorno(db_session)
    de_la_otra = ajena.transferir()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_transferencia(de_la_otra)
    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_transferencia(uuid4())

    db_session.rollback()
    assert ajena.transferencia(de_la_otra).estado == "CONFIRMADA"
    assert ajena.saldo(ajena.vino_id, ajena.camioneta_id) == 60


# --- quién puede anular (D5 punto 5, D5.4) ---------------------------------------------------


def test_un_vendedor_no_anula_la_transferencia_de_otro_403(entorno: Entorno) -> None:
    """Escenario "Vendedor anula la transferencia de otro" (SEG-06)."""
    marta = entorno.usuario(VENDEDOR)
    pedro = entorno.usuario(VENDEDOR)
    transferencia_id = entorno.transferir(usuario=marta)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.anular_transferencia(transferencia_id, usuario=pedro)

    assert error.value.status_http == 403
    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


def test_administracion_anula_la_transferencia_de_otro_y_queda_su_nombre(
    entorno: Entorno,
) -> None:
    """Escenario "Administración anula la transferencia de otro" (`01` §19)."""
    marta = entorno.usuario(VENDEDOR)
    administracion = entorno.usuario(ADMINISTRACION)
    transferencia_id = entorno.transferir(usuario=marta)

    comando = entorno.anular_transferencia(transferencia_id, usuario=administracion)

    assert comando.estado == "ACEPTADO"
    cabecera = entorno.transferencia(transferencia_id)
    assert (cabecera.usuario_id, cabecera.anulada_por_id) == (marta.id, administracion.id)


def test_sin_transferir_stock_responde_403_aunque_tenga_anular_transferencia(
    entorno: Entorno,
) -> None:
    """D5.4: `ANULAR_TRANSFERENCIA` solo agrega alcance; `TRANSFERIR_STOCK` es necesario."""
    transferencia_id = entorno.transferir()
    auditor = entorno.usuario(frozenset({"ANULAR_TRANSFERENCIA"}))
    sin_nada = entorno.usuario(frozenset({"AJUSTAR_STOCK"}))

    for usuario in (auditor, sin_nada):
        operation_id = uuid4()
        with pytest.raises(PermisoRequeridoError):
            entorno.anular_transferencia(
                transferencia_id, usuario=usuario, operation_id=operation_id
            )
        assert (
            entorno.sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.operation_id == operation_id)
            )
            == 0
        )

    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


# --- stock negativo e inactivos (D5 puntos 6 y 7) --------------------------------------------


def _camioneta_ya_vendio_10(entorno: Entorno) -> UUID:
    transferencia_id = entorno.transferir([(entorno.vino_id, 60)])
    entorno.venta(entorno.vino_id, 10, entorno.camioneta_id)
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 50
    return transferencia_id


def test_el_destino_ya_vendio_parte_sin_permiso_es_stock_insuficiente(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, permisos=ADMINISTRACION)
    transferencia_id = _camioneta_ya_vendio_10(entorno)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(StockInsuficienteError):
        entorno.anular_transferencia(transferencia_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 50
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


def test_el_destino_ya_vendio_parte_con_permiso_queda_en_menos_10_y_observa(
    entorno: Entorno,
) -> None:
    transferencia_id = _camioneta_ya_vendio_10(entorno)

    comando = entorno.anular_transferencia(transferencia_id)

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == -10
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.transferencia(transferencia_id).estado == "ANULADA"
    observaciones = list(
        entorno.sesion.scalars(
            select(Observacion).where(Observacion.organizacion_id == entorno.org)
        ).all()
    )
    assert [(o.codigo, o.operacion_tipo, o.operacion_id) for o in observaciones] == [
        ("STOCK_NEGATIVO", "TRANSFERENCIA", transferencia_id)
    ]
    assert observaciones[0].detalle == {
        "producto_id": str(entorno.vino_id),
        "ubicacion_id": str(entorno.camioneta_id),
        "saldo": -10,
    }
    assert comando.resultado is not None
    assert comando.resultado["observaciones"] == ["STOCK_NEGATIVO"]


def test_un_producto_desactivado_despues_impide_la_anulacion(entorno: Entorno) -> None:
    transferencia_id = entorno.transferir([(entorno.vino_id, 60)])
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)
    entorno.sesion.commit()

    with pytest.raises(ProductoInactivoError):
        entorno.anular_transferencia(transferencia_id)

    entorno.sesion.rollback()
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 60


@pytest.mark.parametrize("cual", ["origen", "destino"])
def test_una_ubicacion_desactivada_despues_impide_la_anulacion(entorno: Entorno, cual: str) -> None:
    transferencia_id = entorno.transferir([(entorno.vino_id, 60)])
    entorno.venta(entorno.vino_id, 60, entorno.camioneta_id)  # el destino queda en cero
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE id = :u"),
        {"u": entorno.deposito_id if cual == "origen" else entorno.camioneta_id},
    )
    entorno.sesion.commit()

    with pytest.raises(UbicacionInactivaError):
        entorno.anular_transferencia(transferencia_id)

    entorno.sesion.rollback()
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


# --- modo, idempotencia (INV-06) -------------------------------------------------------------


def test_el_lote_rechaza_una_anulacion_enviada_sin_conexion(entorno: Entorno) -> None:
    transferencia_id = entorno.transferir()
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ANULAR_TRANSFERENCIA,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.admin.id,
        dispositivo_id=entorno.admin.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={
            "transferencia_id": str(transferencia_id),
            "motivo_id": str(entorno.error_de_carga_id),
        },
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.admin.id,
        dispositivo_id=entorno.admin.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    entorno.sesion.rollback()
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"


def test_inv06_el_reenvio_devuelve_el_resultado_original_sin_nuevos_movimientos(
    entorno: Entorno,
) -> None:
    transferencia_id = entorno.transferir()
    operation_id = uuid4()

    primero = entorno.anular_transferencia(transferencia_id, operation_id=operation_id)
    movimientos = entorno.total_de_movimientos()
    segundo = entorno.anular_transferencia(transferencia_id, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert entorno.total_de_movimientos() == movimientos


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    transferencia_id = entorno.transferir()
    operation_id = uuid4()
    entorno.anular_transferencia(transferencia_id, operation_id=operation_id)
    otro_motivo = entorno.motivo("ANULACION_TRANSFERENCIA")

    with pytest.raises(ComandoInconsistenteError):
        entorno.anular_transferencia(transferencia_id, otro_motivo, operation_id=operation_id)


def test_el_contenido_no_admite_la_organizacion_ni_campos_de_mas(entorno: Entorno) -> None:
    transferencia_id = entorno.transferir()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(
            ANULAR_TRANSFERENCIA,
            {
                "transferencia_id": str(transferencia_id),
                "motivo_id": str(entorno.error_de_carga_id),
                "organizacion_id": str(uuid4()),
            },
        )


# --- auditoría (AUD-02, D10) -----------------------------------------------------------------


def test_aud02_la_anulacion_deja_una_fila_con_el_motivo_y_la_original_sin_motivo(
    entorno: Entorno,
) -> None:
    """Escenario "Auditoría de la anulación"."""
    operacion_original, operacion_anulacion = uuid4(), uuid4()
    comando = entorno.enviar(
        TRANSFERIR, entorno.contenido_de_transferencia(), operation_id=operacion_original
    )
    assert comando.resultado is not None
    transferencia_id = UUID(str(comando.resultado["transferencia_id"]))

    entorno.anular_transferencia(transferencia_id, operation_id=operacion_anulacion)

    (original,) = entorno.auditorias(operacion_original)
    (anulacion,) = entorno.auditorias(operacion_anulacion)
    assert original.accion == TRANSFERIR
    assert original.motivo_id is None
    assert anulacion.accion == ANULAR_TRANSFERENCIA
    assert anulacion.motivo_id == entorno.error_de_carga_id
    assert anulacion.usuario_id == entorno.admin.id
    assert anulacion.dispositivo_id == entorno.admin.dispositivo_id
    assert anulacion.observacion is None


def test_aud02_el_reenvio_no_escribe_otra_fila_y_la_rechazada_no_deja_motivo(
    entorno: Entorno,
) -> None:
    transferencia_id = entorno.transferir()
    aceptada, rechazada = uuid4(), uuid4()

    entorno.anular_transferencia(transferencia_id, operation_id=aceptada)
    entorno.anular_transferencia(transferencia_id, operation_id=aceptada)
    with pytest.raises(TransferenciaYaAnuladaError):
        entorno.anular_transferencia(transferencia_id, operation_id=rechazada)

    assert len(entorno.auditorias(aceptada)) == 1
    assert entorno.auditorias(rechazada) == []


# --- atomicidad (INV-01) e INV-05 (tarea 9.5) ------------------------------------------------


def test_inv01_una_falla_despues_del_primer_inverso_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla en medio de la anulación": una transferencia de dos líneas, ningún
    inverso, ningún cambio de saldo ni de stock total, la cabecera sigue `CONFIRMADA` y el
    `operation_id` se reintenta."""
    transferencia_id = entorno.transferir([(entorno.vino_id, 24), (entorno.agua_id, 10)])
    movimientos = entorno.total_de_movimientos()
    original = stock_service.repository.insertar_movimiento
    llamadas: list[int] = []

    def insertar_y_fallar(*args: Any, **kwargs: Any) -> Any:
        llamadas.append(1)
        movimiento = original(*args, **kwargs)
        if len(llamadas) == 1:
            raise RuntimeError("falla inyectada después del primer inverso")
        return movimiento

    monkeypatch.setattr(stock_service.repository, "insertar_movimiento", insertar_y_fallar)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.anular_transferencia(transferencia_id, operation_id=operation_id)

    assert llamadas == [1]
    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 24
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 96
    assert entorno.stock_total(entorno.vino_id) == 120
    assert entorno.transferencia(transferencia_id).estado == "CONFIRMADA"
    assert entorno.auditorias(operation_id) == []

    monkeypatch.undo()
    comando = entorno.anular_transferencia(transferencia_id, operation_id=operation_id)
    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.vino_id, entorno.camioneta_id) == 0


def _como_app_runtime(entorno: Entorno, sentencia: str, **parametros: object) -> None:
    with entorno.sesion.begin_nested():
        entorno.sesion.execute(text("SET LOCAL ROLE app_runtime"))
        entorno.sesion.execute(text(sentencia), parametros)


def test_inv05_una_transferencia_anulada_no_vuelve_a_confirmada(entorno: Entorno) -> None:
    """El `UPDATE` del estado es un privilegio de `app_runtime` (D5, D8), pero el `CHECK` de
    coherencia rechaza una cabecera `CONFIRMADA` con los datos de anulación."""
    transferencia_id = entorno.transferir()
    entorno.anular_transferencia(transferencia_id)

    with pytest.raises(IntegrityError, match="ck_transferencia__anulacion_coherente"):
        _como_app_runtime(
            entorno,
            "UPDATE transferencia SET estado = 'CONFIRMADA' WHERE id = :t",
            t=transferencia_id,
        )

    assert entorno.transferencia(transferencia_id).estado == "ANULADA"


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM transferencia WHERE id = :t",
        "DELETE FROM transferencia_linea WHERE transferencia_id = :t",
        "UPDATE transferencia_linea SET cantidad_base = 5 WHERE transferencia_id = :t",
        "UPDATE transferencia SET ubicacion_destino_id = ubicacion_origen_id WHERE id = :t",
        "UPDATE transferencia SET observacion = 'x' WHERE id = :t",
        "UPDATE stock_movimiento SET cantidad_base = 5 WHERE origen_id = :t",
        "DELETE FROM stock_movimiento WHERE origen_id = :t",
    ],
)
def test_inv05_tras_anular_app_runtime_no_toca_lineas_movimientos_ni_otras_columnas(
    entorno: Entorno, sentencia: str
) -> None:
    transferencia_id = entorno.transferir()
    entorno.anular_transferencia(transferencia_id)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(ProgrammingError, match="(?i)permission denied"):
        _como_app_runtime(entorno, sentencia, t=transferencia_id)

    assert len(entorno.lineas_de_transferencia()) == 1
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.transferencia(transferencia_id).estado == "ANULADA"
