## ADDED Requirements

### Requirement: Motivos, alícuotas y redondeo por defecto explican sus reglas

Las pestañas "Motivos", "Alícuotas de IVA" y "Redondeo por defecto" DEBEN ofrecer ayuda en el ámbito, el nombre y la baja de un motivo, el porcentaje y la baja de una alícuota, y el redondeo por defecto. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos (ninguna de estas reglas tiene números), con los textos que apruebe el usuario (`design.md` D14 del change 20c).

#### Scenario: Ámbito del motivo
- **WHEN** se abre el "(?)" del ámbito
- **THEN** explica que cada motivo se ofrece solo en la operación de su ámbito y que el ámbito no se cambia después del alta, sin ejemplo
- **Regla:** TR-09; ADR-061

#### Scenario: Baja de un motivo
- **WHEN** se abre el "(?)" de "Dar de baja" en Motivos
- **THEN** explica que deja de ofrecerse, que no se borra, que se puede reactivar y que cada ámbito conserva al menos un motivo activo
- **Regla:** CAT-05; TR-06; ADR-061

#### Scenario: Porcentaje de la alícuota
- **WHEN** se abre el "(?)" del porcentaje
- **THEN** explica que no se cambia una vez creada, cómo pasar a otra tasa y que las compras y ventas hechas conservan su porcentaje
- **Regla:** TR-02; CAT-01; ADR-061

#### Scenario: Redondeo por defecto
- **WHEN** se abre el "(?)" del redondeo por defecto
- **THEN** explica que solo precarga la lista nueva y que no cambia las listas existentes ni sus precios
- **Regla:** PRC-01; PRC-14

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
