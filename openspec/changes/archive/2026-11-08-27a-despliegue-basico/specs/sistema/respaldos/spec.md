## Purpose

Define el backup automático de la base en el entorno de producción de la etapa 1 en su forma básica: un backup diario verificado, con retención mínima y un estado de salud que avisa cuando deja de hacerse (`02` §16.2; `00` §9 criterio 12; `04` §10). La retención completa, la copia fuera del servidor y la restauración probada son del change 27b.

## ADDED Requirements

### Requirement: Backup diario de la base completa

El servicio `backup` DEBE generar una vez por día, a la hora configurada en la zona horaria configurada, un backup completo de la base con `pg_dump` en formato personalizado (comprimido), conectándose con un rol de solo lectura que no puede modificar datos ni esquema. El archivo DEBE nombrarse con la fecha y hora de generación y DEBE escribirse primero con un nombre temporal y renombrarse solo al terminar bien, de modo que nunca quede un archivo final incompleto. DEBE poder generarse además un backup a pedido con el mismo procedimiento (`02` §16.2; INV-05; `design.md` D10, D11).

#### Scenario: Backup a la hora configurada
- **GIVEN** `BACKUP_HORA=03:00` y `TZ=America/Argentina/Mendoza`
- **WHEN** llegan las 03:00 locales
- **THEN** aparece en el directorio de backups un archivo `distribuidora-AAAAMMDD-HHMMSS.dump` con la fecha y hora de esa corrida
- **Regla:** `02` §16.2 («`pg_dump` diario comprimido»)

#### Scenario: Backup a pedido
- **GIVEN** el entorno levantado
- **WHEN** el operador pide un backup a pedido (paso del runbook antes de actualizar)
- **THEN** se genera un archivo con el mismo formato y la misma verificación que el diario
- **Regla:** `design.md` D10, D15

#### Scenario: Un backup interrumpido no deja un archivo final
- **GIVEN** un `pg_dump` que falla a mitad (por ejemplo, la base se detiene)
- **WHEN** termina la corrida
- **THEN** no queda ningún archivo `.dump` nuevo, el temporal se borra y el error queda en el registro del servicio
- **Regla:** `design.md` D10

#### Scenario: El rol de backup no puede escribir
- **GIVEN** el rol de backup
- **WHEN** intenta `INSERT` en cualquier tabla o `CREATE TABLE`
- **THEN** PostgreSQL lo rechaza
- **Regla:** INV-05; `design.md` D11

### Requirement: Cada backup se verifica al generarse

Después de generar un backup, el servicio DEBE comprobar que el archivo se puede leer como backup válido (listando su contenido) y que incluye las tablas de libro (`cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov`, `auditoria`). Si la verificación falla, el archivo NO DEBE contarse como backup válido para la retención ni para la salud, y el error DEBE registrarse (`00` §9 criterio 12; `design.md` D12).

#### Scenario: Backup válido
- **GIVEN** una base con ventas, movimientos de stock y auditoría
- **WHEN** se genera un backup
- **THEN** la verificación lista sus tablas, incluidas las cuatro de libro, y el registro dice «Backup verificado» con el nombre y el tamaño del archivo
- **Regla:** `00` §9 criterio 12; `02` §17 (registro sin datos personales)

#### Scenario: Archivo dañado
- **GIVEN** un archivo de backup truncado
- **WHEN** se verifica
- **THEN** la verificación falla, el archivo se renombra como fallido y no cuenta para la salud
- **Regla:** `design.md` D12

### Requirement: Retención mínima de backups

Después de cada backup verificado, el servicio DEBE conservar los últimos N backups válidos (N configurable, por defecto el valor aprobado en `design.md` D13) y borrar solo los backups válidos más antiguos que esos N. NUNCA DEBE borrar nada si el backup recién generado no se verificó, ni archivos que no siguen el formato de nombre de los backups (`02` §16.2; `04` §10 «retención mínima»; `design.md` D13).

#### Scenario: Se borra el más antiguo
- **GIVEN** N = 7 y ocho backups válidos de ocho días seguidos
- **WHEN** termina un backup verificado nuevo
- **THEN** quedan los siete más recientes (incluido el nuevo)
- **Regla:** `04` §10; `design.md` D13

#### Scenario: Un backup fallido no dispara la limpieza
- **GIVEN** siete backups válidos
- **WHEN** el backup de hoy falla
- **THEN** los siete siguen en el directorio
- **Regla:** `design.md` D13

#### Scenario: Archivos ajenos no se tocan
- **GIVEN** un archivo `restauracion-de-prueba.sql` en el directorio de backups
- **WHEN** corre la retención
- **THEN** ese archivo sigue
- **Regla:** `design.md` D13

### Requirement: La salud del servicio de backup refleja el último backup válido

El servicio `backup` DEBE informar estado no sano cuando el backup válido más reciente tiene más de 26 horas o no existe ninguno pasada la primera hora programada, de modo que `docker compose ps` muestre el problema (`02` §17; `design.md` D14).

#### Scenario: Backups al día
- **GIVEN** un backup válido de hace 3 horas
- **WHEN** se consulta la salud del servicio
- **THEN** está sano
- **Regla:** `design.md` D14

#### Scenario: Backups atrasados
- **GIVEN** el último backup válido de hace 30 horas
- **WHEN** se consulta la salud del servicio
- **THEN** está no sano
- **Regla:** `design.md` D14

### Requirement: Los backups viven fuera de los volúmenes de Docker

Los backups DEBEN escribirse en un directorio del servidor configurable, fuera de los volúmenes de Docker, para que sobrevivan a recrear los contenedores o borrar volúmenes y se puedan copiar con herramientas comunes. El directorio NO DEBE ser legible por otros usuarios del equipo (en Linux, permisos `700` y archivos `600`; en la PC de la oficina con Windows, permisos de la carpeta restringidos al usuario) (`02` §16.2; `design.md` D1, D10).

#### Scenario: Recrear el entorno conserva los backups
- **GIVEN** backups en el directorio configurado
- **WHEN** se ejecuta `docker compose down -v` sobre el compose de producción
- **THEN** los archivos de backup siguen en el directorio del servidor
- **Regla:** `design.md` D10
