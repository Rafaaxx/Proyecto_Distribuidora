## MODIFIED Requirements

### Requirement: Un medio de pago declara si exige referencia
Un medio de pago DEBE tener nombre, una marca que indique si exige un dato de referencia al usarse y una marca de actividad (`03` §4). Las organizaciones nuevas DEBEN nacer con Transferencia, Cheque y Tarjeta marcados como que exigen referencia, y Efectivo y Billetera sin esa marca (`01` §4; aprobado por el usuario el 2026-10-16, `design.md` D5 del change 17b).

#### Scenario: Un medio de pago que exige referencia queda marcado
- **GIVEN** la organización inicial
- **WHEN** se lee el medio de pago transferencia
- **THEN** su indicador de referencia obligatoria es legible, forma parte del catálogo y vale `true`
- **Regla:** `01` §4 (medios de pago: lista con indicador de referencia obligatoria)

#### Scenario: Valores por defecto de la siembra
- **GIVEN** una organización recién sembrada
- **WHEN** se leen sus medios de pago
- **THEN** Transferencia, Cheque y Tarjeta exigen referencia, y Efectivo y Billetera no
- **Regla:** `01` §4; COB-02; PAG-01

#### Scenario: Un medio de pago sin nombre se rechaza
- **GIVEN** la operación de alta de un medio de pago
- **WHEN** se la invoca con nombre vacío
- **THEN** falla con un error explícito y no crea el medio de pago
- **Regla:** `03` §4 (`medio_pago`: `nombre` obligatorio)

## ADDED Requirements

### Requirement: Las organizaciones existentes reciben los valores por defecto de referencia

La migración del change 17b DEBE marcar como que exigen referencia los medios llamados "Transferencia", "Cheque" y "Tarjeta" (sin distinguir mayúsculas) de toda organización existente, sin tocar los demás medios, de forma idempotente (`design.md` D5). El `downgrade` NO DEBE revertir esas marcas. La misma migración DEBE hacer único el nombre de un medio por organización sin distinguir mayúsculas, y DEBE abortar con un mensaje claro si ya hay nombres repetidos (D3).

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 17b con sus cinco medios sin referencia obligatoria
- **WHEN** se aplica la migración
- **THEN** Transferencia, Cheque y Tarjeta exigen referencia, y Efectivo y Billetera no
- **Regla:** `01` §4; COB-02; `04` §2.1 punto 4

#### Scenario: Ida y vuelta
- **GIVEN** la migración aplicada
- **WHEN** se aplica `downgrade` y `upgrade` de nuevo
- **THEN** sube y baja limpio, los medios no se duplican y las marcas de referencia quedan como estaban después de la primera subida
- **Regla:** `04` §2.1 punto 4

#### Scenario: Nombres repetidos
- **GIVEN** una organización con dos medios "Billetera" y "billetera"
- **WHEN** se aplica la migración
- **THEN** la migración aborta nombrando la organización y el nombre repetido, sin cambiar nada
- **Regla:** ADR-053

#### Scenario: Cobranza con transferencia después de la migración
- **GIVEN** la migración aplicada
- **WHEN** se registra con conexión una cobranza de $20.000,00 por "Transferencia" sin referencia
- **THEN** la respuesta es 422 con `REFERENCIA_OBLIGATORIA`
- **Regla:** COB-02
