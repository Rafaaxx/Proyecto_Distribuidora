# ADR-024 — Una categoría con productos activos no se puede desactivar (CAT-01, CAT-05)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-23 |
| Referenciado en | `openspec/changes/05-catalogo/design.md` D11; `01-dominio.md` CAT-01, CAT-05 |

**Aprobado por el usuario: la regla en `design.md` D11 el 2026-09-22, este ADR el 2026-09-23.**

## Contexto

`01-dominio.md` exige que todo producto tenga una categoría (CAT-01) y que una categoría inactiva no se ofrezca para asignar a productos (CAT-05), pero no dice qué pasa si se intenta desactivar una categoría que ya tiene productos activos asignados — es un vacío de negocio, no una pregunta que `01` resuelva ni por omisión ni por remisión a otra regla.

El change 05 (`design.md` D11) lo encontró al implementar `CATEGORIA_MODIFICAR` y lo resolvió como "supuesto a confirmar", aprobado por el usuario el 2026-09-22 dentro del propio `design.md`. La verificación del change (grupo 13, tarea 13.4) lo revisó con criterio más estricto: a diferencia de D9/D10/D12 (forma de API o UI), D11 fija una regla de negocio que otro change podría necesitar releer sin tener que ir a buscar una decisión de diseño de un change ya archivado — mismo criterio que ya se aplicó a D2 (ADR-023). Por eso se promueve a ADR en vez de dejarla solo en `design.md`.

La regla es asimétrica entre categoría y marca: CAT-01 exige categoría a todo producto (no hay producto sin categoría); marca es opcional (`producto.marca_id` nulable). Por eso el rechazo aplica solo a categoría — una marca inactiva no deja a ningún producto sin un campo obligatorio, así que sí se puede desactivar con productos asignados.

## Decisión

`CATEGORIA_MODIFICAR` con `activo=false` se rechaza con `CATEGORIA_CON_PRODUCTOS_ACTIVOS` si existe al menos un producto activo (`producto.activo = true`) de la misma `organizacion_id` con `categoria_id` igual a la categoría que se intenta desactivar. Desactivar una categoría sin productos activos asignados (ninguno, o todos ya inactivos) se acepta sin restricción.

`MARCA_MODIFICAR` con `activo=false` no tiene esta restricción: se acepta aunque existan productos activos con esa `marca_id`, porque `marca_id` es opcional (CAT-01 no la exige) y un producto con una marca inactiva sigue siendo válido — CAT-05 solo impide *asignar* una marca inactiva a un producto nuevo o al modificarlo, no retiene la asignación existente como inválida.

## Consecuencias

- Ningún producto activo queda con una categoría inactiva por efecto de `CATEGORIA_MODIFICAR` (consistente con CAT-01: categoría siempre obligatoria y, por CAT-05, siempre activa mientras el producto lo esté).
- El usuario que quiere reorganizar categorías debe primero desactivar o reasignar los productos activos de una categoría antes de poder desactivarla — sin mecanismo de reasignación masiva en este change; queda como fricción de operación conocida, no una limitación técnica nueva.
- La asimetría categoría/marca es intencional y documentada acá para que un change futuro que toque `MARCA_MODIFICAR` no la "corrija" por simetría sin releer este ADR.
- Sin cambio de esquema: la validación se hace en el handler de `catalogo/commands.py` contando productos activos por categoría, sin columna ni constraint nueva en `producto` ni `categoria`.

## Alternativas consideradas

- **Permitir desactivar la categoría y dejar productos activos con categoría inactiva.** Descartada: contradice CAT-05 directamente (una categoría inactiva no se ofrece/asigna) si se lee como invariante permanente y no solo como regla de alta; dejaría datos en un estado que ninguna otra regla de `01` contempla.
- **Desactivar la categoría en cascada, inactivando también sus productos.** Descartada: una escritura sobre `categoria` no debe tener el efecto secundario de modificar filas de `producto` fuera del comando que el usuario pidió — oculta el alcance real de la operación y complica la auditoría (¿qué comando inactivó el producto?).
- **Aplicar la misma restricción a `MARCA_MODIFICAR`.** Descartada por la asimetría de CAT-01: la marca es opcional, así que no hay invariante equivalente que proteger.
