## ADDED Requirements

### Requirement: Se cobra a un cliente desde el teléfono

Con `REGISTRAR_COBRANZA` en los permisos de los datos del día, el área de ruta DEBE ofrecer «Cobrar» en el inicio (con selector de cliente, la cartera primero) y en la ficha del cliente, con o sin señal. Se DEBE poder cobrar a clientes `ACTIVO` y `SUSPENDIDO` de los datos del día, de la cartera o no; al consumidor final NO (no aparece en el selector y su ficha no ofrece «Cobrar»). La pantalla DEBE mostrar el saldo local actual y el resultante, pedir el importe, de 1 a 20 medios activos de los datos del día con su importe y la referencia donde el medio la exige, y una observación opcional de hasta 500 caracteres. «Confirmar cobranza» NO DEBE confirmar si el importe no es mayor que cero o tiene más de dos decimales, si la suma de los medios no es el importe, si falta una referencia exigida o si la observación es más larga; DEBE pedir la confirmación «¿Registrar la cobranza de {importe} a {cliente}?» y, si el saldo resultante queda a favor del cliente, avisar «El cliente queda con {importe} a favor.» antes de guardar. Con datos cargados, salir de la pantalla DEBE pedir «¿Descartar la cobranza?» y la versión nueva de la aplicación DEBE esperar a que termine. Sin permiso, «Cobrar» NO DEBE aparecer (`design.md` D3, D4, D8).

#### Scenario: Cobrar sin señal
- **GIVEN** `vendedor` sin señal, con su jornada abierta y Kiosco La Esquina debiendo $150.000
- **WHEN** cobra $50.000 con $30.000 en efectivo y $20.000 por transferencia n.º 0042 y confirma
- **THEN** ve «Cobranza guardada» «Sin enviar» y la ficha del cliente muestra saldo $100.000
- **Regla:** COB-01; COB-02; COB-04; CRE-08

#### Scenario: Medios que no suman el importe
- **WHEN** el importe es $50.000 y los medios suman $49.000
- **THEN** «Confirmar cobranza» no confirma y se indica la diferencia
- **Regla:** INV-08; COB-02

#### Scenario: Referencia exigida
- **WHEN** un medio que exige referencia queda sin ella o con solo espacios
- **THEN** «Confirmar cobranza» no confirma y se pide la referencia
- **Regla:** COB-02

#### Scenario: Importe inválido
- **WHEN** el importe es cero, negativo o tiene tres decimales
- **THEN** «Confirmar cobranza» no confirma
- **Regla:** COB-01; INV-03

#### Scenario: Saldo a favor
- **GIVEN** Kiosco La Esquina debe $150.000 según el teléfono
- **WHEN** el vendedor cobra $160.000
- **THEN** antes de guardar se avisa «El cliente queda con $10.000 a favor.» y solo se guarda si lo confirma
- **Regla:** COB-01; CC-04

#### Scenario: Consumidor final
- **WHEN** el vendedor abre la ficha del consumidor final o el selector de cliente de «Cobrar»
- **THEN** la ficha no ofrece «Cobrar» y el consumidor final no está en el selector
- **Regla:** COB-01; CLI-03

#### Scenario: Cliente suspendido o fuera de la cartera
- **WHEN** el vendedor cobra a un cliente suspendido o que no está en su cartera
- **THEN** la cobranza se guarda sin aviso
- **Regla:** COB-01; `01` §19

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `REGISTRAR_COBRANZA` en los datos del día
- **WHEN** abre el inicio o la ficha de un cliente
- **THEN** no ve «Cobrar»
- **Regla:** SYN-10; SEG-06

#### Scenario: Salir con datos cargados
- **GIVEN** la pantalla de cobro con un importe cargado
- **WHEN** el vendedor toca el menú inferior
- **THEN** se pregunta «¿Descartar la cobranza?» y, si no confirma, sigue en la pantalla con los datos
- **Regla:** `02` §13.5

### Requirement: Las cobranzas se ven en las pantallas de ruta

