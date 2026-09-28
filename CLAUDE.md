# CLAUDE.md

Instrucciones operativas para el agente. Léelas completas antes de cualquier acción.
Las reglas de negocio están en `docs/`; este archivo no las duplica.

---

## 1. Qué es este proyecto

Sistema de gestión para una distribuidora de bebidas y alimentos: venta en ruta con soporte offline, stock por ubicación, precios versionados, costos promedio y cuentas corrientes.

**Documentación fuente de verdad** (leer antes de implementar cualquier capacidad):

| Archivo | Contenido |
| --- | --- |
| `docs/00-vision-y-alcance.md` | Qué entra en cada etapa, principios, criterios de aceptación |
| `docs/01-dominio.md` | Reglas de negocio con ID estable (`VTA-12`, `INV-13`, etc.), invariantes, máquinas de estado, permisos |
| `docs/02-arquitectura.md` | Stack, pipeline de comandos, transacciones, sincronización, pruebas, despliegue |
| `docs/03-modelo-de-datos.md` | Tablas, tipos, restricciones, índices |
| `docs/04-roadmap-changes.md` | Orden de construcción, hitos, dependencias, definición de terminado |
| `docs/adr/` | Decisiones de arquitectura |

**Prioridad de fuentes:** `docs/adr/` > `docs/00` a `docs/04`.
Si al implementar surge una decisión que `docs/` no resuelve, **detente**, registra un ADR en `docs/adr/` y espera confirmación antes de continuar.

---

## 2. Stack

| Capa | Herramienta |
| --- | --- |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x síncrono, Pydantic v2, Alembic |
| Base de datos | PostgreSQL 17+ |
| Frontend | React, TypeScript strict, Vite, Tailwind CSS, React Router |
| Estado remoto | TanStack Query (solo área `/admin`) |
| Base local | Dexie/IndexedDB (solo área `/ruta`) |
| Formularios | React Hook Form + Zod |
| PWA | vite-plugin-pwa (Workbox) |
| Nota de venta | pdfmake |
| Dinero frontend | decimal.js |
| Contenedores | Docker, Docker Compose |
| Proxy | Caddy |

---

## 3. Comandos

### Desarrollo

```bash
docker compose up            # levanta PostgreSQL + backend + frontend
docker compose up -d db      # solo la base
```

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

