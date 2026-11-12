## ADDED Requirements

### Requirement: La lista asignada del cliente es una lista activa de la organización

`CLIENTE_CREAR` y `CLIENTE_MODIFICAR` DEBEN aceptar la lista de precios asignada al cliente (CLI-01), opcional: sin lista, el cliente compra con la lista predeterminada de la organización (PRC-20). Una lista que no existe en la organización del token DEBE responder 404, sin revelar si existe en otra; una lista inactiva DEBE rechazarse con `LISTA_INACTIVA`. La base de datos DEBE impedir que un cliente referencie una lista de otra organización o inexistente (`design.md` D11 del change 13; salda la deuda de `design.md` D2 del change 07). La consulta de un cliente DEBE devolver su lista asignada.

#### Scenario: Asignar una lista al cliente
- **GIVEN** el cliente `Kiosco El Faro` sin lista y la lista activa `Mayorista`
- **WHEN** un usuario con `GESTIONAR_CLIENTES` envía `CLIENTE_MODIFICAR` con la lista `Mayorista`
- **THEN** el comando queda `ACEPTADO`, el cliente tiene `Mayorista` asignada y su consulta la devuelve
- **Regla:** CLI-01; PRC-20

#### Scenario: Quitar la lista asignada
- **GIVEN** `Kiosco El Faro` con `Mayorista` asignada
- **WHEN** se envía `CLIENTE_MODIFICAR` con la lista en nulo
- **THEN** el cliente queda sin lista asignada
- **Regla:** CLI-01; PRC-20

#### Scenario: Modificar sin mandar la lista conserva la asignada
- **GIVEN** `Kiosco El Faro` con `Mayorista` asignada
- **WHEN** se envía `CLIENTE_MODIFICAR` (o `PUT /clientes/{id}`) sin el campo `lista_precio_id`, por ejemplo para corregir el nombre
- **THEN** el cliente conserva `Mayorista`; solo un nulo explícito la quita y un identificador la reemplaza. Si el cliente queda activo, la lista conservada se revalida como cualquier lista elegida
- **Regla:** CLI-01; PRC-20; `design.md` D11; ADR-047 punto 27

#### Scenario: Lista inactiva
- **GIVEN** la lista `Especial` inactiva
- **WHEN** se envía `CLIENTE_CREAR` o `CLIENTE_MODIFICAR` con `Especial`
- **THEN** se rechaza con `LISTA_INACTIVA` y el cliente no cambia
- **Regla:** PRC-20; `design.md` D11

#### Scenario: Lista de otra organización
- **WHEN** un usuario de A envía `CLIENTE_MODIFICAR` con una lista de B
- **THEN** la respuesta es 404 y el cliente no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: La base rechaza una lista inexistente escrita por fuera del servicio
- **WHEN** se intenta escribir directamente en un cliente un identificador de lista que no existe en su organización
- **THEN** la base rechaza la escritura por la clave foránea compuesta
- **Regla:** INV-02; `03` §2.4; `03` §10 (`lista_precio_id`)

#### Scenario: Doble envío con lista asignada
- **GIVEN** un `CLIENTE_MODIFICAR` aceptado con `operation_id` X que asigna `Mayorista`
- **WHEN** se reenvía con X y el mismo contenido
- **THEN** se devuelve el resultado original sin efectos nuevos
- **Regla:** INV-06; SYN-02
