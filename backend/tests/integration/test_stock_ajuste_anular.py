"""Change 14, tareas 9.4 y 9.5: `STOCK_AJUSTE_ANULAR` v1 por el bus contra PostgreSQL real (spec
`stock/ajustes-de-stock`, requisitos "Anular un ajuste", "La anulación de un ajuste respeta
el stock y los inactivos" y "se audita con su motivo"; `design.md` D1, D5, D5.1, D5.2, D10).

La cobertura por HTTP es de `test_stock_ajustes_api.py`.

Reglas citadas: STK-05, STK-08, TR-06, TR-09, CST-12, CST-13, CAT-05, SEG-06, SYN-07, INV-01,
INV-05, INV-06, INV-12, INV-21, AUD-01, AUD-02.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from anulaciones_utiles import (
    ADMINISTRACION,
    AJUSTAR,
    ANULAR_AJUSTE,
    MOMENTO,
    RELOJ,
    VENDEDOR,
    Entorno,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import desactivar_producto_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    AjusteYaAnuladoError,
    MotivoInvalidoError,
    ProductoInactivoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    UbicacionInactivaError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- catálogo --------------------------------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5."""
    declarado = catalogo_bus.tipo_declarado(ANULAR_AJUSTE)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(ANULAR_AJUSTE, 1).tipo == ANULAR_AJUSTE


# --- escenarios felices ----------------------------------------------------------------------


def test_anular_una_rotura_cargada_por_otro_usuario(entorno: Entorno) -> None:
    """Escenario "Anular una rotura mal cargada" (TR-06, CST-12, CST-13): el ajuste fue a
    1050 y el promedio de hoy es 1100; el inverso vuelve a 1050 y no cambia el promedio."""
    otro = entorno.usuario(ADMINISTRACION)
    ajuste_id = entorno.ajustar([(entorno.vino_id, -6)], usuario=otro)
    entorno.compra(entorno.vino_id, 114, "1150", entorno.otro_deposito_id)
    assert entorno.promedio(entorno.vino_id) == Decimal("1100.000000")
    historia = entorno.historia_de_costo()
    assert entorno.stock_total(entorno.vino_id) == 228  # 114 + 114

    comando = entorno.anular_ajuste(ajuste_id)

    assert comando.estado == "ACEPTADO"
    (inverso,) = entorno.movimientos("ANULACION_AJUSTE_STOCK")
    assert (inverso.tipo, inverso.cantidad_base, inverso.ubicacion_id) == (
        "AJUSTE",
        6,
        entorno.deposito_id,
    )
    assert inverso.costo_unitario == Decimal("1050.000000")
    assert inverso.motivo_id == entorno.error_de_carga_ajuste_id
    assert inverso.origen_id == ajuste_id
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.stock_total(entorno.vino_id) == 234
    assert entorno.promedio(entorno.vino_id) == Decimal("1100.000000")
    assert entorno.historia_de_costo() == historia
    cabecera = entorno.ajuste(ajuste_id)
    assert cabecera.estado == "ANULADA"
    assert cabecera.anulacion_motivo_id == entorno.error_de_carga_ajuste_id
    assert cabecera.anulado_por_id == entorno.admin.id
    assert cabecera.anulado_en == MOMENTO
    assert cabecera.motivo_id == entorno.motivo_ajuste_id  # el motivo del ajuste no cambia


