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
- Los **cinco secretos** (`POSTGRES_PASSWORD`, `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `APP_BACKUP_DB_PASSWORD`, `JWT_SECRET`): **cada uno distinto**, generado así (imprime una clave aleatoria de 64 caracteres; repetir el comando cinco veces y pegar cada resultado en su línea):

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

Termina con una línea «Backup verificado» que dice archivo y tamaño. El archivo `distribuidora-AAAAMMDD-HHMMSS.dump` queda en la carpeta `BACKUP_DIR` del equipo (`C:\distribuidora\backups` o `/var/backups/distribuidora`), **fuera de los volúmenes de Docker**: sobrevive aunque se borren los volúmenes. Cada backup se verifica al generarse (se lista su contenido y deben estar las cuatro tablas de libro); si falla, el archivo pasa a `.fallido` y no se borra nada. Se conservan los últimos 7 válidos (`BACKUP_RETENCION`).

> Estos backups están **en el mismo equipo**. Hasta que exista la copia externa (change 27b) conviene copiar de vez en cuando la carpeta a un disco externo o a la nube. El procedimiento de restauración se documentará en `docs/runbook/restauracion.md` (change 27b).

### C8 Salud y registros

```bash
dc ps                       # estado de cada servicio
dc logs --tail 100 backend  # últimas 100 líneas del backend (también: caddy, postgres, backup, migraciones)
dc logs -f caddy            # seguir en vivo (Ctrl+C para salir)
```

Los registros rotan solos (no llenan el disco). `backup` pasa a «unhealthy» si el último backup válido tiene más de 26 horas, o si no hay ninguno pasada la primera hora programada.

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
- *Volver atrás:* `git checkout <commit-anterior>`, volver `APP_VERSION` al valor anterior, `dc build` y `dc up -d`. Las migraciones son compatibles hacia adelante, así que normalmente no hace falta restaurar la base; si hiciera falta, existe el backup previo (el procedimiento de restauración llega con el change 27b).

### C10 Crear el usuario de backup en una base que ya existía

El usuario de solo lectura `app_backup` se crea solo **la primera vez que se inicializa el volumen** de la base. Si la base ya existía antes de este change, hay que crearlo a mano una vez (sustituir `LA_CLAVE` por el valor de `APP_BACKUP_DB_PASSWORD` del archivo de entorno):

```bash
dc exec postgres psql -U distribuidora -d distribuidora -c "CREATE ROLE app_backup LOGIN PASSWORD 'LA_CLAVE'" -c "GRANT pg_read_all_data TO app_backup"
```

Si usó otros valores en `POSTGRES_USER` o `POSTGRES_DB`, usar esos. Después, `dc up -d backup`. (`pg_read_all_data` es un permiso predefinido de PostgreSQL que permite leer todo y nada más: el usuario de backup no puede modificar nada.)

### C11 Pasar del Escenario 1 (PC) al Escenario 2 (servidor)

No se cambia código: solo el archivo de entorno del servidor nuevo, con `DOMINIO` (el dominio) y `CADDY_TLS` (un correo). Pasos: preparar el servidor (Escenario 2), clonar el repositorio, armar su archivo de entorno con secretos nuevos y levantar con `dc up -d --build`. Los teléfonos dejan de usar el certificado de la PC (ya no hace falta) y entran por el dominio.

Mientras el entorno tenga solo datos de prueba, alcanza con sembrar de nuevo en el servidor (C6). Llevar los datos reales de la PC al servidor requiere restaurar un backup, procedimiento que se documenta con el change 27b.

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
| Let's Encrypt no emite el certificado (Escenario 2) | Ver E2.4 y `dc logs caddy`. |
