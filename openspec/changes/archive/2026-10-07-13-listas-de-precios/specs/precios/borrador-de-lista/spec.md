## Purpose

Definir la generación de la versión borrador de una lista a partir de los costos informados vigentes, las reglas de margen y el redondeo, la conservación de los precios manuales y las señales que acompañan a cada precio (PRC-17, PRC-16). Escrita con la opción A de `design.md` D2, D3, D4, D5, D7, D12 y D14, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## ADDED Requirements

### Requirement: El borrador de una lista se genera por comando

El sistema DEBE generar el borrador de una lista activa con `LISTA_GENERAR_BORRADOR` (solo `ONLINE`, con `Operation-Id`, permiso `GESTIONAR_LISTAS`). Para cada producto activo de la organización DEBE calcular su precio según `precios/calculo-de-precios`, con el costo informado vigente a la fecha de negocio de la generación, la regla de margen aplicable y el redondeo aplicable (PRC-17, `design.md` D4). El borrador queda en estado `BORRADOR`, sin vigencia, con el número siguiente de la lista y la referencia a su versión base: la versión `PUBLICADA` no anulada de mayor vigencia desde de la lista, si existe. El resultado DEBE informar cuántos precios tiene el borrador y la lista de productos sin precio con su causa. Informar un costo NO DEBE generar ni modificar ningún borrador por sí solo. Una lista inactiva DEBE rechazarse con `LISTA_INACTIVA`; una lista ajena, con 404.

#### Scenario: Primer borrador de una lista
- **GIVEN** la lista `General` sin versiones, con regla de lista `MARGEN_BRUTO` `"0.300000"` y redondeo `"100.00"` `ARRIBA`, y Vino A con costo base vigente `"1000.000000"` y referencia `Caja x6`
- **WHEN** un usuario con `GESTIONAR_LISTAS` envía `LISTA_GENERAR_BORRADOR`
- **THEN** el comando queda `ACEPTADO`, existe la versión n.º 1 en `BORRADOR`, sin vigencia ni versión base, con Vino A a `"8600.00"`
- **Regla:** PRC-17; PRC-02; `01` §7.2 (ejemplo)

#### Scenario: Un costo nuevo cambia el precio en el borrador
- **GIVEN** la versión vigente de `General` con Vino A a `"8600.00"` y, después, un costo informado de Vino A con costo base `"1100.000000"` vigente desde hoy
- **WHEN** se genera el borrador
- **THEN** Vino A queda en el borrador a `"9500.00"`, con costo de referencia `"6600.000000"`, marcado como que cambia respecto de la versión base, y la versión vigente sigue con `"8600.00"`
- **Regla:** PRC-17; PRC-11; PRC-04; `00` §9 (criterio 3)

#### Scenario: Un producto sin cambios queda igual
- **GIVEN** la versión vigente con Cerveza B a `"31200.00"` y ningún cambio en su costo, sus reglas ni su redondeo
- **WHEN** se genera el borrador
- **THEN** Cerveza B queda en el borrador a `"31200.00"`, marcada como igual a la versión base
- **Regla:** PRC-17 (copia la versión vigente)

#### Scenario: Un cambio de regla también llega al borrador
- **GIVEN** la versión vigente con Cerveza B a `"31200.00"` (costo de referencia `"21780.000000"`, margen bruto `"0.300000"`) y la regla modificada después a `"0.350000"`
- **WHEN** se genera el borrador
- **THEN** Cerveza B queda a `"33600.00"`, marcada como que cambia
- **Regla:** PRC-17; PRC-12; `design.md` D4

#### Scenario: Informar un costo no genera un borrador
- **GIVEN** la lista `General` sin borrador
- **WHEN** se registra un costo informado nuevo de Vino A
- **THEN** la lista sigue sin borrador
- **Regla:** `02` §6.5 (`LISTA_GENERAR_BORRADOR`); `design.md` D4

