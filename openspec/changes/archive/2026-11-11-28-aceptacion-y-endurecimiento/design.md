# Diseño técnico — 28-aceptacion-y-endurecimiento

> **Estado: APROBADO (2026-11-10).** D0 a D17: todas con la opción **(A)**, incluido el texto de ayuda de D17; Q2 resuelta (ver D5 y *Open Questions*). Las decisiones quedan en **ADR-073** (*Propuesto* hasta archivar, `docs/adr/ADR-073-aceptacion-y-endurecimiento.md`).
>
> **Gobernanza.** Dominio **ALTO/CRÍTICO** en partes: permisos de base y un rol nuevo que puede borrar (seguridad), encabezados de seguridad (seguridad), una tabla y una pantalla nuevas (lógica de negocio). **CRÍTICAS:** D3 (quién puede borrar y con qué credencial), D10 (qué privilegios quedan fijados). **ALTAS:** D2, D5, D8, D9, D11. **MEDIAS:** D1, D4, D6, D7, D12, D13, D14, D15, D16, D17. **BAJAS:** D0. **De negocio u operativas** (el agente solo recomienda; decide el usuario): **D0, D1, D5, D6, D17**. Las que más conviene mirar: **D1**, **D3**, **D5**, **D9**, **D14**.
>
> **Para el usuario (lenguaje llano).** Cada decisión dice primero **para qué sirve**. Glosario corto: *Playwright* = un programa que maneja un navegador solo, como si fuera una persona, y avisa si algo no salió como se esperaba; *encabezado de seguridad* = una instrucción que el servidor le manda al navegador junto con cada página («no cargues scripts de otros sitios», «no me muestres dentro de otra página»); *CSP* = el encabezado más importante de esos: la lista de lugares de donde la página puede cargar cosas; *rol de base* = un usuario de PostgreSQL con permisos propios; *tarea periódica* = algo que el sistema hace solo a una hora fija, como el backup; *ratchet* = una prueba que impide que algo vuelva para atrás (por ejemplo, que aparezca una ruta sin prueba).
>
> **Revisión.** Decisiones (0.1) antes del apply. Después, el usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Lo que hay hoy (relevado al proponer, 2026-11-10):

- **Playwright no existe.** `frontend/tests/e2e/` tiene solo `.gitkeep`; `package.json` no tiene `@playwright/test` ni el script `test:e2e` que menciona `CLAUDE.md`. La CI (`.github/workflows/ci.yml`) dice «La suite de Playwright en la rama principal sigue pendiente».
- **La CI no corre `tests/concurrency`** (35 archivos), aunque `02` §15 paso 5 lo exige; el `README` de workflows dice que quedaba pendiente «hasta el change 04» y nunca se sumó. Hallazgo de este change.
- **Verificación de consistencia:** `cuentas_corrientes.service.verificar_consistencia` (INV-13) y `stock.service.verificar_consistencia` (INV-12, incluido `stock_total` contra saldos, ADR-039) existen como consultas por organización y se usan en pruebas. No hay ninguna tarea programada ni aviso.
- **Caddy** (`infra/caddy/Caddyfile`) envía solo HSTS; el comentario dice «CSP y demás encabezados: change 28». `Caddyfile.dev` (perfil `lan`) no envía nada. El frontend: sin scripts en línea en `index.html`, `URL.createObjectURL` para descargas (`lib/descarga.ts`), `navigator.share` con archivo para la nota (`lib/nota/compartir.ts`), pdfmake 0.3.13 con sus fuentes empaquetadas. FastAPI publica `/docs` en la raíz, pero Caddy solo reenvía `/api/*`: no es alcanzable desde afuera.
- **`intento_login`:** `app_runtime` tiene `SELECT, INSERT` (migración `e5f6a7b8c9d0`); la prueba `test_inv05_dos_roles.py` la trata como tabla de libro. No hay limpieza (ADR-057 punto 9 la asignó al 28).
- **Roles:** `app_migrations` (dueño), `app_runtime`, `app_backup` (`pg_read_all_data`), creados por `infra/postgres/init-app-roles.sh` y `20-init-backup-role.sh`. Revisión estática de las migraciones: `app_runtime` tiene `DELETE` en tres tablas: `precio_item`, `rol_permiso`, `regla_descuento_alcance` (composición de borradores, permisos de un rol y alcance de una regla; ninguna es libro). Las pruebas actuales verifican libros y «ninguna tabla sin permisos», pero no una matriz completa ni atributos de roles.
- **INV-21:** el ratchet `test_inv21_ratchet_rutas.py` exige que cada ruta esté **declarada** en `COBERTURA_DE_AISLAMIENTO`; hoy **174 de 174** rutas de negocio lo están, cada una con un comentario que nombra su prueba. El ratchet no comprueba que esas pruebas existan.
- **Invariantes (`01` §20):** todos los de la etapa 1 tienen al menos una prueba que los cita por ID (conteo de archivos backend/frontend: INV-07 7/2, INV-19 5/10, INV-15 12/0, INV-18 10/1; el resto, más). INV-09 e INV-20 tienen 0, y son de facturación (`04` §13). No existe una prueba que lo verifique automáticamente.
- **Deuda nominada al 28** (`04` §12 nota del 14; ADR-070 deuda 2): (1) el motivo en la auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (confirmado: los handlers no devuelven `DatosDeAuditoria`); la consulta de auditoría con motivo; (3) el mecanismo común de los puertos de registro de `catalogo`.
- **Siembra:** `python -m app.seed` crea solo la organización inicial y su configuración; `02` §16.1 pide que los datos de ejemplo incluyan «el escenario de la demo de aceptación».

