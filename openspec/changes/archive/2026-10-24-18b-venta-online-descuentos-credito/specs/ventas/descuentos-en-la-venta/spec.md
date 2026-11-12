## Purpose

Define cómo la venta aplica las reglas de descuento y el descuento manual (general y propio por línea), cómo controla el tope, el motivo y la autorización, qué pasa si los descuentos difieren con y sin conexión, y cómo quedan guardados en cada línea (DSC-05 a DSC-09, ADR-050).

## ADDED Requirements

### Requirement: La venta aplica las reglas vigentes al momento de la venta

Al confirmar una venta, el sistema DEBE calcular los descuentos de cada línea con las reglas `ACTIVA` vigentes al `occurred_at` de la venta, en el orden de DSC-05, y DEBE aplicar después el descuento manual: el porcentaje propio de la línea si lo tiene y, si no, el general de la venta. Los descuentos que redondean a $0,00 NO DEBEN informarse (DSC-07). El neto de cada línea DEBE ser el bruto menos la suma de sus descuentos (VTA-04, INV-14).

#### Scenario: Regla por volumen sobre la venta

- **GIVEN** la regla activa "cajas equivalentes ≥ 20 → 5 %" y una venta de 20 cajas de Vino A
- **WHEN** se confirma con conexión con los descuentos que mostró la pantalla
- **THEN** cada línea elegible guarda un descuento `AUTOMATICO` de 5 % con la regla y su importe, y el neto es el bruto menos ese descuento
- **Regla:** DSC-03; DSC-05; DSC-07; INV-14

#### Scenario: 19 cajas y 5 unidades no alcanzan la regla

- **GIVEN** la misma regla y 19 cajas + 5 unidades de un vino x6 (19,83 cajas equivalentes)
- **WHEN** se confirma la venta
- **THEN** ninguna línea lleva descuento automático
- **Regla:** DSC-03

#### Scenario: Una regla pausada o vencida no se aplica

- **GIVEN** una regla pausada antes del momento de la venta
- **WHEN** se confirma una venta que la cumpliría
- **THEN** la venta no lleva ese descuento
- **Regla:** DSC-01; DSC-05

#### Scenario: El propio reemplaza al general

- **GIVEN** un general de 5 % y un propio de 10 % en la línea del vino
- **WHEN** se confirma la venta
- **THEN** la línea del vino lleva un único `MANUAL` de 10 % y las demás uno de 5 %, cada uno sobre el importe que dejaron los automáticos
- **Regla:** DSC-05; DSC-08

### Requirement: Quien vende puede leer las reglas vigentes

Con `VENDER` (sin `GESTIONAR_DESCUENTOS`, DSC-04), el sistema DEBE ofrecer una lectura de las reglas `ACTIVA` y vigentes en el momento de la consulta, con su nombre, tipo, medida, operador, umbral, acción (porcentaje o importe fijo, como texto), si es acumulable, su prioridad y sus alcances, por prioridad y antigüedad. NO DEBE incluir borradores, pausadas, programadas ni vencidas, ni reglas de otra organización. La pantalla calcula con la gemela del motor y el servidor decide al confirmar (TR-10).

#### Scenario: El vendedor lee las reglas vigentes sin poder gestionarlas

- **GIVEN** un usuario con `VENDER` y sin `GESTIONAR_DESCUENTOS`, una regla activa y vigente, y otra pausada
- **WHEN** consulta las reglas aplicables
- **THEN** recibe solo la activa y vigente, con su nombre y sus alcances
- **Regla:** DSC-01; DSC-04; DSC-05

#### Scenario: Las reglas de otra organización no figuran

- **GIVEN** una regla activa de otra organización
- **WHEN** un vendedor consulta las reglas aplicables
- **THEN** la respuesta no la incluye
- **Regla:** INV-21

### Requirement: Con conexión se confirma el descuento que vio el usuario

Con conexión, el sistema DEBE recalcular los descuentos y DEBE rechazar la venta con `DESCUENTO_DIFIERE` (409) si alguna línea difiere de lo enviado en origen, regla, porcentaje o importe, devolviendo los descuentos que calculó el servidor. Un rechazo NO DEBE dejar ninguna fila escrita (INV-01).

#### Scenario: Una regla se activó entre la pantalla y la confirmación

- **GIVEN** una venta armada sin descuento automático y una regla de 5 % activada después
- **WHEN** se confirma con conexión sin ese descuento
- **THEN** se rechaza con `DESCUENTO_DIFIERE` y la respuesta trae el descuento de 5 %
- **AND** no queda venta, movimiento ni cobranza
- **Regla:** DSC-09; INV-01

