## Purpose

Detectar a tiempo un defecto que deje una tabla de saldo distinta de su libro: una tarea diaria compara, por organización, cada saldo materializado con lo que dicen sus movimientos, guarda el resultado y avisa al administrador, sin corregir nada (`02` §7.6, ADR-015, ADR-039).

## ADDED Requirements

### Requirement: La verificación de consistencia corre todos los días sin intervención

El sistema DEBE ejecutar una vez por día, a una hora configurable en la zona horaria del entorno, una verificación de consistencia para cada organización existente. La verificación DEBE poder ejecutarse también a pedido con una orden. Una corrida NO DEBE depender de que haya usuarios conectados ni del backend que atiende la API (`02` §7.6; ADR-015; `design.md` D2, D6).

#### Scenario: La corrida diaria verifica todas las organizaciones
- **GIVEN** dos organizaciones con movimientos de stock y de cuenta corriente
- **WHEN** llega la hora configurada de la verificación
- **THEN** se registra un resultado para cada una de las dos organizaciones con el momento de la corrida
- **Regla:** `02` §7.6; INV-02

#### Scenario: Verificación a pedido
- **GIVEN** el entorno levantado
- **WHEN** se ejecuta la orden de verificación a pedido
- **THEN** la verificación corre en el momento y registra su resultado igual que la diaria
- **Regla:** `design.md` D6

### Requirement: La verificación compara cada saldo con su libro y no corrige

La verificación DEBE comparar, con SQL en la base y filtrando siempre por organización: cada `saldo_cuenta` con la suma de sus `cuenta_movimiento` (INV-13); cada `stock_saldo` con la suma de sus `stock_movimiento` (INV-12); el `stock_total` de cada `costo_producto` con la suma de los `stock_saldo` del producto (ADR-039); y el promedio vigente de cada `costo_producto` con el promedio resultante de su último `costo_producto_mov` (CST-13). NO DEBE modificar ninguna fila de saldo, de libro ni de costo: una diferencia indica un defecto que se investiga (`02` §7.6; ADR-015; `design.md` D4).

#### Scenario: Sin diferencias después de operar
- **GIVEN** una organización con compras, ventas, transferencias, cobranzas y anulaciones registradas por los comandos del sistema
- **WHEN** corre la verificación
- **THEN** el resultado de esa organización es "sin diferencias"
- **Regla:** INV-12; INV-13; `02` §7.6

#### Scenario: Un saldo de cuenta alterado se informa y no se corrige
- **GIVEN** una fila de `saldo_cuenta` alterada a mano en la prueba (con el usuario de migraciones) para que no coincida con su libro
- **WHEN** corre la verificación
- **THEN** el resultado informa esa cuenta con el saldo materializado y la suma del libro, como importes en texto
- **AND** la fila de `saldo_cuenta` sigue con el valor alterado
- **Regla:** INV-13; ADR-015 (nunca se corrige automáticamente)

#### Scenario: Un saldo de stock alterado se informa
- **GIVEN** una fila de `stock_saldo` alterada a mano en la prueba para que no coincida con la suma de sus movimientos
- **WHEN** corre la verificación
- **THEN** el resultado informa el producto y la ubicación con la cantidad materializada y la suma del libro
- **Regla:** INV-12; `02` §7.6

#### Scenario: Un stock total alterado se informa
- **GIVEN** un `costo_producto` cuyo `stock_total` fue alterado a mano en la prueba
- **WHEN** corre la verificación
- **THEN** el resultado informa el producto con el `stock_total` y la suma de sus saldos
- **Regla:** ADR-039; `02` §7.6

#### Scenario: Una diferencia en una organización no se mezcla con otra
- **GIVEN** dos organizaciones, una con una diferencia provocada y otra sin diferencias
- **WHEN** corre la verificación
- **THEN** solo el resultado de la primera informa la diferencia y el de la segunda no menciona datos de la primera
- **Regla:** INV-02; INV-21

### Requirement: Una diferencia queda registrada como error crítico y visible para el administrador

