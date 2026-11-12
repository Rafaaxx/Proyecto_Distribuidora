## Purpose

Definir quién puede mover stock de una ubicación mientras está tomada por una jornada: la propia jornada, o un usuario con `LIBERAR_UBICACION` con auditoría, por cualquier camino que escriba en el libro de stock, de modo que dos dispositivos nunca operen sobre el mismo vehículo (STK-09, RUT-02, RUT-04; ADR-005).

## ADDED Requirements

### Requirement: Una ubicación tomada solo acepta movimientos de su jornada

Mientras una ubicación tiene una jornada `ABIERTA` o `EN_RENDICION`, el sistema DEBE rechazar con `UBICACION_TOMADA` (409) todo movimiento de stock sobre ella que no sea de esa jornada, sin escribir nada (STK-09). Un movimiento es de la jornada cuando la jornada está `ABIERTA` y el usuario **y** el dispositivo que envían el comando son los de la jornada (ADR-005; `design.md` D6). Ese movimiento DEBE quedar registrado con la jornada. Una jornada `EN_RENDICION` ya NO DEBE generar movimientos propios. Los permisos de cada operación (`TRANSFERIR_STOCK`, `AJUSTAR_STOCK` y los demás) DEBEN seguir exigiéndose además de esta regla.

#### Scenario: El vendedor de la jornada mueve stock de su vehículo

- **GIVEN** "Camioneta 1" con 48 unidades de Vino A, tomada por la jornada `ABIERTA` de Juan en el dispositivo V03
- **WHEN** Juan, desde V03, transfiere 6 unidades de "Camioneta 1" a "Depósito central"
- **THEN** la transferencia se acepta y "Camioneta 1" queda en 42
- **AND** el movimiento de "Camioneta 1" queda registrado con la jornada de Juan y el de "Depósito central", sin jornada
- **Regla:** STK-09; RUT-04

#### Scenario: Otro vendedor intenta mover stock de un vehículo tomado

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, y Pedro, Vendedor con `TRANSFERIR_STOCK` y sin `LIBERAR_UBICACION`
- **WHEN** Pedro transfiere 6 unidades de "Depósito central" a "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **AND** no queda transferencia, ni movimiento, ni cambio en ningún saldo ni en el stock total
- **Regla:** STK-09; INV-01; INV-12

#### Scenario: El mismo usuario desde otro dispositivo

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan en el dispositivo V03
- **WHEN** Juan, con su sesión en otro dispositivo, transfiere 6 unidades desde "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-09; ADR-005

#### Scenario: La jornada en rendición ya no mueve stock

- **GIVEN** "Camioneta 1" con la jornada de Juan `EN_RENDICION`
- **WHEN** Juan, desde su dispositivo, transfiere 6 unidades desde "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-09; `01` §18; `design.md` D6

