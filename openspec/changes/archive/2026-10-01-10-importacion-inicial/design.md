# Diseño técnico — 10-importacion-inicial

> **Estado: D0 a D14 APROBADAS el 2026-10-01 (opción A en todas; tarea 0.1).** Agregados posteriores a pedido del usuario: Operation-Id faltante → 400 `OPERATION_ID_REQUERIDO`; dependencia `python-multipart`; código `VALOR_OBLIGATORIO`; grupo 12 (validaciones faltantes en el alta por pantalla).

## Context

Ver `proposal.md` (Why). Ya existe todo lo que una fila necesita para escribirse: `proveedores/service.py::crear_proveedor` e `informar_costos` (06), `catalogo/service.py::crear_producto` (05), `clientes/service.py::crear_cliente` (07), `cuentas_corrientes/service.py::registrar_saldo_inicial` (08) y `stock/service.py::registrar_stock_inicial` (09). Todos reciben UUIDs, validan antes de escribir, no confirman y lanzan `DomainError` con código estable; `informar_costos` ya informa `fila` en `extension` (contrato P9 del 06). La sesión que el bus entrega al handler (`SesionSinCommit`) prohíbe `commit`/`rollback`/`close` pero deja pasar `begin_nested()` (savepoints). El bus guarda solo la huella del contenido, no el contenido (`03` §13).

Lo que `docs/` **no** resuelve o resuelve de forma contradictoria:

- `docs/` no dice si una importación es atómica ni cómo se lleva a comandos (una por archivo, por fila, por lote).
- No hay dependencia para leer `.xlsx` (ADR-001 no la prevé) y las celdas numéricas de Excel son binarias (riesgo INV-03).
- Las planillas no tienen UUIDs: hace falta decidir claves naturales y el formato de presentaciones.
- **Contradicción 1:** CST-05 (`01` §6.1) dice "importación masiva [de costos]: etapa 2"; `04` §6 pone costos en el 10 y el 06 le nominó la deuda.
- **Contradicción 2:** `00` §6.1 incluye "listas" en la importación inicial y `03` §13 tiene el tipo `PRECIOS`, pero las listas nacen en el 13 (que no depende del 10); y `03` §13 no tiene el tipo `COSTOS`.
- **Pregunta heredada del 09 (y D5-C del 08):** fechar el stock y los saldos al día de corte.
- `02` §5.1/§5.3 no listan el módulo `importacion` ni sus dependencias.

## Goals / Non-Goals

**Goals:** una sola vía de importación (un comando por archivo) que reutilice los servicios existentes sin cambiarlos; informe con **todos** los errores por fila; exactitud decimal de punta a punta; mismas reglas que la pantalla.

**Non-Goals:** modificar registros existentes; importar listas, categorías, marcas, ubicaciones o usuarios; procesamiento en segundo plano; vista previa separada (ver D1).

## Decisions

### D0 — Tamaño del change

**Qué hay que decidir.** `04` §2 fija entre medio día y tres días por change; seis importadores más infraestructura puede excederlo.

- **A (recomendada).** Un solo change en tres lotes de apply (infraestructura + proveedores; maestros; puesta en marcha + pantalla). La infraestructura (lectura, conversión, todo o nada, informe) es el grueso; cada importador es un adaptador fino sobre un servicio existente.
- **B.** Dividir en `10a-importacion-maestros` y `10b-importacion-puesta-en-marcha` (actualiza `04` §4).

**Ejemplo.** Con A, el lote 1 ya deja importar proveedores de punta a punta; con B, 10b recién empieza cuando 10a se archiva.

**Aprobada 2026-10-01: opción A (recomendada).**

### D1 — Atomicidad de una importación · ADR pendiente

**Qué hay que decidir.** Qué pasa cuando algunas filas fallan.