Cada corrida DEBE guardar su resultado por organización (momento, resultado y detalle de las diferencias, sin datos personales). Una corrida con diferencias DEBE escribir un registro de nivel crítico en el log, dejar la salud del servicio que la ejecuta como no sana hasta una corrida sin diferencias y, si hay un aviso externo configurado, avisarlo. El aviso externo se envía con la variable propia `AVISO_TAREAS_URL` (distinta de `AVISO_URL`, la de `copia-externa`): tras cada corrida, programada o a pedido, una sin diferencias ni fallos DEBE llamar a esa dirección y una con diferencias o fallida DEBE llamar a `<dirección>/fail`; sin la variable no se llama a nadie; un aviso que no llega NO DEBE cambiar el resultado de la corrida ni la salud del servicio y solo queda en el log, sin la dirección. Para poder salir, `tareas` está en la red `salida` además de `datos` (decisión del usuario, opción A; ADR-073). Las señales locales son el aviso en `/admin`, el registro crítico y la salud no sana. Los usuarios con el permiso `VER_CONSISTENCIA` (de solo lectura, asignado a las plantillas `Administrador` y `Administración`; `Administración` NO recibe `ADMIN_CONFIGURACION`) DEBEN ver en `/admin` un aviso mientras el último resultado de su organización tenga diferencias, con el momento de la corrida y el detalle; el aviso DEBE traer su ayuda contextual. El aviso NO DEBE ofrecer ninguna acción que modifique saldos (`02` §7.6; ADR-015; `02` §17; ADR-051; `design.md` D5, D17).

#### Scenario: El administrador ve el aviso
- **GIVEN** el último resultado de la organización con una diferencia en una cuenta corriente
- **WHEN** un usuario con `VER_CONSISTENCIA` (`Administrador` o `Administración`) abre `/admin`
- **THEN** ve el aviso de diferencias con el momento de la corrida y la cuenta afectada
- **AND** el aviso tiene su "(?)"
- **Regla:** `02` §7.6 (se notifica al administrador); ADR-051

#### Scenario: Un usuario sin el permiso no ve el aviso ni lee el resultado
- **GIVEN** el último resultado con diferencias
- **WHEN** un vendedor abre `/admin` o pide el resultado a la API
- **THEN** no ve el aviso y la API responde 403
- **Regla:** SEG-06; `02` §18 (el servidor exige el permiso por cualquier camino)

#### Scenario: El aviso desaparece cuando una corrida posterior no encuentra diferencias
- **GIVEN** un resultado con diferencias seguido de una corrida sin diferencias
- **WHEN** el administrador abre `/admin`
- **THEN** no ve el aviso
- **Regla:** `design.md` D5

#### Scenario: El resultado de otra organización no se ve
- **GIVEN** dos organizaciones, la A con diferencias
- **WHEN** el administrador de la B pide el resultado a la API
- **THEN** recibe solo el resultado de la B, sin datos de la A
- **Regla:** INV-21; SEG-07

#### Scenario: Error crítico y salud no sana
- **GIVEN** una corrida que encuentra una diferencia
- **WHEN** termina
- **THEN** el log tiene un registro crítico con la organización y la cantidad de diferencias, sin nombres de clientes
- **AND** la salud del servicio de tareas queda no sana hasta la siguiente corrida sin diferencias
- **Regla:** `02` §7.6; `02` §17

#### Scenario: Una corrida que falla también se ve
- **GIVEN** la base no disponible a la hora de la verificación
- **WHEN** la corrida falla
- **THEN** queda un registro de error en el log, la salud del servicio queda no sana y la siguiente corrida vuelve a intentar
- **Regla:** `design.md` D6

#### Scenario: Aviso externo de una corrida con diferencias
- **GIVEN** `AVISO_TAREAS_URL` configurada y una diferencia de saldos
- **WHEN** corre la verificación (programada o `ahora`)
- **THEN** se llama a `<AVISO_TAREAS_URL>/fail` y no a la dirección base
- **Regla:** `design.md` D5 d; ADR-073

#### Scenario: Aviso externo de una corrida sin diferencias
- **GIVEN** `AVISO_TAREAS_URL` configurada y todos los saldos coherentes
- **WHEN** corre la verificación y la limpieza termina bien
- **THEN** se llama a `<AVISO_TAREAS_URL>`
- **Regla:** `design.md` D5 d; ADR-073

#### Scenario: Sin dirección de aviso no se llama a nadie
- **GIVEN** `AVISO_TAREAS_URL` vacía
- **WHEN** corre la verificación, con o sin diferencias
- **THEN** no se intenta ninguna llamada de red
- **Regla:** `design.md` D5 d

#### Scenario: Un aviso fallido no altera el resultado
- **GIVEN** `AVISO_TAREAS_URL` configurada pero sin respuesta
- **WHEN** corre la verificación
- **THEN** la corrida guarda el mismo resultado y deja la misma salud que sin aviso, y el log registra el fallo sin mostrar la dirección
- **Regla:** `design.md` D5 d; ADR-073
