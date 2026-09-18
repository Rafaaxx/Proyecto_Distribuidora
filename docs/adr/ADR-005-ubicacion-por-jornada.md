# ADR-005 — Ubicación asignada por jornada y política de stock negativo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §8 |

## Contexto

Varios vendedores operan offline sobre distintos vehículos. Sin señal, cada teléfono solo ve su copia local del stock. Si dos dispositivos operan sobre la misma ubicación, pueden vender más de lo que hay.

## Decisión

Cada vehículo es una ubicación. Durante una jornada, solo el dispositivo que la tomó puede generar movimientos sobre ella (índice único parcial en la base). Esto elimina el conflicto de stock entre dispositivos offline por diseño.

**Stock negativo online:** bloqueado salvo permiso `PERMITIR_STOCK_NEGATIVO`, que acepta con observación.

**Ventas offline:** nunca se rechazan al sincronizar por reglas de negocio. Si el resultado deja stock negativo, se acepta con observación STOCK_NEGATIVO.

Un supervisor con `LIBERAR_UBICACION` puede forzar la liberación de una jornada, con auditoría. Los comandos posteriores de esa jornada se aceptan con observación JORNADA_LIBERADA.

## Consecuencias

- El límite de crédito entre dos vendedores que atienden al mismo cliente sigue siendo un conflicto posible; se acepta con observación (CRE-09).
- Dos personas en el mismo vehículo requieren dos ubicaciones con carga separada.
- Las ventas de depósito (mostrador, PC) son siempre online y no tienen conflicto offline.

## Alternativas consideradas

- **Sin asignación, conflictos resueltos al sincronizar:** obliga a manejar stock negativo como caso frecuente y complica la rendición. Descartado.
