# ADR-004 — Motor de descuentos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §10 |

## Contexto

La distribuidora aplica descuentos por volumen (cajas, unidades o importe) y descuentos manuales controlados. Pueden aplicarse varias reglas a la vez.

## Decisión

Entre las reglas automáticas no acumulables se aplica solo la de mayor beneficio total (desempate por prioridad). Las marcadas como acumulables se aplican en orden de prioridad, cada una sobre el resultado anterior. El descuento manual se aplica sobre el resultado final con tope porcentual por rol; superar el tope requiere `AUTORIZAR_DESCUENTO` o PIN de supervisor.

Cada descuento se registra por línea con origen, regla, porcentaje, importe, motivo y autorizador.

El motor existe en Python (`modules/descuentos/domain/`) y en TypeScript (`domain/calculo.ts`), con casos compartidos en `shared/fixtures/calculo/`.

## Consecuencias

- El servidor recalcula y rechaza online si los descuentos difieren. Offline acepta con observación DESCUENTO_DIFIERE.
- Fidelización por historial, promociones por segmento y precio especial quedan para la etapa 2.
- El motor duplicado requiere mantener los fixtures compartidos sincronizados ante cualquier cambio de regla.

## Alternativas consideradas

- **Solo manual:** sin reglas automáticas. Descartado porque el cliente ya negocia descuentos por volumen.
- **Motor en servidor únicamente:** requeriría conexión para calcular el total. Incompatible con offline.
