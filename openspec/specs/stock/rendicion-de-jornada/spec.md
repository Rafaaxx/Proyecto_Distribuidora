# stock/rendicion-de-jornada Specification

## Purpose
Rendición de una jornada de ruta: la entrega del día desde el teléfono, el conteo físico del vehículo contra el stock esperado, las diferencias en el libro, el resumen de la jornada y la devolución del remanente al cerrar.

## Requirements

### Requirement: La entrega del día marca la jornada como entregada

`JORNADA_ENTREGAR` v1 DEBE exigir `ABRIR_JORNADA`, admitirse solo en modo `OFFLINE` por el lote, llevar el contenido vacío y aplicarse a la jornada del sobre, que DEBE ser del usuario y del dispositivo del sobre (`JORNADA_AJENA`, `JORNADA_INEXISTENTE`, `JORNADA_REQUERIDA`). Con la jornada `ABIERTA` y sin entrega DEBE guardar el momento de registro, el momento de origen y la secuencia de la entrega, sin cambiar el estado. Con la jornada en otro estado DEBE rechazarse con `JORNADA_ESTADO_INVALIDO` y, ya entregada, con `JORNADA_YA_ENTREGADA`, sin cambios (`design.md` D1).

#### Scenario: Entrega aceptada
- **GIVEN** la jornada `ABIERTA` de Juan sobre "Camioneta 1" en su teléfono
- **WHEN** llega su `JORNADA_ENTREGAR` con la secuencia 12
- **THEN** la jornada sigue `ABIERTA` con la entrega registrada (momento y secuencia 12)
- **Regla:** RUT-05; `design.md` D1

#### Scenario: Entrega de una jornada liberada
- **GIVEN** la jornada de Juan `LIBERADA` por un supervisor
- **WHEN** llega su `JORNADA_ENTREGAR`
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO` y la jornada no cambia
- **Regla:** RUT-09; `01` §18

#### Scenario: Segunda entrega con otro identificador
- **GIVEN** la jornada de Juan ya entregada
- **WHEN** llega otro `JORNADA_ENTREGAR` con otro `operation_id`
- **THEN** se rechaza con `JORNADA_YA_ENTREGADA` y la entrega original no cambia
- **Regla:** RUT-05

#### Scenario: Entrega de la jornada de otro
- **GIVEN** la jornada de Pedro en otro dispositivo
- **WHEN** Juan envía `JORNADA_ENTREGAR` con esa jornada en el sobre
- **THEN** se rechaza con `JORNADA_AJENA` sin cambios
- **Regla:** RUT-01; INV-21

#### Scenario: Entrega sin permiso
- **GIVEN** un usuario sin `ABRIR_JORNADA`
- **WHEN** envía `JORNADA_ENTREGAR`
- **THEN** se rechaza con `PERMISO_REQUERIDO` sin cambios
- **Regla:** `01` §19; SEG-06

#### Scenario: Doble envío de la entrega
- **GIVEN** un `JORNADA_ENTREGAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original y la entrega no cambia
- **Regla:** SYN-02; INV-06

### Requirement: La rendición exige la entrega y el conteo físico

`JORNADA_RENDIR` v2 DEBE exigir `RENDIR_JORNADA`, ser solo `ONLINE`, aplicarse a una jornada `ABIERTA` y entregada (`JORNADA_ESTADO_INVALIDO`, `JORNADA_SIN_ENTREGA`, 409) y llevar, por producto, la cantidad contada entera y no negativa en unidad base (`CANTIDAD_INVALIDA`) y el esperado que vio quien contó, sin productos repetidos (`PRODUCTO_REPETIDO`), y una observación opcional de hasta 500 caracteres (`OBSERVACION_INVALIDA`). Cada producto con saldo distinto de cero en la ubicación o con algún movimiento en ella durante la jornada DEBE estar (`CONTEO_INCOMPLETO`, 422, con los productos que faltan); un producto activo fuera de ese conjunto PUEDE agregarse con esperado cero. Si un esperado enviado no es el del servidor en la transacción, DEBE rechazarse con `ESPERADO_DIFIERE` (409) con los esperados actuales. Aceptada, la jornada DEBE quedar `EN_RENDICION` con su rendición, una línea por producto del conteo y el momento y el usuario de la rendición. `JORNADA_RENDIR` v1 NO DEBE aceptarse más (`VERSION_DE_COMANDO_SIN_HANDLER`) (`design.md` D2).

