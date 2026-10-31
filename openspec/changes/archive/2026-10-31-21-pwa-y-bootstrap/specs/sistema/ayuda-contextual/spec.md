## ADDED Requirements

### Requirement: El área de ruta tiene su ayuda sin conexión

`/ruta` DEBE montar el índice de ayuda en `/ruta/ayuda` y las páginas de tema en `/ruta/ayuda/:tema` con la misma página de tema de `/admin`, disponibles sin conexión (precacheadas). Dentro de `/ruta`, "Ver más" DEBE navegar a la página interna en la misma ventana. En `/admin`, cuando la aplicación corre instalada (modo `standalone`), "Ver más" DEBE navegar a la ruta interna en lugar de abrir otra pestaña; en el navegador sigue abriendo otra pestaña (`design.md` D21).

#### Scenario: Ver más en ruta sin señal
- **GIVEN** el teléfono sin señal y una visita previa con conexión
- **WHEN** el vendedor toca "Ver más" en un "(?)" de `/ruta`
- **THEN** se abre `/ruta/ayuda/<tema>` en la misma ventana con el texto completo
- **Regla:** ADR-051

#### Scenario: Ver más en la aplicación instalada
- **GIVEN** la aplicación instalada abierta en `/admin`
- **WHEN** se toca "Ver más"
- **THEN** navega a `/admin/ayuda/<tema>` en la misma ventana
- **Regla:** ADR-051

### Requirement: Las pantallas de ruta explican el PIN, los datos del día, el almacenamiento y la cartera

Las pantallas de `/ruta` DEBEN ofrecer ayuda en el PIN de desbloqueo, en la fecha de los datos y "Actualizar datos", en la advertencia de almacenamiento y en la lista de clientes (cartera). La apertura de la jornada DEBE reutilizar la clave de ayuda existente de la toma de ubicación. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D21).

#### Scenario: PIN de desbloqueo
- **WHEN** se abre el "(?)" del PIN
- **THEN** explica que abre la aplicación en ese teléfono con o sin señal, que no es la contraseña ni viaja al servidor, y qué pasa al superar los intentos sin perder lo pendiente
- **Regla:** SEG-03; SEG-04; ADR-011

#### Scenario: Datos del día
- **WHEN** se abre el "(?)" de la fecha de los datos
- **THEN** explica que los datos se descargan al abrir la jornada, que se ven los de ese momento hasta actualizarlos y que actualizar requiere conexión y no toca lo pendiente
- **Regla:** SYN-11; ADR-006

#### Scenario: Almacenamiento
- **WHEN** se abre el "(?)" de la advertencia de almacenamiento
- **THEN** explica que el navegador puede borrar los datos y qué hacer
- **Regla:** `02` §13.3

#### Scenario: Cartera
- **WHEN** se abre el "(?)" de la lista de clientes
- **THEN** explica que primero aparecen los clientes asignados y que se puede buscar y vender a cualquiera
- **Regla:** `01` §19; ADR-060

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
