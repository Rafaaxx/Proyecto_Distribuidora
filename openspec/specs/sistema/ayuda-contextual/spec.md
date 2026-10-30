# Sistema - Ayuda contextual

## Purpose

Explicar en pantalla, junto al campo, las reglas de negocio que no son obvias (descuentos, topes, precios, costos, toma de ubicación), con textos cortos y un ejemplo numérico, y páginas "Ver más" para los temas largos, sin inventar reglas: cada texto se apoya en una regla de `docs/01-dominio.md` o en un ADR vigente (ADR-051).

## Requirements

### Requirement: El botón de ayuda se abre con clic, tap o teclado

Junto a cada campo o concepto con ayuda, la interfaz DEBE mostrar un botón "(?)" que abre un panel con la explicación. El panel DEBE abrirse con clic, con tap (la app se usa en el teléfono, no alcanza con pasar el puntero) y con Enter o Espacio sobre el botón; y DEBE cerrarse con Escape, con un clic o tap fuera del panel o volviendo a activar el botón. Al cerrarse con Escape el foco DEBE volver al botón. Abrir la ayuda NO DEBE enviar el formulario ni cambiar ni perder lo cargado. A lo sumo un panel de ayuda DEBE estar abierto a la vez en la pantalla.

#### Scenario: Abrir con clic y cerrar con Escape

- **GIVEN** el formulario de una regla de descuento con el campo "Medida" a medio cargar
- **WHEN** la persona hace clic en el "(?)" de "Medida" y después presiona Escape
- **THEN** el panel se abre con la explicación de las cajas equivalentes, se cierra con Escape, el foco vuelve al botón y lo cargado sigue igual
- **Regla:** DSC-03; ADR-051

#### Scenario: Abrir con teclado

- **GIVEN** el foco en el "(?)" de "Prioridad"
- **WHEN** la persona presiona Enter (o Espacio)
- **THEN** el panel se abre, y el botón no envía el formulario
- **Regla:** DSC-05; ADR-051

#### Scenario: Cerrar con un clic afuera

- **GIVEN** el panel de "Acumulable" abierto
- **WHEN** la persona hace clic fuera del panel
- **THEN** el panel se cierra
- **Regla:** ADR-051

#### Scenario: Un solo panel abierto

- **GIVEN** el panel de "Medida" abierto
- **WHEN** la persona abre el "(?)" de "Umbral"
- **THEN** el de "Medida" se cierra y queda abierto solo el de "Umbral"
- **Regla:** ADR-051

### Requirement: La ayuda es accesible con lector de pantalla

El botón DEBE tener un nombre accesible que nombre el concepto ("Ayuda: Medida"), DEBE informar si el panel está abierto o cerrado y DEBE quedar asociado al panel que controla. El botón NO DEBE estar dentro de la etiqueta del campo (activarlo no mueve el foco al control). En el teléfono el panel DEBE quedar dentro del ancho de la pantalla, sin desplazamiento horizontal.

#### Scenario: Nombre y estado

- **GIVEN** el "(?)" de "Tope de descuento (%)" cerrado
- **WHEN** un lector de pantalla lo anuncia y la persona lo activa
- **THEN** se anuncia "Ayuda: Tope de descuento", contraído, y al activarlo pasa a expandido y el panel queda asociado al botón
- **Regla:** DSC-06; ADR-051

### Requirement: El texto es corto, trae un ejemplo y cita su regla

Cada ayuda DEBE tener un título, un texto de 2 o 3 líneas y, cuando la regla tiene números, un ejemplo numérico tomado de `docs/01-dominio.md` o de un ADR vigente. Cada ayuda DEBE citar al menos un identificador de regla (`DSC-03`, `PRC-13`, `CST-11`, `STK-09`, …) o de ADR que exista en `docs/`. Los identificadores sirven para mantener el texto y no se muestran en la pantalla. Una ayuda con tema largo DEBE ofrecer un enlace "Ver más" a su página.

#### Scenario: Texto con ejemplo

- **GIVEN** el "(?)" de "Medida" en una regla de descuento
- **WHEN** se abre
- **THEN** explica que las cajas equivalentes suman las unidades de cada producto divididas por las de su caja, con el ejemplo "15 botellas de un vino que viene de a 6 son 2,5 cajas", y ofrece "Ver más" hacia "Cómo se aplican los descuentos"
- **Regla:** DSC-03; ADR-050

#### Scenario: Una ayuda sin regla citada no pasa las pruebas

