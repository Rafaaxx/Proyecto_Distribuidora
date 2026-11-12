## ADDED Requirements

### Requirement: Una ubicación tomada no se desactiva ni cambia de tipo o de toma

Mientras una ubicación tiene una jornada `ABIERTA` o `EN_RENDICION`, `UBICACION_MODIFICAR` NO DEBE desactivarla ni cambiar su tipo ni su indicador de toma: DEBE rechazarse con `UBICACION_TOMADA` (409) sin modificar nada (STK-02, RUT-01; `design.md` D14). El nombre DEBE poder cambiarse. Cuando la jornada se cierra o se libera, la ubicación vuelve a regirse solo por sus reglas anteriores (`UBICACION_CON_STOCK`).

#### Scenario: Desactivar un vehículo tomado y sin stock

- **GIVEN** "Camioneta 2" sin stock, tomada por la jornada `ABIERTA` de Pedro
- **WHEN** se envía `UBICACION_MODIFICAR` con `activo = false`
- **THEN** se rechaza con `UBICACION_TOMADA` y la ubicación sigue activa
- **Regla:** RUT-01; ADR-038

#### Scenario: Quitar la toma a una ubicación tomada

- **GIVEN** una ubicación de tipo `OTRO` con `requiere_toma` verdadero y una jornada `EN_RENDICION`
- **WHEN** se envía `UBICACION_MODIFICAR` con `requiere_toma = false`
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-02; INV-16

#### Scenario: Renombrar una ubicación tomada

- **GIVEN** "Camioneta 2" tomada por la jornada de Pedro
- **WHEN** se envía `UBICACION_MODIFICAR` cambiando solo el nombre a "Camioneta 2 (Kangoo)"
- **THEN** se acepta y la jornada sigue sobre esa ubicación
- **Regla:** STK-02

#### Scenario: Desactivar después del cierre

- **GIVEN** "Camioneta 2" sin stock, cuya jornada quedó `CERRADA`
- **WHEN** se envía `UBICACION_MODIFICAR` con `activo = false`
- **THEN** se acepta
- **Regla:** RUT-08; ADR-038
