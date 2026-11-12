# ADR-065 — Conciliación del saldo y el stock locales, observaciones y rechazos en el teléfono, métricas de lote y cierre de INV-17

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-01 |
| Referenciado en | `openspec/changes/22c-stock-credito-locales-y-conflictos/design.md` D0 a D9 y `specs/sync/cola-local`, `specs/sync/bootstrap`, `specs/sync/lote-de-comandos`, `specs/sync/motor-de-sincronizacion`, `specs/ruta/area-de-ruta`, `specs/sistema/logging-estructurado`, `specs/sistema/ayuda-contextual`; `01-dominio.md` CRE-08, RUT-04, STK-06, SYN-04 a SYN-07, SYN-09, SYN-11, INV-01, INV-06, INV-17; `02-arquitectura.md` §6.4, §13.2, §13.4, §17; ADR-051, ADR-058, ADR-062, ADR-063, ADR-064 |

**Change 22c. Gobernanza MEDIA (ninguna decisión CRÍTICA ni ALTA). Decisiones D0 a D9 aceptadas con la opción A el 2026-11-02 (tarea 0.1); textos aprobados sin cambios (tarea 0.2). Vigente desde el archivo del change (2026-11-03).**

## Contexto

ADR-063 y ADR-064 dejaron al 22c conciliar los movimientos locales con un bootstrap posterior (hoy, tras sincronizar y actualizar los datos, el teléfono descuenta dos veces lo vendido) y mostrar el detalle de las observaciones y traducir los códigos de rechazo. ADR-058 le dejó habilitar `VENTA_ANULAR` sin conexión (VTA-24). `04` §11 suma métricas de tamaño de lote (`02` §17) y el cierre de INV-17 (SYN-05), y advierte que si el 22c se desborda hay que dividirlo. `docs/` no dice cómo saber qué operaciones locales ya incluye un bootstrap, qué hacer con una venta rechazada, cómo llega el detalle de las observaciones ni qué dice cada código.

## Decisión (aceptada, 2026-11-02: opciones A de `design.md`)

1. **Alcance (D0).** La anulación sin conexión (VTA-24) pasa a un change nuevo, **22d `anulacion-sin-conexion`**, que depende del 22c y va antes del 23. El 22c, en cuatro lotes.
2. **Conciliación (D1).** El bootstrap informa, en la misma foto que el stock y los saldos, la **secuencia procesada**: la mayor secuencia de los comandos registrados de la jornada del bootstrap, del usuario y del dispositivo de la sesión (nula si no hay). Un movimiento local de la jornada cuenta si su operación tiene una secuencia mayor. El bootstrap no toca `movimientos_locales`. Un bootstrap sin la marca cuenta todo.
3. **Rechazadas (D2).** Una venta rechazada sigue contando en el saldo y el stock locales de su jornada (lo conservador: la mercadería ya se entregó). Precisión aprobada 2026-11-02: cuenta **completa** (stock, débito y su cobro en el momento, mismo `operation_id`) hasta que termine la jornada; la cobranza suelta sin conexión (change 23) decidirá su propia regla.
4. **Observaciones (D3).** El resultado de cada ítem del lote trae sus observaciones (código, operación y detalle), también en el reenvío; el teléfono las guarda en `cola` en la misma transacción que el resultado, sin versión nueva de Dexie.
5. **Pantallas (D4).** Sin pantalla nueva: «Sincronización» resume y el detalle de la venta explica.
6. **Textos (D5).** Tabla cerrada de los 16 códigos de SYN-07 y de los rechazos posibles de una venta sin conexión, con el fixture `shared/fixtures/sync/codigos-de-sincronizacion.json` validado por el servidor y por el teléfono; un código desconocido muestra un texto general y el código.
7. **Disponibles en consulta (D6).** Stock, Productos y la ficha del cliente muestran los valores locales.
8. **Métricas (D7).** Un registro de cierre por lote con el reparto por resultado, el corte y la duración.
9. **INV-17 (D8).** Matriz de integración por cada regla de SYN-05, para la venta y la cobranza.
10. **Ayuda (D9).** Una clave nueva y cuatro revisadas, sin ejemplos.

