# Diseño técnico — 09-stock-y-costeo

> **Estado: D1 a D15 aprobadas (2026-09-30).** El usuario aprobó la opción A en cada una de D1 a D15. Gobernanza ALTA (valorización del stock y costos = dinero). Las marcadas "requiere ADR" se registran en `docs/adr/` en el grupo final de tareas, junto con las aclaraciones de `docs/01` y `docs/03` que pidan; ningún ADR está escrito todavía.

## Context

`docs/` resuelve lo esencial: stock por producto y ubicación en unidades base enteras (STK-01, INV-04), tipos de movimiento (STK-03), stock = suma de movimientos (STK-04, INV-12), stock negativo online bloqueado salvo `PERMITIR_STOCK_NEGATIVO` (STK-05, `02` §7.4), promedio ponderado móvil por organización (CST-10, CST-11, ADR-002) con historia reconstruible (CST-13) y encapsulado en `costeo` (CST-14), tablas de saldo con `stock_total` y orden global de bloqueo `saldo_cuenta → costo_producto → stock_saldo → jornada` (`02` §7.2-§7.3, ADR-015), columnas de `03` §7 y §9, el stock inicial como ingreso que recalcula el promedio y se audita (`01` §21) y `STOCK_INICIAL_REGISTRAR` solo online (`02` §6.5). El change 08 dejó los patrones a reutilizar: fila de saldo perezosa (`INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE`), PK compuesta que empieza por `organizacion_id` (ADR-035 punto 6, anticipado para `stock_saldo` y `costo_producto`), validación de existencia por FK compuesta traducida a 404 (ADR-035 punto 4), `dispositivo_id NOT NULL` en el libro (D14 del 08), ruta de escritura dedicada que llama a `sync_service.procesar_comando` (deuda del despacho genérico, change 17) y auditoría única del bus (ADR-022).

Lo que `docs/` **no** resuelve y este documento plantea como decisiones:

- `01` §19 no tiene permiso para registrar stock inicial, para administrar ubicaciones ni para ver stock o kardex.
- Nada dice cuántos stock iniciales admite un producto, cómo se corrige uno mal cargado (cantidad o costo) ni hasta cuándo. CST-11 solo define ingresos; un `STOCK_INICIAL` negativo no está definido.
- La forma del contenido del comando (unidad base o presentación; una línea o varias) y si el costo puede ser cero.
- STK-02 dice "los vehículos requieren toma" pero no si la base lo impone; no hay regla de unicidad de nombre ni de desactivación con stock.
- `03` §7 no dice si `costo_promedio` admite nulo ni cuál es el promedio de un producto sin ingresos (ADR-002 afirma "siempre hay un promedio vigente").
- `03` §9 lista para `stock_movimiento` "columnas de operación" sin detallar `dispositivo_id`; `jornada` todavía no existe; `ubicacion` no tiene `actualizado_en`, que `03` §2.3 exige a los maestros.
- `03` §2.3 nombra solo a `saldo_cuenta` como tabla de saldo sin `id`.

Restricciones: `CLAUDE.md` §4 completo; `02` §5.3 (`stock ──► catalogo, costeo`; `costeo` sin dependencias de negocio; sin ciclos).

## Goals / Non-Goals

**Goals:**

- Un `stock/service.py` y un `costeo/service.py` que 11, 14, 15, 18a, 19 y 24 usen sin reescribir: registrar movimientos (ingreso con costo, egreso) con bloqueos en el orden global, leer saldos, promedio y kardex.
- Que la base garantice INV-04, INV-05 e INV-02 sobre los libros y los saldos.
- INV-12 probado con Hypothesis contra PostgreSQL real; CST-11 con fixtures compartidos.
- Pantallas usables: ubicaciones, stock, kardex y stock inicial.

**Non-Goals:**

- No se escriben movimientos de compra, venta, transferencia, ajuste ni rendición (solo el catálogo los declara, D13).
- No se valida la toma de ubicación (STK-09): `jornada` nace en el 15.
- No se programa la verificación diaria (28): solo la consulta.

## Decisions

### D1 — Qué permiso registra un stock inicial · requiere ADR

**Qué hay que decidir.** Quién puede ingresar mercadería valorizada sin una compra detrás; cambia stock y promedio.

