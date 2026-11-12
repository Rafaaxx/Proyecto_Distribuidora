## ADDED Requirements

### Requirement: La rendición mueve la ubicación tomada por su jornada

Las diferencias de la rendición y la salida de la devolución del remanente en el cierre DEBEN pasar la regla de toma sobre la ubicación de la jornada que se rinde o se cierra, aunque quien rinde no sea el usuario de la jornada ni tenga `LIBERAR_UBICACION`, y DEBEN quedar con el `jornada_id` de esa jornada. La excepción NO DEBE alcanzar a ninguna otra ubicación ni a ningún otro comando, y DEBE fallar cerrada (STK-09; `design.md` D3, D6).

#### Scenario: La rendición escribe sobre el vehículo tomado
- **GIVEN** "Camioneta 1" tomada por la jornada entregada de Juan y una Supervisora sin `LIBERAR_UBICACION`
- **WHEN** la Supervisora rinde con un faltante de 3 de Vino A
- **THEN** el `DIFERENCIA_RENDICION` se escribe con la jornada de Juan, sin `UBICACION_TOMADA`
- **Regla:** STK-09; RUT-06

#### Scenario: La excepción no alcanza a una transferencia común
- **GIVEN** "Camioneta 1" con la jornada de Juan `EN_RENDICION`
- **WHEN** la Supervisora, sin `LIBERAR_UBICACION`, envía `STOCK_TRANSFERIR` desde "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA` y no se escribe nada
- **Regla:** STK-09

#### Scenario: La devolución del cierre sale del vehículo tomado
- **GIVEN** la jornada de Juan `EN_RENDICION`
- **WHEN** la Supervisora la cierra devolviendo el remanente al depósito
- **THEN** la salida de "Camioneta 1" se escribe con la jornada de Juan y la entrada del depósito sin jornada
- **Regla:** STK-09; RUT-08
