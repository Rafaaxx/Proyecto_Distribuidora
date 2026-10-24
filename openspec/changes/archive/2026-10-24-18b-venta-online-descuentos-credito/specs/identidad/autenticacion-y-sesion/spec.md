## ADDED Requirements

### Requirement: El bloqueo del inicio de sesión dura 15 minutos desde el último fallo

> Enmienda a ADR-018 (`design.md` D24 del change 18b).

El bloqueo por intentos DEBE regirse por el último fallo contado, tanto por usuario (límite 5) como por IP (límite 20): sea F el último fallo contado (por usuario: posterior al último desbloqueo manual), hay bloqueo si en (F − 15 min, F] hay al menos el límite de fallos y el momento actual es anterior a F + 15 min. La respuesta 429 DEBE informar `F + 15 min` como momento de desbloqueo, dicho como hora HH:MM (24 h) ("Demasiados intentos. Probá de nuevo a las 23:45."); el 429 del inicio de sesión, por IP y por par, DEBE usar siempre la zona `America/Argentina/Buenos_Aires` (ADR-057), de modo que el texto, el código y el estado sean los mismos exista o no la organización o el usuario y NUNCA revelen datos. Un intento rechazado por bloqueo NO DEBE insertarse en `intento_login`, NO DEBE contar como fallo y NO DEBE extender el bloqueo, aunque traiga la contraseña correcta. Al vencer el bloqueo, el cupo DEBE volver entero. El rechazo por bloqueo de usuario DEBE dejar la fila de auditoría `LOGIN_BLOQUEADO_POR_INTENTOS` y todo rechazo por bloqueo DEBE ir al log en nivel WARNING sin la contraseña. Las contraseñas incorrectas de "Mi PIN" (`PIN_AUTORIZACION_PROPIO_DEFINIR`) DEBEN contar como fallos de este mismo contador y un intento de "Mi PIN" durante el bloqueo DEBE responder `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` sin contar. El límite de 5 fallos DEBE contarse por el par (slug de organización, nombre de usuario) tal como se escribió, con la misma comparación exacta que el login, exista o no la organización o el usuario (ADR-057). Todo rechazo de credenciales DEBE verificar la contraseña, contra un hash ficticio si no hay usuario utilizable, para que el tiempo de respuesta no revele si el usuario existe o está activo. La hora del 429 del login DEBE mostrarse siempre en la zona America/Argentina/Buenos_Aires.

#### Scenario: El desbloqueo es 15 minutos después del último fallo

- **GIVEN** cinco fallos de contraseña de Marta a las 10:02, 10:05, 10:07, 10:09 y 10:10
- **WHEN** Marta intenta entrar a las 10:20 con la contraseña correcta
- **THEN** recibe 429 "Demasiados intentos. Probá de nuevo a las 10:25." (hora de `America/Argentina/Buenos_Aires`; el ejemplo da la hora local), no queda fila nueva en `intento_login` y el desbloqueo no se mueve; a las 10:25 entra
- **Regla:** ADR-018 y su enmienda; SEG-04

#### Scenario: Pasado el bloqueo, el primer fallo abre una ventana nueva

- **GIVEN** el bloqueo anterior vencido a las 10:25
- **WHEN** Marta falla la contraseña a las 10:26
- **THEN** ese fallo es el primero de su ventana y no hay bloqueo
- **Regla:** ADR-018 y su enmienda

#### Scenario: El límite por IP usa la misma regla

- **GIVEN** 20 fallos desde una misma IP
- **WHEN** esa IP reintenta durante el bloqueo
- **THEN** se rechaza hasta 15 minutos después del último fallo contado, sin insertar fila ni extender el bloqueo
- **Regla:** ADR-018 y su enmienda

#### Scenario: El desbloqueo manual reinicia solo el límite por usuario

- **GIVEN** un usuario bloqueado por intentos
- **WHEN** un administrador ejecuta `USUARIO_DESBLOQUEAR`
- **THEN** el usuario puede entrar (el marcador lleva la clave de su par y neutraliza los fallos anteriores de esa clave) y el límite por IP no cambia
- **Regla:** ADR-018; ADR-057; AUD-01

#### Scenario: "Mi PIN" comparte el bloqueo

- **GIVEN** cinco contraseñas incorrectas en "Mi PIN" dentro de 15 minutos
- **WHEN** el usuario intenta de nuevo, en "Mi PIN" o en el inicio de sesión, con la contraseña correcta
- **THEN** recibe `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` hasta 15 minutos después del último fallo, sin que el intento bloqueado cuente
- **Regla:** ADR-018; SEG-05; `design.md` D21 punto 5

#### Scenario: Un nombre inexistente se bloquea igual que uno existente

- **GIVEN** el usuario `marta` existe en la organización y `martha` no; cinco fallos de cada una, desde IP distintas
- **WHEN** cada una intenta por sexta vez, 15 minutos después del quinto fallo de la suya
- **THEN** las dos reciben 429 `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` con el mismo texto "Demasiados intentos. Probá de nuevo a las HH:MM."; ninguno inserta fila en `intento_login`; solo `marta` deja la auditoría `LOGIN_BLOQUEADO_POR_INTENTOS` (el bloqueo de `martha` queda solo en el log, nivel WARNING, sin el texto escrito)
- **Regla:** ADR-057, ADR-018; SEG-01

#### Scenario: Un slug inexistente también se bloquea a los cinco fallos

- **GIVEN** cinco fallos con un `organizacion_slug` que no existe y un mismo nombre de usuario
- **WHEN** se intenta por sexta vez con ese mismo par
- **THEN** recibe el mismo 429, con el mismo código y el mismo texto, que un par con organización existente; no se inserta fila ni se escribe auditoría
- **Regla:** ADR-057; SEG-01

#### Scenario: El contador sigue al texto exacto que compara el login

- **GIVEN** cinco fallos escritos como `Marta` en una organización donde existe `marta`
- **WHEN** `marta` intenta entrar con su contraseña correcta
- **THEN** entra: `Marta` no consume el cupo de `marta` (la clave distingue mayúsculas, espacios y organización; el mismo nombre en dos organizaciones son dos contadores)
- **Regla:** ADR-057

#### Scenario: El tiempo de respuesta no revela si el usuario existe

- **GIVEN** un usuario activo, uno inactivo, uno inexistente y un slug inexistente
- **WHEN** cada uno intenta entrar con una contraseña incorrecta
- **THEN** en los cuatro casos se ejecuta una verificación Argon2id (contra un hash ficticio cuando no hay usuario utilizable) y se levanta el mismo `CredencialesInvalidasError`
- **Regla:** ADR-057; SEG-01
