## Purpose

Define la bandeja de revisión de `/admin`: dónde administración ve las observaciones pendientes de todas las operaciones, cómo las da por resueltas con un comentario sin modificar la operación, y cómo se entera de lo pendiente, en particular de los excesos de crédito detectados al sincronizar (SYN-08, CRE-09).

## ADDED Requirements

### Requirement: Las observaciones se resuelven con un comentario y sin tocar la operación

El sistema DEBE ofrecer el comando `OBSERVACION_RESOLVER` v1, solo `ONLINE`, con el permiso `REVISAR_OBSERVACIONES`, que recibe de 1 a 100 observaciones distintas y un comentario de 1 a 500 caracteres. Todas DEBEN ser de la organización del token y estar `PENDIENTE`; si alguna no lo está, NO DEBE resolverse ninguna. Cada observación resuelta DEBE quedar `RESUELTA` con el usuario que resolvió, el momento del reloj del servidor y el comentario. Resolver NO DEBE modificar la operación observada, su comando ni ningún libro; las correcciones se hacen con operaciones nuevas (SYN-08, `design.md` D1).

#### Scenario: Resolver los avisos de una venta
- **GIVEN** una venta sin conexión de Juan a Kiosco La Esquina con dos observaciones `STOCK_NEGATIVO` pendientes
- **WHEN** la Supervisora las resuelve con el comentario «Se corrigió con un ajuste»
- **THEN** las dos quedan `RESUELTA`, con su usuario, el momento y el comentario
- **AND** la venta, sus líneas, el stock y la cuenta del cliente quedan como estaban
- **Regla:** SYN-08; `01` §18 (Observación)

#### Scenario: Resolución en bloque de varias operaciones
- **GIVEN** observaciones pendientes de una venta y de una cobranza
- **WHEN** se resuelven en un solo comando
- **THEN** todas quedan resueltas con el mismo comentario
- **Regla:** SYN-08; INV-01

#### Scenario: Una ya resuelta impide toda la resolución
- **GIVEN** tres observaciones, una de ellas ya `RESUELTA`
- **WHEN** se intenta resolver las tres
- **THEN** se rechaza con `OBSERVACION_YA_RESUELTA` (409) nombrando la resuelta
- **AND** las otras dos siguen `PENDIENTE`
- **Regla:** INV-01; `01` §18 (PENDIENTE → RESUELTA)

#### Scenario: Comentario vacío o demasiado largo
- **WHEN** se intenta resolver con un comentario vacío, solo de espacios o de más de 500 caracteres
- **THEN** se rechaza con `COMENTARIO_INVALIDO` (422) y nada cambia
- **Regla:** SYN-08 (se resuelve con un comentario)

#### Scenario: Lista vacía, repetida o de más de 100
- **WHEN** se envía una lista vacía, con una observación repetida o con 101
- **THEN** se rechaza con `OBSERVACIONES_INVALIDAS` (422) y nada cambia
- **Regla:** INV-01

#### Scenario: Observación de otra organización
- **GIVEN** una observación de la organización B
- **WHEN** un usuario de la organización A la incluye en una resolución
- **THEN** responde 404 y no se resuelve ninguna
- **Regla:** INV-21; INV-02

#### Scenario: Sin permiso
- **GIVEN** el Vendedor, que no tiene `REVISAR_OBSERVACIONES`
- **WHEN** intenta resolver una observación
- **THEN** responde 403 `PERMISO_REQUERIDO` y nada cambia
- **Regla:** SYN-08; `01` §19

#### Scenario: Doble envío de la resolución
- **GIVEN** una resolución ya aceptada
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** devuelve el resultado original sin volver a escribir ni auditar
- **Regla:** SYN-02; INV-06

#### Scenario: Dos personas resuelven a la vez
- **GIVEN** la misma observación pendiente
- **WHEN** dos usuarios la resuelven al mismo tiempo
- **THEN** una resolución se acepta y la otra se rechaza con `OBSERVACION_YA_RESUELTA`
- **Regla:** INV-01; `01` §18

### Requirement: La bandeja muestra las observaciones por operación

`GET /api/v1/observaciones` (con `REVISAR_OBSERVACIONES`) DEBE devolver, de la organización del token, una entrada por operación observada (venta, cobranza, compra, transferencia o ajuste), con el resumen de la operación, quién la registró, en qué dispositivo y jornada, cuándo ocurrió y cuándo llegó, y todas sus observaciones con código, detalle y estado (y la resolución de las resueltas). DEBE filtrar por estado (`PENDIENTE` por defecto, `RESUELTA` o todas), código, tipo de operación, usuario, jornada y rango de fechas de llegada, y paginar por cursor. Una operación aparece con estado `PENDIENTE` si tiene al menos una observación pendiente. Todos los códigos de SYN-07 DEBEN mostrarse con su detalle legible (`design.md` D3).