- **A (recomendada).** `IMPORTAR_DATOS` ("Importaciones y puesta en marcha", `01` §19), igual que el saldo inicial (ADR-033). `00` §6.1 pone "stock inicial valorizado por ubicación" en *Puesta en marcha*, y el change 10 lo importará con el mismo permiso.
- **B.** `AJUSTAR_STOCK` (ADM, GES): es el permiso de las correcciones de stock.
- **C.** Permiso nuevo `REGISTRAR_STOCK_INICIAL`, con migración del catálogo `permiso`.

**Qué implica.** A: coherente con ADR-033; solo ADM con las plantillas actuales (GES por cambio de plantilla). B: GES podría, pero un ajuste no toca el promedio (CST-12) y el stock inicial sí: mezcla dos poderes distintos. C: explícito pero agrega un permiso para una tarea de única vez.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D2 — Qué permiso administra ubicaciones · requiere ADR

**Qué hay que decidir.** Alta, modificación y desactivación de ubicaciones (STK-02). No hay permiso en `01` §19.

- **A (recomendada).** `ADMIN_CONFIGURACION` (ADM): las ubicaciones son estructura de la organización (depósito, vehículos), se cambian rara vez y un vehículo nuevo condiciona jornadas (RUT-01) y tomas.
- **B.** `GESTIONAR_CATALOGO` (ADM, GES), como un maestro más.
- **C.** Permiso nuevo `GESTIONAR_UBICACIONES` (ADM, GES), con migración.

**Qué implica.** A: sin permisos nuevos; GES no crea vehículos salvo cambio de plantilla. B: GES sí, pero el catálogo de productos pasa a gobernar la estructura de stock. C: explícito, con migración y reparto por rol a decidir.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D3 — Qué permiso permite ver stock y kardex, y quién ve costos · requiere ADR

**Qué hay que decidir.** El ratchet exige un permiso por ruta. El kardex puede mostrar costos (`stock_movimiento.costo_unitario`) y el promedio, que el vendedor no debe ver (`01` §19: "no ve costos").

- **A (recomendada).** Listado de ubicaciones, stock por ubicación y kardex con `TRANSFERIR_STOCK` (ADM, GES, SUP, VEN: quien mueve stock necesita verlo). Los campos de costo (`costo_unitario`, promedio) **se omiten** de la respuesta si el usuario no tiene `VER_COSTOS`; el promedio vigente por producto, en ruta propia con `VER_COSTOS`, definida en `catalogo` (`GET /api/v1/catalogo/productos/{producto_id}/costo`, ver la enmienda a D3 más abajo).
- **B.** `VER_REPORTES` (ADM, GES, SUP, CON) para todo, costos también con `VER_COSTOS`.
- **C.** Permiso nuevo `VER_STOCK`.

**Qué implica.** A: el vendedor ve cantidades pero nunca costos; el rol CON no ve stock en `/admin` (le llegará por reportes, 26). La respuesta depende de un segundo permiso: se prueba con los dos roles. B: el vendedor no ve el stock del depósito antes de cargar el vehículo. C: agrega permiso y migración.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

**Enmienda a D3 (aprobada 2026-09-30): dónde vive la ruta del promedio.** La lectura del costo promedio vigente **no** vive en `costeo` (`GET /api/v1/costeo/productos/{id}`, como decían las primeras tareas) sino en `catalogo`: **`GET /api/v1/catalogo/productos/{producto_id}/costo`**, en `backend/app/modules/catalogo/api.py` (prefijo `/catalogo`), con permiso `VER_COSTOS` (D3-A sin cambios). `catalogo` resuelve primero el producto en la organización del token (404 si no existe o es de otra organización, INV-21, sin revelar nada) y después llama a `costeo/service.py` (dependencia permitida `catalogo -> costeo`; `costeo` **no** importa `catalogo`, `02` §5.3). Un producto sin ingresos responde 200 con `costo_promedio` nulo (D10). Motivo: mismo patrón que ADR-035 punto 5 (las lecturas viven con su entidad) y `costeo` no puede distinguir por sí solo un producto inexistente (404) de uno sin ingresos (200 nulo) sin depender de `catalogo`. Se registrará en el ADR del grupo 10 junto con D3. `stock` sigue sirviendo ubicaciones, saldos y kardex.

### D4 — Cuántos stock iniciales admite un producto, cómo se corrige y hasta cuándo · requiere ADR