def test_el_resultado_trae_la_operacion_anulada_y_el_saldo_resultante(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar([(entorno.vino_id, -6)])

    comando = entorno.anular_ajuste(ajuste_id)

    assert comando.resultado is not None
    assert comando.resultado["estado"] == "ANULADA"
    assert comando.resultado["ajuste_id"] == str(ajuste_id)
    assert comando.resultado["motivo_id"] == str(entorno.motivo_ajuste_id)
    assert comando.resultado["anulacion"] == {
        "motivo_id": str(entorno.error_de_carga_ajuste_id),
        "anulado_en": MOMENTO.isoformat(),
        "anulado_por_id": str(entorno.admin.id),
    }
    assert comando.resultado["lineas"] == [
        {"producto_id": str(entorno.vino_id), "cantidad_base": -6, "saldo": 120}
    ]
    assert comando.resultado["observaciones"] == []
    assert "costo" not in str(comando.resultado)


def test_anular_un_conteo_con_signos_mezclados_cada_uno_a_su_costo(entorno: Entorno) -> None:
    """Escenario "Anular un conteo con signos mezclados": Vino A −2 y Agua 500 +1."""
    ajuste_id = entorno.ajustar([(entorno.vino_id, -2), (entorno.agua_id, 1)])

    entorno.anular_ajuste(ajuste_id)

    inversos = entorno.movimientos("ANULACION_AJUSTE_STOCK")
    assert sorted((m.producto_id, m.cantidad_base, m.costo_unitario) for m in inversos) == sorted(
        [
            (entorno.vino_id, 2, Decimal("1050.000000")),
            (entorno.agua_id, -1, Decimal("400.000000")),
        ]
    )
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 40
    assert entorno.stock_total(entorno.agua_id) == 40


def test_un_ajuste_positivo_de_un_producto_que_hoy_no_tiene_promedio_se_anula(
    entorno: Entorno,
) -> None:
    """La regla `PRODUCTO_SIN_COSTO` no se aplica a un inverso (D3, D5.2). El caso se arma
    con una compra anulada que dejó el producto sin promedio: un ajuste +6 a 1050 y, después,
    el promedio vacío."""
    ajuste_id = entorno.ajustar([(entorno.vino_id, 6)])
    entorno.sesion.execute(
        text("UPDATE costo_producto SET costo_promedio = NULL WHERE producto_id = :p"),
        {"p": entorno.vino_id},
    )
    entorno.sesion.commit()
    assert entorno.promedio(entorno.vino_id) is None

    comando = entorno.anular_ajuste(ajuste_id)

    assert comando.estado == "ACEPTADO"
    (inverso,) = entorno.movimientos("ANULACION_AJUSTE_STOCK")
    assert (inverso.cantidad_base, inverso.costo_unitario) == (-6, Decimal("1050.000000"))
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120


# --- segunda anulación, motivo, permisos, aislamiento ----------------------------------------


def test_segunda_anulacion_es_ajuste_ya_anulado_y_no_escribe_nada(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar()
    entorno.anular_ajuste(ajuste_id)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(AjusteYaAnuladoError):
        entorno.anular_ajuste(ajuste_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.ajuste(ajuste_id).estado == "ANULADA"


def test_motivo_de_otro_ambito_o_inactivo_es_motivo_invalido_sin_efectos(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar()
    movimientos = entorno.total_de_movimientos()
    inactivo = entorno.motivo("ANULACION_AJUSTE", activo=False)

    for motivo_id in (entorno.motivo_ajuste_id, entorno.error_de_carga_id, inactivo):
        with pytest.raises(MotivoInvalidoError):
            entorno.anular_ajuste(ajuste_id, motivo_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


def test_motivo_de_otra_organizacion_o_inexistente_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session)
    ajuste_id = entorno.ajustar()

    for motivo_id in (ajena.error_de_carga_ajuste_id, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.anular_ajuste(ajuste_id, motivo_id)

    entorno.sesion.rollback()
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


def test_sin_ajustar_stock_responde_403_aunque_pueda_transferir(entorno: Entorno) -> None:
    """Escenario "Sin permiso": un Vendedor con `TRANSFERIR_STOCK` (SEG-06)."""
    ajuste_id = entorno.ajustar()
    vendedor = entorno.usuario(VENDEDOR)
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.anular_ajuste(ajuste_id, usuario=vendedor, operation_id=operation_id)

    assert error.value.status_http == 403
    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


def test_inv21_el_ajuste_de_otra_organizacion_es_404(entorno: Entorno, db_session: Session) -> None:
    ajena = Entorno(db_session)
    de_la_otra = ajena.ajustar()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_ajuste(de_la_otra)
    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_ajuste(uuid4())

    db_session.rollback()
    assert ajena.ajuste(de_la_otra).estado == "CONFIRMADA"
    assert ajena.saldo(ajena.vino_id, ajena.deposito_id) == 114


# --- stock negativo e inactivos (D5 punto 6 y 7, D1) -----------------------------------------


def _el_stock_de_un_ajuste_positivo_ya_salio(entorno: Entorno) -> UUID:
    """Ajuste de +12 de Vino A en el depósito, que ahora tiene 5 (se ajustó a la baja)."""
    ajuste_id = entorno.ajustar([(entorno.vino_id, 12)])
    entorno.venta(entorno.vino_id, 127, entorno.deposito_id)  # 132 − 127
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 5
    return ajuste_id


def test_el_stock_de_un_ajuste_positivo_ya_salio_sin_permiso_es_stock_insuficiente(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, permisos=ADMINISTRACION)
    ajuste_id = _el_stock_de_un_ajuste_positivo_ya_salio(entorno)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(StockInsuficienteError):
        entorno.anular_ajuste(ajuste_id)

    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 5
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


def test_el_stock_de_un_ajuste_positivo_ya_salio_con_permiso_queda_en_menos_7_y_observa(
    entorno: Entorno,
) -> None:
    ajuste_id = _el_stock_de_un_ajuste_positivo_ya_salio(entorno)

    comando = entorno.anular_ajuste(ajuste_id)

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == -7
    assert entorno.ajuste(ajuste_id).estado == "ANULADA"
    observaciones = list(
        entorno.sesion.scalars(
            select(Observacion).where(Observacion.organizacion_id == entorno.org)
        ).all()
    )
    assert [(o.codigo, o.operacion_tipo, o.operacion_id) for o in observaciones] == [
        ("STOCK_NEGATIVO", "AJUSTE_STOCK", ajuste_id)
    ]
    assert observaciones[0].detalle == {
        "producto_id": str(entorno.vino_id),
        "ubicacion_id": str(entorno.deposito_id),
        "saldo": -7,
    }


def test_un_ajuste_nuevo_sigue_sin_poder_dejar_negativo_con_el_mismo_permiso(
    entorno: Entorno,
) -> None:
    """D1 = B: la excepción es de la anulación y no se extiende al ajuste."""
    with pytest.raises(StockInsuficienteError):
        entorno.ajustar([(entorno.vino_id, -500)])


def test_un_producto_desactivado_despues_impide_la_anulacion(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar([(entorno.vino_id, -6)])
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.vino_id)
    entorno.sesion.commit()

    with pytest.raises(ProductoInactivoError):
        entorno.anular_ajuste(ajuste_id)

    entorno.sesion.rollback()
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114


def test_una_ubicacion_desactivada_despues_impide_la_anulacion(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar([(entorno.vino_id, -6)])
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE id = :u"), {"u": entorno.deposito_id}
    )
    entorno.sesion.commit()

    with pytest.raises(UbicacionInactivaError):
        entorno.anular_ajuste(ajuste_id)

    entorno.sesion.rollback()
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


# --- modo, idempotencia (INV-06) -------------------------------------------------------------


def test_el_lote_rechaza_una_anulacion_enviada_sin_conexion(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar()
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ANULAR_AJUSTE,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.admin.id,
        dispositivo_id=entorno.admin.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={
            "ajuste_id": str(ajuste_id),
            "motivo_id": str(entorno.error_de_carga_ajuste_id),
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
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"


def test_inv06_el_reenvio_devuelve_el_resultado_original_sin_nuevos_movimientos(
    entorno: Entorno,
) -> None:
    ajuste_id = entorno.ajustar()
    operation_id = uuid4()

    primero = entorno.anular_ajuste(ajuste_id, operation_id=operation_id)
    movimientos = entorno.total_de_movimientos()
    segundo = entorno.anular_ajuste(ajuste_id, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert entorno.total_de_movimientos() == movimientos


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar()
    operation_id = uuid4()
    entorno.anular_ajuste(ajuste_id, operation_id=operation_id)
    otro_motivo = entorno.motivo("ANULACION_AJUSTE")

    with pytest.raises(ComandoInconsistenteError):
        entorno.anular_ajuste(ajuste_id, otro_motivo, operation_id=operation_id)


# --- auditoría (AUD-01, AUD-02, D10) ---------------------------------------------------------


def test_aud02_dos_filas_el_ajuste_con_rotura_y_la_anulacion_con_error_de_carga(
    entorno: Entorno,
) -> None:
    """Escenario "Auditoría de la anulación"."""
    operacion_ajuste, operacion_anulacion = uuid4(), uuid4()
    comando = entorno.enviar(AJUSTAR, entorno.contenido_de_ajuste(), operation_id=operacion_ajuste)
    assert comando.resultado is not None
    ajuste_id = UUID(str(comando.resultado["ajuste_id"]))

    entorno.anular_ajuste(ajuste_id, operation_id=operacion_anulacion)

    (del_ajuste,) = entorno.auditorias(operacion_ajuste)
    (de_la_anulacion,) = entorno.auditorias(operacion_anulacion)
    assert (del_ajuste.accion, del_ajuste.motivo_id) == (AJUSTAR, entorno.motivo_ajuste_id)
    assert (de_la_anulacion.accion, de_la_anulacion.motivo_id) == (
        ANULAR_AJUSTE,
        entorno.error_de_carga_ajuste_id,
    )
    assert de_la_anulacion.usuario_id == entorno.admin.id
    assert de_la_anulacion.observacion is None


def test_aud02_el_reenvio_no_escribe_otra_fila_y_la_rechazada_no_deja_motivo(
    entorno: Entorno,
) -> None:
    ajuste_id = entorno.ajustar()
    aceptada, rechazada = uuid4(), uuid4()

    entorno.anular_ajuste(ajuste_id, operation_id=aceptada)
    entorno.anular_ajuste(ajuste_id, operation_id=aceptada)
    with pytest.raises(AjusteYaAnuladoError):
        entorno.anular_ajuste(ajuste_id, operation_id=rechazada)

    assert len(entorno.auditorias(aceptada)) == 1
    assert entorno.auditorias(rechazada) == []


# --- atomicidad (INV-01) e INV-05 (tarea 9.5) ------------------------------------------------


def test_inv01_una_falla_despues_del_primer_inverso_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla en medio de la anulación": un ajuste de dos líneas."""
    ajuste_id = entorno.ajustar([(entorno.vino_id, -6), (entorno.agua_id, -3)])
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
        entorno.anular_ajuste(ajuste_id, operation_id=operation_id)

    assert llamadas == [1]
    entorno.sesion.rollback()
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 114
    assert entorno.saldo(entorno.agua_id, entorno.deposito_id) == 37
    assert entorno.stock_total(entorno.vino_id) == 114
    assert entorno.ajuste(ajuste_id).estado == "CONFIRMADA"
    assert entorno.auditorias(operation_id) == []

    monkeypatch.undo()
    comando = entorno.anular_ajuste(ajuste_id, operation_id=operation_id)
    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(entorno.vino_id, entorno.deposito_id) == 120


def _como_app_runtime(entorno: Entorno, sentencia: str, **parametros: object) -> None:
    with entorno.sesion.begin_nested():
        entorno.sesion.execute(text("SET LOCAL ROLE app_runtime"))
        entorno.sesion.execute(text(sentencia), parametros)


def test_inv05_un_ajuste_anulado_no_vuelve_a_confirmado(entorno: Entorno) -> None:
    ajuste_id = entorno.ajustar()
    entorno.anular_ajuste(ajuste_id)

    with pytest.raises(IntegrityError, match="ck_ajuste_stock__anulacion_coherente"):
        _como_app_runtime(
            entorno, "UPDATE ajuste_stock SET estado = 'CONFIRMADA' WHERE id = :a", a=ajuste_id
        )

    assert entorno.ajuste(ajuste_id).estado == "ANULADA"


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM ajuste_stock WHERE id = :a",
        "DELETE FROM ajuste_stock_linea WHERE ajuste_id = :a",
        "UPDATE ajuste_stock_linea SET cantidad_base = 5 WHERE ajuste_id = :a",
        "UPDATE ajuste_stock SET observacion = 'x' WHERE id = :a",
        "UPDATE ajuste_stock SET motivo_id = anulacion_motivo_id WHERE id = :a",
        "UPDATE stock_movimiento SET cantidad_base = 5 WHERE origen_id = :a",
        "DELETE FROM stock_movimiento WHERE origen_id = :a",
    ],
)
def test_inv05_tras_anular_app_runtime_no_toca_lineas_movimientos_ni_otras_columnas(
    entorno: Entorno, sentencia: str
) -> None:
    ajuste_id = entorno.ajustar()
    entorno.anular_ajuste(ajuste_id)
    movimientos = entorno.total_de_movimientos()

    with pytest.raises(ProgrammingError, match="(?i)permission denied"):
        _como_app_runtime(entorno, sentencia, a=ajuste_id)

    assert len(entorno.lineas_de_ajuste()) == 1
    assert entorno.total_de_movimientos() == movimientos
    assert entorno.ajuste(ajuste_id).estado == "ANULADA"
