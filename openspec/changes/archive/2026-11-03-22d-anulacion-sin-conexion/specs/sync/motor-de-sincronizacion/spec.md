## ADDED Requirements

### Requirement: El resultado de una anulación se escribe en el teléfono

El resultado de una anulación, identificado por su `operation_id`, DEBE dejar su comando con el resultado, el código y las observaciones, y la anulación con su estado de envío, en la misma transacción que el resto de los resultados del lote. El estado de envío de la venta anulada NO DEBE cambiar por el resultado de su anulación (`design.md` D6, D7).

#### Scenario: Anulación aceptada
- **GIVEN** la venta V03-000142 «Enviada» y su anulación sin enviar
- **WHEN** el servidor acepta la anulación
- **THEN** la anulación queda «Enviada» y la venta sigue «Enviada»
- **Regla:** SYN-04; SYN-09

#### Scenario: Anulación con observaciones
- **WHEN** el servidor acepta la anulación con `JORNADA_LIBERADA`
- **THEN** la anulación queda «Con observaciones» y su comando guarda la observación con su detalle
- **Regla:** SYN-04; SYN-07; RUT-09

#### Scenario: Anulación rechazada
- **WHEN** el servidor rechaza la anulación con `VENTA_YA_ANULADA`
- **THEN** la anulación queda «Rechazada» con ese código, sigue visible y no se reenvía sola
- **Regla:** SYN-06; SYN-09

#### Scenario: Falla al escribir los resultados
- **GIVEN** una respuesta con el resultado de una venta y el de su anulación
- **WHEN** la escritura local falla después del primero
- **THEN** ninguna de las dos cambia de estado y el próximo envío las manda otra vez
- **Regla:** INV-01; INV-06

#### Scenario: Doble envío
- **WHEN** el servidor devuelve otra vez el resultado de una anulación ya escrita
- **THEN** la anulación y su comando no cambian
- **Regla:** INV-06; SYN-02

### Requirement: Con señal, el teléfono se entera de que su jornada ya no está abierta

En cada sincronización con señal (al abrir, al volver la señal o a primer plano, después de cada operación, cada 2 minutos y con «Sincronizar») el teléfono DEBE consultar el estado de la jornada de su sesión. También DEBE darla por no abierta cuando el bootstrap o «Actualizar datos» responde `JORNADA_REQUERIDA`, cuando la consulta al entrar no encuentra su jornada abierta y cuando un resultado del lote trae `JORNADA_LIBERADA` sobre una operación de esa jornada. Lo que aprende DEBE guardarse en la base local con la jornada y su estado, de modo que valga sin señal y después de recargar, hasta que se aplique el bootstrap de otra jornada. Sin señal, o si la consulta falla o no está permitida, NO DEBE cambiar nada. La cola DEBE seguir enviándose (`design.md` D8).

#### Scenario: Jornada liberada durante el día
- **GIVEN** el teléfono de `vendedor` con su jornada J1 abierta y con señal
- **WHEN** un Supervisor libera J1 desde `/admin` y llega la sincronización periódica
- **THEN** el teléfono guarda que J1 está `LIBERADA`
- **Regla:** RUT-09; `02` §13.3

#### Scenario: Actualizar datos sin jornada
- **WHEN** «Actualizar datos» responde `JORNADA_REQUERIDA`
- **THEN** el teléfono guarda que su jornada ya no está abierta, sin estado conocido
- **Regla:** RUT-03; SYN-11

#### Scenario: Resultado con jornada liberada
- **WHEN** un resultado del lote trae `JORNADA_LIBERADA` sobre una venta de J1
- **THEN** el teléfono guarda que J1 está `LIBERADA`
- **Regla:** RUT-09; SYN-07

#### Scenario: Sin señal
- **GIVEN** J1 liberada en el servidor y el teléfono sin señal
- **WHEN** corre la sincronización periódica
- **THEN** nada cambia en el teléfono
- **Regla:** RUT-09; CRE-08

#### Scenario: Lo vendido se sigue enviando
- **GIVEN** J1 guardada como liberada y dos ventas de J1 sin enviar
- **WHEN** se sincroniza
- **THEN** las dos ventas se envían
- **Regla:** RUT-09; SYN-09

#### Scenario: Jornada nueva
- **GIVEN** J1 guardada como liberada
- **WHEN** el vendedor abre la jornada J2 y se aplica su bootstrap
- **THEN** el teléfono ya no la considera no abierta
- **Regla:** RUT-03

#### Scenario: Doble consulta
- **GIVEN** J1 guardada como liberada
- **WHEN** la consulta devuelve otra vez `LIBERADA`
- **THEN** lo guardado no cambia
- **Regla:** INV-06
