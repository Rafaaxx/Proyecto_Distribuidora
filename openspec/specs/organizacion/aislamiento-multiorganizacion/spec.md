# aislamiento-multiorganizacion Specification

## Purpose

Define el contrato de aislamiento entre organizaciones que toda tabla, todo repositorio y toda ruta del sistema debe cumplir: un dato de negocio pertenece a exactamente una organización y nunca es alcanzable desde otra (TR-08, INV-02, INV-21, `02` §8, `03` §2.4).

## Requirements

### Requirement: Toda tabla de negocio declara su organización
Toda tabla de negocio DEBE tener una columna `organizacion_id` no nula y una restricción de unicidad compuesta `UNIQUE (organizacion_id, id)`, de modo que la organización de una fila sea siempre determinable desde la propia fila y pueda usarse como destino de una clave foránea compuesta (INV-02, `03` §2.3, `03` §2.4).

#### Scenario: Una tabla de negocio sin organización no llega a la base
- **WHEN** se recorre el catálogo de tablas de negocio de la base
- **THEN** toda tabla de negocio tiene `organizacion_id` declarada `NOT NULL`
- **AND** toda tabla de negocio tiene una restricción única sobre `(organizacion_id, id)`
- **Regla:** INV-02 (todo dato de negocio pertenece a exactamente una organización)

#### Scenario: Insertar una fila de negocio sin organización falla
- **GIVEN** una organización existente y la tabla `motivo`
- **WHEN** se intenta insertar un motivo con `organizacion_id` nulo
- **THEN** la base rechaza la inserción y no queda ninguna fila nueva
- **Regla:** INV-02

#### Scenario: Una organización inexistente no puede referenciarse
- **GIVEN** un identificador de organización que no existe en `organizacion`
- **WHEN** se intenta insertar una alícuota de IVA con ese `organizacion_id`
- **THEN** la base rechaza la inserción por violación de clave foránea
- **Regla:** INV-02

### Requirement: Las referencias entre entidades de negocio son compuestas
Las claves foráneas entre dos entidades de negocio DEBEN incluir `organizacion_id`, de modo que la base —y no el código— impida que una fila referencie a una fila de otra organización (`03` §2.4, `02` §8).

#### Scenario: Una referencia cruzada entre organizaciones se rechaza en la base
- **GIVEN** la organización A con una fila de configuración y la organización B
- **WHEN** se intenta crear desde la organización B una referencia a una fila de negocio de la organización A
- **THEN** la base rechaza la operación por violación de clave foránea compuesta
- **AND** el rechazo ocurre aunque el código de aplicación no haya validado nada
- **Regla:** `03` §2.4 (las claves foráneas entre entidades de negocio son compuestas e incluyen `organizacion_id`)

#### Scenario: El esquema no tiene referencias simples entre entidades de negocio
- **GIVEN** el esquema migrado a la última revisión
- **WHEN** se recorre el catálogo de claves foráneas entre tablas de negocio
- **THEN** ninguna clave foránea entre dos tablas de negocio omite `organizacion_id`, salvo la referencia de la propia `organizacion_id` a `organizacion (id)`
- **Regla:** `03` §2.4

### Requirement: Ningún acceso a datos existe sin organización
Toda operación de lectura o escritura sobre datos de negocio DEBE recibir la organización como parámetro obligatorio y filtrarla en la consulta. NO DEBE existir ninguna operación de acceso a datos de negocio que devuelva o modifique filas sin haber recibido una organización (`02` §8).

#### Scenario: Una consulta nunca ve filas de otra organización
- **GIVEN** la organización A con un medio de pago y la organización B con otro medio de pago
- **WHEN** se listan los medios de pago de la organización A
- **THEN** el resultado contiene únicamente el medio de pago de la organización A
- **Regla:** TR-08 (todo dato de negocio solo es visible y modificable desde su organización)

#### Scenario: Buscar por identificador con la organización equivocada no encuentra nada
- **GIVEN** una alícuota de IVA que pertenece a la organización A
- **WHEN** se la busca por su identificador indicando la organización B
- **THEN** la búsqueda no devuelve ninguna fila, como si el identificador no existiera
- **AND** no se revela que la fila exista en otra organización
- **Regla:** SEG-07 (un recurso de otra organización responde 404, no 403)

#### Scenario: Modificar con la organización equivocada no cambia nada
- **GIVEN** un motivo que pertenece a la organización A
- **WHEN** se intenta desactivarlo indicando la organización B
- **THEN** la operación falla como "no encontrado" y el motivo de la organización A queda intacto
- **Regla:** TR-08, SEG-07

#### Scenario: Una operación de acceso a datos sin organización no llega a existir
- **GIVEN** el conjunto de operaciones de acceso a datos de negocio del sistema
- **WHEN** se inspeccionan sus parámetros
- **THEN** todas exigen la organización como parámetro obligatorio
- **AND** la verificación falla nombrando la operación que la omite
- **Regla:** `02` §8 ("no existen funciones de repositorio sin organización")

### Requirement: Toda ruta de negocio queda cubierta por la verificación de aislamiento
El sistema DEBE mantener una verificación que recorra dinámicamente todas las rutas registradas y compruebe que cada ruta de negocio fue ejercida con una organización ajena sin exponer ni modificar datos. Una ruta de negocio nueva que no esté cubierta DEBE hacer fallar la verificación; solo las rutas de sistema declaradas explícitamente quedan exentas (INV-21, `02` §8, `02` §15).

#### Scenario: Una ruta de negocio sin cobertura de aislamiento hace fallar la verificación
- **GIVEN** una ruta de negocio registrada y no declarada en la cobertura de aislamiento
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** la verificación falla nombrando la ruta y su método
- **Regla:** INV-21 (ningún usuario obtiene ni modifica datos de otra organización)

#### Scenario: Las rutas de sistema no requieren organización
- **GIVEN** las rutas de salud, versión y documentación de la API
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** esas rutas quedan exentas por estar declaradas como rutas de sistema
- **AND** la exención es explícita y enumerable, no una regla de nombre
- **Regla:** INV-21, `02` §15 (la prueba recorre dinámicamente todas las rutas registradas)
