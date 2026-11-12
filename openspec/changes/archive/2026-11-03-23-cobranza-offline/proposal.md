# Change 23-cobranza-offline

## Qué resuelve este change

El vendedor con `REGISTRAR_COBRANZA` cobra a un cliente desde el teléfono, con o sin señal: la cobranza se guarda y se encola en una sola transacción, baja enseguida el saldo y sube el crédito disponible locales, y «Sincronización» muestra cómo volvió.

## Why

`04` §11 (fila 23). El servidor acepta `COBRANZA_REGISTRAR` `OFFLINE` desde el change 17, pero `/ruta` no tiene dónde cobrar: ADR-052 (deuda 3) dejó al 23 la pantalla y la cola local, y ADR-065 (D2) le dejó decidir si una cobranza suelta rechazada sigue contando en el saldo local (deuda del 22c «al 23»).

## What Changes

- **Servidor** (D2): sin cambios de código. Fixture de contrato `shared/fixtures/sync/cobranza-registrar-offline.json` validado por el lote y por Vitest; pruebas de caracterización (lote con venta y cobranza, rechazos, doble envío); `codigos-de-sincronizacion.json` suma los rechazos y observaciones de la cobranza.
- **Teléfono** (D1, D3 a D6): la cobranza va siempre por la cola; reglas locales antes de encolar (INV-08, referencia, consumidor final, saldo a favor con confirmación); Dexie v5 (índices en `cobranzas`); cobranza local atómica; su efecto en el saldo local y la regla de la cobranza rechazada; resultado de la cobranza.
- **Corte** (D7): «Cobrar» se deshabilita con la jornada no abierta y por debajo de la versión mínima.
- **Pantallas** (D8 a D10): «Cobrar» (ficha e inicio), «Cobranza guardada», «Cobranzas de hoy», cobranzas en «Sincronización» y en lo pendiente. Sin comprobante (COB-06 es etapa 2).
- **Textos y ayuda** (D11, D12): rechazos y observaciones de la cobranza; claves nuevas y revisadas, sin ejemplos.
- **ADR-067** (*Propuesto*, creado con esta propuesta) y `propuesta-docs.md` (en el último lote).

## Decisiones

`design.md` D0 a D12, pendientes (tarea 0.1). Ninguna CRÍTICA. ALTAS: D2, D4, D6. De negocio: D0, D3, D4, D6, D7, D9. **Bloqueante:** sin 0.1 y 0.2 no empieza el apply. La que más conviene mirar: **D6** (la cobranza rechazada deja de contar), luego D4 (referencia obligatoria en el teléfono) y D7.

## No incluye

Anular una cobranza desde el teléfono (COB-05: solo con conexión, desde `/admin`); comprobante de cobranza (COB-06, etapa 2); cobrar a un cliente inactivo desde el teléfono (no está en el bootstrap; se cobra desde `/admin`); imputación a ventas (COB-03, etapa 4); cobranzas en la rendición (24); resolver cobranzas rechazadas (25); reenviar a mano un rechazado.

## Reglas e invariantes

- **COB-01 a COB-04, CC-04, CC-05, CRE-01, CRE-08, CLI-03, RUT-09, SYN-01 a SYN-07, SYN-09, SYN-10; `02` §6.4, §6.6, §13.2, §13.3.**
- **INV-08**: el teléfono no confirma si la suma de los medios no es el importe; el servidor lo rechaza como malformado.
- **INV-01**: la cobranza local es una transacción Dexie (cobranza, movimiento, comando, secuencia); el resultado se escribe en una transacción.
- **INV-06**: ni el reenvío ni el doble toque duplican la cobranza.
- **INV-17**: sin rechazos por reglas de negocio (prueba de caracterización).
- **INV-05**: nada se borra. **INV-21**: cliente o medio ajeno, rechazo sin efectos. **INV-03**: importes string con `decimal.js`.
- **Sin cambios en reglas de cálculo:** sin fixtures de cálculo. Contrato: nuevo `cobranza-registrar-offline.json`; se amplía `codigos-de-sincronizacion.json`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `sync/lote-de-comandos`: el sobre de cobranza del teléfono, fijado por contrato.
- `sync/cola-local`: cobranza local atómica y su efecto en el saldo local (con la regla del rechazo).
- `sync/base-local`: cobranzas sueltas en la base local (v5).
- `sync/motor-de-sincronizacion`: resultado de la cobranza.
- `ruta/area-de-ruta`: cobrar, cobranzas en pantallas, corte de «Cobrar».
- `sistema/ayuda-contextual`: ayudas nuevas y revisadas.

## Impact

Backend: solo pruebas (`tests/unit`, `tests/integration`, `tests/concurrency`); sin migración ni permisos nuevos. Frontend: `lib/dispositivo/db.ts` (v5), `sync/` (`registrarCobranzaLocal.ts` nuevo, `sobre.ts`, `aplicarResultados.ts`, `ventasPendientes.ts`), `domain/ruta/` (reglas de la cobranza, `disponiblesLocales.ts`, `textosDeSincronizacion.ts`, `avisoDeJornada.ts`), `areas/ruta/` (cobro, cobranza guardada, cobranzas de hoy, inicio, ficha, «Sincronización», sesión), `ayuda/textos.ts`. `shared/fixtures/sync/`. Docs al archivar.
