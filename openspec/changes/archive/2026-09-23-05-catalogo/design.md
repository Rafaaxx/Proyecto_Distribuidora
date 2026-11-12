## Context

Primer maestro de negocio sobre el bus del change 04 (ver `proposal.md`). Estado relevante:

- El bus (`sync/service.py::procesar_comando`) reserva el `operation_id`, verifica el permiso, ejecuta el handler con una `SesionSinCommit`, audita **una** fila `origen = COMANDO` por comando ejecutado y confirma. Un error no transitorio revierte todo, incluida la reserva (`02` §6.3).
- La plantilla D7 del change 04 (`identidad/commands.py`) es la referencia: un tipo `ENTIDAD_ACCION`, esquema Pydantic v1, handler que llama al servicio, `registrar_handler` + `declarar_tipo`.
- Tres ratchets ya exigen, para toda ruta nueva: pasar por `procesar_comando` si escribe (`test_bus_cobertura_rutas_de_escritura.py`), declarar exactamente un permiso (`test_ratchet_permiso_por_ruta.py`) y tener prueba de aislamiento real (`test_inv21_ratchet_rutas.py`).
- `alicuota_iva` vive en `configuracion` (change 02) con `UNIQUE (organizacion_id, id)`; `catalogo` la consume por `configuracion/service.py`. `02` §5.1 lista "alícuotas" también en `catalogo`: se interpreta como la **asignación** de alícuota al producto, no la tabla.
- `proveedor` no existe (change 06); ninguna tabla de operaciones que use presentaciones existe todavía (06, 09, 11, 18a).
- `/admin` solo tiene `LoginScreen` y `DispositivosScreen`, sin estilo ni layout. No hay endpoint de "mis permisos" (ADR-017).

## Goals / Non-Goals

**Goals:**
- Esquema de `03` §5 fiel, con las garantías de base que `03` §15 le asigna (CAT-03, unicidades, FK compuestas).
- Reglas de CAT que la base no puede expresar (al menos una referencia, CAT-04) en el servicio, sin romper los límites de `02` §5.3.
- Dejar los puntos de extensión que los changes 06, 11, 13 y 18a necesitan, nominados como deuda.

**Non-Goals:**
- Resolver la firma de `HandlerFuncion` para el lote `OFFLINE` (ver D3).
- Diseño visual completo de `/admin` (ver D10).

## Decisions

### D1 — `producto.proveedor_id` antes de que exista `proveedor` (**BLOQUEANTE**)

CAT-01 y CAT-06 exigen proveedor en todo producto y `03` §5 lo marca "obligatorio en etapa 1", pero `proveedor` nace en el change 06, que depende de 04 y no de 05.

- **A) Columna `uuid` nulable y sin FK; el change 06 agrega la FK compuesta y el `NOT NULL`.** Mismo patrón que el change 02 (D3) y el 04 (D8). **Consecuencia:** hasta el 06, CAT-01 se cumple a medias; el 06 debe completar productos sin proveedor antes del `NOT NULL` (FK con `NOT VALID` + `VALIDATE`, luego `SET NOT NULL`). Riesgo acotado: los datos reales entran en el change 10, que depende del 06.
- **B) Crear en este change la tabla `proveedor` completa (`03` §6: nombre, cuit, contacto, teléfono, email, activo) con un comando mínimo de alta, sin pantalla.** **Consecuencia:** CAT-01 completo desde el día uno, pero invade el 06 y agrega un tipo de comando y una ruta más (con sus tres ratchets).
- **C) Reordenar: partir el 06 en `06a-proveedores-ficha` antes del 05.** **Consecuencia:** CAT-01 completo sin invadir; toca `04-roadmap-changes.md` (dependencias) y retrasa el catálogo.

**Recomendación: A.** Es el precedente del proyecto para exactamente este problema, no crea tablas fuera de su change y no reordena el roadmap. **Requiere confirmación humana** porque relaja temporalmente una regla de negocio; si se aprueba, se anota como deuda del change 06 en `04-roadmap-changes.md` (sin ADR: es una decisión de secuencia, como D3 del 02).

**Resuelto: opción A, aprobado por el usuario 2026-09-22.**

### D2 — Cómo se sabe que una presentación "fue usada" (CAT-04, INV-18) (**BLOQUEANTE**)

`03` §5: "CAT-04 se valida en el servicio de catálogo; la base no puede expresarlo". Pero las tablas que usan presentaciones (`costo_informado`, `compra_linea`, `venta_linea`, …) son de módulos que dependen de `catalogo`, y `02` §5.3 prohíbe el ciclo (`catalogo ──► sin dependencias de negocio`).

