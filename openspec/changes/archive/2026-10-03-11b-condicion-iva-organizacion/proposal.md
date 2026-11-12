# Change 11b-condicion-iva-organizacion

## Qué resuelve este change

Agrega la condición de la organización frente al IVA (`RESPONSABLE_INSCRIPTO`, `MONOTRIBUTO`, `EXENTO`). Solo un responsable inscripto descuenta el IVA de lo que compra; para los demás, el IVA pagado es costo. Cada costo y cada compra guardan la regla con que se calcularon, así que cambiar la condición nunca recalcula la historia.

## Why

La distribuidora real es **monotributista**, pero `docs/` supone un responsable inscripto: CST-02 divide por `1 + alícuota` cuando el valor incluye IVA, CMP-02 sugiere `neto + IVA` como total de factura y `00` §5 fija "listas sin IVA (modo A)" con modalidad de IVA al facturar (ADR-009, FAC-02/03/08). Para un monotributista ese IVA no se recupera: el costo, el promedio y, desde el 13, los precios quedarían subvaluados alrededor de un 17% (`1 − 1/1,21`). Hay que corregirlo antes del 13, el primer change que fija precios a partir de costos.

## What Changes

- **Parámetro nuevo** `condicion_iva` en `configuracion_organizacion` y una regla derivada única: *computa crédito fiscal de IVA en compras* solo para `RESPONSABLE_INSCRIPTO` (regla nueva propuesta: CST-06). `modo_impositivo` y `modalidad_iva_default` solo se aplican a responsables inscriptos (`design.md` D2).
- **Congelamiento por registro**: `costo_informado` y `compra_linea` guardan `computa_credito_fiscal` (D3). Los costos y las compras ya registrados no cambian.
- **CST-02 y CMP-02** para una organización no inscripta: nunca se divide por `1 + alícuota`. `incluye_iva = true` se rechaza con `INCLUYE_IVA_NO_APLICA` (D4), el total de factura sugerido es la suma de las líneas (D5) y la importación de costos rechaza `incluye_iva = S` (D6). Para un responsable inscripto todo sigue exactamente como hoy.
- **Comando** para cambiar la condición, con `ADMIN_CONFIGURACION` y auditado. No tiene efecto retroactivo (D7). Lectura `GET /api/v1/configuracion/fiscal` (D8) y una pantalla `/admin` mínima.
- **Pantallas**: compras y carga de costos ocultan "Incluye IVA" en una organización no inscripta; el detalle y el historial muestran la regla congelada.
- **Fixtures compartidos** (antes del código): se **modifican** `cst-02-costo-base.json` y `cmp-02-compra.json`, que agregan `computa_credito_fiscal` y casos de monotributo. `cst-11` no cambia.
- **Siembra y migración**: la organización inicial nace `MONOTRIBUTO`; las existentes quedan `RESPONSABLE_INSCRIPTO` (D9, **lo decide el usuario**).
- **Docs** (en el apply): ADR-045 (enmienda ADR-009); `00` §5; `01` §4, §6 y §16; `03` §4 y §6; `04` (11b antes del 13 y su impacto en 13, 18a y facturación).

## Decisiones abiertas (bloquean la implementación)

`design.md` D0 a D10, cada una con la opción A recomendada y un ejemplo en pesos. **De negocio:** D1, D2, D4, D5, D6, D7, D9 y D10. **Técnicas:** D0, D3 y D8. Todas van a ADR-045. La pregunta abierta sobre cómo llegan las facturas de proveedores inscriptos no bloquea.

## No incluye

Facturación y Factura C. El tope de la categoría del monotributo (idea futura: un reporte de los últimos 12 meses). Recalcular lo registrado. El stock inicial (ya carga el costo por unidad base). Los modos B y C. La `condicion_iva` del **cliente** (deuda del 07).

## Invariantes

- **TR-06**: tras cambiar la condición, costos y compras previos se releen intactos (prueba).
- **INV-01**: el cambio y su auditoría son atómicos. **INV-06 / INV-21**: idempotencia y aislamiento del comando y la lectura nuevos.
- **CST-02 / ADR-016**: los fixtures pasan en pytest y Vitest.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `organizacion/parametros-de-organizacion`: condición, regla derivada, cambio, lectura y pantalla.
- `proveedores/costos-informados`: costo base según la condición, congelado.
- `proveedores/compras`: línea y total sugerido según la condición.
- `proveedores/administracion-de-compras` y `proveedores/administracion-de-proveedores`: pantallas sin "Incluye IVA" para no inscriptos.
- `importacion/importacion-de-maestros`: columna `incluye_iva` según la condición.

## Impact

Backend: `identidad`, `proveedores` e `importacion`, más una migración. Frontend: `costoBase.ts`, `domain/compras/*`, `CostosCargaScreen`, `CompraFormScreen` y la pantalla fiscal nueva.
