# Change 09-stock-y-costeo

## Qué resuelve este change

Crea las ubicaciones, el libro de stock (`stock_movimiento`, solo inserción) con su saldo bloqueable (`stock_saldo`), el costo promedio por producto (`costo_producto` con `stock_total`) con su historia (`costo_producto_mov`), el comando `STOCK_INICIAL_REGISTRAR` valorizado y el kardex. Es la base que escriben compras, transferencias, ventas y rendiciones.

## Why

`04` §3 ("los libros antes que sus operaciones") y `04` §4: 10, 11, 13, 14, 15 y 18a dependen de este change. Sin libro de stock no hay STK-04, sin promedio no hay costo congelado (VTA-05), y la puesta en marcha exige "stock inicial valorizado por ubicación" (`00` §6.1).

## What Changes

- **Tablas** `ubicacion`, `stock_saldo`, `stock_movimiento`, `costo_producto`, `costo_producto_mov` (`03` §7, §9) con FK compuestas, `integer` en cantidades base (INV-04), `numeric(18,6)` en costos (INV-03) y `GRANT` de solo `SELECT, INSERT` sobre los dos libros (ADR-020, INV-05).
- **Módulos nuevos** `stock` y `costeo` (`02` §5.1, §5.3: `stock ──► catalogo, costeo`; `costeo` sin dependencias de negocio).
- **`costeo/service.py`**: bloquear filas de costo en orden, recalcular el promedio de un ingreso (CST-10, CST-11) y registrar su historia (CST-13), mantener `stock_total` (`02` §7.2). Único lugar que calcula costos (CST-14).
- **`stock/service.py`**: registrar movimientos con las filas bloqueadas en el **orden global** (`02` §7.3, ADR-015: `costo_producto` antes que `stock_saldo`, por clave ascendente), leer saldos, kardex y consistencia. Es la interfaz que usarán 10, 11, 14, 15, 18a, 19 y 24.
- **Comandos** `UBICACION_CREAR`, `UBICACION_MODIFICAR` y `STOCK_INICIAL_REGISTRAR` (solo `ONLINE`, `02` §6.5), auditados (`01` §21, AUD-01).
- **Kardex** por producto y ubicación con saldo acumulado calculado en SQL (STK-04, `02` §11).
- **Pantallas** `/admin`: ubicaciones, stock por ubicación en cajas + unidades (CAT-08), kardex y stock inicial.
- **Fixtures compartidos**: se **agrega** `shared/fixtures/calculo/cst-11-costo-promedio.json` (casos de CST-11, incluido el ejemplo de `01` §6.2), ejecutado por pytest y Vitest como CST-02, antes de escribir el código del promedio (D14; hay una contradicción entre `CLAUDE.md` §4 y la spec `sistema/calculo-compartido` que D14 resuelve). CST-02 no cambia.

## Decisiones (aprobadas 2026-09-30)

Detalle en `design.md`. El usuario aprobó la opción A en D1 a D15. `docs/` no las resolvía: permisos de stock inicial (D1), de ubicaciones (D2) y de lectura de stock/kardex (D3); cuántos stock iniciales admite un producto y cómo se corrige uno mal cargado (D4); forma del contenido (D5) y costo admitido (D6); reglas de la ubicación (D7) y su desactivación (D8); reparto entre `stock` y `costeo` y el orden de bloqueo (D9); fila y promedio inicial de `costo_producto` (D10); kardex (D11); columnas de los libros (D12); catálogo de tipos (D13); fixtures de CST-11 (D14); frontend (D15). Queda abierta, para el change 10 y sin bloquear este, la duda de fechar el stock inicial al día de corte en la importación.

## No incluye

Compras y su anulación (11), transferencias y ajustes (14), jornadas y la validación de ubicación tomada STK-09 (15), ventas y costo congelado (18a), anulación de ventas (19), rendición (24), stock en el bootstrap (21), importación de stock inicial por planilla (10, reutiliza el servicio), tarea diaria de consistencia (28; aquí solo la consulta), verificador de uso de presentaciones (el stock inicial se carga en unidad base, D5).

## Invariantes

- **INV-12** (Hypothesis): saldo en la misma transacción que el movimiento, con la fila bloqueada; propiedad contra PostgreSQL real que compara `stock_saldo` con la suma SQL del libro y `stock_total` con la suma de `stock_saldo`.
- **INV-04**: `integer` en toda cantidad base, rechazo de no enteros en la API y prueba sobre el catálogo de columnas.
- **INV-05**: `app_runtime` sin `UPDATE`/`DELETE` sobre `stock_movimiento` y `costo_producto_mov`.
- **INV-01 / INV-06**: comando atómico (falla inyectada) e idempotente.
- **INV-02 / INV-21**: FK compuestas, PK compuestas que empiezan por `organizacion_id` (ADR-035 punto 6), rutas en los ratchets, 404 para lo ajeno.
- **INV-03**: `numeric` y strings en JSON.

## Capabilities

### New Capabilities

- `stock/ubicaciones`: alta, modificación y desactivación de ubicaciones (STK-02).
- `stock/libro-de-stock`: movimientos, saldo materializado, bloqueo en orden global e invariantes (STK-01, STK-03, STK-04, INV-04, INV-05, INV-12).
- `stock/stock-inicial`: comando de puesta en marcha valorizado (STK-03, CST-11, `01` §21).
- `stock/kardex`: consulta de movimientos con saldo acumulado (STK-04).
- `stock/administracion-de-stock`: pantallas de `/admin` (ADR-027).
- `costeo/costo-promedio`: promedio ponderado móvil, `stock_total` e historia (CST-10, CST-11, CST-13, CST-14, ADR-002).

### Modified Capabilities

Ninguna.

## Impact

Módulos nuevos `backend/app/modules/stock/` y `backend/app/modules/costeo/`, una migración, tres tipos de comando, contratos de import-linter, ampliación de ratchets e INV-02/INV-05. Frontend en `areas/admin/stock/` y `features/stock/`. `docs/03` §2.3/§9 y `01` §19 requieren actualización según lo que se apruebe (ADR en el grupo final).
