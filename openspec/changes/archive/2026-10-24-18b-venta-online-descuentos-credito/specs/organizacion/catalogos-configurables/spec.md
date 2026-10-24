## ADDED Requirements

### Requirement: Toda organización tiene motivos de descuento manual

Toda organización DEBE tener motivos activos del ámbito `DESCUENTO_MANUAL`, sembrados de forma idempotente en las organizaciones que no tienen ninguno, para que una organización que exige motivo pueda vender con descuento manual. Los motivos sembrados son los aprobados por el usuario (`design.md` D13).

#### Scenario: Organización nueva

- **WHEN** se crea una organización
- **THEN** tiene los motivos aprobados del ámbito `DESCUENTO_MANUAL`, activos
- **Regla:** TR-09; DSC-06

#### Scenario: La siembra no duplica

- **GIVEN** una organización que ya tiene motivos de `DESCUENTO_MANUAL`
- **WHEN** se vuelve a correr la siembra o la migración
- **THEN** no se agrega ninguno
- **Regla:** TR-09

#### Scenario: Motivos por API

- **WHEN** se piden los motivos del ámbito `DESCUENTO_MANUAL`
- **THEN** se devuelven solo los activos de esa organización
- **Regla:** TR-09; INV-21
