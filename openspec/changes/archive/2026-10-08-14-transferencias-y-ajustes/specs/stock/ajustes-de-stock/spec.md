## Purpose

Corregir el stock de una ubicación con un motivo del catálogo de la organización (rotura, vencimiento, diferencia de inventario, etc.), como operación atómica e idempotente valorizada al costo promedio vigente sin modificarlo (STK-08, CST-12, AUD-01), y anularlo por completo cuando se cargó mal (TR-06). Un ajuste positivo es también el camino para regularizar un saldo negativo; un ajuste nunca deja un saldo negativo.

## ADDED Requirements

### Requirement: Registrar un ajuste de stock con motivo

El sistema DEBE registrar el comando `STOCK_AJUSTAR` (solo `ONLINE`, `02` §6.5) con el permiso `AJUSTAR_STOCK`, una ubicación activa de la organización, un motivo activo del ámbito `AJUSTE_STOCK` de la organización, una observación opcional de hasta 500 caracteres y de 1 a 200 líneas sin producto repetido, cada una con `cantidad_base` entera distinta de cero, admitiendo signos mezclados en el mismo ajuste (STK-08, TR-09, `design.md` D6). En una sola transacción DEBE crear el ajuste con sus líneas y un movimiento `AJUSTE` por línea con el motivo y origen en el ajuste (STK-03, `design.md` D8). El ajuste DEBE nacer en estado `CONFIRMADA`. Un motivo de otro ámbito o inactivo DEBE rechazarse con `MOTIVO_INVALIDO` (422); uno de otra organización o inexistente, con 404. Todo producto DEBE existir en la organización (si no, 404) y estar activo (`PRODUCTO_INACTIVO`, `design.md` D4).

#### Scenario: Rotura en el depósito

- **GIVEN** 120 unidades de Vino A en el depósito, stock total 120 y promedio `"1050.000000"`
- **WHEN** un usuario de Administración con `AJUSTAR_STOCK` registra un ajuste de −6 en el depósito con el motivo "Rotura"
- **THEN** el comando queda `ACEPTADO`, existe un ajuste `CONFIRMADA` con el motivo y una línea de −6 a `"1050.000000"`, el libro tiene un movimiento `AJUSTE` de −6 con el motivo y ese costo, el saldo queda en 114, el stock total en 114 y el promedio en `"1050.000000"`
- **Regla:** STK-08; CST-12

#### Scenario: Conteo con sobrantes y faltantes

- **GIVEN** stock de Vino A y Agua 500 en "Camioneta 1"
- **WHEN** se registra un ajuste con Vino A −2 y Agua 500 +1 con el motivo "Diferencia de inventario"
- **THEN** existe un ajuste con dos líneas y dos movimientos `AJUSTE`, y cada saldo cambia por su cantidad
- **Regla:** STK-08; `design.md` D6

#### Scenario: Motivo inválido

- **GIVEN** un motivo inactivo del ámbito `AJUSTE_STOCK` y uno activo del ámbito `ANULACION_COMPRA`
- **WHEN** se registra un ajuste con cada uno
- **THEN** ambos se rechazan con `MOTIVO_INVALIDO` y no se escribe nada
- **Regla:** STK-08; TR-09

#### Scenario: Motivo, ubicación o producto de otra organización

- **GIVEN** un motivo, una ubicación y un producto de la organización B
- **WHEN** un usuario de la organización A los usa en un ajuste
- **THEN** la respuesta es 404 y no se escribe nada
- **Regla:** INV-21; SEG-07

#### Scenario: Líneas inválidas

- **GIVEN** un usuario con `AJUSTAR_STOCK`
- **WHEN** envía un ajuste sin líneas, con 201 líneas, con un producto repetido, con cantidad 0 o con cantidad 1.5
- **THEN** se rechaza con `LINEAS_INVALIDAS`, `PRODUCTO_REPETIDO`, `CANTIDAD_INVALIDA` o 422 de validación, sin escribir nada
- **Regla:** INV-04; `design.md` D6

