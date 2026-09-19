## Context

Ver `proposal.md` — Why. Estado actual relevante: `backend/app/modules/` está vacío; `backend/app/api_v1/sistema.py` expone `/salud` y `/version`; Alembic tiene una única revisión base vacía; `backend/tests/integration/conftest.py` levanta PostgreSQL real con Testcontainers y aísla por transacción revertida; `core/{money,clock,ids,errors}.py` existen desde `01b`.

`03` §2.3, §2.4 y §4 fijan el esquema al detalle, y `01` §4 fija los parámetros. Lo que `docs/` **no** resuelve y este documento decide: qué hacer con el aislamiento cuando todavía no existe el token del que `02` §8 dice que sale `organizacion_id` (el JWT llega en el change 03); en qué módulo vive cada tabla ante una discrepancia entre `02` §5.1 y `03` §3; qué hacer con dos columnas cuya tabla destino no existe; dónde vive la siembra de la organización inicial; y si este change entrega pantalla.

## Goals / Non-Goals

**Goals:**
- Dejar el patrón de aislamiento (columna, unicidad compuesta, FK compuesta, repositorio con organización obligatoria) como algo que los changes 03..27 copian sin decidir nada de nuevo.
- Que INV-21 tenga desde hoy un mecanismo que **falle solo** cuando un change futuro agregue una ruta de negocio sin cubrirla, en vez de una prueba que haya que acordarse de escribir.
- No introducir ningún sustituto temporal de la autenticación que alguien pueda copiar por error en el change 03.

**Non-Goals:**
- Diseñar el contrato HTTP de administración de organización y configuración: se diseña en el change 03, sobre el bus (change 04) y con permisos reales.
- Row Level Security de PostgreSQL: `02` §8 la posterga explícitamente a la etapa 4.

## Decisions

### D1 — Cómo se satisface `02` §8 ("`organizacion_id` se toma del token") sin token

`02` §8 exige que la organización venga del token y que exista una prueba que recorra todos los endpoints con un usuario de otra organización (INV-21). El JWT, el usuario y el login son el change 03. Alternativas:

- **A) Sin rutas de negocio en este change. El aislamiento se define y se prueba en la capa de datos, y INV-21 queda instalado como ratchet de rutas.** El repositorio y el servicio reciben `organizacion_id` como primer parámetro obligatorio; las pruebas los invocan directamente con dos organizaciones. La prueba de INV-21 recorre `app.routes` y falla si aparece una ruta que no esté ni en la lista de rutas de sistema (`/salud`, `/version`, `/openapi.json`, `/docs`, `/redoc`) ni en la cobertura de aislamiento. **Consecuencia:** hoy la prueba de rutas pasa sin ejercitar nada de negocio (no hay ninguna), pero el change 03 no puede agregar su primer endpoint sin que la suite se ponga roja hasta cubrirlo. El aislamiento real sí queda probado, en la capa donde hoy existe. La regla "sale del token" se cumple por vacuidad: no hay ninguna otra fuente porque no hay ninguna ruta.
- **B) Un mecanismo de desarrollo que lea `organizacion_id` de una cabecera o un parámetro de consulta, para poder exponer endpoints ya.** **Consecuencia:** contradice directamente la regla no negociable de `CLAUDE.md` §4 ("`organizacion_id` se toma siempre del token JWT, nunca del cuerpo de la petición") y deja en el repositorio un patrón copiable que, si sobrevive al change 03, es una escalada de privilegios entre organizaciones en producción. El costo de removerlo después es exactamente el riesgo de olvidarse de removerlo.
- **C) Adelantar del change 03 lo mínimo de JWT para poder exponer endpoints.** **Consecuencia:** arrastra usuario, rol, permiso, hash de contraseña y emisión de tokens; convierte un change de medio día en el change 03 completo y rompe `04` §2 ("entre medio día y tres días").

**Decisión: A.** Es la única que no inventa un segundo camino hacia `organizacion_id`. El ratchet convierte la obligación de INV-21 en una verificación estructural en lugar de una promesa. No amerita ADR: no cambia ninguna regla de `docs/`, decide el orden en que se construye lo que `02` §8 ya manda.

### D2 — En qué módulo vive cada tabla (`02` §5.1 vs `03` §3)

`02` §5.1 asigna al módulo `configuracion` los "parámetros de organización", pero `03` §3 —el mapa explícito de tabla a módulo— pone `organizacion` y `configuracion_organizacion` en `identidad`, y deja en `configuracion` solo `alicuota_iva`, `medio_pago` y `motivo`. Alternativas:

- **A) Seguir `03` §3 al pie de la letra.** `identidad/` tiene `organizacion` y `configuracion_organizacion`; `configuracion/` tiene los tres catálogos. `identidad.service` expone la lectura de la configuración para los demás módulos. **Consecuencia:** el nombre del módulo `configuracion` queda algo más angosto que su descripción en `02` §5.1, pero el mapa de tablas —que es el documento que los changes 05..27 van a consultar para saber dónde poner las suyas— se cumple literalmente y sin excepciones que recordar.
- **B) Seguir `02` §5.1 y mover `configuracion_organizacion` a `configuracion`.** **Consecuencia:** `configuracion` pasa a depender de `identidad` (la FK a `organizacion`) y `03` §3 queda desactualizado en su primera fila, obligando a corregir el documento del que dependen todos los changes siguientes.

