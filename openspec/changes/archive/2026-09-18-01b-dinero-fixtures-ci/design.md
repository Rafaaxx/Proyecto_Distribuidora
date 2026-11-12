## Context

Ver `proposal.md` — Why. Estado actual relevante: `01a` dejó el backend con pytest, ruff, mypy e import-linter configurados; las pruebas de integración apuntan a la base de Docker Compose vía `DATABASE_URL` (`backend/tests/integration/conftest.py`); `.github/workflows/` está vacío a propósito; `shared/fixtures/calculo/`, `backend/tests/fixtures_compartidos/` y `backend/tests/properties/` existen con `.gitkeep`; el frontend usa Vitest con jsdom y no tiene `decimal.js`.

`docs/02` §10 y §15 fijan el qué. Lo que `docs/` no resuelve y este documento decide: cómo llega el mismo archivo de fixtures a dos ecosistemas de pruebas distintos, cómo se levanta PostgreSQL en integración, y si Playwright entra en la CI de este change.

## Goals / Non-Goals

**Goals:**
- Un único punto de redondeo por lado, con firmas equivalentes, verificable por comparación directa entre ambos.
- Un arnés de fixtures que hoy corre con un caso semilla y mañana absorbe PRC-22, DSC-05, VTA-04 y CRE-01..08 sin reescribirse.
- Integración reproducible en cualquier máquina con un motor de contenedores, sin depender de que Docker Compose esté arriba.

**Non-Goals:**
- Definir la forma de `entrada`/`salida_esperada` para reglas de negocio que aún no existen: el arnés trata esos bloques como datos opacos y los pasa al motor que el caso declare.
- Optimizar el tiempo de CI (hoy la suite es trivialmente corta).

## Decisions

### D1 — Cómo consumen las dos suites el mismo `shared/fixtures/calculo/`

- **A) Lectura directa del directorio desde ambas suites.** pytest resuelve `shared/fixtures/calculo/` relativo a la raíz del repo; Vitest hace lo mismo con un `import.meta.glob` o `fs.readdirSync` sobre una ruta resuelta desde la raíz. Consecuencia: cero build intermedio, cero artefacto que se desincronice; a cambio, ambas suites dependen de la estructura del repo y el frontend lee fuera de `frontend/` (requiere agregar la ruta a `server.fs.allow`/`test.includeSource` de Vite si corriera en navegador; con jsdom y `fs` no hace falta).
- **B) Copiar los fixtures a cada suite en un paso previo.** Un script de `pretest` copia los JSON. Consecuencia: aísla cada suite, pero introduce una copia que puede quedar vieja y viola el "viven una sola vez" de `02` §10.4 en espíritu.
- **C) Publicar los fixtures como paquete npm local + módulo Python.** Consecuencia: limpio a largo plazo, desproporcionado para un monorepo de un solo desarrollador y agrega dos empaquetados que mantener.

**Decisión: A.** Es la lectura literal de `02` §10.4 ("los casos viven una sola vez"). El costo es una constante de ruta en cada suite, resuelta desde el archivo de la propia prueba hacia arriba, no desde el directorio de trabajo (para que `pytest` y `vitest` funcionen invocados desde cualquier lado). No amerita ADR: es una decisión de arnés, subordinada a ADR-016.

### D2 — Ciclo de vida del contenedor de PostgreSQL en integración

- **A) Un contenedor por sesión de pytest, migraciones una vez, aislamiento por transacción revertida.** Consecuencia: arranque único (~2-5 s), y coincide con la regla de `02` §15 ("las pruebas de integración aíslan con una transacción revertida al final de cada prueba"). Las de concurrencia, que sí confirman, necesitarán su propia limpieza explícita — previsto pero sin uso hasta el change 04.
- **B) Un contenedor por prueba.** Aislamiento perfecto, tiempo de CI inaceptable ya con pocas decenas de pruebas.
- **C) Seguir usando la base de Docker Compose vía `DATABASE_URL`.** Sin arranque, pero no reproducible en CI ni entre máquinas, y `04` §5 pide explícitamente "Testcontainers funcionando".

