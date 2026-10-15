## Purpose

Definir cómo se aplica un descuento manual, general para la venta o propio de una línea, sobre el resultado de los descuentos automáticos y cómo se decide si el usuario puede otorgarlo solo, si necesita autorización o si no puede, según la configuración de la organización, su permiso y el tope de su rol (DSC-05, DSC-06; ADR-004). La verificación del PIN y el registro en la venta pertenecen al change 18b.

## ADDED Requirements

### Requirement: El descuento manual se aplica sobre el resultado de los automáticos

El descuento manual DEBE expresarse solo como porcentaje, nunca como importe: una fracción de hasta 6 decimales, mayor que cero y no mayor que uno, tanto si es el general de la venta como si es el propio de una línea (`design.md` D11; TR-02). El porcentaje que le corresponde a cada línea DEBE aplicarse después de todos los descuentos automáticos, sobre el importe que estos dejaron en esa línea, redondeado a 2 decimales por línea (DSC-05 paso 5, DSC-07). Cada línea DEBE informar ese descuento con origen `MANUAL`, sin regla, con su porcentaje y su importe (DSC-08). Un porcentaje fuera de ese dominio, general o propio, DEBE rechazarse con `DESCUENTO_MANUAL_INVALIDO`; en particular, un porcentaje propio de cero NO es una forma de excluir una línea (`design.md` D11.1). El servidor y el dispositivo DEBEN calcularlo igual, con casos compartidos.

#### Scenario: Manual del diez por ciento después de los automáticos

- **GIVEN** dos líneas que, después de los descuentos automáticos, quedaron en $135.240,00 y $84.280,00
- **WHEN** se aplica un descuento manual general de `0.100000` y ninguna línea tiene porcentaje propio
- **THEN** las líneas reciben $13.524,00 y $8.428,00 de origen `MANUAL`
- **AND** sus netos quedan en $121.716,00 y $75.852,00
- **Regla:** DSC-05 (paso 5); DSC-07; DSC-08

#### Scenario: Manual sin descuentos automáticos

- **GIVEN** una línea de bruto $31.250,00 sin reglas aplicables
- **WHEN** se aplica un descuento manual de `0.050000`
- **THEN** la línea recibe $1.562,50 de origen `MANUAL` y su neto es $29.687,50
- **Regla:** DSC-05 (paso 5); PRC-22 (ejemplo de `01` §7.3)

#### Scenario: El manual se redondea por línea

- **GIVEN** una línea que quedó en $1.433,33
- **WHEN** se aplica un descuento manual de `0.050000`
- **THEN** la línea recibe $71,67
- **Regla:** DSC-07; TR-03

#### Scenario: Porcentaje fuera de dominio

- **GIVEN** una venta
- **WHEN** se pide un descuento manual general de `0`, negativo, mayor que `1`, con siete decimales o como número de punto flotante
- **THEN** se rechaza con `DESCUENTO_MANUAL_INVALIDO` y no se calcula nada
- **Regla:** TR-02; INV-03

#### Scenario: Porcentaje propio de una línea fuera de dominio

- **GIVEN** una venta con un descuento manual general válido de `0.050000`
- **WHEN** una de sus líneas trae un porcentaje propio de `0`, negativo, mayor que `1`, con siete decimales o como número de punto flotante
- **THEN** se rechaza con `DESCUENTO_MANUAL_INVALIDO` y no se calcula nada, tampoco para las demás líneas
- **Regla:** TR-02; INV-03; `design.md` D11, D11.1

#### Scenario: Sin descuento manual

- **GIVEN** una venta con descuentos automáticos, sin descuento manual general y sin porcentaje propio en ninguna línea
- **WHEN** se calculan los descuentos
- **THEN** ninguna línea tiene un descuento de origen `MANUAL`
- **AND** el mayor porcentaje manual de la venta se informa como nulo
- **Regla:** DSC-05

### Requirement: El porcentaje propio de una línea reemplaza al general en esa línea

Una venta PUEDE llevar un porcentaje manual general y, además, un porcentaje manual propio en cualquiera de sus líneas; los dos son opcionales (`design.md` D11). Cada línea DEBE llevar a lo sumo un descuento de origen `MANUAL`: el de su porcentaje propio si lo tiene; si no, el del general; si no hay ninguno de los dos, ninguno. El porcentaje propio DEBE reemplazar al general en esa línea, sea mayor o menor que él: NO DEBEN sumarse ni aplicarse uno sobre el otro. El cálculo DEBE informar, junto con el resultado por línea, el mayor porcentaje manual que quedó aplicado en alguna línea de la venta, o nulo si ninguna lleva descuento manual; un general que quedó reemplazado en todas las líneas NO cuenta para ese máximo.

