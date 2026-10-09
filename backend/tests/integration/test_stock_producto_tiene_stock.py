"""Change 14, tarea 8.2: `stock/service.py::producto_tiene_stock`, el verificador que `stock`
registra en el puerto de `catalogo` (`design.md` D4, D4.1, D4.2; spec delta
`catalogo/productos-y-presentaciones`).

Reglas citadas: CAT-05, ADR-038 punto 5, INV-21.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql

from app.core.clock import FixedClock
from app.modules.catalogo import service as catalogo_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"TRANSFERIR_STOCK"})
        )
        self.producto_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )

    def stock_inicial(self, cantidad: int, ubicacion_id: UUID | None = None) -> None:
        stock_service.registrar_stock_inicial(
            self.org,
            self.sesion,
            RELOJ,
            ubicacion_id=ubicacion_id or self.deposito_id,
            lineas=[
                LineaDeStockInicial(self.producto_id, cantidad, "1050" if cantidad > 0 else None)
            ],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    def transferir(self, cantidad: int, *, desde: UUID, hacia: UUID) -> None:
        stock_service.transferir(
            self.org,
            self.sesion,
            RELOJ,
            ubicacion_origen_id=desde,
            ubicacion_destino_id=hacia,
            lineas=[stock_service.LineaDeTransferencia(self.producto_id, cantidad)],
            observacion=None,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            permitir_negativo=True,
        )

    def tiene_stock(self, producto_id: UUID | None = None) -> bool:
        return stock_service.producto_tiene_stock(
            self.org, producto_id or self.producto_id, self.sesion
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_con_stock_en_una_ubicacion(entorno: Entorno) -> None:
    entorno.stock_inicial(18)

    assert entorno.tiene_stock() is True


def test_sin_ninguna_fila_de_saldo(entorno: Entorno) -> None:
    assert entorno.tiene_stock() is False


def test_con_todos_los_saldos_en_cero(entorno: Entorno) -> None:
    """La fila de saldo existe pero en cero (corrección de stock inicial): no hay stock."""
    entorno.stock_inicial(18)
    entorno.stock_inicial(-18)

    assert (
        stock_service.obtener_saldo(
            entorno.org,
            entorno.sesion,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.deposito_id,
        )
        == 0
    )
    assert entorno.tiene_stock() is False


def test_saldos_que_se_compensan_cuentan_como_stock(entorno: Entorno) -> None:
    """+5 en la camioneta y −5 en el depósito: suman cero pero hay saldos distintos de cero."""
    entorno.transferir(5, desde=entorno.deposito_id, hacia=entorno.camioneta_id)

    assert entorno.tiene_stock() is True


def test_un_saldo_negativo_cuenta_como_stock(entorno: Entorno) -> None:
    """Hay 40 y se transfieren 52 con permiso: el depósito queda en −12."""
    entorno.stock_inicial(40)
    entorno.transferir(52, desde=entorno.deposito_id, hacia=entorno.camioneta_id)

    assert (
        stock_service.obtener_saldo(
            entorno.org,
            entorno.sesion,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.deposito_id,
        )
        == -12
    )
    assert entorno.tiene_stock() is True


def test_no_mira_los_saldos_de_otra_organizacion(db_session: Session) -> None:
    """INV-21."""
    entorno = Entorno(db_session)
    ajena = Entorno(db_session)
    ajena.stock_inicial(99)

    assert ajena.tiene_stock() is True
    assert stock_service.producto_tiene_stock(entorno.org, ajena.producto_id, db_session) is False
    assert entorno.tiene_stock() is False


def test_lee_los_saldos_del_producto_for_share(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4.2: el repositorio pide las filas con `FOR SHARE`, para que un movimiento concurrente
    no las cambie mientras se decide."""
    sentencias: list[str] = []
    original = entorno.sesion.scalar

    def espiar(consulta: object, *args: object, **kwargs: object) -> object:
        sentencias.append(str(consulta.compile(dialect=entorno.sesion.bind.dialect)))  # type: ignore[attr-defined]
        return original(consulta, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(entorno.sesion, "scalar", espiar)
    entorno.stock_inicial(3)
    sentencias.clear()

    assert entorno.tiene_stock() is True

    assert any("FOR SHARE" in sentencia for sentencia in sentencias)


def test_el_arranque_de_la_aplicacion_registra_el_verificador_de_stock() -> None:
    """D4.1, como ADR-025: importar `app.main` (que importa `stock.commands`) deja registrado el
    verificador; sin él `catalogo` falla cerrado al desactivar un producto."""
    importlib.import_module("app.main")

    assert catalogo_service._VERIFICADOR_DE_STOCK is stock_service.producto_tiene_stock
