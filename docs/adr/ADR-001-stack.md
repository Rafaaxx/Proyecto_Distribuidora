# ADR-001 — Stack tecnológico

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/02` §3 |

## Contexto

El sistema requiere un backend transaccional con PostgreSQL, una aplicación web que funcione sin conexión en teléfonos y una base de datos sólida. El desarrollador tiene experiencia previa con Python/FastAPI, React/TypeScript y PostgreSQL.

## Decisión

- **Backend:** Python 3.12+, FastAPI con endpoints síncronos (`def`), SQLAlchemy 2.x en modo síncrono, Pydantic v2, Alembic para migraciones.
- **Base de datos:** PostgreSQL 17+.
- **Frontend:** React + TypeScript strict, Vite, Tailwind CSS, React Router.
- **PWA:** vite-plugin-pwa con Workbox.
- **Infraestructura:** Docker Compose, Caddy como proxy y TLS.
- **Gestión de dependencias:** pip con `requirements.txt` versionado exacto; npm con `package-lock.json`.

## Consecuencias

- Los tipos del frontend se generan desde el OpenAPI de FastAPI con openapi-typescript: único punto de definición del contrato.
- FastAPI ejecuta los endpoints `def` en un pool de hilos; suficiente para el volumen esperado.
- El modo síncrono de SQLAlchemy elimina errores de carga diferida en contexto asíncrono y simplifica las transacciones con bloqueos.
- Cambiar a async en el futuro no requiere tocar el dominio; solo repositorios y handlers.

## Alternativas consideradas

- **Node.js + NestJS:** permitiría compartir tipos entre back y front sin generación. Descartado porque el desarrollador domina Python y la generación desde OpenAPI resuelve lo mismo.
- **async FastAPI + AsyncSession:** mejor para miles de conexiones concurrentes. Descartado porque el límite de este sistema es la base de datos, no el servidor, y async agrega errores específicos de carga diferida.
