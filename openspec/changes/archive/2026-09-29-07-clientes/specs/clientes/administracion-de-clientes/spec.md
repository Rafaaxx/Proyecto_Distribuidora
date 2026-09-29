## Purpose

Definir las pantallas de `/admin/clientes`: el menú, el listado, la ficha y la pantalla de crédito, todas decididas por los permisos efectivos de la sesión (`GET /api/v1/yo`, ADR-027) y no por una reacción a un 403, que el change 06b retiró. Las escrituras de estas pantallas son `ONLINE`: el área `/ruta` es la que encola comandos sin conexión (ADR-012, SYN-05).

## ADDED Requirements

### Requirement: La sección de clientes se decide con el permiso de la sesión

El sistema DEBE mostrar la sección de clientes en el menú del área de administración solo cuando el usuario tiene `GESTIONAR_CLIENTES` en sus permisos efectivos, y NO DEBE deducirla de un 403. Un usuario sin ese permiso NO DEBE ver la sección, y la API DEBE responder 403 `PERMISO_REQUERIDO` a cualquier ruta de clientes. Un usuario con `GESTIONAR_CREDITO` pero sin `GESTIONAR_CLIENTES` tampoco ve la sección.

#### Scenario: Usuario con permiso de clientes

- **GIVEN** un usuario de la organización A con `GESTIONAR_CLIENTES` (rol Supervisor comercial)
- **WHEN** entra a la sección de administración
- **THEN** ve la entrada de clientes en el menú y la pantalla de listado carga
- **Regla:** ADR-027; `01` §19 (`GESTIONAR_CLIENTES`)

#### Scenario: Usuario sin permiso de clientes

- **GIVEN** un usuario de la organización A sin `GESTIONAR_CLIENTES`
- **WHEN** entra a la sección de administración
- **THEN** no ve la entrada de clientes, y si pide la ruta de clientes la respuesta es 403
- **Regla:** ADR-027; ADR-028

#### Scenario: Permiso de crédito sin permiso de clientes

- **GIVEN** un usuario de la organización A con `GESTIONAR_CREDITO` y sin `GESTIONAR_CLIENTES`
- **WHEN** entra a la sección de administración
- **THEN** no ve la entrada de clientes
- **Regla:** ADR-028; `01` §19

### Requirement: El listado de clientes muestra el estado y filtra

La pantalla de clientes DEBE listar los clientes de la organización con el nombre, el estado (`ACTIVO`, `SUSPENDIDO` o `INACTIVO`) visible, la marca de consumidor final cuando corresponda, y DEBE permitir filtrar por texto y por estado y paginar con el cursor que devuelve la API. La ficha DEBE mostrar el detalle del cliente, y sus tres campos de crédito en solo lectura para quien no tiene `GESTIONAR_CREDITO`.

#### Scenario: Buscar un cliente por texto

- **GIVEN** en A el cliente `Kiosco La Esquina` `ACTIVO` y `Kiosco El Faro` `SUSPENDIDO`
- **WHEN** el usuario busca `Esquina`
- **THEN** el listado muestra `Kiosco La Esquina` con su estado `ACTIVO` y no muestra `Kiosco El Faro`
- **Regla:** `01` §18; `02` §11

#### Scenario: Filtrar por estado suspendido

- **GIVEN** los mismos dos clientes
- **WHEN** el usuario filtra por `SUSPENDIDO`
- **THEN** el listado muestra solo `Kiosco El Faro`
- **Regla:** CLI-02; `01` §18

#### Scenario: La ficha muestra el crédito en solo lectura

- **GIVEN** un usuario sin `GESTIONAR_CREDITO` y el cliente `Kiosco La Esquina` con límite `"150000.00"`
- **WHEN** abre la ficha del cliente
- **THEN** ve el límite `"150000.00"` y la política, sin botón de edición ni campos habilitados
- **Regla:** `01` §19; ADR-028; `design.md` D3

### Requirement: La edición del crédito es una pantalla propia

El sistema DEBE ofrecer la modificación del crédito en una pantalla separada de la ficha, a la que solo se llega con un botón visible cuando el usuario tiene `GESTIONAR_CREDITO`, y DEBE ocultarla por completo a quien no lo tiene. El formulario DEBE mostrar los tres campos con el valor vigente, distinguiendo el nulo de la herencia de la organización, y DEBE enviar el cambio por el comando de crédito.

#### Scenario: Usuario con permiso de crédito

- **GIVEN** un usuario con `GESTIONAR_CREDITO` (rol Administración)
- **WHEN** abre la ficha de `Kiosco La Esquina`
- **THEN** ve el botón de crédito, y al abrirlo puede fijar límite, política y tolerancia
- **Regla:** `01` §19 (`GESTIONAR_CREDITO`); ADR-028

