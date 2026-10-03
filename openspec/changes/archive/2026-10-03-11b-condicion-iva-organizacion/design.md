# Diseño técnico — 11b-condicion-iva-organizacion

> **Estado: D0 a D10 APROBADAS con la opción A el 2026-10-03 (tarea 0.1), incluido el ID de regla nuevo CST-06.** Las specs y las tareas están escritas con la opción A de cada decisión. Cada decisión indica si es **de negocio** o **técnica**. Todas se documentan en **ADR-045** (enmienda ADR-009), que se redacta durante el apply en estado *Propuesto*.

## Context

Ver `proposal.md` (Why). Estado actual del código:

- `configuracion_organizacion` (modelo en `identidad/models.py`, validadores en `identidad/domain/valores.py`) ya guarda `modo_impositivo` (`A`, `B`, `C`, `NOT NULL`) y `modalidad_iva_default` (nulable). Solo se crea en la siembra (`app/seed.py`, `modo_impositivo = "A"`). El único comando que escribe esta tabla es `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (07), con permiso `ADMIN_CONFIGURACION`. No hay pantalla ni lectura de configuración en `/admin`.
- `proveedores/domain/costo_base.py::calcular_costo_base(valor, incluye_iva, alicuota, bonificacion, unidades)` (CST-02) y su gemela `frontend/src/domain/proveedores/costoBase.ts`, sobre `cst-02-costo-base.json`.
- `proveedores/domain/compras.py`: `importe_con_iva = round2(importe_neto × (1 + alícuota))` y `total_factura_sugerido = Σ importe_con_iva` (CMP-02, D1 del 11). Gemelas TS en `frontend/src/domain/compras/{calculoCompra,formularioCompra}.ts`, sobre `cmp-02-compra.json`.
- `costo_informado` y `compra_linea` ya congelan `incluye_iva` y `alicuota_aplicada` (`03` §6).
- La importación de costos (`importacion/domain/planilla.py`, `domain/costos.py`) tiene la columna `incluye_iva` **obligatoria** (`S`/`N`) y registra por `informar_costos`.
- El stock inicial (`STOCK_INICIAL_REGISTRAR` y su importación) recibe `costo_unitario` por unidad base: no aplica IVA, así que **no cambia**. Para un monotributista ese costo es el pagado; se aclara en la ayuda de la plantilla, sin regla nueva.
- `GET /api/v1/yo` tiene un contrato cerrado (06b): usuario, organización (id y nombre), rol y permisos.

Lo que `docs/` no resuelve:

- **Contradicción 1:** CST-02 y CMP-02 suponen que el IVA de compra se recupera. Para un monotributista o un exento, el IVA es costo. → D1, D4, D5.
- **Contradicción 2:** ADR-009 y FAC-02/03/08 (modalidad CLIENTE/ABSORBIDO, "utilidad neta de IVA") solo tienen sentido para un responsable inscripto. Un monotributista emite Factura C, sin IVA discriminado. → D2.
- **Hueco:** `docs/` no dice qué pasa con lo ya registrado si la condición cambia (por ejemplo, el monotributista que pasa a inscripto). → D3, D7, D10.

## Goals / Non-Goals

**Goals:** una sola regla (`computa_credito_fiscal`) que decida el cálculo en servidor, cliente e importación; un responsable inscripto con el comportamiento actual intacto, sin cambios en sus fixtures; historia congelada.

**Non-Goals:** facturación y Factura C; tope del monotributo (idea futura: reporte de facturación de los últimos 12 meses contra el tope de la categoría); recalcular costos o compras previos; percepciones; `condicion_iva` del cliente.

## Decisions

### D0 — Tamaño del change · técnica

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** El alcance son una columna, una regla en dos cálculos, un comando, una lectura, una pantalla mínima y cambios en dos pantallas y una importación. Cabe en un change chico.

- **A (recomendada).** Un solo change en dos lotes de apply: (1) fixtures, migración, regla, cálculo, comando, lectura e importación por API; (2) frontend, cobertura, docs y verificación manual.
- **B.** Un solo lote.

**Ejemplo.** Con A, al cerrar el lote 1 ya se puede confirmar por API una compra de una organización monotributista y ver el costo base sin IVA descontado.

### D1 — Cómo se modela la condición frente al IVA · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Cómo se representa la condición y qué regla se deriva de ella.

- **A (recomendada).** `configuracion_organizacion.condicion_iva text NOT NULL` con `CHECK IN ('RESPONSABLE_INSCRIPTO', 'MONOTRIBUTO', 'EXENTO')` y una sola regla derivada, función pura: `computa_credito_fiscal(condicion) = (condicion == RESPONSABLE_INSCRIPTO)`. `EXENTO` se comporta como `MONOTRIBUTO` para el costo, pero se distingue para la facturación futura. Regla nueva **CST-06** en `01` §6.1, más una fila en `01` §4.
- **B.** Un booleano `computa_credito_fiscal` en la configuración, sin la condición. Es más simple, pero pierde el dato que necesitará la facturación (Factura A/B o C).
- **C.** Un modo impositivo nuevo `M` en `modo_impositivo`. Mezcla cómo se venden los precios (A/B/C) con lo que la organización recupera en compras.

**Ejemplo.** Caja x12 de Cerveza B, factura del proveedor de $21.780 (18.000 + 21%). Con A: un responsable inscripto carga "incluye IVA" y el costo base es 21.780 / 1,21 / 12 = $1.500,000000. Un monotributista carga $21.780 sin opción de IVA y el costo base es 21.780 / 12 = $1.815,000000.

### D2 — Modo impositivo y modalidad de IVA de una organización no inscripta · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué valen `modo_impositivo` y `modalidad_iva_default` cuando la organización no es responsable inscripta.

- **A (recomendada).** Una restricción de base lo exige: `condicion_iva = 'RESPONSABLE_INSCRIPTO' OR (modo_impositivo = 'A' AND modalidad_iva_default IS NULL)`. El modo A (venta a precio final, sin IVA en la venta, VTA-04) es exactamente lo que hace un monotributista. La modalidad CLIENTE/ABSORBIDO no existe para él (Factura C). ADR-045 deja escrito que ADR-009 y FAC-02/03/04/08 solo se aplican a responsables inscriptos.
- **B.** Se guardan como hoy y se ignoran. Así quedan datos que dicen algo que el sistema no hace.
- **C.** Volverlos nulables y exigir nulo cuando no es RI. Rompe el `NOT NULL` de `modo_impositivo`, que leen los changes 13 y 18a.

**Ejemplo.** Un monotributista con `modalidad_iva_default = ABSORBIDO`: con A, la base lo rechaza; con B, el día que exista la facturación, alguien podría "absorber" un IVA que nunca se cobró.

### D3 — Congelamiento de la regla en cada registro · técnica

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Cómo se garantiza que cambiar la condición nunca recalcule la historia y que cada costo se pueda reconstruir.

- **A (recomendada).** Columna `computa_credito_fiscal boolean NOT NULL` en `costo_informado` y en `compra_linea`, que se toma de la condición vigente al registrar. Se agrega `CHECK (computa_credito_fiscal OR NOT incluye_iva)`. Las filas existentes se migran con `true`: se calcularon con la regla de un responsable inscripto. CST-02 queda `valor × (1 − bonif) / (1 + alícuota si incluye IVA y computa crédito fiscal) / unidades`. El costo base ya se guarda, así que nada se recalcula.
- **B.** Sin columna nueva: en una organización no inscripta se guarda `incluye_iva = false`. Reproduce el costo, pero no deja rastro de por qué no se descontó el IVA, y un "Incluye IVA: No" en un costo de $21.780 que sí lo incluía engaña.
- **C.** Guardar el texto `condicion_iva` en `compra` (cabecera) y en `costo_informado`. Es más informativo, pero no permite un `CHECK` por fila sobre la línea.

**Ejemplo.** En marzo se compra como monotributista a $21.780 → $1.815,000000 (`computa_credito_fiscal = false`). En junio la organización pasa a responsable inscripto. Con A, el detalle de la compra de marzo sigue en $1.815,000000 con "IVA no computable", y las compras nuevas descuentan el IVA.

### D4 — Qué pasa con "incluye IVA" en una organización no inscripta · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué hace el servidor si llega `incluye_iva = true` en `COSTO_INFORMAR` o en una línea de `COMPRA_CONFIRMAR` de una organización no inscripta.

- **A (recomendada).** Se rechaza con 422 `INCLUYE_IVA_NO_APLICA`, indicando la línea o la fila. El valor que se carga es siempre el pagado. La pantalla oculta la casilla y envía `false`. Es explícito y coherente con TR-10.
- **B.** Se acepta y se ignora (se guarda `false`). Es más tolerante, pero un cliente desactualizado cree que se descontó un IVA que no se descontó.

**Ejemplo.** Un monotributista informa Caja x12 a $21.780 con `incluye_iva = true`. Con A: 422 y nada se registra. Con B: queda $1.815,000000 y `incluye_iva = false`, sin aviso.

### D5 — Total de factura sugerido en una organización no inscripta · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué propone la pantalla como total de factura (CMP-02).

- **A (recomendada).** El sugerido es la suma de los importes de las líneas (`total_neto`), sin IVA agregado, porque el valor cargado ya es el pagado. La pantalla muestra "Total" en lugar de "Total neto" y oculta "IVA sugerido". El total de factura sigue siendo editable para percepciones o redondeos (D1 del 11). En la base, `total_neto` conserva su nombre. En una organización no inscripta significa "total de costo", e incluye el IVA pagado (se anota en `03` §6).
- **B.** Seguir sugiriendo `neto + IVA` con la alícuota del producto. Duplica el IVA en la deuda: $21.780 × 1,21 = $26.353,80.

**Ejemplo.** Compra del criterio 2 hecha por un monotributista, con los valores de factura: 10 cajas de Vino A x6 a $7.260 + 60 botellas de Cerveza B a $1.331. Con A: la suma de las líneas es $72.600,00 + $79.860,00 = $152.460,00 y ese es el total sugerido; la deuda es $152.460,00 (lo mismo que paga un inscripto) y los promedios quedan en $1.210,000000 y $1.331,000000, contra $1.000 y $1.100 de un inscripto. Con B, el sugerido sería $87.846,00 + $96.630,60 = $184.476,60, con el IVA cobrado dos veces.

### D6 — Importación de costos en una organización no inscripta · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué hace la importación con la columna `incluye_iva`.

- **A (recomendada).** Para un responsable inscripto, todo sigue igual (columna obligatoria). Para uno no inscripto, la columna pasa a ser opcional: vacía o `N` se aceptan, y `S` se rechaza en la fila con `INCLUYE_IVA_NO_APLICA`. Rige todo o nada (ADR-040). Es "la misma regla que el alta individual" (spec `importacion-de-maestros`, IMP, TR-10), así que la planilla no puede registrar algo que la pantalla rechazaría.
- **B.** Ignorar la columna: `S` se trata como `N` sin aviso. Una planilla armada pensando en un inscripto pasa sin que nadie revise si los valores son los pagados.
- **C.** Rechazar cualquier valor no vacío, incluso `N`. Es más estricto sin ganar nada: `N` ya significa "no se descuenta IVA".

**Ejemplo.** Planilla de 40 filas con `incluye_iva = S` en la fila 7. Con A: la importación falla con la fila 7 señalada; el usuario confirma que $21.780 es lo pagado, vacía la columna y reimporta. Con B: se importa todo y nadie revisa.

### D7 — Cambio de condición · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Cómo se cambia la condición (un caso real: el monotributista que pasa a responsable inscripto).

- **A (recomendada).** Comando `ORGANIZACION_CONDICION_IVA_CAMBIAR` v1 (`ONLINE`), con permiso `ADMIN_CONFIGURACION` (el mismo criterio que `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`). Lleva una sola auditoría del bus con el valor anterior y el nuevo (AUD-01, "cambios de configuración"). No tiene efecto retroactivo: rige para lo que se registre después. Si el valor es el mismo, se rechaza con `CONDICION_IVA_SIN_CAMBIO`. Pasar a no inscripto con `modo_impositivo ≠ A` o con modalidad definida se rechaza con `MODO_IMPOSITIVO_INCOMPATIBLE` (D2). Pasar a inscripto deja modo A y modalidad sin definir. Mismo `operation_id` y misma huella devuelven el resultado original (INV-06).
- **B.** Un permiso nuevo `CAMBIAR_CONDICION_IVA`, solo para ADM. Es más granular, pero suma una semilla y una fila en `01` §19 por un cambio que ocurre pocas veces en la vida de la organización.
- **C.** Sin comando: se cambia por migración o SQL de operador. No queda auditado. El usuario lo descartó.

**Ejemplo.** El 1/07 la organización pasa de `MONOTRIBUTO` a `RESPONSABLE_INSCRIPTO`. Con A: una auditoría "MONOTRIBUTO → RESPONSABLE_INSCRIPTO". La compra del 30/06 sigue en $1.815,000000. La del 2/07 a $21.780 con IVA incluido da $1.500,000000.

### D8 — Cómo se entera el frontend de la condición · técnica

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** De dónde lee la interfaz la condición para ocultar la casilla y elegir el total sugerido.

- **A (recomendada).** `GET /api/v1/configuracion/fiscal` → `{condicion_iva, computa_credito_fiscal, modo_impositivo, modalidad_iva_default}`, para cualquier usuario autenticado de la organización del token (INV-21). Hook de TanStack Query compartido por compras, carga de costos y la pantalla nueva `/admin/configuracion/fiscal`, que muestra la condición y, con `ADMIN_CONFIGURACION`, permite cambiarla con una confirmación que explica que no es retroactivo (D10).
- **B.** Agregar `condicion_iva` a `GET /yo`. Ahorra un viaje, pero reabre un contrato cerrado y aprobado en el 06b.

**Ejemplo.** Un usuario con solo `REGISTRAR_COMPRA` abre el alta de compra. Con A, el formulario pide `/configuracion/fiscal`, ve `computa_credito_fiscal = false` y no muestra la casilla.

### D9 — Valor inicial en la migración y en la siembra · de negocio · **lo decide el usuario**

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué condición toman las organizaciones existentes y la organización inicial sembrada.

- **A (recomendada).** La migración pone `RESPONSABLE_INSCRIPTO` a toda organización existente, porque sus costos y compras ya se calcularon con esa regla (las filas quedan coherentes con `computa_credito_fiscal = true`) y nada cambia de comportamiento por migrar. La **siembra** de una organización inicial nueva usa `MONOTRIBUTO` (`00` §5). La organización de desarrollo se pasa a `MONOTRIBUTO` con el comando de D7 durante la verificación manual: así queda auditado y se prueba el flujo real.
- **B.** La migración pone `MONOTRIBUTO` a la organización inicial (por su `slug`) y `RESPONSABLE_INSCRIPTO` a las demás. Es más cómodo, pero la migración toma una decisión de negocio sin auditoría y deja costos viejos calculados como inscripto en una organización que figura como monotributista desde siempre.
- **C.** `MONOTRIBUTO` para todas. Es igual de silencioso que B, y lo previo queda incoherente con la condición.

**Ejemplo.** En desarrollo hay 30 costos cargados "con IVA incluido" a $18.000 → $1.239,669421. Con A siguen así (`computa_credito_fiscal = true`). Tras el cambio a monotributo, el historial los muestra con "IVA descontado" y los nuevos sin descontar. Si los datos de desarrollo se van a descartar antes de cargar los reales, A y B dan lo mismo.

### D10 — Costos informados vigentes al cambiar la condición · de negocio

**Decisión: opción A, aprobada por el usuario el 2026-10-03.**

**Qué hay que decidir.** Qué pasa con los costos informados vigentes calculados con la regla anterior, que el 13 usará para fijar precios (PRC-11).

- **A (recomendada).** Siguen vigentes tal como se registraron (CST-03). La pantalla del cambio informa cuántos costos vigentes se calcularon con la otra regla y sugiere volver a informarlos. No hay recálculo automático. ADR-045 lo deja como insumo del 13.
- **B.** Bloquear el cambio mientras existan costos vigentes con la otra regla. Es demasiado rígido para un cambio que ocurre con fecha fiscal.
- **C.** Generar costos nuevos automáticamente con la regla nueva. Contradice CMP-04 ("nunca automático") y el carácter informado del costo.

**Ejemplo.** Un monotributista con Caja x12 vigente en $1.815,000000 pasa a inscripto. Con A, sigue vigente $1.815,000000 hasta que se informe $1.500,000000. La pantalla avisa "12 costos vigentes calculados sin descontar IVA".

## Detalles derivados (no requieren decisión)

- **Dueño de la regla:** `identidad` (dueño de `configuracion_organizacion`) expone `identidad/service.py::obtener_condicion_iva(organizacion_id, sesion)` y la función pura `computa_credito_fiscal` en `identidad/domain/valores.py`. `proveedores` e `importacion` la leen solo por `service.py` (import-linter). `importacion` sigue registrando por `proveedores.informar_costos`, que es quien valida D4.
- **Firma de cálculo:** `calcular_costo_base(..., computa_credito_fiscal: bool)` y la línea de compra reciben el booleano. El sugerido por línea es `importe_neto × (1 + alícuota)` si computa y `importe_neto` si no. La validación `INCLUYE_IVA_NO_APLICA` vive en el dominio de `proveedores` (pura), antes de escribir.
- **Huella del comando:** `computa_credito_fiscal` **no** viaja en el comando (lo decide el servidor). Un reenvío idempotente después de un cambio de condición devuelve el resultado original (INV-06).
- **Orden:** el comando de cambio toma `configuracion_organizacion FOR UPDATE`. `COSTO_INFORMAR` y `COMPRA_CONFIRMAR` leen la condición `FOR SHARE` al inicio, así una compra concurrente con el cambio usa una sola regla de punta a punta.
- **Rotulado en pantallas:** "Valor pagado" en lugar de "Valor" cuando no computa. El detalle de compra y el historial de costos muestran "IVA descontado: Sí/No" desde la columna congelada.
- **Auditoría:** una por comando, la del bus (ADR-022).
- **Resumen para D10:** `GET /api/v1/costos/resumen-regla-iva?fecha=` en `proveedores` (`ADMIN_CONFIGURACION` o `EDITAR_COSTOS`). Cuenta los costos vigentes a la fecha por `computa_credito_fiscal` con SQL en la base. Lo usa la pantalla de cambio de condición.
- **Docs:** `04` inserta 11b en el hito 3, antes del 12 y del 13, con dependencias `02, 06, 10, 11`. El 13, el 18a, la nota de venta y la facturación dependen de él. Se anota que un monotributista vende a precio final (modo A, Factura C sin IVA discriminado) y la idea futura del reporte de tope del monotributo.

## Risks / Trade-offs

- [Romper el comportamiento de un responsable inscripto] → los fixtures existentes pasan intactos con `computa_credito_fiscal = true`; las suites del 06, 10 y 11 corren como red de seguridad.
- [Costos vigentes con la otra regla alimentan precios en el 13] → D10: aviso en el cambio y ADR-045 como insumo del 13.
- [Confundir "total neto" en una organización no inscripta] → rótulos de pantalla y nota en `03` §6; la deuda siempre es `total_factura`.
- [Planillas preparadas para un inscripto] → D6 rechaza `S`; la ayuda de la plantilla explica "valor pagado".
- [Compra concurrente con el cambio de condición] → bloqueo `FOR SHARE`/`FOR UPDATE` sobre la configuración y una prueba de concurrencia.

## Migration Plan

Una revisión de Alembic: agrega `condicion_iva` a `configuracion_organizacion` (rellena `RESPONSABLE_INSCRIPTO`, según D9, luego `NOT NULL` y `CHECK`), con el `CHECK` de D2. Agrega `computa_credito_fiscal` a `costo_informado` y `compra_linea` (rellena `true`, luego `NOT NULL` y el `CHECK` de D3). Los permisos de `app_runtime` no cambian, salvo `UPDATE (condicion_iva)` sobre `configuracion_organizacion` si la concesión actual es por columnas. `downgrade` quita columnas y restricciones. Se prueba con `upgrade`/`downgrade`/`upgrade` sobre una base con costos y compras.

## Open Questions

- **No bloqueante:** ¿los proveedores inscriptos facturan con el IVA discriminado (Factura A/B con neto + IVA) o como un total único? La interfaz funciona igual en los dos casos, porque se carga el **valor pagado** por presentación. Si llegara discriminado, el usuario suma el IVA al cargar. Una ayuda "neto + IVA" en la línea queda como mejora posible, sin cambiar specs.
