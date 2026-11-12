## MODIFIED Requirements

### Requirement: Guardar el crédito no evalúa el crédito

El sistema DEBE guardar los tres campos como datos, sin resolverlos: NO DEBE calcular crédito disponible ni exceso, NO DEBE aplicar la política ni la tolerancia, NO DEBE crear observaciones, NO DEBE bloquear ni autorizar nada y NO DEBE modificar ningún saldo. Ninguna respuesta de las consultas de administración de clientes DEBE incluir `disponible`, `exceso` ni `politica_aplicada`. La resolución del crédito ocurre en la venta y en la sincronización, con el saldo real (CRE-01, CRE-09, CRE-10; `design.md` D8). La única lectura que expone el disponible y la política aplicable es la de crédito para vender, con `VENDER` (`01` §19: el vendedor ve el crédito disponible de sus clientes; change 18b, D16).

#### Scenario: Guardar un límite no altera ninguna otra fila

- **GIVEN** la organización A con sus tablas de libros y saldos
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `limite_credito = "150000.00"`
- **THEN** la única fila que cambia es la del cliente y su auditoría, y no se inserta ningún movimiento ni cambia ningún saldo
- **Regla:** CRE-01; CC-04; INV-13

#### Scenario: Guardar la política BLOQUEAR no bloquea nada

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `politica_credito = BLOQUEAR`
- **THEN** el comando queda `ACEPTADO` y ninguna operación ya registrada cambia
- **Regla:** CRE-03; CRE-07; `design.md` D8

#### Scenario: Las consultas no exponen cálculos de crédito

- **GIVEN** un cliente con límite `"150000.00"`
- **WHEN** se pide su detalle
- **THEN** la respuesta trae `limite_credito`, `politica_credito` y la tolerancia, y no trae `disponible`, `exceso` ni `politica_aplicada`
- **Regla:** CRE-01; CRE-10; `design.md` D8

#### Scenario: La lectura para vender sí trae el disponible

- **GIVEN** un cliente con límite `"150000.00"` y saldo `"100000.00"`
- **WHEN** un usuario con `VENDER` pide su crédito para vender
- **THEN** la respuesta trae disponible `"50000.00"` y la política aplicable
- **Regla:** CRE-01; `01` §19