Lo que `docs/` **ya decide** y no se reabre: verificación diaria que nunca corrige y se notifica al administrador (`02` §7.6, ADR-015); limpieza de `intento_login` de más de 24 horas con un rol distinto de `app_runtime` (`04` §12, ADR-018, ADR-057); CSP restrictiva y encabezados (`02` §18); Playwright con los criterios de `00` §9 incluido el corte de red y en la rama principal contra Docker Compose (`02` §15). Lo que **no** resuelve: D0 a D17.

## Goals / Non-Goals

**Goals:** la demostración de la etapa 1 se puede repetir con un comando y avisa si se rompe; un defecto que desincronice saldos se ve al día siguiente; el navegador queda protegido contra inyección de scripts y contra ser incrustado en otro sitio; los permisos de la base quedan escritos y vigilados; `intento_login` no crece sin límite; la CI corre lo que `02` §15 pide.

**Non-Goals:** WebKit/iPhone en Playwright (se prueba a mano en el teléfono real); Row Level Security (etapa 4); corregir diferencias; pruebas de carga; monitoreo externo más allá del aviso opcional ya existente; la consulta de auditoría en pantalla (D1).

## Decisions

### D0 — Alcance y lotes · alcance · BAJA · de negocio · `04` §2, §12

*Para qué:* cuántas partes tiene el trabajo y en qué orden.

- **A (recomendada). Un change en ocho lotes**, un subagente por lote, en secuencia, sin revisión entre lotes; se anota como **excepción de tamaño** (como el 24 y el 26): **Lote 1** rol `app_mantenimiento`, migración y matriz de permisos (D3, D10); **Lote 2** tareas periódicas: verificación, limpieza, programador y servicio (D2, D4, D6, D7); **Lote 3** aviso en `/admin` y motivo en la auditoría (D5, D17, D1); **Lote 4** encabezados y CSP (D8, D9); **Lote 5** ratchets de INV-21 e invariantes y concurrencia en la CI (D11, D12); **Lote 6** Playwright: instalación, entorno, siembra y criterios 1 a 4 (D13, D14); **Lote 7** criterios 5 a 11, aislamiento, mapa de cobertura y job de la CI (D15, D16); **Lote 8** runbook, ADR, `propuesta-docs.md` y suites completas. Después, la prueba manual.
- **B. Dos changes:** `28a-endurecimiento` (lotes 1 a 5) y `28b-aceptacion` (lotes 6 a 8). Consecuencia: cada uno más chico y revisable por separado; la etapa 1 cierra un change más tarde, y el 28b igual depende de todo el 28a (la suite corre con CSP y con el rol nuevo).

### D1 — Deuda nominada al 28 · alcance · MEDIA · de negocio · `04` §12; ADR-070

*Para qué:* tres pendientes que changes anteriores dejaron «para el 28», aunque la fila 28 no los nombra.

- **A (recomendada). Incluir solo el motivo en la auditoría de las dos anulaciones; pasar a la etapa 2 la consulta de auditoría con motivo y el mecanismo común de puertos de `catalogo`.** El motivo es un dato que AUD-02 ya exige guardar y hoy se pierde (dos handlers, una prueba cada uno); lo que no se guarda hoy no se puede mostrar después. La consulta de auditoría es una pantalla nueva (no está en `00` §9 ni en la fila 28) y el mecanismo común es una reorganización interna sin efecto visible: ninguno cambia lo que la etapa 1 entrega y los dos agregan riesgo a un change de cierre. Se anotan en `04` como deuda de la etapa 2.
- **B. Incluir las tres.** Consecuencia: un lote más (pantalla de auditoría con filtros, permiso `VER_AUDITORIA`, su ayuda, su aislamiento) y una reorganización de `catalogo` justo antes de cerrar.
- **C. Ninguna.** Consecuencia: las anulaciones de compra y pago siguen sin motivo en la auditoría (incumple AUD-02) hasta la etapa 2.

### D2 — Dónde corren las tareas periódicas · técnica · ALTA · `02` §7.6, §16.2

*Para qué:* la verificación y la limpieza tienen que ocurrir solas todos los días, sin depender de que alguien abra la aplicación.

- **A (recomendada). Un servicio nuevo `tareas` en el compose**, con la **misma imagen del backend** (mismo código, sin construir otra) y la orden `python -m app.tareas`: un bucle que espera hasta la hora configurada (como `programar.sh` del backup, con la hora del reloj inyectable `core/clock.py`), corre la verificación de cada organización y la limpieza, y vuelve a esperar. `python -m app.tareas ahora` corre todo en el momento (`docker compose run --rm tareas ahora`). Red `datos` (sin internet) salvo que se configure `AVISO_URL` (D5), sin puertos, `restart: unless-stopped`, rotación de registros, salud por un archivo de estado (como el backup). Credencial: solo `app_mantenimiento` (D3). En el compose de desarrollo se agrega igual, para probar a mano. Consecuencia: un contenedor más; si el backend se cae, las tareas siguen.
- **B. Un hilo programado dentro del backend** (por ejemplo APScheduler). Consecuencia: el backend corre con varios procesos (`WEB_CONCURRENCY=2`): cada uno ejecutaría la tarea (doble corrida) salvo un bloqueo extra; y el backend necesitaría la credencial que puede borrar, que es justo lo que la fila 28 quiere evitar.
- **C. El programador del sistema operativo** (Programador de tareas de Windows o `cron`). Consecuencia: queda fuera del compose y del runbook único; hay que configurarlo distinto en la PC y en el VPS, y no hay salud visible en `docker compose ps`.

