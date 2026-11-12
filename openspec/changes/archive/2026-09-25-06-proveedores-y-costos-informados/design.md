## Context

Segundo maestro sobre el bus del change 04 y primer change que escribe **dinero** (costos). Ver `proposal.md` para el porqué. Estado relevante:

- `catalogo` (change 05) está archivado: `producto.proveedor_id` es `uuid` nulable **sin FK** (D1 del 05); `PRODUCTO_CREAR`/`PRODUCTO_MODIFICAR` v1 no traen proveedor y el handler pasa `proveedor_id=None`. `catalogo/service.py` expone el puerto `registrar_verificador_uso` (ADR-023) con la lista vacía en producción.
- `02` §5.3: `proveedores ──► catalogo, stock, costeo, cuentas_corrientes`; `catalogo ──► (sin dependencias de negocio)`. **`catalogo` no puede importar `proveedores`** (sería un ciclo): esto condiciona cómo valida el proveedor del producto (D9).
- Los permisos `GESTIONAR_PROVEEDORES`, `VER_COSTOS` y `EDITAR_COSTOS` ya existen en `identidad/domain/permisos.py` y en la base (change 03).
- El bus audita una fila `origen = COMANDO` por comando ejecutado (`entidad = "comando"`), sin `antes`/`despues` (ADR-022).
- `core/money.py` (`redondear_costo`, 6 decimales, `ROUND_HALF_UP`) y `lib/money.ts` (decimal.js clonado con `ROUND_HALF_UP`) ya existen; el arnés de `shared/fixtures/calculo/` corre en pytest y Vitest (CAT-08 es el precedente, D8 del 05).
- Tres ratchets (cobertura del bus, un permiso por ruta, aislamiento INV-21) y los de esquema (INV-02, INV-03, modelos = migración, repositorios con `organizacion_id`) alcanzan automáticamente a todo lo nuevo.
- No hay datos reales: el despliegue es el change 27a y la carga real el 10. Solo las bases de desarrollo tienen productos sin proveedor.

## Goals / Non-Goals

**Goals:**
- `03` §6 fiel para `proveedor` y `costo_informado`, con las garantías de base que la regla permite (FK compuestas, `CHECK`, solo inserción).
- CST-02 en un único juego de casos compartidos, idéntico en Python y TypeScript.
- Cerrar CAT-01/CAT-06 (proveedor obligatorio) sin romper `02` §5.3 ni el `downgrade`.
- Dejar a `proveedores/service.py` listo para que el change 13 lea el costo vigente (PRC-11) y el 11 compare (CMP-04).

**Non-Goals:**
- Saldo o cuenta corriente del proveedor (08). Compras y su verificador de uso (11).
- Importación masiva (10). Varios proveedores por producto (etapa 4).

## Decisions

Las decisiones que eran **BLOQUEANTES** (B1–B8, grupo 0 de `tasks.md`) quedaron resueltas por el usuario el 2026-09-23, todas con la opción recomendada (A); las specs reflejan la opción aprobada. Los supuestos de D6 y D12 se confirmaron en la misma fecha. D5 y D9 se registran como ADR (ADR-026 y ADR-025); su texto fue aprobado por el usuario el 2026-09-23, ambos en estado *Vigente*. La Open Question sobre el nombre del proveedor inactivo en el formulario de producto se resolvió el 2026-09-23 con la opción B (ver D8, D9, D13 y D16).

### D1 — ¿Un costo informado "usa" la presentación? (INV-18) (B1, resuelto)

`01` no dice si registrar un costo sobre una presentación la congela (CAT-04). La deuda del 05 exige decidirlo.

