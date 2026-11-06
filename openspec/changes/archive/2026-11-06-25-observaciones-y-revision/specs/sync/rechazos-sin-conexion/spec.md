## Purpose

Define qué guarda el servidor de una operación sin conexión que no acepta (venta, anulación, cobranza o entrega del día rechazada por el lote) y cómo administración la revisa y la da por resuelta, con su corrección cargada con conexión si la operación ocurrió (SYN-06, SYN-08, SYN-09).

## ADDED Requirements

### Requirement: El lote guarda cada rechazo sin conexión

Cuando el lote responde RECHAZADO a un comando en modo `OFFLINE` de un dispositivo activo, el servidor DEBE guardarlo en el registro de rechazos, en una transacción aparte, con organización, `operation_id`, tipo, versión, usuario, dispositivo, jornada (si existe en la organización), secuencia, momento, versión de la aplicación, contenido completo, código del rechazo y momento de llegada, en estado `PENDIENTE`. El rechazo NO DEBE producir ningún efecto de negocio. NO DEBEN guardarse: un ítem que trae credenciales, un lote rechazado entero por cola ajena, ni un comando de un dispositivo revocado (va a la cuarentena). Si el registro no puede escribirse por un error transitorio, el ítem DEBE informarse como error transitorio y cortar el lote (`design.md` D6).

#### Scenario: Venta con totales incoherentes
- **GIVEN** una venta sin conexión de Juan a Kiosco La Esquina cuyo total no coincide con sus líneas
- **WHEN** llega en el lote
- **THEN** se responde RECHAZADO con `TOTALES_INCONSISTENTES`
- **AND** queda un rechazo `PENDIENTE` con su contenido completo, la jornada y el código
- **AND** no hay venta, movimientos ni fila de comando
- **Regla:** SYN-05; SYN-06

#### Scenario: Rechazo con fila de comando
- **GIVEN** una anulación sin conexión de una venta que no existe
- **WHEN** llega en el lote
- **THEN** se responde RECHAZADO con `VENTA_INEXISTENTE` y queda también su rechazo `PENDIENTE`
- **Regla:** SYN-06; ADR-066

#### Scenario: Cobranza con medios que no suman
- **GIVEN** una cobranza sin conexión cuyos medios no suman el importe
- **WHEN** llega en el lote
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y queda su rechazo
- **Regla:** INV-08; SYN-05; ADR-067

#### Scenario: Jornada inexistente
- **WHEN** llega una venta sin conexión con una jornada que no existe en la organización
- **THEN** se rechaza con `JORNADA_INEXISTENTE` y el rechazo queda guardado sin jornada
- **Regla:** SYN-06; INV-21

#### Scenario: El rechazo no corta el lote
- **GIVEN** un lote con una venta rechazada y una cobranza válida después
- **WHEN** se procesa
- **THEN** la cobranza se acepta y queda un solo rechazo
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Dispositivo revocado y credenciales
- **WHEN** llega un comando de un dispositivo revocado, o un ítem con credenciales
- **THEN** el primero va solo a la cuarentena y el segundo no se guarda en ningún lado
- **Regla:** SYN-06; ADR-056

#### Scenario: Doble envío del rechazado
- **GIVEN** un rechazo ya guardado
- **WHEN** el teléfono envía otra vez el mismo `operation_id`
- **THEN** se responde el mismo rechazo y sigue habiendo un solo registro
- **Regla:** SYN-02; INV-06

#### Scenario: Error transitorio al guardar
- **GIVEN** que guardar el rechazo falla por un error transitorio de la base
- **WHEN** se procesa el lote
- **THEN** ese ítem vuelve como error transitorio y los siguientes no se procesan
- **Regla:** SYN-03; SYN-09 (no se pierde)

### Requirement: Los rechazos se leen por organización y no se borran

`GET /api/v1/observaciones/rechazos` (con `REVISAR_OBSERVACIONES`) DEBE devolver los rechazos y las cuarentenas de la organización del token, con el origen (rechazo o teléfono dado de baja), el tipo, quién y en qué jornada, el código, el resumen legible del contenido (cliente, número, total, líneas o importe y medios) aunque el contenido esté mal formado, si el mismo `operation_id` se aceptó después, y la resolución. DEBE filtrar por estado, origen, tipo, usuario y jornada. La aplicación NO DEBE poder borrar un rechazo (INV-05).

#### Scenario: Resumen del contenido
- **GIVEN** la venta rechazada de Juan a Kiosco La Esquina
- **WHEN** se lee la lista
- **THEN** muestra el cliente, el número de la venta, el total y las líneas que envió el teléfono
- **Regla:** SYN-06; SYN-09

#### Scenario: Contenido con un cliente que no existe
- **GIVEN** un rechazo por `RECURSO_NO_ENCONTRADO` cuyo cliente no existe
- **WHEN** se lee
- **THEN** el resumen lo indica sin fallar
- **Regla:** SYN-06

