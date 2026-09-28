## Purpose

Define cómo la interfaz de `/admin` conoce la identidad y los permisos efectivos de la sesión en curso (`GET /api/v1/yo`) y cómo los usa para mostrar u ocultar menú, pantallas y acciones, sin que ocultar reemplace nunca la validación del servidor (ADR-027, SEG-06).

> Los escenarios marcados con **(B1)**, **(B2)**, **(B3)** o **(B4)** reflejan la opción A de las decisiones D3 a D6 de `design.md`, aprobadas por el usuario el 2026-09-25. La marca solo indica de qué decisión sale el escenario. Los marcados con **(D9)** dependen de ADR-028 (CRÍTICO), aprobado por el usuario el 2026-09-25, y reflejan las opciones aprobadas.

## ADDED Requirements

### Requirement: La sesión consulta su propia identidad y sus permisos efectivos
El sistema DEBE exponer una consulta de solo lectura de la sesión en curso que devuelva el usuario (identificador y nombre), la organización (identificador y nombre), el rol (identificador y nombre) y la lista de códigos de permiso vigentes del usuario, ordenada alfabéticamente y sin repetidos. La consulta DEBE exigir un access token válido y NO DEBE exigir ningún permiso en particular. NO DEBE escribir datos: no registra comandos ni auditoría. NO DEBE devolver secretos del usuario (contraseña, PIN de autorización, sal, iteraciones) ni el tope de descuento.

#### Scenario: Un usuario de Administración obtiene sus permisos ordenados
- **GIVEN** un usuario de la organización inicial con el rol Administración, cuya composición es la de la plantilla de `01` §19 (columna GES)
- **WHEN** consulta su propia sesión con su access token
- **THEN** obtiene su identificador y nombre, los de su organización y los de su rol
- **AND** obtiene exactamente los permisos de su rol, en orden alfabético, entre ellos `GESTIONAR_CATALOGO`, `GESTIONAR_PROVEEDORES`, `EDITAR_COSTOS` y `VER_COSTOS`, y no `GESTIONAR_DISPOSITIVOS`
- **Regla:** `01` §19; ADR-027

#### Scenario: Un usuario sin ningún permiso de administración igual obtiene su sesión
- **GIVEN** un usuario con el rol Vendedor/Repartidor, que no tiene ningún permiso de las pantallas de `/admin`
- **WHEN** consulta su propia sesión
- **THEN** la consulta responde con éxito, con sus datos y con los permisos de su rol (`VENDER`, `REGISTRAR_COBRANZA`, …)
- **AND** no se rechaza por falta de permiso
- **Regla:** ADR-027 (la consulta no exige ningún permiso); `01` §19

#### Scenario: Un rol sin permisos devuelve la lista vacía
- **GIVEN** un usuario cuyo rol quedó sin ningún permiso
- **WHEN** consulta su propia sesión
- **THEN** obtiene sus datos y una lista de permisos vacía, no un error
- **Regla:** ADR-027; `01` §19 (los roles son plantillas modificables)

#### Scenario: Sin access token la consulta se rechaza
- **GIVEN** una petición sin access token, o con un access token vencido o con la firma alterada
- **WHEN** consulta la sesión
- **THEN** se rechaza como no autenticada y no devuelve ningún dato
- **Regla:** SEG-06; `02` §12.1

#### Scenario: Un usuario dado de baja no obtiene su sesión (D9)
- **GIVEN** un usuario con un access token todavía vigente, que pasó a `INACTIVO` o cuyo rol se desactivó
- **WHEN** consulta su propia sesión
- **THEN** la consulta se rechaza como no autenticada (401, código según D9.2 de `design.md`) y no devuelve ningún dato
- **AND** nunca responde con éxito y una lista de permisos vacía
- **Regla:** ADR-028; ADR-017; SEG-06

#### Scenario: La respuesta no expone secretos
- **GIVEN** un supervisor con PIN de autorización definido
- **WHEN** consulta su propia sesión
- **THEN** la respuesta no contiene la contraseña, el PIN, su sal ni sus iteraciones, ni el tope de descuento
- **Regla:** `03` §4 (columnas de contraseña y PIN); ADR-019; `02` §12.4

#### Scenario: Consultar la sesión no escribe nada
- **GIVEN** un usuario autenticado
- **WHEN** consulta su propia sesión varias veces
- **THEN** no se registra ningún comando ni ninguna fila de auditoría
- **Regla:** ADR-027 (lectura, sin bus de comandos); ADR-022

