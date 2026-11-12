# Diseño técnico — 27b-backups-y-runbook-completo

> **Estado: APROBADO 2026-11-08 (tarea 0.1): opción (A) en D0–D16; D3 Backblaze B2 con la cuenta a abrir más adelante; D13 fuera de alcance (acceso desde la calle → VPS). Q1–Q3 siguen abiertas.**
>
> *Texto original:* **Estado: PROPUESTO, esperando aprobación (tarea 0.1).** Las opciones marcadas **(A)** son las recomendadas. Nada se implementa antes de la aprobación. Las decisiones se documentarán en **ADR-072** (*Propuesto*, `docs/adr/ADR-072-backups-completos-copia-externa-y-restauracion.md`).
>
> **Gobernanza.** Dominio **ALTO** (backups y restauración de datos de usuarios): nada se escribe antes de la aprobación. **CRÍTICAS:** D3 (adónde salen los datos del negocio), D13 (exponer o no la PC a internet). **ALTAS:** D1, D2, D4, D5, D7, D8, D12. **MEDIAS:** D6, D9, D10, D11, D14, D16. **BAJAS:** D0, D15. **De negocio u operativas** (el agente solo recomienda; decide el usuario): **D3, D7, D10, D12, D13, D14**. Las que más conviene mirar: **D3**, **D5**, **D7**, **D12**, **D13**.
>
> **Para el usuario (lenguaje llano).** Cada decisión dice primero **para qué sirve**. Glosario corto: *backup* = una foto completa de la base en un archivo; *restaurar* = volver a cargar esa foto en una base; *almacenamiento externo* = un lugar fuera de la PC (un servicio en internet) donde guardar copias; *cifrar* = ponerle un candado al archivo: sin la clave nadie puede leerlo, ni el proveedor; *retención* = cuántos backups viejos se guardan antes de borrarlos.
>
> **Sin textos de interfaz nuevos** (no hay pantallas) y **sin ayuda contextual** (ADR-051: «no aplica»). Sin migración de Alembic, sin cambios de API, sin Dexie.
>
> **Revisión.** Decisiones (0.1) antes del apply. Después, el usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Lo que dejó el 27a y este change **reutiliza sin romper** (ver `openspec/specs/sistema/respaldos`, `sistema/despliegue` y ADR-071):

- **`infra/backup/`** (imagen sobre `postgres:17`): `programar.sh` (bucle diario a `BACKUP_HORA` en `TZ`; `ahora` para un backup a pedido; función `segundos_hasta_proxima` probada aislada con `PROGRAMAR_SOLO_FUNCIONES=1`), `respaldar.sh` (`pg_dump -Fc` a `.tmp` → `pg_restore --list` con las cuatro tablas de libro → `.dump` o `.dump.fallido` → retención de los últimos `BACKUP_RETENCION=7`), `salud.sh` (no sano si el último `.dump` tiene más de 26 horas). Nombre `distribuidora-AAAAMMDD-HHMMSS.dump` (hora local de `TZ`).
- **Servicio `backup`** en `docker-compose.prod.yml`: red `datos` (**interna, sin salida a internet**), rol `app_backup` (`pg_read_all_data`), `BACKUP_DIR` del equipo montado en `/backups`, **corre como root** (limitación aceptada en el 27a, a endurecer aquí).
- **Roles (ADR-020, ADR-071):** `app_migrations` es dueño del esquema `public` (sin extensiones en las migraciones: comprobado, ningún `CREATE EXTENSION`), `app_runtime` recibe permisos tabla por tabla (sin `UPDATE`/`DELETE` en libros, INV-05), `app_backup` solo lee. Los roles son globales del servidor: `pg_dump` de la base **no** los incluye, sí incluye dueños y `GRANT`.
- **Pruebas** en `backend/tests/infra/` con Testcontainers (`conftest.py`: base migrada y con datos, imagen de backup, `Corredor`), en CI en el trabajo de integración.
- **Runbook** `docs/runbook/puesta-en-marcha.md`: C7 dice «Se conservan los últimos 7» y remite a `restauracion.md`; C11 dice que llevar los datos de la PC al servidor «se documenta con el change 27b».
- **Entorno real:** PC de Windows con Docker Desktop, `CADDY_TLS=internal`, `DOMINIO` = IP de la red local, carpeta de backups `C:\distribuidora\backups`. Los teléfonos guardan su cola y su sesión en IndexedDB, que **depende del origen** (`https://<IP>` y `https://<dominio>` son orígenes distintos).

Lo que `docs/` **ya decide** y no se reabre: 14 diarios y 8 semanales y copia a almacenamiento externo (`02` §16.2; `04` §12); backup diario (`02` §16.2); restauración probada en un entorno separado antes de salir a producción y luego al menos una vez por mes (`02` §16.2; `00` §9 criterio 12); «monitoreo avanzado» fuera de la etapa 1 (`00` §6). Lo que `docs/` **no** resuelve: D0 a D16.

