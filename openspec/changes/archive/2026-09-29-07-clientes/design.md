# Diseño técnico — 07-clientes

## Context

`docs/` resuelve el modelo de la tabla `cliente` (`03` §10), la ficha (CLI-01), la máquina de estados (`01` §18), los permisos (`01` §19) y la separación entre guardar el crédito y evaluarlo (CRE-01, CRE-03, CRE-06 contra el change 18b). No resuelve cinco puntos concretos: qué campos identifican a un cliente y si se repiten, cómo se guarda la lista asignada antes de que exista `lista_precio`, qué permiso gobierna el consumidor final, qué se hace con `condicion_iva`, y qué precisión tiene el valor de la tolerancia cuando el tipo es `PORCENTAJE`. Este documento decide esos cinco y cierra el resto con el precedente de los changes 05 y 06.

Restricciones que condicionan el diseño:

- `configuracion_organizacion` ya existe con `permite_consumidor_final` y `cliente_consumidor_final_id` (`03` §4), pero **no hay API ni `service.py` que la modifique**: hoy solo existe `crear_organizacion_con_configuracion` y `obtener_configuracion` en `identidad/service.py`, y su modelo vive en `identidad/models.py`.
- `GESTIONAR_CLIENTES` y `GESTIONAR_CREDITO` ya existen en el catálogo de permisos (`01` §19, `identidad/domain/permisos.py`), con `ADMIN_CONFIGURACION` como permiso de la configuración de la organización. Con las plantillas de rol vigentes, `ROL-GES` y `ROL-SUP` tienen `GESTIONAR_CLIENTES`, y solo `ROL-ADM` tiene `ADMIN_CONFIGURACION`.
- La tabla `lista_precio` no existe hasta el change 13, y el usuario de aplicación no puede ejecutar `ALTER TABLE` en caliente.
- `config.py` ya advierte que `configuracion_organizacion.app_version_minima` es una columna huérfana, señal de que tocar esa tabla tiene precedentes desfavorables.
- Los ratchets de permiso por ruta, de cobertura del bus, de aislamiento y de repositorios con `organizacion_id` son enumerados: cada ruta nueva hay que registrarlos a mano.

Ver `proposal.md` para la motivación y `specs/` para el comportamiento.

## Goals / Non-Goals

**Goals:**

- Un maestro de clientes que el change 10 pueda reutilizar fila por fila, sin reescribir reglas.
- Que guardar el crédito y evaluarlo queden en manos de changes distintos, sin que el 07 tenga que hacer trabajo de otro.
- Dejar la tabla lista para las FKs de los changes que siguen, sin que ese trabajo exija un `ALTER TABLE` con el sistema en servicio.
- Mantener la separación de permisos que el change 06b dejó como patrón: un permiso por ruta, decidido por la sesión.

**Non-Goals:**

- No se implementa ninguna evaluación de crédito, aunque el modelo ya tenga los tres campos.
- No se implementa nada del consumidor final más allá de crearlo y apuntarlo en la configuración.
- No se resuelve `PRC-20` (precio por lista asignada): por eso `lista_precio_id` no se valida.
- No se implementa importación masiva ni bootstrap de dispositivo; este change solo deja el `service.py` que ambos usarán.
- No se agregan endpoints que hoy no tiene consumidor: en particular, ni `/clientes/opciones` ni escritura de parámetros de organización en general.

## Decisions

### D1 — Identidad del cliente: código y documento únicos, nombre libre

La ficha tiene tres candidatos a identidad natural (`codigo`, `documento_tipo`/`documento_numero`, `nombre`) y ninguno es obligatorio. La regla nueva es la que el change 06 aplicó al proveedor (D7, aprobada 2026-09-23): **unicidad en la base, no solo en el handler**, con índice parcial para lo opcional, y un error de dominio estable.

- **A (recomendada).** `codigo` único por organización con índice parcial `WHERE codigo IS NOT NULL`; `(documento_tipo, documento_numero)` único por organización con índice parcial `WHERE documento_numero IS NOT NULL`; `nombre` sin unicidad. El número se normaliza a dígitos (se descartan guiones y espacios) antes de comparar, igual que el CUIT del proveedor, y se guarda normalizado.
- **B.** Los tres únicos, como el proveedor.
- **C.** Ninguno único, resuelto solo en el handler.

