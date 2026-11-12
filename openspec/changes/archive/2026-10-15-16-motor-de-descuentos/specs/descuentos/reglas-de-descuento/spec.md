## Purpose

Definir las reglas de descuento por volumen de una organización: su alta, su edición mientras son borrador, sus estados, su vigencia, su alcance y sus consultas, de modo que el motor de descuentos y la venta dispongan de un conjunto de reglas bien formado (DSC-01, DSC-02, DSC-03, DSC-04; `01` §18; ADR-004).

## ADDED Requirements

### Requirement: Una regla de descuento se crea por comando como borrador

El comando `REGLA_DESCUENTO_CREAR` DEBE crear una regla en estado `BORRADOR` con nombre, tipo, condición (medida, operador y umbral), acción (tipo y valor), alcance, prioridad, indicador de acumulable y vigencia opcional (DSC-01). DEBE exigir el permiso `GESTIONAR_DESCUENTOS` y conexión: es solo `ONLINE`. Los tipos DEBEN ser `VOLUMEN_OPERACION` y `VOLUMEN_ALCANCE` (DSC-02); las medidas, `CAJAS_EQUIVALENTES`, `UNIDADES_BASE` e `IMPORTE_BRUTO`; los operadores, `GTE` (≥) y `GT` (>) (DSC-03); las acciones, `PORCENTAJE` e `IMPORTE_FIJO` (DSC-04). Ningún otro tipo, medida, operador ni acción DEBE aceptarse (`design.md` D1). El nombre se guarda recortado y NO DEBE quedar vacío (`NOMBRE_INVALIDO`). La regla y sus alcances se escriben todos o ninguno (INV-01). Una regla en `BORRADOR` NO participa de ningún cálculo.

#### Scenario: Regla de volumen sobre toda la venta

- **GIVEN** un Administrador con `GESTIONAR_DESCUENTOS`
- **WHEN** envía `REGLA_DESCUENTO_CREAR` con tipo `VOLUMEN_OPERACION`, medida `CAJAS_EQUIVALENTES`, operador `GTE`, umbral `20`, acción `PORCENTAJE` de `0.050000`, prioridad 1 y no acumulable
- **THEN** se crea la regla en `BORRADOR`, sin alcances, con el porcentaje guardado como `0.050000`
- **Regla:** DSC-01; DSC-02; DSC-03; TR-02

#### Scenario: Regla de volumen sobre una marca

- **GIVEN** la marca "Bodega Norte" de la organización
- **WHEN** el Administrador envía `REGLA_DESCUENTO_CREAR` con tipo `VOLUMEN_ALCANCE`, un alcance `MARCA` "Bodega Norte", medida `UNIDADES_BASE`, operador `GT`, umbral `60` y acción `IMPORTE_FIJO` de `1000.00`
- **THEN** se crea la regla en `BORRADOR` con ese alcance
- **Regla:** DSC-02; DSC-04; `design.md` D1

#### Scenario: Sin permiso

- **GIVEN** un usuario del rol Administración, que no tiene `GESTIONAR_DESCUENTOS`
- **WHEN** envía `REGLA_DESCUENTO_CREAR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` y no se crea ninguna regla
- **Regla:** SEG-06; `01` §19

#### Scenario: Tipo, medida, operador o acción desconocidos

- **GIVEN** un Administrador
- **WHEN** envía `REGLA_DESCUENTO_CREAR` con una medida `HISTORIAL_DE_COMPRAS` o una acción `BONIFICACION_EN_UNIDADES`
- **THEN** se rechaza con 422 y no se crea ninguna regla
- **Regla:** DSC-02; DSC-03; DSC-04; DSC-10 (etapa 2)

#### Scenario: Umbral inválido para la medida

- **GIVEN** un Administrador
- **WHEN** envía una regla con medida `UNIDADES_BASE` y umbral `10.5`, o con cualquier medida y umbral `0` o negativo, o con medida `IMPORTE_BRUTO` y umbral de tres decimales
- **THEN** se rechaza con 422 `UMBRAL_INVALIDO`
- **Regla:** DSC-03; INV-04; TR-01; `design.md` D5

#### Scenario: Valor de la acción inválido

- **GIVEN** un Administrador
- **WHEN** envía una acción `PORCENTAJE` de `0`, de `1.200000` o con siete decimales, o una acción `IMPORTE_FIJO` de `0`, negativa o con tres decimales
- **THEN** se rechaza con 422 `ACCION_INVALIDA`
- **Regla:** DSC-04; TR-01; TR-02; INV-03

#### Scenario: El valor de la acción llega como número

- **GIVEN** un Administrador
- **WHEN** envía el porcentaje como número JSON `0.05` en lugar de la cadena `"0.050000"`
- **THEN** se rechaza con 422 y no se crea ninguna regla
- **Regla:** INV-03; `02` §10.2

