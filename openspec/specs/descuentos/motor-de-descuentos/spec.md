# descuentos/motor-de-descuentos Specification

## Purpose

Calcular los descuentos automáticos de una venta a partir del bruto de sus líneas y de las reglas aplicables, con el mismo resultado en el servidor y en el dispositivo, de modo que el vendedor vea sin conexión el mismo importe que queda registrado (DSC-03, DSC-04, DSC-05, DSC-07; ADR-004, ADR-016).

## Requirements

### Requirement: La condición de volumen se evalúa sobre las líneas elegibles

El motor DEBE evaluar la condición de cada regla comparando, con su operador explícito (`GTE` ≥ o `GT` >), una medida contra el umbral (DSC-03). Las líneas elegibles de una regla `VOLUMEN_OPERACION` DEBEN ser todas las de la venta; las de una `VOLUMEN_ALCANCE`, las líneas cuyo producto, categoría o marca figura en alguno de sus alcances (DSC-02; `design.md` D6). Las medidas DEBEN ser: unidades base (suma de las cantidades base), importe bruto (suma de los brutos) y cajas equivalentes (suma, línea por línea, de la cantidad base dividida por las unidades de referencia con las que se calculó el bruto de esa línea; `design.md` D5). La medida NO DEBE redondearse antes de comparar. Una regla sin líneas elegibles no aplica. Las condiciones DEBEN evaluarse siempre sobre las cantidades y los brutos de las líneas, nunca sobre importes ya descontados por otra regla.

#### Scenario: Veinte cajas alcanzan el umbral

- **GIVEN** la regla "cajas equivalentes ≥ 20 → 5%" sobre toda la venta
- **WHEN** la venta tiene 20 cajas de un vino de caja x6 (120 unidades base)
- **THEN** la regla aplica
- **Regla:** DSC-03 (ejemplo de `01` §10)

#### Scenario: Diecinueve cajas y cinco unidades no alcanzan

- **GIVEN** la misma regla
- **WHEN** la venta tiene dos líneas del mismo vino x6: 19 cajas y 5 unidades (119 unidades base, 19,83 cajas equivalentes)
- **THEN** la regla no aplica y ninguna línea recibe descuento
- **Regla:** DSC-03 (ejemplo de `01` §10); VTA-02

#### Scenario: Operador mayor estricto

- **GIVEN** una regla "cajas equivalentes > 20 → 5%"
- **WHEN** la venta tiene exactamente 20 cajas
- **THEN** la regla no aplica
- **Regla:** DSC-03

#### Scenario: Fracciones que suman una caja exacta

- **GIVEN** una regla "cajas equivalentes ≥ 1" y tres vinos distintos de caja x6
- **WHEN** la venta tiene 2 unidades de cada uno (un tercio de caja cada línea)
- **THEN** la medida es exactamente 1 y la regla aplica
- **Regla:** DSC-03; TR-03; `design.md` D5

#### Scenario: Cajas equivalentes de productos con distinta caja

- **GIVEN** una regla "cajas equivalentes ≥ 1", un vino de caja x6 y una cerveza de caja x12
- **WHEN** la venta tiene 3 unidades del vino y 6 unidades de la cerveza
- **THEN** la medida es 0,5 + 0,5 = 1 y la regla aplica
- **Regla:** DSC-03; glosario "Cajas equivalentes"

#### Scenario: Regla de alcance mide solo sus líneas

- **GIVEN** una regla con alcance en el producto "Vino A" y condición "cajas equivalentes ≥ 10"
- **WHEN** la venta tiene 8 cajas de "Vino A" y 10 cajas de "Vino B"
- **THEN** la medida es 8 y la regla no aplica
- **Regla:** DSC-02; DSC-03

#### Scenario: Alcance por categoría y por marca

- **GIVEN** una regla con dos alcances, la categoría "Vinos" y la marca "Cervecería Sur"
- **WHEN** la venta tiene una línea de un vino de otra marca, una de una cerveza de "Cervecería Sur" y una de un alfajor
- **THEN** las dos primeras son elegibles y la del alfajor no
- **Regla:** DSC-02; `design.md` D6

