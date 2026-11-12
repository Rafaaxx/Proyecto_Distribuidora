# Change 22c-stock-credito-locales-y-conflictos

## Qué resuelve este change

El saldo y el stock del teléfono dejan de contar dos veces las ventas ya enviadas, se ven en Stock, Productos y la ficha del cliente, y el vendedor entiende qué anotó o por qué rechazó el sistema cada venta, sin señal. Cierra INV-17 y las métricas de lote.

## Why

`04` §11 (fila 22c) y deudas de ADR-063 y ADR-064: hoy, tras sincronizar y actualizar los datos, el teléfono descuenta dos veces lo vendido (CRE-08, RUT-04), y «Sincronización» solo muestra un texto general y el código. ADR-058 dejó al 22c la anulación sin conexión (VTA-24). **El alcance de la fila es demasiado grande para un change** (`04`: «Si 22b o 22c se desbordan: … dividir»): se propone pasar la anulación a un change nuevo **22d `anulacion-sin-conexion`** (`design.md` D0, de negocio).

## What Changes

- **Conciliación** (D1, D2): el bootstrap informa la mayor secuencia de la jornada que el servidor ya procesó; el teléfono cuenta solo los movimientos de operaciones posteriores, y una venta rechazada sigue contando (lo conservador). Exacto aunque se pierda una respuesta.
- **Observaciones en el resultado del lote** (D3): cada ítem trae sus observaciones con detalle, también al reenviar; el teléfono las guarda con el resultado.
- **Observaciones y rechazos traducidos** (D4, D5): «Sincronización» resume y el detalle de la venta explica cada observación y el motivo del rechazo; fixture compartido de códigos validado por servidor y teléfono.
- **Disponibles locales en las pantallas de consulta** (D6).
- **Métrica de cierre por lote** (D7, `02` §17).
- **Cierre de INV-17** (D8): matriz de integración por cada regla de SYN-05.
- **Ayuda** (D9): una clave nueva y cuatro revisadas, sin ejemplos.
- **ADR-065** (*Propuesto*) y `propuesta-docs.md`.

## Decisiones

`design.md` D0 a D9, pendientes (tarea 0.1). De negocio: **D0** (división), **D1**, **D2**, **D4**, **D6**. Ninguna CRÍTICA. Bloqueante: sin D0 aprobada no se empieza el apply.

## No incluye

Anulación sin conexión (22d si D0 = A); cobranza independiente sin conexión (23; la regla de D1 ya la cubre); bandeja y resolución de observaciones (25); reenviar a mano un rechazado; métricas en el teléfono.

## Reglas e invariantes

- **CRE-08, RUT-04, STK-06, SYN-04, SYN-05, SYN-06, SYN-07, SYN-09, SYN-11; `02` §6.4, §13.2, §13.4, §17.**
- **INV-17** (cierra, SYN-05): matriz de integración por el lote con PostgreSQL real, cada caso citando INV-17.
- **INV-01** (local): resultados y observaciones de un lote se escriben todos o ninguno.
- **INV-06**: el reenvío devuelve las mismas observaciones; doble sincronización no cambia los disponibles.
- **INV-03, INV-04**: importes como string y cantidades enteras en las pantallas.
- **Sin cambios en reglas de cálculo:** sin fixtures de cálculo nuevos; fixture de contrato nuevo `shared/fixtures/sync/codigos-de-sincronizacion.json`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `sync/cola-local`: qué movimientos cuentan en el saldo y el stock locales.
- `sync/bootstrap`: la secuencia procesada de la jornada.
- `sync/lote-de-comandos`: observaciones en el resultado; INV-17 de punta a punta.
- `sync/motor-de-sincronizacion`: el teléfono guarda las observaciones.
- `ruta/area-de-ruta`: disponibles locales en consulta; observaciones y rechazos explicados.
- `sistema/logging-estructurado`: registro de cierre del lote.
- `sistema/ayuda-contextual`: ayudas de disponibles y conflictos.

## Impact

Backend: `sync/bootstrap.py` y `schemas.py` (marca), `sync/service.py` y `api.py` (observaciones en el resultado, registro de cierre), pruebas de integración; sin migración ni permisos nuevos. Frontend: `lib/dispositivo/db.ts` (tipos, sin Dexie v4), `sync/aplicarResultados.ts`, `sync/aplicarBootstrap.ts`, `domain/ruta/disponiblesLocales.ts`, `areas/ruta/` (Stock, Productos, ficha, «Sincronización», detalle de la venta), `ayuda/textos.ts`, tipos generados del OpenAPI. `shared/fixtures/sync/`. Docs: `04` §11 (22d nuevo) y el resto al archivar.