#### Scenario: Rendición sin diferencias
- **GIVEN** la jornada entregada de Juan con 40 unidades esperadas de Vino A y 12 de Agua 500 en "Camioneta 1"
- **WHEN** la Supervisora rinde con 40 y 12 contadas
- **THEN** la jornada queda `EN_RENDICION` con su rendición y dos líneas sin diferencia, y no se escribe ningún movimiento
- **Regla:** RUT-06; `01` §18

#### Scenario: Rendición sin la entrega
- **GIVEN** la jornada `ABIERTA` de Juan sin entrega
- **WHEN** la Supervisora envía `JORNADA_RENDIR`
- **THEN** se rechaza con `JORNADA_SIN_ENTREGA` y no se escribe nada
- **Regla:** RUT-05

#### Scenario: Falta contar un producto
- **GIVEN** la jornada entregada con esperado de Vino A y de Agua 500
- **WHEN** la rendición trae solo Vino A
- **THEN** se rechaza con `CONTEO_INCOMPLETO` nombrando Agua 500 y no se escribe nada
- **Regla:** RUT-06; `design.md` D2

#### Scenario: Un producto vendido hasta cero también se cuenta
- **GIVEN** Agua 500 cargada y vendida entera durante la jornada (saldo 0)
- **WHEN** la rendición no la trae
- **THEN** se rechaza con `CONTEO_INCOMPLETO` nombrando Agua 500
- **Regla:** RUT-06

#### Scenario: Sobrante de un producto no esperado
- **GIVEN** la jornada entregada sin movimientos de Agua 1500
- **WHEN** la rendición agrega Agua 1500 con 2 contadas y esperado 0
- **THEN** la línea queda con esperado 0, contado 2 y diferencia +2
- **Regla:** RUT-06

#### Scenario: El esperado cambió mientras se contaba
- **GIVEN** la Supervisora vio 40 esperadas de Vino A y un usuario con `LIBERAR_UBICACION` sacó 6 del vehículo
- **WHEN** envía la rendición con esperado 40
- **THEN** se rechaza con `ESPERADO_DIFIERE` con el esperado actual 34 y no se escribe nada
- **Regla:** RUT-06; STK-04

#### Scenario: Cantidad contada inválida
- **WHEN** la rendición trae una cantidad negativa o con decimales, o un producto repetido
- **THEN** se rechaza con `CANTIDAD_INVALIDA` o `PRODUCTO_REPETIDO` y no se escribe nada
- **Regla:** INV-04

#### Scenario: El vendedor no rinde
- **GIVEN** Juan, Vendedor, sin `RENDIR_JORNADA`
- **WHEN** envía `JORNADA_RENDIR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO`
- **Regla:** RUT-05; `01` §19

#### Scenario: Rendición de otra organización
- **WHEN** un usuario con `RENDIR_JORNADA` rinde una jornada de otra organización
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: La versión sin conteo ya no se acepta
- **WHEN** llega un `JORNADA_RENDIR` v1 nuevo
- **THEN** se rechaza con `VERSION_DE_COMANDO_SIN_HANDLER` y la jornada no cambia
- **Regla:** RUT-06; `design.md` D2

#### Scenario: Reenvío de una rendición v1 ya aceptada
- **GIVEN** una rendición v1 aceptada antes del change 24
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se rechaza con `VERSION_DE_COMANDO_SIN_HANDLER` (el bus resuelve el handler antes de la idempotencia) y no se devuelve el resultado guardado
- **Regla:** RUT-06; `design.md` D2

#### Scenario: Doble envío de la rendición
- **GIVEN** una rendición aceptada
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original sin otra rendición ni otros movimientos
- **Regla:** SYN-02; INV-06