#### Scenario: Una venta con varios avisos es una sola entrada
- **GIVEN** una venta con `STOCK_NEGATIVO` en dos líneas y `DESCUENTO_DIFIERE`
- **WHEN** se lee la bandeja de pendientes
- **THEN** la venta aparece una vez, con sus tres observaciones
- **Regla:** SYN-07; SYN-08

#### Scenario: El detalle de los descuentos y del crédito
- **GIVEN** una venta con `DESCUENTO_DIFIERE` (causa `TOPE`), `AUTORIZACION_OFFLINE` y `EXCESO_CREDITO_DETECTADO_SYNC`
- **WHEN** se lee la bandeja
- **THEN** cada observación trae su detalle: las causas, el tipo de autorización con el autorizador y si conserva el permiso, y la evaluación del dispositivo frente a la del servidor
- **Regla:** DSC-09; CRE-09; ADR-055

#### Scenario: Los nombres de lo que el detalle nombra por id
- **GIVEN** una `AUTORIZACION_OFFLINE` con un autorizador, un `STOCK_NEGATIVO` de la línea 1 de un producto, una `UBICACION_TOMADA_AL_SINCRONIZAR` de la jornada de un vendedor y otra de una jornada que no existe
- **WHEN** se lee la bandeja
- **THEN** cada observación trae `nombres` con el autorizador, el producto y el número de línea, o el vendedor de la jornada («(no existe)» para la jornada inexistente), resueltos solo dentro de la organización y con una consulta por tipo de entidad
- **Regla:** SYN-07; INV-21

#### Scenario: Códigos de cobranza, de jornada y de consumidor final
- **GIVEN** una cobranza con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`, una venta con `CONSUMIDOR_FINAL_CON_DEUDA` y otra con `JORNADA_RENDIDA`
- **WHEN** se filtra por cada código
- **THEN** cada una aparece con el medio y el importe, el total y lo cobrado, o la jornada y el momento de la rendición
- **Regla:** SYN-07; ADR-052; ADR-054; ADR-068

#### Scenario: Filtro por jornada y por vendedor
- **GIVEN** observaciones de las jornadas de Juan y de otro vendedor
- **WHEN** se filtra por la jornada de Juan
- **THEN** solo aparecen las operaciones de esa jornada
- **Regla:** SYN-07

#### Scenario: Otra organización no aparece
- **GIVEN** observaciones pendientes de las organizaciones A y B
- **WHEN** un usuario de A lee la bandeja
- **THEN** solo ve las de A
- **Regla:** INV-21; INV-02

#### Scenario: Sin permiso no se lee la bandeja
- **WHEN** un usuario sin `REVISAR_OBSERVACIONES` pide la bandeja
- **THEN** responde 403
- **Regla:** `01` §19

### Requirement: Administración ve un aviso de lo pendiente

`GET /api/v1/observaciones/resumen` (con `REVISAR_OBSERVACIONES`) DEBE devolver la cantidad de observaciones pendientes por código, de rechazos pendientes y de cuarentenas pendientes. `/admin` DEBE mostrar, a quien tiene ese permiso, el total pendiente junto a «Revisión» en el menú y, en el inicio, la tarjeta «Para revisar» con la línea de los excesos de crédito detectados al sincronizar aparte; el aviso DEBE actualizarse solo, sin recargar la página. Es la notificación a administración de CRE-09 (`design.md` D5).

#### Scenario: Exceso detectado al sincronizar
- **GIVEN** una venta sin conexión que llega con `EXCESO_CREDITO_DETECTADO_SYNC`
- **WHEN** administración está en `/admin`
- **THEN** el contador sube y el inicio dice «1 exceso de crédito detectado al sincronizar», con acceso a la bandeja filtrada por ese código
- **Regla:** CRE-09

#### Scenario: Sin pendientes
- **GIVEN** que no hay nada pendiente
- **WHEN** se abre el inicio
- **THEN** el menú no muestra contador y la tarjeta dice «Sin avisos pendientes.»
- **Regla:** SYN-08

#### Scenario: Sin permiso no hay aviso
- **GIVEN** el usuario de Consulta, sin `REVISAR_OBSERVACIONES`
- **WHEN** abre `/admin`
- **THEN** no ve «Revisión» ni la tarjeta, y no se pide el resumen
- **Regla:** `01` §19; SEG-06

### Requirement: Resolver nunca altera la operación

Para toda secuencia de resoluciones, las ventas, cobranzas, compras, transferencias, ajustes, sus libros (`stock_movimiento`, `cuenta_movimiento`, `costo_producto_mov`) y los comandos observados DEBEN quedar exactamente como estaban; solo cambian las columnas de la resolución (SYN-08).

#### Scenario: Propiedad de no alteración
- **GIVEN** operaciones con observaciones generadas al azar
- **WHEN** se resuelven en cualquier orden y agrupación
- **THEN** una consulta SQL de las operaciones, de los libros y de los comandos da el mismo resultado antes y después
- **Regla:** SYN-08; INV-05; INV-12; INV-13
