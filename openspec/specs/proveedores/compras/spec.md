# Compras — Especificación

## Purpose

Registrar compras a proveedores con líneas en cualquier presentación de compra, de modo que en una sola operación atómica ingrese el stock, se recalcule el costo promedio, quede la deuda en la cuenta corriente del proveedor y, si la compra es de contado, su pago (CMP-01 a CMP-04, CMP-08, CC-05, INV-01, INV-07).

## Requirements

### Requirement: Una compra se confirma por comando con al menos una línea

El sistema DEBE registrar una compra con el comando `COMPRA_CONFIRMAR` (solo `ONLINE`, con `Operation-Id`), que indica proveedor, fecha, ubicación de destino, condición (`CONTADO` o `CREDITO`), total de factura y una o más líneas; cada línea indica producto, presentación de compra, cantidad, valor por presentación, si incluye IVA y bonificación opcional (CMP-01, `design.md` D1, D12). Una compra sin líneas DEBE rechazarse con `COMPRA_SIN_LINEAS` dentro de la transacción y sin efectos (INV-07). La compra nace `CONFIRMADA` y NO DEBE editarse (TR-06).

#### Scenario: Compra a crédito de vino por caja y cerveza por unidad
- **GIVEN** el proveedor activo P, al que pertenecen `Vino A` (Caja x6) y `Cerveza B` (Botella de 1 unidad), sin stock previo, alícuota 21%
- **WHEN** se confirma una compra a crédito al depósito con `Vino A`, Caja x6, cantidad 10, valor `"6000.00"` sin IVA, y `Cerveza B`, Botella, cantidad 60, valor `"1100.00"` sin IVA, con total de factura `"152460.00"`
- **THEN** la compra queda `CONFIRMADA` con total neto `"126000.00"`, el depósito tiene 60 unidades de cada producto, los promedios son `"1000.000000"` y `"1100.000000"` y la cuenta de P aumenta `"152460.00"` con un movimiento `COMPRA`
- **Regla:** CMP-01; CMP-02; CMP-03; `00` §9 criterio 2

#### Scenario: INV-07 — compra sin líneas
- **WHEN** se envía `COMPRA_CONFIRMAR` con la lista de líneas vacía
- **THEN** se rechaza con `COMPRA_SIN_LINEAS` y no queda compra, movimiento ni saldo
- **Regla:** INV-07

#### Scenario: Compras solo con conexión
- **WHEN** llega `COMPRA_CONFIRMAR` en modo `OFFLINE` por el lote de sincronización
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** CMP-08; `02` §6.5

#### Scenario: Doble envío del mismo comando
- **GIVEN** una compra confirmada con `Operation-Id` X
- **WHEN** se reenvía el mismo contenido con X
- **THEN** se devuelve el resultado original y existe una sola compra, un solo ingreso por línea y un solo movimiento `COMPRA`
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo Operation-Id con contenido distinto
- **WHEN** se reenvía X con otra cantidad
- **THEN** se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** SYN-02

### Requirement: Cada línea deriva su cantidad base, su costo base y su importe neto

Cada línea DEBE calcular `cantidad base = cantidad × unidades de la presentación` (entero, INV-04), `costo base` con la fórmula de CST-02 usando la alícuota del producto (redondeado a 6 decimales solo al final) e `importe neto = cantidad base × costo base` redondeado a 2 decimales por línea; el total neto DEBE ser la suma de los importes netos (CMP-02, TR-03). La línea DEBE congelar las unidades de la presentación y la alícuota aplicada (`design.md` D12). Los casos DEBEN existir primero en `shared/fixtures/calculo/cmp-02-compra.json` y pasar en Python y TypeScript (`design.md` D15).

#### Scenario: Caja x12 sin IVA
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, sin IVA, sin bonificación
- **THEN** cantidad base 12, costo base `"1500.000000"`, importe neto `"18000.00"`
- **Regla:** CMP-02; CST-02 (`01` §6.1)

#### Scenario: Caja x12 con IVA incluido
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, con IVA 21%
- **THEN** costo base `"1239.669421"` e importe neto `"14876.03"`
- **Regla:** CMP-02; CST-02; TR-03

#### Scenario: Caja x12 con bonificación del 10%
- **WHEN** una línea es Caja x12, cantidad 1, valor `"18000.00"`, sin IVA, bonificación `"0.100000"`
- **THEN** costo base `"1350.000000"` e importe neto `"16200.00"`
- **Regla:** CMP-02; CST-02

#### Scenario: Cantidad fraccionaria que da unidades enteras
- **WHEN** una línea es Caja x6, cantidad `"2.5"`
- **THEN** la cantidad base es 15
- **Regla:** CMP-02; INV-04; `design.md` D5

