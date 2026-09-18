# ADR-012 — Pipeline único de comandos idempotentes

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §13, `docs/02` §6 |

## Contexto

El sistema opera online y offline. Sin esta decisión, la venta online y la offline serían dos implementaciones distintas, duplicando la lógica y garantizando inconsistencias.

## Decisión

Toda escritura de negocio (online u offline) es un comando con `operation_id` (UUIDv7 generado por el cliente), tipo, huella del contenido y metadatos. Ambos caminos (endpoint REST directo y lote de sincronización) construyen el mismo sobre y llaman al mismo bus, que ejecuta el mismo handler.

La idempotencia se garantiza con `INSERT … ON CONFLICT DO NOTHING` sobre `(organizacion_id, operation_id)`. Mismo ID + misma huella = devolver resultado original. Mismo ID + huella distinta = RECHAZADO (COMANDO_INCONSISTENTE).

En modo ONLINE, un error de dominio rechaza y la reserva se revierte (el ID puede reintentarse corregido). En modo OFFLINE, las reglas que no pueden rechazar producen observaciones.

El modo OFFLINE solo se admite por el endpoint de sincronización, con jornada abierta y dispositivo activo.

## Consecuencias

- El offline (change 22) es un agregado sobre la base: cola local, bootstrap y motor de sincronización. No requiere reescribir ninguna operación.
- La venta online ya nace como comando idempotente (change 18), así que el doble envío accidental no duplica datos.
- Versiones de comando: el servidor conserva handlers de toda versión que pueda estar en colas activas. Retirar una versión requiere verificar que no haya comandos pendientes de ella.
- Los handlers no hacen commit. La transacción la abre y cierra el bus.

## Alternativas consideradas

- **Dos implementaciones separadas (online y offline):** duplica la lógica de negocio y garantiza divergencia. Descartado.
- **Idempotencia en el handler con SELECT previo:** sujeto a condiciones de carrera bajo concurrencia. El INSERT con ON CONFLICT es atómico. Descartado.
