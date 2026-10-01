# ADR-039 — Reparto entre `stock` y `costeo`, orden de bloqueo, filas perezosas de saldo y de costo con promedio nulo sin ingresos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-30 |
| Referenciado en | `openspec/changes/09-stock-y-costeo/design.md` D9, D10 y D12 y `specs/stock/libro-de-stock`, `specs/costeo/costo-promedio`; `01-dominio.md` CST-10 a CST-14 y STK-04 a STK-05; `02-arquitectura.md` §5.3 y §7.2 a §7.6; `03-modelo-de-datos.md` §2.3, §7 y §9; ADR-002 (promedio ponderado móvil); ADR-015 (orden de bloqueo); ADR-035 (clave de `saldo_cuenta`) |

**Decisiones D9 y D10 (opción A en cada una) aprobadas por el usuario el 2026-09-30, con D12 (columnas de los libros) en lo que afecta a `jornada_id`. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

`02` §5.3 define `stock ──► catalogo, costeo` y `costeo` sin dependencias de negocio; `02` §7.2 y §7.3 fijan el orden global de bloqueo `saldo_cuenta → costo_producto → stock_saldo → jornada` y ADR-015 pide que los handlers no bloqueen filas y usen funciones de servicios. Lo que `docs/` no resuelve: quién expone cada operación, cómo nacen las filas de saldo y de costo, y cuál es el promedio de un producto sin ingresos (ADR-002 afirma "siempre hay un promedio vigente"). Además `03` §2.3 nombra solo a `saldo_cuenta` como tabla de saldo sin `id`, y `03` §9 no detalla las columnas de operación de `stock_movimiento`.

## Decisión

1. **Dos módulos.** `costeo/service.py` (sin dependencias de negocio) ofrece `bloquear_costos(productos)`, `aplicar_ingreso(...)` (CST-11 más la fila de `costo_producto_mov` y `stock_total`), `aplicar_egreso(...)` (solo `stock_total`; devuelve el promedio vigente con el que valorizar), `obtener_promedio` y `obtener_costo`. `stock/service.py` ofrece `registrar_movimientos(lineas)` como **único camino** para cambiar stock: reúne todos los pares, toma las ubicaciones `FOR SHARE`, llama a `costeo.bloquear_costos` y **recién después** bloquea `stock_saldo` por `(producto_id, ubicacion_id)` ascendentes; solo entonces decide e inserta. `STOCK_INICIAL_REGISTRAR`, las ubicaciones y el kardex viven en `stock`. Quien necesite `saldo_cuenta` (changes 11 y 18a) lo bloquea antes de llamar a `stock`. El producto se valida por FK compuesta (404) y su estado, por `catalogo/service.py`.
2. **Dependencias de módulos.** `stock -> catalogo, costeo` (ya en `02` §5.3) y **`catalogo -> costeo`** (nueva, ADR-036 punto 5: la ruta del costo vive en `catalogo`). `costeo` no importa ningún módulo de negocio y `stock.domain` y `costeo.domain` no importan infraestructura; los contratos de import-linter lo verifican y prohíben la inversa. No hay ciclo.
3. **Egresos.** Un egreso se aplica con `UPDATE stock_saldo SET cantidad_base = cantidad_base - :q WHERE ... AND cantidad_base >= :q RETURNING` (`02` §7.4) y se valoriza al promedio vigente sin cambiarlo (CST-12). Ningún camino de este change deja saldo negativo. `stock_total` cambia con **todo** movimiento del producto; `costo_producto_mov` solo con los que recalculan o deben dejar historia (CST-13).
4. **Filas perezosas.** Las filas de `stock_saldo` y de `costo_producto` nacen con el primer movimiento (`INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`), como `saldo_cuenta` (ADR-035). Dos primeros movimientos simultáneos dejan una sola fila de cada una.
5. **Sin `id`.** `stock_saldo` (PK `(organizacion_id, producto_id, ubicacion_id)`) y `costo_producto` (PK `(organizacion_id, producto_id)`) no tienen `id`: ninguna tabla referencia una fila de saldo y la clave natural empieza por `organizacion_id` (INV-02). Es la aplicación de ADR-035 punto 6, anticipado para estas dos tablas; `03` §2.3 pasa a nombrarlas.
6. **Promedio nulo sin ingresos.** `costo_producto.costo_promedio` es **nulo** hasta el primer ingreso con costo (`CHECK (costo_promedio IS NULL OR costo_promedio > 0)`); `stock_total integer NOT NULL DEFAULT 0`. "Sin costo" es distinguible de "costo cero". Esto **matiza ADR-002**: "siempre hay un promedio vigente" vale desde el primer ingreso. La lectura de un producto sin ingresos responde 200 con `costo_promedio` nulo. **Cómo costea una venta sin promedio lo decide el change 18a** (quedó como deuda nominada).
7. **Columnas de los libros (D12).** `stock_movimiento` lleva las columnas de operación completas, con `dispositivo_id uuid NOT NULL` y FK compuestas a `producto`, `ubicacion`, `usuario`, `dispositivo` y `motivo` (opcional). `jornada_id` es nulable y **sin FK** hasta el change 15, que crea `jornada` (mismo trato que `comando.jornada_id`; deuda nominada). `origen_tipo` y `origen_id` son genéricos, sin FK (`03` §9).
8. **Tipos de movimiento.** La base acepta los nueve tipos de la etapa 1 de STK-03 en `stock_movimiento.tipo` y los cuatro orígenes de `03` §7 en `costo_producto_mov.origen_tipo`; solo `STOCK_INICIAL` tiene comando en este change. Los changes 11, 14, 15, 18a y 19 no migran el libro.

