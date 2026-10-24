# Crédito en la venta — Especificación

## Purpose

Define cómo la venta evalúa el crédito del cliente con las políticas ADVERTIR, AUTORIZAR y BLOQUEAR, con y sin conexión, quién puede superar un exceso y qué evaluación queda congelada en la venta (CRE-02 a CRE-10, ADR-003).

## Requirements

### Requirement: La venta evalúa el crédito con el saldo actual del cliente

Al confirmar con conexión, el sistema DEBE evaluar el crédito con el saldo del cliente tomado en la misma transacción, el total de la venta y la cobranza registrada con ella: saldo resultante = saldo + total − cobranza (CRE-02); exceso = la parte no cobrada de la venta que queda por encima del límite. Un cliente sin límite NO DEBE tener control (CRE-01). La política aplicada DEBE ser la del cliente o, si no tiene, la de la organización (CRE-03).

#### Scenario: Ejemplo de la regla

- **GIVEN** límite $200.000, saldo $150.000, venta $80.000 con cobranza $20.000
- **WHEN** se evalúa
- **THEN** el saldo resultante es $210.000 y el exceso $10.000
- **Regla:** CRE-02; CRE-03

#### Scenario: Una venta cobrada entera no tiene exceso

- **GIVEN** un cliente con límite $200.000 y saldo $210.000
- **WHEN** se confirma una venta de $30.000 cobrada entera
- **THEN** el exceso es $0 y la venta se confirma sin autorización
- **Regla:** CRE-02; CRE-07

#### Scenario: Cliente sin límite

- **GIVEN** un cliente sin límite cargado y saldo $500.000
- **WHEN** se confirma una venta de $80.000 sin cobranza
- **THEN** se confirma sin evaluación de exceso y la venta congela el saldo considerado con límite, disponible y exceso vacíos
- **Regla:** CRE-01; CRE-10

#### Scenario: Dos ventas simultáneas al mismo cliente

- **GIVEN** límite $200.000, saldo $150.000, política BLOQUEAR y dos ventas de $40.000 sin cobranza confirmadas a la vez
- **WHEN** las dos terminan
- **THEN** una se confirma y la otra se rechaza con `CREDITO_EXCEDIDO`, porque evalúa con la deuda de la primera
- **Regla:** CRE-02; INV-13

### Requirement: Cada política resuelve el exceso con conexión

Con exceso y conexión: **ADVERTIR** DEBE exigir que el contenido acepte el exceso (si no, 409 `EXCESO_CREDITO_SIN_ACEPTAR`) y DEBE dejar la observación `EXCESO_CREDITO_ADVERTIDO`; **AUTORIZAR** DEBE confirmarse por permiso propio `SUPERAR_CREDITO` o por un autorizador con ese permiso y su PIN verificado, y si no, 403 `AUTORIZACION_CREDITO_REQUERIDA` o `AUTORIZADOR_SIN_PERMISO`; **BLOQUEAR** DEBE rechazar con 409 `CREDITO_EXCEDIDO` sin excepción de permiso. Todo rechazo DEBE devolver límite, saldo considerado, disponible, exceso y política, y NO DEBE dejar nada escrito.

#### Scenario: ADVERTIR aceptado

- **GIVEN** política ADVERTIR y exceso $10.000
- **WHEN** se confirma aceptando el exceso
- **THEN** se acepta con resolución `ADVERTENCIA_ACEPTADA` y la observación `EXCESO_CREDITO_ADVERTIDO`
- **Regla:** CRE-04

#### Scenario: ADVERTIR sin aceptar

- **WHEN** se confirma sin aceptar el exceso
- **THEN** se rechaza con `EXCESO_CREDITO_SIN_ACEPTAR` y la respuesta trae el exceso de $10.000
- **Regla:** CRE-04; INV-01

#### Scenario: AUTORIZAR con PIN de supervisor

- **GIVEN** política AUTORIZAR, Pedro sin `SUPERAR_CREDITO` y Marta con `SUPERAR_CREDITO` que ingresa su PIN
- **WHEN** se confirma
- **THEN** se acepta con resolución `PIN_SUPERVISOR` y Marta como autorizadora del crédito
- **Regla:** CRE-05; SEG-05

