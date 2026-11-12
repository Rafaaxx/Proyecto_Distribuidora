# Puesta en marcha — Especificación

## Purpose

Cargar desde planillas el stock inicial valorizado por ubicación y los saldos iniciales de clientes y proveedores, reutilizando exactamente las reglas de `STOCK_INICIAL_REGISTRAR` (STK-10, CST-11) y de `SALDO_INICIAL_REGISTRAR` (CC-08), para que la organización arranque con stock, costo promedio y cuentas corrientes correctos.

## Requirements

### Requirement: Importar stock inicial valorizado

La planilla de stock inicial DEBE tener las columnas `ubicacion` (nombre), `producto_codigo`, `cantidad_base` (entero distinto de cero) y `costo_unitario` (costo por unidad base, obligatorio si la cantidad es positiva y prohibido si es negativa), según `design.md` D13. Cada fila DEBE registrarse con las mismas reglas que `STOCK_INICIAL_REGISTRAR` (ADR-037): una cantidad positiva ingresa y recalcula el promedio (CST-11); una negativa corrige, egresa al promedio vigente sin recalcularlo (CST-12) y no deja negativo el saldo de la ubicación. Cada movimiento DEBE quedar como `STOCK_INICIAL` con el `operation_id` de la importación. El momento de los movimientos es el de `design.md` D7.

#### Scenario: Stock inicial de dos ubicaciones

- **GIVEN** Vino A sin movimientos, un depósito y un vehículo
- **WHEN** se importan las filas (depósito, `VA-750`, 60, `1000`) y (vehículo, `VA-750`, 60, `1100`)
- **THEN** el depósito y el vehículo tienen 60 cada uno, el stock total es 120 y el promedio `"1050.000000"`
- **Regla:** CST-10; CST-11; STK-10

#### Scenario: Corrección negativa en el mismo archivo

- **GIVEN** las filas (depósito, `VA-750`, 60, `1000`) y luego (depósito, `VA-750`, −12, vacío)
- **WHEN** se importa
- **THEN** el saldo del depósito es 48 y el promedio sigue en `"1000.000000"`
- **Regla:** STK-10; CST-12

#### Scenario: Costo cero

- **GIVEN** una fila con cantidad 60 y `costo_unitario` = `0`
- **WHEN** se importa
- **THEN** la fila da `COSTO_INVALIDO`
- **Regla:** ADR-037 punto 6

#### Scenario: Costo con más de seis decimales

- **GIVEN** una fila con `costo_unitario` = `1000,1234567`
- **WHEN** se importa
- **THEN** la fila da `COSTO_INVALIDO` (no se redondea)
- **Regla:** TR-02; ADR-037 punto 6

#### Scenario: Producto con operaciones de otro tipo

- **GIVEN** un producto que ya tiene un movimiento que no es `STOCK_INICIAL`
- **WHEN** una fila de stock inicial lo usa
- **THEN** la fila da `PRODUCTO_CON_OPERACIONES`
- **Regla:** STK-10

#### Scenario: Corrección que deja negativo el saldo

- **GIVEN** 10 unidades de Vino A en el vehículo
- **WHEN** una fila trae (vehículo, `VA-750`, −12, vacío)
- **THEN** la fila da `STOCK_INSUFICIENTE`, aunque el usuario tenga `PERMITIR_STOCK_NEGATIVO`
- **Regla:** STK-10

#### Scenario: Ubicación inactiva

- **GIVEN** una ubicación "Camión 2" inactiva
- **WHEN** una fila la usa
- **THEN** la fila da `UBICACION_INACTIVA`
- **Regla:** ADR-038

#### Scenario: Producto inactivo

- **GIVEN** un producto inactivo
- **WHEN** una fila de stock inicial lo usa
- **THEN** la fila da `PRODUCTO_INACTIVO`
- **Regla:** CAT-05

### Requirement: Importar saldos iniciales

