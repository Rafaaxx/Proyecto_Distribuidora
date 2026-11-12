## Purpose

Garantiza que las dos implementaciones del cálculo de negocio (Python en el servidor y TypeScript en el dispositivo) no diverjan: los casos de prueba viven una sola vez en `shared/fixtures/calculo/` y los ejecutan tanto pytest como Vitest (`02` §10.4, `02` §15).

Nota de trazabilidad: este change construye el arnés que ejecuta los casos compartidos. Los casos de negocio (PRC-22, DSC-05, VTA-04, CRE-01 a CRE-08) los agregan sus changes respectivos.

## ADDED Requirements

### Requirement: Los casos de cálculo viven una sola vez
Los casos de prueba del cálculo compartido DEBEN residir exclusivamente en `shared/fixtures/calculo/*.json`, con el formato de caso de `02` §10.4 (`id`, `reglas`, `entrada`, `salida_esperada`). Ninguna de las dos suites DEBE mantener una copia propia de esos casos.

#### Scenario: Un caso nuevo se agrega en un solo lugar
- **GIVEN** un caso nuevo agregado a `shared/fixtures/calculo/`
- **WHEN** se ejecutan la suite de Python y la suite de TypeScript sin ningún otro cambio
- **THEN** ambas descubren y ejecutan el caso nuevo
- **Regla:** `02` §10.4 (los casos viven una sola vez y los ejecutan tanto pytest como Vitest)

#### Scenario: Un caso con formato inválido se rechaza
- **GIVEN** un archivo en `shared/fixtures/calculo/` sin `id`, sin `reglas` o sin `salida_esperada`
- **WHEN** se ejecuta cualquiera de las dos suites
- **THEN** la suite falla indicando el archivo y el campo faltante, en lugar de saltear el caso
- **Regla:** `02` §10.4 (formato de caso)

### Requirement: Cada caso compartido es una prueba identificable en ambas suites
Cada caso compartido DEBE aparecer como una prueba independiente en la suite de Python y en la de TypeScript, con el `id` del caso visible en el nombre de la prueba, de modo que un caso que falla identifique la regla que rompe.

#### Scenario: Una salida distinta falla en la suite correspondiente
- **GIVEN** un caso compartido cuya `salida_esperada` no coincide con lo que produce una de las dos implementaciones
- **WHEN** se ejecutan ambas suites
- **THEN** la suite de esa implementación falla nombrando el `id` del caso y las `reglas` que cita
- **AND** la otra suite pasa, evidenciando la divergencia entre implementaciones
- **Regla:** `02` §10.4 (ambas implementaciones son funciones puras con la misma entrada y la misma salida)

#### Scenario: Los importes esperados se comparan como texto exacto
- **GIVEN** un caso cuya `salida_esperada` contiene el importe `"31250.00"`
- **WHEN** cualquiera de las dos suites compara el resultado
- **THEN** la comparación es sobre la representación decimal exacta y no admite tolerancia numérica
- **Regla:** `02` §10.2 (los importes viajan como string); INV-03

### Requirement: Ninguna suite puede ignorar los casos compartidos
Si existen casos en `shared/fixtures/calculo/` y una de las dos suites no ejecuta ninguno, esa suite DEBE fallar. El arnés no puede quedar mudo.

#### Scenario: La suite de TypeScript deja de cargar los casos
- **GIVEN** casos presentes en `shared/fixtures/calculo/`
- **WHEN** la suite de TypeScript se ejecuta sin descubrir ningún caso
- **THEN** la suite falla indicando que no encontró casos compartidos
- **Regla:** `02` §10.4 (CI falla si cualquiera de las dos suites falla)

#### Scenario: El directorio de casos no existe
- **GIVEN** que `shared/fixtures/calculo/` no existe o no es accesible desde la suite
- **WHEN** se ejecuta la suite
- **THEN** la suite falla con un mensaje que nombra la ruta esperada
- **Regla:** `02` §10.4

### Requirement: Los casos compartidos preceden al cambio de código
Todo cambio en una regla de cálculo DEBE agregar o modificar los casos compartidos antes de modificar cualquiera de las dos implementaciones (`02` §10.4).

#### Scenario: Se cambia una regla de cálculo
- **GIVEN** una regla de cálculo que cambia su resultado esperado
- **WHEN** se prepara el cambio
- **THEN** los casos de `shared/fixtures/calculo/` que citan esa regla se actualizan primero
- **AND** ambas implementaciones se modifican después hasta que las dos suites vuelven a pasar
- **Regla:** `02` §10.4 (todo cambio en una regla de cálculo agrega o modifica casos compartidos antes de modificar el código)