### Requirement: Los permisos informados son los mismos con los que el servidor autoriza
La lista de permisos de la consulta de sesión DEBE salir de la misma fuente que usa el servidor para autorizar cada petición: los permisos vigentes del rol del usuario, leídos en el momento de la consulta y sin caché propia. No DEBE existir una segunda fuente de verdad. Por eso, un cambio en la composición del rol DEBE verse en la consulta siguiente, igual que en la autorización (ADR-017).

#### Scenario: Lo informado coincide con lo que el servidor autoriza
- **GIVEN** un usuario cuya consulta de sesión incluye `VER_COSTOS` y no incluye `GESTIONAR_DISPOSITIVOS`
- **WHEN** pide el costo vigente de un producto de su organización y después el listado de dispositivos
- **THEN** el costo vigente responde con éxito y el listado de dispositivos se rechaza con `PERMISO_REQUERIDO`
- **Regla:** SEG-06; ADR-027 (misma función que la autorización del servidor)

#### Scenario: Quitar un permiso al rol se refleja en la consulta siguiente
- **GIVEN** un usuario con sesión activa cuyo rol tiene `GESTIONAR_PROVEEDORES`
- **WHEN** se le quita ese permiso al rol y el usuario vuelve a consultar su sesión con el mismo access token
- **THEN** la lista ya no incluye `GESTIONAR_PROVEEDORES`
- **Regla:** ADR-017 (revocación inmediata con conexión); ADR-027

#### Scenario: Agregar un permiso al rol se refleja en la consulta siguiente
- **GIVEN** un usuario con sesión activa cuyo rol no tiene `GESTIONAR_DISPOSITIVOS`
- **WHEN** se le agrega ese permiso al rol y el usuario vuelve a consultar su sesión con el mismo access token
- **THEN** la lista incluye `GESTIONAR_DISPOSITIVOS`, sin volver a iniciar sesión
- **Regla:** ADR-017; ADR-027

### Requirement: La consulta de sesión solo muestra datos de la organización del token
El usuario y la organización de la consulta de sesión DEBEN salir siempre del access token. La consulta NO DEBE aceptar ningún identificador de usuario, organización o rol desde la ruta, la consulta, el cuerpo ni un encabezado. NO DEBE devolver datos de otra organización (INV-21, SEG-07). La ruta DEBE estar cubierta por la verificación de aislamiento que recorre todas las rutas de negocio.

#### Scenario: Dos organizaciones, cada usuario ve solo lo suyo
- **GIVEN** la organización A con un usuario de rol Administrador y la organización B con un usuario de rol Vendedor/Repartidor, cada uno con sesión iniciada con sus credenciales
- **WHEN** el usuario de B consulta su propia sesión
- **THEN** obtiene su usuario, la organización B y su rol de B, con los permisos de ese rol
- **AND** la respuesta no contiene ningún identificador, nombre ni permiso que provenga de la organización A
- **Regla:** INV-21; SEG-07

#### Scenario: Una organización o un usuario informados en la petición se ignoran
- **GIVEN** un usuario autenticado en la organización B
- **WHEN** consulta su sesión informando el identificador de la organización A o de un usuario de A en la consulta o en un encabezado
- **THEN** la respuesta es la misma que sin esos datos: su usuario y la organización B
- **Regla:** `02` §8 (`organizacion_id` se toma del token); INV-21

#### Scenario: La ruta forma parte de la cobertura de aislamiento
- **GIVEN** la verificación que recorre todas las rutas registradas
- **WHEN** se ejecuta con la consulta de sesión registrada
- **THEN** la ruta figura como cubierta por su prueba de aislamiento y la verificación pasa
- **AND** si se quitara de la cobertura, la verificación fallaría nombrando la ruta y el método
- **Regla:** INV-21; `02` §15

### Requirement: `/admin` obtiene los permisos de la consulta de sesión y los refresca en cada renovación del token
El área `/admin` DEBE obtener los permisos de la consulta de sesión una vez al iniciar sesión, y DEBE volver a consultarlos cada vez que se renueva el access token. Si la renovación falla, DEBE descartar los permisos que tenía. Esa consulta DEBE ser la única fuente de permisos de la interfaz: ni menú ni pantallas pueden deducir permisos de otra forma. Los permisos DEBEN vivir solo en memoria: NO DEBEN guardarse en `localStorage`, `sessionStorage` ni IndexedDB (ADR-017, ADR-027). El área `/ruta` NO DEBE usar esta consulta: sigue con los permisos del bootstrap (SYN-10, SYN-11).