## Goals / Non-Goals

**Goals:** perder la PC no pierde los datos; nadie fuera de la distribuidora puede leer las copias externas; la retención nunca deja al sistema sin backups; restaurar es una orden con barandas (no pisa una base con datos); la prueba mensual ocurre sola y se ve si falla; la mudanza a un VPS está escrita y ensayada; todo lo que se puede probar, probado automáticamente.

**Non-Goals:** PITR, réplicas, más de un backup por día; alertas propias más allá del aviso opcional (D14); exponer la PC a internet (D13 A); contratar VPS, dominio o almacenamiento (decisión y pago del usuario); restaurar parcialmente una tabla o una organización.

## Decisions

### D0 — Alcance y lotes · alcance · BAJA · `04` §2, §12

*Para qué:* cuántas partes tiene el trabajo y en qué orden.

- **A (recomendada). Un change en cuatro lotes**, un subagente por lote, en secuencia, sin revisión entre lotes: **Lote 1** retención 14 + 8 y contenedores no root (D1, D11); **Lote 2** copia externa (D2, D4, D5, D6, D14); **Lote 3** restauración y prueba periódica (D8, D9, D10); **Lote 4** runbooks (D12, D15), ADR, `propuesta-docs.md`, CI, suites. Después, la prueba manual del usuario.
- **B. Dos changes:** `27b` (retención y restauración) y `27c` (copia externa). Consecuencia: la copia externa, que es lo que protege de perder la PC, se demora un change más.

### D1 — Cómo se cuentan los 14 diarios y los 8 semanales · operativa · ALTA · `02` §16.2

*Para qué:* decidir qué backups viejos se borran. Borrar mal es perder la posibilidad de volver atrás.

- **A (recomendada). Por días y semanas que tienen backup, sin día fijo.** Después de cada backup verificado, se conservan: el backup válido **más reciente de cada uno de los 14 días más recientes que tienen backup**, y el **más reciente de cada una de las 8 semanas más recientes que tienen backup** (semana de lunes a domingo, en la hora local de `TZ`). Un mismo archivo puede contar como diario y como semanal (máximo 22 archivos). El día y la semana salen **del nombre del archivo**, no de la fecha de modificación (que cambia al copiar). Solo se borran `.dump` con el formato de nombre, y solo después de un backup verificado (como en el 27a). Como se cuentan días *con backup* y no días del calendario, **si el servicio deja de hacer backups no se borra nada más**: los últimos siempre quedan. Variables `BACKUP_DIARIOS=14` y `BACKUP_SEMANALES=8` reemplazan a `BACKUP_RETENCION` (que deja de leerse; el runbook pide quitarla). La regla es una función de shell pura (recibe la lista de nombres, devuelve los que se conservan), probada aislada como `segundos_hasta_proxima`. Consecuencia: no hay que elegir un «día del backup semanal»; si el domingo falla, el semanal de esa semana es el del sábado.
- **B. Día semanal fijo** (por ejemplo, domingo) copiado a una carpeta `semanales/`. Consecuencia: hay que elegir el día; si el backup de ese día falla, esa semana queda sin semanal; duplica archivos.
- **C. Por calendario** (borrar todo lo de más de 14 días salvo un semanal de las últimas 8 semanas contadas desde hoy). Consecuencia: si los backups se detienen dos meses sin que nadie lo note, la retención termina borrando todos. Descartada por riesgo.

### D2 — Retención en la copia externa · operativa · ALTA · `02` §16.2

*Para qué:* que la copia externa sirva justo cuando la PC tuvo un problema (virus, borrado por error).

- **A (recomendada). Copiar sin replicar borrados, y aplicar la misma regla de D1 en el destino por separado.** La copia externa solo **sube** archivos; nunca borra en el destino porque falten en la PC. Después de una subida exitosa aplica en el destino la regla de D1 sobre los archivos **que hay en el destino**. Consecuencia: si alguien (o un virus) borra o cifra la carpeta de la PC, la copia externa conserva los últimos 14 + 8.
- **B. Espejo (sincronizar la carpeta).** Consecuencia: más simple, pero un borrado o un cifrado en la PC se replica al destino en la siguiente corrida.
- **C. Guardar todo en el destino para siempre** (limpieza a mano). Consecuencia: el costo crece sin techo y alguien tiene que acordarse de limpiar.

### D3 — Adónde va la copia externa · de negocio · **CRÍTICA** · `02` §16.2

*Para qué:* elegir el lugar fuera de la PC donde quedan las copias. Los backups tienen datos personales de clientes (CUIT, domicilios, saldos) y de usuarios; el agente no decide adónde salen. **Las copias van cifradas (D5)**: el proveedor guarda archivos que no puede leer.

