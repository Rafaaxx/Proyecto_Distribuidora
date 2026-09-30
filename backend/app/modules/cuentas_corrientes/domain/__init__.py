"""Dominio puro de `cuentas_corrientes`: sin FastAPI, sin SQLAlchemy, sin el
bus de comandos (`CLAUDE.md` §4, `pyproject.toml`, contrato
`cuentas-corrientes-domain-no-infraestructura`).

Piezas, todas puras y sin acceso a datos:

- `catalogo.py`: tipos de cuenta, sentidos y tipos de movimiento por cuenta
  (CC-02, CC-03, `design.md` D12).
- `importe.py`: validación del importe de un movimiento (CC-01, INV-03).
- `reglas.py`: efecto de un movimiento sobre el saldo (CC-04) y las reglas de
  D3 y D4 como funciones que reciben datos.
- `errores.py`: errores de dominio con código estable.
"""
