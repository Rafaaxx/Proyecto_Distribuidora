## Purpose

Definir el cliente genérico "consumidor final" que la organización puede habilitar, con límite de crédito cero (CLI-03), y la habilitación misma como operación de configuración de la organización. La venta al consumidor final y su resolución de precio son del change 18a (VTA-08, PRC-20).

## ADDED Requirements

### Requirement: El consumidor final es un cliente con límite de crédito cero

Si la organización lo habilita, DEBE existir un cliente genérico "consumidor final" con `limite_credito` cero, y ese cliente DEBE llevar una marca que lo distinga de los clientes comunes. Su límite NO DEBE poder fijarse en otro valor, y su crédito NO DEBE admitir política ni tolerancia propias: es solo contado (CLI-03; CRE-01, "límite cero significa solo contado"). El consumidor final es un cliente más y su estado lo gobierna la misma máquina de estados (CLI-02). El sistema NO DEBE crear el cliente por bootstrap ni por sincronización: lo crea el único comando de habilitación.

#### Scenario: El consumidor final habilitado tiene límite cero

- **GIVEN** la organización A con el consumidor final habilitado
- **WHEN** se pide el detalle del cliente apuntado por `cliente_consumidor_final_id`
- **THEN** trae la marca de consumidor final y `limite_credito: "0.00"`
- **Regla:** CLI-03; CRE-01

#### Scenario: No se puede cambiar el límite del consumidor final

- **GIVEN** la organización A con el consumidor final habilitado
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` sobre ese cliente con `limite_credito = "50000.00"`
- **THEN** se rechaza con `CONSUMIDOR_FINAL_SIN_CREDITO` y el límite sigue siendo `"0.00"`
- **Regla:** CLI-03; CRE-01

#### Scenario: El consumidor final admite la misma máquina de estados

- **GIVEN** la organización A con el consumidor final habilitado y `ACTIVO`
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = SUSPENDIDO` y luego con `estado = ACTIVO`
- **THEN** el cliente queda suspendido y luego activo, sin dejar de ser el consumidor final
- **Regla:** CLI-02; CLI-03

#### Scenario: La marca de consumidor final no se asigna a un cliente común

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` cuyo contenido intenta marcar el cliente como consumidor final
- **THEN** se rechaza como malformado: solo el comando de habilitación puede crearlo
- **Regla:** CLI-03; `design.md` D4

### Requirement: La organización habilita el consumidor final con un comando

El sistema DEBE habilitar el consumidor final con el comando `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (`ONLINE`, permiso `ADMIN_CONFIGURACION` porque escribe la configuración de la organización, `01` §4), que crea el cliente, le asigna el límite cero y fija `permite_consumidor_final` y `cliente_consumidor_final_id` en la misma transacción. El comando NO DEBE admitir un cliente ya existente, ni cambiar un consumidor final ya habilitado, ni admitir campos de ficha o de crédito. Con las plantillas de rol vigentes, solo el rol Administrador puede habilitarlo, porque es el único que tiene `ADMIN_CONFIGURACION` (`design.md` D4).

#### Scenario: Habilitar el consumidor final

- **GIVEN** la organización A sin consumidor final habilitado
- **WHEN** un usuario con `ADMIN_CONFIGURACION` envía `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` con el nombre `Consumidor final`
- **THEN** el comando queda `ACEPTADO`, existe un cliente activo marcado como consumidor final con límite `"0.00"` y la configuración de A tiene `permite_consumidor_final` en `true` apuntando a ese cliente
- **Regla:** CLI-03; `01` §4; `03` §4; INV-01

#### Scenario: Doble envío de la habilitación

- **GIVEN** un `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y no se crea un segundo cliente ni se reescribe la configuración
- **Regla:** INV-06; SYN-02

#### Scenario: Habilitar cuando ya está habilitado

- **GIVEN** la organización A con el consumidor final habilitado
- **WHEN** se envía `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` con `operation_id` distinto
- **THEN** se rechaza con `CONSUMIDOR_FINAL_YA_HABILITADO` y no se crea ningún cliente
- **Regla:** CLI-03; `design.md` D4

#### Scenario: Sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin `ADMIN_CONFIGURACION` (rol Administración)
- **WHEN** envía `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, no se crea el cliente ni cambia la configuración
- **Regla:** `01` §19 (`ADMIN_CONFIGURACION`); SEG

#### Scenario: La configuración de otra organización no se toca

- **GIVEN** las organizaciones A y B, con B que ya tiene su consumidor final habilitado
- **WHEN** un usuario de A envía `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`
- **THEN** la configuración de B no cambia y el cliente de B sigue siendo el suyo
- **Regla:** INV-02; INV-21

#### Scenario: Nombre vacío o campos de ficha en el contenido

- **GIVEN** la organización A sin consumidor final habilitado
- **WHEN** se envía `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` con nombre vacío, o con `limite_credito`, o con un `cliente_id` al que asociarlo
- **THEN** se rechaza con `NOMBRE_INVALIDO` o como malformado, y no se crea ningún cliente
- **Regla:** CLI-03; `design.md` D4

### Requirement: La organización consulta su consumidor final habilitado

El sistema DEBE permitir consultar si la organización tiene consumidor final habilitado y cuál es (`GET /api/v1/clientes/consumidor-final`), con el permiso `GESTIONAR_CLIENTES`, y DEBE devolver únicamente los datos de la organización que consulta. El consumo de ese dato por el área `/ruta` llega con el bootstrap del change 21 (SYN-11).

#### Scenario: Organización sin consumidor final

- **GIVEN** la organización A sin consumidor final habilitado
- **WHEN** un usuario con `GESTIONAR_CLIENTES` consulta el consumidor final
- **THEN** la respuesta es 200 con `habilitado: false` y sin identificador de cliente
- **Regla:** CLI-03

#### Scenario: Organización con consumidor final

- **GIVEN** la organización A con el consumidor final habilitado
- **WHEN** un usuario con `GESTIONAR_CLIENTES` consulta el consumidor final
- **THEN** la respuesta es 200 con `habilitado: true` y el identificador y nombre del cliente final de A
- **Regla:** CLI-03; `03` §4

#### Scenario: Consulta aislada por organización

- **GIVEN** las organizaciones A y B, con B con consumidor final habilitado
- **WHEN** un usuario de A consulta el consumidor final
- **THEN** no recibe ningún dato del cliente ni de la configuración de B
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso de clientes

- **GIVEN** un usuario sin `GESTIONAR_CLIENTES`
- **WHEN** consulta el consumidor final
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19 (`GESTIONAR_CLIENTES`)
