# Change 12-pagos-a-proveedores

## Qué resuelve este change

Registra pagos a proveedores independientes de una compra, con uno o más medios, que reducen el saldo general del proveedor. Permite anular un pago con permiso y motivo, por movimiento inverso y sin borrar nada.

## Why

`04` §7 (hito 3) y `00` §6.1. El change 11 dejó la deuda en la cuenta del proveedor, pero hoy solo se paga de contado, dentro de la compra: una compra a crédito queda como deuda para siempre.

## What Changes

- **Comando `PAGO_PROVEEDOR_REGISTRAR`** (solo `ONLINE`, `02` §6.5), en el módulo `proveedores`: proveedor, fecha, importe y uno o más medios activos cuya suma es el importe (PAG-01, INV-08), con referencia donde el medio la exige. Crea un `pago_proveedor` con `origen = INDEPENDIENTE` y registra `PAGO` (reduce) en la cuenta del proveedor (PAG-02, CC-03). No toca stock ni costos.
- **Comando `PAGO_PROVEEDOR_ANULAR`** (solo `ONLINE`): con `ANULAR_PAGO_PROVEEDOR` y motivo, pasa el pago a `ANULADA` y registra `ANULACION_PAGO` (aumenta) (PAG-03, TR-06).
- **Reutiliza el change 11 (ADR-043):** tablas `pago_proveedor` y `pago_proveedor_medio`, validación de medios, anulación del pago, tipos `PAGO` y `ANULACION_PAGO` del libro (ADR-034) y lectura de medios y motivos. Se generaliza, no se duplica.
- **Migración chica** (`design.md` D9): ámbito de motivo para anular pagos con sus motivos, observación opcional, coherencia de anulación e índices. Los datos existentes no se migran.
- **Lecturas:** listado y detalle de pagos (también los de origen `COMPRA`) y saldo del proveedor.
- **Pantallas `/admin`:** listado, alta con saldo actual y resultante, detalle y anulación; acceso desde la cuenta corriente; aviso de saldo a nuestro favor al cargar una compra.
- **Fixtures compartidos:** ninguno nuevo ni modificado. No se tocan precios, descuentos ni costos; la suma de medios es una igualdad exacta, sin redondeo.

## Decisiones abiertas (bloquean la implementación)

`design.md` D0 a D11, todas **PENDIENTES**, con opción A recomendada y ejemplo en pesos. Las tres que el change 11 dejó nominadas (`04` §7): **D1** motivo de anulación de un pago, **D2** si el pago de una compra de contado se anula por separado, **D3** pago mayor que la deuda y cómo se compensa el saldo a nuestro favor. Además, de negocio: D4 (fecha), D5 (proveedor inactivo), D6 (medios y observación), D7 (permisos de lectura), D8 (qué entrega "saldo de proveedor"), D11 (pantallas). Técnicas: D0, D9, D10. Requieren **ADR-046**.

## No incluye

Imputación de pagos a compras (PAG-02: saldo general), vencimientos, notas de crédito y débito de proveedor (CMP-09, etapa 2), orden de pago imprimible, pagos offline, reporte de saldos (change 26), cobranzas (change 17), caja (etapa 2), edición de pagos (TR-06).

## Invariantes

- **INV-08** (lo cierra este change para pagos): dominio, propiedad Hypothesis e integración.
- **INV-01:** pago y anulación atómicos (falla inyectada entre el pago y la cuenta).
- **INV-13:** propiedad contra PostgreSQL real con pagos y anulaciones aleatorias.
- **INV-05:** `app_runtime` sin `DELETE` sobre pagos.
- **INV-06 / INV-21:** idempotencia y 404 para lo ajeno.

## Capabilities

### New Capabilities

- `proveedores/pagos-a-proveedores`: registro del pago independiente, efecto en la cuenta y consultas (PAG-01, PAG-02, INV-08).
- `proveedores/anulacion-de-pagos`: anulación con permiso y motivo (PAG-03).
- `proveedores/administracion-de-pagos`: pantallas `/admin` de pagos.

### Modified Capabilities

- `organizacion/catalogos-configurables`: ámbito de motivo para anular pagos y sus motivos sembrados.
- `proveedores/administracion-de-compras`: aviso de saldo a nuestro favor al cargar una compra.

## Impact

`backend/app/modules/proveedores/` (pagos), `configuracion` (ámbito de motivo), una migración, dos tipos de comando, ratchets. Frontend en `areas/admin/pagos-proveedores/`, `features/pagos-proveedores/` y `domain/pagos-proveedores/`; ajustes en compras y cuenta corriente. Docs `01` §6.4, `02` §6.5, `03` §4 y §6, `04` y ADR-046 al cierre. Gobernanza **alta**: nada se implementa sin la tarea 0.1.
