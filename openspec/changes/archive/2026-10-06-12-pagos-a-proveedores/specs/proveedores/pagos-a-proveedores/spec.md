## Purpose

Definir el pago a un proveedor independiente de una compra: su registro por comando con uno o más medios, su efecto en la cuenta corriente del proveedor y sus consultas (PAG-01, PAG-02, INV-08). Escrita con la opción A de `design.md` D3 a D8 y D10, pendientes de aprobación (tarea 0.1).

## ADDED Requirements

### Requirement: Un pago a proveedor se registra por comando con uno o más medios

El sistema DEBE registrar un pago con el comando `PAGO_PROVEEDOR_REGISTRAR` (solo `ONLINE`, con `Operation-Id`), que indica proveedor, fecha, importe, de 1 a 20 medios de pago y una observación opcional (PAG-01, `design.md` D6). El importe DEBE ser mayor que cero con 2 decimales (`IMPORTE_INVALIDO`). El pago nace `CONFIRMADA`, con origen `INDEPENDIENTE` y sin compra asociada, y NO DEBE editarse (TR-06). La observación se guarda recortada y vacía equivale a no informarla.

#### Scenario: Pago con efectivo y transferencia
- **GIVEN** el proveedor P con saldo `"152460.00"` y los medios activos "Efectivo" y "Transferencia" (exige referencia)
- **WHEN** se envía `PAGO_PROVEEDOR_REGISTRAR` por `"152460.00"` con `"100000.00"` en efectivo y `"52460.00"` por transferencia con referencia `"0042"`
- **THEN** existe un pago `CONFIRMADA` de origen `INDEPENDIENTE` por `"152460.00"` con dos medios, y el saldo de P es `"0.00"`
- **Regla:** PAG-01; PAG-02; INV-08

#### Scenario: Pago con un solo medio y observación
- **WHEN** se registra un pago de `"100000.00"` en efectivo con observación `"  paga factura 0001-123  "`
- **THEN** el pago queda con un medio y la observación `"paga factura 0001-123"`
- **Regla:** PAG-01; `design.md` D6

#### Scenario: Pago sin medios
- **WHEN** se envía el comando con la lista de medios vacía
- **THEN** se rechaza con `MEDIOS_INVALIDOS` y no queda pago, movimiento ni cambio de saldo
- **Regla:** PAG-01; `design.md` D6

#### Scenario: Importe inválido
- **WHEN** el importe es `"0.00"`, es negativo o tiene tres decimales (`"100000.001"`)
- **THEN** se rechaza con `IMPORTE_INVALIDO` y no queda ningún efecto
- **Regla:** TR-01; PAG-01

#### Scenario: Observación demasiado larga
- **WHEN** la observación tiene 501 caracteres (el largo se mide sobre el texto recibido, antes de recortar espacios), y otro pago la trae de exactamente 500
- **THEN** la de 501 se rechaza con un error de validación (422) y no queda pago, medio ni movimiento de cuenta; la de 500 se acepta y se guarda completa
- **Regla:** PAG-01; INV-03; `design.md` D6

#### Scenario: Pagos solo con conexión
- **WHEN** llega `PAGO_PROVEEDOR_REGISTRAR` en modo `OFFLINE` por el lote de sincronización
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

### Requirement: La suma de los medios es igual al importe del pago

La suma de los importes de los medios DEBE ser exactamente igual al importe del pago (INV-08); si no, el comando DEBE rechazarse con `MEDIOS_NO_SUMAN_IMPORTE`. Cada medio DEBE ser un medio de pago activo de la organización, con importe mayor que cero de 2 decimales, y DEBE traer referencia no vacía cuando el medio la exige (`REFERENCIA_OBLIGATORIA`). El mismo medio PUEDE repetirse en un pago. Un error de medio DEBE indicar qué medio lo causó (PAG-01, ADR-043 punto 2, `design.md` D6).

