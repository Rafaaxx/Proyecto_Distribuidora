## MODIFIED Requirements

### Requirement: Toda tabla de negocio declara su organización
Toda tabla de negocio DEBE tener una columna `organizacion_id` no nula y una restricción de unicidad compuesta `UNIQUE (organizacion_id, id)`, de modo que la organización de una fila sea siempre determinable desde la propia fila y pueda usarse como destino de una clave foránea compuesta (INV-02, `03` §2.3, `03` §2.4).

Un catálogo global —dato atado al código y no a ninguna organización, sincronizado por migración (`03` §17)— queda exento de este requisito. Las exenciones DEBEN estar declaradas en una lista explícita y enumerable; una tabla que no esté en esa lista se verifica como tabla de negocio.

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

#### Scenario: El catálogo global de permisos queda exento de forma explícita
- **GIVEN** la tabla `permiso`, que `03` §4 define como catálogo global sin organización
- **WHEN** se ejecuta la verificación estructural de INV-02
- **THEN** queda exenta por estar declarada en la lista de catálogos globales
- **AND** la exención es explícita y enumerable, no una regla de nombre ni una excepción implícita
- **Regla:** INV-02, `03` §4 (el catálogo de `permiso` es global, sin organización)

#### Scenario: Una tabla de negocio no puede exentarse por omisión
- **GIVEN** una tabla nueva con datos de negocio que no fue declarada como catálogo global
- **WHEN** se ejecuta la verificación estructural de INV-02
- **THEN** se la verifica como tabla de negocio y la verificación falla si le falta `organizacion_id` o la unicidad compuesta
- **Regla:** INV-02

#### Scenario: La relación entre roles y permisos sí pertenece a una organización
- **GIVEN** la tabla que asocia roles con permisos
- **WHEN** se ejecuta la verificación estructural de INV-02
- **THEN** se la verifica como tabla de negocio, porque la composición de un rol es dato de la organización
- **Regla:** INV-02, `03` §4 (`rol_permiso` incluye `organizacion_id`), `01` §19 (los roles son plantillas que la organización puede modificar)

### Requirement: Toda ruta de negocio queda cubierta por la verificación de aislamiento
El sistema DEBE mantener una verificación que recorra dinámicamente todas las rutas registradas y compruebe que cada ruta de negocio fue ejercida con una organización ajena sin exponer ni modificar datos. Una ruta de negocio nueva que no esté cubierta DEBE hacer fallar la verificación; solo las rutas de sistema declaradas explícitamente quedan exentas (INV-21, `02` §8, `02` §15).

La verificación DEBE ejercer cada ruta de negocio con un usuario realmente autenticado en otra organización —no con una organización informada por fuera del token— y comprobar que la respuesta indica que el recurso no existe (SEG-07). Las rutas de autenticación quedan exentas como rutas de sistema, porque operan antes de que exista una organización en el contexto.

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

#### Scenario: Las rutas de autenticación quedan exentas por operar sin organización en contexto
- **GIVEN** las rutas de inicio, renovación y cierre de sesión
- **WHEN** se ejecuta la verificación de aislamiento
- **THEN** quedan exentas por estar declaradas, junto a las rutas de sistema, como rutas sin organización en contexto
- **AND** el aislamiento del inicio de sesión se cubre por separado: un usuario de una organización no inicia sesión contra los datos de otra
- **Regla:** INV-21, SEG-01

#### Scenario: Cada ruta de negocio se ejerce con un usuario de otra organización
- **GIVEN** dos organizaciones, cada una con un usuario autenticado y con los permisos necesarios
- **WHEN** se recorre cada ruta de negocio registrada usando el token del usuario de la otra organización sobre recursos ajenos
- **THEN** ninguna ruta expone ni modifica datos de la organización ajena
- **AND** todas responden que el recurso no existe
- **Regla:** INV-21, SEG-07, `02` §8 (existe una prueba automatizada que recorre todos los endpoints con un usuario de otra organización)

#### Scenario: La organización usada es siempre la del token
- **GIVEN** un usuario autenticado en una organización
- **WHEN** se recorre cada ruta de negocio informando otra organización por fuera del token
- **THEN** ninguna ruta opera sobre la organización informada
- **Regla:** `02` §8 (`organizacion_id` se toma del token y nunca del contenido de la petición), INV-21
