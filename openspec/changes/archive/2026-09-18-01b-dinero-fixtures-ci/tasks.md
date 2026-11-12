## 1. Dependencias

- [x] 1.1 Agregar `hypothesis` y `testcontainers[postgres]` a `backend/requirements-dev.txt` con versión fijada y verificar que `pip install -r requirements-dev.txt` resuelve limpio.
- [x] 1.2 Agregar `decimal.js` a las dependencias de producción de `frontend/package.json` (se usa en `src/lib/money.ts`, no solo en pruebas) y verificar que `npm run build` sigue pasando.

## 2. Fixtures compartidos (antes del cálculo, `02` §10.4)

- [x] 2.1 Definir el caso semilla `shared/fixtures/calculo/money-redondeo.json` con el formato de `02` §10.4 (`id`, `reglas`, `entrada`, `salida_esperada`), cubriendo desempate al medio positivo y negativo, cuantización a 2 y a 6 decimales, y la alícuota `0.210000` de `03` §2.2. `reglas` cita `INV-03`.
- [x] 2.2 Escribir el cargador compartido en `backend/tests/fixtures_compartidos/` que descubre `shared/fixtures/calculo/*.json` resolviendo la ruta desde el archivo de prueba (no desde el cwd), valida el formato del caso y falla nombrando archivo y campo faltante si está incompleto (spec `calculo-compartido`, escenario "caso con formato inválido").
- [x] 2.3 Parametrizar pytest por caso, con el `id` del caso en el nombre de la prueba, y hacer que la suite falle si el directorio no existe o si no descubre ningún caso.
- [x] 2.4 Escribir el cargador equivalente en `frontend/tests/unit/calculo/` leyendo con `fs` (entorno Node/jsdom, no a través del grafo de módulos de Vite, ver `design.md` D1), con las mismas validaciones y el mismo fallo cuando no descubre casos.
- [x] 2.5 Verificar manualmente que un caso con `salida_esperada` alterada hace fallar exactamente una de las dos suites nombrando el `id` del caso.

## 3. Redondeo en el backend

- [x] 3.1 Implementar `backend/app/core/money.py` con `redondear_importe` (2 decimales) y `redondear_costo` (6 decimales), usando `Decimal.quantize` con `ROUND_HALF_UP` pasado explícitamente en cada llamada, sin tocar el contexto decimal global (`02` §10.1).
- [x] 3.2 Hacer que ambas funciones rechacen `float` y cadenas no numéricas con un error de dominio explícito (spec `dinero-y-redondeo`, "Rechazo de entradas que no son dinero exacto").
- [x] 3.3 Conectar el cargador de fixtures del paso 2.2 a `core/money.py` para que el caso semilla se ejecute contra la implementación real en pytest.
- [x] 3.4 Escribir las unitarias de `money.py`: `0.125 → 0.13`, `-0.125 → -0.13`, `1.0000005 → 1.000001`, y los casos de error.
- [x] 3.5 Escribir en `backend/tests/properties/` la propiedad con Hypothesis: toda salida de `redondear_importe` tiene exactamente 2 decimales, y la de `redondear_costo` exactamente 6, para cualquier `Decimal` de entrada dentro del rango de `numeric(14,2)` / `numeric(18,6)`.

## 4. Redondeo en el frontend

- [x] 4.1 Implementar `frontend/src/lib/money.ts` configurando decimal.js con `ROUND_HALF_UP` y exponiendo `redondearImporte` y `redondearCosto` con el mismo contrato que el backend, más el parseo desde la cadena de la API y el formateo para mostrar (`02` §10.3).
- [x] 4.2 Hacer que las funciones rechacen `number` nativo con error explícito, de modo que ningún importe pueda entrar al cálculo como flotante binario (INV-03).
- [x] 4.3 Conectar el cargador de fixtures del paso 2.4 a `lib/money.ts` para que el caso semilla se ejecute contra la implementación real en Vitest.
- [x] 4.4 Escribir las unitarias de `money.ts` con los mismos valores del paso 3.4, para que la equivalencia entre lados sea comprobable leyendo ambos archivos.
- [x] 4.5 Verificar que `npm run typecheck` y `npm run lint` pasan sin `any` en `money.ts` ni en el cargador de fixtures.

