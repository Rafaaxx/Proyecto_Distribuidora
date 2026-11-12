## Context

Ver `proposal.md` — Why. Estado actual relevante: `backend/app/modules/identidad/` ya existe con `organizacion` y `configuracion_organizacion` (change 02); `backend/app/modules/configuracion/` tiene los tres catálogos; no hay ninguna ruta HTTP de negocio y `backend/tests/integration/test_inv21_ratchet_rutas.py` recorre `app.routes` y falla si aparece una que no esté ni exenta como ruta de sistema ni declarada en la cobertura de aislamiento; `python -m app.seed` siembra la organización inicial de forma idempotente; `docker-compose.yml` tiene **un** solo rol de PostgreSQL, que además es el dueño del esquema; `core/` tiene `money`, `clock`, `ids`, `errors`, `db` y `config`.

`03` §4 fija las siete tablas al detalle, `01` §19 fija los 39 permisos y las cinco plantillas de rol, y ADR-017 fija la mecánica de los tokens. Lo que `docs/` **no** resuelve y este documento decide (o eleva a decisión humana): los parámetros del rate limit de login y dónde se cuentan los intentos (**D1, bloqueante**); si el PIN de autorización en claro llega al servidor (**D2, bloqueante**); cómo se provisionan los dos roles de base que exige INV-05 (D3); el algoritmo y la gestión de la clave del JWT (D4); qué significa "caché breve" de permisos (D5); cómo conviven las escrituras de este change con un bus de comandos que todavía no existe (D6); cómo se declara exento el catálogo global `permiso` (D7); y de dónde sale el primer usuario administrador (D8).

## Goals / Non-Goals

**Goals:**

- Que la dependencia de permisos quede como el **único** camino por el que un endpoint obtiene `organizacion_id`, `usuario_id` y `dispositivo_id`, de modo que los changes 04..27 no tengan que decidir nada y no exista una segunda fuente.
- Que INV-05 sea una propiedad de la base verificada por una prueba, no una convención de código: una tabla de libro futura sin su `GRANT` restringido debe poner la suite en rojo.
- Que el ratchet de rutas del change 02 se estrene con rutas reales y siga siendo el portón para las de los changes siguientes.
- No dejar ningún atajo copiable: ni un segundo camino a `organizacion_id`, ni un secreto con valor por defecto, ni una contraseña sembrada fija.

**Non-Goals:**

- Diseñar el sobre del comando ni la idempotencia: `02` §6 y change 04.
- `GET /auditoria` como endpoint de consulta: la capacidad de auditoría se verifica acá leyendo la tabla en pruebas de integración; la pantalla y el endpoint de consulta van con reportes (change 26). `VER_AUDITORIA` se siembra igual, porque el catálogo de permisos se sincroniza completo por migración (`03` §17).
- Row Level Security: `02` §8 la posterga a la etapa 4.
- Cifrado de IndexedDB: `02` §12.3 lo posterga explícitamente.

## Decisions

### D1 — Rate limit de login: dónde se cuentan los intentos y con qué umbrales (**BLOQUEANTE**)

`02` §18 exige "límite de intentos en login por usuario y por IP" y no dice nada más: ni umbral, ni ventana, ni duración del bloqueo, ni si el bloqueo es del usuario, de la IP o del par. `01` §4 no tiene un parámetro para esto (`intentos_pin_max` es el PIN de desbloqueo local, SEG-04, y es otra cosa). Producción corre "varios workers" (`02` §16.2) y el stack no tiene almacén compartido.

- **A) Tabla `intento_login` en PostgreSQL, contada por ventana deslizante.** Un `INSERT` por intento fallido y una consulta agregada indexada antes de verificar la contraseña. **Consecuencia:** el límite es correcto y uniforme entre workers, sobrevive a reinicios y es auditable; cuesta una escritura por intento fallido (volumen despreciable: `03` §18) y obliga a una tarea de purga, que es la primera del sistema. Es también la única opción que permite mostrarle a un administrador por qué una cuenta está bloqueada.
- **B) Contador en memoria del proceso.** Cero dependencias y cero escrituras. **Consecuencia:** con N workers el límite efectivo se multiplica por N y un atacante que reparta los intentos lo diluye; se pierde en cada despliegue, que es justo cuando conviene que no se pierda. Convierte un control de seguridad en una aproximación, sin decirlo en ningún lado.
- **C) Redis u otro almacén compartido.** Lo natural para contadores con expiración. **Consecuencia:** agrega un servicio a la infraestructura que `02` §16.2 no contempla, con su backup, su monitoreo y su modo de falla (¿se bloquea el login si Redis no responde, o se abre?). Es una decisión de infraestructura que excede este change.

