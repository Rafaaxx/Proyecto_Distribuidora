# Tareas — 01a fundacion-repo-base

Referencias: `docs/02-arquitectura.md` §3 (stack y dependencias), §4 (estructura), §9 (ids y reloj), §11 (API), §14 (Alembic), §16.1 (desarrollo), §17 (observabilidad); ADR-001; `docs/04-roadmap-changes.md` §2.1 (definición de terminado).

No se crea `design.md`: no hay decisión técnica que `docs/` no resuelva.

## 1. Estructura del monorepo

- [x] 1.1 Crear el árbol de directorios de `02` §4 en la raíz: `backend/`, `frontend/`, `shared/fixtures/calculo/`, `infra/caddy/`, `infra/backup/`, `.github/workflows/`. Verificable: `ls` de cada ruta coincide con el árbol de `02` §4 (excluidos los módulos de negocio, que llegan en sus changes).
- [x] 1.2 Crear `README.md` en la raíz con: qué es el proyecto, prerrequisitos, cómo levantar el entorno (`docker compose up`) y puntero a `docs/` como fuente de verdad. Verificable: un lector sigue el README y llega a la aplicación corriendo.
- [x] 1.3 Crear `.gitignore` (raíz, `backend/`, `frontend/`) y `.env.example` con las variables que consume el backend, sin valores reales. Verificable: `.env` real no aparece en `git status`; ningún secreto está versionado (`02` §16.2).

## 2. Backend: proyecto y dependencias

- [x] 2.1 Crear `backend/requirements.txt` con las dependencias de producción y versión exacta (`==`), generado con `pip freeze` desde un entorno virtual limpio: FastAPI, Pydantic v2, SQLAlchemy 2.x, psycopg 3, Alembic, uvicorn. Verificable: `pip install -r requirements.txt` en un venv vacío reproduce el entorno (`02` §3).
- [x] 2.2 Crear `backend/requirements-dev.txt` empezando con `-r requirements.txt` y agregando pytest, Ruff, mypy e import-linter con versión exacta. Verificable: `pip install -r requirements-dev.txt` instala ambas capas (`02` §3).
- [x] 2.3 Crear `backend/pyproject.toml` solo con configuración de herramientas (Ruff lint y formato, mypy estricto, pytest), sin dependencias. Verificable: `python -m ruff check .`, `python -m ruff format --check .` y `python -m mypy app` corren sin error de configuración (`02` §3.1).
- [x] 2.4 Crear los paquetes `backend/app/`, `backend/app/core/`, `backend/app/commands/`, `backend/app/modules/` con sus `__init__.py` vacíos, y `backend/tests/{unit,integration,concurrency,properties,fixtures_compartidos}/`. Verificable: `python -c "import app"` funciona y `python -m pytest` recoge 0 pruebas sin errores de importación (`02` §4).

## 3. Backend: núcleo

- [x] 3.1 Implementar `app/core/config.py`: configuración por variables de entorno con Pydantic Settings (URL de base, versión de aplicación, nivel de log, entorno). Verificable: prueba unitaria que construye la configuración desde variables de entorno y falla si falta la URL de base.
- [x] 3.2 Implementar `app/core/clock.py`: reloj inyectable que devuelve el momento actual en UTC (`timestamptz`), con una implementación fija para pruebas. Verificable: prueba unitaria que fija la hora y comprueba el valor devuelto (`02` §9).
- [x] 3.3 Implementar `app/core/ids.py`: generación de UUIDv7. Verificable: prueba unitaria que genera dos ids consecutivos y comprueba versión 7 y orden creciente (`02` §9).
- [x] 3.4 Implementar `app/core/db.py`: motor y fábrica de sesiones SQLAlchemy 2.x síncrono sobre psycopg 3, con carga diferida implícita desactivada en la configuración de mapeo y sin `create_all`. Verificable: prueba de integración de la tarea 8.1 abre una sesión y ejecuta `SELECT 1` (`02` §3.1, §14).

## 4. Backend: logging estructurado

- [x] 4.1 Implementar `app/core/logging.py`: formateador que emite un objeto JSON por línea con nivel, momento, mensaje y contexto; los campos `operation_id`, organización, usuario y dispositivo quedan declarados y vacíos. Verificable: prueba unitaria que captura una línea de log y la parsea como JSON con los campos esperados (spec `sistema/logging-estructurado`, `02` §17).
- [x] 4.2 Implementar el middleware de `request_id`: toma el encabezado de correlación si viene, si no genera uno; lo propaga al contexto de log de toda la petición y lo devuelve en la respuesta. Verificable: prueba que hace dos peticiones y comprueba que cada una tiene un `request_id` propio y que el encabezado entrante se respeta (spec, escenarios 1 a 3 de "Registros en JSON con `request_id`").
- [x] 4.3 Emitir el registro de fin de petición con método, ruta, código de estado y duración; y garantizar que ni credenciales ni tokens llegan al log. Verificable: pruebas que cubren el escenario "Registro de fin de petición" y los dos escenarios de "Datos sensibles fuera de los registros" (`02` §17, §18).

