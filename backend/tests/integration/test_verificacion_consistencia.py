"""Change 28, tarea 2.1: la verificación de consistencia compara cada saldo con su libro, guarda un
resultado por organización y no corrige nada (`design.md` D4, D5).

La tarea corre conectada como `app_mantenimiento` (D3). Los datos se CONFIRMAN de verdad (una
sesión propia, sin rollback externo) porque la conexión de mantenimiento es otra; al terminar se
vacía `organizacion` en cascada, igual que las pruebas de concurrencia. Los saldos se alteran con
`app_migrations` (dueño del esquema): ni `app_runtime` ni `app_mantenimiento` pueden.

Reglas citadas: INV-02, INV-12, INV-13, INV-21, CST-13, ADR-015, ADR-039, `02` §7.6.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from anulaciones_utiles import Entorno as EntornoDeStock
from compras_utiles import Entorno as EntornoDeCompras
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from ventas_anular_utiles import EntornoAnulacion

from app.core.clock import FixedClock
from app.core.db import crear_session_factory
from app.tareas import verificacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

AHORA = datetime(2026, 11, 11, 5, 0, tzinfo=UTC)
RELOJ = FixedClock(AHORA)
PERMISOS_DE_COMPRAS = frozenset({"REGISTRAR_COMPRA", "EDITAR_COSTOS", "ANULAR_COMPRA"})


@pytest.fixture
def sesion_real(_engine_de_sesion: Engine) -> Iterator[Session]:
    """Sesión que confirma de verdad (la conexión de mantenimiento es otra)."""
    with crear_session_factory(_engine_de_sesion)() as sesion:
        yield sesion
        sesion.rollback()
    with _engine_de_sesion.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def _compra_de_vino(entorno: EntornoDeCompras, *, cantidad: str, valor: str) -> UUID:
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


def _compra_de_botellas(entorno: EntornoDeCompras, cantidad: str, valor: str) -> UUID:
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


@pytest.fixture
def dos_organizaciones(sesion_real: Session) -> tuple[EntornoDeCompras, EntornoAnulacion]:
    """A: compras y sus anulaciones (con y sin recálculo del promedio). B: stock inicial, compra,
    venta y anulación de venta."""
    compras = EntornoDeCompras(sesion_real, permisos=PERMISOS_DE_COMPRAS)
    _compra_de_vino(compras, cantidad="10", valor="6000.00")
    segunda = _compra_de_botellas(compras, "60", "1100.00")
    compras.anular(segunda)  # recalcula el promedio (CMP-06)
    primera = _compra_de_botellas(compras, "6", "1300.00")
    compras.anular(primera)

    ventas = EntornoAnulacion(sesion_real)
    producto_id, presentacion_id = ventas.producto_a("1000.00")
    linea = ventas.linea(producto_id, presentacion_id, 5, precio="1000.00", unidades_referencia=1)
    venta_id = ventas.vender_y_obtener_id(linea)
    ventas.anular(venta_id)
    otra = ventas.linea(producto_id, presentacion_id, 3, precio="1000.00", unidades_referencia=1)
    ventas.vender_y_obtener_id(otra)  # una venta vigente: egresos del libro y del costo
    return compras, ventas


def _resultados(app_mantenimiento_engine: Engine, organizacion_id: UUID) -> list[Any]:
    with app_mantenimiento_engine.connect() as conexion:
        return list(
            conexion.execute(
                text(
                    "SELECT resultado, diferencias, ejecutada_en FROM verificacion_consistencia "
                    "WHERE organizacion_id = :o ORDER BY ejecutada_en, registered_at"
                ),
                {"o": organizacion_id},
            )
        )


def _correr(app_mantenimiento_engine: Engine) -> list[verificacion.ResultadoDeOrganizacion]:
    return verificacion.ejecutar_verificacion(
        crear_session_factory(app_mantenimiento_engine), RELOJ
    )


def _alterar(motor: Engine, sql: str, **parametros: object) -> None:
    with motor.begin() as conexion:
        assert conexion.execute(text(sql), parametros).rowcount >= 1


def test_inv12_inv13_sin_diferencias_despues_de_operar_por_los_comandos(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
) -> None:
    """Escenario «Sin diferencias después de operar»; cubre CST-13 con compras, anulaciones de
    compra (con y sin recálculo), stock inicial y anulación de venta."""
    compras, ventas = dos_organizaciones

    resultados = _correr(app_mantenimiento_engine)

    assert {r.organizacion_id for r in resultados} == {compras.org, ventas.org}
    assert all(r.diferencias == 0 and r.error is None for r in resultados)
    for organizacion_id in (compras.org, ventas.org):
        ((resultado, diferencias, ejecutada_en),) = _resultados(
            app_mantenimiento_engine, organizacion_id
        )
        assert (resultado, diferencias, ejecutada_en) == ("SIN_DIFERENCIAS", [], AHORA)


def test_inv13_un_saldo_de_cuenta_alterado_se_informa_y_no_se_corrige(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
) -> None:
    """Escenario «Un saldo de cuenta alterado…»; ADR-015: nunca se corrige. Además INV-02: la
    diferencia de B no aparece en el resultado de A."""
    compras, ventas = dos_organizaciones
    _alterar(
        app_migrations_engine,
        "UPDATE saldo_cuenta SET saldo = saldo + 7.50 WHERE organizacion_id = :o",
        o=ventas.org,
    )

    _correr(app_mantenimiento_engine)

    ((resultado, diferencias, _),) = _resultados(app_mantenimiento_engine, ventas.org)
    assert resultado == "CON_DIFERENCIAS"
    (detalle,) = diferencias
    assert detalle["tipo"] == "SALDO_CUENTA"
    assert detalle["cuenta_tipo"] == "CLIENTE"
    esperado = Decimal(detalle["suma_del_libro"])
    assert Decimal(detalle["saldo_materializado"]) == esperado + Decimal("7.50")
    assert isinstance(detalle["saldo_materializado"], str)
    with app_migrations_engine.connect() as conexion:
        saldo = conexion.execute(
            text("SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o"), {"o": ventas.org}
        ).scalar_one()
    assert saldo == esperado + Decimal("7.50")
    ((resultado_a, diferencias_a, _),) = _resultados(app_mantenimiento_engine, compras.org)
    assert (resultado_a, diferencias_a) == ("SIN_DIFERENCIAS", [])


def test_inv12_un_saldo_de_stock_alterado_se_informa_con_producto_y_ubicacion(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
) -> None:
    _, ventas = dos_organizaciones
    _alterar(
        app_migrations_engine,
        "UPDATE stock_saldo SET cantidad_base = cantidad_base + 3 WHERE organizacion_id = :o",
        o=ventas.org,
    )

    _correr(app_mantenimiento_engine)

    ((resultado, diferencias, _),) = _resultados(app_mantenimiento_engine, ventas.org)
    assert resultado == "CON_DIFERENCIAS"
    saldos = [d for d in diferencias if d["tipo"] == "STOCK_SALDO"]
    assert saldos
    for d in saldos:
        assert d["producto_id"] and d["ubicacion_id"]
        assert d["materializado"] == d["esperado"] + 3


def test_adr039_un_stock_total_alterado_se_informa_sin_ubicacion(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
) -> None:
    compras, _ = dos_organizaciones
    _alterar(
        app_migrations_engine,
        "UPDATE costo_producto SET stock_total = stock_total + 11 "
        "WHERE organizacion_id = :o AND producto_id = :p",
        o=compras.org,
        p=compras.vino_id,
    )

    _correr(app_mantenimiento_engine)

    ((resultado, diferencias, _),) = _resultados(app_mantenimiento_engine, compras.org)
    assert resultado == "CON_DIFERENCIAS"
    (detalle,) = diferencias
    assert detalle["tipo"] == "STOCK_TOTAL"
    assert detalle["producto_id"] == str(compras.vino_id)
    assert detalle["ubicacion_id"] is None
    assert detalle["materializado"] == detalle["esperado"] + 11


def test_cst13_un_promedio_distinto_del_ultimo_movimiento_de_costo_se_informa(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
) -> None:
    compras, _ = dos_organizaciones
    with app_migrations_engine.connect() as conexion:
        vigente = conexion.execute(
            text(
                "SELECT costo_promedio FROM costo_producto "
                "WHERE organizacion_id = :o AND producto_id = :p"
            ),
            {"o": compras.org, "p": compras.vino_id},
        ).scalar_one()
    _alterar(
        app_migrations_engine,
        "UPDATE costo_producto SET costo_promedio = costo_promedio + 5 "
        "WHERE organizacion_id = :o AND producto_id = :p",
        o=compras.org,
        p=compras.vino_id,
    )

    _correr(app_mantenimiento_engine)

    ((resultado, diferencias, _),) = _resultados(app_mantenimiento_engine, compras.org)
    assert resultado == "CON_DIFERENCIAS"
    (detalle,) = diferencias
    assert detalle["tipo"] == "PROMEDIO_COSTO"
    assert detalle["producto_id"] == str(compras.vino_id)
    assert Decimal(detalle["promedio_vigente"]) == vigente + 5
    assert Decimal(detalle["promedio_historia"]) == vigente


def test_cst13_un_promedio_sin_historia_se_informa(
    dos_organizaciones: tuple[EntornoDeCompras, EntornoAnulacion],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
) -> None:
    """Segundo caso de la comparación (4): un promedio cargado a mano en un producto sin ningún
    movimiento de costo no tiene con qué coincidir."""
    compras, _ = dos_organizaciones
    with app_migrations_engine.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
                "stock_total, actualizado_en) VALUES (:o, :p, 99.5, 0, :m)"
            ),
            {"o": compras.org, "p": compras.cerveza_id, "m": AHORA},
        )

    _correr(app_mantenimiento_engine)

    ((_, diferencias, _),) = _resultados(app_mantenimiento_engine, compras.org)
    (detalle,) = [d for d in diferencias if d["tipo"] == "PROMEDIO_COSTO"]
    assert detalle["producto_id"] == str(compras.cerveza_id)
    assert detalle["promedio_vigente"] == "99.500000"
    assert detalle["promedio_historia"] is None


def test_la_verificacion_de_un_ingreso_sin_recalculo_no_da_falsos_positivos(
    sesion_real: Session, app_mantenimiento_engine: Engine
) -> None:
    """CST-12: una transferencia y un ajuste positivo suben el stock total sin tocar el promedio
    ni dejar historia; la comparación (4) sigue en cero diferencias."""
    entorno = EntornoDeStock(sesion_real)
    transferencia_id = entorno.transferir([(entorno.vino_id, 10)])
    ajuste_id = entorno.ajustar([(entorno.agua_id, 4)])
    entorno.anular_transferencia(transferencia_id)  # su inverso tampoco recalcula
    entorno.anular_ajuste(ajuste_id)
    assert sesion_real.is_active

    (resultado,) = _correr(app_mantenimiento_engine)

    assert resultado.diferencias == 0 and resultado.error is None


def test_cst13_la_anulacion_sin_recalculo_deja_el_promedio_y_la_historia_coincidentes(
    sesion_real: Session, app_mantenimiento_engine: Engine
) -> None:
    """CMP-06: anular la única compra deja el stock en cero; el promedio se mantiene y la fila
    de historia repite el anterior. La comparación (4) lo acepta."""
    entorno = EntornoDeCompras(sesion_real, permisos=PERMISOS_DE_COMPRAS)
    compra_id = _compra_de_vino(entorno, cantidad="10", valor="6000.00")
    entorno.anular(compra_id)
    assert entorno.stock_total(entorno.vino_id) == 0

    (resultado,) = _correr(app_mantenimiento_engine)

    assert resultado.diferencias == 0 and resultado.error is None
