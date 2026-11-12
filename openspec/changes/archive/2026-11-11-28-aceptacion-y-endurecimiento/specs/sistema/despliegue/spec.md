## MODIFIED Requirements

### Requirement: Solo el proxy queda expuesto a la red

El entorno de producción DEBE componerse de los servicios `caddy`, `backend`, `postgres`, `migraciones`, `backup`, `copia-externa`, `prueba-restauracion` y `tareas`, más el servicio `restauracion`, que solo se ejecuta a pedido y no arranca con el entorno. Solo `caddy` DEBE publicar puertos en el servidor (80 y 443). `postgres` y `backend` NO DEBEN publicar puertos; el backend DEBE ser alcanzable solo desde `caddy` y la base solo desde `backend`, `migraciones`, `backup`, `restauracion` y `tareas`. `tareas` DEBE estar solo en la red interna de datos, salvo que se configure el aviso externo. `copia-externa` DEBE tener salida a internet sin acceso a la red de la base, y `prueba-restauracion` NO DEBE tener red (`02` §16.2; `design.md` D3, D5 del 27a; D4, D8, D10 del 27b; D2 del 28).

#### Scenario: La base no es alcanzable desde afuera
- **GIVEN** el entorno de producción levantado
- **WHEN** se intenta conectar al puerto 5432 o al 8000 del servidor desde otra máquina
- **THEN** la conexión es rechazada; solo 80 y 443 responden
- **Regla:** `02` §16.2 («puerto no expuesto»); `02` §18

#### Scenario: El compose de producción no publica la base ni el backend
- **GIVEN** el archivo del compose de producción
- **WHEN** se inspeccionan los servicios
- **THEN** solo `caddy` declara `ports`, y `backend` no comparte red con nadie más que `caddy` y la red de datos
- **Regla:** `02` §16.2; `design.md` D3 del 27a

#### Scenario: Los servicios nuevos de respaldo no amplían la exposición
- **GIVEN** el archivo del compose de producción
- **WHEN** se inspeccionan `copia-externa`, `prueba-restauracion` y `restauracion`
- **THEN** ninguno declara `ports`; `copia-externa` está solo en la red de salida; `prueba-restauracion` no tiene red; `restauracion` está en un perfil que `up` no arranca
- **Regla:** `design.md` D4, D8, D10

#### Scenario: El servicio de tareas no amplía la exposición
- **GIVEN** el archivo del compose de producción
- **WHEN** se inspecciona `tareas`
- **THEN** no declara `ports`, está en la red de datos y en la de salida (solo saliente, para el aviso externo; `datos` sigue `internal`), declara salud, `restart` y la rotación de registros
- **Regla:** `02` §16.2; `design.md` D2 del 28; ADR-073

### Requirement: Cada servicio usa solo el rol de base que le corresponde

El backend DEBE conectarse solo como `app_runtime` y NO DEBE recibir la conexión de `app_migrations`. Las migraciones DEBEN correr como `app_migrations` en un servicio aparte que termina al aplicarlas. El backup DEBE conectarse con un rol de solo lectura. La restauración DEBE conectarse como `app_migrations`, dueño del esquema. `tareas` DEBE conectarse solo como `app_mantenimiento`. `copia-externa` y `prueba-restauracion` NO DEBEN recibir ninguna credencial de la base de producción. Ninguno DEBE usar el superusuario de Postgres (INV-05; ADR-018; ADR-020; `02` §18; `design.md` D7, D11 del 27a; D4, D8, D10 del 27b; D3 del 28).

#### Scenario: El backend no conoce la conexión de migraciones
- **GIVEN** el compose de producción
- **WHEN** se inspecciona el entorno del servicio `backend`
- **THEN** tiene `DATABASE_URL` con `app_runtime` y no tiene `DATABASE_URL_MIGRATIONS`
- **Regla:** INV-05; ADR-020

#### Scenario: La aplicación sigue sin borrar libros
- **GIVEN** el entorno de producción migrado
- **WHEN** el rol `app_runtime` intenta `DELETE` sobre `auditoria`
- **THEN** PostgreSQL lo rechaza por falta de permiso
- **Regla:** INV-05