**Qué hay que decidir.** El libro no se edita (TR-06). Una carga equivocada (cantidad o costo) necesita una corrección sin borrar, y hoy no hay ajustes (llegan en el 14, y no tocan el promedio, CST-12).

- **A (recomendada).** Varios `STOCK_INICIAL` por producto y ubicación, con **cantidad con signo** (≠ 0). Positivo: ingreso con costo que recalcula por CST-11. Negativo: corrección que egresa al promedio vigente sin recalcularlo (mismo criterio que CST-12 para egresos) y no puede dejar negativo el saldo de la ubicación (`STOCK_INSUFICIENTE`, sin excepción por `PERMITIR_STOCK_NEGATIVO`). Admitidos **solo mientras el producto no tenga en la organización movimientos de otro tipo** (`PRODUCTO_CON_OPERACIONES`), análogo a CC-08. Un costo equivocado se corrige llevando el stock total a cero con negativos y recargando: con `stock_total = 0` el promedio pasa a ser el costo del nuevo ingreso (CST-11).
- **B.** Un único `STOCK_INICIAL` por producto y ubicación (índice único parcial), positivo; la cantidad se corrige con ajustes del 14 y el costo no se corrige.
- **C.** Varios, solo positivos, sin restricción temporal; correcciones de cantidad con ajustes del 14; el costo no se corrige.

**Qué implica.** A: corrige cantidad y costo en la puesta en marcha sin tipos nuevos; es una regla nueva (se propone como STK-10 en `01` §8.1) y una extensión de CST-11 (egreso por stock inicial). La restricción queda latente en este change (nadie escribe otros tipos) y se prueba insertando por el servicio. B: simple, pero un costo mal cargado contamina el promedio para siempre. C: igual que B para el costo, y permite "stock inicial" después de operar, que no es puesta en marcha.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D5 — Forma del contenido de `STOCK_INICIAL_REGISTRAR`

**Qué hay que decidir.** Unidad de la cantidad y del costo, y si un comando lleva una o varias líneas.

- **A (recomendada).** `ubicacion_id` y `lineas` (1 a 200, límite de D12 del 06): cada una `producto_id`, `cantidad_base` (entero ≠ 0, D4) y `costo_unitario` (string, costo por unidad base, obligatorio si la cantidad es positiva y prohibido si es negativa). Un producto no se repite en el comando (`PRODUCTO_REPETIDO`). Atómico (INV-01). Momento: `occurred_at` del sobre. Cada movimiento guarda `origen_tipo = STOCK_INICIAL`, `origen_id = operation_id` (no hay tabla de documento en `03`) y `costo_unitario` (el ingresado, o el promedio usado en un negativo). La pantalla ayuda a escribir cajas + unidades y las convierte a base con aritmética entera (CAT-08), sin calcular costos.
- **B.** Una línea por comando.
- **C.** Líneas en presentación (`presentacion_id`, cantidad, valor por presentación, IVA, bonificación) convertidas con CST-02.

**Qué implica.** A: una puesta en marcha de ~100 productos son uno o pocos comandos; no usa presentaciones, así que no congela unidades (sin verificador de INV-18). B: 100 comandos y 100 auditorías. C: reutiliza CST-02 pero congela presentaciones (verificador INV-18) y exige alícuota; más superficie.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D6 — Qué costo admite un ingreso de stock inicial

- **A (recomendada).** `costo_unitario > 0`, hasta 6 decimales sin redondear (TR-02), dentro de `numeric(18,6)`; si no, `COSTO_INVALIDO`.
- **B.** `costo_unitario ≥ 0` (admite mercadería sin costo, por ejemplo bonificada).
- **C.** Como A, pero hasta 2 decimales (el usuario escribe importes).

**Qué implica.** A: "valorizado" (`00` §6.1) exige valor; un cero arrastraría el promedio. B: cubre unidades bonificadas, pero baja el promedio y la utilidad aparente (la bonificación en unidades es etapa 2, DSC-10). C: pierde precisión para costos de unidad chica derivados de una caja.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D7 — Reglas de la ubicación · requiere ADR

**Qué hay que decidir.** STK-02: nombre, tipo, estado, `requiere_toma`, "los vehículos requieren toma".

