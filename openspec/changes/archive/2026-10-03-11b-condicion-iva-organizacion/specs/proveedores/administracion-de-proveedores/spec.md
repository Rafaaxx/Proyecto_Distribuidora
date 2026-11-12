## MODIFIED Requirements

### Requirement: Carga de costos de un proveedor con vista previa del costo base
Desde la ficha de un proveedor activo, el usuario con `EDITAR_COSTOS` DEBE poder cargar uno o varios costos en un único envío: por fila, un producto activo del proveedor, una presentación activa de compra de ese producto, el valor, si incluye IVA (solo si la organización computa crédito fiscal, CST-06), la bonificación en porcentaje (se envía como fracción), la vigencia desde (por defecto la fecha de hoy de la organización) y una observación. Si la organización no computa crédito fiscal (`GET /api/v1/configuracion/fiscal`), la fila NO DEBE ofrecer "Incluye IVA", rotula el valor como "Valor pagado" y envía `incluye_iva = false` (`design.md` D4). Cada fila DEBE mostrar el costo base calculado en el cliente con la misma fórmula del servidor antes de enviar. Los importes NO DEBEN convertirse a número de punto flotante para calcular. Tras aceptarse, la pantalla DEBE mostrar el costo base devuelto por el servidor.

#### Scenario: Vista previa de una caja con IVA
- **GIVEN** la fila `Cerveza B` / `Caja x12` con alícuota `21%`, en una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** el usuario escribe `18000` con IVA incluido
- **THEN** la fila muestra costo base `1.239,669421` antes de enviar
- **Regla:** CST-02 (ejemplo 3); ADR-016

#### Scenario: Vista previa de un monotributista
- **GIVEN** la fila `Cerveza B` / `Caja x12` con alícuota `21%`, en una organización `MONOTRIBUTO`
- **WHEN** el usuario escribe `21780` como valor pagado
- **THEN** la fila no ofrece "Incluye IVA", muestra costo base `1.815,000000` y el comando envía `incluye_iva = false`
- **Regla:** CST-02; CST-06; `design.md` D4

#### Scenario: Bonificación en porcentaje
- **GIVEN** la fila `Cerveza B` / `Caja x12`
- **WHEN** el usuario escribe `18000` sin IVA y bonificación `10` %
- **THEN** la fila muestra costo base `1.350,000000` y el comando envía bonificación `"0.100000"`
- **Regla:** CST-02 (ejemplo 4); TR-02

#### Scenario: Carga de dos costos en un envío
- **GIVEN** dos filas válidas (`Caja x12` de `Cerveza B` y `Botella` de `Vino A`)
- **WHEN** el usuario confirma la carga
- **THEN** se envía un único `COSTO_INFORMAR` con los dos costos y, al aceptarse, ambos aparecen en el historial
- **Regla:** CST-05

#### Scenario: Error del servidor en una fila
- **GIVEN** una carga de dos filas cuya segunda el servidor rechaza con `PRESENTACION_INVALIDA` o `INCLUYE_IVA_NO_APLICA`
- **WHEN** llega la respuesta
- **THEN** la pantalla señala la segunda fila, conserva las dos filas cargadas y no muestra ningún costo como registrado
- **Regla:** INV-01; TR-10

#### Scenario: Solo presentaciones de compra
- **GIVEN** `Vino A` con `Botella` (compra) y `Caja x6` (solo venta)
- **WHEN** el usuario elige `Vino A` en una fila
- **THEN** el selector de presentación ofrece `Botella` y no `Caja x6`
- **Regla:** ADR-010; `00` §5

#### Scenario: Tras cargar los costos, la pantalla vuelve a la ficha del proveedor
- **GIVEN** una carga de uno o varios costos que el servidor acepta
- **WHEN** termina el envío
- **THEN** la pantalla navega a la ficha del proveedor, en vez de dejar el formulario intacto sin ninguna señal de éxito
- **Regla:** CST-05; TR-10 (una operación aceptada debe distinguirse claramente de una que no lo fue, para no reenviarse por error)

### Requirement: Historial y costo vigente por producto
La pantalla DEBE mostrar, para un producto, su costo vigente a hoy y el historial de costos informados de la vigencia más reciente a la más antigua, con lo informado (valor, si incluye IVA y bonificación), si se descontó IVA según la regla congelada en cada costo (`computa_credito_fiscal`, CST-06), la alícuota aplicada como porcentaje, el costo base, el usuario y el momento de registro, marcando cuál fila del historial es la vigente. Los importes y costos DEBEN mostrarse formateados sin perder decimales; la alícuota y la bonificación se muestran como porcentaje (TR-02), nunca como fracción.

#### Scenario: Historial con vigente resaltado
- **GIVEN** costos de `Cerveza B` con vigencias `2026-09-01` (`"1500.000000"`, alícuota aplicada `"0.210000"`) y `2026-10-01` (`"1350.000000"`), y hoy es `2026-09-15` en la zona de la organización
- **WHEN** el usuario abre el historial de `Cerveza B`
- **THEN** ve los dos costos, el de `2026-10-01` primero marcado como programado, la fila del costo de `2026-09-01` marcada como vigente (insignia "Vigente", no solo color) con su valor informado, si incluye IVA, su bonificación, la alícuota aplicada como `21 %` (no `0,210000`), el usuario que lo registró y el momento de registro, y `1.500,000000` como costo vigente en el resumen
- **Regla:** CST-03; TR-04; TR-02 (alícuota y bonificación como porcentaje)

#### Scenario: Historial con costos de las dos reglas
- **GIVEN** un costo de `Cerveza B` registrado como `MONOTRIBUTO` (`"1815.000000"`) y otro posterior como `RESPONSABLE_INSCRIPTO` con IVA incluido (`"1500.000000"`)
- **WHEN** el usuario abre el historial
- **THEN** el primero muestra "IVA descontado: No" y el segundo "IVA descontado: Sí"
- **Regla:** CST-06; TR-06; `design.md` D3
