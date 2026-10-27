# ADR-058 — Anulación de venta con conexión: contrato, dinero cobrado, costo del reingreso, ubicación tomada, maestros inactivos, cobranza anulada con la venta y orden de bloqueo

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-27, archivo del change 19) |
| Fecha | 2026-10-24 |
| Referenciado en | `openspec/changes/19-venta-anulacion/design.md` D0 a D19 y `specs/ventas/anulacion-de-venta`, `specs/ventas/administracion-de-ventas`, `specs/cobranzas/anulacion-de-cobranzas`, `specs/stock/libro-de-stock`, `specs/costeo/costo-promedio`, `specs/organizacion/catalogos-configurables`, `specs/sistema/pipeline-de-comandos`, `specs/sistema/ayuda-contextual`; `01-dominio.md` VTA-20 a VTA-24, INV-19, CST-11, CST-12, STK-09, COB-05, CLI-03, AUD-01, AUD-02; `02-arquitectura.md` §6.5 y §7.3; `03-modelo-de-datos.md` §4 y §12; ADR-043, ADR-044, ADR-046, ADR-049, ADR-052 (punto 79), ADR-054 (punto 4), ADR-056 |

**Aprobado por el usuario en tres puntos de control y completado con las precisiones del apply. Vigente desde el 2026-10-27, al archivar el change 19.**

## Aprobaciones

