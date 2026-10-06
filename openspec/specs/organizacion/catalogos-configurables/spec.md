# catalogos-configurables Specification

## Purpose

Define las alícuotas de IVA, los medios de pago y los motivos como catálogos que pertenecen a cada organización y se administran como datos, no como valores fijos en el código, de modo que ninguna regla posterior (venta, cobranza, ajuste de stock, anulación) tenga que enumerarlos en tiempo de compilación (TR-09, `03` §4).

## Requirements

### Requirement: Los catálogos configurables son datos de la organización
Las alícuotas de IVA, los medios de pago y los motivos DEBEN almacenarse como filas propias de cada organización. El sistema NO DEBE enumerarlos como constantes en el código ni compartirlos entre organizaciones (TR-09).

#### Scenario: Dos organizaciones tienen catálogos independientes
- **GIVEN** la organización A con la alícuota `21%` y la organización B con la alícuota `10,5%`
- **WHEN** se listan las alícuotas de cada una
- **THEN** A ve solo `21%` y B ve solo `10,5%`
- **Regla:** TR-09 (los catálogos configurables son datos de la organización, no valores fijos en código)

#### Scenario: La organización inicial nace con los catálogos documentados
- **GIVEN** un sistema recién migrado
- **WHEN** se siembra la organización inicial
- **THEN** sus alícuotas de IVA son `21%`, `10,5%` y `0%`
- **AND** sus medios de pago son efectivo, transferencia, cheque, billetera y tarjeta
- **AND** sus motivos de ajuste de stock son rotura, vencimiento, muestra, consumo interno, diferencia de inventario y otro
- **Regla:** `01` §4 (alícuotas, medios de pago y motivos de ajuste de la organización inicial)

### Requirement: Las alícuotas de IVA se expresan como fracción de seis decimales
Una alícuota de IVA DEBE tener nombre, valor y marca de actividad. El valor DEBE representarse como fracción decimal exacta de 6 decimales, nunca como punto flotante binario (TR-02, INV-03, `03` §4).

#### Scenario: El 21 % se almacena como fracción
- **GIVEN** la alícuota de IVA del 21 % de la organización inicial
- **WHEN** se lee su valor
- **THEN** es `0.210000`
- **Regla:** TR-02 (los porcentajes se representan con 6 decimales como fracción, 21 % = 0,210000)

#### Scenario: Una alícuota del 0 % es válida
- **GIVEN** la organización inicial
- **WHEN** se lee la alícuota de valor `0.000000`
- **THEN** existe y está activa
- **Regla:** `01` §4 (alícuotas iniciales: 21 %, 10,5 %, 0 %)

#### Scenario: Un valor de punto flotante no entra al catálogo
- **GIVEN** la operación de alta de una alícuota
- **WHEN** se le pasa el valor como número de punto flotante binario
- **THEN** la operación falla con un error explícito y no crea la alícuota
- **Regla:** INV-03

### Requirement: Un medio de pago declara si exige referencia
Un medio de pago DEBE tener nombre, una marca que indique si exige un dato de referencia al usarse y una marca de actividad (`03` §4).

#### Scenario: Un medio de pago que exige referencia queda marcado
- **GIVEN** la organización inicial
- **WHEN** se lee el medio de pago transferencia
- **THEN** su indicador de referencia obligatoria es legible y forma parte del catálogo
- **Regla:** `01` §4 (medios de pago: lista con indicador de referencia obligatoria)

#### Scenario: Un medio de pago sin nombre se rechaza
- **GIVEN** la operación de alta de un medio de pago
- **WHEN** se la invoca con nombre vacío
- **THEN** falla con un error explícito y no crea el medio de pago
- **Regla:** `03` §4 (`medio_pago`: `nombre` obligatorio)

### Requirement: Un motivo pertenece a un ámbito de la lista cerrada
Un motivo DEBE declarar su ámbito dentro de la lista cerrada `AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`, además de nombre y marca de actividad. Los motivos DEBEN poder listarse filtrados por ámbito (`03` §4). El ámbito `ANULACION_PAGO` es el de la anulación de pagos a proveedores (PAG-03, `design.md` D1 del change 12).

#### Scenario: Los motivos se listan por ámbito
- **GIVEN** la organización inicial con sus motivos de ajuste de stock sembrados
- **WHEN** se listan los motivos del ámbito `AJUSTE_STOCK`
- **THEN** el resultado contiene los seis motivos de ajuste y ninguno de otro ámbito
- **Regla:** `01` §4, `03` §4 (`motivo.ambito`)

