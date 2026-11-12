# Contrato de API: change 06 (tarea 10.1)

> **Estado: BORRADOR para revisión humana.** Zona **[ALTA: contrato de API]**. No se escribe código de los grupos 10 y 11 hasta que este contrato se confirme.
> Fuentes: `design.md` (D3, D5 a D9, D12 a D14, D16), specs delta de `proveedores/*` y `catalogo/*`, ADR-025, ADR-026, `02` §6.2, §10.2 y §11, `01` §19, y el código existente de `catalogo/api.py`, `catalogo/schemas.py`, `configuracion/schemas.py`, `proveedores/{commands,service,repository}.py` y `proveedores/domain/errores.py`.

## 0. Convenciones comunes (ya vigentes)

| Tema | Regla | Fuente |
| --- | --- | --- |
| Base | Todas las rutas van bajo `/api/v1`. Catálogo cuelga de `/catalogo`. | `02` §11; `app/main.py`; `catalogo/api.py` |
| Idempotencia | Toda escritura exige el encabezado `Operation-Id` (UUIDv7) mediante `requiere_comando_online(PERMISO)`. Si falta, responde 400 `OPERATION_ID_REQUERIDO`; si está mal formado, 400 `OPERATION_ID_INVALIDO`. Un reenvío con el mismo id y el mismo contenido devuelve el resultado original. Con el mismo id y otro contenido, responde 409 `COMANDO_INCONSISTENTE`. | `02` §6.2; SYN-02; `core/autenticacion.py` |
| Permiso | Exactamente un permiso por ruta, lo verifica el ratchet. Sin el permiso, 403 `PERMISO_REQUERIDO`, sin efectos y sin reserva del `operation_id`. | `design.md` D8; `01` §19 |
| Organización | Sale del JWT y nunca del cuerpo. Un recurso de otra organización responde 404 `RECURSO_NO_ENCONTRADO`. | `CLAUDE.md` §4; INV-21; SEG-07 |
| Errores | Problem Details con `codigo` estable (`DomainError` → `app/main.py`). Un campo obligatorio ausente o de tipo erróneo cae en el 422 de validación de FastAPI, igual que en el 05. | `02` §11 |
| Decimales | En JSON viajan como string. En la salida se serializan con `field_serializer` → `str(Decimal)`, que conserva la escala de la columna (`"0.210000"`, no `"0.21"`), igual que `AlicuotaResponse`. | `02` §10.2; `configuracion/schemas.py` |
| Paginación | Parámetros `cursor` (opaco, base64) y `limite` (por defecto 50, se acota a `[1, 100]`). La respuesta es `{ items, cursor_siguiente }` y `cursor_siguiente` vale `null` en la última página. | `02` §11; `repository.LIMITE_PAGINA_*` |
| Fechas | `vigencia_desde` y `fecha` son `date` ISO (`YYYY-MM-DD`). Los momentos son `timestamptz` ISO 8601 con zona. | `02` §11 |
| Versión del sobre | Los tres comandos nuevos usan `version=1`. `PRODUCTO_CREAR` y `PRODUCTO_MODIFICAR` pasan a `version=2`. | D6; `commands.py` |

## 1. Rutas

### 1.1 Nuevas (`proveedores/api.py`)

| # | Método | Ruta (`/api/v1` + …) | Permiso | Comando / consulta | Éxito | Errores posibles (HTTP `codigo`) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/proveedores` | `GESTIONAR_PROVEEDORES` | `PROVEEDOR_CREAR` v1 | 201 | 400 `OPERATION_ID_*`; 403 `PERMISO_REQUERIDO`; 422 `NOMBRE_INVALIDO`, `CUIT_INVALIDO`; 409 `NOMBRE_DUPLICADO`, `CUIT_DUPLICADO`, `COMANDO_INCONSISTENTE` |
| 2 | PUT | `/proveedores/{proveedor_id}` | `GESTIONAR_PROVEEDORES` | `PROVEEDOR_MODIFICAR` v1 | 200 | Los mismos que la ruta 1, más 404 `RECURSO_NO_ENCONTRADO` y 409 `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` (D5, ADR-026) |
| 3 | GET | `/proveedores` | `GESTIONAR_PROVEEDORES` | `service.listar_proveedores` | 200 | 403 |
| 4 | GET | `/proveedores/opciones` | `GESTIONAR_CATALOGO` (D8) | `service.listar_opciones_de_proveedores` | 200 | 403 |
| 5 | GET | `/proveedores/{proveedor_id}` | `GESTIONAR_PROVEEDORES` | `service.obtener_proveedor` | 200 | 403; 404 |
| 6 | POST | `/costos` | `EDITAR_COSTOS` | `COSTO_INFORMAR` v1 | 201 | 400 `OPERATION_ID_*`; 403; 404 (proveedor, producto o presentación inexistente o ajeno); 422 `PROVEEDOR_INACTIVO`, `PROVEEDOR_NO_CORRESPONDE` (D3), `PRODUCTO_INACTIVO`, `PRESENTACION_INVALIDA`, `VALOR_INVALIDO`, `BONIFICACION_INVALIDA`, `COSTOS_INVALIDOS` (D12); 409 `COMANDO_INCONSISTENTE` |
| 7 | GET | `/costos/productos/{producto_id}/vigente` | `VER_COSTOS` | `service.obtener_costo_informado_vigente` | 200 | 403; 404 (producto inexistente o ajeno) |
| 8 | GET | `/costos/productos/{producto_id}/historial` | `VER_COSTOS` | `service.listar_historial_costos` | 200 | 403; 404 (producto inexistente o ajeno) |

