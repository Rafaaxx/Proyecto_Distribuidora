# ADR-013 — Monolito modular con límites verificados por import-linter

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §5 y §19 |

## Contexto

El sistema tiene múltiples módulos de negocio con transacciones que los cruzan (una venta toca stock, costos, cuenta corriente y cobranzas). Se necesita un límite explícito entre módulos sin el costo operativo de microservicios.

## Decisión

Un solo backend desplegable (monolito) con módulos internos de límites explícitos. Un módulo usa a otro solo a través de su `service.py`; nunca importa sus modelos ni su repositorio directamente. `domain/` dentro de cada módulo no importa FastAPI, SQLAlchemy ni infraestructura.

import-linter verifica estas restricciones en CI. Una violación rompe el pipeline.

El módulo `reportes` es la única excepción: puede leer tablas de cualquier módulo con SQL de solo lectura.

## Consecuencias

- Los límites son verificables automáticamente, no solo una convención.
- Transacciones que cruzan módulos se coordinan en el handler del módulo que orquesta (normalmente `ventas`), usando los servicios de los demás módulos.
- Si aparece una dependencia circular, se resuelve moviendo lógica al módulo orquestador o registrando un ADR. No se rompe la regla.
- Migrar a microservicios en el futuro (si el volumen lo justifica) es más limpio con límites ya definidos.