- **A (recomendada). Todo o nada, con informe completo.** Un comando `IMPORTACION_REGISTRAR` por archivo. El handler procesa cada fila dentro de un savepoint (`begin_nested`), llamando al servicio; si la fila falla, revierte solo su savepoint, anota el error y sigue. Al terminar, si hubo algún error lanza `IMPORTACION_CON_ERRORES` (422, `extension.errores`) y el bus revierte **toda** la transacción, incluida la reserva de idempotencia. Sin errores, inserta la fila de `importacion` y el bus confirma. Cumple INV-01 al nivel de archivo y se corrige reenviando el archivo entero.
- **B. Parcial.** Mismo mecanismo de savepoints, pero las filas buenas se confirman y la fila de `importacion` guarda `filas_ok`, `filas_error` y `errores` (las columnas de `03` §13 lo sugieren). Corregir obliga a reenviar solo las filas fallidas (reenviar todo duplica o choca con duplicados).
- **C. Un comando por fila desde el navegador**, con los endpoints existentes y un `operation_id` por fila; el informe lo arma la pantalla.

**Qué implica.** A: un archivo es una operación; sin estados intermedios; la falla de una fila de 2.000 obliga a reenviar todo (barato: no hubo efectos). Savepoints dentro del handler no son un `commit` (no violan `CLAUDE.md` §4), pero conviene dejarlo escrito en el ADR. B: más amigable con archivos enormes, pero deja la organización a medio cargar y complica el reenvío. C: casi sin backend, pero contradice "la importación corre en el servidor" (`04` §6), no tiene registro de importación y la lectura del archivo queda en el cliente.

**Ejemplo.** 300 clientes, filas 45 y 210 con DNI de 6 dígitos. A: 422 con dos errores, cero clientes creados; se corrige y se reenvía el archivo con otro `Operation-Id`. B: 298 creados; hay que armar un archivo con las dos filas corregidas.

**Aprobada 2026-10-01: opción A (recomendada).**

### D2 — Dónde y qué archivos se leen · ADR pendiente (amplía ADR-001)

- **A (recomendada). En el servidor: CSV y `.xlsx`.** `POST /api/v1/importaciones/{tipo}` multipart. La API lee el archivo, lo convierte en filas de texto (`{fila, valores}`) y ese JSON es el `contenido` del sobre (la huella es la de las filas, así que el mismo archivo da la misma huella). CSV: UTF-8 (con o sin BOM) y, si no decodifica, Windows-1252; separador `,` o `;` detectado en el encabezado (Excel en español guarda con `;`). `.xlsx`: primera hoja, con un lector propio de la biblioteca estándar (`zipfile` + `xml.etree`) que toma el texto literal de cada celda (D3), sin dependencia nueva; si se prefiere una biblioteca (`openpyxl`), es dependencia nueva y ADR.
- **B. En el navegador** con una biblioteca JS de planillas; se envía JSON. Dependencia nueva en el front y los números de Excel llegan como `number` de JS (INV-03).
- **C. Solo CSV en la etapa 1**; desde Excel, "Guardar como CSV".

**Ejemplo.** Un `clientes.xlsx` de 300 filas sube tal cual con A; con C el usuario debe exportarlo a CSV antes.

**Aprobada 2026-10-01: opción A (recomendada).**

### D3 — Celdas numéricas de Excel sin punto flotante

- **A (recomendada).** Tomar el texto literal guardado en el XML de la celda (`<v>1239.669421</v>`) y pasarlo como cadena al conversor decimal; nunca `float`. Un resultado de fórmula con decimales espurios se rechaza por la regla de decimales del destino, sin redondear.
- **B.** Leer el `float` y convertir con `Decimal(repr(x))`: casi siempre coincide con lo tipeado, pero pasa por binario (contradice INV-03).
- **C.** Exigir celdas con formato texto en columnas de dinero y cantidad (rechazar celdas numéricas).

**Ejemplo.** Celda tipeada `1239,669421` → A: `"1239.669421"`. Celda con fórmula `=18000/1,21/12` guardada como `1239.6694214876034` → A: `COSTO_INVALIDO` (más de 6 decimales); B la aceptaría o la redondearía según el destino.