Notas:
- Las rutas `/proveedores` y `/costos` se exponen como **dos routers** dentro de `proveedores/api.py`, con prefijos `/proveedores` y `/costos`. Las dos rutas de costos corresponden a D13.
- La ruta 4 se declara **antes** que la 5. Si no, `opciones` se interpreta como un `{proveedor_id}` UUID y responde 422.
- En las rutas 7 y 8, `proveedores` resuelve el 404 del producto con `catalogo_service.obtener_producto`, una dirección permitida por `02` §5.3. Hace falta porque el repositorio devuelve una lista vacía o `None` tanto para un producto ajeno como para uno sin costos, y la spec exige 404 para el ajeno (INV-21).
- No existe una ruta `DELETE` (TR-06; spec "No existe borrado de proveedores").

### 1.2 Modificadas (`catalogo/api.py`)

| Método | Ruta | Permiso | Cambio |
| --- | --- | --- | --- |
| POST | `/catalogo/productos` | `GESTIONAR_CATALOGO` (sin cambio) | El cuerpo suma `proveedor_id`, que es obligatorio. El sobre pasa a `PRODUCTO_CREAR` **v2**. Errores nuevos: 404 si el proveedor no existe o es ajeno (FK `fk_producto__proveedor`) y 422 `PROVEEDOR_INACTIVO`. La respuesta suma `proveedor_id` y `proveedor_nombre`. |
| PUT | `/catalogo/productos/{producto_id}` | `GESTIONAR_CATALOGO` | El cuerpo suma `proveedor_id` obligatorio (estado completo) y el sobre pasa a **v2**. Los errores nuevos son los mismos. Conservar el proveedor actual aunque esté inactivo se acepta (D5). |
| GET | `/catalogo/productos/{producto_id}` | `GESTIONAR_CATALOGO` | La respuesta suma `proveedor_id` y `proveedor_nombre` (D13, opción B). No cambia el permiso. |
| GET | `/catalogo/productos` | `GESTIONAR_CATALOGO` | Ver §3.3 y el punto a confirmar P1. |

## 2. Esquemas

### 2.1 Proveedores

**`ProveedorCrearRequest`** (ruta 1) y **`ProveedorModificarRequest`** (ruta 2)

| Campo | Tipo | Oblig. | Notas |
| --- | --- | --- | --- |
| `nombre` | string | sí | Se recorta. Si queda vacío, `NOMBRE_INVALIDO`. Es único en la organización (D7). |
| `cuit` | string \| null | no | Acepta guiones y espacios. Se normaliza a 11 dígitos y, si no llega a 11, `CUIT_INVALIDO`. No se valida el dígito verificador (D7). |
| `contacto`, `telefono`, `email` | string \| null | no | Texto libre, sin validación de formato (`03` §6 no la define). |
| `activo` | bool | sí, **solo en Modificar** | `false` con productos activos → `PROVEEDOR_CON_PRODUCTOS_ACTIVOS`. |

`PUT` reemplaza el estado completo: un opcional ausente o `null` se guarda como `null`. Así lo definen la spec ("cuyo contenido es el estado completo deseado") y el mismo criterio de `PUT /catalogo/*`.

**`ProveedorResponse`** (rutas 1, 2, 3 y 5): `id` uuid, `nombre` string, `cuit` string\|null (siempre 11 dígitos sin guiones), `contacto`, `telefono`, `email` string\|null, `activo` bool, `creado_en` y `actualizado_en` datetime. No lleva saldo (CC-04 llega con el change 08).