#### Scenario: Sin permiso
- **WHEN** un usuario con `PUBLICAR_LISTAS` y sin `GESTIONAR_LISTAS` envía `LISTA_GENERAR_BORRADOR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se crea ningún borrador
- **Regla:** `01` §19 (`GESTIONAR_LISTAS`: borradores); SEG-06

#### Scenario: Lista inactiva
- **WHEN** se envía `LISTA_GENERAR_BORRADOR` sobre una lista inactiva
- **THEN** se rechaza con `LISTA_INACTIVA`
- **Regla:** PRC-01; `design.md` D4

#### Scenario: Lista de otra organización
- **WHEN** un usuario de A envía `LISTA_GENERAR_BORRADOR` sobre una lista de B
- **THEN** la respuesta es 404 y la lista de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío
- **GIVEN** un `LISTA_GENERAR_BORRADOR` aceptado con `operation_id` X
- **WHEN** se reenvía con X y el mismo contenido
- **THEN** se devuelve el resultado original y la lista sigue con un solo borrador
- **Regla:** INV-06; SYN-02

#### Scenario: Solo con conexión
- **WHEN** llega `LISTA_GENERAR_BORRADOR` en modo `OFFLINE`
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

#### Scenario: La generación es atómica
- **GIVEN** una falla inyectada después de escribir parte de los precios del borrador
- **WHEN** se procesa `LISTA_GENERAR_BORRADOR`
- **THEN** no queda ningún borrador ni ningún precio de esa operación
- **Regla:** INV-01

### Requirement: Un producto que no puede calcularse queda sin precio y se informa

Un producto activo sin costo informado vigente (`SIN_COSTO`), sin regla de margen aplicable (`SIN_REGLA`) o cuyo redondeo da cero (`PRECIO_NO_POSITIVO`) NO DEBE recibir un precio calculado: el borrador no lo incluye y el resultado de la generación y la consulta del borrador DEBEN listarlo con su causa (`design.md` D4). Un producto inactivo NO DEBE entrar en el borrador.

#### Scenario: Producto sin costo
- **GIVEN** el producto Gaseosa C activo, sin ningún costo informado
- **WHEN** se genera el borrador
- **THEN** el borrador no tiene precio de Gaseosa C y el resultado la lista con la causa `SIN_COSTO`
- **Regla:** PRC-11; CST-03; `design.md` D4

#### Scenario: Producto sin regla aplicable
- **GIVEN** una lista con una sola regla, de categoría `Vinos`, y Cerveza B de categoría `Cervezas` con costo vigente
- **WHEN** se genera el borrador
- **THEN** el borrador no tiene precio de Cerveza B y el resultado la lista con la causa `SIN_REGLA`
- **Regla:** PRC-13; `design.md` D4

#### Scenario: Producto sin presentación de referencia
- **GIVEN** un producto activo sin presentación de referencia, aunque tenga costo vigente y una regla aplicable
- **WHEN** se genera el borrador
- **THEN** el borrador no tiene precio del producto y el resultado y la lectura del borrador lo listan como producto sin precio con la causa `SIN_PRESENTACION_DE_REFERENCIA`
- **Regla:** PRC-17; PRC-10; `design.md` D4 (adición aprobada el 2026-10-06)

#### Scenario: Producto inactivo
- **GIVEN** un producto inactivo con costo vigente y precio en la versión base
- **WHEN** se genera el borrador
- **THEN** el borrador no lo incluye
- **Regla:** CAT-05

### Requirement: Una lista tiene como máximo un borrador, que se regenera

Una lista NO DEBE tener más de un borrador, tampoco ante generaciones simultáneas. Si la lista ya tiene un borrador, `LISTA_GENERAR_BORRADOR` DEBE recalcular sus precios sobre el mismo borrador, conservando su número y los precios manuales fijados en él (`design.md` D5). Un borrador NO DEBE borrarse.

#### Scenario: Regenerar el borrador
- **GIVEN** el borrador n.º 4 de `General` con Vino A a `"8600.00"` y, después, un costo nuevo de Vino A con costo base `"1100.000000"`
- **WHEN** se envía de nuevo `LISTA_GENERAR_BORRADOR`
- **THEN** la lista sigue con un solo borrador, el n.º 4, y Vino A queda a `"9500.00"`
- **Regla:** PRC-17; `design.md` D5

#### Scenario: Dos generaciones simultáneas
- **GIVEN** la lista `General` sin borrador
- **WHEN** dos transacciones con commits reales envían al mismo tiempo `LISTA_GENERAR_BORRADOR` con distinto `operation_id`
- **THEN** al terminar ambas la lista tiene exactamente un borrador, con un solo precio por producto
- **Regla:** PRC-10; `design.md` D5 y D14

### Requirement: El precio de un producto puede fijarse a mano en el borrador

El sistema DEBE permitir fijar el precio final de un producto activo en un borrador con `LISTA_BORRADOR_PRECIO_FIJAR` (`GESTIONAR_LISTAS`): un importe mayor que cero con hasta dos decimales, enviado como string, que queda marcado como manual y al que NO DEBE aplicarse el redondeo de la lista (`design.md` D7). Un importe no positivo, con más de dos decimales o que no es un decimal exacto DEBE rechazarse con `IMPORTE_INVALIDO`. El precio manual DEBE guardar el costo de referencia, la regla aplicable y el precio calculado sin redondear de ese momento, o nulos si el producto no tiene costo o regla (PRC-16). El mismo comando DEBE permitir quitar la marca manual: el precio vuelve a calcularse, y si no puede calcularse el producto queda sin precio. Sobre una versión que no está en `BORRADOR` el comando DEBE rechazarse con `VERSION_NO_ES_BORRADOR`; sobre un producto inactivo, con `PRODUCTO_INACTIVO`.

#### Scenario: Fijar un precio manual
- **GIVEN** el borrador de `General` con Vino A calculado a `"8600.00"` (costo de referencia `"6000.000000"`, margen bruto `"0.300000"`)
- **WHEN** se envía `LISTA_BORRADOR_PRECIO_FIJAR` para Vino A con `"9000.00"`
- **THEN** Vino A queda a `"9000.00"` con `manual = true`, costo de referencia `"6000.000000"` y precio calculado `"8571.428571"`
- **Regla:** PRC-16; `design.md` D7

#### Scenario: El precio manual no se redondea
- **GIVEN** una lista con redondeo `"100.00"` `ARRIBA`
- **WHEN** se fija a mano `"8990.00"`
- **THEN** el precio final es `"8990.00"`
- **Regla:** PRC-16; `design.md` D7

#### Scenario: Precio manual de un producto sin costo
- **GIVEN** Gaseosa C sin costo informado y, por eso, sin precio en el borrador
- **WHEN** se le fija a mano `"12000.00"`
- **THEN** el borrador tiene Gaseosa C a `"12000.00"`, manual, con costo de referencia, regla y precio calculado en nulo y con las unidades de su referencia guardadas
- **Regla:** PRC-16; `design.md` D7

#### Scenario: Importe inválido
- **WHEN** se fija a mano `"0.00"`, `"-10.00"` o `"8600.005"`
- **THEN** se rechaza con `IMPORTE_INVALIDO` y el precio no cambia
- **Regla:** TR-01; INV-03

#### Scenario: Quitar la marca manual
- **GIVEN** Vino A manual a `"9000.00"` en el borrador, con costo de referencia `"6000.000000"` y margen bruto `"0.300000"`
- **WHEN** se envía `LISTA_BORRADOR_PRECIO_FIJAR` quitando la marca manual
- **THEN** Vino A vuelve a `"8600.00"` con `manual = false`
- **Regla:** PRC-16; PRC-17; `design.md` D7

#### Scenario: Fijar un precio en una versión publicada
- **GIVEN** una versión `PUBLICADA`
- **WHEN** se envía `LISTA_BORRADOR_PRECIO_FIJAR` sobre ella
- **THEN** se rechaza con `VERSION_NO_ES_BORRADOR` y ningún precio de la versión cambia
- **Regla:** INV-11; PRC-04

#### Scenario: Sin permiso
- **WHEN** un usuario sin `GESTIONAR_LISTAS` envía `LISTA_BORRADOR_PRECIO_FIJAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06

