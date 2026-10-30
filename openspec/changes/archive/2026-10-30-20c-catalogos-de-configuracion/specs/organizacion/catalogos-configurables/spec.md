## MODIFIED Requirements

### Requirement: Las alícuotas de IVA se expresan como fracción de seis decimales
Una alícuota de IVA DEBE tener nombre, valor y marca de actividad. El valor DEBE representarse como fracción decimal exacta de 6 decimales, mayor o igual que cero y menor que uno, nunca como punto flotante binario (TR-02, INV-03, `03` §4). El nombre (sin distinguir mayúsculas) y el valor DEBEN ser únicos dentro de la organización, entre activas e inactivas, y el valor NO DEBE cambiar después del alta (`design.md` D6 y D7 del change 20c, ADR-061).

#### Scenario: El 21 % se almacena como fracción
- **GIVEN** la alícuota de IVA del 21 % de la organización inicial
- **WHEN** se lee su valor
- **THEN** es `0.210000`
- **Regla:** TR-02 (los porcentajes se representan con 6 decimales como fracción, 21 % = 0,210000)

#### Scenario: Una alícuota del 0 % es válida
- **GIVEN** la organización inicial
- **WHEN** se lee la alícuota de valor `0.000000`
- **THEN** existe y está activa
- **Regla:** `01` §4 (alícuotas iniciales: 21 %, 10,5 %, 0 %)

#### Scenario: Un valor de punto flotante no entra al catálogo
- **GIVEN** la operación de alta de una alícuota
- **WHEN** se le pasa el valor como número de punto flotante binario
- **THEN** la operación falla con un error explícito y no crea la alícuota
- **Regla:** INV-03

#### Scenario: Dos alícuotas con el mismo valor en una organización
- **GIVEN** la alícuota de valor `0.210000` de la organización A, activa o no
- **WHEN** se intenta guardar otra de valor `0.210000` en A
- **THEN** la base la rechaza; en la organización B el mismo valor se acepta
- **Regla:** IMP-04 (la importación resuelve la alícuota por porcentaje); INV-02

#### Scenario: Un valor de 100 % o más no entra
- **WHEN** se intenta guardar una alícuota de valor `1.000000`
- **THEN** la base la rechaza
- **Regla:** TR-02; `design.md` D7 del change 20c

### Requirement: Un motivo pertenece a un ámbito de la lista cerrada
Un motivo DEBE declarar su ámbito dentro de la lista cerrada `AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`, además de nombre y marca de actividad. Los motivos DEBEN poder listarse filtrados por ámbito (`03` §4). El ámbito `ANULACION_PAGO` es el de la anulación de pagos a proveedores (PAG-03, `design.md` D1 del change 12). El nombre DEBE ser único dentro de la organización y el ámbito sin distinguir mayúsculas, entre activos e inactivos, y el ámbito NO DEBE cambiar después del alta (`design.md` D2 y D3 del change 20c, ADR-061).

#### Scenario: Los motivos se listan por ámbito
- **GIVEN** la organización inicial con sus motivos de ajuste de stock sembrados
- **WHEN** se listan los motivos del ámbito `AJUSTE_STOCK`
- **THEN** el resultado contiene los seis motivos de ajuste y ninguno de otro ámbito
- **Regla:** `01` §4, `03` §4 (`motivo.ambito`)

#### Scenario: Un ámbito fuera de la lista se rechaza
- **GIVEN** la operación de alta de un motivo
- **WHEN** se la invoca con un ámbito que no está en la lista cerrada
- **THEN** falla con un error explícito y no crea el motivo
- **Regla:** `03` §4 (lista cerrada de `ambito`)

#### Scenario: Motivos de anulación de pago por API
- **GIVEN** la organización A con motivos de `ANULACION_COMPRA` y de `ANULACION_PAGO`
- **WHEN** se piden los motivos del ámbito `ANULACION_PAGO`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** PAG-03; TR-09; INV-21

#### Scenario: Nombre repetido en el ámbito
- **GIVEN** el motivo "Otro" del ámbito `AJUSTE_STOCK` de la organización A
- **WHEN** se intenta guardar "otro" en `AJUSTE_STOCK` de A
- **THEN** la base lo rechaza; "Otro" en `ANULACION_VENTA` de A se acepta
- **Regla:** `03` §4; `design.md` D3 del change 20c
