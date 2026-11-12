## MODIFIED Requirements

### Requirement: Cada línea deriva su cantidad base, su costo base y su importe neto

Cada línea DEBE calcular `cantidad base = cantidad × unidades de la presentación` (entero, INV-04), `costo base` con la fórmula de CST-02 usando la alícuota del producto, que divide por `1 + alícuota` solo si la línea incluye IVA **y** la organización computa crédito fiscal (CST-06), redondeado a 6 decimales solo al final, e `importe neto = cantidad base × costo base` redondeado a 2 decimales por línea; el total neto DEBE ser la suma de los importes netos (CMP-02, TR-03). La línea DEBE congelar las unidades de la presentación, la alícuota aplicada (`design.md` D12 del 11) y si la organización computaba crédito fiscal al confirmar (`computa_credito_fiscal`, `design.md` D3). En una organización que no computa crédito fiscal, el valor de la línea es el pagado y una línea con `incluye_iva = true` DEBE rechazarse con `INCLUYE_IVA_NO_APLICA` indicando la línea. Los casos DEBEN existir primero en `shared/fixtures/calculo/cmp-02-compra.json` y pasar en Python y TypeScript (`design.md` D15 del 11).

#### Scenario: Caja x12 sin IVA
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, sin IVA, sin bonificación
- **THEN** cantidad base 12, costo base `"1500.000000"`, importe neto `"18000.00"`
- **Regla:** CMP-02; CST-02 (`01` §6.1)

#### Scenario: Caja x12 con IVA incluido
- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, con IVA 21%
- **THEN** costo base `"1239.669421"` e importe neto `"14876.03"`
- **Regla:** CMP-02; CST-02; TR-03

#### Scenario: Caja x12 con bonificación del 10%
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, sin IVA, bonificación `"0.100000"`
- **THEN** costo base `"1350.000000"` e importe neto `"16200.00"`
- **Regla:** CMP-02; CST-02

#### Scenario: Línea de un monotributista al valor pagado
- **GIVEN** una organización `MONOTRIBUTO` y Cerveza B con alícuota 21%
- **WHEN** una línea es Caja x12, cantidad 1, valor `"21780.00"`, sin bonificación
- **THEN** cantidad base 12, costo base `"1815.000000"`, importe neto `"21780.00"` y la línea queda con `computa_credito_fiscal = false`
- **Regla:** CMP-02; CST-02; CST-06; `design.md` D3

#### Scenario: Línea con IVA incluido en una organización no inscripta
- **GIVEN** una organización `MONOTRIBUTO`
- **WHEN** la línea 2 de una compra trae `incluye_iva = true`
- **THEN** se rechaza con 422 `INCLUYE_IVA_NO_APLICA` indicando la línea 2 y no queda ningún efecto
- **Regla:** CST-06; TR-10; `design.md` D4

#### Scenario: Cantidad fraccionaria que da unidades enteras
- **WHEN** una línea es Caja x6, cantidad `"2.5"`
- **THEN** la cantidad base es 15
- **Regla:** CMP-02; INV-04; `design.md` D5 del 11

#### Scenario: Cantidad fraccionaria que no da unidades enteras
- **WHEN** una línea es Caja x6, cantidad `"2.3"`
- **THEN** se rechaza con `CANTIDAD_INVALIDA` indicando la línea y no queda ningún efecto
- **Regla:** INV-04; `design.md` D5 del 11

#### Scenario: Valor cero o negativo
- **WHEN** una línea tiene valor `"0.00"`
- **THEN** se rechaza con `VALOR_INVALIDO` indicando la línea
- **Regla:** CST-02; `design.md` D5 del 11

#### Scenario: Unidades congeladas en la línea
- **GIVEN** una compra con una línea en Caja x6, confirmada en una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** se lee su detalle
- **THEN** la línea muestra `unidades_presentacion = 6`, la alícuota aplicada `"0.210000"` y `computa_credito_fiscal = true`
- **Regla:** INV-18; `design.md` D12 del 11; `design.md` D3

#### Scenario: El cambio de condición no toca compras confirmadas
- **GIVEN** una compra confirmada como `MONOTRIBUTO` con una línea de costo base `"1815.000000"`
- **WHEN** la organización pasa a `RESPONSABLE_INSCRIPTO` y después se anula esa compra
- **THEN** el detalle sigue mostrando `"1815.000000"` y `computa_credito_fiscal = false`, y la anulación egresa a `"1815.000000"`
- **Regla:** TR-06; CMP-05; `design.md` D3

### Requirement: La deuda es el total de la factura del proveedor

El total de factura DEBE ser un importe mayor que cero con 2 decimales y DEBE ser el importe del movimiento `COMPRA` en la cuenta del proveedor; el total neto DEBE ser el que valoriza el stock y el promedio (`design.md` D1 del 11). En una organización que computa crédito fiscal, el total neto no tiene IVA y la pantalla propone como total de factura el total neto más el IVA de cada línea con la alícuota del producto. En una organización que no computa crédito fiscal, el total neto ya incluye el IVA pagado y el sugerido es el total neto, sin IVA agregado (CMP-02, CST-06). En los dos casos, el usuario puede corregir el total de factura.

#### Scenario: Total de factura distinto del sugerido
- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** el total neto es `"126000.00"`, el sugerido `"152460.00"` y el usuario informa `"153720.00"` (con una percepción)
- **THEN** la cuenta de P aumenta `"153720.00"` y los promedios no cambian respecto de informar `"152460.00"`
- **Regla:** CMP-03; CST-04 (el costo de la compra es neto); `design.md` D1 del 11

#### Scenario: Total sugerido de un monotributista
- **GIVEN** una organización `MONOTRIBUTO`
- **WHEN** la compra es 10 cajas de Vino A x6 a `"7260.00"` y 60 botellas de Cerveza B a `"1331.00"`
- **THEN** el total neto es `"152460.00"`, el total sugerido es `"152460.00"`, la cuenta de P aumenta `"152460.00"` y los promedios quedan en `"1210.000000"` y `"1331.000000"`
- **Regla:** CMP-02; CMP-03; CST-06; `design.md` D5

#### Scenario: Total de factura con tres decimales
- **WHEN** el total de factura es `"152460.001"`
- **THEN** se rechaza con `IMPORTE_INVALIDO`
- **Regla:** TR-01
