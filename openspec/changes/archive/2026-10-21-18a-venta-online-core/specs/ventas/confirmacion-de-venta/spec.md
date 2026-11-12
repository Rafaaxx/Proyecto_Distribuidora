## Purpose

Definir la confirmación de una venta por comando: sus datos, sus efectos atómicos en stock, costo, cuenta corriente y cobranza, la numeración por dispositivo, el cliente habilitado, la ubicación y la jornada, y su recepción sin conexión (VTA-01, VTA-05, VTA-06, VTA-08, VTA-10 a VTA-12, CC-05, STK-05, STK-06, SYN-05, INV-01, INV-07, INV-14, INV-17). Escrita con las opciones recomendadas (A) de `design.md` D1, D3 a D5, D10 a D13, D15 y D17, pendientes de aprobación.

## ADDED Requirements

### Requirement: Una venta se confirma por comando con todos sus efectos o con ninguno

El sistema DEBE confirmar una venta con `VENTA_CONFIRMAR` v1 (con `Operation-Id`), que indica el identificador de la venta generado por quien la origina, su número (D4), cliente, ubicación, líneas, lista o versión elegidas con su motivo, cobranza opcional y los valores esperados (`design.md` D2). En una sola transacción DEBE registrar la venta `CONFIRMADA` y sus líneas, un egreso de stock `VENTA` por línea, el costo congelado, un débito `VENTA` por el total en la cuenta del cliente, la cobranza y su crédito si existe, el estado de facturación, las observaciones y la auditoría; si algo falla, no se registra nada (VTA-12, INV-01). Exige `VENDER` (VTA-10). Un identificador de venta ya usado DEBE rechazarse con `VENTA_DUPLICADA`.

#### Scenario: Venta con cobranza parcial
- **GIVEN** Kiosco La Esquina con saldo `"150000.00"`, Vino A con 48 botellas en "Depósito central" y promedio `"1050.000000"`
- **WHEN** se confirma una venta de 15 botellas a $12.500 la caja x6 con `"20000.00"` en efectivo
- **THEN** existe una venta `CONFIRMADA` con total `"31250.00"`; el stock queda en 33; la línea tiene costo unitario `"1050.000000"` y costo total `"15750.00"`; la cuenta tiene un débito `VENTA` de `"31250.00"` y un crédito `COBRANZA` de `"20000.00"`; el saldo es `"161250.00"`
- **Regla:** VTA-12; VTA-05; CC-05; VTA-11; INV-14

#### Scenario: Una falla a mitad no deja nada
- **GIVEN** una falla inyectada después del movimiento de stock, otra después del débito y otra después de la cobranza
- **WHEN** se procesa cada comando
- **THEN** en los tres casos no queda venta, línea, movimiento de stock, cambio de `costo_producto`, movimiento de cuenta, cobranza ni cambio de saldo, y el número sigue libre
- **Regla:** INV-01; VTA-12

#### Scenario: Doble envío
- **GIVEN** una venta aceptada
- **WHEN** se reenvía el mismo comando con el mismo contenido, y después con el mismo `operation_id` y otra cantidad
- **THEN** el primer reenvío devuelve el resultado original sin duplicar ningún efecto; el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

#### Scenario: Identificador de venta repetido
- **WHEN** llega otro comando, con otro `operation_id`, con el identificador de una venta existente
- **THEN** se rechaza con `VENTA_DUPLICADA` y la venta original no cambia
- **Regla:** `02` §9; SYN-06

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `VENDER`
- **WHEN** envía `VENTA_CONFIRMAR` con conexión
- **THEN** recibe 403 y no queda ningún efecto
- **Regla:** VTA-10; SEG-06

#### Scenario: Organización tomada del token
- **WHEN** el contenido trae un `organizacion_id` o un cliente de otra organización
- **THEN** el campo se ignora o el cliente responde como inexistente (404)
- **Regla:** INV-21; SEG-07

### Requirement: El total de la venta es la suma de netos más la suma de IVA

La venta DEBE guardar `total_neto`, `total_iva` y `total` con `total = total_neto + total_iva`, `total_neto` igual a la suma de los netos de sus líneas y `total_iva` igual a la suma de sus IVA (INV-14). En modo `A` el IVA es cero. La base DEBE rechazar una cabecera con `total ≠ total_neto + total_iva` y una línea con `neto ≠ bruto − descuento`.

