# Change 25-observaciones-y-revision

## Qué resuelve este change

Administración revisa en `/admin` todo lo que el sistema marcó para mirar: las observaciones pendientes y las operaciones del teléfono que no se aceptaron (rechazadas y en cuarentena). Las da por resueltas con un comentario, sin tocar la operación (SYN-08), y ve un aviso de lo pendiente, con los excesos de crédito detectados al sincronizar (CRE-09).

## Why

`04` §11 (fila 25; SYN-08). Las observaciones nacen `PENDIENTE` y nadie puede resolverlas; un rechazo sin conexión no deja rastro en el servidor (el bus revierte la reserva) y el teléfono dice «avisá a administración».

## What Changes

- **Resolver observaciones** (D1, D2): `OBSERVACION_RESOLVER` v1 (`REVISAR_OBSERVACIONES`, solo `ONLINE`), de 1 a 100 con un comentario, todo o nada; la base solo admite actualizar las columnas de la resolución.
- **Bandeja** (D3, D4): agrupada por operación, con filtros y el detalle legible de cada código; el resumen de cada operación llega por puertos.
- **Aviso** (D5): contador en el menú y tarjeta «Para revisar» en el inicio de `/admin`, con los excesos detectados al sincronizar aparte.
- **Rechazos** (D6, D7): el lote guarda cada rechazo sin conexión en `comando_rechazado` (transacción aparte); `RECHAZO_RESOLVER` v1 resuelve un rechazo o una cuarentena con comentario y vínculo opcional a la corrección. Nada se reenvía.
- **Teléfono** (D8): el bootstrap informa los rechazos resueltos de la jornada; la venta rechazada resuelta deja de contar en lo local. Sin versión nueva de Dexie.
- **Rendición** (D9 = B): `JORNADA_RENDIR` se rechaza con `RECHAZOS_PENDIENTES` (409) mientras la jornada tenga rechazos sin conexión pendientes (la cuarentena no bloquea); la entrega del día no se bloquea; la pantalla de conteo avisa y deshabilita «Registrar rendición». **Producto desactivado** (D10): observación nueva `PRODUCTO_DESACTIVADO`.
- **Pantallas, textos y ayuda** (D11 a D13). **Migración** sí; **sin permisos nuevos**. **ADR-069** (*Propuesto*) y `propuesta-docs.md`.

## Deudas heredadas y cómo se saldan

| Origen | Deuda | Cómo |
| --- | --- | --- |
| 04 | Permiso de la cuarentena, reenvío, `OBSERVACION_RESOLVER` | D7 (`REVISAR_OBSERVACIONES`, sin reenvío), D1 |
| 17 | Resolver `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE` | D1, D3 |
| 18a / ADR-054 | Mostrar `CONSUMIDOR_FINAL_CON_DEUDA`, `UBICACION_TOMADA_AL_SINCRONIZAR`, `VENTA_SIN_COSTO`; producto desactivado sin observación | D3; D10 |
| 18b / ADR-055 | `AUTORIZACION_OFFLINE`, causas de `DESCUENTO_DIFIERE`, `EXCESO_CREDITO_DETECTADO_SYNC` y su notificación | D3; D5 |
| 22c | Resolver una venta rechazada, con permiso y ADR | D6, D7, D8 |
| 22d (D5) | Anulación de una «Rechazada» y resolución de las rechazadas | D8 (no se anula en el teléfono; la resuelve administración), D7 |
| 23 / ADR-067 | Resolución de las cobranzas rechazadas | D6, D7 |
| 24 / ADR-068 | Mostrar y resolver `JORNADA_RENDIDA` | D3, D1 |

Ninguna se reasigna.

## Decisiones

`design.md` D0 a D13, **aprobadas** (tarea 0.1, 2026-11-05): todas en A salvo **D9 = B**. **CRÍTICAS: D6 y D7.** ALTAS: D1, D2, D5, D8, D9. **Bloqueante:** sin 0.2 (textos) no empieza el apply.

## No incluye

Reprocesar o reenviar comandos rechazados o en cuarentena; correo u otro canal fuera de la aplicación; reabrir una observación resuelta; cargar la corrección desde la bandeja (se carga en sus pantallas); el reporte de observaciones por vendedor (26); la bandeja en el teléfono.

## Reglas e invariantes

- **SYN-04, SYN-05, SYN-06, SYN-07, SYN-08, SYN-09, SYN-11, CRE-08, CRE-09, RUT-05, RUT-06, AUD-01; `01` §18 (Observación), §19.**
- **SYN-08** (cierra): propiedad con SQL, resolver no cambia operaciones, libros ni comandos. **INV-01**: todo o nada. **INV-02/INV-21**: ajenas, 404. **INV-05**: sin `DELETE`, `UPDATE` acotado. **INV-06**: doble envío. **INV-17**: `PRODUCTO_DESACTIVADO` no rechaza.
- Sin cálculo nuevo ni fixture de cálculo; `codigos-de-sincronizacion.json` suma `PRODUCTO_DESACTIVADO`.

## Capabilities

### New Capabilities

- `sync/revision-de-observaciones`: bandeja, resolución y aviso.
- `sync/rechazos-sin-conexion`: registro y resolución de los rechazos del lote.

### Modified Capabilities

- `sync/observaciones`: resolución inmutable y `PRODUCTO_DESACTIVADO`.
- `sync/cuarentena-de-comandos`: revisión y resolución, sin reenvío.
- `sync/bootstrap`: rechazos resueltos de la jornada.
- `sync/cola-local`: la venta rechazada resuelta deja de contar.
- `ruta/area-de-ruta`: «Resuelta por administración».
- `stock/rendicion-de-jornada`: la rendición espera a que se resuelvan las rechazadas de la jornada (`RECHAZOS_PENDIENTES`).
- `sistema/ayuda-contextual`: claves nuevas y revisadas.

## Impact

Backend: `sync/`, puertos en `ventas/`, `cobranzas/`, `proveedores/` y `stock/`, migración. Frontend: `areas/admin/revision/` (nueva), detalles con la resolución, `RendicionScreen`, `sync/` del teléfono, `ayuda/textos.ts`. `shared/fixtures/sync/`. Docs al archivar.
