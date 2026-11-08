# Sistema - Despliegue

## Purpose

Define cómo se levanta el sistema en producción con Docker Compose, en una PC de la oficina o en un servidor con dominio, con el mismo compose: qué servicios existen y qué expone cada uno, HTTPS, manejo de secretos, migraciones al desplegar, la primera puesta en marcha y la actualización a una versión nueva (`02` §16.2, §18; `04` §10).

## Requirements

### Requirement: Solo el proxy queda expuesto a la red

El entorno de producción DEBE componerse de los servicios `caddy`, `backend`, `postgres`, `migraciones` y `backup`. Solo `caddy` DEBE publicar puertos en el servidor (80 y 443). `postgres` y `backend` NO DEBEN publicar puertos; el backend DEBE ser alcanzable solo desde `caddy` y la base solo desde `backend`, `migraciones` y `backup` (`02` §16.2; `design.md` D3, D5).

#### Scenario: La base no es alcanzable desde afuera
- **GIVEN** el entorno de producción levantado
- **WHEN** se intenta conectar al puerto 5432 o al 8000 del servidor desde otra máquina
- **THEN** la conexión es rechazada; solo 80 y 443 responden
- **Regla:** `02` §16.2 («puerto no expuesto»); `02` §18

#### Scenario: El compose de producción no publica la base ni el backend
- **GIVEN** el archivo del compose de producción
- **WHEN** se inspeccionan los servicios
- **THEN** solo `caddy` declara `ports`, y `backend` no comparte red con nadie más que `caddy` y la red de datos
- **Regla:** `02` §16.2; `design.md` D3

### Requirement: HTTPS obligatorio con el mismo origen

