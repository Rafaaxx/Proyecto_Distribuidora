# ADR-016 — Motor de cálculo duplicado con fixtures compartidos obligatorios

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §10 y §19 |

## Contexto

El dispositivo necesita calcular sin conexión: precio de línea, descuentos, totales y evaluación de crédito. El servidor valida todo al sincronizar. Si los dos cálculos divergen, el vendedor ve un total distinto al que queda en la base.

## Decisión

El motor de cálculo existe en dos implementaciones:
- `backend/app/modules/ventas/domain/calculo.py` (y los módulos de dominio que use)
- `frontend/src/domain/calculo.ts`

Los casos de prueba viven una sola vez en `shared/fixtures/calculo/*.json` y los ejecutan tanto pytest como Vitest. Todo cambio en una regla de cálculo agrega o modifica casos compartidos **antes** de modificar el código. CI falla si cualquiera de las dos suites falla.

El redondeo usa `ROUND_HALF_UP` explícito en ambos lados (`core/money.py` y `lib/money.ts`).

## Consecuencias

- Cualquier divergencia entre lenguajes se detecta en CI, no en producción.
- El Python por defecto redondea con `ROUND_HALF_UP` al usar `quantize`, pero el contexto decimal global usa `ROUND_HALF_EVEN`. Por eso el redondeo se llama siempre desde `money.py` con el modo explícito.
- `decimal.js` usa `ROUND_HALF_UP` por defecto cuando se configura así; `lib/money.ts` lo establece al inicializar.
- El agente de IA es el vector de riesgo más probable de divergencia: cualquier cambio de lógica de cálculo debe incluir casos compartidos en el mismo commit.

## Alternativas consideradas

- **Calcular solo en el servidor:** requiere conexión para mostrar totales. Incompatible con offline.
- **Un servicio compartido (WASM o microservicio):** complejidad desproporcionada para el volumen.


## Enmienda del change 18a (ADR-054)

El motor de totales de la venta (bruto de línea, descuentos y totales VTA-04, modo impositivo A) vive en `backend/app/modules/ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts`, como orquestador puro que recibe por línea los valores ya resueltos. Para no depender de infraestructura, `ventas.domain` importa solo `precios.domain.bruto_de_linea` y `descuentos.domain.*`, las dos `ignore_imports` documentadas en `backend/pyproject.toml` (ADR-054 punto 23). Los casos compartidos están en `shared/fixtures/calculo/vta-04-totales.json` (`"motor": "vta04"`); los de crédito se agregan en el change 18b.