#### Scenario: Observación demasiado larga

- **GIVEN** un usuario con `AJUSTAR_STOCK`
- **WHEN** envía una observación de 501 caracteres
- **THEN** la respuesta es 422 y no se escribe nada
- **Regla:** `design.md` D6

#### Scenario: Ubicación inactiva

- **GIVEN** "Camioneta 2" inactiva
- **WHEN** se registra un ajuste sobre ella
- **THEN** se rechaza con `UBICACION_INACTIVA`
- **Regla:** ADR-038

#### Scenario: Usuario con permiso de transferir pero no de ajustar

- **GIVEN** un Vendedor con `TRANSFERIR_STOCK` y sin `AJUSTAR_STOCK`
- **WHEN** envía un ajuste
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se escribe nada
- **Regla:** STK-08; SEG-06

#### Scenario: Comando fuera de línea

- **GIVEN** un usuario con `AJUSTAR_STOCK`
- **WHEN** el comando llega con modo `OFFLINE`
- **THEN** se rechaza y no se escribe nada
- **Regla:** `02` §6.5

#### Scenario: Doble envío del mismo comando

- **GIVEN** un ajuste aceptado con un `operation_id`
- **WHEN** se reenvía con el mismo contenido y después con otro contenido
- **THEN** el primer reenvío devuelve el resultado original sin nuevos movimientos y el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

### Requirement: Un ajuste se valoriza al promedio vigente sin modificarlo

Todo movimiento de ajuste, de ingreso o de egreso, DEBE guardar como costo el promedio vigente del producto al aplicarse, sin recalcularlo y sin historia en `costo_producto_mov`; el stock total DEBE cambiar por la cantidad ajustada (CST-12, CST-13, `design.md` D3). Un ajuste positivo de un producto sin promedio DEBE rechazarse con `PRODUCTO_SIN_COSTO` (409).

#### Scenario: Ajuste positivo al promedio

- **GIVEN** Vino A con stock total 120 y promedio `"1050.000000"`
- **WHEN** se ajusta +2 en el depósito con "Diferencia de inventario"
- **THEN** el movimiento guarda `"1050.000000"`, el stock total es 122, el promedio sigue en `"1050.000000"` y no hay historia de costo nueva
- **Regla:** CST-12; CST-13

#### Scenario: Ajuste positivo de un producto sin costo

- **GIVEN** el producto Agua 1500 sin ningún ingreso con costo
- **WHEN** se ajusta +24 en el depósito
- **THEN** se rechaza con `PRODUCTO_SIN_COSTO` y no se escribe nada
- **Regla:** CST-12; ADR-039; `design.md` D3

### Requirement: Un ajuste nunca deja stock negativo

Un ajuste negativo DEBE aplicarse solo si el saldo de la ubicación alcanza. Si no alcanza, DEBE rechazarse con `STOCK_INSUFICIENTE` (409) sin escribir nada, **tenga o no** el usuario `PERMITIR_STOCK_NEGATIVO`: un ajuste refleja un conteo físico y lo físico no es negativo (STK-05 precisada por `design.md` D1 = B). Un ajuste de varias líneas DEBE rechazarse entero si una sola no alcanza.

#### Scenario: Ajuste mayor que el saldo sin permiso

- **GIVEN** 10 unidades de Vino A en el depósito y un usuario de Administración sin `PERMITIR_STOCK_NEGATIVO`
- **WHEN** ajusta −11
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 10
- **Regla:** STK-05; `design.md` D1

#### Scenario: Ajuste mayor que el saldo con permiso de stock negativo

- **GIVEN** 10 unidades de Vino A en el depósito y un Administrador con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** ajusta −11
- **THEN** se rechaza igual con `STOCK_INSUFICIENTE`, el saldo sigue en 10 y no hay observación `STOCK_NEGATIVO`
- **Regla:** STK-05; `design.md` D1

#### Scenario: Una línea que no alcanza rechaza todo el ajuste

