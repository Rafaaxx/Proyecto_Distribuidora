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