#### Scenario: Prioridad inválida

- **GIVEN** un Administrador
- **WHEN** envía una regla con prioridad `0`, negativa o no entera
- **THEN** se rechaza con 422 `PRIORIDAD_INVALIDA`
- **Regla:** DSC-01; `design.md` D8

#### Scenario: Falla a mitad de la escritura

- **GIVEN** una regla `VOLUMEN_ALCANCE` con tres alcances
- **WHEN** la escritura falla después de guardar la regla y antes de guardar el último alcance
- **THEN** no queda ni la regla ni ningún alcance, y el mismo `operation_id` se puede reintentar
- **Regla:** INV-01

#### Scenario: Doble envío del alta

- **GIVEN** un `REGLA_DESCUENTO_CREAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y sigue habiendo una sola regla
- **Regla:** SYN-02; INV-06

#### Scenario: Mismo identificador con otro contenido

- **GIVEN** un `REGLA_DESCUENTO_CREAR` ya aceptado con umbral `20`
- **WHEN** llega el mismo `operation_id` con umbral `10`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y la regla original no cambia
- **Regla:** SYN-02

#### Scenario: El alta no se acepta sin conexión

- **GIVEN** un lote de sincronización con un `REGLA_DESCUENTO_CREAR` en modo `OFFLINE`
- **WHEN** el servidor procesa el lote
- **THEN** ese comando se rechaza y no se crea ninguna regla
- **Regla:** `02` §6.5

### Requirement: El alcance de una regla es coherente con su tipo

Una regla `VOLUMEN_OPERACION` NO DEBE tener alcances; una `VOLUMEN_ALCANCE` DEBE tener al menos uno (`03` §11). Cada alcance DEBE ser un producto, una categoría o una marca de la misma organización (DSC-02); una entidad inexistente o de otra organización responde 404. Un mismo alcance NO DEBE repetirse dentro de una regla. La base DEBE impedir que un alcance apunte a una entidad de otra organización (INV-02).

#### Scenario: Regla de alcance sin alcances

- **GIVEN** un Administrador
- **WHEN** envía una regla `VOLUMEN_ALCANCE` sin ningún alcance
- **THEN** se rechaza con 422 `ALCANCE_INVALIDO`
- **Regla:** DSC-02; `03` §11

#### Scenario: Regla de operación con alcances

- **GIVEN** un Administrador
- **WHEN** envía una regla `VOLUMEN_OPERACION` con un alcance `CATEGORIA`
- **THEN** se rechaza con 422 `ALCANCE_INVALIDO`
- **Regla:** DSC-02; `03` §11

#### Scenario: Alcance repetido

- **GIVEN** un Administrador
- **WHEN** envía una regla con el mismo producto dos veces en sus alcances
- **THEN** se rechaza con 422 `ALCANCE_INVALIDO`
- **Regla:** DSC-02

#### Scenario: Entidad del alcance de otra organización

- **GIVEN** una categoría que pertenece a otra organización
- **WHEN** el Administrador envía una regla `VOLUMEN_ALCANCE` con esa categoría
- **THEN** responde 404 y no se crea ninguna regla
- **Regla:** INV-21; SEG-07

#### Scenario: La base rechaza un alcance ajeno escrito por fuera del servicio

- **GIVEN** una regla de la organización A y un producto de la organización B
- **WHEN** se inserta directamente en la base un alcance de esa regla hacia ese producto
- **THEN** la base lo rechaza
- **Regla:** INV-02

### Requirement: Una regla solo se edita mientras es borrador

El comando `REGLA_DESCUENTO_MODIFICAR` DEBE reemplazar los datos de una regla en `BORRADOR` con las mismas validaciones que el alta, y DEBE exigir `GESTIONAR_DESCUENTOS`. Sobre una regla `ACTIVA` o `PAUSADA` DEBE rechazarse con `REGLA_NO_ES_BORRADOR` (409), salvo el cambio de su vigencia hasta (`design.md` D15, D16): para cambiar la condición, la acción, el alcance, la prioridad o la acumulabilidad de una regla ya activada se la pausa y se crea otra. Ninguna regla se borra (TR-06). Una regla de otra organización responde 404.

#### Scenario: Corregir el umbral de un borrador

- **GIVEN** una regla en `BORRADOR` con umbral `20`
- **WHEN** el Administrador envía `REGLA_DESCUENTO_MODIFICAR` con umbral `24`
- **THEN** la regla queda con umbral `24` y sigue en `BORRADOR`
- **Regla:** DSC-01; `design.md` D15

#### Scenario: Intentar cambiar el porcentaje de una regla activa

- **GIVEN** una regla `ACTIVA` del 5%
- **WHEN** el Administrador envía `REGLA_DESCUENTO_MODIFICAR` con 8%
- **THEN** se rechaza con 409 `REGLA_NO_ES_BORRADOR` y la regla sigue en 5%
- **Regla:** TR-06; `design.md` D15

#### Scenario: Ponerle fin a una regla activa

- **GIVEN** una regla `ACTIVA` sin vigencia hasta
- **WHEN** el Administrador envía `REGLA_DESCUENTO_MODIFICAR` solo con una vigencia hasta futura
- **THEN** la regla conserva todos sus datos y queda con esa vigencia hasta
- **Regla:** DSC-01; `design.md` D16

#### Scenario: Regla de otra organización

- **GIVEN** una regla que pertenece a otra organización
- **WHEN** el Administrador envía `REGLA_DESCUENTO_MODIFICAR` sobre ella
- **THEN** responde 404 y la regla ajena no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe forma de borrar una regla

- **GIVEN** una regla en cualquier estado
- **WHEN** se recorren las rutas y los comandos del sistema
- **THEN** ninguno borra una regla ni sus alcances de una regla ya activada
- **Regla:** TR-06

### Requirement: Una regla se activa y se pausa siguiendo su máquina de estados

Los comandos `REGLA_DESCUENTO_ACTIVAR` y `REGLA_DESCUENTO_PAUSAR` DEBEN mover una regla por `BORRADOR → ACTIVA ↔ PAUSADA` (`01` §18) y exigir `GESTIONAR_DESCUENTOS`. Activar DEBE aceptarse desde `BORRADOR` y desde `PAUSADA`; pausar, solo desde `ACTIVA`. Cualquier otra transición DEBE rechazarse con `REGLA_ESTADO_INVALIDO` (409) y dejar la regla como estaba; ninguna regla vuelve a `BORRADOR`. Al activar por primera vez, la vigencia desde DEBE quedar definida: la indicada o, si no se indicó, el momento de la activación (`design.md` D16). Dos transiciones simultáneas sobre la misma regla NO DEBEN dejarla en un estado que ninguna de las dos pidió.

#### Scenario: Activar un borrador

- **GIVEN** una regla en `BORRADOR` sin vigencia desde
- **WHEN** el Administrador envía `REGLA_DESCUENTO_ACTIVAR`
- **THEN** la regla queda `ACTIVA` con vigencia desde igual al momento de la activación
- **Regla:** `01` §18; DSC-01

#### Scenario: Pausar y reactivar

- **GIVEN** una regla `ACTIVA`
- **WHEN** el Administrador la pausa y más tarde la activa otra vez
- **THEN** queda `PAUSADA` y después `ACTIVA`, con la misma vigencia desde
- **Regla:** `01` §18

#### Scenario: Pausar un borrador

- **GIVEN** una regla en `BORRADOR`
- **WHEN** el Administrador envía `REGLA_DESCUENTO_PAUSAR`
- **THEN** se rechaza con 409 `REGLA_ESTADO_INVALIDO` y la regla sigue en `BORRADOR`
- **Regla:** `01` §18

#### Scenario: Activar una regla ya activa

- **GIVEN** una regla `ACTIVA`
- **WHEN** llega un `REGLA_DESCUENTO_ACTIVAR` con un `operation_id` nuevo
- **THEN** se rechaza con 409 `REGLA_ESTADO_INVALIDO`
- **Regla:** `01` §18

#### Scenario: Activar una regla cuya vigencia ya terminó

- **GIVEN** una regla `PAUSADA` con vigencia hasta anterior a este momento
- **WHEN** el Administrador envía `REGLA_DESCUENTO_ACTIVAR`
- **THEN** se rechaza con 422 `VIGENCIA_INVALIDA`
- **Regla:** DSC-01; `design.md` D16

#### Scenario: Activar sin permiso

- **GIVEN** un Supervisor comercial, que no tiene `GESTIONAR_DESCUENTOS`
- **WHEN** envía `REGLA_DESCUENTO_ACTIVAR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` y la regla no cambia
- **Regla:** SEG-06; `01` §19

#### Scenario: Doble envío de la activación

- **GIVEN** un `REGLA_DESCUENTO_ACTIVAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original, sin rechazo por estado
- **Regla:** SYN-02; INV-06