- **GIVEN** 10 unidades de Vino A y 5 de Agua 500 en el depósito
- **WHEN** se ajusta Vino A −2 y Agua 500 −6 en un mismo ajuste
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y ningún saldo cambia
- **Regla:** STK-05; INV-01

### Requirement: Un ajuste positivo regulariza un saldo negativo

Un saldo negativo (por ejemplo el que deja una anulación de compra con permiso, ADR-044) DEBE poder regularizarse con un ajuste positivo, que no tiene tratamiento especial (`design.md` D2).

#### Scenario: Regularizar a cero tras anular una compra

- **GIVEN** −12 unidades de Vino A en el depósito tras anular una compra de 60 cuando quedaban 48, y promedio `"1050.000000"`
- **WHEN** se ajusta +12 con "Diferencia de inventario"
- **THEN** el saldo queda en 0, el movimiento guarda `"1050.000000"` y el promedio no cambia
- **Regla:** STK-05; CST-12; `design.md` D2

### Requirement: Un ajuste rechaza un producto inactivo

Un ajuste con algún producto inactivo DEBE rechazarse con `PRODUCTO_INACTIVO` (409), sea la línea positiva o negativa, sin escribir nada (CAT-05, ADR-038 punto 5, `design.md` D4). Como un producto con stock no puede desactivarse (spec `catalogo/productos-y-presentaciones`), la baja del stock de un producto que se discontinúa se registra **antes** de desactivarlo.

#### Scenario: Baja de un producto inactivo

- **GIVEN** "Vino Rosado" inactivo, que quedó con 18 unidades en "Camioneta 1" porque se desactivó antes de que existiera la regla
- **WHEN** se ajusta −18 con "Vencimiento"
- **THEN** se rechaza con `PRODUCTO_INACTIVO` y el saldo sigue en 18
- **Regla:** CAT-05; ADR-038; `design.md` D4

#### Scenario: Ingreso de un producto inactivo

- **GIVEN** "Vino Rosado" inactivo
- **WHEN** se ajusta +6
- **THEN** se rechaza con `PRODUCTO_INACTIVO`
- **Regla:** CAT-05

#### Scenario: Reactivar, dar de baja y volver a desactivar

- **GIVEN** "Vino Rosado" reactivado con 18 unidades en "Camioneta 1"
- **WHEN** se ajusta −18 con "Vencimiento" y después se lo desactiva
- **THEN** el ajuste se acepta, el saldo queda en 0 y la desactivación se acepta
- **Regla:** CAT-05; `design.md` D4

### Requirement: Un ajuste es atómico

El ajuste, sus líneas y todos sus movimientos DEBEN registrarse completos o no registrarse (INV-01).

#### Scenario: Falla entre dos líneas

- **GIVEN** un ajuste de dos líneas y una falla inyectada después de escribir el primer movimiento
- **WHEN** se procesa
- **THEN** no queda ajuste, línea, movimiento ni cambio de saldo o de stock total
- **Regla:** INV-01

### Requirement: Los ajustes se consultan por organización

El sistema DEBE listar los ajustes de la organización, más recientes primero, con filtros opcionales por ubicación, motivo y fechas de negocio, con cursor y límite de 1 a 200, y DEBE devolver el detalle con ubicación, motivo, observación, usuario, `occurred_at`, **estado** (`CONFIRMADA` o `ANULADA`) y líneas con código, nombre, cantidad y unidades de referencia del producto. El listado DEBE traer el estado de cada ajuste; el detalle de uno anulado DEBE traer el motivo, el usuario y el momento de la anulación. Ambas lecturas DEBEN exigir `AJUSTAR_STOCK`; el costo de cada línea DEBE omitirse sin `VER_COSTOS` (`design.md` D7, ADR-036). Un ajuste de otra organización DEBE responderse como 404.

#### Scenario: Listado filtrado por motivo

