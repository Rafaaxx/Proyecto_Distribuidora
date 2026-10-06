# Verificación manual — 12-pagos-a-proveedores

Tarea 13.2. Probado por el usuario en el navegador el 2026-10-06, como administrador, sobre el entorno local (`docker compose up`). El change no agregó dependencias, así que no hizo falta reconstruir las imágenes (13.1).

## Resultado

| # | Caso | Resultado |
| --- | --- | --- |
| 1 | Compra a crédito y saldo "Le debemos" en la cuenta corriente | OK |
| 2 | Pago parcial con dos medios: saldo actual y resultante, faltante de medios, referencia obligatoria | OK |
| 3 | Pago mayor que la deuda, con su confirmación de saldo a nuestro favor | OK |
| 4 | Aviso de saldo a favor en "Nueva compra" y compra a crédito posterior que lo absorbe | OK |
| 5 | Anulación de un pago con motivo | OK |
| 6 | Listado de pagos con sus filtros | OK |
| 7 | Compra de contado y su pago de origen compra | OK |
| 8 | Intento de anular el pago de una compra vigente | OK |
| 9 | Compra de contado anulada sin devolución del pago | OK |
| 10 | Anulación posterior del pago de esa compra | OK |
| 11 | Enlaces del estado de cuenta a pagos y compras | OK |
| 12 | Pago a un proveedor inactivo desde su cuenta corriente | OK |
| 13 | Usuario con solo `REGISTRAR_PAGO_PROVEEDOR` | No verificado a mano |
| 14 | Usuario sin permisos de pago | No verificado a mano |

## Casos 13 y 14: no verificados a mano

La aplicación no tiene pantalla ni endpoint para crear usuarios o roles, así que no se pudo armar un usuario con permisos recortados. El usuario aceptó cerrarlos con la cobertura automática:

- Backend: `tests/integration/test_ratchet_permiso_por_ruta.py` (permiso exigido por cada ruta de pagos) y `tests/integration/test_pagos_proveedor_api.py` (403 sin efectos al registrar, anular y listar sin el permiso).
- Frontend: `tests/unit/areas/admin/pagos-proveedores/rutas.test.tsx` (menú, listado, "Nuevo pago" y aviso de falta de permiso según los permisos), `PagoFormScreen.test.tsx`, `PagoDetalleScreen.test.tsx` y `tests/unit/areas/admin/cuentas-corrientes/CuentaCorrienteScreen.test.tsx` ("Registrar pago" y enlaces de los movimientos según los permisos).

## Observaciones

- El estado de cuenta lista los movimientos en orden ascendente, así que los últimos quedan al final. Es el orden que fija ADR-034 (change 08), no un defecto de este change. El usuario preferiría verlos en orden descendente; queda como ajuste aparte, con su ADR, fuera del change 12.