- **GIVEN** una entrada del archivo de textos sin ningún identificador de regla, o con uno que no existe en `docs/01-dominio.md` ni en `docs/adr/`
- **WHEN** corren las pruebas del frontend
- **THEN** la prueba de trazabilidad falla y nombra la clave
- **Regla:** ADR-051

### Requirement: Todos los textos viven en un único archivo

Los textos de ayuda (los cortos y los de las páginas "Ver más") DEBEN vivir en un único archivo del frontend, identificados por clave. Ninguna pantalla DEBE escribir un texto de ayuda por su cuenta. Usar una clave que no existe en el archivo DEBE fallar al compilar y en las pruebas.

#### Scenario: Clave inexistente

- **GIVEN** una pantalla que pide la ayuda `descuentos.medidda` (mal escrita)
- **WHEN** se compila y corren las pruebas
- **THEN** la verificación de tipos falla y la prueba que recorre las claves usadas en `frontend/src` también, nombrando la clave y el archivo
- **Regla:** ADR-051

#### Scenario: Corregir un texto en un solo lugar

- **GIVEN** el texto de "Prioridad", usado en el formulario de regla
- **WHEN** se corrige su entrada en el archivo de textos
- **THEN** el cambio se ve en todas las pantallas que lo usan, sin tocar ninguna pantalla
- **Regla:** ADR-051

### Requirement: Las páginas "Ver más" explican los temas largos

`/admin` DEBE ofrecer una página de ayuda con el índice de temas y una página por tema: "Cómo se aplican los descuentos", "Cómo funcionan los topes" y "Cómo se calcula el precio de una lista". Las páginas NO DEBEN pedir datos al servidor ni depender de permisos: las ve todo usuario con sesión en `/admin`, desde una entrada "Ayuda" del menú. El enlace "Ver más" de un panel DEBE abrir la página en otra pestaña, para no perder lo cargado en el formulario. Un tema inexistente DEBE mostrar "No encontramos ese tema de ayuda" con un enlace al índice.

#### Scenario: Cómo se aplican los descuentos

- **GIVEN** un usuario con sesión en `/admin`
- **WHEN** abre "Cómo se aplican los descuentos"
- **THEN** lee, en orden: que la condición se mide sobre cantidades y brutos originales; que entre las no acumulables gana una sola en toda la venta, la de mayor beneficio, y la prioridad solo desempata (número más bajo, mayor prioridad); que las acumulables se aplican después, en orden de prioridad, cada una sobre el resultado anterior (8 % y luego 2 % equivalen a 9,84 %); y que al final se aplica el descuento manual
- **Regla:** DSC-03, DSC-04, DSC-05; ADR-050

#### Scenario: Cómo funcionan los topes

- **GIVEN** un usuario con sesión en `/admin`
- **WHEN** abre "Cómo funcionan los topes"
- **THEN** lee que el tope limita solo el descuento manual, no los automáticos; que se evalúa una vez por venta contra el mayor porcentaje manual aplicado en alguna línea; que superarlo pide autorización de alguien con `AUTORIZAR_DESCUENTO`, que una autorización cubre toda la venta y que quien autoriza no está limitado por su propio tope; y que los roles nacen con tope 0 % salvo el Administrador
- **Regla:** DSC-06; ADR-050

#### Scenario: Cómo se calcula el precio de una lista

- **GIVEN** un usuario con sesión en `/admin`
- **WHEN** abre "Cómo se calcula el precio de una lista"
- **THEN** lee el camino costo de referencia → regla de margen (por precedencia) → redondeo, con el ejemplo del vino de costo de referencia $6.000: markup 30 % da $7.800,00 y margen bruto 30 % da $8.571,43, que con múltiplo 100 queda $8.600 arriba, $8.600 al más cercano y $8.500 abajo
- **Regla:** PRC-11, PRC-12, PRC-13, PRC-14

#### Scenario: Ver más no pierde el formulario

- **GIVEN** un formulario de regla de descuento a medio cargar y el panel de "Acumulable" abierto
- **WHEN** la persona sigue "Ver más"
- **THEN** la página se abre en otra pestaña y el formulario sigue con lo cargado
- **Regla:** ADR-051

#### Scenario: Tema inexistente

- **GIVEN** un usuario con sesión
- **WHEN** abre `/admin/ayuda/no-existe`
- **THEN** ve "No encontramos ese tema de ayuda" y un enlace al índice
- **Regla:** ADR-051

