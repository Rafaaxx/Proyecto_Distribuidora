## Purpose

Definir las reglas de margen de una lista: markup o margen bruto, con alcance por producto, marca, categoría, proveedor o lista, y su resolución por precedencia (PRC-12, PRC-13). Escrita con la opción A de `design.md` D8, D12 y D13, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## ADDED Requirements

### Requirement: Una regla de margen se crea por comando con tipo, valor y alcance

El sistema DEBE crear una regla de margen con `REGLA_MARGEN_CREAR` (solo `ONLINE`, con `Operation-Id`, permiso `GESTIONAR_LISTAS`), que pertenece a una lista e indica el tipo (`MARKUP` o `MARGEN_BRUTO`), el valor como fracción de hasta seis decimales enviada como string (30% = `"0.300000"`) y el alcance: `PRODUCTO`, `MARCA`, `CATEGORIA` o `PROVEEDOR` con la entidad, o `LISTA` sin entidad (PRC-12, PRC-13). El valor DEBE ser mayor o igual que cero y, si el tipo es `MARGEN_BRUTO`, menor que uno; cualquier otro valor, o uno con más de seis decimales, DEBE rechazarse con `MARGEN_INVALIDO`. Un alcance `LISTA` con entidad, u otro alcance sin ella, DEBE rechazarse con `ALCANCE_INVALIDO`. La lista y la entidad del alcance DEBEN pertenecer a la organización (404 si no); la entidad puede estar inactiva. La regla nace activa.

#### Scenario: Regla general de la lista
- **GIVEN** la lista `General`
- **WHEN** un usuario con `GESTIONAR_LISTAS` envía `REGLA_MARGEN_CREAR` con tipo `MARKUP`, valor `"0.300000"` y alcance `LISTA`
- **THEN** el comando queda `ACEPTADO`, la regla existe activa en `General` y hay una sola fila de auditoría
- **Regla:** PRC-12; PRC-13; `03` §8 (`regla_margen`)

#### Scenario: Regla por categoría con margen bruto
- **WHEN** se crea en `General` una regla `MARGEN_BRUTO` de `"0.300000"` con alcance `CATEGORIA` `Vinos`
- **THEN** la regla existe y su alcance es la categoría `Vinos`
- **Regla:** PRC-12; PRC-13

#### Scenario: Margen bruto del 100% o más
- **WHEN** se envía una regla `MARGEN_BRUTO` con valor `"1.000000"` o `"1.200000"`
- **THEN** se rechaza con `MARGEN_INVALIDO` y no se crea la regla
- **Regla:** PRC-12 (`m < 1`); `03` §8 (`ck_regla_margen__valor`)

#### Scenario: Valor negativo o con siete decimales
- **WHEN** se envía una regla con valor `"-0.100000"` o `"0.3000001"`
- **THEN** se rechaza con `MARGEN_INVALIDO`
- **Regla:** PRC-12; TR-02; INV-03

#### Scenario: Markup mayor que el 100%
- **WHEN** se crea una regla `MARKUP` con valor `"1.500000"`
- **THEN** se acepta
- **Regla:** PRC-12 (el límite `m < 1` es solo del margen bruto)

#### Scenario: Alcance incoherente
- **WHEN** se envía una regla con alcance `LISTA` y una entidad, o con alcance `MARCA` sin entidad
- **THEN** se rechaza con `ALCANCE_INVALIDO`
- **Regla:** PRC-13; `03` §8 (`alcance_id` nulo si `LISTA`)

#### Scenario: Entidad del alcance de otra organización
- **WHEN** un usuario de A crea una regla con alcance `PRODUCTO` y un producto de B
- **THEN** la respuesta es 404 y no se crea la regla
- **Regla:** INV-21; INV-02