- **A (recomendada). Un almacenamiento de objetos compatible con S3** (un «disco en internet» pensado para guardar archivos: Backblaze B2, Cloudflare R2, Wasabi, o el del futuro VPS). Hoy los backups pesan pocos MB: 22 archivos entran en los **10 GB gratuitos** de B2 o R2; aun con años de datos el costo esperable es de centavos a pocos dólares por mes. Se configura en el archivo de entorno (proveedor, región, cubo, clave de acceso con permiso solo sobre ese cubo). El sistema no depende del proveedor: cambiarlo es cambiar variables. Recomendación concreta: **Backblaze B2** (cuenta gratuita, sin tarjeta para el nivel gratuito al momento de escribir; verificar al contratar). Elección final: **Q2**.
- **B. Una nube personal** (Google Drive, OneDrive) con la misma herramienta. Consecuencia: el usuario ya la tiene, pero depende de un permiso que vence o se revoca (hay que volver a autorizar), mezcla datos del negocio con una cuenta personal y tiene límites de uso.
- **C. Un disco USB externo** que alguien conecta y lleva a otro lugar. Consecuencia: sin costo, pero depende de una persona y de la memoria; mientras está enchufado a la PC, un virus lo alcanza igual. Sirve como **complemento**, no como copia externa (el mismo mecanismo acepta una carpeta local como destino, que es lo que usa el ensayo).

### D4 — Con qué y desde dónde se copia · técnica · ALTA · `02` §16.2, §18

*Para qué:* qué programa sube los archivos y con qué permisos, sin abrirle internet a quien puede leer la base.

- **A (recomendada). rclone en un servicio aparte, `copia-externa`.** rclone es un programa libre y muy usado para copiar archivos a casi cualquier almacenamiento (S3, B2, R2, Drive, una carpeta local), con cifrado incorporado (D5). Imagen propia `distribuidora-copia:${APP_VERSION}` sobre la imagen oficial de rclone con **versión fijada**. El servicio: **no recibe ninguna credencial de la base**, monta `BACKUP_DIR` **solo lectura**, está en una red nueva `salida` (con salida a internet, sin Postgres ni backend) y se configura **solo con variables de entorno** (sin archivo de configuración de rclone). El servicio `backup` sigue en la red interna `datos`, sin internet. La regla de retención (D1) es el mismo script en las dos imágenes. Consecuencia: si alguien compromete el contenedor con internet, no tiene la base; si compromete el de la base, no tiene internet.
- **B. restic** (programa de backups con repositorio propio, cifrado y retención «14 diarios, 8 semanales» incorporados). Consecuencia: menos código propio, pero las copias quedan en un formato propio: para restaurar hace falta restic y su clave, y no se ven los `.dump` en el destino; más difícil de explicar y de verificar a mano.
- **C. Sumar el servicio `backup` a una red con internet.** Consecuencia: un servicio menos, pero el contenedor que tiene la credencial de la base queda con salida a internet.

### D5 — Cifrado de las copias externas · seguridad · ALTA · `02` §18

*Para qué:* que nadie fuera de la distribuidora (ni el proveedor, ni quien robe la clave de acceso al almacenamiento) pueda leer los datos.

- **A (recomendada). Cifrar en la PC, antes de salir, con el cifrado de rclone (`crypt`).** Cada archivo sale cifrado (y con el nombre cifrado); en el destino solo hay datos ilegibles. La clave de cifrado (dos frases: clave y «sal») vive en el archivo de entorno, **nunca** en el almacenamiento externo, y una copia queda en custodia fuera del sistema (D7). Restaurar desde la copia externa exige la clave; **sin la clave, las copias externas no sirven** (es el precio de que nadie más pueda leerlas). La verificación de la copia descarga y lee el archivo con la clave (D6).
- **B. Solo el cifrado del proveedor** (el proveedor cifra en sus discos). Consecuencia: más simple, pero el proveedor (o quien obtenga la clave de acceso) puede leer los datos.
- **C. Sin cifrado.** Consecuencia: no recomendable con datos personales (`02` §18).

### D6 — Cuándo se copia, cómo se verifica y cómo se ve si falla · técnica · MEDIA · `02` §17

*Para qué:* que una caída de internet no haga perder copias y que el problema se vea.

- **A (recomendada). Cada hora, sube lo que falta; salud a las 26 horas.** El servicio `copia-externa` corre cada hora (y a pedido con `run --rm copia-externa ahora`): lista el destino, sube los `.dump` válidos que la retención local conserva y que todavía no están en el destino, **comprueba cada archivo subido** (rclone compara el contenido descifrado contra el local, `cryptcheck`) y recién entonces aplica la retención del destino (D2). Si no hay internet, reintenta la hora siguiente sin perder nada. Salud: **no sano si el backup más reciente que llegó al destino tiene más de 26 horas** (por la fecha de su nombre) o si la última corrida falló por credenciales o clave. Registros sin datos del negocio (nombre, tamaño, duración). Las variables de la copia son obligatorias (`:?`): sin copia externa configurada el compose no levanta (en el ensayo se usa una carpeta local como destino).
- **B. Una vez por día, una hora después del backup.** Consecuencia: si ese momento no hay internet, la copia espera un día entero.
- **C. Copiar desde el mismo `respaldar.sh` al terminar el backup.** Consecuencia: obliga a darle internet al servicio con la base (contradice D4 A).