**Decisión: A**, con un escape: si `DATABASE_URL` viene definida en el entorno, el arnés la usa en lugar de levantar un contenedor. Eso mantiene el flujo rápido del desarrollador con Compose arriba y deja CI en Testcontainers. Si no hay `DATABASE_URL` ni motor de contenedores, las pruebas fallan con mensaje explícito — nunca caen a SQLite (`02` §15).

### D3 — Playwright en este change

- **A) Diferirlo hasta que exista un flujo de UI real.** Hoy el frontend son dos rutas placeholder; una suite E2E no verificaría nada y agregaría al pipeline el arranque de Compose y la descarga de navegadores.
- **B) Instalarlo ahora con una prueba de humo ("la app carga y `/salud` responde").** Deja el andamiaje listo, pero introduce mantenimiento y tiempo de CI por una aserción que las pruebas de integración y la unitaria de rutas ya cubren.
- **C) Instalarlo ahora con la suite completa de `00` §9.** Imposible: esos criterios describen flujos que no existen.

**Decisión: A — se difiere.** `02` §15 pide Playwright "en la rama principal, además", y el roadmap asigna la suite de los 12 criterios de `00` §9 al change 28 (`aceptacion-y-endurecimiento`). El change 20 (`nota-de-venta`) cierra el primer flujo de punta a punta realmente verificable; ahí es donde conviene introducir Playwright. Este change deja `frontend/tests/e2e/.gitkeep` en su lugar y lo documenta en el README de workflows, para que el hueco quede visible y no se olvide. Criterio conservador: no se agrega herramienta sin sujeto que probar. No amerita ADR — no cambia ninguna decisión de arquitectura, solo el momento de adopción dentro del roadmap ya escrito.

### D4 — Contrato de las funciones de redondeo

Ambos lados exponen `redondear_importe` (2 decimales) y `redondear_costo` (6 decimales), nombres tomados literalmente de `02` §10.1. Aceptan `Decimal`/`Decimal.Value` o cadena; rechazan `float`/`number` con error explícito (INV-03). No se agrega una tercera función para porcentajes: `03` §2.2 los define como `numeric(9,6)` y `02` §10.1 los agrupa con los costos; ambos cuantizan a 6 decimales, así que `redondear_costo` los cubre sin ambigüedad de escala. La diferencia entre `numeric(18,6)` y `numeric(9,6)` es de precisión total, no de redondeo, y se resuelve en la definición de cada columna.

## Risks / Trade-offs

- **Vitest leyendo fuera de `frontend/`** → Se lee con `fs` en entorno Node/jsdom, no a través del grafo de módulos de Vite, evitando restricciones de `server.fs`. Si en el futuro el arnés corre en navegador, habrá que agregar la ruta a `server.fs.allow`.
- **Testcontainers exige Docker en CI y en la máquina del desarrollador** → El escape por `DATABASE_URL` cubre el desarrollo local; el runner de GitHub Actions trae Docker de fábrica.
- **El caso semilla es trivial y podría dar falsa sensación de cobertura** → La spec de `calculo-compartido` exige que una suite que no descubre ningún caso falle, así que el arnés no puede quedar mudo cuando lleguen los casos reales.
- **Divergencia silenciosa entre `money.py` y `money.ts`** → Se mitiga con casos compartidos de redondeo puro que ambos lados ejecutan sobre el mismo vector de entradas, no solo con pruebas paralelas escritas a mano.
- **Paso 3 de CI de `02` §15 (tipos del cliente API) queda sin implementar** → Se documenta explícitamente en `proposal.md` y en el README de workflows; entra cuando exista generación de tipos desde el OpenAPI.

## Migration Plan

No hay datos ni esquema que migrar: el change no agrega tablas. La revisión base de Alembic existente sigue siendo la cabeza; la prueba de INV-03 se ejecuta sobre la base migrada y hoy pasa trivialmente por ausencia de columnas de negocio, quedando armada para el change 02.

## Open Questions

- Ninguna que bloquee. Se deja registrada una inconsistencia menor entre documentos, no bloqueante para este change: `02` §10.1 agrupa los porcentajes en `numeric(18,6)` mientras `03` §2.2 los define como `numeric(9,6)`. La escala de redondeo (6 decimales) coincide en ambos, por lo que no afecta a `money.py` ni a `money.ts`; conviene unificar la redacción cuando el change 02 defina las primeras columnas de porcentaje.
