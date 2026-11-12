## Purpose

Definir el ciclo de una versión de lista: publicación con vigencia, estados derivados, anulación antes de su vigencia, consulta de versiones anteriores e inmutabilidad de lo publicado (PRC-02 a PRC-06, INV-11, `01` §18). Escrita con la opción A de `design.md` D5, D6, D12, D13 y D14, aprobadas por el usuario el 2026-10-06 (tarea 0.1).

## ADDED Requirements

### Requirement: Un borrador se publica por comando con su vigencia

El sistema DEBE publicar un borrador con `LISTA_PUBLICAR` (solo `ONLINE`, con `Operation-Id`), que exige `PUBLICAR_LISTAS` (PRC-06) y lleva una vigencia desde opcional y una vigencia hasta opcional (PRC-02). Sin vigencia desde, DEBE usarse el momento de la publicación. Una vigencia desde anterior al momento de la publicación, o una vigencia hasta que no es posterior a la vigencia desde, DEBE rechazarse con `VIGENCIA_INVALIDA`: nunca se publica hacia atrás (`design.md` D6). Una vigencia desde igual a la de otra versión publicada de la misma lista DEBE rechazarse con `VIGENCIA_DUPLICADA`. Un borrador sin precios DEBE rechazarse con `VERSION_SIN_PRECIOS`; una versión que no está en `BORRADOR`, con `VERSION_NO_ES_BORRADOR`; una lista inactiva, con `LISTA_INACTIVA`. La versión publicada DEBE quedar `PUBLICADA` con el usuario y el momento de publicación, y la publicación DEBE quedar auditada (AUD-01). Publicar NO DEBE recalcular precios ni modificar ninguna otra versión.

#### Scenario: Publicación con vigencia inmediata
- **GIVEN** el borrador n.º 1 de `General` con Vino A a `"8600.00"`
- **WHEN** un usuario con `PUBLICAR_LISTAS` envía `LISTA_PUBLICAR` sin vigencia desde
- **THEN** el comando queda `ACEPTADO`, la versión n.º 1 queda `PUBLICADA` con vigencia desde igual al momento de la publicación, con usuario y momento de publicación, y hay una sola fila de auditoría con el `operation_id`
- **Regla:** PRC-02; PRC-06; AUD-01; `01` §18 (BORRADOR → PUBLICADA)

#### Scenario: Publicación programada
- **GIVEN** un borrador y la fecha de hoy 28/09
- **WHEN** se publica con vigencia desde el 01/10 y vigencia hasta el 01/11
- **THEN** la versión queda `PUBLICADA` con esas vigencias y su estado derivado es `PROGRAMADA`
- **Regla:** PRC-02; PRC-03

#### Scenario: Vigencia desde en el pasado
- **WHEN** se publica un borrador con vigencia desde anterior al momento de la publicación
- **THEN** se rechaza con `VIGENCIA_INVALIDA` y la versión sigue en `BORRADOR`
- **Regla:** PRC-02; PRC-20; `design.md` D6

#### Scenario: Vigencia hasta no posterior a la vigencia desde
- **WHEN** se publica con vigencia hasta igual o anterior a la vigencia desde
- **THEN** se rechaza con `VIGENCIA_INVALIDA`
- **Regla:** PRC-02; `design.md` D6

#### Scenario: Misma vigencia desde que otra versión publicada
- **GIVEN** la versión n.º 3 de `General` publicada con vigencia desde el 01/10 a las 00:00
- **WHEN** se publica el borrador n.º 4 con esa misma vigencia desde
- **THEN** se rechaza con `VIGENCIA_DUPLICADA`
- **Regla:** PRC-03; `design.md` D6

#### Scenario: Borrador sin precios
- **GIVEN** un borrador en el que ningún producto pudo calcularse
- **WHEN** se envía `LISTA_PUBLICAR`
- **THEN** se rechaza con `VERSION_SIN_PRECIOS`
- **Regla:** PRC-10; `design.md` D6

#### Scenario: Publicar dos veces
- **GIVEN** una versión ya `PUBLICADA`
- **WHEN** se envía `LISTA_PUBLICAR` sobre ella con otro `Operation-Id`
- **THEN** se rechaza con `VERSION_NO_ES_BORRADOR` y la versión no cambia
- **Regla:** PRC-04; INV-11; `01` §18