**Recomendación: A**, con los umbrales como configuración del backend y no hardcodeados.

**Por qué esto es bloqueante y no una decisión de este documento:** el mecanismo lo puedo elegir, pero los **valores y el comportamiento observable** son regla de negocio nueva —cuántos intentos, en qué ventana, cuánto dura el bloqueo, si bloquea al usuario o a la IP, si el usuario legítimo puede desbloquearse y cómo, y qué ve— y `01` no tiene ninguna regla `SEG-` que lo cubra. Un límite mal puesto bloquea a un vendedor en la calle sin señal para llamar a soporte. **Requiere ADR y confirmación humana antes de implementar** (`04` §2, regla de oro). Hasta que exista, las tareas de rate limit de `tasks.md` quedan sin ejecutar y el resto del change puede avanzar: no hay dependencia de código entre el rate limit y el resto del login.

### D2 — Quién deriva el PIN de autorización de supervisor (**BLOQUEANTE**)

`02` §12.4 y ADR-011 fijan PBKDF2 con sal e "iteraciones altas", mínimo 6 dígitos, rotable desde administración, y que el bootstrap envía la derivación al dispositivo. `03` §4 fija las tres columnas (`pin_autorizacion_hash`, `_sal`, `_iteraciones`). Ninguno dice si el PIN en claro llega al servidor.

- **A) El dispositivo deriva y envía derivación, sal e iteraciones; el servidor solo almacena.** El PIN en claro nunca sale del dispositivo. **Consecuencia:** el servidor no puede hacer cumplir el mínimo de 6 dígitos ni que sean dígitos (recibe bytes opacos), y no puede rotar el PIN desde administración sin el dispositivo del supervisor — las dos mitigaciones que ADR-011 declara para el riesgo aceptado. También deja que un cliente modificado fije iteraciones bajísimas y debilite la derivación que el bootstrap después reparte a todos los dispositivos.
- **B) El dispositivo envía el PIN en claro sobre HTTPS; el servidor valida formato, deriva con parámetros que él elige y almacena.** **Consecuencia:** el servidor hace cumplir longitud, formato, iteraciones y rotación, y el parámetro de iteraciones deja de ser un dato que el cliente controla. A cambio, el PIN cruza la red (protegido por el TLS obligatorio de `02` §18) y vive en memoria del proceso durante la petición: hay que garantizar que no aparezca en logs ni en el cuerpo de un error, cosa que `02` §17 ya prohíbe explícitamente y que se verifica con una prueba.
- **C) El dispositivo deriva y además declara longitud y formato.** **Consecuencia:** el servidor no puede verificar la declaración; es una validación decorativa que da falsa seguridad y no habilita la rotación.

**Recomendación: B**, porque es la única que sostiene las mitigaciones sobre las que ADR-011 apoyó el riesgo aceptado.

**Por qué es bloqueante:** define si un secreto de autorización en claro atraviesa la red y el proceso del servidor. Es una propiedad de seguridad del sistema, no un detalle de implementación, y ADR-011 no la fijó. **Requiere confirmación humana y una extensión de ADR-011 antes de implementar.**

### D3 — Cómo se provisionan los dos roles de base (INV-05)

`02` §18 exige que el usuario de aplicación no sea superusuario ni dueño del esquema y que las migraciones usen uno distinto; `03` §2.5 exige que no tenga `UPDATE` ni `DELETE` sobre las tablas de libro y que "una prueba lo verifica". Hoy hay un solo rol, dueño de todo.