#### Scenario: Cantidad fraccionaria que no da unidades enteras
- **WHEN** una línea es Caja x6, cantidad `"2.3"`
- **THEN** se rechaza con `CANTIDAD_INVALIDA` indicando la línea y no queda ningún efecto
- **Regla:** INV-04; `design.md` D5

#### Scenario: Valor cero o negativo
- **WHEN** una línea tiene valor `"0.00"`
- **THEN** se rechaza con `VALOR_INVALIDO` indicando la línea
- **Regla:** CST-02; `design.md` D5

#### Scenario: Unidades congeladas en la línea
- **GIVEN** una compra con una línea en Caja x6
- **WHEN** se lee su detalle
- **THEN** la línea muestra `unidades_presentacion = 6` y la alícuota aplicada `"0.210000"`
- **Regla:** INV-18; `design.md` D12

### Requirement: Las referencias de la compra se validan antes de escribir

El comando DEBE rechazar sin efectos: un proveedor inexistente o de otra organización (404), un proveedor inactivo (`PROVEEDOR_INACTIVO`), un producto de otro proveedor (`PROVEEDOR_NO_CORRESPONDE`, `design.md` D4), un producto inactivo (`PRODUCTO_INACTIVO`), una presentación que no es del producto, inactiva o sin uso en compra (`PRESENTACION_INVALIDA`), una ubicación inexistente (404) o inactiva (`UBICACION_INACTIVA`) y una fecha posterior a la fecha de negocio de hoy (`FECHA_INVALIDA`, `design.md` D6).

#### Scenario: Presentación solo de venta
- **WHEN** una línea usa una presentación con `usar_en_compra = false`
- **THEN** se rechaza con `PRESENTACION_INVALIDA` y no queda ningún efecto
- **Regla:** CAT-02; CMP-01

#### Scenario: Producto de otro proveedor
- **WHEN** la compra al proveedor P incluye un producto cuyo proveedor es Q
- **THEN** se rechaza con `PROVEEDOR_NO_CORRESPONDE`
- **Regla:** CAT-06; `design.md` D4

#### Scenario: Proveedor inactivo
- **WHEN** se confirma una compra a un proveedor inactivo
- **THEN** se rechaza con `PROVEEDOR_INACTIVO`
- **Regla:** CAT-05

#### Scenario: Fecha futura
- **WHEN** la fecha de la compra es mañana en la zona de la organización
- **THEN** se rechaza con `FECHA_INVALIDA`
- **Regla:** TR-04; `design.md` D6

#### Scenario: Proveedor de otra organización
- **WHEN** un usuario de A confirma una compra con un proveedor de B
- **THEN** la respuesta es 404 y no queda ningún efecto
- **Regla:** INV-21; SEG-07

### Requirement: Confirmar una compra es una operación atómica

En una sola transacción, `COMPRA_CONFIRMAR` DEBE ingresar el stock de cada línea en la ubicación de destino (movimiento `COMPRA` con su costo base), recalcular el promedio de cada producto (CST-11), registrar `COMPRA` en la cuenta del proveedor por el total de factura y, si es de contado, el pago; si algo falla, nada queda registrado (CMP-03, INV-01). Las filas DEBEN bloquearse en el orden `saldo_cuenta → costo_producto → stock_saldo` (`02` §7.3).

#### Scenario: Promedio con stock previo
- **GIVEN** `Vino A` con stock total 60 y promedio `"1000.000000"`
- **WHEN** se confirma una compra de 60 unidades a costo base `"1100.000000"`
- **THEN** el promedio pasa a `"1050.000000"` y el stock total a 120
- **Regla:** CST-11 (`01` §6.2)

#### Scenario: Dos líneas del mismo producto
- **GIVEN** `Vino A` sin stock
- **WHEN** una compra trae Caja x6 cantidad 10 a `"6000.00"` y Botella cantidad 60 a `"1100.00"`, ambas sin IVA
- **THEN** se aplican en el orden de las líneas y el promedio queda `"1050.000000"` con stock 120
- **Regla:** CST-11; `design.md` D5

#### Scenario: INV-01 — falla después del stock
- **GIVEN** una falla inyectada después de ingresar el stock y antes de registrar la cuenta
- **WHEN** se procesa la compra
- **THEN** no queda compra, línea, movimiento de stock, historia de costo, movimiento de cuenta ni cambio de saldo
- **Regla:** INV-01

### Requirement: Una compra de contado registra su pago

Una compra `CONTADO` DEBE registrar, en la misma transacción, un pago al proveedor con origen `COMPRA` por el total de factura, con uno o más medios de pago activos cuya suma DEBE ser igual al importe (INV-08) y con referencia en los medios que la exigen; la cuenta del proveedor DEBE recibir `COMPRA` (aumenta) y `PAGO` (reduce) por separado (CC-05, `design.md` D2). Una compra `CREDITO` NO DEBE traer medios.

