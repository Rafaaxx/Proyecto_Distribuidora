## Context

`02` §6 especifica el pipeline con un detalle poco común: el sobre campo por campo (§6.2), los siete pasos del procesamiento en orden (§6.3), la semántica del lote (§6.4), el catálogo de tipos de la etapa (§6.5) y la compatibilidad de versiones (§6.6). `03` §13 fija las tres tablas. ADR-012 fija la decisión de fondo. Lo que `docs/` **no** resuelve y este documento decide (o eleva a decisión humana): la serialización canónica exacta de la huella (**D1, bloqueante**); cómo se expresa la obligatoriedad de `auditoria.operation_id` sin romper la auditoría del login (**D2, bloqueante**); dónde vive el bus y cómo se registran los handlers (D3); cómo entra el `operation_id` por REST (D4); la curva de espera de los reintentos (D5); hasta dónde llega la cuarentena en este change (D6); cómo se envuelven las tres escrituras del change 03 sin reescribirlas (D7); qué pasa con `comando.jornada_id` mientras `jornada` no existe (D8); y de dónde sale la versión mínima de aplicación (D9).

Restricción que gobierna todo lo demás: el bus es la única puerta de escritura de los changes 05 a 27. Todo lo que quede ambiguo acá se copia veintitrés veces.

## Goals / Non-Goals

**Goals:**

- Que un handler no pueda hacer nada mal por omisión: recibe contexto, devuelve resultado y observaciones, y no tiene forma de confirmar una transacción ni de leer la organización de otro lado que no sea el sobre.
- Que la idempotencia sea una propiedad de la base verificada por pruebas de concurrencia con commits reales, no una convención de código.
- Que la huella quede congelada en un documento y en un juego de fixtures compartidos Python/TypeScript **antes** de que exista el primer dispositivo con cola.
- Que el change 05 (catálogo) pueda escribir su primer comando copiando un handler de maestros de este change, sin decidir nada.

**Non-Goals:**

- Ejercer el modo OFFLINE de punta a punta: no hay jornada (change 15) ni comandos de venta o cobranza (17, 18a). Acá se define y se rechaza donde no corresponde.
- Resolver observaciones y revisar cuarentena: changes 25 y siguientes.
- El lado del dispositivo (cola Dexie, motor de sincronización): changes 22a y 22b. Acá se define el contrato del servidor que esos changes consumen.
- Row Level Security: `02` §8 la posterga a la etapa 4.

## Decisions

### D1 — Serialización canónica de la huella (**BLOQUEANTE**)

`02` §6.2 dice "SHA-256 del contenido en JSON canónico (claves ordenadas, decimales como string)". Eso fija dos propiedades; una serialización canónica necesita fijar además: separadores y espacios, escape de no-ASCII, normalización Unicode del texto, si una clave ausente y una clave con valor nulo dan la misma huella, y la representación de los decimales (`"31250.00"` y `"31250.0"` son el mismo importe y distinta cadena). Cualquiera de esas decisiones tomada distinto por el cliente TypeScript y por el servidor Python produce huellas distintas para el mismo contenido: el reenvío legítimo de un comando encolado se rechazaría como `COMANDO_INCONSISTENTE` (SYN-02) y el vendedor vería una venta real marcada como inconsistente.

- **A) Adoptar JCS (RFC 8785, JSON Canonicalization Scheme) tal cual, con los decimales normalizados a la escala de su columna antes de serializar.** **Consecuencia:** el algoritmo está especificado por un estándar con vectores de prueba públicos, hay implementaciones en ambos lenguajes, y las seis preguntas de arriba quedan contestadas por el documento y no por nosotros. Obliga a normalizar la escala de los decimales antes de serializar, porque JCS canoniza números pero acá los decimales viajan como **texto** y `"31250.0"` ≠ `"31250.00"` como cadena. Agrega una dependencia (o unas treinta líneas propias) por lado.
- **B) Serialización propia mínima: `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` y su equivalente en TypeScript.** **Consecuencia:** cero dependencias y es lo que la mayoría hace. Deja sin fijar el escape de no-ASCII (un nombre con acento serializa distinto según la bandera), la normalización Unicode (NFC vs. NFD: el mismo nombre tipeado en iOS y en Android puede dar bytes distintos) y ausente vs. nulo. Cada una de esas es un rechazo intermitente en producción, imposible de reproducir desde la oficina.
- **C) Firmar el contenido tal como llegó, byte a byte, sin canonizar.** **Consecuencia:** trivial y perfectamente estable **si** el cliente reenvía exactamente los mismos bytes. Pero el sobre se reconstruye al pasar por Pydantic y la cola local de Dexie guarda objetos, no bytes; cualquier reserialización rompe la huella. Además ata la idempotencia a un detalle de transporte.