### Requirement: Las diferencias de la rendición quedan en el libro

Por cada producto con diferencia distinta de cero (contado menos esperado) la rendición DEBE escribir un movimiento `DIFERENCIA_RENDICION` con esa cantidad con signo, con origen en la rendición y con la jornada, valorizado al costo promedio vigente sin recalcularlo ni dejar historia de costo; sin promedio, con costo nulo. Un producto inactivo con faltante (diferencia negativa) DEBE aceptarse y registrar su diferencia; con sobrante (diferencia positiva) DEBE rechazarse con `PRODUCTO_INACTIVO`, que exige reactivarlo; con diferencia cero no se escribe movimiento y se acepta (CAT-05; decisión del usuario 2026-11-05). Después de la rendición el stock de cada producto contado en la ubicación DEBE ser lo contado y la suma de sus movimientos. La rendición DEBE registrarse completa o no registrarse (`design.md` D5).

#### Scenario: Faltante
- **GIVEN** 40 unidades esperadas de Vino A con promedio `"1050.000000"`
- **WHEN** se rinden 37 contadas
- **THEN** queda un `DIFERENCIA_RENDICION` de −3 a `"1050.000000"`, el stock de Vino A en "Camioneta 1" es 37 y el promedio no cambia
- **Regla:** RUT-06; CST-12; INV-12

#### Scenario: Sobrante sin promedio
- **GIVEN** un producto sin costo promedio con esperado 0
- **WHEN** se rinden 2 contadas
- **THEN** queda un `DIFERENCIA_RENDICION` de +2 con costo nulo y la rendición se acepta
- **Regla:** RUT-06; CST-12; `design.md` D5

#### Scenario: Sobrante de un producto inactivo
- **GIVEN** un producto inactivo agregado al conteo con 3 contadas
- **WHEN** se envía la rendición
- **THEN** se rechaza con `PRODUCTO_INACTIVO` y no se escribe nada

#### Scenario: Faltante de un producto inactivo
- **GIVEN** un producto inactivo con 5 esperadas y 3 contadas
- **WHEN** se envía la rendición
- **THEN** se acepta, se registra `DIFERENCIA_RENDICION` de -2 y el saldo queda en 3

#### Scenario: Producto inactivo sin diferencia
- **GIVEN** un producto inactivo con 5 esperadas y 5 contadas
- **WHEN** se envía la rendición
- **THEN** se acepta sin movimiento de diferencia
- **Regla:** CAT-05; INV-01

#### Scenario: Falla a mitad de la rendición
- **WHEN** la escritura de la segunda diferencia falla
- **THEN** no queda la rendición, ni sus líneas, ni ningún movimiento, y la jornada sigue `ABIERTA`
- **Regla:** INV-01

#### Scenario: La rendición no se modifica ni se borra
- **WHEN** el usuario de aplicación intenta `UPDATE` o `DELETE` sobre una rendición o una línea de rendición
- **THEN** la base lo rechaza
- **Regla:** INV-05

#### Scenario: El stock cuadra con lo contado
- **GIVEN** cualquier secuencia de cargas, ventas, anulaciones y una rendición registrada contra PostgreSQL real
- **WHEN** se suma con SQL
- **THEN** el stock de cada producto contado es lo contado y es la suma de sus movimientos
- **Regla:** INV-12; RUT-06

### Requirement: El resumen de la jornada cuadra y se congela al rendir

`GET /api/v1/stock/jornadas/{id}/resumen` DEBE leerse con `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION` y calcularse en la base. Por producto DEBE informar, con los movimientos de la ubicación registrados entre la apertura y la rendición: stock al abrir, ingresos (`TRANSFERENCIA_ENTRADA`), ventas, anulaciones, otros, esperado (al abrir + ingresos − ventas + anulaciones + otros), contado y diferencia. Esas columnas DEBEN guardarse con la rendición y no cambiar después. DEBE informar además, por la jornada de cada operación: ventas vigentes (cantidad y total), ventas anuladas (por la jornada de la anulación, aunque la jornada se haya liberado), cobranzas confirmadas por medio de pago y cobranzas anuladas, y aparte lo registrado después de la rendición. El valor de las diferencias DEBE informarse solo con `VER_COSTOS`. Una jornada sin rendición DEBE informar el stock calculado hasta su rendición, cierre o liberación (o hasta ahora si está abierta), sin contado ni diferencias (`design.md` D4, D8).

