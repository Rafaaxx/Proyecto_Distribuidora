## Purpose

Define cómo un usuario inicia sesión, cómo se mantiene esa sesión sin exponer credenciales a XSS y cómo se corta: access token de vida corta en memoria, refresh token rotativo en cookie vinculado al dispositivo, y detección de reuso que revoca la familia (ADR-017, `02` §12.1).

## ADDED Requirements

### Requirement: El inicio de sesión exige credenciales válidas y un dispositivo

El sistema DEBE aceptar un inicio de sesión solo cuando recibe un nombre de usuario, una contraseña correcta de un usuario activo y un identificador de dispositivo. El inicio de sesión requiere conexión (SEG-01).

#### Scenario: Inicio de sesión con credenciales correctas

- **GIVEN** un usuario activo de la organización A con contraseña conocida y un identificador de dispositivo
- **WHEN** inicia sesión con esos datos
- **THEN** recibe un access token asociado a su usuario, su organización y ese dispositivo
- **AND** recibe un refresh token en una cookie, no en el cuerpo de la respuesta
- **Regla:** SEG-01, `02` §12.1

#### Scenario: Contraseña incorrecta no distingue de usuario inexistente

- **GIVEN** la organización A con un usuario `vendedor1`
- **WHEN** se intenta iniciar sesión con `vendedor1` y contraseña incorrecta, y por separado con un usuario que no existe
- **THEN** ambas respuestas son indistinguibles en código, mensaje y forma
- **AND** ninguna revela si el usuario existe
- **Regla:** SEG-01, `02` §18

#### Scenario: Un usuario inactivo no obtiene sesión

- **GIVEN** un usuario con estado `INACTIVO` y contraseña correcta
- **WHEN** intenta iniciar sesión
- **THEN** el intento se rechaza y no se emite ningún token
- **Regla:** SEG-01, `03` §4 (`usuario.estado`)

#### Scenario: Un inicio de sesión sin dispositivo se rechaza

- **GIVEN** credenciales correctas
- **WHEN** el inicio de sesión no informa identificador de dispositivo
- **THEN** se rechaza y no se emite ningún token
- **Regla:** `02` §12.1 (el access token contiene usuario, organización y dispositivo), SEG-02

#### Scenario: Un inicio de sesión desde un dispositivo revocado se rechaza

- **GIVEN** un dispositivo en estado `REVOCADO` y credenciales correctas de un usuario activo
- **WHEN** se intenta iniciar sesión desde ese dispositivo
- **THEN** el intento se rechaza y no se emite ningún token
- **Regla:** SEG-02, `02` §12.2 (revocar un dispositivo invalida sus refresh tokens)

#### Scenario: La contraseña nunca queda registrada

- **GIVEN** un inicio de sesión, exitoso o fallido
- **WHEN** se inspeccionan los registros producidos por la petición
- **THEN** no aparece la contraseña en ninguno, en ningún nivel de registro
- **Regla:** `02` §17 (nunca se registran contraseñas, PIN ni tokens)

### Requirement: El access token es de vida corta, viaja en memoria y no lleva permisos

El access token DEBE ser un token firmado con una vida de 15 minutos que identifique usuario, organización y dispositivo. NO DEBE contener los permisos del usuario. El sistema NO DEBE entregarlo de una forma que lo persista en el navegador (ni cookie, ni almacenamiento local) (ADR-017, `02` §12.1).

#### Scenario: El access token identifica usuario, organización y dispositivo

- **GIVEN** una sesión recién iniciada
- **WHEN** se inspecciona el contenido del access token
- **THEN** identifica al usuario, a su organización y al dispositivo desde el que inició sesión
- **Regla:** `02` §12.1

#### Scenario: El access token no lleva permisos

- **GIVEN** un usuario con el rol Administrador, que tiene todos los permisos
- **WHEN** se inspecciona el contenido de su access token
- **THEN** no contiene ninguna lista de permisos ni el tope de descuento
- **Regla:** ADR-017 (los permisos no viajan en el token, para que una revocación tenga efecto inmediato)

