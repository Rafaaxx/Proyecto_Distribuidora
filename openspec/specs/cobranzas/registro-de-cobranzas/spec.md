# Cobranzas - Registro de cobranzas

## Purpose

Definir la cobranza independiente de un cliente: su registro por comando con uno o más medios, con y sin conexión, su efecto en la cuenta corriente del cliente, la jornada que la recibe y sus consultas (COB-01 a COB-04, CC-05, INV-08, INV-17). Escrita con lo aprobado el 2026-10-15 en `design.md` D1 a D5, D8, D12, D16 y D18 (opción A) y D13 (opción C).

## Requirements

### Requirement: Una cobranza se registra por comando con uno o más medios

El sistema DEBE registrar una cobranza con el comando `COBRANZA_REGISTRAR` v1 (con `Operation-Id`; modos `ONLINE` y `OFFLINE`), que indica el identificador de la cobranza generado por quien la origina, cliente, importe, de 1 a 20 medios de pago y una observación opcional de hasta 500 caracteres (COB-01, `design.md` D2). El importe DEBE ser mayor que cero con 2 decimales (`IMPORTE_INVALIDO`). La cobranza nace `CONFIRMADA`, con origen `INDEPENDIENTE` y sin venta, y NO DEBE editarse (TR-06). Su momento es el `occurred_at` del comando (`design.md` D3). La observación se guarda recortada y vacía equivale a no informarla. Un identificador de cobranza ya usado por otra operación DEBE rechazarse con `COBRANZA_DUPLICADA`.

#### Scenario: Cobranza con efectivo y transferencia
- **GIVEN** el cliente `Kiosco La Esquina` con saldo `"150000.00"` y los medios activos "Efectivo" y "Transferencia" (exige referencia)
- **WHEN** se envía `COBRANZA_REGISTRAR` por `"50000.00"` con `"30000.00"` en efectivo y `"20000.00"` por transferencia con referencia `"0042"`
- **THEN** existe una cobranza `CONFIRMADA` de origen `INDEPENDIENTE` por `"50000.00"` con dos medios, y el saldo del cliente es `"100000.00"`
- **Regla:** COB-01; COB-02; COB-03; INV-08

#### Scenario: Observación recortada
- **WHEN** se registra una cobranza de `"20000.00"` en efectivo con observación `"  paga facturas de septiembre  "`
- **THEN** la cobranza guarda la observación `"paga facturas de septiembre"`
- **Regla:** COB-01; `design.md` D2

#### Scenario: Importe inválido
- **WHEN** el importe es `"0.00"`, es negativo, tiene tres decimales (`"50000.001"`) o llega como número JSON
- **THEN** se rechaza (`IMPORTE_INVALIDO`, o 422 por esquema para el número) y no queda cobranza, medio ni movimiento
- **Regla:** TR-01; COB-01; INV-03

#### Scenario: Sin medios o con demasiados
- **WHEN** la lista de medios está vacía o tiene 21 elementos
- **THEN** se rechaza con `MEDIOS_INVALIDOS` y no queda ningún efecto
- **Regla:** COB-01; `design.md` D2

#### Scenario: Observación demasiado larga
- **WHEN** la observación tiene 501 caracteres, y otra cobranza la trae de exactamente 500
- **THEN** la de 501 se rechaza con un error de validación (422) sin ningún efecto; la de 500 se acepta y se guarda completa
- **Regla:** `design.md` D2

#### Scenario: Identificador de cobranza repetido
- **GIVEN** una cobranza ya registrada con el identificador X
- **WHEN** llega otro comando, con otro `operation_id`, que trae el mismo identificador X
- **THEN** se rechaza con `COBRANZA_DUPLICADA` y la cobranza original no cambia
- **Regla:** `02` §9; SYN-06

#### Scenario: Doble envío
- **GIVEN** una cobranza aceptada
- **WHEN** se reenvía el mismo comando con el mismo contenido, y después con el mismo `operation_id` y otro importe
- **THEN** el primer reenvío devuelve el resultado original sin una segunda cobranza ni un segundo movimiento; el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

