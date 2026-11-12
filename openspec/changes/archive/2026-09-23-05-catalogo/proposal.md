## Qué resuelve este change

Crea el catálogo (categorías, marcas, productos, presentaciones con su presentación de referencia), escrito solo por comandos del bus, con la primera pantalla real de `/admin` y la visualización de cantidades en cajas + unidades. Cierra CAT-03 e INV-18.

## Why

Es el primer change del Hito 2 y el primer maestro de negocio sobre el bus del change 04. Todo lo que sigue referencia un producto y una presentación: costos informados (06), stock (09), precios (13), descuentos (16) y ventas (18a). Si las unidades de una presentación o la presentación de referencia nacen sin sus garantías, los valores congelados de venta (INV-10, PRC-23) quedan apoyados sobre arena.

## What Changes

- **Tablas** de `03` §5: `categoria`, `marca`, `producto`, `presentacion`, con `organizacion_id`, `UNIQUE (organizacion_id, id)`, FK compuestas, `actualizado_en`/`actualizado_por_id` (`03` §2.3), `ux_producto__codigo` (CAT-01), `ux_presentacion__referencia` parcial (CAT-03), `ck_presentacion__referencia_venta` y `CHECK (unidades_base >= 1)` (CAT-02). `GRANT` sin `DELETE` (ADR-020, CAT-05).
- **Comandos** (`ENTIDAD_ACCION`, solo `ONLINE`, `02` §6.5): `CATEGORIA_CREAR`, `CATEGORIA_MODIFICAR`, `MARCA_CREAR`, `MARCA_MODIFICAR`, `PRODUCTO_CREAR` (con sus presentaciones iniciales), `PRODUCTO_MODIFICAR`, `PRESENTACION_AGREGAR`, `PRESENTACION_MODIFICAR`, `PRESENTACION_REFERENCIA_CAMBIAR`. Todos exigen `GESTIONAR_CATALOGO`.
- **Reglas de servicio**: exactamente una referencia activa y de venta por producto (CAT-03); unidades congeladas si la presentación fue usada (CAT-04, INV-18) mediante un puerto de "verificadores de uso" que los changes 06/11/18a poblarán; desactivar en lugar de borrar (CAT-05).
- **Consultas** con paginación por cursor (`02` §11): listado de productos con filtros, detalle con presentaciones, listados de categorías y marcas.
- **Listado de alícuotas** (agregado 2026-09-23, `design.md` D12): `GET /api/v1/configuracion/alicuotas`, de solo lectura, primer `api.py` de `configuracion`, para que el formulario de producto elija la alícuota de un selector.
- **Visualización CAT-08**: función pura en Python y TypeScript con casos compartidos en `shared/fixtures/calculo/`.
- **Pantalla `/admin/catalogo`**: listado, alta y edición de productos y presentaciones, categorías y marcas (TanStack Query + React Hook Form + Zod), con `Operation-Id` por escritura.

## Bloqueantes (decisiones que `docs/` no resuelve)

- **B1 — `producto.proveedor_id` sin tabla `proveedor`.** CAT-01/CAT-06 lo exigen obligatorio, pero `proveedor` llega en el change 06, que no es dependencia de este. Ver `design.md` D1. **Requiere decisión humana.**
- **B2 — Cómo sabe el catálogo que una presentación "fue usada".** Ninguna operación existe todavía y `catalogo` no puede depender de los módulos que la usan (`02` §5.3). Ver `design.md` D2. **Requiere confirmación.**

## No incluye

- Tabla y alta de proveedores, costos informados: change 06.
- Precios y su relación con el cambio de presentación de referencia: change 13 (deuda nominada, `design.md` D5).
- Aplicación de CAT-07 (venta de sueltas) y de "inactivos no se ofrecen" en operaciones: changes 18a y 21; aquí solo se expone el indicador `activo`.
- Importación masiva de productos: change 10. Códigos de barras y fotos: etapa posterior (`00` §6.1).
- Catálogo en Dexie / bootstrap: change 21.

## Invariantes

- **CAT-03**: índice único parcial (a lo sumo una) + validación de servicio (al menos una) + prueba de concurrencia con commits.
- **INV-18**: validación de servicio con verificadores de uso; prueba que lo cita por ID con un verificador que declara uso.
- **INV-02 / INV-21**: tablas en el ratchet estructural y rutas en el ratchet de aislamiento (otra organización → 404).
- **INV-03**: ninguna columna nueva es de punto flotante (la prueba existente recorre el catálogo de columnas).
- **INV-04**: `unidades_base` es `integer`.

## Capabilities

### New Capabilities
- `catalogo/categorias-y-marcas`: alta, modificación, activación y unicidad de nombre (CAT-01, TR-09).
- `catalogo/productos-y-presentaciones`: producto, presentaciones, referencia única, unidades congeladas, desactivación (CAT-01 a CAT-06, INV-18).
- `catalogo/visualizacion-de-cantidades`: cajas + unidades con signo (CAT-08), idéntica en Python y TypeScript.
- `catalogo/administracion-de-catalogo`: pantalla de `/admin` para gestionar el catálogo.

### Modified Capabilities
(ninguna: los ratchets de bus, aislamiento y permisos ya exigen cubrir rutas nuevas sin cambiar sus requisitos)

## Impact

- Backend: módulo nuevo `app/modules/catalogo/` (api, schemas, commands, queries, domain, models, repository, service), una revisión de Alembic, contratos de `import_linter`, registro de handlers en el arranque. En `configuracion`: `api.py`, `schemas.py`, `queries.py` nuevos y una función de listado paginado en `repository.py` (D12).
- Frontend: `features/catalogo/`, `features/configuracion/` (alícuotas, D12), ruta `/admin/catalogo`, `domain/catalogo/cantidades.ts`; tipos regenerados del OpenAPI.
- Fixtures compartidos: agrega `shared/fixtures/calculo/cat-08-visualizacion.json`. No toca precios, descuentos ni costos.
