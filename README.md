# Distribuidora — sistema de gestión

Sistema de gestión para una distribuidora de bebidas y alimentos: venta en ruta
con soporte offline, stock por ubicación, precios versionados, costos
promedio y cuentas corrientes.

La documentación funcional y técnica completa vive en [`docs/`](docs/) y es la
única fuente de verdad del proyecto. Antes de leer o modificar código, leer:

- [`docs/00-vision-y-alcance.md`](docs/00-vision-y-alcance.md) — alcance y principios
- [`docs/01-dominio.md`](docs/01-dominio.md) — reglas de negocio
- [`docs/02-arquitectura.md`](docs/02-arquitectura.md) — stack y arquitectura
- [`docs/03-modelo-de-datos.md`](docs/03-modelo-de-datos.md) — modelo de datos
- [`docs/04-roadmap-changes.md`](docs/04-roadmap-changes.md) — roadmap de construcción

## Prerrequisitos

- Docker y Docker Compose
- Para desarrollo fuera de contenedores: Python 3.12+ y Node.js 20+

## Variables de entorno

Copiar `.env.example` a `.env` y ajustar los secretos antes de levantar el
entorno (`docker compose up` los necesita: no tienen valor por defecto).

Dos roles de PostgreSQL, no uno (INV-05, `ADR-020`, change 03):

- **`app_migrations`**: dueño del esquema. Solo lo usa Alembic para correr
  migraciones (`DATABASE_URL_MIGRATIONS`, leída directamente por
  `backend/app/core/alembic_url.py` — no es un campo de `Settings`).
- **`app_runtime`**: el único rol que usa la aplicación en runtime
  (`DATABASE_URL`, la única que conoce `backend/app/core/config.py`).
  Recibe permisos otorgados tabla por tabla en cada migración (nunca
  `UPDATE`/`DELETE` sobre tablas de libro, como `auditoria`).

`infra/postgres/init-app-roles.sh` crea los dos roles la primera vez que se
inicializa el volumen `postgres_data`, usando `APP_MIGRATIONS_DB_PASSWORD` y
`APP_RUNTIME_DB_PASSWORD` del `.env`. **En producción, estos dos valores y
`JWT_SECRET` se inyectan por separado y nunca comparten valor entre sí** ni
con `POSTGRES_PASSWORD` (que solo lo usa Postgres para su propio arranque).

Si ya tenías el entorno levantado antes de este change (un solo rol), el
script de arriba no corre solo sobre un volumen existente: hay que recrear
el volumen (`docker compose down -v` y volver a levantar) o crear los roles
a mano contra la base ya levantada, con el mismo SQL de
`infra/postgres/init-app-roles.sh` (`design.md` D3, Risks).

### Puesta en marcha (`python -m app.seed`)

Además de la organización inicial (change 02), la siembra crea las cinco
plantillas de rol (`01` §19) y un usuario `admin` con permisos de
Administrador. La contraseña del administrador sale de `ADMIN_PASSWORD`
(sin valor por defecto, tarea 8.13 del change 03): sin definirla, la
siembra falla antes de crear nada. Repetir la siembra nunca pisa la
contraseña de un administrador ya existente.

`ADMIN_PASSWORD` **no** está declarada en `environment:` del servicio
`backend` de `docker-compose.yml` (a diferencia de `JWT_SECRET` y las
contraseñas de los roles de base), así que ponerla en `.env` no alcanza
para que la vea el contenedor al correr la siembra: hay que pasarla con
`-e` en el propio comando `docker compose exec`:

```bash
docker compose exec -e ADMIN_PASSWORD=CAMBIAR_ESTA_CLAVE backend python -m app.seed
```

Para reiniciar el entorno con una contraseña de administrador distinta
(por ejemplo, si no se recuerda la anterior), no alcanza con volver a
correr la siembra (no pisa la contraseña existente): hay que recrear el
volumen de Postgres (`docker compose down -v`, vuelve a `docker compose up`
y a aplicar migraciones) y recién ahí sembrar de nuevo con el
`ADMIN_PASSWORD` nuevo.

## Cómo levantar el entorno

```bash
docker compose up
```

Esto levanta tres servicios:

- `postgres` — PostgreSQL 17+ con un volumen persistente y los dos roles de
  aplicación
- `backend` — FastAPI con recarga automática en `http://localhost:8000`
- `frontend` — Vite (React + TypeScript) en `http://localhost:5173`

Verificar que el backend responde (en PowerShell, `curl` es un alias de
`Invoke-WebRequest` — usar `curl.exe`; en bash, `curl` funciona tal cual):

```bash
curl.exe http://localhost:8000/api/v1/salud
curl.exe http://localhost:8000/api/v1/version
```

Aplicar migraciones (Alembic corre como `app_migrations`, nunca como
`app_runtime`):

```bash
docker compose exec backend alembic upgrade head
```

## Desarrollo del backend fuera de Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m pytest
```

Fuera de Docker, `alembic upgrade head` necesita `DATABASE_URL_MIGRATIONS`
en el entorno (o en `.env`), apuntando al rol `app_migrations` contra el
Postgres de `docker compose up -d postgres`. `python -m pytest` necesita
`DATABASE_URL` (rol `app_runtime`) para las pruebas que no levantan su
propio Testcontainers.

## Desarrollo del frontend fuera de Docker

```bash
cd frontend
npm install
npm run dev
```

## Estructura del repositorio

Ver `docs/02-arquitectura.md` §4 para el árbol completo del monorepo y la
justificación de cada carpeta.
