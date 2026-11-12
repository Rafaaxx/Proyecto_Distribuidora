## Qué resuelve este change

No existe todavía ningún código: no hay repositorio con estructura, ni entorno levantable, ni backend que responda.
Este change crea la base técnica sobre la que se construyen todos los changes siguientes (`04` §4: `01a` no depende de nada y `01b` depende de él).
Deja el monorepo de `02` §4 en pie, con `docker compose up` funcionando y un backend que responde `/salud` y `/version` con logs en JSON.

## Why

`04` §5 define `01a` como el primer change del Hito 1: sin estructura de repositorio, entorno de desarrollo reproducible y esqueleto de backend y frontend, ningún change posterior puede empezar. `02` §16.1 exige que `docker compose up` levante PostgreSQL, backend con recarga automática y frontend con Vite; `02` §17 exige logs estructurados en JSON con `request_id` desde el inicio, porque agregar el contexto de logging después obliga a reescribir cada handler.

## What Changes

- **Estructura de monorepo** exactamente como `02` §4: `backend/`, `frontend/`, `shared/fixtures/calculo/`, `infra/`, `docs/`, `openspec/`, `.github/workflows/`. Los directorios de módulos de `backend/app/modules/` se crean vacíos (con `__init__.py`) a medida que los changes los necesiten; este change solo crea `core/` y `commands/` como paquetes vacíos.
- **Gestión de dependencias** según `02` §3: `requirements.txt` con versiones exactas (`==`) generado por `pip freeze`, `requirements-dev.txt` que empieza con `-r requirements.txt`, `pyproject.toml` solo con configuración de herramientas (Ruff, mypy, pytest), `package-lock.json` versionado.
- **Docker Compose de desarrollo** (`docker-compose.yml`): PostgreSQL 17+, backend FastAPI con recarga automática, frontend Vite (`02` §16.1).
- **Backend FastAPI mínimo**: `app/main.py`, `core/config.py` (configuración por variables de entorno), `core/db.py` (motor y sesión SQLAlchemy 2.x síncrono con psycopg 3, carga diferida implícita desactivada), `core/clock.py` (reloj inyectable, `02` §9), `core/ids.py` (UUIDv7), `core/logging.py`.
- **Endpoints de sistema** bajo `/api/v1` (`02` §11, grupo Sistema): `GET /salud` que verifica la conexión con la base (`02` §17) y `GET /version`.
- **Logging estructurado en JSON con `request_id`** (`02` §17): middleware que asigna un `request_id` por petición y lo propaga al contexto de log. Los campos `operation_id`, organización, usuario y dispositivo quedan previstos en el formato pero se poblarán en los changes 03 y 04.
- **Alembic inicializado**: `alembic/` configurado contra la URL de la base, con una revisión base vacía que permite verificar `upgrade head` y `downgrade base` sobre una base limpia. Ninguna tabla de negocio (`02` §14: toda tabla llega por migración revisada).
- **Frontend Vite vacío**: React + TypeScript `strict: true`, Tailwind CSS, React Router con las rutas `/ruta` y `/admin` como placeholders cargados de forma diferida (`02` §13.1), ESLint y Vitest configurados sin pruebas de negocio.

## No incluye

- `core/money.py` y `lib/money.ts`, redondeo `ROUND_HALF_UP` y fixtures compartidos de cálculo → change **01b** (`04` §5).
- Testcontainers y la CI completa (lint, tipos, unitarias, integración, build) → change **01b**. Este change deja `.github/workflows/` creado pero vacío.
- Cualquier tabla, modelo o migración de negocio, autenticación, bus de comandos y `organizacion_id` → changes 02, 03 y 04.
- `docker-compose.prod.yml`, Caddy y backups → change **27a** (`04` §10). `infra/caddy/` e `infra/backup/` quedan como directorios vacíos.
- Service worker, PWA y Dexie → change 21.

## Capabilities

### New Capabilities
- `sistema/salud-y-version`: endpoints `GET /api/v1/salud` (verificación de conexión con la base) y `GET /api/v1/version`, según `02` §11 y §17.
- `sistema/logging-estructurado`: formato de log JSON con `request_id` por petición y las restricciones de `02` §17 sobre datos sensibles.

### Modified Capabilities
<!-- Ninguna: no existen specs previas en openspec/specs/. -->

## Reglas e invariantes

- **Invariantes de `01` §20 que cierra: ninguno.** Así lo indica `04` §5 para `01a`. INV-03 lo cierra `01b`.
- Reglas aplicadas de `02`: §3 (stack y dependencias exactas), §4 (estructura), §9 (reloj inyectable, UUIDv7, `timestamptz`), §11 (API bajo `/api/v1`, grupo Sistema), §14 (todo cambio de esquema por Alembic, sin `create_all` fuera de pruebas), §16.1 (entorno de desarrollo), §17 (observabilidad).
- **Fixtures compartidos:** este change no toca cálculo de precios, descuentos ni costos. Solo crea el directorio `shared/fixtures/calculo/` vacío; el arnés que los ejecuta llega en 01b.

## Decisiones no resueltas en `docs/`

Ninguna bloqueante. Dos puntos se resuelven con la opción más conservadora y quedan registrados aquí como supuestos; si el usuario prefiere otra, se ajusta antes de implementar:

- `02` §16.1 menciona "`make seed` o equivalente" para datos de ejemplo. No hay datos de negocio todavía, así que el comando de seed no se crea en este change.
- El origen de `/version` no está especificado en `docs/`. Se toma de una variable de entorno inyectada en el build, con valor `dev` por defecto.

## Impact

- Crea `backend/`, `frontend/`, `shared/`, `infra/`, `docker-compose.yml`, `.github/workflows/`, `README.md`. No modifica `docs/` ni `openspec/specs/`.
- Fija las versiones del stack de ADR-001 en `requirements.txt` y `package-lock.json`; todo change posterior hereda esas versiones.
- No hay API previa ni consumidores: sin cambios que rompan nada.
