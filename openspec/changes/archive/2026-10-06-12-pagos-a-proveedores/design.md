# Diseño técnico — 12-pagos-a-proveedores

> **Estado: D0 a D11 APROBADAS con la opción A el 2026-10-03 (tarea 0.1), incluidos los nombres de los motivos de D1.** Las specs y las tareas están escritas con la opción A de cada decisión. Cada decisión indica si es **de negocio** o **técnica**. Las que cambian reglas se documentan en **ADR-046** (precisa ADR-043), que se redacta durante el apply en estado *Propuesto*. Dominio de gobernanza alto (pagos y cuentas corrientes): no se escribe código hasta la aprobación.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Tablas** `pago_proveedor` y `pago_proveedor_medio` (migración `c0d1e2f3a4b5`, change 11): `origen` (`COMPRA`, `INDEPENDIENTE`) con `CHECK` que exige `compra_id` nulo en un pago independiente, `estado` (`CONFIRMADA`, `ANULADA`), `anulado_en`, `anulado_por_id`, `anulacion_motivo_id` nulable, columnas de operación, FK compuestas, índice único parcial por `compra_id`. `app_runtime` tiene `SELECT, INSERT` y `UPDATE` solo sobre `estado, anulado_en, anulado_por_id, anulacion_motivo_id`; nunca `DELETE` (INV-05).
- **Modelos** `PagoProveedor` y `PagoProveedorMedio` en `proveedores/models.py`.
- **Dominio** `proveedores/domain/compras.py`: `MedioDeEntrada`, `validar_pago(condicion, total_factura, medios)` (importe positivo con 2 decimales por medio, suma exacta, referencia obligatoria) y los errores `MEDIOS_NO_SUMAN_IMPORTE`, `REFERENCIA_OBLIGATORIA`, `MEDIO_PAGO_INACTIVO`, `IMPORTE_INVALIDO`, `FECHA_INVALIDA`, `MOTIVO_INVALIDO`.
- **Servicio** `proveedores/service.py`: `_resolver_medios` (medio de la organización, activo, con índice del medio en el error), `_validar_motivo_de_anulacion`, y dentro de `confirmar_compra` y `anular_compra` el registro de `PAGO` y `ANULACION_PAGO` con `origen_tipo`/`origen_id` del pago.
- **Repositorio** `insertar_pago_de_compra`, `obtener_pago_de_compra` (`FOR UPDATE`), `marcar_pago_anulado`, `listar_medios_de_pago`.
- **Libro** `cuentas_corrientes/service.py`: `bloquear_saldo`, `registrar_movimiento`, `obtener_saldo`; el catálogo ya admite `PAGO` (reduce) y `ANULACION_PAGO` (aumenta) para proveedores (ADR-034 punto 5). El estado de cuenta ya devuelve `origen_tipo` y `origen_id`, y la pantalla ya rotula "Pago" y "Anulación de pago".
- **Configuración** `GET /configuracion/medios-pago` y `GET /configuracion/motivos?ambito=` (cualquier sesión, ADR-043).
- **Permisos** `REGISTRAR_PAGO_PROVEEDOR` y `ANULAR_PAGO_PROVEEDOR` ya están en el catálogo y en las plantillas ADM y GES (`identidad/domain/permisos.py`, `01` §19).
- **Bus** audita cada comando con su `operation_id` (ADR-022); `requiere_algun_permiso` y `requiere_sesion` existen (ADR-043 punto 12).
- **Frontend** `areas/admin/compras/` (formulario con medios de contado y faltante), `features/compras/useOperationIdPorContenido.ts`, `areas/admin/cuentas-corrientes/`.

Lo que `docs/` **no** resuelve o resuelve de forma contradictoria:

- **Deuda (a) del change 11 (`04` §7):** `motivo.ambito` (`03` §4) tiene `ANULACION_COBRANZA` pero ninguno para pagos a proveedor, y `anulacion_motivo_id` es nulable aunque PAG-03 exige motivo. → D1, D9.
- **Deuda (b):** ADR-043 deja abierta la pregunta de si un pago de origen `COMPRA` se anula por separado de su compra. → D2.
- **Deuda (c):** nada dice si un pago puede superar la deuda ni cómo se compensa el saldo a nuestro favor. → D3.
- **PAG-01 es más corta que COB-01/COB-02:** no menciona referencia obligatoria por medio, origen ni observación; ADR-043 solo lo resolvió para el pago de contado. → D4, D5, D6.
- **PAG-03 no dice el efecto de la anulación** (el movimiento `ANULACION_PAGO` sale de CC-03) ni qué pasa con un proveedor inactivo. → D5.
- **`01` §19 no tiene permiso de lectura de pagos** y el saldo del proveedor hoy solo se lee con `GESTIONAR_PROVEEDORES` (estado de cuenta, ADR-033). → D7, D8.
- **Roadmap:** la fila del 12 dice "saldo de proveedor", pero el saldo ya existe desde el 08 (ficha y estado de cuenta). → D8.
- **Asimetría de modelo:** `03` §12 modela la anulación de una cobranza en una tabla aparte (`cobranza_anulacion`); el pago la lleva en columnas propias (change 11). → D9.
- **`02` §7.3** empieza el orden global en `saldo_cuenta`; ADR-043 punto 15 ya puso la fila de la operación (`compra FOR UPDATE`) antes. Falta decir dónde entra la fila del pago. → D10.
- **Nombre del estado:** `03` §6 y la base usan `ANULADA`; ADR-043 punto 3 y la spec `proveedores/anulacion-de-compras` escribían "`ANULADO`". No es una decisión: este change usa el valor real, `ANULADA`. Ambos textos se corrigieron el 2026-10-03, antes del apply.

Regla heredada que se vuelve visible (no es decisión): desde el primer `PAGO`, la cuenta del proveedor ya no admite `SALDO_INICIAL` (`CUENTA_CON_OPERACIONES`, CC-08, ADR-034).

La condición frente al IVA (CST-06, ADR-045) no cambia nada en un pago: se paga contra el saldo, que ya se formó con el total de factura de cada compra (ADR-043 punto 1). Para la distribuidora monotributista, los ejemplos usan los importes pagados ($152.460 es el total de la compra del criterio 2 con el IVA como costo).

## Goals / Non-Goals

**Goals:** un pago independiente y su anulación como operaciones atómicas e idempotentes sobre las tablas del change 11; una sola función de dominio para validar medios, usada por la compra de contado y por el pago; cero regresiones en compras.

**Non-Goals:** imputación de pagos a compras; tipos de movimiento nuevos en el libro (CC-03 queda como está); reembolsos de proveedor como operación propia; orden de pago imprimible; cambios en `cuentas_corrientes` más allá de leer el saldo.

## Decisions

### D0 — Tamaño del change · técnica

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** El alcance son dos comandos, dos lecturas, una migración chica y cuatro pantallas. Cabe en `04` §2 (hasta tres días).

- **A (recomendada).** Un solo change en tres lotes de apply: (1) migración, dominio y `PAGO_PROVEEDOR_REGISTRAR` de punta a punta por API; (2) anulación, consultas y saldo; (3) pantallas, concurrencia, cobertura, docs y verificación manual.
- **B.** Dividir en `12a-pagos-a-proveedores` (registro) y `12b-anulacion-de-pagos`.

**Ejemplo.** Con A, al cerrar el lote 1 ya se puede pagar por API $100.000 de una deuda de $153.720 y ver el saldo en $53.720; con B, un pago mal cargado no se puede anular hasta archivar 12a.

### D1 — Motivo de anulación de un pago · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).** Deuda (a) del change 11.

**Qué hay que decidir.** PAG-03 exige motivo, pero no existe un ámbito de motivo para pagos a proveedor.

- **A (recomendada). Ámbito nuevo `ANULACION_PAGO`** en la lista cerrada de `motivo.ambito`, con tres motivos sembrados en organizaciones nuevas y, por migración idempotente, en las existentes que no tengan ninguno: **"Error de carga", "Pago rechazado o devuelto" y "Otro"** (los nombres los aprueba el usuario). `PAGO_PROVEEDOR_ANULAR` exige un motivo activo de ese ámbito (`MOTIVO_INVALIDO` si no). Un pago anulado junto con su compra (`COMPRA_ANULAR` con `devuelve_pago = true`) sigue llevando el motivo de la compra, como hoy.
- **B. Reutilizar los motivos de `ANULACION_COMPRA`.** Sin tocar el `CHECK`, pero "Devolución al proveedor" no describe por qué se anula un pago, y un cheque rechazado no tiene dónde caer.
- **C. Texto libre**, sin catálogo. Contradice `03` §6 (`anulacion_motivo_id` es FK a `motivo`) y TR-09.