#### Scenario: Totales de cabecera y líneas
- **WHEN** se confirma una venta de dos líneas con brutos `"25000.00"` y `"6250.00"`
- **THEN** `total_neto` es `"31250.00"`, `total_iva` `"0.00"`, `total` `"31250.00"` y la suma con SQL de los netos de sus líneas coincide
- **Regla:** INV-14; VTA-04

#### Scenario: La base impide un total incoherente
- **WHEN** se inserta por SQL una venta con `total_neto = 100.00`, `total_iva = 0.00` y `total = 99.00`
- **THEN** la base la rechaza
- **Regla:** INV-14

### Requirement: Solo se vende en modo impositivo A

Si la organización tiene modo `B` o `C`, la venta DEBE rechazarse con `MODO_IMPOSITIVO_NO_SOPORTADO` (409). La venta DEBE congelar `modo_impositivo = 'A'` y cada línea la alícuota del producto con IVA cero. La venta NO DEBE leer la modalidad de IVA de la organización (`design.md` D13, ADR-045).

#### Scenario: Organización monotributista
- **GIVEN** una organización `MONOTRIBUTO`, modo `A`, modalidad de IVA nula, y Vino A con alícuota 21 %
- **WHEN** se confirma una venta de Vino A
- **THEN** se acepta; la línea guarda alícuota `"0.210000"` e IVA `"0.00"`
- **Regla:** VTA-04; CST-06; ADR-045

#### Scenario: Modo B
- **GIVEN** una organización responsable inscripta con modo `B`
- **WHEN** se confirma una venta
- **THEN** se rechaza con `MODO_IMPOSITIVO_NO_SOPORTADO` sin ningún efecto
- **Regla:** VTA-04 (B: etapa 4)

### Requirement: El costo de cada línea se congela al promedio vigente

Cada línea DEBE congelar `costo_unitario` igual al costo promedio vigente del producto al procesar la venta y `costo_total = costo_unitario × cantidad base` redondeado a 2 decimales (VTA-05, CST-14); el promedio no cambia (CST-12). Con conexión, un producto sin promedio DEBE rechazarse con `PRODUCTO_SIN_COSTO` (409), aun con `PERMITIR_STOCK_NEGATIVO`; sin conexión DEBE aceptarse con costo nulo y la observación `VENTA_SIN_COSTO` por línea (`design.md` D10).

#### Scenario: Costo congelado del ejemplo de CST-11
- **GIVEN** Vino A con 120 botellas y promedio `"1050.000000"`
- **WHEN** se venden 72
- **THEN** la línea congela `"1050.000000"` y `"75600.00"`; el promedio sigue `"1050.000000"` y el stock total queda en 48
- **Regla:** VTA-05; CST-11; CST-12

#### Scenario: Una compra posterior no cambia el costo congelado
- **GIVEN** la venta anterior
- **WHEN** se compran 60 botellas a $1.200
- **THEN** el promedio pasa a `"1133.333333"` y la línea vendida sigue con `"75600.00"`
- **Regla:** INV-10; CST-11

#### Scenario: Producto sin costo con conexión
- **GIVEN** Vino C sin ingresos con costo y un usuario con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** se confirma una venta de 3 botellas con conexión
- **THEN** se rechaza con `PRODUCTO_SIN_COSTO` y el detalle nombra el producto
- **Regla:** ADR-039; `design.md` D10

#### Scenario: Producto sin costo sin conexión
- **WHEN** la misma venta llega por el lote en modo `OFFLINE`
- **THEN** se acepta con costo nulo en la línea y la observación `VENTA_SIN_COSTO` con producto y línea
- **Regla:** SYN-05; INV-17; `design.md` D10

### Requirement: Una venta que deja stock negativo se rechaza salvo permiso

