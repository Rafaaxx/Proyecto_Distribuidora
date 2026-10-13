# Identidad - Autenticación y Sesión

## Purpose

Define cómo un usuario inicia sesión, cómo se mantiene esa sesión sin exponer credenciales a XSS y cómo se corta: access token de vida corta en memoria, refresh token rotativo en cookie vinculado al dispositivo, y detección de reuso que revoca la familia (ADR-017, `02` §12.1).

## Requirements

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

### Requirement: La renovación y el inicio de sesión exigen usuario y rol activos

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja las opciones aprobadas: D9.2-A (código de rechazo existente), D9.3-B (corte con canal acotado para la cola offline) y D9.4-A (rol inactivo igual que usuario inactivo).
>
> **(Change 15)** La excepción de D9.3-B pasa a ser efectiva. Dominio CRÍTICO: refleja las opciones aprobadas de `design.md` D17, D18 y D19 del change 15-jornadas (opción A, aprobación explícita del usuario el 2026-10-09).

La renovación de sesión DEBE verificar, después de validar el refresh token, que el usuario está `ACTIVO` y que su rol está activo. Si no lo están, DEBE:

- rechazar la renovación con el mismo rechazo genérico de un refresh token inválido;
- revocar las sesiones de refresh de ese usuario, en todos sus dispositivos, con un motivo que distinga usuario inactivo de rol inactivo, **salvo** la del dispositivo alcanzado por la excepción de abajo;
- auditar la revocación.

La revocación DEBE persistir aunque la respuesta sea un error.

La única excepción (D9.3-B) es un dispositivo con una jornada no cerrada de ese usuario: una jornada `ABIERTA` o `EN_RENDICION` cuyo usuario y cuyo dispositivo son los de la sesión que renueva. Ahí la renovación DEBE permitirse, rotando el refresh token como siempre y sin revocar ninguna sesión, y DEBE quedar auditada. El access token resultante solo sirve para entregar la cola de sincronización, porque toda otra ruta rechaza al usuario inactivo. Una jornada `CERRADA` o `LIBERADA` NO habilita la excepción, y tampoco una jornada de otro usuario en ese dispositivo, ni una jornada del mismo usuario en otro dispositivo. Si el sistema no puede determinar si existe esa jornada, DEBE comportarse como si no existiera.

El inicio de sesión DEBE rechazar, con el mismo rechazo genérico que ya usa para un usuario inactivo, a un usuario cuyo rol está inactivo, sin revelar la causa (SEG-01). La excepción de la jornada NO alcanza al inicio de sesión: un usuario inactivo no inicia sesión aunque tenga una jornada no cerrada.

Reactivar al usuario NO DEBE revivir las sesiones revocadas: hace falta un inicio de sesión con credenciales.

#### Scenario: Un usuario dado de baja no puede renovar su sesión
- **GIVEN** un usuario con un refresh token vigente, que pasó a `INACTIVO`, y un dispositivo sin jornada abierta
- **WHEN** se intenta renovar la sesión con ese refresh token
- **THEN** la renovación se rechaza como refresh token inválido
- **AND** todas las sesiones de refresh de ese usuario quedan revocadas, en todos sus dispositivos
- **AND** hay un registro de auditoría con el usuario, el dispositivo y el motivo
- **Regla:** ADR-028; ADR-017; AUD-01

#### Scenario: Un rol desactivado impide renovar la sesión
- **GIVEN** un usuario activo con un refresh token vigente, cuyo rol pasa a inactivo
- **WHEN** se intenta renovar la sesión
- **THEN** la renovación se rechaza y sus sesiones de refresh quedan revocadas con un motivo que indica el rol inactivo
- **Regla:** ADR-028 (D9.4-A)

#### Scenario: Reactivar al usuario no revive la sesión revocada
- **GIVEN** un usuario cuyas sesiones de refresh se revocaron por estar `INACTIVO`
- **WHEN** vuelve a `ACTIVO` y presenta el mismo refresh token
- **THEN** la renovación se rechaza y necesita un inicio de sesión con credenciales
- **Regla:** ADR-028; ADR-017

#### Scenario: La baja de un usuario no toca la sesión de otro en el mismo dispositivo
- **GIVEN** dos usuarios activos que iniciaron sesión en el mismo dispositivo
- **WHEN** uno pasa a `INACTIVO` y su renovación se rechaza
- **THEN** la sesión del otro usuario sigue pudiendo renovarse
- **Regla:** ADR-017 (sesión vinculada a usuario y dispositivo); ADR-028

