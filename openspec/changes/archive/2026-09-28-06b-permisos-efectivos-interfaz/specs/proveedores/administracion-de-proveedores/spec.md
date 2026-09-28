## MODIFIED Requirements

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