- **A) Sí: `proveedores` registra su verificador** (`catalogo_service.registrar_verificador_uso("costo_informado", …)`, `EXISTS` sobre `costo_informado` por `presentacion_id`). **Consecuencia:** el historial siempre se lee con las mismas unidades con que se informó; una presentación con unidades mal cargadas y ya costeada se corrige creando una nueva y desactivando la anterior (el camino normal de CAT-04). Cero esquema nuevo.
- **B) No se registra; se agrega `costo_informado.unidades_presentacion` congelada.** **Consecuencia:** la presentación sigue editable, pero agrega una columna que `03` §6 no define (ADR + actualizar `03`), y un costo "Caja x12 a $18.000" pasaría a mostrarse junto a una presentación que ya no tiene 12 unidades.
- **C) No se registra y no se congela nada.** **Consecuencia:** el costo base guardado sigue siendo correcto, pero "valor por presentación" deja de ser reconstruible (CST-02 no se puede recalcular) y el historial miente.

**Recomendación: A.** Es la lectura natural de CAT-04 ("usada en alguna operación": `COSTO_INFORMAR` es una operación con `operation_id` y auditoría, AUD-01), no toca el esquema y cumple la deuda nominada. No requiere ADR nuevo: aplica ADR-023 tal cual.

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** `proveedores` registra el verificador `costo_informado` en el puerto de ADR-023; INV-18 alcanza a las presentaciones con costo informado. Sin cambio de esquema.

### D2 — Productos existentes sin proveedor antes del `NOT NULL` (B2, resuelto) **[ALTA: migración de datos]**

Todo producto creado antes de este change tiene `proveedor_id` nulo (no existía la tabla). `03` §17 exige "agregar como opcional, completar datos, agregar la restricción", y `04` §2.1 punto 4 exige que la migración suba y baje limpia **con datos**.

- **A) La migración crea, solo en las organizaciones con productos sin proveedor, un proveedor provisorio inactivo** ("Proveedor a asignar", sin CUIT) y se lo asigna a esos productos; luego `VALIDATE` y `SET NOT NULL`. **Consecuencia:** la migración siempre sube; el dato provisorio es visible, no se ofrece para asignar (inactivo, D5) y se reemplaza con `PRODUCTO_MODIFICAR`. Es un dato generado por migración, pero de corrección (`03` §17 "completar datos"), no de ejemplo.
- **B) La migración aborta si hay productos sin proveedor**, con un mensaje; en desarrollo se recrea la base. **Consecuencia:** sin dato inventado, pero no cumple `04` §2.1 punto 4 (toda base con productos del 05 los tiene sin proveedor) y rompe `alembic upgrade head` en cada entorno de desarrollo.
- **C) Partir: FK en este change y `NOT NULL` en un `06b` previo al 10.** **Consecuencia:** CAT-01 sigue a medias otro change; reordena `04`.

**Recomendación: A.** Es la única que cumple `03` §17 y `04` §2.1 punto 4 a la vez. El `downgrade` vuelve a `NULL` los productos que apuntan al provisorio (identificado por una marca en la propia migración, no por el nombre) antes de borrar las tablas.

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** La migración crea un único proveedor "Proveedor a asignar" inactivo por organización con productos sin proveedor, se lo asigna, luego `SET NOT NULL`; el `downgrade` lo revierte. El SQL exacto se describe y confirma antes de escribirlo (tarea 4.1, zona **[ALTA]**).

**SQL de la tarea 4.1 aprobado por el usuario el 2026-09-23** (detalle en `tasks.md` 4.1). Esta aprobación **reemplaza la forma de revertir** descrita arriba:
- **Sin marca:** no hay marca ni valor centinela para identificar al provisorio.
- **`downgrade` de esta revisión:** solo hace `DROP NOT NULL`. Los provisorios y sus asignaciones se conservan.
- **`downgrade` de `70dcb6dce507`:** pone en `NULL` `producto.proveedor_id` y borra las tablas.
- **Nombre repetido:** si ya existe un proveedor llamado exactamente "Proveedor a asignar", la migración falla entera (no reutiliza el existente).
- **`actualizado_por_id`:** `NULL` en el provisorio.

