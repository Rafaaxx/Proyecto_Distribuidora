# Change 22a-cola-confirmacion-local

## Qué resuelve este change

El vendedor confirma una venta en `/ruta`, con o sin señal: la venta, sus efectos locales y el comando en la cola se guardan en el teléfono en una sola transacción, la nota se comparte sin señal y cada venta muestra que todavía no se envió.

## Why

`04` §11 (fila 22a) y deudas de los changes 18a (consumidor final), 18b (PIN de supervisor local, crédito del dispositivo), 20 (nota desde Dexie, `00` §9 criterio 7), 20c (motivo dado de baja) y 21 (Dexie v3, guarda del carrito). Hoy `/ruta` solo consulta; sin cola, el 22b no tiene nada que enviar.

## What Changes

- **Base local v3** (`design.md` D3): tablas `ventas`, `cobranzas`, `movimientos_locales`, `cola` e `intentos_pin`; el bootstrap no las toca.
- **Confirmación local atómica** (D1, D2, D4): toda venta de `/ruta` se confirma en el teléfono y queda en la cola como `VENTA_CONFIRMAR` `OFFLINE` (UUIDv7 del cliente, número y secuencia asignados dentro de la misma transacción Dexie).
- **Reglas locales** (D5 a D9): saldo considerado = saldo del bootstrap + movimientos locales pendientes de la jornada (CRE-08); stock disponible igual (RUT-04), con la línea que lo supera bloqueada salvo `PERMITIR_STOCK_NEGATIVO` (D6); las reglas de la venta con conexión que el teléfono puede evaluar con sus datos; el consumidor final solo de contado (bloqueo, ADR-054 punto 24); crédito con la variante sin conexión (CRE-06, CRE-07).
- **PIN de supervisor local** (D10): derivación PBKDF2 en el teléfono contra la del bootstrap, con `intentos_pin_max` fallos y bloqueo hasta el próximo bootstrap (no por tiempo); el PIN nunca se guarda ni viaja.
- **Pantallas** (D12 a D14, D16): "Vender" (cliente, pedido, descuentos, cobro, crédito, autorización, confirmar), "Ventas de hoy" con su estado de envío, contador de pendientes en el inicio, guarda del carrito frente a la versión nueva y aviso al cerrar sesión con pendientes.
- **Nota sin señal** (D15): la venta local congela los datos de la nota; adaptador desde Dexie a la misma función de armado (ADR-059).
- **Motivo dado de baja** (D11): se cierra en el 22a sin código nuevo.
- **ADR-063** (*Propuesto*) y ayudas "(?)" nuevas (D17).

## Decisiones

`design.md` D0 a D17, **APROBADAS el 2026-10-31: A en todas salvo D6 = C y D10 = B**. De negocio (decide el usuario): D1, D6, D7, D8, D10, D11, D13, D14, D16. Gobernanza **ALTA** en D10 (PIN); **MEDIA** en el resto.

## No incluye

Envío de la cola, Web Locks, reintentos, aplicación de resultados, versión mínima de la aplicación (22b); conciliación de movimientos locales tras sincronizar, pantalla de conflictos, anulación sin conexión (22c); cobranza independiente sin conexión (23); cambios en el backend fuera de pruebas.

## Reglas e invariantes

- **VTA-01, VTA-06, VTA-07, VTA-11, VTA-12, VTA-13, CLI-02, CLI-03, PRC-20, PRC-21, DSC-06, CRE-04 a CRE-08, CRE-10, STK-05, STK-06, RUT-04, SYN-01, SYN-03, SYN-05, SYN-09, SYN-10, SEG-05, ADR-054, ADR-055, ADR-059, ADR-062.**
- **INV-01** (local): venta, cobranza, movimientos, cola, correlativo y secuencia, todo o nada en una transacción Dexie (prueba con falla inyectada). **INV-03/INV-04:** importes string, cantidades enteras. **INV-06:** reconfirmar no encola dos comandos (el doble envío al servidor es del 22b).
- **Sin cambios en reglas de cálculo:** no se agregan fixtures de cálculo (se usan `prc22`, `dsc05`, `dsc06`, `vta04`, `cre01`). Se agrega un **fixture de contrato** del sobre en `shared/fixtures/sync/`.

## Capabilities

### New Capabilities

- `sync/cola-local`: confirmación atómica, numeración, secuencia, sobre, estado de envío y saldo y stock locales.
- `ventas/venta-en-ruta`: pantalla de venta del teléfono y reglas que aplica antes de encolar.

### Modified Capabilities

- `sync/base-local`: versión 3 con las tablas de operaciones que el bootstrap no toca.
- `identidad/pin-de-autorizacion`: verificación local con límite de intentos.
- `ventas/nota-de-venta`: nota desde la base local y compartida sin señal.
- `sistema/aplicacion-instalable`: la versión nueva no se aplica con un carrito abierto.
- `ruta/area-de-ruta`: pendientes en el inicio, "Ventas de hoy" y cierre de sesión con pendientes.

## Impact

Frontend: `lib/dispositivo/db.ts`, `sync/`, `domain/ruta/`, `lib/sesionLocal/`, `areas/ruta/`, `ayuda/textos.ts`. Backend: solo una prueba de contrato del sobre (`shared/fixtures/sync/`); sin migración ni endpoint. Sin dependencias nuevas.