### D7 — Quién guarda las claves · de negocio · ALTA · `02` §18

*Para qué:* si la PC se pierde, el archivo de entorno se pierde con ella; sin la clave de cifrado (D5) y el acceso al almacenamiento (D3), las copias externas no se pueden usar.

- **A (recomendada). El archivo de entorno más una copia en custodia del dueño, fuera de la PC.** La clave de cifrado, la sal y los datos de acceso al almacenamiento se guardan además en un **gestor de contraseñas** del dueño (o impresos en un sobre cerrado en un lugar seguro fuera de la oficina). El runbook incluye una «hoja de recuperación» (qué datos guardar, nunca los valores en el repositorio). La prueba manual incluye restaurar **usando solo lo que está en custodia**. Quién más tiene acceso: **Q3** (por ejemplo, el dueño y una segunda persona de confianza).
- **B. Solo en el archivo de entorno de la PC.** Consecuencia: si se pierde la PC, se pierden las claves y las copias externas quedan ilegibles para siempre. Descartada por riesgo; se deja escrita para que se vea por qué.
- **C. Dos personas con mitades de la clave.** Consecuencia: nadie solo puede leer las copias, pero hacen falta las dos para restaurar; excesivo para el tamaño del negocio.

### D8 — Cómo se restaura · técnica · ALTA · `02` §16.2; INV-05; ADR-020

*Para qué:* volver a cargar un backup sin riesgo de pisar una base con datos y conservando los permisos que impiden borrar libros.

- **A (recomendada). Una orden con barandas, solo sobre una base vacía, con el rol dueño del esquema.** Servicio `restauracion` en un **perfil aparte** del compose (no arranca con `up`; se usa con `--profile restauracion run --rm restauracion <archivo>`), misma imagen del backup, red `datos`, con la credencial de `app_migrations` (dueño del esquema, ADR-020; **no** el superusuario) y `BACKUP_DIR` solo lectura. Antes de tocar nada: verifica el archivo (`pg_restore --list` y las cuatro tablas de libro), **se niega si la base de destino tiene alguna tabla** en `public` y **se niega si hay otras conexiones** a la base (el backend debe estar detenido). Restaura en **una sola transacción** y deteniéndose al primer error (si algo falla, la base queda vacía como estaba). Los dueños y `GRANT` del archivo se conservan, así que `app_runtime` vuelve a quedar sin `UPDATE`/`DELETE` en libros (INV-05). Para un archivo de la copia externa, el runbook primero lo baja y descifra con `run --rm copia-externa bajar <archivo>` a una subcarpeta de `BACKUP_DIR`. Después de restaurar se corre `run --rm migraciones` (si la versión del código es más nueva, migra; si es la misma, no hace nada). **Verificar en el Lote 3** que `app_migrations` alcanza para restaurar todo el archivo (incluidos los `GRANT` y secuencias); si no alcanza, detenerse y consultar (B como alternativa).
- **B. Restaurar como superusuario de Postgres.** Consecuencia: sin dudas de permisos, pero la orden recibe la credencial más poderosa del sistema.
- **C. Restaurar «encima» (`pg_restore --clean`) sobre la base en uso.** Consecuencia: un error de archivo o de dedo borra la base de producción. Descartada.

- **Resultado de la verificación (Lote 3, 2026-11-09): `app_migrations` ALCANZA.** `restaurar.sh` restaura el archivo completo de la base migrada de prueba (59 tablas, secuencias, índices, claves foráneas, dueños y `GRANT`) conectándose como `app_migrations` a un Postgres 17 inicializado con `init-app-roles.sh` y `20-init-backup-role.sh`, sin ningún privilegio extra; `app_runtime` queda sin `UPDATE`/`DELETE` en las cuatro tablas de libro (INV-05) y las filas y la suma de control por tabla coinciden con el origen. No se usó el superusuario en producción. Detalles: la base de destino debe tener `public` con dueño `app_migrations` (lo deja `init-app-roles.sh`); la baranda de «otras conexiones» mira `pg_stat_activity` por `datid` y `usename IS NOT NULL` porque `app_migrations` no ve el `backend_type` de sesiones de otros roles; la prueba mensual restaura con el usuario `postgres` de **su** servidor temporal (roles `NOLOGIN`), con el mismo `restaurar.sh`.

### D9 — Cómo se comprueba que «los datos coinciden» · técnica · MEDIA · `00` §9 criterio 12

*Para qué:* que «restauré y no dio error» no alcance; hay que saber que está todo.