#### Scenario: Contado con efectivo y transferencia
- **WHEN** se confirma una compra de contado con total de factura `"152460.00"` pagada con `"100000.00"` en efectivo y `"52460.00"` por transferencia con referencia
- **THEN** la cuenta de P tiene `COMPRA` `"152460.00"` y `PAGO` `"152460.00"`, su saldo no cambia y existe un pago con dos medios
- **Regla:** CMP-03; CC-05; PAG-01; INV-08

#### Scenario: INV-08 — medios que no suman el importe
- **WHEN** los medios suman `"150000.00"` y el total de factura es `"152460.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; PAG-01

#### Scenario: Medio que exige referencia sin referencia
- **WHEN** se paga con un medio que exige referencia y no se la informa
- **THEN** se rechaza con `REFERENCIA_OBLIGATORIA`
- **Regla:** `01` §4 (medios con referencia obligatoria)

#### Scenario: Crédito con medios
- **WHEN** una compra `CREDITO` trae medios de pago
- **THEN** se rechaza con `CONDICION_INVALIDA`
- **Regla:** CMP-01; `design.md` D2

### Requirement: La deuda es el total de la factura del proveedor

El total de factura DEBE ser un importe mayor que cero con 2 decimales y DEBE ser el importe del movimiento `COMPRA` en la cuenta del proveedor; el total neto (sin IVA) DEBE ser el que valoriza el stock y el promedio (`design.md` D1). La pantalla lo propone como total neto más el IVA de cada línea con la alícuota del producto, y el usuario puede corregirlo.

#### Scenario: Total de factura distinto del sugerido
- **WHEN** el total neto es `"126000.00"`, el sugerido `"152460.00"` y el usuario informa `"153720.00"` (con una percepción)
- **THEN** la cuenta de P aumenta `"153720.00"` y los promedios no cambian respecto de informar `"152460.00"`
- **Regla:** CMP-03; CST-04 (el costo de la compra es neto); `design.md` D1

#### Scenario: Total de factura con tres decimales
- **WHEN** el total de factura es `"152460.001"`
- **THEN** se rechaza con `IMPORTE_INVALIDO`
- **Regla:** TR-01

### Requirement: La compra informa los costos que difieren del costo informado vigente

La respuesta de `COMPRA_CONFIRMAR` DEBE listar las líneas cuyo costo base difiere del costo base del costo informado vigente del producto a la fecha de la compra, o cuyo producto no tiene costo informado vigente, con ambos valores. El sistema NUNCA DEBE registrar un costo informado como efecto de la compra (CMP-04, `design.md` D7).

#### Scenario: Costo distinto del vigente
- **GIVEN** `Vino A` con costo informado vigente de costo base `"1000.000000"`
- **WHEN** se confirma una compra de `Vino A` con costo base `"1100.000000"`
- **THEN** la respuesta incluye la línea con `costo_base_compra = "1100.000000"` y `costo_base_vigente = "1000.000000"` y no se creó ningún costo informado
- **Regla:** CMP-04

#### Scenario: Costo igual al vigente
- **WHEN** el costo base de la línea es igual al vigente
- **THEN** la línea no aparece en la lista
- **Regla:** CMP-04

### Requirement: Las compras se consultan por organización

El sistema DEBE listar compras de la organización con paginación por cursor (límite 1 a 200, 422 fuera de rango), filtrables por proveedor, estado y rango de fechas, en orden descendente de fecha, y DEBE devolver el detalle con líneas, pago y anulación si la hubo. Leer compras DEBE exigir `REGISTRAR_COMPRA` o `ANULAR_COMPRA` (`design.md` D14). Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Filtro por proveedor
- **GIVEN** compras a P y a Q
- **WHEN** se listan con filtro P
- **THEN** solo aparecen las de P, cada una una vez a lo largo de las páginas
- **Regla:** `02` §11

#### Scenario: Compra de otra organización
- **WHEN** un usuario de A pide el detalle de una compra de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso
- **WHEN** un usuario sin `REGISTRAR_COMPRA` ni `ANULAR_COMPRA` lista compras
- **THEN** la respuesta es 403
- **Regla:** `01` §19; `design.md` D14

### Requirement: Registrar compras exige permiso

`COMPRA_CONFIRMAR` DEBE exigir `REGISTRAR_COMPRA`, también cuando es de contado (`design.md` D14). Una compra confirmada DEBE quedar auditada por el bus con su `operation_id` (AUD-01, ADR-022).

#### Scenario: Sin permiso de compra
- **WHEN** un usuario sin `REGISTRAR_COMPRA` envía `COMPRA_CONFIRMAR`
- **THEN** la respuesta es 403 y no queda ningún efecto
- **Regla:** `01` §19

#### Scenario: Auditoría de la compra
- **WHEN** se confirma una compra
- **THEN** existe una sola fila de auditoría con el `operation_id` del comando
- **Regla:** AUD-01; AUD-02; ADR-022
