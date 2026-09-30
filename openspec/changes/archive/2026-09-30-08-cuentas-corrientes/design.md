# Diseño técnico — 08-cuentas-corrientes

> **Estado: D1 a D14 aprobadas (2026-09-29).** El usuario aprobó la opción A en cada una de D1 a D13, y D14 (agregar `dispositivo_id` a `cuenta_movimiento`) como decisión nueva. Las marcadas "requiere ADR" se registran en `docs/adr/` en el grupo final de tareas (grupo 9), junto con las actualizaciones de `docs/01` y `docs/03` que estas decisiones piden; ningún ADR está escrito todavía.

## Context

`docs/` resuelve lo esencial del libro: qué es un movimiento (CC-01), qué tipos hay (CC-02, CC-03), que el saldo se deriva del libro (CC-04), que nada se edita ni se borra (CC-06, TR-06, INV-05), cómo se muestra el estado de cuenta (CC-07), las columnas de `cuenta_movimiento` y `saldo_cuenta` (`03` §12), la tabla de saldo materializada con su bloqueo y su orden global (`02` §7.2, §7.3, ADR-015), los dos usuarios de PostgreSQL con sus permisos por tipo de tabla (ADR-020) y que `SALDO_INICIAL_REGISTRAR` es un comando solo online (`02` §6.5). `01` §21 agrega que el saldo inicial puede ser + o − en clientes y proveedores y que se audita.

Lo que `docs/` **no** resuelve, y por eso este documento plantea como decisiones del usuario:

- `01` §19 no tiene un permiso para registrar saldos iniciales ni uno para ver la cuenta corriente.
- En la etapa 1 no existe el tipo `AJUSTE` (CC-02 lo deja para la etapa 2): nada dice cómo se corrige un saldo inicial mal cargado, ni cuántos admite una cuenta, ni hasta cuándo.
- `03` §2.4 exige claves foráneas compuestas entre entidades de negocio, pero `entidad_id` apunta a veces a `cliente` y a veces a `proveedor`: una FK común no puede apuntar a dos tablas.
- `02` §5.3 dice que `cuentas_corrientes` no depende de ningún otro módulo de negocio (`clientes ──► cuentas_corrientes`, `proveedores ──► cuentas_corrientes`), así que el libro no puede preguntarle a `clientes` si un cliente existe o en qué estado está.
- `03` §2.3 dice que toda tabla de negocio tiene `id`, y `03` §12 le da a `saldo_cuenta` una clave primaria compuesta sin `id`. La prueba genérica de INV-02 (`test_inv02_aislamiento_esquema.py`) exige `UNIQUE (organizacion_id, id)`.
- La spec `clientes/fichas-de-cliente` dejó dicho que CLI-06 (un `INACTIVO` con operaciones no se reactiva) se activa "en el change que registre la primera operación". Este puede ser ese change.

Restricciones que condicionan todo el diseño: `CLAUDE.md` §4 (dinero en `Decimal`/`numeric`, strings en JSON, libros de solo inserción, saldos calculados en SQL, bus de comandos, handlers sin `commit`, UUIDv7, `timestamptz`, reloj inyectable, 404 para lo ajeno) y la deuda del despacho genérico del bus: todo comando `ONLINE` tiene ruta de escritura dedicada que llama a `sync_service.procesar_comando` (enmienda de D9 del change 07; la corrige el change 17).

## Goals / Non-Goals

**Goals:**

- Un `cuentas_corrientes/service.py` que 11, 12, 17, 18a, 18b y 19 puedan usar sin reescribir nada: registrar un movimiento con la fila de saldo bloqueada, leer y bloquear el saldo, y saber si una cuenta tiene movimientos.
- Que la base, y no solo el código, garantice INV-05 (permisos) e INV-02 (FK compuestas) sobre el libro.
- Que INV-13 quede probado con Hypothesis contra PostgreSQL real.
- Una pantalla usable: ver la cuenta corriente y cargar un saldo inicial.

**Non-Goals:**

- No se escriben movimientos de venta, cobranza, compra ni pago, ni sus anulaciones.
- No se evalúa crédito (18b) ni se agrega el saldo al bootstrap (21).
- No se programa la tarea diaria de consistencia (28): solo se deja la consulta.
- No se agrega importación por planilla (10).

