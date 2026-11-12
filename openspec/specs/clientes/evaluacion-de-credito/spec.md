# Evaluación de crédito — Especificación

## Purpose

Define el cálculo puro de la evaluación de crédito (disponible, saldo resultante, exceso, tolerancia y resolución por política), idéntico en el servidor y en el dispositivo y probado con casos compartidos (CRE-01 a CRE-08, ADR-016, ADR-032).

## Requirements

### Requirement: El cálculo de crédito es exacto y determinista

El cálculo DEBE recibir límite (o vacío), saldo actual, total de la venta, cobranza, política, tolerancia (tipo y valor, o vacía), modo (con o sin conexión) y lo que el usuario dispone para resolver (acepta el exceso, tiene permiso propio, hay un autorizador verificado), y DEBE devolver disponible (CRE-01), saldo resultante (CRE-02), exceso y la resolución o el código de rechazo. Todos los importes DEBEN ser decimales exactos con dos decimales; un valor de punto flotante DEBE rechazarse (INV-03).

#### Scenario: Disponible

- **GIVEN** límite $200.000 y saldo $150.000
- **WHEN** se calcula
- **THEN** el disponible es $50.000
- **Regla:** CRE-01

#### Scenario: Límite cero

- **GIVEN** límite $0 y una venta de $1.000 sin cobranza
- **WHEN** se calcula
- **THEN** el exceso es $1.000
- **Regla:** CRE-01

#### Scenario: Saldo a favor

- **GIVEN** límite $100.000, saldo −$20.000 y una venta de $110.000 sin cobranza
- **WHEN** se calcula
- **THEN** el saldo resultante es $90.000 y no hay exceso
- **Regla:** CRE-02

#### Scenario: Entrada de punto flotante

- **WHEN** se entrega un importe que no es decimal exacto
- **THEN** se rechaza con un error de código estable
- **Regla:** INV-03

### Requirement: La tolerancia sin conexión se aplica sobre el exceso

Sin conexión y con política AUTORIZAR, el exceso que no supera la tolerancia DEBE resolverse como `TOLERANCIA_OFFLINE`; el que la supera DEBE resolverse por permiso propio o PIN de supervisor y, sin ninguno, DEBE comportarse como BLOQUEAR. Una tolerancia en porcentaje DEBE calcularse sobre el límite (`valor` con dos decimales, `2.50` = 2,50 %) y redondearse a dos decimales mitad hacia arriba. Sin tolerancia en el cliente ni en la organización, la tolerancia DEBE ser cero.

#### Scenario: Ejemplo de la regla

- **GIVEN** exceso $10.000
- **WHEN** la tolerancia es $20.000
- **THEN** la resolución es `TOLERANCIA_OFFLINE`
- **AND** con tolerancia $5.000 y sin permiso ni PIN se rechaza como BLOQUEAR
- **Regla:** CRE-06

#### Scenario: Tolerancia en porcentaje

- **GIVEN** límite $200.000 y tolerancia 5,00 %
- **WHEN** el exceso es $10.000 y luego $10.000,01
- **THEN** el primero queda dentro de la tolerancia y el segundo no
- **Regla:** CRE-06; ADR-032; TR-03

#### Scenario: Sin tolerancia cargada

- **WHEN** no hay tolerancia en el cliente ni en la organización y el exceso es $0,01
- **THEN** pide permiso propio o PIN
- **Regla:** CRE-06

### Requirement: El servidor y el dispositivo evalúan lo mismo

El cálculo DEBE existir en el servidor y en el dispositivo y ambos DEBEN pasar los mismos casos compartidos del archivo de casos de crédito, escritos antes que el código (ADR-016).

#### Scenario: Los casos compartidos corren en las dos suites

- **GIVEN** el archivo de casos de crédito con los ejemplos de `01` §9.2
- **WHEN** corren las suites de Python y de TypeScript
- **THEN** ambas dan el mismo disponible, saldo resultante, exceso y resolución en cada caso
- **Regla:** CRE-01; CRE-02; CRE-06; ADR-016
