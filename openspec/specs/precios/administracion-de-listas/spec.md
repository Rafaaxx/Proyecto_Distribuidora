# precios/administracion-de-listas Specification

## Purpose
Definir las pantallas de `/admin/precios`: listas, reglas de margen, redondeos, borrador, publicación y versiones anteriores, decididas por los permisos efectivos de la sesión (ADR-027) y sin lógica de negocio en los componentes. Escrita con la opción A de `design.md` D12 y D15, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## Requirements

### Requirement: El área de listas de precios se decide con los permisos de la sesión

El área `/admin` DEBE ofrecer la entrada "Listas de precios" y sus pantallas solo a usuarios cuya sesión incluye `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS` (ADR-027). Las acciones de crear y editar listas, reglas y redondeos, generar el borrador y fijar precios DEBEN mostrarse solo con `GESTIONAR_LISTAS`; publicar y anular, solo con `PUBLICAR_LISTAS`. La pantalla NO DEBE consultar la API para descubrir un permiso que la sesión no tiene. Ocultar una acción no reemplaza la validación del servidor (SEG-06).

#### Scenario: Usuario de Administración
- **GIVEN** un usuario con `GESTIONAR_LISTAS` y sin `PUBLICAR_LISTAS`
- **WHEN** abre el borrador de una lista
- **THEN** ve "Regenerar" y la edición de precios, y no ve "Publicar"
- **Regla:** `01` §19; PRC-06; ADR-027

#### Scenario: Usuario sin permisos de listas
- **GIVEN** un Vendedor sin `GESTIONAR_LISTAS` ni `PUBLICAR_LISTAS`
- **WHEN** entra a `/admin`
- **THEN** no ve la entrada "Listas de precios", la ruta directa le muestra que no tiene permiso y no se pide ningún dato de listas
- **Regla:** ADR-027; SEG-06

#### Scenario: Administrador
- **GIVEN** un Administrador con los dos permisos
- **WHEN** abre el borrador de una lista
- **THEN** ve "Regenerar", la edición de precios y "Publicar"
- **Regla:** `01` §19

### Requirement: Listas, reglas y redondeos se gestionan desde la pantalla

La pantalla DEBE listar las listas con su redondeo, su versión vigente y si tienen borrador; DEBE permitir crear y editar una lista con su múltiplo y su dirección de redondeo; y, en el detalle de una lista, crear, editar y desactivar reglas de margen eligiendo el alcance, y definir redondeos por categoría. Cada regla DEBE mostrarse con la fórmula que aplica (PRC-12). Los formularios DEBEN validar con el mismo criterio que el servidor y mostrar junto al campo el error que el servidor devuelva. Los porcentajes y los múltiplos NO DEBEN convertirse a número para calcular.

#### Scenario: La fórmula de cada tipo de margen es visible
- **GIVEN** una regla `MARKUP` de 30% y otra `MARGEN_BRUTO` de 30%
- **WHEN** se muestran en el detalle de la lista
- **THEN** la primera dice que el precio es el costo por 1,30 y la segunda que es el costo dividido por 0,70
- **Regla:** PRC-12 (la interfaz muestra la fórmula aplicada)

#### Scenario: Margen bruto inválido en el formulario
- **WHEN** se carga una regla de margen bruto de 100%
- **THEN** el formulario lo marca como inválido y no envía el comando
- **Regla:** PRC-12 (`m < 1`); TR-10

#### Scenario: Regla duplicada informada por el servidor
- **GIVEN** una regla activa para la categoría `Vinos`
- **WHEN** se intenta crear otra para `Vinos` y el servidor responde `REGLA_DUPLICADA`
- **THEN** la pantalla muestra el mensaje junto al alcance y conserva lo cargado
- **Regla:** PRC-13; TR-10; `design.md` D8

#### Scenario: Lista en uso
- **WHEN** se intenta desactivar la lista predeterminada y el servidor responde `LISTA_EN_USO`
- **THEN** la pantalla explica que la lista es la predeterminada o está asignada a clientes y la lista sigue activa
- **Regla:** PRC-20; `design.md` D11

### Requirement: El borrador se revisa, se ajusta y se regenera desde la pantalla

La pantalla del borrador DEBE mostrar, por producto, el precio en la versión base, el precio nuevo, si cambia, si es manual y sus señales (margen menor que el de la regla, costo con otra regla de IVA, costos distintos por presentación, sin costo), el precio por presentación de venta calculado con PRC-22 y, aparte, los productos sin precio con su causa. Con `VER_COSTOS` DEBE mostrar además el costo de referencia, la regla y el precio calculado; sin él, NO DEBE mostrarlos. DEBE permitir fijar y quitar un precio manual y regenerar el borrador, e indicar cuándo se generó. Los importes DEBEN mostrarse desde el string de la API, sin convertirlos a número para calcular.

