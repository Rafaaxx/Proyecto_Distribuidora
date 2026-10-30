## ADDED Requirements

### Requirement: La baja y el restablecimiento de la contraseña revocan las sesiones en el acto

Cuando un comando da de baja a un usuario o le restablece la contraseña, sus sesiones de refresh vigentes DEBEN quedar revocadas en la misma transacción, con el motivo `USUARIO_INACTIVO` o `CONTRASENA_RESTABLECIDA`, salvo las de los dispositivos con una jornada no cerrada de ese usuario, que DEBEN seguir renovando según ADR-028 D9.3-B. La revocación DEBE auditarse como `REVOCAR_SESIONES_REFRESH_USUARIO` con origen de comando y el `operation_id` del comando. El cambio de rol NO DEBE revocar sesiones (`design.md` D2, D7, D8).

#### Scenario: Sesiones en dos dispositivos, uno con jornada
- **GIVEN** el vendedor Juan con sesión en la PC y en el teléfono, y una jornada `ABIERTA` en el teléfono
- **WHEN** se lo da de baja
- **THEN** la familia de la PC queda revocada con motivo `USUARIO_INACTIVO` y la del teléfono sigue vigente
- **Regla:** ADR-028 D9.3-B, D9.5

#### Scenario: La revocación se distingue de la de la renovación
- **WHEN** se lee la auditoría de una baja
- **THEN** la fila `REVOCAR_SESIONES_REFRESH_USUARIO` tiene origen de comando, el usuario que dio la baja y el `operation_id` del comando
- **Regla:** AUD-02

#### Scenario: Un rechazo no revoca
- **WHEN** una baja se rechaza por `IDENTIDAD_SIN_ADMINISTRADOR` o `IDENTIDAD_AUTOBAJA`
- **THEN** ninguna sesión del usuario queda revocada
- **Regla:** INV-01

#### Scenario: El cambio de rol no cierra la sesión
- **GIVEN** la supervisora Ana con sesión iniciada
- **WHEN** se le cambia el rol
- **THEN** su sesión sigue renovando y su siguiente petición usa los permisos del rol nuevo
- **Regla:** ADR-017

### Requirement: Cada usuario cambia su propia contraseña con la actual

`CONTRASENA_PROPIA_CAMBIAR` v1 DEBE permitir a cualquier usuario autenticado y activo, sin un permiso especial y solo con conexión, cambiar la contraseña de **su propio** usuario (tomado del token, nunca del cuerpo) enviando la contraseña actual y la nueva. La nueva DEBE cumplir las reglas del alta y del restablecimiento del administrador y ser distinta de la actual. Las dos contraseñas DEBEN viajar fuera del contenido del comando y no aparecer en la huella, el comando, la cuarentena, la auditoría, el resultado ni el registro de idempotencia. Una contraseña actual incorrecta DEBE responder 403 `IDENTIDAD_CONTRASENA_INCORRECTA` y contar como intento fallido de inicio de sesión (transacción aparte, que se confirma aunque el comando se rechace), con el bloqueo por intentos del login (429 `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, también con la contraseña correcta). Un cambio aceptado DEBE revocar en la misma transacción las sesiones de refresh del usuario de los demás dispositivos con el motivo `CONTRASENA_CAMBIADA`, conservar las del dispositivo de la sesión actual y NO revocar las de dispositivos con una jornada no cerrada del usuario (ADR-028 D9.3-B), y auditar el cambio sin secretos (`design.md` D20).

#### Scenario: Cambio correcto cierra las otras sesiones
- **GIVEN** la usuaria Laura con sesión en la PC y en el teléfono, sin jornada abierta
- **WHEN** desde la PC cambia su contraseña con la actual correcta y una nueva válida
- **THEN** inicia sesión con la nueva y no con la anterior, la sesión de la PC sigue renovando, la del teléfono ya no renueva (motivo `CONTRASENA_CAMBIADA`) y la auditoría registra `CAMBIAR_CONTRASENA_PROPIA` y `REVOCAR_SESIONES_REFRESH_USUARIO` con origen de comando y el mismo `operation_id`, sin contraseñas
- **Regla:** ADR-018; ADR-056; AUD-01; AUD-02

#### Scenario: Dispositivo con jornada no cerrada
- **GIVEN** el vendedor Juan con la sesión actual en la PC y una jornada `ABIERTA` en su teléfono
- **WHEN** cambia su contraseña
- **THEN** la sesión del teléfono no se revoca y puede renovar y entregar su cola
- **Regla:** ADR-028 D9.3-B; SYN-05; SYN-10

#### Scenario: Contraseña actual incorrecta cuenta como intento fallido
- **WHEN** un usuario envía una contraseña actual incorrecta
- **THEN** la respuesta es 403 `IDENTIDAD_CONTRASENA_INCORRECTA`, la contraseña no cambia, ninguna sesión se revoca, queda un intento fallido confirmado en `intento_login` y un reintento con el mismo `Operation-Id` y datos corregidos se procesa
- **Regla:** ADR-018; ADR-057; INV-01

#### Scenario: No se puede forzar la contraseña desde una sesión abierta
- **GIVEN** un usuario que alcanzó el límite de intentos fallidos
- **WHEN** envía el cambio, incluso con la contraseña actual correcta
- **THEN** la respuesta es 429 `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` sin verificar ni cambiar nada
- **Regla:** ADR-018; ADR-057; SEG-04

#### Scenario: Contraseña nueva inválida o igual a la actual
- **WHEN** la nueva no cumple las reglas del alta (menos de 8 caracteres o en blanco) o es igual a la actual
- **THEN** la respuesta es 422, la contraseña anterior sigue vigente, ninguna sesión se revoca y no cuenta como intento fallido
- **Regla:** INV-01

#### Scenario: Solo la propia contraseña
- **WHEN** el contenido o el cuerpo intenta indicar otro usuario
- **THEN** se rechaza por campo no admitido y solo puede cambiarse la contraseña del usuario del token
- **Regla:** SEG-06; INV-21

#### Scenario: Las contraseñas no quedan guardadas
- **WHEN** se leen el comando, la cuarentena, la auditoría, el registro de idempotencia y la respuesta de un cambio
- **THEN** ninguno contiene la contraseña actual ni la nueva, y el lote rechaza el tipo como tipo que exige credenciales efímeras
- **Regla:** ADR-056

#### Scenario: Doble envío
- **GIVEN** un cambio ya aceptado
- **WHEN** se reenvía con el mismo `Operation-Id`
- **THEN** no se revoca nada otra vez ni se audita una segunda vez
- **Regla:** INV-06

### Requirement: La pantalla "Mi contraseña" y el menú "Mi cuenta"

El menú de `/admin` DEBE agrupar "Mi PIN" y "Mi contraseña" bajo "Mi cuenta", visible para todo usuario autenticado; "Mi PIN" DEBE conservar su regla de visibilidad actual. "Mi contraseña" (en `areas/admin/cuenta/`) DEBE pedir la actual, la nueva y su confirmación (solo en la interfaz), explicar en palabras simples los errores y avisar al terminar que las demás sesiones se cerraron.

#### Scenario: Visible para todos
- **GIVEN** el vendedor, que no tiene permisos de autorización
- **WHEN** abre `/admin`
- **THEN** ve "Mi cuenta" con "Mi contraseña" y sin "Mi PIN"
- **Regla:** ADR-027

#### Scenario: Confirmación distinta
- **WHEN** la confirmación no coincide con la nueva
- **THEN** la pantalla lo señala y no envía nada
- **Regla:** `design.md` D20