#### Scenario: Usuario sin permisos de descuentos

- **GIVEN** un usuario del rol Administración (sin `GESTIONAR_DESCUENTOS`)
- **WHEN** abre "Ayuda" en el menú
- **THEN** ve los tres temas y puede leerlos; no se pide nada al servidor
- **Regla:** ADR-051

### Requirement: Las pantallas de descuentos explican sus reglas

El formulario de regla de descuento DEBE ofrecer ayuda en "Alcance de la regla", "Medida", "Umbral", "Acción", "Prioridad", "Acumulable" y en la vigencia; el detalle de una regla, junto a "Activar", DEBE explicar que una regla activada ya no se edita; la pantalla "Topes por rol" DEBE ofrecer ayuda en "Tope de descuento (%)". El contenido de cada una es el del inventario de `design.md` D9.

#### Scenario: Umbral

- **GIVEN** el formulario de una regla
- **WHEN** se abre el "(?)" de "Umbral"
- **THEN** explica que es el número que hay que alcanzar, que en cajas admite decimales (2,5), en unidades solo enteros (60) y en importe pesos con centavos ($31.250,00)
- **Regla:** DSC-03

#### Scenario: Prioridad

- **GIVEN** el formulario de una regla
- **WHEN** se abre el "(?)" de "Prioridad"
- **THEN** explica que el número más bajo es la mayor prioridad, que entre no acumulables gana la de mayor beneficio y la prioridad solo desempata, y que entre acumulables fija el orden
- **Regla:** DSC-05; ADR-050

#### Scenario: Acumulable

- **GIVEN** el formulario de una regla
- **WHEN** se abre el "(?)" de "Acumulable"
- **THEN** explica que una acumulable se aplica después de la ganadora, sobre el resultado anterior (8 % y después 2 % son 9,84 % en total, no 10 %), y que su condición se mide sobre las cantidades y el bruto originales
- **Regla:** DSC-03, DSC-05

#### Scenario: Tope por rol

- **GIVEN** la pantalla "Topes por rol"
- **WHEN** se abre el "(?)" de "Tope de descuento (%)"
- **THEN** explica que el tope limita solo el descuento manual, que se compara contra el mayor porcentaje manual de la venta, que superarlo pide una autorización que cubre toda la venta, y ofrece "Ver más" hacia "Cómo funcionan los topes"
- **Regla:** DSC-06; ADR-050

### Requirement: Las pantallas de listas de precios explican sus reglas

El formulario de lista DEBE ofrecer ayuda en el redondeo; la sección de redondeos por categoría, en la sobrescritura; el diálogo de regla de margen, en "Tipo de margen" y en "Se aplica a"; el borrador, en "Generar borrador", en las señales de los precios y en "Productos sin precio"; el diálogo de precio manual, en "Precio manual"; y el diálogo de publicación, en la vigencia.

#### Scenario: Tipo de margen

- **GIVEN** el diálogo de una regla de margen
- **WHEN** se abre el "(?)" de "Tipo de margen"
- **THEN** explica markup (`costo × (1 + m)`) y margen bruto (`costo / (1 − m)`) con el ejemplo de costo $6.000 y 30 %: $7.800,00 contra $8.571,43
- **Regla:** PRC-12

#### Scenario: Precedencia

- **GIVEN** el diálogo de una regla de margen
- **WHEN** se abre el "(?)" de "Se aplica a"
- **THEN** explica que manda la más específica (producto, marca, categoría, proveedor, lista), que hay a lo sumo una regla activa por alcance y que el cambio rige desde el próximo borrador
- **Regla:** PRC-13

#### Scenario: Publicar con vigencia

- **GIVEN** el diálogo de publicación de un borrador
- **WHEN** se abre el "(?)" de la vigencia
- **THEN** explica que sin vigencia desde rige al publicar, que no puede ser anterior a ese momento, que la versión anterior deja de regir sola y vuelve a regir si la nueva vence, y que solo se anula una versión que todavía no empezó
- **Regla:** PRC-02, PRC-03, PRC-05

### Requirement: Las pantallas de compras y costos explican sus reglas

El formulario de compra y la carga de costos DEBEN ofrecer ayuda en "Valor" (o "Valor pagado") con "Incluye IVA", en "Bonificación %" y en el costo base calculado; el formulario de compra, además, en "Total de factura"; el resultado de la compra, junto a "Registrar como costo informado", DEBE explicar la diferencia entre el costo promedio y el costo informado. Las dos pantallas DEBEN usar las mismas claves para los mismos conceptos.