#### Scenario: Roles de los servicios de respaldo
- **GIVEN** el compose de producción
- **WHEN** se inspecciona el entorno de `restauracion`, `copia-externa` y `prueba-restauracion`
- **THEN** `restauracion` se conecta como `app_migrations` y los otros dos no tienen ninguna variable de conexión a la base ni la contraseña de ningún rol
- **Regla:** INV-05; ADR-020; `design.md` D4, D8, D10

#### Scenario: El servicio de tareas usa su propio rol
- **GIVEN** el compose de producción
- **WHEN** se inspecciona el entorno de `tareas`
- **THEN** se conecta como `app_mantenimiento` y no tiene la contraseña de `app_runtime`, de `app_migrations` ni del superusuario
- **Regla:** ADR-018 (limpieza con un rol distinto de `app_runtime`); ADR-020; `design.md` D3 del 28

## ADDED Requirements

### Requirement: Encabezados de seguridad y política de contenido en todas las respuestas

`caddy` DEBE enviar en toda respuesta HTTPS, tanto de la aplicación como de `/api/*`, una política de seguridad de contenido restrictiva (solo recursos del mismo origen, sin scripts en línea ni `eval`, sin objetos incrustados, sin ser incrustada en marcos de otros sitios) y los encabezados `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` y `Cross-Origin-Opener-Policy`, además del HSTS existente, y NO DEBE anunciar su nombre en `Server`. Los mismos encabezados DEBEN aplicarse en el perfil `lan` de desarrollo. La aplicación DEBE funcionar completa con la política aplicada, incluidas la instalación, el service worker, la nota de venta y la descarga de archivos (`02` §18; ADR-071 punto 3; `design.md` D8, D9).

#### Scenario: La política de contenido llega con la aplicación
- **GIVEN** el entorno levantado
- **WHEN** se pide `https://{DOMINIO}/` y `https://{DOMINIO}/api/v1/salud`
- **THEN** las dos respuestas traen `Content-Security-Policy` con `default-src 'self'`, `script-src 'self'`, `object-src 'none'` y `frame-ancestors 'none'`, sin `unsafe-eval`
- **Regla:** `02` §18 (encabezados de seguridad, CSP restrictiva)

#### Scenario: Encabezados complementarios
- **GIVEN** el entorno levantado
- **WHEN** se pide `https://{DOMINIO}/admin`
- **THEN** la respuesta trae `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` y `Strict-Transport-Security`, y no trae `Server: Caddy`
- **Regla:** `02` §18

#### Scenario: El Caddyfile de producción y el de desarrollo comparten los encabezados
- **GIVEN** los dos Caddyfile
- **WHEN** se validan y se inspeccionan
- **THEN** los dos importan la misma definición de encabezados
- **Regla:** `design.md` D8

#### Scenario: La nota de venta funciona con la política aplicada
- **GIVEN** el entorno levantado con la política aplicada
- **WHEN** se genera y se descarga una nota de venta
- **THEN** el PDF se genera sin violaciones de la política en la consola
- **Regla:** `02` §18; `design.md` D9

### Requirement: El rol de mantenimiento se crea en un entorno nuevo y en uno existente

Un volumen de datos nuevo DEBE crear `app_mantenimiento` al inicializarse, con contraseña obligatoria del archivo de entorno sin valor por defecto. Para un entorno ya en uso, el runbook DEBE traer los pasos para crear el rol antes de migrar. La migración que le otorga permisos DEBE fallar con un mensaje que nombra el paso del runbook si el rol no existe (`CLAUDE.md` §4; `design.md` D3).

#### Scenario: Falta la contraseña del rol de mantenimiento
- **GIVEN** el archivo de entorno sin la contraseña de `app_mantenimiento`
- **WHEN** se levanta el compose de producción
- **THEN** no se levanta ningún servicio y el error nombra la variable
- **Regla:** `CLAUDE.md` §4

#### Scenario: Migrar sin el rol creado
- **GIVEN** un entorno existente donde todavía no se creó `app_mantenimiento`
- **WHEN** corre `migraciones`
- **THEN** la migración falla con un mensaje que nombra el rol y el paso del runbook, y la base queda como estaba
- **Regla:** `design.md` D3; INV-01
