# sistema/aplicacion-instalable Specification

## Purpose
Hace que la aplicación se instale en el teléfono y abra sin conexión: un service worker precachea el shell del área de ruta, la ayuda y el generador de la nota, nunca guarda respuestas de la API, se actualiza con aviso y pide almacenamiento persistente para que el navegador no borre los datos locales (`02` §13.3, §13.5, ADR-001).

## Requirements

### Requirement: La aplicación de ruta abre sin conexión

El service worker DEBE precachear el shell de la aplicación, el código del área `/ruta`, los textos y páginas de ayuda y el fragmento de pdfmake con sus fuentes, de modo que `/ruta` y sus subrutas abran sin conexión tras una primera visita con conexión. El código del área `/admin` NO DEBE precachearse (`design.md` D17).

#### Scenario: Abrir sin señal
- **GIVEN** una visita previa a `/ruta` con conexión
- **WHEN** el teléfono sin señal abre `/ruta/clientes`
- **THEN** la aplicación carga y pide el PIN
- **Regla:** `02` §13.5

#### Scenario: El generador de la nota está disponible sin señal
- **GIVEN** una visita previa con conexión
- **WHEN** sin señal se carga el fragmento de pdfmake
- **THEN** se obtiene del precache sin pedirlo a la red
- **Regla:** VTA-13; ADR-059

#### Scenario: Administración no se descarga en el teléfono
- **WHEN** se instala el service worker
- **THEN** el precache no incluye el código del área `/admin`
- **Regla:** `02` §13.1

### Requirement: El service worker no guarda respuestas de la API

Ninguna petición a `/api/` DEBE responderse desde una caché del service worker ni guardarse en ella; la navegación a `/api/` NO DEBE recibir el shell como respuesta.

#### Scenario: API sin señal
- **GIVEN** el teléfono sin señal
- **WHEN** la aplicación pide `GET /api/v1/sync/bootstrap`
- **THEN** la petición falla como error de red y no hay respuesta guardada
- **Regla:** `02` §13.5

### Requirement: Una versión nueva se aplica con aviso

Cuando hay una versión nueva, DEBE instalarse en segundo plano y mostrarse un aviso "Hay una versión nueva" con "Actualizar". La aplicación NO DEBE recargarse sola; al tocar "Actualizar" se activa la versión nueva y se recarga (`design.md` D17).

#### Scenario: Versión nueva
- **GIVEN** la aplicación abierta y una versión nueva publicada
- **WHEN** el service worker la detecta
- **THEN** aparece el aviso y la pantalla actual no se recarga hasta que el usuario toca "Actualizar"
- **Regla:** `02` §13.5

### Requirement: Se pide almacenamiento persistente

Tras el primer bootstrap aplicado y en cada arranque mientras no esté concedido, `/ruta` DEBE pedir almacenamiento persistente al navegador. Si lo niega o no lo admite, el inicio DEBE mostrar una advertencia permanente con su ayuda; si lo concede, no DEBE mostrar nada (`design.md` D18).

#### Scenario: Concedido
- **GIVEN** un navegador que concede el almacenamiento persistente
- **WHEN** se aplica el primer bootstrap
- **THEN** no se muestra advertencia
- **Regla:** `02` §13.3; `00` §11

#### Scenario: Negado
- **GIVEN** un navegador que lo niega
- **WHEN** se muestra el inicio
- **THEN** aparece la advertencia de que el navegador puede borrar los datos, con su "(?)"
- **Regla:** `02` §13.3; `00` §11

### Requirement: La aplicación es instalable

La aplicación DEBE publicar un manifiesto con nombre, íconos, color, `display: standalone` y `start_url` `/ruta`, para instalarse en la pantalla de inicio del teléfono.

#### Scenario: Instalar en el teléfono
- **WHEN** el vendedor elige "Agregar a la pantalla de inicio"
- **THEN** la aplicación se instala y abre en `/ruta` sin barra del navegador
- **Regla:** ADR-001; `design.md` D17
