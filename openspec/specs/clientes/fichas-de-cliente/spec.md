# Fichas de cliente — Especificación

## Purpose

Define el cliente como dato maestro de la organización, escrito solo por comandos del bus: ficha completa (CLI-01), estados `ACTIVO`, `SUSPENDIDO` e `INACTIVO` sin borrado (CLI-02, CLI-04) y consulta aislada por organización. El cliente no guarda saldo: su cuenta corriente llega con el change 08 (CC-04), y sus campos de crédito se rigen en `clientes/datos-de-credito`.

## Requirements

### Requirement: Un cliente se da de alta por comando

El sistema DEBE crear un cliente con el comando `CLIENTE_CREAR` (`ONLINE`, permiso `GESTIONAR_CLIENTES`), cuyo contenido lleva `nombre`, `direccion` y `contacto` obligatorios —los campos que CLI-01 no marca como opcionales— y, opcionales, razón social, tipo y número de documento, teléfono, email, código, lista asignada y estado de facturación inicial. El cliente nace `ACTIVO`; el estado se cambia después con `CLIENTE_MODIFICAR` (`design.md` D7, analogía con el proveedor que nace activo). El identificador lo genera el servidor (UUIDv7) y se devuelve en el resultado. El cliente NO DEBE tener ningún dato de saldo.

#### Scenario: Alta de un cliente

- **GIVEN** la organización A sin clientes
- **WHEN** un usuario con `GESTIONAR_CLIENTES` envía `CLIENTE_CREAR` con nombre `Kiosco La Esquina`, dirección `Av. San Martín 1420`, contacto `Rocío`, tipo y número de documento `DNI` `30111222` y teléfono
- **THEN** el comando queda `ACEPTADO`, el cliente existe `ACTIVO` en A con el número de documento guardado solo con dígitos (`30111222`), sus tres campos de crédito en nulo y se registra una sola fila de auditoría con el `operation_id`
- **Regla:** CLI-01; CLI-02; `03` §10 (`cliente`); AUD-01; CC-04

#### Scenario: Doble envío del alta no duplica el cliente

- **GIVEN** un `CLIENTE_CREAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y el cliente existe una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con contenido distinto

- **GIVEN** un `CLIENTE_CREAR` aceptado con `operation_id` X y nombre `Kiosco La Esquina`
- **WHEN** se reenvía con `operation_id` X y nombre `Kiosco El Faro`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y no se crea `Kiosco El Faro`
- **Regla:** SYN-02

#### Scenario: Sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin `GESTIONAR_CLIENTES` (rol Vendedor/Repartidor)
- **WHEN** envía `CLIENTE_CREAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, no se crea el cliente ni queda reserva del `operation_id`
- **Regla:** `01` §19 (`GESTIONAR_CLIENTES`); SEG

#### Scenario: Nombre vacío

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` con nombre vacío o solo espacios
- **THEN** se rechaza con `NOMBRE_INVALIDO` y no se crea ninguna fila
- **Regla:** TR-10

#### Scenario: Ficha sin un campo obligatorio

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` sin `direccion` o sin `contacto`
- **THEN** se rechaza con `FICHA_INCOMPLETA` y no se crea ninguna fila
- **Regla:** CLI-01

#### Scenario: La ficha no escribe los campos de crédito

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` o `CLIENTE_MODIFICAR` cuyo contenido incluya `limite_credito`, `politica_credito`, `tolerancia_offline_tipo` o `tolerancia_offline_valor`
- **THEN** se rechaza como malformado y el cliente no cambia
- **Regla:** `01` §19 (`GESTIONAR_CREDITO`); `design.md` D3

### Requirement: Código y documento identifican al cliente sin repetirlo en la organización

El `codigo` es opcional y, cuando existe, DEBE ser único entre los clientes de la organización tras descartar espacios al inicio y al final. El tipo y el número de documento son opcionales como pareja: si se informa uno DEBE informarse el otro, el número DEBE quedar solo con dígitos (se descartan guiones y espacios) y la pareja DEBE ser única en la organización. El `nombre` NO DEBE ser único: el mismo nombre puede repetir en la organización. La base de datos DEBE garantizar las unicidades aun ante altas concurrentes. Las longitudes se validan por tipo según CLI-05: el CUIT DEBE tener 11 dígitos y el DNI entre 7 y 8, siempre solo numéricos, y un tipo fuera del catálogo (CUIT, DNI) se rechaza (`design.md` D1, decidido el 2026-09-28).

#### Scenario: Código repetido

- **GIVEN** el cliente de código `K-001` existe en A
- **WHEN** se envía `CLIENTE_CREAR` o `CLIENTE_MODIFICAR` que deja otro cliente con código `K-001` en A
- **THEN** se rechaza con `CODIGO_DUPLICADO` y no cambia ninguna fila
- **Regla:** `design.md` D1

#### Scenario: Documento repetido

- **GIVEN** el cliente con documento `DNI` `30111222` existe en A
- **WHEN** se envía otro cliente con documento `DNI` `30-111.222`, o con `DNI` `30111223` como número distinto
- **THEN** el primero se rechaza con `DOCUMENTO_DUPLICADO` porque coincide tras normalizar, y el segundo se acepta
- **Regla:** `design.md` D1

#### Scenario: Documento a medias o con letras

- **GIVEN** la organización A
- **WHEN** se informa `documento_tipo` sin `documento_numero`, o un número con letras
- **THEN** se rechaza con `DOCUMENTO_INCOMPLETO` y no se crea ninguna fila
- **Regla:** CLI-01; `design.md` D1

#### Scenario: Longitud inválida según el tipo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` con documento `CUIT` `30111222` (no tiene 11 dígitos), o con `DNI` `123456` (no tiene 7 u 8 dígitos)
- **THEN** se rechaza con `DOCUMENTO_INVALIDO` y no se crea ninguna fila
- **Regla:** CLI-05; `design.md` D1