- **A) Puerto de verificadores de uso.** `catalogo/service.py` expone `registrar_verificador_uso(nombre, funcion)`, donde `funcion(organizacion_id, presentacion_id, sesion) -> bool`. Cada módulo que registra operaciones registra su verificador al arrancar (igual que los handlers del bus). `PRESENTACION_MODIFICAR` con unidades distintas consulta todos; si alguno responde `True`, rechaza con `UNIDADES_CONGELADAS`. En este change la lista está vacía en producción; las pruebas de INV-18 registran un verificador de prueba. **Consecuencia:** sin cambio de esquema, sin ciclo de importación, sin contención en ventas; cada change futuro debe acordarse de registrar el suyo (se mitiga con una tarea nominada en 06/11/18a y una prueba por módulo).
- **B) Columna `presentacion.usada_desde timestamptz` marcada por cada operación vía `catalogo/service.py`, más un trigger que impide cambiar `unidades_base` si no es nula.** **Consecuencia:** la base lo garantiza, pero agrega una columna que `03` no define (requiere ADR y actualizar `03`), y obliga a cada venta a escribir la fila de la presentación dentro de su transacción (contención y un nivel más en el orden de bloqueo de `02` §7.3), incluso para ventas offline sincronizadas.
- **C) El catálogo consulta por SQL las tablas de los otros módulos.** Viola `02` §5.2 (la única excepción es `reportes`). Descartada de entrada.

**Recomendación: A.** Respeta los límites de módulos y `03` §5 tal como está. La ventana de carrera (se modifican las unidades mientras una primera venta con esa presentación está en vuelo) está cubierta por diseño: `venta_linea` congela `unidades_presentacion` (INV-18 en `03` §15, PRC-23), así que la venta conserva su valor. Se nomina al change 18a que la venta lea la presentación con `FOR KEY SHARE` y al 05 que la modificación bloquee la fila del producto (D5). Queda abierta para el change 06 una pregunta de negocio: ¿un costo informado cuenta como "uso"? (CST-01 registra la presentación; `01` no lo dice).

**Resuelto: opción A, aprobado por el usuario 2026-09-22.**

### D3 — Firma de los handlers de catálogo

`registro.HandlerFuncion` es `Callable[[SobreComando, BaseModel], object]`, sin `Session` ni `Clock`. La plantilla D7 lo resolvió con `sesion`/`reloj` como parámetros de palabra clave obligatorios, `# type: ignore[arg-type]` al registrar y `admite_offline=False`, porque el endpoint REST llama al handler directamente dentro de `ejecutar_handler`.

- **A) Seguir la plantilla D7 tal cual.** **Consecuencia:** consistente con identidad; los nueve tipos son `admite_offline=False`, que es lo que `02` §6.5 exige para maestros. El hueco sigue abierto.
- **B) Corregir ahora `HandlerFuncion` para recibir un contexto (`sesion`, `reloj`) y adaptar `_procesar_item_de_lote` y los cinco handlers de identidad.** **Consecuencia:** cierra el hueco, pero reabre el mecanismo del change 04 ya archivado dentro de un change de catálogo y agranda su alcance.

**Recomendación: A**, y nominar la corrección como deuda del change 17 (`cobranzas`), el primero con un tipo que admite `OFFLINE` (`COBRANZA_REGISTRAR`, `02` §6.5): ahí el despacho por el lote deja de ser teórico.

**Resuelto: opción A, aprobado por el usuario 2026-09-22.**

### D4 — Granularidad de los comandos

Nueve tipos, todos `ONLINE`, permiso `GESTIONAR_CATALOGO`: `CATEGORIA_CREAR`, `CATEGORIA_MODIFICAR`, `MARCA_CREAR`, `MARCA_MODIFICAR`, `PRODUCTO_CREAR`, `PRODUCTO_MODIFICAR`, `PRESENTACION_AGREGAR`, `PRESENTACION_MODIFICAR`, `PRESENTACION_REFERENCIA_CAMBIAR`. Los `*_MODIFICAR` llevan el **estado completo deseado** (incluido `activo`), no un parche: la huella queda determinada por el resultado buscado y el reenvío es trivialmente idempotente. `PRODUCTO_CREAR` incluye las presentaciones iniciales para que CAT-03 ("exactamente una") se cumpla desde la primera confirmación, sin un estado intermedio sin referencia.

Alternativas descartadas: comandos separados de activar/desactivar (duplican tipos sin agregar regla; se pueden sumar como versión nueva si la auditoría lo pide) y un "upsert" genérico de producto con presentaciones (mezcla altas, cambios de unidades y cambio de referencia en un contenido difícil de validar y auditar).

