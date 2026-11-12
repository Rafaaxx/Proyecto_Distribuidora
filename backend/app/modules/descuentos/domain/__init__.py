"""Dominio puro de `descuentos`: sin FastAPI, sin SQLAlchemy, sin el bus de comandos
(`CLAUDE.md` §4; ADR-004). El motor de descuentos (DSC-03 a DSC-07) vive acá y su gemela en
TypeScript en `frontend/src/domain/descuentos/`; ambas corren los casos de
`shared/fixtures/calculo/dsc-05-descuentos.json` (ADR-016)."""
