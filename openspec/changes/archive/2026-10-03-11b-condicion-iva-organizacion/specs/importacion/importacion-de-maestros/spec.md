## MODIFIED Requirements

### Requirement: Importar costos informados

La planilla de costos DEBE tener las columnas `producto_codigo`, `presentacion`, `valor`, `incluye_iva`, `bonificacion` (porcentaje, opcional), `vigencia_desde` y `observacion` (opcional); el proveedor es el proveedor actual del producto (CAT-06). En una organización que computa crédito fiscal (CST-06), `incluye_iva` es obligatoria (`S`/`N`). En una que no lo computa, `incluye_iva` es opcional, `valor` es el valor pagado, vacío o `N` se aceptan y `S` DEBE dar `INCLUYE_IVA_NO_APLICA` en la fila, con la regla de todo o nada (ADR-040, `design.md` D6). Cada fila DEBE registrarse por el mismo camino que `COSTO_INFORMAR`: costo base derivado según CST-02 con la regla de IVA de la organización, congelada en el costo, sin sobrescribir costos anteriores (CST-03), con presentación de compra activa del producto, y DEBE congelar las unidades de esa presentación (INV-18). Esta capacidad existe solo si `design.md` D8 del change 10 confirma que la importación de costos entra en la etapa 1.

#### Scenario: Costo por caja sin IVA

- **GIVEN** Cerveza B con presentación "Caja x12" de compra
- **WHEN** se importa una fila con `valor` = `18000`, `incluye_iva` = `N`, sin bonificación
- **THEN** queda un costo informado con costo base `"1500.000000"`
- **Regla:** CST-01; CST-02

#### Scenario: Costo con IVA incluido

- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`, Cerveza B con alícuota 21% y "Caja x12" de compra
- **WHEN** se importa `valor` = `18000`, `incluye_iva` = `S`
- **THEN** el costo base es `"1239.669421"`
- **Regla:** CST-02

#### Scenario: Costo con bonificación

- **WHEN** se importa `valor` = `18000`, `incluye_iva` = `N`, `bonificacion` = `10`
- **THEN** el costo base es `"1350.000000"`
- **Regla:** CST-02; TR-02

#### Scenario: Monotributista importa el valor pagado con la columna vacía

- **GIVEN** una organización `MONOTRIBUTO`, Cerveza B con alícuota 21% y "Caja x12" de compra
- **WHEN** se importa `valor` = `21780` con `incluye_iva` vacía
- **THEN** queda un costo informado con costo base `"1815.000000"` y `computa_credito_fiscal = false`
- **Regla:** CST-02; CST-06; `design.md` D6

#### Scenario: Monotributista con incluye IVA marcado

- **GIVEN** una organización `MONOTRIBUTO` y una planilla de 40 filas válidas salvo la fila 7, con `incluye_iva` = `S`
- **WHEN** se importa
- **THEN** la fila 7 da `INCLUYE_IVA_NO_APLICA` y no se registra ningún costo de la planilla
- **Regla:** CST-06; ADR-040; TR-10; `design.md` D6

#### Scenario: Inscripto sin la columna

- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** una fila trae `incluye_iva` vacía
- **THEN** la fila da el error `VALOR_OBLIGATORIO` de la columna `incluye_iva` y no se registra ningún costo
- **Regla:** CST-01; `design.md` D6

#### Scenario: Presentación que no es de compra

- **GIVEN** la presentación "Botella" de Vino A, solo de venta
- **WHEN** una fila de costos la usa
- **THEN** la fila da `PRESENTACION_INVALIDA`
- **Regla:** CST-01

#### Scenario: La presentación con costo queda congelada

- **GIVEN** un costo importado sobre "Caja x12" de Cerveza B
- **WHEN** después se intenta cambiar sus unidades por pantalla
- **THEN** se rechaza con `UNIDADES_CONGELADAS`
- **Regla:** INV-18; CAT-04