- **A (recomendada). Conteo de filas del archivo contra la base restaurada, más permisos.** Al terminar una restauración (D8) o una prueba (D10), se cuenta, tabla por tabla, cuántas filas trae el archivo (leyendo sus datos con `pg_restore`) y cuántas quedaron en la base; deben ser iguales en **todas** las tablas, y se comprueba que `app_runtime` no puede `UPDATE` ni `DELETE` en las cuatro tablas de libro y que existe la versión de Alembic. El resultado se registra («Restauración verificada: N tablas, M filas») sin datos del negocio. En las pruebas automáticas, además, se compara la base de origen con la restaurada (conteos y una suma de control por tabla). En la prueba manual, el usuario compara en `/admin` los saldos de clientes y el stock de un depósito entre producción y el entorno restaurado (sin operaciones en el medio).
- **B. Solo que `pg_restore` termine sin error.** Consecuencia: no detecta una tabla vacía o un archivo cortado de forma «válida».
- **C. Un manifiesto de conteos guardado al hacer el backup.** Consecuencia: los conteos se tomarían en otro instante que el `pg_dump` (no coinciden si hubo ventas en el medio) salvo exportar la instantánea de la transacción, más complejo para el mismo resultado que A.

### D10 — La prueba mensual de restauración · operativa · MEDIA · de negocio · `02` §16.2

*Para qué:* `02` §16.2 exige probar una restauración al menos una vez por mes; si depende de acordarse, no pasa.

- **A (recomendada). Automática, en un servicio sin red con su propio Postgres temporal.** Servicio `prueba-restauracion` (misma imagen del backup, que ya trae Postgres): **sin red** (`network_mode: none`), `BACKUP_DIR` solo lectura, sin ninguna credencial. El día `PRUEBA_DIA` de cada mes (por defecto el 1) a `PRUEBA_HORA` (por defecto 04:00), levanta **dentro de su contenedor** un servidor Postgres temporal **en el disco del contenedor** (no en memoria; se borra después de cada prueba; otro servidor, otros datos, entorno separado del de producción), crea los tres roles sin contraseña ni ingreso, restaura el backup válido más reciente con el mismo procedimiento de D8, verifica con D9 y lo descarta. A pedido: `run --rm prueba-restauracion ahora [archivo]`. Salud: **no sano si la última prueba buena tiene más de 35 días** o si la última falló. Además, la primera prueba antes de salir a producción se hace **a mano desde la copia externa** (tarea manual), que es la que demuestra que se puede recuperar sin la PC.
- **B. Manual, una vez por mes, con un recordatorio en el runbook.** Consecuencia: un servicio menos; depende de que alguien se acuerde y no hay aviso si se olvida.
- **C. Automática, montando el socket de Docker para levantar contenedores.** Consecuencia: el contenedor tendría control total del equipo. Descartada.

### D11 — Los contenedores de respaldo sin root · seguridad · MEDIA · ADR-071 (limitación)

*Para qué:* si alguien aprovechara una falla de un contenedor, que no sea administrador dentro de él.

- **A (recomendada).** `backup`, `copia-externa`, `prueba-restauracion` y `restauracion` corren con un usuario sin privilegios (`user: "${BACKUP_UID:-999}:${BACKUP_GID:-999}"`, el usuario `postgres` de la imagen). En Linux (VPS) la carpeta de backups debe pertenecer a ese usuario (`chown 999:999`, paso del runbook); en Windows con Docker Desktop la carpeta montada acepta la escritura sin cambiar dueños. **Verificar en el Lote 1** en la PC de Windows (ensayo) que el usuario no root escribe en la carpeta montada; si no puede, detenerse y consultar.
- **B. Seguir como root, documentado.** Consecuencia: cero trabajo, el riesgo aceptado en el 27a sigue.
- **Resultado de la verificación (Lote 1, 2026-11-09, PC de Windows con Docker Desktop 28.5.1): OK.** `docker run --user 999:999` de la imagen `distribuidora-backup` con `ahora`, contra un Postgres de ensayo y con una carpeta de Windows montada en `/backups`, generó `distribuidora-AAAAMMDD-HHMMSS.dump` verificado (exit 0) y el archivo aparece en la carpeta de Windows. Los permisos 600/700 no se pueden fijar ahí (el archivo queda `rw-r--r--`), lo ya previsto en `respaldar.sh`. En Linux la carpeta debe pertenecer a 999:999 (probado con un volumen con `chown 999:999`). Las pruebas `test_backup.py` (sección «Usuario sin privilegios») pasaron sin cambios de código en la imagen: ya no necesitaba root; el `Dockerfile` solo fija permisos explícitos de `/opt/backup` (755/644).

### D12 — Mudanza de los datos de la PC a un VPS · operativa · ALTA · de negocio · `04` (cierre del 27a)

*Para qué:* cuando se contrate el VPS, llevarse los datos reales sin perder ventas.