#### Scenario: El porcentaje de la línea reemplaza al general

- **GIVEN** dos líneas que, después de los descuentos automáticos, quedaron en $135.240,00 ("Vino A") y $84.280,00 ("Vino B")
- **WHEN** se aplica un descuento manual general de `0.050000` y "Vino A" trae un porcentaje propio de `0.100000`
- **THEN** "Vino A" recibe un solo descuento `MANUAL`, de porcentaje `0.100000` e importe $13.524,00, y queda en $121.716,00
- **AND** "Vino B" recibe un solo descuento `MANUAL`, de porcentaje `0.050000` e importe $4.214,00, y queda en $80.066,00
- **AND** el mayor porcentaje manual de la venta es `0.100000`
- **Regla:** DSC-05 (paso 5); DSC-07; DSC-08; `design.md` D11

#### Scenario: Los porcentajes no se suman ni se encadenan

- **GIVEN** la venta del escenario anterior
- **WHEN** se lee el resultado de "Vino A"
- **THEN** su descuento manual es $13.524,00 (10% de $135.240,00), no $20.286,00 (15%) ni $19.609,80 (5% y después 10%)
- **Regla:** `design.md` D11

#### Scenario: Un porcentaje propio menor que el general también lo reemplaza

- **GIVEN** las mismas dos líneas, en $135.240,00 y $84.280,00
- **WHEN** se aplica un descuento manual general de `0.100000` y "Vino B" trae un porcentaje propio de `0.030000`
- **THEN** "Vino A" recibe $13.524,00 y "Vino B" recibe $2.528,40, con neto $81.751,60
- **AND** el mayor porcentaje manual de la venta es `0.100000`
- **Regla:** DSC-05 (paso 5); `design.md` D11

#### Scenario: Porcentaje propio sin descuento general

- **GIVEN** las mismas dos líneas y ningún descuento manual general
- **WHEN** "Vino A" trae un porcentaje propio de `0.100000`
- **THEN** "Vino A" recibe $13.524,00 de origen `MANUAL` y "Vino B" no tiene ningún descuento de origen `MANUAL`
- **AND** el mayor porcentaje manual de la venta es `0.100000`
- **Regla:** DSC-05 (paso 5); `design.md` D11

#### Scenario: El general reemplazado en todas las líneas no cuenta para el máximo

- **GIVEN** las mismas dos líneas
- **WHEN** se aplica un descuento manual general de `0.100000`, "Vino A" trae un porcentaje propio de `0.030000` y "Vino B" uno de `0.020000`
- **THEN** las líneas reciben $4.057,20 y $1.685,60
- **AND** el mayor porcentaje manual de la venta es `0.030000`
- **Regla:** `design.md` D11, D12

### Requirement: El descuento manual exige que la organización lo habilite y el permiso del usuario

La evaluación de un descuento manual DEBE rechazarlo con `DESCUENTO_MANUAL_DESHABILITADO` si la organización no lo tiene habilitado, y con `PERMISO_REQUERIDO` si el usuario no tiene `DESCUENTO_MANUAL` (DSC-06; `01` §4, §19). Si la organización exige motivo en el descuento manual y no se indica uno, DEBE rechazarlo con `MOTIVO_REQUERIDO`; mientras ese parámetro esté sin definir, el motivo NO es obligatorio (`design.md` D14). La evaluación DEBE hacerse una sola vez por venta, con un único motivo que cubre el porcentaje general y los propios de las líneas (`design.md` D11.2). Una venta sin ningún descuento manual NO se evalúa. La evaluación NO DEBE escribir nada.

#### Scenario: Organización con el descuento manual deshabilitado

- **GIVEN** una organización con el descuento manual deshabilitado y un Vendedor con `DESCUENTO_MANUAL`
- **WHEN** se evalúa un descuento manual de `0.030000`
- **THEN** se rechaza con `DESCUENTO_MANUAL_DESHABILITADO`
- **Regla:** DSC-06; `01` §4

#### Scenario: Usuario sin el permiso

- **GIVEN** un usuario del rol Administración, que no tiene `DESCUENTO_MANUAL`
- **WHEN** se evalúa un descuento manual
- **THEN** se rechaza con `PERMISO_REQUERIDO`
- **Regla:** DSC-06; SEG-06; `01` §19

#### Scenario: Motivo obligatorio y ausente