**Variante de `downgrade` aprobada (2026-09-23, ajusta el párrafo anterior):** el `downgrade` de la migración 2 (`producto_proveedor_obligatorio`) hace únicamente `DROP NOT NULL` sobre `producto.proveedor_id`; NO vuelve a `NULL` los productos que apuntan al proveedor provisorio ni lo borra. Los proveedores provisorios quedan como datos (inactivos, visibles, reasignables con `PRODUCTO_MODIFICAR` — igual que en producción). Consecuencia: no hace falta una marca/sentinela en `proveedor.contacto` ni en ninguna otra columna para identificar cuáles filas son provisorias al bajar la migración; la migración 1 (`fk_producto__proveedor`) sí se revierte completa (borra la FK y las tablas) como antes. Ver Migration Plan y tarea 4.4 (grupo 4, fuera del alcance de los grupos 2-3).

### D3 — ¿El costo debe venir del proveedor actual del producto? (B3, resuelto)

CST-01 registra proveedor y producto; CAT-06 dice "un único proveedor" en etapa 1; CST-03 resuelve el vigente **por producto**, no por proveedor.

- **A) Sí: `proveedor_id` del costo = `producto.proveedor_id` al registrar** (`PROVEEDOR_NO_CORRESPONDE` si no). El historial conserva el proveedor de cada costo aunque el producto cambie de proveedor después. **Consecuencia:** el vigente por producto (CST-03, índice de `03` §16) es coherente con CAT-06; para cargar costos de otro proveedor se cambia antes el proveedor del producto.
- **B) Cualquier proveedor activo.** **Consecuencia:** anticipa la etapa 4, pero el "vigente por producto" mezclaría proveedores sin regla de preferencia (`01` no la tiene) y PRC-13 (precedencia por proveedor) quedaría ambiguo.

**Recomendación: A.** Cuando llegue la etapa 4 (varios proveedores) se revisa con ADR.

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** Un costo de un proveedor distinto del proveedor actual del producto se rechaza con `PROVEEDOR_NO_CORRESPONDE`.

### D4 — Dos costos del mismo producto con la misma vigencia desde (B4, resuelto)

CST-03 ("el de mayor vigencia desde") no desempata. Pasa con una corrección el mismo día.

- **A) Prevalece el registrado último** (orden `vigencia_desde DESC, creado_en DESC, id DESC`; el `id` UUIDv7 desempata dentro del mismo instante). **Consecuencia:** corregir un error de carga es "informar de nuevo" (CST-03: no se sobrescribe); el índice de `03` §16 se extiende con esas columnas.
- **B) `UNIQUE (organizacion_id, producto_id, vigencia_desde)`.** **Consecuencia:** determinista por construcción, pero impide corregir un error el mismo día salvo con otra fecha, y dentro de una operación con dos presentaciones del mismo producto obliga a elegir una.

**Recomendación: A.**

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** Con la misma vigencia desde prevalece el registrado último (`creado_en DESC, id DESC`); el índice de `03` §16 se extiende con esas columnas.

### D5 — Proveedor inactivo (B5, resuelto; ADR-026 *Propuesto*)

`01` no dice qué hace un proveedor inactivo. Se propuso: un proveedor inactivo **no se asigna** a un producto (salvo conservar el actual en `PRODUCTO_MODIFICAR`) y **no recibe costos**; y se preguntó si puede desactivarse con productos activos.

- **A) No: `PROVEEDOR_CON_PRODUCTOS_ACTIVOS`**, simétrico con ADR-024 (CAT-01 exige proveedor, igual que categoría). **Consecuencia:** para dejar de trabajar con un proveedor se reasignan o desactivan antes sus productos. `proveedores` lo consulta vía `catalogo/service.py` (dirección permitida).
- **B) Sí, libremente.** **Consecuencia:** quedan productos activos con proveedor inactivo, a los que no se les puede cargar costo hasta reasignarlos.

**Recomendación: A** (y confirmar las dos reglas de la primera frase).

**Resuelto: opción A, aprobado por el usuario 2026-09-23**, incluidas las dos reglas de la primera frase (un proveedor inactivo no se asigna a un producto —conservar el actual en `PRODUCTO_MODIFICAR` sí se acepta— y no recibe costos). Registrado en `docs/adr/ADR-026-proveedor-con-productos-activos-no-se-desactiva.md`, estado *Propuesto* hasta que el usuario apruebe el texto del ADR.