#### Scenario: Sin permiso
- **WHEN** un usuario con `PUBLICAR_LISTAS` y sin `GESTIONAR_LISTAS` envía `REGLA_MARGEN_CREAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se crea la regla
- **Regla:** `01` §19; SEG-06

#### Scenario: Doble envío
- **GIVEN** un `REGLA_MARGEN_CREAR` aceptado con `operation_id` X
- **WHEN** se reenvía con X y el mismo contenido
- **THEN** se devuelve el resultado original y la regla existe una sola vez
- **Regla:** INV-06; SYN-02

### Requirement: Hay como máximo una regla activa por lista y alcance

Una lista NO DEBE tener dos reglas activas con el mismo tipo de alcance y la misma entidad: el alta o la reactivación de una segunda DEBE rechazarse con `REGLA_DUPLICADA`, también ante escrituras simultáneas (`design.md` D8). Una regla inactiva no cuenta.

#### Scenario: Segunda regla para la misma categoría
- **GIVEN** en `General` la regla activa "categoría `Vinos`: margen bruto `"0.300000"`"
- **WHEN** se crea otra regla con alcance `CATEGORIA` `Vinos`, tipo `MARKUP` y valor `"0.400000"`
- **THEN** se rechaza con `REGLA_DUPLICADA` y la regla existente no cambia
- **Regla:** PRC-13; `design.md` D8

#### Scenario: Reemplazo de una regla desactivada
- **GIVEN** la regla de `Vinos` desactivada
- **WHEN** se crea otra regla con alcance `CATEGORIA` `Vinos`
- **THEN** se acepta
- **Regla:** PRC-13; `design.md` D8

#### Scenario: La misma categoría en otra lista
- **GIVEN** la regla de `Vinos` en `General`
- **WHEN** se crea una regla de `Vinos` en `Mayorista`
- **THEN** se acepta: las reglas pertenecen a su lista
- **Regla:** PRC-13

### Requirement: Una regla se modifica y se desactiva sin tocar versiones

El sistema DEBE modificar el tipo, el valor y la actividad de una regla con `REGLA_MARGEN_MODIFICAR` (`GESTIONAR_LISTAS`), con las validaciones del alta; el alcance y la lista NO DEBEN cambiar. Una regla NO DEBE borrarse. Modificar o desactivar una regla NO DEBE alterar ningún precio de ninguna versión existente: rige para los borradores generados después (PRC-04, PRC-16).

#### Scenario: Subir el margen no cambia lo publicado
- **GIVEN** una versión publicada donde Vino A vale `"8600.00"` por la regla "margen bruto `"0.300000"`"
- **WHEN** la regla se modifica a `"0.350000"`
- **THEN** la versión publicada sigue con Vino A a `"8600.00"`, con tipo `MARGEN_BRUTO` y valor `"0.300000"` guardados en el precio
- **Regla:** PRC-04; PRC-16; INV-11

#### Scenario: Regla de otra organización
- **WHEN** un usuario de A modifica una regla de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

### Requirement: La regla aplicable se resuelve por precedencia

Para un producto y una lista, la regla aplicable DEBE ser la regla activa de alcance más específico, en este orden: producto, marca, categoría, proveedor, lista (PRC-13). Un producto sin marca no tiene regla de marca. Si ninguna regla activa alcanza al producto, el producto no tiene regla aplicable.

#### Scenario: La regla de producto gana a todas
- **GIVEN** Vino A (marca `Bodega Norte`, categoría `Vinos`, proveedor `Bodega Sur`) y reglas activas de producto, marca, categoría, proveedor y lista en `General`
- **WHEN** se resuelve la regla de Vino A
- **THEN** se obtiene la de alcance `PRODUCTO`
- **Regla:** PRC-13

#### Scenario: La marca gana a la categoría
- **GIVEN** reglas activas de marca `Bodega Norte`, de categoría `Vinos` y de lista, y ninguna de producto para Vino A
- **WHEN** se resuelve la regla de Vino A
- **THEN** se obtiene la de alcance `MARCA`
- **Regla:** PRC-13

#### Scenario: La categoría gana al proveedor
- **GIVEN** reglas activas de categoría `Vinos`, de proveedor `Bodega Sur` y de lista
- **WHEN** se resuelve la regla de Vino A
- **THEN** se obtiene la de alcance `CATEGORIA`
- **Regla:** PRC-13

#### Scenario: Solo la regla de la lista
- **GIVEN** una única regla activa, de alcance `LISTA`
- **WHEN** se resuelve la regla de cualquier producto
- **THEN** se obtiene la de alcance `LISTA`
- **Regla:** PRC-13

#### Scenario: Una regla inactiva no participa
- **GIVEN** la regla de producto de Vino A desactivada y la de categoría `Vinos` activa
- **WHEN** se resuelve la regla de Vino A
- **THEN** se obtiene la de alcance `CATEGORIA`
- **Regla:** PRC-13; `design.md` D8

#### Scenario: Producto sin regla aplicable
- **GIVEN** una lista con una sola regla, de categoría `Vinos`, y el producto Cerveza B de categoría `Cervezas`
- **WHEN** se resuelve la regla de Cerveza B
- **THEN** no hay regla aplicable
- **Regla:** PRC-13; `design.md` D8

### Requirement: Las reglas de una lista se consultan con su fórmula

El sistema DEBE listar las reglas de una lista con su alcance (tipo, entidad y nombre de la entidad), tipo, valor como string y actividad, con `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. Las lecturas de productos, categorías, marcas y opciones de proveedor que alimentan la elección del alcance DEBEN responder también con `GESTIONAR_LISTAS`, solo en lectura (`design.md` D12).

#### Scenario: Listado de reglas
- **GIVEN** `General` con una regla de lista `MARKUP` `"0.300000"` y una de categoría `Vinos` `MARGEN_BRUTO` `"0.300000"`
- **WHEN** se listan sus reglas
- **THEN** se devuelven las dos, con el nombre `Vinos` en la segunda y los valores como string
- **Regla:** PRC-12; `02` §10.2

#### Scenario: Elegir el alcance con solo el permiso de listas
- **GIVEN** un usuario con `GESTIONAR_LISTAS` y sin `GESTIONAR_CATALOGO` ni `GESTIONAR_PROVEEDORES`
- **WHEN** lee productos, categorías, marcas y opciones de proveedor
- **THEN** las cuatro lecturas responden, y un alta de producto con ese usuario sigue dando 403
- **Regla:** `01` §19; SEG-06; `design.md` D12

#### Scenario: Reglas de una lista ajena
- **WHEN** un usuario de A lista las reglas de una lista de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