- **A) Rol dueño para Alembic, rol de aplicación con `GRANT` explícito por tabla, otorgado en la misma migración que crea la tabla.** Una tabla normal recibe `SELECT, INSERT, UPDATE, DELETE`; una tabla de libro recibe solo `SELECT, INSERT`. **Consecuencia:** cada migración futura tiene que acordarse de su `GRANT`, pero no depende de acordarse: la prueba de INV-05 recorre `information_schema.role_table_grants` y falla si el rol de aplicación tiene `UPDATE` o `DELETE` sobre una tabla declarada de libro, **o** si una tabla no tiene ningún `GRANT` (que es cómo se detecta el olvido).
- **B) `ALTER DEFAULT PRIVILEGES` para que el rol de aplicación reciba los cuatro permisos sobre toda tabla nueva.** Cómodo: ninguna migración piensa en permisos. **Consecuencia:** el valor por omisión es exactamente lo que INV-05 prohíbe. Una tabla de libro futura (`cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov`) nacería con `UPDATE` y `DELETE` concedidos y habría que acordarse de revocarlos — invierte el sentido del ratchet: el olvido produce el estado inseguro en vez del error.

**Decisión: A.** El criterio es el mismo del change 02: la verificación tiene que fallar sola cuando alguien se olvide, y el olvido tiene que producir un error, no un agujero.

Implicancia operativa: `docker-compose.yml`, `.env.example` y el arnés de Testcontainers pasan a crear los dos roles. **Gobernanza ALTA** (configuración que afecta el despliegue): la tarea correspondiente se detiene para revisión humana antes de escribirse.

### D4 — Algoritmo de firma y gestión de la clave del JWT

ADR-017 dice "JWT firmado" y no fija algoritmo ni gestión de clave.

- **A) HS256 con secreto desde variable de entorno, obligatorio y sin valor por defecto, con `kid` en el encabezado.** **Consecuencia:** emisor y verificador son el mismo proceso, así que la clave simétrica alcanza; el `kid` permite rotar el secreto sin invalidar los access tokens vigentes (dos claves aceptadas durante 15 minutos). Que el secreto no tenga valor por defecto significa que el backend no levanta sin él, igual que hoy no levanta sin `database_url`: no existe el escenario "quedó el secreto de ejemplo en producción".
- **B) RS256 con par de claves.** **Consecuencia:** necesario si algún verificador externo tuviera que validar tokens sin poder firmarlos; en la etapa 1 no hay ninguno (`02` §2). Agrega gestión y distribución de claves a cambio de una propiedad que nadie usa.

**Decisión: A.** No amerita ADR: no cambia ninguna regla de `docs/`, elige un mecanismo dentro de lo que ADR-017 ya decidió.

**Nonce/`jti` en el access token: descartado.** Sin lista negra de tokens individuales, un `jti` no aporta ningún beneficio de seguridad: la revocación de ADR-017 opera sobre refresh tokens y dispositivos, no sobre access tokens sueltos. Que dos access tokens emitidos en el mismo segundo para el mismo usuario/organización/dispositivo sean bytes idénticos es una consecuencia observable, no un riesgo. No amerita ADR.

### D5 — Qué significa "caché breve" de permisos

ADR-017 pide "caché breve en memoria del proceso" y, en la misma línea, que una revocación tenga "efecto inmediato con conexión". En el límite son incompatibles: todo TTL mayor que cero es una ventana de revocación.

- **A) Sin caché: una consulta a `rol_permiso` por petición, por clave primaria compuesta.** **Consecuencia:** "efecto inmediato" es literal, que es la propiedad por la que ADR-017 descartó poner los permisos en el token. El costo es una consulta indexada por petición sobre una tabla de decenas de filas, despreciable frente a la consulta de negocio que la petición va a hacer igual.
- **B) TTL corto (5-60 s) por proceso.** **Consecuencia:** ahorra una consulta barata y reintroduce, en pequeño, exactamente la latencia de revocación que ADR-017 rechazó; además hace que el comportamiento dependa de qué worker atienda la petición, que es un modo de falla molesto de reproducir.

