# Puesta en marcha en producción

Guía para poner el sistema a funcionar en un equipo real, actualizarlo y hacer backups. Está escrita para quien **nunca instaló una aplicación en un servidor**: cada término se explica la primera vez que aparece. Decisiones de fondo: ADR-071 y `docs/02-arquitectura.md` §16.2.

Hay dos formas de usarla:

- **Escenario 1: la PC de la oficina** (Windows con Docker Desktop). Es la que se usa ahora. Los teléfonos entran al sistema conectados al Wi-Fi de la oficina.
- **Escenario 2: un servidor alquilado (VPS) con un dominio** (por ejemplo `app.sudominio.com.ar`). Es la que se usará más adelante, para entrar también desde la calle.

Las dos usan **el mismo programa y el mismo archivo `docker-compose.prod.yml`**. Lo único que cambia es un archivo de configuración (el «archivo de entorno»).

Orden de lectura: primero los **Términos básicos**, después el **Escenario 1** (o el 2) y al final los **Pasos comunes**, que valen para los dos.

---

## Términos básicos

- **Servidor.** Una computadora que queda encendida y a la que otras (los teléfonos, otras PC) se conectan. Puede ser la PC de la oficina o una máquina alquilada por internet.
- **VPS.** Un servidor alquilado a una empresa (se paga por mes). Se maneja por una consola de texto remota.
- **Docker.** Programa que ejecuta aplicaciones «empaquetadas», así no hay que instalar a mano Python, PostgreSQL ni nada más. **Docker Desktop** es la versión para Windows.
- **Imagen.** El paquete cerrado con un programa y todo lo que necesita (como un instalador).
- **Contenedor.** Una imagen en funcionamiento. El sistema usa cinco: `postgres` (la base de datos), `migraciones` (prepara la base y termina), `backend` (la lógica del sistema), `caddy` (la «puerta de entrada» que atiende a los teléfonos) y `backup` (hace las copias de seguridad).
- **Docker Compose.** La herramienta que lee `docker-compose.prod.yml` (la «receta») y levanta los cinco contenedores juntos.
- **Volumen.** Un espacio de disco que Docker guarda aparte para que los datos **no se pierdan** al reiniciar o reconstruir un contenedor. La base de datos vive en el volumen `postgres_data`; los certificados de Caddy, en `caddy_data`. Borrar un volumen borra esos datos para siempre.
- **Archivo de entorno.** Un archivo de texto con la configuración y las contraseñas (`produccion.env`). **Nunca se sube a git ni se comparte**: el repositorio solo trae una plantilla vacía, `infra/produccion.env.example`.
- **Puerto.** La «puerta numerada» por la que entra un tipo de conexión. La web usa el **80** (sin candado) y el **443** (con candado, HTTPS). El sistema solo abre esos dos hacia afuera; la base de datos (5432) y el backend (8000) quedan cerrados.
- **Firewall.** El guardia que decide qué conexiones pueden entrar a un equipo. En Windows hay que decirle que deje pasar el 80 y el 443.
- **IP.** La dirección de un equipo en una red (por ejemplo `192.168.1.50`). **IP fija** es una que no cambia nunca; si cambiara, los teléfonos dejarían de encontrar la PC.
- **Router y reserva DHCP.** El router de la oficina reparte direcciones IP. Una «reserva DHCP» le dice: «a esta PC dale siempre la misma dirección». Así se consigue la IP fija sin tocar la configuración de Windows.
- **DNS y dominio.** El dominio (`app.sudominio.com.ar`) es el nombre; el DNS es la «guía telefónica» de internet que traduce el nombre a la IP del servidor. En el Escenario 2 se crea un registro **A** (nombre → IP).
- **HTTPS y certificado.** El candado del navegador: la conexión va cifrada y el navegador comprueba que habla con el sitio correcto. Eso lo garantiza un **certificado**, firmado por una **autoridad de certificación** (una «escribanía» en la que el navegador confía).
  - **Let's Encrypt:** autoridad pública y gratuita. Todos los teléfonos ya confían en ella. Se usa con un dominio real (Escenario 2).
  - **Autoridad propia de Caddy (`internal`):** Caddy se firma sus propios certificados. Sirve para una IP de la oficina, pero cada teléfono tiene que **instalar y aceptar una vez** el «certificado raíz» de Caddy (la firma de esa escribanía); si no, muestra un aviso de «conexión no segura». Se explica en el Escenario 1.
- **Terminal.** La ventana de texto donde se escriben comandos. En Windows se puede usar **PowerShell** o **Git Bash** (viene con Git). Cada comando de esta guía dice cuál usar cuando difieren; los que no lo aclaran sirven en ambos.
- **Repositorio.** La carpeta con el código del sistema (por ejemplo `C:\Proyecto_distribuidora`).

> La contraseña del administrador se pide sin mostrarla, para que no quede escrita en el historial del terminal ni en ningún archivo.

---

## Escenario 1: la PC de la oficina (Windows + Docker Desktop)

Configuración de este escenario: `CADDY_TLS=internal` y `DOMINIO` = la IP fija de la PC (por ejemplo `192.168.1.50`).

### E1.1 Que la PC se comporte como un servidor