**Ruta 3, query:** `cursor?`, `limite?` (≤ 100), `texto?` (subcadena sin distinguir mayúsculas; la spec dice **nombre o CUIT**, ver P5) y `activo?` (bool; si se omite, trae todos). Ordena por `nombre`. La respuesta es `PaginaProveedores { items: ProveedorResponse[], cursor_siguiente }`.

**Ruta 4:** `ProveedorOpcionResponse { id, nombre }`. Trae solo activos, sin CUIT ni contacto (D8). Paginación en P2.

### 2.2 Costos

**`CostoInformarRequest`** (ruta 6), de D12:

| Campo | Tipo | Oblig. | Formato / notas |
| --- | --- | --- | --- |
| `proveedor_id` | uuid | sí | Debe estar activo y ser el proveedor actual de cada producto (D3). |
| `costos` | array | sí | De 1 a **200** elementos. Una tupla `(producto_id, presentacion_id, vigencia_desde)` repetida → `COSTOS_INVALIDOS`. |
| `costos[].producto_id` | uuid | sí | El producto debe estar activo. |
| `costos[].presentacion_id` | uuid | sí | Debe ser del producto, estar activa y tener `usar_en_compra` (ADR-010). |
| `costos[].valor` | **string** decimal | sí | `> 0`, **como máximo 2 decimales**. Si trae más, se rechaza y no se redondea: `VALOR_INVALIDO` (D12, TR-03). Ejemplo: `"18000.00"`. |
| `costos[].incluye_iva` | bool | sí | |
| `costos[].bonificacion` | **string** decimal | no (por defecto `"0"`) | Fracción en `[0, 1)`, **como máximo 6 decimales**. Si no, `BONIFICACION_INVALIDA`. Ejemplo: `"0.100000"`. |
| `costos[].vigencia_desde` | date | sí | Admite fechas pasadas y futuras (D12). |
| `costos[].observacion` | string \| null | no | |

La cantidad de decimales **no** se restringe con el patrón del esquema HTTP. Esa validación pertenece al dominio (`lote.py`), de modo que devuelva `VALOR_INVALIDO` o `BONIFICACION_INVALIDA` y no un 422 genérico (spec "Valor o bonificación inválidos"). Ver P3 para números JSON.

**`CostoInformadoResponse`** (rutas 7 y 8):

| Campo | Tipo | Formato |
| --- | --- | --- |
| `id`, `proveedor_id`, `producto_id`, `presentacion_id` | uuid | |
| `valor` | string | 2 decimales (`numeric(14,2)`), ejemplo `"18000.00"` |
| `incluye_iva` | bool | |
| `bonificacion` | string | 6 decimales (`numeric(9,6)`), ejemplo `"0.000000"` |
| `alicuota_aplicada` | string | 6 decimales (`numeric(9,6)`), congelada, ejemplo `"0.210000"` |
| `costo_base` | string | 6 decimales (`numeric(18,6)`), ejemplo `"1239.669421"` |
| `vigencia_desde` | date | |
| `observacion` | string \| null | |
| `usuario_id` | uuid | Quién lo registró (spec del historial) |
| `operation_id` | uuid | Enlaza con la auditoría (D15) |
| `creado_en` | datetime | Momento del registro |

Nombres para mostrar (proveedor, presentación, usuario): ver P4.

**Ruta 6, respuesta** (P6): `CostoInformarResponse { costos: [{ id: uuid, costo_base: string(6) }] }` en el orden del pedido. Sale de `comando.resultado` (`costo_ids`, `costos_base`), así que un reenvío idempotente devuelve exactamente lo mismo. D12 lo fija: "Resultado: ids y costo base de cada costo".

**Ruta 6, error de fila** (P9, enmienda aprobada 2026-09-24): un error de `COSTO_INFORMAR` específico de una fila del lote (`PRESENTACION_INVALIDA`, `VALOR_INVALIDO`, `BONIFICACION_INVALIDA`, `PROVEEDOR_NO_CORRESPONDE`, `PRODUCTO_INACTIVO`, `RECURSO_NO_ENCONTRADO` de un producto referenciado, o `COSTOS_INVALIDOS` por duplicado dentro del lote) suma `fila: integer` al problem+json de la respuesta -- el índice 0-based dentro de `costos` de la fila que lo causó. Un error que no es de una fila puntual (permiso, proveedor no encontrado/inactivo, lote vacío o con más de 200 costos) no lleva `fila`. Mecanismo: `DomainError` gana un campo aditivo opcional `extension: dict[str, Any] | None` (`app/core/errors.py`); `app/main.py::_domain_error_a_problem_details` vuelca `exc.extension` sobre el cuerpo si no es `None`. No cambia ningún error existente que no pase `extension`.

