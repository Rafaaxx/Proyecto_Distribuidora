"""Unitarias del mapeo de `stock/models.py` y `costeo/models.py` (tarea 2.1).

No tocan la base: miran la metadata declarada. Que coincida con la migración lo
prueba `tests/integration/test_modelos_coinciden_con_migracion.py`
(`alembic revision --autogenerate` sin diferencias).

Reglas citadas: STK-01, STK-03, CST-10, CST-13, INV-02, INV-04 y `design.md` D7
(ubicación), D10 (claves de los saldos), D12 (`dispositivo_id` no nulable,
`jornada_id` sin FK).
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Integer, Numeric, inspect

from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock.models import StockMovimiento, StockSaldo, Ubicacion

TODOS = (Ubicacion, StockSaldo, StockMovimiento, CostoProducto, CostoProductoMov)


def _fks_por_nombre(modelo: type) -> dict[str, tuple[str, ...]]:
    tabla = modelo.__table__  # type: ignore[attr-defined]
    return {
        c.name: tuple(e.parent.name for e in c.elements)
        for c in tabla.constraints
        if isinstance(c, ForeignKeyConstraint)
    }


def test_las_tablas_se_llaman_como_en_03() -> None:
    assert [m.__tablename__ for m in TODOS] == [  # type: ignore[attr-defined]
        "ubicacion",
        "stock_saldo",
        "stock_movimiento",
        "costo_producto",
        "costo_producto_mov",
    ]


def test_los_saldos_tienen_clave_compuesta_que_empieza_por_la_organizacion() -> None:
    """ADR-035 punto 6, D10."""
    assert [c.name for c in inspect(CostoProducto).primary_key] == [
        "organizacion_id",
        "producto_id",
    ]
    assert [c.name for c in inspect(StockSaldo).primary_key] == [
        "organizacion_id",
        "producto_id",
        "ubicacion_id",
    ]


def test_el_libro_exige_el_dispositivo_y_deja_la_jornada_sin_fk() -> None:
    """D12: `dispositivo_id` `NOT NULL`; `jornada_id` nulable y sin FK hasta el
    change 15."""
    columnas = StockMovimiento.__table__.columns  # type: ignore[attr-defined]

    assert columnas["dispositivo_id"].nullable is False
    assert columnas["jornada_id"].nullable is True
    assert not columnas["jornada_id"].foreign_keys
    assert not any("jornada_id" in cols for cols in _fks_por_nombre(StockMovimiento).values())


def test_los_costos_son_numeric_18_6_y_las_cantidades_integer() -> None:
    """`CLAUDE.md` §4, INV-03, INV-04."""
    movimiento = StockMovimiento.__table__.columns  # type: ignore[attr-defined]
    costo = CostoProducto.__table__.columns  # type: ignore[attr-defined]
    historia = CostoProductoMov.__table__.columns  # type: ignore[attr-defined]

    for columna in (
        movimiento["costo_unitario"],
        costo["costo_promedio"],
        historia["costo_ingreso"],
        historia["promedio_anterior"],
        historia["promedio_nuevo"],
    ):
        assert isinstance(columna.type, Numeric)
        assert (columna.type.precision, columna.type.scale) == (18, 6)

    for columna in (
        movimiento["cantidad_base"],
        StockSaldo.__table__.columns["cantidad_base"],  # type: ignore[attr-defined]
        costo["stock_total"],
        historia["cantidad"],
        historia["stock_anterior"],
        historia["stock_nuevo"],
    ):
        assert isinstance(columna.type, Integer)


def test_el_promedio_es_nulable_hasta_el_primer_ingreso() -> None:
    """D10."""
    assert CostoProducto.__table__.columns["costo_promedio"].nullable is True  # type: ignore[attr-defined]
    assert CostoProductoMov.__table__.columns["promedio_anterior"].nullable is True  # type: ignore[attr-defined]
    assert CostoProductoMov.__table__.columns["promedio_nuevo"].nullable is False  # type: ignore[attr-defined]


def test_toda_fk_a_una_entidad_de_negocio_es_compuesta_con_la_organizacion() -> None:
    """`CLAUDE.md` §4, INV-21."""
    esperadas = {
        StockMovimiento: {
            "fk_stock_movimiento__producto": ("organizacion_id", "producto_id"),
            "fk_stock_movimiento__ubicacion": ("organizacion_id", "ubicacion_id"),
            "fk_stock_movimiento__usuario": ("organizacion_id", "usuario_id"),
            "fk_stock_movimiento__dispositivo": ("organizacion_id", "dispositivo_id"),
            "fk_stock_movimiento__motivo": ("organizacion_id", "motivo_id"),
        },
        StockSaldo: {
            "fk_stock_saldo__producto": ("organizacion_id", "producto_id"),
            "fk_stock_saldo__ubicacion": ("organizacion_id", "ubicacion_id"),
        },
        CostoProducto: {"fk_costo_producto__producto": ("organizacion_id", "producto_id")},
        CostoProductoMov: {"fk_costo_producto_mov__producto": ("organizacion_id", "producto_id")},
        Ubicacion: {"fk_ubicacion__actualizado_por": ("organizacion_id", "actualizado_por_id")},
    }
    for modelo, esperado in esperadas.items():
        fks = _fks_por_nombre(modelo)
        assert {n: c for n, c in fks.items() if n in esperado} == esperado, modelo


def test_ningun_modelo_declara_relaciones() -> None:
    """`CLAUDE.md` §4: sin carga diferida implícita."""
    for modelo in TODOS:
        assert not inspect(modelo).relationships, modelo


def test_el_id_de_los_libros_y_de_la_ubicacion_se_genera_con_uuid_v7() -> None:
    """`CLAUDE.md` §4: claves primarias UUIDv7 (`core/ids.py`)."""
    for modelo in (Ubicacion, StockMovimiento, CostoProductoMov):
        generador = modelo.__table__.columns["id"].default  # type: ignore[attr-defined]
        assert generador is not None, modelo
        identificador = generador.arg(None)
        assert identificador.version == 7, modelo
