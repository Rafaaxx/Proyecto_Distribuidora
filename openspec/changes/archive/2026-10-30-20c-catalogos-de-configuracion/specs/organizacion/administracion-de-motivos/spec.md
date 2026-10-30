## Purpose

Permite que la organización administre sus motivos de cada ámbito (alta, cambio de nombre, baja y reactivación) desde `/admin`, por el bus de comandos y sin borrar nada, sin dejar ninguna operación sin un motivo activo que elegir (TR-09, CAT-05, ADR-061).

## ADDED Requirements

### Requirement: Un motivo se crea por comando

El sistema DEBE crear un motivo solo mediante el comando `MOTIVO_CREAR` v1, en modo `ONLINE` y con `ADMIN_CONFIGURACION`, con un ámbito de la lista cerrada y un nombre. El nombre DEBE guardarse recortado; vacío o de solo espacios DEBE rechazarse con `NOMBRE_INVALIDO` (422). Un ámbito fuera de la lista DEBE rechazarse con `AMBITO_INVALIDO` (422). El nombre DEBE ser único en la organización y el ámbito sin distinguir mayúsculas, entre activos e inactivos (`NOMBRE_DUPLICADO`, 409). El motivo DEBE nacer activo y la organización DEBE salir del token (`design.md` D1 a D3, D5).

#### Scenario: Alta de un motivo de ajuste
- **GIVEN** la organización A con sus motivos de ajuste sembrados
- **WHEN** un administrador crea el motivo "  Robo  " en el ámbito `AJUSTE_STOCK`
- **THEN** se crea activo con el nombre "Robo" y aparece entre los motivos de `AJUSTE_STOCK` de A
- **Regla:** TR-09; INV-21

#### Scenario: Nombre repetido en el mismo ámbito
- **GIVEN** el motivo "Rotura" de `AJUSTE_STOCK` de A, inactivo
- **WHEN** se crea "rotura" en `AJUSTE_STOCK`
- **THEN** se rechaza con `NOMBRE_DUPLICADO` y no se crea nada
- **Regla:** `design.md` D3; INV-01

#### Scenario: El mismo nombre en otro ámbito o en otra organización
- **GIVEN** el motivo "Otro" en `AJUSTE_STOCK` de A
- **WHEN** se crea "Otro" en `ANULACION_VENTA` de A, o "Rotura" en `AJUSTE_STOCK` de B
- **THEN** los dos se aceptan
- **Regla:** `design.md` D3; INV-02

#### Scenario: Nombre vacío o ámbito inválido
- **WHEN** se crea un motivo con nombre "   " o con ámbito `CUALQUIERA`
- **THEN** se rechaza con `NOMBRE_INVALIDO` o `AMBITO_INVALIDO` (422) y no se crea nada
- **Regla:** `03` §4 (lista cerrada de `ambito`); TR-10

#### Scenario: Sin permiso
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía `MOTIVO_CREAR`
- **THEN** recibe `PERMISO_REQUERIDO` y no se crea nada
- **Regla:** SEG-06; ADR-056

#### Scenario: Doble envío
- **WHEN** se envía dos veces `MOTIVO_CREAR` con el mismo `operation_id` y el mismo contenido
- **THEN** existe un solo motivo y la segunda respuesta es la original
- **Regla:** INV-06

### Requirement: Un motivo se renombra, se da de baja y se reactiva por comando

El sistema DEBE modificar un motivo solo mediante `MOTIVO_MODIFICAR` v1 (`ONLINE`, `ADMIN_CONFIGURACION`), con reemplazo completo de nombre y estado activo. El ámbito NO DEBE cambiar. Ningún comando DEBE borrar un motivo. La baja DEBE rechazarse con `ULTIMO_MOTIVO_ACTIVO` (409) si deja el ámbito sin ningún motivo activo en la organización. Un motivo inactivo NO DEBE ofrecerse en operaciones nuevas y DEBE seguir legible por id en las operaciones que lo usaron. Un motivo de otra organización o inexistente DEBE responder 404 (`design.md` D2, D4).

#### Scenario: Renombrar
- **GIVEN** un ajuste de stock confirmado con el motivo "Rotura"
- **WHEN** el motivo pasa a llamarse "Rotura en depósito"
- **THEN** el ajuste muestra "Rotura en depósito"
- **Regla:** `design.md` D2; TR-06