**Ejemplo.** Se pagaron $52.460 a Bodega Sur por transferencia y el banco la rechazó. A: se anula con "Pago rechazado o devuelto" y la cuenta vuelve a deber $52.460. B: hay que elegir entre "Error de carga", "Devolución al proveedor" u "Otro".

### D2 — ¿Se anula por separado el pago de una compra de contado? · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).** Deuda (b) del change 11.

**Qué hay que decidir.** Hoy un pago de origen `COMPRA` solo se anula con `COMPRA_ANULAR` y `devuelve_pago = true`.

- **A (recomendada). Solo si la compra ya está anulada.** Mientras la compra está `CONFIRMADA`, `PAGO_PROVEEDOR_ANULAR` sobre su pago se rechaza con `PAGO_DE_COMPRA_VIGENTE` (409): una compra de contado vigente siempre tiene su pago vigente (CMP-03). Si la compra se anuló con `devuelve_pago = false` y el proveedor devuelve el dinero después, el pago se anula por separado y el saldo a nuestro favor desaparece.
- **B. Siempre.** El pago de contado se anula aunque la compra siga vigente; la compra queda como deuda. Sirve para corregir un medio mal cargado sin revertir stock, pero deja compras "de contado" sin pago.
- **C. Nunca.** El pago de una compra solo se anula con la compra. El saldo a favor de una anulación sin devolución solo se consume con compras futuras.

**Ejemplo.** Compra de contado de $152.460 a Bodega Sur, anulada el lunes con `devuelve_pago = false`: saldo −$152.460 ("Saldo a nuestro favor"). El viernes el proveedor devuelve el efectivo. A y B: se anula el pago, `ANULACION_PAGO` $152.460, saldo $0. C: el sistema sigue diciendo que Bodega Sur nos debe $152.460 hasta la próxima compra. Con B, además, alguien podría anular el pago de una compra de contado vigente y dejarla debiendo $152.460.

### D3 — Pago mayor que la deuda y compensación del saldo a nuestro favor · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).** Deuda (c) del change 11.

**Qué hay que decidir.** Si un pago puede dejar saldo negativo y cómo se "usa" ese saldo.

- **A (recomendada). Se admite cualquier importe mayor que cero; el saldo a favor se compensa solo, por el saldo general.** PAG-02 no imputa pagos a compras: la próxima compra **a crédito** aumenta el saldo y absorbe el saldo a favor, sin operación nueva ni tipos de movimiento nuevos (CC-03 intacto). En pantalla: el alta de pago muestra "Le debemos" y el saldo resultante, y si este queda a nuestro favor pide una confirmación explícita; el alta de compra avisa "Este proveedor tiene saldo a nuestro favor de $X: cargada a crédito, se descuenta de ese saldo". Si el proveedor devuelve dinero, se anula el pago (D2) y se registra el correcto.
- **B. Se rechaza un pago mayor que la deuda** (`PAGO_SUPERA_DEUDA`). No admite anticipos ni pagos antes de cargar la factura.
- **C. Se admite con observación** (`ACEPTADO_CON_OBSERVACIONES`, código nuevo en SYN-07) para revisión posterior. Agrega una observación a un caso que es habitual (anticipo).

**Ejemplo.** Le debemos $153.720 a Bodega Sur y se le transfieren $160.000. A: tras confirmar el aviso, saldo −$6.280 ("Saldo a nuestro favor $6.280"); la próxima compra a crédito de $100.000 deja el saldo en $93.720. B: se rechaza; hay que pagar $153.720 o menos. C: se acepta y queda una observación pendiente por $6.280.

### D4 — Fecha del pago y momento del movimiento · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** PAG-01 pide "fecha" pero no dice cuál ni cómo se ordena en la cuenta. ADR-043 punto 6 lo resolvió solo para compras.

- **A (recomendada). Igual que la compra.** `fecha` es la del pago real (la del recibo o la transferencia): obligatoria y no posterior a la fecha de negocio de hoy en la zona de la organización (`FECHA_INVALIDA`), sin límite hacia atrás. El movimiento `PAGO` usa el `occurred_at` del comando; la `fecha` se muestra en el listado y en el detalle.
- **B.** El movimiento se fecha al inicio del día de `fecha`: el estado de cuenta queda en orden de recibo, pero un pago cargado tarde aparece "antes" de movimientos ya consultados y cambia saldos acumulados históricos.

