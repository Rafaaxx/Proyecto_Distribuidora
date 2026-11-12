## MODIFIED Requirements

### Requirement: La jornada se rinde y se cierra siguiendo su máquina de estados

`JORNADA_RENDIR` DEBE pasar una jornada de `ABIERTA` a `EN_RENDICION` y `JORNADA_CERRAR` de `EN_RENDICION` a `CERRADA`; ambos exigen `RENDIR_JORNADA`, son solo `ONLINE` y valen sobre la jornada de cualquier usuario de la organización (`01` §18, §19). Desde el change 24, `JORNADA_RENDIR` (v2) DEBE exigir que la jornada esté entregada (`JORNADA_SIN_ENTREGA`) y DEBE registrar el conteo físico y sus diferencias (RUT-05, RUT-06; spec `stock/rendicion-de-jornada`); la v1, sin conteo, NO DEBE aceptarse más. `JORNADA_CERRAR` (v1 y v2) DEBE liberar la ubicación (RUT-08); la v2 admite devolver el remanente. Cualquier otra transición DEBE rechazarse con `JORNADA_ESTADO_INVALIDO` (409) sin modificar la jornada. Cada transición DEBE guardar su momento y su usuario. La entrega del día NO es una transición: la jornada entregada sigue `ABIERTA` (`design.md` D1).

#### Scenario: Rendir una jornada abierta

- **GIVEN** una jornada `ABIERTA` y entregada de Juan sobre "Camioneta 1" y una Supervisora con `RENDIR_JORNADA`
- **WHEN** la Supervisora envía `JORNADA_RENDIR` v2 con el conteo completo
- **THEN** la jornada queda `EN_RENDICION` con el momento y el usuario de la rendición y su conteo
- **AND** "Camioneta 1" sigue tomada
- **Regla:** `01` §18; RUT-05; RUT-06

#### Scenario: Rendir una jornada sin entrega

- **GIVEN** una jornada `ABIERTA` sin entrega
- **WHEN** se envía `JORNADA_RENDIR` v2
- **THEN** se rechaza con `JORNADA_SIN_ENTREGA` y la jornada sigue `ABIERTA`
- **Regla:** RUT-05

#### Scenario: Cerrar una jornada en rendición libera la ubicación

- **GIVEN** una jornada `EN_RENDICION` sobre "Camioneta 1"
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_CERRAR`
- **THEN** la jornada queda `CERRADA` con el momento y el usuario del cierre
- **AND** "Camioneta 1" queda libre
- **Regla:** RUT-08; `01` §18

#### Scenario: Cerrar una jornada que no se rindió

- **GIVEN** una jornada `ABIERTA`, entregada o no
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_CERRAR`
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO` y la jornada sigue `ABIERTA`
- **Regla:** `01` §18

#### Scenario: Rendir dos veces

- **GIVEN** una jornada `EN_RENDICION`
- **WHEN** llega un `JORNADA_RENDIR` con otro `operation_id`
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO`
- **Regla:** `01` §18

#### Scenario: Transición sobre una jornada terminada

- **GIVEN** una jornada `CERRADA` y otra `LIBERADA`
- **WHEN** se envía `JORNADA_RENDIR` o `JORNADA_CERRAR` sobre cualquiera de las dos
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO`
- **Regla:** `01` §18; TR-06

#### Scenario: El vendedor no rinde su propia jornada

- **GIVEN** Juan, Vendedor, sin `RENDIR_JORNADA`, con su jornada `ABIERTA`
- **WHEN** envía `JORNADA_RENDIR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO`
- **Regla:** RUT-05; `01` §19

#### Scenario: Jornada de otra organización

- **GIVEN** una jornada de otra organización
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_RENDIR` o `JORNADA_CERRAR` sobre ella
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: Doble envío del cierre

- **GIVEN** un `JORNADA_CERRAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original y la jornada sigue `CERRADA` con los datos del primer cierre
- **Regla:** SYN-02; INV-06