**Aprobada 2026-10-01: opción A (recomendada).**

### D4 — Claves naturales

**Qué hay que decidir.** Cómo una fila nombra lo que referencia.

- **A (recomendada).** Categoría y marca por nombre; alícuota por porcentaje (`21`, `10,5`, `0`); proveedor por **nombre** (único y obligatorio; el CUIT es opcional); producto por código; presentación por nombre dentro del producto; cliente por código o, si no, por documento (dígitos); ubicación por nombre. Comparación sin mayúsculas ni espacios al borde; más de una coincidencia → `REFERENCIA_AMBIGUA`; ninguna en la organización → `REFERENCIA_NO_ENCONTRADA` (nunca 404: es un error de fila y no revela otras organizaciones). Las referencias deben existir: **no** se crean categorías ni marcas al vuelo.
- **B.** Igual que A, pero se crean al vuelo las categorías y marcas que no existan.
- **C.** Columnas con UUID (requiere exportar ids primero).

**Ejemplo.** Fila de producto con `categoria` = "Vinoss": A → `REFERENCIA_NO_ENCONTRADA`; B → crea una categoría "Vinoss" que después hay que desactivar a mano.

**Aprobada 2026-10-01: opción A (recomendada).**

### D5 — Presentaciones en la planilla de productos

- **A (recomendada).** Una fila por presentación, agrupadas por `codigo`, con los datos del producto repetidos: `codigo, nombre, categoria, marca, proveedor, unidad_base, alicuota, presentacion, unidades_base, usar_en_venta, usar_en_compra, es_referencia`. Datos de producto distintos entre filas del mismo código → `PRODUCTO_INCONSISTENTE`.
- **B.** Una fila por producto con columnas fijas para la referencia y una unidad suelta opcional (`referencia_nombre, referencia_unidades, agregar_unidad_suelta`). No cubre presentaciones de compra distintas.
- **C.** Dos planillas (productos y presentaciones).

**Ejemplo (A).** `VA-750, Vino A, Vinos, , Bodega Sur, botella, 21, Caja x6, 6, S, S, S` y `VA-750, Vino A, Vinos, , Bodega Sur, botella, 21, Botella, 1, S, N, N`.

**Aprobada 2026-10-01: opción A (recomendada).**

### D6 — Solo altas; código de cliente obligatorio en la planilla

- **A (recomendada).** Solo altas: una clave que ya existe da el error de duplicado de la entidad; duplicados dentro del archivo dan `FILA_DUPLICADA`. En la planilla de clientes, `codigo` es obligatorio (CLI-01 lo deja opcional en la pantalla), para poder referenciarlos en saldos y para que una reimportación no duplique clientes.
- **B.** Solo altas, `codigo` opcional como en la pantalla: un cliente sin código ni documento se puede crear dos veces y no se le puede cargar saldo por planilla.
- **C.** Alta o modificación (upsert) por clave natural.

**Ejemplo.** Archivo importado dos veces por error con distinto `Operation-Id`: A → la segunda falla entera con `CODIGO_DUPLICADO`; B → los clientes sin código quedan duplicados.

**Aprobada 2026-10-01: opción A (recomendada).** Restricción de negocio confirmada por el usuario.

### D7 — Fecha de corte del stock y los saldos iniciales · ADR pendiente si se elige B

- **A (recomendada).** Sin fecha de corte: el momento es el `occurred_at` del sobre (el momento de la importación), igual que la pantalla (ADR-034, ADR-037 punto 5). Como STK-10 y CC-08 impiden cargar después de la primera operación, nada operativo queda antes.
- **B.** Campo opcional `fecha_corte` (fecha de negocio, no futura) en las importaciones de stock y saldos; los movimientos toman como `occurred_at` el fin de ese día en la zona de la organización (TR-04). Reabre ADR-037 punto 5 y D5-C del 08 (también para la pantalla, para no tener dos criterios).

