# ADR-044 — Reversión de un ingreso de compra y stock negativo solo en la anulación (enmienda de ADR-039)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-02 |
| Referenciado en | `openspec/changes/11-compras-y-deuda-proveedor/design.md` D9 y D10 y `specs/costeo/costo-promedio`, `specs/stock/libro-de-stock`, `specs/proveedores/anulacion-de-compras`; `01-dominio.md` CMP-05 a CMP-07, CST-11 a CST-13, STK-04; `02-arquitectura.md` §7.3 y §7.4; ADR-039 (puntos 3 y 8, que esta decisión enmienda); ADR-015 (orden de bloqueo) |

**Decisiones D9 y D10 (opción A en cada una) aprobadas por el usuario el 2026-10-02. Texto del ADR pendiente de aprobación; estado *Propuesto*. Enmienda el punto 3 de ADR-039 ("ningún camino deja saldo negativo") y resuelve la deuda anotada en sus consecuencias sobre la historia de costo de una `ANULACION_COMPRA`.**

## Contexto

ADR-039 hace de `stock/service.py::registrar_movimientos` el único camino para cambiar stock: un egreso se valoriza al promedio vigente, no lo cambia y nunca deja saldo negativo. Anular una compra (CMP-05) obliga a lo contrario: el egreso debe valorizarse al **costo de la línea**, revierte el ingreso en el promedio (CMP-06) y, con `PERMITIR_STOCK_NEGATIVO`, puede dejar el saldo bajo cero (CMP-07). Además CST-13 pide que la historia de costo sea reconstruible, y el change 09 dejó sin decidir qué guarda `costo_producto_mov` cuando la anulación no recalcula.

## Decisión

1. **Una sola puerta.** `registrar_movimientos` acepta egresos de tipo `ANULACION_COMPRA` **con** `costo_unitario` (el costo base de la línea; sin costo es `COSTO_INVALIDO`). Para ese tipo no llama a `aplicar_egreso` sino a la función nueva `costeo.revertir_ingreso`; los demás egresos (venta, ajuste, transferencia) siguen valorizándose al promedio vigente sin historia. El orden de bloqueo (ADR-039 punto 1, `02` §7.3) no cambia, y las líneas se revierten en orden inverso al de la compra.
2. **Reversión (CMP-06).** El cálculo vive en `costeo/domain` (`calcular_reversion`, función pura sin infraestructura). Con `S` el stock total de la organización del producto antes de revertir, `P` el promedio vigente, `q` la cantidad revertida y `c` el costo de la línea, el stock restante es `S - q` (se interpreta "stock restante" como stock total de la organización, porque el promedio es por organización, CST-10, y CST-11 usa ese mismo stock) y el promedio resultante es `(P·S - c·q) / (S - q)`, redondeado una sola vez a 6 decimales `ROUND_HALF_UP`. Si `S - q > 0` y el resultado es `> 0` se recalcula; en otro caso se **mantiene** `P` y la anulación queda con la observación `ANULACION_COMPRA_SIN_RECALCULO` (SYN-07). Dos redondeos a 6 decimales (el del ingreso y el de la reversión) hacen que la inversa no sea exacta: la propiedad admite una diferencia de `0.000001 × (S+q)/S`. Un producto sin promedio previo es `PROMEDIO_INCONSISTENTE`.
3. **Historia siempre.** Cada reversión escribe **una fila** de `costo_producto_mov` con `origen_tipo = ANULACION_COMPRA`, `cantidad` negativa, `costo_ingreso` = costo de la línea, stock anterior y nuevo, `recalculado` verdadero o falso y `promedio_nuevo = promedio_anterior` cuando no recalcula. Resuelve la deuda del change 09: el promedio se reconstruye con la historia (CST-13) y queda a la vista por qué no cambió.
4. **Stock negativo solo en la anulación (D10).** `registrar_movimientos` recibe `permitir_negativo: bool` (por defecto `False`; el handler lo pasa según `PERMITIR_STOCK_NEGATIVO`). **Solo tiene efecto para `ANULACION_COMPRA`** (para cualquier otro tipo se ignora y rige la condición de `02` §7.4); con `True`, el egreso que no alcanza se aplica sin la condición `cantidad_base >= :q` y el resultado marca la línea como negativa, lo que el handler informa con la observación `STOCK_NEGATIVO`. Sin permiso, el egreso que no alcanza es `STOCK_INSUFICIENTE` y nada queda escrito. Esto **enmienda el punto 3 de ADR-039**: ningún camino deja saldo negativo, salvo la anulación de compra con permiso.
5. **Reversión con producto inactivo.** Para `ANULACION_COMPRA` no se rechaza un producto inactivo (revertir no es una operación nueva, CAT-05, D11 del change 11); los demás tipos lo siguen rechazando. Una ubicación inactiva bloquea siempre.
6. **Fixtures compartidos.** Los casos de reversión se agregan a `cst-11-costo-promedio.json` antes de tocar el código y los corren pytest y Vitest (ADR-016).

## Consecuencias

- `stock_saldo.cantidad_base` puede ser negativo solo por una anulación con permiso; la verificación de consistencia (INV-12) lo trata como un saldo más y `STOCK_NEGATIVO` deja el aviso para quien lo regularice (ajuste, change 14).
- Un ingreso posterior sobre un saldo negativo se promedia con el stock total real (negativo incluido); no hay casos especiales en `aplicar_ingreso`.
- El kardex muestra el egreso de una anulación al costo de la línea original, no al promedio del momento.
- Cualquier tipo de movimiento futuro que necesite valorizarse a un costo propio (por ejemplo notas de crédito de proveedor, CMP-09) requiere un ADR nuevo; este no abre un mecanismo general.

## Alternativas consideradas

- **`stock.revertir_origen(origen_tipo, origen_id)` que lea los movimientos originales (B de D9):** descartada: acopla el libro de stock a un origen y a líneas que no son suyas.
- **Sin fila de historia cuando no recalcula (C de D9):** descartada: CST-13 pide que el promedio sea reconstruible y quedaría sin rastro de por qué no cambió.
- **Admitir stock negativo para cualquier egreso desde ya (B de D10):** descartada: más superficie sin dueño; los changes 14 y 18a lo decidirán por su cuenta.