#### Scenario: El resumen cuadra
- **GIVEN** 10 unidades de Vino A en "Camioneta 1" antes de abrir, una carga de 36, ventas por 8 y una anulación de 2
- **WHEN** se lee el resumen
- **THEN** Vino A muestra al abrir 10, ingresos 36, ventas 8, anulaciones 2, otros 0 y esperado 40
- **Regla:** RUT-07; STK-04

#### Scenario: Cobranzas por medio de pago
- **GIVEN** la jornada con una venta cobrada $30.000 en efectivo y una cobranza a Kiosco La Esquina de $50.000 con $30.000 en efectivo y $20.000 por transferencia
- **WHEN** se lee el resumen
- **THEN** las cobranzas muestran efectivo $60.000 y transferencia $20.000, como string
- **Regla:** RUT-07; COB-01; INV-03

#### Scenario: Anulación de una jornada liberada
- **GIVEN** una anulación sin conexión con la jornada del sobre ya liberada
- **WHEN** se lee el resumen de esa jornada
- **THEN** la venta figura entre las anuladas
- **Regla:** RUT-07; ADR-066

#### Scenario: Cobranza anulada aparte
- **GIVEN** una cobranza de la jornada anulada desde `/admin`
- **WHEN** se lee el resumen
- **THEN** no suma en su medio de pago y figura entre las anuladas
- **Regla:** RUT-07; COB-05

#### Scenario: Lo tardío no cambia el resumen rendido
- **GIVEN** una jornada rendida
- **WHEN** después llega una venta sin conexión de esa jornada
- **THEN** el stock del resumen no cambia y la venta figura aparte como registrada después de la rendición
- **Regla:** RUT-07; `design.md` D4, D7

#### Scenario: Sin permiso de costos
- **GIVEN** un usuario con `RENDIR_JORNADA` y sin `VER_COSTOS`
- **WHEN** lee el resumen
- **THEN** no recibe el valor de las diferencias
- **Regla:** `01` §19

#### Scenario: Jornada sin conteo
- **GIVEN** una jornada `CERRADA` antes de este change y otra `LIBERADA`
- **WHEN** se lee el resumen de cualquiera
- **THEN** informa el stock calculado y el dinero, sin contado ni diferencias
- **Regla:** `01` §18; `design.md` D8

#### Scenario: Resumen de otra organización
- **WHEN** se pide el resumen de una jornada de otra organización
- **THEN** responde 404
- **Regla:** INV-21

### Requirement: El cierre puede devolver el remanente

`JORNADA_CERRAR` v2 DEBE admitir una devolución opcional con un destino activo, distinto de la ubicación de la jornada y sin toma (`UBICACION_INACTIVA`, `UBICACIONES_IGUALES`, `UBICACION_CON_TOMA`) y de 1 a 200 líneas de producto con cantidad entera positiva que no supere el saldo (`LINEAS_INVALIDAS`, `CANTIDAD_INVALIDA`, `STOCK_INSUFICIENTE`, sin excepción por permiso). Con devolución DEBE exigir además `TRANSFERIR_STOCK`. En la misma transacción DEBE escribir una transferencia común, anulable, y cerrar la jornada; si algo falla, nada (`design.md` D6).

#### Scenario: Cerrar devolviendo al depósito
- **GIVEN** la jornada `EN_RENDICION` con 37 de Vino A contadas en "Camioneta 1"
- **WHEN** la Supervisora cierra devolviendo 37 de Vino A al "Depósito central"
- **THEN** queda una transferencia de "Camioneta 1" al depósito por 37, la jornada `CERRADA` y "Camioneta 1" libre
- **Regla:** RUT-08; STK-07; INV-16