**Decisión: A**, con la carga de permisos aislada en una sola función para que agregar un TTL más adelante sea un cambio de una línea si el perfilado lo justifica. Se cumple ADR-017 leyendo "caché breve" como cota superior, no como obligación.

### D6 — Escrituras de este change frente al bus de comandos, que llega en el change 04

`02` §6.5 incluye "altas y modificaciones de maestros" entre lo que pasa por el bus, y usuario, rol y dispositivo son maestros. El bus es el change 04, que depende de este.

- **A) Las escrituras van por `identidad/service.py` desde endpoints delgados, sin `operation_id`, sin `commit` en el servicio (la transacción la abre el endpoint), y `tasks.md` del change 04 hereda la tarea explícita de envolverlas en comandos.** **Consecuencia:** el servicio queda con la forma que el handler del change 04 va a necesitar (recibe contexto, no hace `commit`, lanza errores de dominio), así que el 04 envuelve en lugar de reescribir. Durante un change, tres endpoints de maestros viven fuera del bus, lo que `04` §5 permite explícitamente ("después del 04, ninguna escritura se implementa fuera del bus").
- **B) Este change no expone ninguna escritura HTTP: usuarios, roles y dispositivos se crean solo por el comando de siembra, y los endpoints llegan con el bus.** **Consecuencia:** evita la deuda, pero incumple el entregable del roadmap para el change 03 ("registro y revocación de dispositivos", `04` §5) y deja SEG-02 sin forma de ejercerse; además el único endpoint de negocio para cerrar INV-21 sería de lectura, cubriendo la mitad del invariante ("obtiene" sí, "modifica" no).

**Decisión: A.** Las tres escrituras (alta de usuario, revocación de dispositivo, rotación de PIN) se marcan en el código y en `tasks.md` como deuda nominada del change 04, igual que el change 02 nominó las dos FK pendientes (su D3).

**Los endpoints de `/auth` quedan permanentemente fuera del bus**, y eso no es deuda: no son operaciones de negocio, no tienen `operation_id` ni pueden tenerlo (el de login ocurre antes de que exista un usuario autenticado que lo genere) y `02` §6.5 no los lista.

### D7 — El catálogo global `permiso` y las verificaciones estructurales del change 02

`03` §4 define `permiso` con clave primaria `codigo` y **sin** `organizacion_id`: es un catálogo global sincronizado por migración. La prueba estructural del change 02 exige `organizacion_id NOT NULL` y `UNIQUE (organizacion_id, id)` en toda tabla de negocio.

- **A) Lista explícita y enumerable de tablas globales exentas (`permiso`, más `alembic_version`), igual que la lista de rutas de sistema del ratchet.** **Consecuencia:** la exención se lee de un solo lugar, se revisa en el diff y no se puede ampliar sin que se note. Una tabla de negocio nueva que alguien agregue a la lista por conveniencia queda visible para siempre.
- **B) Darle `organizacion_id` a `permiso` y duplicar las 39 filas por organización.** **Consecuencia:** contradice `03` §4 y convierte el catálogo de permisos —que está atado al código, no a la organización— en dato replicado que hay que mantener sincronizado en cada alta de organización.

**Decisión: A.** `rol_permiso` sí lleva `organizacion_id` (`03` §4), así que la relación entre roles y permisos queda dentro del patrón de aislamiento; lo global es solo el catálogo.

### D8 — De dónde sale el primer usuario administrador

`python -m app.seed` (change 02, su D4) siembra la organización inicial. Alguien tiene que poder entrar por primera vez.

- **A) La siembra se extiende: crea las cinco plantillas de rol con su composición de `01` §19 y un usuario administrador cuya contraseña sale de una variable de entorno obligatoria; si no está definida, la siembra falla en vez de inventar una.** Sigue siendo idempotente: reejecutarla no pisa la contraseña de un usuario existente. **Consecuencia:** no existe ninguna contraseña por defecto en el repositorio ni en la imagen, que es el modo estándar de que un sistema salga a producción con `admin/admin`.
- **B) Una contraseña inicial fija y un cambio obligatorio en el primer login.** **Consecuencia:** la ventana entre el despliegue y el primer login es una puerta abierta con una contraseña publicada en el repositorio; y "cambio obligatorio en el primer login" es una máquina de estados de usuario que `01` §18 no define.