#### Scenario: Sin permiso de publicar
- **WHEN** un usuario con `GESTIONAR_LISTAS` y sin `PUBLICAR_LISTAS` (rol Administración) envía `LISTA_PUBLICAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y la versión sigue en `BORRADOR`
- **Regla:** PRC-06; `01` §19 (`PUBLICAR_LISTAS`: solo ADM); SEG-06

#### Scenario: Versión de otra organización
- **WHEN** un usuario de A envía `LISTA_PUBLICAR` sobre un borrador de B
- **THEN** la respuesta es 404 y el borrador de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío de la publicación
- **GIVEN** un `LISTA_PUBLICAR` aceptado con `operation_id` X
- **WHEN** se reenvía con X y el mismo contenido, y después con X y otra vigencia
- **THEN** el primero devuelve el resultado original sin efectos nuevos y el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

#### Scenario: Solo con conexión
- **WHEN** llega `LISTA_PUBLICAR` en modo `OFFLINE`
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

#### Scenario: La publicación es atómica
- **GIVEN** una falla inyectada después de marcar la versión y antes de terminar el comando
- **WHEN** se procesa `LISTA_PUBLICAR`
- **THEN** la versión sigue en `BORRADOR` y no hay auditoría de la publicación
- **Regla:** INV-01

#### Scenario: Publicar no afecta costos, stock ni cuentas
- **WHEN** se publica una versión
- **THEN** no cambia ningún stock, ningún costo promedio ni ningún saldo de cuenta corriente
- **Regla:** `01` §21 (fila "Versión publicada")

### Requirement: Una versión publicada no cambia

Una vez `PUBLICADA`, una versión NO DEBE cambiar sus precios, sus vigencias ni ningún dato del cálculo, por ningún comando ni por cambios posteriores en la lista, sus reglas, su redondeo, los costos informados o el catálogo (PRC-04, INV-11). El único cambio admitido es su anulación antes de la vigencia. Las correcciones DEBEN hacerse con una versión nueva. El cambio de la presentación de referencia de un producto NO DEBE alterar el precio ni las unidades de referencia guardadas en una versión publicada (`design.md` D1).

#### Scenario: Ningún comando modifica un precio publicado
- **GIVEN** la versión n.º 3 `PUBLICADA` con Vino A a `"8600.00"`
- **WHEN** se intenta fijar un precio manual sobre ella, regenerarla o publicarla de nuevo
- **THEN** cada intento se rechaza y Vino A sigue a `"8600.00"`
- **Regla:** INV-11; PRC-04

#### Scenario: Un costo nuevo no cambia lo publicado
- **GIVEN** la versión n.º 3 `PUBLICADA` con Vino A a `"8600.00"`
- **WHEN** se informa un costo nuevo de Vino A y se genera un borrador
- **THEN** la versión n.º 3 sigue con Vino A a `"8600.00"` y costo de referencia `"6000.000000"`
- **Regla:** INV-11; PRC-04; `00` §9 (criterio 3)

#### Scenario: Publicar otra versión no toca la anterior
- **GIVEN** la versión n.º 2 `PUBLICADA` sin vigencia hasta
- **WHEN** se publica la versión n.º 3 con vigencia desde posterior
- **THEN** la versión n.º 2 conserva todos sus datos, incluida su vigencia hasta nula
- **Regla:** INV-11; PRC-03; `design.md` D6

#### Scenario: Cambiar la presentación de referencia
- **GIVEN** la versión `PUBLICADA` con Vino A a `"8600.00"` y unidades de referencia `6`
- **WHEN** se cambia la referencia de Vino A a `Caja x12`
- **THEN** la versión sigue informando `"8600.00"` y unidades de referencia `6`
- **Regla:** INV-11; PRC-10; INV-18; `design.md` D1

#### Scenario: Publicar y fijar un precio al mismo tiempo
- **GIVEN** un borrador con Vino A a `"8600.00"`
- **WHEN** dos transacciones con commits reales envían al mismo tiempo `LISTA_PUBLICAR` y `LISTA_BORRADOR_PRECIO_FIJAR` de Vino A a `"9000.00"`
- **THEN** o la versión queda publicada con `"9000.00"`, o queda publicada con `"8600.00"` y el precio manual se rechaza con `VERSION_NO_ES_BORRADOR`; nunca cambia un precio después de publicado
- **Regla:** INV-11; `design.md` D14

### Requirement: La versión vigente y los estados derivados se calculan de las fechas

La versión vigente de una lista en un momento DEBE ser, entre sus versiones `PUBLICADA` cuya vigencia desde no supera ese momento y cuya vigencia hasta, si existe, es posterior, la de mayor vigencia desde (PRC-03, `design.md` D6). Los estados `PROGRAMADA` (publicada cuya vigencia aún no comenzó), `VIGENTE` e `HISTÓRICA` (publicada que ya empezó y no es la vigente) DEBEN derivarse de las fechas al consultar y NO DEBEN almacenarse. Una versión `BORRADOR` o `ANULADA` nunca es vigente.

#### Scenario: La versión más nueva reemplaza a la anterior
- **GIVEN** la versión n.º 2 con vigencia desde el 01/09 y la n.º 3 con vigencia desde el 01/10, ambas `PUBLICADA` y sin vigencia hasta
- **WHEN** se consulta la versión vigente al 15/09 y al 02/10
- **THEN** es la n.º 2 y la n.º 3 respectivamente; al 02/10 la n.º 2 es `HISTÓRICA`
- **Regla:** PRC-03; `01` §18

#### Scenario: Versión programada
- **GIVEN** la versión n.º 3 con vigencia desde el 01/10
- **WHEN** se consulta el 30/09
- **THEN** su estado derivado es `PROGRAMADA` y la vigente es la n.º 2
- **Regla:** PRC-03

#### Scenario: Una versión que vence devuelve la vigencia a la anterior
- **GIVEN** la versión n.º 2 desde el 01/09 sin vigencia hasta y la n.º 3 desde el 01/10 hasta el 01/11
- **WHEN** se consulta la versión vigente al 05/11
- **THEN** es la n.º 2
- **Regla:** PRC-03; `design.md` D6

#### Scenario: Momento exacto del límite
- **GIVEN** la versión n.º 3 con vigencia desde el 01/10 a las 00:00 y hasta el 01/11 a las 00:00
- **WHEN** se consulta en el instante del 01/10 a las 00:00 y en el del 01/11 a las 00:00
- **THEN** en el primero es vigente y en el segundo ya no
- **Regla:** PRC-03 (desde que no supere el momento; hasta posterior)

#### Scenario: Lista sin versión vigente
- **GIVEN** una lista con un borrador y ninguna versión publicada
- **WHEN** se consulta su versión vigente
- **THEN** no tiene
- **Regla:** PRC-03

#### Scenario: Los estados derivados no se guardan
- **WHEN** se recorre el esquema de la base
- **THEN** el estado almacenado de una versión solo admite `BORRADOR`, `PUBLICADA` y `ANULADA`
- **Regla:** PRC-02; PRC-03; `03` §8

### Requirement: Solo se anula una versión publicada cuya vigencia aún no comenzó

El sistema DEBE anular una versión con `LISTA_ANULAR_VERSION` (solo `ONLINE`, con `Operation-Id`, permiso `PUBLICAR_LISTAS`) únicamente si está `PUBLICADA` y su vigencia desde es posterior al momento de la anulación (PRC-05). Una versión cuya vigencia ya comenzó DEBE rechazarse con `VERSION_YA_VIGENTE`; un borrador o una versión ya anulada, con `VERSION_NO_PUBLICADA`. La versión anulada DEBE quedar `ANULADA` con usuario y momento, sin borrar ni modificar sus precios, y la anulación DEBE quedar auditada (AUD-01). Una versión `ANULADA` NO DEBE volver a otro estado.

#### Scenario: Anular una versión programada
- **GIVEN** la versión n.º 3 `PUBLICADA` con vigencia desde el 01/10 y la fecha de hoy 30/09
- **WHEN** un usuario con `PUBLICAR_LISTAS` envía `LISTA_ANULAR_VERSION`
- **THEN** la versión queda `ANULADA` con usuario y momento, conserva sus precios, hay una fila de auditoría y la vigente sigue siendo la n.º 2 también después del 01/10
- **Regla:** PRC-05; AUD-01; `01` §18 (PUBLICADA → ANULADA)

#### Scenario: Anular una versión que ya rige
- **GIVEN** la versión n.º 3 con vigencia desde el 01/10 y la fecha de hoy 02/10
- **WHEN** se envía `LISTA_ANULAR_VERSION`
- **THEN** se rechaza con `VERSION_YA_VIGENTE` y la versión sigue `PUBLICADA`
- **Regla:** PRC-05; PRC-04

#### Scenario: Anular un borrador o una versión anulada
- **WHEN** se envía `LISTA_ANULAR_VERSION` sobre un borrador o sobre una versión `ANULADA`
- **THEN** se rechaza con `VERSION_NO_PUBLICADA`
- **Regla:** PRC-05; `01` §18

#### Scenario: Sin permiso
- **WHEN** un usuario con `GESTIONAR_LISTAS` y sin `PUBLICAR_LISTAS` envía `LISTA_ANULAR_VERSION`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y la versión sigue `PUBLICADA`
- **Regla:** `01` §19 (`PUBLICAR_LISTAS`: publicar y anular versiones); SEG-06

#### Scenario: Versión de otra organización
- **WHEN** un usuario de A anula una versión de B
- **THEN** la respuesta es 404 y la versión de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío de la anulación
- **GIVEN** un `LISTA_ANULAR_VERSION` aceptado con `operation_id` X
- **WHEN** se reenvía con X y el mismo contenido
- **THEN** se devuelve el resultado original y hay una sola fila de auditoría de la anulación
- **Regla:** INV-06; SYN-02

#### Scenario: Dos anulaciones simultáneas
- **WHEN** dos transacciones con commits reales anulan a la vez la misma versión programada con distinto `operation_id`
- **THEN** una la anula y la otra recibe `VERSION_NO_PUBLICADA`
- **Regla:** PRC-05; `design.md` D14

#### Scenario: La anulación no borra nada
- **GIVEN** una versión anulada
- **WHEN** se consultan sus precios
- **THEN** están todos, sin cambios
- **Regla:** TR-06; INV-11

### Requirement: Las versiones de una lista se consultan, incluidas las anteriores

El sistema DEBE listar las versiones de una lista, de la más nueva a la más antigua, con número, estado almacenado, estado derivado, vigencias, quién la creó y quién y cuándo la publicó o anuló; y DEBE devolver los precios de cualquier versión, también `HISTÓRICA` o `ANULADA`, paginados por cursor, con las mismas reglas de visibilidad de costos que el borrador (`VER_COSTOS`, `design.md` D12). Las lecturas DEBEN exigir `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. Ninguna lectura DEBE devolver versiones de otra organización.