#### Scenario: Un usuario con rol inactivo no inicia sesión
- **GIVEN** un usuario `ACTIVO` con credenciales correctas, cuyo rol está inactivo
- **WHEN** intenta iniciar sesión
- **THEN** recibe el mismo rechazo genérico que ante credenciales incorrectas, sin revelar la causa
- **AND** el intento queda auditado como inicio de sesión fallido
- **Regla:** SEG-01; ADR-028

#### Scenario: Un usuario dado de baja con jornada abierta renueva para entregar su cola
- **GIVEN** un usuario que pasó a `INACTIVO`, con un refresh token vigente en un dispositivo donde tiene una jornada `ABIERTA`
- **WHEN** ese dispositivo renueva la sesión
- **THEN** la renovación se acepta y devuelve un access token y un refresh token nuevos
- **AND** ninguna sesión de refresh del usuario queda revocada
- **AND** hay un registro de auditoría de la renovación con jornada pendiente, con el usuario y el dispositivo
- **Regla:** ADR-028 (D9.3-B); SYN-09; RUT-05

#### Scenario: El token obtenido por la excepción no abre otras rutas
- **GIVEN** el access token de ese usuario inactivo, obtenido por la excepción
- **WHEN** consulta su identidad o cualquier ruta de negocio que no sea el lote de sincronización
- **THEN** recibe el rechazo de sesión no habilitada
- **AND** el lote de sincronización no lo rechaza por ruta
- **Regla:** ADR-028 (D9.1, D9.3-B)

#### Scenario: Una jornada en rendición también habilita la renovación
- **GIVEN** un usuario `INACTIVO` con una jornada `EN_RENDICION` en su dispositivo
- **WHEN** ese dispositivo renueva la sesión
- **THEN** la renovación se acepta
- **Regla:** ADR-028 (D9.3-B); INV-16

#### Scenario: Al cerrarse la jornada, la sesión del inactivo muere
- **GIVEN** un usuario `INACTIVO` que venía renovando por la excepción, cuya jornada pasa a `CERRADA`
- **WHEN** su dispositivo intenta renovar otra vez
- **THEN** la renovación se rechaza y todas sus sesiones de refresh quedan revocadas, con auditoría
- **Regla:** ADR-028 (D9.3-B); RUT-08

#### Scenario: Una jornada liberada no habilita la renovación
- **GIVEN** un usuario `INACTIVO` cuya jornada fue `LIBERADA` por un supervisor
- **WHEN** su dispositivo intenta renovar
- **THEN** la renovación se rechaza y sus sesiones de refresh quedan revocadas
- **Regla:** ADR-028; RUT-09; `design.md` D18

#### Scenario: La jornada de otro usuario en el dispositivo no habilita
- **GIVEN** un dispositivo con una jornada `ABIERTA` de otro vendedor, y un usuario `INACTIVO` con un refresh token vigente en ese mismo dispositivo
- **WHEN** el usuario inactivo intenta renovar
- **THEN** la renovación se rechaza
- **AND** la sesión del vendedor de la jornada sigue pudiendo renovarse
- **Regla:** ADR-028 (D9.3-B); ADR-017

#### Scenario: El rechazo en otro dispositivo no cierra el canal de la cola
- **GIVEN** un usuario `INACTIVO` con una jornada `ABIERTA` en el dispositivo D1 y una sesión en el dispositivo D2, sin jornada
- **WHEN** D2 intenta renovar
- **THEN** la renovación de D2 se rechaza y la sesión de D2 queda revocada
- **AND** la sesión de D1 no se revoca y D1 sigue pudiendo renovar
- **Regla:** ADR-028 (D9.3-B, D9.5); SYN-09

#### Scenario: Un usuario inactivo con jornada abierta no inicia sesión
- **GIVEN** un usuario `INACTIVO` con una jornada `ABIERTA` en su dispositivo y credenciales correctas
- **WHEN** intenta iniciar sesión
- **THEN** recibe el rechazo genérico de credenciales
- **Regla:** SEG-01; ADR-028 (D9.1)

#### Scenario: Un rol desactivado con jornada abierta sigue la misma excepción
- **GIVEN** un usuario activo cuyo rol pasa a inactivo, con una jornada `ABIERTA` en su dispositivo
- **WHEN** ese dispositivo renueva la sesión
- **THEN** la renovación se acepta, igual que para un usuario inactivo con jornada abierta
- **Regla:** ADR-028 (D9.3-B, D9.4-A)

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
