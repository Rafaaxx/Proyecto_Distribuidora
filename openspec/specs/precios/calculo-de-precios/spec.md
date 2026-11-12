# precios/calculo-de-precios Specification

## Purpose
Definir cómo se calcula el precio de referencia de un producto en una lista: costo de referencia, margen y redondeo, con decimales exactos y un solo redondeo final (PRC-10 a PRC-16, TR-03). El cálculo corre solo en el servidor. Escrita con la opción A de `design.md` D1, D2, D9 y D10, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## Requirements

### Requirement: El costo de referencia sale del costo informado vigente

El costo de referencia de un producto DEBE ser el costo base de su costo informado vigente multiplicado por las unidades de su presentación de referencia, sin redondear (PRC-11). El costo informado vigente es el de CST-03, cualquiera sea la presentación en que se informó (`design.md` D2). El costo promedio NO DEBE usarse para calcular precios (CST-04). Un producto sin costo informado vigente no tiene costo de referencia.

#### Scenario: Costo informado por botella y referencia por caja
- **GIVEN** Vino A con costo base vigente `"1000.000000"` y referencia `Caja x6`
- **WHEN** se calcula su costo de referencia
- **THEN** es `"6000.000000"`
- **Regla:** PRC-11; `01` §7.2 (ejemplo)

#### Scenario: Costo informado en la misma caja de referencia
- **GIVEN** Cerveza B con costo informado `Caja x12` a `"18000.00"` (costo base `"1500.000000"`) y referencia `Caja x12`
- **WHEN** se calcula su costo de referencia
- **THEN** es `"18000.000000"`
- **Regla:** PRC-11; CST-02

#### Scenario: Organización monotributista
- **GIVEN** una organización `MONOTRIBUTO` y Cerveza B con costo informado `Caja x12` a `"21780.00"` (costo base `"1815.000000"`, el IVA es costo)
- **WHEN** se calcula su costo de referencia sobre `Caja x12`
- **THEN** es `"21780.000000"`
- **Regla:** PRC-11; CST-02; CST-06

#### Scenario: El costo promedio no interviene
- **GIVEN** Vino A con costo informado vigente de costo base `"1000.000000"` y costo promedio `"1133.333333"`
- **WHEN** se calcula su costo de referencia sobre `Caja x6`
- **THEN** es `"6000.000000"`
- **Regla:** CST-04; PRC-11

#### Scenario: Producto sin costo informado vigente
- **GIVEN** un producto cuyo único costo informado tiene vigencia desde una fecha futura
- **WHEN** se calcula su costo de referencia a hoy
- **THEN** no tiene costo de referencia
- **Regla:** CST-03; PRC-11

### Requirement: El margen se aplica como markup o como margen bruto

El precio calculado sin redondear DEBE ser `costo de referencia × (1 + m)` para una regla `MARKUP` y `costo de referencia / (1 − m)` para una regla `MARGEN_BRUTO`, con `m` el valor de la regla (PRC-12). El cálculo DEBE hacerse con decimales exactos, sin punto flotante binario y sin redondeos intermedios (TR-01, TR-03, INV-03). El precio calculado se registra con seis decimales.

#### Scenario: Markup del 30%
- **GIVEN** costo de referencia `"6000.000000"` y regla `MARKUP` `"0.300000"`
- **WHEN** se calcula el precio
- **THEN** el precio calculado es `"7800.000000"`
- **Regla:** PRC-12; `01` §7.2 (ejemplo: $7.800,00)

#### Scenario: Margen bruto del 30%
- **GIVEN** costo de referencia `"6000.000000"` y regla `MARGEN_BRUTO` `"0.300000"`
- **WHEN** se calcula el precio
- **THEN** el precio calculado es `"8571.428571"`
- **Regla:** PRC-12; `01` §7.2 (ejemplo: $8.571,43)

#### Scenario: Margen cero
- **GIVEN** costo de referencia `"6000.000000"` y regla `MARKUP` o `MARGEN_BRUTO` de `"0.000000"`
- **WHEN** se calcula el precio
- **THEN** el precio calculado es `"6000.000000"`
- **Regla:** PRC-12

#### Scenario: Entrada en punto flotante
- **WHEN** el cálculo recibe un costo o un margen como punto flotante binario
- **THEN** se rechaza con `ENTRADA_NO_ES_DINERO_EXACTO`
- **Regla:** INV-03; TR-01

### Requirement: El precio final se obtiene redondeando al múltiplo en la dirección indicada

El precio final DEBE ser el precio calculado sin redondear llevado al múltiplo del redondeo aplicable: hacia arriba (`ARRIBA`), hacia abajo (`ABAJO`) o al más cercano (`CERCANO`), y en `CERCANO` el punto medio DEBE redondear hacia arriba (PRC-14). Un precio calculado que ya es múltiplo NO DEBE cambiar. El redondeo aplicable es la sobrescritura activa de la categoría del producto y, si no hay, el de la lista (`design.md` D9). El precio final tiene dos decimales y DEBE ser mayor que cero: si el redondeo da cero, el producto no tiene precio. En modos impositivos A y B el redondeo se aplica al precio neto (PRC-15).