### D6 — Versionado de `PRODUCTO_CREAR` y `PRODUCTO_MODIFICAR`

El contenido v1 no tiene proveedor y no puede cumplir el `NOT NULL`. Se registran **v2** (con `proveedor_id` obligatorio) y **se retira v1**: `02` §6.6 permite retirar una versión si no quedan comandos pendientes, y ambos tipos son `admite_offline=False`, así que no existen colas con v1. Un envío v1 recibe `VersionDeComandoSinHandlerError` (ya implementado en `commands/registro.py`). Los endpoints REST pasan a construir el sobre con `version=2`. Alternativa descartada: cambiar v1 en el lugar (rompe la huella de comandos v1 ya guardados en `comando` si alguien reenvía un `operation_id` viejo y oculta el cambio de contrato). **Supuesto confirmado por el usuario 2026-09-23.**

### D7 — Identidad del proveedor (B6, resuelto)

`03` §6 lista columnas sin unicidades. Recomendación: **nombre** obligatorio, recortado y único por organización (`ux_proveedor__nombre`, como categoría); **CUIT** opcional, normalizado a 11 dígitos (se descartan guiones y espacios), único por organización cuando existe (`ux_proveedor__cuit` parcial), **sin** validar dígito verificador (regla fiscal que `01` no define). Alternativas: sin unicidades (la importación del 10 duplicaría proveedores en silencio) o validar dígito verificador (rechazaría CUITs reales mal tipeados en origen sin una regla de negocio que lo pida). **Resuelto: recomendación tal cual, aprobado por el usuario 2026-09-23.** `03` §6 se actualiza con las unicidades en la verificación (13.4).

### D8 — Permiso del listado que usa el formulario de producto (B7, resuelto)

El ratchet exige exactamente un permiso por ruta. El formulario de producto (`GESTIONAR_CATALOGO`) necesita elegir proveedor.

- **A) Dos rutas en `proveedores/api.py`:** `GET /proveedores` completo (`GESTIONAR_PROVEEDORES`) y `GET /proveedores/opciones` reducido — solo proveedores activos, con `id` y `nombre`, sin CUIT ni contacto — (`GESTIONAR_CATALOGO`). **Consecuencia:** cada pantalla usa el permiso de quien la consume (criterio de D9/D12 del 05) sin exponer datos de contacto.
- **B) Una ruta con `GESTIONAR_PROVEEDORES`.** Un rol con catálogo y sin proveedores no puede dar de alta productos.
- **C) Una ruta con `GESTIONAR_CATALOGO`.** La pantalla de proveedores queda protegida por el permiso de otro dominio.

**Recomendación: A.** La pantalla de costos elige productos con las rutas de catálogo (`GESTIONAR_CATALOGO`); en los roles base quien tiene `EDITAR_COSTOS` (ADM, GES) también lo tiene. Se anota como riesgo.

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** `GET /proveedores/opciones` devuelve solo proveedores activos (`id`, `nombre`). En la edición de un producto cuyo proveedor actual está inactivo, ese proveedor no llega por esta ruta: el formulario lo conserva seleccionado a partir del `proveedor_id` del producto y lo señala como inactivo, mostrando su **nombre real** (no un texto genérico), resuelto por **opción B** el 2026-09-23 (ver D9 y D13): el detalle de producto lo obtiene a través del mismo puerto de ADR-025, sin ampliar el permiso de esta ruta.

### D9 — Cómo valida `catalogo` el proveedor sin depender de `proveedores` (B8, resuelto; ADR-025 *Propuesto*)

La **existencia y pertenencia** a la organización las garantiza la FK compuesta `(organizacion_id, proveedor_id) → proveedor`; el repositorio de catálogo ya traduce `IntegrityError` por nombre de restricción (D6 del 05): `fk_producto__proveedor` → 404. Falta el chequeo de **actividad** (D5), que la base no expresa.