Los identificadores de entidades nuevas se generan en el servidor (UUIDv7, `core/ids.py`) y se devuelven en el resultado del comando, como `USUARIO_CREAR`.

### D5 — Concurrencia y cambio de referencia

Todo comando que toque presentaciones de un producto (`PRESENTACION_*`, `PRODUCTO_MODIFICAR`) toma primero `SELECT … FOR UPDATE` sobre la fila del `producto`: serializa los cambios por producto y hace que la validación "exactamente una referencia" y el chequeo de uso de D2 se evalúen sin carreras. `PRESENTACION_REFERENCIA_CAMBIAR` desmarca la anterior y luego marca la nueva, en ese orden, dentro de la misma transacción (el índice parcial no es diferible). `producto` no es tabla de saldo y no entra en el orden de `02` §7.3; ninguna operación de este change bloquea filas de esos niveles.

Deuda nominada al change 13: cambiar la referencia de un producto con precios publicados cambia el significado de su `precio_referencia` (PRC-10, PRC-22), y `precio_item` no congela las unidades de referencia. El 13 debe decidir (con ADR) si bloquear el cambio o congelar las unidades en `precio_item`. En este change no hay precios y el cambio se permite.

### D6 — Errores de dominio y unicidades

Toda violación de regla lanza un `DomainError` con código estable (`NOMBRE_DUPLICADO`, `NOMBRE_INVALIDO`, `CODIGO_DUPLICADO`, `PRODUCTO_SIN_PRESENTACIONES`, `REFERENCIA_INVALIDA`, `UNIDADES_INVALIDAS`, `UNIDADES_CONGELADAS`, `CATEGORIA_INACTIVA`, `MARCA_INACTIVA`, `ALICUOTA_INACTIVA`, `CATEGORIA_CON_PRODUCTOS_ACTIVOS`): el bus revierte y el `operation_id` puede reintentarse corregido (`02` §6.3). Referencias inexistentes o de otra organización → `RecursoNoEncontradoError` (404). Esto difiere de identidad, que devuelve `RECHAZADO` persistido para "no encontrado"; aquí se sigue `02` §6.3 al pie de la letra.

Las unicidades se validan primero en el servicio (mensaje claro) y la base es la garantía final: el repositorio hace el `flush` dentro de un `SAVEPOINT` (`begin_nested`, que `SesionSinCommit` delega) y traduce `IntegrityError` por nombre de restricción (`ux_producto__codigo` → `CODIGO_DUPLICADO`, etc.) para que dos altas concurrentes terminen en un error de dominio y no en un 500.

### D7 — Auditoría

AUD-01 no enumera cambios de catálogo. Se registra solo la fila automática del bus (`accion = tipo`, `origen = COMANDO`). Los servicios de catálogo son nuevos y **no** auditan por su cuenta, por lo que no necesitan el parámetro `auditar` de ADR-022.

### D8 — Visualización CAT-08 como cálculo compartido

Función pura en `catalogo/domain/cantidades.py` y `frontend/src/domain/catalogo/cantidades.ts`, con casos en `shared/fixtures/calculo/cat-08-visualizacion.json` (formato `02` §10.4) y una propiedad Hypothesis de reconstrucción. CAT-08 no es cálculo de dinero, pero la usan el dispositivo offline (21, 18a) y reportes (26): un solo juego de casos evita la divergencia que ADR-016 describe. En TS se opera con `number` entero (no es un importe); se valida `Number.isSafeInteger`.

### D9 — Permiso de las lecturas

El ratchet exige exactamente un permiso por ruta. Las lecturas de catálogo exigen `GESTIONAR_CATALOGO`. Consecuencia: SUP, VEN y CON no leen el catálogo por `/admin` en este change; VEN lo recibirá por bootstrap (SYN-11, change 21) y los módulos que lo necesiten lo leerán por `catalogo/service.py`. Si un change posterior necesita una pantalla de catálogo de solo lectura para otros roles, eso requiere un permiso nuevo (decisión de negocio).

**Resuelto: sin permiso nuevo (D9 tal cual), aprobado por el usuario 2026-09-22.**

### D10 — Primera pantalla real de `/admin`