1. **Docker Desktop que inicia con Windows.** Abrir Docker Desktop, ir a *Settings* (engranaje) → *General* y activar **Start Docker Desktop when you sign in to your computer**. Docker Desktop arranca cuando el usuario inicia sesión en Windows: la PC debe iniciar sesión sola tras un reinicio, o alguien debe entrar. Para que inicie sesión sola: tecla Windows, escribir `netplwiz`, desmarcar «Los usuarios deben escribir su nombre y contraseña» y poner la contraseña del usuario (solo conviene si la PC está en un lugar seguro de la oficina).
2. **Sin suspensión ni hibernación.** En PowerShell **como administrador**:

   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   ```

   (La pantalla sí puede apagarse.)
3. **Actualizaciones de Windows.** Windows reinicia solo para actualizarse. Conviene fijar el «horario activo» (*Windows Update* → *Opciones avanzadas*) fuera del horario de ventas. Tras un reinicio, Docker Desktop y los contenedores vuelven solos (tienen `restart: unless-stopped`); se tarda uno o dos minutos.
4. **IP fija por reserva DHCP.** Averiguar la dirección física (MAC) de la PC con `ipconfig /all` (línea «Dirección física» del adaptador que usa la PC: Wi-Fi o cable). Entrar a la página del router (suele ser `http://192.168.1.1`; el usuario y la clave suelen estar en la etiqueta del router), buscar «DHCP», «Reserva de direcciones» o «Asignación estática», y asignar a esa MAC una IP fuera del rango que el router reparte (por ejemplo `192.168.1.50`). Reiniciar la PC y comprobar con `ipconfig` que la IP quedó. Anotarla: es el valor de `DOMINIO`.
5. **Firewall de Windows para los puertos 80 y 443** (PowerShell **como administrador**, una sola vez):

   ```powershell
   New-NetFirewallRule -DisplayName "Distribuidora HTTP 80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
   New-NetFirewallRule -DisplayName "Distribuidora HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -Profile Private
   New-NetFirewallRule -DisplayName "Distribuidora HTTP/3 443 UDP" -Direction Inbound -Protocol UDP -LocalPort 443 -Action Allow -Profile Private
   ```

   `-Profile Private` abre los puertos **solo si la red está marcada como «Privada»**. Comprobarlo en *Configuración* → *Red e Internet* → *Wi-Fi* (o *Ethernet*) → la red de la oficina → «Tipo de perfil de red» = **Red privada**. Con «Pública», Windows seguiría bloqueando.
6. **Carpetas fuera del repositorio** (PowerShell):

   ```powershell
   New-Item -ItemType Directory -Force C:\distribuidora, C:\distribuidora\backups
   ```
7. **Proteger el archivo de entorno y la carpeta de backups** (después de crear el archivo en el paso C2). Esto quita los permisos heredados y deja acceso solo a su usuario (PowerShell):

   ```powershell
   icacls C:\distribuidora\produccion.env /inheritance:r /grant:r "${env:USERNAME}:(R,W)"
   icacls C:\distribuidora\backups /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F"
   ```

   Comprobar con `icacls C:\distribuidora\produccion.env`: debe figurar solamente su usuario. (En Windows, Docker no hace cumplir los permisos Linux `700`/`600` sobre carpetas compartidas: la protección es esta.)

### E1.2 Valores del archivo de entorno para este escenario

En el paso C2 se completa el archivo. Para la PC de la oficina:

```
DOMINIO=192.168.1.50
CADDY_TLS=internal
BACKUP_DIR=C:/distribuidora/backups
```

`192.168.1.50` es un ejemplo: poner la IP reservada en el paso E1.1.4. En `BACKUP_DIR` se usan barras comunes `/`.

Conviene ensayar primero en la propia PC con `DOMINIO=localhost`: el sistema se prueba entero sin depender de la red.

### E1.3 El certificado raíz de Caddy en los teléfonos

Con `CADDY_TLS=internal`, el candado lo firma la autoridad propia de Caddy. Cada teléfono debe **instalar y aceptar su certificado raíz una sola vez**. Hasta entonces, el navegador del teléfono avisa que la conexión no es segura.

**Exportar el certificado de la PC.** Con el sistema ya levantado (paso C5), en el terminal, desde la carpeta del repositorio (`dc` es el atajo del paso C3). El certificado raíz es el archivo `root.crt` que Caddy guarda en el volumen `caddy_data`, en `pki/authorities/local/root.crt`; dentro del contenedor está en `/data/caddy/pki/authorities/local/root.crt`.

```powershell
# PowerShell
dc cp caddy:/data/caddy/pki/authorities/local/root.crt C:\distribuidora\caddy-raiz.crt
```

```bash
# Git Bash (MSYS_NO_PATHCONV evita que Git Bash "traduzca" la ruta del contenedor)
MSYS_NO_PATHCONV=1 dc cp caddy:/data/caddy/pki/authorities/local/root.crt C:/distribuidora/caddy-raiz.crt
```

`caddy-raiz.crt` es un certificado **público**: no contiene claves privadas y puede enviarse por WhatsApp, correo o cable USB. Lo que **nunca** se comparte es la carpeta `pki/authorities/local/` completa (tiene la clave privada `root.key`).

Pasar `caddy-raiz.crt` al teléfono.

**Android** (los nombres varían según la marca):

1. Guardar el archivo en el teléfono (carpeta *Descargas*).
2. *Ajustes* → *Seguridad y privacidad* → *Más seguridad* (o *Otros ajustes de seguridad*) → *Cifrado y credenciales* → **Instalar un certificado** → **Certificado de CA**.
3. Android advierte que «tus datos personales pueden estar en riesgo»: es el aviso normal para certificados de CA propios. Elegir **Instalar de todos modos** y seleccionar `caddy-raiz.crt`. Si pide PIN o patrón, ingresarlo.
4. Abrir Chrome y entrar a `https://<IP-de-la-PC>/ruta`: no debe aparecer ningún aviso.

**iPhone** (dos pasos; el segundo es el que casi todos se olvidan):

1. Pasar el archivo al iPhone (AirDrop, correo o la app *Archivos*). Al abrirlo dice «Perfil descargado» (si viene por Safari, tocar **Permitir**).
2. *Ajustes* → arriba aparece **Perfil descargado** (o *General* → *VPN y administración de dispositivos*) → tocar el perfil de Caddy → **Instalar** → ingresar el código del iPhone → **Instalar** otra vez.
3. **Activar la confianza total:** *Ajustes* → *General* → *Información* → al final, **Ajustes de confianza de certificados** → activar el interruptor del certificado de Caddy («Caddy Local Authority …») → **Continuar**. Sin este paso el certificado queda instalado pero **no es de confianza** y Safari sigue avisando.
4. Abrir Safari y entrar a `https://<IP-de-la-PC>/ruta`: sin avisos.

> **Cuándo hay que repetirlo.** Si alguna vez se borra el volumen `caddy_data` (por ejemplo con `down -v`), Caddy crea una autoridad nueva y hay que volver a exportar e instalar el certificado en cada teléfono. Por eso `caddy_data` no se borra salvo que haya una razón clara.

### E1.4 Limitación: solo dentro de la red de la oficina

Con la PC como servidor, los teléfonos llegan al sistema **solo conectados al Wi-Fi de la oficina**. Esto no impide vender: la venta en ruta **funciona sin conexión** en el teléfono y se sincroniza sola al volver a la oficina.