### D3 — Con qué rol de base · seguridad · **CRÍTICA** · ADR-018, ADR-020, INV-05

*Para qué:* la limpieza tiene que borrar filas; el usuario de la aplicación no puede borrar (es la garantía de que no se pierde historia). Hace falta otra credencial que pueda borrar **solo** eso.

- **A (recomendada). Rol nuevo `app_mantenimiento`**, con ingreso y contraseña propia (`APP_MANTENIMIENTO_DB_PASSWORD`, obligatoria, sin valor por defecto): `SELECT` sobre las tablas que compara la verificación (`saldo_cuenta`, `cuenta_movimiento`, `stock_saldo`, `stock_movimiento`, `costo_producto`, `costo_producto_mov`, `organizacion`), `INSERT, SELECT` sobre la tabla de resultados (D5) y `SELECT, DELETE` sobre `intento_login`; nada más. **Se crea** con un script nuevo `infra/postgres/30-init-mantenimiento-role.sh` (volumen nuevo) y, en un entorno ya en uso, con el SQL del runbook **antes** de migrar (la PC de la oficina ya tiene su volumen). Los permisos los otorga **la migración** (como todo `GRANT`, ADR-020); si el rol no existe, la migración **falla** con un mensaje que nombra el paso del runbook (no lo saltea en silencio). Consecuencia: un secreto más en el archivo de entorno y un paso más en la actualización.
- **B. Una función de base `SECURITY DEFINER`** (corre con los permisos de su dueño, `app_migrations`) que borra lo de más de 24 horas, con `EXECUTE` para `app_runtime`. Consecuencia: sin rol nuevo, pero contradice la letra de la fila 28 y de ADR-057 («un rol distinto de `app_runtime`»): habría que enmendarlas; y la aplicación podría disparar el borrado.
- **C. Usar `app_migrations`** desde el servicio `tareas`. Consecuencia: el contenedor que corre todos los días tendría la credencial dueña de todo el esquema (puede borrar cualquier tabla). Descartada.

### D4 — Qué compara la verificación · técnica · MEDIA · `02` §7.6; ADR-015; ADR-039; CST-13

*Para qué:* definir qué es «una diferencia».

- **A (recomendada). Cuatro comparaciones por organización, con SQL en la base:** (1) `saldo_cuenta` contra la suma del libro (INV-13; consulta existente); (2) `stock_saldo` contra la suma de `stock_movimiento` (INV-12; existente); (3) `stock_total` de `costo_producto` contra la suma de `stock_saldo` del producto (ADR-039; existente); (4) **nueva:** el promedio vigente de `costo_producto` contra `promedio_nuevo` de su último `costo_producto_mov` (CST-13: el libro de costo guarda el resultado de cada recálculo). **En el Lote 2, verificar** contra datos reales de pruebas que (4) se cumple siempre (por ejemplo, después de una anulación de venta o de un ingreso sin recálculo); si hay un caso legítimo en que no, detenerse y consultar. La tarea usa los servicios de cada módulo (`service.py`), sin importar sus modelos. Las diferencias se guardan con identificadores e importes (string), sin nombres ni datos personales.
- **B. Solo (1) y (2)** (lo que dice literalmente «cada tabla de saldo con la suma de su libro»). Consecuencia: un `stock_total` o un promedio desincronizados (que alimentan el costo congelado de cada venta) no se detectan.

### D5 — Cómo se avisa una diferencia · de negocio · ALTA · `02` §7.6, §17

*Para qué:* `02` §7.6 dice «se notifica al administrador». El administrador no mira los registros de Docker.

