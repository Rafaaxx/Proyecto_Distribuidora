## ADDED Requirements

### Requirement: El alta de compra avisa el saldo a nuestro favor del proveedor

Al elegir un proveedor cuyo saldo es negativo, el formulario de compra DEBE mostrar un aviso informativo con el saldo a favor de la organización y la indicación de que una compra a crédito se descuenta de ese saldo (PAG-02, `design.md` D3 del change 12). El aviso NO DEBE cambiar la condición elegida ni impedir confirmar; con saldo cero o positivo NO DEBE mostrarse. El saldo se formatea desde el string de la API, sin convertirlo a `number` para calcular.

#### Scenario: Proveedor con saldo a nuestro favor
- **GIVEN** `Bodega Sur` con saldo `"-152460.00"` por una compra de contado anulada sin devolución del pago
- **WHEN** el usuario la elige en "Nueva compra"
- **THEN** ve "Este proveedor tiene saldo a nuestro favor de $ 152.460,00: cargada a crédito, la compra se descuenta de ese saldo"
- **Regla:** PAG-02; CMP-05; ADR-034 punto 8

#### Scenario: Proveedor con deuda
- **GIVEN** `Bodega Sur` con saldo `"153720.00"`
- **WHEN** el usuario la elige en "Nueva compra"
- **THEN** no se muestra el aviso
- **Regla:** PAG-02

#### Scenario: El saldo no se puede leer
- **WHEN** la lectura del saldo falla
- **THEN** el formulario no muestra el aviso y la compra se puede cargar igual
- **Regla:** TR-10 (el aviso es informativo; la validación es del servidor)
