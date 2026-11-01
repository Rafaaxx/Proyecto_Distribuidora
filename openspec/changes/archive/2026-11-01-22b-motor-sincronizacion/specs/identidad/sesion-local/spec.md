## ADDED Requirements

### Requirement: Las pestañas del teléfono no renuevan la sesión a la vez

En un mismo navegador, dos pestañas de la aplicación NO DEBEN renovar la sesión al mismo tiempo: cada renovación DEBE esperar a que termine la anterior, de modo que la siguiente use el refresh token ya rotado y no se revoque la familia del dispositivo por un reuso aparente. El servidor, la cookie y la rotación no cambian (`design.md` D11; `02` §12.1).

#### Scenario: Dos pestañas con el access token vencido
- **GIVEN** dos pestañas de `/ruta` con el access token vencido y el refresh token vigente
- **WHEN** las dos piden algo al servidor a la vez
- **THEN** las dos renuevan una después de la otra, las dos siguen con sesión y la familia del dispositivo no se revoca
- **Regla:** `02` §12.1; ADR-017

#### Scenario: Reuso real de un refresh token
- **GIVEN** un refresh token ya rotado presentado otra vez desde fuera de la aplicación
- **WHEN** llega al servidor
- **THEN** el servidor revoca la familia del dispositivo, igual que antes de este change
- **Regla:** `02` §12.1
