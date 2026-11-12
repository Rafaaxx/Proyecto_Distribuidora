## ADDED Requirements

### Requirement: Los parámetros de la nota de venta se definen por comando

Un usuario con `ADMIN_CONFIGURACION` DEBE poder definir, con conexión, si la nota de venta muestra el saldo (por defecto no) y el domicilio y el teléfono de la organización que imprime la nota (opcionales; un texto vacío o solo de espacios queda vacío), mediante el comando `NOTA_VENTA_CONFIGURAR` v1 con `operation_id`, por `POST /api/v1/configuracion/nota-de-venta`, auditado con el valor anterior y el nuevo. Un domicilio de más de 200 caracteres o un teléfono de más de 50 DEBEN rechazarse con `DATO_DE_NOTA_INVALIDO`. Cualquier campo extra DEBE rechazarse como contenido inválido. `GET /api/v1/configuracion/nota-de-venta` DEBE devolver los valores vigentes con el mismo permiso (`design.md` D3, D4, D10).

#### Scenario: Valores iniciales
- **GIVEN** una organización recién migrada
- **WHEN** el Administrador lee los parámetros de la nota
- **THEN** "mostrar saldo" es falso y domicilio y teléfono están vacíos
- **Regla:** VTA-13

#### Scenario: Activar el saldo y cargar los datos
- **WHEN** el Administrador envía "mostrar saldo" verdadero, un domicilio y un teléfono
- **THEN** la configuración cambia, queda una fila de auditoría con el valor anterior y el nuevo, y la próxima nota los muestra
- **Regla:** VTA-13; AUD-01

#### Scenario: Texto demasiado largo
- **WHEN** se envía un domicilio de 201 caracteres
- **THEN** se rechaza con 422 `DATO_DE_NOTA_INVALIDO` y nada cambia
- **Regla:** VTA-13

#### Scenario: Texto vacío
- **WHEN** se envía un teléfono de solo espacios
- **THEN** el teléfono queda vacío y la nota no lo muestra
- **Regla:** VTA-13

#### Scenario: Sin el permiso
- **WHEN** el usuario `sup01`, sin `ADMIN_CONFIGURACION`, envía el comando o lee los parámetros
- **THEN** recibe 403 `PERMISO_REQUERIDO` y nada cambia
- **Regla:** SEG-06

#### Scenario: Doble envío
- **WHEN** se reenvía el comando con el mismo `operation_id` y contenido
- **THEN** devuelve el resultado original sin otra fila de auditoría
- **Regla:** INV-06

#### Scenario: Aislamiento
- **WHEN** el Administrador de una organización define los parámetros
- **THEN** la nota de otra organización no cambia
- **Regla:** INV-21

### Requirement: El nombre y el CUIT de la organización se definen por comando

Un usuario con `ADMIN_CONFIGURACION` DEBE poder definir, con conexión, el nombre (obligatorio) y el CUIT (opcional) de la organización que imprime el encabezado de la nota, mediante un comando con `operation_id` (`ORGANIZACION_DATOS_CONFIGURAR` v1, `POST /api/v1/configuracion/organizacion`, con su `GET`), auditado con el valor anterior y el nuevo. El valor se normaliza a dígitos (se descartan guiones y espacios; los puntos no se aceptan, como en el CUIT del proveedor); un valor vacío o solo de espacios queda nulo; un valor que tras normalizar no tenga exactamente 11 dígitos DEBE rechazarse con 422 `CUIT_INVALIDO` sin cambiar nada. Sin columna nueva ni migración. El nombre se recorta; uno vacío o de más de 200 caracteres DEBE rechazarse con 422 `NOMBRE_DE_ORGANIZACION_INVALIDO` sin cambiar nada. Se guardan en `organizacion.nombre` y `organizacion.cuit`. El alta de organizaciones no se ofrece. No se valida el dígito verificador del CUIT (`design.md` D15 b).

#### Scenario: Cambiar el nombre
- **GIVEN** una organización llamada "Distribuidora Demo"
- **WHEN** el Administrador envía "  Distribuidora Norte  "
- **THEN** `organizacion.nombre` queda "Distribuidora Norte", hay una fila de auditoría con el nombre anterior y el nuevo, y la próxima nota lo muestra
- **Regla:** VTA-13; AUD-01

