"""Dominio puro de `ventas`: sin FastAPI, sin SQLAlchemy, sin el bus de comandos
(`CLAUDE.md` §4; ADR-004). El motor de cálculo de la venta (VTA-04) vive acá y su gemela en
TypeScript en `frontend/src/domain/calculo.ts`; ambas corren los casos de
`shared/fixtures/calculo/vta-04-totales.json` (ADR-016)."""
