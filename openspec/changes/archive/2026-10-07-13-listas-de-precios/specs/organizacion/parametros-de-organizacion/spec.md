## ADDED Requirements

### Requirement: La lista de precios predeterminada se define por comando

La lista de precios por defecto de la organización (`01` §4) DEBE definirse con el comando `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (solo `ONLINE`, con `Operation-Id`, permiso `ADMIN_CONFIGURACION`), que solo admite una lista activa de la organización del token: una lista inactiva DEBE rechazarse con `LISTA_INACTIVA` y una inexistente o de otra organización DEBE responder 404. La base de datos DEBE impedir que la configuración referencie una lista de otra organización o inexistente. El cambio DEBE quedar auditado con el valor anterior y el nuevo (AUD-01) y NO DEBE modificar ninguna versión de lista ni la lista asignada de ningún cliente. La siembra de una organización NO DEBE crear listas de precios: la lista predeterminada queda sin definir hasta que un usuario la define (`design.md` D11 del change 13). La lista predeterminada DEBE poder consultarse con `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`.

#### Scenario: Definir la lista General como predeterminada
- **GIVEN** la organización A sin lista predeterminada y la lista activa `General`
- **WHEN** un usuario con `ADMIN_CONFIGURACION` envía `LISTA_PRECIO_PREDETERMINADA_DEFINIR` con `General`
- **THEN** el comando queda `ACEPTADO`, la lista predeterminada de A es `General` y hay una fila de auditoría con el valor anterior nulo y el nuevo
- **Regla:** `01` §4 (lista de precios por defecto: General); PRC-20; AUD-01

#### Scenario: Cambiar la lista predeterminada
- **GIVEN** `General` como predeterminada y la lista activa `Mayorista`
- **WHEN** se define `Mayorista` como predeterminada
- **THEN** la predeterminada es `Mayorista`, los clientes con lista asignada conservan la suya y ninguna versión cambia
- **Regla:** PRC-20; INV-11

#### Scenario: Lista inactiva
- **WHEN** se envía `LISTA_PRECIO_PREDETERMINADA_DEFINIR` con una lista inactiva
- **THEN** se rechaza con `LISTA_INACTIVA` y la configuración no cambia
- **Regla:** PRC-20; `design.md` D11 del change 13

#### Scenario: Lista de otra organización
- **WHEN** un usuario de A envía el comando con una lista de B
- **THEN** la respuesta es 404 y la configuración de A no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso de configuración
- **WHEN** un usuario con `GESTIONAR_LISTAS` y sin `ADMIN_CONFIGURACION` (rol Administración) envía el comando
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y la configuración no cambia
- **Regla:** `01` §19 (`ADMIN_CONFIGURACION`); SEG-06

#### Scenario: Doble envío
- **GIVEN** un `LISTA_PRECIO_PREDETERMINADA_DEFINIR` aceptado con `operation_id` X
- **WHEN** se reenvía con X y el mismo contenido
- **THEN** se devuelve el resultado original y hay una sola fila de auditoría
- **Regla:** INV-06; SYN-02

#### Scenario: La organización recién sembrada no tiene lista predeterminada
- **WHEN** se siembra una organización nueva
- **THEN** no tiene ninguna lista de precios y su lista predeterminada queda sin definir
- **Regla:** `01` §4; `design.md` D11 del change 13

#### Scenario: La base rechaza una lista inexistente escrita por fuera del servicio
- **WHEN** se intenta escribir directamente en la configuración un identificador de lista que no existe en la organización
- **THEN** la base rechaza la escritura por la clave foránea compuesta
- **Regla:** INV-02; `03` §2.4; `03` §4 (`lista_precio_default_id`)

### Requirement: La lista predeterminada se administra desde la pantalla de configuración

El área `/admin` DEBE ofrecer, en Configuración y solo con `ADMIN_CONFIGURACION` (ADR-027), la elección de la lista de precios predeterminada entre las listas activas, mostrando la actual. Mientras la organización no tenga lista predeterminada, la pantalla DEBE advertir que los clientes sin lista asignada no tienen precio.

#### Scenario: Elegir la lista predeterminada
- **GIVEN** un Administrador y las listas activas `General` y `Mayorista`
- **WHEN** elige `General` y guarda
- **THEN** la pantalla muestra `General` como lista predeterminada
- **Regla:** `01` §4; PRC-20

#### Scenario: Organización sin lista predeterminada
- **GIVEN** una organización sin lista predeterminada
- **WHEN** un Administrador abre Configuración
- **THEN** ve la advertencia de que los clientes sin lista asignada no tienen precio
- **Regla:** PRC-20; VTA-10

#### Scenario: Sin permiso de configuración
- **GIVEN** un usuario sin `ADMIN_CONFIGURACION`
- **WHEN** entra a `/admin`
- **THEN** no ve la elección de la lista predeterminada
- **Regla:** ADR-027; SEG-06