## 5. Arnés de integración con Testcontainers

- [x] 5.1 Reescribir `backend/tests/integration/conftest.py` para levantar PostgreSQL real con Testcontainers una vez por sesión, con el escape de `design.md` D2: si `DATABASE_URL` está definida en el entorno, usarla en lugar de levantar contenedor.
- [x] 5.2 Aplicar las migraciones de Alembic sobre la base de la sesión antes de la primera prueba, y dejar la revisión base existente como cabeza (no se agrega migración nueva en este change).
- [x] 5.3 Proveer el aislamiento por transacción revertida al final de cada prueba de integración (`02` §15), y dejar documentado en el conftest por qué las de concurrencia no podrán usarlo.
- [x] 5.4 Hacer que la ausencia de motor de contenedores y de `DATABASE_URL` falle con mensaje explícito, nunca con un sustituto en memoria (spec `integracion-continua`, "No hay motor de contenedores disponible").
- [x] 5.5 Verificar que las pruebas de integración heredadas de `01a` (`test_alembic_integracion.py`, `test_sistema_integracion.py`) siguen pasando con el nuevo arnés.

## 6. Prueba de INV-03 sobre el catálogo de columnas

- [x] 6.1 Escribir en `backend/tests/integration/` la prueba que recorre `information_schema.columns` de los esquemas de la aplicación sobre la base migrada y falla si encuentra `real`, `double precision`, `float` o `money`, nombrando tabla y columna (`03` §2.2, `04` §5).
- [x] 6.2 Citar `INV-03` en el nombre o el docstring de la prueba, como exige `02` §15.
- [x] 6.3 Verificar la prueba en negativo: crear una tabla temporal con una columna `double precision` dentro de la prueba y comprobar que la verificación la detecta.

## 7. Integración continua

- [x] 7.1 Crear el workflow de GitHub Actions que corre en cada push y pull request, con los pasos de `02` §15: (1) ruff check + ruff format --check + mypy + eslint + tsc, (2) import-linter, (4) pytest unitarias + propiedades + fixtures compartidos y `vitest run`, (5) pytest integración con Testcontainers, (6) `npm run build`.
- [x] 7.2 Cachear dependencias de pip y npm para que la corrida sea razonable.
- [x] 7.3 Actualizar `.github/workflows/README.md`: dejar registrado que el paso 3 de `02` §15 (tipos del cliente API) entra cuando exista generación desde el OpenAPI, y que Playwright se difiere al change 20 según `design.md` D3.
- [x] 7.4 Verificar que un cambio deliberadamente roto (error de tipos, o fixture alterado) hace fallar la CI en el paso correspondiente, y revertirlo.

## 8. Verificación final

- [x] 8.1 Correr la suite completa en local: `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy app`, `lint-imports`, `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build`. Los 8 comandos pasan limpio. `lint-imports` fallaba por una condición preexistente de `01a` (el contrato tenía `ignore_imports` apuntando a módulos que todavía no existen bajo `app/modules/`, e import-linter falla ante un `ignore_imports` sin efecto): se movieron esas excepciones al change 05 (`catalogo`, primer módulo de negocio real) en `backend/pyproject.toml`, y se corrigió `include_external_packages = true` (requerido cuando `forbidden_modules` incluye paquetes externos como `fastapi`/`sqlalchemy`). El job `import-linter` de `.github/workflows/ci.yml` habría quedado en rojo en cada push sin este arreglo.
- [x] 8.2 Comprobar la definición de terminado de `04` §2.1 aplicable a este change: pruebas en CI, cada escenario de las tres specs con al menos una prueba, INV-03 citado por ID, Alembic sube y baja limpio.
- [x] 8.3 Verificación manual en el navegador: levantar `docker compose up`, abrir `/ruta` y `/admin` y confirmar que el frontend sigue cargando tras agregar `decimal.js` y `lib/money.ts`.
