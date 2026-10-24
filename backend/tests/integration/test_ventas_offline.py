"""Tarea 11.2 (change 18a; spec `ventas/confirmacion-de-venta`, requisito "Una venta sin conexión
nunca se rechaza por reglas de negocio", y spec `sync/lote-de-comandos`, requisito
"VENTA_CONFIRMAR se acepta por el lote sin conexión"; `design.md` D1, CRÍTICO, alcance confirmado
por el usuario el 2026-10-20), contra PostgreSQL real y por `procesar_lote`.

- Se rechaza solo lo malformado (`TOTALES_INCONSISTENTES`, `VENTA_SIN_LINEAS`), lo inexistente
  (cliente, producto, presentación, versión, medio) y lo inconsistente (número repetido o de otro
  dispositivo, jornada del sobre ausente o ajena). Sin fila de comando ni efecto; el lote sigue.
- Se acepta con observación sobre la venta: `STOCK_NEGATIVO` por línea (el stock se descuenta
  igual), `CLIENTE_NO_HABILITADO`, `CONSUMIDOR_FINAL_CON_DEUDA`, `LISTA_NO_VIGENTE` (una por venta),
  `VENTA_SIN_COSTO` por línea, `PERMISO_REVOCADO` y `JORNADA_LIBERADA`; `MEDIO_INACTIVO` y
  `REFERENCIA_FALTANTE` sobre su cobranza (como el change 17).
- Un producto o una presentación desactivados después del bootstrap se aceptan sin observación.
- Se congelan la versión, el precio y las unidades que envió el dispositivo.
- Con conexión nada cambia: ni por REST ni por el lote en `ONLINE`.

Reglas citadas: SYN-05, SYN-06, SYN-07, SYN-10, STK-06, RUT-09, INV-06, INV-07, INV-17, VTA-06,
CLI-02, CLI-03, PRC-23, D7 y D10 del change.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import MOMENTO as MOMENTO_DE_LIBERACION
from stock_utiles import crear_ubicacion_sql
from test_ventas_api import JWT_SECRET, URL_VENTAS, Sesion, _con_op
from ventas_confirmar_utiles import (
    MOMENTO_VENTA,
    PERMISOS_DE_SUPERVISOR,
    PERMISOS_DE_VENTA,
    RELOJ_VENTA,
    EntornoVenta,
)

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

HOY_TEMPRANO = datetime(2026, 10, 19, 11, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


# --- armado ---------------------------------------------------------------------------------


def _camioneta(entorno: EntornoVenta, *, stock: int = 48) -> UUID:
    """Una ubicación que requiere toma con `stock` botellas a $1.050 (el stock entra ANTES de que
    la jornada la tome: una ubicación tomada solo la mueve su jornada, STK-09)."""
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", requiere_toma=True
    )
    if stock:
        entorno.comprar(entorno.vino_id, stock, "1050", ubicacion_id=camioneta_id)
    entorno.sesion.commit()
    return camioneta_id


def _item(
    entorno: EntornoVenta,
    contenido: dict[str, Any],
    *,
    modo: str,
    jornada_id: UUID | None,
    operation_id: UUID | None = None,
    occurred_at: datetime = MOMENTO_VENTA,
    secuencia: int = 1,
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="VENTA_CONFIRMAR",
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=occurred_at,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido=contenido,
        jornada_id=jornada_id,
    )


class Ruta:
    """El teléfono de Juan: una camioneta con stock y su jornada (por defecto `ABIERTA`)."""

    def __init__(
        self,
        entorno: EntornoVenta,
        *,
        stock: int = 48,
        estado_jornada: str = "ABIERTA",
        extra: tuple[tuple[UUID, int, str], ...] = (),
    ) -> None:
        self.entorno = entorno
        self.camioneta_id = _camioneta(entorno, stock=stock)
        for producto_id, cantidad, costo in extra:
            entorno.comprar(producto_id, cantidad, costo, ubicacion_id=self.camioneta_id)
        entorno.sesion.commit()
        self.jornada_id = entorno.crear_jornada(
            estado=estado_jornada, ubicacion_id=self.camioneta_id
        )

    def contenido(self, *lineas: dict[str, Any], **cambios: object) -> dict[str, Any]:
        cambios.setdefault("ubicacion_id", None)  # sin conexión la ubicación es la de la jornada
        # Change 18b, D7: sin conexión el `credito` del dispositivo es obligatorio.
        cambios.setdefault("credito", self.entorno.credito_offline())
        return self.entorno.contenido(*lineas, **cambios)

    def item(
        self,
        contenido: dict[str, Any] | None = None,
        *,
        jornada_id: UUID | None | str = "la de Juan",
        **opciones: Any,
    ) -> ItemLote:
        return _item(
            self.entorno,
            contenido if contenido is not None else self.contenido(),
            modo=opciones.pop("modo", "OFFLINE"),
            jornada_id=self.jornada_id if jornada_id == "la de Juan" else jornada_id,  # type: ignore[arg-type]
            **opciones,
        )

    def enviar(
        self, *lineas: dict[str, Any], **cambios: object
    ) -> tuple[ItemLote, sync_service.ResultadoItemLote]:
        item = self.item(self.contenido(*lineas, **cambios))
        return item, lote(self.entorno, item)[item.operation_id]


def lote(entorno: EntornoVenta, *items: ItemLote) -> dict[UUID, sync_service.ResultadoItemLote]:
    resultados = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ_VENTA,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=list(items),
    )
    return {resultado.operation_id: resultado for resultado in resultados}


def _observaciones(entorno: EntornoVenta) -> list[Observacion]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
            .order_by(Observacion.codigo, Observacion.id)
        ).all()
    )


def _codigos(entorno: EntornoVenta) -> list[str]:
    return [observacion.codigo for observacion in _observaciones(entorno)]


def _comandos(entorno: EntornoVenta, operation_id: UUID) -> list[Comando]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


def _rechazada(
    resultado: sync_service.ResultadoItemLote, codigo: str, item: ItemLote, entorno: EntornoVenta
) -> None:
    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", codigo)
    assert _comandos(entorno, item.operation_id) == []


def _sin_efectos(entorno: EntornoVenta, stock: int, ubicacion_id: UUID) -> None:
    """Nada quedó escrito por la venta (INV-01): ni venta, ni cobranza, ni movimientos, ni
    observaciones; el saldo, el stock y el correlativo siguen como estaban."""
    entorno.sesion.rollback()
    assert entorno.ventas() == []
    assert entorno.movimientos_de_stock("VENTA") == []
    assert entorno.movimientos("VENTA") == []
    assert entorno.cobranzas() == []
    assert entorno.stock(ubicacion_id=ubicacion_id) == stock
    assert entorno.saldo() == Decimal("150000.00")
    assert entorno.ultimo_correlativo() == 0
    assert _observaciones(entorno) == []


def _producto_con_precio(
    entorno: EntornoVenta,
    nombre: str,
    precio: str,
    *,
    unidades: int = 12,
    version_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    producto_id, presentacion_id = entorno.crear_producto(nombre, unidades_caja=unidades)
    entorno.poner_precio(version_id or entorno.version_id, producto_id, precio, unidades)
    entorno.sesion.commit()
    return producto_id, presentacion_id


def _linea_de(
    entorno: EntornoVenta, producto_id: UUID, presentacion_id: UUID, **cambios: Any
) -> dict[str, Any]:
    """Dos cajas de 12 a $24.000 la caja (`48000.00`)."""
    return entorno.linea(
        producto_id,
        presentacion_id,
        cambios.pop("cantidad", 2),
        unidades_presentacion=12,
        precio=cambios.pop("precio", "24000.00"),
        unidades_referencia=12,
        **cambios,
    )


# --- la venta común (SYN-05) ------------------------------------------------------------------


def test_syn05_una_venta_offline_sin_nada_que_observar_se_acepta_sin_observaciones(
    entorno: EntornoVenta,
) -> None:
    """Escenario base: Juan vende 15 botellas de la camioneta con su jornada abierta. La venta, su
    stock, su cuenta y el correlativo quedan como en una venta con conexión; el modo es `OFFLINE`
    y la venta lleva la jornada del sobre (D3)."""
    ruta = Ruta(entorno)

    item, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert resultado.resultado is not None and resultado.resultado["venta_id"] == str(venta.id)
    assert venta.modo_confirmacion == "OFFLINE"
    assert (venta.ubicacion_id, venta.jornada_id) == (ruta.camioneta_id, ruta.jornada_id)
    assert (venta.total, venta.operation_id) == (Decimal("31250.00"), item.operation_id)
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.costo_unitario, linea.costo_total) == (
        Decimal("1050.000000"),
        Decimal("15750.00"),
    )
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert entorno.saldo() == Decimal("181250.00")
    assert entorno.ultimo_correlativo() == 1
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id == ruta.jornada_id
    assert _observaciones(entorno) == []


def test_inv17_el_momento_no_se_valida_sin_conexion(entorno: EntornoVenta) -> None:
    """D9 es solo del camino con conexión: una venta de hace 23 horas se acepta."""
    ruta = Ruta(entorno)
    item = ruta.item(occurred_at=datetime(2026, 10, 18, 13, 0, tzinfo=UTC))

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert venta.occurred_at == datetime(2026, 10, 18, 13, 0, tzinfo=UTC)


# --- STOCK_NEGATIVO (STK-06) ------------------------------------------------------------------


def test_stk06_una_venta_offline_sobre_stock_insuficiente_se_acepta_con_stock_negativo(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Negativo sin conexión": Juan vende 8 botellas de una camioneta que, al
    sincronizar, tiene 5: se acepta, el stock queda en -3 y la venta lleva `STOCK_NEGATIVO` (saldo
    -3) aunque no tenga `PERMITIR_STOCK_NEGATIVO`."""
    ruta = Ruta(entorno, stock=5)

    _, resultado = ruta.enviar(entorno.linea(cantidad=8))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "STOCK_NEGATIVO"
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert observacion.detalle == {
        "linea_id": str(linea.id),
        "producto_id": str(entorno.vino_id),
        "ubicacion_id": str(ruta.camioneta_id),
        "saldo_resultante": -3,
    }
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == -3
    assert linea.costo_unitario == Decimal(
        "1050.000000"
    )  # el promedio vigente también sobre negativo