| Punto de control | Fecha | Qué aprobó el usuario |
| --- | --- | --- |
| Tarea 0.1 | 2026-10-24 | D0 a D19 de `design.md` en la opción A, con aprobación explícita de la crítica (D10) y de las altas (D1, D4, D5, D6, D9, D14, D15, D19) y las de negocio (D2, D3, D4, D5, D6, D7, D12, D13). D4 se aprobó tras aclarar que con cobro quedan las dos opciones: devolverlo o dejarlo a favor del cliente. También aprobó el alcance extra (el filtro por estado en `GET /ventas`, D14), los nombres de los motivos (D12) y los tres códigos nuevos: `VENTA_YA_ANULADA` (409), `DEVOLUCION_INVALIDA` (422) y `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409). |
| Tarea 0.2 | 2026-10-24 | Los seis textos de ayuda de D18 (`ventas.anulacion`, `ventas.devolverDinero`, `ventas.motivoAnulacion`, `ventas.consumidorFinalAnulacion`, `ventas.reingresoUbicacion`, `ventas.costoAnulacion`), **sin ejemplos**, y la revisión de `cobranzas.anulacion` ("El cobro de una venta se anula anulando la venta."). |
| Tarea 7.1 | 2026-10-27 | Orden de bloqueo y precedencia de rechazos de D10, opción A, tal como están en `design.md` (venta `FOR UPDATE`, su cobranza `FOR UPDATE`, motivo y devolución, `saldo_cuenta`, stock, escrituras y auditoría), contrastado con `02` §7.3, `COBRANZA_ANULAR` y `COMPRA_ANULAR`. |

## Contexto

VTA-20 a VTA-22 describen la anulación total de una venta, pero `docs/` no dice cómo se referencia la venta, si indicar la devolución es obligatorio, qué pasa con el consumidor final, con una línea vendida sin costo, con una ubicación original tomada por otra jornada o con maestros desactivados, qué motivo lleva la cobranza anulada con la venta, ni dónde entra la venta en el orden global de bloqueo. INV-19 y VTA-22 parecen contradecirse cuando no se devuelve el dinero. Los changes 17 y 18a dejaron como deuda anular la cobranza de una venta y el `UPDATE` de `venta.estado`.

## Decisión

1. **Contrato (D1, D19).** `VENTA_ANULAR` v1, permiso `ANULAR_VENTA`, solo `ONLINE` hasta el change 22c. Contenido: `venta_id` (generado por el dispositivo), `motivo_id` (ámbito `ANULACION_VENTA`), `observacion` opcional (500) y `devuelve_dinero`. Ruta `POST /api/v1/ventas/{venta_id}/anulacion`. VTA-24 se precisa: la anulación referencia a la venta por su identificador.
2. **Dinero cobrado (D2, D3).** `devuelve_dinero` es obligatorio si la venta tiene cobranza `CONFIRMADA` y prohibido si no (`DEVOLUCION_INVALIDA`, 422). En el consumidor final la devolución es obligatoria (`CONSUMIDOR_FINAL_SIN_DEVOLUCION`, 409).
3. **INV-19 (D4).** Se refiere a los efectos de la venta. Con devolución, stock y saldo quedan exactamente como antes de la venta; sin devolución, el saldo difiere solo en el importe cobrado, que queda a favor (VTA-22).
4. **Reingreso (D5).** Cada línea ingresa con tipo `ANULACION_VENTA` a su `costo_unitario` congelado (6 decimales) y recalcula el promedio por CST-11 con historia; una línea sin costo ingresa sin recalcular ni historia, con costo nulo.
5. **Ubicación (D6, D8).** La mercadería vuelve a la ubicación de la venta y STK-09 rige igual: con la ubicación tomada por otra jornada anula solo quien tiene `LIBERAR_UBICACION`; si no, `UBICACION_TOMADA`. Con la jornada `ABIERTA` del usuario y el dispositivo sobre esa ubicación, la anulación lleva esa jornada. Una venta de una jornada cerrada se anula igual con conexión.
6. **Maestros (D7).** Se anula con cliente suspendido o inactivo y con producto o presentación inactivos (el libro de stock exime a `ANULACION_VENTA` del producto activo, como a `ANULACION_COMPRA` en ADR-044 punto 5); una ubicación inactiva rechaza (`UBICACION_INACTIVA`).
7. **Cobranza (D9).** `cobranzas/service.py::anular_cobranza_de_venta` la anula dentro de la transacción de la venta con el motivo y la observación de la venta y `ANULACION_COBRANZA` por el importe completo. `COBRANZA_ANULAR` sigue rechazándola (`COBRANZA_DE_VENTA` mientras está confirmada; `COBRANZA_YA_ANULADA` si ya se anuló con la venta, ver precisión 8).
8. **Transacción (D10).** Venta `FOR UPDATE` (revalida `VENTA_YA_ANULADA`, 409) → su cobranza `FOR UPDATE` → motivo y devolución → `saldo_cuenta` → niveles 2 a 5 por `registrar_movimientos` → escrituras → auditoría. Precedencia: contenido, venta, motivo, dinero cobrado, ubicación. Enmienda `02` §7.3.
9. **Datos (D11, D12).** `venta_anulacion` con `devuelve_dinero` nulo si y solo si no había cobranza y `jornada_id` nulable; `app_runtime` con `SELECT, INSERT` en ella y `UPDATE (estado)` en `venta`; motivos sembrados "Error de carga", "Devolución del cliente" y "Otro"; el `downgrade` aborta si hay ventas anuladas.
10. **Facturación (D13).** VTA-23 no se adelanta: la regla la agrega el módulo de facturación.
11. **Permisos, lecturas y auditoría (D14, D15).** Sin permisos nuevos; el detalle trae la anulación y el listado filtra por estado; una fila de auditoría por comando con el motivo y, en su observación, la cobranza anulada y la constancia de ubicación tomada; sin observaciones nuevas de SYN-07.
12. **Fixtures (D17).** Casos de anulación de venta en `cst-11-costo-promedio.json` y fixture `vta-22-anulacion.json`, antes del código.

## Precisiones del apply

Lo que el apply fijó y `design.md` dejaba abierto o con otro nombre; no cambia ninguna decisión aprobada.

1. **Motivo sembrado (D12).** El segundo motivo se llama "Devolución del cliente" (los tres: "Error de carga", "Devolución del cliente" y "Otro"). La migración `d9e0f1a2b3c4` los agrega, una sola vez, a las organizaciones que no tengan ninguno del ámbito `ANULACION_VENTA`, y las organizaciones nuevas nacen con ellos.
2. **Cobranza anulada con la venta (D9).** `cobranzas/service.py::anular_cobranza_de_venta` recibe el motivo y la **observación** de la venta (los copia a `cobranza_anulacion`) y devuelve un `ResultadoDeAnulacion` (con el saldo que deja), igual que `anular_cobranza`; `tomar_cobranza_de_venta` toma la cobranza de origen `VENTA` `FOR UPDATE`. No valida el ámbito `ANULACION_COBRANZA` del motivo en este camino: el motivo es de `ANULACION_VENTA`.
3. **Observación (D1).** El largo (500) lo valida el dominio (`validar_observacion`, `OBSERVACION_INVALIDA`, 422) y no `max_length` de Pydantic, para que el rechazo lleve su código estable y respete la precedencia de D10 (contenido primero).
4. **Costo del reingreso (D5).** El `costo_unitario` congelado de la línea se reingresa con sus 6 decimales (`NUMERIC(18,6)`), sin redondearlo.
5. **Jornada de la anulación (D8).** `venta_anulacion.jornada_id` sale del resultado del movimiento de stock (`jornada_id` del primer movimiento, STK-09): la propia jornada `ABIERTA` o nulo si la ubicación estaba libre o se usó la excepción de `LIBERAR_UBICACION`. No se calcula aparte.
6. **Lectura para la pantalla (D14, D16).** `GET /ventas/{id}` suma `cliente_es_consumidor_final` (booleano): la pantalla fija la devolución del consumidor final (D3) y quien solo tiene `ANULAR_VENTA` no lee `/clientes`. Es un campo nuevo de lectura, sin permisos nuevos.
7. **Texto de `UBICACION_TOMADA` (D16).** El servidor no informa quién tiene la ubicación (el error no lleva el nombre de la jornada), así que la pantalla explica la regla (la ubicación está en la jornada de otro vendedor y solo anula quien puede mover una ubicación tomada) sin nombrarlo. El usuario lo confirmó el 2026-10-27: no hace falta revelar el nombre de otro vendedor.
8. **Concurrencia (D10).** Con la cobranza de la venta ya anulada por la venta, `COBRANZA_ANULAR` responde `COBRANZA_YA_ANULADA` (la regla de estado va antes que la de origen en `validar_cobranza_a_anular`) y `COBRANZA_DE_VENTA` solo si llega antes de que la venta se anule; en los dos casos hay una sola anulación de la cobranza. El usuario aprobó el 2026-10-27 ajustar la spec a este comportamiento en lugar de cambiar el orden del dominio. La desactivación de un producto exige stock cero: con la anulación primero, la desactivación se rechaza (`PRODUCTO_CON_STOCK`) porque las unidades volvieron; con la desactivación primero, la anulación reingresa igual a un producto inactivo.

## Consecuencias

- Se saldan ADR-052 punto 79 y ADR-054 punto 4.
- El change 22c habilita `VENTA_ANULAR` sin conexión sin una v2 del comando (regla de la jornada en curso y venta inexistente como dependencia inexistente).
- Un producto inactivo puede quedar con stock tras una anulación; se reactiva para moverlo.
- Deudas nuevas: al 20, si la nota de una venta anulada lleva una marca; al 24, contar las anulaciones en la rendición (RUT-07) con `venta_anulacion`; al 26, excluir las anuladas e informarlas aparte (REP-02); al módulo de facturación, VTA-23 y excluir las anuladas de lo facturable.

## Alternativas consideradas

Ver `design.md` D0 a D19 (opciones B y C de cada decisión).