- **A (recomendada). Las cuatro capas:** (a) tabla nueva `verificacion_consistencia` (`id`, `organizacion_id`, `ejecutada_en` `timestamptz`, `resultado` `SIN_DIFERENCIAS`/`CON_DIFERENCIAS`, `diferencias` `jsonb` con identificadores e importes en string, `registered_at`), de solo inserción (la escribe `tareas`; `app_runtime` solo `SELECT`); (b) **aviso en `/admin`** (en el inicio, visible para quien tenga el permiso nuevo `VER_CONSISTENCIA`, de solo lectura, asignado a las plantillas `Administrador` y `Administración`; Q2) mientras el último resultado de su organización tenga diferencias: momento de la corrida y el detalle (cuenta o producto y ubicación, con su nombre leído al mostrar), sin botones que modifiquen saldos, con su «(?)» (D17); lo lee un endpoint nuevo `GET /api/v1/sistema/consistencia` (permiso `VER_CONSISTENCIA`, organización del token, prueba de aislamiento INV-21); (c) registro **crítico** en el log y salud **no sana** del servicio `tareas` hasta una corrida sin diferencias; (d) el **aviso externo opcional** del 27b (`AVISO_URL`) si está configurado. La escritura de la tabla no pasa por el bus de comandos: **no es una operación de negocio** (no la origina un usuario, no tiene `operation_id`, no cambia ningún dato del negocio), igual que el `INSERT` de `intento_login` del login. Consecuencia: migración (tabla y permiso nuevo), endpoint, pantalla y un texto de ayuda. **Permiso nuevo `VER_CONSISTENCIA` (Q2, decidido 2026-11-10):** ver el aviso y leer el resultado; no modifica nada. Se asigna a `Administrador` (que ya tiene los 41) y `Administración`. No se le da `ADMIN_CONFIGURACION` a `Administración` para no ampliar sus poderes (configuración de la organización). Sigue el precedente de `ANULAR_TRANSFERENCIA` (change 14): catálogo de 41 permisos en `permisos.py` (fuente única de `PLANTILLAS_DE_ROL`), migración que inserta el permiso y lo asigna a los roles de plantilla de las organizaciones existentes por nombre, tabla de `01` §19 con la fila nueva.
- **B. Solo (c) y (d):** log crítico, salud y aviso externo opcional. Consecuencia: sin tabla, sin endpoint, sin pantalla; pero si `AVISO_URL` no está configurado (hoy no lo está), nadie se entera salvo que mire `docker compose ps`.
- **C. Correo electrónico.** Consecuencia: hace falta un servidor de correo o un servicio externo y sus credenciales; no hay nada de eso en el stack.

### D6 — Cuándo corre · operativa · MEDIA · de negocio · `02` §7.6

*Para qué:* elegir una hora en que no se cruce con el trabajo ni con el backup.

- **A (recomendada). Una vez por día a `TAREAS_HORA` (por defecto `05:00`) en `TZ`**, después del backup (`03:00`) y de la prueba mensual (`04:00` del día 1). Primero la verificación de todas las organizaciones, después la limpieza; una falla en una organización se registra y no frena a las demás; la salud cae si la última corrida falló o si no hubo corrida en 26 horas. Consecuencia: una diferencia de una venta de la tarde se ve a la mañana siguiente.
- **B. Cada hora.** Consecuencia: se ve antes, pero las consultas recorren todos los libros de todas las organizaciones 24 veces por día sin necesidad (`03` §15: «tarea nocturna»).

### D7 — Detalle de la limpieza · técnica · MEDIA · ADR-018, ADR-057

*Para qué:* borrar lo viejo sin afectar el bloqueo vigente ni la auditoría.

- **A (recomendada).** `DELETE FROM intento_login WHERE creado_en < :ahora - interval '24 hours'`, con `:ahora` del reloj inyectable, en una sola transacción; incluye las marcas de desbloqueo manual (el bloqueo mira 15 minutos: una marca de más de 24 horas ya no cambia nada). Registra cuántas filas borró, sin pares ni IP. No toca `auditoria` (AUD-03) ni `intento_pin_autorizacion` (ADR-018 no la menciona). La prueba `test_inv05_dos_roles.py` sigue tratando `intento_login` como libro para `app_runtime`.
- **B. Borrar en tandas** (por ejemplo, de a 10 000 filas). Consecuencia: innecesario para el volumen esperado (una oficina, pocos intentos); queda como ajuste si algún día crece.

### D8 — Dónde y qué encabezados · seguridad · ALTA · `02` §18; ADR-071

*Para qué:* que el navegador se niegue a hacer cosas peligrosas aunque alguien logre meter código en una página.

