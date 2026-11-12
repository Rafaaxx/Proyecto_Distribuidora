"""Change 25, tarea 5.1: los resumidores de operación que `sync` consulta para la bandeja (spec
`sync/revision-de-observaciones`; `design.md` D4; `02` §5.3).

Cada módulo dueño de una operación (`ventas`, `cobranzas`, `proveedores`, `stock`) ofrece en su
`service.py` una función que resume varias operaciones a la vez, y `sync.service` las registra por
tipo de operación. La cantidad de consultas no crece con la cantidad de operaciones.

Reglas citadas: INV-21 (nunca de otra organización), INV-02, SYN-07.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import event
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    _limpiar_datos_confirmados,
    sesion,
)
from ventas_utiles import insertar_sql, sembrar_venta_sql

from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)


@contextmanager
def _contando_consultas(sesion: Session) -> Iterator[list[str]]:
    consultas: list[str] = []

    def _anotar(conexion, cursor, sentencia, parametros, contexto, many):  # type: ignore[no-untyped-def]  # noqa: ARG001
        consultas.append(sentencia)

    motor = sesion.get_bind()
    event.listen(motor, "before_cursor_execute", _anotar)
    try:
        yield consultas
    finally:
        event.remove(motor, "before_cursor_execute", _anotar)


class _Mundo:
    """Una organización con un usuario y un dispositivo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)

    def venta(self, cliente: str, numero: str, total: str) -> UUID:
        cliente_id = crear_cliente(self.sesion, self.org, nombre=cliente)
        return sembrar_venta_sql(
            self.sesion,
            self.org,
            cliente_id=cliente_id,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            numero=numero,
            total=total,
            total_neto=total,
            occurred_at=MOMENTO,
        ).venta_id

    def cobranza(self, cliente: str, importe: str) -> UUID:
        cobranza_id = uuid4()
        insertar_sql(
            self.sesion,
            "cobranza",
            {
                "id": cobranza_id,
                "organizacion_id": self.org,
                "cliente_id": crear_cliente(self.sesion, self.org, nombre=cliente),
                "origen": "INDEPENDIENTE",
                "importe": importe,
                "estado": "CONFIRMADA",
                "operation_id": uuid4(),
                "usuario_id": self.usuario_id,
                "dispositivo_id": self.dispositivo_id,
                "occurred_at": MOMENTO,
                "registered_at": MOMENTO,
            },
        )
        return cobranza_id

    def compra(self, proveedor: str, comprobante: str | None, total: str) -> UUID:
        compra_id = uuid4()
        insertar_sql(
            self.sesion,
            "compra",
            {
                "id": compra_id,
                "organizacion_id": self.org,
                "proveedor_id": crear_proveedor(self.sesion, self.org, nombre=proveedor),
                "ubicacion_id": crear_ubicacion_sql(self.sesion, self.org),
                "fecha": MOMENTO.date(),
                "condicion": "CREDITO",
                "total_neto": total,
                "total_factura": total,
                "numero_comprobante": comprobante,
                "estado": "CONFIRMADA",
                "operation_id": uuid4(),
                "usuario_id": self.usuario_id,
                "dispositivo_id": self.dispositivo_id,
                "occurred_at": MOMENTO,
                "registered_at": MOMENTO,
            },
        )
        return compra_id

    def transferencia(self, origen: str, destino: str) -> UUID:
        transferencia_id = uuid4()
        insertar_sql(
            self.sesion,
            "transferencia",
            {
                "id": transferencia_id,
                "organizacion_id": self.org,
                "ubicacion_origen_id": crear_ubicacion_sql(self.sesion, self.org, nombre=origen),
                "ubicacion_destino_id": crear_ubicacion_sql(self.sesion, self.org, nombre=destino),
                "estado": "CONFIRMADA",
                "operation_id": uuid4(),
                "usuario_id": self.usuario_id,
                "dispositivo_id": self.dispositivo_id,
                "occurred_at": MOMENTO,
                "registered_at": MOMENTO,
            },
        )
        return transferencia_id

    def ajuste(self, ubicacion: str) -> UUID:
        ajuste_id = uuid4()
        insertar_sql(
            self.sesion,
            "ajuste_stock",
            {
                "id": ajuste_id,
                "organizacion_id": self.org,
                "ubicacion_id": crear_ubicacion_sql(self.sesion, self.org, nombre=ubicacion),
                "motivo_id": crear_motivo_sql(self.sesion, self.org),
                "estado": "CONFIRMADA",
                "operation_id": uuid4(),
                "usuario_id": self.usuario_id,
                "dispositivo_id": self.dispositivo_id,
                "occurred_at": MOMENTO,
                "registered_at": MOMENTO,
            },
        )
        return ajuste_id


def test_la_venta_se_resume_con_su_numero_cliente_total_y_momento(sesion: Session) -> None:
    mundo = _Mundo(sesion)
    venta_id = mundo.venta("Kiosco La Esquina", "V01-000123", "37500.00")

    resumen = sync_service.resumir_operaciones(mundo.org, sesion, "VENTA", [venta_id])

    assert set(resumen) == {venta_id}
    assert resumen[venta_id].titulo == "Venta V01-000123"
    assert resumen[venta_id].tercero == "Kiosco La Esquina"
    assert resumen[venta_id].total == "37500.00"
    assert resumen[venta_id].momento == MOMENTO


