## ADDED Requirements

### Requirement: El redondeo por defecto se define por comando

El sistema DEBE definir el redondeo por defecto de la organización solo mediante `REDONDEO_POR_DEFECTO_DEFINIR` v1 (`ONLINE`, `ADMIN_CONFIGURACION`), con múltiplo (string decimal) y dirección (`ARRIBA`, `CERCANO`, `ABAJO`), los dos presentes o los dos nulos; los dos nulos lo dejan sin definir. El múltiplo DEBE ser mayor que cero con hasta dos decimales y la dirección de la lista cerrada (`REDONDEO_INVALIDO`, 422; PRC-01, PRC-14). Uno presente y otro nulo DEBE rechazarse con `REDONDEO_INVALIDO`. El comando NO DEBE modificar ninguna lista existente ni ningún precio. DEBE dejar una fila de auditoría con el valor anterior y el nuevo (`design.md` D10, D13).

#### Scenario: Definir el redondeo por defecto
- **GIVEN** la organización A sin redondeo por defecto (`01` §4: "a definir")
- **WHEN** un administrador define múltiplo `"100.00"` y dirección `ARRIBA`
- **THEN** la configuración de A queda con esos valores y la auditoría registra antes nulo y después `100.00` / `ARRIBA`
- **Regla:** `01` §4; PRC-14; AUD-01

#### Scenario: Las listas existentes no cambian
- **GIVEN** la lista General de A con redondeo a múltiplo de 100 hacia arriba (`01` §7.2) y su versión vigente
- **WHEN** se define el redondeo por defecto en múltiplo `"500.00"` y dirección `ABAJO`
- **THEN** la lista General conserva su redondeo y su versión vigente no cambia
- **Regla:** PRC-01 (la lista siempre tiene su propio redondeo)

#### Scenario: Quitar el redondeo por defecto
- **WHEN** se envía múltiplo y dirección nulos
- **THEN** el redondeo por defecto queda sin definir
- **Regla:** `design.md` D10

#### Scenario: Valores inválidos
- **WHEN** se envía múltiplo `"0.00"`, `"10.005"`, dirección `HACIA_ARRIBA`, o múltiplo sin dirección
- **THEN** se rechaza con `REDONDEO_INVALIDO` (422) y nada cambia
- **Regla:** PRC-01; INV-01

#### Scenario: Sin permiso, doble envío y modo offline
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía el comando, o un administrador lo envía dos veces con el mismo `operation_id`, o llega en modo `OFFLINE`
- **THEN** el primero recibe `PERMISO_REQUERIDO`; el segundo deja un solo cambio; el tercero se rechaza como tipo que no admite ese modo
- **Regla:** SEG-06; INV-06; `02` §6.5

#### Scenario: La base no admite un redondeo a medias
- **WHEN** se intenta guardar en la base un múltiplo sin dirección o un múltiplo no positivo
- **THEN** la restricción de la tabla lo rechaza
- **Regla:** `03` §4; `design.md` D10

### Requirement: El redondeo por defecto se consulta

El sistema DEBE exponer `GET /configuracion/redondeo-por-defecto` a quien tenga `ADMIN_CONFIGURACION` o `GESTIONAR_LISTAS`, con el múltiplo como string y la dirección, o los dos nulos si no está definido, solo de la organización del token (`design.md` D11).

#### Scenario: Lectura con permiso de listas
- **GIVEN** A con redondeo por defecto `"100.00"` / `ARRIBA`
- **WHEN** un usuario de Administración (con `GESTIONAR_LISTAS`, sin `ADMIN_CONFIGURACION`) lo lee
- **THEN** recibe `"100.00"` y `ARRIBA`
- **Regla:** `01` §19 (`GESTIONAR_LISTAS`); INV-21

#### Scenario: Sin permiso
- **WHEN** lo lee un vendedor
- **THEN** responde 403
- **Regla:** SEG-06

### Requirement: El redondeo por defecto se administra desde la pantalla de configuración

`/admin` DEBE ofrecer, con `ADMIN_CONFIGURACION`, la pestaña "Redondeo por defecto" en Configuración, con múltiplo y dirección, validados con el mismo criterio que el servidor y sin convertir el múltiplo a número para calcular, y un botón para dejarlo sin definir (`design.md` D12).

#### Scenario: Guardar y quitar
- **WHEN** un administrador guarda `100` y "Hacia arriba", y después usa "Quitar"
- **THEN** primero queda definido y después sin definir, con un mensaje de confirmación en cada caso
- **Regla:** `01` §4

#### Scenario: Múltiplo inválido en el formulario
- **WHEN** carga un múltiplo `0`
- **THEN** el formulario lo marca inválido y no envía el comando
- **Regla:** PRC-01; TR-10