## Decisions

### D1 — Qué permiso registra un saldo inicial · requiere ADR

**Qué hay que decidir.** Quién puede cargar la deuda previa de un cliente o de un proveedor. Es una escritura que cambia saldos sin que exista una venta o compra detrás, así que es sensible.

- **A (recomendada).** `IMPORTAR_DATOS` ("Importaciones y puesta en marcha", `01` §19). `00` §5 pone los saldos iniciales dentro de "Puesta en marcha", y el change 10 los va a importar con ese mismo permiso. Con las plantillas actuales, solo el Administrador lo tiene.
- **B.** El permiso de la entidad: `GESTIONAR_CREDITO` para clientes y `GESTIONAR_PROVEEDORES` para proveedores. Como el bus declara un permiso por tipo de comando, obliga a partir el comando en dos (`SALDO_INICIAL_CLIENTE_REGISTRAR` y `..._PROVEEDOR_...`), distinto de `02` §6.5.
- **C.** Un permiso nuevo `REGISTRAR_SALDO_INICIAL` en `01` §19, con migración del catálogo `permiso`.

**Qué implica.** A: no cambia el catálogo; la carga manual y la importación usan el mismo permiso, que es lo coherente. La consecuencia es que Administración (GES) no puede cargar saldos iniciales salvo que se le agregue `IMPORTAR_DATOS` a su rol (cambio de plantilla, no de código). B: Administración sí podría, pero "editar el límite de crédito" y "crear deuda" quedan bajo el mismo permiso, que son cosas distintas, y el comando se parte en dos. C: es lo más explícito, pero agrega un permiso para una tarea que se hace una vez en la vida de la organización.

**Aprobada (2026-09-29).** El usuario eligió la opción A: `IMPORTAR_DATOS` registra el saldo inicial, tanto a mano como por la importación del change 10.

### D2 — Qué permiso permite ver la cuenta corriente · requiere ADR

**Qué hay que decidir.** `01` §19 no tiene "ver cuenta corriente". El ratchet de rutas exige un permiso por ruta.

- **A (recomendada).** Quien puede ver la ficha puede ver su cuenta: `GESTIONAR_CLIENTES` para el estado de cuenta de un cliente y `GESTIONAR_PROVEEDORES` para el de un proveedor. Es el mismo criterio que ADR-031 punto 3 (ver el crédito no exige poder editarlo).
- **B.** `VER_REPORTES` para las dos cuentas.
- **C.** Un permiso nuevo `VER_CUENTAS_CORRIENTES` en `01` §19.

**Qué implica.** A: ADM, GES y SUP ven la cuenta de los clientes; ADM y GES la de los proveedores. El rol Consulta/Dirección (CON) no la ve en esta pantalla; sus saldos le llegan con el reporte de saldos del change 26 (`VER_REPORTES`). El vendedor tampoco: `01` §19 dice que ve el saldo de sus clientes, y eso llega con el bootstrap (SYN-11, change 21), no con esta pantalla de `/admin`. B: ADM, GES, SUP y CON verían todas las cuentas, incluida la de proveedores para SUP, que hoy no ve la ficha del proveedor; y el permiso de "reportes" pasaría a gobernar una pantalla operativa. C: explícito, pero agrega un permiso y obliga a decidir su reparto por rol.

**Aprobada (2026-09-29).** El usuario eligió la opción A: `GESTIONAR_CLIENTES` para la cuenta de un cliente, `GESTIONAR_PROVEEDORES` para la de un proveedor.

### D3 — Cuántos saldos iniciales admite una cuenta, cómo se corrige uno mal cargado y hasta cuándo · requiere ADR

**Qué hay que decidir.** Un saldo inicial es un movimiento del libro, y el libro no se edita (CC-06). En la etapa 1 no hay ajustes (CC-02). Si alguien carga $150.000 en vez de $130.000, hace falta una forma de corregirlo sin borrar.