#### Scenario: AUTORIZAR con permiso propio

- **GIVEN** un Supervisor con `SUPERAR_CREDITO`
- **WHEN** confirma una venta con exceso
- **THEN** se acepta con resolución `PERMISO_PROPIO`
- **Regla:** CRE-05

#### Scenario: AUTORIZAR sin autorización

- **WHEN** Pedro confirma con exceso sin autorizador
- **THEN** se rechaza con `AUTORIZACION_CREDITO_REQUERIDA`
- **Regla:** CRE-05

#### Scenario: BLOQUEAR aunque tenga el permiso

- **GIVEN** política BLOQUEAR y un Administrador con `SUPERAR_CREDITO`
- **WHEN** confirma con exceso
- **THEN** se rechaza con `CREDITO_EXCEDIDO`
- **Regla:** CRE-07

#### Scenario: BLOQUEAR se resuelve cobrando más

- **GIVEN** política BLOQUEAR y exceso $10.000
- **WHEN** se vuelve a confirmar con $10.000 más de cobranza
- **THEN** se acepta con resolución `SIN_EXCESO`
- **Regla:** CRE-07

### Requirement: La venta congela su evaluación de crédito

Toda venta confirmada desde este change DEBE congelar límite, saldo considerado, disponible, exceso, política aplicada, resolución (`SIN_EXCESO`, `ADVERTENCIA_ACEPTADA`, `PERMISO_PROPIO`, `PIN_SUPERVISOR`, `TOLERANCIA_OFFLINE`) y autorizador; el modo de confirmación ya distingue con y sin conexión. Esos valores NO DEBEN cambiar después (INV-10).

#### Scenario: El snapshot no cambia cuando cambia el límite

- **GIVEN** una venta confirmada con límite $200.000
- **WHEN** después se cambia el límite del cliente a $300.000
- **THEN** la venta sigue mostrando $200.000
- **Regla:** CRE-10; INV-10

#### Scenario: El usuario de aplicación no puede modificar el snapshot

- **WHEN** se intenta actualizar una columna de crédito de una venta
- **THEN** la base lo rechaza por falta de privilegio
- **Regla:** INV-10; TR-06

### Requirement: El consumidor final solo compra de contado

El consumidor final DEBE evaluarse con límite cero y ninguna autorización DEBE permitirle quedar debiendo: con conexión rige `CONSUMIDOR_FINAL_CONTADO` antes que el crédito; sin conexión solo `CONSUMIDOR_FINAL_CON_DEUDA` (o `CLIENTE_NO_HABILITADO`), sin observaciones de crédito adicionales.

#### Scenario: Con PIN de supervisor tampoco

- **GIVEN** el consumidor final y una venta de $5.000 con cobranza de $3.000 y un supervisor que ingresa su PIN
- **WHEN** se confirma con conexión
- **THEN** se rechaza con `CONSUMIDOR_FINAL_CONTADO`
- **Regla:** CLI-03; VTA-11

#### Scenario: De contado

- **WHEN** se le vende $5.000 con cobranza de $5.000
- **THEN** se confirma con límite cero y resolución `SIN_EXCESO`
- **Regla:** CLI-03; CRE-10

### Requirement: Sin conexión el servidor congela la evaluación del dispositivo y nunca rechaza por crédito

Sin conexión, el sistema DEBE congelar la evaluación que hizo el dispositivo (límite, saldo considerado, política, resolución y autorizador; disponible y exceso calculados sobre esos valores), DEBE recalcular con el saldo real y la política vigente y NO DEBE rechazar la venta por crédito (CRE-09, SYN-05). DEBE observar: `EXCESO_CREDITO_ADVERTIDO` (advertencia aceptada), `EXCESO_CREDITO_AUTORIZADO_OFFLINE` (dentro de la tolerancia), `AUTORIZACION_OFFLINE` (PIN o permiso propio) y `EXCESO_CREDITO_DETECTADO_SYNC` cuando el real da exceso y el dispositivo no lo vio. El objeto `credito` del dispositivo es obligatorio sin conexión (la aplicación no tiene versiones anteriores en uso; decisión del usuario del 2026-10-23); solo DEBE rechazar un `credito` ausente o incoherente consigo mismo (`CREDITO_INCONSISTENTE`, 422) o un autorizador inexistente o ajeno. El servidor NO DEBE validar el tamaño de la tolerancia que usó el dispositivo (no la envía): solo exige exceso mayor que cero cuando la resolución no es `SIN_EXCESO`, y un exceso cero con otra resolución se acepta tal cual.

