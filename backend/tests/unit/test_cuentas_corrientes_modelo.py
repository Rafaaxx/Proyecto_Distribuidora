"""Unitarias del mapeo de `cuentas_corrientes/models.py` (tarea 2.1).

No tocan la base: miran la metadata declarada. Que coincida con la migración lo
prueba `tests/integration/test_modelos_coinciden_con_migracion.py`
(`alembic revision --autogenerate` sin diferencias).

Reglas citadas: CC-01, CC-04 y `design.md` D6 (columnas generadas), D11 (clave
de `saldo_cuenta`), D14 (`dispositivo_id` no nulable).
"""

from __future__ import annotations

from sqlalchemy import Computed, ForeignKeyConstraint, inspect

from app.modules.cuentas_corrientes.models import CuentaMovimiento, SaldoCuenta


def _generadas(modelo: type) -> set[str]:
    tabla = modelo.__table__  # type: ignore[attr-defined]
    return {c.name for c in tabla.columns if isinstance(c.computed, Computed)}


def _fks_por_nombre(modelo: type) -> dict[str, tuple[str, ...]]:
    tabla = modelo.__table__  # type: ignore[attr-defined]
    return {
        c.name: tuple(e.parent.name for e in c.elements)
        for c in tabla.constraints
        if isinstance(c, ForeignKeyConstraint)
    }


def test_cliente_id_y_proveedor_id_son_columnas_generadas_en_las_dos_tablas() -> None:
    """D6-A: las calcula PostgreSQL, SQLAlchemy no las inserta."""
    assert _generadas(CuentaMovimiento) == {"cliente_id", "proveedor_id"}
    assert _generadas(SaldoCuenta) == {"cliente_id", "proveedor_id"}


def test_el_libro_exige_el_dispositivo_y_no_guarda_saldo() -> None:
    """D14 (`NOT NULL`) y CC-04 (sin saldo acumulado por movimiento)."""
    columnas = CuentaMovimiento.__table__.columns  # type: ignore[attr-defined]

    assert columnas["dispositivo_id"].nullable is False
    assert "saldo" not in columnas
    assert columnas["importe"].type.precision == 14
    assert columnas["importe"].type.scale == 2


def test_el_saldo_tiene_clave_compuesta_que_empieza_por_la_organizacion() -> None:
    """D11-A."""
    clave = [c.name for c in inspect(SaldoCuenta).primary_key]

    assert clave == ["organizacion_id", "cuenta_tipo", "entidad_id"]


def test_toda_fk_a_una_entidad_de_negocio_es_compuesta_con_la_organizacion() -> None:
    """`CLAUDE.md` §4, INV-21."""
    esperadas = {
        "fk_cuenta_movimiento__usuario": ("organizacion_id", "usuario_id"),
        "fk_cuenta_movimiento__dispositivo": ("organizacion_id", "dispositivo_id"),
        "fk_cuenta_movimiento__cliente": ("organizacion_id", "cliente_id"),
        "fk_cuenta_movimiento__proveedor": ("organizacion_id", "proveedor_id"),
    }
    fks = _fks_por_nombre(CuentaMovimiento)
    assert {n: c for n, c in fks.items() if n in esperadas} == esperadas
    assert _fks_por_nombre(SaldoCuenta)["fk_saldo_cuenta__cliente"] == (
        "organizacion_id",
        "cliente_id",
    )


def test_ningun_modelo_declara_relaciones() -> None:
    """`CLAUDE.md` §4: sin carga diferida implícita."""
    assert not inspect(CuentaMovimiento).relationships
    assert not inspect(SaldoCuenta).relationships
