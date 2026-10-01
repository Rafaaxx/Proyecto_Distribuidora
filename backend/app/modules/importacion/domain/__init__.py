"""Dominio puro de `importacion`: sin FastAPI, sin SQLAlchemy, sin el bus de
comandos (`CLAUDE.md` §4, `pyproject.toml`, contrato
`importacion-domain-no-infraestructura`).

Piezas, todas puras y sin acceso a datos:

- `valores`: conversión exacta de texto a decimal, entero, booleano y fecha
  (`design.md` D3, D12; INV-03, INV-04).
- `planilla`: columnas por tipo, encabezados, filas y límites del archivo
  (`design.md` D5, D6, D11, D13).
- `informe`: traducción de errores de dominio a errores de fila y el error
  agregado de la importación (`design.md` D1).
"""