**Decisión: A.** El catálogo de permisos y las plantillas de rol van por migración (`03` §17 lo exige para datos de catálogo atados al código); el usuario administrador va por la siembra, porque es un dato de negocio con organización (mismo criterio que la D4 del change 02).

## Risks / Trade-offs

- **El change es grande para el tamaño que fija `04` §2 (medio día a tres días).** Siete capacidades, siete tablas, dos migraciones y frontend. → El roadmap ya lo definió con este alcance, así que no lo divido por mi cuenta; `tasks.md` queda ordenado para que el corte natural, si hace falta, sea entre los grupos 1-7 (identidad, autenticación, auditoría, backend completo y verificable) y 8-9 (dispositivos en el frontend y pantallas). Si al implementar se desborda, ese es el punto de corte a proponer.
- **D1 y D2 bloquean partes del change, no el change entero.** → El rate limit es un decorador delante del handler de login y el PIN es una columna con su endpoint: ambos se pueden dejar para el final sin bloquear autenticación, permisos ni auditoría. Las tareas están agrupadas de modo que lo bloqueado quede junto y al final.
- **Los dos roles de base rompen el entorno de desarrollo de quien ya lo tenga levantado** (el volumen existente tiene un solo rol). → La migración crea los roles con `IF NOT EXISTS` y el `README` documenta el paso; el arnés de Testcontainers los crea desde cero en cada corrida, así que CI no arrastra estado.
- **Un refresh token robado sigue siendo utilizable hasta que se use** (la detección de reuso es reactiva: descubre el robo recién cuando el legítimo y el atacante usan el mismo token). → Es la propiedad que ADR-017 ya aceptó al elegir rotación con detección de familia; la mitigación es la revocación de dispositivo (SEG-02) y la vida corta del access token.
- **La prueba de INV-21 sobre rutas crece con cada endpoint y puede volverse lenta.** → Recorre rutas, no combinaciones; con dos organizaciones y una petición por ruta el costo es lineal y hoy son menos de diez rutas.

## Migration Plan

1. Migración A (esquema): las siete tablas de `03` §4 y §13, con `UNIQUE (organizacion_id, id)` y FK compuestas donde corresponde; `permiso` sin organización (D7); `auditoria` sin `UPDATE`/`DELETE` para el rol de aplicación (D3).
2. Migración B (catálogo): los 39 permisos de `01` §19 y las cinco plantillas de rol con su composición y topes. Es datos atados al código, así que va por migración (`03` §17) y es idempotente (`ON CONFLICT DO NOTHING`).
3. Los roles de base se crean antes de las migraciones, en la provisión del entorno, no dentro de una migración: Alembic corre **como** el rol dueño, así que no puede crearse a sí mismo.
4. `downgrade` de ambas revisiones probado sobre una base con datos (`04` §2.1, punto 4). El `downgrade` de B borra filas de catálogo, no de negocio, así que no choca con TR-06.
5. Despliegue: no hay versión anterior en producción, así que no aplica la compatibilidad hacia adelante de `02` §14; a partir de este change sí, porque ya habrá sesiones activas.
6. Rollback: revertir ambas revisiones deja el sistema en el estado del change 02 (sin rutas de negocio). No hay datos de negocio que perder salvo los usuarios creados.

## Open Questions

- Nombre exacto y prefijo inicial que el servidor asigna al primer dispositivo (`V01`, `D01`). `02` §7.7 fija que el servidor lo asigna y que es único por organización, no su forma. Es un formato sin efecto sobre specs ni tareas: se resuelve al implementar y se documenta en la spec de dispositivos.
- Umbral a partir del cual conviene purgar `intento_login` y cada cuánto corre la purga (D1, si se aprueba A). No afecta el contrato ni el comportamiento observable del límite; se ajusta con volumen real.

(El vencimiento deslizante del refresh no es una pregunta abierta: ADR-017 dice "deslizante", así que se renueva en cada rotación. Queda fijado como escenario en la spec de autenticación.)
