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

## Extensión (2026-09-21, change 04) — Serialización canónica de la huella

**Decisión confirmada, sin ADR nuevo (extiende esta misma):** la huella del contenido de un comando se calcula con JCS (RFC 8785, JSON Canonicalization Scheme) sobre el contenido, con los importes y porcentajes normalizados a la escala fija de su columna (`NUMERIC(14,2)` → siempre dos decimales, `NUMERIC(18,6)` → siempre seis) **antes** de serializar, y normalización Unicode NFC para todo texto. El servidor es la única autoridad: la huella que manda el cliente nunca se usa para decidir, solo la que calcula el servidor sobre el contenido recibido (SYN-01).

- **Por qué hacía falta esta extensión:** `02` §6.2 solo fijaba dos de las seis propiedades necesarias para que Python y TypeScript calculen bytes idénticos (claves ordenadas, decimales como texto). Las cuatro que faltaban — separadores, escape de no-ASCII, normalización Unicode, y si una clave ausente y una con valor nulo dan la misma huella — quedaban libradas a que cada lado eligiera igual por casualidad. JCS responde las seis con un estándar público, en vez de que el proyecto invente su propia norma.
- **Por qué es irreversible y por eso va acá y no en una convención de código:** una vez que un dispositivo tiene comandos encolados localmente con una huella calculada de una manera, cambiar el algoritmo invalida esa cola para siempre — el reenvío legítimo de una venta ya hecha se rechazaría como `COMANDO_INCONSISTENTE` (SYN-02), o peor, se aceptaría como una venta distinta.
- **Verificación obligatoria, parte de la definición de terminado de este change:** un juego de fixtures compartidos (`backend/tests/fixtures_compartidos/`) que corre los mismos casos (acentos, emoji, claves fuera de orden, valores nulos, anidamiento, y los decimales reales del dominio) en Python y en TypeScript y exige la misma huella hexadecimal en ambos. Sin este juego de fixtures en verde, el pipeline no se considera terminado.
- Implementación: change 04, `design.md` D1, tarea del grupo 3 de `tasks.md`.

## Extensión (2026-09-21, change 04) — Origen de un registro de auditoría y obligatoriedad de `operation_id`

**Decisión confirmada, sin ADR nuevo (extiende esta misma):** `auditoria` incorpora una columna `origen` (`COMANDO` | `SISTEMA`) con una restricción de verificación en la base: `operation_id` es no nulo si y solo si `origen = 'COMANDO'`. Todo registro que se origina en un comando del bus queda con su `operation_id` obligatorio, garantizado por la base y no por convención de código; todo registro que se origina fuera del bus (hoy, únicamente el inicio de sesión, que por diseño del change 03 queda permanentemente fuera del bus) se audita declarando `origen = 'SISTEMA'`, sin `operation_id` y sin inventar uno falso.

- **Por qué hacía falta esta extensión:** AUD-02 pedía `operation_id` "en cada registro", y el change 03 dejó la columna nulable con la nota explícita de que este change la cerraría. Pero el inicio de sesión audita (AUD-01) y nunca puede tener `operation_id` — ocurre antes de que exista una sesión que lo genere. Un `NOT NULL` liso sobre `operation_id` habría hecho imposible auditar el login.
- **Por qué no se generó un `operation_id` falso para el login:** un identificador inventado no correspondería a ningún comando real, no sería idempotente ni reenviable, y contaminaría la tabla `comando` por asociación si alguna vez se lo intentara cruzar. La columna `origen` deja la distinción explícita en vez de disfrazarla.
- **Efecto para toda escritura de negocio futura:** una operación que intentara escribir fuera del bus tendría que declararse `origen = 'SISTEMA'` para pasar la restricción de la base, lo que deja un rastro visible en el código y en la auditoría, en vez de colar un `operation_id` nulo sin que nadie lo note.
- **Migración:** los registros de auditoría existentes (todos del change 03, ninguno originado en un comando porque el bus no existía) se rellenan con `origen = 'SISTEMA'` en la misma revisión que agrega la columna.
- Implementación: change 04, `design.md` D2, tarea del grupo 9 de `tasks.md`.
