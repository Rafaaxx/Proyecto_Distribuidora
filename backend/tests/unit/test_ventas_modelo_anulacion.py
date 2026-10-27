"""Tarea 4.1 (change 19, `design.md` D11): el modelo `VentaAnulacion` de `ventas`.

Que coincida con la migración `d9e0f1a2b3c4` lo cubre `test_modelos_coinciden_con_migracion.py`
(compara `Base.metadata` con el esquema real). Reglas citadas: VTA-20, INV-02, INV-05, CLAUDE.md
§4 (sin carga diferida implícita).
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint, inspect

from app.modules.ventas.models import Venta, VentaAnulacion


def test_venta_anulacion_no_declara_relaciones() -> None:
    """Carga explícita (`CLAUDE.md` §4): ni `VentaAnulacion` ni `Venta` tienen `relationship()`."""
    assert list(inspect(VentaAnulacion).relationships) == []
    assert list(inspect(Venta).relationships) == []


def test_inv02_venta_anulacion_lleva_organizacion_y_una_sola_anulacion_por_venta() -> None:
    tabla = VentaAnulacion.__table__
    assert tabla.name == "venta_anulacion"
    assert tabla.c.organizacion_id.nullable is False
    unicos = {
        c.name: tuple(col.name for col in c.columns)
        for c in tabla.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert unicos["ux_venta_anulacion__venta"] == ("organizacion_id", "venta_id")
    assert unicos["ux_venta_anulacion__org_id"] == ("organizacion_id", "id")


def test_devuelve_dinero_y_jornada_son_nulables_y_el_resto_no() -> None:
    columnas = VentaAnulacion.__table__.c
    nulables = {c.name for c in columnas if c.nullable}
    assert nulables == {"observacion", "devuelve_dinero", "jornada_id"}