**Ruta 7, query:** `fecha?` (date). Si se omite, toma la fecha de negocio de la organización: `identidad_service.fecha_de_negocio(org, sesion, SystemClock())` (TR-04, D13). Respuesta en P7.

**Ruta 8, query:** `cursor?` y `limite?` (≤ 100). No tiene filtros. El orden es `vigencia_desde DESC, creado_en DESC, id DESC` (D4, D13) e incluye las vigencias futuras (programadas). La respuesta es `PaginaCostosInformados { items: CostoInformadoResponse[], cursor_siguiente }`.

## 3. Cambios en catálogo

### 3.1 Cambio incompatible en el contrato de escritura

- **`ProductoCrearRequest` y `ProductoModificarRequest` suman `proveedor_id: uuid` OBLIGATORIO.** Esto **rompe** el contrato de request: un cliente que no lo envíe recibe el 422 de validación y no se crea ni se modifica nada. La spec lo expresa como "sin proveedor el contenido es inválido".
- `catalogo/api.py` pasa a construir los sobres de `PRODUCTO_CREAR` y `PRODUCTO_MODIFICAR` con **`version=2`** y a incluir `proveedor_id` en el contenido. La v1 ya se retiró en la tarea 9.2 (D6). Hoy esos dos endpoints fallan con `VERSION_DE_COMANDO_SIN_HANDLER`: son las 15 fallas nominadas al cierre del grupo 9, y este cambio las resuelve.
- El resto de los endpoints de catálogo (categorías, marcas, presentaciones, referencia) siguen en v1 sin cambios.

### 3.2 Detalle de producto (`ProductoDetalleResponse`)

- Suma `proveedor_id: uuid`. **Hoy no está en `ProductoResponse` ni en el detalle**: la tarea 10.1 no lo daba por presente y aquí se agrega.
- Suma `proveedor_nombre: string`, que `catalogo/queries.py::obtener_producto_con_presentaciones` resuelve llamando a `catalogo_service.consultar_proveedor(org, producto.proveedor_id, sesion).nombre` (ADR-025, D13). Viene siempre, con el proveedor activo o inactivo. `catalogo` no lee la tabla `proveedor` y no cambia el permiso de `/proveedores/opciones` (D8).
- Como la FK garantiza que el proveedor existe, un `None` del puerto se trata como error interno (`assert`) y no como 404. Sin el puerto registrado, falla cerrado (`RuntimeError`, ADR-025).
- `POST /catalogo/productos` devuelve el mismo `ProductoDetalleResponse`, así que también incluye `proveedor_nombre`.
- Nota: la función registrada lee con `FOR SHARE` (ADR-025). En el `GET` eso toma un bloqueo compartido breve, dentro de una transacción de solo lectura. Se acepta sin crear una variante sin bloqueo (D13: "la misma función").

### 3.3 Listado y `PUT` de producto (`ProductoResponse`)

- D13 y la spec **no exigen** cambios en el listado. Se recomienda sumar solo `proveedor_id` a `ProductoResponse`, que el detalle hereda, **sin** `proveedor_nombre`, para no llamar al puerto N veces por página (P1). La consecuencia es que el listado y la respuesta de `PUT` también llevan `proveedor_id`.
- No se agrega un filtro por proveedor al listado: ninguna fuente lo pide. La pantalla de costos filtra en el cliente los productos del proveedor.

## 4. Impacto en el frontend (grupo 11)

- **10.4:** regenerar `backend/openapi.json` y `frontend/src/api/schema.gen.ts`. `ProductoCrearDatos` y `ProductoModificarDatos` (`features/catalogo/api.ts`) quedan con `proveedor_id` obligatorio, y el `typecheck` va a marcar cada lugar que los construye.
- `domain/catalogo/productoSchema.ts`: `proveedor_id` pasa a ser obligatorio en Zod.
- `areas/admin/catalogo/ProductoFormScreen.tsx`: agrega un selector alimentado por `GET /proveedores/opciones`. En edición conserva el proveedor actual inactivo usando `proveedor_id` y `proveedor_nombre` del detalle y lo muestra con el texto "(inactivo)" (D16). `mapaErrorACampo.ts` mapea `PROVEEDOR_INACTIVO` al campo proveedor.
- `features/proveedores/*` es nuevo (11.2 a 11.5): los tipos `ProveedorResponse`, `CostoInformadoResponse`, etc. se generan del OpenAPI, y los decimales se tipan `string` y se operan con decimal.js.
- La lista de productos no se rompe: `proveedor_id` es un campo nuevo que solo se agrega.

