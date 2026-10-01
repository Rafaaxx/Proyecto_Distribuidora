## ADDED Requirements

### Requirement: El estado de facturación inicial pertenece al catálogo cerrado

El alta y la modificación de un cliente DEBEN aceptar como `estado_facturacion_default` solo `NO_REQUIERE`, `PENDIENTE` o el valor nulo (el de la organización, VTA-08). Cualquier otro valor DEBE rechazarse con `ESTADO_FACTURACION_INVALIDO` (422), sin escribir nada y nunca con un error interno. La regla vive en el dominio de clientes: la importación de clientes (change 10) la hereda sin repetirla (TR-10). Agregado por el change 10 (grupo 12) para cerrar una laguna del alta por pantalla, donde el valor inválido llegaba a la base y terminaba en 500.

#### Scenario: Estado de facturación fuera del catálogo

- **GIVEN** la organización A
- **WHEN** un usuario con `GESTIONAR_CLIENTES` envía `CLIENTE_CREAR` con `estado_facturacion_default` = `FACTURADA`
- **THEN** responde 422 con `ESTADO_FACTURACION_INVALIDO` y no se crea ningún cliente
- **Regla:** VTA-08; `03` §10 (`cliente`)

#### Scenario: Estado válido o nulo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREAR` con `PENDIENTE` y otro con el valor nulo
- **THEN** ambos clientes se crean y conservan el valor recibido
- **Regla:** VTA-08
