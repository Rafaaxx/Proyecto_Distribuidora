## MODIFIED Requirements

### Requirement: Un costo informado se registra por comando con su costo base derivado
El sistema DEBE registrar costos informados con el comando `COSTO_INFORMAR` (`ONLINE`, permiso `EDITAR_COSTOS`). Cada costo registra proveedor, producto, presentación, valor por presentación, si incluye IVA, bonificación opcional como fracción (default `0`), vigencia desde (fecha) y observación opcional (CST-01). El servidor DEBE congelar en el costo la alícuota vigente del producto y si la organización computa crédito fiscal de IVA al registrarlo (`computa_credito_fiscal`, CST-06). DEBE calcular y guardar el costo base con la fórmula de CST-02, que divide por `1 + alícuota` solo si el valor incluye IVA **y** la organización computa crédito fiscal, redondeado a 6 decimales con `ROUND_HALF_UP` una sola vez al final. En una organización que no computa crédito fiscal, el valor es el pagado y `incluye_iva = true` DEBE rechazarse con `INCLUYE_IVA_NO_APLICA`. Valor, bonificación, alícuota y costo base DEBEN viajar como string en JSON. Cambiar después la condición de la organización NO DEBE modificar costos ya registrados.

#### Scenario: Caja x12 sin IVA
- **GIVEN** el producto activo `Cerveza B` del proveedor activo `Distribuidora Norte`, con la presentación activa de compra `Caja x12` (12 unidades) y alícuota `21%`, en una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** un usuario con `EDITAR_COSTOS` envía `COSTO_INFORMAR` con `Caja x12` a `"18000.00"`, sin IVA, sin bonificación, vigencia desde `2026-09-01`
- **THEN** el comando queda `ACEPTADO` y el costo queda registrado con costo base `"1500.000000"`, alícuota aplicada `"0.210000"`, `computa_credito_fiscal = true` y una sola fila de auditoría con el `operation_id`
- **Regla:** CST-01; CST-02 (ejemplo 1); CST-06; AUD-01

#### Scenario: Botella sin IVA
- **GIVEN** el producto `Vino A` con la presentación de compra `Botella` (1 unidad)
- **WHEN** se informa `Botella` a `"1000.00"`, sin IVA, sin bonificación
- **THEN** el costo base es `"1000.000000"`
- **Regla:** CST-02 (ejemplo 2); ADR-010 (cualquier presentación)

#### Scenario: Caja x12 con IVA incluido
- **GIVEN** `Cerveza B` con alícuota `21%` y `Caja x12`, en una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** se informa `Caja x12` a `"18000.00"` con IVA incluido
- **THEN** el costo base es `"1239.669421"` (18.000 / 1,21 / 12, redondeado solo al final) y la alícuota aplicada `"0.210000"`
- **Regla:** CST-02 (ejemplo 3); TR-03

#### Scenario: Caja x12 con bonificación
- **GIVEN** `Cerveza B` y `Caja x12`
- **WHEN** se informa `Caja x12` a `"18000.00"`, sin IVA, con bonificación `"0.100000"`
- **THEN** el costo base es `"1350.000000"` (18.000 × 0,9 / 12)
- **Regla:** CST-02 (ejemplo 4); TR-02

#### Scenario: Monotributista informa el valor pagado
- **GIVEN** `Cerveza B` con alícuota `21%` y `Caja x12`, en una organización `MONOTRIBUTO`
- **WHEN** se informa `Caja x12` a `"21780.00"` (lo que factura el proveedor con IVA), sin marcar IVA, sin bonificación
- **THEN** el costo base es `"1815.000000"` (21.780 / 12, sin dividir por 1,21), con alícuota aplicada `"0.210000"` y `computa_credito_fiscal = false`
- **Regla:** CST-02; CST-06; `design.md` D1 y D3

#### Scenario: Monotributista con bonificación
- **GIVEN** una organización `MONOTRIBUTO`, `Cerveza B` y `Caja x12`
- **WHEN** se informa `Caja x12` a `"21780.00"` con bonificación `"0.100000"`
- **THEN** el costo base es `"1633.500000"` (21.780 × 0,9 / 12)
- **Regla:** CST-02; CST-06

#### Scenario: Incluye IVA en una organización no inscripta
- **GIVEN** una organización `MONOTRIBUTO` o `EXENTO`
- **WHEN** se envía `COSTO_INFORMAR` con un costo `incluye_iva = true`
- **THEN** se rechaza con 422 `INCLUYE_IVA_NO_APLICA` indicando el costo y no se registra ninguno
- **Regla:** CST-06; TR-10; `design.md` D4