- **GIVEN** una organización que exige motivo en el descuento manual
- **WHEN** se evalúa un descuento manual sin motivo
- **THEN** se rechaza con `MOTIVO_REQUERIDO`
- **Regla:** `01` §4; DSC-08

#### Scenario: Parámetro de motivo sin definir

- **GIVEN** una organización con la obligatoriedad de motivo sin definir
- **WHEN** se evalúa un descuento manual sin motivo, dentro del tope
- **THEN** se acepta
- **Regla:** `01` §4; `design.md` D14

### Requirement: El tope del rol decide si el descuento manual necesita autorización

El tope aplicable a un usuario DEBE ser su tope propio cuando lo tiene definido y el de su rol cuando no. El porcentaje que se compara contra el tope DEBE ser el mayor porcentaje manual que quedó aplicado en alguna línea de la venta, sea el general o el propio de una línea (`design.md` D11, D12). Si ese porcentaje es menor o igual al tope aplicable, el descuento manual de toda la venta DEBE aceptarse sin autorización. Si es mayor, una sola autorización DEBE cubrir toda la venta, y DEBE aceptarse solo si el propio usuario tiene `AUTORIZAR_DESCUENTO` o si lo autoriza otro usuario que tiene `AUTORIZAR_DESCUENTO`; en otro caso DEBE rechazarse con `AUTORIZACION_REQUERIDA` (DSC-06). El tope se compara contra el descuento manual, no contra los descuentos automáticos ni contra el descuento total de la venta. Quien autoriza con `AUTORIZAR_DESCUENTO` NO queda limitado por su propio tope (`design.md` D12). El resultado DEBE informar el tope aplicado, si hizo falta autorización, la forma de resolución (`DENTRO_DEL_TOPE`, `PERMISO_PROPIO` o `AUTORIZADO_POR_SUPERVISOR`) y el autorizador, para que la venta los registre (DSC-08, SEG-05).

#### Scenario: Dentro del tope

- **GIVEN** un Vendedor cuyo rol tiene tope `0.050000`
- **WHEN** se evalúa un descuento manual de `0.030000`
- **THEN** se acepta sin autorización, con resolución `DENTRO_DEL_TOPE` y sin autorizador
- **Regla:** DSC-06

#### Scenario: Igual al tope

- **GIVEN** un Vendedor cuyo rol tiene tope `0.050000`
- **WHEN** se evalúa un descuento manual de `0.050000`
- **THEN** se acepta sin autorización
- **Regla:** DSC-06

#### Scenario: Supera el tope sin autorización

- **GIVEN** un Vendedor con tope `0.050000` y sin `AUTORIZAR_DESCUENTO`
- **WHEN** se evalúa un descuento manual de `0.100000` sin autorizador
- **THEN** se rechaza con `AUTORIZACION_REQUERIDA`
- **Regla:** DSC-06

#### Scenario: El tope se compara contra el mayor porcentaje de la venta

- **GIVEN** un Vendedor con tope `0.050000` y sin `AUTORIZAR_DESCUENTO`, y una venta con descuento manual general de `0.050000` y una línea con porcentaje propio de `0.100000`
- **WHEN** se evalúa el descuento manual de la venta, cuyo mayor porcentaje es `0.100000`, sin autorizador
- **THEN** se rechaza con `AUTORIZACION_REQUERIDA`, aunque el general por sí solo está dentro del tope
- **Regla:** DSC-06; `design.md` D11, D12

#### Scenario: Una sola autorización cubre toda la venta

- **GIVEN** la venta del escenario anterior y una Supervisora con `AUTORIZAR_DESCUENTO`
- **WHEN** se evalúa el descuento manual de la venta con la Supervisora como autorizadora
- **THEN** se acepta con una única resolución `AUTORIZADO_POR_SUPERVISOR`, que vale para todas las líneas, incluidas las que llevan el general de `0.050000`
- **Regla:** DSC-06; SEG-05; `design.md` D12

#### Scenario: Un porcentaje propio menor no dispara la autorización

- **GIVEN** un Vendedor con tope `0.050000` y una venta con descuento manual general de `0.050000` y una línea con porcentaje propio de `0.030000`
- **WHEN** se evalúa el descuento manual de la venta, cuyo mayor porcentaje es `0.050000`
- **THEN** se acepta sin autorización, con resolución `DENTRO_DEL_TOPE`
- **Regla:** DSC-06; `design.md` D12

#### Scenario: Solo un porcentaje propio supera el tope

- **GIVEN** un Vendedor con tope `0.050000` y una venta sin descuento manual general, con una línea de porcentaje propio `0.080000`
- **WHEN** se evalúa el descuento manual de la venta sin autorizador
- **THEN** se rechaza con `AUTORIZACION_REQUERIDA`
- **Regla:** DSC-06; `design.md` D12