def test_la_cobranza_se_resume_con_el_cliente_y_el_importe(sesion: Session) -> None:
    mundo = _Mundo(sesion)
    cobranza_id = mundo.cobranza("Almacén Don Pedro", "50000.00")

    resumen = sync_service.resumir_operaciones(mundo.org, sesion, "COBRANZA", [cobranza_id])

    assert resumen[cobranza_id].titulo == "Cobranza"
    assert resumen[cobranza_id].tercero == "Almacén Don Pedro"
    assert resumen[cobranza_id].total == "50000.00"
    assert resumen[cobranza_id].momento == MOMENTO


def test_la_compra_se_resume_con_el_comprobante_o_sin_el(sesion: Session) -> None:
    mundo = _Mundo(sesion)
    con = mundo.compra("Bodega Sur", "A-0001-00000042", "153720.00")
    sin = mundo.compra("Bodega Norte", None, "1000.50")

    resumen = sync_service.resumir_operaciones(mundo.org, sesion, "COMPRA", [con, sin])

    assert resumen[con].titulo == "Compra A-0001-00000042"
    assert resumen[con].tercero == "Bodega Sur"
    assert resumen[con].total == "153720.00"
    assert resumen[sin].titulo == "Compra"
    assert resumen[sin].tercero == "Bodega Norte"
    assert resumen[sin].total == "1000.50"


def test_la_transferencia_y_el_ajuste_dicen_las_ubicaciones_y_no_tienen_total(
    sesion: Session,
) -> None:
    mundo = _Mundo(sesion)
    transferencia = mundo.transferencia("Depósito central", "Camioneta 1")
    ajuste = mundo.ajuste("Camioneta 2")

    de_transferencias = sync_service.resumir_operaciones(
        mundo.org, sesion, "TRANSFERENCIA", [transferencia]
    )
    de_ajustes = sync_service.resumir_operaciones(mundo.org, sesion, "AJUSTE_STOCK", [ajuste])

    esperado = "Transferencia de Depósito central a Camioneta 1"
    assert de_transferencias[transferencia].titulo == esperado
    assert de_transferencias[transferencia].total is None
    assert de_transferencias[transferencia].momento == MOMENTO
    assert de_ajustes[ajuste].titulo == "Ajuste de stock en Camioneta 2"
    assert de_ajustes[ajuste].total is None


def test_inv21_una_operacion_de_otra_organizacion_no_aparece(sesion: Session) -> None:
    mundo = _Mundo(sesion)
    ajena = _Mundo(sesion)
    propia_id = mundo.venta("Kiosco La Esquina", "V01-000001", "100.00")
    ajena_id = ajena.venta("Kiosco Ajeno", "V01-000002", "200.00")

    resumen = sync_service.resumir_operaciones(mundo.org, sesion, "VENTA", [propia_id, ajena_id])

    assert set(resumen) == {propia_id}


def test_un_tipo_sin_resumidor_o_sin_ids_da_un_resumen_vacio(sesion: Session) -> None:
    mundo = _Mundo(sesion)
    venta_id = mundo.venta("Kiosco La Esquina", "V01-000003", "100.00")

    desconocido = sync_service.resumir_operaciones(mundo.org, sesion, "NO_EXISTE", [venta_id])
    assert desconocido == {}
    assert sync_service.resumir_operaciones(mundo.org, sesion, "VENTA", []) == {}
    assert sync_service.resumir_operaciones(mundo.org, sesion, "VENTA", [uuid4()]) == {}


def test_cada_tipo_resume_muchas_operaciones_con_la_misma_cantidad_de_consultas(
    sesion: Session,
) -> None:
    """D4: una consulta por tipo (las lecturas de nombres de otros módulos son lotes constantes)."""
    mundo = _Mundo(sesion)
    una_venta = [mundo.venta("Cliente 0", "V01-100000", "10.00")]
    cinco_ventas = [mundo.venta(f"Cliente {i}", f"V01-10000{i}", "10.00") for i in range(1, 6)]
    una_cobranza = [mundo.cobranza("Cliente C0", "10.00")]
    cinco_cobranzas = [mundo.cobranza(f"Cliente C{i}", "10.00") for i in range(1, 6)]
    una_compra = [mundo.compra("Proveedor 0", None, "10.00")]
    cinco_compras = [mundo.compra(f"Proveedor {i}", None, "10.00") for i in range(1, 6)]
    una_transferencia = [mundo.transferencia("A0", "B0")]
    cinco_transferencias = [mundo.transferencia(f"A{i}", f"B{i}") for i in range(1, 6)]
    un_ajuste = [mundo.ajuste("U0")]
    cinco_ajustes = [mundo.ajuste(f"U{i}") for i in range(1, 6)]
    sesion.commit()

    casos = [
        ("VENTA", una_venta, cinco_ventas),
        ("COBRANZA", una_cobranza, cinco_cobranzas),
        ("COMPRA", una_compra, cinco_compras),
        ("TRANSFERENCIA", una_transferencia, cinco_transferencias),
        ("AJUSTE_STOCK", un_ajuste, cinco_ajustes),
    ]
    for tipo, pocas, muchas in casos:
        with _contando_consultas(sesion) as con_una:
            assert len(sync_service.resumir_operaciones(mundo.org, sesion, tipo, pocas)) == 1
        with _contando_consultas(sesion) as con_cinco:
            assert len(sync_service.resumir_operaciones(mundo.org, sesion, tipo, muchas)) == 5
        assert len(con_cinco) == len(con_una), tipo