La planilla de saldos iniciales DEBE tener las columnas `cuenta_tipo` (`CLIENTE` o `PROVEEDOR`), `entidad` (clave natural de `design.md` D4: código o documento del cliente; nombre del proveedor), `importe` (positivo, hasta dos decimales) y `sentido`, aceptando los rótulos de ADR-034 punto 8 ("Nos debe"/"Saldo a favor" para clientes, "Le debemos"/"Saldo a nuestro favor" para proveedores) además de `AUMENTA`/`REDUCE`. Cada fila DEBE registrarse con las mismas reglas que `SALDO_INICIAL_REGISTRAR` (CC-08, ADR-034): varios saldos por cuenta mientras no tenga movimientos de otro tipo, cualquier estado de la entidad salvo el consumidor final. El momento de los movimientos es el de `design.md` D7.

#### Scenario: Saldo inicial de cliente

- **GIVEN** el cliente `C001` sin movimientos
- **WHEN** se importa (`CLIENTE`, `C001`, `150000`, "Nos debe")
- **THEN** la cuenta de `C001` tiene un movimiento `SALDO_INICIAL` `AUMENTA` de `"150000.00"` y saldo `"150000.00"`
- **Regla:** CC-08; INV-13

#### Scenario: Corrección en el mismo archivo

- **GIVEN** las filas (`CLIENTE`, `C001`, `150000`, `AUMENTA`) y (`CLIENTE`, `C001`, `20000`, `REDUCE`)
- **WHEN** se importa
- **THEN** la cuenta tiene dos movimientos `SALDO_INICIAL` y saldo `"130000.00"`
- **Regla:** CC-08; ADR-034 punto 1

#### Scenario: Saldo de proveedor

- **GIVEN** el proveedor "Bodega Sur"
- **WHEN** se importa (`PROVEEDOR`, `Bodega Sur`, `80000`, "Le debemos")
- **THEN** la cuenta del proveedor tiene saldo `"80000.00"`
- **Regla:** CC-08; CC-01

#### Scenario: Consumidor final

- **GIVEN** el consumidor final habilitado con código `CF`
- **WHEN** una fila le carga saldo
- **THEN** la fila da `CONSUMIDOR_FINAL_SIN_CUENTA`
- **Regla:** CC-08; CLI-03

#### Scenario: Cuenta con operaciones

- **GIVEN** un cliente con un movimiento que no es `SALDO_INICIAL`
- **WHEN** una fila le carga saldo inicial
- **THEN** la fila da `CUENTA_CON_OPERACIONES`
- **Regla:** CC-08

#### Scenario: Importe con tres decimales

- **GIVEN** una fila con `importe` = `100,005`
- **WHEN** se importa
- **THEN** la fila da `IMPORTE_INVALIDO` (no se redondea)
- **Regla:** TR-01

#### Scenario: Sentido desconocido

- **GIVEN** una fila con `sentido` = "debe"
- **WHEN** se importa
- **THEN** la fila da `SENTIDO_INVALIDO`
- **Regla:** CC-01; ADR-034 punto 8

#### Scenario: Cliente inexistente

- **GIVEN** ningún cliente con código ni documento `C999`
- **WHEN** una fila lo referencia
- **THEN** la fila da `REFERENCIA_NO_ENCONTRADA` en `entidad`
- **Regla:** INV-21; `design.md` D4

### Requirement: Orden de bloqueo en una importación de puesta en marcha

Una importación que escribe varios movimientos DEBE adquirir las filas de saldo respetando el orden global (`02` §7.3): las filas de saldos iniciales por (`cuenta_tipo`, entidad) ascendente y las de stock inicial por producto y ubicación ascendentes, de modo que no produzca interbloqueos con otras operaciones concurrentes.

#### Scenario: Importación concurrente con un stock inicial por pantalla

- **GIVEN** una importación de stock con Cerveza B y Vino A en orden inverso al de sus identificadores
- **WHEN** en paralelo se registra por pantalla un stock inicial de los mismos productos
- **THEN** ambas operaciones terminan sin interbloqueo y el stock y el promedio son los de aplicar las dos
- **Regla:** `02` §7.3; INV-12