#### Scenario: Nombre inválido
- **WHEN** se envía un nombre vacío, de solo espacios o de 201 caracteres
- **THEN** se rechaza con 422 `NOMBRE_DE_ORGANIZACION_INVALIDO` y ni el nombre ni el CUIT cambian
- **Regla:** VTA-13

#### Scenario: Cargar el CUIT
- **GIVEN** una organización con `cuit` nulo
- **WHEN** el Administrador envía `30-71234567-8`
- **THEN** `organizacion.cuit` queda `30712345678`, hay una fila de auditoría con el valor anterior (nulo) y el nuevo, y la próxima nota lo muestra
- **Regla:** VTA-13; AUD-01

#### Scenario: Largo inválido
- **WHEN** se envía `3071234567` (10 dígitos) o `307123456789` (12)
- **THEN** se rechaza con 422 `CUIT_INVALIDO` y nada cambia
- **Regla:** VTA-13; CLI-05

#### Scenario: Caracteres inválidos
- **WHEN** se envía `30.71234567.8` o `30-7123456A-8`
- **THEN** se rechaza con 422 `CUIT_INVALIDO` y nada cambia
- **Regla:** VTA-13

#### Scenario: Vaciar el CUIT
- **GIVEN** una organización con CUIT cargado
- **WHEN** se envía un texto de solo espacios
- **THEN** `organizacion.cuit` queda nulo, la auditoría registra el valor anterior y la nota deja de mostrarlo
- **Regla:** VTA-13; AUD-01

#### Scenario: Sin el permiso
- **WHEN** el usuario `sup01`, sin `ADMIN_CONFIGURACION`, envía el comando o lee el CUIT
- **THEN** recibe 403 `PERMISO_REQUERIDO` y nada cambia
- **Regla:** SEG-06

#### Scenario: Doble envío
- **WHEN** se reenvía el comando con el mismo `operation_id` y contenido
- **THEN** devuelve el resultado original sin otra fila de auditoría
- **Regla:** INV-06

#### Scenario: Aislamiento
- **WHEN** el Administrador de una organización define su CUIT
- **THEN** el CUIT de otra organización no cambia
- **Regla:** INV-21

### Requirement: Los parámetros de la nota se administran desde la pantalla de configuración

La configuración de `/admin` DEBE ofrecer, con `ADMIN_CONFIGURACION`, una sección "Nota de venta" que muestre y permita cambiar "mostrar saldo" y, en "Encabezado de la nota", el domicilio y el teléfono, y una sección propia "Datos de la organización" (`/admin/configuracion/organizacion`) con el nombre y el CUIT, y que muestre los errores del comando junto al campo que corresponde (`design.md` D10, D15). La sección "Datos de la organización" no lleva ayuda contextual (D15 c).

#### Scenario: Guardar desde la pantalla
- **GIVEN** el usuario `admin` en "Configuración › Nota de venta"
- **WHEN** activa "mostrar saldo" y guarda
- **THEN** la pantalla muestra el valor nuevo
- **Regla:** VTA-13

#### Scenario: Error junto al campo
- **WHEN** guarda un teléfono de 51 caracteres
- **THEN** el error aparece junto al teléfono y los demás valores no cambian
- **Regla:** VTA-13

#### Scenario: Guardar el nombre y el CUIT desde la pantalla
- **GIVEN** el usuario `admin` en "Configuración › Datos de la organización", con CUIT vacío
- **WHEN** cambia el nombre, escribe `30-71234567-8` en "CUIT" y guarda
- **THEN** la pantalla muestra el nombre nuevo y `30712345678`, y la nota de venta imprime ambos en el encabezado
- **Regla:** VTA-13

#### Scenario: Error junto al campo
- **WHEN** guarda un CUIT de 10 dígitos o un nombre vacío
- **THEN** el error aparece junto al campo que corresponde y el otro valor escrito no se pierde
- **Regla:** VTA-13
