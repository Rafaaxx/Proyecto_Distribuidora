# Restauración, prueba mensual y mudanza a otro equipo

Esta guía es para el día en que hay que **recuperar los datos**: se rompió o se perdió la PC, se quiere comprobar que los backups sirven, o se quiere llevar el sistema a otro equipo (por ejemplo, de la PC de la oficina a un servidor en internet). Está escrita para alguien que **no es experto en servidores**: cada término se explica la primera vez y cada paso dice para qué sirve.

Antes de empezar conviene haber leído `puesta-en-marcha.md` (instalación, el atajo `dc` y el archivo de entorno). Aquí se usa el mismo atajo `dc` (es `docker compose -f docker-compose.prod.yml --env-file <archivo>`; ver el paso C3 de esa guía).

## Términos básicos

| Término | Qué significa |
| --- | --- |
| **Backup** | Un archivo `distribuidora-AAAAMMDD-HHMMSS.dump` con **toda** la base de datos de un momento. Se hace solo, una vez por día. |
| **Restaurar** | Volver a cargar un backup en una base de datos para recuperar lo que tenía. |
| **Copia externa** | Una copia de cada backup guardada **fuera de la PC** (en un servicio de almacenamiento en internet), **cifrada** antes de salir. Si la PC se pierde, los backups que estaban en ella se pierden con ella; la copia externa no. |
| **Cifrada** | Embrollada con una clave, de modo que sin la clave el archivo (y hasta su nombre) no se puede leer, ni siquiera por el proveedor. |
| **Hoja de recuperación** | Una hoja (o una nota en un gestor de contraseñas) con lo mínimo para recuperarse **sin nada de la PC**. Ver la sección siguiente. |
| **Base vacía** | Una base de datos sin ninguna tabla. La restauración **solo** se hace sobre una base vacía, para que sea imposible pisar datos por error. |
| **Volumen de Docker** | El «disco» interno donde Docker guarda los datos de la base. Si se borra, la base se pierde (por eso existen los backups, que viven **fuera** de los volúmenes). |

## La hoja de recuperación

**Qué guardar**, fuera de la PC y fuera del repositorio de código (un gestor de contraseñas, o un sobre cerrado en poder del dueño del negocio):

