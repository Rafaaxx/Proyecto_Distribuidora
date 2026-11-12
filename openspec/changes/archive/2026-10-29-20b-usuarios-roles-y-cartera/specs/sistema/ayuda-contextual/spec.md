## ADDED Requirements

### Requirement: Usuarios, roles y cartera explican sus reglas

Las pantallas de usuarios, de roles y de clientes DEBEN ofrecer ayuda en la baja de usuarios, el cambio de rol, el tope propio, el restablecimiento de la contraseña, la baja de roles y el vendedor asignado, y la ayuda del último administrador DEBE nombrar también la baja de usuarios y de roles y el cambio de rol. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D18).

#### Scenario: Baja de usuario
- **WHEN** se abre el "(?)" de "Dar de baja"
- **THEN** explica que el usuario deja de entrar, que su teléfono con jornada abierta puede subir lo pendiente y que no se puede dar de baja al último administrador ni a uno mismo, sin ejemplo
- **Regla:** ADR-028; ADR-053

#### Scenario: Tope propio
- **WHEN** se abre el "(?)" del tope propio
- **THEN** explica que reemplaza al del rol y que vacío rige el del rol
- **Regla:** DSC-06

#### Scenario: Último administrador revisado
- **WHEN** se abre el "(?)" del último administrador
- **THEN** nombra el cambio de permisos, la baja de usuarios y de roles y el cambio de rol
- **Regla:** ADR-053

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
