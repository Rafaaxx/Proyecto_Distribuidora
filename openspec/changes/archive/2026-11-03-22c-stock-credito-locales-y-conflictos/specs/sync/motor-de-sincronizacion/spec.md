## MODIFIED Requirements

### Requirement: El resultado de cada operación se escribe en el teléfono

Por cada resultado del lote, identificado por su `operation_id` y nunca por su posición, el teléfono DEBE dejar el comando con su resultado, su código de error y sus observaciones (código, operación y detalle), y la venta con el estado de envío «Enviada» (`ACEPTADO`), «Con observaciones» (`ACEPTADO_CON_OBSERVACIONES`) o «Rechazada» (`RECHAZADO`). Los resultados de un lote, con sus observaciones, DEBEN escribirse todos o ninguno. Un error transitorio y los ítems que el servidor no llegó a procesar DEBEN quedar «Sin enviar». Ninguna venta, cobranza, movimiento ni comando DEBE borrarse por recibir su resultado (`design.md` D3; D3 del 22b).

#### Scenario: Venta aceptada
- **GIVEN** la venta V03-000142 sin enviar
- **WHEN** el servidor responde `ACEPTADO`
- **THEN** la venta queda «Enviada» y su comando con resultado `ACEPTADO` y sin observaciones, y los dos siguen en el teléfono
- **Regla:** SYN-04; SYN-09

#### Scenario: Venta con observaciones
- **GIVEN** una venta sin conexión que superó el crédito por tolerancia
- **WHEN** el servidor responde `ACEPTADO_CON_OBSERVACIONES` con `EXCESO_CREDITO_AUTORIZADO_OFFLINE`
- **THEN** la venta queda «Con observaciones» y su comando guarda esa observación con su detalle
- **Regla:** SYN-04; SYN-05; SYN-07

#### Scenario: Venta rechazada
- **GIVEN** una venta cuyo sobre llega con una jornada inexistente
- **WHEN** el servidor responde `RECHAZADO` con `JORNADA_INEXISTENTE`
- **THEN** la venta queda «Rechazada» con ese código y sigue visible en el teléfono
- **Regla:** SYN-06; SYN-09

#### Scenario: Corte a mitad del lote
- **GIVEN** un lote de tres ventas
- **WHEN** el servidor acepta la primera y responde `ERROR_TRANSITORIO` en la segunda
- **THEN** la primera queda «Enviada» y la segunda y la tercera siguen «Sin enviar»
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Falla al escribir los resultados
- **GIVEN** una respuesta de lote con dos resultados, uno con observaciones
- **WHEN** la escritura local falla después del primero
- **THEN** ninguna de las dos ventas cambia de estado, ninguna observación queda guardada y el próximo envío las manda otra vez
- **Regla:** INV-01; INV-06

#### Scenario: Respuesta sin observaciones
- **GIVEN** una respuesta de lote de un servidor anterior, sin la lista de observaciones
- **WHEN** el teléfono la aplica
- **THEN** escribe el estado y el código como siempre y deja las observaciones sin dato
- **Regla:** SYN-04; `02` §6.6
