# ADR-003 — Límite de crédito y política de autorización

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §9.2 |

## Contexto

Los clientes compran a cuenta corriente. La distribuidora necesita controlar cuánto puede deber cada cliente, con distintos niveles de tolerancia según el cliente, y que los vendedores puedan operar sin conexión.

## Decisión

Política configurable con tres modos: ADVERTIR, AUTORIZAR y BLOQUEAR. Configurable por organización (default) y sobrescribible por cliente. Límite vacío = sin control; límite cero = solo contado.

Solo consume crédito la parte no cobrada de la venta.

**Online:** ADVERTIR acepta con observación; AUTORIZAR requiere usuario con `SUPERAR_CREDITO` o PIN de supervisor en el dispositivo; BLOQUEAR rechaza.

**Offline:** ADVERTIR funciona igual. AUTORIZAR usa una tolerancia configurable (importe o porcentaje del límite, por organización y cliente); si el exceso la supera, se bloquea salvo permiso propio o PIN. BLOQUEAR funciona igual.

El servidor recalcula al sincronizar y nunca rechaza por crédito. Si detecta exceso que el dispositivo no detectó, agrega observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración.

La evaluación se congela en la venta (límite, saldo considerado, disponible, exceso, política, resolución, autorizador).

## Consecuencias

- El saldo local al evaluar crédito offline puede diferir del saldo real (otros dispositivos, pagos registrados en oficina). Es un riesgo aceptado: con ubicación asignada por dispositivo (ADR-005) y un cliente atendido normalmente por un vendedor, el desvío es chico.
- La autorización remota (supervisor aprueba desde otra pantalla) queda para la etapa 2.
- Bloqueo por antigüedad de deuda queda para la etapa 2.

## Alternativas consideradas

- **Límite fijo sin excepciones:** demasiado rígido para la operación real en ruta.
- **Solo advertencia:** sin control real del riesgo crediticio.
