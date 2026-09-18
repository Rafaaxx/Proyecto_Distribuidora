# ADR-008 — Nota de venta y numeración por dispositivo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §11.1, `docs/02` §7.7 |

## Contexto

El vendedor necesita emitir un comprobante al cliente en el momento de la venta, incluso sin señal. La numeración debe ser única por organización sin depender de un servidor central.

## Decisión

El comprobante se llama "Nota de venta" con leyenda "Documento no válido como factura". Se genera en el dispositivo con pdfmake.

La numeración usa el prefijo del dispositivo (asignado por el servidor al registrarse) más un correlativo local (`V03-000142`). El bootstrap devuelve el último correlativo registrado; el dispositivo usa el mayor entre ese y el local para no repetir números si se borran los datos del navegador.

El comprobante se comparte con Web Share API; si no está disponible (escritorio), se descarga.

## Consecuencias

- El nombre y la leyenda exactos del comprobante se validan con el contador antes de implementar.
- Restricción única `(organizacion_id, numero)` en la base; una colisión en sync indica un defecto de consistencia, no un caso normal.
- La misma función genera el comprobante desde administración para reimpresión.
