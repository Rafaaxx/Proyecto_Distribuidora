## ADDED Requirements

### Requirement: El tope de descuento de un rol se define por comando

El comando `ROL_TOPE_DESCUENTO_DEFINIR` DEBE fijar el tope de descuento manual de un rol de la organización (`01` §19: "la organización puede modificar … los topes de descuento"; DSC-06). DEBE exigir el permiso `ADMIN_USUARIOS` y conexión: es solo `ONLINE`. El tope DEBE llegar como cadena con una fracción de hasta 6 decimales entre `0` y `1` (TR-02, INV-03); fuera de ese rango se rechaza con `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO` (422). Un rol inexistente o de otra organización responde 404. El comando NO DEBE cambiar los permisos del rol ni el tope propio de ningún usuario, y el tope nuevo DEBE regir desde la siguiente evaluación de un descuento manual. El cambio DEBE quedar auditado con el valor anterior y el nuevo (AUD-01, AUD-02). Los roles de la organización DEBEN poder consultarse con su tope, como cadena, por quien tenga `ADMIN_USUARIOS`. El tope NO DEBE agregarse al token ni a la consulta de la sesión en curso.

#### Scenario: Definir el tope de un rol

- **GIVEN** un Administrador con `ADMIN_USUARIOS` y el rol "Vendedor/Repartidor" con tope `0.000000`
- **WHEN** envía `ROL_TOPE_DESCUENTO_DEFINIR` con `"0.050000"`
- **THEN** el rol queda con tope `0.050000` y sus permisos no cambian
- **Regla:** DSC-06; `01` §19; TR-02

#### Scenario: El tope nuevo rige en la siguiente evaluación

- **GIVEN** un Vendedor sin tope propio cuyo rol pasó de `0.000000` a `0.050000`
- **WHEN** se consulta su tope aplicable
- **THEN** es `0.050000`
- **Regla:** DSC-06; `03` §4

#### Scenario: El tope propio de un usuario no cambia

- **GIVEN** un Vendedor con tope propio `0.080000`
- **WHEN** el tope de su rol se cambia a `0.050000`
- **THEN** su tope aplicable sigue siendo `0.080000`
- **Regla:** `03` §4 (`tope_descuento_override`)

#### Scenario: Sin permiso

- **GIVEN** un Supervisor comercial, que no tiene `ADMIN_USUARIOS`
- **WHEN** envía `ROL_TOPE_DESCUENTO_DEFINIR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` y el tope no cambia
- **Regla:** SEG-06; `01` §19

#### Scenario: Tope fuera de rango

- **GIVEN** un Administrador
- **WHEN** envía un tope negativo, mayor que `1.000000` o con siete decimales
- **THEN** se rechaza con 422 `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO` y el tope no cambia
- **Regla:** TR-02; `01` §19

#### Scenario: El tope llega como número

- **GIVEN** un Administrador
- **WHEN** envía el tope como número JSON `0.05`
- **THEN** se rechaza con 422 y el tope no cambia
- **Regla:** INV-03; `02` §10.2

#### Scenario: Rol de otra organización

- **GIVEN** un rol que pertenece a otra organización
- **WHEN** el Administrador envía `ROL_TOPE_DESCUENTO_DEFINIR` sobre él
- **THEN** responde 404 y el rol ajeno no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: El cambio queda auditado

- **GIVEN** un rol con tope `0.000000`
- **WHEN** se acepta un `ROL_TOPE_DESCUENTO_DEFINIR` con `"0.050000"`
- **THEN** queda una sola fila de auditoría con el usuario, el rol, el valor anterior `0.000000`, el nuevo `0.050000` y el `operation_id`
- **Regla:** AUD-01; AUD-02

#### Scenario: Doble envío

- **GIVEN** un `ROL_TOPE_DESCUENTO_DEFINIR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y sigue habiendo una sola fila de auditoría
- **Regla:** SYN-02; INV-06

#### Scenario: Mismo identificador con otro tope

- **GIVEN** un `ROL_TOPE_DESCUENTO_DEFINIR` ya aceptado con `"0.050000"`
- **WHEN** llega el mismo `operation_id` con `"0.200000"`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y el tope sigue en `0.050000`
- **Regla:** SYN-02

#### Scenario: El comando no se acepta sin conexión

- **GIVEN** un lote de sincronización con un `ROL_TOPE_DESCUENTO_DEFINIR` en modo `OFFLINE`
- **WHEN** el servidor procesa el lote
- **THEN** ese comando se rechaza y el tope no cambia
- **Regla:** `02` §6.5

#### Scenario: Consulta de roles con su tope

- **GIVEN** un Administrador
- **WHEN** consulta los roles de la organización
- **THEN** recibe cada rol con su nombre, si está activo y su tope como cadena (`"1.000000"` para el Administrador), y ningún rol de otra organización
- **Regla:** `01` §19; INV-21; `02` §10.2

#### Scenario: La sesión en curso sigue sin exponer el tope

- **GIVEN** un usuario autenticado
- **WHEN** consulta su sesión en curso
- **THEN** la respuesta sigue sin contener el tope de descuento
- **Regla:** ADR-027; SYN-11