**Ejemplo.** Transferencia de $100.000 hecha el 28/09 y cargada el 01/10. A: el estado de cuenta la muestra el 01/10 y el detalle dice "Fecha del pago: 28/09". B: aparece el 28/09, antes de una compra registrada el 30/09, y el acumulado de esa compra cambia respecto de lo que se vio el 30/09.

### D5 — Pagar a un proveedor inactivo · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** Una compra a un proveedor inactivo se rechaza (`PROVEEDOR_INACTIVO`); `docs/` no dice nada del pago.

- **A (recomendada). Se admite registrar y anular.** La deuda existe aunque el proveedor esté dado de baja (mismo criterio que el saldo inicial, ADR-034 punto 3). El selector de la pantalla ofrece los activos; a un inactivo se le paga desde su cuenta corriente.
- **B. Registrar se rechaza con `PROVEEDOR_INACTIVO`**; anular se admite. Para pagar hay que reactivar al proveedor.

**Ejemplo.** Bodega Norte se dio de baja debiéndole $80.000. A: se registra el pago de $80.000 y el saldo queda en $0. B: hay que reactivarla, pagar y volver a darla de baja.

### D6 — Contenido del pago: medios y observación · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** Qué viaja en `PAGO_PROVEEDOR_REGISTRAR` más allá de PAG-01.

- **A (recomendada).** `importe` explícito (mayor que cero, 2 decimales, `IMPORTE_INVALIDO`) y de 1 a 20 medios (`MEDIOS_INVALIDOS` fuera de ese rango), cada uno con medio activo, importe positivo de 2 decimales y referencia donde el medio la exige (mismas reglas y códigos que el contado, ADR-043 punto 2). El mismo medio puede repetirse (dos cheques). **Observación opcional** de hasta 500 caracteres, guardada recortada (columna nueva nulable, D9): como no hay imputación, es donde se anota "paga facturas 0001-123 y 0001-124".
- **B.** Igual, sin observación (sin columna nueva).
- **C.** Sin `importe`: el importe es la suma de los medios. INV-08 se cumple por construcción, pero PAG-01 pide registrar el importe y verificarlo contra los medios, y se pierde la detección del error de tipeo.

**Ejemplo.** Pago de $152.460: $100.000 en efectivo y $52.460 por transferencia con referencia "0042". A y B: si se tipea $52.640 en la transferencia, los medios suman $152.640 y se rechaza con `MEDIOS_NO_SUMAN_IMPORTE`. C: se acepta un pago de $152.640 y la cuenta queda $180 a nuestro favor sin que nadie lo note.

### D7 — Permisos de lectura y lecturas de apoyo · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** `01` §19 solo cubre registrar y anular.

- **A (recomendada). Sin permisos nuevos, mismo criterio que compras (ADR-043 puntos 10 y 11).** Registrar: `REGISTRAR_PAGO_PROVEEDOR`. Anular: `ANULAR_PAGO_PROVEEDOR`. Listado y detalle de pagos: cualquiera de los dos. `GET /proveedores/opciones` abre **solo su lectura** también a `REGISTRAR_PAGO_PROVEEDOR`. Medios y motivos: cualquier sesión, como hoy.
- **B.** Además, `GESTIONAR_PROVEEDORES` lee pagos, porque ya ve los movimientos `PAGO` en el estado de cuenta.

**Ejemplo.** Un rol "Tesorería" con solo `REGISTRAR_PAGO_PROVEEDOR` paga $100.000 a Bodega Sur. A: elige al proveedor, paga y ve el listado, sin poder editar proveedores. Un usuario con solo `GESTIONAR_PROVEEDORES` ve en la cuenta el movimiento "Pago $100.000" pero no el enlace a su detalle. B: ese usuario también abre el detalle con los medios.

### D8 — Qué entrega "saldo de proveedor" · de negocio · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** La fila del 12 en `04` §7 dice "saldo de proveedor"; el saldo y el estado de cuenta ya existen (08) y el reporte de saldos es del 26.

