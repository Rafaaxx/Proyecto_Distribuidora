# precios/listas-de-precios Specification

## Purpose
Definir la lista de precios como dato maestro de la organización: nombre, regla de redondeo y sobrescritura de redondeo por categoría, escritos solo por comandos del bus (PRC-01, PRC-14). Sus precios viven en versiones (`precios/versiones-de-lista`). Escrita con la opción A de `design.md` D9, D11, D12, D13 y D14, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## Requirements

### Requirement: Una lista de precios se crea por comando con su redondeo

El sistema DEBE crear una lista con el comando `LISTA_PRECIO_CREAR` (solo `ONLINE`, con `Operation-Id`, permiso `GESTIONAR_LISTAS`), cuyo contenido lleva el nombre y la regla de redondeo: un múltiplo mayor que cero con hasta dos decimales, enviado como string, y una dirección `ARRIBA`, `CERCANO` o `ABAJO` (PRC-01, PRC-14, `design.md` D9). El nombre se guarda recortado, NO DEBE quedar vacío (`NOMBRE_INVALIDO`) y NO DEBE repetirse en la organización sin distinguir mayúsculas (`NOMBRE_DUPLICADO`). Un múltiplo no positivo, con más de dos decimales o que no es un decimal exacto DEBE rechazarse con `REDONDEO_INVALIDO`, igual que una dirección fuera del catálogo. La lista nace activa y sin versiones. El identificador lo genera el servidor (UUIDv7).

#### Scenario: Alta de la lista General
- **GIVEN** la organización A sin listas
- **WHEN** un usuario con `GESTIONAR_LISTAS` envía `LISTA_PRECIO_CREAR` con nombre `General`, múltiplo `"100.00"` y dirección `ARRIBA`
- **THEN** el comando queda `ACEPTADO`, la lista existe activa en A, sin versiones, y se registra una sola fila de auditoría con el `operation_id`
- **Regla:** PRC-01; PRC-14; `03` §8 (`lista_precio`)

#### Scenario: Nombre repetido
- **GIVEN** la lista `General` en la organización A
- **WHEN** se envía `LISTA_PRECIO_CREAR` con nombre ` general `
- **THEN** se rechaza con `NOMBRE_DUPLICADO` y no se crea ninguna lista
- **Regla:** PRC-01; `design.md` D13

#### Scenario: Nombre vacío
- **WHEN** se envía `LISTA_PRECIO_CREAR` con nombre vacío o de solo espacios
- **THEN** se rechaza con `NOMBRE_INVALIDO`
- **Regla:** PRC-01; TR-10

#### Scenario: Redondeo inválido
- **WHEN** se envía `LISTA_PRECIO_CREAR` con múltiplo `"0"`, `"-100"`, `"0.005"` o con dirección `MITAD`
- **THEN** se rechaza con `REDONDEO_INVALIDO` y no se crea ninguna lista
- **Regla:** PRC-14; INV-03; `design.md` D9

#### Scenario: Sin permiso
- **WHEN** un usuario sin `GESTIONAR_LISTAS` (rol Vendedor) envía `LISTA_PRECIO_CREAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, no se crea la lista ni queda reserva del `operation_id`
- **Regla:** `01` §19 (`GESTIONAR_LISTAS`); SEG-06

#### Scenario: Doble envío del alta
- **GIVEN** un `LISTA_PRECIO_CREAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido, y después con X y otro nombre
- **THEN** el primero devuelve el resultado original sin crear otra lista y el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

#### Scenario: Solo con conexión
- **WHEN** llega `LISTA_PRECIO_CREAR` en modo `OFFLINE` por el lote de sincronización
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

### Requirement: Una lista se modifica y se desactiva por comando, sin borrarse

El sistema DEBE modificar el nombre, el redondeo y la actividad de una lista con `LISTA_PRECIO_MODIFICAR` (`GESTIONAR_LISTAS`), con las mismas validaciones que el alta. Cambiar el redondeo NO DEBE modificar ninguna versión existente: rige para los borradores que se generen después (PRC-04). Una lista NO DEBE borrarse: se desactiva. Una lista que es la predeterminada de la organización, o que está asignada a algún cliente que no está `INACTIVO`, NO DEBE desactivarse (`LISTA_EN_USO`, `design.md` D11). Una lista de otra organización DEBE responder 404.

#### Scenario: Cambiar el redondeo no toca lo publicado
- **GIVEN** la lista `General` con múltiplo `"100.00"` `ARRIBA` y una versión publicada con Vino A a `"8600.00"`
- **WHEN** se modifica la lista a dirección `ABAJO`
- **THEN** la versión publicada sigue con Vino A a `"8600.00"`
- **Regla:** PRC-04; INV-11

