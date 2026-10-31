## Purpose

Permite al vendedor armar y confirmar una venta en el teléfono, con o sin señal, con los datos y los permisos que bajó al abrir la jornada, aplicando antes de encolar las reglas que puede evaluar localmente (`design.md` D1, D6 a D9, D14; `00` §9 criterios 5 y 6).

## ADDED Requirements

### Requirement: La venta de ruta se confirma siempre en el teléfono

Toda venta de `/ruta` DEBE confirmarse en el teléfono y quedar en la cola como comando sin conexión, haya o no señal; NO DEBE enviarse por la ruta de venta con conexión. "Vender" DEBE ofrecerse solo con `VENDER` entre los permisos del bootstrap, la jornada abierta y los datos del día descargados (`design.md` D1).

#### Scenario: Con señal
- **GIVEN** `vendedor` con señal y su jornada abierta
- **WHEN** confirma una venta
- **THEN** la venta queda en el teléfono como "Sin enviar" y no se llama a la ruta de venta con conexión
- **Regla:** SYN-01; `02` §13.1

#### Scenario: Sin señal
- **GIVEN** `vendedor` con la red cortada y su jornada abierta
- **WHEN** confirma una venta
- **THEN** la venta se confirma igual y queda como "Sin enviar"
- **Regla:** SYN-05; `00` §9 criterio 5

#### Scenario: Sin el permiso de vender
- **GIVEN** un usuario cuyo bootstrap no trae `VENDER`
- **WHEN** abre el inicio de `/ruta`
- **THEN** no aparece "Vender"
- **Regla:** SYN-10; SEG-06

### Requirement: El pedido usa los precios, los descuentos y las presentaciones del bootstrap

El pedido DEBE armarse en cajas y unidades con las presentaciones de venta, el precio de la versión vigente al momento de la venta de la lista que corresponde al cliente, los descuentos automáticos de las reglas vigentes y el descuento manual general o por línea, con el mismo cálculo que el servidor. Un producto sin precio en la versión NO DEBE poder agregarse. Otra lista o una versión anterior DEBEN ofrecerse solo con `USAR_LISTA_ANTERIOR` y, si la organización exige motivo, con un motivo activo del bootstrap (`design.md` D7).

#### Scenario: Pedido en cajas y unidades
- **GIVEN** Vino A en caja x6 a $12.500 en la versión vigente
- **WHEN** el vendedor carga 2 cajas y 3 botellas
- **THEN** la línea suma 15 botellas y su bruto es $31.250,00
- **Regla:** PRC-22; VTA-02

#### Scenario: Descuento manual general
- **GIVEN** un pedido con Vino A en $29.687,50 tras una regla de volumen y un tope propio de 10 %
- **WHEN** el vendedor aplica 5 % general
- **THEN** el vino lleva $1.484,38 de descuento manual y la venta no pide autorización
- **Regla:** DSC-05; DSC-06

#### Scenario: Lista anterior sin permiso
- **GIVEN** `vendedor` sin `USAR_LISTA_ANTERIOR`
- **WHEN** arma una venta
- **THEN** no se ofrece elegir otra lista ni otra versión
- **Regla:** PRC-21

#### Scenario: Lista anterior sin motivo
- **GIVEN** un usuario con `USAR_LISTA_ANTERIOR`, una organización que exige motivo y una versión anterior elegida
- **WHEN** intenta confirmar sin motivo
- **THEN** la venta no se confirma y se pide el motivo
- **Regla:** PRC-21

#### Scenario: Producto sin precio
- **GIVEN** un producto sin precio en la versión de la venta
- **WHEN** el vendedor lo busca
- **THEN** se muestra "Producto sin precio en la lista: no se puede vender." y no se puede agregar
- **Regla:** VTA-10

### Requirement: El teléfono aplica las reglas del cliente antes de encolar

El teléfono NO DEBE confirmar una venta a un cliente `SUSPENDIDO` sin `VENDER_CLIENTE_SUSPENDIDO` entre los permisos del bootstrap. Al consumidor final DEBE exigirle una cobranza exactamente igual al total, haya o no señal, y NO DEBE mostrarle el panel de crédito (`design.md` D7, D8; ADR-054 punto 24).

#### Scenario: Cliente suspendido sin permiso
- **GIVEN** un cliente suspendido y `vendedor` sin `VENDER_CLIENTE_SUSPENDIDO`
- **WHEN** intenta confirmar
- **THEN** la venta no se confirma y se informa que el cliente está suspendido
- **Regla:** CLI-02

#### Scenario: Consumidor final con cobro parcial
- **GIVEN** una venta de $4.300 al consumidor final con $4.000 cobrados
- **WHEN** el vendedor intenta confirmar sin señal
- **THEN** la venta no se confirma y se muestra "Cargá una cobranza igual al total para poder confirmar."
- **Regla:** CLI-03; VTA-11; ADR-054