- **A (recomendada).** Nombre normalizado y único por organización (`ux_ubicacion__nombre`, activas o no, como D7 del 06). `CHECK (tipo <> 'VEHICULO' OR requiere_toma)` en la base además del dominio (`VEHICULO_REQUIERE_TOMA`); para `DEPOSITO`/`OTRO` es libre, por defecto `false`. `actualizado_en` y `actualizado_por_id` como todo maestro (`03` §2.3, falta en `03` §9).
- **B.** Como A, pero la regla del vehículo solo en el dominio.
- **C.** `requiere_toma` derivado del tipo (sin columna editable).

**Qué implica.** A: la base impide un vehículo sin toma aunque falle el servicio. B: una migración o SQL manual podría romperla. C: contradice STK-02, que lo pide como indicador propio.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D8 — Desactivación de ubicaciones y operaciones sobre inactivos · requiere ADR

- **A (recomendada).** Una ubicación con algún `stock_saldo` distinto de cero no se desactiva (`UBICACION_CON_STOCK`), mismo criterio que ADR-024/ADR-026; se reactiva libremente. Sobre una ubicación inactiva o un producto inactivo no se registran movimientos nuevos (`UBICACION_INACTIVA`, `PRODUCTO_INACTIVO`; CAT-05). La comprobación se hace con las filas de `stock_saldo` de la ubicación leídas `FOR SHARE` para no competir con el orden global.
- **B.** Se desactiva siempre; el stock queda "congelado" hasta reactivarla.
- **C.** Como A, sin restringir movimientos sobre productos inactivos.

**Qué implica.** A: nada queda escondido en una ubicación invisible. B: stock fuera de toda pantalla operativa. C: contradice CAT-05 ("los inactivos no se ofrecen en nuevas operaciones").

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D9 — Reparto entre `stock` y `costeo` y orden de bloqueo · requiere ADR

- **A (recomendada).** Dos módulos. `costeo/service.py` (sin dependencias de negocio): `bloquear_costos(productos)` (ordena por `producto_id`, fila perezosa + `FOR UPDATE`), `aplicar_ingreso(...)` (CST-11 + `costo_producto_mov` + `stock_total`), `aplicar_egreso(...)` (solo `stock_total`, devuelve el promedio vigente), `obtener_promedio`. `stock/service.py`: `registrar_movimientos(lineas)` reúne todos los pares, llama primero a `costeo.bloquear_costos` y después bloquea `stock_saldo` por `(producto_id, ubicacion_id)` ascendentes (`02` §7.3), recién entonces decide e inserta. `STOCK_INICIAL_REGISTRAR`, las ubicaciones y el kardex viven en `stock`. Quien necesite `saldo_cuenta` (11, 18a) lo bloquea antes de llamar a `stock`. El producto se valida por FK compuesta (404) y su estado por `catalogo/service.py` (dependencia permitida).
- **B.** Un helper transversal `core/bloqueos.py` que conoce las cuatro tablas y bloquea en orden.
- **C.** Bloqueos consultivos (`pg_advisory_xact_lock`) por producto.

**Qué implica.** A: respeta `02` §5.3 y ADR-015 ("los handlers no bloquean filas: usan funciones de servicios"); la regla "ninguna otra parte calcula costos" (CST-14) queda en `costeo`. B: `core` pasaría a depender de modelos de negocio. C: se aparta de ADR-015.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D10 — Nacimiento de `costo_producto` y promedio de un producto sin ingresos · requiere ADR

- **A (recomendada).** Filas perezosas (patrón D10 del 08) para `costo_producto` y `stock_saldo`. `costo_promedio` **nulo** hasta el primer ingreso con costo (`CHECK (costo_promedio IS NULL OR costo_promedio > 0)`); `stock_total integer NOT NULL DEFAULT 0`; PK `(organizacion_id, producto_id)` sin `id` (ADR-035 punto 6). Cómo costea una venta sin promedio lo decide el 18a.
- **B.** `costo_promedio NOT NULL DEFAULT 0`.
- **C.** Crear la fila al dar de alta el producto, con migración para los existentes.

**Qué implica.** A: "sin costo" es distinguible de "costo cero"; matiza ADR-002 ("siempre hay un promedio vigente": vale desde el primer ingreso). B: una venta anterior al primer ingreso quedaría con costo cero y utilidad inflada sin aviso. C: acopla `catalogo` a `costeo` (prohibido por `02` §5.3) o exige puertos.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D11 — Kardex: alcance, período y paginación

