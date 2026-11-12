## Qué resuelve este change

Crea el maestro de proveedores y la carga de costos informados (cualquier presentación de compra, con o sin IVA y bonificación, con vigencia e historial y costo base derivado), escritos solo por comandos del bus. Salda la deuda del change 05: `producto.proveedor_id` pasa a obligatorio con FK compuesta.

## Why

Precios (13) parte del costo informado vigente (PRC-11), compras (11) lo compara (CMP-04) y la importación (10) carga proveedores y costos reales. CAT-01/CAT-06 siguen incumplidas (D1 del change 05) y deben cerrarse antes del change 10.

## What Changes

- **Tablas** (`03` §6): `proveedor` y `costo_informado` con FK compuestas; `costo_informado` de solo inserción para `app_runtime` (CST-03).
- **Deuda del 05** **[ALTA: migración de datos existentes]**: FK compuesta `producto → proveedor` (`NOT VALID` + `VALIDATE`), completar productos sin proveedor con un proveedor provisorio inactivo (B2) y `SET NOT NULL`.
- **Comandos** (solo `ONLINE`): `PROVEEDOR_CREAR`, `PROVEEDOR_MODIFICAR` (`GESTIONAR_PROVEEDORES`); `COSTO_INFORMAR` (`EDITAR_COSTOS`), con uno o varios costos de un proveedor en una sola operación (CST-05). **BREAKING (contrato interno):** `PRODUCTO_CREAR` y `PRODUCTO_MODIFICAR` pasan a versión 2 con `proveedor_id` obligatorio; se retira la v1 (`design.md` D6).
- **Cálculo CST-02** en Python y TypeScript con casos compartidos (vista previa en el formulario; el servidor decide).
- **Consultas**: proveedores paginados; costo vigente a una fecha (CST-03) e historial por producto (`VER_COSTOS`), también expuestos por `proveedores/service.py` para el change 13.
- **Pantallas** `/admin/proveedores` (ficha, carga de costos, historial) y selector de proveedor en el formulario de producto.

## Decisiones resueltas (antes bloqueantes)

Opciones y detalle en `design.md`. Todas aprobadas por el usuario el 2026-09-23 con la opción A:

- **B1 — Un costo informado "usa" la presentación y congela sus unidades (INV-18):** `proveedores` registra su verificador en el puerto de ADR-023. (D1)
- **B2 — Productos existentes sin proveedor:** la migración crea un proveedor "Proveedor a asignar" inactivo por organización afectada, se lo asigna y aplica `NOT NULL`; el `downgrade` lo revierte. (D2)
- **B3 — El costo debe venir del proveedor actual del producto;** si no, `PROVEEDOR_NO_CORRESPONDE`. (D3)
- **B4 — Misma vigencia desde:** prevalece el registrado último. (D4)
- **B5 — Un proveedor con productos activos no se desactiva** (`PROVEEDOR_CON_PRODUCTOS_ACTIVOS`); un proveedor inactivo no se asigna de nuevo ni recibe costos. ADR-026 (*Propuesto*). (D5)
- **B6 — Nombre obligatorio y único por organización; CUIT opcional, 11 dígitos, único cuando existe, sin dígito verificador.** (D7)
- **B7 — `GET /proveedores` (`GESTIONAR_PROVEEDORES`) y `GET /proveedores/opciones` (solo activos, `id` y `nombre`; `GESTIONAR_CATALOGO`).** (D8)
- **B8 — `catalogo` valida el proveedor con FK compuesta y un puerto de consulta que falla cerrado.** ADR-025 (*Propuesto*). (D9)

## No incluye

- Saldo y cuenta corriente del proveedor: change 08 (CC-04).
- Compras, CMP-04 y su verificador de uso: change 11. Pagos: change 12.
- Uso del costo en listas (PRC-11, PRC-17): change 13. Costo promedio: change 09 (CST-04: el costo informado no costea ventas).
- Importación masiva desde planillas: change 10 (CST-05 etapa 2).
- Varios proveedores por producto (CAT-06, etapa 4).

## Invariantes

- **INV-01**: `COSTO_INFORMAR` con varios costos se registra completo o no (transacción del bus; prueba con el último ítem inválido).
- **INV-02 / INV-21**: tablas en los ratchets de esquema y de aislamiento; FK compuestas; recurso ajeno → 404.
- **INV-03**: `numeric(14,2)`, `numeric(18,6)`, `numeric(9,6)`; importes y porcentajes como string en JSON.
- **INV-06**: reenvíos idénticos no duplican costos ni proveedores.
- **INV-18**: `proveedores` registra su verificador (ADR-023, D1-A) con una prueba que lo cita.

## Capabilities

### New Capabilities
- `proveedores/fichas-de-proveedor`: alta, modificación, desactivación y consulta de proveedores.
- `proveedores/costos-informados`: registro de costos (CST-01..05), costo base derivado, vigencia, historial.
- `proveedores/administracion-de-proveedores`: pantallas de `/admin` para proveedores y costos.

### Modified Capabilities
- `catalogo/productos-y-presentaciones`: el proveedor pasa a obligatorio y validado (CAT-01, CAT-06).
- `catalogo/administracion-de-catalogo`: el formulario de producto exige elegir proveedor.

## Impact

- Backend: módulo `proveedores/`; dos revisiones de Alembic; `catalogo` (comandos v2, puerto de proveedor); import-linter.
- Frontend: `features/proveedores/`, `areas/admin/proveedores/`, `domain/proveedores/costoBase.ts`, `ProductoFormScreen.tsx`.
- Fixtures compartidos: **agrega** `shared/fixtures/calculo/cst-02-costo-base.json` (ejemplos de `01` §6.1 más bordes); no modifica los existentes.
- Docs: `04-roadmap-changes.md`; `03` §6 con las unicidades de B6 y el índice de B4; ADR-025 (B8) y ADR-026 (B5), redactados en estado *Propuesto*.
