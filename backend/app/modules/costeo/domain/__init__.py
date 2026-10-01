"""Dominio puro de `costeo`: sin FastAPI, sin SQLAlchemy, sin el bus de
comandos (`CLAUDE.md` §4).

- `costo_promedio`: CST-11 (un ingreso con costo recalcula el promedio) y CST-12
  (un egreso no lo modifica), con decimal exacto y un único redondeo al final.
- `errores`: errores de dominio con código estable.
"""