#### Scenario: INV-08 — medios que no suman el importe
- **WHEN** el importe es `"152460.00"` y los medios suman `"150000.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; PAG-01

#### Scenario: INV-08 — propiedad sobre pagos aceptados
- **GIVEN** importes y repartos de medios aleatorios válidos
- **WHEN** el pago se acepta
- **THEN** la suma de sus medios guardados es igual a su importe
- **Regla:** INV-08

#### Scenario: Medio que exige referencia sin referencia
- **WHEN** se paga por transferencia sin referencia, o con una referencia de solo espacios
- **THEN** se rechaza con `REFERENCIA_OBLIGATORIA` indicando el medio
- **Regla:** `01` §4 (medios con referencia obligatoria); ADR-043 punto 2

#### Scenario: Medio inactivo
- **WHEN** uno de los medios está inactivo
- **THEN** se rechaza con `MEDIO_PAGO_INACTIVO` indicando el medio
- **Regla:** TR-09; CAT-05

#### Scenario: Medio de otra organización
- **WHEN** uno de los medios pertenece a otra organización
- **THEN** la respuesta es 404 y no queda ningún efecto
- **Regla:** INV-21; SEG-07

#### Scenario: El mismo medio dos veces
- **WHEN** un pago de `"152460.00"` trae dos medios "Cheque" de `"100000.00"` y `"52460.00"` con referencias distintas
- **THEN** se acepta y el pago tiene dos medios
- **Regla:** PAG-01; `design.md` D6

#### Scenario: Más de 20 medios
- **WHEN** el pago trae 21 medios
- **THEN** se rechaza con `MEDIOS_INVALIDOS`
- **Regla:** `design.md` D6

### Requirement: El pago reduce el saldo general del proveedor y no modifica costos

Registrar un pago DEBE insertar en la cuenta corriente del proveedor un movimiento `PAGO` que reduce el saldo por el importe del pago, con el pago como origen y el momento del comando (PAG-02, CC-03, CC-05). El pago NO DEBE imputarse a ninguna compra ni modificar stock, costo promedio ni costos informados. Un pago PUEDE superar la deuda: el saldo queda negativo, a favor de la organización (`design.md` D3).

#### Scenario: Pago parcial de una deuda
- **GIVEN** el proveedor P con saldo `"153720.00"`
- **WHEN** se registra un pago de `"100000.00"`
- **THEN** la cuenta de P tiene un movimiento `PAGO` `REDUCE` de `"100000.00"` con origen en el pago y el saldo es `"53720.00"`
- **Regla:** PAG-02; CC-03; CC-04

#### Scenario: Pago mayor que la deuda
- **GIVEN** el proveedor P con saldo `"153720.00"`
- **WHEN** se registra un pago de `"160000.00"`
- **THEN** se acepta y el saldo es `"-6280.00"` ("Saldo a nuestro favor")
- **Regla:** PAG-02; ADR-034 punto 8; `design.md` D3

#### Scenario: El saldo a favor se compensa con la compra siguiente
- **GIVEN** el proveedor P con saldo `"-6280.00"`
- **WHEN** se confirma una compra a crédito con total de factura `"100000.00"`
- **THEN** el saldo es `"93720.00"`, sin ningún movimiento de compensación
- **Regla:** PAG-02; CC-04; `design.md` D3

#### Scenario: El pago no toca costos ni stock
- **GIVEN** `Vino A` con costo promedio `"1210.000000"` y 60 unidades en el depósito
- **WHEN** se registra un pago a su proveedor
- **THEN** el promedio, el stock y la historia de costo de `Vino A` no cambian
- **Regla:** PAG-02; CST-14

#### Scenario: Después de un pago la cuenta no admite saldo inicial
- **GIVEN** el proveedor P con un pago registrado
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` para P
- **THEN** se rechaza con `CUENTA_CON_OPERACIONES`
- **Regla:** CC-08

### Requirement: La fecha del pago es la del pago real y no puede ser futura

La `fecha` del pago DEBE ser obligatoria y NO DEBE ser posterior a la fecha de negocio de hoy en la zona horaria de la organización (`FECHA_INVALIDA`); no tiene límite hacia atrás. El movimiento de cuenta DEBE usar el momento del comando, no la fecha del pago (TR-04, TR-05, `design.md` D4).

