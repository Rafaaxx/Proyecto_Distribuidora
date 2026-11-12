# Sistema - Respaldos

## Purpose

Define el backup automático de la base en el entorno de producción: un backup diario verificado al generarse, retención de los últimos 14 diarios y 8 semanales, copia externa cifrada que solo sube y tiene su propia retención, restauración en una base vacía y prueba mensual de restauración en un entorno separado y sin red, con un estado de salud por cada parte (`02` §16.2; `00` §9 criterio 12; `04` §12; ADR-072).

## Requirements

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

### Requirement: Retención de 14 backups diarios y 8 semanales

Después de cada backup verificado, el servicio DEBE conservar el backup válido más reciente de cada uno de los 14 días más recientes que tienen backup y el backup válido más reciente de cada una de las 8 semanas más recientes que tienen backup (semana de lunes a domingo, en la zona horaria configurada), y borrar solo los demás backups válidos. El día y la semana de un backup DEBEN tomarse de la fecha de su nombre. Un mismo backup PUEDE contar como diario y como semanal. NUNCA DEBE borrar nada si el backup recién generado no se verificó, ni archivos que no siguen el formato de nombre de los backups. Las cantidades DEBEN ser configurables, por defecto 14 y 8 (`02` §16.2; `04` §12; `design.md` D1).

#### Scenario: Dos meses de backups diarios
- **GIVEN** un backup válido por día, a las 03:00, del 2026-11-01 al 2026-12-31
- **WHEN** termina la retención después del backup del 2026-12-31
- **THEN** quedan 19 backups: los 14 del 2026-12-18 al 2026-12-31, y los semanales del 2026-12-13, 2026-12-06, 2026-11-29, 2026-11-22 y 2026-11-15 (los semanales del 2026-12-20, 2026-12-27 y 2026-12-31 ya están entre los diarios)
- **Regla:** `02` §16.2 («retención de 14 diarios y 8 semanales»); `design.md` D1

#### Scenario: Varios backups el mismo día
- **GIVEN** del 2026-12-31 un backup de las 03:00 y uno a pedido de las 15:20, y backups diarios de los 13 días anteriores
- **WHEN** termina la retención después del backup de las 15:20
- **THEN** del 2026-12-31 queda el de las 15:20 y se borra el de las 03:00
- **Regla:** `design.md` D1

#### Scenario: Si los backups se detienen, no se borran los últimos
- **GIVEN** 14 backups diarios válidos del 2026-09-01 al 2026-09-14 y ninguno después
- **WHEN** el 2026-12-01 termina un backup verificado
- **THEN** quedan el nuevo y los 13 más recientes de septiembre (del 2026-09-02 al 2026-09-14) y se borra solo el del 2026-09-01 (los semanales de esas semanas, 2026-09-06, 2026-09-13 y 2026-09-14, ya están entre los diarios); nada se borra por la fecha del calendario
- **Regla:** `design.md` D1

#### Scenario: Un backup fallido no dispara la limpieza
- **GIVEN** 22 backups válidos
- **WHEN** el backup de hoy falla la verificación
- **THEN** los 22 siguen en el directorio
- **Regla:** `design.md` D1

#### Scenario: Archivos ajenos no se tocan
- **GIVEN** en el directorio de backups un archivo `restauracion-de-prueba.sql`, un `.dump.fallido` y una subcarpeta con archivos bajados de la copia externa
- **WHEN** corre la retención
- **THEN** los tres siguen
- **Regla:** `design.md` D1

### Requirement: Copia externa de cada backup válido

Un servicio de copia DEBE subir a un almacenamiento externo, fuera del equipo, cada backup válido que la retención local conserva y que todavía no está en el destino, al menos una vez por hora, reintentando en la corrida siguiente si falla. DEBE comprobar cada archivo subido contra el original antes de considerarlo copiado. El servicio de copia NO DEBE tener credenciales de la base ni acceso a su red, DEBE leer el directorio de backups solo en modo lectura y DEBE poder ejecutarse a pedido. El destino DEBE configurarse en el archivo de entorno sin cambiar código (`02` §16.2; `04` §12; `design.md` D3, D4, D6).

#### Scenario: Un backup nuevo llega al destino
- **GIVEN** un backup válido nuevo en el directorio de backups y el destino configurado
- **WHEN** corre la copia
- **THEN** el archivo queda en el destino, la comprobación contra el original es correcta y el registro dice «Copia externa verificada» con el nombre y el tamaño, sin datos del negocio
- **Regla:** `02` §16.2; `02` §17

#### Scenario: Sin internet, la copia espera y no pierde nada
- **GIVEN** el destino inaccesible durante una corrida
- **WHEN** vuelve a estar accesible y corre la copia siguiente
- **THEN** se suben todos los backups conservados que faltaban
- **Regla:** `design.md` D6