#### Scenario: Importe bruto de las líneas elegibles

- **GIVEN** una regla con alcance en la categoría "Vinos" y condición "importe bruto ≥ 30.000"
- **WHEN** la venta tiene 15 unidades de un vino x6 de precio de referencia $12.500 (bruto $31.250,00) y otras líneas fuera de la categoría
- **THEN** la medida es $31.250,00 y la regla aplica
- **Regla:** DSC-03; PRC-22 (ejemplo de `01` §7.3)

#### Scenario: Unidades base con operador mayor estricto

- **GIVEN** una regla "unidades base > 60"
- **WHEN** la venta tiene exactamente 60 unidades base
- **THEN** la regla no aplica
- **Regla:** DSC-03; INV-04

### Requirement: El descuento porcentual se calcula y redondea por línea

Una acción `PORCENTAJE` DEBE descontar, en cada línea elegible, el porcentaje aplicado sobre el importe de esa línea al momento de aplicar la regla, redondeado a 2 decimales con mitad hacia arriba, línea por línea (DSC-04, DSC-07, TR-03). El descuento NO DEBE calcularse sobre el total y repartirse después.

#### Scenario: Cinco por ciento sobre veinte cajas

- **GIVEN** la regla "cajas equivalentes ≥ 20 → 5%" y una línea de 20 cajas de un vino x6 de precio de referencia $12.500 (bruto $250.000,00)
- **WHEN** se calculan los descuentos
- **THEN** la línea tiene un descuento de $12.500,00 y un neto de $237.500,00
- **Regla:** DSC-04; DSC-07; VTA-04

#### Scenario: El redondeo es por línea y mitad hacia arriba

- **GIVEN** una regla del 5% que aplica y una línea de 1 unidad de un vino x6 de precio de referencia $8.600 (bruto $1.433,33)
- **WHEN** se calculan los descuentos
- **THEN** el descuento de esa línea es $71,67 (5% de $1.433,33 es $71,6665)
- **Regla:** DSC-07; TR-03; PRC-22 (ejemplo de `01` §7.3)

#### Scenario: Las líneas no elegibles no reciben descuento

- **GIVEN** una regla del 8% con alcance en "Vino A" que aplica
- **WHEN** la venta tiene líneas de "Vino A" y de "Vino B"
- **THEN** solo las líneas de "Vino A" reciben descuento
- **Regla:** DSC-02; DSC-04

### Requirement: El importe fijo se reparte entre las líneas elegibles

Una acción `IMPORTE_FIJO` DEBE repartirse entre las líneas elegibles en proporción a su importe al momento de aplicar la regla (el bruto, si ninguna regla anterior las descontó), con cada parte redondeada a 2 decimales (DSC-04, DSC-07). El remanente de redondeo, positivo o negativo, DEBE asignarse a la línea elegible de mayor importe; si hay empate, a la primera en el orden de la venta. La suma de las partes DEBE ser exactamente el importe aplicado. El importe aplicado NO DEBE superar la suma de los importes de las líneas elegibles: si la regla fija más, se aplica esa suma y ninguna línea queda con neto negativo (`design.md` D10).

#### Scenario: Reparto proporcional sin remanente

- **GIVEN** una regla "importe bruto ≥ 30.000 → $1.000 fijo" sobre toda la venta
- **WHEN** la venta tiene una línea de bruto $31.250,00 y otra de bruto $4.300,00
- **THEN** los descuentos son $879,04 y $120,96, que suman $1.000,00
- **Regla:** DSC-04; DSC-07; PRC-22 (ejemplos de `01` §7.3)

#### Scenario: Remanente negativo a la línea de mayor importe

- **GIVEN** la misma regla
- **WHEN** la venta tiene líneas de bruto $31.250,00, $4.300,00 y $1.433,33
- **THEN** las partes redondeadas son $844,98, $116,27 y $38,76, que suman $1.000,01
- **AND** el centavo sobrante se quita de la línea de $31.250,00, que queda con $844,97, y la suma es $1.000,00
- **Regla:** DSC-04; DSC-07

