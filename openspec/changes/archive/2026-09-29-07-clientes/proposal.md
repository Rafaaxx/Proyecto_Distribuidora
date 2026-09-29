# Change 07-clientes

## Qué resuelve este change

Crea el maestro de clientes: ficha completa (CLI-01), estados `ACTIVO`, `SUSPENDIDO` e `INACTIVO` (CLI-02) sin baja física, lista asignada y campos de crédito **guardados sin evaluarse**, más el cliente genérico "consumidor final" (CLI-03). Toda escritura pasa por el bus de comandos (`02` §6.5, SYN-06).

## Why

No hay venta (VTA-10), cobranza (COB-01), cuenta corriente (CC-01), bootstrap de dispositivo (SYN-11) ni evaluación de crédito (CRE-01) sin clientes: los changes 08, 10, 17, 18a, 18b y 21 dependen de este (`04` §4). Es además el primer maestro que nace con los permisos efectivos de `GET /api/v1/yo` (ADR-027).

## What Changes

- **Tabla `cliente`** (`03` §10) con FK compuesta a organización y unicidades. Sin columna de saldo (CC-04, llega en el 08).
- **Comandos** (los tres `ONLINE`, `admite_offline=False`, `operation_id` obligatorio, plantilla D7 de `04`): `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` (`GESTIONAR_CLIENTES`; ficha sin campos de crédito) y `CLIENTE_CREDITO_MODIFICAR` (`GESTIONAR_CREDITO`: límite, política y tolerancia, auditado según AUD-01).
- **Estados** validados contra la máquina de `01` §18: `ACTIVO ↔ SUSPENDIDO` y `ACTIVO/SUSPENDIDO ↔ INACTIVO`. Ninguna baja física (CLI-04, INV-05).
- **Crédito sin evaluación**: se guardan y se muestran `limite_credito` (nulo = sin control, CRE-01), `politica_credito` (nulo = la de la organización, CRE-03) y `tolerancia_offline_tipo`/`_valor` (nulos = los de la organización, CRE-06). Ningún cálculo de disponible, exceso ni resolución: es del 18b.
- **Consumidor final** (CLI-03) con `es_consumidor_final` y `limite_credito = 0`, apuntado desde `configuracion_organizacion.cliente_consumidor_final_id` (`03` §4).
- **Consultas**: `GET /api/v1/clientes` (cursor, filtros por texto y estado) y `GET /api/v1/clientes/{cliente_id}`.
- **Pantallas** `/admin/clientes` con `usePermisos()` y `<SiTienePermiso>` (ADR-027, ADR-028); la edición de crédito es pantalla propia, como la carga de costos del 06.
- **Servicio reutilizable fila por fila** para la importación del change 10, como el 06 dejó el de proveedores.

## Decisiones

Detalle, alternativas y consecuencias en `design.md`.

- **D1 — Identidad:** `codigo` y `(documento_tipo, documento_numero)` únicos por organización cuando existen; el **nombre no es único** (a diferencia de `proveedor`, D7 del 06). **A confirmar.**
- **D2 — Lista asignada antes del 13:** `lista_precio_id` sin FK ni validación de existencia; la FK compuesta se agrega en el 13, como el 06 hizo con `producto.proveedor_id` (ADR-025). **A confirmar.**
- **D3 — Permisos:** `GESTIONAR_CLIENTES` para la ficha, `GESTIONAR_CREDITO` para el crédito, en comandos separados. **A confirmar.**
- **D4 — Consumidor final:** comando propio `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` que crea el cliente y fija la configuración de organización en la misma transacción. `docs/` no resuelve cómo nace ni qué permiso lo gobierna: **pendiente de ADR.**
- **D5 — `condicion_iva`:** no se crea en este change; `01` §16 y FAC-04 no definen su dominio y la facturación es otro módulo. **A confirmar.**
- **D6 — `tolerancia_offline_valor`:** mismo tipo que la organización (`numeric(14,2)`); su interpretación como porcentaje queda para el 18b. **A confirmar.**

## No incluye

Saldo, cuenta corriente y pago aplicado (08, CC-01 a CC-07); evaluación de crédito con políticas, tolerancia aplicada y PIN de supervisor (18b, CRE-01 a CRE-10); listas de precios (13, PRC-20); importación masiva desde planillas (10); bootstrap del dispositivo (21, SYN-11); `condicion_iva` y facturación. La comprobación de que un cliente sin operaciones no puede pasar a `INACTIVO` (CLI-02) queda sin verificar: necesita operaciones, que llegan en 10, 17 y 18a.

## Invariantes

**INV-01** cada comando es una transacción del bus y **INV-06** los tres son idempotentes por `operation_id`. **INV-02 / INV-21** `organizacion_id NOT NULL`, `UNIQUE (organizacion_id, id)`, FK compuesta y cliente ajeno responde 404, con las rutas sumadas al ratchet de aislamiento y `test_inv21_aislamiento_endpoints_clientes.py`. **INV-03** `limite_credito` y `tolerancia_offline_valor` en `numeric(14,2)`, `Decimal` en Python, string en JSON, `decimal.js` al formatear. **INV-05** sin `DELETE` sobre `cliente`. **AUD-01** los cambios de crédito se auditan con valor anterior y nuevo. **Fixtures compartidos** (`02` §10): no toca precios, descuentos ni costos, así que no agrega ni modifica ninguno.

## Capabilities

### New Capabilities

- `clientes/fichas-de-cliente` — alta, edición, estados y consulta (CLI-01, CLI-02, CLI-04, `01` §18, GESTIONAR_CLIENTES).
- `clientes/datos-de-credito` — límite, política y tolerancia por cliente, guardados y auditados, sin evaluación (CRE-01, CRE-03, CRE-06, GESTIONAR_CREDITO, AUD-01).
- `clientes/consumidor-final` — cliente genérico con límite cero y su habilitación por organización (CLI-03).
- `clientes/administracion-de-clientes` — pantallas de `/admin/clientes` con permisos efectivos (ADR-027, ADR-028).

### Modified Capabilities

Ninguna: `02` §6.5 ya cubre con texto genérico las altas y modificaciones de maestros, y `organizacion/parametros-de-organizacion` no cambia porque el seed sigue dejando `permite_consumidor_final` y `cliente_consumidor_final_id` sin definir.

## Impact

Módulo nuevo `backend/app/modules/clientes/`, migración Alembic de `cliente`, tres tipos de comando con sus handlers, registro en `main.py`, contratos de `import-linter`, `service.py` de `organizacion` extendido para el consumidor final. En el frontend, `frontend/src/areas/admin/clientes/` (lista, ficha, crédito), sección en `secciones.ts` y ruta diferida en `AdminScreen.tsx`. Pruebas unitarias de la máquina de estados y del crédito, integración de aislamiento, idempotencia y auditoría, y ampliación de los ratchets de permiso por ruta, bus, aislamiento y repositorios.
