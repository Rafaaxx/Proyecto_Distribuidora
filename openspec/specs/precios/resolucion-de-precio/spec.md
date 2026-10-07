# precios/resolucion-de-precio Specification

## Purpose
Definir cómo se resuelve el precio aplicable: la lista del cliente o la predeterminada, la versión vigente a un momento, el precio de un producto con sus unidades de referencia y el cálculo del importe bruto de una línea, idéntico en el servidor y en el dispositivo (PRC-20, PRC-22, ADR-010, ADR-016). El uso en la venta, el congelado por línea y el uso de otra lista o de una versión anterior llegan con el change 18a (PRC-21, PRC-23). Escrita con la opción A de `design.md` D1, D6, D10, D11 y D12, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## Requirements

### Requirement: La lista aplicable es la asignada o la predeterminada de la organización

Dada la lista asignada a un cliente, o ninguna, la lista aplicable DEBE ser la asignada si existe y, si no, la lista predeterminada de la organización (PRC-20). Si la lista que corresponde está inactiva, o el cliente no tiene lista y la organización no tiene una predeterminada, NO hay lista aplicable y la resolución DEBE informar `SIN_LISTA_APLICABLE`. La resolución DEBE hacerse siempre dentro de la organización del token.

#### Scenario: Cliente con lista asignada
- **GIVEN** `Kiosco El Faro` con la lista `Mayorista` asignada y `General` como predeterminada
- **WHEN** se resuelve la lista aplicable
- **THEN** es `Mayorista`
- **Regla:** PRC-20

#### Scenario: Cliente sin lista asignada
- **GIVEN** `Kiosco La Esquina` sin lista asignada y `General` como predeterminada
- **WHEN** se resuelve la lista aplicable
- **THEN** es `General`
- **Regla:** PRC-20; `01` §4 (lista de precios por defecto)

#### Scenario: Sin lista asignada ni predeterminada
- **GIVEN** un cliente sin lista y una organización sin lista predeterminada
- **WHEN** se resuelve la lista aplicable
- **THEN** se informa `SIN_LISTA_APLICABLE`
- **Regla:** PRC-20; VTA-10 (precio resoluble)

#### Scenario: Lista asignada de otra organización
- **WHEN** se resuelve la lista aplicable con el identificador de una lista de otra organización
- **THEN** se responde como recurso inexistente
- **Regla:** INV-21; SEG-07

### Requirement: El precio de un producto se resuelve en la versión vigente a un momento

El sistema DEBE resolver, para una lista y un momento, la versión vigente según PRC-03 y devolver de ella, para cada producto pedido, el precio de referencia y las unidades de referencia guardadas en el precio (PRC-20, PRC-10, `design.md` D1). Si la lista no tiene versión vigente a ese momento DEBE informar `LISTA_SIN_VERSION_VIGENTE`. Un producto sin precio en la versión NO DEBE recibir un precio inventado: se informa como sin precio. La lectura por API de la versión vigente de una lista DEBE exigir `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`, y los precios DEBEN viajar como string.

#### Scenario: Precio vigente de un producto
- **GIVEN** `General` con la versión n.º 3 vigente, donde Vino A vale `"8600.00"` con unidades de referencia `6`
- **WHEN** se resuelve el precio de Vino A en `General` a ahora
- **THEN** se obtiene la versión n.º 3, precio de referencia `"8600.00"` y unidades de referencia `6`
- **Regla:** PRC-20; PRC-10; PRC-03

#### Scenario: Se usa la versión vigente al momento pedido
- **GIVEN** la versión n.º 2 desde el 01/09 con Vino A a `"7800.00"` y la n.º 3 desde el 01/10 con Vino A a `"8600.00"`
- **WHEN** se resuelve el precio de Vino A al 15/09 y al 02/10
- **THEN** se obtiene `"7800.00"` de la versión n.º 2 y `"8600.00"` de la n.º 3 respectivamente
- **Regla:** PRC-20 (versión vigente al `occurred_at`); PRC-03

#### Scenario: Lista sin versión vigente
- **GIVEN** una lista con solo un borrador
- **WHEN** se resuelve un precio en ella
- **THEN** se informa `LISTA_SIN_VERSION_VIGENTE`
- **Regla:** PRC-03; PRC-20; VTA-10

#### Scenario: Producto sin precio en la versión vigente
- **GIVEN** la versión vigente de `General` sin precio para Gaseosa C
- **WHEN** se resuelven los precios de Vino A y de Gaseosa C
- **THEN** Vino A se devuelve con su precio y Gaseosa C como sin precio
- **Regla:** PRC-10; VTA-10

