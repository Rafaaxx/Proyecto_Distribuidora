## ADDED Requirements

### Requirement: Toda autorización sin conexión deja una observación

Una venta sin conexión cuyo descuento manual o cuyo exceso de crédito se resolvió por PIN de supervisor o por permiso propio DEBE llevar una observación `AUTORIZACION_OFFLINE` por cada autorización, con el tipo (`DESCUENTO` o `CREDITO`), la resolución, el autorizador y si el autorizador conserva el permiso al sincronizar. La venta NO DEBE rechazarse si el autorizador ya no tiene el permiso; un autorizador inexistente o de otra organización DEBE rechazar el comando como dependencia inexistente. El catálogo de SYN-07 suma `AUTORIZACION_OFFLINE`.

#### Scenario: PIN de supervisor sin conexión

- **GIVEN** una venta sin conexión con 10 % manual autorizado por Marta con PIN
- **WHEN** se sincroniza
- **THEN** se acepta con `AUTORIZACION_OFFLINE` tipo `DESCUENTO`, autorizadora Marta y `autorizador_con_permiso = true`
- **Regla:** SEG-05; ADR-011; `02` §12.4

#### Scenario: El autorizador perdió el permiso

- **GIVEN** a Marta le quitaron `SUPERAR_CREDITO` después del bootstrap
- **WHEN** llega una venta con exceso autorizado por su PIN
- **THEN** se acepta con `AUTORIZACION_OFFLINE` tipo `CREDITO` y `autorizador_con_permiso = false`
- **Regla:** SYN-05; INV-17

#### Scenario: Autorizador inexistente

- **WHEN** la venta nombra un autorizador que no existe en la organización
- **THEN** se rechaza y el lote sigue
- **Regla:** SYN-06; INV-21

#### Scenario: Doble envío

- **WHEN** el lote reenvía la venta
- **THEN** devuelve el resultado original sin duplicar la observación
- **Regla:** INV-06