#### Scenario: Historial de versiones
- **GIVEN** `General` con las versiones n.º 1 (histórica), n.º 2 (vigente), n.º 3 (anulada) y n.º 4 (borrador)
- **WHEN** se listan sus versiones
- **THEN** se devuelven las cuatro en orden 4, 3, 2, 1, cada una con su estado almacenado y su estado derivado cuando corresponde
- **Regla:** PRC-02; PRC-03

#### Scenario: Precios de una versión anterior
- **GIVEN** la versión n.º 1, `HISTÓRICA`, con Vino A a `"7800.00"`
- **WHEN** se consultan sus precios
- **THEN** se devuelve Vino A a `"7800.00"` con sus unidades de referencia, tal como se publicó
- **Regla:** PRC-04; PRC-16; INV-11

#### Scenario: La versión muestra el precio por presentación
- **GIVEN** una versión no borrador con Vino A a `"9500.00"` sobre 6 unidades de referencia, con presentaciones Botella (1 u.) y Caja x6 (6 u.), y un producto sin otras presentaciones de venta
- **WHEN** se abre la pantalla de la versión, con o sin `VER_COSTOS`
- **THEN** la línea de Vino A muestra Botella a `$ 1.583,33` y Caja x6 a `$ 9.500,00` (PRC-22, a partir del precio y las unidades guardados en la versión), y la del producto sin presentaciones no muestra ninguna; el cálculo es el mismo que en el borrador y es solo informativo
- **Regla:** PRC-22; PRC-04

#### Scenario: Versiones de una lista ajena
- **WHEN** un usuario de A lista las versiones de una lista de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso
- **WHEN** un usuario sin `GESTIONAR_LISTAS` ni `PUBLICAR_LISTAS` lista versiones o precios
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06
