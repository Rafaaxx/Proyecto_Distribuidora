# CI

`ci.yml` implementa la CI de `docs/02-arquitectura.md` §15 en cada push y
pull request, con 6 jobs correspondientes a los pasos 1, 2, 4, 5 y 6 de esa
sección (agregados en el change `01b-dinero-fixtures-ci`):

1. Lint, formato y tipos del backend (`ruff check`, `ruff format --check`,
   `mypy`) y del frontend (`eslint`, `tsc`).
2. `import-linter` (límites entre módulos).
4. `pytest` unitarias + propiedades + fixtures compartidos, y `vitest run`.
5. `pytest tests/integration` contra PostgreSQL real levantado con
   Testcontainers (el runner de GitHub Actions trae Docker de fábrica).
6. `npm run build` (build de producción del frontend).

## Huecos deliberados, documentados y con dueño

- **Paso 3 de `02` §15 (tipos del cliente API actualizados desde el
  OpenAPI).** No hay generación de tipos con `openapi-typescript` todavía
  porque no existe cliente API en el frontend. Se agrega a este workflow
  cuando exista esa generación (ver `proposal.md` de `01b`, sección "No
  incluye").
- **Playwright en la rama principal (`02` §15: "En la rama principal,
  además: suite de Playwright").** Se difiere al change `20-nota-de-venta`
  (`design.md` de `01b`, decisión D3): hoy el frontend son dos rutas
  placeholder y no hay flujo de punta a punta real que verificar. Mientras
  tanto queda `frontend/tests/e2e/.gitkeep` como marcador visible del hueco.
- **Pruebas de concurrencia (`docs/02` §15: "Integración y concurrencia con
  Testcontainers").** El arnés de Testcontainers ya las soporta (ver el
  comentario en `backend/tests/integration/conftest.py` sobre por qué no
  pueden usar `db_session`), pero no hay escritura concurrente que probar
  hasta el change `04`. `backend/tests/concurrency/` sigue con `.gitkeep` y
  no se agrega un job de CI para un directorio vacío.