#### Scenario: Un importe enviado con un centavo de diferencia

- **WHEN** el contenido trae un descuento de `"1562.49"` donde el servidor calcula `"1562.50"`
- **THEN** se rechaza con `DESCUENTO_DIFIERE`
- **Regla:** DSC-09; DSC-07

#### Scenario: Doble envío

- **GIVEN** una venta con descuentos ya confirmada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** devuelve el resultado original y no duplica descuentos
- **Regla:** INV-06; SYN-02

### Requirement: El descuento manual se evalúa una vez por venta contra el tope

El sistema DEBE evaluar el descuento manual una sola vez por venta, con el mayor porcentaje manual que quedó aplicado en alguna línea, en el orden de DSC-06: organización deshabilitada → `DESCUENTO_MANUAL_DESHABILITADO` (409); sin `DESCUENTO_MANUAL` → `PERMISO_REQUERIDO` (403); motivo exigido y ausente → `MOTIVO_REQUERIDO` (422); dentro del tope → se acepta; sobre el tope → permiso propio `AUTORIZAR_DESCUENTO`, o un autorizador con ese permiso y su PIN verificado; si no, `AUTORIZACION_REQUERIDA` o `AUTORIZADOR_SIN_PERMISO` (403). Una sola autorización DEBE cubrir toda la venta y quien autoriza NO DEBE quedar limitado por su propio tope.

#### Scenario: Dentro del tope

- **GIVEN** Pedro (Vendedor, tope 5 %) y un general de 5 %
- **WHEN** confirma con conexión
- **THEN** se acepta sin autorización
- **Regla:** DSC-06

#### Scenario: Sobre el tope con PIN de supervisor

- **GIVEN** Pedro con tope 5 %, un propio de 10 % en una línea y Marta (Supervisor, `AUTORIZAR_DESCUENTO`) que ingresa su PIN correcto
- **WHEN** confirma con conexión
- **THEN** se acepta y cada descuento `MANUAL` guarda a Marta como autorizadora
- **Regla:** DSC-06; DSC-08; SEG-05

#### Scenario: Sobre el tope sin autorización

- **GIVEN** Pedro con tope 5 % y un general de 8 %, sin autorizador
- **WHEN** confirma con conexión
- **THEN** se rechaza con `AUTORIZACION_REQUERIDA` y no queda nada escrito
- **Regla:** DSC-06; INV-01

#### Scenario: Autorizador sin el permiso

- **GIVEN** un autorizador cuyo rol no tiene `AUTORIZAR_DESCUENTO`
- **WHEN** Pedro confirma con 8 % indicando a ese autorizador
- **THEN** se rechaza con `AUTORIZADOR_SIN_PERMISO`
- **Regla:** DSC-06; SEG-06

#### Scenario: El permiso propio se resuelve primero

- **GIVEN** un Supervisor con `AUTORIZAR_DESCUENTO` que vende con 30 % e indica a otro autorizador
- **WHEN** confirma con conexión
- **THEN** se acepta por permiso propio, el autorizador indicado no se registra y su PIN no se verifica
- **Regla:** DSC-06

#### Scenario: Un general reemplazado en todas las líneas no cuenta

- **GIVEN** tope 5 %, general de 10 % y un propio de 3 % en cada línea
- **WHEN** confirma
- **THEN** el máximo es 3 % y pasa sin autorización
- **Regla:** DSC-06

#### Scenario: Organización con el descuento manual deshabilitado

- **GIVEN** la organización con el descuento manual deshabilitado
- **WHEN** se confirma una venta con un general de 2 %
- **THEN** se rechaza con `DESCUENTO_MANUAL_DESHABILITADO` y los descuentos automáticos no cambian ese resultado
- **Regla:** DSC-06

#### Scenario: Autorizador de otra organización

- **WHEN** el contenido nombra un autorizador de otra organización
- **THEN** responde como recurso inexistente (404)
- **Regla:** INV-21; SEG-07

### Requirement: El motivo del descuento manual es uno por venta y del ámbito correcto

Cuando la organización exige motivo, una venta con descuento manual DEBE traer un motivo activo del ámbito `DESCUENTO_MANUAL`, que se copia en cada descuento `MANUAL`. Con conexión, un motivo inactivo o de otro ámbito DEBE rechazarse con `MOTIVO_INVALIDO` (422) y uno inexistente o ajeno, con 404. Sin descuento manual, un motivo enviado NO DEBE guardarse.

#### Scenario: Motivo exigido y presente

