## ADDED Requirements

### Requirement: La base local guarda las operaciones del dispositivo

La base local DEBE tener, además de las tablas maestras, las tablas de operaciones: ventas, cobranzas, movimientos locales, cola de comandos e intentos del PIN de supervisor, y guardar en `meta` el último correlativo y la última secuencia usados. Pasar de la versión anterior a esta NO DEBE perder la sesión, el PIN de desbloqueo, el identificador del dispositivo ni los datos maestros (`design.md` D3).

#### Scenario: Actualización de la base
- **GIVEN** un teléfono con la base de la versión anterior, sesión, PIN y datos del día
- **WHEN** abre la versión de la aplicación con las tablas de operaciones
- **THEN** la sesión, el PIN, el `dispositivo_id` y los datos del día siguen y las tablas de operaciones existen vacías
- **Regla:** `02` §13.2; ADR-062

### Requirement: El bootstrap no toca las operaciones locales

Aplicar un bootstrap NO DEBE escribir, vaciar ni modificar ventas, cobranzas, movimientos locales, cola, intentos del PIN de supervisor, último correlativo ni última secuencia (`02` §13.4).

#### Scenario: Bootstrap con operaciones pendientes
- **GIVEN** una venta sin enviar con su cobranza, sus movimientos, su comando, un intento fallido de PIN de supervisor y el correlativo 142
- **WHEN** se aplica un bootstrap
- **THEN** todas esas filas y los dos contadores quedan exactamente iguales
- **Regla:** `02` §13.4; SYN-09; INV-01

#### Scenario: Bootstrap que falla con operaciones pendientes
- **GIVEN** una venta sin enviar
- **WHEN** un bootstrap falla a mitad del reemplazo
- **THEN** la venta sigue y los datos maestros son los anteriores
- **Regla:** INV-01
