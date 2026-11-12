# Change 13-listas-de-precios

## Qué resuelve este change

Crea las listas de precios: reglas de margen con precedencia, redondeo, borrador generado desde los costos informados, publicación de versiones inmutables y resolución del precio vigente. Deja listo el bruto de línea (PRC-22) en Python y TypeScript.

## Why

`04` §7 (hito 3) y `00` §6.1 y §9 (criterio 3). Hay costos informados (change 06) pero ningún precio: la venta (18a) no puede resolver PRC-20 ni puede hacerse la validación con el cliente de `04` §7.

## What Changes

- **Módulo `precios`** con las cinco tablas de `03` §8 y una migración.
- **Listas** (PRC-01, PRC-14) con su redondeo y la sobrescritura por categoría, por comando.
- **Reglas de margen** (PRC-12, PRC-13): markup o margen bruto, con precedencia.
- **Cálculo del precio de referencia** (PRC-10, PRC-11, PRC-14 a PRC-16), puro y solo en el servidor.
- **`LISTA_GENERAR_BORRADOR`** (PRC-17): calcula el borrador, conserva los precios manuales y señala los de margen menor que el de la regla.
- **`LISTA_PUBLICAR` y `LISTA_ANULAR_VERSION`** (PRC-02 a PRC-06), con `PUBLICAR_LISTAS` y auditoría; estados derivados y versiones anteriores.
- **Resolución de precio** (PRC-20): lista del cliente o lista por defecto, versión vigente a un momento. Salda la deuda del change 07 (clave foránea de `cliente.lista_precio_id`).
- **Fixtures compartidos (nuevos):** `shared/fixtures/calculo/prc-22-bruto-de-linea.json`, con los ejemplos de `01` §7.3, ejecutados por pytest y Vitest **antes** de escribir el cálculo. Ninguno existente se modifica (`design.md` D10).
- **Pantallas `/admin/precios`:** listas, reglas, borrador, versiones.

## Decisiones abiertas (bloquean la implementación)

`design.md` D0 a D15, todas **APROBADAS (opción A) por el usuario el 2026-10-06**, con la opción A recomendada y ejemplo en pesos. Las tres deudas de `04` §7 que exigen ADR: **D1** cambio de presentación de referencia con precios publicados (change 05), **D2** costo de referencia con varias presentaciones de compra (change 06), **D3** costos vigentes con otra regla de IVA (change 11b). De negocio, además: D4 y D5 (borrador), D6 (vigencias), D7 (precio manual), D8 (reglas), D9 (redondeo), D11 (lista del cliente y por defecto), D12 (lecturas), D15 (pantallas). Técnicas: D0, D10, D13, D14. Requieren **ADR-047**.

## No incluye

Importador `PRECIOS` (deuda del change 10: D0 recomienda un `13b`); uso del precio en la venta, congelado por línea y `USAR_LISTA_ANTERIOR` (PRC-21, PRC-23: change 18a); bootstrap de precios (change 21); descuentos (change 16); modo impositivo C (etapa 4); programación masiva y duplicación de listas (etapa 2); precio por presentación (ADR-010).

## Invariantes

- **INV-11** (lo cierra este change): servicio, integración, concurrencia y propiedad que lo citan.
- **INV-01:** generar y publicar son atómicos (falla inyectada).
- **INV-02, INV-03, INV-06, INV-21:** claves compuestas, columnas exactas, idempotencia y 404 para lo ajeno.
- **INV-18:** las unidades de referencia de un precio publicado no cambian (D1).

## Capabilities

### New Capabilities

- `precios/listas-de-precios`: listas, redondeo y sobrescritura por categoría (PRC-01, PRC-14).
- `precios/reglas-de-margen`: reglas y precedencia (PRC-12, PRC-13).
- `precios/calculo-de-precios`: costo de referencia, margen y redondeo (PRC-10 a PRC-16).
- `precios/borrador-de-lista`: generación, precio manual y señales (PRC-17).
- `precios/versiones-de-lista`: publicación, anulación, vigencia e inmutabilidad (PRC-02 a PRC-06, INV-11).
- `precios/resolucion-de-precio`: lista aplicable, versión vigente y bruto de línea (PRC-20, PRC-22).
- `precios/administracion-de-listas`: pantallas `/admin`.

### Modified Capabilities

- `clientes/fichas-de-cliente`: la lista asignada se valida contra las listas de la organización.
- `clientes/administracion-de-clientes`: el formulario ofrece la lista asignada (requisito reemplazado).
- `organizacion/parametros-de-organizacion`: la lista por defecto se define por comando.

## Impact

`backend/app/modules/precios/` (nuevo), lecturas por lote en `catalogo` y `proveedores`, `clientes` e `identidad`, una migración, diez tipos de comando, import-linter y ratchets. Frontend en `areas/admin/precios/`, `features/precios/` y `domain/precios/`. Docs `01` §7 y §19, `02` §5.3 y §6.5, `03` §8, `04` y ADR-047 al cierre. Gobernanza **media**: cuatro lotes revisables; nada se implementa sin la tarea 0.1.