#### Scenario: Una sola consulta por sesión mientras no se renueve el token
- **GIVEN** un usuario que acaba de iniciar sesión en `/admin`
- **WHEN** navega entre Catálogo, Proveedores y la ficha de un producto sin que se renueve el access token
- **THEN** la consulta de sesión se hizo una sola vez
- **AND** ninguna pantalla pide un dato solo para averiguar si el usuario tiene un permiso
- **Regla:** ADR-027 (un pedido por sesión y por renovación)

#### Scenario: Tras renovar el token, la interfaz refleja un permiso quitado
- **GIVEN** un usuario de Administración con la sesión abierta en `/admin`, al que se le quitó `GESTIONAR_PROVEEDORES` del rol
- **WHEN** su access token vence y la aplicación lo renueva
- **THEN** la consulta de sesión se repite y la entrada "Proveedores" desaparece del menú sin recargar la página
- **Regla:** ADR-027 (un permiso quitado deja de mostrarse en 15 minutos como máximo); `02` §12.1

#### Scenario: Si la renovación falla, los permisos se descartan
- **GIVEN** un usuario con la sesión abierta en `/admin`
- **WHEN** la renovación del access token es rechazada (refresh vencido o revocado)
- **THEN** los permisos en memoria se descartan y ninguna entrada ni acción protegida sigue visible con los permisos anteriores
- **Regla:** ADR-017; ADR-027

#### Scenario: Los permisos no quedan en el almacenamiento del navegador
- **GIVEN** un usuario que inició sesión en `/admin` y navegó por sus pantallas
- **WHEN** se inspeccionan `localStorage`, `sessionStorage` e IndexedDB
- **THEN** ninguno contiene la lista de permisos ni la respuesta de la consulta de sesión
- **Regla:** ADR-027 (los permisos viven en la caché en memoria, igual que el access token); ADR-017

### Requirement: El menú de `/admin` muestra solo las secciones que el usuario puede usar
El menú de `/admin` DEBE mostrar cada sección solo si el usuario tiene el permiso de esa sección en su consulta de sesión: Catálogo con `GESTIONAR_CATALOGO`, Proveedores con `GESTIONAR_PROVEEDORES` y Dispositivos con `GESTIONAR_DISPOSITIVOS`. Mientras la consulta está pendiente o si falla, NO DEBE mostrar ninguna sección protegida. Si falla, DEBE informar el error y ofrecer reintentar. Si falla porque la sesión terminó (renovación rechazada), DEBE ofrecer iniciar sesión **(B1)**. Tras iniciar sesión, `/admin` DEBE llevar a la primera sección permitida del menú. Si no hay ninguna, DEBE informar que el usuario no tiene secciones de administración disponibles **(B3)**. El encabezado DEBE mostrar el nombre del usuario, el de la organización y el del rol **(B4)**. Ocultar una sección es una comodidad: el servidor sigue validando cada petición (SEG-06).

#### Scenario: Administración ve Catálogo y Proveedores, no Dispositivos
- **GIVEN** un usuario con rol Administración (`GESTIONAR_CATALOGO`, `GESTIONAR_PROVEEDORES`, sin `GESTIONAR_DISPOSITIVOS`)
- **WHEN** inicia sesión en `/admin`
- **THEN** el menú muestra Catálogo y Proveedores, y no muestra Dispositivos
- **AND** llega a Catálogo, la primera sección permitida **(B3)**
- **Regla:** `01` §19; ADR-027

#### Scenario: Supervisor comercial ve solo Dispositivos
- **GIVEN** un usuario con rol Supervisor comercial (`GESTIONAR_DISPOSITIVOS`, sin `GESTIONAR_CATALOGO` ni `GESTIONAR_PROVEEDORES`)
- **WHEN** inicia sesión en `/admin`
- **THEN** el menú muestra solo Dispositivos y el usuario llega a esa sección
- **Regla:** `01` §19; ADR-027

#### Scenario: Un usuario sin secciones de administración
- **GIVEN** un usuario con rol Vendedor/Repartidor
- **WHEN** inicia sesión en `/admin`
- **THEN** el menú no muestra ninguna sección y la pantalla informa que no tiene secciones de administración disponibles **(B3)**
- **Regla:** `01` §19; ADR-027