#### Scenario: Las tres direcciones del ejemplo
- **GIVEN** un precio calculado de `"8571.428571"` y múltiplo `"100.00"`
- **WHEN** se redondea con `ARRIBA`, con `CERCANO` y con `ABAJO`
- **THEN** el precio final es `"8600.00"`, `"8600.00"` y `"8500.00"` respectivamente
- **Regla:** PRC-14; `01` §7.2 (ejemplo)

#### Scenario: Un múltiplo exacto no cambia
- **GIVEN** un precio calculado de `"7800.000000"` y múltiplo `"100.00"`
- **WHEN** se redondea con cualquiera de las tres direcciones
- **THEN** el precio final es `"7800.00"`
- **Regla:** PRC-14; `01` §7.2 (ejemplo)

#### Scenario: Punto medio en más cercano
- **GIVEN** un precio calculado de `"8550.000000"` y múltiplo `"100.00"`
- **WHEN** se redondea con `CERCANO`
- **THEN** el precio final es `"8600.00"`
- **Regla:** PRC-14 (el punto medio redondea hacia arriba); TR-03

#### Scenario: La categoría sobrescribe el redondeo de la lista
- **GIVEN** la lista con múltiplo `"100.00"` `CERCANO`, la categoría del producto con sobrescritura activa `"500.00"` `ARRIBA` y un precio calculado de `"8571.428571"`
- **WHEN** se redondea
- **THEN** el precio final es `"9000.00"`
- **Regla:** PRC-14; `design.md` D9

#### Scenario: Redondeo que da cero
- **GIVEN** un precio calculado de `"80.000000"`, múltiplo `"100.00"` y dirección `ABAJO`
- **WHEN** se redondea
- **THEN** el producto no tiene precio y la causa informada es `PRECIO_NO_POSITIVO`
- **Regla:** PRC-14; `design.md` D9

#### Scenario: Múltiplo de un centavo
- **GIVEN** un precio calculado de `"8571.428571"`, múltiplo `"0.01"` y dirección `CERCANO`
- **WHEN** se redondea
- **THEN** el precio final es `"8571.43"`
- **Regla:** PRC-14; TR-03; `01` §7.2 (ejemplo: $8.571,43)

### Requirement: Cada precio guarda cómo se calculó

Cada precio de una versión DEBE guardar: el costo de referencia usado, la regla de margen aplicada con su tipo y su valor, el precio calculado sin redondear, el precio final, si fue fijado manualmente (PRC-16), las unidades de la presentación de referencia vigentes al calcularlo (`design.md` D1) y el costo informado del que salió (`design.md` D2). Estos datos NO DEBEN recalcularse al leerlos: son los del momento del cálculo.

#### Scenario: Datos guardados de un precio calculado
- **GIVEN** Vino A con costo de referencia `"6000.000000"`, regla de categoría `MARGEN_BRUTO` `"0.300000"`, referencia `Caja x6` y redondeo `"100.00"` `ARRIBA`
- **WHEN** se genera su precio
- **THEN** el precio guarda costo de referencia `"6000.000000"`, la regla aplicada con tipo `MARGEN_BRUTO` y valor `"0.300000"`, precio calculado `"8571.428571"`, precio final `"8600.00"`, `manual = false` y unidades de referencia `6`
- **Regla:** PRC-16; PRC-10; `03` §8 (`precio_item`)

#### Scenario: El precio conserva el margen aunque la regla cambie
- **GIVEN** el precio anterior y la regla modificada después a `"0.350000"`
- **WHEN** se lee el precio
- **THEN** sigue informando valor de margen `"0.300000"` y precio final `"8600.00"`
- **Regla:** PRC-16; PRC-04

### Requirement: Hay un único precio por producto, sobre la presentación de referencia

Una versión DEBE tener como máximo un precio por producto, expresado sobre la presentación de referencia (PRC-10); la base de datos DEBE impedir un segundo precio del mismo producto en la misma versión. NO DEBE existir un precio por presentación (ADR-010).

#### Scenario: Segundo precio del mismo producto
- **GIVEN** una versión con un precio de Vino A
- **WHEN** se intenta escribir directamente otro precio de Vino A en esa versión
- **THEN** la base lo rechaza por el índice único de versión y producto
- **Regla:** PRC-10; `03` §8 (`ux_precio_item__version_producto`); `03` §15

### Requirement: El cálculo de precios no se genera con modo impositivo C

En una organización con modo impositivo `C` el sistema NO DEBE generar precios: el redondeo sobre el precio con IVA incluido pertenece a la etapa 4 (PRC-15). El intento DEBE rechazarse con `MODO_IMPOSITIVO_NO_SOPORTADO`.

#### Scenario: Organización en modo C
- **GIVEN** una organización responsable inscripta con modo impositivo `C`
- **WHEN** se envía `LISTA_GENERAR_BORRADOR`
- **THEN** se rechaza con `MODO_IMPOSITIVO_NO_SOPORTADO` y no se crea ningún borrador
- **Regla:** PRC-15 (C: etapa 4); `design.md` D9

#### Scenario: Organización en modo A
- **GIVEN** la organización inicial, `MONOTRIBUTO` y modo `A`
- **WHEN** se envía `LISTA_GENERAR_BORRADOR`
- **THEN** se genera el borrador y el redondeo se aplica al precio neto, que es el precio final de venta
- **Regla:** PRC-15; ADR-045