## Consecuencias

- La regla "ninguna otra parte calcula costos" (CST-14) queda en `costeo`; el bloqueo en el orden de `02` §7.3 queda en una sola función, que es lo que hace posible probarlo (concurrencia con productos en orden inverso).
- Quien agregue un movimiento de otro tipo (compras, ventas, transferencias, ajustes, rendiciones) **debe** pasar por `registrar_movimientos`; no puede bloquear filas por su cuenta (ADR-015).
- Un ingreso de un tipo sin reglas de costo definidas (ajuste, transferencia, rendición) se rechaza en `registrar_movimientos` hasta que el change dueño lo defina (changes 14, 15 y 24).
- La verificación de consistencia (`stock_saldo` contra la suma SQL del libro y `stock_total` contra la suma de los saldos, `02` §7.6) queda disponible como consulta; programarla es del change 28.
- El change 15 debe agregar la FK de `stock_movimiento.jornada_id` (con datos existentes) y aplicar STK-09; el 18a debe decidir el costo de una venta sin promedio; el 11 debe decidir qué queda en la historia de costo de una `ANULACION_COMPRA` con `recalculado = false`.
- `costo_producto_mov.promedio_anterior` es nulo en el primer ingreso (no hay promedio previo); `03` §7 lo aclara.

## Alternativas consideradas

- **Un helper transversal `core/bloqueos.py` que conozca las cuatro tablas:** descartada: `core` pasaría a depender de modelos de negocio.
- **Bloqueos consultivos (`pg_advisory_xact_lock`) por producto:** descartada: se aparta de ADR-015 y de `02` §7.3.
- **`costo_promedio NOT NULL DEFAULT 0`:** descartada: una venta anterior al primer ingreso quedaría con costo cero y utilidad inflada sin aviso.
- **Crear la fila de costo al dar de alta el producto, con migración para los existentes:** descartada: acopla `catalogo` a `costeo` (prohibido por `02` §5.3) o exige puertos.
- **`stock_saldo` y `costo_producto` con `id` y `UNIQUE (organizacion_id, producto_id, ...)`:** descartada: un `id` que nadie referencia y un índice más.
- **Seguir `03` §9 al pie de la letra sin `dispositivo_id`:** descartada: inconsistente con `cuenta_movimiento` y pierde la trazabilidad del dispositivo cuando lleguen las ventas de ruta.