**Consecuencias.** A: el nombre se puede repetir, que es lo que pasa en la calle (dos kioscos en la misma cuadra con el mismo nombre); el documento y el código sujetan la base de datos y no dependen de la carrera entre dos requests, con la prueba de concurrencia con commits reales que ya usa el 06. B: obliga a inventar un sufijo en el nombre ("Kiosco La Esquina (2)") y no aporta nada, porque el documento ya identifica; además difiere de `proveedor` sin motivo de dominio. C: es el precedente descartado por el 06 (D7) porque dos requests concurrentes pueden pasar la validación y crear el duplicado.

**Decidido (2026-09-28).** El usuario pidió validar las longitudes por tipo de documento: se agrega la regla CLI-05 a `docs/01-dominio.md` (catálogo CUIT o DNI; CUIT 11 dígitos, DNI 7 a 8, solo numéricos) y este change la implementa junto con el formato de dígitos y la unicidad. La spec `fichas-de-cliente` incorpora el escenario de longitud inválida (`DOCUMENTO_INVALIDO`).

### D2 — `lista_precio_id` existe como columna sin FK hasta el change 13

`03` §10 incluye `lista_precio_id` en `cliente` y PRC-20 exige que la venta resuelva la lista asignada, pero la tabla `lista_precio` la crea el change 13.

- **A (recomendada).** Crear la columna `uuid NULL` sin FK ni validación de existencia; el 13 agrega la FK compuesta `(organizacion_id, lista_precio_id)`. Precedente exacto: el change 06 creó `producto.proveedor_id` sin FK y el ADR-025 la agrega cuando existe el destino.
- **B.** No crear la columna hasta el 13.
- **C.** Crear la tabla `lista_precio` adelantada.

**Consecuencias.** A: la migración de este change no depende del 13 y la columna queda en el modelo que `docs/` ya declara; se acepta un `uuid` que hoy apunta a nada, y el formulario no la ofrece, así que solo la escribe la importación del change 10. B: el modelo en código queda incompleto respecto de `03` §10, y el 13 tiene que agregar columna y FK, con el mismo costo que A más un paso. C: mete en este change una tabla de otro dominio con reglas de precio que no están resueltas (PRC-01 a PRC-22); es exactamente lo que `docs/04` prohíbe.

**Aprobada (2026-09-28).** El usuario confirmó la columna nullable sin FK como deuda consciente; el ADR del 13 debe anotarla.

### D3 — Dos comandos y dos permisos, y un solo tipo por comando

`01` §19 separa `GESTIONAR_CLIENTES` ("Alta y edición de clientes") de `GESTIONAR_CREDITO` ("Límite, política y tolerancia de clientes"), y el ratchet de rutas exige **un** permiso por ruta. La ficha completa de CLI-01, sin embargo, incluye el límite, la política y la tolerancia.

- **A (recomendada).** `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` con `GESTIONAR_CLIENTES` y sin campos de crédito; `CLIENTE_CREDITO_MODIFICAR` con `GESTIONAR_CREDITO` y sin campos de ficha. Un contenido con campos del otro comando se rechaza como malformado. Las lecturas devuelven los tres campos a quien puede ver el cliente, y la pantalla de crédito es una ruta aparte.
- **B.** `CLIENTE_MODIFICAR` con la ficha completa y un solo permiso, corrigiendo el catálogo de permisos para que `GESTIONAR_CLIENTES` incluya el crédito.
- **C.** Una acción de pantalla que aplica ambos comandos en el navegador.

**Consecuencias.** A: un Supervisor comercial (tiene `GESTIONAR_CLIENTES`, no `GESTIONAR_CREDITO`) puede dar de alta clientes y ver su crédito pero no tocarlo, que es la razón de existir de los dos permisos; el costo es que guardar la ficha y el crédito son dos envíos, y que la UI tiene dos formularios. B: contradice el texto del catálogo de permisos (`01` §19 es fuente de verdad y ya está implementado), y con las plantillas de rol el efecto real sería que un Supervisor comercial pudiera cambiar el límite de crédito. C: dos transacciones, dos `operation_id` y un estado intermedio en que la ficha quedó guardada y el crédito no; además, un rechazo del segundo comando deja el primero aplicado sin que el usuario pueda revertirlo.

