## ADDED Requirements

### Requirement: Las pantallas de medios de pago y de roles explican sus reglas

La pestaña "Medios de pago" DEBE ofrecer ayuda en "Pide referencia" y en "Dar de baja"; la pantalla "Roles y permisos", en los permisos del rol, en el permiso "Usuarios, roles y permisos" y en los permisos de autorización. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (para qué sirve en una oración, palabras de todos los días, un ejemplo con nombres y montos reales, tres o cuatro oraciones) (`design.md` D12 del change 17b).

#### Scenario: Pide referencia
- **GIVEN** la pestaña "Medios de pago"
- **WHEN** se abre el "(?)" de "Pide referencia"
- **THEN** explica que hay que anotar un dato como el número de la transferencia, que con conexión sin ese dato no se guarda y que sin señal entra marcado para revisar, con el ejemplo de $20.000 por transferencia n.º 0042
- **Regla:** COB-02, PAG-01, SYN-07

#### Scenario: Dar de baja
- **GIVEN** la pestaña "Medios de pago"
- **WHEN** se abre el "(?)" de "Dar de baja"
- **THEN** explica que el medio deja de ofrecerse, que no se borra, que se puede reactivar y que tiene que quedar al menos uno activo
- **Regla:** CAT-05, TR-06, ADR-053

#### Scenario: Permisos del rol
- **GIVEN** la pantalla "Roles y permisos" con un rol elegido
- **WHEN** se abre el "(?)" de los permisos
- **THEN** explica que el cambio vale para todos los usuarios del rol desde su próxima acción, con el ejemplo de quitarle "Anular cobranzas" al Supervisor comercial
- **Regla:** `01` §19, ADR-017

#### Scenario: Último administrador
- **GIVEN** la pantalla "Roles y permisos"
- **WHEN** se abre el "(?)" del permiso "Usuarios, roles y permisos"
- **THEN** explica que siempre tiene que quedar al menos una persona activa con ese permiso
- **Regla:** ADR-053

#### Scenario: Permisos de autorización
- **GIVEN** la pantalla "Roles y permisos"
- **WHEN** se abre el "(?)" de los permisos de autorización
- **THEN** explica que, si el rol se queda sin ninguno, se borra el PIN de sus usuarios
- **Regla:** ADR-011

#### Scenario: Trazabilidad
- **GIVEN** las cinco claves nuevas
- **WHEN** corre la prueba de trazabilidad del archivo de textos
- **THEN** cada una cita reglas que existen en `docs/01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