Para que el sistema sea accesible desde la calle haría falta abrir los puertos 80 y 443 en el router hacia la PC (*port forwarding*, «reenvío de puertos») y contar con una IP pública fija o un servicio de DNS dinámico; o mudarse a un servidor con dominio (Escenario 2). **Esto está documentado pero no implementado**: no lo haga sin consultar, porque expone la PC a internet.

### E1.5 Limitación: toda la oficina cuenta como una sola «dirección» para el bloqueo de ingresos

El sistema se protege de quien prueba contraseñas al azar. Una de las protecciones es un límite por **IP** (la «dirección» de quien se conecta): si desde una misma IP hay **20 ingresos fallidos en 15 minutos**, el sistema rechaza los siguientes ingresos de esa IP hasta que pasen los 15 minutos.

En Docker Desktop para Windows hay una particularidad: todos los dispositivos (teléfonos y PCs) llegan al sistema con **la misma IP interna**. En la prueba se vio `172.30.10.1`, que es la «puerta de entrada» de la red interna de Docker. Para el sistema, entonces, **toda la oficina es una sola IP**, y los fallos de todos se suman en el mismo contador.

Qué se nota en la práctica:

- Si entre todos se acumulan 20 ingresos fallidos en 15 minutos, **nadie** puede ingresar por unos minutos, aunque escriba bien su contraseña.
- El botón de desbloquear de Administración levanta el bloqueo de **un usuario**, pero **no** el de la IP. Para el bloqueo por IP no hay botón: se resuelve solo cuando pasan 15 minutos desde el último fallo.
- Es poco probable en el uso normal (20 fallos son muchos), pero puede pasar si alguien reintenta muchas veces seguidas.

Qué hacer: esperar 15 minutos sin intentar de nuevo (cada intento fallido reinicia la cuenta). **No hace falta reiniciar nada ni tocar el servidor.**

En el Escenario 2 (servidor Linux) esto no pasa: el sistema ve la IP real de cada teléfono y cada uno cuenta aparte. No se cambia el umbral de 20 porque en ese escenario protege como debe.

---

## Escenario 2: servidor Linux (VPS) con dominio

Configuración de este escenario: `CADDY_TLS=<un correo>` y `DOMINIO=<el dominio>`. No depende del proveedor.

### E2.1 Requisitos

- **Servidor:** Ubuntu Server 24.04 LTS o Debian 12; mínimo 2 vCPU, 2 GB de RAM y 40 GB de disco.
- **Un dominio o subdominio** propio (por ejemplo `app.sudominio.com.ar`) y acceso al panel donde se administra su DNS.
- **Firewall** con solo estos puertos entrantes abiertos: **22** (acceso remoto), **80** y **443**. Con `ufw` (¡abrir el 22 antes de activarlo, o se pierde el acceso!):

  ```bash
  sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable
  ```
- **DNS:** crear un registro **A** que apunte el dominio (o subdominio) a la IP del servidor. Esperar a que propague (de unos minutos a unas horas) y comprobar con `nslookup app.sudominio.com.ar`: debe devolver la IP del servidor. **No levantar el sistema antes**: Let's Encrypt comprueba que el dominio apunta al servidor.

### E2.2 Instalar Docker

Seguir la guía oficial para su distribución: <https://docs.docker.com/engine/install/ubuntu/> (Ubuntu) o <https://docs.docker.com/engine/install/debian/> (Debian), incluido el complemento **Docker Compose**. Comprobar con `docker --version` y `docker compose version`. Instalar también git: `sudo apt install -y git`.

### E2.3 Archivo de entorno del servidor

Desde la carpeta del repositorio ya clonado (paso C1):

```bash
sudo mkdir -p /etc/distribuidora /var/backups/distribuidora
sudo chmod 700 /var/backups/distribuidora
sudo cp infra/produccion.env.example /etc/distribuidora/produccion.env
sudo chown root:root /etc/distribuidora/produccion.env
sudo chmod 600 /etc/distribuidora/produccion.env
sudo nano /etc/distribuidora/produccion.env
```

`chmod 600` deja el archivo legible solo para `root`. Completarlo según el paso C2, con:

```
DOMINIO=app.sudominio.com.ar
CADDY_TLS=sistemas@sudominio.com.ar
BACKUP_DIR=/var/backups/distribuidora
```

El correo recibe los avisos de vencimiento de Let's Encrypt.

### E2.4 Aviso: límite de Let's Encrypt

Let's Encrypt limita cuántos certificados entrega por dominio y por semana (hay cupo de sobra para uso normal, pero se agota si se repite el primer arranque muchas veces). Por eso:

- **Ensayar primero con `DOMINIO=localhost` y `CADDY_TLS=internal`** (no consume cupo).
- **No borrar `caddy_data`**: ahí quedan guardados los certificados ya emitidos.
- Si el primer arranque no consigue el certificado, mirar `dc logs caddy`: casi siempre es que el DNS todavía no apunta al servidor o que el puerto 80 o el 443 está cerrado.

Con el candado público de Let's Encrypt, los teléfonos **no instalan nada** y pueden entrar con datos móviles.

---

## Pasos comunes (valen para los dos escenarios)

### C1 Obtener el código (clonado)