**Recomendación: A**, con NFC como normalización de texto explícita, decimales normalizados a su escala antes de serializar, y un juego de fixtures compartidos (`backend/tests/fixtures_compartidos/`) que corre los mismos casos en Python y TypeScript y exige la misma huella hexadecimal — incluyendo acentos, emoji, claves fuera de orden, nulos, anidamiento y los decimales del dominio.

**Por qué es bloqueante y no una decisión de este documento:** la huella es un contrato de cable **irreversible**. Una vez que un dispositivo tiene comandos encolados, cambiar el algoritmo invalida la idempotencia de esa cola para siempre, y el efecto es duplicar ventas o rechazarlas, no un error de compilación. **Requiere ADR** (extensión de ADR-012) y confirmación humana antes de implementar el grupo 3 de `tasks.md`. El resto del change puede avanzar: la huella entra al pipeline por una función con firma conocida.

### D2 — `auditoria.operation_id` obligatorio frente a los eventos que no son comandos (**BLOQUEANTE**)

AUD-02 enumera `operation_id` entre lo que "cada registro guarda", y el change 03 lo dejó nulable con un comentario en la migración que nombra a este change como responsable de cerrarlo (su tarea 2.6). Pero AUD-01 manda auditar el inicio de sesión, y el login **no tiene ni puede tener** `operation_id`: ocurre antes de que exista un usuario autenticado que lo genere, y el change 03 (su D6) dejó los endpoints de `/auth` permanentemente fuera del bus. Un `NOT NULL` liso haría imposible auditar el login.

- **A) Columna `origen` (`COMANDO`, `SISTEMA`) con una restricción de verificación: `operation_id` no nulo si y solo si `origen = 'COMANDO'`.** **Consecuencia:** la obligatoriedad queda en la base y es total para lo que sale del bus, que es lo que INV-06 y TR-07 quieren proteger; el login se audita declarando su origen, sin identificador inventado; y una escritura de negocio que intentara colarse fuera del bus tendría que **declararse** `SISTEMA` para pasar, lo que deja un rastro contable y visible en el diff en vez de un nulo silencioso. Cuesta una columna y una migración que rellena los registros existentes con `SISTEMA`.
- **B) Generar un `operation_id` del servidor para los eventos sin comando.** **Consecuencia:** la columna queda `NOT NULL` a secas y el modelo es uniforme, pero el identificador es falso: no corresponde a ningún comando, no es idempotente, no es reenviable y contamina `comando` por asociación. Quien después audite "todas las operaciones" no puede distinguir una operación real de un relleno.
- **C) Dejarla nulable y exigirla solo en código.** **Consecuencia:** cero migración, y exactamente la garantía que ya tenemos hoy: ninguna. Un handler nuevo que se olvide de propagar el identificador no falla en ningún lado.

**Recomendación: A.**

**Por qué es bloqueante:** cambia la lectura de AUD-02 (de "cada registro" a "cada registro originado en un comando"), introduce una clasificación de eventos auditables que `01` §21 no tiene, y toca una tabla de libro de solo inserción. **Requiere confirmación humana** y queda registrado como extensión de ADR-012 o como nota en AUD antes de implementar el grupo 9.

### D3 — Dónde vive el bus y cómo se registran los handlers

`CLAUDE.md` §7 ya reserva `backend/app/commands/` para "bus, sobre, registro de handlers, idempotencia", y `02` §5.3 dice que `sync` depende de todos los módulos con comandos. Hay dos cosas distintas: el **mecanismo** (sobre, huella, reserva, transacción, reintentos) y el **módulo de negocio** de sincronización (tablas, endpoint de lote, cuarentena, observaciones).

**Decisión:** el mecanismo vive en `app/commands/` y no importa ningún módulo; los handlers viven en el módulo dueño de la operación (`identidad/commands.py` para los tres de maestros) y se registran por `(tipo, version)` en un registro explícito que el arranque puebla importando los módulos. El módulo `sync/` es el dueño de `comando`, `comando_cuarentena` y `observacion` y del endpoint de lote; `app/commands/` escribe en esas tablas a través de `sync/service.py`, no de sus repositorios.

**Alternativa descartada:** descubrimiento automático por escaneo de paquetes. Un handler que no se registra porque nadie lo importó es un fallo silencioso en producción; un registro explícito falla en el arranque y se ve en el diff. Se agrega una prueba que exige que todo tipo declarado en el catálogo tenga handler registrado y viceversa.

Contratos de `import_linter` a declarar: `app/commands/` no importa `app/modules/*`; `domain/` de ningún módulo importa `app/commands/`; `sync/` puede importar los `service.py` de los demás módulos.

### D4 — Cómo entra el `operation_id` por REST

