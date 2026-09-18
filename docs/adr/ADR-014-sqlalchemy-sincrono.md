# ADR-014 — SQLAlchemy 2.x en modo síncrono

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §3.4 y §19 |

## Contexto

FastAPI soporta tanto endpoints síncronos (`def`) como asíncronos (`async def`). SQLAlchemy 2.x tiene una API síncrona y una asíncrona. La elección afecta a todos los archivos del backend.

## Decisión

Endpoints síncronos (`def`) con `Session` de SQLAlchemy (no `AsyncSession`). FastAPI ejecuta los `def` en un pool de hilos.

## Consecuencias

- Las relaciones se cargan de forma explícita en los repositorios; la carga diferida implícita está desactivada en los modelos.
- Las pruebas de concurrencia usan `ThreadPoolExecutor` estándar.
- El límite de concurrencia es el pool de hilos de FastAPI (configurable) y el pool de conexiones de SQLAlchemy, suficiente para el volumen esperado.
- Cambiar a async en el futuro no requiere tocar `domain/`; solo repositorios, handlers y la configuración de la sesión.

## Alternativas consideradas

- **async FastAPI + AsyncSession:** mejor para miles de conexiones simultáneas. Descartado porque el cuello de botella es la base de datos (bloqueos de fila), no el servidor, y async agrega el error frecuente de `MissingGreenlet` al acceder a relaciones no precargadas.