- **A (recomendada). Una lectura liviana del saldo:** `GET /api/v1/proveedores/{id}/saldo` devuelve el saldo actual (string, SQL sobre `saldo_cuenta`), con `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA`. La usan el alta de pago (saldo actual y resultante) y el aviso del alta de compra (D3). Sin columna de saldo en el listado de proveedores: eso es el reporte del 26.
- **B.** Además, columna "Saldo" en el listado de proveedores.
- **C.** Nada nuevo: el saldo se sigue leyendo del estado de cuenta, que exige `GESTIONAR_PROVEEDORES`.

**Ejemplo.** El rol "Tesorería" abre "Nuevo pago" para Bodega Sur. A: ve "Le debemos $153.720" y, al tipear $100.000, "Saldo después del pago: $53.720". C: no ve ningún saldo y paga a ciegas. B: además ve en el listado los ~10 proveedores con su saldo.

### D9 — Modelo de datos y migración · técnica · ADR-046

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** Cuánto se toca de lo que creó el change 11.

- **A (recomendada). Una revisión de Alembic, sin mover datos existentes:**
  1. `ck_motivo__ambito` suma `ANULACION_PAGO` (D1) y siembra idempotente de sus motivos.
  2. `pago_proveedor.observacion text` nulable (D6). No entra en el `GRANT UPDATE`: es inmutable.
  3. `ck_pago_proveedor__anulacion_coherente` pasa a exigir "anulada ⇔ momento, usuario **y motivo**", como `compra`. La migración verifica antes que ningún pago `ANULADA` tenga el motivo nulo (el change 11 siempre lo escribe) y falla con un mensaje claro si lo encuentra.
  4. Índices de listado `(organizacion_id, fecha DESC, id DESC)` y `(organizacion_id, proveedor_id, fecha DESC, id DESC)`.
  `downgrade` quita índices, columna y `CHECK` estricto, pone en nulo el motivo de los pagos anulados con un motivo `ANULACION_PAGO`, borra esos motivos y restaura el `CHECK` de ámbitos: pierde motivos y observaciones por diseño, y una prueba lo deja escrito.
- **B. Mínima:** solo el punto 1. Sin observación, sin `CHECK` estricto (PAG-03 queda garantizada solo por el servicio) y sin índices.
- **C. Tabla `pago_proveedor_anulacion`** simétrica a `cobranza_anulacion` (`03` §12). Obliga a migrar las anulaciones que el change 11 ya guarda en columnas, contra "sin migrar lo existente" (`04` §7).

**Ejemplo.** Pago de $52.460 anulado. A: la base rechaza una fila `ANULADA` sin motivo aunque un defecto del servicio lo intente. B: la fila entra y el reporte de pagos anulados muestra uno sin motivo.

### D10 — Bloqueos, concurrencia e idempotencia · técnica · ADR-046 (precisa ADR-043 punto 15 y `02` §7.3)

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** Dónde entra la fila del pago en el orden de bloqueo.

- **A (recomendada). La fila de la operación antes del orden global.** `PAGO_PROVEEDOR_REGISTRAR`: `bloquear_saldo` del proveedor (nivel 1; una entidad ajena o inexistente da 404 ahí) y luego inserta pago, medios y `PAGO`. `PAGO_PROVEEDOR_ANULAR`: lee el pago sin bloquear; si es de origen `COMPRA` toma **primero** `compra FOR UPDATE`; luego `pago FOR UPDATE`, revalida estado (`PAGO_YA_ANULADO`, 409) y D2, y recién después `bloquear_saldo`. Es el mismo orden que ya usa `COMPRA_ANULAR` (compra → pago → `saldo_cuenta`), así que no hay interbloqueo entre anular una compra y anular su pago.
- **B. `saldo_cuenta` primero**, literal de `02` §7.3, y después las filas de compra y pago. Invierte el orden que ya usa `COMPRA_ANULAR` y obligaría a cambiarlo.

**Ejemplo.** Dos usuarios, al mismo tiempo: uno anula la compra de contado de $152.460 con `devuelve_pago = true` y otro anula su pago. A: ambos piden primero la fila de la compra; uno espera, y al entrar ve el pago ya `ANULADA` y recibe `PAGO_YA_ANULADO`: una sola `ANULACION_PAGO` de $152.460. Con un orden mezclado, la base podría abortar a uno por interbloqueo.

