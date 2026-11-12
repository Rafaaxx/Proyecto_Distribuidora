## MODIFIED Requirements

### Requirement: Solo el proxy queda expuesto a la red

El entorno de producción DEBE componerse de los servicios `caddy`, `backend`, `postgres`, `migraciones`, `backup`, `copia-externa` y `prueba-restauracion`, más el servicio `restauracion`, que solo se ejecuta a pedido y no arranca con el entorno. Solo `caddy` DEBE publicar puertos en el servidor (80 y 443). `postgres` y `backend` NO DEBEN publicar puertos; el backend DEBE ser alcanzable solo desde `caddy` y la base solo desde `backend`, `migraciones`, `backup` y `restauracion`. `copia-externa` DEBE tener salida a internet sin acceso a la red de la base, y `prueba-restauracion` NO DEBE tener red (`02` §16.2; `design.md` D3, D5 del 27a; D4, D8, D10 del 27b).

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

### Requirement: Los secretos no tienen valor por defecto ni viven en el repositorio

El entorno de producción DEBE leer todos los secretos (contraseña del superusuario de Postgres, de `app_migrations`, de `app_runtime`, del rol de backup, `JWT_SECRET`, las credenciales de acceso al almacenamiento externo y la clave y la sal de cifrado de la copia externa) de un archivo de entorno fuera del repositorio. Ningún secreto DEBE tener valor por defecto: si falta, el compose DEBE negarse a levantar con un mensaje que nombra la variable. El repositorio DEBE incluir solo una plantilla sin valores (`02` §16.2; `CLAUDE.md` §4; `design.md` D8 del 27a; D5, D7 del 27b).

#### Scenario: Falta un secreto
- **GIVEN** el archivo de entorno sin `JWT_SECRET`
- **WHEN** se levanta el compose de producción
- **THEN** no se levanta ningún servicio y el error nombra `JWT_SECRET`
- **Regla:** `02` §16.2; `CLAUDE.md` §4

#### Scenario: Falta la clave de cifrado de la copia externa
- **GIVEN** el archivo de entorno sin la clave de cifrado de la copia externa
- **WHEN** se levanta el compose de producción
- **THEN** no se levanta ningún servicio y el error nombra esa variable
- **Regla:** `design.md` D5

#### Scenario: La plantilla no trae valores
- **GIVEN** la plantilla de entorno versionada
- **WHEN** se lee
- **THEN** cada secreto aparece sin valor
- **Regla:** `02` §16.2

### Requirement: Cada servicio usa solo el rol de base que le corresponde

El backend DEBE conectarse solo como `app_runtime` y NO DEBE recibir la conexión de `app_migrations`. Las migraciones DEBEN correr como `app_migrations` en un servicio aparte que termina al aplicarlas. El backup DEBE conectarse con un rol de solo lectura. La restauración DEBE conectarse como `app_migrations`, dueño del esquema. `copia-externa` y `prueba-restauracion` NO DEBEN recibir ninguna credencial de la base de producción. Ninguno DEBE usar el superusuario de Postgres (INV-05; ADR-020; `02` §18; `design.md` D7, D11 del 27a; D4, D8, D10 del 27b).

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

### Requirement: Primera puesta en marcha documentada

El repositorio DEBE incluir un runbook de primera puesta en marcha, con la jerga explicada, que lleve, desde un equipo con Docker, hasta un administrador que entra por HTTPS, en dos escenarios: una PC de la oficina con Windows y Docker Desktop (inicio automático, sin suspensión, IP fija, firewall, certificado raíz de Caddy en los teléfonos Android e iPhone, y la limitación de la red local) y un servidor Linux con dominio (requisitos del servidor y del dominio, y el dueño de la carpeta de backups). En ambos: archivo de entorno y generación de secretos, configuración de la copia externa (cuenta, acceso limitado, clave de cifrado y su custodia fuera del equipo), levantar el entorno, sembrar la organización inicial con la contraseña del administrador pedida sin quedar en el historial, primer ingreso, verificación del primer backup y de su primera copia externa, la revisión periódica de la salud y la actualización a una versión nueva. El repositorio DEBE incluir además un runbook de restauración. La siembra repetida NO DEBE crear otra organización ni pisar la contraseña existente (`04` §10, §12; `design.md` D1, D9, D15, D16 del 27a; D7, D15 del 27b).

#### Scenario: Primer ingreso del administrador
- **GIVEN** el entorno recién levantado y la siembra corrida con una contraseña
- **WHEN** el administrador entra a `https://{DOMINIO}/admin` con la organización `organizacion-inicial`, el usuario `admin` y esa contraseña
- **THEN** entra y puede crear usuarios y asignar clientes (changes 20 y 20b)
- **Regla:** `04` §4 (27a depende de 20 y 20b); `design.md` D9 del 27a

#### Scenario: Siembra repetida
- **GIVEN** una organización ya sembrada
- **WHEN** se vuelve a correr la siembra con otra contraseña
- **THEN** no se crea otra organización y la contraseña del administrador no cambia
- **Regla:** `design.md` D9 del 27a (comportamiento existente de la siembra)

#### Scenario: Restaurar con solo la hoja de recuperación
- **GIVEN** la copia externa con backups y la hoja de recuperación guardada fuera del equipo
- **WHEN** se sigue el runbook de restauración en un entorno separado, sin usar nada de la PC
- **THEN** se baja, descifra y restaura el backup más reciente y la comprobación dice que los datos coinciden
- **Regla:** `00` §9 criterio 12; `design.md` D7, D15

## ADDED Requirements

### Requirement: Mudanza de los datos a otro equipo

El runbook de restauración DEBE describir cómo llevar los datos de un equipo a otro (por ejemplo, de la PC de la oficina a un VPS) restaurando un backup en el equipo nuevo recién instalado sin sembrar: antes, cada teléfono DEBE quedar con la cola de sincronización vacía (la cola pertenece a la dirección vieja y no se ve desde la nueva) y el backend del equipo viejo detenido; después, la restauración DEBE comprobarse como cualquier otra y el equipo viejo DEBE conservarse sin borrar como vuelta atrás (`04`, cierre del 27a; `design.md` D12).

#### Scenario: Mudanza sin pérdida
- **GIVEN** el entorno en la PC con datos, todos los teléfonos con la cola vacía y el backend de la PC detenido
- **WHEN** se hace un backup a pedido, se restaura en un entorno nuevo siguiendo el runbook y se corren las migraciones
- **THEN** la comprobación dice que los datos coinciden, los saldos de clientes y el stock que muestra `/admin` son los mismos que en la PC, y el administrador entra al entorno nuevo
- **Regla:** `00` §9 criterio 12; `design.md` D12

#### Scenario: Teléfono con operaciones sin sincronizar
- **GIVEN** un teléfono con ventas en la cola
- **WHEN** se sigue el runbook de mudanza
- **THEN** el runbook indica no continuar hasta que ese teléfono sincronice y su cola quede vacía
- **Regla:** `design.md` D12; ADR-063