## 5. Puntos a confirmar

Solo se listan cuestiones que `design.md`, los ADR y los docs no resuelven. Quedan **resueltos** y no se reabren: PUT como reemplazo completo (spec), el máximo de 200 costos y el rechazo de decimales de más (D12), un permiso por ruta y `/opciones` con `GESTIONAR_CATALOGO` (D8), `proveedor_nombre` en el detalle (D13, opción B), y v2 con retiro de v1 (D6).

| # | Punto | Opciones | Recomendación |
| --- | --- | --- | --- |
| P1 | ¿Dónde va `proveedor_id` en productos? | A) en `ProductoResponse` (listado, PUT y detalle); B) solo en el detalle | **A.** Es una columna propia y no cuesta nada. Evita una clase extra y el detalle lo hereda. `proveedor_nombre` va solo en el detalle. **Aprobado 2026-09-24.** |
| P2 | ¿`/proveedores/opciones` va paginado? D13 lista las tres rutas con "cursor por nombre, límite 100", pero `repository.listar_opciones_de_proveedores` devuelve todos, sin cursor. | A) paginado `{items, cursor_siguiente}`, con límite de 100; B) lista completa | **A.** Cumple `02` §11 y D13 al pie de la letra, y el selector puede pedir la página siguiente. Requiere sumar `cursor` y `limite` al repositorio (10.2). **Aprobado 2026-09-24.** |
| P3 | ¿Un decimal enviado como **número** JSON (`18000`) en `POST /costos`? Hoy `CostoDelLoteContenidoV1` usa `Decimal`, que lo acepta. | A) el request HTTP tipa `valor` y `bonificacion` como `str` estricto con un patrón `^-?\d+(\.\d+)?$` y convierte a `Decimal`: un número JSON se rechaza con 422; B) aceptar números | **A.** `02` §10.2 es un DEBE, y un número JSON puede llegar ya degradado por `float` en el cliente. El patrón no limita la cantidad de decimales, que sigue validando el dominio. **Aprobado 2026-09-24.** |
| P4 | Nombres en el historial. La spec pide mostrar "proveedor, presentación, usuario". | A) solo ids; B) sumar `proveedor_nombre` (tabla propia) y `presentacion_nombre` (vía `catalogo_service`, dirección permitida), y `usuario_id` solo como id | **B.** Quien tiene `VER_COSTOS` puede no tener `GESTIONAR_PROVEEDORES` ni acceso al detalle de usuarios, así que el front no puede resolver esos nombres. El nombre de usuario queda fuera porque `identidad/service.py` no expone una búsqueda por id: se deja para cuando exista, sin inventarla ahora. **Aprobado 2026-09-24.** |
| P5 | El filtro `texto` de `GET /proveedores`: la spec dice "nombre o CUIT", pero el repositorio de la tarea 7.2 solo busca en `nombre`. | A) ampliarlo a `nombre ILIKE OR cuit LIKE dígitos(texto)`; B) dejar solo el nombre y corregir la spec | **A.** La spec (`administracion-de-proveedores`, requisito de consultas) es la fuente. Es un ajuste del repositorio con su prueba en 10.2. **Aprobado 2026-09-24.** |
| P6 | Respuesta de `POST /costos` | A) `{costos:[{id, costo_base}]}` desde `comando.resultado`; B) volver a leer las filas completas | **A.** D12 fija el resultado, un reenvío idempotente devuelve lo mismo sin otra lectura, y el front ya tiene el resto de los datos. La pantalla vuelve a pedir el historial al invalidar. **Aprobado 2026-09-24.** |
| P7 | `GET …/vigente` cuando no hay costo vigente | A) 200 `{ fecha, costo: CostoInformadoResponse \| null }`; B) 404 | **A.** Deja el 404 solo para un producto inexistente o ajeno (INV-21). "Sin costo vigente" es un resultado válido (spec, fecha `2026-08-31`), y `fecha` devuelve cuál se usó cuando se omitió. **Aprobado 2026-09-24.** |
| P8 | Código HTTP de `PUT /proveedores/{id}` y de `POST /costos` | 200 / 201, igual que en el 05 | **Confirmar 200 para PUT y 201 para POST**, el mismo patrón que `catalogo/api.py`. **Aprobado 2026-09-24.** |
| P9 | El problem+json de un error de `COSTO_INFORMAR` no dice qué fila del lote falló; el frontend (`CostosCargaScreen.tsx`) adivinaba buscando un UUID en `title`, frágil. | A) sumar `fila: integer` (0-based) al problem+json de errores específicos de una fila, vía un campo aditivo `extension` en `DomainError`; B) mantener la heurística del frontend | **A.** Aditivo en `core/errors.py` (sin romper ningún error existente), quita la heurística. **Aprobado 2026-09-24 (enmienda posterior al resto de P1-P8).** |
| P10 | La verificación manual (tarea 13.5) encontró que `CostosHistorialScreen.tsx` no muestra quién registró cada costo: P4 había dejado `usuario_nombre` fuera porque `identidad/service.py` no exponía una búsqueda por id. La pantalla necesita ese nombre para cumplir el requisito "Historial y costo vigente por producto" (spec `administracion-de-proveedores`, "...con lo informado, la alícuota aplicada, el costo base, el usuario y el momento de registro"). | A) sumar `usuario_nombre: string` a `CostoInformadoResponse` (rutas 7 y 8), resuelto por `proveedores/api.py` vía una función nueva y pública de `identidad/service.py` (`obtener_nombres_de_usuarios`, búsqueda por lote de un conjunto de ids, filtrada por `organizacion_id`) -- nunca importando `identidad.models`/`repository` directamente; B) dejarlo fuera y resolverlo solo en el frontend con otra llamada | **A.** Cambio aditivo (no rompe ningún cliente existente), respeta `CLAUDE.md` §4 (un módulo usa a otro solo por su `service.py`) y evita N+1 al resolver todos los ids de una página en una sola consulta. `identidad -> proveedores` no cambia de dirección: sigue siendo `proveedores.api -> identidad.service`, ya usado hoy para `fecha_de_negocio` y ya permitido por el contrato `proveedores-solo-por-service-ajeno` de `import-linter` (no incluye `identidad.service` en `forbidden_modules`). **Aprobado durante la verificación manual 13.5 (2026-09-25).** |
| P11 | La verificación manual (tarea 13.5) encontró que la pantalla de historial no muestra el último costo informado de CADA presentación del producto -- solo el vigente del producto (una sola presentación), lo que no alcanza para detectar una presentación con un costo desactualizado. | A) sumar `por_presentacion: list[CostoInformadoResponse]` a `CostoVigenteResponse` (ruta 7): el último costo informado (D4: `vigencia_desde DESC, creado_en DESC, id DESC`) de CADA presentación del producto con al menos un costo con `vigencia_desde <= fecha` -- una presentación sin costo se omite. Se resuelve con una única consulta `SELECT DISTINCT ON (presentacion_id) ...` en `proveedores/repository.py::obtener_ultimo_por_presentacion`, nunca trayendo el historial completo a Python. El orden de exhibición es por `presentacion_nombre` (aplicado en `api.py` sobre la lista ya resuelta, una vez que los nombres están disponibles -- la consulta SQL debe empezar su `ORDER BY` por `presentacion_id`, la columna del `DISTINCT ON`). Puramente informativo: el precio (PRC-11) sigue calculándose solo con `costo` (el costo vigente del producto), nunca con esta lista; B) una ruta nueva dedicada (`GET .../por-presentacion`) | **A.** Cambio aditivo sobre una ruta ya existente (no rompe ningún cliente: `costo` no se toca), evita un segundo viaje de red desde la pantalla que ya pide `/vigente`, y reutiliza el mismo mecanismo de resolución de nombres por lote (`identidad_service.obtener_nombres_de_usuarios`, un solo llamado que incluye los usuarios de `costo` y de `por_presentacion` juntos) que P4/P10. `CostosHistorialScreen.tsx` agrega una sección "Último costo informado por presentación" (tabla: presentación, proveedor, vigencia desde, informado, costo base por unidad, insignia "Vigente" en la fila cuyo `id` coincide con `costo.id`) debajo del box de costo vigente, con una nota fija aclarando que el precio se calcula solo con el costo vigente; la sección no se renderiza si la lista viene vacía. **Aprobado durante la verificación manual 13.5, opción B de la decisión del usuario (2026-09-25) -- ver tarea 14.6.** |