#### Scenario: Devolver más de lo que hay
- **WHEN** el cierre intenta devolver 40 de Vino A con saldo 37
- **THEN** se rechaza con `STOCK_INSUFICIENTE`, la jornada sigue `EN_RENDICION` y no queda transferencia
- **Regla:** RUT-08; INV-01

#### Scenario: Destino con toma
- **WHEN** el destino de la devolución es "Camioneta 2"
- **THEN** se rechaza con `UBICACION_CON_TOMA` sin cambios
- **Regla:** STK-09; `design.md` D6

#### Scenario: Devolución sin permiso de transferir
- **GIVEN** un usuario con `RENDIR_JORNADA` y sin `TRANSFERIR_STOCK`
- **WHEN** cierra con devolución
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` sin cambios
- **Regla:** `01` §19

#### Scenario: Cerrar sin devolver
- **WHEN** la Supervisora cierra sin devolución
- **THEN** la jornada queda `CERRADA`, la ubicación libre y el stock del vehículo igual
- **Regla:** RUT-08

#### Scenario: Doble envío del cierre con devolución
- **GIVEN** un cierre con devolución aceptado
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original con una sola transferencia
- **Regla:** SYN-02; INV-06

### Requirement: La rendición se serializa con los movimientos de su ubicación

La rendición y el cierre DEBEN tomar la ubicación de la jornada antes que la jornada y que cualquier saldo, y NO DEBEN tomar `saldo_cuenta`; así, un movimiento concurrente sobre esa ubicación termina antes (y entra en el esperado) o espera y ve la jornada rendida, sin interbloqueo (`design.md` D3).

#### Scenario: Rendición y venta tardía a la vez
- **GIVEN** una rendición y una venta sin conexión de la misma jornada procesándose a la vez, con commits reales
- **WHEN** terminan las dos
- **THEN** no hay interbloqueo: o la venta terminó antes y la rendición la ve en el esperado (con `ESPERADO_DIFIERE` si el esperado enviado no la incluía), o la venta espera, llega con `JORNADA_RENDIDA` y el stock final es lo contado menos esa venta
- **Regla:** INV-01; INV-12; `02` §7.3

#### Scenario: Rendición y liberación a la vez
- **WHEN** una rendición y una liberación de la misma jornada llegan a la vez
- **THEN** no hay interbloqueo: o la liberación gana y la rendición se rechaza con `JORNADA_ESTADO_INVALIDO` sin escribir nada, o la rendición queda completa y la liberación pasa la jornada `EN_RENDICION` a `LIBERADA` sin tocar el stock
- **Regla:** RUT-09; INV-01

### Requirement: La rendición espera a que se resuelvan las operaciones rechazadas de la jornada

`JORNADA_RENDIR` DEBE rechazarse con `RECHAZOS_PENDIENTES` (409, con la cantidad pendiente en el detalle) y sin escribir nada mientras la jornada tenga rechazos sin conexión `PENDIENTE` en el registro de rechazos (cualquier tipo de comando cuyo sobre traía esa jornada). Lo comprueba después de tomar la jornada `FOR UPDATE`, en una consulta aparte, por un puerto que `stock/service.py` declara y `sync/service.py` registra; sin puerto registrado la rendición falla (no se rinde sin comprobar). Los comandos en cuarentena NO DEBEN bloquear la rendición (no tienen jornada en el registro y su teléfono dado de baja no puede entregar el día: RUT-05, RUT-09). La entrega del día (`JORNADA_ENTREGAR`), el cierre y la liberación NO DEBEN bloquearse por los rechazos. `GET /api/v1/stock/jornadas/{id}` DEBE devolver `rechazos_pendientes` (solo la cantidad) a quien puede leer la jornada; la pantalla de conteo y el detalle de la jornada DEBEN mostrar «Esta jornada tiene {N} operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.» (en singular con una) y deshabilitar «Registrar rendición»; el acceso «Ver rechazadas» a la lista filtrada por la jornada se muestra solo con `REVISAR_OBSERVACIONES` (`design.md` D9 = B).

#### Scenario: Rendición con una venta rechazada sin resolver
- **GIVEN** la jornada entregada de Juan con una venta sin conexión rechazada y `PENDIENTE`
- **WHEN** la Supervisora envía la rendición con el conteo completo
- **THEN** se rechaza con `RECHAZOS_PENDIENTES` (409) y la cantidad 1
- **AND** la jornada sigue `ABIERTA`, sin `DIFERENCIA_RENDICION` ni conteo, y el stock del vehículo no cambia
- **Regla:** RUT-05; RUT-06; SYN-06; ADR-069

#### Scenario: Rendición permitida cuando todo está resuelto
- **GIVEN** que la Supervisora cargó con conexión la venta rechazada y resolvió el rechazo vinculándola
- **WHEN** envía la rendición
- **THEN** se acepta; el esperado ya incluye la venta cargada y la mercadería se descuenta una sola vez
- **Regla:** RUT-05; RUT-06; SYN-08

#### Scenario: Resuelto sin vínculo
- **GIVEN** que el rechazo se resolvió sin vínculo («la venta no ocurrió»)
- **WHEN** envía la rendición
- **THEN** se acepta
- **Regla:** RUT-05; SYN-08

#### Scenario: La entrega del día no se bloquea
- **GIVEN** la jornada de Juan con un rechazo `PENDIENTE`
- **WHEN** Juan toca «Terminar el día» y el lote procesa `JORNADA_ENTREGAR`
- **THEN** la entrega se acepta igual
- **Regla:** RUT-05

#### Scenario: Rechazos de otra jornada o en cuarentena
- **GIVEN** rechazos `PENDIENTE` de otra jornada, rechazos sin jornada y comandos en cuarentena del mismo vendedor
- **WHEN** se rinde la jornada de Juan sin rechazos propios pendientes
- **THEN** se acepta
- **Regla:** RUT-05; SYN-06; INV-21

#### Scenario: Pantalla de conteo con rechazos pendientes
- **GIVEN** la jornada entregada con 2 rechazos pendientes
- **WHEN** la Supervisora abre la pantalla de conteo
- **THEN** ve «Esta jornada tiene 2 operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.», «Registrar rendición» deshabilitado y «Ver rechazadas», que abre «Rechazadas» de `/admin/revision` filtrada por la jornada
- **Regla:** RUT-05; SYN-06

#### Scenario: Sin permiso de revisión
- **GIVEN** un rol con `RENDIR_JORNADA` y sin `REVISAR_OBSERVACIONES`
- **WHEN** abre la pantalla de conteo de una jornada con rechazos pendientes
- **THEN** ve el aviso y «Registrar rendición» deshabilitado, con «Las resuelve quien revisa las observaciones.», sin «Ver rechazadas» y sin pedir la lista de rechazos
- **Regla:** `01` §19; SEG-06

#### Scenario: Sin rechazos pendientes
- **GIVEN** que los rechazos de la jornada ya se resolvieron
- **WHEN** abre la pantalla de conteo
- **THEN** no hay aviso y «Registrar rendición» está habilitado
- **Regla:** SYN-08

#### Scenario: Doble envío de una rendición rechazada
- **GIVEN** una rendición rechazada con `RECHAZOS_PENDIENTES`
- **WHEN** después de resolver los rechazos se envía otra vez con el mismo `operation_id`
- **THEN** se procesa de nuevo (el rechazo revirtió la reserva de idempotencia) y se acepta
- **Regla:** SYN-02; INV-06

#### Scenario: Resolución y rendición a la vez
- **WHEN** una persona resuelve el último rechazo de la jornada mientras otra envía la rendición
- **THEN** la rendición se acepta si ve el rechazo ya resuelto, o se rechaza con `RECHAZOS_PENDIENTES` y se puede reintentar; nunca hay interbloqueo
- **Regla:** INV-01; RUT-05