- **A) Puerto de consulta en `catalogo/service.py`**, gemelo del de ADR-023: `registrar_consulta_proveedor(funcion)`, donde `funcion(organizacion_id, proveedor_id, sesion) -> EstadoProveedor | None` (`None` = no existe; si no, `activo`). `proveedores` lo registra al arrancar. La consulta lee con `FOR SHARE` para serializar con `PROVEEDOR_MODIFICAR` (D14). Sin puerto registrado, `PRODUCTO_CREAR` falla cerrado (error de configuración, nunca acepta sin validar). **Consecuencia:** sin ciclo y validación completa en el servidor (TR-10).
- **B) Solo FK, sin chequeo de actividad.** Viola D5 y TR-10 si D5 se aprueba.
- **C) `catalogo` importa `proveedores.service`.** Ciclo prohibido por `02` §5.3.

**Recomendación: A**, registrada como **ADR-025** (es un segundo uso del mecanismo de ADR-023 con otra firma y semántica "falla cerrado", por eso no se asume cubierto por aquel).

**Resuelto: opción A, aprobado por el usuario 2026-09-23.** FK compuesta + puerto `registrar_consulta_proveedor` en `catalogo/service.py` que verifica actividad; sin puerto registrado se rechaza (falla cerrado). Registrado en `docs/adr/ADR-025-validacion-de-proveedor-desde-catalogo-por-puerto.md`; texto aprobado por el usuario 2026-09-23, estado *Vigente*.

**Open Question resuelta (opción B, aprobada 2026-09-23):** `EstadoProveedor` (el tipo que devuelve la consulta) lleva, además de `activo`, el campo `nombre`. El detalle de producto (`catalogo`, consulta de lectura de `GET /productos/{id}`) usa la misma consulta registrada para mostrar el **nombre real** del proveedor asignado cuando está inactivo, en vez de un texto genérico, sin que `catalogo` lea la tabla `proveedor` ni se amplíe el permiso de `GET /proveedores/opciones` (D8). Ver D13 (consultas) y D16 (frontend); ADR-025 documenta esta extensión.

### D10 — Esquema

- `proveedor`: columnas de `03` §6 + `actualizado_en`, `actualizado_por_id` (`03` §2.3), `UNIQUE (organizacion_id, id)`, unicidades de D7, `GRANT SELECT, INSERT, UPDATE` (sin `DELETE`).
- `costo_informado`: columnas de `03` §6; FK compuestas a `proveedor`, `producto`, `presentacion` y `usuario`; `ck_costo_informado__valor` (`valor > 0`), `ck_costo_informado__bonificacion` (`0 <= b < 1`), `ck_costo_informado__alicuota` (`>= 0`), `ck_costo_informado__costo_base` (`>= 0`); índice de D4. **Solo inserción**: `GRANT SELECT, INSERT` (CST-03 en la base, no solo en el servicio). No es tabla de libro de INV-05, pero se prueba igual citando CST-03. La coherencia presentación ↔ producto se valida en el servicio (una FK triple exigiría una unicidad nueva en `presentacion`, tabla de otro módulo).
- `producto`: `fk_producto__proveedor` compuesta y `NOT NULL` (D2, plan de migración abajo).

### D11 — CST-02 como cálculo compartido

Función pura `proveedores/domain/costo_base.py::calcular_costo_base(valor, incluye_iva, alicuota, bonificacion, unidades)` y `frontend/src/domain/proveedores/costoBase.ts`, con `shared/fixtures/calculo/cst-02-costo-base.json` (**primero los casos, después el código**: `02` §10.4). Casos: los cuatro de `01` §6.1, `$10.000 / 12` (ADR-010), redondeo de medio hacia arriba en el sexto decimal, IVA + bonificación combinados, alícuota `0`, y entradas inválidas (valor ≤ 0, bonificación ≥ 1, unidades < 1). Operación sin redondeos intermedios y un único `redondear_costo` al final (TR-03). En TS se usa la instancia de `lib/money.ts`; se verifica que su precisión (decimal.js: 20 dígitos significativos por defecto) alcanza para `numeric(14,2)` / `numeric(9,6)` con un caso de valor máximo; si no alcanza, se ajusta `precision` en `lib/money.ts` (cambio de un módulo existente, con su línea base). Propiedad Hypothesis: el resultado nunca es negativo y es monótono en el valor.