- **GIVEN** un ajuste por "Rotura" y otro por "Vencimiento"
- **WHEN** se lista con el filtro "Rotura"
- **THEN** solo aparece el primero, con su estado
- **Regla:** `design.md` D7

#### Scenario: Costo según permiso

- **GIVEN** el ajuste de −6 de Vino A
- **WHEN** lo consultan un Administrador y un usuario con `AJUSTAR_STOCK` sin `VER_COSTOS`
- **THEN** el primero recibe `costo_unitario` `"1050.000000"` como string y el segundo no recibe ningún campo de costo
- **Regla:** `01` §19; ADR-036

#### Scenario: Detalle de un ajuste anulado

- **GIVEN** el ajuste de −6 de Vino A anulado por "Error de carga"
- **WHEN** se consulta su detalle y el listado
- **THEN** ambos lo muestran `ANULADA`, y el detalle trae el motivo "Rotura" del ajuste y, de la anulación, el motivo "Error de carga", quién lo anuló y cuándo
- **Regla:** TR-06; `design.md` D5

#### Scenario: Lectura sin permiso o ajena

- **GIVEN** un ajuste de la organización B
- **WHEN** un Vendedor sin `AJUSTAR_STOCK` lista, o un usuario de la organización A pide su detalle
- **THEN** las respuestas son 403 y 404 respectivamente
- **Regla:** INV-21; SEG-06

### Requirement: Un ajuste se audita con su motivo

Cada ajuste DEBE dejar una sola fila de auditoría del comando con acción `STOCK_AJUSTAR`, usuario, dispositivo, `operation_id` y, en `motivo_id`, el motivo del ajuste, que el handler devuelve y el bus copia a su fila (AUD-01, AUD-02, ADR-022, `design.md` D10). El motivo y la observación DEBEN quedar además en el ajuste y el motivo en sus movimientos. Un ajuste rechazado NO DEBE dejar fila de auditoría con motivo, y un reenvío idempotente NO DEBE escribir otra fila. El cambio del bus NO DEBE alterar la auditoría de los demás comandos: los que no devuelven motivo siguen dejando `motivo_id` nulo.

#### Scenario: Auditoría del ajuste con motivo

- **GIVEN** un ajuste de −6 por "Rotura" aceptado
- **WHEN** se consulta la auditoría
- **THEN** existe una sola fila con acción `STOCK_AJUSTAR`, el usuario, el dispositivo, el `operation_id` y `motivo_id` igual al de "Rotura"
- **Regla:** AUD-01; AUD-02; ADR-022

#### Scenario: Reenvío del mismo ajuste

- **GIVEN** ese ajuste ya auditado
- **WHEN** se reenvía con el mismo `operation_id`
- **THEN** sigue existiendo una sola fila de auditoría
- **Regla:** INV-06; ADR-022

#### Scenario: Los demás comandos no cambian

- **GIVEN** una transferencia y una anulación de compra aceptadas después de este change
- **WHEN** se consulta la auditoría
- **THEN** sus filas tienen `motivo_id` nulo, como antes
- **Regla:** ADR-022; `design.md` D10

### Requirement: Un ajuste no se edita ni se borra

Un ajuste confirmado NO DEBE modificarse ni eliminarse (TR-06): `app_runtime` DEBE tener `SELECT` e `INSERT` sobre `ajuste_stock` y `ajuste_stock_linea`, sin `DELETE` sobre ninguna y sin `UPDATE` sobre las líneas; sobre la cabecera DEBE tener `UPDATE` **solo** del estado y de las columnas de anulación (motivo, momento y usuario), como `compra` (`design.md` D5, D8). Un ajuste mal cargado se corrige anulándolo y cargando otro.

#### Scenario: Sin permisos de modificación

- **GIVEN** la base migrada y una conexión como `app_runtime`
- **WHEN** intenta `DELETE` sobre `ajuste_stock` o `ajuste_stock_linea`, `UPDATE` sobre `ajuste_stock_linea`, o `UPDATE` de `motivo_id`, `ubicacion_id` u `observacion` de `ajuste_stock`
- **THEN** PostgreSQL rechaza cada sentencia
- **Regla:** INV-05; TR-06

