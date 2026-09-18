# ADR-015 — Tablas de saldo materializadas, orden global de bloqueo y verificación de consistencia

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §7 y §19, `docs/03` §7 y §12 |

## Contexto

El stock y los saldos de cuentas se modifican concurrentemente. Sumar movimientos bajo concurrencia no da resultados consistentes sin bloquear todas las filas del historial.

## Decisión

Se mantienen tablas de saldo (`stock_saldo`, `saldo_cuenta`, `costo_producto`) actualizadas en la misma transacción que cada movimiento. Son las filas que se bloquean para serializar operaciones concurrentes.

`costo_producto` también mantiene `stock_total` (suma de `stock_saldo` del producto en todas las ubicaciones) para que el recálculo del promedio use un stock consistente sin sumar filas bajo concurrencia.

**Orden global de bloqueo** (toda transacción con varios bloqueos los adquiere en este orden, por clave ascendente dentro de cada nivel):
1. `saldo_cuenta`
2. `costo_producto`
3. `stock_saldo`
4. `jornada`

Los handlers no bloquean filas directamente; usan funciones de los servicios que respetan este orden.

**Verificación diaria:** una tarea compara cada tabla de saldo con la suma de su libro. Una diferencia se registra como error crítico y se notifica. Nunca se corrige automáticamente.

## Consecuencias

- Los libros (`stock_movimiento`, `cuenta_movimiento`) son la verdad (INV-12, INV-13). Las tablas de saldo son materializaciones verificables, no la fuente de verdad.
- El orden global de bloqueo elimina deadlocks entre operaciones concurrentes del mismo tipo. Las pruebas de concurrencia verifican los escenarios críticos.
- Una diferencia detectada por la verificación diaria indica un defecto de código; no se tapa con una corrección automática.