#### Scenario: Un ámbito fuera de la lista se rechaza
- **GIVEN** la operación de alta de un motivo
- **WHEN** se la invoca con un ámbito que no está en la lista cerrada
- **THEN** falla con un error explícito y no crea el motivo
- **Regla:** `03` §4 (lista cerrada de `ambito`)

#### Scenario: Motivos de anulación de pago por API
- **GIVEN** la organización A con motivos de `ANULACION_COMPRA` y de `ANULACION_PAGO`
- **WHEN** se piden los motivos del ámbito `ANULACION_PAGO`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** PAG-03; TR-09; INV-21

### Requirement: Los elementos de catálogo se desactivan, no se borran
Un elemento de catálogo DEBE poder desactivarse y NO DEBE eliminarse. Las listas para nuevas operaciones DEBEN ofrecer únicamente los elementos activos, mientras que la lectura por identificador DEBE seguir resolviendo los inactivos para no romper las operaciones históricas que los referencian (TR-06, CAT-05, `03` §2.5).

#### Scenario: Un elemento desactivado deja de ofrecerse
- **GIVEN** un medio de pago activo de la organización inicial
- **WHEN** se lo desactiva
- **THEN** ya no aparece en la lista de medios de pago disponibles para nuevas operaciones
- **AND** sigue siendo legible por su identificador
- **Regla:** CAT-05 (un elemento usado en operaciones no se elimina: se desactiva; los inactivos no se ofrecen en nuevas operaciones)

#### Scenario: Desactivar un elemento de otra organización no hace nada
- **GIVEN** un motivo de la organización A
- **WHEN** se intenta desactivarlo indicando la organización B
- **THEN** la operación falla como "no encontrado" y el motivo de A sigue activo
- **Regla:** TR-08, SEG-07

#### Scenario: No existe operación de borrado de catálogo
- **GIVEN** el conjunto de operaciones expuestas sobre los catálogos configurables
- **WHEN** se las enumera
- **THEN** ninguna elimina filas; la baja se expresa como desactivación
- **Regla:** TR-06 (ninguna operación confirmada se edita ni se borra)

### Requirement: Los medios de pago y los motivos activos se consultan por API

El sistema DEBE exponer, para usuarios autenticados de la organización, la lista de medios de pago activos (con `requiere_referencia`) y la de motivos activos filtrada por un ámbito obligatorio de la lista cerrada, sin datos de otra organización. Un ámbito fuera de la lista DEBE responder 422 (`AMBITO_INVALIDO`) (`design.md` D2 y D8 del change 11).

#### Scenario: Motivos de anulación de compra
- **GIVEN** la organización A con motivos de `AJUSTE_STOCK` y de `ANULACION_COMPRA`
- **WHEN** se piden los motivos del ámbito `ANULACION_COMPRA`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** `03` §4; TR-09; INV-21

#### Scenario: Medios de pago de la organización
- **WHEN** un usuario de A pide los medios de pago
- **THEN** recibe solo los activos de A con su indicador de referencia obligatoria
- **Regla:** `01` §4; TR-08

#### Scenario: Ámbito inválido
- **WHEN** se piden los motivos del ámbito `CUALQUIERA`
- **THEN** la respuesta es 422 con `AMBITO_INVALIDO`
- **Regla:** `03` §4 (lista cerrada de `ambito`)

### Requirement: Toda organización tiene motivos de anulación de compra

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_COMPRA` para poder anular compras (CMP-05): la siembra de una organización nueva los crea y la migración del change 11 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar (`design.md` D8 del change 11).

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de compra aprobados en `design.md` D8 (recomendados: "Error de carga", "Devolución al proveedor", "Otro")
- **Regla:** CMP-05; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 11 sin motivos de `ANULACION_COMPRA`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** CMP-05; `03` §17

### Requirement: Toda organización tiene motivos de anulación de pago

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_PAGO` para poder anular pagos a proveedores (PAG-03): la siembra de una organización nueva los crea y la migración del change 12 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar (`design.md` D1 del change 12).

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de pago aprobados en `design.md` D1 (recomendados: "Error de carga", "Pago rechazado o devuelto", "Otro")
- **Regla:** PAG-03; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 12 sin motivos de `ANULACION_PAGO`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** PAG-03; `04` §2.1 punto 4

#### Scenario: Ámbito desconocido en la base
- **WHEN** se intenta insertar un motivo con un ámbito fuera de la lista cerrada directamente en la base
- **THEN** la restricción de la base lo rechaza
- **Regla:** `03` §4 (lista cerrada de `ambito`)
