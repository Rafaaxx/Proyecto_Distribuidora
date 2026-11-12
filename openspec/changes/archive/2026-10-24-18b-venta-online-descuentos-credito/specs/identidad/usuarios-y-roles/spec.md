## ADDED Requirements

### Requirement: La contraseña del alta de usuario viaja fuera del contenido del comando

`USUARIO_CREAR` DEBE recibir la contraseña fuera del contenido: la ruta `POST /api/v1/identidad/usuarios` DEBE separarla del cuerpo antes de armar el contenido y calcular la huella, y entregarla al handler como dato efímero (`SecretStr`) que no se persiste, no se registra y no se incluye en el resultado. El contenido DEBE llevar solo `usuario`, `nombre`, `email` y `rol_id` con `extra="forbid"`: un contenido con `password` adentro DEBE rechazarse como malformado. La contraseña NO DEBE aparecer en la huella, en `comando`, en `comando_cuarentena`, en la auditoría, en el resultado, en los registros ni en el `input` de un error de validación; las reglas de validación de la contraseña no cambian y su mensaje no incluye el valor (`02` §17, ADR-019, ADR-056).

#### Scenario: La contraseña no queda en ningún registro

- **GIVEN** un administrador con `ADMIN_USUARIOS`
- **WHEN** crea un usuario con una contraseña válida y otro intento con una inválida
- **THEN** la contraseña no aparece en la huella, `comando`, la auditoría, el resultado, los registros ni la respuesta de error, y el usuario creado inicia sesión con ella
- **Regla:** `02` §17; ADR-019; ADR-022

#### Scenario: Dos contraseñas distintas dan la misma huella

- **GIVEN** un alta aceptada
- **WHEN** se reenvía con el mismo `Operation-Id`, el mismo contenido y otra contraseña
- **THEN** devuelve el resultado original sin volver a derivar la contraseña
- **Regla:** INV-06; SYN-02

#### Scenario: Un contenido con contraseña adentro

- **WHEN** el contenido del comando trae `password`
- **THEN** se rechaza como malformado
- **Regla:** `02` §17; ADR-056