#### Scenario: Activar y pausar a la vez

- **GIVEN** una regla `ACTIVA`
- **WHEN** dos usuarios envían al mismo tiempo dos `REGLA_DESCUENTO_PAUSAR` con distinto `operation_id`
- **THEN** uno se acepta y el otro se rechaza con `REGLA_ESTADO_INVALIDO`
- **Regla:** `01` §18

### Requirement: La vigencia delimita cuándo aplica una regla

Una regla DEBE aplicar en un momento dado solo si está `ACTIVA` y ese momento es igual o posterior a su vigencia desde y anterior a su vigencia hasta, cuando la tiene (DSC-01, DSC-05 paso 2; mismo criterio que las versiones de lista, PRC-02). La vigencia hasta, si existe, DEBE ser posterior a la desde (`VIGENCIA_INVALIDA`). El estado `VENCIDA` es derivado y NO se almacena: una regla `ACTIVA` o `PAUSADA` cuya vigencia hasta ya pasó se informa como `VENCIDA` (`01` §18). El conjunto de reglas aplicables a un momento DEBE poder obtenerse con sus alcances, para la venta y para el bootstrap.

#### Scenario: Regla programada

- **GIVEN** una regla `ACTIVA` con vigencia desde el lunes próximo
- **WHEN** se piden las reglas aplicables a hoy
- **THEN** esa regla no figura
- **Regla:** DSC-01; DSC-05