#### Scenario: Usuario sin permiso de crédito

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `GESTIONAR_CREDITO`
- **WHEN** abre la ficha de `Kiosco La Esquina`
- **THEN** no ve el botón de crédito, y si llega a la ruta de la pantalla de crédito no encuentra la sección y la escritura responde 403
- **Regla:** ADR-028; `01` §19

#### Scenario: Guardar el crédito y ver el resultado

- **GIVEN** un usuario con `GESTIONAR_CREDITO` en la pantalla de crédito de `Kiosco La Esquina`
- **WHEN** fija el límite en `150000.00` y guarda
- **THEN** la pantalla confirma el guardado y la ficha muestra el límite `"150000.00"` con dos decimales
- **Regla:** INV-03; `lib/money.ts`; `design.md` D6

#### Scenario: El formulario de crédito rechaza un valor inválido

- **GIVEN** el usuario en la pantalla de crédito
- **WHEN** envía un límite negativo o una política fuera del catálogo
- **THEN** la pantalla muestra el mensaje del dominio y no confirma el cambio
- **Regla:** INV-03; CRE-03

### Requirement: El alta y la edición de la ficha se escriben con comandos idempotentes

El formulario de alta y el de edición de la ficha DEBE enviar un comando con un `operation_id` nuevo por envío, y DEBE reusar el mismo `operation_id` cuando reintenta un envío que falló, de modo que el reintento no duplique el cliente. La pantalla NO DEBE encolar escrituras sin conexión: si no hay conexión, DEBE indicarlo y no enviar, porque estos comandos solo admiten modo `ONLINE`. Los campos de dinero DEBE mostrarlos desde el string que devuelve la API, con dos decimales, sin convertirlos a número para calcular.

#### Scenario: Reintento del alta tras un fallo transitorio

- **GIVEN** un usuario en el formulario de alta de `Kiosco La Esquina` cuyo primer envío falló con un error transitorio de la base
- **WHEN** reintenta el envío
- **THEN** se reenvía con el mismo `operation_id` y el cliente existe una sola vez
- **Regla:** INV-06; SYN-02; `02` §6.4

#### Scenario: Sin conexión la pantalla no escribe

- **GIVEN** un usuario en el formulario de alta sin conexión
- **WHEN** intenta guardar
- **THEN** la pantalla indica que se necesita conexión, no envía el comando y no encola nada
- **Regla:** ADR-012; `02` §6.2; `02` §6.5

#### Scenario: La pantalla no ofrece la lista asignada

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` en el formulario de alta
- **WHEN** abre el formulario
- **THEN** no hay selector de lista de precios, porque las listas llegan con el change 13 (PRC-20)
- **Regla:** PRC-20; `design.md` D2

#### Scenario: La pantalla no ofrece los campos de crédito en la ficha

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y `GESTIONAR_CREDITO`
- **WHEN** abre el formulario de alta o de edición de la ficha
- **THEN** no hay campos de límite, política ni tolerancia: el crédito se edita en su propia pantalla
- **Regla:** `01` §19; `design.md` D3

### Requirement: Inactivar un cliente exige confirmación tipeada en la pantalla

La pantalla NO DEBE enviar `CLIENTE_MODIFICAR` con `estado = INACTIVO` hasta que el usuario tipee el **nombre completo del cliente** en el diálogo de confirmación; el envío queda bloqueado si el texto no coincide exactamente con el nombre vigente. El diálogo DEBE mostrar el estado actual, el código y el documento para distinguir clientes de igual nombre, y DEBE explicar la consecuencia (no se le podrá vender; si ya tiene operaciones, no habrá vuelta atrás). La confirmación es de interfaz y solo frontend: el comando que se envía es el mismo `CLIENTE_MODIFICAR`, no lleva el texto confirmado, y el backend rechaza por su cuenta la transición si el estado no corresponde.

#### Scenario: Inactivar sin confirmar el nombre no envía nada

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` en la ficha de `Kiosco La Esquina`
- **WHEN** selecciona `estado = INACTIVO` sin tipear el nombre completo
- **THEN** el botón de guardar queda deshabilitado y no se envía ningún comando
- **Regla:** `design.md` D7; CLI-04

#### Scenario: Inactivar confirmando el nombre envía el comando

- **GIVEN** el mismo usuario en la ficha de `Kiosco La Esquina`
- **WHEN** tipea `Kiosco La Esquina` en el diálogo y confirma
- **THEN** se envía `CLIENTE_MODIFICAR` con `estado = INACTIVO` y el listado muestra el cliente `INACTIVO`
- **Regla:** `design.md` D7; CLI-02