1. Los datos de acceso al almacenamiento externo: dirección del servicio (`COPIA_S3_ENDPOINT`), región (`COPIA_S3_REGION`), nombre del cubo y carpeta (`COPIA_RUTA`), `COPIA_ACCESS_KEY_ID` y `COPIA_SECRET_ACCESS_KEY`.
2. Las **dos claves de cifrado**: `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO`.
3. Las cinco claves del sistema (`POSTGRES_PASSWORD`, `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `APP_BACKUP_DB_PASSWORD`, `JWT_SECRET`). En un equipo nuevo se pueden generar otras, pero tenerlas evita dudas.
4. La dirección del repositorio del código y la versión instalada (`APP_VERSION`).
5. Lo ideal: una copia del archivo `produccion.env` completo.

**Lo más importante: sin `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO`, las copias externas son ilegibles.** No hay forma de recuperarlas ni de pedirlas al proveedor. Si se pierde la PC y no está la hoja, los datos se pierden.

**Nunca** poner estos valores en el repositorio, en un chat ni en un correo.

## Qué se pierde y qué no

- Se recupera **todo lo que había en el último backup** (ventas, cobranzas, stock, clientes, precios, usuarios, auditoría).
- Se pierde **lo registrado después del último backup** (hasta un día). Es la consecuencia de hacer un backup diario.
- Lo que un teléfono tenía **sin sincronizar** (su cola de ventas hechas sin señal) **no** está en el backup: sigue en el teléfono y se sincroniza solo cuando vuelva a conectarse, siempre que el sistema esté en la **misma dirección** (ver la mudanza).
- Los archivos de backup **no se modifican** al restaurar: restaurar solo lee.

## Prueba mensual: cómo se lee su resultado

No alcanza con tener backups: hay que saber que **se pueden restaurar**. El servicio `prueba-restauracion` lo comprueba solo, una vez por mes (el día `PRUEBA_DIA` a la hora `PRUEBA_HORA`, por defecto el 1 a las 04:00):

1. Levanta, **dentro de su propio contenedor y sin conexión de red**, una base de datos temporal (aparte de la de producción: no la toca ni puede verla). Vive en el disco del contenedor.
2. Restaura en ella el último backup válido y compara tabla por tabla las filas del archivo con las de la base restaurada.
3. Descarta la base temporal (se borra después de cada prueba).

**Cómo saber si salió bien.** Esta prueba **no manda ningún aviso** (a propósito: no tiene red). La única señal es su estado en `dc ps` (columna `STATUS`):

- `healthy`: la última prueba buena es de hace menos de 35 días.
- `unhealthy`: la última prueba falló, o pasaron más de 35 días sin una buena. Hay que mirarlo.

Por eso existe la **revisión semanal** (dos minutos): una vez por semana, abrir una consola en la carpeta del código y correr `dc ps`. Los servicios `backup`, `copia-externa` y `prueba-restauracion` tienen que decir `healthy`. Si alguno dice `unhealthy`, ver `dc logs --tail 100 <servicio>` y la sección «Si algo no funciona».

Para correrla **a pedido** (por ejemplo, después de una actualización):

```bash
dc run --rm prueba-restauracion ahora                                      # con el último backup válido
dc run --rm prueba-restauracion ahora distribuidora-20261101-030000.dump   # con uno elegido
```

Sale bien si termina con estas líneas: `Prueba de restauracion verificada: archivo=… tablas=N filas=M` y `Servidor temporal descartado`. Si falla, el comando termina con error y dice el motivo (por ejemplo, un backup dañado).

## Restaurar paso a paso

Hay tres situaciones; la restauración en sí (R4 a R7) es la misma:

- **Desastre en el mismo equipo** (se borró el volumen de la base, pero la carpeta de backups está): desde R3.
- **Desastre y se perdió el equipo** (equipo nuevo; solo hay copia externa y hoja de recuperación): desde R1.
- **Mudanza a otro equipo**: ver la sección «Mudanza a otro equipo», que usa estos mismos pasos.

### R1 Preparar un equipo nuevo (solo si no hay equipo)

1. Instalar Docker y clonar el código siguiendo `puesta-en-marcha.md` (instalación y paso C1).
2. Crear el archivo de entorno (paso C2) con los valores de la **hoja de recuperación**. Si las cinco claves del sistema se generan nuevas, no pasa nada: la base se crea de cero con ellas. Lo que **no** puede cambiar son las dos claves de cifrado de la copia externa.
3. En **Linux**, la carpeta de backups tiene que pertenecer al usuario sin privilegios con que corren los servicios de respaldo (el 999). Si no, no pueden leer ni escribir (un archivo escrito por `root` con permisos privados no lo puede leer la restauración):

   ```bash
   sudo mkdir -p /var/backups/distribuidora/bajados
   sudo chown 999:999 /var/backups/distribuidora /var/backups/distribuidora/bajados
   ```

   (Cambiar la ruta si `BACKUP_DIR` es otra.) En **Windows con Docker Desktop**, una carpeta **nueva** no necesita cambiar dueños: solo crear la subcarpeta `bajados` dentro de `BACKUP_DIR`. Si la carpeta **ya existía de la versión 27a** (o algo dice `Permission denied` sobre `/backups`), hacer **una vez**:

   ```powershell
   docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b
   ```

   (cambiar la carpeta si `BACKUP_DIR` es otra).

### R2 Traer el backup desde la copia externa

Solo si el backup no está en la carpeta `BACKUP_DIR` del equipo. Para este paso el archivo de entorno debe tener las variables de la copia externa (`COPIA_TIPO`, `COPIA_RUTA`, el servicio, las claves de acceso y las dos de cifrado). No hace falta levantar nada más.

1. **Ver qué backups hay.** Los nombres en el proveedor están cifrados y no se entienden; esta orden los lista ya descifrados:

   ```bash
   dc run --rm --entrypoint sh copia-externa -c ". /opt/copia/lib.sh && rclone lsf cifrado:"
   ```

   Muestra nombres como `distribuidora-20261108-030000.dump`; el de fecha más reciente es el último.
2. **Bajar y descifrar uno:**

   ```bash
   dc run --rm copia-externa bajar distribuidora-20261108-030000.dump
   ```

   Termina con «Backup bajado y descifrado» y deja el archivo en la subcarpeta `bajados` de `BACKUP_DIR`. Si falla por la clave, revisar `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO` (tienen que ser exactamente los de siempre); no queda ningún archivo a medias.

### R3 Levantar solo la base y dejar el backend parado

La restauración necesita que la base **exista y esté vacía**, y que **nadie más esté conectado** (el backend parado). En un equipo nuevo, o con un volumen nuevo, la base se crea vacía sola:

```bash
dc up -d postgres
dc stop backend          # si ya existía; en un equipo nuevo no hace falta
```

Si se está **rehaciendo la base en el mismo equipo** y el volumen todavía existe con datos dañados, primero hay que borrarlo (**esto borra la base actual**: asegurarse de tener el backup): `dc down` y después `docker volume rm <proyecto>_postgres_data` (el nombre exacto sale de `docker volume ls`); recién entonces `dc up -d postgres`.

### R4 Restaurar

```bash
dc --profile restauracion run --rm restauracion distribuidora-20261108-030000.dump
```

(El archivo se busca primero en `BACKUP_DIR` y después en `BACKUP_DIR/bajados`.) La orden:

1. Comprueba que el archivo es un backup válido (si no, dice «no es un backup valido»).
2. **Se niega** si la base tiene alguna tabla («la base de destino no esta vacia») o si hay otras conexiones abiertas («detenga el backend»). En ambos casos **no cambia nada**.
3. Restaura todo **en una sola operación**: si algo falla a la mitad, la base queda vacía como estaba y se puede reintentar.
4. Compara las filas de cada tabla con las del archivo y comprueba que la aplicación sigue sin poder modificar ni borrar los libros (tablas que solo admiten agregar).

Termina bien con una línea que empieza con `Restauracion verificada:` y dice cuántas tablas y filas. Si no aparece, **no seguir**: ver «Si algo no funciona».

> La restauración usa el usuario dueño de las tablas (`app_migrations`), nunca el superusuario de la base. Esa credencial solo la recibe este servicio, y solo mientras corre.

### R5 Migrar

Si el código instalado es más nuevo que el del backup, la base necesita sus cambios de estructura. Si es la misma versión, esta orden no hace nada:

```bash
dc run --rm migraciones
```

### R6 Levantar todo

```bash
dc up -d
dc ps
```

Todos los servicios deben quedar `healthy` (los de respaldo pueden tardar unos minutos). **No sembrar** (`python -m app.seed`): los usuarios y los datos vienen en el backup; sembrar de nuevo crearía datos de más.

### R7 Comprobar con los ojos

Entrar a `https://<DOMINIO>/admin` con un usuario del negocio y comparar con lo que se sabe: el saldo de un par de clientes y el stock de un depósito. En una restauración de ensayo se comparan con el sistema original (sin operaciones en el medio).

## Ensayar sin tocar el sistema real

Para practicar, o para la primera prueba antes de salir a producción, se restaura en un **entorno separado** en la misma PC: otro proyecto de Compose (`-p distribuidora-restauracion`), con carpeta y archivo de entorno propios. Lo real no se toca: ni su base, ni sus backups.

**Qué se puede hacer con la oficina funcionando y qué no.** Restaurar y migrar el entorno separado se hace **con la oficina andando**: solo usan las redes internas `datos` y `salida`. Pero para **abrir su `/admin` y comparar** hace falta levantar su `caddy`, y ahí chocan dos cosas fijas del sistema real: la red `frente` tiene una subred fija (`172.30.10.0/24`, para confiar en el proxy) y los puertos 80 y 443 son únicos. Por eso, para ese paso hay que **bajar la oficina un rato** (con `dc down` **sin `-v`**: quita los contenedores y las redes, pero **conserva la base y los backups**). Avisar antes: durante ese rato nadie puede usar el sistema. Los comandos se escriben **uno por línea**, no pegados con `;` ni `&&`: si uno falla, hay que verlo antes de seguir.

1. **Carpeta propia.** Crear `C:\distribuidora-ensayo\backups\bajados`.
2. **Archivo de entorno propio.** Copiar `C:\distribuidora\produccion.env` a `C:\distribuidora-ensayo\produccion.env` y cambiar **solo** `BACKUP_DIR` a `C:\distribuidora-ensayo\backups`. Las demás variables (incluidas las claves de cifrado y de la copia externa) quedan iguales.
3. **El atajo `dc2`**, todo en una sola línea (PowerShell, desde la carpeta del código):

   ```powershell
   function dc2 { docker compose -p distribuidora-restauracion -f docker-compose.prod.yml --env-file C:\distribuidora-ensayo\produccion.env @args }
   ```
4. **Ver los backups de la copia externa:**

   ```bash
   dc2 run --rm --entrypoint sh copia-externa -c ". /opt/copia/lib.sh && rclone lsf cifrado:"
   ```
5. **Bajar uno:**

   ```bash
   dc2 run --rm copia-externa bajar distribuidora-20261108-030000.dump
   ```
6. **Levantar solo la base del ensayo** (base nueva y vacía, volumen propio):

   ```bash
   dc2 up -d postgres
   ```
7. **Restaurar** y **migrar**:

   ```bash
   dc2 --profile restauracion run --rm restauracion distribuidora-20261108-030000.dump
   dc2 run --rm migraciones
   ```

   La restauración debe terminar con `Restauracion verificada: …`.
8. **Para comparar en pantalla:** bajar la oficina, levantar la del ensayo, abrir `https://<DOMINIO>/admin` y comparar saldos de clientes y stock con lo conocido. Al terminar, bajar el ensayo **con `-v`** (borra solo sus volúmenes) y volver a levantar la oficina, siempre un comando por vez:

   ```bash
   dc down
   dc2 up -d caddy
   dc2 down -v
   dc up -d
   dc ps
   ```

   `dc down` va **sin `-v`**. La `-v` solo se usa con `dc2`, nunca con `dc`. Al final, `dc ps` debe mostrar la oficina sana.

**Destino local para ensayar sin cuenta.** Para practicar la copia y la bajada sin abrir cuenta en un proveedor se usa `COPIA_TIPO=local`, `COPIA_RUTA=/destino-local/copias` y, en `COPIA_ACCESS_KEY_ID` y `COPIA_SECRET_ACCESS_KEY`, el texto `no-aplica` (no pueden quedar vacías). Para ver la carpeta, `COPIA_LOCAL_DIR` apunta a una carpeta de la PC. **No protege de perder la PC**: es solo un ensayo.

## Mudanza a otro equipo

Sirve para pasar, por ejemplo, de la PC de la oficina a un servidor en internet. Se hace restaurando un backup en el equipo nuevo. **El orden importa**, sobre todo por los teléfonos.

### M1 Antes de nada: la cola de cada teléfono tiene que estar vacía

Cada teléfono guarda en sí mismo las ventas hechas sin señal (su **cola**), asociadas a la **dirección** del sistema (por ejemplo `https://192.168.1.20`). En el equipo nuevo la dirección cambia (por ejemplo, a un dominio), y desde la dirección nueva el teléfono **no ve** la cola vieja: lo que quede sin sincronizar se pierde.

**No continuar hasta que cada teléfono tenga la cola vacía.** Teléfono por teléfono: con señal y entrando por la dirección vieja, abrir `/ruta`, dejar que sincronice y comprobar que no queda ninguna operación pendiente (cola vacía). Si un teléfono tiene ventas en la cola, **esperar** a que sincronice: no seguir con M2.

### M2 Detener el equipo viejo y hacer el backup final

Con la cola de todos los teléfonos vacía, en el equipo viejo:

```bash
dc stop backend                   # nadie puede cargar nada más
dc run --rm backup ahora          # el backup final, verificado
dc run --rm copia-externa ahora   # lo sube a la copia externa (si está configurada)
```

**No borrar nada** del equipo viejo: se conserva intacto al menos **30 días** como vuelta atrás. Si la mudanza sale mal, `dc start backend` y todo sigue donde estaba.

### M3 Restaurar en el equipo nuevo

En el equipo nuevo, recién instalado y **sin sembrar**, seguir R1 a R7 con el backup final. Con copia externa, R2 trae el archivo; sin ella, copiar a mano el `.dump` a la carpeta `bajados`.

### M4 Después

- Los teléfonos entran por la dirección nueva y hay que volver a iniciar sesión (y, si el equipo nuevo usa otro certificado, instalar el que corresponda; ver `puesta-en-marcha.md`).
- Comparar saldos y stock (R7) con los del equipo viejo antes de apagar nada.
- Esperar al menos 30 días antes de borrar el equipo viejo y sus backups.

## Si algo no funciona

| Síntoma | Qué mirar |
| --- | --- |
| `la base de destino no esta vacia` | La base ya tiene tablas. La restauración no pisa datos. Si de verdad se quiere reemplazar, hay que borrar el volumen (R3) sabiendo que se pierde lo que hay. |
| `detenga el backend` | Hay conexiones abiertas: `dc stop backend` y esperar unos segundos. Revisar también que nadie tenga una consola abierta contra la base. |
| `no es un backup valido` | El archivo está dañado o incompleto, o no es de este sistema. Probar con el backup anterior. |
| `el archivo '…' no existe` | Está mal escrito o falta bajarlo (R2). Se busca en `BACKUP_DIR` y en `BACKUP_DIR/bajados`. |
| `Permission denied` sobre `/backups` (al respaldar, bajar o restaurar) | La carpeta quedó con permisos de la versión 27a o creada por otro usuario. Windows, una vez: `docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b`. Linux: `sudo chown -R 999:999 <BACKUP_DIR>`. |
| La restauración no puede leer el archivo (permiso denegado) | En Linux, `BACKUP_DIR` y `bajados/` tienen que pertenecer a 999:999 (R1). Un archivo copiado a mano como `root` con permisos privados no se puede leer: `sudo chown 999:999 <archivo>`. |
| `no se pudo bajar … (revise la clave de cifrado)` | `COPIA_CLAVE_CIFRADO` o `COPIA_SAL_CIFRADO` no son exactamente los de siempre. No se pueden cambiar una vez que hay copias. |
| `copia-externa` o `prueba-restauracion` dicen `unhealthy` | `dc logs --tail 100 <servicio>`. En `copia-externa`: credenciales vencidas, cubo inexistente o proveedor caído. En `prueba-restauracion`: la última prueba falló o pasaron más de 35 días; correr `dc run --rm prueba-restauracion ahora` y leer el motivo. |
| La restauración termina pero la comprobación falla | **No usar esa base.** Quedó con datos que no coinciden con el backup. Borrar el volumen (R3), probar con otro backup y avisar a quien mantiene el código. |
| Sigue sin andar | Guardar la salida completa del comando y consultar. No improvisar con la base. |