- **A (recomendada). Restaurar el último backup en el VPS recién instalado, con la cola de los teléfonos vacía antes.** Pasos en `restauracion.md`: (1) avisar y elegir un momento sin ventas; (2) **en cada teléfono, sincronizar hasta que la cola quede vacía** y cerrar las rendiciones abiertas, porque la cola del teléfono pertenece a la dirección vieja (`https://<IP>`) y **desde la dirección nueva no se ve**: lo que quede sin sincronizar se pierde; (3) en la PC, detener `backend` (nadie más escribe) y hacer un backup a pedido; (4) en el VPS, instalar con el Escenario 2 **sin sembrar**, con secretos nuevos y la misma `APP_VERSION`; levantar solo `postgres`; restaurar (D8) el archivo (llevado por la copia externa o copiado a mano); `run --rm migraciones`; `up -d`; (5) verificar con D9 y comparar saldos y stock; (6) cada teléfono entra por el dominio nuevo, instala la PWA de nuevo e inicia sesión con conexión (el `JWT_SECRET` nuevo invalida las sesiones); (7) la PC queda apagada pero **sin borrar** por al menos 30 días como vuelta atrás. Se ensaya en la prueba manual con otro proyecto de Compose en la misma PC (o en el VPS si Q1 ya está resuelta).
- **B. Copiar los archivos del volumen de Docker.** Consecuencia: depende de la versión exacta y del sistema (Windows → Linux); frágil. Descartada.
- **C. Conectar el VPS a la base de la PC por la red.** Consecuencia: obliga a exponer la base. Descartada.

### D13 — Acceso desde la calle mientras siga en la PC · de negocio · **CRÍTICA** · ADR-071 D1

*Para qué:* hoy los teléfonos solo sincronizan en el Wi-Fi de la oficina. Decidir si se hace algo antes de tener el VPS.

- **A (recomendada). Fuera de este change, explícitamente; el camino es mudarse al VPS (D12).** La venta en ruta ya funciona sin conexión y sincroniza en la oficina. Exponer la PC tiene riesgos que el 27a no cubre (Windows expuesto a internet, IP pública que cambia, muchos proveedores de internet no permiten abrir puertos). Q1 sigue abierta y no bloquea.
- **B. Abrir puertos en el router y usar DNS dinámico** (*port forwarding*: el router reenvía las conexiones de internet a la PC; *DNS dinámico*: un nombre que sigue a la IP cambiante). Consecuencia: los vendedores sincronizan desde la calle sin pagar servidor, pero la PC queda accesible desde todo internet y obliga a decisiones nuevas de endurecimiento (necesitaría su propio ADR); el certificado sigue siendo el de la autoridad propia.
- **C. Una red privada tipo VPN** (por ejemplo, Tailscale: los teléfonos se unen a una red privada con la PC, sin abrir puertos). Consecuencia: nada queda expuesto a internet, pero cada teléfono instala una aplicación más y `DOMINIO` pasa a ser la dirección de esa red (otro certificado raíz); también necesitaría su propio ADR.

### D14 — Aviso cuando algo falla · operativa · MEDIA · de negocio · `02` §17; `00` §6

*Para qué:* la salud de los servicios solo se ve con `docker compose ps`; nadie mira eso todos los días.

- **A (recomendada). Aviso externo opcional, apagado por defecto.** Si `AVISO_URL` tiene valor, `copia-externa` hace una llamada a esa dirección después de cada corrida buena (y a `…/fail` si falla). **`prueba-restauracion` no avisa** (decisión del usuario, 2026-11-09): sigue con `network_mode: none` y su única señal es la salud (`unhealthy` en `dc ps`), que la revisión semanal del runbook atrapa; sus scripts conservan la capacidad de avisar, sin usarla en el compose. Sirve con servicios gratuitos de «hombre muerto» (por ejemplo healthchecks.io): si no reciben la llamada a tiempo, mandan un correo. Sin valor, no hace nada. Además, el runbook pide una revisión semanal de `dc ps` (dos minutos). Consecuencia: el usuario puede activar avisos por correo sin código nuevo; no es «monitoreo avanzado» (`00` §6).
- **B. Sin avisos; solo la salud y la revisión semanal.** Consecuencia: más simple, pero una copia que falla puede pasar semanas sin que nadie lo note.

### D15 — Runbooks · documentación · BAJA · `04` §12

*Para qué:* que alguien que nunca restauró una base pueda hacerlo con el documento en la mano.

