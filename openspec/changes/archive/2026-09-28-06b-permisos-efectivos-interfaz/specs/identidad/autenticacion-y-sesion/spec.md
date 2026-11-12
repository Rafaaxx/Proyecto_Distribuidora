## ADDED Requirements

### Requirement: La renovación y el inicio de sesión exigen usuario y rol activos

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja las opciones aprobadas: D9.2-A (código de rechazo existente), D9.3-B (corte con canal acotado para la cola offline) y D9.4-A (rol inactivo igual que usuario inactivo).

La renovación de sesión DEBE verificar, después de validar el refresh token, que el usuario está `ACTIVO` y que su rol está activo. Si no lo están, DEBE:

- rechazar la renovación con el mismo rechazo genérico de un refresh token inválido;
- revocar todas las sesiones de refresh de ese usuario, en todos sus dispositivos, con un motivo que distinga usuario inactivo de rol inactivo;
- auditar la revocación.

La revocación DEBE persistir aunque la respuesta sea un error.

La única excepción (D9.3-B) es un dispositivo con una jornada no cerrada de ese usuario. Ahí la renovación se permite, y el access token resultante solo sirve para entregar la cola de sincronización, porque toda otra ruta rechaza al usuario inactivo. Hasta que existan las jornadas, la excepción no puede cumplirse.

El inicio de sesión DEBE rechazar, con el mismo rechazo genérico que ya usa para un usuario inactivo, a un usuario cuyo rol está inactivo, sin revelar la causa (SEG-01).

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