#### Scenario: Supera el tope con autorización de un supervisor

- **GIVEN** un Vendedor con tope `0.050000` y una Supervisora con `AUTORIZAR_DESCUENTO`
- **WHEN** se evalúa un descuento manual de `0.100000` con la Supervisora como autorizadora
- **THEN** se acepta con resolución `AUTORIZADO_POR_SUPERVISOR` y la Supervisora como autorizadora
- **Regla:** DSC-06; SEG-05

#### Scenario: Supera el tope con permiso propio

- **GIVEN** una Supervisora con tope `0.100000` y `AUTORIZAR_DESCUENTO`
- **WHEN** se evalúa un descuento manual suyo de `0.150000`
- **THEN** se acepta con resolución `PERMISO_PROPIO` y ella misma como autorizadora
- **Regla:** DSC-06

#### Scenario: El autorizador no tiene el permiso

- **GIVEN** un Vendedor con tope `0.050000` y otro Vendedor sin `AUTORIZAR_DESCUENTO`
- **WHEN** se evalúa un descuento manual de `0.100000` con el segundo como autorizador
- **THEN** se rechaza con `AUTORIZADOR_SIN_PERMISO`
- **Regla:** DSC-06; SEG-06

#### Scenario: El autorizador no queda limitado por su tope

- **GIVEN** un Vendedor con tope `0.050000` y una Supervisora con `AUTORIZAR_DESCUENTO` y tope `0.100000`
- **WHEN** se evalúa un descuento manual de `0.200000` con la Supervisora como autorizadora
- **THEN** se acepta
- **Regla:** DSC-06; `01` §19 ("Superar tope de descuento"); `design.md` D12

#### Scenario: El tope propio del usuario manda sobre el del rol

- **GIVEN** un Vendedor con tope propio `0.080000` cuyo rol tiene tope `0.050000`
- **WHEN** se evalúa un descuento manual de `0.070000`
- **THEN** se acepta sin autorización, con tope aplicado `0.080000`
- **Regla:** DSC-06; `03` §4 (`tope_descuento_override`)

#### Scenario: Administrador sin tope

- **GIVEN** un Administrador, cuyo rol tiene tope `1.000000`
- **WHEN** se evalúa un descuento manual de `0.400000`
- **THEN** se acepta sin autorización
- **Regla:** DSC-06; `01` §19 ("sin tope")

#### Scenario: Autorizador de otra organización

- **GIVEN** un Vendedor de la organización A y una Supervisora de la organización B
- **WHEN** se evalúa en A un descuento manual sobre el tope con esa Supervisora como autorizadora
- **THEN** la autorizadora no se encuentra y el descuento no se acepta
- **Regla:** INV-21; SEG-07

#### Scenario: Vendedor con el tope de la plantilla sin definir

- **GIVEN** un Vendedor cuyo rol conserva el tope `0.000000` con que nace la plantilla
- **WHEN** se evalúa un descuento manual de `0.010000` sin autorizador
- **THEN** se rechaza con `AUTORIZACION_REQUERIDA`
- **Regla:** DSC-06; `design.md` D13

### Requirement: La evaluación del tope es la misma en el servidor y en el dispositivo

La decisión de tope y autorización DEBE existir como función pura en el servidor y en el dispositivo, con casos compartidos que ejecutan las dos suites y que se agregan antes que el código (`02` §10.4, ADR-016). El servidor DEBE repetir la evaluación aunque el dispositivo ya la haya hecho (TR-10).

#### Scenario: Casos compartidos de tope y autorización

- **GIVEN** los casos compartidos del descuento manual
- **WHEN** se ejecutan la suite del servidor y la del dispositivo
- **THEN** ambas corren los mismos casos y cubren dentro del tope, igual al tope, sobre el tope sin autorización, con permiso propio, con autorizador, autorizador sin permiso, organización deshabilitada y usuario sin permiso
- **AND** los casos del cálculo cubren el porcentaje propio que reemplaza al general y el mayor porcentaje manual que el cálculo entrega para la evaluación
- **Regla:** DSC-06; `02` §10.4; ADR-016

#### Scenario: El servidor no confía en la evaluación del dispositivo

- **GIVEN** un descuento manual que el dispositivo dio por permitido
- **WHEN** el servidor lo evalúa con los datos vigentes del usuario
- **THEN** obtiene su propio resultado, sin usar el que informó el dispositivo
- **Regla:** TR-10; SEG-06