### D12 — Contenido y reglas de `COSTO_INFORMAR`

`{ proveedor_id, costos: [{ producto_id, presentacion_id, valor, incluye_iva, bonificacion?, vigencia_desde, observacion? }] }`, entre 1 y **200** costos (supuesto: el volumen inicial es ~100 productos, `00` §5; un lote mayor es importación, change 10). Decimales como string; `valor` con más de 2 decimales o `bonificacion` con más de 6 se **rechazan**, no se redondean (TR-03: redondear solo donde la regla lo dice). Repetir `(producto, presentación, vigencia)` en el lote → `COSTOS_INVALIDOS`. `alicuota_aplicada` = valor de la alícuota del producto al registrar (vía `catalogo/service.py` → `configuracion/service.py`), guardada siempre, incluya IVA o no. La vigencia desde admite fechas pasadas (carga de historia) y futuras (programadas). Resultado: ids y costo base de cada costo. **Supuestos (máximo 200, vigencias pasadas y futuras, decimales de más rechazados) confirmados por el usuario 2026-09-23.**

### D13 — Consultas

- `GET /proveedores`, `GET /proveedores/{id}`, `GET /proveedores/opciones` (D8), cursor por `nombre`, límite 100.
- `GET /costos/productos/{producto_id}/vigente?fecha=` y `GET /costos/productos/{producto_id}/historial` (`VER_COSTOS`), cursor por `(vigencia_desde, creado_en, id)`. La fecha por defecto es la de negocio en la zona de la organización (TR-04, reloj de `core/clock.py`). El vigente se resuelve con SQL (`ORDER BY … LIMIT 1` sobre el índice de D4), nunca trayendo filas a Python.
- `proveedores/service.py::obtener_costo_informado_vigente(organizacion_id, producto_id, fecha, sesion)` para el change 13.
- `GET /productos/{id}` (`catalogo`, ya existente) suma `proveedor_nombre` a su respuesta: la consulta de detalle de `catalogo` llama a la misma función registrada por el puerto de ADR-025 (`registrar_consulta_proveedor`) para obtener el nombre del proveedor asignado, activo o no. Sin cambio de permiso (sigue `GESTIONAR_CATALOGO`) ni de tabla leída directamente.

### D14 — Concurrencia

Ninguna operación de este change toca tablas de saldo ni entra en el orden de `02` §7.3. `PROVEEDOR_MODIFICAR` toma `FOR UPDATE` sobre el proveedor; `PRODUCTO_CREAR/MODIFICAR` (vía puerto D9) y `COSTO_INFORMAR` lo leen con `FOR SHARE`: una desactivación y una asignación simultáneas se serializan (nunca queda un producto activo recién asignado a un proveedor recién desactivado). `COSTO_INFORMAR` lee el producto con `FOR SHARE` (el 05 lo modifica con `FOR UPDATE`, D5 del 05) para que el chequeo de D3 no compita con un cambio de proveedor. Orden fijo dentro de `COSTO_INFORMAR`: proveedor, luego productos por `id` ascendente (evita interbloqueos entre dos lotes). Dos costos concurrentes con la misma vigencia no necesitan bloqueo: D4 los desempata.

### D15 — Auditoría

AUD-01 incluye "costos informados". Basta la fila automática del bus (`accion = COSTO_INFORMAR`, `operation_id`): la fila de `costo_informado` es inmutable y lleva el mismo `operation_id`, así que valor informado y anterior vigente son reconstruibles sin duplicar datos. Los servicios nuevos no auditan por su cuenta (no necesitan el parámetro de ADR-022).

### D16 — Frontend