Idempotencia: la reserva del bus (INV-06) cubre los dos comandos; reenviar el mismo contenido devuelve el resultado original y uno distinto da `COMANDO_INCONSISTENTE`.

### D11 — Alcance de las pantallas · de negocio

> **APROBADA: opción A (2026-10-03).**

**Qué hay que decidir.** Desde dónde se paga y se consulta.

- **A (recomendada).** Área "Pagos a proveedores" (`/admin/pagos-proveedores`): listado paginado con filtros (proveedor, estado, origen, fechas), alta, detalle con medios y anulación. Además, botón "Registrar pago" en la cuenta corriente del proveedor (precarga el proveedor) y enlace desde cada movimiento `PAGO`/`ANULACION_PAGO` y `COMPRA`/`ANULACION_COMPRA` a su operación, visible según permiso. Los pagos de origen `COMPRA` aparecen en el listado con enlace a su compra.
- **B.** Sin área propia: se paga y se anula solo desde la cuenta corriente del proveedor. Menos pantallas, pero no hay "todos los pagos de la semana".
- **C.** A más un botón "Pagar" en el detalle de una compra a crédito con el total precargado. Sugiere una imputación que no existe (PAG-02).

**Ejemplo.** El viernes se pagan $100.000 a Bodega Sur y $80.000 a Bodega Norte. A: el listado filtrado por fecha muestra los dos pagos, $180.000 en total a la vista. B: hay que abrir la cuenta de cada proveedor.

## Enfoque técnico (con la opción A de cada decisión)

- **Dominio** (`proveedores/domain/pagos.py`, puro): `validar_medios(importe, medios)` (cantidad de medios, importes, suma exacta, referencias) y `validar_pago_independiente`. `validar_pago` de compras pasa a delegar en `validar_medios` para el contado, sin cambiar su contrato ni sus códigos. Errores nuevos: `MEDIOS_INVALIDOS` (422), `PAGO_YA_ANULADO` y `PAGO_DE_COMPRA_VIGENTE` (409).
- **Servicio** `registrar_pago` y `anular_pago` en `proveedores/service.py`; el repositorio generaliza `insertar_pago_de_compra` a un `insertar_pago` con origen, sin cambiar lo que escribe la compra.
- **Comandos** `PAGO_PROVEEDOR_REGISTRAR` v1 y `PAGO_PROVEEDOR_ANULAR` v1 en `proveedores/commands.py`, `ONLINE`, con `_exigir_permiso`.
- **API** `POST /api/v1/pagos-proveedores`, `POST /api/v1/pagos-proveedores/{id}/anulacion`, `GET /api/v1/pagos-proveedores`, `GET /api/v1/pagos-proveedores/{id}` y `GET /api/v1/proveedores/{id}/saldo`. Importes como string; cursor y límite como en compras.
- **Dependencias:** ninguna nueva. `proveedores` ya usa `cuentas_corrientes` y `configuracion` por `service.py` (ADR-043 punto 15).
- **Frontend:** `domain/pagos-proveedores/` (suma de medios, faltante y saldo resultante con `decimal.js`), `features/pagos-proveedores/` (hooks y `Operation-Id` por contenido), `areas/admin/pagos-proveedores/` (pantallas sin lógica de negocio).

## Risks / Trade-offs

- [Generalizar la validación de medios rompe la compra de contado] → red de seguridad: suite completa de compras en verde antes y después de cada paso; el contrato de `validar_pago` no cambia.
- [Interbloqueo entre `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR`] → D10 y prueba de concurrencia con commits reales.
- [El `CHECK` estricto de anulación falla sobre datos existentes] → la migración verifica antes y aborta con mensaje; prueba de migración con un pago anulado por compra sembrado.
- [`downgrade` pierde motivos y observaciones] → aceptado y probado como aserción explícita (D9).
- [Un pago de más pasa inadvertido] → confirmación explícita en pantalla (D3); el servidor no lo bloquea.
- [Tras el primer pago ya no se puede corregir el saldo inicial (CC-08)] → se avisa en la verificación manual; la corrección espera a los ajustes de la etapa 2.

## Migration Plan

Una revisión de Alembic (D9), aplicable con datos. Despliegue: `alembic upgrade head`; no hay dependencias nuevas, así que no hace falta reconstruir imágenes salvo que el apply agregue alguna. Rollback: `alembic downgrade -1`, con la pérdida descripta en D9.