`02` §6.2 lo fija: encabezado `Operation-Id` en REST, cuerpo en sync.

**Decisión:** una dependencia de FastAPI que exige el encabezado, lo valida como identificador y arma el sobre en modo `ONLINE` combinándolo con el contexto de sesión que ya devuelve la dependencia de permisos del change 03. Los endpoints de escritura declaran esa dependencia y reciben el sobre armado; no lo construyen. Ausencia del encabezado → 400 con el formato de error de `02` §11, antes de tocar la base.

**Alternativa descartada:** aceptarlo también en el cuerpo por comodidad del frontend. Dos fuentes para el mismo dato es exactamente el patrón que `02` §8 prohíbe para `organizacion_id`, y no hay razón para estrenarlo acá.

### D5 — Curva de espera de los reintentos transitorios

`02` §6.3 fija el disparador (`40001`, `40P01`), el techo (3 intentos) y "espera incremental". No fija los milisegundos.

**Decisión (no bloqueante):** espera exponencial con jitter, base y techo como configuración del backend con valores por defecto conservadores (del orden de decenas de milisegundos, techo por debajo del tiempo de espera del cliente). El jitter importa: sin él, dos lotes que chocan por la misma fila de saldo reintentan en fase y vuelven a chocar. Los valores son parámetros operativos, no regla de negocio: se ajustan sin ADR. Lo que **sí** queda fijo en la spec es que se reintenta la transacción **completa**, incluida la reserva de idempotencia, y que un error de dominio no se reintenta nunca.

### D6 — Hasta dónde llega la cuarentena en este change

SYN-06 manda guardar en cuarentena los comandos de dispositivos revocados "para revisión manual", y `03` §13 le da a la tabla `revisado_en` y `revisado_por_id`. Pero `01` §19 no tiene ningún permiso para revisar cuarentena (el único parecido, `REVISAR_OBSERVACIONES`, es de otra cosa por SYN-08) y ninguna regla dice si un comando en cuarentena puede reenviarse al bus — reenviarlo sería, literalmente, ejecutar la operación de un dispositivo revocado.

**Decisión:** este change **persiste** la cuarentena y no expone ninguna revisión. El endpoint de revisión, el permiso que lo gobierna y la política de reenvío requieren un ADR con decisión humana, y su dueño natural es el change 25 (`observaciones-y-revision`), que ya tiene la bandeja. Las dos columnas de revisión se crean igual, como manda `03` §13: la tabla queda completa y el change 25 solo agrega comportamiento.

**Alternativa descartada:** inventar acá el permiso y el endpoint. Agregar una fila al catálogo de 39 permisos de `01` §19 es una decisión de negocio, y `CLAUDE.md` §8 es explícito: no se toman por cuenta propia.

### D7 — Cómo se envuelven las tres escrituras del change 03

El change 03 (su D6) dejó alta de usuario, revocación de dispositivo y rotación de PIN en `identidad/service.py`, con la forma que un handler necesita: reciben contexto, no hacen `commit`, lanzan errores de dominio. El texto de esa decisión dice que el change 04 "envuelve en lugar de reescribir".

**Decisión:** se cumple literalmente. Por cada una: un tipo de comando (`USUARIO_CREAR`, `DISPOSITIVO_REVOCAR`, `PIN_AUTORIZACION_ROTAR`), un esquema de contenido versión 1, un handler de tres líneas que llama al método de servicio existente, y el endpoint pasa a declarar la dependencia de D4 y a delegar en el bus. El cuerpo del servicio **no se toca**; si hubiera que tocarlo, es señal de que la forma que dejó el change 03 no servía y hay que decirlo, no arreglarlo en silencio.

**Convención de nombres de tipo de comando, que este change establece para los 23 siguientes:** `ENTIDAD_ACCION` en singular y en español, en mayúsculas, con el verbo en infinitivo, como ya hace `02` §6.5 (`VENTA_CONFIRMAR`, `STOCK_TRANSFERIR`). Los maestros no están enumerados en §6.5 ("Altas y modificaciones de maestros"), así que la convención se fija acá.

**Cambio de contrato, que hay que declarar:** esos tres endpoints pasan a exigir `Operation-Id`. El cliente de `/admin` (change 03) genera hoy sus peticiones sin él, así que el frontend cambia en el mismo change: un generador de UUIDv7 en el cliente y el encabezado en cada escritura. No es opcional ni posponible — si se pospone, los tres endpoints quedan rotos.

### D8 — `comando.jornada_id` mientras `jornada` no existe

`03` §13 le da a `comando` una columna `jornada_id`, y `02` §6.2 la marca obligatoria en comandos de ruta. La tabla `jornada` llega en el change 15.

