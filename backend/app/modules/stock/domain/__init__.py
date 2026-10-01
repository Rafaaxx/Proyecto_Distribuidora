"""Dominio puro de `stock`: sin FastAPI, sin SQLAlchemy, sin el bus de comandos
(`CLAUDE.md` §4, `pyproject.toml`, contrato `stock-domain-no-infraestructura`).

- `ubicaciones`: STK-02 (tipo, `VEHICULO_REQUIERE_TOMA`, nombre) y la regla de
  desactivación (D7, D8).
- `movimientos`: catálogo de tipos (STK-03), líneas del stock inicial (D5, D6),
  corrección (D4), estados activos (D8) y la definición de saldo (STK-04,
  INV-12).
- `kardex`: límite, cursor y rango de fechas (D11) y los tipos de lectura.
- `errores`: errores de dominio con código estable.
"""
