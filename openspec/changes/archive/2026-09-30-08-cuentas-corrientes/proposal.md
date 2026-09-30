# Change 08-cuentas-corrientes

## Qué resuelve este change

Crea el libro de cuenta corriente de clientes y proveedores (`cuenta_movimiento`, solo inserción) y su saldo materializado y bloqueable (`saldo_cuenta`), el comando `SALDO_INICIAL_REGISTRAR` y el estado de cuenta con saldo acumulado. Es el libro que ventas, compras, cobranzas y pagos van a escribir después.

## Why

`04` §3 ("los libros antes que sus operaciones") y `04` §4: los changes 09, 12, 17 y 18a dependen de este. Sin libro no hay saldo (CC-04), ni crédito disponible (CRE-01), ni puesta en marcha con saldos iniciales (`00` §5).

## What Changes

- **Tablas** `cuenta_movimiento` y `saldo_cuenta` (`03` §12) con `organizacion_id`, `importe numeric(14,2) CHECK (> 0)`, `sentido` `AUMENTA`/`REDUCE`, `dispositivo_id uuid NOT NULL` (D14), índice de estado de cuenta y `GRANT` de solo `SELECT, INSERT` sobre el libro (ADR-020, INV-05).
- **`cuentas_corrientes/service.py`**: registrar un movimiento bloqueando antes la fila de saldo (`02` §7.3, primer nivel del orden global), leer el saldo y armar el estado de cuenta. Es la interfaz que usarán 11, 12, 17, 18a y 19.
- **Comando** `SALDO_INICIAL_REGISTRAR` (`ONLINE`, `02` §6.5) con ruta de escritura dedicada, auditado (`01` §21).
- **Estado de cuenta** de cliente y de proveedor: movimientos por `occurred_at` con saldo acumulado calculado en SQL al consultar (CC-07), paginado por cursor.
- **Pantallas** `/admin`: cuenta corriente desde la ficha del cliente y del proveedor, y formulario de saldo inicial.
- **CLI-06** se activa: un cliente `INACTIVO` con movimientos ya no se reactiva (D8).

## Decisiones (D1-D14 aprobadas, 2026-09-29)

Detalle en `design.md`. `docs/` no resolvía: permisos de escritura (D1) y lectura (D2), cuántos saldos iniciales admite una cuenta y cómo se corrige uno equivocado (D3), estados admitidos (D4), forma del contenido (D5), FK de la referencia polimórfica `entidad_id` (D6), ubicación de cada pieza según `02` §5.3 (D7), saldo inicial como "operación" para CLI-06 (D8), paginación (D9), fila de saldo (D10), clave de `saldo_cuenta` (D11), tipos habilitados (D12), frontend (D13) y si `cuenta_movimiento` agrega `dispositivo_id` (D14, nueva). El usuario aprobó la opción A en las 13 primeras y agregó D14. D1-D2, D3-D4-D8 y D6-D7-D11 se registran como ADR en el grupo 9, junto con las aclaraciones de `docs/01` §12.1 y `docs/03` §2.3/§12 que estas decisiones piden.

## No incluye

Ventas y su anulación (18a, 19), cobranzas (17), compras (11), pagos a proveedores (12): sus tipos de movimiento no se escriben acá. Evaluación de crédito (18b). Importación de saldos por planilla (10, reutiliza el servicio fila por fila). Saldo en el bootstrap (21, SYN-11). Tarea diaria de consistencia (`02` §7.6, change 28); este change deja la consulta. Ajustes y notas de cuenta corriente (etapa 2, CC-02). Estado de cuenta en PDF (etapa 2, CC-07).

## Invariantes

- **INV-13**: el saldo se actualiza en la misma transacción que el movimiento, con la fila bloqueada; una prueba de propiedades de Hypothesis compara `saldo_cuenta` con la suma SQL del libro.
- **INV-05**: `app_runtime` sin `UPDATE` ni `DELETE` sobre `cuenta_movimiento`, verificado por `test_inv05_dos_roles.py`.
- **INV-01 / INV-06**: comando atómico e idempotente por `operation_id`.
- **INV-02 / INV-21**: FK compuestas (D6), rutas en los ratchets, entidad ajena responde 404.
- **INV-03**: `numeric` y strings en JSON.

Fixtures compartidos: no toca precios, descuentos ni costos; no agrega ninguno.

## Capabilities

### New Capabilities

- `cuentas-corrientes/libro-de-cuenta-corriente`: movimientos, saldo materializado, bloqueo e invariantes (CC-01, CC-04, CC-06, INV-05, INV-13).
- `cuentas-corrientes/saldo-inicial`: comando de puesta en marcha (CC-02, CC-03, `01` §21).
- `cuentas-corrientes/estado-de-cuenta`: consulta con saldo acumulado (CC-07).
- `cuentas-corrientes/administracion-de-cuentas-corrientes`: pantallas de `/admin` (ADR-027).

### Modified Capabilities

- `clientes/fichas-de-cliente`: la reactivación de un `INACTIVO` se rechaza si su cuenta tiene movimientos (CLI-06, D8).

## Impact

Módulo nuevo `backend/app/modules/cuentas_corrientes/`, una migración, un tipo de comando, contratos de import-linter, rutas nuevas en `clientes/api.py` y `proveedores/api.py`, ampliación de ratchets. Frontend en `areas/admin/clientes/`, `areas/admin/proveedores/` y `features/cuentas-corrientes/`.
