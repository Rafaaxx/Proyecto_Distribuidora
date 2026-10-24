## ADDED Requirements

### Requirement: Los tipos que reciben secretos no se admiten en el lote

El lote de sincronización NO DEBE admitir, en ningún modo, los tipos de comando declarados con `exige_credenciales_efimeras` (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`): su secreto (contraseña o PIN) viaja fuera del contenido y solo entra por la ruta del tipo. Un ítem de esos tipos DEBE rechazarse con `MODO_NO_ADMITIDO_PARA_TIPO` (422) antes de reservar el `operation_id`, sin dejar fila de `comando`, y su contenido NO DEBE aparecer en los registros. Si el dispositivo está revocado, ese ítem DEBE responderse `DISPOSITIVO_REVOCADO` sin guardarse en `comando_cuarentena`; los demás ítems del mismo lote DEBEN ir a cuarentena como siempre (SYN-06). Un ítem de cualquier tipo que traiga credenciales fuera del contenido DEBE rechazarse como malformado sin guardarlas.

#### Scenario: USUARIO_CREAR por el lote

- **GIVEN** un administrador con `ADMIN_USUARIOS`
- **WHEN** envía `USUARIO_CREAR` por el lote, en modo `ONLINE`
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO`, no queda usuario ni fila de `comando` y el contenido no aparece en los registros
- **Regla:** SYN-06; `02` §17; ADR-056

#### Scenario: Rotar o definir el PIN por el lote, con o sin conexión

- **WHEN** se envía `PIN_AUTORIZACION_ROTAR` o `PIN_AUTORIZACION_PROPIO_DEFINIR` por el lote, en modo `ONLINE` o `OFFLINE`
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO` antes de reservar y el PIN no cambia
- **Regla:** SYN-06; `02` §17; ADR-056

#### Scenario: Un tipo con secretos desde un dispositivo revocado

- **GIVEN** un dispositivo revocado y un lote con un ítem de `USUARIO_CREAR` y otro ítem de otro tipo
- **WHEN** se envía el lote
- **THEN** el ítem de `USUARIO_CREAR` responde `DISPOSITIVO_REVOCADO` sin fila de `comando_cuarentena`, y el otro ítem sí va a cuarentena
- **Regla:** SYN-06; `02` §17; ADR-056