#### Scenario: Las unidades de referencia son las del precio, no las actuales
- **GIVEN** la versión vigente con Vino A a `"8600.00"` y unidades de referencia `6`, y la referencia de Vino A cambiada después a `Caja x12`
- **WHEN** se resuelve el precio de Vino A
- **THEN** se obtiene `"8600.00"` con unidades de referencia `6`
- **Regla:** PRC-10; INV-11; `design.md` D1

#### Scenario: Versión vigente de una lista ajena
- **WHEN** un usuario de A pide la versión vigente de una lista de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

#### Scenario: Lectura sin permiso
- **WHEN** un usuario sin `GESTIONAR_LISTAS` ni `PUBLICAR_LISTAS` pide la versión vigente de una lista
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06; `design.md` D12

### Requirement: El importe bruto de una línea se calcula una sola vez y con un solo redondeo

El importe bruto de una línea DEBE ser `precio de referencia × cantidad base / unidades de referencia`, redondeado a dos decimales una sola vez, con medio hacia arriba (PRC-22, TR-03, ADR-010). El precio unitario por presentación DEBE mostrarse con ese mismo cálculo (cantidad base igual a las unidades de la presentación) y NO DEBE usarse para calcular totales. La cantidad base y las unidades de referencia son enteras (INV-04); una cantidad base no positiva o unas unidades de referencia menores que uno DEBEN rechazarse. El cálculo NO DEBE usar punto flotante binario (INV-03).

#### Scenario: Cajas y unidades sueltas
- **GIVEN** precio de referencia `"12500.00"` y unidades de referencia `6`
- **WHEN** se calcula el bruto de 15 unidades base (2 cajas y 3 unidades)
- **THEN** el bruto es `"31250.00"`
- **Regla:** PRC-22; `01` §7.3 (ejemplo)

#### Scenario: Media caja
- **GIVEN** precio de referencia `"8600.00"` y unidades de referencia `6`
- **WHEN** se calcula el bruto de 3 unidades base
- **THEN** el bruto es `"4300.00"`
- **Regla:** PRC-22; `01` §7.3 (ejemplo)

#### Scenario: Una unidad con redondeo
- **GIVEN** precio de referencia `"8600.00"` y unidades de referencia `6`
- **WHEN** se calcula el bruto de 1 unidad base
- **THEN** el bruto es `"1433.33"`
- **Regla:** PRC-22; TR-03; `01` §7.3 (ejemplo)

#### Scenario: El total no se arma con el precio unitario redondeado
- **GIVEN** precio de referencia `"8600.00"` y unidades de referencia `6`
- **WHEN** se calcula el bruto de 3 unidades base
- **THEN** el bruto es `"4300.00"` y no `"4299.99"`, que es el precio unitario mostrado `"1433.33"` multiplicado por 3
- **Regla:** PRC-22 (el precio unitario nunca se usa para calcular totales)

#### Scenario: Cantidad o unidades inválidas
- **WHEN** se calcula el bruto con cantidad base `0` o negativa, o con unidades de referencia `0`
- **THEN** el cálculo se rechaza con un error explícito
- **Regla:** PRC-22; INV-04

### Requirement: El bruto de línea tiene casos compartidos entre el servidor y el dispositivo

Los casos del bruto de línea DEBEN vivir una sola vez en `shared/fixtures/calculo/`, con los tres ejemplos de `01` §7.3 como mínimo, y DEBEN ejecutarlos la suite de Python y la de TypeScript contra sus respectivas implementaciones, con comparación exacta de los importes como texto (`02` §10.4, ADR-016, `design.md` D10). Los casos DEBEN agregarse antes de escribir cualquiera de las dos implementaciones.

#### Scenario: Las dos suites ejecutan los casos de PRC-22
- **GIVEN** los casos de PRC-22 en `shared/fixtures/calculo/`
- **WHEN** se ejecutan la suite de Python y la de TypeScript
- **THEN** ambas descubren los mismos casos, cada uno como prueba con su `id`, y todos pasan con salida idéntica
- **Regla:** PRC-22; `02` §10.4; ADR-016

#### Scenario: Una implementación diverge
- **GIVEN** una implementación que redondea el precio unitario antes de multiplicar
- **WHEN** se ejecuta su suite
- **THEN** falla nombrando el `id` del caso de PRC-22 que rompe
- **Regla:** PRC-22; `02` §10.4; `02` §20 (divergencia entre cálculo del dispositivo y del servidor)

#### Scenario: Los casos preceden al código
- **GIVEN** los casos de PRC-22 agregados y ninguna implementación del bruto de línea
- **WHEN** se ejecutan las dos suites
- **THEN** ambas fallan por la implementación faltante, no por falta de casos
- **Regla:** `02` §10.4 (los casos compartidos se agregan antes de modificar el código)
