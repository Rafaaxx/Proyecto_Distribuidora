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

## Cómo levantar el entorno

```bash
docker compose up
```

Esto levanta tres servicios:

- `postgres` — PostgreSQL 17+ con un volumen persistente
- `backend` — FastAPI con recarga automática en `http://localhost:8000`
- `frontend` — Vite (React + TypeScript) en `http://localhost:5173`

Verificar que el backend responde:

```bash
curl http://localhost:8000/api/v1/salud
curl http://localhost:8000/api/v1/version
```

## Desarrollo del backend fuera de Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m pytest
```

## Desarrollo del frontend fuera de Docker

```bash
cd frontend
npm install
npm run dev
```

## Estructura del repositorio

Ver `docs/02-arquitectura.md` §4 para el árbol completo del monorepo y la
justificación de cada carpeta.
