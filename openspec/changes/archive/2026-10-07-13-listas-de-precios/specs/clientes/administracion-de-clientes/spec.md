## ADDED Requirements

### Requirement: El alta y la edición de la ficha se escriben con comandos idempotentes y ofrecen la lista asignada

El formulario de alta y el de edición de la ficha DEBE enviar un comando con un `operation_id` nuevo por envío, y DEBE reusar el mismo `operation_id` cuando reintenta un envío que falló, de modo que el reintento no duplique el cliente. La pantalla NO DEBE encolar escrituras sin conexión: si no hay conexión, DEBE indicarlo y no enviar, porque estos comandos solo admiten modo `ONLINE`. Los campos de dinero DEBE mostrarlos desde el string que devuelve la API, con dos decimales, sin convertirlos a número para calcular. El formulario DEBE ofrecer la lista de precios asignada con un selector de las listas activas de la organización y la opción de no asignar ninguna, que deja al cliente con la lista predeterminada (PRC-20, `design.md` D11 del change 13).

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

#### Scenario: La pantalla ofrece la lista asignada

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `GESTIONAR_LISTAS`, y las listas `General` y `Mayorista` activas y `Especial` inactiva
- **WHEN** abre el formulario de alta o de edición de la ficha
- **THEN** hay un selector de lista de precios con `General`, `Mayorista` y la opción de usar la lista predeterminada, sin `Especial`
- **Regla:** CLI-01; PRC-20; `design.md` D11 y D12 del change 13

#### Scenario: Guardar la ficha sin cambiar la lista no la pierde
- **GIVEN** un cliente con `Mayorista` asignada y su formulario de edición abierto
- **WHEN** corrige otro dato y guarda sin tocar el selector de lista
- **THEN** el formulario reenvía la lista asignada y el cliente conserva `Mayorista`; elegir la opción de la predeterminada la quita
- **Regla:** CLI-01; PRC-20; ADR-047 punto 27

#### Scenario: Lista inactiva informada por el servidor

- **GIVEN** un cliente en edición y una lista que se desactivó mientras el formulario estaba abierto
- **WHEN** se guarda con esa lista y el servidor responde `LISTA_INACTIVA`
- **THEN** la pantalla muestra el mensaje junto al selector y el cliente no cambia
- **Regla:** PRC-20; TR-10

#### Scenario: La pantalla no ofrece los campos de crédito en la ficha

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y `GESTIONAR_CREDITO`
- **WHEN** abre el formulario de alta o de edición de la ficha
- **THEN** no hay campos de límite, política ni tolerancia: el crédito se edita en su propia pantalla
- **Regla:** `01` §19; `design.md` D3

## REMOVED Requirements

### Requirement: El alta y la edición de la ficha se escriben con comandos idempotentes

**Reason**: Su escenario "La pantalla no ofrece la lista asignada" deja de valer: las listas de precios existen desde el change 13 y la ficha ofrece la lista asignada (PRC-20, CLI-01).

**Migration**: Lo reemplaza el requisito "El alta y la edición de la ficha se escriben con comandos idempotentes y ofrecen la lista asignada", que conserva sin cambios los escenarios de reintento, de falta de conexión y de campos de crédito, y sustituye el de la lista asignada por "La pantalla ofrece la lista asignada".