#### Scenario: La toma no reemplaza el permiso de la operación

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, que no tiene `AJUSTAR_STOCK`
- **WHEN** Juan, desde su dispositivo, envía un ajuste sobre "Camioneta 1"
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO`
- **Regla:** STK-08; SEG-06

### Requirement: Una ubicación con toma y sin jornada se mueve libremente

Una ubicación que requiere toma y no tiene ninguna jornada no cerrada NO DEBE restringir los movimientos por esta regla: valen los permisos de cada operación (STK-09: "mientras está tomada"; RUT-02: carga "antes de la apertura"). Una ubicación que no requiere toma nunca queda alcanzada por esta regla.

#### Scenario: Carga del vehículo antes de abrir

- **GIVEN** "Camioneta 1" sin jornada y "Depósito central" con 120 unidades de Vino A
- **WHEN** un usuario con `TRANSFERIR_STOCK` transfiere 48 unidades del depósito a "Camioneta 1"
- **THEN** se acepta: el depósito queda en 72 y "Camioneta 1" en 48
- **Regla:** RUT-02; STK-07

#### Scenario: Devolución del remanente después del cierre

- **GIVEN** "Camioneta 1" con 12 unidades de Vino A, cuya jornada quedó `CERRADA`
- **WHEN** un usuario con `TRANSFERIR_STOCK` transfiere las 12 unidades a "Depósito central"
- **THEN** se acepta
- **Regla:** RUT-08; STK-09

#### Scenario: Un depósito nunca queda tomado

- **GIVEN** "Depósito central", que no requiere toma, y jornadas abiertas sobre otras ubicaciones
- **WHEN** un usuario con `AJUSTAR_STOCK` ajusta −6 por "Rotura" en "Depósito central"
- **THEN** se acepta como antes de este change
- **Regla:** STK-08; STK-09

### Requirement: Quien tiene `LIBERAR_UBICACION` mueve una ubicación tomada, con auditoría

Un usuario con `LIBERAR_UBICACION` DEBE poder registrar movimientos sobre una ubicación tomada por otra jornada, en cualquier estado no cerrado de esa jornada, siempre que tenga además el permiso de la operación (STK-09). El movimiento NO DEBE quedar registrado con la jornada, y el registro de auditoría del comando DEBE dejar constancia de que se operó sobre una ubicación tomada y de cuál era la jornada (AUD-02; `design.md` D8).

#### Scenario: Una supervisora recarga un vehículo tomado

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, y una Supervisora con `TRANSFERIR_STOCK` y `LIBERAR_UBICACION`
- **WHEN** la Supervisora transfiere 12 unidades de "Depósito central" a "Camioneta 1"
- **THEN** la transferencia se acepta
- **AND** el movimiento de "Camioneta 1" queda sin jornada
- **AND** el registro de auditoría del comando indica que se operó sobre una ubicación tomada e identifica la jornada de Juan
- **Regla:** STK-09; AUD-01; AUD-02

#### Scenario: Un movimiento sin excepción no lleva esa constancia

- **GIVEN** "Camioneta 2" sin jornada
- **WHEN** la misma Supervisora transfiere 12 unidades a "Camioneta 2"
- **THEN** el registro de auditoría del comando no lleva la constancia de ubicación tomada
- **Regla:** AUD-02; ADR-022

#### Scenario: Tener permiso de la operación no alcanza

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, y un usuario del rol Administración con `TRANSFERIR_STOCK` y sin `LIBERAR_UBICACION`
- **WHEN** transfiere 12 unidades a "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-09; `01` §19

### Requirement: La regla de toma alcanza a todo camino que mueve stock

La regla de toma DEBE aplicarse a toda operación que escriba movimientos en el libro de stock, sobre cada ubicación que toque: transferencia (origen y destino), anulación de transferencia, ajuste, anulación de ajuste, stock inicial por pantalla y por importación, compra y anulación de compra (STK-09; ADR-039: única puerta; `design.md` D7). Una operación rechazada por esta regla NO DEBE dejar ningún efecto en ningún libro (INV-01).

#### Scenario: Ajuste sobre un vehículo tomado

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, y un usuario del rol Administración con `AJUSTAR_STOCK`
- **WHEN** ajusta −6 por "Rotura" en "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA` y no queda ajuste ni movimiento
- **Regla:** STK-09; STK-08

#### Scenario: Anulación de una transferencia cuyo destino quedó tomado

- **GIVEN** una transferencia de 48 unidades del depósito a "Camioneta 1" hecha por un usuario de Administración, y "Camioneta 1" tomada después por la jornada de Juan
- **WHEN** ese usuario anula la transferencia
- **THEN** se rechaza con `UBICACION_TOMADA` y la transferencia sigue `CONFIRMADA`
- **Regla:** STK-09; TR-06

#### Scenario: El vendedor anula su propia carga durante la jornada

- **GIVEN** una transferencia de 24 unidades del depósito a "Camioneta 1" hecha por Juan desde su dispositivo, con su jornada `ABIERTA` sobre "Camioneta 1"
- **WHEN** Juan la anula desde ese dispositivo
- **THEN** la anulación se acepta y el movimiento inverso de "Camioneta 1" queda registrado con su jornada
- **Regla:** STK-09; STK-07

#### Scenario: Anulación de un ajuste sobre un vehículo tomado

- **GIVEN** un ajuste confirmado sobre "Camioneta 1", tomada después por la jornada de Juan
- **WHEN** un usuario con `AJUSTAR_STOCK` y sin `LIBERAR_UBICACION` lo anula
- **THEN** se rechaza con `UBICACION_TOMADA` y el ajuste sigue `CONFIRMADA`
- **Regla:** STK-09