#### Scenario: Pago con fecha anterior
- **GIVEN** hoy es 1 de octubre en la zona de la organización
- **WHEN** se registra un pago con fecha 28 de septiembre
- **THEN** el pago guarda la fecha 28 de septiembre y su movimiento `PAGO` tiene el `occurred_at` del comando
- **Regla:** PAG-01; TR-05; `design.md` D4

#### Scenario: Fecha futura
- **WHEN** la fecha del pago es mañana
- **THEN** se rechaza con `FECHA_INVALIDA`
- **Regla:** TR-04; `design.md` D4

### Requirement: El proveedor del pago se valida antes de escribir

El proveedor DEBE existir en la organización del token; uno ajeno o inexistente DEBE responder 404 sin efectos (INV-21). Un proveedor inactivo DEBE admitirse: la deuda existe aunque esté dado de baja (`design.md` D5).

#### Scenario: Proveedor de otra organización
- **WHEN** un usuario de la organización A registra un pago a un proveedor de B
- **THEN** la respuesta es 404 y no queda pago ni movimiento en ninguna de las dos
- **Regla:** INV-21; SEG-07; TR-08

#### Scenario: Proveedor inactivo con deuda
- **GIVEN** el proveedor inactivo `Bodega Norte` con saldo `"80000.00"`
- **WHEN** se registra un pago de `"80000.00"`
- **THEN** se acepta y el saldo es `"0.00"`
- **Regla:** PAG-02; ADR-034 punto 3; `design.md` D5

### Requirement: Registrar un pago es una operación atómica e idempotente

El pago, sus medios, el movimiento de cuenta y el saldo DEBEN registrarse en una sola transacción o ninguno (INV-01), con la fila de saldo del proveedor bloqueada antes de escribir (`02` §7.3). Reenviar el mismo comando NO DEBE duplicar efectos (INV-06).

#### Scenario: INV-01 — falla entre el pago y la cuenta
- **GIVEN** una falla inyectada después de insertar el pago y antes del movimiento de cuenta
- **WHEN** se procesa el comando
- **THEN** no queda pago, medio, movimiento ni cambio de saldo
- **Regla:** INV-01

#### Scenario: Doble envío del mismo comando
- **GIVEN** un pago registrado con `Operation-Id` X
- **WHEN** se reenvía el mismo contenido con X
- **THEN** se devuelve el resultado original y existe un solo pago y un solo movimiento `PAGO`
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo Operation-Id con contenido distinto
- **WHEN** se reenvía X con otro importe
- **THEN** se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** SYN-02

#### Scenario: Dos pagos simultáneos al mismo proveedor
- **GIVEN** el proveedor P con saldo `"153720.00"`
- **WHEN** dos sesiones registran a la vez pagos de `"100000.00"` y `"53720.00"` con distinto `Operation-Id`
- **THEN** ambos se aceptan, el saldo es `"0.00"` y coincide con la suma del libro
- **Regla:** INV-13; `02` §7.3

#### Scenario: INV-13 — propiedad con pagos y anulaciones
- **GIVEN** una secuencia aleatoria válida de compras a crédito, pagos y anulaciones de pago
- **WHEN** se aplican
- **THEN** el saldo de cada proveedor es igual a la suma de sus movimientos
- **Regla:** INV-13; CC-04

### Requirement: Los pagos se consultan por organización

El sistema DEBE exponer el listado de pagos de la organización, paginado por cursor (límite de 1 a 200; fuera de rango, 422) y filtrable por proveedor, estado, origen y rango de fechas del pago, y el detalle de un pago con sus medios, su observación, su origen (y la compra, si es de origen `COMPRA`) y, si está anulado, motivo, usuario y momento. Los importes DEBEN viajar como string. Un pago de otra organización DEBE responder 404.

#### Scenario: Listado filtrado por proveedor y fechas
- **GIVEN** pagos a P del 28 y del 30 de septiembre y un pago a Q del 29
- **WHEN** se listan los pagos de P desde el 29 de septiembre
- **THEN** se devuelve solo el pago del 30, con fecha, proveedor, importe, origen y estado
- **Regla:** PAG-01; TR-04

