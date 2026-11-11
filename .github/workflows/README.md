# CI

`ci.yml` implementa la CI de `docs/02-arquitectura.md` §15 en cada push y
pull request, con 6 jobs correspondientes a los pasos 1, 2, 4, 5 y 6 de esa
sección (agregados en el change `01b-dinero-fixtures-ci`):

1. Lint, formato y tipos del backend (`ruff check`, `ruff format --check`,
   `mypy`) y del frontend (`eslint`, `tsc`).
2. `import-linter` (límites entre módulos).
4. `pytest` unitarias + propiedades + fixtures compartidos, y `vitest run`.
5. `pytest tests/integration` contra PostgreSQL real levantado con
   Testcontainers (el runner de GitHub Actions trae Docker de fábrica) y, cada
   uno en un paso propio porque sus `conftest` chocan si se juntan,
   `pytest tests/infra` (change `27a`) y `pytest tests/concurrency` (change `28`).
6. `npm run build` (build de producción del frontend).

## Huecos deliberados, documentados y con dueño

- **Paso 3 de `02` §15 (tipos del cliente API actualizados desde el
  OpenAPI).** No hay generación de tipos con `openapi-typescript` todavía
  porque no existe cliente API en el frontend. Se agrega a este workflow
  cuando exista esa generación (ver `proposal.md` de `01b`, sección "No
  incluye").
- **Playwright en la rama principal (`02` §15). Cerrado en el change `28`.**
  Trabajo `aceptacion-playwright` (D16): solo en push a `main`; levanta el
  compose de producción con `npm run test:e2e`, y si falla sube
  `frontend/test-results` y `frontend/playwright-report` como artefacto
  (`trazas-de-aceptacion`). En las ramas de change se corre a mano antes de
  archivar.
- **Pruebas de concurrencia (`docs/02` §15: "Integración y concurrencia con
  Testcontainers"). Cerrado en el change `28`.** Corren en cada push (D12): paso
  `pytest concurrencia` del trabajo "5. Integración con Testcontainers", con
  `python -m pytest tests/concurrency`, separado del de integración porque
  sus `conftest` chocan si se juntan. Una falla hace fallar la verificación;
  una prueba intermitente no se ignora, es una carrera real.