`caddy` DEBE atender el `DOMINIO` configurado (dominio, IP de la red local o `localhost`) solo por HTTPS, con el emisor del certificado elegido por el archivo de entorno (`CADDY_TLS`: la autoridad propia de Caddy, o Let's Encrypt con obtención y renovación automáticas) sin cambiar el código ni el Caddyfile, redirigir HTTP a HTTPS y enviar `Strict-Transport-Security`. DEBE servir la compilación de producción del frontend y reenviar `/api/*` al backend en el mismo origen, sin CORS. El service worker, el manifiesto, `registerSW.js` e `index.html` DEBEN servirse con `Cache-Control: no-cache`, y toda ruta del frontend que no sea un archivo DEBE devolver `index.html` (`02` §11, §18; ADR-062; `design.md` D1, D2, D4).

#### Scenario: El emisor del certificado se elige con el archivo de entorno
- **GIVEN** el Caddyfile de producción
- **WHEN** se valida con `CADDY_TLS=internal` y, por separado, con `CADDY_TLS` igual a un correo
- **THEN** las dos configuraciones son válidas; con `internal` el certificado lo emite la autoridad propia de Caddy, y con un correo se pide a Let's Encrypt (ACME) con ese correo
- **Regla:** `design.md` D1, D2

#### Scenario: La PC de la oficina sirve por HTTPS a un teléfono que confía en Caddy
- **GIVEN** el entorno levantado en la PC de la oficina con `DOMINIO` igual a su IP fija y `CADDY_TLS=internal`, y un teléfono en la misma red con el certificado raíz de Caddy instalado y marcado como confiable
- **WHEN** el teléfono abre `https://{DOMINIO}/ruta`
- **THEN** la aplicación carga sin aviso de certificado
- **Regla:** `design.md` D1; ADR-062

#### Scenario: HTTP redirige a HTTPS
- **GIVEN** el entorno levantado con `DOMINIO` configurado
- **WHEN** se pide `http://{DOMINIO}/admin`
- **THEN** la respuesta redirige a `https://{DOMINIO}/admin`
- **Regla:** `02` §18 (HTTPS obligatorio)

#### Scenario: HSTS en las respuestas HTTPS
- **GIVEN** el entorno levantado
- **WHEN** se pide `https://{DOMINIO}/`
- **THEN** la respuesta trae `Strict-Transport-Security` con `max-age` de al menos un año
- **Regla:** `02` §18 (HSTS)

#### Scenario: La API responde en el mismo origen
- **GIVEN** el entorno levantado y migrado
- **WHEN** se pide `https://{DOMINIO}/api/v1/salud`
- **THEN** responde 200 desde el backend, sin encabezados de CORS abiertos
- **Regla:** `02` §11; `02` §17

#### Scenario: Una ruta de la aplicación recarga sin error
- **GIVEN** el entorno levantado
- **WHEN** se pide `https://{DOMINIO}/ruta/sincronizacion` directamente
- **THEN** responde 200 con `index.html`
- **Regla:** ADR-062

#### Scenario: El service worker no queda en caché
- **GIVEN** el entorno levantado
- **WHEN** se pide `https://{DOMINIO}/sw.js`
- **THEN** la respuesta trae `Cache-Control: no-cache`
- **Regla:** ADR-062; `design.md` D4

### Requirement: Los secretos no tienen valor por defecto ni viven en el repositorio

El entorno de producción DEBE leer todos los secretos (contraseña del superusuario de Postgres, de `app_migrations`, de `app_runtime`, del rol de backup y `JWT_SECRET`) de un archivo de entorno fuera del repositorio. Ningún secreto DEBE tener valor por defecto: si falta, el compose DEBE negarse a levantar con un mensaje que nombra la variable. El repositorio DEBE incluir solo una plantilla sin valores (`02` §16.2; `CLAUDE.md` §4; `design.md` D8).

#### Scenario: Falta un secreto
- **GIVEN** el archivo de entorno sin `JWT_SECRET`
- **WHEN** se levanta el compose de producción
- **THEN** no se levanta ningún servicio y el error nombra `JWT_SECRET`
- **Regla:** `02` §16.2; `CLAUDE.md` §4

#### Scenario: La plantilla no trae valores
- **GIVEN** la plantilla de entorno versionada
- **WHEN** se lee
- **THEN** cada secreto aparece sin valor
- **Regla:** `02` §16.2

### Requirement: El backend de producción valida su configuración al arrancar

Con `ENVIRONMENT=production`, el backend DEBE negarse a arrancar si `JWT_SECRET` tiene menos de 32 caracteres o si `APP_VERSION` no tiene la forma `X.Y.Z`, con un error que nombra la variable y nunca muestra su valor. Fuera de producción esta validación NO DEBE aplicarse (`02` §6.6, §17; `design.md` D6).

#### Scenario: Secreto corto en producción
- **GIVEN** `ENVIRONMENT=production` y un `JWT_SECRET` de 20 caracteres
- **WHEN** arranca el backend
- **THEN** falla al leer la configuración; el error nombra `JWT_SECRET` y no incluye su valor
- **Regla:** `02` §17 (nunca se registran secretos); `design.md` D6

#### Scenario: Versión sin formato en producción
- **GIVEN** `ENVIRONMENT=production` y `APP_VERSION=dev`
- **WHEN** arranca el backend
- **THEN** falla nombrando `APP_VERSION`
- **Regla:** `02` §6.6 (versión mínima de aplicación)

#### Scenario: En desarrollo no se valida
- **GIVEN** `ENVIRONMENT=development`, `APP_VERSION=dev` y un `JWT_SECRET` corto
- **WHEN** arranca el backend
- **THEN** arranca como hasta ahora
- **Regla:** `design.md` D6

### Requirement: Cada servicio usa solo el rol de base que le corresponde

El backend DEBE conectarse solo como `app_runtime` y NO DEBE recibir la conexión de `app_migrations`. Las migraciones DEBEN correr como `app_migrations` en un servicio aparte que termina al aplicarlas. El backup DEBE conectarse con un rol de solo lectura. Ninguno de los tres DEBE usar el superusuario de Postgres (INV-05; ADR-020; `02` §18; `design.md` D7, D11).

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

### Requirement: Las migraciones corren antes de la nueva versión del backend

Al levantar o actualizar el entorno, las migraciones DEBEN aplicarse antes de iniciar el backend; si fallan, el backend NO DEBE iniciar con la versión nueva y el error DEBE quedar en los registros del servicio de migraciones (`02` §14, §16.2; `design.md` D7, D15).

#### Scenario: Primera vez
- **GIVEN** una base vacía con los roles creados
- **WHEN** se levanta el entorno
- **THEN** `migraciones` aplica todas las migraciones y termina con éxito, y recién entonces arranca `backend`
- **Regla:** `02` §16.2

#### Scenario: Una migración falla
- **GIVEN** una versión cuya migración falla
- **WHEN** se actualiza el entorno
- **THEN** `migraciones` termina con error, `backend` no inicia con la versión nueva y el error se ve en `docker compose logs migraciones`
- **Regla:** `02` §16.2; `design.md` D15

### Requirement: El backend ve la IP real del cliente

Detrás de `caddy`, el backend DEBE tomar la IP del cliente del encabezado reenviado por `caddy` y confiar en ese encabezado solo cuando la conexión viene de la red del proxy, para que el límite de intentos por IP del login y de «Mi PIN» cuente por cliente y no por proxy (ADR-018 punto 5; ADR-057; `02` §18; `design.md` D5).

#### Scenario: Dos clientes distintos no comparten el límite por IP
- **GIVEN** el entorno de producción y dos clientes con IP distintas
- **WHEN** el primero agota 20 intentos fallidos de login
- **THEN** el segundo todavía puede intentar; el registro de `intento_login` guarda la IP de cada cliente, no la de `caddy`
- **Regla:** ADR-018 (límite por IP, 20); ADR-057

#### Scenario: Un encabezado falsificado desde afuera no cambia la IP
- **GIVEN** un cliente que envía su propio `X-Forwarded-For` con otra IP
- **WHEN** pide `POST /api/v1/auth/login`
- **THEN** el backend registra la IP real de ese cliente
- **Regla:** ADR-018; `design.md` D5

### Requirement: Los servicios se recuperan solos y sus registros no llenan el disco

Los servicios de larga vida DEBEN reiniciarse solos tras una caída o un reinicio del servidor, declarar una verificación de salud y rotar sus registros con un tamaño máximo. `backend` DEBE iniciar solo con `postgres` sano y `caddy` solo con `backend` sano (`02` §17; `design.md` D14).

#### Scenario: Reinicio del servidor
- **GIVEN** el entorno levantado
- **WHEN** se reinicia el servidor
- **THEN** los servicios vuelven a estar sanos sin intervención y `https://{DOMINIO}/api/v1/salud` responde 200
- **Regla:** `02` §17

#### Scenario: Registros acotados
- **GIVEN** el compose de producción
- **WHEN** se inspecciona cada servicio
- **THEN** todos declaran rotación de registros con tamaño y cantidad de archivos máximos
- **Regla:** `design.md` D14

### Requirement: Primera puesta en marcha documentada

El repositorio DEBE incluir un runbook de primera puesta en marcha, con la jerga explicada, que lleve, desde un equipo con Docker, hasta un administrador que entra por HTTPS, en dos escenarios: una PC de la oficina con Windows y Docker Desktop (inicio automático, sin suspensión, IP fija, firewall, certificado raíz de Caddy en los teléfonos Android e iPhone, y la limitación de la red local) y un servidor Linux con dominio (requisitos del servidor y del dominio). En ambos: archivo de entorno y generación de secretos, levantar el entorno, sembrar la organización inicial con la contraseña del administrador pedida sin quedar en el historial, primer ingreso, verificación del primer backup, y la actualización a una versión nueva. La siembra repetida NO DEBE crear otra organización ni pisar la contraseña existente (`04` §10; `design.md` D1, D9, D15, D16).

#### Scenario: Primer ingreso del administrador
- **GIVEN** el entorno recién levantado y la siembra corrida con una contraseña
- **WHEN** el administrador entra a `https://{DOMINIO}/admin` con la organización `organizacion-inicial`, el usuario `admin` y esa contraseña
- **THEN** entra y puede crear usuarios y asignar clientes (changes 20 y 20b)
- **Regla:** `04` §4 (27a depende de 20 y 20b); `design.md` D9

#### Scenario: Siembra repetida
- **GIVEN** una organización ya sembrada
- **WHEN** se vuelve a correr la siembra con otra contraseña
- **THEN** no se crea otra organización y la contraseña del administrador no cambia
- **Regla:** `design.md` D9 (comportamiento existente de la siembra)

### Requirement: Actualización a una versión nueva

Actualizar el entorno DEBE hacer un backup antes de cambiar nada, construir las imágenes de la versión nueva, aplicar las migraciones con `run --rm migraciones` (mientras el backend viejo sigue atendiendo) y, solo si terminaron bien, reemplazar backend y `caddy` sin borrar los volúmenes de datos. La versión de la compilación del frontend y la del backend DEBEN ser la misma `APP_VERSION` (`02` §6.6, §14; `design.md` D15).

#### Scenario: Actualizar conserva los datos
- **GIVEN** el entorno con datos de prueba y `APP_VERSION=0.27.0`
- **WHEN** se actualiza a `APP_VERSION=0.27.1` siguiendo el runbook
- **THEN** los datos siguen, existe un backup previo a la actualización y `GET /api/v1/version` informa `0.27.1`
- **Regla:** `02` §14 (migraciones compatibles hacia adelante); `02` §6.6

#### Scenario: Una migración fallida no reemplaza la versión en servicio
- **GIVEN** el entorno funcionando en `0.27.1`
- **WHEN** se actualiza siguiendo el runbook y `run --rm migraciones` termina con error
- **THEN** el runbook indica no ejecutar `up -d`, el backend viejo sigue atendiendo y `GET /api/v1/version` sigue informando `0.27.1`
- **Regla:** `design.md` D15 (hallazgo del ensayo, paso 18)
