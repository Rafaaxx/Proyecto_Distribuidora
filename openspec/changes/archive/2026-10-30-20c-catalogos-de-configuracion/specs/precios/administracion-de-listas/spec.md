## ADDED Requirements

### Requirement: El formulario de una lista nueva precarga el redondeo por defecto

Al crear una lista, el formulario DEBE precargar el múltiplo y la dirección del redondeo por defecto de la organización cuando está definido. Si no está definido, el múltiplo DEBE quedar vacío y la dirección sin elegir, ambos obligatorios (PRC-01); el formulario NO DEBE traer valores fijos en el código. El usuario DEBE poder cambiar lo precargado antes de guardar. La edición de una lista existente DEBE mostrar siempre su propio redondeo (`01` §4; `design.md` D11 del change 20c).

#### Scenario: Con redondeo por defecto definido
- **GIVEN** el redondeo por defecto de la organización en múltiplo `100` y dirección "Hacia arriba"
- **WHEN** un usuario con `GESTIONAR_LISTAS` abre "Nueva lista"
- **THEN** el formulario trae `100` y "Hacia arriba"
- **Regla:** `01` §4 (el redondeo por defecto solo precarga el formulario de una lista nueva)

#### Scenario: Sin redondeo por defecto
- **GIVEN** el redondeo por defecto sin definir
- **WHEN** abre "Nueva lista"
- **THEN** el múltiplo está vacío y la dirección sin elegir, y el formulario no se envía hasta completarlos
- **Regla:** PRC-01; `design.md` D11 del change 20c

#### Scenario: Una lista existente muestra su redondeo
- **GIVEN** la lista General con redondeo `100` "Hacia arriba" y el redondeo por defecto en `500` "Hacia abajo"
- **WHEN** se edita la lista General
- **THEN** el formulario muestra `100` y "Hacia arriba"
- **Regla:** PRC-01