- **A (recomendada).** Una cuenta admite **varios** `SALDO_INICIAL`, cada uno con su sentido. Un error se corrige con otro saldo inicial en sentido contrario por la diferencia ($20.000 `REDUCE`); los dos quedan visibles en el estado de cuenta y en la auditoría. Se admiten **solo mientras la cuenta no tenga movimientos de otro tipo** (`CUENTA_CON_OPERACIONES`): pasada la puesta en marcha, la corrección tiene que esperar a los ajustes de la etapa 2.
- **B.** Un **único** saldo inicial por cuenta (índice único parcial), sin forma de corregirlo en la etapa 1.
- **C.** Un único saldo inicial, más un comando de anulación que inserta el movimiento inverso con un tipo nuevo `ANULACION_SALDO_INICIAL`; exige agregar ese tipo a CC-02 y CC-03.

**Qué implica.** A: no inventa tipos, respeta CC-02/CC-03 tal como están y deja corregir errores de carga, que en una puesta en marcha con 200 clientes van a ocurrir. El costo: el estado de cuenta puede mostrar dos o tres líneas de saldo inicial en vez de una, y la regla "solo sin otras operaciones" es una regla de negocio nueva (se propondría como CC-08 en `01` §12.1). En este change ningún módulo escribe otros tipos, así que la restricción queda latente, como CLI-06 en el 07. B: lo más simple, pero un error de carga queda para siempre en la cuenta hasta la etapa 2, o se "compensa" con operaciones falsas, que es peor. C: la corrección queda más prolija en pantalla, pero cambia el catálogo de tipos de `01` y agrega un comando más.

**Aprobada (2026-09-29).** El usuario eligió la opción A: varios `SALDO_INICIAL` por cuenta, corrección por saldo inverso, admitidos solo mientras la cuenta no tenga movimientos de otro tipo. La regla nueva se propone como CC-08 en `01` §12.1 (tarea 9.1).

### D4 — A qué clientes y proveedores se les puede cargar saldo inicial · requiere ADR

**Qué hay que decidir.** Si el estado de la entidad importa. `docs/` no lo dice.

- **A (recomendada).** A cualquiera, sin importar el estado (cliente `ACTIVO`, `SUSPENDIDO` o `INACTIVO`; proveedor activo o inactivo), **salvo al consumidor final**, que se rechaza con `CONSUMIDOR_FINAL_SIN_CUENTA`. La deuda previa existe aunque el cliente esté suspendido o dado de baja; y el consumidor final es un cliente genérico con límite cero (CLI-03) que no identifica a ningún deudor.
- **B.** Solo a entidades activas (cliente `ACTIVO` o `SUSPENDIDO`, proveedor activo).
- **C.** A cualquiera, incluido el consumidor final.

**Qué implica.** A: permite cargar la deuda de un cliente al que ya no se le vende pero todavía debe, que es un caso real de puesta en marcha. No necesita leer el estado del cliente, así que el libro no depende de `clientes` (ver D7); para saber quién es el consumidor final alcanza con la configuración de la organización, que `cuentas_corrientes` puede leer de `identidad/service.py`. B: obliga al libro a leer el estado del cliente y del proveedor, lo que requiere puertos registrados por `clientes` y `proveedores` (D7-B), y un cliente dado de baja con deuda no se podría cargar. C: permite deuda en una cuenta sin titular, que nadie podría cobrar.

**Aprobada (2026-09-29).** El usuario eligió la opción A: cualquier estado admite saldo inicial, salvo el consumidor final.

### D5 — Cómo se expresa el saldo inicial en el comando

**Qué hay que decidir.** La forma del contenido. `03` §12 guarda `importe > 0` y `sentido`.

- **A (recomendada).** `cuenta_tipo`, `entidad_id`, `importe` (string positivo con hasta dos decimales, sin redondear: más decimales se rechaza) y `sentido` (`AUMENTA`/`REDUCE`), igual que las columnas. El momento es el `occurred_at` del sobre (TR-05), y el movimiento guarda `origen_tipo = SALDO_INICIAL` y `origen_id = operation_id`, porque no hay una tabla de "saldo inicial" a la que apuntar. En pantalla, el sentido se muestra como "Nos debe" / "Saldo a favor".
- **B.** Un `importe` con signo (negativo = a favor) que el servidor traduce a sentido.
- **C.** Como A, más una `fecha_corte` explícita (puede ser anterior a hoy, no futura) que se usa como `occurred_at`.