- **A (recomendada). En Caddy, en un fragmento compartido** `infra/caddy/encabezados.caddy` que importan el Caddyfile de producción y el `lan` de desarrollo (así el teléfono de prueba ve lo mismo que producción). Para toda respuesta (aplicación y `/api/*`): `Content-Security-Policy` (D9), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` que apaga cámara, micrófono, geolocalización y pagos, `Cross-Origin-Opener-Policy: same-origin`, `X-Frame-Options: DENY` (para navegadores viejos; CSP `frame-ancestors` lo cubre en los nuevos) y sin `Server`. HSTS sigue igual (ADR-071). Además, `/docs` y `/openapi.json` del backend se apagan en producción (hoy no se alcanzan desde afuera; es defensa extra). Consecuencia: un archivo más; las pruebas de `backend/tests/infra/test_caddy.py` lo verifican en los dos modos de `CADDY_TLS`.
- **B. En el backend (middleware) y en Caddy solo para los archivos estáticos.** Consecuencia: dos lugares que mantener iguales; un error en uno deja una parte sin encabezados.
- **C. CSP con una etiqueta `<meta>` en `index.html`.** Consecuencia: no admite `frame-ancestors` ni cubre las respuestas de la API.

### D9 — La política CSP concreta y cómo se activa · seguridad · ALTA · `02` §18

*Para qué:* la CSP demasiado abierta no protege; demasiado cerrada rompe la aplicación (instalación, nota de venta, descargas).

- **A (recomendada). Aplicarla directamente (no en modo «solo informar»)** con: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. La suite de Playwright corre con la política aplicada y **falla ante cualquier violación** (spec `sistema/aceptacion-etapa-1`), así que la protección no depende de mirar la consola a mano. **Verificar en el Lote 4**, con el build real: que pdfmake no necesite `unsafe-eval` y que ningún componente inyecte estilos en línea que haya que permitir. **Si pdfmake necesita `unsafe-eval` o algo exige `style-src 'unsafe-inline'`, detenerse y consultar** con las opciones concretas (permitir solo eso, con su riesgo explicado, o cambiar la forma de generar el PDF).
- **B. Primero `Content-Security-Policy-Report-Only` unas semanas**, después aplicarla. Consecuencia: el modo solo informar no protege nada; y no hay dónde recibir los informes (haría falta un endpoint que los guarde). Tiene sentido con muchos usuarios y pantallas que no se pueden probar; acá la suite las recorre.

- **Resultado de la verificación (Lote 4, 2026-11-10).** La política de la opción A se aplicó tal cual, sin `unsafe-eval` ni `unsafe-inline`. Con la compilación real: `index.html` no tiene scripts ni estilos en línea; pdfmake 0.3.13 genera y se descarga el PDF con la política aplicada (sin `eval`); los estilos que pone React (`style={{left}}`, en el «(?)») se aplican por el modelo de objetos del navegador, que la política no bloquea; las descargas son `blob:` por navegación y `navigator.share` no pasa por la política; el service worker se registra y carga su `importScripts` del mismo origen. Único hallazgo: Zod 4 intentaba `new Function("")` (el navegador lo rechaza y Zod sigue por su camino normal, pero la política lo informa como violación); se evitó con `z.config({ jitless: true })` en `src/lib/zodSinEval.ts` (importado primero en `main.tsx`), sin cambiar la política. Pendiente de la prueba manual 9.1(a): pantallas con sesión, instalar la PWA y compartir en el teléfono real.

### D10 — Revisión de permisos de base · seguridad · **CRÍTICA** · INV-05; ADR-020

*Para qué:* que nadie, sin querer, le dé a la aplicación permiso para borrar historia en una migración futura.

- **A (recomendada). Una matriz explícita y una prueba que la compara con la base real.** Archivo `backend/tests/integration/permisos_de_base.py` con, por cada tabla, los privilegios esperados de `app_runtime`, `app_backup` (lectura de todo por `pg_read_all_data`) y `app_mantenimiento`, y una **justificación escrita en cada `DELETE`** (hoy: `precio_item`, `rol_permiso`, `regla_descuento_alcance`, a confirmar en el Lote 1 contra `information_schema`: la revisión estática puede no ver `GRANT` armados en un bucle). La prueba (`test_permisos_de_base.py`, cita INV-05) falla si sobra o falta un privilegio o si aparece una tabla sin entrada; otra comprueba atributos (ningún rol de servicio superusuario, `CREATEROLE`, `CREATEDB`, `BYPASSRLS`; dueño de todo `app_migrations`; `PUBLIC` sin privilegios de tabla ni `CREATE` en `public`); también secuencias. Si la revisión encuentra un privilegio que no se puede justificar, **se detiene y se consulta** antes de quitarlo (quitar un permiso puede romper una pantalla). Las pruebas de `test_inv05_dos_roles.py` siguen como están.
- **B. Mantener solo las pruebas actuales** (libros y «toda tabla tiene algún permiso»). Consecuencia: un `DELETE` de más en una tabla maestra (ADR-020 dice «nunca `DELETE`») no se detecta.

### D11 — INV-21 en todas las rutas · técnica · ALTA · INV-21; `02` §8, §15

*Para qué:* que «las 174 rutas están cubiertas» sea cierto y no solo una lista.

- **A (recomendada). La cobertura apunta a pruebas reales.** `COBERTURA_DE_AISLAMIENTO` pasa de un conjunto de rutas a un diccionario ruta → pruebas (`archivo::nombre`), cargado a partir de los comentarios que hoy ya nombran cada prueba. El ratchet comprueba, sin correrlas, que cada prueba existe (recolección de pytest o lectura del archivo) y que su archivo o su texto cita INV-21; falla también por una ruta declarada que ya no existe. Donde un comentario no nombre una prueba precisa, el Lote 5 la busca o la escribe (con login real de dos organizaciones, como pide el propio ratchet). Consecuencia: trabajo mecánico sobre 174 entradas; ninguna prueba nueva de negocio salvo los huecos que aparezcan.
- **B. Un barrido genérico**: una prueba que recorre todas las rutas con el token de otra organización y los identificadores de la primera, esperando 404. Consecuencia: para las escrituras hay que armar un cuerpo válido por ruta (174 cuerpos distintos) o solo prueba que la validación rechaza, que no es aislamiento; las lecturas de listas no tienen identificador. Mucho código que repite lo que ya prueban las pruebas por módulo.
- **C. Dejarlo como está.** Consecuencia: si alguien borra o renombra una prueba de aislamiento, el ratchet sigue verde.

### D12 — Cobertura de invariantes y concurrencia en la CI · técnica · MEDIA · `02` §15

*Para qué:* «todos los invariantes de `01` §20 cubiertos» (fila 28) verificado por una máquina, y que las pruebas de concurrencia (las que detectan carreras reales) corran siempre.

- **A (recomendada).** (a) Prueba `backend/tests/unit/test_cobertura_de_invariantes.py`: lee la tabla de `01` §20, exime por nombre INV-09 e INV-20 (`04` §13, con la razón) y busca cada ID en las carpetas que corre la CI (`backend/tests/{unit,integration,concurrency,properties,infra,fixtures_compartidos}`, `frontend/tests/unit`); falla nombrando el que falte. (b) Job de la CI con `python -m pytest tests/concurrency` en un paso propio (sus `conftest` chocan con los de integración si se juntan). Si al sumarla aparece una prueba de concurrencia intermitente, no se ignora (es una carrera real): se detiene y se consulta.
- **B. Solo la concurrencia en la CI** y la cobertura se revisa a mano al archivar. Consecuencia: depende de que alguien se acuerde.

### D13 — Dónde corre Playwright · técnica · MEDIA · `02` §15, §16

*Para qué:* probar lo que de verdad usa el vendedor: la compilación con service worker, sobre HTTPS, con los encabezados aplicados.

- **A (recomendada). El compose de producción, en un proyecto aparte** (`docker compose -p distribuidora-aceptacion -f docker-compose.prod.yml --env-file infra/aceptacion.env up -d --build`), con `DOMINIO=localhost`, `CADDY_TLS=internal`, puertos distintos para no chocar con el perfil `lan` (variables de puertos con el 80/443 por defecto en producción), copia externa a una carpeta local y base nueva en su propio volumen. Playwright corre en el equipo (no en un contenedor) contra `https://localhost:<puerto>`, aceptando el certificado de Caddy solo en la prueba. `infra/aceptacion.env` está en el repositorio **sin secretos reales** (claves de prueba, no sirven para nada fuera de ese entorno). `npm run test:e2e` levanta, siembra, corre y descarta (`down -v`); con una opción, deja el entorno levantado para mirar. Consecuencia: la primera corrida tarda (construye las imágenes); prueba también el compose de producción.
- **B. El compose de desarrollo con `vite dev`.** Consecuencia: no hay service worker: recargar sin señal muestra el dinosaurio (lo vimos en el 21 y el 22d); no prueba la CSP real.
- **C. El perfil `lan` de desarrollo.** Consecuencia: usa la base de desarrollo del usuario: la suite la llenaría de datos de prueba.