## Precisiones del apply

- **Rechazada, completa (D2).** La venta rechazada cuenta con todo lo que lleva el mismo `operation_id`: el stock, el débito y su cobro en el momento. Si no, el cobro de la venta dejaría de restar del saldo y el cliente aparecería debiendo de más. Vale hasta que termine la jornada; la cobranza suelta sin conexión (change 23) decidirá su propia regla.
- **Operación fuera de la cola.** Un movimiento local cuya operación no está en `cola` sigue contando (no hay secuencia con la que compararlo).
- **Sin migración.** El servidor usa `ix_comando__org_dispositivo_secuencia`; el teléfono guarda la marca en `sesion` y las observaciones en `cola` sin versión nueva de Dexie. `estado_operacion` de los movimientos locales queda sin uso.
- **Ventas aceptadas antes del 22c.** No tienen observaciones guardadas: el detalle dice que no está en el teléfono y remite a administración (nunca se inventa un detalle).
- **Observaciones en el reenvío.** Un comando ya procesado devuelve sus observaciones registradas; el doble envío no las duplica (INV-06).
- **Prueba de punta a punta.** `FlujoConciliacion.test.tsx` recorre 63 botellas, venta de 15 sin red, envío con `STOCK_NEGATIVO`, «Actualizar datos» (48, sin descontar dos veces) y «Sincronizar» sin cambios.

## Consecuencias

- El saldo y el stock del teléfono son exactos después de actualizar los datos, aunque se pierda la respuesta de un lote.
- La regla de conciliación es por operación: la cobranza sin conexión (23) y la anulación (22d) solo suman movimientos.
- `02` §6.4 gana las observaciones en el resultado del lote; SYN-11 y `02` §13.2 la secuencia procesada; CRE-08 la regla de conciliación; `02` §17 el registro de cierre del lote.
- `04` §11 gana la fila del 22d.

## Alternativas consideradas

- **D0.** B: todo en el 22c (seis lotes, con la anulación sin conexión). Descartada: desborda el change (`04` §11 pide dividir).
- **D1.** B: ordenar sincronización y bootstrap en el teléfono (con la respuesta perdida la venta cuenta dos veces); C: lista de `operation_id` procesados (crece con cada venta y repite lo que la marca resume).
- **D2.** B: la rechazada deja de contar al recibir el rechazo (el teléfono ofrecería stock que ya no está en el vehículo y crédito ya usado).
- **D3.** B: lectura aparte por operación (sin señal no se ve; endpoint y permiso más); C: solo los códigos (no se entienden sin producto, medio ni autorizador).
- **D4.** B: pantalla nueva `/ruta/conflictos` (duplica «Sincronización»).
- **D5.** B: texto general y código para las observaciones (no se sabe qué se anotó).
- **D6.** B: Stock y la ficha quedan con los del bootstrap (contradicen a Vender después de la primera venta).
- **D7.** B: nada nuevo (el corte y el reparto solo se reconstruyen sumando líneas).
- **D8.** B: propiedad con Hypothesis (lenta contra la base real y difícil de leer qué regla falló).
- **D9.** B: sin ayudas nuevas ni revisadas (los textos actuales quedarían falsos).

## Deudas nominadas

- **Al 22d (D0 = A, aprobada):** `VENTA_ANULAR` sin conexión (VTA-24, ADR-058), con las decisiones listadas en `design.md` D0 opción B.

- **Saldadas por el 22c:** las de ADR-063 y ADR-064 «al 22c» (conciliación, detalle de las observaciones, traducción de los códigos, métricas de lote, cierre de INV-17). La de ADR-058 «al 22c» se reasigna al 22d.