#### Scenario: Estado y anulación coherentes en la base

- **GIVEN** la base migrada
- **WHEN** se intenta dejar un ajuste `ANULADA` sin motivo de anulación, o `CONFIRMADA` con momento de anulación, o con un estado distinto de los dos
- **THEN** la base lo rechaza
- **Regla:** `01` §18; `design.md` D8

### Requirement: Anular un ajuste

El sistema DEBE registrar el comando `STOCK_AJUSTE_ANULAR` (solo `ONLINE`) con el permiso `AJUSTAR_STOCK`, sobre un ajuste `CONFIRMADA` de la organización, propio o de otro usuario, con un motivo activo del ámbito `ANULACION_AJUSTE` (`MOTIVO_INVALIDO`, 422, si está inactivo o es de otro ámbito; 404 si es ajeno). La anulación DEBE ser total y única: en una sola transacción DEBE tomar el ajuste con bloqueo exclusivo, escribir por cada línea un movimiento `AJUSTE` de signo contrario con origen `ANULACION_AJUSTE_STOCK`, el id del ajuste y el motivo de la anulación, y pasarlo a `ANULADA` con su motivo, momento y usuario (TR-06, `01` §18, `design.md` D5, D5.1). Cada movimiento inverso DEBE guardar el **mismo `costo_unitario`** que la línea original (nulo si era nulo); la anulación DEBE mover el stock total en sentido contrario al ajuste y NO DEBE cambiar el promedio ni dejar historia de costo (CST-12, CST-13). La regla `PRODUCTO_SIN_COSTO` NO se aplica a un movimiento inverso. Un ajuste ya anulado DEBE rechazarse con `AJUSTE_YA_ANULADO` (409). Un ajuste inexistente o de otra organización DEBE responderse como 404.

#### Scenario: Anular una rotura mal cargada

- **GIVEN** un ajuste de −6 de Vino A en el depósito a `"1050.000000"` (saldo 114, stock total 114), cargado por otro usuario, y el promedio de hoy en `"1100.000000"`
- **WHEN** un usuario de Administración con `AJUSTAR_STOCK` lo anula con el motivo "Error de carga"
- **THEN** el comando queda `ACEPTADO`, el libro suma un `AJUSTE` de +6 a `"1050.000000"` con origen `ANULACION_AJUSTE_STOCK` y el motivo "Error de carga", el saldo queda en 120, el stock total en 120, el promedio sigue en `"1100.000000"` sin historia de costo nueva y el ajuste queda `ANULADA`
- **Regla:** TR-06; CST-12; CST-13; `design.md` D5

#### Scenario: Anular un conteo con signos mezclados

- **GIVEN** un ajuste con Vino A −2 y Agua 500 +1
- **WHEN** se lo anula
- **THEN** el libro suma Vino A +2 y Agua 500 −1, cada uno al costo de su línea original
- **Regla:** TR-06; `design.md` D5

#### Scenario: Segunda anulación

- **GIVEN** un ajuste `ANULADA`
- **WHEN** se lo anula otra vez con otro `operation_id`
- **THEN** se rechaza con `AJUSTE_YA_ANULADO` y no se escribe nada
- **Regla:** `01` §18; `design.md` D5

#### Scenario: Motivo inválido o ajeno

- **GIVEN** un motivo activo del ámbito `AJUSTE_STOCK`, uno inactivo de `ANULACION_AJUSTE` y uno de la organización B
- **WHEN** se anula un ajuste con cada uno
- **THEN** los dos primeros se rechazan con `MOTIVO_INVALIDO` y el tercero con 404, sin escribir nada
- **Regla:** TR-09; INV-21

#### Scenario: Sin permiso o ajuste de otra organización