- **A (recomendada). `docs/runbook/restauracion.md` nuevo** con la jerga explicada: qué es cada cosa, la «hoja de recuperación» (D7), los tres casos (prueba mensual y cómo leer su resultado; desastre en el mismo equipo: volumen nuevo y restauración; mudanza a otro equipo, D12), cómo bajar un archivo de la copia externa, qué se pierde (lo hecho en el servidor después del último backup: hasta un día; las ventas que todavía están en la cola de un teléfono no se pierden y se sincronizan solas), y «si algo no funciona». **`puesta-en-marcha.md`**: nueva sección de la copia externa (crear la cuenta y el cubo, la clave de acceso limitada, generar la clave de cifrado, primera copia y cómo verla), C7 con la retención 14 + 8, `BACKUP_RETENCION` → `BACKUP_DIARIOS`/`BACKUP_SEMANALES`, `chown` en Linux (D11), C11 enlazando a la mudanza, revisión semanal (D14). `README.md` enlaza el runbook nuevo.
- **B. Todo dentro de `puesta-en-marcha.md`.** Consecuencia: un solo archivo, cada vez más largo y difícil de seguir en una emergencia.

### D16 — Cómo se prueba · técnica · MEDIA · `02` §15; `04` §2.1

*Para qué:* que cada escenario de las specs tenga una prueba que falle si se rompe.

- **A (recomendada).** En `backend/tests/infra/`: (a) la función de retención de D1, aislada, con listas de nombres (los ejemplos de la spec); (b) con Testcontainers, la imagen de backup corriendo como usuario no root; (c) la imagen de copia con un destino **local** cifrado (contenido y nombres ilegibles en el destino, subida de lo que falta, sin replicar borrados, retención del destino, `bajar` descifra, salud por antigüedad) y un caso contra un destino S3 de prueba levantado con `rclone serve s3` (sin cuentas reales); (d) restauración: base de origen migrada y con datos → backup → restauración en otro `postgres:17` vacío con los roles → conteos y sumas de control iguales, `app_runtime` sin `DELETE` en `auditoria` en la restaurada, negativa con base no vacía y con otra conexión, error a mitad deja la base vacía; (e) la prueba periódica sin red, con un backup bueno, uno dañado y el cálculo del día del mes; (f) lectura del compose (servicios, redes, perfiles, `user`, solo lectura, secretos con `:?`, ninguna credencial de base en `copia-externa` ni en `prueba-restauracion`), de la plantilla y de los runbooks. **Manual:** primera restauración desde la copia externa en un proyecto separado usando solo la hoja de recuperación, ensayo de la mudanza (D12) y comparación de saldos y stock.
- **B. Solo pruebas manuales.** Consecuencia: un cambio futuro podría romper la retención (y borrar backups) sin que nada falle.

## Risks / Trade-offs

- **[Clave de cifrado perdida]** (D5, D7) → las copias externas quedan ilegibles; la hoja de recuperación y la prueba manual con lo que está en custodia lo mitigan.
- **[La retención borra lo que no debe]** (D1, D2) → la regla es pura y probada con los ejemplos de la spec; cuenta días con backup (no calendario), solo borra después de un backup verificado y solo nombres con formato.
- **[Pérdida de hasta un día]** → una restauración por desastre vuelve al último backup: lo que el servidor registró después se pierde (lo que siga en la cola de un teléfono se sincroniza solo después). Es la consecuencia del backup diario de `02` §16.2; se explica en el runbook.
- **[Teléfonos con cola al mudarse]** (D12) → la cola es por origen; el runbook exige cola vacía antes de la mudanza y lo verifica teléfono por teléfono.
- **[Proveedor caído o credenciales vencidas]** (D3, D6) → la salud de `copia-externa` pasa a no sano en 26 horas; D14 permite un aviso por correo.
- **[`app_migrations` no alcanza para restaurar]** (D8) → se verifica en el Lote 3; si no alcanza, se consulta.
- **[Usuario no root en la carpeta de Windows]** (D11) → se verifica en el Lote 1; si falla, se consulta.
- **[Recursos de la prueba mensual]** (D10) → un Postgres temporal unos minutos por mes, en el disco del contenedor (se borra tras cada prueba); con la base actual, segundos y poco espacio.
- **[Datos en un tercero]** (D3) → cifrados antes de salir (D5); la clave de acceso solo sirve para ese cubo.

## Migration Plan

**Sin migración de Alembic.** Sin cambios de API, de permisos de la aplicación ni de Dexie. En el entorno de la PC: agregar al archivo de entorno las variables nuevas (copia externa, clave de cifrado, `BACKUP_DIARIOS`, `BACKUP_SEMANALES`; quitar `BACKUP_RETENCION`), `build` y `up -d` siguiendo C9. Los backups existentes siguen sirviendo (mismo formato de nombre); la primera corrida de la copia sube los que la retención conserva. Vuelta atrás: volver al commit anterior (los archivos de backup no cambian de formato).

## Open Questions

- **Q1 (ADR-071 D1).** ¿Qué proveedor de VPS y qué dominio? Sigue abierta y **no bloquea**: la mudanza (D12) queda escrita y ensayada en la PC.
- **Q2 (D3).** ¿Qué proveedor de almacenamiento externo y quién abre la cuenta? No bloquea el apply (las pruebas y el ensayo usan un destino local); hace falta para la prueba manual con copia real.
- **Q3 (D7).** ¿Quién, además del dueño, guarda la hoja de recuperación? No cambia el código; se anota en el runbook del usuario (fuera del repositorio).