#### Scenario: Permiso faltante con conexión
- **GIVEN** un usuario sin `REGISTRAR_COBRANZA`
- **WHEN** envía `COBRANZA_REGISTRAR` en modo `ONLINE`
- **THEN** recibe 403 y no queda ningún efecto
- **Regla:** SEG-06; `01` §19

#### Scenario: Una falla a mitad no deja nada
- **GIVEN** una falla inyectada después de insertar los medios y antes del movimiento de cuenta
- **WHEN** se procesa el comando
- **THEN** no queda cobranza, medio, movimiento ni cambio de saldo
- **Regla:** INV-01

### Requirement: La suma de los medios es igual al importe de la cobranza

La suma de los importes de los medios DEBE ser exactamente igual al importe de la cobranza (INV-08); si no, el comando DEBE rechazarse con `MEDIOS_NO_SUMAN_IMPORTE`, también en modo `OFFLINE`. Cada medio DEBE tener importe mayor que cero de 2 decimales. Con conexión (modo `ONLINE`, por REST o por el lote), cada medio DEBE ser un medio de pago activo de la organización (`MEDIO_PAGO_INACTIVO`) y DEBE traer referencia no vacía cuando el medio la exige (`REFERENCIA_OBLIGATORIA`), igual que el pago a proveedor; sin conexión, esos dos casos se aceptan con observación (requisito "Una cobranza sin conexión nunca se rechaza por reglas de negocio"). El mismo medio PUEDE repetirse. Un error de medio DEBE indicar qué medio lo causó. Las reglas y los códigos son los mismos que los del pago a proveedor (`design.md` D17).