#### Scenario: El servicio de copia no puede llegar a la base
- **GIVEN** el compose de producción
- **WHEN** se inspecciona el servicio de copia
- **THEN** no tiene ninguna variable de conexión a la base, no está en la red de la base y monta el directorio de backups solo lectura
- **Regla:** INV-05; `design.md` D4

### Requirement: La copia externa está cifrada y su clave no viaja con ella

Cada archivo DEBE cifrarse en el equipo antes de salir, con una clave que vive en el archivo de entorno y NUNCA se guarda en el almacenamiento externo. En el destino no DEBEN poder leerse ni el contenido ni el nombre original de los backups. Con la clave DEBE poder bajarse y descifrarse cualquier archivo del destino a una carpeta del equipo (`02` §18; `design.md` D5, D7).

#### Scenario: El destino no es legible sin la clave
- **GIVEN** un backup copiado al destino
- **WHEN** se lee directamente el destino, sin la clave
- **THEN** no aparece el nombre `distribuidora-…dump` ni el contenido del backup
- **Regla:** `02` §18; `design.md` D5

#### Scenario: Bajar un backup de la copia externa
- **GIVEN** un backup en el destino y la clave correcta
- **WHEN** se pide bajarlo
- **THEN** queda en una subcarpeta del directorio de backups un archivo idéntico al original, que `pg_restore --list` lee con las cuatro tablas de libro
- **Regla:** `design.md` D5, D8

#### Scenario: Clave equivocada
- **GIVEN** un backup en el destino
- **WHEN** se pide bajarlo con otra clave
- **THEN** la operación falla con un error que lo dice y no deja ningún archivo `.dump`
- **Regla:** `design.md` D5

### Requirement: La copia externa conserva su propia retención y no replica borrados

La copia NO DEBE borrar archivos del destino porque falten en el equipo. Después de una corrida exitosa DEBE aplicar en el destino la misma regla de retención de 14 diarios y 8 semanales sobre los backups que hay en el destino (`design.md` D2).

#### Scenario: Se borra la carpeta de la PC
- **GIVEN** 22 backups en el destino
- **WHEN** se borran todos los backups del equipo y corre la copia
- **THEN** los 22 siguen en el destino
- **Regla:** `design.md` D2

#### Scenario: Retención en el destino
- **GIVEN** en el destino un backup por día del 2026-11-01 al 2026-12-30 y el del 2026-12-31 recién subido
- **WHEN** termina la corrida
- **THEN** en el destino quedan los mismos 19 backups que la retención local conserva en ese caso
- **Regla:** `design.md` D1, D2

### Requirement: La salud del servicio de copia refleja la última copia

El servicio de copia DEBE informar estado no sano cuando el backup más reciente que llegó al destino tiene más de 26 horas (por la fecha de su nombre) o cuando la última corrida falló por credenciales o por la clave (`02` §17; `design.md` D6).

#### Scenario: Copia al día
- **GIVEN** en el destino un backup de hace 3 horas
- **WHEN** se consulta la salud del servicio de copia
- **THEN** está sano
- **Regla:** `design.md` D6

#### Scenario: Copia atrasada
- **GIVEN** el backup más reciente del destino de hace 30 horas
- **WHEN** se consulta la salud del servicio de copia
- **THEN** está no sano
- **Regla:** `design.md` D6

### Requirement: Restauración de un backup en una base vacía

DEBE existir un procedimiento de una sola orden, que no arranca con el entorno, que restaure un backup elegido en la base de producción usando el rol dueño del esquema (nunca el superusuario). Antes de restaurar DEBE verificar el archivo y DEBE negarse si la base de destino tiene alguna tabla o si hay otras conexiones a ella. DEBE restaurar en una sola transacción, de modo que un error deje la base vacía como estaba. Los dueños y permisos del archivo DEBEN conservarse (`02` §16.2; INV-05; ADR-020; `design.md` D8).

#### Scenario: Restaurar en una base vacía
- **GIVEN** una base recién creada, con los roles de la aplicación y sin tablas, y un backup válido de una base con ventas, movimientos de stock y auditoría
- **WHEN** se restaura ese backup
- **THEN** la base queda con todas las tablas y filas del backup y el registro dice «Restauración verificada»
- **Regla:** `00` §9 criterio 12

#### Scenario: Se niega a pisar una base con datos
- **GIVEN** la base de producción con tablas
- **WHEN** se pide restaurar un backup en ella
- **THEN** la orden termina con error sin modificar nada y el mensaje dice que la base no está vacía
- **Regla:** `design.md` D8

#### Scenario: Se niega con el sistema en uso
- **GIVEN** una base vacía con otra conexión abierta
- **WHEN** se pide restaurar
- **THEN** la orden termina con error sin modificar nada y pide detener el backend
- **Regla:** `design.md` D8

