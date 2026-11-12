# ADR-019 — PIN de autorización derivado en el servidor

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/01` §14, ADR-011, change 03 |

## Contexto

Los supervisores tienen un PIN de autorización que los vendedores usan para aprobar excepciones sin conexión (exceso de crédito, descuento fuera de tope). El PIN se verifica localmente en el dispositivo. Hay que decidir quién hace la derivación PBKDF2: el cliente antes de enviar, o el servidor al recibirlo.

## Decisión

El PIN llega en texto plano en el cuerpo del request HTTPS. El servidor:
1. Valida longitud mínima de 6 dígitos y rechaza PINs triviales (secuencias, repeticiones).
2. Deriva con PBKDF2-HMAC-SHA256, sal aleatoria de 32 bytes, iteraciones altas.
3. Guarda hash y sal en `usuario.pin_autorizacion_hash` y `usuario.pin_autorizacion_sal`.

El bootstrap descarga la derivación PBKDF2 del PIN de cada supervisor activo para verificación local offline (ADR-011).

## Consecuencias

- El servidor controla la política de calidad del PIN (longitud, trivialidad) porque ve el valor antes de derivarlo.
- Rotar o invalidar el PIN desde administración es posible sin que el supervisor cambie nada: el admin genera uno nuevo, el servidor lo deriva y lo distribuye en el próximo bootstrap.
- Si el cliente derivara primero, los bytes derivados se convertirían en el secreto real y el servidor no podría validar nada sobre el PIN original.
- El PIN viaja cifrado por TLS como cualquier contraseña; no es diferente a un password convencional.
- **Riesgo aceptado (de ADR-011):** los hashes del PIN de supervisores en el dispositivo pueden atacarse offline con acceso físico. La mitigación es longitud mínima + rotación periódica + límite de intentos en la UI + toda autorización offline queda auditada.

## Alternativas consideradas

- **Cliente deriva, servidor recibe bytes opacos:** el hash se convierte en el secreto. El servidor no puede rechazar `000000` ni forzar rotación sin cooperación del cliente. Descartado.

## Enmienda del change 18b (ADR-055)

(1) **Qué es un PIN trivial** (punto 1, que hasta ahora solo controlaba longitud y dígitos): todos los dígitos iguales (`000000`, `777777`) o una escalera de paso 1, ascendente o descendente, sin vuelta (`123456`, `012345`, `456789`, `987654`), de cualquier largo. Se rechaza con `IDENTIDAD_PIN_AUTORIZACION_INVALIDO`, sin el valor en el mensaje. Vale para los **dos** comandos de definición del PIN (`PIN_AUTORIZACION_ROTAR` y `PIN_AUTORIZACION_PROPIO_DEFINIR`) y solo al definir: un PIN vigente que sea trivial sigue validando hasta que se cambie. (2) **El PIN llega fuera del contenido del comando:** sigue en texto plano en el cuerpo HTTPS, pero la ruta lo separa antes de armar el contenido y la huella y lo entrega al handler por clausura; ni la huella, ni `comando`, ni la cuarentena, ni la auditoría, ni el resultado, ni los registros lo contienen (antes la rotación lo llevaba dentro del contenido: se corrige). (3) El servidor no conoce el PIN de desbloqueo local (vive solo en el dispositivo, `02` §12.4) y no puede compararlo con el de autorización: son dos secretos independientes; si se quiere controlar la igualdad, lo hace el dispositivo. (4) Además de la verificación local sin conexión, el servidor verifica el PIN con conexión cuando una venta lo necesita (ADR-011, enmienda del change 18b).