#### Scenario: Baja y reactivación
- **GIVEN** los seis motivos activos de `AJUSTE_STOCK` (`01` §4)
- **WHEN** se da de baja "Muestra"
- **THEN** deja de aparecer en `GET /configuracion/motivos?ambito=AJUSTE_STOCK` y un ajuste nuevo con ese motivo se rechaza
- **AND** al reactivarlo vuelve a ofrecerse
- **Regla:** CAT-05; STK-08

#### Scenario: Último motivo activo del ámbito
- **GIVEN** `LIBERACION_JORNADA` de A con un solo motivo activo, "Otro"
- **WHEN** se da de baja "Otro"
- **THEN** se rechaza con `ULTIMO_MOTIVO_ACTIVO` (409) y el motivo sigue activo
- **Regla:** `design.md` D4; RUT-09; INV-01

#### Scenario: El ámbito no se cambia
- **WHEN** `MOTIVO_MODIFICAR` trae un campo de ámbito
- **THEN** se rechaza por contenido inválido y nada cambia
- **Regla:** `design.md` D2

#### Scenario: Motivo de otra organización
- **WHEN** un administrador de B modifica un motivo de A
- **THEN** responde 404 y el motivo de A no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío y auditoría
- **WHEN** se envía dos veces la misma baja con el mismo `operation_id`
- **THEN** hay un solo cambio y una fila de auditoría de `motivo` con `antes` y `despues`
- **Regla:** INV-06; AUD-01

### Requirement: Dos bajas simultáneas no dejan un ámbito sin motivos

Las bajas concurrentes de motivos de un mismo ámbito DEBEN serializarse, de modo que nunca quede el ámbito sin motivos activos (`design.md` D4).

#### Scenario: Bajas simultáneas de los dos últimos
- **GIVEN** `ANULACION_TRANSFERENCIA` de A con dos motivos activos
- **WHEN** dos administradores dan de baja uno cada uno al mismo tiempo, con commits reales
- **THEN** una baja se acepta y la otra se rechaza con `ULTIMO_MOTIVO_ACTIVO`
- **Regla:** `design.md` D4; INV-01

### Requirement: La administración lee todos los motivos

El sistema DEBE exponer `GET /configuracion/motivos/todos`, con `ADMIN_CONFIGURACION`, que devuelve los motivos activos e inactivos de la organización del token, opcionalmente filtrados por un ámbito de la lista cerrada, ordenados por ámbito y nombre, con `ambito`, `nombre`, `activo` y `actualizado_en`. `GET /configuracion/motivos?ambito=` NO DEBE cambiar (`design.md` D12).

#### Scenario: Activos e inactivos
- **GIVEN** "Muestra" de baja en `AJUSTE_STOCK` de A
- **WHEN** un administrador lee los motivos de `AJUSTE_STOCK`
- **THEN** recibe los seis, "Muestra" con `activo = false`, y ninguno de B
- **Regla:** TR-08; INV-21

#### Scenario: Sin permiso
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` pide la lectura completa
- **THEN** responde 403
- **Regla:** SEG-06

### Requirement: La pantalla de motivos

`/admin` DEBE ofrecer, con `ADMIN_CONFIGURACION`, la pestaña "Motivos" en Configuración: un selector de ámbito con nombres en castellano, la lista de motivos del ámbito con su estado, el alta, el cambio de nombre y la baja y reactivación con confirmación. Los errores `NOMBRE_DUPLICADO`, `NOMBRE_INVALIDO` y `ULTIMO_MOTIVO_ACTIVO` DEBEN explicarse en palabras simples. Un reintento DEBE reusar el mismo `Operation-Id` (`design.md` D12).

#### Scenario: Alta desde la pantalla
- **WHEN** un administrador elige "Ajuste de stock" y crea "Robo"
- **THEN** el motivo aparece en la lista y en el desplegable del ajuste de stock
- **Regla:** TR-09

#### Scenario: Último activo explicado
- **WHEN** intenta dar de baja el último motivo activo de un ámbito
- **THEN** la pantalla explica que cada ámbito tiene que conservar al menos un motivo activo
- **Regla:** `design.md` D4

#### Scenario: Sin permiso no se ofrece
- **WHEN** entra un usuario sin `ADMIN_CONFIGURACION`
- **THEN** no ve la pestaña "Motivos"
- **Regla:** ADR-027
