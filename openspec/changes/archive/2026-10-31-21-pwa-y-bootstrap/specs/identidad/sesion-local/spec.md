## Purpose

Mantiene la sesión del vendedor en el teléfono sin depender de la red: un PIN de desbloqueo definido con conexión y guardado solo como derivación en el dispositivo, con límite de intentos, cierre de sesión y cambio de usuario que nunca pierden operaciones pendientes (SEG-01, SEG-03, SEG-04, ADR-011, `02` §12.3).

## ADDED Requirements

### Requirement: El PIN de desbloqueo se define con conexión y se guarda derivado

Tras el primer inicio de sesión de un usuario en `/ruta` en un dispositivo, el sistema DEBE pedirle que defina un PIN de desbloqueo antes de continuar: exactamente 6 dígitos, ingresado dos veces, que no sea trivial (todos los dígitos iguales o una escalera de paso 1, ascendente o descendente). El PIN DEBE guardarse en la base local solo como derivación PBKDF2-SHA256 con sal aleatoria de 32 bytes e iteraciones altas, junto con la sal y las iteraciones, y NUNCA DEBE enviarse al servidor ni guardarse en claro (`design.md` D13).

#### Scenario: Definir el PIN
- **GIVEN** `vendedor` recién logueado por primera vez en el teléfono
- **WHEN** ingresa 482915 dos veces
- **THEN** la base local guarda la derivación con su sal e iteraciones, no el PIN, y ninguna petición al servidor lleva el PIN
- **Regla:** SEG-03; ADR-011

#### Scenario: PIN trivial o distinto
- **WHEN** ingresa 111111, 123456 o 654321, o dos PIN distintos
- **THEN** se rechaza con el motivo y no se guarda nada
- **Regla:** ADR-055 (PIN trivial); `design.md` D13

#### Scenario: Definir sin conexión
- **GIVEN** un usuario sin PIN en el dispositivo y sin señal
- **WHEN** abre `/ruta`
- **THEN** se le indica que necesita conexión para iniciar sesión y definir su PIN
- **Regla:** SEG-01; SEG-03

### Requirement: El PIN desbloquea la sesión local con y sin conexión

Al abrir la aplicación (arranque o recarga), `/ruta` DEBE pedir el PIN antes de mostrar datos, con o sin conexión. NO DEBE volver a pedirlo al volver de segundo plano. Con el PIN correcto DEBE mostrar el inicio; con conexión DEBE además renovar el access token con el refresh token. Si la renovación es rechazada, DEBE pedir inicio de sesión y conservar la base local (`design.md` D14).

#### Scenario: Desbloqueo sin señal
- **GIVEN** un bootstrap aplicado y el teléfono sin señal
- **WHEN** el vendedor abre la aplicación e ingresa su PIN
- **THEN** ve el inicio con los datos locales, sin ninguna petición a la red
- **Regla:** SEG-03; ADR-011

#### Scenario: Desbloqueo con conexión
- **GIVEN** el refresh token vigente
- **WHEN** ingresa su PIN con conexión
- **THEN** ve el inicio y la aplicación obtiene un access token nuevo
- **Regla:** ADR-017; `02` §12.3

#### Scenario: El refresh token venció
- **GIVEN** el refresh token vencido o revocado
- **WHEN** desbloquea con conexión
- **THEN** se le pide iniciar sesión y la base local se conserva
- **Regla:** `02` §12.3; ADR-011

#### Scenario: Vuelta de segundo plano
- **WHEN** la aplicación vuelve de segundo plano, sin importar cuánto tiempo estuvo
- **THEN** no pide el PIN; solo lo pide al abrirla de nuevo (arranque o recarga)
- **Regla:** `design.md` D14

### Requirement: Los intentos fallidos bloquean la sesión local

Los fallos de PIN DEBEN contarse en la base local (sobreviven a una recarga) y reiniciarse con un acierto. Al llegar a 10 fallos (constante fija en código, que no depende de `intentos_pin_max` de la organización), la sesión local DEBE bloquearse: se borra la derivación del PIN y se exige iniciar sesión con conexión; los datos maestros y las operaciones pendientes NO DEBEN perderse. Tras el login, el usuario DEBE definir un PIN nuevo (`design.md` D15).

#### Scenario: Décimo fallo
- **GIVEN** nueve fallos seguidos, con `intentos_pin_max` de la organización en cualquier valor
- **WHEN** el vendedor ingresa un PIN incorrecto por décima vez
- **THEN** la sesión local se bloquea, se borra la derivación y se le pide iniciar sesión con conexión
- **Regla:** SEG-04

#### Scenario: Recargar no reinicia la cuenta
- **GIVEN** tres fallos
- **WHEN** recarga la aplicación y falla dos veces más
- **THEN** la sesión local se bloquea
- **Regla:** SEG-04; `design.md` D15

#### Scenario: Nada se pierde
- **GIVEN** la sesión local bloqueada
- **WHEN** el mismo usuario inicia sesión con conexión y define un PIN nuevo
- **THEN** los datos locales y las operaciones pendientes siguen ahí
- **Regla:** SEG-04; SYN-09

### Requirement: Cambiar el PIN de desbloqueo

Desde "Mi cuenta", el usuario DEBE poder cambiar su PIN de desbloqueo ingresando el actual y el nuevo dos veces, con las mismas reglas del alta, con o sin conexión. Un PIN actual incorrecto DEBE contar como fallo.

#### Scenario: Cambio correcto
- **WHEN** ingresa su PIN actual y un PIN nuevo válido dos veces
- **THEN** la derivación se reemplaza y el PIN anterior deja de abrir la aplicación
- **Regla:** SEG-03

#### Scenario: PIN actual incorrecto
- **WHEN** ingresa un PIN actual incorrecto
- **THEN** no se cambia nada y el fallo se suma a la cuenta de intentos
- **Regla:** SEG-04

### Requirement: Cerrar sesión y cambiar de usuario en el dispositivo

El dispositivo DEBE tener una sola sesión local a la vez. "Cerrar sesión" DEBE requerir conexión, revocar la sesión del dispositivo en el servidor y borrar la sesión local, la derivación del PIN y los datos maestros; las operaciones pendientes NO DEBEN borrarse. Si inicia sesión un usuario distinto del de la sesión local, DEBEN borrarse la sesión local y los datos maestros del anterior antes de usar el dispositivo; las operaciones pendientes del anterior se conservan para cuando vuelva a iniciar sesión (`design.md` D16).

#### Scenario: Cerrar sesión
- **GIVEN** `vendedor` con datos locales, con conexión
- **WHEN** toca "Cerrar sesión" y confirma
- **THEN** el servidor revoca la sesión del dispositivo, la base local queda sin sesión, sin PIN y sin datos maestros, y se muestra el login
- **Regla:** ADR-017; `design.md` D16

#### Scenario: Cerrar sesión sin conexión
- **GIVEN** el teléfono sin señal
- **WHEN** el vendedor busca "Cerrar sesión"
- **THEN** está deshabilitado y dice que requiere conexión
- **Regla:** `design.md` D16

#### Scenario: Otro usuario en el mismo teléfono
- **GIVEN** la sesión local de `vendedor`
- **WHEN** `vendedor2` inicia sesión en `/ruta` en el mismo teléfono
- **THEN** se borran la sesión, el PIN y los datos maestros de `vendedor`, y `vendedor2` define su propio PIN
- **Regla:** `02` §12.3; `design.md` D16
