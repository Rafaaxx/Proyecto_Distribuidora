## MODIFIED Requirements

### Requirement: La baja de un usuario no cierra el canal de su cola pendiente

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja la opción aprobada D9.3-B. La segunda parte se implementa en el change 17 (`design.md` D10).

El lote de sincronización NO DEBE rechazar en bloque, por ruta, a un usuario autenticado que está `INACTIVO` o cuyo rol está inactivo. DEBE procesar su lote comando por comando, igual que el de un usuario activo, para que una venta o cobranza registrada sin conexión nunca quede sin forma de llegar al servidor (`00` §3, SYN-05, SYN-09).

Con la verificación de permisos por comando del lote (paso 4 de `02` §6.3), para ese usuario:

- un comando `OFFLINE` DEBE aceptarse con la observación `PERMISO_REVOCADO` (SYN-10);
- un comando `ONLINE` DEBE rechazarse, igual que en REST.

#### Scenario: El lote de un usuario dado de baja no se rechaza en bloque
- **GIVEN** un usuario con un access token todavía vigente, que pasó a `INACTIVO`
- **WHEN** envía un lote de sincronización
- **THEN** el lote no se rechaza como no autenticado por la ruta
- **AND** cada comando recibe su propio resultado, como en el lote de un usuario activo
- **Regla:** ADR-028 (D9.3-B); SYN-05; SYN-09

#### Scenario: Cobranza offline de un usuario dado de baja
- **GIVEN** un vendedor `INACTIVO` con su jornada `ABIERTA` en el dispositivo y una cobranza de `"50000.00"` en la cola
- **WHEN** renueva su sesión con la excepción de jornada no cerrada y envía el lote
- **THEN** la cobranza se acepta con `PERMISO_REVOCADO` y el saldo del cliente baja `"50000.00"`
- **Regla:** ADR-028 (D9.3-B); ADR-049 punto 18; SYN-10

#### Scenario: Comando con conexión de un usuario dado de baja
- **GIVEN** el mismo vendedor `INACTIVO`
- **WHEN** el lote trae un `COBRANZA_REGISTRAR` en modo `ONLINE`
- **THEN** ese comando se rechaza y los demás del lote reciben su propio resultado
- **Regla:** ADR-028; SEG-06

## ADDED Requirements

### Requirement: Un comando sin conexión pertenece a una jornada del usuario y del dispositivo

Un comando en modo `OFFLINE` DEBE traer en su sobre una jornada; si no la trae, DEBE rechazarse con `JORNADA_REQUERIDA`. La jornada DEBE ser del usuario y del dispositivo de la sesión; si es de otro usuario o de otro dispositivo, el comando DEBE rechazarse con `JORNADA_AJENA`. En ambos casos no queda registro del comando ni efecto alguno, y el lote sigue (SYN-06). Una jornada inexistente sigue respondiendo `JORNADA_INEXISTENTE`. Si la jornada es del usuario y del dispositivo, el comando NO DEBE rechazarse por el estado de la jornada: con `ABIERTA` se procesa normalmente; con `LIBERADA` se acepta con la observación `JORNADA_LIBERADA`, que indica la jornada y el momento de la liberación (RUT-09); con `EN_RENDICION` o `CERRADA` se acepta sin observación nueva (`design.md` D12 del change 17).

#### Scenario: Cobranza posterior a una liberación
- **GIVEN** la jornada de la camioneta 2 liberada a las 14:00 con un motivo
- **WHEN** a las 19:00 el dispositivo de esa jornada sincroniza una cobranza de `"50000.00"` hecha a las 11:00
- **THEN** se acepta con `JORNADA_LIBERADA`, el saldo del cliente baja `"50000.00"` y la cobranza queda asociada a esa jornada
- **Regla:** RUT-09; SYN-05; SYN-07

#### Scenario: Jornada abierta
- **GIVEN** la jornada del vendedor `ABIERTA` en su dispositivo
- **WHEN** sincroniza una cobranza en modo `OFFLINE`
- **THEN** se acepta sin `JORNADA_LIBERADA`
- **Regla:** RUT-04; SYN-04

#### Scenario: Jornada ya cerrada
- **GIVEN** la jornada del vendedor ya `CERRADA`
- **WHEN** llega una cobranza en modo `OFFLINE` de esa jornada
- **THEN** se acepta sin observación nueva
- **Regla:** SYN-05; INV-17; `design.md` D12

#### Scenario: Comando sin conexión sin jornada
- **WHEN** llega una cobranza en modo `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA`, sin registro del comando, y el lote sigue
- **Regla:** `02` §6.2; SYN-06

#### Scenario: Jornada de otro vendedor
- **GIVEN** la jornada K de otro vendedor
- **WHEN** llega una cobranza en modo `OFFLINE` cuyo sobre nombra K
- **THEN** se rechaza con `JORNADA_AJENA`, sin registro del comando, y el lote sigue
- **Regla:** SYN-06; `02` §6.4

#### Scenario: Liberación simultánea
- **WHEN** una liberación de la jornada y una cobranza offline de esa jornada se procesan a la vez y confirman
- **THEN** la cobranza queda aceptada sin observación (si se procesó antes) o con `JORNADA_LIBERADA` (si se procesó después), nunca con otro resultado
- **Regla:** RUT-09; `02` §7.3

#### Scenario: Doble envío de una cobranza offline
- **GIVEN** una cobranza offline aceptada con `JORNADA_LIBERADA`
- **WHEN** el dispositivo reenvía el mismo comando en otro lote
- **THEN** recibe el resultado original con la misma observación, sin una segunda cobranza, movimiento ni observación
- **Regla:** INV-06; SYN-02; SYN-09