#### Scenario: Remanente positivo con empate de mayor importe

- **GIVEN** una regla de $100 fijos que aplica sobre toda la venta
- **WHEN** la venta tiene tres líneas de bruto $8.600,00 cada una
- **THEN** cada parte redondeada es $33,33 y el centavo faltante se asigna a la primera línea: $33,34, $33,33 y $33,33
- **Regla:** DSC-04; `design.md` D10

#### Scenario: Importe fijo mayor que las líneas elegibles

- **GIVEN** una regla de $5.000 fijos con alcance en "Vino B" que aplica
- **WHEN** la única línea elegible tiene bruto $4.300,00
- **THEN** el descuento de esa línea es $4.300,00 y su neto es $0,00
- **Regla:** DSC-04; VTA-04; `design.md` D10

### Requirement: Entre las reglas no acumulables gana una sola por venta

Entre las reglas no acumulables que aplican, el motor DEBE aplicar solo una en toda la venta: la de mayor beneficio total, calculado como la suma de los descuentos que produciría sobre el bruto de sus líneas elegibles (DSC-05 paso 3; ADR-004; `design.md` D7). Las demás no acumulables NO DEBEN aplicarse a ninguna línea, aunque sus líneas elegibles no hayan recibido descuento. Ante igual beneficio DEBE ganar la de mayor prioridad, que es la de número de prioridad más bajo (`design.md` D8); ante igual prioridad, la regla creada primero.

#### Scenario: Gana la de mayor beneficio total

- **GIVEN** dos reglas no acumulables: R1 "cajas equivalentes ≥ 20 → 5%" sobre toda la venta, y R2 "cajas equivalentes ≥ 10 → 8%" con alcance en "Vino A"
- **WHEN** la venta tiene 12 cajas de "Vino A" (caja x6 a $12.500, bruto $150.000,00) y 10 cajas de "Vino B" (caja x6 a $8.600, bruto $86.000,00)
- **THEN** R1 daría $7.500,00 + $4.300,00 = $11.800,00 y R2 daría $12.000,00, así que se aplica solo R2
- **AND** "Vino A" queda con descuento $12.000,00 y neto $138.000,00, y "Vino B" queda sin descuento, con neto $86.000,00
- **Regla:** DSC-05 (paso 3); ADR-004

#### Scenario: Empate de beneficio se resuelve por prioridad

- **GIVEN** dos reglas no acumulables que darían el mismo beneficio total, una con prioridad 1 y otra con prioridad 2
- **WHEN** se calculan los descuentos
- **THEN** se aplica la de prioridad 1 y la otra no se aplica
- **Regla:** DSC-05 (paso 3); `design.md` D8

#### Scenario: Empate de beneficio y de prioridad

- **GIVEN** dos reglas no acumulables con el mismo beneficio total y la misma prioridad
- **WHEN** se calculan los descuentos, entregando las reglas en cualquier orden
- **THEN** se aplica siempre la que se creó primero
- **Regla:** DSC-05; `design.md` D7

#### Scenario: Una sola regla no acumulable que aplica

- **GIVEN** una regla no acumulable que aplica y otra cuya condición no se cumple
- **WHEN** se calculan los descuentos
- **THEN** se aplica la primera
- **Regla:** DSC-05 (pasos 2 y 3)

### Requirement: Las reglas acumulables se aplican en orden de prioridad sobre el resultado anterior

Después de la regla no acumulable ganadora, si la hay, el motor DEBE aplicar todas las reglas acumulables que aplican, en orden de prioridad (número más bajo primero; ante igual prioridad, la creada primero), cada una sobre el importe que dejó la anterior en cada línea elegible (DSC-05 paso 4; `design.md` D9). El neto de una línea NO DEBE quedar negativo. Un descuento cuyo importe redondeado es cero NO DEBE figurar entre los descuentos de la línea.

#### Scenario: Una acumulable después de la ganadora