#### Scenario: INV-08 — medios que no suman el importe
- **WHEN** el importe es `"50000.00"` y los medios suman `"49000.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; COB-02

#### Scenario: INV-08 — propiedad sobre cobranzas aceptadas
- **GIVEN** importes y repartos de medios aleatorios válidos, aceptados con y sin conexión
- **WHEN** se suman con SQL los medios guardados de cada cobranza
- **THEN** la suma es igual a su importe en todas
- **Regla:** INV-08

#### Scenario: Medio que exige referencia sin referencia
- **WHEN** se cobra por transferencia sin referencia, o con una referencia de solo espacios, con conexión
- **THEN** se rechaza con `REFERENCIA_OBLIGATORIA` indicando el medio
- **Regla:** COB-02; `01` §4

#### Scenario: Medio inactivo con conexión
- **WHEN** uno de los medios está inactivo y el comando es `ONLINE`, por REST o por el lote
- **THEN** se rechaza con `MEDIO_PAGO_INACTIVO` indicando el medio, sin observación `MEDIO_INACTIVO` y sin ningún efecto
- **Regla:** TR-09; `design.md` D13

#### Scenario: Mismo medio repetido
- **WHEN** se cobran `"50000.00"` con dos medios "Efectivo" de `"25000.00"`
- **THEN** se acepta con dos medios
- **Regla:** COB-01; `design.md` D2

#### Scenario: Medio de otra organización
- **WHEN** uno de los medios pertenece a otra organización
- **THEN** la respuesta es 404 y no queda ningún efecto
- **Regla:** INV-21; SEG-07

### Requirement: La cobranza registra su propio crédito en la cuenta corriente del cliente

Toda cobranza aceptada DEBE registrar, en la misma transacción, un movimiento `COBRANZA` que reduce el saldo del cliente por el importe completo, con la cobranza como operación de origen y el `occurred_at` del comando (CC-01, CC-05, COB-03). La cobranza NO DEBE imputarse a ninguna venta. Desde la primera cobranza, la cuenta del cliente ya no admite saldo inicial (`CUENTA_CON_OPERACIONES`, CC-08). El saldo materializado DEBE ser igual a la suma del libro (INV-13).

#### Scenario: El crédito lleva la cobranza como origen
- **WHEN** se acepta la cobranza de `"50000.00"` a `Kiosco La Esquina`
- **THEN** su cuenta tiene un movimiento `COBRANZA`, `REDUCE`, por `"50000.00"`, con la cobranza como origen y el momento del comando
- **Regla:** CC-01; CC-05; COB-03

#### Scenario: Saldo inicial después de una cobranza
- **GIVEN** un cliente con una cobranza
- **WHEN** se intenta registrarle un saldo inicial
- **THEN** se rechaza con `CUENTA_CON_OPERACIONES`
- **Regla:** CC-08

#### Scenario: INV-13 — saldo igual a la suma del libro
- **GIVEN** secuencias aleatorias de saldos iniciales, cobranzas y anulaciones sobre varios clientes
- **WHEN** se compara el saldo materializado con la suma de sus movimientos
- **THEN** coinciden en cada cliente
- **Regla:** INV-13

#### Scenario: Dos cobranzas simultáneas al mismo cliente
- **GIVEN** `Kiosco La Esquina` con saldo `"150000.00"`
- **WHEN** dos sesiones registran a la vez cobranzas de `"50000.00"` y confirman
- **THEN** el saldo es `"50000.00"` y hay dos movimientos `COBRANZA`
- **Regla:** INV-13; `02` §7.3

### Requirement: Una cobranza puede dejar saldo a favor del cliente

El sistema DEBE aceptar una cobranza de cualquier importe mayor que cero, aunque supere la deuda del cliente: el saldo negativo queda como saldo a favor y la próxima venta lo absorbe sin operación nueva. El servidor NO DEBE rechazar ni observar la cobranza por ese motivo (COB-03, `design.md` D5).

#### Scenario: Pago de más
- **GIVEN** `Kiosco La Esquina` con saldo `"150000.00"`
- **WHEN** se registra una cobranza de `"160000.00"`
- **THEN** se acepta sin observaciones y el saldo es `"-10000.00"`
- **Regla:** COB-03; CC-04

#### Scenario: Cliente sin deuda
- **GIVEN** un cliente con saldo `"0.00"`
- **WHEN** se registra una cobranza de `"20000.00"`
- **THEN** se acepta y el saldo es `"-20000.00"`
- **Regla:** COB-03; `design.md` D5

### Requirement: Se cobra a un cliente de cualquier estado, salvo al consumidor final

Con conexión, el sistema DEBE aceptar la cobranza de un cliente `ACTIVO`, `SUSPENDIDO` o `INACTIVO`, y DEBE rechazar la cobranza independiente al consumidor final con `CONSUMIDOR_FINAL_SIN_CUENTA` (`design.md` D4). Un cliente inexistente o de otra organización DEBE responder 404.

#### Scenario: Cliente inactivo con deuda
- **GIVEN** el cliente `Almacén Don Pedro`, `INACTIVO`, con saldo `"12000.00"`
- **WHEN** se le registra una cobranza de `"12000.00"`
- **THEN** se acepta y su saldo es `"0.00"`
- **Regla:** CLI-02; `design.md` D4

#### Scenario: Cliente suspendido
- **GIVEN** un cliente `SUSPENDIDO` con deuda
- **WHEN** se le registra una cobranza
- **THEN** se acepta
- **Regla:** CLI-02; `design.md` D4

#### Scenario: Consumidor final
- **WHEN** se intenta registrar una cobranza independiente al consumidor final con conexión
- **THEN** se rechaza con `CONSUMIDOR_FINAL_SIN_CUENTA` y no queda ningún efecto
- **Regla:** CLI-03; CC-08; `design.md` D4

#### Scenario: Cliente de otra organización
- **WHEN** se envía una cobranza con un cliente de otra organización
- **THEN** la respuesta es 404 y no queda ningún efecto
- **Regla:** INV-21; SEG-07

### Requirement: Una cobranza con conexión lleva la jornada abierta de quien la registra

En modo `ONLINE`, si el usuario y el dispositivo de la sesión tienen una jornada `ABIERTA`, la cobranza DEBE quedar asociada a esa jornada; si no, queda sin jornada. Si el sobre trae una jornada distinta de esa, el comando DEBE rechazarse con `JORNADA_AJENA` (`design.md` D8).

#### Scenario: Vendedor con jornada abierta
- **GIVEN** un vendedor con la jornada J `ABIERTA` en su dispositivo
- **WHEN** registra con conexión una cobranza de `"50000.00"`
- **THEN** la cobranza queda asociada a J
- **Regla:** RUT-07; `design.md` D8

#### Scenario: Administración sin jornada
- **GIVEN** un usuario sin jornada no cerrada
- **WHEN** registra una cobranza con conexión
- **THEN** la cobranza queda sin jornada
- **Regla:** `design.md` D8

#### Scenario: Jornada en rendición
- **GIVEN** un vendedor con su jornada `EN_RENDICION`
- **WHEN** registra con conexión una cobranza
- **THEN** la cobranza queda sin jornada
- **Regla:** `design.md` D8

#### Scenario: Jornada del sobre que no es la propia
- **GIVEN** un vendedor con la jornada J abierta y otra jornada K de otro vendedor
- **WHEN** envía una cobranza `ONLINE` cuyo sobre nombra K
- **THEN** se rechaza con `JORNADA_AJENA` y no queda ningún efecto
- **Regla:** `design.md` D8

### Requirement: Una cobranza sin conexión nunca se rechaza por reglas de negocio

En modo `OFFLINE`, `COBRANZA_REGISTRAR` DEBE rechazarse solo por contenido malformado (esquema, importe, cantidad de medios o medios que no suman el importe), por un cliente o un medio inexistente o de otra organización, por un identificador de cobranza repetido o por su jornada (requisito de `sync/lote-de-comandos`). Todo lo demás DEBE aceptarse: cualquier estado del cliente (sin observación) y la falta de permiso (con `PERMISO_REVOCADO`). El consumidor final DEBE aceptarse con la observación `CLIENTE_NO_HABILITADO`. Cada línea cuyo medio de pago está inactivo al sincronizar DEBE aceptarse con una observación `MEDIO_INACTIVO`, y cada línea cuyo medio exige referencia (según su configuración al sincronizar) y llega sin referencia o con solo espacios DEBE aceptarse con una observación `REFERENCIA_FALTANTE`, guardando la referencia nula. El detalle de esas dos observaciones DEBE indicar la línea (`medio`, su posición desde 0), el medio de pago (`medio_pago_id` y `nombre`) y el `importe` de la línea; una línea PUEDE llevar las dos, y dos líneas afectadas dan dos observaciones. Un comando con alguna observación queda `ACEPTADO_CON_OBSERVACIONES` (SYN-05, SYN-07, INV-17, `design.md` D13). La cobranza DEBE quedar asociada a la jornada del sobre.

#### Scenario: INV-17 — medio desactivado después de abrir la jornada
- **GIVEN** la vendedora cobró `"10000.00"` con "Billetera" sin conexión y después la administración desactivó "Billetera"
- **WHEN** sincroniza la cobranza en modo `OFFLINE` con su jornada abierta
- **THEN** se acepta como `ACEPTADO_CON_OBSERVACIONES`, el saldo del cliente baja `"10000.00"` y queda una observación `MEDIO_INACTIVO` pendiente cuyo detalle indica la línea `0`, el medio "Billetera" y el importe `"10000.00"`
- **Regla:** SYN-05; SYN-07; INV-17; `design.md` D13

#### Scenario: Medio inactivo en una de varias líneas
- **GIVEN** "Billetera" inactivo y "Efectivo" activo
- **WHEN** llega en modo `OFFLINE` una cobranza de `"30000.00"` con `"20000.00"` en efectivo y `"10000.00"` con "Billetera"
- **THEN** se acepta con una sola observación `MEDIO_INACTIVO`, que indica la línea `1` y el medio "Billetera", y se guardan las dos líneas
- **Regla:** SYN-05; SYN-07; `design.md` D13

#### Scenario: INV-17 — referencia faltante
- **GIVEN** el medio "Transferencia", activo, que exige referencia
- **WHEN** llega en modo `OFFLINE` una cobranza de `"20000.00"` por transferencia sin referencia, o con una referencia de solo espacios
- **THEN** se acepta como `ACEPTADO_CON_OBSERVACIONES`, el saldo baja `"20000.00"`, la línea se guarda con referencia nula y queda una observación `REFERENCIA_FALTANTE` cuyo detalle indica la línea `0`, el medio "Transferencia" y el importe `"20000.00"`
- **Regla:** SYN-05; SYN-07; INV-17; `design.md` D13

#### Scenario: Medio inactivo y sin referencia en la misma línea
- **GIVEN** "Transferencia" exige referencia y se desactivó después de abrir la jornada
- **WHEN** llega en modo `OFFLINE` una cobranza por transferencia sin referencia
- **THEN** se acepta con dos observaciones sobre la línea `0`: `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`
- **Regla:** SYN-05; SYN-07; `design.md` D13

#### Scenario: Observaciones de medio junto con otras
- **GIVEN** un vendedor al que le quitaron `REGISTRAR_COBRANZA` y "Billetera" inactivo
- **WHEN** sincroniza en modo `OFFLINE` una cobranza con "Billetera"
- **THEN** se acepta con `PERMISO_REVOCADO` y `MEDIO_INACTIVO`; un reenvío del mismo comando devuelve el resultado original con las mismas dos observaciones, sin duplicarlas
- **Regla:** SYN-07; SYN-10; INV-06; `design.md` D13

#### Scenario: Medio activo con su referencia, sin observación
- **WHEN** llega en modo `OFFLINE` una cobranza con medios activos y la referencia que cada uno exige, de un cliente activo, enviada por un usuario con el permiso vigente y la jornada abierta
- **THEN** se acepta como `ACEPTADO` sin observaciones
- **Regla:** SYN-04; `design.md` D13

#### Scenario: Cliente inactivo sin conexión
- **WHEN** llega en modo `OFFLINE` una cobranza de un cliente `INACTIVO`
- **THEN** se acepta sin observación por el estado del cliente
- **Regla:** SYN-05; CLI-02; `design.md` D4

#### Scenario: INV-17 — consumidor final
- **WHEN** llega en modo `OFFLINE` una cobranza independiente al consumidor final
- **THEN** se acepta con la observación `CLIENTE_NO_HABILITADO`
- **Regla:** SYN-05; SYN-07; INV-17

#### Scenario: INV-08 también sin conexión
- **WHEN** llega en modo `OFFLINE` una cobranza de `"50000.00"` cuyos medios suman `"49000.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; SYN-06