#### Scenario: El cambio de condición no toca costos registrados
- **GIVEN** un costo informado como `RESPONSABLE_INSCRIPTO` con IVA incluido y costo base `"1239.669421"`
- **WHEN** la organización pasa a `MONOTRIBUTO`
- **THEN** ese costo sigue con costo base `"1239.669421"`, `incluye_iva = true` y `computa_credito_fiscal = true`, y sigue siendo el vigente hasta que se informe otro
- **Regla:** CST-03; TR-06; `design.md` D3 y D10

#### Scenario: Doble envío no duplica el costo
- **GIVEN** un `COSTO_INFORMAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y el costo existe una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con otro valor
- **GIVEN** un `COSTO_INFORMAR` aceptado con `operation_id` X y valor `"18000.00"`
- **WHEN** se reenvía con `operation_id` X y valor `"19000.00"`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y no se registra el costo de `"19000.00"`
- **Regla:** SYN-02

#### Scenario: Sin permiso para editar costos
- **GIVEN** un usuario sin `EDITAR_COSTOS` (rol Supervisor comercial)
- **WHEN** envía `COSTO_INFORMAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se registra ningún costo
- **Regla:** `01` §19 (`EDITAR_COSTOS`)

#### Scenario: Valor o bonificación inválidos
- **GIVEN** `Cerveza B` y `Caja x12`
- **WHEN** se informa un valor `"0.00"`, negativo o con más de 2 decimales, o una bonificación negativa, mayor o igual a `"1"` o con más de 6 decimales
- **THEN** se rechaza con `VALOR_INVALIDO` o `BONIFICACION_INVALIDA` y no se registra ningún costo
- **Regla:** TR-01; TR-02; TR-10

### Requirement: El costo base se calcula igual en el servidor y en el cliente
La fórmula de CST-02, con su dependencia de `computa_credito_fiscal` (CST-06), DEBE existir como función pura en el backend y en el frontend, y ambas DEBEN pasar el mismo conjunto de casos compartidos. Ese conjunto incluye los cuatro ejemplos de `01` §6.1 (con `computa_credito_fiscal = true`) y los casos de una organización no inscripta. El cálculo del cliente es solo una vista previa; el valor registrado es siempre el del servidor.

#### Scenario: Los ejemplos de CST-02 pasan en ambas suites
- **GIVEN** los casos compartidos de costo base
- **WHEN** corren pytest y Vitest
- **THEN** ambas suites obtienen `"1500.000000"`, `"1000.000000"`, `"1239.669421"` y `"1350.000000"` para los cuatro ejemplos de `01` §6.1
- **Regla:** CST-02; ADR-016

#### Scenario: Los casos sin crédito fiscal pasan en ambas suites
- **GIVEN** los casos compartidos con `computa_credito_fiscal = false`
- **WHEN** corren pytest y Vitest
- **THEN** ambas obtienen `"1815.000000"` para Caja x12 a `"21780.00"` y `"1633.500000"` con bonificación del 10%
- **Regla:** CST-02; CST-06; ADR-016

#### Scenario: Redondeo solo al final
- **GIVEN** una caja x12 informada a `"10000.00"` sin IVA ni bonificación
- **WHEN** se calcula el costo base en ambas suites
- **THEN** el resultado es `"833.333333"`
- **Regla:** CST-02; TR-03; ADR-010 (ejemplo $10.000 / 12)

## ADDED Requirements

### Requirement: Los costos vigentes se resumen por regla de IVA
El sistema DEBE informar, para la organización del token y a una fecha, cuántos costos informados vigentes (CST-03, uno por producto y presentación) se registraron computando crédito fiscal y cuántos sin computarlo, con permiso `ADMIN_CONFIGURACION` o `EDITAR_COSTOS`. Es la lectura que usa la pantalla de cambio de condición (`design.md` D10).

#### Scenario: Resumen tras cambiar la condición
- **GIVEN** una organización con 12 costos vigentes registrados como `MONOTRIBUTO` y 3 registrados después como `RESPONSABLE_INSCRIPTO`
- **WHEN** se pide el resumen a hoy
- **THEN** informa 3 con crédito fiscal y 12 sin crédito fiscal
- **Regla:** CST-03; CST-06

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_CONFIGURACION` ni `EDITAR_COSTOS`
- **WHEN** pide el resumen
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19