## 5. Backend: aplicación y endpoints de sistema

- [x] 5.1 Implementar `app/main.py`: aplicación FastAPI con el router de la versión 1 montado en `/api/v1`, el middleware de `request_id` y el logging configurado al arrancar. Verificable: el documento OpenAPI se genera sin error (spec `sistema/salud-y-version`, requisito "Contrato publicado en el OpenAPI").
- [x] 5.2 Implementar `GET /api/v1/salud` (endpoint síncrono `def`): ejecuta una consulta contra la base y responde `200` si conecta, `503` si no, sin exponer la cadena de conexión. Verificable: pruebas de los tres escenarios del requisito "Verificación de salud del servicio".
- [x] 5.3 Implementar `GET /api/v1/version`: devuelve la versión de aplicación de la configuración, o `dev` si no está definida. Verificable: pruebas de los dos escenarios del requisito "Consulta de la versión desplegada".

## 6. Alembic

- [x] 6.1 Inicializar `backend/alembic/` con `alembic.ini` y `env.py` leyendo la URL de base desde `app/core/config.py`, no desde el archivo `.ini`. Verificable: `alembic current` responde contra la base de desarrollo (`02` §14).
- [x] 6.2 Crear la revisión base vacía (sin tablas de negocio) que fija el punto de partida del historial. Verificable: `alembic upgrade head` y `alembic downgrade base` corren limpios sobre una base vacía, en ese orden y repetidos (`04` §2.1, criterio 4).

## 7. Frontend y entorno de desarrollo

- [x] 7.1 Crear el proyecto Vite en `frontend/` con React y TypeScript, `strict: true` en `tsconfig.json`, y `package-lock.json` versionado. Verificable: `npm run typecheck` y `npm run build` pasan (`02` §3.2, ADR-001).
- [x] 7.2 Configurar Tailwind CSS, ESLint y Vitest; crear los scripts `dev`, `build`, `typecheck`, `lint`, `test` en `package.json`. Verificable: `npm run lint` y `npm run test` terminan sin error con cero pruebas (`02` §3.2).
- [x] 7.3 Crear la estructura de `frontend/src/` de `02` §4 (`app/`, `areas/ruta/`, `areas/admin/`, `features/`, `domain/`, `sync/`, `lib/`, `components/ui/`) y `frontend/tests/{unit,e2e}/`, con React Router sirviendo `/ruta` y `/admin` como pantallas vacías cargadas de forma diferida. Verificable: navegar a `/ruta` y a `/admin` muestra cada pantalla y el bundle de administración no se descarga en `/ruta` (`02` §13.1).
- [x] 7.4 Escribir `docker-compose.yml` de desarrollo: PostgreSQL 17+ con volumen, backend con recarga automática y frontend con Vite, más el healthcheck del backend apuntando a `/api/v1/salud`. Verificable: `docker compose up` desde un clon limpio deja los tres servicios sanos (`02` §16.1).
- [x] 7.5 Dejar `.github/workflows/` creado y vacío, con una nota de que la CI completa llega en el change 01b. Verificable: el directorio existe y no hay workflow que falle por estar incompleto (`04` §5).

## 8. Pruebas de integración

- [x] 8.1 Escribir las pruebas de integración de este change contra la base de desarrollo levantada por Docker Compose: `/salud` con base disponible y con base caída, `/version`, y `alembic upgrade head` seguido de `downgrade base`. Verificable: `python -m pytest tests/integration` pasa con el entorno levantado. Nota: el arnés de Testcontainers llega en el change 01b (`02` §15); mientras tanto estas pruebas usan la base del Compose de desarrollo, nunca SQLite.

## 9. Verificación manual

- [x] 9.1 Desde un clon limpio: `docker compose up`, abrir `http://localhost:<puerto>/api/v1/salud` y `/api/v1/version` en el navegador, abrir `/ruta` y `/admin` en el frontend, y comprobar en la salida del backend que cada petición emitió una línea JSON con su `request_id`. Verificable a ojo; es el paso 5 de la definición de terminado (`04` §2.1). Verificado: `/api/v1/salud` → `{"estado":"ok"}`, `/api/v1/version` → `{"version":"dev"}`, frontend responde 200 en `/`, logs del backend emiten JSON con `request_id` UUIDv7 por petición. Además: `backend/requirements.txt` no tenía `pydantic-settings` (faltaba pese a estar instalado en el `.venv` local) — el build de Docker fallaba con `ModuleNotFoundError`; se agregó `pydantic-settings==2.15.0` y se reconstruyó la imagen.