#### Scenario: Stock inicial sobre un vehículo tomado

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan
- **WHEN** un usuario con `IMPORTAR_DATOS` y sin `LIBERAR_UBICACION` registra un stock inicial en "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-09; STK-10

#### Scenario: Compra con destino a un vehículo tomado

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan, y un usuario del rol Administración con `REGISTRAR_COMPRA`
- **WHEN** confirma una compra con destino "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA`
- **AND** no queda compra, ni movimiento de stock, ni cambio del promedio, ni movimiento en la cuenta del proveedor
- **Regla:** STK-09; CMP-03; INV-01

#### Scenario: El Administrador registra la misma compra

- **GIVEN** la misma situación, y un Administrador con `REGISTRAR_COMPRA` y `LIBERAR_UBICACION`
- **WHEN** confirma la compra con destino "Camioneta 1"
- **THEN** se acepta y el registro de auditoría del comando deja la constancia de ubicación tomada
- **Regla:** STK-09; AUD-02

#### Scenario: Importación de stock inicial con una fila sobre un vehículo tomado

- **GIVEN** una planilla de stock inicial con una fila sobre "Camioneta 1", tomada por la jornada de Juan, importada por un usuario sin `LIBERAR_UBICACION`
- **WHEN** se registra la importación
- **THEN** la importación se rechaza entera y el informe señala esa fila con `UBICACION_TOMADA`
- **Regla:** STK-09; IMP-01; IMP-02

### Requirement: La carga del vehículo es una transferencia

La carga de un vehículo DEBE registrarse con la misma operación de transferencia entre ubicaciones, con conexión, antes de abrir la jornada o durante ella (RUT-02; STK-07). La apertura de la jornada NO lleva líneas de carga (`design.md` D4).

#### Scenario: Carga durante la jornada por el propio vendedor

- **GIVEN** Juan con su jornada `ABIERTA` sobre "Camioneta 1", que tiene 48 unidades de Vino A, y "Depósito central" con 72
- **WHEN** Juan, desde su dispositivo, transfiere 24 unidades del depósito a "Camioneta 1"
- **THEN** se acepta: el depósito queda en 48 y "Camioneta 1" en 72
- **AND** el stock total de Vino A y su costo promedio no cambian
- **Regla:** RUT-02; STK-07; INV-15

#### Scenario: Doble envío de la carga

- **GIVEN** esa transferencia ya aceptada
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y los saldos no cambian
- **Regla:** SYN-02; INV-06

### Requirement: La toma y los movimientos concurrentes se ordenan

Una apertura y un movimiento simultáneos sobre la misma ubicación DEBEN ordenarse: o el movimiento queda confirmado antes de la toma, o encuentra la ubicación tomada y se le aplica esta regla; NO DEBE quedar un movimiento ajeno confirmado después de la toma. Una liberación o un cierre y un movimiento de esa jornada DEBEN ordenarse del mismo modo, sin interbloqueo (`02` §7.3; `design.md` D9).

#### Scenario: Apertura y transferencia ajena simultáneas

- **GIVEN** "Camioneta 1" libre, Juan a punto de abrir y Pedro a punto de transferirle 6 unidades
- **WHEN** las dos operaciones se envían al mismo tiempo
- **THEN** o la transferencia de Pedro se confirma y la jornada de Juan abre con ese stock, o la jornada abre y Pedro recibe `UBICACION_TOMADA`
- **AND** en ningún caso hay un movimiento de Pedro posterior a la apertura
- **Regla:** STK-09; `02` §7.3

#### Scenario: Liberación y movimiento de la jornada simultáneos

- **GIVEN** la jornada `ABIERTA` de Juan sobre "Camioneta 1"
- **WHEN** una Supervisora la libera en el mismo instante en que Juan transfiere 6 unidades desde "Camioneta 1"
- **THEN** las dos operaciones terminan sin interbloqueo
- **AND** el saldo de "Camioneta 1" es igual a la suma de sus movimientos
- **Regla:** STK-09; INV-12; `02` §7.3