## Precisiones del apply (Lotes 1 a 4)

**Decisiones del usuario del 2026-11-09 (D10, D14).** (1) `prueba-restauracion` queda con `network_mode: none` y **sin aviso externo**: si la prueba mensual falla, el servicio figura `unhealthy` en `dc ps` y la revisión semanal del runbook lo atrapa; `AVISO_URL` aplica solo a `copia-externa` (los scripts de la prueba conservan el soporte, sin usarlo en el compose; `backup` no tiene aviso). (2) El Postgres temporal de la prueba corre en el disco del contenedor, no en memoria, y se borra tras cada prueba.

- **Lote 1.** La retención vive en `infra/backup/retencion.sh`; `BACKUP_RETENCION` se reemplazó por `BACKUP_DIARIOS` (14) y `BACKUP_SEMANALES` (8). Los servicios corren como `${BACKUP_UID:-999}:${BACKUP_GID:-999}`; 999:999 escribe bien en un montaje de Windows (nota de D11).
- **Lote 2.** `infra/copia/` con rclone 1.68.2, configurado solo por variables (`local` o `s3` + `crypt`). La verificación por archivo usa `rclone check --download --one-way` en lugar de `cryptcheck` (la 1.68.2 no trae `--download` en `cryptcheck`; el resultado es equivalente y más estricto). Montaje de lectura y escritura extra `${BACKUP_DIR}/bajados:/bajados` para `bajar`; volumen `copia_local` / `COPIA_LOCAL_DIR` para el destino local del ensayo (con `local`, las claves de acceso valen `no-aplica`, porque son `:?`). Salud: backup más reciente del destino con más de 26 h, o última corrida fallida por credenciales o clave, es no sano; un corte de red solo no. Variables nuevas: `COPIA_ACCESS_KEY_ID`, `COPIA_SECRET_ACCESS_KEY`, `COPIA_CLAVE_CIFRADO`, `COPIA_SAL_CIFRADO` (ofuscadas con `rclone obscure`), `COPIA_TIPO`, `COPIA_RUTA`, `COPIA_S3_ENDPOINT`, `COPIA_S3_REGION`, `COPIA_S3_PROVEEDOR`, `COPIA_LOCAL_DIR`, `AVISO_URL`.
- **Lote 3.** D8 confirmada: `app_migrations` alcanza para restaurar el archivo completo (ver D8). La baranda de «otras conexiones» usa `datid` y `usename IS NOT NULL`. Umbral de salud de la prueba: 35 días. Volumen `estado_prueba` para que la salud sobreviva a recrear el contenedor. Variables `PRUEBA_DIA` (1) y `PRUEBA_HORA` (04:00).
- **Lote 4.** `docs/runbook/restauracion.md` y ajustes de `puesta-en-marcha.md` (C7, nuevo C7b, C8, C9/C11); enlace desde `README.md`. Para ver los nombres de los backups de la copia externa en un desastre (en el proveedor están cifrados) el runbook usa `run --rm --entrypoint sh copia-externa -c ". /opt/copia/lib.sh && rclone lsf cifrado:"`: no se agregó un comando `listar` a `copiar.sh` (mejora posible, no cubierta por la spec).

## Prueba manual (5.1) — 2026-11-10

Resultados de la prueba del usuario en su PC (Windows + Docker Desktop):

- **(a)** Entorno actualizado con C9 y las variables nuevas; todo `healthy`.
- **(b)** Backup y copia a pedido OK; el destino muestra nombres cifrados. Hubo que arreglar, antes, los permisos de la carpeta heredada de 27a (`chown -R 999:999`) y unas claves de cifrado que habían quedado con el texto de ejemplo. Retención del mismo día verificada en local y en el destino.
- **(c)** Prueba de restauración a pedido OK.
- **(d)** Restauración en entorno separado desde la copia externa: listar, bajar, restaurar («59 tablas, 294 filas»), migrar; saldos de clientes y stock coinciden con la oficina (criterio 12 de `00` §9). Requirió `dc down` de la oficina por la subred fija de `frente`.
- **(e)** Negativa sobre la base de la oficina: «la base de destino no esta vacia (tiene 59 tablas)», sin cambios.
- **(f)** Parte del teléfono (una cola sin sincronizar frena la mudanza): **PENDIENTE**. El teléfono (192.168.100.97) no alcanza la PC (`ERR_ADDRESS_UNREACHABLE`) pese a red Privada; es un problema de red local ajeno al change. La venta se hizo desde `/admin`.
- **(g)** `dc2 down -v` y vuelta de la oficina OK.

**Ajustes derivados** (con prueba): runbooks con el `chown` para carpetas de 27a y lista «Actualizar desde 0.27.x»; ensayo reescrito con la secuencia completa y el `dc down` de la oficina; `TZ` en `restauracion`.