- Layout mínimo de `/admin` (encabezado con navegación a Catálogo y Dispositivos, `<Outlet />`) y ruta `/admin/catalogo/*` cargada en diferido dentro del área.
- Estilo con utilidades de Tailwind v4 y un conjunto chico de tokens en `@theme` (color primario, superficie, borde, peligro, radio), más cuatro componentes en `components/ui/` (botón, campo, tabla, diálogo). Se aplican las reglas de `tailwind-design-system` (tokens semánticos, sin valores mágicos) y de `vercel-react-best-practices` (sin cascadas de peticiones, carga diferida por área, estado derivado sin efectos).
- Datos con TanStack Query (claves por entidad, invalidación tras cada comando aceptado), formularios con React Hook Form + Zod (`useFieldArray` para presentaciones). La sesión tras recarga ya funciona por el `/auth/refresh` automático de `httpClient` ante un 401.
- El `Operation-Id` se genera al abrir el envío y se conserva en el estado de la mutación para reintentos (escenario "reintento tras error de red").

**Decisión de diseño visual abierta (no bloqueante):** si se quiere una identidad visual (paleta, tipografía) se define antes del grupo de UI; si no, se usan los tokens neutros anteriores y se ajustan después sin tocar lógica.

### D11 — Desactivar una categoría con productos activos (supuesto a confirmar)

`01` no lo dice. Se rechaza (`CATEGORIA_CON_PRODUCTOS_ACTIVOS`) porque CAT-01 exige categoría a todo producto y una categoría inactiva no se ofrece (CAT-05). Las marcas, opcionales, sí pueden desactivarse con productos. Si se prefiere permitirlo, solo cambia un escenario y una validación.

**Resuelto: se rechaza (comportamiento tal cual descrito), aprobado por el usuario 2026-09-22.** Promovido a ADR en la verificación del change (13.4): `docs/adr/ADR-024-categoria-con-productos-activos-no-se-desactiva.md`.

### D12 — Listado de alícuotas para el formulario de producto (agregado durante el grupo 10)

**Contexto.** Al implementar 10.5 apareció un hueco: el formulario de producto necesita elegir la alícuota de IVA (escenario "Alta de producto con presentaciones": "alícuota `21%`"), pero ninguna ruta la lista. `configuracion` (change 02) no tiene `api.py`; solo expone `service.listar_alicuotas_activas` y `service.obtener_alicuota_por_id`, de uso interno entre módulos. Hoy el formulario pide el `uuid` de la alícuota como texto libre, lo que no es usable. El usuario decidió resolverlo dentro de este change (2026-09-23).

**Decisión.**
- **Ruta:** `GET /api/v1/configuracion/alicuotas`, endpoint síncrono (`def`) en un `configuracion/api.py` nuevo (router `prefix="/configuracion"`, agregado en `api_v1/__init__.py`), con `configuracion/schemas.py` y `configuracion/queries.py` siguiendo el patrón de `catalogo` (9.2): `queries.py` lee por `configuracion/repository.py` del propio módulo. `organizacion_id` sale del token (`ContextoAutenticado`), nunca de la petición. Es de solo lectura: no pasa por el bus (el ratchet de cobertura del bus solo alcanza escrituras).
- **Forma de la respuesta:** `PaginaAlicuotas { items: AlicuotaResponse[], cursor_siguiente }`, con `AlicuotaResponse { id, nombre, valor, activo }` — las columnas reales de `alicuota_iva` (`03` §4; modelo del change 02: `nombre text`, `valor numeric(9,6)`, `activo boolean`). `valor` viaja como **string** (`"0.210000"`, `CLAUDE.md` §4: porcentajes como string). Paginación por cursor sobre `nombre` con límite máximo 100, como exige `02` §11 para todo listado (aunque la lista sea corta: no se abre una excepción a la convención sin ADR).
- **Devuelve todas (activas e inactivas) con `activo`; el cliente filtra.** Es el mismo contrato que `GET /catalogo/categorias` y `GET /catalogo/marcas`, que también devuelven `activo` y cuyo filtrado a activas hace el formulario (10.6, CAT-05). Así el formulario de edición puede mostrar la alícuota actual de un producto aunque se haya desactivado, y la futura pantalla de configuración (que sí necesita ver inactivas para reactivarlas) reutiliza la ruta. La garantía de negocio no depende del filtro del cliente: `PRODUCTO_CREAR`/`PRODUCTO_MODIFICAR` ya rechazan una alícuota inactiva o ajena en el servicio (7.3; escenario "Alícuota, categoría o marca inexistente, inactiva o ajena").
- **Permiso: `GESTIONAR_CATALOGO`.** El ratchet exige exactamente un permiso por ruta. `01` §19 no define un permiso de lectura de configuración: `ADMIN_CONFIGURACION` ("Configuración de la organización") solo lo tiene ADM, y `GESTIONAR_CATALOGO` lo tienen ADM y GES. Se usa `GESTIONAR_CATALOGO`, por el mismo razonamiento de D9 (la lectura se protege con el permiso de quien la consume): con `ADMIN_CONFIGURACION` un GES —que el escenario "Usuario con permiso" habilita a dar de alta productos— no podría elegir la alícuota. **Resuelto: opción A, aprobado por el usuario 2026-09-23.**
- **Frontend:** `features/configuracion/` (`api.ts` tipado contra `schema.gen.ts`, `claves.ts`, `useAlicuotas.ts` con TanStack Query) y en `ProductoFormScreen.tsx` un `<select>` que ofrece solo las alícuotas activas (etiqueta `nombre`), en alta y en edición, reemplazando el campo de texto `uuid`. El esquema Zod no cambia (sigue validando `uuid`).