**Qué implica.** A: el contenido es la columna misma, sin traducciones; un cero se rechaza igual que en la base. B: más corto de escribir a mano, pero el signo es fácil de invertir por error (¿negativo es que debe o que le deben?) y hay que traducir en dos lados. C: sirve si la puesta en marcha quiere fechar los saldos al día de corte (por ejemplo, el 31 del mes anterior). Con A, el saldo inicial queda con la fecha en que se cargó; como no hay otras operaciones antes (D3), el orden del estado de cuenta es el mismo.

**Aprobada (2026-09-29).** El usuario eligió la opción A: `cuenta_tipo`, `entidad_id`, `importe` positivo y `sentido`, sin `fecha_corte`.

### D6 — Cómo garantiza la base que `entidad_id` pertenece a la organización · requiere ADR

**Qué hay que decidir.** `03` §2.4 exige FK compuestas, y `entidad_id` apunta a dos tablas según `cuenta_tipo`.

- **A (recomendada).** Mantener `cuenta_tipo` y `entidad_id` como dice `03` §12, y agregar dos columnas **generadas** por la base: `cliente_id` (= `entidad_id` si `cuenta_tipo = CLIENTE`, si no nulo) y `proveedor_id` (ídem para `PROVEEDOR`), cada una con su FK compuesta `(organizacion_id, cliente_id) → cliente` y `(organizacion_id, proveedor_id) → proveedor`. Lo mismo en `saldo_cuenta`. Nadie escribe esas columnas: las calcula PostgreSQL.
- **B.** Reemplazar `entidad_id` por dos columnas normales `cliente_id` y `proveedor_id` nulables, con un `CHECK` de que exactamente una está cargada y coincide con `cuenta_tipo`.
- **C.** Sin FK: la existencia y la organización las valida el servicio.

**Qué implica.** A: la base impide que un movimiento apunte a un cliente de otra organización, a uno inexistente o a un proveedor con `cuenta_tipo = CLIENTE`, sin cambiar las columnas documentadas; y la FK tiene un efecto útil: al insertar un movimiento, PostgreSQL toma un bloqueo liviano sobre la fila del cliente, que serializa el saldo inicial con una reactivación concurrente (D8). El costo es una técnica poco común (FK sobre columna generada), que se documenta en el ADR y se prueba. B: equivalente en garantías, pero cambia el modelo de `03` §12 y el índice principal. C: contradice `03` §2.4 y la prueba genérica `test_inv02_ninguna_fk_entre_tablas_de_negocio_es_simple` pasaría sin proteger nada; un error del servicio dejaría deuda de una organización colgada de otra.

**Aprobada (2026-09-29).** El usuario eligió la opción A: columnas generadas `cliente_id`/`proveedor_id` con FK compuestas, en `cuenta_movimiento` y en `saldo_cuenta`.

### D7 — Dónde vive cada pieza sin romper las dependencias entre módulos · requiere ADR

**Qué hay que decidir.** El libro (`cuentas_corrientes`) no puede importar `clientes` ni `proveedores` (`02` §5.3). Pero el comando tiene que responder 404 si la entidad no existe, y el estado de cuenta también.

- **A (recomendada).** La escritura (`SALDO_INICIAL_REGISTRAR`, `POST /api/v1/cuentas-corrientes/saldos-iniciales`) vive en `cuentas_corrientes` y valida la entidad **por la FK de D6**: si la base rechaza la referencia, el repositorio lo traduce a 404, como ya hace catálogo con el proveedor (ADR-025). El consumidor final (D4) se reconoce leyendo la configuración de la organización por `identidad/service.py`. Las lecturas viven con su entidad: `GET /api/v1/clientes/{id}/cuenta-corriente` en `clientes/api.py` y `GET /api/v1/proveedores/{id}/cuenta-corriente` en `proveedores/api.py`, que ya saben responder 404 y llaman a `cuentas_corrientes/service.py` (dependencia permitida). Coincide con `02` §11, que agrupa "clientes, estado de cuenta".
- **B.** Todo en `cuentas_corrientes`, con **puertos** que `clientes` y `proveedores` registran al arrancar para responder "existe y en qué estado está" (el patrón de ADR-023 y ADR-025, con falla cerrada si falta el registro).
- **C.** Dos comandos, uno en `clientes` y otro en `proveedores`, que llaman al servicio del libro.

