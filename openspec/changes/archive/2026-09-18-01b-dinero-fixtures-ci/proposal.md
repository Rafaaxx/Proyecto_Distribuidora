## Qué resuelve este change

Instala la base de cálculo con dinero exacto (`core/money.py`, `lib/money.ts`), el arnés que ejecuta los fixtures compartidos en Python y TypeScript, Testcontainers para integración, y la CI que corre todo en cada push.

## Why

Todos los changes de negocio (02 en adelante) calculan importes, costos y porcentajes. Si el redondeo no está centralizado y probado desde ahora, cada módulo improvisa el suyo y la divergencia se descubre tarde. `docs/02` §10 exige un único módulo de redondeo por lado y que los casos de cálculo vivan una sola vez en `shared/fixtures/calculo/*.json`, ejecutados por pytest y por Vitest; `docs/02` §15 exige integración contra PostgreSQL real y una CI de 6 pasos. El change `01a` dejó explícitamente esos huecos abiertos (`.github/workflows/README.md`, `backend/tests/integration/conftest.py`).

## What Changes

- **`backend/app/core/money.py`**: `redondear_importe` (2 decimales) y `redondear_costo` (6 decimales) sobre `Decimal`, con `ROUND_HALF_UP` explícito en cada `quantize`. No se altera el contexto decimal global (redondea al par por defecto y no debe usarse para cuantizar, `02` §10.1).
- **`frontend/src/lib/money.ts`**: mismas funciones sobre decimal.js con `ROUND_HALF_UP`, más helpers de parseo desde string y de formateo para mostrar. Ningún importe se convierte a `number` para calcular (`02` §10.3). Se agrega la dependencia `decimal.js`.
- **Arnés de fixtures compartidos**: cargador de `shared/fixtures/calculo/*.json` en `backend/tests/fixtures_compartidos/` (pytest) y en `frontend/tests/unit/calculo/` (Vitest), parametrizado por caso y con el `id` del caso en el nombre de la prueba. Se agrega un caso semilla de redondeo puro (`MONEY-redondeo-medio`) que sólo ejercita `money`; los casos de negocio (PRC-22, DSC-05, VTA-04, CRE-01..08) llegan en sus changes.
- **Guardia de deriva**: si un fixture existe y una de las dos suites no lo ejecuta, la suite falla. Así el arnés no se queda mudo cuando lleguen los casos reales.
- **Testcontainers**: `backend/tests/integration/conftest.py` pasa a levantar PostgreSQL real con Testcontainers (nunca SQLite, `02` §15), con la base compartida por sesión y aislamiento por transacción revertida.
- **Hypothesis**: instalado y con una propiedad mínima sobre `money` (toda salida de `redondear_importe` tiene exactamente 2 decimales y respeta el desempate hacia arriba).
- **Prueba de INV-03**: recorre el catálogo de columnas de la base migrada (`information_schema`) y falla si aparece `real`, `double precision`, `float` o `money` en cualquier columna de negocio (`03` §2.2, `docs/04` §5).
- **CI en GitHub Actions**: lint, formato y tipos (backend y frontend), import-linter, unitarias + propiedades + cálculo compartido, integración con Testcontainers, build del frontend.

## No incluye

- Ninguna tabla ni módulo de negocio (empiezan en el change 02).
- El motor de cálculo de negocio (PRC-22, DSC-05, VTA-04, CRE-01..08): este change construye el arnés, no las reglas.
- Paso 3 de CI de `02` §15 (tipos del cliente API actualizados): no hay generación de tipos desde OpenAPI todavía; se agrega cuando exista.
- Suite de Playwright en rama principal: no hay flujo de UI real que probar (ver `design.md`).
- Pruebas de concurrencia: quedan habilitadas por el arnés, pero no hay escritura concurrente que probar hasta el change 04.

## Invariantes

- **INV-03** (ningún importe, costo o porcentaje se representa con punto flotante binario): lo cierra con la prueba de catálogo de columnas, con el redondeo centralizado en `Decimal`/decimal.js y con el lint que prohíbe `float` en dinero.

## Capabilities

### New Capabilities
- `sistema/dinero-y-redondeo`: contrato único de redondeo en backend y frontend, y prohibición de punto flotante binario en el esquema (INV-03).
- `sistema/calculo-compartido`: los casos de cálculo viven una sola vez en `shared/fixtures/calculo/` y los ejecutan pytest y Vitest.
- `sistema/integracion-continua`: qué verifica la CI en cada push y con qué base de datos.

### Modified Capabilities
(ninguna)

## Impact

- Código: `backend/app/core/money.py`, `backend/tests/{fixtures_compartidos,properties,integration}/`, `frontend/src/lib/money.ts`, `frontend/tests/unit/calculo/`, `shared/fixtures/calculo/`, `.github/workflows/`.
- Dependencias nuevas: `hypothesis` y `testcontainers[postgres]` en `requirements-dev.txt`; `decimal.js` en `frontend/package.json`.
- Docker requerido para `pytest tests/integration`.