**Ejemplo.** Se cierra el papel el 30/09 y se importa el 03/10. A: el estado de cuenta muestra el saldo inicial el 03/10. B: lo muestra el 30/09 23:59 (Mendoza) y un filtro "septiembre" lo incluye.

**Aprobada 2026-10-01: opción A (recomendada).**

### D8 — Costos pese a CST-05 · requiere aclarar `01`

- **A (recomendada).** Incluir la importación de costos (`04` §6 es posterior y el 06 nominó la deuda) y proponer aclarar CST-05: "importación inicial: etapa 1 (change 10); importación masiva recurrente: etapa 2". Cada fila usa `informar_costos` (lote de una fila, con su `fila` traducida).
- **B.** Excluir costos (CST-05 literal) y mover la deuda del 06 a la etapa 2.

**Ejemplo.** Con A, 150 costos de "Bodega Sur" entran en un archivo; con B se cargan desde la pantalla de costos en lotes.

**Aprobada 2026-10-01: opción A (recomendada).**

### D9 — Tipos de importación y listas de precios

- **A (recomendada).** `CHECK` de `importacion.tipo` con los seis de `03` §13 más `COSTOS` (`PRODUCTOS, CLIENTES, PROVEEDORES, PRECIOS, COSTOS, STOCK_INICIAL, SALDOS_INICIALES`), como el precedente de declarar el catálogo completo de la etapa (ADR-034 punto 7, D13 del 09). `PRECIOS` no tiene importador hasta el 13 (deuda nominada) y la API lo rechaza con 422.
- **B.** Solo los seis implementados; el 13 agrega `PRECIOS` con su migración.

**Ejemplo.** `POST /importaciones/PRECIOS` → A y B: 422 `TIPO_IMPORTACION_INVALIDO` en este change.

**Aprobada 2026-10-01: opción A (recomendada).**

### D10 — Módulo y dependencias · ADR pendiente (actualiza `02` §5)

- **A (recomendada).** Módulo `importacion` (ya previsto en `03` §3) que orquesta: `importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad`, solo por `service.py`; nadie depende de él. Se agrega a `02` §5.1/§5.3 y a import-linter.
- **B.** Cada módulo expone su propio importador y un lector común vive en `core/`; la API despacha por tipo.

**Ejemplo.** Con A, el lector, el todo-o-nada y el informe están en un solo lugar y probados una vez; con B se repiten seis veces.

**Aprobada 2026-10-01: opción A (recomendada).**

### D11 — Límites del archivo y columnas

- **A (recomendada).** Máximo 2.000 filas de datos y 5 MB por archivo; columna desconocida, faltante o repetida rechaza el archivo (`COLUMNAS_INVALIDAS`); orden libre; filas vacías se ignoran; plantillas CSV con solo el encabezado.
- **B.** 5.000 filas; columnas desconocidas se ignoran.

**Ejemplo.** Una columna `observaciones` en clientes: A rechaza el archivo nombrándola (evita creer que se cargó); B la ignora en silencio.

**Aprobada 2026-10-01: opción A (recomendada).**

### D12 — Formato de números escritos como texto

Aplica al CSV y a las celdas de texto de Excel (las celdas numéricas se leen por D3).

- **A (recomendada).** Coma decimal, sin separador de miles; un punto se rechaza (`NUMERO_INVALIDO`). Es lo que Excel en español escribe al guardar CSV y evita la ambigüedad de `1.500`.
- **B.** Coma o punto decimal, sin miles: cómodo, pero `1.500` (mil quinientos, en uso local) se leería 1,5 en silencio.
- **C.** Formato argentino completo (coma decimal, punto de miles opcional): `1.500` es 1500, pero `1.5` también se leería 15.

**Ejemplo.** `18000,50` → A, B y C: `"18000.50"`. `1.500` como importe de saldo → A: `NUMERO_INVALIDO` en la fila; B: `"1.50"` (error silencioso de mil veces); C: `"1500.00"`.

**Aprobada 2026-10-01: opción A (recomendada).**