**Decisión:** la columna se crea ahora, nulable y **sin** clave foránea, y se nomina explícitamente como deuda del change 15, igual que el change 02 nominó sus dos FK pendientes (su D3) y el 03 nominó estas tres escrituras. La tarea correspondiente queda escrita en este `tasks.md` para que el 15 la herede. La obligatoriedad por tipo de comando (§6.2: "obligatorio en comandos de ruta") se valida en el esquema del tipo, no en la columna, porque depende del tipo y no de la tabla.

**Alternativa descartada:** omitir la columna hasta el change 15. Obliga a una migración que altera `comando` cuando ya tiene volumen, y deja el sobre incompleto respecto de `02` §6.2 justo en el change que lo define.

### D9 — De dónde sale la versión mínima de aplicación

`02` §6.6 dice que el servidor la publica, sin decir dónde se configura ni por dónde se consulta.

**Decisión:** configuración del backend (no de la organización: es una propiedad del despliegue, igual que la versión desplegada) y se publica extendiendo el `GET /version` que ya existe del change 01a, en vez de estrenar un endpoint. Con la versión mínima ausente, no se bloquea nada: el valor por defecto no restringe, igual que `/version` responde `dev` cuando no está configurada.

**Alternativa descartada:** guardarla en `configuracion_organizacion` (change 02). Una organización no elige qué versión de la aplicación tolera el servidor que la atiende; sería un parámetro de negocio para una decisión de despliegue.

## Risks / Trade-offs

- **[La huella se implementa distinto en los dos lenguajes y no se nota hasta que hay dispositivos en la calle]** → Fixtures compartidos que corren en Python y TypeScript y exigen la misma huella hexadecimal, incluidos acentos, emoji, nulos y decimales; son parte de la definición de terminado de este change, no un extra.
- **[El bus se convierte en el cuello de botella de veintitrés changes y cualquier error de diseño se copia]** → Los handlers de maestros de este change quedan como plantilla explícita y una prueba exige que todo tipo del catálogo tenga handler registrado. El grupo de verificación incluye una prueba que recorre las rutas de escritura y exige que ninguna escriba sin pasar por el bus — la señal temprana que pide `04` §14.
- **[La reserva de idempotencia bloquea transacciones concurrentes del mismo `operation_id` y se confunde con un interbloqueo]** → Es el comportamiento buscado (`02` §6.3: PostgreSQL bloquea el `INSERT` hasta que la otra transacción termina). Se cubre con una prueba de concurrencia con commits reales, y el clasificador de errores transitorios distingue `40001`/`40P01` de cualquier otro fallo.
- **[Hacer obligatorio `operation_id` rompe la auditoría del login y no se descubre hasta el despliegue]** → D2 lo resuelve por diseño y el spec de auditoría tiene un escenario explícito de login auditado sin identificador de operación; la migración se verifica con datos representativos de ambos orígenes, como exige `04` §2.1 punto 4.
- **[El frontend de `/admin` queda roto al exigir `Operation-Id` en los tres endpoints]** → D7 lo declara como parte del alcance y no como consecuencia; las pruebas de esos endpoints cubren la ausencia del encabezado y el frontend se prueba a mano antes de cerrar el change.
- **[La cuarentena acumula comandos que nadie revisa hasta el change 25]** → Aceptado y explícito: SYN-06 exige que no se pierdan, no que se revisen ya. El volumen es despreciable (solo dispositivos revocados) y `03` §18 no lo contempla como tabla de volumen.

## Migration Plan

Una sola revisión de Alembic con las tres tablas, la columna `origen` de `auditoria` con su restricción de verificación (D2) y los `GRANT` de ADR-020: `comando` (`SELECT, INSERT, UPDATE`, sin `DELETE`: el estado pasa de intermedio a final), `comando_cuarentena` (`SELECT, INSERT, UPDATE`, sin `DELETE`) y `observacion` (`SELECT, INSERT, UPDATE`, sin `DELETE`: se resuelve en el change 25, nunca se borra).

El relleno de `auditoria.origen` recorre los registros existentes y los marca `SISTEMA`: todos son del change 03 y ninguno salió del bus, que no existía. `downgrade` quita la restricción y la columna antes de dropear las tablas, y se verifica `upgrade head` → `downgrade base` → `upgrade head` sobre una base **con datos** de ambos orígenes.

No hay despliegue en producción todavía (change 27a), así que no hay estrategia de vuelta atrás en caliente que diseñar.

## Open Questions

- Si el `COSTO_INFORMAR` y los demás tipos de `02` §6.5 necesitan una versión inicial distinta de 1 cuando lleguen sus changes. No afecta a este change: el registro es por `(tipo, version)` desde el primer día.
- Si la purga de `comando` (volumen estimado ~60.000 en `03` §18) necesita tarea programada antes de la etapa 2. No cambia el esquema ni el pipeline.
