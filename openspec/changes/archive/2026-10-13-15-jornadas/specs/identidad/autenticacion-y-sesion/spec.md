## MODIFIED Requirements

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
