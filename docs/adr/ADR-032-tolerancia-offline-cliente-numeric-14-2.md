# ADR-032 — `tolerancia_offline_valor` del cliente es `numeric(14,2)`, igual que la organización (`03` §4, `03` §10)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-28 |
| Referenciado en | `openspec/changes/07-clientes/design.md` D6; `03-modelo-de-datos.md` §4 (`configuracion_organizacion`) y §10 (`cliente`); CRE-06 |

**Decisión (D6, opción A) aprobada por el usuario el 2026-09-28. Texto del ADR aprobado por el usuario el 2026-09-28; estado *Vigente*.**

## Contexto

`configuracion_organizacion` ya tiene `tolerancia_offline_tipo text` (`IMPORTE`, `PORCENTAJE`) y `tolerancia_offline_valor numeric(14,2)` (`03` §4). El cliente repite el mismo par de campos para poder anular la tolerancia de la organización (CRE-06), y hacía falta decidir la precisión de la columna del cliente: si copia exactamente la de la organización o si, por tratarse a veces de un porcentaje, necesita más decimales (como los `numeric(9,6)` que usa el catálogo de alícuotas y porcentajes de descuento).

La decisión importa porque el change 18b (evaluación de crédito) va a leer este campo del cliente o, en su ausencia, el de la organización, y una diferencia de escala entre ambos obligaría a convertir en cada herencia. Se registra como ADR porque fija la precisión de una columna que otro change (18b) va a consumir por contrato, con el mismo criterio que ADR-016 para el motor de cálculo compartido.

## Decisión

1. `cliente.tolerancia_offline_valor` es `numeric(14,2)`, exactamente el mismo tipo que `configuracion_organizacion.tolerancia_offline_valor`.
2. Cuando `tolerancia_offline_tipo = IMPORTE`, el valor es un importe en pesos con la escala monetaria habitual del sistema. Cuando `tolerancia_offline_tipo = PORCENTAJE`, el valor es un porcentaje con hasta dos decimales (por ejemplo, `2.50` = 2,50 %).
3. `clientes` valida únicamente que el tipo esté en el catálogo (`IMPORTE`, `PORCENTAJE`) y que tipo y valor viajen juntos (`TOLERANCIA_OFFLINE_INVALIDA` en caso contrario); no valida ni resuelve cómo el porcentaje se aplica sobre el límite, el disponible o el saldo — eso queda para el change 18b.

## Consecuencias

- La columna del cliente es idéntica a la de la organización: heredar el valor de la organización cuando el del cliente es nulo (CRE-06) es una lectura directa, no una conversión de escala.
- Dos decimales alcanzan para expresar una tolerancia porcentual con la precisión que un caso de negocio de crédito necesita; se descarta la necesidad de un tercer decimal.
- Si en el futuro un caso de uso necesitara más precisión en el porcentaje, el cambio de escala se decide con un ADR nuevo que además revise la de la organización, para no romper la simetría que esta decisión fija.

## Alternativas consideradas

- **`numeric(9,6)`, como los porcentajes de alícuotas y descuentos.** Descartada: rompe la simetría con `configuracion_organizacion.tolerancia_offline_valor`, obliga a convertir en cada herencia y agrega superficie de error sin un caso de negocio que pida esa precisión.
- **Dos columnas separadas (`tolerancia_offline_importe`, `tolerancia_offline_porcentaje`).** Descartada: contradice `03` §10, que ya define un único par tipo/valor, y duplicaría la misma decisión en la organización más adelante.