#### Scenario: Otra organización
- **WHEN** un usuario de la organización A lee rechazos o pide uno de la organización B
- **THEN** no los ve y el pedido de uno responde 404
- **Regla:** INV-21; INV-02

#### Scenario: La aplicación no puede borrar un rechazo
- **WHEN** la aplicación intenta borrar un rechazo
- **THEN** la base lo impide
- **Regla:** INV-05

### Requirement: Un rechazo se resuelve con comentario y, si ocurrió, con su corrección

El sistema DEBE ofrecer `RECHAZO_RESOLVER` v1, solo `ONLINE`, con `REVISAR_OBSERVACIONES`, que resuelve un rechazo o una cuarentena `PENDIENTE` de la organización con un comentario de 1 a 500 caracteres y, opcionalmente, un vínculo a la operación que lo corrige: una venta para una venta rechazada, una cobranza para una cobranza rechazada; los demás tipos, incluida la anulación rechazada, no admiten vínculo y se resuelven solo con comentario (decisión del 2026-11-06). Resolver NO DEBE reenviar ni reprocesar el comando ni crear ninguna operación (SYN-08, `design.md` D7). Mientras una jornada tenga rechazos `PENDIENTE`, su rendición se rechaza con `RECHAZOS_PENDIENTES`; las cuarentenas no cuentan para eso (`design.md` D9 = B, spec `stock/rendicion-de-jornada`). `sync/service.py` DEBE ofrecer la cantidad de rechazos `PENDIENTE` de una jornada de la organización, en una sola consulta sobre el índice parcial, y registrarla como el puerto que declara `stock/service.py`.

#### Scenario: Venta rechazada corregida con conexión
- **GIVEN** la venta rechazada de Juan y la venta que la Supervisora cargó con conexión
- **WHEN** resuelve el rechazo con un comentario y el vínculo a esa venta
- **THEN** el rechazo queda `RESUELTO` con usuario, momento, comentario y vínculo, y no se crea ni cambia ninguna venta
- **Regla:** SYN-08; SYN-06

#### Scenario: La venta no ocurrió
- **WHEN** se resuelve una venta rechazada sin vínculo, con el comentario «El cliente devolvió la mercadería»
- **THEN** queda resuelta sin vínculo
- **Regla:** SYN-08

#### Scenario: Resolver el último rechazo de la jornada habilita la rendición
- **GIVEN** una jornada entregada con un solo rechazo `PENDIENTE`
- **WHEN** se resuelve
- **THEN** la cantidad de rechazos pendientes de la jornada es cero y su rendición ya no se rechaza con `RECHAZOS_PENDIENTES`
- **Regla:** SYN-08; RUT-05

#### Scenario: Cantidad pendiente por jornada
- **GIVEN** dos rechazos `PENDIENTE` y uno `RESUELTO` de la jornada de Juan, uno `PENDIENTE` de otra jornada, uno `PENDIENTE` sin jornada y uno de otra organización
- **WHEN** se pide la cantidad pendiente de la jornada de Juan
- **THEN** es 2
- **Regla:** INV-21; RUT-05

#### Scenario: Vínculo de otro tipo
- **WHEN** se resuelve una cobranza rechazada vinculándola a una venta, o una anulación rechazada vinculándola a cualquier venta
- **THEN** se rechaza con `VINCULO_INVALIDO` (422) y nada cambia
- **Regla:** SYN-08

#### Scenario: Anulación rechazada sin vínculo
- **GIVEN** una anulación sin conexión rechazada (por ejemplo, `VENTA_YA_ANULADA`)
- **WHEN** se resuelve solo con un comentario
- **THEN** queda `RESUELTO` con el comentario y sin vínculo
- **Regla:** SYN-08

#### Scenario: Vínculo inexistente o ajeno
- **WHEN** el vínculo apunta a una venta que no existe o es de otra organización
- **THEN** responde 404 y nada cambia
- **Regla:** INV-21

#### Scenario: Ya resuelto
- **GIVEN** un rechazo ya resuelto
- **WHEN** se intenta resolverlo otra vez con otro `operation_id`
- **THEN** se rechaza con `RECHAZO_YA_RESUELTO` (409)
- **Regla:** `01` §18

#### Scenario: Sin permiso
- **WHEN** el Vendedor intenta resolver un rechazo
- **THEN** responde 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19

#### Scenario: Doble envío de la resolución
- **GIVEN** una resolución de rechazo ya aceptada
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** devuelve el resultado original
- **Regla:** SYN-02; INV-06

#### Scenario: Dos resoluciones a la vez
- **WHEN** dos usuarios resuelven el mismo rechazo al mismo tiempo
- **THEN** uno se acepta y el otro recibe `RECHAZO_YA_RESUELTO`
- **Regla:** INV-01