- **GIVEN** un Vendedor con `TRANSFERIR_STOCK` y sin `AJUSTAR_STOCK`, y un ajuste de la organización B
- **WHEN** el Vendedor anula un ajuste de su organización, y un usuario de la organización A con `AJUSTAR_STOCK` anula el de la B
- **THEN** las respuestas son 403 `PERMISO_REQUERIDO` y 404
- **Regla:** SEG-06; INV-21

#### Scenario: Doble envío y comando fuera de línea

- **GIVEN** una anulación aceptada con un `operation_id`
- **WHEN** se reenvía con el mismo `operation_id` y contenido, y aparte llega otra en modo `OFFLINE`
- **THEN** el reenvío devuelve el resultado original sin nuevos movimientos y la `OFFLINE` se rechaza
- **Regla:** INV-06; `02` §6.5

#### Scenario: Falla en medio de la anulación

- **GIVEN** un ajuste de dos líneas y una falla inyectada después del primer movimiento inverso
- **WHEN** se procesa la anulación
- **THEN** no queda ningún movimiento inverso ni cambio de saldo o de stock total y el ajuste sigue `CONFIRMADA`
- **Regla:** INV-01

### Requirement: La anulación de un ajuste respeta el stock y los inactivos

Si la anulación de un ajuste con líneas positivas dejaría bajo cero algún saldo, DEBE rechazarse con `STOCK_INSUFICIENTE` sin escribir nada, salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`: entonces DEBE aplicarse y el comando DEBE quedar `ACEPTADO_CON_OBSERVACIONES` con una observación `STOCK_NEGATIVO` por cada producto y ubicación bajo cero (STK-05, ADR-044, `design.md` D5). Esta excepción es de la anulación y NO se extiende al ajuste (`design.md` D1). Si algún producto o la ubicación del ajuste está inactivo, la anulación DEBE rechazarse con `PRODUCTO_INACTIVO` o `UBICACION_INACTIVA` (ADR-038 punto 5, `design.md` D4).

#### Scenario: El stock de un ajuste positivo ya salió, sin permiso

- **GIVEN** un ajuste de +12 de Vino A en el depósito, que ahora tiene 5, y un usuario de Administración sin `PERMITIR_STOCK_NEGATIVO`
- **WHEN** lo anula
- **THEN** se rechaza con `STOCK_INSUFICIENTE`, el saldo sigue en 5 y el ajuste sigue `CONFIRMADA`
- **Regla:** STK-05; `design.md` D5

#### Scenario: El stock de un ajuste positivo ya salió, con permiso

- **GIVEN** la misma situación y un Administrador con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** lo anula
- **THEN** el saldo queda en −7, el comando queda `ACEPTADO_CON_OBSERVACIONES` con `STOCK_NEGATIVO` sobre el ajuste y este queda `ANULADA`
- **Regla:** STK-05; SYN-07; ADR-044

#### Scenario: Producto o ubicación inactivos

- **GIVEN** un ajuste cuyo producto se desactivó después, y otro cuya ubicación se desactivó después
- **WHEN** se anula cada uno
- **THEN** se rechazan con `PRODUCTO_INACTIVO` y `UBICACION_INACTIVA` y nada cambia
- **Regla:** CAT-05; ADR-038; `design.md` D5

### Requirement: La anulación de un ajuste se audita con su motivo

Cada anulación DEBE dejar una sola fila de auditoría del comando con acción `STOCK_AJUSTE_ANULAR`, usuario, dispositivo, `operation_id` y, en `motivo_id`, el motivo de la anulación que el handler devuelve y el bus copia (AUD-02, ADR-022, `design.md` D10).

#### Scenario: Auditoría de la anulación

- **GIVEN** el ajuste por "Rotura" anulado con "Error de carga"
- **WHEN** se consulta la auditoría
- **THEN** existen dos filas: `STOCK_AJUSTAR` con el motivo "Rotura" y `STOCK_AJUSTE_ANULAR` con el motivo "Error de carga", cada una con su `operation_id`
- **Regla:** AUD-01; AUD-02; ADR-022
