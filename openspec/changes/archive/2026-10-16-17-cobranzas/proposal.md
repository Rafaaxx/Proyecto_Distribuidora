# Change 17-cobranzas

## Qué resuelve este change

Permite registrar cobranzas independientes de clientes con uno o varios medios y anularlas con motivo, con su crédito en la cuenta corriente (COB-01 a COB-05, CC-05, INV-08). Prepara el bus para el primer comando que admite `OFFLINE`: firma tipada, despacho por lote, permisos por comando, `PERMISO_REVOCADO` y `JORNADA_LIBERADA`.

## Why

`04` §8, fila 17; el 18a depende de este change. Hoy solo existen los permisos, los tipos `COBRANZA`/`ANULACION_COBRANZA` del libro (ADR-034) y el ámbito de motivo sin motivos. Cinco deudas nominadas (changes 05, 06b, 14 y 15; ADR-048 punto 5, ADR-049 punto 19) esperan al primer tipo `OFFLINE`.

## What Changes

- **Módulo `cobranzas`** (tablas `cobranza`, `cobranza_medio`, `cobranza_anulacion`, `03` §12) con `COBRANZA_REGISTRAR` v1 (`ONLINE` y `OFFLINE`) y `COBRANZA_ANULAR` v1 (solo `ONLINE`), por el bus; origen `INDEPENDIENTE` (el de `VENTA` lo usa el 18a).
- **Medios:** importe explícito y de 1 a 20 medios activos que suman el importe (INV-08), con la referencia que el medio exija; validación de medios compartida con los pagos a proveedores. Sin conexión, un medio inactivo o una referencia faltante no rechazan: se aceptan con las observaciones nuevas `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`, que indican la línea (enmienda `01` SYN-07, D13); con conexión se rechazan como en los pagos.
- **Cuenta corriente:** movimiento `COBRANZA` (reduce) y `ANULACION_COBRANZA` (aumenta) por `cuentas_corrientes/service.py`; saldo a favor admitido con confirmación en pantalla.
- **Motivos sembrados** del ámbito `ANULACION_COBRANZA`.
- **Bus (deudas):** firma tipada de los handlers y despacho por lote con sesión y reloj para todos los tipos registrados (también stock y jornadas); paso 4 de `02` §6.3 en el lote; `PERMISO_REVOCADO` (SYN-10); validación de la jornada del sobre en comandos `OFFLINE` y `JORNADA_LIBERADA` (RUT-09).
- **Lecturas:** listado y detalle de cobranzas, saldo del cliente y selector de clientes abiertos a `REGISTRAR_COBRANZA`.
- **Pantallas `/admin`:** área "Cobranzas" (listado, alta, detalle, anulación) y "Registrar cobranza" desde la cuenta corriente del cliente; ayuda contextual (ADR-051).

## Decisiones (bloqueantes)

`design.md` D0 a D20, **APROBADAS 2026-10-15: opción A en todas salvo D13 = C** (medio inactivo y referencia faltante sin conexión: aceptados con observación). **Pendiente:** la revisión de los textos de ayuda de D20 (tarea 0.2). De negocio y no resueltas en `docs/`: fecha de la cobranza (D3), estado del cliente y consumidor final (D4), saldo a favor (D5), motivos (D6), reglas de anulación (D7), jornada de una cobranza online (D8), qué hace el servidor con una cobranza offline en cada caso (D12, D13) y lecturas (D14). **Críticas:** permisos por comando en el lote (D10) y la foto de permisos (D11). Requieren **ADR-052** y enmiendan `01` SYN-07 (dos códigos).

**Contradicción de `docs/`:** `01` §19 dice que el vendedor ve el saldo "de sus clientes", pero `03` no asigna clientes a vendedores (D14).

## Tamaño

Supera `04` §2. D0 recomienda un solo change en cinco lotes, con el lote del bus aislado y cortable a `17b`.

## No incluye

Cobranza con la venta (18a) y su anulación al anular la venta (VTA-22, 19). Cola local y pantalla de `/ruta` (23). Saldo local (CRE-08). Comprobante (COB-06). Imputación (COB-03). Rendición (RUT-07, 24). Bandeja de observaciones (25). Reporte de saldos (26).

## Invariantes

- **INV-08:** cerrado para cobranzas: validación pura, prueba de propiedad y verificación con SQL.
- **CC-05 (parte cobranza):** la cobranza registra su propio crédito; el débito de la venta llega con el 18a.
- **INV-13:** movimiento y saldo en la misma transacción, con concurrencia real. **INV-05:** sin `DELETE`; `UPDATE` solo del estado. **INV-01, INV-02, INV-06, INV-21:** ratchets y doble envío. **INV-17:** la cobranza offline nunca se rechaza por reglas de negocio; un medio inactivo o una referencia faltante quedan como observación (D13-C).

## Capabilities

### New Capabilities

- `cobranzas/registro-de-cobranzas`: alta, medios, efecto en la cuenta, jornada y consultas (COB-01 a COB-04, INV-08, CC-05).
- `cobranzas/anulacion-de-cobranzas`: anulación con motivo (COB-05, CC-02).
- `cobranzas/administracion-de-cobranzas`: pantallas y lecturas de apoyo.

### Modified Capabilities

- `sistema/pipeline-de-comandos`: permisos por comando en ambos modos; firma tipada.
- `sync/lote-de-comandos`: `PERMISO_REVOCADO`, jornada del sobre, `JORNADA_LIBERADA`.
- `organizacion/catalogos-configurables`: motivos de anulación de cobranza.
- `cuentas-corrientes/administracion-de-cuentas-corrientes`: registrar cobranza desde la cuenta del cliente.
- `sistema/ayuda-contextual`: pantallas de cobranzas.

## Impact

Backend: módulo `cobranzas/`; `app/commands/registro.py` y 54 handlers (firma); `sync/service.py` y `sync/models.py` (dos códigos de observación); validación de medios movida a `configuracion`; `clientes/api.py`; import-linter; una migración (incluye ampliar `ck_observacion__codigo`). Frontend: `areas/admin/cobranzas/`, cuenta corriente, `ayuda/textos.ts`. Docs y ADR-052 al cierre. Gobernanza **media**, con piezas **críticas** (D10, D11) y **altas** (D12 a D15).