#### Scenario: Valor con IVA en un responsable inscripto

- **GIVEN** una organización que computa crédito fiscal
- **WHEN** se abre el "(?)" de "Valor"
- **THEN** explica que con "Incluye IVA" el IVA se descuenta del costo, con el ejemplo "caja x12 a $18.000 con IVA: $18.000 / 1,21 / 12 = unos $1.239,67 por botella"
- **Regla:** CST-02, CST-06

#### Scenario: Valor pagado en una organización monotributista

- **GIVEN** una organización que no computa crédito fiscal
- **WHEN** se abre el "(?)" de "Valor pagado"
- **THEN** explica que el IVA es parte del costo y no se descuenta, con el ejemplo "caja x12 a $21.780: $21.780 / 12 = $1.815 por botella"
- **Regla:** CST-02, CST-06

#### Scenario: Costo promedio frente a costo informado

- **GIVEN** una compra confirmada con una línea cuyo costo difiere del informado vigente
- **WHEN** se abre el "(?)" junto a "Registrar como costo informado"
- **THEN** explica que la compra ya recalculó el costo promedio, que es el que costea las ventas (60 botellas a $1.000 y después 60 a $1.100 dejan un promedio de $1.050), y que el costo informado es el que usa la lista de precios y solo se registra si se pide
- **Regla:** CST-04, CST-11, CMP-04

### Requirement: Las pantallas de stock y jornadas explican la toma de ubicación

El formulario de ubicación DEBE ofrecer ayuda en "Requiere toma"; el listado de ubicaciones y la apertura de jornada, en la toma actual; el detalle de jornada, junto a "Liberar", en la liberación forzada.

#### Scenario: Ubicación tomada

- **GIVEN** el listado de ubicaciones con un vehículo tomado
- **WHEN** se abre el "(?)" de "Toma actual"
- **THEN** explica que el vehículo está tomado mientras su jornada está abierta o en rendición; que con la jornada abierta solo ella mueve su stock y en rendición ya no; que quien tiene `LIBERAR_UBICACION` lo mueve siempre; y que cualquier otro movimiento se rechaza
- **Regla:** STK-09, RUT-01

#### Scenario: Liberación forzada

- **GIVEN** el detalle de una jornada abierta, visto por quien tiene `LIBERAR_UBICACION`
- **WHEN** se abre el "(?)" junto a "Liberar"
- **THEN** explica que liberar destraba la ubicación sin tocar el stock del vehículo, que pide un motivo, que queda auditado, y que lo que el vendedor envíe después de esa jornada se acepta con una observación
- **Regla:** RUT-09, STK-09, AUD-01

### Requirement: Las pantallas de cobranzas explican sus reglas

El alta de cobranza DEBE ofrecer ayuda en "Medios de pago", en el saldo resultante y en "Jornada"; el detalle, en "Jornada", junto a "Anular" y en las observaciones de sincronización. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (para qué sirve en una oración, palabras de todos los días, un ejemplo con nombres y montos reales, tres o cuatro oraciones) (`design.md` D20 del change 17).

#### Scenario: Medios de pago

- **GIVEN** el alta de una cobranza
- **WHEN** se abre el "(?)" de "Medios de pago"
- **THEN** explica que el importe se puede repartir en varios medios que suman justo el total y que algunos piden referencia, con un ejemplo de un pago de $50.000 repartido en $30.000 en efectivo y $20.000 por transferencia con su número
- **Regla:** COB-01, COB-02, INV-08

#### Scenario: Saldo a favor

- **GIVEN** el alta de una cobranza
- **WHEN** se abre el "(?)" del saldo resultante
- **THEN** explica que la cobranza baja la deuda total del cliente y no una venta, y que si paga de más le queda saldo a favor, con el ejemplo "debe $150.000 y paga $160.000 → le quedan $10.000 a favor"
- **Regla:** COB-03, CC-04

#### Scenario: Anular

- **GIVEN** el detalle de una cobranza confirmada, visto por quien tiene `ANULAR_COBRANZA`
- **WHEN** se abre el "(?)" junto a "Anular"
- **THEN** explica que el cliente vuelve a deber lo mismo, que la cobranza no se borra y que se anula entera
- **Regla:** COB-05, CC-02

#### Scenario: Observaciones de una cobranza sin señal