#### Scenario: Cliente inexistente sin conexión
- **WHEN** llega en modo `OFFLINE` una cobranza para un cliente que no existe en la organización
- **THEN** se rechaza como dependencia inexistente y no queda ningún efecto
- **Regla:** SYN-06

#### Scenario: Medio inexistente o de otra organización sin conexión
- **WHEN** llega en modo `OFFLINE` una cobranza con un medio de pago que no existe en la organización
- **THEN** se rechaza como dependencia inexistente, sin observación `MEDIO_INACTIVO` y sin ningún efecto
- **Regla:** SYN-06; INV-21; `design.md` D13

### Requirement: Las cobranzas se consultan por organización

El sistema DEBE ofrecer `GET /api/v1/cobranzas` (filtros de cliente, estado, usuario, jornada y fechas de negocio; cursor y límite) y `GET /api/v1/cobranzas/{id}` (medios, jornada, anulación y observaciones), con `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`, sobre todas las cobranzas de la organización, con importes como string (`design.md` D14). Una cobranza de otra organización DEBE responder 404.

#### Scenario: Listado del día
- **GIVEN** tres cobranzas de hoy y una de ayer
- **WHEN** un usuario con `REGISTRAR_COBRANZA` lista con el filtro de hoy
- **THEN** recibe las tres de hoy, de la más reciente a la más antigua, con sus importes como string
- **Regla:** COB-01; INV-03

#### Scenario: Detalle con medios
- **WHEN** se abre el detalle de la cobranza de `"50000.00"`
- **THEN** trae sus dos medios con importe y referencia, el estado y la jornada
- **Regla:** COB-01; COB-02

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `REGISTRAR_COBRANZA` ni `ANULAR_COBRANZA`
- **WHEN** pide el listado
- **THEN** recibe 403
- **Regla:** SEG-06

#### Scenario: Cobranza de otra organización
- **WHEN** se pide el detalle de una cobranza de otra organización
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