#### Scenario: Consumidor final con cobro de más
- **GIVEN** una venta de $4.300 al consumidor final con $5.000 cobrados
- **WHEN** el vendedor intenta confirmar
- **THEN** la venta no se confirma con el mismo aviso
- **Regla:** CLI-03; VTA-11

#### Scenario: Consumidor final de contado
- **GIVEN** una venta de $4.300 al consumidor final con $4.300 cobrados
- **WHEN** el vendedor confirma
- **THEN** la venta se confirma con la evaluación de crédito `SIN_EXCESO`
- **Regla:** CLI-03; CRE-10

### Requirement: El stock insuficiente bloquea salvo con PERMITIR_STOCK_NEGATIVO

Si una línea supera el stock disponible local del vehículo, el teléfono NO DEBE confirmar la venta, salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO` entre los permisos del bootstrap. Sin el permiso, DEBE informar lo que queda e indicar que se actualicen los datos con señal. Con el permiso, DEBE avisar en la línea con lo que queda y pedir una confirmación expresa ("Vender igual"); el servidor deja `STOCK_NEGATIVO` como red de seguridad (`design.md` D6 = C).

#### Scenario: Sin el permiso, la línea que supera el stock bloquea
- **GIVEN** 48 botellas disponibles de Vino A y `vendedor` sin `PERMITIR_STOCK_NEGATIVO`
- **WHEN** carga 50 y quiere confirmar
- **THEN** la línea informa "Supera el stock del vehículo (quedan 48)", la venta no se confirma y el mensaje indica actualizar los datos con señal
- **Regla:** STK-06; RUT-04

#### Scenario: Con el permiso, aviso y "Vender igual"
- **GIVEN** 48 botellas disponibles de Vino A y un usuario con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** carga 50 y confirma
- **THEN** la línea avisa "Supera el stock del vehículo (quedan 48)", se pide "Vender igual" y, aceptado, la venta se confirma y el disponible queda en −2
- **Regla:** STK-06; SYN-05

#### Scenario: Con el permiso, cancela ante el aviso
- **GIVEN** el aviso de stock insuficiente de un usuario con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** no acepta "Vender igual"
- **THEN** no se confirma nada y el carrito sigue abierto
- **Regla:** INV-01

### Requirement: El crédito se evalúa sin conexión con el saldo local

El teléfono DEBE evaluar el crédito como sin conexión, con el saldo local, el límite, la política y la tolerancia del bootstrap: con ADVERTIR pide aceptar el exceso; con AUTORIZAR confirma por tolerancia si el exceso no la supera y, si la supera, exige `SUPERAR_CREDITO` propio o el PIN de un supervisor con ese permiso; con BLOQUEAR no confirma. La venta DEBE guardar y encolar la evaluación (`design.md` D9).

#### Scenario: Exceso dentro de la tolerancia
- **GIVEN** límite $200.000, saldo local $150.000, política AUTORIZAR y tolerancia de $20.000
- **WHEN** el vendedor confirma una venta de $80.000 con $20.000 cobrados
- **THEN** la venta se confirma con resolución `TOLERANCIA_OFFLINE`, exceso $10.000 y saldo considerado $150.000
- **Regla:** CRE-06; CRE-10

#### Scenario: Exceso fuera de la tolerancia
- **GIVEN** el mismo caso con tolerancia de $5.000 y `vendedor` sin `SUPERAR_CREDITO`
- **WHEN** intenta confirmar
- **THEN** se pide el PIN de un supervisor con `SUPERAR_CREDITO`; sin él la venta no se confirma
- **Regla:** CRE-06; CRE-05

#### Scenario: Política bloquear
- **GIVEN** límite $200.000, saldo local $150.000 y política BLOQUEAR
- **WHEN** el vendedor intenta confirmar una venta de $80.000 con $20.000 cobrados
- **THEN** la venta no se confirma y se sugiere cobrar más o sacar productos
- **Regla:** CRE-07

#### Scenario: Política advertir sin aceptar
- **GIVEN** política ADVERTIR y una venta que deja un exceso de $10.000
- **WHEN** el vendedor intenta confirmar sin aceptar el exceso
- **THEN** la venta no se confirma hasta que lo acepta; aceptado, queda con resolución `ADVERTENCIA_ACEPTADA`
- **Regla:** CRE-04

### Requirement: La venta confirmada se muestra con su número y su estado

Al confirmar, el teléfono DEBE mostrar el número asignado, el total, el estado "Sin enviar" y las acciones "Compartir nota" (si el navegador comparte archivos), "Descargar nota" y "Nueva venta" (`design.md` D14).

#### Scenario: Venta guardada
- **WHEN** `vendedor` confirma su primera venta del día en un teléfono con prefijo V03 y último correlativo 141
- **THEN** ve "Venta V03-000142", el total, "Sin enviar" y las acciones de la nota
- **Regla:** VTA-06; VTA-13
