## ADDED Requirements

### Requirement: El ingreso de una anulación de venta lleva el costo de su línea

Un ingreso `ANULACION_VENTA` DEBE llevar el costo unitario congelado de la línea de venta que revierte y recalcular el promedio (CST-11). Sin costo (línea vendida sin costo) DEBE aceptarse: sube el stock total sin recalcular el promedio y el movimiento queda con costo nulo. El origen DEBE ser la venta (`design.md` D5).

#### Scenario: Ingreso con costo
- **WHEN** se registra un ingreso `ANULACION_VENTA` de 72 unidades de Vino A a $1.050,000000
- **THEN** el movimiento queda con ese costo, el saldo de la ubicación sube 72 y el promedio se recalcula
- **Regla:** STK-03; CST-11; VTA-21

#### Scenario: Ingreso sin costo
- **WHEN** se registra un ingreso `ANULACION_VENTA` sin costo de 12 unidades de Agua B
- **THEN** el saldo sube 12, el stock total sube 12, el promedio no cambia y el movimiento queda con costo nulo
- **Regla:** STK-03; CST-12; ADR-058

#### Scenario: Cantidad negativa
- **WHEN** se intenta un `ANULACION_VENTA` con cantidad negativa
- **THEN** se rechaza y nada queda escrito
- **Regla:** STK-03; INV-01

### Requirement: Una anulación de venta admite un producto inactivo

Un ingreso `ANULACION_VENTA` DEBE aceptarse aunque el producto esté inactivo (revertir no es una operación nueva). Una ubicación inactiva DEBE seguir rechazándolo con `UBICACION_INACTIVA`, y la regla de toma (STK-09) DEBE aplicarse igual que a cualquier movimiento (`design.md` D6, D7).

#### Scenario: Producto inactivo
- **GIVEN** Vino A inactivo
- **WHEN** se registra un ingreso `ANULACION_VENTA` de Vino A
- **THEN** se acepta y el saldo sube
- **Regla:** CAT-05; ADR-058

#### Scenario: Otro tipo sigue exigiendo producto activo
- **WHEN** se registra un ingreso `COMPRA` de Vino A inactivo
- **THEN** se rechaza con `PRODUCTO_INACTIVO`
- **Regla:** CAT-05

#### Scenario: Ubicación tomada sin permiso de excepción
- **GIVEN** la camioneta 2 tomada por la jornada de Pedro
- **WHEN** otro usuario sin `LIBERAR_UBICACION` registra un ingreso `ANULACION_VENTA` en ella
- **THEN** se rechaza con `UBICACION_TOMADA` y nada queda escrito
- **Regla:** STK-09