**Alternativas descartadas.**
- *Filtrar a activas en el servidor:* contrato más chico, pero distinto del de categorías y marcas, deja sin representación la alícuota inactiva de un producto existente en edición y obliga a una segunda ruta el día que exista la pantalla de configuración.
- *Exponer la ruta dentro de `catalogo` (`GET /catalogo/alicuotas`) vía `configuracion/service.py`:* resolvería el permiso por D9 sin discusión, pero pone el listado de una tabla de `configuracion` en la API de otro módulo; `02` §5.1 asigna la tabla a `configuracion` y la "alícuota" de `catalogo` es solo su asignación al producto (ver Context).
- *Lista sin paginar:* más simple, pero contradice `02` §11 sin un ADR que lo justifique.
- *Mantener el campo `uuid` y postergarlo:* descartado por el usuario.

## Risks / Trade-offs

- [Un change futuro olvida registrar su verificador de uso y INV-18 queda sin efecto para esa operación] → Tareas nominadas en `04-roadmap-changes.md` para 06, 11 y 18a, y una prueba en cada uno que cita INV-18.
- [El change queda grande: 4 tablas, 9 comandos, consultas paginadas y la primera UI] → Grupos separados backend/frontend; si el backend termina sin la UI dentro de los 3 días de `04` §2, partir en `05a`/`05b` en ese punto, no al final.
- [Relajar CAT-01 hasta el 06 (D1-A) deja productos sin proveedor] → Nadie carga datos reales antes del change 10; la migración del 06 valida antes de `NOT NULL`.
- [La traducción de `IntegrityError` por nombre de restricción es frágil ante renombres] → Los nombres siguen `03` §2.1 y una prueba de integración por restricción la ejercita.
- [Cambiar la referencia con precios existentes] → Nominado al 13 (D5).

## Migration Plan

Una revisión de Alembic: `categoria`, `marca`, `producto`, `presentacion` con `organizacion_id`, `UNIQUE (organizacion_id, id)`, FK compuestas (`producto → categoria, marca, alicuota_iva`; `presentacion → producto`; `actualizado_por_id → usuario`), `ux_categoria__nombre`, `ux_marca__nombre`, `ux_producto__codigo`, `ux_presentacion__referencia` (parcial), `ck_presentacion__referencia_venta`, `ck_presentacion__unidades_base`, índices `ix_producto__categoria`, `ix_producto__marca`, `ix_presentacion__producto` (consultas y chequeo de D11 cubiertos, sin índices redundantes). `presentacion` agrega `actualizado_en`/`actualizado_por_id` y `categoria`/`marca` agregan `actualizado_por_id`, porque `03` §2.3 lo exige a todo maestro aunque `03` §5 no lo repita. `GRANT SELECT, INSERT, UPDATE` a `app_runtime` (sin `DELETE`, CAT-05). Tablas nuevas y vacías: no aplican índices concurrentes. Se verifica `upgrade head → downgrade -1 → upgrade head` con datos.

## Open Questions

- ¿Los nombres de categoría/marca y el código de producto se comparan sin distinguir mayúsculas? Se asume comparación exacta tras recortar espacios, como `03` §5 (`UNIQUE (organizacion_id, nombre)`).
- ¿Un costo informado cuenta como "uso" de una presentación para CAT-04? Lo decide el change 06 al registrar (o no) su verificador (D2).
- **(D12, resuelto)** ¿Qué permiso exige `GET /api/v1/configuracion/alicuotas`? `01` §19 no lo resuelve. Opciones: (A) `GESTIONAR_CATALOGO` — ADM y GES pueden elegir alícuota al dar de alta productos; (B) `ADMIN_CONFIGURACION` — solo ADM; un GES no podría completar el formulario de producto; (C) un permiso nuevo de lectura de configuración — decisión de negocio que toca `01` §19 y requiere ADR. **Resuelto: opción A, `GESTIONAR_CATALOGO`, aprobado por el usuario 2026-09-23.**