**Qué implica.** A: sin puertos nuevos ni ciclos; cada módulo hace lo que ya sabe hacer. Solo funciona si D4 no exige leer el estado de la entidad (con D4-B hace falta B). B: es necesario si se elige D4-B; sería el tercer uso del patrón de puertos, y ADR-025 ya advirtió que en ese caso conviene pensar un mecanismo común, que agranda este change. C: se aparta de `02` §6.5 (un solo `SALDO_INICIAL_REGISTRAR`) y duplica la validación del importe y del sentido.

**Aprobada (2026-09-29).** El usuario eligió la opción A: escritura y lectura de saldo/estado de cuenta divididas como en A, coherente con D4-A.

### D8 — ¿Un saldo inicial cuenta como "operación" para CLI-06? · requiere ADR

**Qué hay que decidir.** CLI-06 y ADR-030: un cliente `INACTIVO` vuelve a `ACTIVO` solo si no tiene operaciones. Hoy `clientes/service.py::modificar_cliente` recibe `tiene_operaciones` como dato y el handler pasa siempre `False`.

- **A (recomendada).** Sí: un cliente tiene operaciones si su cuenta corriente tiene **cualquier** movimiento, incluido un saldo inicial. El handler de `CLIENTE_MODIFICAR` lo pregunta a `cuentas_corrientes/service.py::cuenta_tiene_movimientos` (dependencia permitida) después de bloquear la fila del cliente. Como ventas y cobranzas también escriben en el libro, la misma consulta las cubre cuando lleguen.
- **B.** No: solo cuentan ventas, cobranzas y compras; cada change registra su verificador.
- **C.** Solo si el saldo actual es distinto de cero.

**Qué implica.** A: activa CLI-06 hoy, sin esperar al 17 o al 18a, y cumple el espíritu de ADR-030: no revivir deudores. Un cliente dado de baja por error al que ya se le cargó un saldo inicial no se puede reactivar (habría que crear otro). La concurrencia entre reactivación y saldo inicial queda serializada por la FK de D6-A (se prueba). B: un cliente inactivo con $150.000 de deuda previa podría reactivarse sin revisión, que es justo lo que ADR-030 quiso evitar. C: un cliente que debía y saldó a cero podría revivirse, y la regla depende de un número que cambia.

**Aprobada (2026-09-29).** El usuario eligió la opción A: cualquier movimiento del libro, incluido `SALDO_INICIAL`, cuenta como operación para CLI-06.

### D9 — Estado de cuenta: período, saldo anterior y paginación

**Qué hay que decidir.** `02` §11 exige cursor y límite por página, y CC-07 exige saldo acumulado calculado al consultar. Con paginación, cada página tiene que arrancar desde el acumulado correcto.

- **A (recomendada).** Filtro opcional `desde`/`hasta` (fechas de negocio en la zona horaria de la organización, TR-04). La respuesta trae `saldo_anterior` (suma SQL de lo anterior a `desde`, o `"0.00"`), el saldo actual y los movimientos en orden ascendente `(occurred_at, id)` con `SUM(...) OVER (ORDER BY occurred_at, id)` calculado sobre la cuenta completa y filtrado después, para que el acumulado sea siempre el real. El cursor es `(occurred_at, id)` del último movimiento; límite por defecto 50, máximo 200. Usa el índice `(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)` de `03` §16.
- **B.** Sin filtro de período: todo el historial paginado por cursor.
- **C.** Sin paginación: todos los movimientos en una respuesta.

**Qué implica.** A: la pantalla puede mostrar "el último mes" con el saldo con que arrancó, que es como se lee un estado de cuenta en papel. Con ~50.000 movimientos por año en toda la organización (`03` §18), la ventana sobre una sola cuenta es barata. B: más simple, pero para ver el mes actual de un cliente viejo hay que recorrer todas las páginas. C: contradice `02` §11.

**Aprobada (2026-09-29).** El usuario eligió la opción A: filtro `desde`/`hasta` opcional, `saldo_anterior` calculado en SQL, cursor `(occurred_at, id)`.

### D10 — Cómo nace y se bloquea la fila de saldo

**Qué hay que decidir.** La primera vez que una cuenta recibe un movimiento no tiene fila en `saldo_cuenta`. Dos transacciones a la vez no pueden crear dos filas ni perder un movimiento.