- **A (recomendada).** Por producto **y** ubicación (ambos obligatorios), con `desde`/`hasta` opcionales (fechas de negocio en la zona de la organización, `hasta` inclusivo), `saldo_anterior`, saldo actual y movimientos ascendentes `(occurred_at, id)` con acumulado `SUM(...) OVER` sobre toda la historia y filtrado después; cursor opaco; límite 50, máximo 200, 422 fuera de rango. Mismo contrato que ADR-034 punto 6.
- **B.** Como A, más una vista de todas las ubicaciones con acumulado de la organización.
- **C.** Sin filtro de período.

**Qué implica.** A: reutiliza el mecanismo probado del estado de cuenta y el índice de `03` §16. B: más útil para auditar el promedio, pero duplica la lógica; puede agregarse después. C: recorrer toda la historia para ver un mes.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D12 — Columnas y referencias de los libros

- **A (recomendada).** `stock_movimiento` con las columnas de operación completas (`operation_id`, `usuario_id`, `dispositivo_id uuid NOT NULL`, `occurred_at`, `registered_at`), FK compuestas a `producto`, `ubicacion`, `usuario`, `dispositivo` y `motivo` (opcional); `jornada_id` nulable **sin FK** hasta el 15 (mismo trato que `comando.jornada_id`, D8 del 04, deuda nominada); `origen_tipo` + `origen_id` genéricos sin FK (`03` §9). `costo_producto_mov` como `03` §7 más FK compuesta a `producto`. Índices de `03` §9 más `id` en el del kardex.
- **B.** Seguir `03` §9 al pie de la letra sin `dispositivo_id`.
- **C.** Como A, pero `jornada_id` se agrega recién en el 15.

**Qué implica.** A: trazabilidad directa del dispositivo, necesaria cuando lleguen las ventas de ruta; una deuda más para el 15. B: inconsistente con `cuenta_movimiento`. C: evita la deuda, pero el 15 migra un libro con datos.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D13 — Catálogo de tipos que acepta la base

- **A (recomendada).** `CHECK` de `stock_movimiento.tipo` con los nueve tipos de etapa 1 de STK-03 y de `costo_producto_mov.origen_tipo` con los cuatro de `03` §7; solo `STOCK_INICIAL` tiene comando. Mismo criterio que D12 del 08.
- **B.** Solo `STOCK_INICIAL`; cada change amplía su `CHECK`.

**Qué implica.** A: 11, 14, 18a, 19 y 24 no migran el libro. B: más migraciones, cada tipo con su dueño.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D14 — Fixtures compartidos de CST-11

**Contradicción encontrada.** `CLAUDE.md` §4 exige que todo cambio en una regla de cálculo actualice los fixtures compartidos, pero la spec vigente `sistema/calculo-compartido` ("Cada caso compartido es una prueba identificable en ambas suites") exige que **cada** caso de `shared/fixtures/calculo/` corra en pytest **y** en Vitest, y `02` §10.4 solo lista cálculos de venta como motor compartido. CST-02 ya resolvió esto con una implementación TypeScript (`frontend/src/domain/proveedores/costoBase.ts`) que la pantalla de costos usa para previsualizar.

- **A (recomendada).** `shared/fixtures/calculo/cst-11-costo-promedio.json` con el ejemplo de `01` §6.2 y bordes (stock previo cero y negativo, redondeo a 6 decimales `ROUND_HALF_UP` solo al final, egreso sin recálculo), ejecutado por las dos suites, igual que CST-02: `costeo/domain` en Python y `frontend/src/domain/costeo/costoPromedio.ts`, que la pantalla de stock inicial usa para **previsualizar** el promedio resultante a quien tenga `VER_COSTOS` (el servidor recalcula siempre, TR-10). Sin cambios de specs existentes.
- **B.** Los mismos casos en un archivo solo del backend (fuera de `shared/`), con pruebas unitarias; sin implementación TypeScript. Deja sin cumplir la letra de `CLAUDE.md` §4.
- **C.** Casos en `shared/` ejecutados solo por pytest, modificando `sistema/calculo-compartido` para admitir motores de una sola implementación (delta MODIFIED de esa spec).

**Qué implica.** A: cumple `CLAUDE.md` y la spec vigente, sigue el precedente de CST-02; el costo es una función TS más y una previsualización en pantalla. B: menos código, pero una regla de costo sin fixture compartido. C: cambia un contrato del arnés que protege al motor de venta (el riesgo que `02` §10.4 quiere evitar es justamente que una suite quede muda).

