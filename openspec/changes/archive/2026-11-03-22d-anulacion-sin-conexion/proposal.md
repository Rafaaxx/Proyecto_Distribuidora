# Change 22d-anulacion-sin-conexion

## Qué resuelve este change

El vendedor con `ANULAR_VENTA` anula desde el teléfono, con o sin señal, una venta de su jornada en curso; el stock y el crédito locales lo reflejan y «Sincronización» muestra cómo volvió. Y cuando el teléfono, con señal, se entera de que su jornada ya no está abierta, deja de ofrecer «Vender» y lo avisa.

## Why

`04` §11 (fila 22d). ADR-058 dejó `VENTA_ANULAR` solo `ONLINE` y pidió habilitarlo sin conexión sin una v2 del comando (VTA-24); ADR-065 lo reasignó al 22d. Además, el usuario decidió el 2026-11-03 que el teléfono corte la venta cuando su jornada fue liberada (RUT-09): hoy sigue ofreciendo «Vender» hasta que se vuelve a entrar.

## What Changes

- **Servidor** (D1 a D3): `VENTA_ANULAR` v1 admite `OFFLINE` por el lote, con la regla de la jornada en curso, la venta inexistente como dependencia inexistente (`VENTA_INEXISTENTE`, nuevo) y qué rechaza o acepta con observación. Mismo servicio y orden de bloqueo de ADR-058. Fixture de contrato nuevo.
- **Teléfono** (D4 a D7): la anulación va siempre por la cola; Dexie v4 con `anulaciones`; anulación local atómica con movimientos inversos; regla de conciliación de la anulación.
- **Jornada no abierta** (D8, D9): el teléfono consulta el estado de su jornada en cada sincronización con señal y lo aprende del bootstrap y de `JORNADA_LIBERADA`; lo guarda, deshabilita «Vender» y «Anular» y avisa. La cola se sigue enviando.
- **Pantallas** (D10, D11): «Anular venta», estado «Anulada», anulaciones en «Ventas de hoy» y «Sincronización», nota con la marca (VTA-13), textos de rechazos y observaciones.
- **Ayuda** (D12): tres claves nuevas y cuatro revisadas, sin ejemplos.
- **ADR-066** (*Propuesto*), `propuesta-docs.md` y restitución de la spec principal `ventas/anulacion-de-venta`, que falta (D13).

## Decisiones

`design.md` D0 a D13, pendientes (tarea 0.1). **CRÍTICA: D2.** ALTAS: D1, D3, D7. De negocio: D0, D2, D5, D7, D9. Bloqueante: sin 0.1 y 0.2 no empieza el apply.

## No incluye

Cobranza suelta sin conexión (23); resolución de ventas y anulaciones rechazadas (25); contar anulaciones en la rendición (24, RUT-07); reenviar a mano un rechazado; anular una venta que no está en el teléfono; anulación parcial (etapa 2); VTA-23.

## Reglas e invariantes

- **VTA-13, VTA-20 a VTA-22, VTA-24, STK-09, RUT-03, RUT-04, RUT-09, CRE-08, SYN-02, SYN-03, SYN-06, SYN-07, SYN-09, SYN-10; `02` §6.4, §6.5, §6.6, §13.2 a §13.4.**
- **INV-19**: en el servidor por el lote y en el teléfono (con devolución, stock y saldo locales como antes de la venta).
- **INV-01**: la anulación local es una transacción Dexie; en el servidor, una del bus.
- **INV-06**: el reenvío no duplica efectos ni observaciones.
- **INV-05**: nada se borra, tampoco lo rechazado.
- **INV-21**: venta o motivo de otra organización, sin efectos.
- **INV-03, INV-04**: importes string, cantidades enteras.
- **Sin cambios en reglas de cálculo:** sin fixtures de cálculo. Contrato: nuevo `shared/fixtures/sync/venta-anular-offline.json`; se amplía `codigos-de-sincronizacion.json`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `ventas/anulacion-de-venta`: anulación sin conexión de la jornada en curso.
- `sync/lote-de-comandos`: `VENTA_ANULAR` en `OFFLINE`.
- `sync/cola-local`: anulación local y su efecto en los disponibles.
- `sync/base-local`: tabla `anulaciones`.
- `sync/motor-de-sincronizacion`: resultado de la anulación; estado de la jornada.
- `ruta/area-de-ruta`: anular; anulaciones en pantallas; jornada no abierta.
- `sistema/ayuda-contextual`: ayudas nuevas y revisadas.

## Impact

Backend: `ventas/commands.py`, `ventas/service.py`, `ventas/domain/`, `stock/service.py`, pruebas de integración y concurrencia; sin migración ni permisos nuevos. Frontend: `lib/dispositivo/db.ts` (v4), `sync/`, `domain/ruta/`, `domain/ventas/notaDesdeLocal.ts`, `areas/ruta/`, `ayuda/textos.ts`, `api/schema.gen.ts`. `shared/fixtures/sync/`. Docs al archivar.