- **GIVEN** la organización exige motivo y el motivo activo "Negociación por volumen"
- **WHEN** se confirma una venta con 5 % general y ese motivo
- **THEN** cada descuento `MANUAL` guarda ese motivo
- **Regla:** DSC-06; DSC-08

#### Scenario: Motivo de otro ámbito

- **WHEN** se envía un motivo del ámbito `LISTA_ANTERIOR`
- **THEN** se rechaza con `MOTIVO_INVALIDO`
- **Regla:** DSC-06; TR-09

#### Scenario: Motivo exigido y ausente

- **WHEN** se confirma una venta con descuento manual sin motivo y la organización lo exige
- **THEN** se rechaza con `MOTIVO_REQUERIDO`
- **Regla:** DSC-06

### Requirement: Cada descuento queda guardado en su línea y no cambia

Cada descuento informado DEBE guardarse en la línea con su origen, regla (nula si es manual), porcentaje (nulo si es un importe fijo), importe, motivo y autorizador. Una línea DEBE llevar a lo sumo un descuento `MANUAL`. Los descuentos guardados NO DEBEN modificarse ni borrarse (INV-10).

#### Scenario: A lo sumo un manual por línea

- **WHEN** se intenta guardar un segundo descuento `MANUAL` en la misma línea
- **THEN** la base lo rechaza
- **Regla:** DSC-08

#### Scenario: Los descuentos congelados no se modifican

- **GIVEN** una venta confirmada con descuentos
- **WHEN** el usuario de aplicación intenta modificar o borrar uno
- **THEN** la base lo rechaza por falta de privilegio
- **Regla:** INV-10; INV-05; TR-06

#### Scenario: Una regla de otra organización no se puede referenciar

- **WHEN** se intenta guardar un descuento con una regla de otra organización
- **THEN** la clave foránea compuesta lo rechaza
- **Regla:** INV-02; INV-21

### Requirement: Sin conexión se aceptan los descuentos del dispositivo

Sin conexión, el sistema DEBE congelar los descuentos que registró el dispositivo, sin rechazar la venta por reglas de descuento (SYN-05, INV-17). DEBE recalcular con las reglas vigentes al `occurred_at` y reevaluar el descuento manual con los datos vigentes, y DEBE agregar una sola observación `DESCUENTO_DIFIERE` por venta cuando algo no coincide, con las causas en el detalle (`CALCULO`, `TOPE`, `PERMISO`, `DESHABILITADO`, `MOTIVO`, `AUTORIZADOR_SIN_PERMISO`). Solo DEBE rechazar lo malformado (`TOTALES_INCONSISTENTES`: neto distinto de bruto menos descuentos, más de un manual por línea, importe no positivo, origen y regla incoherentes), lo inexistente (regla, motivo o autorizador inexistentes o ajenos) y un motivo de otro ámbito (`MOTIVO_INVALIDO`).

#### Scenario: El dispositivo usó una regla que ya se pausó

- **GIVEN** una venta sin conexión con un 5 % de una regla pausada antes de su `occurred_at`
- **WHEN** se sincroniza
- **THEN** se acepta con el 5 % congelado y `DESCUENTO_DIFIERE` con causa `CALCULO`
- **Regla:** DSC-09; SYN-05; INV-17

#### Scenario: Le bajaron el tope después de abrir la jornada

- **GIVEN** Pedro dio 5 % sin conexión con tope 5 % y al sincronizar su tope es 3 %
- **WHEN** se sincroniza
- **THEN** se acepta con `DESCUENTO_DIFIERE` causa `TOPE`
- **Regla:** DSC-09; SYN-10; INV-17

#### Scenario: Neto que no cierra

- **WHEN** el total llega distinto de la suma de los netos (bruto menos descuentos de cada línea), o los descuentos de una línea superan su bruto
- **THEN** se rechaza con `TOTALES_INCONSISTENTES` y el lote sigue
- **Regla:** SYN-06; INV-14

#### Scenario: Descuento malformado

- **WHEN** llega un descuento con importe no positivo o con más de dos decimales, un porcentaje fuera de (0, 1], dos manuales en una línea, un automático sin regla o un manual con regla
- **THEN** se rechaza con `TOTALES_INCONSISTENTES` sin dejar nada escrito
- **Regla:** SYN-06; DSC-07; DSC-08

#### Scenario: Motivo inactivo sin conexión

- **WHEN** llega con un motivo `DESCUENTO_MANUAL` desactivado después del bootstrap
- **THEN** se acepta sin observación por el motivo
- **Regla:** SYN-05

#### Scenario: Doble envío por el lote

- **WHEN** el lote reenvía la misma venta con el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones y sin duplicar descuentos
- **Regla:** INV-06; SYN-02