**Aprobada (2026-09-28).** El usuario confirmó que las lecturas no exijan `GESTIONAR_CREDITO` para mostrar el límite: un supervisor que no edita crédito igual ve los tres campos en la ficha.

### D4 — El consumidor final lo habilita un comando de la organización

CLI-03 dice "si la organización lo habilita, existe un cliente genérico consumidor final con límite de crédito cero", y `03` §4 ya tiene las dos columnas. No dice quién lo habilita ni cómo nace el cliente.

- **A (recomendada).** Un comando `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (`ONLINE`, `ADMIN_CONFIGURACION`) que crea el cliente con límite cero, le pone la marca, y fija `permite_consumidor_final` y `cliente_consumidor_final_id` en la misma transacción, a través de un setter nuevo en `identidad/service.py` (el módulo `clientes` alcanza a `identidad` solo por su `service.py`, con el mismo contrato de import-linter que ya existe para `configuracion`). La marca no se puede poner desde `CLIENTE_CREAR`, y un segundo intento se rechaza con `CONSUMIDOR_FINAL_YA_HABILITADO`.
- **B.** El cliente lo crea a mano un usuario con `GESTIONAR_CLIENTES` y después un comando aparte activa el flag.
- **C.** El consumidor final lo crea el seed de la organización.

**Consecuencias.** A: no existe el estado en que la organización dice que tiene consumidor final sin cliente, ni el contrario, porque es una transacción; y el permiso es coherente con el catálogo, ya que lo que se escribe es la configuración de la organización. La consecuencia asumida: con las plantillas de rol actuales **solo el Administrador puede habilitarlo**, porque es el único con `ADMIN_CONFIGURACION`. B: deja un cliente huérfano y un flag que se puede activar apuntando a cualquier cliente, incluido uno con crédito, que contradice CLI-03. C: la creación automática contradice "si la organización lo habilita", y el seed no es lugar para una decisión de negocio.

**Decidido (2026-09-28).** El usuario aprobó la opción A; sus dos consecuencias se registran en ADR-029: lo habilita solo el rol `ADM` (permiso `ADMIN_CONFIGURACION`), y el cliente consumidor final no puede pasar a `INACTIVO` — `CLIENTE_MODIFICAR` con `estado = INACTIVO` sobre él se rechaza; para dejar de vender "de paso" se deshabilita la función con el mismo comando. El nombre del cliente genérico lo recibe el comando como dato (default "Consumidor final"). `docs/01` §18 y CLI-03 se actualizaron.

### D5 — `condicion_iva` no se crea en este change

`03` §10 lista `condicion_iva` en `cliente`, pero `01` §16 y FAC-04 no definen su dominio y el cambio que la va a consumir es el de facturación.

- **A (recomendada).** No crear la columna; el change de facturación la agrega junto con su catálogo.
- **B.** Crearla como `text NULL` sin FK ni validación, como se hizo con `lista_precio_id`.
- **C.** Crear ahora el catálogo de condiciones de IVA.

**Consecuencias.** A: el modelo en código queda sin una columna que `docs/` declara, y la diferencia se anota en el change de facturación para que la agregue. B: guarda un dato que nadie puede escribir ni leer, que es peor que no tenerlo. C: es dominio de facturación, con sus reglas de redondeo y de alícuotas.

**Aprobada (2026-09-28).** El usuario confirmó no crear `condicion_iva`; el change de facturación la agrega.

### D6 — `tolerancia_offline_valor` es `numeric(14,2)`, como en la organización

La organización ya tiene `tolerancia_offline_tipo text` (`IMPORTE`, `PORCENTAJE`) y `tolerancia_offline_valor numeric(14,2)` (`03` §4). El cliente repite los dos campos.

- **A (recomendada).** Mismos tipos exactos que la organización. Cuando el tipo es `IMPORTE` el valor es un importe en pesos; cuando es `PORCENTAJE` es un porcentaje que el 18b interpreta al calcular el exceso. `numeric(14,2)` alcanza para ambos, y la validación de este change es que el tipo esté en el catálogo y que valor y tipo vayan juntos.
- **B.** `numeric(9,6)` para el valor, como los porcentajes del catálogo, por si un porcentaje necesita más decimales.
- **C.** Dos columnas: `tolerancia_offline_importe` y `tolerancia_offline_porcentaje`.

**Consecuencias.** A: la columna del cliente es idéntica a la de la organización, así que la herencia de CRE-06 es una lectura y no una conversión. Con `numeric(14,2)`, un porcentaje admite dos decimales (por ejemplo `2.50` = 2,50 %), lo cual es suficiente para una tolerancia y descarta el redondeo a tres decimales. B: rompe la simetría con la organización y obliga a convertir en cada herencia, con más superficie de error. C: contradice `03` §10, que define un par tipo/valor.

**Aprobada (2026-09-28).** El usuario confirmó `numeric(14,2)` y que la interpretación del porcentaje (sobre el límite, el disponible o el saldo) queda para el 18b.

### D7 — El cliente nace `ACTIVO` y `INACTIVO` se revierte solo sin operaciones

`03` §10 define `estado` con `text NOT NULL` y `01` §18 da las transiciones, pero no dice con qué estado nace un cliente ni si `INACTIVO` es reversible.

- **A (recomendada).** `CLIENTE_CREAR` nace siempre `ACTIVO` y el estado se cambia con `CLIENTE_MODIFICAR`, igual que el proveedor del 06 nace activo y se desactiva con el comando de modificación. `INACTIVO` no tiene salida: volver a `ACTIVO` o `SUSPENDIDO` se rechaza con `TRANSICION_ESTADO_INVALIDA`. Un cliente sin operaciones puede inactivationarse en cualquier momento; la comprobación de que no tenga operaciones se activa en el change que introduce la primera.
- **B.** `CLIENTE_CREAR` acepta el estado inicial, y `INACTIVO` puede volver a `ACTIVO`.
- **C.** `INACTIVO` es reversible solo con un comando especial de reactivación.

**Consecuencias.** A: no hay cliente creado ya inactivo, que sería una forma de importar histórico sin operaciones; y la irreversibilidad de `INACTIVO` evita que un cliente con historial reaparezca en ventas sin que nadie lo decida. Cuesta que reactivar exija otro camino, que de todos modos no existe hoy. B: permite clientes inactivos y después activos sin más trámite, y contradice el espíritu de CLI-04. C: agrega un comando que hoy ningún caso de negocio pide.

**Decidido (2026-09-28).** El usuario aprobó la opción C: `INACTIVO → ACTIVO` solo si el cliente no tiene operaciones (CLI-06, ADR-030; `docs/01` §18 actualizado); con operaciones es terminal y la restricción se activa cuando exista la primera (changes 08/10/17/18a). Quien edita la ficha (`GESTIONAR_CLIENTES`) puede inactivar, sin permiso nuevo.

**Confirmación tipeada en la pantalla (solo frontend).** Para evitar clics rápidos, la pantalla NO envía `CLIENTE_MODIFICAR` con `estado = INACTIVO` hasta que el usuario tipea el **nombre completo del cliente** en un diálogo (patrón GitHub); el texto confirmado NO viaja en el comando y el backend no lo conoce: la protección real queda en la máquina de estados, el verificador de CLI-06 y la auditoría (AUD-01). Se eligió el nombre —en vez de una palabra fija como "BORRAR"— porque el sistema no borra clientes (CLI-04) y porque tipear el nombre protege también contra inactivar al cliente equivocado; el diálogo muestra código y documento para desambiguar nombres repetidos (D1). Alternativa aceptada con un cambio de una línea: una palabra fija (`INACTIVAR`).

### D8 — El crédito se guarda sin resolver y sin exponer cálculos

CRE-01 a CRE-06 describen la evaluación en la venta y la sincronización, y CRE-10 congela los valores evaluados en la venta. `03` §10 no tiene columnas de disponible ni de exceso.

- **A (recomendada).** `clientes` no calcula disponible, exceso ni política aplicada, y la respuesta de la API no incluye esos campos. La evaluación lee los tres campos del cliente, resuelve la herencia de la organización en ese momento (CRE-03, CRE-06) y ocurre en el módulo que confirma la venta, con su propia prueba. `clientes` expone el `service.py` mínimo que el 18b necesitará, sin calculadora.
- **B.** Calcular el disponible en el detalle del cliente para que la pantalla lo muestre.
- **C.** Dejar la evaluación en `clientes` para reutilizarla.

**Consecuencias.** A: el 07 tiene menos código y ninguna regla de crédito que probar; el 18b tiene que escribir esa evaluación una vez, y es el change que la necesita. El detalle de la ficha muestra el límite sin el disponible, que es aceptable en un maestro. B: el disponible necesita el saldo, que llega con el 08, y obliga a calcular en lectura una cuenta corriente que este change no tiene. C: mezcla dos responsabilidades y hace que el módulo de clientes dependa de reglas de venta.

### D9 — La API de este change es la mínima, y el `service.py` se escribe para el 10

`docs/04` pone la importación (10) y el bootstrap (21) después del 07.

- **A (recomendada).** Rutas: `GET /api/v1/clientes`, `GET /api/v1/clientes/{cliente_id}` y `GET /api/v1/clientes/consumidor-final`; escrituras: los cuatro comandos. El `service.py` expone `crear_cliente`, `modificar_cliente`, `modificar_credito_cliente` y `obtener_cliente_por_id`, cada uno con `organizacion_id` primero y sin `commit`, para que el 10 los reuse fila por fila. No se agrega `/clientes/opciones` hasta que el 18a lo consuma al elegir cliente en una venta.
- **B.** Agregar `/clientes/opciones` ahora, por simetría con `/proveedores/opciones`.
- **C.** Agregar además escritura de los parámetros de organización en general.

**Consecuencias.** A: menos superficie que mantener; `/clientes/opciones` se agrega con su consumidor, y el 06 lo hizo igual para el 09 que lo necesitaba. C: es el módulo de configuración de la organización, con sus permisos y sus reglas; este change solo necesita la pareja de columnas del consumidor final.

**Enmienda (2026-09-29) — las escrituras necesitan una ruta dedicada por comando, no el despacho genérico.** El texto original de A decía "escrituras: los cuatro comandos" asumiendo que `POST /api/v1/sync/comandos` podía despachar cualquier comando `ONLINE`. Al implementar el grupo 4 se confirmó que `sync/service.py::_procesar_item_de_lote` invoca `handler_registrado.funcion(sobre, contenido_validado)` con solo dos argumentos posicionales, mientras que los cuatro handlers de `clientes/commands.py` — como todo handler del backend — declaran `sesion`/`reloj` como parámetros de palabra clave obligatorios; enviar un comando de `clientes` por el despacho genérico produce un `TypeError` no manejado (500). Esta es la misma deuda ya nombrada en `catalogo/commands.py` y asignada al change 17: hoy **ningún módulo del backend despacha sus comandos por `/sync/comandos`**, cada tipo `admite_offline=False` tiene su propia ruta de escritura en `api.py` que llama a `sync_service.procesar_comando` directamente (ver `proveedores/api.py` y `catalogo/api.py`).

El usuario aprobó (2026-09-29) seguir ese precedente exacto en lugar de esperar al change 17: se agregan cuatro rutas de escritura dedicadas a `clientes/api.py`, una por comando `ONLINE`, mirando `proveedores/api.py` línea por línea (sobre/envelope, `operation_id`, permiso por ruta, códigos de estado y mapeo de errores — 403 `PERMISO_REQUERIDO`, 404 para recurso ajeno, `COMANDO_INCONSISTENTE` en doble envío idempotente):

- `POST /api/v1/clientes` → `CLIENTE_CREAR`
- `PUT /api/v1/clientes/{cliente_id}` → `CLIENTE_MODIFICAR`
- `PUT /api/v1/clientes/{cliente_id}/credito` → `CLIENTE_CREDITO_MODIFICAR`
- `POST /api/v1/clientes/consumidor-final` → `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`

No hace falta un ADR nuevo: es el mismo patrón ya adoptado (y documentado en ADR) por catálogo y proveedores, aplicado sin variación. Las cuatro rutas se dan de alta en los mismos ratchets que el resto de las rutas del módulo (D9 original, tarea 4.2): `test_ratchet_permiso_por_ruta.py`, `test_inv21_ratchet_rutas.py` (enumeración manual de `COBERTURA_DE_AISLAMIENTO`) y los ratchets de permiso/bus basados en introspección, que las detectan solas. Cualquier docstring de `clientes/schemas.py` que describa el envío por `/sync/comandos` se corrige para reflejar las rutas dedicadas.

## Risks / Trade-offs

- **`lista_precio_id` sin FK** → queda un `uuid` que nada valida. Mitigación: el 13 agrega la FK compuesta y su prueba de integridad; hasta entonces la columna no se ofrece en ningún formulario (spec `clientes/administracion-de-clientes`).
- **Un `uuid` sin destino también es `cliente_consumidor_final_id`**, porque no hay FK a `cliente` todavía. Mitigación: la FK compuesta se agrega en el change que defina el ciclo de vida del consumidor final, junto con D4.
- **Solo el Administrador puede habilitar el consumidor final** (D4, ADR-029) → si Administración necesita hacerlo, no puede hasta que un rol tenga `ADMIN_CONFIGURACION`. Mitigación: es un cambio de plantilla de rol, no de código; decidido por el usuario el 2026-09-28.
- **El modelo en código difiere de `03` §10** en `condicion_iva` (D5) → alguien puede leer `03` y esperar la columna. Mitigación: queda anotado en el design y en el change de facturación; no se agrega una columna muerta.
- **`INACTIVO` se revierte solo sin operaciones (D7)** → la restricción queda en CLI-06/ADR-030 y se activa con la primera operación (changes 08/10/17/18a). Mitigación: verificadores de uso (ADR-023); la spec documenta el caso y su prueba llega con el change que registra la primera operación.
- **Tres comandos nuevos amplían el registro** de tipos de comando, el ratchet de rutas y los contratos de import-linter. Mitigación: es trabajo mecánico y enumerable del grupo de tareas.
- **La separación de comandos (D3) hace que la UI tenga dos formularios** → un usuario con ambos permisos puede creer que guardó la ficha cuando el crédito quedó sin guardar. Mitigación: la pantalla de crédito tiene su propio estado guardado y la ficha muestra siempre el valor vigente.

## Migration Plan

Una sola revisión de Alembic, de solo agregado, para la tabla `cliente`: `id` UUIDv7, `organizacion_id` con `NOT NULL`, `UNIQUE (organizacion_id, id)`, FK compuesta a `organizacion`, los campos de `03` §10 salvo `condicion_iva` (D5), `created_at` y `updated_at`, más `ux_cliente_codigo` y `ux_cliente_documento` parciales (D1) y los índices de listado por organización, estado y texto. No hay migración de datos, no se toca `configuracion_organizacion` y no se toca ningún libro.

Despliegue: aplicar migraciones antes de la nueva versión del frontend; como la tabla está vacía y nadie la consulta todavía, el orden inverso también es seguro. Rollback: revertir la revisión elimina la tabla y las filas que se hayan creado a mano, que es aceptable mientras el cambio no esté en producción con datos reales. Cuando el change se cierre y la decisión de D3, D4 y D6 quede aprobada, se registran los ADR correspondientes en `docs/adr/`, porque `01` §19 y `docs/02` §9 apuntan a ellos.

## Open Questions

- Si el change 10 necesita dar de alta clientes sin `GESTIONAR_CLIENTES` —el importador usa `IMPORTAR_DATOS`—, el `service.py` ya lo permite porque el permiso se comprueba en el bus, no en el servicio. No cambia este change.
- Si el 18a va a necesitar un listado reducido de clientes en `/ruta` con paginación por cursor y búsqueda por nombre, la API actual lo cubre con filtros; la ruta de venta la arma el 18a.
- El nombre por defecto del cliente consumidor final: la proposal propone "Consumidor final" y el comando lo recibe como dato, así que cada organización puede elegirlo. Si debe ser fijo, es una línea.