#### Scenario: Comparación con la versión base
- **GIVEN** un borrador donde Vino A pasa de `"8600.00"` a `"9500.00"` sobre `Caja x6`
- **WHEN** se abre la pantalla del borrador
- **THEN** Vino A muestra $ 8.600,00 → $ 9.500,00 marcado como que cambia, y la botella a $ 1.583,33
- **Regla:** PRC-17; PRC-22; `04` §7 (punto de validación con el cliente)

#### Scenario: El precio por presentación no pide el detalle de cada producto
- **GIVEN** un borrador de cien productos, cada línea con las presentaciones activas de venta de su producto
- **WHEN** se abre la pantalla del borrador
- **THEN** el precio por presentación sale de las presentaciones que trae cada línea, sin pedir el detalle de ningún producto al catálogo, y las líneas no llevan costos sin `VER_COSTOS`
- **Regla:** PRC-22; ADR-047 punto 28; D12

#### Scenario: Señal de margen menor que el de la regla
- **GIVEN** Vino A manual a `"9000.00"` con la señal de margen menor que el de la regla
- **WHEN** se abre el borrador
- **THEN** la fila de Vino A muestra que es manual y la advertencia de margen
- **Regla:** PRC-17

#### Scenario: Productos sin precio
- **GIVEN** un borrador con Gaseosa C sin precio por `SIN_COSTO`
- **WHEN** se abre el borrador
- **THEN** Gaseosa C aparece en la lista de productos sin precio con su causa y la opción de fijarle un precio manual
- **Regla:** PRC-17; `design.md` D4 y D7

#### Scenario: Sin permiso de ver costos
- **GIVEN** un usuario con `GESTIONAR_LISTAS` y sin `VER_COSTOS`
- **WHEN** abre el borrador
- **THEN** ve precios y señales, y no ve columnas de costo, margen ni precio calculado
- **Regla:** `01` §19 (`VER_COSTOS`); `design.md` D12

#### Scenario: Reintento seguro
- **GIVEN** un envío de "Regenerar" que falló por un error de red
- **WHEN** el usuario reintenta sin cambiar nada
- **THEN** se reenvía con el mismo `Operation-Id`
- **Regla:** INV-06; SYN-02

#### Scenario: Sin conexión
- **GIVEN** un usuario sin conexión en la pantalla del borrador
- **WHEN** intenta regenerar o fijar un precio
- **THEN** la pantalla indica que se necesita conexión, no envía el comando y no encola nada
- **Regla:** `02` §6.5; ADR-012

### Requirement: La publicación y la anulación se confirman desde la pantalla

Con `PUBLICAR_LISTAS`, la pantalla DEBE permitir publicar el borrador indicando la vigencia desde (por defecto, ahora) y, opcionalmente, la vigencia hasta, con una confirmación que informe cuántos precios se publican y cuántos productos quedan sin precio. DEBE permitir anular una versión solo cuando su estado derivado es `PROGRAMADA`. Las versiones publicadas y anuladas DEBEN mostrarse en solo lectura, cada una con su estado, y sin ninguna acción de edición.

#### Scenario: Publicar con confirmación
- **GIVEN** un borrador con 98 precios y 2 productos sin precio
- **WHEN** un usuario con `PUBLICAR_LISTAS` pulsa "Publicar"
- **THEN** la confirmación informa "98 precios, 2 productos sin precio" y, al aceptar, la versión aparece como vigente
- **Regla:** PRC-06; PRC-02; `design.md` D15

#### Scenario: Vigencia inválida informada por el servidor
- **WHEN** se publica con una vigencia desde pasada y el servidor responde `VIGENCIA_INVALIDA`
- **THEN** la pantalla muestra el mensaje junto a la fecha y el borrador sigue sin publicar
- **Regla:** PRC-02; TR-10; `design.md` D6

#### Scenario: Anular solo una versión programada
- **GIVEN** una versión `PROGRAMADA` y otra `VIGENTE`
- **WHEN** un usuario con `PUBLICAR_LISTAS` abre cada una
- **THEN** la programada ofrece "Anular" y la vigente no
- **Regla:** PRC-05

#### Scenario: Una versión publicada es de solo lectura
- **GIVEN** una versión `VIGENTE` o `HISTÓRICA`
- **WHEN** un usuario con `GESTIONAR_LISTAS` la abre
- **THEN** ve sus precios tal como se publicaron y ningún control para editarlos
- **Regla:** PRC-04; INV-11