### D14 — Datos y forma de la suite · técnica · MEDIA · de negocio en parte · `00` §9; `02` §16.1

*Para qué:* que la suite cuente la misma historia que la demostración, con los mismos usuarios que el usuario conoce.

- **A (recomendada).** (a) **Siembra del escenario de aceptación** en `app.seed` (opción `--escenario-aceptacion`, repetible): organización inicial con sus roles, los usuarios **con los mismos nombres que en desarrollo** (`admin`, `administracion`, `ges01`, `consulta`, `supervisor`, `sup01`, `vendedor`, `vendedor2`) y contraseñas de prueba fijas solo para este entorno, depósito y vehículo, política de crédito y tolerancia, una regla de descuento por volumen y el tope de descuento manual del vendedor; y una **segunda organización** con su `admin` (control de aislamiento). Los productos, clientes, proveedores, stock y saldos **no** se siembran: los carga el criterio 1 importando planillas de ejemplo (`frontend/tests/e2e/datos/`), con valores tomados de los ejemplos de `docs/01` donde existan. (b) **Una suite en serie**, en el orden de la demostración (cada criterio usa lo que dejó el anterior, como en `00` §9: «de punta a punta»); si uno falla, los siguientes se marcan como no corridos, no como fallidos. (c) **Dos proyectos de Playwright:** «PC» (Chrome de escritorio) para `/admin` y «teléfono» (Chrome con la emulación de un Pixel: pantalla, toque, sin ratón) para `/ruta`. Solo Chromium. Consecuencia: si el criterio 1 falla, no corre nada más (es lo que pasaría en la demostración real).
- **B. Pruebas independientes**, cada una con sus datos creados por la API. Consecuencia: más robusto para encontrar la causa de una falla, pero no prueba que la historia completa encadene, y cada prueba arma muchos datos.

### D15 — Lo que Playwright no puede hacer solo · técnica · MEDIA · `00` §9 criterios 7 y 12

*Para qué:* ser honestos sobre qué prueba la máquina y qué se prueba a mano.

- **A (recomendada).** **Criterio 7:** la prueba corta la red, genera la nota y comprueba que se generó el PDF y que se llamó a la hoja de compartir con ese archivo (la hoja del sistema y WhatsApp no existen en un navegador automatizado; se reemplaza `navigator.share` por un espía); el envío real por WhatsApp va a la prueba manual. **Criterio 12:** ya lo cubren `backend/tests/infra/test_restauracion.py` y `test_prueba_restauracion.py` (27b) y la prueba manual del 2026-11-10; un **mapa de cobertura** (`frontend/tests/e2e/criterios.ts`) lista los 12 criterios con su prueba y una prueba de Vitest falla si alguno no tiene. **«En un teléfono real»** (`00` §9): la emulación no lo reemplaza; va a la prueba manual (criterios 4 a 8 en el teléfono del vendedor).
- **B. Automatizar el criterio 12 desde Playwright** (que la prueba levante una restauración con Docker). Consecuencia: la suite del navegador manejaría contenedores; duplica pruebas que ya existen.

### D16 — Cuándo corre Playwright en la CI · técnica · MEDIA · `02` §15