- **GIVEN** el detalle de una cobranza con `MEDIO_INACTIVO`
- **WHEN** se abre el "(?)" de las observaciones
- **THEN** explica que el pago se tomó igual porque la plata ya se cobró, y qué significan "Medio inactivo", "Falta la referencia", "Permiso revocado", "Jornada liberada" y "Cliente no habilitado" (el panel queda corto y el detalle de cada aviso va en su "Ver más", tema `cobranzas-observaciones`), con palabras de todos los días
- **Regla:** SYN-05, SYN-07, SYN-10, RUT-09

### Requirement: Las pantallas de medios de pago y de roles explican sus reglas

La pestaña "Medios de pago" DEBE ofrecer ayuda en "Pide referencia" y en "Dar de baja"; la pantalla "Roles y permisos", en los permisos del rol, en el permiso "Usuarios, roles y permisos" y en los permisos de autorización. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (para qué sirve en una oración, palabras de todos los días, un ejemplo con nombres y montos reales, tres o cuatro oraciones) (`design.md` D12 del change 17b).

#### Scenario: Pide referencia
- **GIVEN** la pestaña "Medios de pago"
- **WHEN** se abre el "(?)" de "Pide referencia"
- **THEN** explica que hay que anotar un dato como el número de la transferencia, que con conexión sin ese dato no se guarda y que sin señal entra marcado para revisar, con el ejemplo de $20.000 por transferencia n.º 0042
- **Regla:** COB-02, PAG-01, SYN-07

#### Scenario: Dar de baja
- **GIVEN** la pestaña "Medios de pago"
- **WHEN** se abre el "(?)" de "Dar de baja"
- **THEN** explica que el medio deja de ofrecerse, que no se borra, que se puede reactivar y que tiene que quedar al menos uno activo
- **Regla:** CAT-05, TR-06, ADR-053

#### Scenario: Permisos del rol
- **GIVEN** la pantalla "Roles y permisos" con un rol elegido
- **WHEN** se abre el "(?)" de los permisos
- **THEN** explica que el cambio vale para todos los usuarios del rol desde su próxima acción, con el ejemplo de quitarle "Anular cobranzas" al Supervisor comercial
- **Regla:** `01` §19, ADR-017

#### Scenario: Último administrador
- **GIVEN** la pantalla "Roles y permisos"
- **WHEN** se abre el "(?)" del permiso "Usuarios, roles y permisos"
- **THEN** explica que siempre tiene que quedar al menos una persona activa con ese permiso
- **Regla:** ADR-053

#### Scenario: Permisos de autorización
- **GIVEN** la pantalla "Roles y permisos"
- **WHEN** se abre el "(?)" de los permisos de autorización
- **THEN** explica que, si el rol se queda sin ninguno, se borra el PIN de sus usuarios
- **Regla:** ADR-011