alembic upgrade head         # aplicar migraciones
alembic revision --autogenerate -m "descripcion"    # nueva migración
python -m pytest             # todas las pruebas
python -m pytest tests/unit  # solo unitarias
python -m pytest tests/integration    # requiere Docker
python -m pytest tests/concurrency    # requiere Docker
python -m pytest tests/properties     # Hypothesis
python -m ruff check .       # lint
python -m ruff format .      # formato
python -m mypy app           # tipos
python -m import_linter      # límites entre módulos
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # desarrollo
npm run build        # build de producción
npm run typecheck    # tipos
npm run lint         # ESLint
npm run test         # Vitest
npm run test:e2e     # Playwright (requiere entorno levantado)
```

### Fixtures compartidos

```bash
# Desde la raíz — corre los mismos casos en Python y TypeScript
python -m pytest backend/tests/fixtures_compartidos/
cd frontend && npm run test -- tests/unit/calculo
```

---

## 4. Reglas no negociables

Estas reglas no se discuten ni se omiten. Si una implementación las viola, es un error.

### Dinero

- **NUNCA** `float`, `double`, `real` ni `money` de PostgreSQL para importes, costos o porcentajes.
- Backend: `Decimal` de Python siempre; redondeo solo desde `core/money.py` con `ROUND_HALF_UP`.
- Frontend: `decimal.js` siempre; redondeo solo desde `lib/money.ts`.
- API: importes, costos y porcentajes viajan como **string** en JSON (`"31250.00"`).
- Columnas: `NUMERIC(14,2)` para importes, `NUMERIC(18,6)` para costos por unidad base, `NUMERIC(9,6)` para porcentajes y alícuotas.
- Cantidades en unidad base: `integer` siempre.

### Base de datos

- Todo cambio de esquema va en una migración de Alembic. Nunca `create_all` fuera de tests.
- Las tablas de libro (`cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov`, `auditoria`) son de solo inserción. El usuario de aplicación **no tiene** `UPDATE` ni `DELETE` sobre ellas.
- Ninguna operación confirmada se borra. Las correcciones usan movimientos inversos.
- Todo dato de negocio tiene `organizacion_id`. Toda consulta lo filtra. Sin excepciones.
- Las claves foráneas entre entidades de negocio son compuestas e incluyen `organizacion_id`.
- Carga de relaciones siempre explícita; la carga diferida implícita está desactivada.
- Reportes y saldos se calculan con SQL en la base. Nunca se traen filas a Python para sumar.

### Arquitectura

- Toda escritura de negocio pasa por el bus de comandos. No existen endpoints de escritura que lo esquiven.
- Un módulo usa a otro solo a través de su `service.py`. No importa modelos ni repositorios ajenos.
- Los handlers no hacen `commit`. La transacción la gestiona el bus.
- `domain/` no importa FastAPI, SQLAlchemy ni nada de infraestructura.
- `organizacion_id` se toma siempre del token JWT, nunca del cuerpo de la petición.
- Un recurso de otra organización responde 404, no 403.

### Identificadores y tiempo

- Claves primarias: UUIDv7.
- `timestamptz` para todos los momentos.
- El backend obtiene la hora desde un componente de reloj inyectable (`core/clock.py`), no desde `datetime.now()` directamente.

### Pruebas

- Las de integración usan PostgreSQL real (Testcontainers). Nunca SQLite.
- Las de concurrencia confirman sus transacciones; no usan rollback externo.
- Todo invariante de `docs/01-dominio.md` §20 tiene al menos una prueba que lo cita por ID.
- Todo cambio en una regla de cálculo actualiza los fixtures compartidos antes de tocar el código.

---

## 5. Convenciones de código

### Python

- Tipado estricto en todo el código nuevo. Sin `Any` sin justificación.
- Funciones de dominio puras: reciben datos, devuelven resultados o lanzan excepciones de dominio. Sin efectos secundarios.
- Errores de dominio: clases propias que heredan de una base `DomainError`, con código estable.
- Endpoints síncronos (`def`, no `async def`).
- Nombres en español para entidades de negocio (igual que la base). Infraestructura en inglés está bien.

### TypeScript

- `strict: true` siempre.
- Sin `any`. Si los tipos generados desde el OpenAPI no cubren algo, se amplían, no se ignoran.
- Los importes nunca se convierten a `number` para calcular; solo para formatear.
- Los componentes no contienen lógica de negocio. La lógica vive en `domain/` o en hooks.

### Git

- **NUNCA** hacer `git push` sin instrucción explícita.
- **NUNCA** hacer `git commit` sin instrucción explícita.
- **NUNCA** modificar archivos en `docs/referencia/`.
- **NUNCA** modificar archivos en `openspec/changes/archive/`.
- `git add` y `git status` están permitidos para mostrar el estado.
- Los mensajes de commit siguen Conventional Commits: `feat(ventas): confirmar venta online`.
- Cada change termina en un commit (o pocos commits) con el número y slug del change.

---

## 6. Cómo trabajar un change de OpenSpec

1. Leer `docs/04-roadmap-changes.md` para entender el change en curso y sus dependencias.
2. Leer los documentos de `docs/` relevantes para ese change.
3. Usar el comando `/opsx propose` para generar la proposal.
4. **Esperar revisión humana antes de implementar.** La proposal no es un permiso para empezar.
5. Una vez aprobada, seguir `tasks.md` en orden.
6. Al terminar, verificar la definición de terminado de `docs/04-roadmap-changes.md` §2.1.
7. Archivar el change con `/opsx archive`.
8. Si durante la implementación surgió una decisión nueva, registrarla como ADR en `docs/adr/`.

**No generar proposals de changes futuros** hasta que el change actual esté archivado.

---

## 7. Estructura del backend

```
backend/app/
├── core/          # config, db, seguridad, errores, logging, money.py, clock.py, ids.py
├── commands/      # bus, sobre, registro de handlers, idempotencia
└── modules/
    └── <modulo>/
        ├── api.py         # routers FastAPI
        ├── schemas.py     # Pydantic entrada/salida
        ├── commands.py    # handlers (casos de uso de escritura)
        ├── queries.py     # casos de uso de lectura
        ├── domain/        # lógica pura, sin dependencias de infraestructura
        ├── models.py      # SQLAlchemy
        ├── repository.py  # acceso a datos del módulo
        └── service.py     # interfaz pública para otros módulos
```

---

## 8. Qué hacer si algo no está claro

En orden:

1. Buscar en `docs/01-dominio.md` por el identificador de regla (`VTA-`, `INV-`, `CRE-`, etc.).
2. Buscar en el ADR correspondiente en `docs/adr/`.
3. Buscar en `docs/02-arquitectura.md` si es una pregunta técnica.
4. Si después de buscar sigue sin resolverse: **preguntar antes de inventar una solución**.

No se toman decisiones de negocio por cuenta propia. No se simplifica una regla porque parece redundante. No se omite una restricción porque complica la implementación.
