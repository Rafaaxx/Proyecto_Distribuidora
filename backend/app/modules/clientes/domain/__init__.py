"""Dominio puro de `clientes`: sin FastAPI, sin SQLAlchemy, sin el bus de
comandos (`CLAUDE.md` §4, `pyproject.toml`, contrato
`clientes-domain-no-infraestructura`).

Tres piezas, todas puras y sin acceso a datos:

- `ficha.py`: nombre, código y documento (CLI-01, CLI-05, TR-10, D1).
- `estado.py`: la máquina de estados de `01` §18 (CLI-02, CLI-04, CLI-06, D7).
- `credito.py`: los tres campos de crédito guardados sin resolver (CRE-01,
  CRE-03, CRE-06, CLI-03, D6, D8).

Nada acá consulta la base ni conoce `organizacion_id`: la unicidad la
sustentan los índices de la base (D1) y el filtro por organización es del
servicio. Las funciones reciben datos y devuelven datos o lanzan un error de
dominio con código estable."""