#### Scenario: Regla vencida

- **GIVEN** una regla `ACTIVA` cuya vigencia hasta fue ayer
- **WHEN** se piden las reglas aplicables a hoy y se consulta la regla
- **THEN** no figura entre las aplicables y su estado se informa como `VENCIDA`
- **Regla:** `01` §18; DSC-05

#### Scenario: Regla pausada

- **GIVEN** una regla `PAUSADA` dentro de su vigencia
- **WHEN** se piden las reglas aplicables a hoy
- **THEN** esa regla no figura
- **Regla:** `01` §18; DSC-05

#### Scenario: Las reglas aplicables son las del momento de la operación

- **GIVEN** una regla `ACTIVA` vigente desde el día 10 y otra vigente hasta el día 10
- **WHEN** se piden las reglas aplicables a un momento del día 9
- **THEN** figura solo la segunda
- **Regla:** DSC-05; TR-05

#### Scenario: Vigencia hasta anterior a la desde

- **GIVEN** un Administrador
- **WHEN** envía una regla con vigencia hasta anterior o igual a la vigencia desde
- **THEN** se rechaza con 422 `VIGENCIA_INVALIDA`
- **Regla:** DSC-01

#### Scenario: Reglas aplicables de otra organización

- **GIVEN** dos organizaciones, cada una con una regla `ACTIVA` y vigente
- **WHEN** se piden las reglas aplicables de la primera
- **THEN** no figura la regla de la segunda
- **Regla:** INV-21; TR-08

### Requirement: Las reglas se consultan por organización

El sistema DEBE ofrecer el listado de reglas (con filtro por estado, incluido el derivado `VENCIDA`, paginado por cursor) y el detalle de una regla con sus alcances y el nombre de cada entidad, a quien tenga `GESTIONAR_DESCUENTOS` (`design.md` D18). Los porcentajes y los importes DEBEN viajar como cadena. Las lecturas de productos, categorías y marcas necesarias para elegir un alcance DEBEN abrirse, solo en lectura, a `GESTIONAR_DESCUENTOS`. Una regla de otra organización responde 404.

#### Scenario: Listado de reglas

- **GIVEN** un Administrador y reglas en `BORRADOR`, `ACTIVA` y `PAUSADA`
- **WHEN** pide el listado
- **THEN** recibe cada regla con su tipo, condición, acción, prioridad, acumulabilidad, vigencia y estado, con el porcentaje como `"0.050000"` y el importe como `"1000.00"`
- **Regla:** DSC-01; `02` §10.2; INV-03

#### Scenario: Filtro por vencidas

- **GIVEN** una regla `ACTIVA` con la vigencia hasta ya pasada y otra `ACTIVA` vigente
- **WHEN** el Administrador pide el listado con estado `VENCIDA`
- **THEN** recibe solo la primera
- **Regla:** `01` §18

#### Scenario: Lectura sin permiso

- **GIVEN** un Vendedor, que no tiene `GESTIONAR_DESCUENTOS`
- **WHEN** pide el listado de reglas
- **THEN** se rechaza con 403
- **Regla:** SEG-06; `01` §19; `design.md` D18

#### Scenario: Elegir el alcance con solo el permiso de descuentos

- **GIVEN** un rol a medida con `GESTIONAR_DESCUENTOS` y sin `GESTIONAR_CATALOGO`
- **WHEN** pide los productos, las categorías y las marcas para elegir un alcance
- **THEN** los recibe, y un intento de modificarlos se rechaza con 403
- **Regla:** `01` §19; `design.md` D18

#### Scenario: Detalle de una regla ajena

- **GIVEN** una regla de otra organización
- **WHEN** el Administrador pide su detalle
- **THEN** responde 404
- **Regla:** INV-21; SEG-07