El área de ruta DEBE mostrar «Cobranzas de hoy» con las cobranzas independientes de la jornada (cliente, importe, hora y estado de envío) y el detalle de cada una («Cobranza guardada»: cliente, importe, medios, observación, momento, estado y la explicación de sus observaciones o su rechazo con los textos de la tabla de códigos). «Sincronización» DEBE listar las cobranzas «Con observaciones» y «Rechazadas» como «Cobranza a {cliente}». Lo pendiente DEBE decirse uniendo las partes que no son cero («N ventas, M anulaciones y K cobranzas sin enviar»), en el inicio y en los avisos de cierre de sesión y de pendientes de otro usuario. No hay comprobante de cobranza (`design.md` D8, D9, D10, D11).

#### Scenario: Cobranzas de hoy
- **GIVEN** dos cobranzas de la jornada, una «Enviada» y otra «Sin enviar»
- **WHEN** el vendedor abre «Cobranzas de hoy»
- **THEN** ve las dos con cliente, importe, hora y estado
- **Regla:** SYN-09

#### Scenario: Cobranza con observaciones
- **GIVEN** una cobranza aceptada con `MEDIO_INACTIVO` sobre "Billetera"
- **WHEN** el vendedor abre su detalle
- **THEN** ve «Con observaciones» y «El medio Billetera estaba dado de baja cuando llegó el cobro.»
- **Regla:** SYN-07

#### Scenario: Cobranza rechazada en Sincronización
- **GIVEN** una cobranza a Kiosco La Esquina rechazada con `RECURSO_NO_ENCONTRADO`
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve «Cobranza a Kiosco La Esquina» con «El sistema no tiene el cliente o el medio de pago de la cobranza.» y el aviso de que el teléfono ya no la descuenta, con acceso al detalle
- **Regla:** SYN-06; SYN-09

#### Scenario: Código desconocido
- **WHEN** una cobranza vuelve rechazada con un código que no está en la tabla
- **THEN** se muestra el texto general de la cobranza y el código
- **Regla:** SYN-06

#### Scenario: Pendientes
- **GIVEN** dos ventas, una anulación y una cobranza sin enviar
- **WHEN** el vendedor mira el inicio o cierra sesión
- **THEN** lee «2 ventas, 1 anulación y 1 cobranza sin enviar»
- **Regla:** SYN-09

#### Scenario: Solo cobranzas pendientes
- **GIVEN** tres cobranzas sin enviar y nada más
- **WHEN** otro usuario inicia sesión en el teléfono
- **THEN** el aviso dice «Hay 3 cobranzas sin enviar de {vendedor}.»
- **Regla:** SYN-09; INV-05

#### Scenario: Doble sincronización
- **GIVEN** una cobranza «Enviada»
- **WHEN** se sincroniza otra vez
- **THEN** «Cobranzas de hoy» y «Sincronización» no cambian
- **Regla:** INV-06

### Requirement: Cobrar se corta con la jornada no abierta y por debajo de la versión mínima

Cuando el teléfono guardó que su jornada ya no está abierta, o la aplicación está por debajo de la versión mínima, «Cobrar» DEBE quedar deshabilitado en el inicio y en la ficha, con el aviso correspondiente, y «Confirmar cobranza» NO DEBE confirmar (el formulario sigue). La cola DEBE seguir enviándose. Vale sin señal y después de recargar. El aviso de la jornada DEBE terminar con «Lo que ya vendiste y cobraste se sigue enviando.» (`design.md` D7).

#### Scenario: Jornada liberada
- **GIVEN** el teléfono guardó que su jornada fue liberada
- **WHEN** el vendedor abre el inicio o la ficha
- **THEN** «Cobrar» está deshabilitado y se lee «Tu jornada fue liberada. Lo que ya vendiste y cobraste se sigue enviando.»
- **Regla:** RUT-09

#### Scenario: Formulario abierto cuando se corta
- **GIVEN** la pantalla de cobro con datos cargados
- **WHEN** el teléfono se entera de que la jornada no está abierta y el vendedor toca «Confirmar cobranza»
- **THEN** no se guarda nada, los datos siguen y se muestra el aviso
- **Regla:** RUT-09; INV-01

#### Scenario: Versión por debajo de la mínima
- **WHEN** la aplicación está por debajo de la versión mínima conocida
- **THEN** «Cobrar» está deshabilitado con el aviso de versión y las cobranzas guardadas se siguen enviando
- **Regla:** `02` §6.6

#### Scenario: Sin dato guardado
- **WHEN** el teléfono no tiene marcada la jornada como no abierta y la versión está al día
- **THEN** «Cobrar» funciona como siempre
- **Regla:** RUT-09