#### Scenario: El listado incluye los pagos de contado
- **GIVEN** una compra de contado a P con su pago
- **WHEN** se listan los pagos de P
- **THEN** ese pago aparece con origen `COMPRA` y el identificador de su compra
- **Regla:** CMP-03; CC-05

#### Scenario: Detalle con medios
- **WHEN** se pide el detalle del pago de `"152460.00"` con efectivo y transferencia
- **THEN** la respuesta trae los dos medios con su nombre, importe `"100000.00"` y `"52460.00"` y la referencia `"0042"`
- **Regla:** PAG-01; INV-03

#### Scenario: Rango de fechas invertido
- **WHEN** `desde` es posterior a `hasta`
- **THEN** la respuesta es 422 con `RANGO_DE_FECHAS_INVALIDO`
- **Regla:** ADR-043 punto 13

#### Scenario: Pago de otra organización
- **WHEN** un usuario de A pide el detalle de un pago de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

### Requirement: El saldo del proveedor se consulta para pagar

El sistema DEBE exponer el saldo actual de un proveedor de la organización como string, calculado en la base (`"0.00"` si la cuenta no tiene movimientos), a quien tenga `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA` (`design.md` D8). Un proveedor ajeno o inexistente DEBE responder 404.

#### Scenario: Saldo de un proveedor con deuda
- **GIVEN** el proveedor P con saldo `"153720.00"` y un usuario con solo `REGISTRAR_PAGO_PROVEEDOR`
- **WHEN** pide el saldo de P
- **THEN** recibe `"153720.00"`
- **Regla:** CC-04; INV-03; `design.md` D8

#### Scenario: Proveedor sin movimientos
- **WHEN** se pide el saldo de un proveedor sin movimientos
- **THEN** la respuesta es `"0.00"`
- **Regla:** CC-04

#### Scenario: Sin ninguno de los permisos
- **WHEN** un usuario sin `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` ni `REGISTRAR_COMPRA` pide el saldo
- **THEN** la respuesta es 403
- **Regla:** `01` §19; SEG-06

#### Scenario: Proveedor de otra organización
- **WHEN** un usuario de A pide el saldo de un proveedor de B
- **THEN** la respuesta es 404
- **Regla:** INV-21

### Requirement: Registrar y consultar pagos exige permiso

`PAGO_PROVEEDOR_REGISTRAR` DEBE exigir `REGISTRAR_PAGO_PROVEEDOR`. El listado y el detalle de pagos DEBEN exigir `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`. La lista de proveedores para elegir DEBE poder leerse también con `REGISTRAR_PAGO_PROVEEDOR`, sin abrir ninguna escritura (`design.md` D7). Un pago registrado DEBE quedar auditado por el bus con su `operation_id` (AUD-01, ADR-022).

#### Scenario: Sin permiso de pago
- **WHEN** un usuario sin `REGISTRAR_PAGO_PROVEEDOR` envía `PAGO_PROVEEDOR_REGISTRAR`
- **THEN** la respuesta es 403 y no queda ningún efecto
- **Regla:** `01` §19; SEG-06

#### Scenario: Lectura con solo el permiso de anular
- **WHEN** un usuario con `ANULAR_PAGO_PROVEEDOR` y sin `REGISTRAR_PAGO_PROVEEDOR` lista los pagos
- **THEN** recibe el listado
- **Regla:** `01` §19; `design.md` D7

#### Scenario: Lectura sin permisos de pago
- **WHEN** un usuario sin `REGISTRAR_PAGO_PROVEEDOR` ni `ANULAR_PAGO_PROVEEDOR` lista los pagos
- **THEN** la respuesta es 403
- **Regla:** `01` §19

#### Scenario: Auditoría del pago
- **WHEN** se registra un pago
- **THEN** existe una sola fila de auditoría con el `operation_id` del comando
- **Regla:** AUD-01; AUD-02; ADR-022