- **GIVEN** la venta del escenario "Gana la de mayor beneficio total" y, además, una regla acumulable R3 "importe bruto ≥ 200.000 → 2%" sobre toda la venta
- **WHEN** se calculan los descuentos
- **THEN** R3 aplica porque el bruto de la venta es $236.000,00
- **AND** "Vino A" suma un descuento de $2.760,00 (2% de $138.000,00) y queda en $135.240,00
- **AND** "Vino B" recibe $1.720,00 (2% de $86.000,00) y queda en $84.280,00
- **Regla:** DSC-05 (paso 4); DSC-07

#### Scenario: Dos acumulables en orden de prioridad

- **GIVEN** el resultado del escenario anterior y otra regla acumulable R5 de $1.000 fijos sobre toda la venta, con prioridad posterior a la de R3
- **WHEN** se calculan los descuentos
- **THEN** R5 se reparte sobre $135.240,00 y $84.280,00: $616,07 y $383,93
- **AND** los netos quedan en $134.623,93 y $83.896,07
- **Regla:** DSC-05 (paso 4); DSC-04; `design.md` D9, D10

#### Scenario: Solo acumulables

- **GIVEN** ninguna regla no acumulable que aplique y una acumulable del 2% que aplica
- **WHEN** se calculan los descuentos
- **THEN** la acumulable se aplica sobre el bruto de cada línea elegible
- **Regla:** DSC-05 (pasos 3 y 4)

#### Scenario: La condición de una acumulable no mira lo ya descontado

- **GIVEN** una regla acumulable "importe bruto ≥ 200.000 → 2%" y una venta de bruto $236.000,00 (líneas de $150.000,00 y $86.000,00) cuya regla no acumulable ganadora fija $38.000,00 y la deja en $198.000,00 ($125.847,46 y $72.152,54)
- **WHEN** se calculan los descuentos
- **THEN** la acumulable aplica, porque su condición se evalúa sobre el bruto
- **AND** descuenta $2.516,95 y $1.443,05, y los netos quedan en $123.330,51 y $70.709,49
- **Regla:** DSC-03; DSC-05 (paso 2); `design.md` D6

#### Scenario: Sin reglas aplicables

- **GIVEN** una venta y ninguna regla que aplique
- **WHEN** se calculan los descuentos
- **THEN** cada línea queda sin descuentos y con neto igual a su bruto
- **Regla:** DSC-05; VTA-04

### Requirement: El resultado detalla cada descuento por línea

El motor DEBE devolver, por cada línea y en el orden en que se aplicaron, cada descuento con su origen (`AUTOMATICO`), la regla que lo produjo, su porcentaje cuando la acción es porcentual y su importe, además del total descontado y el neto de la línea (DSC-08, VTA-04). El neto de cada línea DEBE ser su bruto menos la suma de sus descuentos. El motor NO calcula IVA ni el total de la venta.

El motor DEBE recibir el descuento manual en dos lugares: un porcentaje general de la venta, opcional, y un porcentaje propio en cada línea, opcional (`design.md` D4, D11). Cuando una línea lleva descuento manual, ese descuento DEBE ser el último de la línea, uno solo, con origen `MANUAL`, sin regla y con el porcentaje que le correspondió (el propio, o el general si no tiene propio); su cálculo lo define `descuentos/descuento-manual`. Junto con el detalle por línea, el motor DEBE devolver el mayor porcentaje manual que quedó aplicado en alguna línea, o nulo si ninguna lleva descuento manual, para que la evaluación del tope use ese mismo número (`design.md` D12).

#### Scenario: Línea con dos descuentos

- **GIVEN** la línea de "Vino A" del escenario "Una acumulable después de la ganadora"
- **WHEN** se lee su resultado
- **THEN** tiene dos descuentos en orden: el de R2 (`AUTOMATICO`, porcentaje `0.080000`, importe `12000.00`) y el de R3 (`AUTOMATICO`, porcentaje `0.020000`, importe `2760.00`)
- **AND** su total descontado es `14760.00` y su neto `135240.00`
- **Regla:** DSC-08; VTA-04

