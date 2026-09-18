# ADR-009 — Modo impositivo por organización y modalidad de IVA al facturar

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §16, `docs/03` §4 |

## Contexto

La organización inicial trabaja con listas sin IVA (modo A). Otras organizaciones pueden trabajar con IVA incluido en la venta o en el precio. Al facturar sobre ventas sin IVA, la distribuidora necesita poder elegir si el IVA lo paga el cliente o lo absorbe la empresa.

## Decisión

**Modo impositivo por organización:** A (precio neto, IVA solo en factura), B (precio neto + IVA en la venta), C (precio con IVA incluido). Los modos B y C son operativos en la etapa 4; el modelo los soporta desde la etapa 1.

**Modalidad de IVA al facturar (solo modo A):** CLIENTE (la factura genera un débito de IVA en la cuenta corriente) o ABSORBIDO (el saldo del cliente no cambia; la utilidad se reduce con un ajuste distribuido por línea). Cascada: organización → cliente → factura. Cambiar a ABSORBIDO respecto del default requiere permiso `FACTURAR_ABSORBIENDO_IVA`.

La utilidad es siempre neta de IVA: `venta neta − costo congelado − IVA absorbido asignado`.

## Consecuencias

- El IVA absorbido se registra en `ajuste_iva_absorbido` y nunca modifica los valores congelados de la venta (INV-10).
- El IVA del módulo de facturación se calcula por alícuota, no con una tasa global.
- Validar con el contador de la organización qué pasa fiscalmente cuando un cliente pide factura y si el IVA se cobra encima o se absorbe.