Instalar [Git](https://git-scm.com/downloads) si no está. Elegir una carpeta (por ejemplo `C:\` en Windows, o su carpeta personal en Linux) y:

```bash
git clone <dirección-del-repositorio> Proyecto_distribuidora
cd Proyecto_distribuidora
git checkout <etiqueta-o-commit-a-desplegar>
```

(`<dirección-del-repositorio>` la da quien administra el código.) Los comandos siguientes se corren **siempre desde esa carpeta**.

### C2 Archivo de entorno y secretos

Copiar la plantilla **fuera** del repositorio (en Windows ya existe `C:\distribuidora`, paso E1.1.6; en Linux ya se hizo en E2.3):

```powershell
# PowerShell (Windows)
Copy-Item infra\produccion.env.example C:\distribuidora\produccion.env
notepad C:\distribuidora\produccion.env
```

Completar:

- `DOMINIO`, `CADDY_TLS` y `BACKUP_DIR`: según el escenario.
- `APP_VERSION`: tres números, por ejemplo `0.27.0`. **Si no tiene esa forma, el backend no arranca** (a propósito).
- Los **seis secretos** (`POSTGRES_PASSWORD`, `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `APP_BACKUP_DB_PASSWORD`, `APP_MANTENIMIENTO_DB_PASSWORD`, `JWT_SECRET`): **cada uno distinto**, generado así (imprime una clave aleatoria de 64 caracteres; repetir el comando seis veces y pegar cada resultado en su línea):

  ```bash
  # Git Bash o Linux
  openssl rand -hex 32
  ```

  ```powershell
  # PowerShell (si no tiene openssl)
  $b = New-Object byte[] 32; (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($b); ($b | ForEach-Object { $_.ToString('x2') }) -join ''
  ```

  Sin espacios alrededor del `=` ni comillas. Guardar una copia de las claves en un lugar seguro (un gestor de contraseñas). **Una vez creada la base, no se cambian en el archivo las contraseñas de PostgreSQL** (la base ya quedó con las originales). `JWT_SECRET` sí se puede cambiar, pero cierra las sesiones abiertas.
- `ADMIN_PASSWORD` **no** va en el archivo: se pide al sembrar (paso C6).

Después, en Windows, proteger el archivo (paso E1.1.7). Si falta un secreto, el sistema **no arranca y dice cuál falta**.

### C3 Un atajo para el comando de Docker Compose

Todos los comandos llevan `-f docker-compose.prod.yml --env-file <archivo>`. Para no escribirlo cada vez se define un atajo llamado `dc`:

```powershell
# PowerShell (Windows): vale para esta ventana
function dc { docker compose -f docker-compose.prod.yml --env-file C:\distribuidora\produccion.env @args }
```

```bash
# Git Bash (Windows)
dc() { docker compose -f docker-compose.prod.yml --env-file /c/distribuidora/produccion.env "$@"; }
```

```bash
# Linux (servidor)
dc() { sudo docker compose -f docker-compose.prod.yml --env-file /etc/distribuidora/produccion.env "$@"; }
```

Para que quede para siempre: en PowerShell, `notepad $PROFILE` y pegar la línea de la función; en Git Bash o Linux, pegarla al final de `~/.bashrc`. Si no está guardada, hay que volver a pegarla cada vez que se abre una ventana nueva.

### C4 Primer arranque

```bash
dc up -d --build
```

La primera vez descarga y construye todo (varios minutos). Hace, en este orden: levanta `postgres` (crea la base y sus usuarios, incluido el de solo lectura para los backups), corre `migraciones` (crea las tablas y termina), arranca `backend` y después `caddy`. Si falta una variable, se detiene al principio y nombra la que falta.

### C5 Comprobar que todo está sano

```bash
dc ps
```

Hay que ver `postgres`, `backend`, `caddy` y `backup` con estado **healthy** (sano). `migraciones` aparece como `Exited (0)`: está bien, hizo su trabajo y terminó. Las verificaciones de salud tardan hasta un minuto en pasar a «healthy».

Después, abrir en el navegador `https://<DOMINIO>/api/v1/salud`: debe responder `ok`. (En Windows, `curl` con `-w %{http_code}` puede imprimir `000` por cómo Windows maneja el certificado; usar el navegador o `curl -v`.) En el Escenario 1 con certificado `internal`, la propia PC todavía no confía en la autoridad de Caddy y el navegador mostrará un aviso: se puede continuar para este chequeo o instalar el certificado también en la PC (doble clic en `caddy-raiz.crt` → *Instalar certificado* → *Equipo local* → *Colocar todos los certificados en el siguiente almacén* → **Entidades de certificación raíz de confianza**).

### C6 Sembrar y primer ingreso

La siembra crea la organización inicial (nombre «Organización inicial», identificador `organizacion-inicial`) y el usuario `admin`. Se corre **una sola vez** (repetirla no pisa nada). La contraseña se pide sin mostrarla y no queda guardada en el historial ni en el archivo de entorno. Elegir una contraseña larga.

```powershell
# PowerShell (Windows)
$s = Read-Host -AsSecureString "Contraseña para admin"
$env:ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
dc run --rm -e ADMIN_PASSWORD backend python -m app.seed
Remove-Item Env:ADMIN_PASSWORD
```

```bash
# Git Bash o Linux
read -s -p "Contraseña para admin: " ADMIN_PASSWORD; echo
export ADMIN_PASSWORD
dc run --rm -e ADMIN_PASSWORD backend python -m app.seed
unset ADMIN_PASSWORD
```

Para ingresar: abrir `https://<DOMINIO>/admin`. En **Organización** escribir `organizacion-inicial`, usuario `admin` y la contraseña elegida. Desde allí se cambian el nombre y el CUIT de la organización (Configuración → Datos de la organización) y se crean los demás usuarios. El sistema arranca **sin datos de demostración**: usuarios, productos y clientes se cargan desde las pantallas o con la importación inicial.

Los vendedores entran por `https://<DOMINIO>/ruta` con la misma organización.

### C7 Primer backup a pedido y dónde verlo

El servicio `backup` hace uno todos los días a la hora `BACKUP_HORA` (por defecto 03:00, zona `TZ`). Para hacer uno ahora:

```bash
dc run --rm backup ahora
```

**Recomendado justo después de instalar:** ejecutar este comando una vez, así hay un backup desde el primer día (si no, el primero lo hace el servicio recién a la hora programada).

Termina con una línea «Backup verificado» que dice archivo y tamaño. El archivo `distribuidora-AAAAMMDD-HHMMSS.dump` queda en la carpeta `BACKUP_DIR` del equipo (`C:\distribuidora\backups` o `/var/backups/distribuidora`), **fuera de los volúmenes de Docker**: sobrevive aunque se borren los volúmenes. Cada backup se verifica al generarse (se lista su contenido y deben estar las cuatro tablas de libro); si falla, el archivo pasa a `.fallido` y no se borra nada. Se conservan, de los backups válidos, **el más reciente de cada uno de los últimos 14 días que tienen backup y de cada una de las últimas 8 semanas** (lunes a domingo): en total, hasta unos 20 archivos distintos. Las cantidades se cambian con `BACKUP_DIARIOS` (14) y `BACKUP_SEMANALES` (8) en el archivo de entorno; antes se usaba `BACKUP_RETENCION`, que ya no existe. Nunca se borra por el solo paso del tiempo: si los backups se detienen, los que hay se quedan.

**Usuario de los servicios de respaldo.** Los servicios `backup`, `copia-externa`, `prueba-restauracion` y `restauracion` no corren como administrador del sistema sino con un usuario sin privilegios (`BACKUP_UID`/`BACKUP_GID`, por defecto 999). Para qué: si alguno fuera vulnerado, no podría tocar el resto del equipo. En **Windows con Docker Desktop**, una carpeta de backups **nueva** no necesita nada. Pero una carpeta que **ya existía de la versión 0.27.x (27a)** guarda permisos puestos por el usuario administrador de entonces, y los servicios nuevos no pueden escribir ni borrar en ella: el backup falla con `Permission denied` sobre `/backups`. Se arregla **una sola vez** (cambiar `C:/distribuidora/backups` si `BACKUP_DIR` es otra carpeta; en Git Bash anteponer `MSYS_NO_PATHCONV=1`):

```powershell
docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b
```

Cubre también los backups viejos, para que la retención y la prueba de restauración puedan leerlos y borrarlos. En **Linux**, la carpeta de backups tiene que pertenecerle a ese usuario, o los servicios no pueden escribirla (el equivalente de lo anterior, con la carpeta del equipo):

```bash
sudo mkdir -p /var/backups/distribuidora/bajados
sudo chown 999:999 /var/backups/distribuidora /var/backups/distribuidora/bajados
```

> Estos backups están **en el mismo equipo**: si se pierde o se rompe la PC, se pierden con ella. Por eso existe la **copia externa** (paso C7b). La restauración, la prueba mensual y la mudanza a otro equipo están en [`restauracion.md`](restauracion.md).

### C7b Copia externa de los backups

El servicio `copia-externa` sube cada backup válido, **cifrado en la PC antes de salir**, a un almacenamiento en internet. Para qué: que un incendio, un robo o un virus en la PC no se lleven también los backups. Es la única forma de que el negocio sobreviva a perder el equipo. Se hace una sola vez, y lleva unos 20 minutos:

1. **Abrir una cuenta de almacenamiento compatible con S3** (el proveedor elegido es Backblaze B2; sirve cualquiera que diga «compatible con S3»). Esta cuenta la abre y la paga el dueño del negocio.
2. **Crear un cubo** («bucket», una carpeta de nivel superior) **privado**, y una **clave de acceso limitada a ese cubo** (el proveedor da dos valores: el identificador y la clave secreta). Limitada significa que, si alguien la roba, solo alcanza esos archivos (que además están cifrados). Anotar también la dirección del servicio (`endpoint`, por ejemplo `https://s3.us-west-004.backblazeb2.com`) y la región.
3. **Inventar dos frases largas y distintas** (la de la clave de cifrado y la de la «sal», un segundo ingrediente del cifrado) y **ofuscarlas** con `rclone obscure` (el archivo de entorno no guarda la frase en claro). Para cada una:

   ```bash
   docker run --rm --entrypoint rclone rclone/rclone:1.68.2 obscure "su frase larga"
   ```

   El resultado (una cadena rara) va a `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO` respectivamente. **Una vez que hay copias, no se cambian**: las copias ya hechas quedarían ilegibles.
4. **Completar el archivo de entorno** con: `COPIA_TIPO=s3`, `COPIA_RUTA` (nombre del cubo, opcionalmente `cubo/carpeta`), `COPIA_S3_ENDPOINT`, `COPIA_S3_REGION`, `COPIA_S3_PROVEEDOR` (si el proveedor tiene un nombre propio en rclone; si no, queda `Other`), `COPIA_ACCESS_KEY_ID`, `COPIA_SECRET_ACCESS_KEY`, `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO`. Sin la clave de cifrado el sistema no arranca el servicio (a propósito: una copia sin cifrar nunca sale).
5. **Guardar la hoja de recuperación fuera de la PC**: estos mismos valores, copiados a un gestor de contraseñas o a un sobre en poder del dueño (ver `restauracion.md`). **Sin las dos claves de cifrado las copias no se pueden leer.**
6. **Primera copia y cómo verla.** Con el sistema levantado (`dc up -d --build`):

   ```bash
   dc run --rm copia-externa ahora
   ```

   Termina con líneas «Copia externa verificada: archivo=… tamano=…» (una por backup subido; cada una se bajó y se comparó con el original). En la consola del proveedor se ve que **los archivos están pero con nombres sin sentido**: eso es el cifrado. Después la subida es automática, cada hora, y solo sube lo que falta.

**Qué se conserva en el destino.** La misma regla que en la PC (14 diarios y 8 semanales), calculada sobre lo que hay en el destino. Borrar archivos de la PC **no** borra nada del destino, y si el destino no responde la copia espera y reintenta sin borrar nada.

**Ensayar sin cuenta (destino local).** Para probar sin abrir cuenta: `COPIA_TIPO=local`, `COPIA_RUTA=/destino-local/copias`, y `no-aplica` en `COPIA_ACCESS_KEY_ID` y `COPIA_SECRET_ACCESS_KEY` (no pueden quedar vacías). `COPIA_LOCAL_DIR` es la carpeta de la PC que hace de destino (si se deja `copia_local`, es un volumen de Docker). No protege de perder la PC.

**Aviso por correo (opcional).** Si `AVISO_URL` tiene una dirección (por ejemplo la de un control gratuito de «hombre muerto» como healthchecks.io), `copia-externa` la llama después de cada corrida buena, y a `<dirección>/fail` si falla; si no la reciben a tiempo, el servicio les manda un correo al dueño. Vacía, no se avisa nada. No se envía ningún dato del negocio. La verificación diaria (`tareas`) tiene su propio aviso, con otra variable (`AVISO_TAREAS_URL`, ver C13). La prueba mensual de restauración **no** avisa: no tiene red (ver C8).

### C8 Salud y registros

```bash
dc ps                       # estado de cada servicio
dc logs --tail 100 backend  # últimas 100 líneas del backend (también: caddy, postgres, backup, migraciones)
dc logs -f caddy            # seguir en vivo (Ctrl+C para salir)
```

Los registros rotan solos (no llenan el disco). `backup` pasa a «unhealthy» si el último backup válido tiene más de 26 horas, o si no hay ninguno pasada la primera hora programada. `copia-externa` pasa a «unhealthy» si el backup más reciente que hay en el destino tiene más de 26 horas, o si la última corrida falló por credenciales o por la clave (un corte de internet por sí solo no lo marca). `prueba-restauracion` pasa a «unhealthy» si la última prueba falló o pasaron más de 35 días sin una buena.

`tareas` pasa a «unhealthy» si la última verificación de consistencia encontró diferencias, si la última corrida falló, o si pasaron más de 26 horas sin ninguna corrida (ver C13).

**Revisión semanal (dos minutos).** Una vez por semana correr `dc ps` y comprobar que `backup`, `copia-externa`, `prueba-restauracion` y `tareas` dicen `healthy`. Es **la única señal de la prueba mensual** (no manda avisos, porque corre sin red): si nadie mira, un fallo puede pasar semanas sin que se note. Qué hacer si alguno falla: `restauracion.md`, sección «Si algo no funciona».

> **Hora de gracia.** Recién instalado, `backup` figura como «healthy» aunque todavía no haya hecho ningún backup: no pasa a «unhealthy» hasta que haya transcurrido una hora desde la primera hora programada (`BACKUP_HORA`). Un «healthy» del primer día **no** prueba que haya un backup; por eso conviene hacer uno a pedido (C7) apenas se instala.

Comandos del día a día:

```bash
dc stop          # detiene todo sin borrar nada
dc start         # lo vuelve a iniciar
dc restart backend
```

> **No usar `dc down -v`**: la opción `-v` **borra los volúmenes**, es decir, la base de datos y el certificado raíz de Caddy. `dc down` (sin `-v`) detiene y quita los contenedores pero conserva los datos.

### C9 Actualizar a una versión nueva

Los mismos pasos en la PC y en el servidor. Hay un corte de unos segundos mientras se reemplaza el backend (los teléfonos reintentan solos).

La clave es **migrar antes de reemplazar**: primero se aplican las migraciones con la imagen nueva mientras la versión vieja sigue atendiendo, y recién si salieron bien se reemplazan `backend` y `caddy`. Las migraciones son compatibles hacia adelante (`docs/02-arquitectura.md` §14): el backend viejo funciona con el esquema ya migrado.

1. **Backup previo:** `dc run --rm backup ahora` y comprobar que dice «Backup verificado».
   **Si el entorno es anterior al change 28** (no tiene el usuario `app_mantenimiento`), antes del paso de migrar hay que crearlo una vez: ver C12. Sin él, las migraciones se niegan a correr y lo dicen.
2. **Traer la versión nueva:**

   ```bash
   git fetch
   git checkout <etiqueta-o-commit-nuevo>
   ```
3. **Cambiar `APP_VERSION`** en el archivo de entorno al número nuevo (por ejemplo de `0.27.0` a `0.28.0`).
4. **Construir las imágenes nuevas** (no cambia nada de lo que está corriendo):

   ```bash
   dc build
   ```
5. **Migrar con la imagen nueva** (el backend viejo sigue funcionando):

   ```bash
   dc run --rm migraciones
   ```

   Es una corrida única: crea un contenedor temporal que aplica las migraciones y se borra solo (`--rm`). Solo arranca `postgres` si hiciera falta; no toca `backend` ni `caddy`. Una salvedad: si en el archivo de entorno cambió alguna variable que usa `postgres` (por ejemplo una contraseña de base), Compose recrea también `postgres` y hay un corte de unos segundos; en una actualización normal esas variables no cambian. Si termina sin errores, seguir. **Si muestra un error, no pasar al paso 6** (ver «Si las migraciones fallan»).
6. **Reemplazar backend y caddy:**

   ```bash
   dc up -d
   ```
7. **Verificar:** `dc ps` (todo sano) y abrir `https://<DOMINIO>/api/v1/version`: debe mostrar la versión nueva. Entrar a `/admin` y comprobar que los datos siguen.

**Si las migraciones fallan** (el paso 5 termina con error). La versión vieja sigue funcionando: todavía no se reemplazó nada. Leer el error que imprime la propia corrida (o `dc logs migraciones`), corregir la causa (por ejemplo, una contraseña mal escrita en el archivo de entorno) y repetir desde el paso 5. **No ejecutar `dc up -d` hasta que el paso 5 termine bien**: `up -d` reemplaza `backend` y `caddy` aunque `migraciones` falle, y el sistema queda caído.

**Si el sistema quedó caído** (por ejemplo, alguien ejecutó `dc up -d` y `migraciones` falló: `backend` y `caddy` figuran como `Created` y la dirección `/api/v1/version` no responde). Hay dos salidas:

- *Corregir y seguir adelante:* arreglar la causa (por ejemplo el archivo de entorno), comprobar con `dc run --rm migraciones` y ejecutar `dc up -d`.
- *Volver atrás:* `git checkout <commit-anterior>`, volver `APP_VERSION` al valor anterior, `dc build` y `dc up -d`. Las migraciones son compatibles hacia adelante, así que normalmente no hace falta restaurar la base; si hiciera falta, existe el backup previo (el procedimiento está en [`restauracion.md`](restauracion.md)).

#### Actualizar desde 0.27.x (27a)

Además de los pasos anteriores, quien actualiza desde la versión 27a hace **una sola vez** esto (antes del paso 6):

1. **Permisos de la carpeta de backups** (si no, `dc run --rm backup ahora` falla con `Permission denied`). En Windows: `docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b`. En Linux: `sudo chown -R 999:999 <BACKUP_DIR>`.
2. **Retención:** en el archivo de entorno, reemplazar `BACKUP_RETENCION` (ya no existe) por `BACKUP_DIARIOS` (14) y `BACKUP_SEMANALES` (8).
3. **Variables nuevas:** las `COPIA_*` (copia externa, paso C7b; `COPIA_CLAVE_CIFRADO` y `COPIA_SAL_CIFRADO` con valores reales, no el texto de ejemplo) y las `PRUEBA_*` (prueba mensual), copiándolas de `infra/produccion.env.example`.
4. **Crear la subcarpeta `bajados`** dentro de `BACKUP_DIR` (en Linux, con dueño 999).
5. **Levantar construyendo:** `dc up -d --build` (hay servicios nuevos que construir), y comprobar con `dc ps`.

### C10 Crear el usuario de backup en una base que ya existía

El usuario de solo lectura `app_backup` se crea solo **la primera vez que se inicializa el volumen** de la base. Si la base ya existía antes de este change, hay que crearlo a mano una vez (sustituir `LA_CLAVE` por el valor de `APP_BACKUP_DB_PASSWORD` del archivo de entorno):

```bash
dc exec postgres psql -U distribuidora -d distribuidora -c "CREATE ROLE app_backup LOGIN PASSWORD 'LA_CLAVE'" -c "GRANT pg_read_all_data TO app_backup"
```

Si usó otros valores en `POSTGRES_USER` o `POSTGRES_DB`, usar esos. Después, `dc up -d backup`. (`pg_read_all_data` es un permiso predefinido de PostgreSQL que permite leer todo y nada más: el usuario de backup no puede modificar nada.)

### C11 Pasar del Escenario 1 (PC) al Escenario 2 (servidor)

No se cambia código: solo el archivo de entorno del servidor nuevo, con `DOMINIO` (el dominio) y `CADDY_TLS` (un correo). Pasos: preparar el servidor (Escenario 2), clonar el repositorio, armar su archivo de entorno con secretos nuevos y levantar con `dc up -d --build`. Los teléfonos dejan de usar el certificado de la PC (ya no hace falta) y entran por el dominio.

Mientras el entorno tenga solo datos de prueba, alcanza con sembrar de nuevo en el servidor (C6). Llevar los datos reales de la PC al servidor requiere restaurar un backup: el procedimiento completo está en la sección «Mudanza a otro equipo» de [`restauracion.md`](restauracion.md). Lo más importante, antes de mudarse: **la cola de cada teléfono tiene que estar vacía** (la cola pertenece a la dirección vieja y no se ve desde la nueva).

### C12 Crear el usuario de mantenimiento en una base que ya existía

**Para qué sirve.** Desde el change 28 hay un servicio nuevo, `tareas`, que una vez por día revisa que los saldos coincidan con los movimientos y borra los intentos de inicio de sesión de más de 24 horas. Para hacerlo usa un usuario de base **propio**, `app_mantenimiento`, que puede leer los saldos, anotar el resultado de la revisión y borrar solo esos intentos viejos; no puede tocar nada más. El usuario con el que corre el sistema (`app_runtime`) sigue sin poder borrar nada: por eso este trabajo no se le da a él.

**Cuándo hace falta.** En un entorno **nuevo** (volumen de la base recién creado) el usuario se crea solo. En un entorno que **ya existía**, hay que crearlo a mano **una sola vez y ANTES de migrar** (paso 5 de C9): las migraciones le otorgan sus permisos y, si el usuario no existe, se detienen con un mensaje que apunta a este paso (y la base queda como estaba).

1. **Agregar la clave** al archivo de entorno: una línea `APP_MANTENIMIENTO_DB_PASSWORD=` con una clave nueva generada como en C2 (`openssl rand -hex 32`). Es distinta de las otras cinco. Para qué: es la contraseña con la que `tareas` entra a la base.
2. **Crear el usuario** (sustituir `LA_CLAVE` por ese mismo valor). La contraseña viaja como variable de `psql` (`-v clave=...`) y no pegada dentro del texto SQL, así queda bien escrita aunque tenga caracteres raros:

   ```bash
   dc up -d postgres
   echo "CREATE ROLE app_mantenimiento LOGIN PASSWORD :'clave'" | dc exec -T postgres psql -U distribuidora -d distribuidora -v clave=LA_CLAVE
   ```

   Si usó otros valores en `POSTGRES_USER` o `POSTGRES_DB`, usar esos. Debe imprimir `CREATE ROLE`. Si dice que el usuario ya existe, no hace falta repetirlo.
3. **Seguir con la actualización** (C9, desde el paso 5: `dc run --rm migraciones`) y después `dc up -d --build`, que levanta el servicio `tareas`.

Si olvidó este paso, `dc run --rm migraciones` termina con un error que nombra a `app_mantenimiento`: no se rompió nada; crear el usuario y repetir el paso.

### C13 El servicio `tareas`: la verificación diaria y cómo leerla

**Qué hace.** Todos los días a `TAREAS_HORA` (por defecto `05:00`, en la zona `TZ`; elegida después del backup de las 03:00 y de la prueba de restauración de las 04:00) hace dos cosas: (1) compara, para cada organización, los saldos de cuentas, el stock y el costo promedio contra los movimientos que los explican, y guarda el resultado; (2) borra los intentos de inicio de sesión de más de 24 horas. **Nunca corrige nada:** una diferencia significa que hay un defecto que alguien debe investigar.

**Verificación a pedido** (para comprobar ahora mismo, sin esperar a las 05:00):

```bash
dc run --rm tareas ahora
```

Lo normal es leer:

```text
Verificación de consistencia: sin diferencias
Limpieza: 12 intentos de inicio de sesión de más de 24 horas borrados
```

Si hay diferencias, la primera línea dice cuántas y recuerda «avisar a soporte». El detalle (qué cuenta, producto o ubicación, con el valor guardado y el recalculado) se ve en el inicio de `/admin` como administrador o personal de Administración; también queda en el registro: `dc logs tareas`.

**Qué hacer ante el aviso de diferencias.** Regla: **no corregir a mano** (ni tocar la base, ni cargar un ajuste «para que cierre»): corregir tapa el síntoma y borra la pista de qué falló. Anotar la fecha y el detalle que muestra `/admin` y avisar a soporte. El aviso desaparece solo cuando la siguiente verificación da sin diferencias.

**Variables** (en el archivo de entorno): `TAREAS_HORA` (formato `HH:MM`), `TZ` (zona horaria) y `AVISO_TAREAS_URL` (opcional: el aviso por correo, que se explica abajo). **No es la misma que `AVISO_URL`**: esa es de la copia externa (C7b). Cada una tiene su propio control en healthchecks.io.

**Aviso por correo si la verificación no corre o encuentra diferencias (recomendado).** Las señales locales (el aviso en `/admin`, `dc logs tareas` y el estado `unhealthy` de `dc ps`) solo se ven si alguien mira. Para que le llegue un correo, se usa un servicio gratuito de «hombre muerto» (*dead man's switch*): `tareas` le avisa «estoy bien» después de cada corrida, y si el servicio **deja de recibir ese aviso a tiempo** (el equipo se apagó, el servicio se cayó, no hay internet) o recibe un aviso de falla, le manda un correo. Pasos:

1. Crear una cuenta gratuita en `https://healthchecks.io` con su correo y confirmarlo.
2. Crear un control nuevo (*Add Check*) y ponerle de nombre **Verificación diaria**. En *Period* (cada cuánto esperan el aviso) poner **1 day** y en *Grace Time* (cuánto esperan antes de dar la alarma) unas **2 hours**. En *Integrations* dejar tildado su correo.
3. El control muestra una dirección de aviso (*ping URL*), parecida a `https://hc-ping.com/…`. Copiarla **completa**: es secreta (quien la tenga puede mandar avisos falsos), así que no se comparte ni se pega en chats.
4. Pegarla en el archivo de entorno, en la línea `AVISO_TAREAS_URL=` (sin comillas), y aplicar:

   ```bash
   dc up -d
   ```

5. Probar sin esperar a las 05:00. La prueba **también avisa** (igual que la corrida programada):

   ```bash
   dc run --rm tareas ahora
   ```

   En healthchecks.io el control **Verificación diaria** pasa a verde («up») en unos segundos. Si no pasa, ver «Si el control no se pone verde» abajo.

**Qué hace `tareas` con el aviso.** Después de cada corrida: si no hubo diferencias y la limpieza no falló, llama a la dirección (control en verde); si hubo diferencias o algo falló, llama a `<dirección>/fail` (el control se pone en rojo y llega un correo enseguida). Con `AVISO_TAREAS_URL` vacía no avisa nada. No se envía ningún dato del negocio. Un aviso que no llega **no rompe nada**: la verificación y su resultado son los mismos, y solo queda una línea en `dc logs tareas` («No se pudo llamar al aviso externo»; no muestra la dirección).

**Qué correo llega y qué hacer.**

- **Falla o diferencias** (correo «DOWN», o el control en rojo): es el mismo caso que el aviso de diferencias de arriba; seguir esa regla (no corregir a mano, anotar y avisar a soporte).
- **Falta de aviso** (correo «DOWN» sin que haya habido diferencias, pasadas las 2 horas de gracia): la verificación no corrió. Revisar que el equipo esté encendido y con internet, `dc ps` (¿`tareas` está `healthy`?) y `dc logs tareas`.
- Cuando la siguiente corrida da bien, el control vuelve a verde solo.

**Si el control no se pone verde.** Correr `dc logs tareas` y buscar «No se pudo llamar al aviso externo». Causas habituales: la dirección está mal copiada (probar de nuevo desde healthchecks.io), el equipo no tiene internet, o se olvidó correr `dc up -d` después de editar el archivo de entorno.

**Por qué `tareas` puede salir a internet.** `tareas` está en la red `datos` (la de la base, que **no** tiene salida a internet) y además en la red `salida`, la misma de `copia-externa`: esa red tiene internet pero no ve ni la base ni el backend, y no abre ningún puerto hacia adentro; `tareas` la usa solo para llamar al aviso. La base y la red `datos` siguen cerradas. Decisión: ADR-073.

### C14 Correr la suite de aceptación (`npm run test:e2e`)

**Para qué sirve.** Recorre automáticamente los 12 criterios de aceptación de la etapa 1 (`docs/00-vision-y-alcance.md` §9) contra una copia completa del sistema: sirve para comprobar, antes de entregar una versión, que todo funciona junto (incluida la venta sin señal).

**Qué hace por su cuenta.** Levanta una copia del sistema **aparte** llamada `distribuidora-aceptacion` (base nueva, con datos de prueba, en HTTPS), corre el navegador contra ella y al terminar la **borra con sus datos**. No toca el entorno de desarrollo ni el de producción. Hace falta tener instalados Node.js y Docker.

```bash
cd frontend
npm install
npx playwright install chromium   # una sola vez
npm run test:e2e
```

Tarda varios minutos. Conviene detener el entorno de desarrollo (`docker compose -p distribuidora stop`) para no quedarse sin memoria. Si falla una prueba, deja una traza en `frontend/test-results` y un informe en `frontend/playwright-report` (`npx playwright show-report`). Para dejar la copia levantada y mirarla: `npm run test:e2e:mantener` (después hay que bajarla a mano con `docker compose -p distribuidora-aceptacion down -v`). La misma suite corre sola en GitHub cuando se actualiza la rama principal.

---

## Si algo no funciona

| Síntoma | Qué mirar |
| --- | --- |
| `dc up` se detiene con «Falta … en el archivo de entorno» | Esa variable está vacía o falta en `produccion.env`. |
| El backend no arranca y `dc logs backend` dice «APP_VERSION…» o «JWT_SECRET debe tener al menos 32 caracteres» | `APP_VERSION` debe ser `X.Y.Z` y `JWT_SECRET` tener 32 o más caracteres. |
| Docker avisa que el puerto 80 o 443 está ocupado | Hay otro programa usándolo (por ejemplo el entorno de desarrollo con `docker compose` en la misma PC). Detenerlo y reintentar. |
| El teléfono muestra «conexión no segura» | Falta instalar o aceptar el certificado raíz (E1.3), o la fecha del teléfono está mal. |
| El teléfono no llega al sistema | Comprobar que está en el Wi-Fi de la oficina, que la IP de la PC no cambió (`ipconfig`) y las reglas del firewall (E1.1, paso 5). |
| Tras reiniciar Windows el sistema no responde | Docker Desktop debe estar iniciado (ícono de la ballena en la barra); esperar uno o dos minutos y `dc ps`. |
| `curl` en Windows imprime `000` | Es el manejo del certificado en Windows; usar el navegador o `curl -v`. |
| `dc run --rm backup ahora` falla con `Permission denied` sobre `/backups` | La carpeta de backups quedó con permisos de la versión 27a. Una sola vez: `docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b` (Linux: `sudo chown -R 999:999 <BACKUP_DIR>`). Ver C7. |
| `dc run --rm migraciones` falla nombrando a `app_mantenimiento` | Falta crear el usuario de mantenimiento en una base que ya existía: ver C12. |
| `tareas` figura «unhealthy» | Hay diferencias de consistencia, la última corrida falló o pasaron más de 26 horas sin corrida: ver C13 y `dc logs tareas`. |
| El control «Verificación diaria» de healthchecks.io no se pone verde | La dirección de `AVISO_TAREAS_URL` está mal copiada, falta `dc up -d` o no hay internet: ver C13 («Si el control no se pone verde») y `dc logs tareas` |
| Let's Encrypt no emite el certificado (Escenario 2) | Ver E2.4 y `dc logs caddy`. |