### Requirement: Los precios manuales se conservan y se señalan si su margen es menor que el de la regla

Al generar o regenerar un borrador, los precios manuales de la versión base y los fijados en el propio borrador DEBEN conservarse con su precio final, actualizando el costo de referencia, la regla aplicable y el precio calculado que se guardan con ellos (PRC-17). Un precio manual DEBE señalarse como de margen menor que el de la regla cuando su precio final es menor que el precio calculado sin redondear con la regla aplicable; sin costo o sin regla no hay esa señal, y el precio DEBE señalarse como sin costo (`design.md` D7).

#### Scenario: El manual se conserva al llegar un costo nuevo
- **GIVEN** la versión vigente con Vino A manual a `"9000.00"` y un costo nuevo con costo base `"1100.000000"`
- **WHEN** se genera el borrador
- **THEN** Vino A sigue a `"9000.00"` y manual, con costo de referencia `"6600.000000"` y precio calculado `"9428.571429"`
- **Regla:** PRC-17

#### Scenario: Señal de margen menor que el de la regla
- **GIVEN** el caso anterior, con regla aplicable de margen bruto `"0.300000"`
- **WHEN** se consulta el borrador
- **THEN** Vino A lleva la señal de margen menor que el de la regla, porque `"9000.00"` es menor que `"9428.571429"`
- **Regla:** PRC-17

