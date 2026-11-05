## ADDED Requirements

### Requirement: Lo que llega con la jornada ya rendida se acepta con observación

Una venta, una anulación de venta o una cobranza sin conexión cuya jornada del sobre está `EN_RENDICION` o `CERRADA` DEBE aceptarse (INV-17) con una observación `JORNADA_RENDIDA` sobre la operación (detalle: jornada y momento de la rendición), además de las que ya correspondan. `JORNADA_RENDIDA` DEBE pertenecer al catálogo de SYN-07 (`design.md` D7).

#### Scenario: Venta tardía
- **GIVEN** la jornada de Juan rendida a las 18:00
- **WHEN** llega una venta sin conexión de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA` y `UBICACION_TOMADA_AL_SINCRONIZAR`, y descuenta el stock sin jornada
- **Regla:** SYN-05; SYN-07; INV-17; STK-09

#### Scenario: Cobranza tardía con la jornada cerrada
- **GIVEN** la jornada de Juan `CERRADA`
- **WHEN** llega una cobranza sin conexión de $50.000 a Kiosco La Esquina de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA` y baja el saldo del cliente
- **Regla:** SYN-05; INV-17; RUT-05

#### Scenario: Anulación tardía
- **GIVEN** la jornada de Juan `EN_RENDICION`
- **WHEN** llega una anulación sin conexión de una venta de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA`
- **Regla:** SYN-07; VTA-24

#### Scenario: Doble envío de la operación tardía
- **GIVEN** una cobranza tardía ya aceptada con `JORNADA_RENDIDA`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original y no se registra otra observación
- **Regla:** SYN-02; INV-06