Con conexión, una línea que deja el saldo de la ubicación por debajo de cero DEBE rechazar la venta con `STOCK_INSUFICIENTE` (409, con producto y ubicación) salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`; con el permiso, la venta DEBE aceptarse con una observación `STOCK_NEGATIVO` por línea afectada (producto, ubicación, saldo resultante). Sin conexión DEBE aceptarse siempre con `STOCK_NEGATIVO` (STK-05, STK-06). El costo es el promedio vigente también sobre saldo negativo (`design.md` D11).

#### Scenario: Sin permiso
- **GIVEN** Vino A con 48 botellas en la ubicación
- **WHEN** un Vendedor sin el permiso vende 50
- **THEN** se rechaza con `STOCK_INSUFICIENTE` sin ningún efecto
- **Regla:** STK-05; INV-01

#### Scenario: Con permiso
- **GIVEN** el mismo stock y promedio `"1050.000000"`
- **WHEN** un Administrador con `PERMITIR_STOCK_NEGATIVO` vende 50
- **THEN** se acepta con `STOCK_NEGATIVO` (saldo −2), costo total `"52500.00"`, y el comando queda `ACEPTADO_CON_OBSERVACIONES`
- **Regla:** STK-05; VTA-05; SYN-07

#### Scenario: Sin conexión
- **WHEN** la venta de 50 llega por el lote en modo `OFFLINE` de un Vendedor sin el permiso
- **THEN** se acepta con `STOCK_NEGATIVO`
- **Regla:** STK-06; SYN-05; INV-17

### Requirement: La venta va a la ubicación de la jornada del vendedor o a la que se elige

Con conexión, si el usuario y el dispositivo tienen una jornada `ABIERTA`, la venta DEBE ir a la ubicación de esa jornada y llevarla; una ubicación distinta en el contenido DEBE rechazarse con `JORNADA_AJENA` (409). Si no tienen jornada abierta, la venta DEBE ir a la ubicación activa elegida y quedar sin jornada; STK-09 rige igual (`UBICACION_TOMADA`, 409). Sin conexión, la venta lleva la jornada del sobre y la ubicación de esa jornada, e ignora la `ubicacion_id` del contenido (`design.md` D3, RUT-04); si esa ubicación está tomada al sincronizar (la propia jornada en `EN_RENDICION`, o la de otro vendedor tras una liberación), la venta NO DEBE rechazarse: DEBE aceptarse con `UBICACION_TOMADA_AL_SINCRONIZAR` y la constancia de la jornada en la auditoría (SYN-05, INV-17, STK-09; aprobado por el usuario el 2026-10-20).

#### Scenario: Vendedor con jornada abierta
- **GIVEN** Juan con la jornada abierta en la camioneta 2 desde su teléfono
- **WHEN** confirma una venta con conexión sin indicar ubicación
- **THEN** el stock baja en la camioneta 2 y la venta y su movimiento llevan esa jornada
- **Regla:** RUT-04; STK-09

#### Scenario: Venta desde la oficina
- **GIVEN** Ana sin jornada
- **WHEN** confirma una venta desde "Depósito central"
- **THEN** la venta queda sin jornada y el stock baja en el depósito
- **Regla:** VTA-01; `03` §12

#### Scenario: Ubicación tomada por otra jornada
- **GIVEN** la camioneta 2 tomada por la jornada de Juan
- **WHEN** Ana, sin `LIBERAR_UBICACION`, vende desde la camioneta 2
- **THEN** se rechaza con `UBICACION_TOMADA`
- **Regla:** STK-09

#### Scenario: Ubicación tomada al sincronizar una venta sin conexión
- **GIVEN** la jornada de Juan en `EN_RENDICION` (o liberada y la camioneta 2 tomada por la jornada de Ana)
- **WHEN** llega su venta sin conexión, aunque no tenga `LIBERAR_UBICACION`
- **THEN** se acepta, el stock baja, la venta conserva la jornada del sobre y lleva `UBICACION_TOMADA_AL_SINCRONIZAR` (y `JORNADA_LIBERADA` si corresponde); la auditoría deja `ubicación tomada por la jornada <id>`
- **Regla:** SYN-05; SYN-07; INV-17; STK-09; RUT-09

#### Scenario: Ubicación distinta de la jornada
- **WHEN** Juan, con su jornada abierta, envía la venta con "Depósito central"
- **THEN** se rechaza con `JORNADA_AJENA`
- **Regla:** RUT-04; `design.md` D3

### Requirement: El cliente debe estar habilitado

Con conexión, un cliente `SUSPENDIDO` DEBE requerir `VENDER_CLIENTE_SUSPENDIDO` (`CLIENTE_SUSPENDIDO`, 409) y a un cliente `INACTIVO` NO DEBE vendérsele (`CLIENTE_INACTIVO`, 409). Al consumidor final DEBE vendérsele solo de contado: la cobranza en el acto igual al total (`CONSUMIDOR_FINAL_CONTADO`, 422). Sin conexión nada DEBE rechazarse: el cliente suspendido sin el permiso o inactivo DEBE aceptarse con `CLIENTE_NO_HABILITADO` y el consumidor final con una cobranza distinta del total, con `CONSUMIDOR_FINAL_CON_DEUDA` (si el cliente además no está habilitado, solo `CLIENTE_NO_HABILITADO`) (CLI-02, CLI-03, SYN-05, `design.md` D5, decisión del usuario del 2026-10-19).

#### Scenario: Suspendido sin permiso
- **WHEN** un Vendedor vende a un cliente suspendido
- **THEN** se rechaza con `CLIENTE_SUSPENDIDO`
- **Regla:** CLI-02

#### Scenario: Suspendido con permiso
- **WHEN** un Supervisor con `VENDER_CLIENTE_SUSPENDIDO` vende al mismo cliente
- **THEN** se acepta
- **Regla:** CLI-02

#### Scenario: Inactivo
- **WHEN** cualquier usuario vende a un cliente inactivo con conexión
- **THEN** se rechaza con `CLIENTE_INACTIVO`
- **Regla:** CLI-02

#### Scenario: Consumidor final de contado
- **WHEN** se vende $4.300,00 al consumidor final con `"4300.00"` en efectivo, y otra con `"4000.00"`
- **THEN** la primera se acepta y su saldo queda en `"0.00"`; la segunda se rechaza con `CONSUMIDOR_FINAL_CONTADO`
- **Regla:** CLI-03; CC-08; `design.md` D5

#### Scenario: Cliente no habilitado sin conexión
- **WHEN** una venta a un cliente inactivo llega por el lote en modo `OFFLINE`
- **THEN** se acepta con `CLIENTE_NO_HABILITADO`
- **Regla:** SYN-05; INV-17

#### Scenario: Consumidor final con deuda sin conexión
- **WHEN** llega por el lote en modo `OFFLINE` una venta de $4.300,00 al consumidor final con $4.000,00 en efectivo (o sin cobranza)
- **THEN** se acepta con la observación `CONSUMIDOR_FINAL_CON_DEUDA` (y no con `CLIENTE_NO_HABILITADO`); la venta y la cobranza quedan como las envió el dispositivo
- **Regla:** CLI-03; SYN-05; SYN-07; INV-17

### Requirement: La cobranza en el acto registra su propio crédito

La venta DEBE admitir a lo sumo una cobranza, con su identificador, de 1 a 20 medios y observación opcional; su importe es la suma de los medios (INV-08) y puede ser parcial, total o superior al total (VTA-11). DEBE registrarse con origen `VENTA`, la venta, el mismo momento, jornada y dispositivo, después del débito `VENTA` (CC-05). Con conexión, un medio inactivo o una referencia faltante DEBEN rechazar la venta (`MEDIO_PAGO_INACTIVO`, `REFERENCIA_OBLIGATORIA`); sin conexión se aceptan con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (SYN-07).

#### Scenario: Ejemplo de `01` §9.2
- **GIVEN** un cliente con saldo `"150000.00"`
- **WHEN** se confirma una venta de `"80000.00"` con `"20000.00"` en efectivo
- **THEN** la cuenta tiene el débito `VENTA` de `"80000.00"` antes del crédito `COBRANZA` de `"20000.00"` y el saldo es `"210000.00"`
- **Regla:** CRE-02; CC-05; VTA-11

#### Scenario: Cobranza superior al total
- **GIVEN** un cliente con saldo `"10000.00"`
- **WHEN** se vende `"31250.00"` y paga `"50000.00"`
- **THEN** se acepta y el saldo queda en `"-8750.00"` (a favor del cliente)
- **Regla:** VTA-11; CC-04

#### Scenario: Sin cobranza
- **WHEN** se vende `"31250.00"` sin cobranza
- **THEN** solo hay débito y no existe cobranza de esa venta
- **Regla:** VTA-11

#### Scenario: Medios que no suman
- **WHEN** la cobranza trae medios inválidos (lista vacía o 21 medios, o importe con tres decimales)
- **THEN** se rechaza sin ningún efecto (`MEDIOS_INVALIDOS` o `IMPORTE_INVALIDO`)
- **Regla:** INV-08; COB-02

#### Scenario: Referencia faltante con conexión
- **WHEN** la cobranza paga por transferencia sin referencia
- **THEN** se rechaza con `REFERENCIA_OBLIGATORIA` y no queda la venta
- **Regla:** COB-02; INV-01

### Requirement: El número de la nota es el prefijo del dispositivo y su correlativo

La venta DEBE traer su número con el prefijo del dispositivo de la sesión y un correlativo de seis dígitos (`V03-000142`); un prefijo ajeno o un formato inválido DEBEN rechazarse con `NUMERO_INVALIDO` (422) y un número ya usado en la organización con `NUMERO_DUPLICADO` (409) con conexión. Al confirmar, `ultimo_correlativo` del dispositivo DEBE pasar al mayor entre el actual y el de la venta, sin retroceder nunca (VTA-06, ADR-008, `design.md` D4).

#### Scenario: Número aceptado
- **GIVEN** el dispositivo `V01` con último correlativo 41
- **WHEN** se confirma la venta `V01-000042`
- **THEN** se acepta y el último correlativo pasa a 42
- **Regla:** VTA-06

#### Scenario: Número repetido
- **WHEN** otra venta llega con `V01-000042`
- **THEN** se rechaza con `NUMERO_DUPLICADO` y no queda ningún efecto
- **Regla:** VTA-06; INV-01

#### Scenario: Prefijo de otro dispositivo
- **WHEN** el dispositivo `V01` envía `V02-000001`
- **THEN** se rechaza con `NUMERO_INVALIDO`
- **Regla:** VTA-06; SEG-02

#### Scenario: Un número menor no retrocede el correlativo
- **GIVEN** el último correlativo 50
- **WHEN** llega sin conexión la venta `V01-000045`, nunca usada
- **THEN** se acepta y el último correlativo sigue en 50
- **Regla:** VTA-06; INV-17; `design.md` D4

#### Scenario: Dos ventas simultáneas con el mismo número
- **WHEN** dos transacciones confirman a la vez `V01-000043`
- **THEN** una se acepta y la otra se rechaza con `NUMERO_DUPLICADO`, sin efectos
- **Regla:** VTA-06; INV-01

### Requirement: El estado de facturación inicial sale del cliente o de la organización

La venta DEBE nacer con el estado de facturación del cliente o, si es nulo, el de la organización, e `importe_facturado = 0` (VTA-08, FAC-09).

#### Scenario: Estado del cliente y de la organización
- **GIVEN** la organización con `NO_REQUIERE`, Kiosco La Esquina con `PENDIENTE` y Almacén Don Pedro sin estado propio
- **WHEN** se vende a cada uno
- **THEN** la primera venta nace `PENDIENTE` y la segunda `NO_REQUIERE`
- **Regla:** VTA-08

### Requirement: La venta confirmada deja una sola fila de auditoría del comando

El sistema DEBE dejar, por cada `VENTA_CONFIRMAR` aceptado, una única fila de auditoría del bus, sin fila propia de la entidad. Si la venta usó otra lista que la del cliente o una versión no vigente, la fila DEBE llevar el motivo de la lista y una observación que nombre la lista y la versión. Si la venta movió el stock de una ubicación tomada por otra jornada (excepción de `LIBERAR_UBICACION`), la fila DEBE llevar además la constancia `ubicación tomada por la jornada <id>`; con ambos casos, los dos textos van en la misma observación, separados por `; `. Un comando rechazado NO DEBE dejar motivo ni observación de venta (AUD-01, AUD-02, STK-09, SYN-04, `design.md` D20).

#### Scenario: Venta común
- **WHEN** Juan confirma una venta con la lista y la versión vigente del cliente, desde su propia jornada
- **THEN** la fila de auditoría no lleva motivo ni observación
- **Regla:** AUD-01; ADR-022

#### Scenario: Otra lista o versión anterior
- **WHEN** un Supervisor confirma una venta con la versión 1 de "General" cuando la vigente es la 2, con un motivo
- **THEN** la fila lleva ese motivo y una observación con la lista "General" y la versión 1
- **Regla:** AUD-01; AUD-02; PRC-21

#### Scenario: Ubicación tomada por otra jornada
- **GIVEN** la camioneta 2 tomada por la jornada de Juan
- **WHEN** una Supervisora con `LIBERAR_UBICACION` vende desde la camioneta 2
- **THEN** la fila lleva la observación `ubicación tomada por la jornada <id de Juan>` y el movimiento queda sin jornada
- **Regla:** STK-09; AUD-02

#### Scenario: Las dos cosas a la vez
- **WHEN** la misma venta usa una versión anterior y sale de una ubicación tomada
- **THEN** la observación de la fila lleva el texto de la lista y el de la ubicación tomada, separados por `; `
- **Regla:** AUD-02; STK-09

#### Scenario: Venta rechazada
- **WHEN** una venta se rechaza (por ejemplo, `STOCK_INSUFICIENTE`)
- **THEN** no queda fila de venta ni motivo; solo la fila del comando rechazado
- **Regla:** AUD-01; SYN-04

### Requirement: Una venta sin conexión nunca se rechaza por reglas de negocio

`VENTA_CONFIRMAR` DEBE admitir modo `OFFLINE` por el lote con `permiso_offline = VENDER`. Sin conexión, la venta DEBE congelar la versión, el precio y las unidades de referencia que envió el dispositivo y solo DEBE rechazarse si está malformada (esquema, INV-07, medios que no suman, totales que no coinciden con el cálculo sobre los valores enviados: `TOTALES_INCONSISTENTES`), si nombra algo inexistente o si es inconsistente (número repetido); stock, cliente, lista, permiso, costo, medio y referencia producen observaciones (SYN-05, SYN-06, INV-17, `design.md` D1). `LISTA_NO_VIGENTE` DEBE emitirse una vez por venta cuando la versión enviada no es la vigente al momento para la lista aplicable.

#### Scenario: Venta con lista no vigente
- **GIVEN** el teléfono de Juan con la versión 3 bajada y la versión 4 publicada después
- **WHEN** llega su venta sin conexión con los precios de la versión 3
- **THEN** se acepta con los precios de la versión 3 y la observación `LISTA_NO_VIGENTE` (versión enviada 3, vigente 4)
- **Regla:** SYN-05; SYN-07; PRC-23

#### Scenario: Motivo y versiones sin conexión
- **WHEN** llega sin conexión una venta con un motivo de lista inactivo
- **THEN** se acepta; con un motivo de otro ámbito se rechaza con `MOTIVO_INVALIDO`, y con líneas de versiones distintas (o distintas de la de la cabecera), con `VERSION_NO_PERMITIDA`
- **Regla:** PRC-21; PRC-23; SYN-05; SYN-06

#### Scenario: Varias observaciones en una venta
- **WHEN** llega sin conexión una venta que deja stock negativo, a un cliente suspendido, de un vendedor al que le quitaron `VENDER`
- **THEN** se acepta con `STOCK_NEGATIVO`, `CLIENTE_NO_HABILITADO` y `PERMISO_REVOCADO`
- **Regla:** SYN-05; SYN-10; INV-17

#### Scenario: Totales incoherentes
- **WHEN** llega sin conexión una venta cuyo bruto enviado no es `precio × cantidad base / unidades` redondeado
- **THEN** se rechaza con `TOTALES_INCONSISTENTES` y no queda ningún efecto
- **Regla:** SYN-06; ADR-016

#### Scenario: Doble envío sin conexión
- **WHEN** el lote reenvía la misma venta aceptada con observaciones
- **THEN** devuelve el resultado original con las mismas observaciones y sin duplicar efectos
- **Regla:** INV-06; SYN-02

#### Scenario: Con conexión no cambia
- **WHEN** la misma venta con stock insuficiente llega por REST o por el lote en modo `ONLINE`
- **THEN** se rechaza con `STOCK_INSUFICIENTE`
- **Regla:** STK-05; SYN-05