- **A (recomendada).** Creación perezosa dentro de la función del servicio: `INSERT ... (saldo 0) ON CONFLICT DO NOTHING` y enseguida `SELECT ... FOR UPDATE`; recién entonces se inserta el movimiento y se hace `UPDATE saldo_cuenta SET saldo = saldo ± importe`. El servicio expone `registrar_movimiento(...)` (bloquea, inserta, actualiza, devuelve el saldo nuevo), `bloquear_saldo(...)` (para que el 18b evalúe crédito con la fila tomada), `obtener_saldo(...)` y `cuenta_tiene_movimientos(...)`; ninguno hace `commit`.
- **B.** Creación anticipada: la fila de saldo nace con el cliente o el proveedor, más una migración que la crea para los existentes.
- **C.** Bloqueos consultivos de PostgreSQL (`pg_advisory_xact_lock`) por cuenta en lugar de bloqueo de fila.

**Qué implica.** A: no toca `clientes` ni `proveedores` para crear filas; la carrera de la primera fila la resuelve la restricción de clave, igual que la reserva de idempotencia del 04. B: obliga a modificar dos módulos y una migración de datos, y cualquier alta que se olvide de crear la fila rompe el bloqueo. C: se aparta de ADR-015, que fija el bloqueo sobre la fila de saldo como parte del orden global.

**Aprobada (2026-09-29).** El usuario eligió la opción A: creación perezosa con `INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE`.

### D11 — La clave de `saldo_cuenta`

**Qué hay que decidir.** `03` §2.3 dice que toda tabla de negocio tiene `id`; `03` §12 le da a `saldo_cuenta` clave primaria `(organizacion_id, cuenta_tipo, entidad_id)` sin `id`. La prueba genérica de INV-02 exige `UNIQUE (organizacion_id, id)` o que `organizacion_id` sea la clave primaria entera.

- **A (recomendada).** Seguir `03` §12 (clave compuesta, sin `id`) y ampliar la prueba de INV-02 para aceptar, además, una clave primaria compuesta **que empiece por** `organizacion_id`, con `saldo_cuenta` como caso probado. `03` §2.3 se aclara en el ADR.
- **B.** Agregar `id` UUIDv7 como clave primaria, `UNIQUE (organizacion_id, id)` y `UNIQUE (organizacion_id, cuenta_tipo, entidad_id)`.
- **C.** Agregar `saldo_cuenta` a la lista de exentas de la prueba de INV-02.

**Qué implica.** A: respeta el modelo documentado y la búsqueda del saldo por clave (`03` §16). La prueba sigue exigiendo que la organización esté en la clave, que es lo que INV-02 busca. Lo mismo servirá para `stock_saldo` y `costo_producto` en el change 09. B: agrega una columna que nadie usa (nadie referencia una fila de saldo), pero no hay que tocar la prueba. C: debilita la prueba; la lista de exentas es solo para catálogos globales.

**Aprobada (2026-09-29).** El usuario eligió la opción A: clave compuesta sin `id`, y la prueba de INV-02 se amplía en vez de tocar el modelo.

### D12 — Qué tipos de movimiento acepta la base desde ahora

**Qué hay que decidir.** El `CHECK` de `tipo`. `03` §2.2 elige `CHECK` en vez de `enum` para que agregar valores sea una migración simple.

- **A (recomendada).** Todos los tipos de la etapa 1 de CC-02 (`SALDO_INICIAL`, `VENTA`, `ANULACION_VENTA`, `COBRANZA`, `ANULACION_COBRANZA`) y CC-03 (`SALDO_INICIAL`, `COMPRA`, `ANULACION_COMPRA`, `PAGO`, `ANULACION_PAGO`), con un `CHECK` de coherencia entre `cuenta_tipo` y `tipo`. Los tipos de IVA los agrega el módulo de facturación. El dominio conoce el catálogo completo (sirve a la prueba de propiedades), pero en este change solo `SALDO_INICIAL` tiene comando.
- **B.** Solo `SALDO_INICIAL`; cada change amplía el `CHECK` con su migración.
- **C.** Todos, incluidos `IVA_FACTURA` y `ANULACION_IVA_FACTURA`.