#### Scenario: Manual con margen suficiente
- **GIVEN** Vino A manual a `"9000.00"` con costo de referencia `"6000.000000"` y margen bruto `"0.300000"` (calculado `"8571.428571"`)
- **WHEN** se consulta el borrador
- **THEN** Vino A no lleva la señal de margen
- **Regla:** PRC-17

#### Scenario: Manual fijado en el borrador y regenerado
- **GIVEN** el borrador n.º 4 con Vino A fijado a mano en `"9000.00"`
- **WHEN** se regenera el borrador
- **THEN** Vino A sigue a `"9000.00"` y manual
- **Regla:** PRC-17; `design.md` D5

### Requirement: El borrador señala los costos que requieren atención

Cada precio del borrador calculado con un costo informado registrado con una regla de IVA distinta de la actual de la organización DEBE llevar la señal de costo con otra regla de IVA, y el resultado de la generación DEBE informar cuántos son; la generación y la publicación NO DEBEN bloquearse por ello (CST-06, `design.md` D3). Cada precio cuyo producto tiene costos informados vigentes por presentación con distinto costo por unidad base DEBE llevar la señal de costos distintos por presentación, e informar de qué presentación salió el costo usado (`design.md` D2).

#### Scenario: Costo calculado con la regla de IVA anterior
- **GIVEN** una organización que pasó de `MONOTRIBUTO` a `RESPONSABLE_INSCRIPTO` y Cerveza B con costo vigente `Caja x12` a `"21780.00"`, registrado sin computar crédito fiscal
- **WHEN** se genera el borrador con regla `MARKUP` `"0.300000"` y redondeo `"100.00"` `CERCANO`
- **THEN** Cerveza B queda a `"28300.00"` con la señal de costo con otra regla de IVA, y el resultado informa 1 precio en esa situación
- **Regla:** CST-06; PRC-11; ADR-045 punto 10; `design.md` D3

#### Scenario: Organización que no cambió de condición
- **GIVEN** la organización inicial, `MONOTRIBUTO`, con todos sus costos registrados sin computar crédito fiscal
- **WHEN** se genera el borrador
- **THEN** ningún precio lleva la señal de costo con otra regla de IVA
- **Regla:** CST-06; `design.md` D3

#### Scenario: Costos distintos por presentación
- **GIVEN** Vino A con costo informado `Caja x6` a `"6000.00"` y, registrado después con la misma vigencia, `Caja x12` a `"11400.00"`; referencia `Caja x6`, regla `MARKUP` `"0.300000"` y redondeo `"100.00"` `CERCANO`
- **WHEN** se genera el borrador
- **THEN** Vino A queda a `"7400.00"` con costo de referencia `"5700.000000"`, informa que el costo salió de `Caja x12` y lleva la señal de costos distintos por presentación
- **Regla:** CST-03; PRC-11; `design.md` D2

### Requirement: El borrador se consulta con sus precios, señales y productos sin precio

El sistema DEBE devolver el borrador de una lista con sus precios paginados por cursor: producto, unidades de referencia, precio final, si es manual, el precio del mismo producto en la versión base, su relación con ella (nuevo, cambia o igual), las señales y, aparte, los productos activos sin precio con su causa. La lectura DEBE exigir `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. El costo de referencia, el tipo y el valor del margen y el precio calculado DEBEN devolverse solo a quien tiene `VER_COSTOS`; sin ese permiso van en nulo (`design.md` D12). Importes, costos y porcentajes DEBEN viajar como string.

#### Scenario: Consulta con permiso de ver costos
- **GIVEN** un usuario con `GESTIONAR_LISTAS` y `VER_COSTOS`
- **WHEN** consulta el borrador
- **THEN** Vino A aparece con precio final `"9500.00"`, precio en la versión base `"8600.00"`, relación "cambia", costo de referencia `"6600.000000"` y valor de margen `"0.300000"`
- **Regla:** PRC-16; PRC-17; `02` §10.2

#### Scenario: Consulta sin permiso de ver costos
- **GIVEN** un usuario con `GESTIONAR_LISTAS` y sin `VER_COSTOS`
- **WHEN** consulta el borrador
- **THEN** Vino A aparece con precio final `"9500.00"` y sus señales, y con costo de referencia, margen y precio calculado en nulo
- **Regla:** `01` §19 (`VER_COSTOS`); `design.md` D12

#### Scenario: Sin permiso de listas
- **WHEN** un usuario sin `GESTIONAR_LISTAS` ni `PUBLICAR_LISTAS` consulta el borrador
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06

#### Scenario: Borrador de otra organización
- **WHEN** un usuario de A consulta el borrador de una lista de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
