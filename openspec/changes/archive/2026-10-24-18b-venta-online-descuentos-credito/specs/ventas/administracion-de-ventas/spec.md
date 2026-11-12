## ADDED Requirements

### Requirement: Quien vende conoce su tope, los motivos y los autorizadores

Con `VENDER`, el sistema DEBE ofrecer una lectura de contexto de venta con: si el descuento manual está habilitado y si exige motivo; si el usuario tiene `DESCUENTO_MANUAL`, su tope aplicable (el propio si lo tiene, si no el de su rol) como fracción de texto y si puede autorizar descuentos; si puede superar crédito; los motivos activos del ámbito `DESCUENTO_MANUAL`; y los autorizadores (usuarios activos de la organización, con rol activo, PIN definido y `AUTORIZAR_DESCUENTO` o `SUPERAR_CREDITO`, sin el propio usuario) con su nombre y qué pueden autorizar. NO DEBE exponer la derivación del PIN ni datos de otra organización. El tope NO DEBE agregarse a `GET /yo` ni al token.

#### Scenario: El vendedor ve su tope

- **GIVEN** Pedro, Vendedor, con tope de rol 5 %
- **WHEN** pide el contexto de venta
- **THEN** recibe tope `"0.050000"` y la pantalla muestra "Podés descontar hasta 5 %; más pide autorización"
- **Regla:** DSC-06; SYN-11

#### Scenario: Sin permiso de descuento manual

- **GIVEN** un usuario con `VENDER` y sin `DESCUENTO_MANUAL`
- **WHEN** pide el contexto
- **THEN** recibe que no tiene el permiso y la pantalla deshabilita los porcentajes manuales
- **Regla:** DSC-06; SEG-06

#### Scenario: Los autorizadores no traen el PIN

- **GIVEN** Marta, Supervisor con PIN definido
- **WHEN** Pedro pide el contexto
- **THEN** Marta figura con su nombre y lo que puede autorizar, sin derivación ni sal
- **Regla:** SYN-11; ADR-011

#### Scenario: Sin VENDER

- **WHEN** un usuario sin `VENDER` pide el contexto
- **THEN** se rechaza con `PERMISO_REQUERIDO`
- **Regla:** SEG-06

### Requirement: Quien vende ve el crédito del cliente

Con `VENDER`, el sistema DEBE ofrecer el crédito de un cliente de la organización para vender: límite (vacío = sin control), saldo, disponible, política aplicable y tolerancia aplicable, con la herencia de la organización ya resuelta. Un cliente de otra organización DEBE responder 404.

#### Scenario: Crédito con política heredada

- **GIVEN** Kiosco La Esquina con límite $200.000, saldo $150.000 y sin política propia, y la organización con AUTORIZAR
- **WHEN** Pedro pide su crédito
- **THEN** recibe disponible `"50000.00"` y política `AUTORIZAR`
- **Regla:** CRE-01; CRE-03; `01` §19

#### Scenario: Cliente ajeno

- **WHEN** se pide el crédito de un cliente de otra organización
- **THEN** responde 404
- **Regla:** INV-21; SEG-07

### Requirement: La pantalla de venta muestra descuentos, crédito y pide autorización

La pantalla "Nueva venta" DEBE mostrar el tope del usuario, permitir un porcentaje manual general y uno propio por línea indicando cuál rige en cada línea, mostrar los descuentos automáticos de cada línea, pedir el motivo cuando la organización lo exige, mostrar el crédito del cliente con el saldo resultante y el exceso calculados con el mismo cálculo que el servidor, pedir la aceptación del exceso con ADVERTIR y, cuando haga falta, la autorización con un autorizador y su PIN enmascarado. El PIN NO DEBE guardarse en el navegador. Los errores del servidor DEBEN mostrarse.

#### Scenario: Cuál porcentaje rige en cada línea

- **GIVEN** un general de 5 % y un propio de 10 % en el vino
- **WHEN** se ve el pedido
- **THEN** el vino muestra "10 % (propio)" y las demás líneas "5 % (general)"
- **Regla:** DSC-05

#### Scenario: El propio es de la línea, no del producto

- **GIVEN** un producto con dos líneas (cajas y botellas sueltas) y un propio de 10 % escrito solo en la línea de cajas
- **WHEN** se ve y se confirma el pedido
- **THEN** solo la línea de cajas lleva el `MANUAL` de 10 % y la de botellas no lleva ninguno (o el general, si lo hay)
- **Regla:** DSC-05; DSC-08; ADR-050

#### Scenario: Los descuentos automáticos se ven antes de confirmar

- **GIVEN** una regla vigente que alcanza al pedido
- **WHEN** quien vende arma el pedido
- **THEN** cada línea muestra su descuento automático con el nombre de la regla y el neto, y el total los refleja, sin esperar al aviso `DESCUENTO_DIFIERE`
- **Regla:** DSC-05

#### Scenario: Pedir autorización una sola vez para la misma persona

- **GIVEN** una venta que pasa el tope y excede el crédito con AUTORIZAR, y Marta con los dos permisos
- **WHEN** Pedro elige a Marta como autorizadora
- **THEN** la pantalla pide el PIN de Marta una sola vez
- **Regla:** DSC-06; CRE-05

#### Scenario: BLOQUEAR en pantalla

- **GIVEN** un cliente con política BLOQUEAR y exceso
- **WHEN** se arma la venta
- **THEN** la pantalla no deja confirmar y sugiere aumentar la cobranza o sacar productos
- **Regla:** CRE-07

#### Scenario: PIN incorrecto

- **WHEN** el servidor responde `PIN_INCORRECTO`
- **THEN** la pantalla lo muestra, borra el PIN ingresado y la venta no se confirma
- **Regla:** SEG-05; INV-01

### Requirement: El detalle muestra descuentos y crédito congelados

El detalle de una venta DEBE mostrar, por línea, cada descuento con su origen, regla, porcentaje, importe, motivo y autorizador, y en la cabecera el snapshot de crédito (límite, saldo considerado, disponible, exceso, política, resolución y autorizador). Una venta anterior a este change DEBE mostrarse sin snapshot de crédito.

#### Scenario: Detalle de una venta autorizada

- **GIVEN** una venta con 10 % manual autorizado por Marta y exceso autorizado por PIN
- **WHEN** se abre el detalle
- **THEN** muestra a Marta como autorizadora del descuento y del crédito y el exceso congelado
- **Regla:** DSC-08; CRE-10

#### Scenario: Venta del change anterior

- **WHEN** se abre una venta confirmada antes de este change
- **THEN** el detalle no muestra snapshot de crédito y no falla
- **Regla:** CRE-10
