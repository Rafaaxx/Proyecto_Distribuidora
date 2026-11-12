# Cobranzas - Administración de cobranzas

## Purpose

Definir las pantallas de cobranzas en `/admin` (listado, alta, detalle y anulación) y las lecturas de apoyo que necesita quien cobra sin administrar clientes: el selector de clientes y el saldo de un cliente (`design.md` D14 y D19, aprobadas el 2026-10-15).

## Requirements

### Requirement: El área de cobranzas se decide con el permiso de la sesión

El menú de `/admin` DEBE ofrecer "Cobranzas" a quien tiene `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`, con el listado paginado y filtros por cliente, estado, usuario, jornada y fechas. "Registrar cobranza" DEBE verse solo con `REGISTRAR_COBRANZA` y "Anular", solo con `ANULAR_COBRANZA` sobre una cobranza `CONFIRMADA` de origen `INDEPENDIENTE` (ADR-027).

#### Scenario: Vendedor
- **GIVEN** un usuario con la plantilla Vendedor
- **WHEN** entra a `/admin`
- **THEN** ve "Cobranzas" con "Registrar cobranza" y sin "Anular"
- **Regla:** `01` §19; ADR-027

#### Scenario: Sin permisos de cobranza
- **GIVEN** un usuario con la plantilla Consulta
- **WHEN** entra a `/admin`
- **THEN** no ve "Cobranzas"
- **Regla:** ADR-027

### Requirement: El alta muestra el saldo, suma los medios y pide confirmación si queda a favor

El formulario DEBE ofrecer el selector de clientes, mostrar el saldo actual y el resultante ("Nos debe" / "Saldo a favor") formateados con `lib/money.ts`, sumar los medios en vivo sin convertir importes a `number` para calcular, pedir referencia en los medios que la exigen y, si el saldo resultante queda a favor, pedir una confirmación explícita antes de enviar. Un reintento DEBE reusar el mismo `Operation-Id` y el mismo identificador de cobranza. Los errores del servidor DEBEN mostrarse junto al campo que los causó (`design.md` D5, D19).

#### Scenario: Suma de medios en vivo
- **GIVEN** el alta para `Kiosco La Esquina` con saldo `"150000.00"` e importe `"50000.00"`
- **WHEN** el usuario carga `"30000.00"` en efectivo y `"20000.00"` por transferencia con referencia
- **THEN** ve "Falta $ 0,00" y "Queda debiendo $ 100.000,00", y puede registrar
- **Regla:** COB-02; INV-08; INV-03

#### Scenario: Confirmación por saldo a favor
- **WHEN** el importe es `"160000.00"` sobre un saldo de `"150000.00"`
- **THEN** antes de enviar se le pide confirmar "Le queda saldo a favor de $ 10.000,00"
- **Regla:** COB-03; `design.md` D5

#### Scenario: Reintento tras un corte
- **GIVEN** el envío falló por un corte de red
- **WHEN** el usuario reintenta
- **THEN** el pedido lleva el mismo `Operation-Id` y no queda una cobranza duplicada
- **Regla:** INV-06; SYN-02

### Requirement: El detalle muestra la cobranza y permite anularla con motivo

El detalle DEBE mostrar cliente, importe, medios con referencia, momento en la zona de la organización, usuario, jornada, observación, estado, la anulación si existe y las observaciones de sincronización. "Anular" DEBE abrir un diálogo con motivo obligatorio (de los activos del ámbito `ANULACION_COBRANZA`) y observación opcional.

#### Scenario: Anular desde el detalle
- **GIVEN** un usuario con `ANULAR_COBRANZA` en el detalle de una cobranza `CONFIRMADA`
- **WHEN** elige un motivo y confirma
- **THEN** la cobranza pasa a "Anulada" y se muestra el motivo
- **Regla:** COB-05

#### Scenario: Cobranza con observación de sincronización
- **GIVEN** una cobranza aceptada con `PERMISO_REVOCADO`
- **WHEN** se abre su detalle
- **THEN** se ve la observación pendiente
- **Regla:** SYN-07; SYN-10

#### Scenario: Observación de medio en el detalle
- **GIVEN** una cobranza aceptada sin conexión con `MEDIO_INACTIVO` en la línea de "Billetera" y `REFERENCIA_FALTANTE` en la de "Transferencia"
- **WHEN** se abre su detalle
- **THEN** se ven "Medio de pago inactivo" junto a la línea de "Billetera" y "Falta la referencia" junto a la de "Transferencia", con su importe
- **Regla:** SYN-07; `design.md` D13

### Requirement: Quien cobra elige el cliente y ve su saldo sin administrar clientes

El sistema DEBE ofrecer `GET /api/v1/clientes/opciones` (identificador, nombre, código y estado; sin crédito ni documento) y `GET /api/v1/clientes/{id}/saldo` (saldo actual como string, calculado en la base) con `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`. El selector DEBE ofrecer clientes `ACTIVO` y `SUSPENDIDO` y no al consumidor final. La ficha, el listado completo y el estado de cuenta siguen exigiendo `GESTIONAR_CLIENTES` (`design.md` D14).

#### Scenario: Vendedor elige cliente
- **GIVEN** un usuario con `REGISTRAR_COBRANZA` y sin `GESTIONAR_CLIENTES`
- **WHEN** pide las opciones de clientes y el saldo de `Kiosco La Esquina`
- **THEN** recibe la lista sin datos de crédito y el saldo `"150000.00"`
- **Regla:** `01` §19; `design.md` D14

#### Scenario: Vendedor no abre la cuenta corriente
- **GIVEN** el mismo usuario
- **WHEN** pide el estado de cuenta del cliente
- **THEN** recibe 403
- **Regla:** `01` §19

#### Scenario: Saldo de un cliente ajeno
- **WHEN** pide el saldo de un cliente de otra organización
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `GESTIONAR_CLIENTES` ni `REGISTRAR_COBRANZA`
- **WHEN** pide las opciones de clientes
- **THEN** recibe 403
- **Regla:** SEG-06