**Decisión: A**, porque `03` §3 es la fuente específica sobre ubicación de tablas y `02` §5.1 es una tabla de responsabilidades a grano grueso; además `02` §5.3 ya permite que todos los módulos dependan de `identidad` y de `configuracion`, así que ninguna ubicación crea un ciclo. **Esta discrepancia entre dos documentos vigentes debería quedar como ADR** (una línea aclarando que `03` §3 manda sobre la ubicación de tablas); queda señalada para revisión humana, no se registra desde este change.

### D3 — Las dos columnas cuya tabla destino todavía no existe

`configuracion_organizacion.lista_precio_default_id` apunta a `lista_precio` (change 13) y `cliente_consumidor_final_id` apunta a `cliente` (change 07). Alternativas:

- **A) Columnas nulables, sin restricción de clave foránea; la FK compuesta la agrega la migración del change que crea la tabla destino.** **Consecuencia:** entre el change 02 y el 07/13 esas dos columnas no tienen garantía de integridad en la base. El riesgo es acotado: nada las escribe todavía, y `01` §4 ya las marca como "A definir al configurar". La migración destino tendrá que agregar la FK y, si hubiera datos, validarlos.
- **B) Crear tablas vacías de `lista_precio` y `cliente` ahora para poder declarar la FK.** **Consecuencia:** invade el alcance de los changes 07 y 13, y una tabla sin sus columnas reales es peor que ninguna: obliga a una migración de reescritura después.

**Decisión: A.** Cada migración que crea una tabla destino agrega su FK compuesta; las tareas del change 02 dejan esa deuda anotada en el `tasks.md` de este change y en el comentario de la migración.

### D4 — Dónde vive la siembra de la organización inicial

`03` §4 dice que el catálogo de `permiso` (global, sin organización) se sincroniza por migración, pero la organización inicial y sus catálogos son datos de negocio con `organizacion_id`. Alternativas:

- **A) Un comando de siembra idempotente en el backend (`python -m app.seed`), fuera de las migraciones.** **Consecuencia:** las migraciones quedan puramente de esquema, así que `alembic upgrade head` y `downgrade` siguen subiendo y bajando limpio sobre una base con datos (`04` §2.1, punto 4). La siembra se puede ejecutar más de una vez sin duplicar (spec `parametros-de-organizacion`), y el operador puede cambiar valores después sin que una reejecución los pise.
- **B) Una migración de datos de Alembic.** **Consecuencia:** el `downgrade` tendría que borrar filas de negocio, lo que choca con TR-06 y con la definición de terminado; y ata la creación de una organización a una revisión de esquema, que es lo contrario de lo que hará el alta de organizaciones cuando exista el bus (change 04).

**Decisión: A.** La siembra usa el servicio del módulo, no SQL suelto, para que las validaciones de dominio se ejerciten en el mismo camino que usará el comando de alta cuando llegue el change 04.

### D5 — Pantalla de administración en este change

`04` §3 pide que cada change deje algo verificable, "preferentemente una pantalla usable; como mínimo, un endpoint con pruebas". Con D1 no hay endpoint. Alternativas:

- **A) Diferir la pantalla al change 03**, donde ya hay login, sesión y permisos donde colgarla. **Consecuencia:** este change entrega migración + repositorios + suite de aislamiento y nada visible en el navegador; el punto 5 de la definición de terminado (`04` §2.1, "se probó a mano el flujo principal en el navegador") no aplica y se declara no aplicable en el cierre del change.
- **B) Construir una pantalla sin autenticación y protegerla después.** **Consecuencia:** una pantalla de administración abierta, aunque sea en desarrollo, es exactamente el mecanismo temporal que D1 decidió no crear, con el agravante de que además expone escritura.

**Decisión: A.** Lo verificable de este change es la suite: el esquema comprobado contra `information_schema`, el aislamiento probado con dos organizaciones y el ratchet de INV-21.

## Risks / Trade-offs

- **La prueba de INV-21 hoy no ejercita ninguna ruta de negocio y puede dar falsa sensación de cobertura** → el nombre de la prueba y su mensaje de fallo dicen explícitamente cuántas rutas de negocio cubrió (hoy, cero) y el `proposal.md` declara INV-21 como cerrado *parcialmente*. La spec exige que la exención de rutas de sistema sea una lista enumerable, no un patrón de nombre, para que nadie pueda exentar una ruta de negocio por accidente.
- **Las dos columnas sin FK (D3) pueden quedar huérfanas si alguien las escribe antes de los changes 07 y 13** → nada las escribe en este change; el comentario de la migración y una tarea explícita en los changes 07 y 13 registran la deuda.
- **Sembrar con el servicio (D4) acopla el arranque al código de dominio** → es deliberado: es el mismo camino que usará el comando de alta del change 04, así que se prueba desde hoy.
- **El patrón de FK compuesta se copia 30 veces en los changes siguientes; si queda mal definido acá, la corrección es carísima** → por eso la verificación de esquema no comprueba las tablas de este change por nombre sino que recorre `information_schema` y exige el patrón a toda tabla de negocio, incluidas las que todavía no existen.

## Migration Plan

- Una sola revisión de Alembic sobre la base vacía de `01b`: `organizacion`, `configuracion_organizacion`, `alicuota_iva`, `medio_pago`, `motivo`.
- `downgrade` elimina las cinco tablas en orden inverso. Al no haber datos de negocio previos, la reversión es limpia (`04` §2.1, punto 4), y se verifica con `upgrade head` → `downgrade base` → `upgrade head` sobre una base sembrada.
- La siembra (D4) es un paso separado y posterior a `alembic upgrade head`, documentado en el README del backend.

## Open Questions

- Ninguna que bloquee la implementación. Pendiente de revisión humana, sin bloquear: registrar como ADR la precedencia de `03` §3 sobre `02` §5.1 para la ubicación de tablas (D2).