#### Scenario: Cliente sin código ni documento

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` sin `codigo` y sin documento
- **THEN** el comando queda `ACEPTADO` y el cliente se identifica por su identificador
- **Regla:** CLI-01 (ambos opcionales)

#### Scenario: El mismo nombre en otra organización es válido

- **GIVEN** el cliente `Kiosco La Esquina` existe en B
- **WHEN** un usuario de A envía `CLIENTE_CREAR` con nombre `Kiosco La Esquina`
- **THEN** el comando queda `ACEPTADO`
- **Regla:** TR-08; INV-02

#### Scenario: Dos altas concurrentes con el mismo documento

- **GIVEN** la organización A sin clientes
- **WHEN** dos transacciones con commits reales envían `CLIENTE_CREAR` con documento `DNI` `30111222` a la vez con `operation_id` distintos
- **THEN** exactamente una queda `ACEPTADA` y la otra se rechaza con `DOCUMENTO_DUPLICADO`
- **Regla:** `design.md` D1; INV-01

### Requirement: El estado del cliente sigue la máquina de estados de `01` §18

El sistema DEBE validar cada cambio de estado contra la máquina de `01` §18: `ACTIVO ↔ SUSPENDIDO`, `ACTIVO → INACTIVO` y `SUSPENDIDO → INACTIVO` y, desde `INACTIVO`, la única salida es `INACTIVO → ACTIVO` y solo si el cliente no tiene operaciones (CLI-06, ADR-030); con operaciones es terminal. Un cliente NO DEBE borrarse en ningún caso (CLI-04, INV-05). A partir del change 08, un cliente tiene operaciones si su cuenta corriente tiene al menos un movimiento de cualquier tipo, incluido `SALDO_INICIAL` (`design.md` D8 del change 08, aprobada 2026-09-29); `clientes` lo consulta a `cuentas_corrientes/service.py` dentro de la misma transacción, después de bloquear la fila del cliente, y la reactivación de un cliente con movimientos se rechaza con `CLIENTE_CON_OPERACIONES`. Ventas y cobranzas (changes 17 y 18a) quedan cubiertas por la misma consulta porque también escriben en el libro.

#### Scenario: Suspender y reactivar

- **GIVEN** el cliente `Kiosco La Esquina` `ACTIVO` en A
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = SUSPENDIDO` y luego con `estado = ACTIVO`
- **THEN** el cliente queda suspendido y luego activo, con `actualizado_en` nuevo en cada cambio
- **Regla:** CLI-02; `01` §18

#### Scenario: Inactivar un cliente

- **GIVEN** el cliente `Kiosco La Esquina` `SUSPENDIDO` en A
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = INACTIVO`
- **THEN** el cliente queda `INACTIVO`, sigue existiendo y aparece en el listado con ese estado
- **Regla:** CLI-02; CLI-04

#### Scenario: Reactivar un cliente sin operaciones

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` en A, sin movimientos en su cuenta corriente
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = ACTIVO`
- **THEN** el cliente vuelve a `ACTIVO` y sigue existiendo
- **Regla:** CLI-06; `01` §18; ADR-030

#### Scenario: Reactivar un cliente con movimientos se rechaza

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` en A, con un saldo inicial de `"150000.00"` en su cuenta corriente
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = ACTIVO`
- **THEN** se rechaza con `CLIENTE_CON_OPERACIONES` y el cliente sigue `INACTIVO`
- **Regla:** CLI-06; ADR-030; `design.md` D8 del change 08

#### Scenario: Reactivación y saldo inicial concurrentes

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` sin movimientos, y dos transacciones que confirman sus commits: una reactivación y un saldo inicial
- **WHEN** se ejecutan a la vez
- **THEN** nunca termina el cliente `ACTIVO` con un movimiento que la reactivación no vio: o se aplica la reactivación antes del saldo inicial, o la reactivación se rechaza con `CLIENTE_CON_OPERACIONES`
- **Regla:** CLI-06; ADR-030; `design.md` D6 y D8 del change 08

