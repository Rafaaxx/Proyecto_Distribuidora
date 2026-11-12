# Administración de Proveedores Specification

## Purpose

Define las pantallas de `/admin` para gestionar proveedores y cargar costos informados: listado y ficha de proveedores, carga de uno o varios costos de un proveedor con vista previa del costo base, e historial y costo vigente por producto. Toda escritura usa los comandos idempotentes del bus.

## Requirements

### Requirement: Las pantallas de proveedores y costos respetan los permisos
La pantalla de proveedores y su entrada en el menú DEBEN mostrarse solo a usuarios con `GESTIONAR_PROVEEDORES`. La carga de costos y el enlace "Cargar costos" de la ficha del proveedor, solo con `EDITAR_COSTOS`. El historial y el costo vigente, junto con el enlace "Ver historial de costos" de la ficha del producto, solo con `VER_COSTOS`. Cada pantalla, entrada y enlace DEBE decidir su visibilidad solo con los permisos efectivos de la consulta de sesión (ADR-027). NO DEBE pedir un dato al servidor solo para averiguar si tiene el permiso. Sin el permiso, la pantalla DEBE mostrar que falta y NO DEBE mostrar datos ni pedirlos al servidor **(B2)**. Si el servidor igual responde `PERMISO_REQUERIDO` (por ejemplo, porque el permiso se quitó entre dos renovaciones del token), la pantalla DEBE mostrar que falta el permiso, sin datos. La restricción de la pantalla no reemplaza la del servidor (SEG-06).

> **(B2)** refleja la opción A de D4 de `design.md`, aprobada por el usuario el 2026-09-25.

#### Scenario: Usuario con permisos
- **GIVEN** un usuario con rol Administración (`GESTIONAR_PROVEEDORES`, `EDITAR_COSTOS`, `VER_COSTOS` en su consulta de sesión)
- **WHEN** entra a `/admin/proveedores`
- **THEN** ve la entrada Proveedores en el menú y el listado de proveedores, y puede abrir la ficha, cargar costos y ver el historial
- **Regla:** `01` §19; ADR-027

#### Scenario: Usuario sin permiso
- **GIVEN** un usuario con rol Vendedor/Repartidor
- **WHEN** entra a `/admin/proveedores`, a la carga de costos de un proveedor o al historial de costos de un producto escribiendo la dirección
- **THEN** el menú no muestra Proveedores y la pantalla muestra el mensaje de falta de permiso, sin ningún proveedor ni costo
- **AND** no se hace ninguna petición de proveedores ni de costos al servidor **(B2)**
- **Regla:** `01` §19 (el vendedor no ve costos); TR-10; ADR-027

#### Scenario: Enlace al historial de costos desde la ficha del producto según el permiso
- **GIVEN** la ficha de un producto existente
- **WHEN** la abre un usuario cuya consulta de sesión incluye `VER_COSTOS`
- **THEN** ve el enlace "Ver historial de costos" hacia el historial de ese producto
- **AND** un usuario sin `VER_COSTOS`, o la ficha en modo alta (sin producto creado todavía), no lo ve
- **AND** en ningún caso se consulta el costo vigente para decidir si el enlace se muestra
- **Regla:** `01` §19 (`VER_COSTOS`); ADR-027 (reemplaza el mecanismo reactivo provisorio del change 06)

#### Scenario: Enlace "Cargar costos" desde la ficha del proveedor según el permiso
- **GIVEN** la ficha de un proveedor activo
- **WHEN** la abre un usuario con `GESTIONAR_PROVEEDORES` cuya consulta de sesión incluye `EDITAR_COSTOS`
- **THEN** ve el enlace "Cargar costos"
- **AND** un usuario con `GESTIONAR_PROVEEDORES` pero sin `EDITAR_COSTOS` no lo ve
- **Regla:** `01` §19 (`EDITAR_COSTOS`); ADR-027

#### Scenario: El servidor rechaza aunque la interfaz creía tener el permiso
- **GIVEN** un usuario cuya consulta de sesión todavía incluye `VER_COSTOS`, al que se le quitó ese permiso del rol antes de la próxima renovación del token
- **WHEN** abre el historial de costos de un producto y el servidor responde `PERMISO_REQUERIDO`
- **THEN** la pantalla muestra que no tiene permiso para ver costos, sin ningún costo y sin un error genérico
- **Regla:** SEG-06; ADR-017

### Requirement: Alta y edición de proveedores desde la pantalla
El listado DEBE permitir buscar por nombre o CUIT, filtrar por actividad y paginar. La ficha DEBE permitir alta, modificación, desactivación y reactivación. Cada envío DEBE llevar un `Operation-Id` UUIDv7 nuevo que se conserva si el usuario reintenta tras un error de red. Los errores de dominio del servidor DEBEN mostrarse junto al campo que corresponde, conservando lo cargado.

#### Scenario: Alta de un proveedor
- **GIVEN** la pantalla de alta de proveedor
- **WHEN** el usuario confirma nombre `Bodega Andina` y CUIT `30-71234567-1`
- **THEN** se envía un único comando y, al aceptarse, el proveedor aparece en el listado sin recargar la página
- **Regla:** CAT-06; `02` §6

#### Scenario: Reintento tras error de red no duplica
- **GIVEN** un alta enviada cuya respuesta no llegó por un corte de red
- **WHEN** el usuario reintenta sin cambiar los datos
- **THEN** se reenvía con el mismo `Operation-Id` y existe un solo proveedor
- **Regla:** INV-06; SYN-02

#### Scenario: Nombre duplicado informado por el servidor
- **GIVEN** el proveedor `Bodega Andina` existe
- **WHEN** el usuario da de alta otro con el mismo nombre
- **THEN** la pantalla muestra que el nombre ya existe junto al campo y conserva lo cargado
- **Regla:** TR-10; `design.md` D7

#### Scenario: Desactivar un proveedor con productos activos
- **GIVEN** el proveedor de un producto activo
- **WHEN** el usuario intenta desactivarlo
- **THEN** la pantalla muestra que tiene productos activos y el proveedor sigue activo
- **Regla:** `design.md` D5

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

### Requirement: Último costo informado por presentación, a título informativo
Para un producto, la pantalla DEBE mostrar además el último costo informado de cada una de sus presentaciones con `vigencia_desde` menor o igual a la fecha consultada (mismo desempate de vigencia que el costo vigente del producto, `design.md` D4), marcando cuál de esas filas es la vigente del producto. Esta sección es puramente informativa: el precio de referencia (PRC-11) se calcula solo con el costo vigente del producto (CST-03), nunca con el costo de una presentación distinta, porque los costos informados no son por presentación (ADR-010; `design.md` D1).

#### Scenario: Último costo informado por presentación
- **GIVEN** `Cerveza B` con `Caja x12` (último costo vigente a la fecha) y `Pack x24` (con un costo informado más reciente que el de `Caja x12`, pero de otra presentación)
- **WHEN** el usuario abre el historial de `Cerveza B`
- **THEN** ve la sección "Último costo informado por presentación" con una fila por presentación con costo informado, la de `Caja x12` marcada como vigente, y una nota indicando que el precio se calcula solo con el costo vigente del producto
- **Regla:** CST-03; PRC-11; ADR-010 (los costos no son por presentación)