**Qué implica.** A: 11, 12, 17 y 18a no necesitan migrar el libro, y la coherencia cliente/proveedor queda en la base desde el día uno. El costo es declarar tipos que todavía nadie escribe. B: cada change toca la misma restricción; más migraciones, pero cada tipo aparece con su dueño. C: mete en el núcleo tipos de un módulo que no existe y cuyas reglas no están cerradas (FAC).

**Aprobada (2026-09-29).** El usuario eligió la opción A: el `CHECK` declara desde ahora todos los tipos de CC-02/CC-03 de la etapa 1.

### D13 — Alcance del frontend

**Qué hay que decidir.** `04` §3 pide que cada change deje algo verificable, preferentemente una pantalla.

- **A (recomendada).** En `/admin`: saldo actual en la ficha del cliente y del proveedor con enlace a una pantalla "Cuenta corriente" (estado de cuenta con filtro de período y "cargar más"), y el formulario "Registrar saldo inicial" en esa pantalla, dentro de `<SiTienePermiso permiso="IMPORTAR_DATOS">`. Sin sección nueva en el menú.
- **B.** Solo backend; las pantallas llegan con cobranzas (17).
- **C.** Solo el estado de cuenta, sin formulario de saldo inicial (se carga por API o con la importación del 10).

**Qué implica.** A: la verificación manual de `04` §2.1 punto 5 se hace en el navegador y la puesta en marcha se puede hacer a mano antes del 10. B: el punto 5 no se puede cumplir. C: para probar el estado de cuenta en el navegador habría que cargar movimientos por API.

**Aprobada (2026-09-29).** El usuario eligió la opción A: saldo y enlace en la ficha, pantalla "Cuenta corriente" con el formulario de saldo inicial detrás de `IMPORTAR_DATOS`.

### D14 — Agregar `dispositivo_id` a `cuenta_movimiento`

**Qué hay que decidir.** `03` §2.3 pone `dispositivo_id` entre las columnas que toda tabla de operaciones agrega (junto a `operation_id`, `usuario_id`, `occurred_at`, `registered_at`), pero `03` §12 no lo lista entre las columnas de `cuenta_movimiento`. Las Open Questions de este diseño dejaban la elección al usuario: seguir la tabla al pie de la letra (sin la columna, recuperando el dispositivo por `operation_id` desde `comando`/`auditoria`) o agregarla.

- **A (recomendada; elegida).** Agregar `dispositivo_id uuid NOT NULL` a `cuenta_movimiento`, con la misma FK compuesta que ya usan `comando`, `comando_cuarentena` y `sesion_refresh`: `FOREIGN KEY (organizacion_id, dispositivo_id) REFERENCES dispositivo (organizacion_id, id)`.
- **B.** No agregarla; seguir resolviendo el dispositivo por `operation_id` vía `comando`/`auditoria`.

**Qué implica.** El usuario la eligió para auditoría directa (saber desde qué dispositivo se registró cada movimiento sin un `JOIN` a `comando`) y porque las ventas de ruta (offline, change 18a) van a necesitar dejar constancia del dispositivo en el propio libro, igual que hace `venta`/`venta_linea` en el resto del dominio.

**Nulabilidad — NOT NULL.** Se decide por consistencia con el resto de las tablas de "operación" de este dominio, no por invención: `03` §2.3 define `dispositivo_id` como una columna que toda tabla de operaciones agrega, sin marcarla opcional; `SobreComando` (`backend/app/commands/sobre.py`) declara `dispositivo_id: UUID` como campo obligatorio (no `UUID | None`) del sobre de todo comando, online u offline, y los handlers reciben el sobre completo antes de escribir. Las tablas ya existentes que copian el sobre de un comando 1:1 —`comando` y `sesion_refresh`— también lo declaran `NOT NULL` con la misma FK compuesta a `dispositivo`; la única tabla con `dispositivo_id` nulable es `auditoria` (`identidad/models.py`), y es nulable porque `auditoria` también registra acciones sin sobre de comando (por ejemplo, acciones del sistema o de arranque), un caso que no aplica a `cuenta_movimiento`: todo movimiento nace de `SALDO_INICIAL_REGISTRAR` u otro comando con sobre completo. `cuenta_movimiento` sigue entonces el patrón de `comando`/`sesion_refresh`, no el de `auditoria`.