#### Scenario: Un access token vencido no da acceso

- **GIVEN** un access token emitido hace más de 15 minutos
- **WHEN** se lo usa en una petición a una ruta de negocio
- **THEN** la petición se rechaza como no autenticada
- **Regla:** `02` §12.1 (vida de 15 minutos)

#### Scenario: Un access token con firma alterada no da acceso

- **GIVEN** un access token válido cuyo contenido fue modificado para nombrar otra organización
- **WHEN** se lo usa en una petición
- **THEN** la petición se rechaza como no autenticada y no se accede a ningún dato
- **Regla:** INV-21, `02` §8 (`organizacion_id` se toma del token)

### Requirement: El refresh token es opaco, rotativo y vinculado al dispositivo

El refresh token DEBE ser opaco, almacenarse en el servidor únicamente como derivación irrecuperable y viajar en una cookie inaccesible desde JavaScript, restringida al camino de autenticación. Cada uso DEBE emitir uno nuevo e invalidar el anterior. Su vencimiento DEBE ser deslizante: 30 días que se renuevan en cada rotación (ADR-017, `02` §12.1).

#### Scenario: Renovar la sesión rota el refresh token

- **GIVEN** una sesión con un refresh token vigente
- **WHEN** se renueva la sesión con ese token
- **THEN** se emite un access token nuevo y un refresh token nuevo
- **AND** el refresh token anterior queda marcado como usado y ya no sirve
- **Regla:** ADR-017 (refresh opaco, rotativo en cada uso)

#### Scenario: El refresh token no es legible desde la aplicación

- **GIVEN** una sesión iniciada
- **WHEN** se inspeccionan la respuesta y la cookie emitida
- **THEN** la cookie es inaccesible desde JavaScript, exige transporte seguro, no se envía en peticiones originadas por otro sitio y se limita al camino de autenticación
- **AND** el valor del refresh token no aparece en el cuerpo de ninguna respuesta
- **Regla:** ADR-017 (`HttpOnly`, `Secure`, `SameSite=Strict`, restringida a `/api/v1/auth`)

#### Scenario: El servidor no guarda el refresh token en claro

- **GIVEN** un refresh token emitido
- **WHEN** se inspecciona lo almacenado en el servidor
- **THEN** lo almacenado es una derivación de la que no se puede reconstruir el token
- **Regla:** `02` §12.1 (guardado en base como hash)

#### Scenario: El vencimiento se renueva en cada rotación

- **GIVEN** un refresh token emitido hace 29 días y usado hoy
- **WHEN** se renueva la sesión
- **THEN** el refresh token nuevo vence 30 días después de hoy, no 1 día después
- **Regla:** ADR-017 (vencimiento deslizante de 30 días)

#### Scenario: Un refresh token vencido obliga a iniciar sesión

- **GIVEN** un refresh token cuyo vencimiento ya pasó
- **WHEN** se intenta renovar la sesión con él
- **THEN** la renovación se rechaza y se requiere un inicio de sesión con credenciales
- **Regla:** `02` §12.3 (si venció, pide login; la cola se conserva)

#### Scenario: Un refresh token de otro dispositivo no sirve

- **GIVEN** un refresh token emitido para el dispositivo D1
- **WHEN** se lo presenta declarando el dispositivo D2
- **THEN** la renovación se rechaza
- **Regla:** ADR-017 (vinculado a usuario y dispositivo)

### Requirement: Reusar un refresh token ya rotado revoca la familia del dispositivo

Cuando el sistema recibe un refresh token que ya fue usado, DEBE tratarlo como indicio de robo y revocar todos los refresh tokens de esa familia, dejando la sesión de ese dispositivo sin forma de renovarse (ADR-017, `02` §12.1).

#### Scenario: El reuso de un token rotado corta toda la familia

