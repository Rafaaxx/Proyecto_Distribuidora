# Administración de Catálogo Specification

## Purpose

Define la pantalla de administración del catálogo en el área `/admin`: consultar, dar de alta y modificar productos, presentaciones, categorías y marcas contra la API, enviando cada escritura como comando idempotente, y mostrando las cantidades en cajas + unidades (CAT-01 a CAT-08, `02` §13.1).

## Requirements

### Requirement: La pantalla de catálogo está disponible solo con el permiso
El área `/admin` DEBE ofrecer la pantalla de catálogo a usuarios autenticados con `GESTIONAR_CATALOGO`, permiso que exigen tanto las lecturas como las escrituras de catálogo en la API. La pantalla DEBE decidir qué mostrar a partir de la respuesta de la API (los permisos no viajan en el token, ADR-017), y a un usuario sin el permiso NO DEBE mostrarle datos ni acciones de escritura. La pantalla DEBE cargarse solo dentro del área `/admin` (el teléfono no descarga su código).

#### Scenario: Usuario con permiso
- **WHEN** un usuario con rol GES autenticado en `/admin` navega a `/admin/catalogo`
- **THEN** ve el listado de productos y las acciones de alta y edición
- **Regla:** `01` §19 (GESTIONAR_CATALOGO: ADM, GES)

#### Scenario: Usuario sin permiso
- **WHEN** un usuario autenticado sin `GESTIONAR_CATALOGO` navega a `/admin/catalogo`
- **THEN** la API responde `PERMISO_REQUERIDO` y la pantalla muestra que no tiene permiso para gestionar el catálogo, sin listado ni acciones de alta o edición
- **Regla:** SEG-06; ADR-017

### Requirement: Listado y detalle de productos
La pantalla DEBE listar productos con búsqueda por código o nombre, filtros por categoría, marca y actividad, y carga de páginas siguientes por cursor. El detalle DEBE mostrar las presentaciones con sus unidades, usos, actividad y cuál es la de referencia, y para cada presentación su equivalencia en cajas + unidades respecto de la referencia.

#### Scenario: Equivalencia de presentaciones en el detalle
- **WHEN** se abre el detalle de `Cerveza B` con referencia `Caja x12` y presentación `Pack x24`
- **THEN** `Pack x24` se muestra como 2 cajas y 0 unidades, y `Caja x12` como 1 caja y 0 unidades
- **Regla:** CAT-08

#### Scenario: Buscar por código
- **WHEN** se busca `VA-` en una base con los productos `VA-001` y `CB-001`
- **THEN** el listado muestra solo `VA-001`
- **Regla:** CAT-01

### Requirement: Alta y edición desde la pantalla usan comandos idempotentes
Cada alta o modificación de la pantalla DEBE enviarse con un `Operation-Id` UUIDv7 nuevo generado en el cliente, que se DEBE conservar si el usuario reintenta la misma operación tras un error de red. Los formularios DEBEN validar en el cliente lo mismo que el servidor puede validar sin datos (campos obligatorios, unidades enteras ≥ 1, exactamente una referencia de venta), sin reemplazar la validación del servidor. Los errores de dominio del servidor DEBEN mostrarse con un mensaje comprensible asociado a su código.

#### Scenario: Alta de producto con presentaciones
- **WHEN** el usuario confirma el formulario de alta con código `VA-001`, nombre `Vino A`, categoría `Vinos`, alícuota `21%`, presentaciones `Botella` (1) y `Caja x6` (6, referencia)
- **THEN** se envía un único comando de alta y, al aceptarse, el producto aparece en el listado sin recargar la página
- **Regla:** CAT-01; CAT-02; CAT-03

#### Scenario: El formulario impide dos referencias
- **WHEN** el usuario marca dos presentaciones como referencia, o una referencia sin uso en venta
- **THEN** el formulario muestra el error y no envía el comando
- **Regla:** CAT-03

#### Scenario: Reintento tras error de red no duplica
- **WHEN** un alta se envía cuya respuesta no llegó por un corte de red y el usuario reintenta sin cambiar los datos
- **THEN** se reenvía con el mismo `Operation-Id` y existe un solo producto
- **Regla:** INV-06; SYN-02

#### Scenario: Código duplicado informado por el servidor
- **WHEN** el usuario da de alta otro producto con un código que ya existe
- **THEN** la pantalla muestra que el código ya existe junto al campo código, y conserva lo cargado
- **Regla:** CAT-01; TR-10

#### Scenario: Unidades congeladas informadas por el servidor
- **WHEN** el usuario intenta cambiar las unidades de una presentación usada en operaciones
- **THEN** la pantalla muestra que debe crear una presentación nueva y desactivar la anterior
- **Regla:** CAT-04; INV-18

### Requirement: Categorías y marcas se gestionan desde la pantalla
La pantalla DEBE permitir listar, crear, renombrar, desactivar y reactivar categorías y marcas, y los selectores de categoría y marca del formulario de producto DEBEN ofrecer solo las activas.

#### Scenario: Una marca desactivada no se ofrece
- **WHEN** se abre el formulario de alta de producto con la marca `Bodega Norte` desactivada
- **THEN** el selector de marca no la ofrece
- **Regla:** CAT-05

### Requirement: El formulario de producto ofrece las alícuotas activas de la organización
El formulario de alta y edición de producto DEBE elegir la alícuota de IVA de un selector alimentado por la API (`GET /api/v1/configuracion/alicuotas`), que devuelve solo las alícuotas de la organización del token con su indicador `activo` y su valor como string. El selector DEBE ofrecer solo las activas. El filtro del cliente no reemplaza la validación del servidor, que rechaza una alícuota inactiva o ajena.

#### Scenario: Una alícuota desactivada no se ofrece
- **WHEN** se abre el formulario de alta de producto con alícuotas `21%` y `10,5%` activas y `27%` desactivada en la organización A
- **THEN** el selector de alícuota ofrece `21%` y `10,5%` y no ofrece `27%`
- **Regla:** CAT-01; CAT-05; TR-09

#### Scenario: Las alícuotas de otra organización no se listan
- **WHEN** un usuario de la organización A consulta las alícuotas con la alícuota `21%` de la organización B existente
- **THEN** la respuesta no incluye ninguna alícuota de la organización B
- **Regla:** INV-21
