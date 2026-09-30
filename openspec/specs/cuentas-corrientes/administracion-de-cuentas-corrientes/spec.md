# Administración de cuentas corrientes — Especificación

## Purpose

Definir las pantallas de `/admin` para consultar la cuenta corriente de clientes y proveedores y registrar saldos iniciales, con los permisos efectivos de `GET /api/v1/yo` (`usePermisos()`, `<SiTienePermiso>`, ADR-027, ADR-028). Alcance según `design.md` D13, aprobada (2026-09-29).

## Requirements

### Requirement: La ficha muestra el saldo y lleva a la cuenta corriente

La ficha de cliente y la de proveedor DEBEN mostrar el saldo actual, formateado desde el string de la API con `lib/money.ts` y rotulado según el signo ("Nos debe" / "Saldo a favor" para clientes; "Le debemos" / "Saldo a nuestro favor" para proveedores), y un enlace a su cuenta corriente, visibles para quien tiene el permiso de lectura de `design.md` D2.

#### Scenario: Ficha de un cliente con deuda

- **GIVEN** el cliente `Kiosco La Esquina` con saldo `"150000.00"` y un usuario con `GESTIONAR_CLIENTES`
- **WHEN** abre la ficha
- **THEN** ve "Nos debe $ 150.000,00" y el enlace "Cuenta corriente"
- **Regla:** CC-04; `01` §2 (Saldo); ADR-027

#### Scenario: Ficha de un proveedor sin movimientos

- **GIVEN** el proveedor `Bodega Norte` sin movimientos y un usuario con `GESTIONAR_PROVEEDORES`
- **WHEN** abre la ficha
- **THEN** ve saldo $ 0,00 y el enlace "Cuenta corriente"
- **Regla:** CC-04

### Requirement: La pantalla de cuenta corriente muestra el estado de cuenta

La pantalla DEBE listar los movimientos con fecha en la zona horaria de la organización (TR-04), tipo, columnas de aumento y reducción, y saldo acumulado; DEBE mostrar el saldo anterior cuando se filtra por período, cargar más movimientos con el cursor y no convertir importes a `number` para calcular.

#### Scenario: Ver el estado de cuenta

- **GIVEN** el cliente `Kiosco La Esquina` con un movimiento `AUMENTA` de `"150000.00"` y uno `REDUCE` de `"20000.00"`
- **WHEN** el usuario abre su cuenta corriente
- **THEN** ve las dos filas con saldos acumulados $ 150.000,00 y $ 130.000,00
- **Regla:** CC-07; TR-04

#### Scenario: Filtrar por período

- **GIVEN** la cuenta del escenario anterior con el primer movimiento en marzo y el segundo en abril
- **WHEN** el usuario filtra desde el 1 de abril
- **THEN** ve el saldo anterior $ 150.000,00 y una sola fila
- **Regla:** CC-07; `design.md` D9

#### Scenario: Error de la API

- **GIVEN** la API responde 404 para la entidad pedida
- **WHEN** se abre la pantalla
- **THEN** se muestra que el recurso no existe, sin datos de otra entidad
- **Regla:** SEG-07

### Requirement: El saldo inicial se registra desde la cuenta corriente con permiso

La pantalla de cuenta corriente DEBE ofrecer "Registrar saldo inicial" solo dentro de `<SiTienePermiso permiso="IMPORTAR_DATOS">` (`design.md` D1). El formulario DEBE pedir importe y sentido con rótulos de negocio ("Nos debe" / "Saldo a favor del cliente"; "Le debemos" / "Saldo a favor nuestro"), generar un `operation_id` nuevo por envío y reutilizarlo en un reintento del mismo envío, avisar que requiere conexión sin encolar nada, mostrar el mensaje del servidor ante un rechazo y volver a la cuenta corriente con el saldo actualizado al aceptarse.

#### Scenario: Registrar un saldo inicial

- **GIVEN** un usuario con `IMPORTAR_DATOS` en la cuenta corriente de `Kiosco La Esquina` sin movimientos
- **WHEN** carga `150000.00` con "Nos debe" y confirma
- **THEN** se envía `SALDO_INICIAL_REGISTRAR` con `importe = "150000.00"` y `sentido = AUMENTA`, y al volver ve saldo $ 150.000,00 y el movimiento en la lista
- **Regla:** CC-02; `01` §21; `design.md` D5

#### Scenario: Reintento tras un error de red

- **GIVEN** un envío de saldo inicial que falló por red antes de recibir respuesta
- **WHEN** el usuario reintenta sin cambiar los datos
- **THEN** se reenvía con el mismo `operation_id` y no se duplica el movimiento
- **Regla:** INV-06; TR-07

#### Scenario: Rechazo del servidor

- **GIVEN** una cuenta con operaciones
- **WHEN** el usuario intenta registrar un saldo inicial
- **THEN** ve el mensaje de `CUENTA_CON_OPERACIONES` y la cuenta no cambia
- **Regla:** `design.md` D3

#### Scenario: Sin permiso no se ofrece la acción

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `IMPORTAR_DATOS`
- **WHEN** abre la cuenta corriente de un cliente
- **THEN** ve el estado de cuenta y no ve "Registrar saldo inicial"; si navega a la URL del formulario, ve el aviso de falta de permiso sin enviar nada
- **Regla:** ADR-027; SEG-06; `design.md` D1