### D13 — Cantidad y costo del stock inicial en la planilla

- **A (recomendada).** `cantidad_base` entera y `costo_unitario` por unidad base, el mismo contrato que `STOCK_INICIAL_REGISTRAR` (ADR-037 punto 5): sin conversiones ni redondeos, sin fixtures nuevos.
- **B.** `cajas` + `unidades` (convertidas con aritmética entera por la presentación de referencia, CAT-08) y costo por presentación de referencia dividido por sus unidades y redondeado a 6 decimales: regla de cálculo nueva, exige fixture compartido y ADR.

**Ejemplo.** Vino A caja x6, 10 cajas y 2 botellas a $6.000 la caja. A: `cantidad_base` 62, `costo_unitario` 1000. B: `cajas` 10, `unidades` 2, `costo_referencia` 6000 → 62 a `"1000.000000"`.

**Aprobada 2026-10-01: opción A (recomendada).**

### D14 — Registro `importacion`

- **A (recomendada).** Columnas de `03` §13 más columnas de operación (`operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at`, `03` §2.3) con FK compuestas. Con D1-A solo se guardan importaciones exitosas: `estado` = `CONFIRMADA`, `filas_error` = 0, `errores` = `[]` (columnas listas para un modo parcial futuro). Solo inserción (`GRANT SELECT, INSERT`).
- **B.** Además, guardar los intentos rechazados en una transacción aparte (como la cuarentena) para tener rastro de los fallidos.

**Ejemplo.** Tras un intento fallido y uno exitoso: A muestra uno en el historial (el fallido queda en el log); B muestra los dos.

**Aprobada 2026-10-01: opción A (recomendada).**

## Detalles derivados (no requieren decisión)

- **Permiso:** `IMPORTAR_DATOS` para todos los tipos y para plantillas e historial (`01` §19: "Importaciones y puesta en marcha"; ADR-033, ADR-036). No se exige además el permiso de la entidad.
- **Auditoría:** una por comando, la del bus (ADR-022).
- **Orden de ejecución:** proveedores, productos y clientes en orden de archivo; costos ordenados por producto; stock por (producto, ubicación) y saldos por (`cuenta_tipo`, entidad) ascendentes, con orden **estable** para que una corrección negativa siga a su positivo (`02` §7.3).
- **Errores:** cada `DomainError` de un servicio se traduce a `{fila, columna, codigo, mensaje}` con una tabla código→columna en `importacion/domain`; una violación de unicidad dentro de un savepoint se traduce al código de duplicado de su entidad.
- **Contenido del comando:** `{tipo, archivo_nombre, filas: [{fila, valores: {columna: texto}}]}`; la conversión a decimales y enteros ocurre en `importacion/domain` (funciones puras, Hypothesis).
- **Reintentos transitorios** del bus re-ejecutan la importación entera: sin efectos duplicados por la atomicidad.

## Risks / Trade-offs

- [Transacción larga con muchos bloqueos] → límite de filas (D11), orden de bloqueo estable, sin otra operación esperable durante la puesta en marcha; prueba de concurrencia.
- [Excel guarda CSV en Windows-1252 con `;`] → detección de codificación y separador (D2).
- [Fechas de Excel como número de serie] → convertir solo si la celda tiene formato de fecha; si no, exigir texto (`FECHA_INVALIDA`).
- [Datos reales que no entran en el modelo (`04` §14)] → el informe por fila los muestra todos; si son masivos, se para y se registra ADR.
- [Savepoints por fila] → costo medido con 2.000 filas en la prueba de integración.

## Migration Plan

Una revisión de Alembic crea `importacion` con FK compuestas, `CHECK` de `tipo` y `estado`, índice `(organizacion_id, registered_at DESC, id)` para el historial y `GRANT SELECT, INSERT`. `downgrade` la elimina. No toca tablas existentes ni datos.

## Open Questions

Ninguna diferible: todas las dudas son D0 a D14 y bloquean la implementación hasta la tarea 0.1.
