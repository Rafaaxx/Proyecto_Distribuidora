## ADDED Requirements

### Requirement: Cada ruta declarada en la cobertura de aislamiento apunta a pruebas que existen

La cobertura de aislamiento DEBE asociar cada ruta de negocio con una o más pruebas identificadas por archivo y nombre. La verificación de rutas DEBE fallar, nombrando la ruta, si alguna prueba asociada no existe o no cita INV-21, y DEBE fallar si una ruta declarada ya no existe. Así, que las 174 rutas de negocio actuales estén declaradas significa que cada una fue ejercida con un usuario de otra organización (INV-21; `02` §8, §15; `design.md` D11).

#### Scenario: Una ruta apunta a una prueba inexistente
- **GIVEN** una ruta de negocio declarada en la cobertura con una prueba que no existe
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** falla nombrando la ruta y la prueba
- **Regla:** INV-21

#### Scenario: Una prueba asociada no cita INV-21
- **GIVEN** una ruta asociada a una prueba que existe pero no cita INV-21
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** falla nombrando la ruta y la prueba
- **Regla:** INV-21; `02` §15 (cada invariante citado por identificador)

#### Scenario: Una ruta declarada que ya no existe
- **GIVEN** una ruta declarada en la cobertura que la aplicación ya no registra
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** falla nombrando la ruta sobrante
- **Regla:** INV-21

#### Scenario: El resultado de la verificación de consistencia es de la organización del token
- **GIVEN** dos organizaciones con resultados de verificación de consistencia
- **WHEN** el administrador de una pide el resultado
- **THEN** recibe solo el de su organización
- **Regla:** INV-21; SEG-07
