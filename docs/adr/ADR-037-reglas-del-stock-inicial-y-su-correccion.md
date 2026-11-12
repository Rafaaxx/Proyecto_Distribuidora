# ADR-037 — Reglas del stock inicial: cantidad con signo, corrección con otro stock inicial hasta la primera operación, contenido del comando y costo exacto positivo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-30 |
| Referenciado en | `openspec/changes/09-stock-y-costeo/design.md` D4, D5 y D6 y `specs/stock/stock-inicial`, `specs/costeo/costo-promedio`; `01-dominio.md` §6.2 (CST-11), §8.1 (STK-03, STK-05, propuesta STK-10) y §21 (stock inicial); `02-arquitectura.md` §6.5 y §7.4; ADR-002 (promedio ponderado móvil); ADR-034 (reglas del saldo inicial) |

**Decisiones D4, D5 y D6 (opción A en cada una) aprobadas por el usuario el 2026-09-30. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

`docs/` dice que el stock inicial es un ingreso que recalcula el promedio y se audita (`01` §21, CST-11), pero no dice cuántos stock iniciales admite un producto, cómo se corrige uno mal cargado (cantidad o costo) ni hasta cuándo, si una línea puede ser negativa, qué forma tiene el contenido del comando (unidad base o presentación; una línea o varias) ni si el costo puede ser cero. El libro no se edita (TR-06) y los ajustes recién llegan en el change 14 y no tocan el promedio (CST-12). Sin una regla, un costo mal cargado contaminaría el promedio para siempre.

Es el mismo problema que ADR-034 resolvió para el saldo inicial (CC-08), con la particularidad de que acá hay un segundo dato que corregir (el costo) y un promedio que depende de él.

## Decisión

1. **Varios `STOCK_INICIAL` por producto y ubicación, con cantidad con signo distinta de cero.** Una cantidad positiva es un ingreso con costo y recalcula el promedio (CST-11). Una cantidad negativa es una **corrección**: egresa al promedio vigente sin recalcularlo (mismo criterio que CST-12 para los egresos) y **no puede dejar negativo el saldo de la ubicación** (`STOCK_INSUFICIENTE`, 409, sin excepción por `PERMITIR_STOCK_NEGATIVO`: no hay excepción por permiso en una corrección de puesta en marcha).
2. **Hasta la primera operación.** Un stock inicial se admite solo mientras el producto **no tenga en la organización movimientos de otro tipo** (`PRODUCTO_CON_OPERACIONES`, 409). La comprobación se hace con la fila de costo del producto ya bloqueada, así que ningún movimiento de otro tipo puede colarse entre la lectura y la inserción. La restricción queda latente en este change (nadie escribe otros tipos todavía) y se prueba insertando el otro tipo por el servicio.
3. **Un costo equivocado se corrige llevando el stock total a cero con negativos y recargando.** Con `stock_total = 0` el promedio pasa a ser el costo del nuevo ingreso (CST-11). Un stock inicial en una ubicación no toca el promedio de otra: el promedio es único por producto y organización (CST-10).
4. **Se propone la regla STK-10** para `01` §8.1: "Un producto admite varios `STOCK_INICIAL`, con cantidad con signo; uno negativo egresa al promedio vigente sin recalcularlo y no deja negativo el saldo. Se admiten solo mientras el producto no tenga movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES`)." El texto exacto está en `propuesta-docs.md`.
5. **Contenido de `STOCK_INICIAL_REGISTRAR`** (una sola forma para la pantalla y para el change 10): `ubicacion_id` y `lineas` (1 a 200, el límite de D12 del change 06). Cada línea: `producto_id`, `cantidad_base` (entero distinto de cero, INV-04) y `costo_unitario` (cadena decimal, costo por unidad base; **obligatorio si la cantidad es positiva y prohibido si es negativa**). Un producto no se repite en el comando (`PRODUCTO_REPETIDO`). Es atómico (INV-01). El momento es el `occurred_at` del sobre. Cada movimiento guarda `origen_tipo = STOCK_INICIAL`, `origen_id = operation_id` del comando (no hay tabla de documento en `03`) y `costo_unitario` (el ingresado, o el promedio usado en un negativo). La pantalla ayuda a escribir cajas + unidades y las convierte a base con aritmética entera (CAT-08); no calcula costos: el servidor recalcula siempre (TR-10).
6. **El costo de un ingreso es una cadena decimal mayor que cero, con hasta 6 decimales, sin redondear** (TR-02), dentro de `numeric(18,6)`; si no, `COSTO_INVALIDO` (422). Cero no se admite: "valorizado" (`00` §6.1) exige valor y un cero arrastraría el promedio. Un número JSON como costo se rechaza (los costos viajan como cadena, `CLAUDE.md` §4).
7. **No se usan presentaciones en el comando**, así que no se congelan unidades y no interviene el verificador de INV-18.
8. **Auditoría:** una sola por comando, la del bus (ADR-022); el resultado no expone costos.

## Consecuencias

- Una puesta en marcha de unos cien productos es uno o pocos comandos; una línea equivocada se corrige con otra en sentido contrario, sin tipos de movimiento nuevos.
- Es una regla nueva (STK-10) y una extensión de CST-11 (egreso por stock inicial); ambas requieren que el usuario apruebe el texto de `propuesta-docs.md` antes de tocar `docs/01`.
- **Debe quedar registrado para el change 10:** la importación reutiliza `stock/service.py::registrar_stock_inicial` fila por fila con `IMPORTAR_DATOS` (ADR-036), hereda STK-10 y cada fila rechazada se traduce a su número de fila. **Pregunta abierta, no bloqueante:** si la importación necesita fechar el stock inicial al día de corte, se reabre el momento del movimiento (hoy, el `occurred_at` del sobre), como D5-C del change 08.
- Un stock inicial en un vehículo se acepta aunque el vehículo requiera toma: la validación de toma (STK-09) nace con `jornada`, en el change 15.
- Quedan sin cubrir, a propósito, las correcciones posteriores a la primera operación: las hacen los ajustes del change 14 (que no tocan el promedio, CST-12).

## Alternativas consideradas

- **Un único `STOCK_INICIAL` por producto y ubicación (índice único parcial), siempre positivo:** descartada: simple, pero un costo mal cargado contamina el promedio para siempre y la cantidad solo se corrige con ajustes del change 14.
- **Varios, solo positivos, sin restricción temporal:** descartada: igual que la anterior para el costo, y permite "stock inicial" después de operar, que no es puesta en marcha.
- **Líneas en presentación (`presentacion_id`, cantidad, valor por presentación, IVA, bonificación) convertidas con CST-02:** descartada: reutiliza CST-02 pero congela presentaciones (verificador de INV-18) y exige alícuota; más superficie para una carga de única vez.
- **Una línea por comando:** descartada: cien comandos y cien auditorías para una puesta en marcha.
- **`costo_unitario >= 0`** (mercadería bonificada): descartada: baja el promedio y la utilidad aparente; la bonificación en unidades es etapa 2 (DSC-10).
- **Costo con hasta 2 decimales:** descartada: pierde precisión para costos de unidad chica derivados de una caja.