*Para qué:* que la suite avise sin hacer lento cada push.

- **A (recomendada). En cada push a `main`** (como dice `02` §15), con las trazas de las fallidas como artefacto; en las ramas de change se corre a mano (`npm run test:e2e`) antes de archivar. Consecuencia: una rotura se ve al integrar a `main`, no antes.
- **B. En cada push de cualquier rama.** Consecuencia: cada push suma varios minutos (construir imágenes y levantar el entorno).

### D17 — Ayuda contextual del aviso · de negocio · MEDIA · ADR-051; `04` §2.1 punto 8

*Para qué:* el aviso de diferencias no es obvio: hay que explicar qué significa y qué hacer.

- **A (recomendada, solo si D5 es A).** Una clave nueva `consistenciaDiferencias` en `frontend/src/ayuda/textos.ts`, **sin ejemplo**, con reglas `02 §7.6`, ADR-015, INV-12, INV-13. Texto propuesto (a aprobar): *«El sistema compara todas las noches los saldos de clientes, proveedores y stock con sus movimientos. Si no coinciden, hay un error del sistema: los saldos no se corrigen solos para no tapar el problema. Avisale a quien da soporte; mientras tanto se puede seguir operando.»* Ninguna otra pantalla cambia. Consecuencia: una clave; la red de los textos (ADR-051) la vigila.
- **B. Sin ayuda.** Consecuencia: el administrador ve un aviso alarmante sin saber qué hacer.

## Risks / Trade-offs

- **[Riesgo] La CSP rompe algo que la suite no recorre** (una pantalla poco usada). → La suite recorre las pantallas de la demostración; las demás se abren en la prueba manual con la consola abierta. Volver atrás es cambiar un archivo de Caddy.
- **[Riesgo] Suite de Playwright frágil** (tiempos, animaciones). → Esperas por estado visible (nunca esperas fijas), reintento 1 en la CI, trazas de las fallidas.
- **[Riesgo] La migración del rol falla en la PC de la oficina** si no se crea el rol antes. → Falla clara que nombra el paso; el runbook de actualización lo pone primero.
- **[Riesgo] Sumar `tests/concurrency` a la CI destapa pruebas intermitentes.** → No se ignoran (`config.yaml` de OpenSpec): se consulta.
- **[Trade-off] Suite en serie (D14 A):** una falla temprana oculta las de después.
- **[Trade-off] Solo Chromium:** Safari del iPhone queda a la prueba manual.

## Migration Plan

1. En la PC de la oficina (o el VPS): crear `app_mantenimiento` con el SQL del runbook y sumar `APP_MANTENIMIENTO_DB_PASSWORD` (y, si se quiere, `TAREAS_HORA`) al archivo de entorno.
2. Actualizar como siempre (`docs/runbook/puesta-en-marcha.md` C9): `migraciones` crea la tabla y otorga los permisos; levanta `tareas`.
3. `run --rm tareas ahora` y ver «Verificación de consistencia: sin diferencias».
4. Volver atrás: la migración baja limpia (borra la tabla y revoca); el rol queda sin uso; los encabezados se quitan con la imagen anterior de Caddy.

## Open Questions

- **Q1 (del 27b, sigue abierta, no bloquea):** VPS y dominio.
- **Q2 (RESUELTA 2026-11-10):** el aviso lo ven `Administrador` y `Administración`, con un permiso nuevo de solo lectura `VER_CONSISTENCIA` (no se amplía `Administración` con `ADMIN_CONFIGURACION`). Ver D5.

## Precisiones del apply (Lotes 1 a 8)

Lo que el apply fue encontrando y decidiendo dentro de las opciones ya aprobadas (D0 a D17 en A; Q2). Copiado a `ADR-073` y a `propuesta-docs.md`.