#### Scenario: Trazabilidad
- **GIVEN** las cinco claves nuevas
- **WHEN** corre la prueba de trazabilidad del archivo de textos
- **THEN** cada una cita reglas que existen en `docs/01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

### Requirement: Las pantallas de venta explican sus reglas

"Nueva venta" DEBE ofrecer ayuda en la carga de cajas y unidades, en el precio, en la elección de otra lista o versión, en la cobranza, en el consumidor final, en el stock y en el número; el detalle, en el costo (solo con `VER_COSTOS`) y en las observaciones, con un tema "Ver más" `ventas-observaciones`. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (`design.md` D22 del change 18a).

#### Scenario: Cajas y unidades
- **GIVEN** la pantalla "Nueva venta"
- **WHEN** se abre el "(?)" de la carga de cajas y unidades
- **THEN** explica que se cobra en proporción al precio de la caja, con el ejemplo "2 cajas + 3 botellas de Vino A (caja x6 a $12.500) = 15 botellas → $31.250"
- **Regla:** CAT-07; VTA-02; PRC-22

#### Scenario: Cobranza
- **WHEN** se abre el "(?)" de la cobranza
- **THEN** explica que puede ser nada, una parte, todo o más, con el ejemplo "venta de $80.000 con $20.000 en efectivo y un saldo de $150.000 → queda debiendo $210.000"
- **Regla:** VTA-11; CC-05

#### Scenario: Otra lista o versión
- **WHEN** quien tiene `USAR_LISTA_ANTERIOR` abre el "(?)" de la elección de lista
- **THEN** explica que pide permiso y motivo y que queda registrado quién lo hizo
- **Regla:** PRC-21; AUD-01

#### Scenario: Observaciones de una venta
- **GIVEN** el detalle de una venta con `STOCK_NEGATIVO`
- **WHEN** se abre el "(?)" de las observaciones
- **THEN** explica que la venta se tomó igual porque la mercadería ya se entregó y lleva al tema "Ver más" con el significado de cada aviso
- **Regla:** SYN-05; SYN-07; STK-06

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave `ventas.*` usada existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

### Requirement: Las pantallas de venta, configuración y PIN explican descuentos, crédito y autorización

Las pantallas de venta, de configuración del descuento manual y del crédito, del PIN de autorización y "Mi PIN" DEBEN traer su ayuda contextual: descuento general, descuento propio, tope, autorización, motivo, descuentos automáticos, crédito del cliente, política de crédito, configuración del descuento manual, configuración del crédito, PIN de autorización y Mi PIN, más una página "Ver más" sobre el crédito de los clientes. Cada texto DEBE citar su regla y los que citan DSC-06 o ADR-050 DEBEN revisarse contra lo que la venta muestra.

#### Scenario: El tope en la venta

- **GIVEN** la pantalla "Nueva venta"
- **WHEN** el usuario abre el "(?)" del tope
- **THEN** ve el texto aprobado con su ejemplo y la cita DSC-06, y "Ver más" lleva al tema de topes
- **Regla:** DSC-06; ADR-051

#### Scenario: El tema del crédito

- **WHEN** se abre "Ver más" del crédito
- **THEN** explica disponible, consumo, las tres políticas, la tolerancia sin señal y lo que queda guardado, citando CRE-01 a CRE-10
- **Regla:** CRE-01; CRE-10; ADR-051

#### Scenario: Toda clave usada existe y cita reglas existentes

- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe en el archivo de textos y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

#### Scenario: Mi PIN

- **GIVEN** la pantalla "Mi PIN" de un supervisor
- **WHEN** abre el "(?)"
- **THEN** ve el texto aprobado de `cuenta.miPin` con su ejemplo y las citas SEG-05, ADR-011 y ADR-019
- **Regla:** SEG-05; ADR-051

### Requirement: La nota de venta y su configuración explican sus reglas

Los botones de la nota en "Venta registrada" y en el detalle, y la sección "Nota de venta" de la configuración, DEBEN ofrecer ayuda en qué es la nota, en compartir o descargar, en la nota de una venta anulada, en "mostrar saldo" y en los datos de la organización. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D11).

#### Scenario: Qué es la nota
- **WHEN** se abre el "(?)" de la nota de venta
- **THEN** explica que es un comprobante interno, que no es factura y que al reimprimirla sale igual, sin ejemplo
- **Regla:** VTA-13; ADR-008

#### Scenario: Mostrar saldo
- **WHEN** se abre el "(?)" de "mostrar saldo"
- **THEN** explica que la nota muestra el saldo que quedó al registrar la venta y que no se muestra al consumidor final ni en una venta anulada
- **Regla:** VTA-13; CRE-02

#### Scenario: Venta anulada
- **WHEN** se abre el "(?)" de la nota en una venta anulada
- **THEN** explica que la nota sale con la marca de anulada, la fecha y el motivo
- **Regla:** ADR-058; ADR-059

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

### Requirement: Usuarios, roles y cartera explican sus reglas

Las pantallas de usuarios, de roles y de clientes DEBEN ofrecer ayuda en la baja de usuarios, el cambio de rol, el tope propio, el restablecimiento de la contraseña, la baja de roles y el vendedor asignado, y la ayuda del último administrador DEBE nombrar también la baja de usuarios y de roles y el cambio de rol. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D18).

#### Scenario: Baja de usuario
- **WHEN** se abre el "(?)" de "Dar de baja"
- **THEN** explica que el usuario deja de entrar, que su teléfono con jornada abierta puede subir lo pendiente y que no se puede dar de baja al último administrador ni a uno mismo, sin ejemplo
- **Regla:** ADR-028; ADR-053

#### Scenario: Tope propio
- **WHEN** se abre el "(?)" del tope propio
- **THEN** explica que reemplaza al del rol y que vacío rige el del rol
- **Regla:** DSC-06

#### Scenario: Último administrador revisado
- **WHEN** se abre el "(?)" del último administrador
- **THEN** nombra el cambio de permisos, la baja de usuarios y de roles y el cambio de rol
- **Regla:** ADR-053

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

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