**Aprobada (2026-09-30).** El usuario eligió la opción A.

### D15 — Alcance del frontend

- **A (recomendada).** Sección "Stock" en el menú de `/admin`: ubicaciones (listado, alta, edición, activar/desactivar), stock por ubicación en cajas + unidades (CAT-08) con costo promedio solo con `VER_COSTOS`, kardex de producto y ubicación con filtro de período y "cargar más", y formulario de stock inicial por ubicación con varias líneas (con la previsualización del promedio de D14-A solo con `VER_COSTOS`), detrás de `<SiTienePermiso>` según D1-D3.
- **B.** Sin kardex en pantalla.
- **C.** Solo backend.

**Qué implica.** A: permite la verificación manual de `04` §2.1 punto 5 y la puesta en marcha a mano antes del 10. B/C: el punto 5 queda incompleto.

**Aprobada (2026-09-30).** El usuario eligió la opción A.

## Detalles derivados (no requieren decisión)

- **Redondeo del promedio.** CST-11 se evalúa con `Decimal` sin redondeos intermedios y el resultado se cuantiza una vez con `redondear_costo` (`ROUND_HALF_UP`, 6 decimales; TR-02, TR-03); el ejemplo `$1.133,333333` de `01` §6.2 lo fija. El `stock × promedio` usa el promedio almacenado.
- **Stock total.** `stock_total` cambia con **todo** movimiento del producto (también egresos); `costo_producto_mov` solo con los que recalculan o deben dejar historia (CST-13).
- **Consistencia.** `verificar_consistencia` compara, en SQL, `stock_saldo` con la suma del libro y `costo_producto.stock_total` con la suma de `stock_saldo` (`02` §7.6).
- **Stock negativo.** Ningún camino de este change deja saldo negativo: el único egreso (D4) exige saldo suficiente con el `UPDATE ... WHERE cantidad_base >= :q` de `02` §7.4.
- **Ubicaciones con toma.** Sin `jornada`, un stock inicial en un vehículo se acepta; STK-09 se aplica desde el 15.

## Risks / Trade-offs

- **Deadlocks entre operaciones futuras** → la función de `stock` es el único camino para bloquear y ordena; prueba de concurrencia con dos comandos que tocan los mismos productos en orden inverso.
- **D4-A agrega una regla y extiende CST-11** → ADR y propuesta de texto para `01`; si no se aprueba, se cae a B o C.
- **Respuesta que depende de `VER_COSTOS` (D3-A)** → pruebas con ADM y VEN; el tipo generado del OpenAPI marca los costos como opcionales.
- **Desborde de `numeric(18,6)`/`integer`** → el dominio acota entradas y el repositorio traduce el desborde a error de dominio.
- **Ratchets y listas declaradas** (`test_ratchet_permiso_por_ruta.py`, `COBERTURA_DE_AISLAMIENTO`, `TABLAS_DE_LIBRO_DECLARADAS`, INV-02) → trabajo mecánico en tareas.

## Migration Plan

Una revisión de Alembic de solo agregado: `ubicacion`, `costo_producto`, `costo_producto_mov`, `stock_saldo`, `stock_movimiento` con las restricciones de D7, D10, D12 y D13, índices de `03` §9/§16 y `GRANT` de ADR-020 (`SELECT, INSERT` en libros; `SELECT, INSERT, UPDATE` en saldos y en `ubicacion`). Sin permisos nuevos si D1-D3 quedan en A. `downgrade` elimina las cinco tablas; se prueba `upgrade → downgrade → upgrade` con datos. Rollback en producción: se pierde el stock inicial cargado; aceptable antes de operar.

ADRs a registrar (grupo final, ahora que D1-D15 están aprobadas): permisos de stock (D1-D3); reglas del stock inicial (D4-D6, con STK-10 propuesto para `01` §8.1 y la extensión de CST-11); ubicaciones (D7-D8); reparto de módulos, bloqueo y promedio nulo (D9-D10, con la aclaración de `03` §2.3 y ADR-002). Aclaraciones de `docs/03` §2.3, §7 y §9 según D7, D10 y D12.

## Open Questions

- Abierta, no bloqueante, nota para el change 10: si la importación del change 10 necesita fechar el stock inicial al día de corte, reabre el momento del movimiento (hoy `occurred_at` del sobre), como D5-C del 08.