Ruta `/admin/proveedores/*` (carga diferida, dentro de `AdminLayout`, enlaces absolutos — lección 10.8 del 05): listado, ficha (alta/edición), carga de costos con `useFieldArray` y vista previa por fila con `domain/proveedores/costoBase.ts`, historial por producto. `ProductoFormScreen.tsx` suma el selector de proveedor (D8) y el esquema Zod lo exige; en edición, si el proveedor actual está inactivo, se muestra con su nombre real (tomado de `GET /productos/{id}`, D13) seguido de "(inactivo)", no un texto genérico. Mismos patrones del 05: TanStack Query, `Operation-Id` en `onMutate`, mapeo de `codigo` a campo, componentes de `components/ui/`. La bonificación se ingresa en porcentaje y se convierte a fracción con decimal.js.

## Risks / Trade-offs

- [El proveedor provisorio de D2 queda olvidado en datos reales] → Solo existe en bases con productos previos al 06 (desarrollo); es inactivo y visible; la verificación manual lo reasigna.
- [Un rol personalizado con `EDITAR_COSTOS` sin `GESTIONAR_CATALOGO` no puede elegir productos en la pantalla de costos] → En los roles base no pasa; si pasa, un change posterior agrega una ruta de opciones de productos en `catalogo` (D8).
- [Puerto de D9 sin registrar en algún arranque] → falla cerrado y una prueba de arranque verifica que `app.main` lo registra.
- [Retirar v1 de `PRODUCTO_*`] → sin colas offline para maestros; prueba que v1 se rechaza sin efectos.
- [Divergencia Python/TS en CST-02] → casos compartidos obligatorios en CI.
- [Change grande: 2 tablas, migración de datos, 3 comandos nuevos + 2 versionados, 2 pantallas] → grupos backend/frontend separados; si la UI de costos se desborda, partir en `06a`/`06b` en ese punto.

## Migration Plan

Dos revisiones de Alembic **[ALTA]**:

1. **`proveedores_y_costos`**: crea `proveedor` y `costo_informado` (D10) con `GRANT`s; agrega `fk_producto__proveedor` como `NOT VALID` y la valida (`VALIDATE CONSTRAINT`; las filas nulas no la violan).
2. **`producto_proveedor_obligatorio`**: por cada organización con productos sin proveedor, inserta el proveedor provisorio inactivo (D2) y lo asigna; `SET NOT NULL`. `downgrade` (variante aprobada 2026-09-23, ver D2): únicamente `DROP NOT NULL`; los productos migrados conservan el proveedor provisorio asignado y el provisorio no se borra (sin sentinela en `contacto` ni en otra columna: no hace falta identificar qué filas son provisorias para revertir esta migración puntual).

`downgrade` de la 1: borra la FK y las tablas. Se prueba `upgrade head → downgrade -2 → upgrade head` con productos del 05 sembrados (sin proveedor), proveedores y costos (`04` §2.1 punto 4).

## Open Questions

Ninguna bloqueante: B1–B8 resueltas el 2026-09-23. Quedan abiertos, sin efecto sobre specs ni tareas salvo lo indicado:

- ~~Cómo muestra el formulario de producto el **nombre** del proveedor actual inactivo en edición~~ **Resuelta (opción B, aprobada 2026-09-23):** el detalle de producto (`GET /productos/{id}`, `catalogo`) incluye `proveedor_nombre`, obtenido a través del mismo puerto de ADR-025 (`EstadoProveedor.nombre`), sin ampliar el permiso de `/proveedores/opciones` ni que `catalogo` lea `proveedor` directamente. Ver D8, D9, D13, D16 y ADR-025.
- Texto exacto del nombre del proveedor provisorio (D2) y si la pantalla de catálogo lo señala con un aviso. No cambia specs ni tareas.
- Si la alícuota de un producto se desactiva, ¿se puede seguir informando costo con IVA incluido con esa alícuota? Se asume que sí (la alícuota es del producto, no se "ofrece"); no cambia el cálculo.
