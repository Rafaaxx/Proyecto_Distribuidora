# clientes/cartera-de-clientes Specification

## Purpose
Asignación de clientes a vendedores ("sus clientes", `01` §19) y su efecto en las lecturas de clientes para vender y cobrar, sin rechazar operaciones por la cartera.

## Requirements

### Requirement: Un cliente tiene a lo sumo un vendedor asignado

Cada cliente de la organización DEBE tener cero o un vendedor asignado, que es un usuario de la misma organización. El consumidor final NO DEBE tener vendedor (`design.md` D13).

#### Scenario: Cliente sin vendedor
- **WHEN** se da de alta un cliente
- **THEN** nace sin vendedor asignado
- **Regla:** `01` §19

#### Scenario: Vendedor de otra organización
- **WHEN** se intenta asignar a un cliente de A un usuario de B
- **THEN** se responde como usuario inexistente y el cliente no cambia
- **Regla:** INV-21; INV-02

### Requirement: La cartera se asigna por comando

`CLIENTE_VENDEDOR_ASIGNAR` v1 DEBE asignar un vendedor (o quitarlo con `null`) a uno o varios clientes de la organización (hasta 500), con `GESTIONAR_CLIENTES`, solo con conexión, todo o nada. El vendedor DEBE estar `ACTIVO`, con rol activo y con `VENDER` o `REGISTRAR_COBRANZA`. Cada cliente cambiado DEBE dejar una fila de auditoría con el vendedor anterior y el nuevo (`design.md` D15).

#### Scenario: Asignar varios clientes
- **GIVEN** tres clientes sin vendedor y el vendedor Juan
- **WHEN** un usuario con `GESTIONAR_CLIENTES` se los asigna a Juan
- **THEN** los tres quedan con Juan y hay una fila de auditoría por cliente
- **Regla:** `01` §19; AUD-01

#### Scenario: Un cliente inexistente en el pedido
- **WHEN** la lista incluye un cliente inexistente o de otra organización
- **THEN** la respuesta es 404 y ningún cliente cambia
- **Regla:** INV-01; INV-21

#### Scenario: Vendedor inválido
- **WHEN** se asigna un usuario `INACTIVO` o sin `VENDER` ni `REGISTRAR_COBRANZA`
- **THEN** la respuesta es 409 `VENDEDOR_INVALIDO` y ningún cliente cambia
- **Regla:** INV-01

#### Scenario: Consumidor final
- **WHEN** la lista incluye al consumidor final
- **THEN** la respuesta es 409 `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR` y ningún cliente cambia
- **Regla:** CLI-03

#### Scenario: Sin permiso
- **WHEN** un usuario sin `GESTIONAR_CLIENTES` envía la asignación por REST o en un lote
- **THEN** recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** SEG-06; ADR-056

#### Scenario: Doble envío
- **GIVEN** una asignación ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin filas de auditoría nuevas
- **Regla:** INV-06

### Requirement: Las lecturas para vender y cobrar ofrecen primero la cartera

Para quien llega a los clientes solo por `VENDER` o `REGISTRAR_COBRANZA`, sin `GESTIONAR_CLIENTES`, la lista de clientes para elegir DEBE traer sus clientes asignados y el consumidor final; DEBE poder pedir todos los clientes de la organización; y si no tiene ningún cliente asignado DEBE traer todos. Quien tiene `GESTIONAR_CLIENTES` DEBE ver todos. La cartera NO DEBE rechazar ni marcar una venta o una cobranza, con o sin conexión (`design.md` D14).

#### Scenario: Vendedor con cartera
- **GIVEN** el vendedor Juan con dos clientes asignados en una organización de diez
- **WHEN** abre la lista de clientes para vender
- **THEN** ve sus dos clientes y el consumidor final
- **Regla:** `01` §19

#### Scenario: Buscar en todos
- **GIVEN** Juan con cartera
- **WHEN** pide la lista con alcance a todos
- **THEN** ve los diez clientes
- **Regla:** `01` §19; ADR-052

#### Scenario: Vendedor sin cartera
- **GIVEN** el vendedor Pedro sin clientes asignados
- **WHEN** abre la lista de clientes para vender
- **THEN** ve todos los clientes de la organización
- **Regla:** ADR-052

#### Scenario: Venta a un cliente fuera de la cartera
- **GIVEN** Juan con cartera
- **WHEN** confirma con conexión una venta a un cliente asignado a otro vendedor
- **THEN** la venta se acepta sin observación por la cartera
- **Regla:** `design.md` D14; SYN-05; INV-17

#### Scenario: Administración ve todos
- **GIVEN** un usuario con `GESTIONAR_CLIENTES`
- **WHEN** abre el listado de clientes
- **THEN** ve todos, con el vendedor de cada uno y un filtro por vendedor que incluye "sin vendedor"
- **Regla:** `01` §19

### Requirement: La cartera se administra desde los clientes

El listado de clientes DEBE mostrar el vendedor y filtrar por vendedor, y permitir elegir varios clientes y asignarles un vendedor; la ficha DEBE mostrar y cambiar el vendedor. Los clientes de un vendedor dado de baja o sin permiso DEBEN marcarse para reasignarlos.

#### Scenario: Reasignar la cartera de un vendedor dado de baja
- **GIVEN** el vendedor Juan dado de baja con clientes asignados
- **WHEN** se filtra el listado por Juan
- **THEN** sus clientes aparecen marcados y se pueden asignar en bloque a otro vendedor
- **Regla:** `design.md` D6, D15

#### Scenario: Elegir vendedor sin administrar usuarios
- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `ADMIN_USUARIOS`
- **WHEN** pide `GET /clientes/vendedores`
- **THEN** recibe solo `id` y `nombre` de los usuarios activos, de rol activo y con `VENDER` o `REGISTRAR_COBRANZA` de su organización; sin `GESTIONAR_CLIENTES` responde 403
- **Regla:** `design.md` D15