#### Scenario: Dentro de la tolerancia

- **GIVEN** exceso $10.000 y tolerancia $20.000
- **WHEN** llega con resolución `TOLERANCIA_OFFLINE`
- **THEN** se acepta con `EXCESO_CREDITO_AUTORIZADO_OFFLINE`
- **Regla:** CRE-06

#### Scenario: Exceso que el dispositivo no vio

- **GIVEN** el dispositivo vio saldo $100.000 y la oficina registró después otra venta, así que el saldo real es $190.000
- **WHEN** llega una venta de $30.000 sin cobranza con resolución `SIN_EXCESO` y límite $200.000
- **THEN** se acepta, congela la evaluación del dispositivo y agrega `EXCESO_CREDITO_DETECTADO_SYNC` con las dos evaluaciones
- **Regla:** CRE-08; CRE-09; INV-17

#### Scenario: Resolución incoherente

- **WHEN** llega una evaluación con exceso $10.000 según sus propios valores y resolución `SIN_EXCESO`
- **THEN** se rechaza con `CREDITO_INCONSISTENTE` y el lote sigue
- **Regla:** SYN-06

#### Scenario: Sin el objeto de crédito

- **WHEN** llega una venta sin conexión sin el objeto `credito`, o con el saldo considerado, la política o la resolución ausentes
- **THEN** se rechaza con `CREDITO_INCONSISTENTE` sin dejar nada escrito y el lote sigue
- **Regla:** SYN-06; INV-01

#### Scenario: Resolución con autorizador faltante o sin límite

- **WHEN** llega `PIN_SUPERVISOR` o `PERMISO_PROPIO` sin autorizador, o una resolución distinta de `SIN_EXCESO` sin límite
- **THEN** se rechaza con `CREDITO_INCONSISTENTE`
- **Regla:** SYN-06; CRE-05

#### Scenario: La tolerancia del dispositivo no se valida

- **GIVEN** una venta con exceso de $21.250 y resolución `TOLERANCIA_OFFLINE`
- **WHEN** se sincroniza, aunque la tolerancia de hoy sea menor
- **THEN** se acepta con `EXCESO_CREDITO_AUTORIZADO_OFFLINE` con el exceso en el detalle
- **Regla:** CRE-06; SYN-05

#### Scenario: Exceso cero con otra resolución

- **WHEN** llega una evaluación sin exceso propio y con resolución `ADVERTENCIA_ACEPTADA`
- **THEN** se acepta tal cual, con la observación de su resolución
- **Regla:** SYN-05; INV-17

#### Scenario: Política BLOQUEAR al sincronizar

- **GIVEN** la política del cliente pasó a BLOQUEAR después del bootstrap
- **WHEN** llega una venta con resolución `TOLERANCIA_OFFLINE`
- **THEN** se acepta con su observación; el servidor nunca rechaza por crédito
- **Regla:** CRE-09; SYN-05

#### Scenario: Consumidor final sin conexión

- **GIVEN** una venta al consumidor final con deuda, con la evaluación del dispositivo de cualquier resolución
- **WHEN** se sincroniza
- **THEN** se congela con límite cero y solo queda `CONSUMIDOR_FINAL_CON_DEUDA`, sin observaciones de crédito
- **Regla:** CLI-03; VTA-11; INV-17

#### Scenario: Doble envío por el lote

- **WHEN** el lote reenvía la misma venta
- **THEN** devuelve el resultado original con las mismas observaciones
- **Regla:** INV-06; SYN-02