#### Scenario: Mientras la consulta de sesión carga, no se muestran secciones protegidas
- **GIVEN** un usuario que acaba de iniciar sesión, con la consulta de sesión todavía pendiente
- **WHEN** se dibuja el menú
- **THEN** no aparece ninguna sección protegida hasta que llega la respuesta **(B1)**
- **Regla:** ADR-027; SEG-06

#### Scenario: Si la consulta de sesión falla, se informa y se puede reintentar
- **GIVEN** un usuario autenticado cuya consulta de sesión falla por un error del servidor o de red
- **WHEN** se dibuja el menú
- **THEN** no aparece ninguna sección protegida, la pantalla informa que no se pudieron obtener los permisos y ofrece reintentar **(B1)**
- **AND** al reintentar con éxito aparecen las secciones permitidas
- **Regla:** ADR-027

#### Scenario: Si la sesión terminó, se ofrece iniciar sesión
- **GIVEN** un usuario cuya consulta de sesión falla con 401 después de que la renovación del access token fue rechazada
- **WHEN** se dibuja el menú
- **THEN** no aparece ninguna sección protegida y la pantalla ofrece ir a iniciar sesión **(B1)**
- **Regla:** ADR-027; ADR-017

#### Scenario: El encabezado identifica la sesión
- **GIVEN** un usuario de Administración de la organización inicial
- **WHEN** entra a `/admin`
- **THEN** el encabezado muestra su nombre, el nombre de la organización y el nombre de su rol **(B4)**
- **Regla:** ADR-027 (la consulta devuelve usuario, organización y rol)

### Requirement: Las pantallas de `/admin` deciden qué mostrar solo con los permisos efectivos
Cada pantalla y cada acción de `/admin` que exige un permiso DEBE decidir si se muestra solo a partir de los permisos de la consulta de sesión, mediante un único mecanismo compartido. NO DEBE pedir un dato al servidor solo para averiguar si tiene permiso. Si el usuario llega por URL a una pantalla cuyo permiso no tiene, la pantalla DEBE mostrar que falta el permiso y NO DEBE pedir sus datos al servidor **(B2)**. Si el servidor igual rechaza una petición con `PERMISO_REQUERIDO` (por ejemplo, porque el permiso se quitó entre dos renovaciones), la pantalla DEBE mostrar que falta el permiso, sin datos y sin un error genérico (SEG-06).

#### Scenario: Entrar por URL a una pantalla sin permiso no consulta sus datos
- **GIVEN** un usuario con rol Administración, sin `GESTIONAR_DISPOSITIVOS`
- **WHEN** escribe en el navegador la dirección `/admin/dispositivos`
- **THEN** la pantalla muestra que no tiene permiso para gestionar dispositivos
- **AND** no se hace ninguna petición al listado de dispositivos **(B2)**
- **Regla:** ADR-027; `01` §19

#### Scenario: Con el permiso, la pantalla muestra sus datos y acciones
- **GIVEN** un usuario con rol Supervisor comercial (`GESTIONAR_DISPOSITIVOS`)
- **WHEN** entra a Dispositivos
- **THEN** ve el listado de dispositivos de su organización y la acción de revocar
- **Regla:** SEG-02; `01` §19

#### Scenario: Un 403 del servidor entre dos renovaciones se muestra como falta de permiso
- **GIVEN** un usuario cuya consulta de sesión todavía incluye `GESTIONAR_DISPOSITIVOS`, al que se le quitó ese permiso del rol antes de la próxima renovación del token
- **WHEN** abre Dispositivos y el servidor responde `PERMISO_REQUERIDO`
- **THEN** la pantalla muestra que no tiene permiso para gestionar dispositivos, sin listado y sin un error genérico
- **Regla:** SEG-06 (el servidor valida en cada petición); ADR-017; ADR-027

#### Scenario: Ocultar una acción no la protege
- **GIVEN** un usuario sin `GESTIONAR_DISPOSITIVOS`, al que la interfaz no le muestra la acción de revocar
- **WHEN** envía de todos modos, por fuera de la interfaz, la revocación de un dispositivo de su organización
- **THEN** el servidor la rechaza con `PERMISO_REQUERIDO` y el dispositivo sigue activo
- **Regla:** SEG-06