#### Scenario: Descuento de importe fijo sin porcentaje

- **GIVEN** una línea que recibió $879,04 de una regla de importe fijo
- **WHEN** se lee su resultado
- **THEN** ese descuento lleva la regla, el importe `879.04` y ningún porcentaje
- **Regla:** DSC-08; DSC-04

#### Scenario: Línea con descuentos automáticos y su porcentaje manual propio

- **GIVEN** la línea de "Vino A" del escenario "Una acumulable después de la ganadora", una venta con descuento manual general de `0.050000` y un porcentaje propio de `0.100000` en "Vino A"
- **WHEN** se lee su resultado
- **THEN** tiene tres descuentos en orden: el de R2 (`AUTOMATICO`, `12000.00`), el de R3 (`AUTOMATICO`, `2760.00`) y uno solo de origen `MANUAL`, sin regla, con porcentaje `0.100000` e importe `13524.00`
- **AND** su total descontado es `28284.00` y su neto `121716.00`
- **AND** "Vino B" termina con un único descuento `MANUAL` de porcentaje `0.050000` e importe `4214.00`, y neto `80066.00`
- **Regla:** DSC-05 (paso 5); DSC-08; `design.md` D11

#### Scenario: El resultado informa el mayor porcentaje manual de la venta

- **GIVEN** la venta del escenario anterior
- **WHEN** se lee el resultado de la venta
- **THEN** el mayor porcentaje manual es `0.100000`
- **AND** en una venta sin descuento manual general y sin porcentajes propios, ese valor es nulo
- **Regla:** DSC-06; `design.md` D4, D12

### Requirement: El servidor y el dispositivo calculan lo mismo

El cálculo DEBE existir como función pura en el servidor y en el dispositivo, con la misma entrada y la misma salida, y DEBE verificarse con casos compartidos que viven una sola vez y que ejecutan las dos suites (`02` §10.4, ADR-016). Los casos compartidos DEBEN agregarse antes que el código del cálculo. Los importes y los porcentajes DEBEN entrar y salir como decimales exactos, nunca como punto flotante (INV-03); una entrada de punto flotante DEBE rechazarse. El resultado NO DEBE depender del orden en que se entregan las reglas.

#### Scenario: Los casos compartidos cubren el orden de resolución

- **GIVEN** los casos compartidos de descuentos
- **WHEN** se ejecutan la suite del servidor y la del dispositivo
- **THEN** ambas corren los mismos casos, cada uno identificado por su `id`, y cubren los ejemplos de DSC-03, el reparto y el remanente de DSC-04, los cinco pasos de DSC-05 (incluido el descuento manual general, el propio de una línea que lo reemplaza y el mayor porcentaje manual de la venta) y el redondeo de DSC-07
- **Regla:** DSC-05; `02` §10.4; ADR-016

#### Scenario: Una divergencia entre implementaciones falla en CI

- **GIVEN** un caso compartido cuya salida esperada no coincide con lo que produce una de las dos implementaciones
- **WHEN** se ejecutan ambas suites
- **THEN** falla la de esa implementación nombrando el `id` del caso
- **Regla:** `02` §10.4; ADR-016

#### Scenario: Un bruto de punto flotante se rechaza

- **GIVEN** una línea cuyo bruto llega como número de punto flotante
- **WHEN** se calculan los descuentos
- **THEN** el cálculo se rechaza con un error de dominio y no devuelve resultado
- **Regla:** INV-03; TR-01

#### Scenario: El orden de entrega de las reglas no cambia el resultado

- **GIVEN** un conjunto de reglas aplicables y una venta
- **WHEN** se calculan los descuentos entregando las reglas en dos órdenes distintos
- **THEN** los dos resultados son idénticos
- **Regla:** DSC-05

#### Scenario: Ningún neto negativo

- **GIVEN** cualquier venta y cualquier conjunto de reglas válidas
- **WHEN** se calculan los descuentos
- **THEN** ninguna línea queda con neto negativo y todo importe tiene exactamente 2 decimales
- **Regla:** DSC-07; VTA-04; TR-01