#### Scenario: Desactivar la lista predeterminada
- **GIVEN** `General` definida como lista predeterminada de la organización
- **WHEN** se envía `LISTA_PRECIO_MODIFICAR` con `activo = false`
- **THEN** se rechaza con `LISTA_EN_USO` y la lista sigue activa
- **Regla:** PRC-20; `01` §4; `design.md` D11

#### Scenario: Desactivar una lista asignada a un cliente
- **GIVEN** la lista `Mayorista` asignada al cliente `Kiosco El Faro`, que está `ACTIVO`
- **WHEN** se intenta desactivar `Mayorista`
- **THEN** se rechaza con `LISTA_EN_USO`
- **Regla:** PRC-20; CLI-01; `design.md` D11

#### Scenario: Desactivar una lista sin uso
- **GIVEN** la lista `Especial`, que no es la predeterminada ni está asignada a ningún cliente
- **WHEN** se la desactiva
- **THEN** queda inactiva, sigue existiendo con sus versiones y no se ofrece para asignar
- **Regla:** PRC-01; TR-06

#### Scenario: Lista de otra organización
- **WHEN** un usuario de A envía `LISTA_PRECIO_MODIFICAR` sobre una lista de B
- **THEN** la respuesta es 404 y la lista de B no cambia
- **Regla:** INV-21; SEG-07

### Requirement: El redondeo de una lista puede sobrescribirse por categoría

El sistema DEBE permitir definir, con `REDONDEO_CATEGORIA_DEFINIR` (`GESTIONAR_LISTAS`), una sobrescritura de redondeo para una categoría dentro de una lista: múltiplo y dirección con las mismas validaciones que el redondeo de la lista, y su actividad (PRC-14). Como máximo DEBE existir una sobrescritura por lista y categoría: definirla de nuevo actualiza la existente. La categoría DEBE pertenecer a la organización (404 si no). Una sobrescritura inactiva NO DEBE aplicarse.

#### Scenario: Sobrescritura para una categoría
- **GIVEN** la lista `General` con múltiplo `"100.00"` y la categoría `Golosinas`
- **WHEN** se define para `Golosinas` el múltiplo `"10.00"` con dirección `ARRIBA`
- **THEN** la lista tiene una sobrescritura activa para `Golosinas` y su redondeo general no cambia
- **Regla:** PRC-14; `03` §8 (`redondeo_categoria`)

#### Scenario: Definir dos veces la misma categoría
- **GIVEN** la sobrescritura de `Golosinas` con múltiplo `"10.00"`
- **WHEN** se define de nuevo con múltiplo `"50.00"`
- **THEN** existe una sola sobrescritura para `Golosinas`, con múltiplo `"50.00"`
- **Regla:** PRC-14; `design.md` D13

#### Scenario: Categoría de otra organización
- **WHEN** se define una sobrescritura con una categoría de otra organización
- **THEN** la respuesta es 404 y no se crea nada
- **Regla:** INV-21; INV-02

#### Scenario: Sobrescritura desactivada
- **GIVEN** la sobrescritura de `Golosinas` desactivada
- **WHEN** se genera un borrador de la lista
- **THEN** los productos de `Golosinas` se redondean con el redondeo de la lista
- **Regla:** PRC-14; `design.md` D9

### Requirement: Las listas se consultan por organización

El sistema DEBE listar las listas de la organización del token, con su redondeo, su actividad, su versión vigente si la tiene y si tienen un borrador, y DEBE devolver el detalle de una lista con sus sobrescrituras de redondeo. Estas lecturas DEBEN exigir `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. El sistema DEBE ofrecer además una lectura reducida de las listas activas (identificador y nombre) con `GESTIONAR_LISTAS`, `PUBLICAR_LISTAS`, `GESTIONAR_CLIENTES` o `ADMIN_CONFIGURACION` (`design.md` D12). Los múltiplos DEBEN viajar como string. Ninguna lectura DEBE devolver listas de otra organización.

#### Scenario: Listado aislado por organización
- **GIVEN** las listas `General` en A y `General` en B
- **WHEN** un usuario de A lista las listas
- **THEN** recibe solo la de A, con su múltiplo como `"100.00"`
- **Regla:** INV-21; TR-08; `02` §10.2

#### Scenario: Opciones para la ficha del cliente
- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `GESTIONAR_LISTAS`, y las listas `General` activa y `Especial` inactiva
- **WHEN** pide la lectura reducida de listas
- **THEN** recibe solo `General`, con identificador y nombre
- **Regla:** CLI-01; `design.md` D12

#### Scenario: Lectura sin permiso
- **WHEN** un usuario sin `GESTIONAR_LISTAS` ni `PUBLICAR_LISTAS` pide el listado o el detalle de una lista
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06

#### Scenario: Detalle de una lista ajena
- **WHEN** un usuario de A pide el detalle de una lista de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
