"""Change 14, tareas 4.2 y 4.3: transferencias, ajustes y sus inversos en
`stock.registrar_movimientos` contra PostgreSQL real (spec delta `stock/libro-de-stock`,
`design.md` D1, D3, D4, D5.2, D9).

Reglas citadas: STK-03, STK-05, STK-07, STK-10, CST-12, CST-13, CAT-05, INV-12, INV-15.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql, desactivar_producto_sql

from app.core.clock import FixedClock
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import service
from app.modules.stock.domain.errores import (
    CostoInvalidoError,
    ProductoInactivoError,
    ProductoSinCostoError,
    StockInsuficienteError,
    TipoDeMovimientoInvalidoError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.producto_id = crear_producto_sql(sesion, self.org)
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )

    def mover(
        self, *lineas: LineaDeMovimiento, permitir_negativo: bool = False
    ) -> list[service.ResultadoDeMovimiento]:
        return service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=list(lineas),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            permitir_negativo=permitir_negativo,
        )

    def linea(
        self,
        cantidad: int,
        tipo: str,
        *,
        costo: str | None = None,
        origen_tipo: str | None = None,
        ubicacion_id: UUID | None = None,
        producto_id: UUID | None = None,
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=producto_id or self.producto_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo=origen_tipo or tipo,
            origen_id=uuid4(),
        )

    def compra(self, cantidad: int, costo: str) -> list[service.ResultadoDeMovimiento]:
        return self.mover(self.linea(cantidad, "COMPRA", costo=costo))

    def saldo(self, ubicacion_id: UUID | None = None) -> int:
        return service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=self.producto_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
        )

    def costo(self) -> CostoProducto:
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == self.producto_id,
            )
            .execution_options(populate_existing=True)
        ).one()

    def historia(self) -> list[CostoProductoMov]:
        return list(
            self.sesion.scalars(
                select(CostoProductoMov).where(CostoProductoMov.organizacion_id == self.org)
            )
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- ingresos sin costo (CST-12, D9) -------------------------------------------


def test_la_transferencia_deja_el_stock_total_y_valoriza_los_dos_movimientos_al_promedio(
    entorno: Entorno,
) -> None:
    """Escenario "Entrada de transferencia valorizada al promedio": INV-15, CST-12."""
    entorno.compra(120, "1050")
    historia = len(entorno.historia())

    salida, entrada = entorno.mover(
        entorno.linea(-48, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
        entorno.linea(
            48,
            "TRANSFERENCIA_ENTRADA",
            origen_tipo="TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
    )

    assert salida.movimiento.costo_unitario == Decimal("1050.000000")
    assert entrada.movimiento.costo_unitario == Decimal("1050.000000")
    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (72, 48)
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1050.000000"), 120)
    assert len(entorno.historia()) == historia  # CST-13: sin historia de costo


@pytest.mark.parametrize(
    ("tipo", "origen"), [("TRANSFERENCIA_ENTRADA", "TRANSFERENCIA"), ("AJUSTE", "AJUSTE_STOCK")]
)
def test_un_ingreso_de_transferencia_o_ajuste_con_costo_es_costo_invalido(
    entorno: Entorno, tipo: str, origen: str
) -> None:
    entorno.compra(120, "1050")

    with pytest.raises(CostoInvalidoError):
        entorno.mover(entorno.linea(2, tipo, costo="1000.000000", origen_tipo=origen))

    assert (entorno.saldo(), entorno.costo().stock_total) == (120, 120)


def test_un_ingreso_de_rendicion_sigue_rechazado(entorno: Entorno) -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError):
        entorno.mover(entorno.linea(2, "DIFERENCIA_RENDICION"))


def test_un_ajuste_positivo_sube_el_stock_total_y_no_recalcula(entorno: Entorno) -> None:
    """D3: +2 al promedio vigente sin historia (CST-12, CST-13)."""
    entorno.compra(120, "1050")
    entorno.mover(entorno.linea(-6, "AJUSTE", origen_tipo="AJUSTE_STOCK"))
    assert entorno.costo().stock_total == 114

    (resultado,) = entorno.mover(entorno.linea(2, "AJUSTE", origen_tipo="AJUSTE_STOCK"))

    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1050.000000"), 116)
    assert len(entorno.historia()) == 1


def test_un_ingreso_de_un_producto_sin_promedio_se_valoriza_nulo(entorno: Entorno) -> None:
    """Un egreso con permiso deja el producto sin promedio y con stock total negativo; la
    entrada de transferencia que lo regulariza queda sin valorizar (D3)."""
    (salida, entrada) = entorno.mover(
        entorno.linea(-6, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
        entorno.linea(
            6,
            "TRANSFERENCIA_ENTRADA",
            origen_tipo="TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
        permitir_negativo=True,
    )

    assert salida.movimiento.costo_unitario is None
    assert entrada.movimiento.costo_unitario is None
    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (-6, 6)
    assert entorno.costo().stock_total == 0


# --- stock negativo (D1) ---------------------------------------------------------


def test_la_salida_de_transferencia_con_permiso_deja_el_saldo_negativo_y_lo_marca(
    entorno: Entorno,
) -> None:
    entorno.compra(48, "1050")

    salida, entrada = entorno.mover(
        entorno.linea(-60, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
        entorno.linea(
            60,
            "TRANSFERENCIA_ENTRADA",
            origen_tipo="TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
        permitir_negativo=True,
    )

    assert (salida.saldo, salida.saldo_negativo) == (-12, True)
    assert (entrada.saldo, entrada.saldo_negativo) == (60, False)
    assert entorno.costo().stock_total == 48  # INV-15


def test_la_salida_de_transferencia_sin_permiso_es_stock_insuficiente_sin_efectos(
    entorno: Entorno,
) -> None:
    entorno.compra(48, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(
            entorno.linea(-60, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
            entorno.linea(
                60,
                "TRANSFERENCIA_ENTRADA",
                origen_tipo="TRANSFERENCIA",
                ubicacion_id=entorno.camioneta_id,
            ),
        )

    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (48, 0)


def test_un_ajuste_negativo_con_permiso_sigue_siendo_stock_insuficiente(entorno: Entorno) -> None:
    """D1 = B: un ajuste nunca deja el saldo negativo, tampoco con
    `PERMITIR_STOCK_NEGATIVO`."""
    entorno.compra(48, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(
            entorno.linea(-60, "AJUSTE", origen_tipo="AJUSTE_STOCK"), permitir_negativo=True
        )

    assert entorno.saldo() == 48


def test_la_correccion_de_stock_inicial_con_permiso_sigue_rechazada(entorno: Entorno) -> None:
    """STK-10: sin excepción por el permiso."""
    entorno.mover(entorno.linea(48, "STOCK_INICIAL", costo="1050"))

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-60, "STOCK_INICIAL"), permitir_negativo=True)

    assert entorno.saldo() == 48


# --- inversos de una anulación (D5.2) ---------------------------------------------


def test_el_inverso_de_un_ajuste_guarda_el_costo_original_y_no_recalcula(
    entorno: Entorno,
) -> None:
    """Escenario "Inverso de un ajuste a su costo original": el ajuste se hizo a 1050 y el
    promedio vigente ya es 1100; el inverso vuelve a 1050 (CST-12, CST-13)."""
    entorno.compra(120, "1050")
    entorno.mover(entorno.linea(-6, "AJUSTE", origen_tipo="AJUSTE_STOCK"))
    entorno.compra(60, "1150")  # (114 x 1050 + 60 x 1150) / 174 = 1084,48...: otro promedio
    promedio = entorno.costo().costo_promedio
    assert promedio != Decimal("1050.000000")
    historia = len(entorno.historia())

    (resultado,) = entorno.mover(
        entorno.linea(6, "AJUSTE", costo="1050.000000", origen_tipo="ANULACION_AJUSTE_STOCK")
    )

    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (promedio, 180)  # 174 + 6
    assert len(entorno.historia()) == historia


def test_el_inverso_de_un_movimiento_sin_costo_se_guarda_nulo(entorno: Entorno) -> None:
    entorno.mover(
        entorno.linea(-6, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
        entorno.linea(
            6,
            "TRANSFERENCIA_ENTRADA",
            origen_tipo="TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
        permitir_negativo=True,
    )

    inversos = entorno.mover(
        entorno.linea(
            -6,
            "TRANSFERENCIA_SALIDA",
            origen_tipo="ANULACION_TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
        entorno.linea(6, "TRANSFERENCIA_ENTRADA", origen_tipo="ANULACION_TRANSFERENCIA"),
    )

    assert [r.movimiento.costo_unitario for r in inversos] == [None, None]
    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (0, 0)


def test_el_inverso_positivo_de_un_ajuste_sin_costo_en_un_producto_sin_promedio_se_acepta(
    entorno: Entorno,
) -> None:
    """Un ajuste positivo nuevo de un producto sin promedio es `PRODUCTO_SIN_COSTO` (D3), pero
    el inverso de una anulación no es un ajuste nuevo (D5.2): se guarda con costo nulo."""
    with pytest.raises(ProductoSinCostoError):
        entorno.mover(entorno.linea(6, "AJUSTE", origen_tipo="AJUSTE_STOCK"))

    (resultado,) = entorno.mover(
        entorno.linea(6, "AJUSTE", costo=None, origen_tipo="ANULACION_AJUSTE_STOCK")
    )

    assert resultado.movimiento.costo_unitario is None
    assert entorno.saldo() == 6


def test_el_egreso_inverso_de_un_ajuste_con_permiso_deja_el_saldo_negativo(
    entorno: Entorno,
) -> None:
    """Escenario "Inverso de una anulación de ajuste con permiso": 5 − 12 = −7."""
    entorno.compra(5, "1050")

    (resultado,) = entorno.mover(
        entorno.linea(-12, "AJUSTE", costo="1050.000000", origen_tipo="ANULACION_AJUSTE_STOCK"),
        permitir_negativo=True,
    )

    assert (resultado.saldo, resultado.saldo_negativo) == (-7, True)


def test_el_egreso_inverso_de_un_ajuste_sin_permiso_es_stock_insuficiente(
    entorno: Entorno,
) -> None:
    entorno.compra(5, "1050")

    with pytest.raises(StockInsuficienteError):
        entorno.mover(
            entorno.linea(-12, "AJUSTE", costo="1050.000000", origen_tipo="ANULACION_AJUSTE_STOCK")
        )

    assert entorno.saldo() == 5


# --- producto inactivo (D4, ADR-038 punto 5) ---------------------------------------


def _transferencia(entorno: Entorno, cantidad: int) -> list[LineaDeMovimiento]:
    return [
        entorno.linea(-cantidad, "TRANSFERENCIA_SALIDA", origen_tipo="TRANSFERENCIA"),
        entorno.linea(
            cantidad,
            "TRANSFERENCIA_ENTRADA",
            origen_tipo="TRANSFERENCIA",
            ubicacion_id=entorno.camioneta_id,
        ),
    ]


@pytest.mark.parametrize("cantidad", [-6, 6])
def test_un_producto_inactivo_rechaza_los_ajustes_de_cualquier_signo(
    entorno: Entorno, cantidad: int
) -> None:
    entorno.compra(20, "1050")
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)

    with pytest.raises(ProductoInactivoError):
        entorno.mover(entorno.linea(cantidad, "AJUSTE", origen_tipo="AJUSTE_STOCK"))

    assert entorno.saldo() == 20


def test_un_producto_inactivo_rechaza_la_salida_y_la_entrada_de_una_transferencia(
    entorno: Entorno,
) -> None:
    entorno.compra(20, "1050")
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)
    salida, entrada = _transferencia(entorno, 6)

    for linea in (salida, entrada):
        with pytest.raises(ProductoInactivoError):
            entorno.mover(linea, permitir_negativo=True)
    with pytest.raises(ProductoInactivoError):
        entorno.mover(salida, entrada)

    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (20, 0)


def test_un_producto_inactivo_rechaza_una_compra_y_solo_admite_anulacion_compra(
    entorno: Entorno,
) -> None:
    """ADR-044 punto 5: la única excepción sigue siendo `ANULACION_COMPRA`."""
    entorno.compra(20, "1050")
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)

    with pytest.raises(ProductoInactivoError):
        entorno.compra(5, "1050")
    entorno.mover(entorno.linea(-20, "ANULACION_COMPRA", costo="1050"))

    assert entorno.saldo() == 0


def test_un_producto_reactivado_vuelve_a_admitir_transferencias(entorno: Entorno) -> None:
    entorno.compra(20, "1050")
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)
    with pytest.raises(ProductoInactivoError):
        entorno.mover(*_transferencia(entorno, 6))
    entorno.sesion.execute(
        text("UPDATE producto SET activo = true WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.producto_id},
    )

    entorno.mover(*_transferencia(entorno, 6))

    assert (entorno.saldo(), entorno.saldo(entorno.camioneta_id)) == (14, 6)
