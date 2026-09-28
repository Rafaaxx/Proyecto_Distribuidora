## MODIFIED Requirements

### Requirement: La pantalla de catálogo está disponible solo con el permiso
El área `/admin` DEBE ofrecer la pantalla de catálogo a usuarios autenticados con `GESTIONAR_CATALOGO`, permiso que exigen tanto las lecturas como las escrituras de catálogo en la API. La pantalla, su entrada en el menú y sus acciones (listado de productos, alta y edición de productos, categorías y marcas) DEBEN mostrarse u ocultarse solo según los permisos efectivos de la consulta de sesión (ADR-027). NO DEBEN decidirlo intentando la consulta y mirando si responde `PERMISO_REQUERIDO`. A un usuario sin el permiso NO DEBE mostrarle datos ni acciones de escritura, y la pantalla NO DEBE pedir datos de catálogo al servidor **(B2)**. Si el servidor igual responde `PERMISO_REQUERIDO` (por ejemplo, porque el permiso se quitó entre dos renovaciones del token), la pantalla DEBE mostrar que no tiene permiso para gestionar el catálogo, sin datos (SEG-06). La pantalla DEBE cargarse solo dentro del área `/admin` (el teléfono no descarga su código).

> **(B2)** refleja la opción A de D4 de `design.md`, aprobada por el usuario el 2026-09-25.

#### Scenario: Usuario con permiso
- **GIVEN** un usuario con rol Administración, cuya consulta de sesión incluye `GESTIONAR_CATALOGO`
- **WHEN** navega a `/admin/catalogo`
- **THEN** ve la entrada Catálogo en el menú, el listado de productos y las acciones de alta y edición
- **Regla:** `01` §19 (GESTIONAR_CATALOGO: ADM, GES); ADR-027

#### Scenario: Usuario sin permiso
- **GIVEN** un usuario autenticado cuya consulta de sesión no incluye `GESTIONAR_CATALOGO` (por ejemplo, rol Supervisor comercial)
- **WHEN** navega a `/admin/catalogo` o a `/admin/catalogo/categorias-y-marcas` escribiendo la dirección
- **THEN** el menú no muestra Catálogo y la pantalla muestra que no tiene permiso para gestionar el catálogo, sin listado ni acciones de alta o edición
- **AND** no se hace ninguna petición de catálogo al servidor **(B2)**
- **Regla:** SEG-06; ADR-017; ADR-027; `01` §19

#### Scenario: El servidor rechaza aunque la interfaz creía tener el permiso
- **GIVEN** un usuario cuya consulta de sesión todavía incluye `GESTIONAR_CATALOGO`, al que se le quitó ese permiso del rol antes de la próxima renovación del token
- **WHEN** abre el listado de productos y el servidor responde `PERMISO_REQUERIDO`
- **THEN** la pantalla muestra que no tiene permiso para gestionar el catálogo, sin listado ni acciones, y sin un error genérico
- **Regla:** SEG-06; ADR-017