def test_stk06_solo_la_linea_que_deja_negativo_lleva_la_observacion(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: dos líneas, una sobre stock suficiente y otra no: una sola observación, de
    la línea afectada."""
    otro, caja_otro = _producto_con_precio(entorno, "Vino B", "24000.00")
    ruta = Ruta(entorno, stock=5, extra=((otro, 30, "2000"),))

    _, resultado = ruta.enviar(entorno.linea(cantidad=8), _linea_de(entorno, otro, caja_otro))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "STOCK_NEGATIVO"
    assert observacion.detalle is not None
    assert observacion.detalle["producto_id"] == str(entorno.vino_id)
    assert entorno.stock(entorno.vino_id, ruta.camioneta_id) == -3
    assert entorno.stock(otro, ruta.camioneta_id) == 30 - 24  # 2 cajas de 12


# --- CLIENTE_NO_HABILITADO y CONSUMIDOR_FINAL_CON_DEUDA (CLI-02, CLI-03, SYN-05) -------------


@pytest.mark.parametrize("estado", ["INACTIVO", "SUSPENDIDO"])
def test_syn05_un_cliente_no_habilitado_se_acepta_con_cliente_no_habilitado(
    entorno: EntornoVenta, estado: str
) -> None:
    """Escenario "Cliente no habilitado sin conexión": inactivo, o suspendido sin
    `VENDER_CLIENTE_SUSPENDIDO`, se acepta con la observación."""
    entorno.actualizar_cliente(entorno.cliente_id, estado=estado)
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "CLIENTE_NO_HABILITADO"
    assert observacion.detalle == {"cliente_id": str(entorno.cliente_id), "estado": estado}
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    assert entorno.saldo() == Decimal("181250.00")


def test_cli02_un_suspendido_con_permiso_se_acepta_sin_observacion(db_session: Session) -> None:
    """Triangulación: con `VENDER_CLIENTE_SUSPENDIDO` (permisos vigentes al sincronizar) no hay
    nada que observar."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []


def _consumidor_final(entorno: EntornoVenta, *, estado: str = "ACTIVO") -> str:
    consumidor = entorno.crear_cliente(
        nombre="Consumidor final", es_consumidor_final=True, estado=estado
    )
    entorno.sesion.commit()
    return str(consumidor)


@pytest.mark.parametrize("pagado", ["30000.00", None])
def test_cli03_el_consumidor_final_con_cobranza_distinta_del_total_queda_con_deuda(
    entorno: EntornoVenta, pagado: str | None
) -> None:
    """Escenario "Consumidor final con deuda sin conexión" (decisión del 2026-10-19): $31.250,00
    con $30.000,00 en efectivo, o sin cobranza, se acepta con `CONSUMIDOR_FINAL_CON_DEUDA` y no
    con `CLIENTE_NO_HABILITADO`; la venta y la cobranza quedan como las envió el dispositivo."""
    consumidor = _consumidor_final(entorno)
    ruta = Ruta(entorno)
    cobranza = None if pagado is None else entorno.cobranza((entorno.efectivo_id, pagado, None))

    _, resultado = ruta.enviar(cliente_id=consumidor, cobranza=cobranza)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "CONSUMIDOR_FINAL_CON_DEUDA"
    assert observacion.detalle == {
        "cliente_id": consumidor,
        "total": "31250.00",
        "cobranza": pagado,
    }
    assert entorno.saldo(UUID(consumidor)) == Decimal("31250.00") - Decimal(pagado or "0.00")


def test_cli03_el_consumidor_final_de_contado_se_acepta_sin_observacion(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: la cobranza igual al total no observa."""
    consumidor = _consumidor_final(entorno)
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(
        cliente_id=consumidor, cobranza=entorno.cobranza((entorno.efectivo_id, "31250.00", None))
    )

    assert resultado.estado == "ACEPTADO"
    assert entorno.saldo(UUID(consumidor)) == Decimal("0.00")


def test_cli03_si_ademas_no_esta_habilitado_solo_cliente_no_habilitado(
    entorno: EntornoVenta,
) -> None:
    """Un consumidor final inactivo con deuda: gana `CLIENTE_NO_HABILITADO`, sin la otra."""
    consumidor = _consumidor_final(entorno, estado="INACTIVO")
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(cliente_id=consumidor)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _codigos(entorno) == ["CLIENTE_NO_HABILITADO"]


# --- PERMISO_REVOCADO (SYN-10) ----------------------------------------------------------------


def test_syn10_un_vendedor_sin_vender_se_acepta_con_permiso_revocado_sobre_la_venta(
    db_session: Session,
) -> None:
    """Escenario "Venta sin conexión de un vendedor sin el permiso": a Juan le quitaron `VENDER`
    después de abrir su jornada. Se acepta con `PERMISO_REVOCADO` anotada sobre la venta."""
    entorno = EntornoVenta(db_session, permisos=frozenset({"REGISTRAR_COBRANZA"}))
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle == {"permiso": "VENDER", "motivo": "PERMISO_QUITADO"}
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33


def test_syn05_varias_observaciones_en_una_misma_venta(db_session: Session) -> None:
    """Escenario "Varias observaciones en una venta": stock negativo, cliente suspendido y
    vendedor sin `VENDER`."""
    entorno = EntornoVenta(db_session, permisos=frozenset({"REGISTRAR_COBRANZA"}))
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")
    ruta = Ruta(entorno, stock=5)

    _, resultado = ruta.enviar(entorno.linea(cantidad=8))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert sorted(_codigos(entorno)) == [
        "CLIENTE_NO_HABILITADO",
        "PERMISO_REVOCADO",
        "STOCK_NEGATIVO",
    ]
    assert len(entorno.ventas()) == 1


# --- la jornada del sobre (RUT-09, SYN-06, SYN-10) ----------------------------------------------


def test_syn10_sin_jornada_en_el_sobre_se_rechaza_con_jornada_requerida_y_el_lote_sigue(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Sin jornada": rechazada sin fila de comando ni efecto; la siguiente se acepta."""
    ruta = Ruta(entorno)
    sin_jornada = ruta.item(jornada_id=None)
    con_jornada = ruta.item(secuencia=2)

    resultados = lote(entorno, sin_jornada, con_jornada)

    _rechazada(resultados[sin_jornada.operation_id], "JORNADA_REQUERIDA", sin_jornada, entorno)
    assert resultados[con_jornada.operation_id].estado == "ACEPTADO"
    assert len(entorno.ventas()) == 1


def test_syn10_la_jornada_de_otro_usuario_se_rechaza_con_jornada_ajena(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(jornada_id=entorno.crear_otro_usuario_con_jornada())

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "JORNADA_AJENA", item, entorno)
    assert entorno.ventas() == []


def test_rut09_una_jornada_liberada_se_acepta_con_jornada_liberada_una_sola_vez(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Jornada liberada": la venta (con su cobranza en el acto) se acepta con UNA
    `JORNADA_LIBERADA` anotada sobre la venta, no sobre la cobranza; ambas llevan la jornada y el
    stock baja de la camioneta, que ya no está tomada."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")

    _, resultado = ruta.enviar(cobranza=entorno.cobranza())

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "JORNADA_LIBERADA"
    assert observacion.detalle == {
        "jornada_id": str(ruta.jornada_id),
        "liberada_en": MOMENTO_DE_LIBERACION.isoformat(),
    }
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    assert venta.jornada_id == ruta.jornada_id
    (cobranza,) = entorno.cobranzas()
    assert (cobranza.jornada_id, cobranza.origen, cobranza.venta_id) == (
        ruta.jornada_id,
        "VENTA",
        venta.id,
    )
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert entorno.saldo() == Decimal("161250.00")


def test_syn05_una_jornada_cerrada_se_acepta_sin_observacion_y_la_venta_la_lleva(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: `CERRADA` no observa (como la cobranza del change 17); la ubicación quedó
    libre y la venta lleva la jornada del sobre."""
    ruta = Ruta(entorno, estado_jornada="CERRADA")

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert (venta.jornada_id, venta.ubicacion_id) == (ruta.jornada_id, ruta.camioneta_id)
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id is None  # la ubicación estaba libre, no tomada por la jornada


def test_rut04_sin_conexion_la_ubicacion_es_la_de_la_jornada_aunque_el_contenido_traiga_otra(
    entorno: EntornoVenta,
) -> None:
    """D3: sin conexión, la jornada del sobre y su ubicación, siempre."""
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(ubicacion_id=str(entorno.deposito_id))

    assert resultado.estado == "ACEPTADO"
    assert entorno.stock(ubicacion_id=entorno.deposito_id) == 48
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33


# --- la lista y los precios congelados (PRC-23, D7) -------------------------------------------


def _con_version_nueva(entorno: EntornoVenta) -> UUID:
    """General con la versión 1 ($12.500, histórica) y la 2 vigente desde las 11:00 (la devuelve)"""
    version_2 = entorno.crear_version(entorno.lista_id, 2, HOY_TEMPRANO, precio_vino="13000.00")
    entorno.sesion.commit()
    return version_2


def test_prc23_una_venta_con_una_version_anterior_se_acepta_con_los_precios_enviados(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Venta con lista no vigente": el teléfono bajó la versión 1 y se publicó la 2.
    Se acepta con los precios de la 1 y `LISTA_NO_VIGENTE` (enviada 1, vigente 2); la fila de
    auditoría del comando lleva la observación de D20 (con el motivo si vino)."""
    version_2 = _con_version_nueva(entorno)
    ruta = Ruta(entorno)

    item, resultado = ruta.enviar(motivo_lista_id=str(entorno.motivo_lista_id))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (venta.lista_version_id, linea.lista_version_id) == (entorno.version_id,) * 2
    assert (linea.precio_referencia, linea.unidades_referencia) == (Decimal("12500.00"), 6)
    assert (linea.importe_bruto, venta.total) == (Decimal("31250.00"),) * 2
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "LISTA_NO_VIGENTE"
    assert observacion.detalle == {
        "version_enviada_id": str(entorno.version_id),
        "version_vigente_id": str(version_2),
    }
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    entorno.sesion.rollback()
    (fila,) = entorno.auditoria_de(item.operation_id)
    assert (fila.accion, fila.origen) == ("VENTA_CONFIRMAR", "COMANDO")
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion is not None
    assert "versión no vigente" in fila.observacion
    assert "versión 1" in fila.observacion


def test_prc23_la_version_vigente_no_observa_y_se_juzga_al_momento_de_la_venta(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: con la 2 publicada hoy a las 11:00, una venta de AYER (la 1 era la vigente
    entonces) enviada con la versión 1 no observa (D7: al `occurred_at`)."""
    _con_version_nueva(entorno)
    ruta = Ruta(entorno)
    ayer = ruta.item(occurred_at=datetime(2026, 10, 18, 20, 0, tzinfo=UTC))

    resultado = lote(entorno, ayer)[ayer.operation_id]

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []
    (venta,) = entorno.ventas()
    assert venta.lista_version_id == entorno.version_id


def test_prc23_el_precio_y_las_unidades_que_envio_el_dispositivo_se_congelan(
    entorno: EntornoVenta,
) -> None:
    """Se congela lo enviado (D1 punto 4): precio $12.000 aunque la versión diga $12.500; el bruto
    es el del motor sobre lo enviado (15 botellas / 6 × $12.000 = $30.000,00)."""
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(entorno.linea(precio="12000.00"))

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.precio_referencia, linea.importe_bruto) == (
        Decimal("12000.00"),
        Decimal("30000.00"),
    )
    assert venta.total == Decimal("30000.00")


def test_prc21_otra_lista_elegida_se_acepta_con_lista_no_vigente_una_sola_vez(
    entorno: EntornoVenta,
) -> None:
    """D7: aunque el vendedor la haya elegido con permiso, la versión enviada no es la vigente de
    la lista aplicable (General): una `LISTA_NO_VIGENTE` por venta (no por línea)."""
    otro, caja_otro = _producto_con_precio(entorno, "Vino B", "24000.00")
    mayorista = entorno.crear_lista("Mayorista")
    version_mayorista = entorno.crear_version(
        mayorista, 1, datetime(2026, 10, 18, 12, 0, tzinfo=UTC), precio_vino="10000.00"
    )
    entorno.poner_precio(version_mayorista, otro, "24000.00", 12)
    entorno.sesion.commit()
    ruta = Ruta(entorno, extra=((otro, 30, "2000"),))

    item, resultado = ruta.enviar(
        entorno.linea(version_id=version_mayorista, precio="10000.00"),
        _linea_de(entorno, otro, caja_otro, version_id=version_mayorista),
        lista_id=str(mayorista),
        lista_version_id=str(version_mayorista),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (venta.lista_id, venta.lista_version_id) == (mayorista, version_mayorista)
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "LISTA_NO_VIGENTE"
    assert observacion.detalle == {
        "version_enviada_id": str(version_mayorista),
        "version_vigente_id": str(entorno.version_id),
    }
    entorno.sesion.rollback()
    (fila,) = entorno.auditoria_de(item.operation_id)
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion is not None
    assert 'Lista "Mayorista"' in fila.observacion
    assert "lista distinta" in fila.observacion


# --- VENTA_SIN_COSTO (D10) ---------------------------------------------------------------------


def test_d10_un_producto_sin_costo_se_acepta_con_costo_nulo_y_venta_sin_costo_por_linea(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Producto sin costo sin conexión": Vino C nunca tuvo compras. La línea queda con
    costo nulo (INV-10: no se completa después) y `VENTA_SIN_COSTO` con línea y producto; la línea
    de Vino A conserva su costo. También sale con `STOCK_NEGATIVO`: un producto sin costo no
    tiene stock."""
    vino_c, caja_c = _producto_con_precio(entorno, "Vino C", "24000.00")
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(entorno.linea(), _linea_de(entorno, vino_c, caja_c, cantidad=1))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    con_costo, sin_costo = entorno.lineas_de_venta(venta.id)
    assert con_costo.costo_unitario == Decimal("1050.000000")
    assert (sin_costo.costo_unitario, sin_costo.costo_total) == (None, None)
    assert _codigos(entorno) == ["STOCK_NEGATIVO", "VENTA_SIN_COSTO"]
    sin_costo_obs = next(o for o in _observaciones(entorno) if o.codigo == "VENTA_SIN_COSTO")
    assert sin_costo_obs.detalle == {"linea_id": str(sin_costo.id), "producto_id": str(vino_c)}
    assert (sin_costo_obs.operacion_tipo, sin_costo_obs.operacion_id) == ("VENTA", venta.id)


# --- la cobranza en el acto (SYN-07) -----------------------------------------------------------


def test_syn07_un_medio_inactivo_y_una_referencia_faltante_se_aceptan_con_observacion(
    entorno: EntornoVenta,
) -> None:
    """La cobranza de la venta se acepta con `MEDIO_INACTIVO` (la administración desactivó
    "Billetera") y `REFERENCIA_FALTANTE` ("Transferencia" exige referencia), como en el change 17,
    anotadas sobre la cobranza. La suma de los medios es el importe y el saldo baja."""
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    entorno.sesion.commit()
    ruta = Ruta(entorno)
    entorno.desactivar_medio(billetera)
    cobranza = entorno.cobranza(
        (billetera, "5000.00", None), (entorno.transferencia_id, "5000.00", None)
    )

    _, resultado = ruta.enviar(cobranza=cobranza)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (cobrada,) = entorno.cobranzas()
    assert cobrada.importe == Decimal("10000.00")
    assert _codigos(entorno) == ["MEDIO_INACTIVO", "REFERENCIA_FALTANTE"]
    assert {(o.operacion_tipo, o.operacion_id) for o in _observaciones(entorno)} == {
        ("COBRANZA", cobrada.id)
    }
    assert entorno.saldo() == Decimal("171250.00")


# --- producto o presentación desactivados (D1 punto 5) ------------------------------------------


@pytest.mark.parametrize("tabla", ["producto", "presentacion"])
def test_d1_un_producto_o_presentacion_desactivado_despues_del_bootstrap_se_acepta_sin_observacion(
    entorno: EntornoVenta, tabla: str
) -> None:
    """La mercadería ya se entregó: se acepta sin observación nueva (queda para la bandeja del
    change 25) y el stock se descuenta."""
    ruta = Ruta(entorno)
    id_ = entorno.vino_id if tabla == "producto" else entorno.botella_id
    entorno.sesion.execute(
        text(f"UPDATE {tabla} SET activo = false WHERE organizacion_id = :o AND id = :i"),
        {"o": entorno.org, "i": id_},
    )
    entorno.sesion.commit()

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert len(entorno.ventas()) == 1


# --- lo malformado, lo inexistente y lo inconsistente (SYN-06) -----------------------------------


def test_syn06_un_bruto_enviado_que_no_es_el_del_motor_se_rechaza_con_totales_inconsistentes(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Totales incoherentes": sin efectos ni fila de comando; el reintento con el
    bruto correcto y el mismo `operation_id` se acepta (el rechazo revirtió la reserva)."""
    ruta = Ruta(entorno)
    mal = ruta.item(ruta.contenido(entorno.linea(bruto="31251.00")))

    resultado = lote(entorno, mal)[mal.operation_id]

    _rechazada(resultado, "TOTALES_INCONSISTENTES", mal, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)
    bien = ruta.item(operation_id=mal.operation_id)
    assert lote(entorno, bien)[bien.operation_id].estado == "ACEPTADO"


def test_syn06_un_total_enviado_que_no_es_el_calculado_se_rechaza(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(total="31250.01"))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "TOTALES_INCONSISTENTES", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_syn06_unidades_de_referencia_invalidas_se_rechazan_como_inconsistentes(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(entorno.linea(unidades_referencia=0, bruto="0.00")))

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "RECHAZADO"
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_inv07_una_venta_sin_lineas_se_rechaza(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(lineas=[], total="0.00"))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "VENTA_SIN_LINEAS", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def _cobranza_con_medio_inexistente(entorno: EntornoVenta) -> dict[str, Any]:
    return entorno.cobranza((uuid4(), "1000.00", None))


@pytest.mark.parametrize(
    "cambios",
    [
        pytest.param(lambda e: {"cliente_id": str(uuid4())}, id="cliente"),
        pytest.param(
            lambda e: {"lineas": [e.linea(producto_id=uuid4(), bruto="31250.00")]},
            id="producto",
        ),
        pytest.param(lambda e: {"lineas": [e.linea(presentacion_id=uuid4())]}, id="presentacion"),
        pytest.param(lambda e: {"lineas": [e.linea(version_id=uuid4())]}, id="version"),
        pytest.param(lambda e: {"cobranza": _cobranza_con_medio_inexistente(e)}, id="medio"),
    ],
)
def test_syn06_lo_inexistente_se_rechaza_sin_efectos(entorno: EntornoVenta, cambios: Any) -> None:
    """Un cliente, producto, presentación, versión de lista o medio de pago inexistente."""
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(**cambios(entorno)))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_vta06_un_numero_repetido_se_rechaza_y_el_prefijo_ajeno_tambien(
    entorno: EntornoVenta,
) -> None:
    """Escenarios "Número repetido" y "Prefijo de otro dispositivo": sin efectos."""
    ruta = Ruta(entorno)
    primera = ruta.item(ruta.contenido(numero=f"{entorno.prefijo}-000042"), secuencia=1)
    repetida = ruta.item(ruta.contenido(numero=f"{entorno.prefijo}-000042"), secuencia=2)
    ajena = ruta.item(ruta.contenido(numero=f"X{entorno.prefijo}-000001"), secuencia=3)

    resultados = lote(entorno, primera, repetida, ajena)

    assert resultados[primera.operation_id].estado == "ACEPTADO"
    _rechazada(resultados[repetida.operation_id], "NUMERO_DUPLICADO", repetida, entorno)
    _rechazada(resultados[ajena.operation_id], "NUMERO_INVALIDO", ajena, entorno)
    assert len(entorno.ventas()) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert entorno.ultimo_correlativo() == 42


def test_vta06_un_numero_menor_no_hace_retroceder_el_correlativo(entorno: EntornoVenta) -> None:
    # Escenario: "Un número menor no retrocede el correlativo"
    ruta = Ruta(entorno)
    mayor = ruta.item(ruta.contenido(numero=f"{entorno.prefijo}-000050"), secuencia=1)
    menor = ruta.item(ruta.contenido(numero=f"{entorno.prefijo}-000045"), secuencia=2)

    resultados = lote(entorno, mayor, menor)

    assert {r.estado for r in resultados.values()} == {"ACEPTADO"}
    assert entorno.ultimo_correlativo() == 50


# --- ubicación tomada al sincronizar (SYN-05, INV-17, STK-09, RUT-09) --------------------------


def _tomar_por_otra_jornada(entorno: EntornoVenta, db_session: Session, ubicacion_id: UUID) -> UUID:
    """Otro vendedor (otro usuario y dispositivo) abre una jornada sobre `ubicacion_id`."""
    otro_id, otro_dispositivo_id = crear_usuario_y_dispositivo(
        db_session, entorno.org, permisos=PERMISOS_DE_VENTA
    )
    return entorno.crear_jornada(
        usuario_id=otro_id, dispositivo_id=otro_dispositivo_id, ubicacion_id=ubicacion_id
    )


def _fila_de_auditoria(entorno: EntornoVenta, operation_id: UUID) -> Any:
    entorno.sesion.rollback()
    (fila,) = entorno.auditoria_de(operation_id)
    return fila


def test_syn05_la_propia_jornada_en_rendicion_se_acepta_con_ubicacion_tomada_al_sincronizar(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Ubicación tomada al sincronizar"
    # Escenario: "Ubicación tomada al sincronizar una venta sin conexión"
    """Decisión del usuario, 2026-10-20 (SYN-05, INV-17, STK-09): la mercadería ya se entregó. La
    jornada del vendedor pasó a `EN_RENDICION` antes de sincronizar y la ubicación sigue tomada:
    la venta, SIN `LIBERAR_UBICACION`, se acepta, descuenta el stock, conserva su jornada y lleva
    `UBICACION_TOMADA_AL_SINCRONIZAR`; la auditoría deja la constancia de STK-09."""
    ruta = Ruta(entorno, estado_jornada="EN_RENDICION")

    item, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (venta.ubicacion_id, venta.jornada_id) == (ruta.camioneta_id, ruta.jornada_id)
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "UBICACION_TOMADA_AL_SINCRONIZAR"
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta.id)
    assert observacion.detalle == {
        "jornada_id": str(ruta.jornada_id),
        "ubicacion_id": str(ruta.camioneta_id),
    }
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    assert entorno.saldo() == Decimal("181250.00")
    assert entorno.ultimo_correlativo() == 1
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id is None  # pasó por la excepción de toma (STK-09)
    fila = _fila_de_auditoria(entorno, item.operation_id)
    assert fila.observacion == f"ubicación tomada por la jornada {ruta.jornada_id}"


def test_syn05_jornada_liberada_y_camioneta_retomada_lleva_las_dos_observaciones(
    entorno: EntornoVenta, db_session: Session
) -> None:
    # Escenario: "Ubicación tomada al sincronizar"
    # Escenario: "Ubicación tomada al sincronizar una venta sin conexión"
    """Triangulación: la propia jornada se liberó y otro vendedor tomó la camioneta antes de que
    el teléfono sincronizara. La venta conserva su jornada y lleva `JORNADA_LIBERADA` (RUT-09) y
    `UBICACION_TOMADA_AL_SINCRONIZAR`, que conviven; la constancia nombra a la jornada que tiene
    la ubicación, no a la del sobre."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    jornada_de_otro = _tomar_por_otra_jornada(entorno, db_session, ruta.camioneta_id)

    item, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert venta.jornada_id == ruta.jornada_id
    observaciones = _observaciones(entorno)
    assert [o.codigo for o in observaciones] == [
        "JORNADA_LIBERADA",
        "UBICACION_TOMADA_AL_SINCRONIZAR",
    ]
    assert observaciones[1].detalle == {
        "jornada_id": str(jornada_de_otro),
        "ubicacion_id": str(ruta.camioneta_id),
    }
    assert {(o.operacion_tipo, o.operacion_id) for o in observaciones} == {("VENTA", venta.id)}
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 33
    fila = _fila_de_auditoria(entorno, item.operation_id)
    assert fila.observacion == f"ubicación tomada por la jornada {jornada_de_otro}"


def test_aud02_la_ubicacion_tomada_al_sincronizar_se_une_al_texto_de_la_lista(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: con una versión que ya no es la vigente, la única fila de auditoría lleva
    los dos textos unidos con `; ` (el de la lista y la constancia de STK-09)."""
    _con_version_nueva(entorno)
    ruta = Ruta(entorno, estado_jornada="EN_RENDICION")

    item, resultado = ruta.enviar(motivo_lista_id=str(entorno.motivo_lista_id))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert [o.codigo for o in _observaciones(entorno)] == [
        "LISTA_NO_VIGENTE",
        "UBICACION_TOMADA_AL_SINCRONIZAR",
    ]
    fila = _fila_de_auditoria(entorno, item.operation_id)
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion is not None
    texto_de_lista, constancia = fila.observacion.split("; ")
    assert "versión no vigente" in texto_de_lista
    assert constancia == f"ubicación tomada por la jornada {ruta.jornada_id}"


def test_syn05_una_venta_de_la_jornada_abierta_no_lleva_ubicacion_tomada(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: si la ubicación está tomada por la propia jornada del sobre (`ABIERTA`) no
    hay nada que observar ni constancia que dejar."""
    ruta = Ruta(entorno)

    item, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []
    assert _fila_de_auditoria(entorno, item.operation_id).observacion is None


def test_stk09_por_el_lote_online_la_ubicacion_tomada_sigue_rechazando(
    entorno: EntornoVenta, db_session: Session
) -> None:
    """Con conexión nada cambia: sin `LIBERAR_UBICACION` la venta desde una ubicación tomada por
    otra jornada sigue siendo `UBICACION_TOMADA`, sin efectos."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    _tomar_por_otra_jornada(entorno, db_session, ruta.camioneta_id)
    item = ruta.item(
        entorno.contenido(ubicacion_id=str(ruta.camioneta_id)), modo="ONLINE", jornada_id=None
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "UBICACION_TOMADA", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


# --- motivo de la lista sin conexión (PRC-21, SYN-05) -------------------------------------------


def test_syn05_un_motivo_inactivo_se_acepta_sin_conexion(entorno: EntornoVenta) -> None:
    # Escenario: "Motivo y versiones sin conexión"
    """Decisión del usuario, 2026-10-20: el motivo existe pero se desactivó después de bajar el
    catálogo; la venta ya ocurrió, se acepta y lo guarda."""
    _con_version_nueva(entorno)
    inactivo = entorno.crear_motivo("LISTA_ANTERIOR", "Motivo viejo", activo=False)
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = ruta.enviar(motivo_lista_id=str(inactivo))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert venta.motivo_lista_id == inactivo


def test_syn06_un_motivo_de_otro_ambito_se_rechaza_como_inconsistente(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Motivo y versiones sin conexión"
    """Triangulación: un motivo que no es del ámbito `LISTA_ANTERIOR` es un comando inconsistente
    (`MOTIVO_INVALIDO`), aunque esté activo; sin efectos."""
    ruta = Ruta(entorno)
    ajeno = entorno.crear_motivo("ANULACION_VENTA", "Otro ámbito")
    entorno.sesion.commit()
    item = ruta.item(ruta.contenido(motivo_lista_id=str(ajeno)))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "MOTIVO_INVALIDO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_syn06_un_motivo_inexistente_sigue_siendo_recurso_no_encontrado(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(motivo_lista_id=str(uuid4())))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)


# --- versiones mezcladas entre líneas (PRC-23, SYN-06) ------------------------------------------


def _dos_productos_con_versiones_distintas(
    entorno: EntornoVenta,
) -> tuple[UUID, dict[str, Any], dict[str, Any]]:
    """La versión 2 de General y dos líneas: Vino A con la 1 y Vino B con la 2 (ambas existen)."""
    version_2 = _con_version_nueva(entorno)
    otro, caja_otro = _producto_con_precio(entorno, "Vino B", "24000.00", version_id=version_2)
    return (
        version_2,
        entorno.linea(),
        _linea_de(entorno, otro, caja_otro, version_id=version_2),
    )


def test_prc23_lineas_con_versiones_distintas_se_rechazan_sin_conexion(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Motivo y versiones sin conexión"
    """Decisión del usuario, 2026-10-20: todas las líneas llevan la misma versión; si difieren el
    comando es inconsistente (`VERSION_NO_PERMITIDA`) y no deja efectos."""
    _, linea_1, linea_2 = _dos_productos_con_versiones_distintas(entorno)
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(linea_1, linea_2))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "VERSION_NO_PERMITIDA", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_prc23_la_version_de_la_cabecera_debe_ser_la_de_las_lineas(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: las líneas son uniformes (versión 1) pero la cabecera elige la 2."""
    version_2 = _con_version_nueva(entorno)
    ruta = Ruta(entorno)
    item = ruta.item(
        ruta.contenido(lista_id=str(entorno.lista_id), lista_version_id=str(version_2))
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "VERSION_NO_PERMITIDA", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_prc23_lineas_y_cabecera_con_la_misma_version_se_aceptan(entorno: EntornoVenta) -> None:
    """Triangulación: dos líneas y la cabecera con la versión 1 (no vigente): se acepta."""
    _con_version_nueva(entorno)
    otro, caja_otro = _producto_con_precio(entorno, "Vino B", "24000.00")
    ruta = Ruta(entorno, extra=((otro, 30, "2000"),))

    _, resultado = ruta.enviar(
        entorno.linea(),
        _linea_de(entorno, otro, caja_otro),
        lista_id=str(entorno.lista_id),
        lista_version_id=str(entorno.version_id),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert [o.codigo for o in _observaciones(entorno)] == ["LISTA_NO_VIGENTE"]


def test_prc23_por_el_lote_online_las_versiones_mezcladas_siguen_rechazando_con_precio_difiere(
    entorno: EntornoVenta,
) -> None:
    """Con conexión nada cambia: la comparación de D2 ya exige una sola versión (la resuelta) y
    una línea con otra es `PRECIO_DIFIERE`."""
    _, linea_1, linea_2 = _dos_productos_con_versiones_distintas(entorno)
    ruta = Ruta(entorno)
    item = ruta.item(
        entorno.contenido(linea_1, linea_2, ubicacion_id=str(entorno.deposito_id)),
        modo="ONLINE",
        jornada_id=None,
    )

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PRECIO_DIFIERE")


# --- doble envío (INV-06) ----------------------------------------------------------------------


def test_inv06_el_doble_envio_se_registra_una_vez_con_las_mismas_observaciones(
    db_session: Session,
) -> None:
    """Escenario "Doble envío sin conexión": el reenvío devuelve el resultado original y las
    mismas observaciones, sin otra venta, otro egreso ni otro débito."""
    entorno = EntornoVenta(db_session, permisos=frozenset({"REGISTRAR_COBRANZA"}))
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")
    ruta = Ruta(entorno, stock=5)
    item = ruta.item(ruta.contenido(entorno.linea(cantidad=8)))

    primero = lote(entorno, item)[item.operation_id]
    codigos = _codigos(entorno)
    segundo = lote(entorno, item)[item.operation_id]

    assert primero.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert (
        _codigos(entorno)
        == codigos
        == ["CLIENTE_NO_HABILITADO", "PERMISO_REVOCADO", "STOCK_NEGATIVO"]
    )
    assert len(entorno.ventas()) == 1
    assert len(entorno.movimientos_de_stock()) == 1
    assert len(entorno.movimientos("VENTA")) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == -3


# --- con conexión no cambia ---------------------------------------------------------------------


def _en_linea(entorno: EntornoVenta, contenido: dict[str, Any], **opciones: Any) -> ItemLote:
    return _item(entorno, contenido, modo="ONLINE", jornada_id=None, **opciones)


def test_stk05_por_el_lote_online_el_stock_insuficiente_sigue_rechazando(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Con conexión no cambia": 50 botellas sobre 48, por el lote en modo `ONLINE`:
    `STOCK_INSUFICIENTE`, sin efectos y sin observaciones."""
    item = _en_linea(entorno, entorno.contenido(entorno.linea(cantidad=50)))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "STOCK_INSUFICIENTE", item, entorno)
    entorno.sin_efectos_de_venta()
    assert _observaciones(entorno) == []


def test_syn05_por_el_lote_online_el_precio_que_difiere_sigue_rechazando(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: con conexión una diferencia de precio es `PRECIO_DIFIERE` (D2), no
    `TOTALES_INCONSISTENTES`."""
    item = _en_linea(entorno, entorno.contenido(entorno.linea(bruto="31251.00")))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "PRECIO_DIFIERE", item, entorno)
    entorno.sin_efectos_de_venta()


def test_syn05_por_el_lote_online_el_momento_fuera_de_rango_sigue_rechazando(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: D9 rige con conexión (la misma hora fuera de rango se acepta sin ella)."""
    item = _en_linea(
        entorno, entorno.contenido(), occurred_at=datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "MOMENTO_FUERA_DE_RANGO", item, entorno)
    entorno.sin_efectos_de_venta()


def test_syn05_por_el_lote_online_el_cliente_y_el_producto_inactivos_siguen_rechazando(
    entorno: EntornoVenta,
) -> None:
    """Con conexión el cliente inactivo (`CLIENTE_INACTIVO`) y el producto desactivado
    (`PRODUCTO_INACTIVO`) se rechazan; los mismos casos sin conexión se aceptan (arriba)."""
    entorno.actualizar_cliente(entorno.cliente_id, estado="INACTIVO")
    entorno.sesion.commit()
    inactivo = _en_linea(entorno, entorno.contenido())
    assert lote(entorno, inactivo)[inactivo.operation_id].error_codigo == "CLIENTE_INACTIVO"

    entorno.actualizar_cliente(entorno.cliente_id, estado="ACTIVO")
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :i"),
        {"o": entorno.org, "i": entorno.vino_id},
    )
    entorno.sesion.commit()
    producto = _en_linea(entorno, entorno.contenido())
    assert lote(entorno, producto)[producto.operation_id].error_codigo == "PRODUCTO_INACTIVO"
    entorno.sin_efectos_de_venta()
    assert _observaciones(entorno) == []


@pytest.fixture
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str, _limpiar_datos_confirmados: None) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def test_stk05_por_rest_el_stock_insuficiente_sigue_rechazando_sin_observaciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Con conexión no cambia", por REST: 409 `STOCK_INSUFICIENTE`, ninguna venta y
    ninguna observación."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)
    cuerpo = s.entorno.contenido(s.entorno.linea(cantidad=50), numero=f"{s.prefijo}-000001")

    respuesta = cliente_http.post(URL_VENTAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "STOCK_INSUFICIENTE"
    for tabla in ("venta", "observacion"):
        cuantas = sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
            {"o": s.entorno.org},
        ).scalar_one()
        assert cuantas == 0