#### Scenario: Estado fuera del catálogo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_MODIFICAR` con un estado que no es `ACTIVO`, `SUSPENDIDO` ni `INACTIVO`
- **THEN** se rechaza con `ESTADO_INVALIDO` y no cambia ninguna fila
- **Regla:** `01` §18; `03` §10

#### Scenario: Cliente de otra organización

- **GIVEN** un cliente de B
- **WHEN** un usuario de A envía `CLIENTE_MODIFICAR` sobre él
- **THEN** la respuesta es 404 y el cliente de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe borrado de clientes

- **GIVEN** la API y los permisos de base del usuario de aplicación
- **WHEN** se busca cualquier operación que elimine un cliente
- **THEN** no existe, y el usuario de aplicación no tiene `DELETE` sobre `cliente`
- **Regla:** CLI-04; TR-06; INV-05

### Requirement: Los clientes se consultan por organización

El sistema DEBE listar los clientes de la organización con paginación por cursor y límite máximo por página, filtrables por texto (nombre, razón social, código o número de documento) y por estado, y DEBE devolver el detalle de un cliente. La respuesta DEBE incluir los tres campos de crédito del cliente aunque quien consulta no pueda modificarlos (`design.md` D3). El listado y el detalle exigen `GESTIONAR_CLIENTES` y NUNCA devuelven datos de otra organización.

#### Scenario: Listado paginado por cursor

- **GIVEN** más clientes en A que el tamaño de página pedido
- **WHEN** se piden páginas sucesivas con el cursor devuelto
- **THEN** cada cliente aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11

#### Scenario: Filtro por texto y por estado

- **GIVEN** en A el cliente `Kiosco La Esquina` `ACTIVO` y `Kiosco El Faro` `SUSPENDIDO`
- **WHEN** se lista filtrando por texto `Esquina` y luego por `estado = SUSPENDIDO`
- **THEN** el primer resultado trae solo `Kiosco La Esquina` y el segundo solo `Kiosco El Faro`, cada uno con su estado
- **Regla:** `01` §18; `02` §11

#### Scenario: Listado aislado por organización

- **GIVEN** clientes en A y en B
- **WHEN** un usuario de A lista clientes
- **THEN** no aparece ningún cliente de B
- **Regla:** INV-21

#### Scenario: El detalle expone el crédito sin permiso de crédito

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `GESTIONAR_CREDITO`
- **WHEN** pide el detalle de un cliente con límite `"150000.00"` y política `AUTORIZAR`
- **THEN** la respuesta es 200 y trae `limite_credito: "150000.00"` y `politica_credito: "AUTORIZAR"`
- **Regla:** `01` §19; `design.md` D3; INV-03

#### Scenario: El listado exige permiso de clientes

- **GIVEN** un usuario sin `GESTIONAR_CLIENTES`
- **WHEN** pide el listado o el detalle de un cliente
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19 (`GESTIONAR_CLIENTES`)

#### Scenario: Detalle de un cliente ajeno

- **GIVEN** un cliente de B
- **WHEN** un usuario de A pide su detalle
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

### Requirement: El estado de facturación inicial pertenece al catálogo cerrado

El alta y la modificación de un cliente DEBEN aceptar como `estado_facturacion_default` solo `NO_REQUIERE`, `PENDIENTE` o el valor nulo (el de la organización, VTA-08). Cualquier otro valor DEBE rechazarse con `ESTADO_FACTURACION_INVALIDO` (422), sin escribir nada y nunca con un error interno. La regla vive en el dominio de clientes: la importación de clientes (change 10) la hereda sin repetirla (TR-10). Agregado por el change 10 (grupo 12) para cerrar una laguna del alta por pantalla, donde el valor inválido llegaba a la base y terminaba en 500.

#### Scenario: Estado de facturación fuera del catálogo

- **GIVEN** la organización A
- **WHEN** un usuario con `GESTIONAR_CLIENTES` envía `CLIENTE_CREAR` con `estado_facturacion_default` = `FACTURADA`
- **THEN** responde 422 con `ESTADO_FACTURACION_INVALIDO` y no se crea ningún cliente
- **Regla:** VTA-08; `03` §10 (`cliente`)

#### Scenario: Estado válido o nulo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` con `PENDIENTE` y otro con el valor nulo
- **THEN** ambos clientes se crean y conservan el valor recibido
- **Regla:** VTA-08