- **Lote 1 (D3).** Rol `app_mantenimiento`. En un entorno existente hay que crearlo **antes** de migrar (runbook C12); variable nueva `APP_MANTENIMIENTO_DB_PASSWORD` (sexto secreto).
- **Lote 2 (D2, D5), corregido el 2026-11-11.** Servicio `tareas`. Al principio `tareas` quedó solo en `datos` (`internal`) y sin aviso externo. **Ampliación aprobada por el usuario (opción A, tarea 8.5):** `tareas` también está en la red `salida` (la de `copia-externa`; solo saliente, sin puertos; `datos` sigue `internal`) y avisa a un servicio de «hombre muerto» con la variable propia `AVISO_TAREAS_URL` (distinta de `AVISO_URL`, la de la copia): sana -> GET a la dirección; con diferencias o fallo -> GET a `<dirección>/fail`; 10 s de espera, 3 intentos; un aviso que falla solo se registra (sin la dirección) y no cambia el resultado ni la salud. `ahora` también avisa (es la forma de probarlo). Alternativa B (servicio avisador sin acceso a la base) descartada. Ver ADR-073 y runbook C13. Las señales locales siguen: aviso en `/admin`, registro crítico y salud no sana.
- **Lote 3 (D1, D5, D17, Q2).** `VER_CONSISTENCIA` (también `Administración`). El endpoint `GET /api/v1/sistema/consistencia` vive en el módulo `reportes` (por import-linter: `reportes` ya lee de los demás módulos por sus `service.py`). Aviso en `AdminInicio`. El motivo queda en la auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR`. **Limitación:** un rol a medida con `VER_CONSISTENCIA` pero sin `REVISAR_OBSERVACIONES` no ve el aviso (el inicio de `/admin` se arma sobre ese permiso); fuera de alcance.
- **Lote 4 (D8, D9).** `encabezados.caddy`; CSP de D9 sin relajar; Zod 4 sondea `new Function`, resuelto con `lib/zodSinEval.ts` (`jitless`); `/docs`, `/redoc` y `/openapi.json` apagados en producción.
- **Lote 5 (D11, D12).** Ratchet de INV-21 ruta → pruebas; cobertura de invariantes; concurrencia en la CI. En esta máquina la suite de concurrencia se corre por tandas (600 passed en 6 tandas).
- **Lote 6 (D13, D14).** `seed --escenario-aceptacion`; Playwright 1.64.1. Desvío: importar y publicar listas lo hace `admin` (`IMPORTAR_DATOS` y `PUBLICAR_LISTAS` son solo de `Administrador`, `01` §19), no `ges01`. En el compose de producción `FRENTE_SUBRED` y los puertos de Caddy pasan a ser variables (para convivir con el entorno de desarrollo).
- **Lote 7 (D15, D16).** 41/41 pruebas e2e en dos corridas. El criterio 9 lo anula un supervisor (`sup01`) desde `/admin` (`Vendedor` no tiene `ANULAR_VENTA`; hace falta `LIBERAR_UBICACION` por VTA-21). El criterio 4 carga todo el stock que usa el 5 (con la jornada abierta no se transfiere al vehículo, STK-09). El tramo 05 a 08 es un único teléfono sin señal (la jornada es por usuario y dispositivo, ADR-005; un teléfono con conexión envía lo pendiente al arrancar). Playwright necesita `--ignore-certificate-errors` para registrar el service worker con el certificado interno de Caddy. «Acción no permitida»: la suite cubre solo la API (403); la parte de pantallas queda como paso manual nombrado en 9.1.
- **Lote 8.** Runbook: C12 (crear el rol antes de migrar), C13 (`tareas`, verificación a pedido, qué hacer ante diferencias), C14 (`npm run test:e2e`); C2 pasa a seis secretos; C8 suma la salud de `tareas`.

## Resultados de la prueba manual 9.1 (2026-11-11)

Hecha por el usuario el 2026-11-11, con los usuarios de desarrollo.

- **Paso 0.** El rol `app_mantenimiento` se creó en desarrollo antes de migrar; `--profile lan up -d --build` (`pwa-build` necesitó `--renew-anon-volumes` por un volumen anónimo viejo de `node_modules`). Las migraciones del 28 en desarrollo se aplicaron con `alembic upgrade head` dentro de `backend` (desarrollo no migra solo).
- **(a) PC.** Encabezados correctos (CSP, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP); HSTS ausente en desarrollo, correcto. **Hallazgo:** un navegador con un dispositivo REVOCADO guardado recibe el 401 genérico; se resuelve borrando los datos del sitio.
- **(a) Teléfono.** PWA instalada, nota de venta generada y compartida. El teléfono no llegaba a la PC (`ERR_ADDRESS_UNREACHABLE`, pendiente desde el 27b): la causa era el firewall de Windows; se resolvió con una regla de entrada TCP 80/443. Caddy de desarrollo con `LAN_IP=192.168.100.160`.
- **(b)** `tareas ahora` en desarrollo: sin diferencias. En aceptación (entorno `npm run test:e2e:mantener`) se alteró a mano +1000 el saldo de un cliente: la verificación informó 1 diferencia (solo esa organización; la segunda sin diferencias); `admin` vio el aviso en `/admin` con su «(?)»; `vendedor` no.
- **(c) Limpieza.** 134 intentos de más de 24 h borrados; los recientes (11) y la auditoría (113 `INICIO_SESION_FALLIDO`) intactos.
- **(d)** `npm run test:e2e` en la PC del usuario: 41 passed (la prueba de CSP con `test.fail` se marca ✘ esperada); traza vista.
- **(g)** `vendedor` no puede abrir `/admin/compras` ni `/admin/configuracion`.
- **(h) healthchecks.io.** Con diferencias (aceptación): control rojo «down» y correo inmediato; en desarrollo sin diferencias: verde «up» y correo de recuperación. **Recomendación:** en la oficina usar un control distinto del de pruebas.
- **(f)** Criterios 4 a 8 en el teléfono real del vendedor con modo avión: transferencia y apertura de jornada, venta sin señal con descuento y cobro parcial, exceso de crédito sin señal, nota sin señal, sincronización sin duplicados (verificada en `/admin`) y terminar el día: todo OK.
- **(e) PC de la oficina: PENDIENTE.** Se hace al instalar allá: crear el rol antes de migrar, actualizar, `dc ps` con `tareas` sano, crear un control de healthchecks propio.
- **Ajuste tras la prueba.** El texto de `tareas ahora` quedó en singular («1 diferencia (no se corrige sola…)», «1 intento… borrado»): `backend/app/tareas/__main__.py`, con prueba nueva `backend/tests/unit/test_tareas_informe.py` (5 casos; 37 passed en las pruebas de tareas; `ruff` y `mypy` limpios).