- **GIVEN** una sesión que ya rotó su refresh token de `T1` a `T2`
- **WHEN** alguien presenta `T1`
- **THEN** la renovación se rechaza
- **AND** `T2` y cualquier otro token de la misma familia quedan revocados
- **AND** el dispositivo necesita un inicio de sesión con credenciales para volver a operar
- **Regla:** ADR-017 (detección de robo), `02` §12.1

#### Scenario: La revocación por reuso queda auditada

- **GIVEN** un reuso de refresh token detectado
- **WHEN** se consulta la auditoría
- **THEN** hay un registro que identifica al usuario, al dispositivo y el motivo de la revocación
- **Regla:** AUD-01 (se audita el inicio de sesión), AUD-02

#### Scenario: La revocación de una familia no afecta a otros dispositivos

- **GIVEN** un usuario con sesión activa en dos dispositivos, D1 y D2
- **WHEN** se detecta reuso en la familia de D1
- **THEN** la sesión de D2 sigue pudiendo renovarse
- **Regla:** ADR-017 (vinculado a usuario y dispositivo)

### Requirement: Cerrar sesión revoca la sesión del dispositivo

Cerrar sesión DEBE revocar el refresh token vigente de ese dispositivo y eliminar la cookie, de modo que la sesión no pueda renovarse.

#### Scenario: Después de cerrar sesión no se puede renovar

- **GIVEN** una sesión activa
- **WHEN** el usuario cierra sesión y luego intenta renovarla con el refresh token anterior
- **THEN** la renovación se rechaza
- **Regla:** ADR-017 (refresh guardado en base: revocable)

#### Scenario: Cerrar sesión sin sesión activa no falla

- **GIVEN** una petición de cierre de sesión sin cookie de refresh
- **WHEN** se procesa
- **THEN** responde como si hubiera cerrado sesión, sin revelar si había una sesión
- **Regla:** `02` §18

### Requirement: El inicio de sesión está limitado en intentos por usuario y por IP

El sistema DEBE limitar los intentos fallidos de inicio de sesión por usuario y por dirección de origen, y DEBE contarlos de forma que el límite sea el mismo sin importar qué proceso atienda la petición (`02` §18, `02` §16.2).

> **Pendiente de ADR (bloqueante):** umbral, ventana, duración y alcance del bloqueo, y cómo se recupera un usuario bloqueado. `02` §18 exige el límite pero no fija ninguno de esos valores, y `01` no tiene una regla que los defina. Ver `design.md` D1. Los escenarios de abajo fijan las propiedades que no dependen de esos valores; los escenarios con umbrales concretos se agregan cuando el ADR los fije.

#### Scenario: Los intentos fallidos se cuentan de forma uniforme entre procesos

- **GIVEN** un backend con varios procesos de trabajo atendiendo peticiones
- **WHEN** los intentos fallidos de un mismo usuario se reparten entre distintos procesos
- **THEN** el límite se alcanza con la misma cantidad total de intentos que si los hubiera atendido uno solo
- **Regla:** `02` §18, `02` §16.2 (FastAPI con varios workers)

#### Scenario: Un inicio de sesión exitoso no queda penalizado por intentos de otro usuario

- **GIVEN** un usuario A que agotó sus intentos fallidos y un usuario B en la misma organización
- **WHEN** el usuario B inicia sesión con credenciales correctas desde otra dirección de origen
- **THEN** su inicio de sesión se acepta
- **Regla:** `02` §18 (límite por usuario y por IP)

#### Scenario: El bloqueo por intentos no revela si el usuario existe

- **GIVEN** un nombre de usuario que no existe
- **WHEN** se agotan los intentos contra él
- **THEN** la respuesta es indistinguible de la que produce un usuario existente bloqueado
- **Regla:** `02` §18

#### Scenario: Un bloqueo por intentos queda auditado

- **GIVEN** un usuario que alcanzó el límite de intentos fallidos
- **WHEN** se consulta la auditoría
- **THEN** hay un registro del bloqueo con usuario, origen y momento
- **Regla:** AUD-01 (se audita el inicio de sesión), AUD-02