#### Scenario: Un error a mitad deja la base vacía
- **GIVEN** un archivo que falla al restaurar una de sus tablas
- **WHEN** se restaura
- **THEN** la orden termina con error y la base queda sin tablas
- **Regla:** `design.md` D8

#### Scenario: La aplicación sigue sin borrar libros después de restaurar
- **GIVEN** una base restaurada
- **WHEN** el rol `app_runtime` intenta `DELETE` o `UPDATE` sobre `auditoria`, `cuenta_movimiento`, `stock_movimiento` o `costo_producto_mov`
- **THEN** PostgreSQL lo rechaza por falta de permiso
- **Regla:** INV-05

### Requirement: La restauración comprueba que los datos coinciden

Toda restauración y toda prueba de restauración DEBE comparar, tabla por tabla, la cantidad de filas que trae el archivo con la que quedó en la base, comprobar que el rol de la aplicación sigue sin `UPDATE` ni `DELETE` en las tablas de libro y que existe la versión de migraciones; si algo no coincide, DEBE informar error nombrando la tabla, sin datos del negocio (`00` §9 criterio 12; INV-05; `design.md` D9).

#### Scenario: Los datos coinciden con el origen
- **GIVEN** una base de origen con datos y su backup
- **WHEN** se restaura en otra base vacía
- **THEN** cada tabla tiene la misma cantidad de filas y la misma suma de control que en el origen
- **Regla:** `00` §9 criterio 12

#### Scenario: Una tabla no coincide
- **GIVEN** una restauración en la que una tabla quedó con menos filas que en el archivo
- **WHEN** se comprueba
- **THEN** la comprobación falla y nombra esa tabla
- **Regla:** `design.md` D9

### Requirement: Prueba de restauración periódica en un entorno separado

Un servicio sin red y sin credenciales DEBE, una vez por mes en el día y la hora configurados, restaurar el backup válido más reciente en un servidor de base temporal propio, separado del de producción, comprobarlo como cualquier restauración y descartarlo. DEBE poder ejecutarse a pedido, con el backup más reciente o con uno elegido. Su salud DEBE ser no sana si la última prueba buena tiene más de 35 días o si la última falló (`02` §16.2 «al menos una vez por mes»; `00` §9 criterio 12; `design.md` D10).

#### Scenario: Prueba mensual buena
- **GIVEN** un backup válido reciente
- **WHEN** llega el día y la hora de la prueba
- **THEN** el registro dice «Prueba de restauración verificada» con el archivo, las tablas y las filas, y la base temporal ya no existe
- **Regla:** `02` §16.2

#### Scenario: Backup que no se puede restaurar
- **GIVEN** el backup más reciente dañado de forma que la restauración falla
- **WHEN** corre la prueba
- **THEN** la prueba informa error y la salud del servicio pasa a no sana
- **Regla:** `design.md` D10

#### Scenario: La prueba no toca producción
- **GIVEN** el compose de producción
- **WHEN** se inspecciona el servicio de prueba
- **THEN** no tiene red, no tiene credenciales de la base y monta el directorio de backups solo lectura
- **Regla:** `design.md` D10

#### Scenario: Prueba atrasada
- **GIVEN** la última prueba buena de hace 40 días
- **WHEN** se consulta la salud del servicio de prueba
- **THEN** está no sano
- **Regla:** `design.md` D10

### Requirement: Los servicios de respaldo no corren como superusuario del sistema

Los servicios de backup, copia, restauración y prueba DEBEN correr con un usuario sin privilegios dentro de su contenedor y seguir escribiendo en el directorio de backups configurado (`02` §18; ADR-071, limitación; `design.md` D11).

#### Scenario: Backup con usuario sin privilegios
- **GIVEN** el servicio de backup corriendo con el usuario configurado
- **WHEN** genera un backup
- **THEN** el proceso no es root y el archivo queda en el directorio de backups
- **Regla:** `design.md` D11

### Requirement: Aviso externo opcional

Si se configura una dirección de aviso, el servicio de copia externa DEBE llamarla después de cada corrida buena y DEBE llamar a su variante de falla cuando falla, sin enviar datos del negocio. Sin dirección configurada, NO DEBE intentar ningún aviso. El servicio de la prueba de restauración corre sin red y NO envía aviso: su única señal es su salud (`design.md` D10) (`02` §17; `design.md` D14).

#### Scenario: Aviso configurado
- **GIVEN** una dirección de aviso configurada
- **WHEN** una copia termina bien
- **THEN** se llama a la dirección de aviso

#### Scenario: Aviso sin configurar
- **GIVEN** la dirección de aviso vacía
- **WHEN** una copia termina bien o mal
- **THEN** no se intenta ninguna llamada de aviso