Como el saldo inicial es `ONLINE` (`admite_offline = false`, D1), el sobre siempre trae el dispositivo del usuario autenticado; no hay caso en este change donde falte.

**Consecuencia para D6.** La FK de `dispositivo_id` es independiente de las columnas generadas `cliente_id`/`proveedor_id` de D6-A: no se genera, se escribe directamente desde el sobre, igual que `usuario_id`.

**Tarea pendiente (no se edita `docs/` en este paso).** `docs/03-modelo-de-datos.md` §12 debe actualizarse para listar `dispositivo_id` en `cuenta_movimiento`, junto con las demás aclaraciones de D6 (columnas generadas) y D11 (clave de `saldo_cuenta`); queda como tarea del grupo 9 (ADRs y documentación), no como edición inmediata.

## Risks / Trade-offs

- **FK sobre columnas generadas (D6-A)** es poco habitual → Mitigación: prueba de migración que intenta las tres referencias inválidas (ajena, inexistente, tipo cruzado) y verifica el ciclo `upgrade → downgrade → upgrade` con datos.
- **Desborde de `numeric(14,2)`** en un saldo acumulado muy grande → Mitigación: el dominio acota el importe de entrada al máximo del tipo y el repositorio traduce un desborde numérico a un error de dominio estable en lugar de un 500.
- **La regla "solo sin otras operaciones" (D3-A) queda latente** hasta el 11/17/18a → Mitigación: se prueba insertando por el servicio un movimiento de otro tipo, igual que CLI-06 se probará acá.
- **El estado de cuenta recalcula el acumulado cuando llega un movimiento con `occurred_at` anterior** (ventas offline que sincronizan tarde) → es el comportamiento que pide CC-07; la spec lo fija con un escenario.
- **Solo el Administrador puede cargar saldos iniciales (D1-A)** → cambio de plantilla de rol si Administración lo necesita.
- **Nuevas rutas en los ratchets** (`test_ratchet_permiso_por_ruta.py`, `COBERTURA_DE_AISLAMIENTO` de `test_inv21_ratchet_rutas.py`) y en `TABLAS_DE_LIBRO_DECLARADAS` de `test_inv05_dos_roles.py` → trabajo mecánico en tareas.
- **El despacho genérico de `/sync/comandos` no puede llamar handlers** (deuda del 17) → ruta dedicada, como 06 y 07.

## Migration Plan

Una revisión de Alembic de solo agregado: `cuenta_movimiento` (columnas de `03` §12 **más `dispositivo_id uuid NOT NULL` de D14**, `UNIQUE (organizacion_id, id)`, FK a `organizacion`, FK compuesta `(organizacion_id, dispositivo_id) → dispositivo` de D14, columnas generadas y FK compuestas de D6, `CHECK` de importe, sentido, `cuenta_tipo`, tipo y coherencia de D12, índice `ix_cuenta_movimiento__estado_de_cuenta`), `saldo_cuenta` (clave de D11, mismas FK de D6, `saldo numeric(14,2) NOT NULL DEFAULT 0`, `actualizado_en`) y los `GRANT` de ADR-020: `SELECT, INSERT` sobre el libro y `SELECT, INSERT, UPDATE` sobre el saldo. Sin migración de datos ni permisos nuevos, dado que D1 y D2 quedaron en A. El `downgrade` elimina las dos tablas con `app_migrations`; se prueba subir y bajar sobre una base con movimientos (`04` §2.1 punto 4). Rollback en producción: perder saldos iniciales cargados; aceptable antes de operar con datos reales.

ADRs a registrar (grupo 9, ahora que D1-D14 están aprobadas): uno para D1 y D2 (permisos de cuenta corriente), uno para D3, D4 y D8 (reglas del saldo inicial y su efecto en CLI-06, con la propuesta de agregar la regla a `01` §12.1), y uno para D6, D7 y D11 (integridad referencial polimórfica, validación sin puertos y clave de `saldo_cuenta`, con la aclaración de `03` §2.3/§12, incluido `dispositivo_id` de D14).

## Open Questions

- La importación del change 10 reutilizará `registrar_saldo_inicial` del servicio fila por fila; si necesita fechar al día de corte, reabre D5-C.
