# Propuesta de cambios a `docs/` — change 09-stock-y-costeo

> **Estado: aprobado y aplicado el 2026-09-30.** Este archivo es parte de la tarea 10.1: el texto exacto que se propone para `docs/01-dominio.md`, `docs/02-arquitectura.md`, `docs/03-modelo-de-datos.md` y, al archivar, `docs/04-roadmap-changes.md`. **Ninguno de esos archivos fue editado.** Cuando el usuario apruebe (o cambie) el texto, se aplica tal cual y se marca 10.1. Cada cambio refleja únicamente lo ya aprobado en `design.md` (D1 a D15 y la enmienda a D3 del 2026-09-30) y lo implementado; no agrega decisiones nuevas.
>
> Los ADR-036, ADR-037, ADR-038 y ADR-039 están escritos en `docs/adr/` con estado *Propuesto*; pasan a *Vigente* cuando el usuario apruebe su texto.

Prioridad de fuentes (`CLAUDE.md` §1): `docs/adr/` > `docs/00` a `docs/04`. Por eso los ADR se aprueban primero y estos documentos los reflejan.

| ADR | Decisiones | Tema |
| --- | --- | --- |
| ADR-036 | D1, D2, D3 y enmienda | Permisos de stock y lectura del costo promedio desde `catalogo` |
| ADR-037 | D4, D5, D6 | Reglas del stock inicial y su corrección (STK-10) |
| ADR-038 | D7, D8 | Reglas de la ubicación y su desactivación |
| ADR-039 | D9, D10, D12 | Reparto `stock`/`costeo`, bloqueo, filas perezosas y promedio nulo |

---

## 1. `docs/01-dominio.md` §6.2 — CST-12 alcanza a la corrección de stock inicial

Fuente: `design.md` D4, ADR-037 puntos 1 y 4.

**Antes:**

```markdown
| CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio. Los egresos por ajuste se valorizan al promedio vigente. | 1 |
```

**Después:**

```markdown
| CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio. Los egresos por ajuste, y los de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. | 1 |
```

## 2. `docs/01-dominio.md` §8.1 — agregar STK-10

Fuente: `design.md` D4, ADR-037.

**Antes** (fin de la tabla de §8.1):

```markdown
| STK-09 | Mientras una ubicación está tomada, solo la jornada que la tomó puede generar movimientos sobre ella, salvo la rendición y usuarios con `LIBERAR_UBICACION`, con auditoría. | 1 |

### 8.2 Jornada y rendición
```

**Después:**

```markdown
| STK-09 | Mientras una ubicación está tomada, solo la jornada que la tomó puede generar movimientos sobre ella, salvo la rendición y usuarios con `LIBERAR_UBICACION`, con auditoría. | 1 |
| STK-10 | Un producto admite varios `STOCK_INICIAL`, cada uno con su cantidad con signo distinta de cero. Uno positivo es un ingreso con costo (CST-11); uno negativo es una corrección: egresa al promedio vigente sin recalcularlo y no puede dejar negativo el saldo de la ubicación (`STOCK_INSUFICIENTE`, sin excepción por `PERMITIR_STOCK_NEGATIVO`). Se admiten solo mientras el producto no tenga en la organización movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES`). Un costo mal cargado se corrige llevando el stock total a cero y recargando. | 1 |

### 8.2 Jornada y rendición
```

## 3. `docs/01-dominio.md` §19 — anotar el uso de cuatro permisos

Fuente: `design.md` D1, D2, D3 y su enmienda, ADR-036.

Los permisos no cambian (no hay permiso nuevo). Solo se amplía el "Alcance" de cuatro filas para que la tabla diga para qué se usan hoy. `IMPORTAR_DATOS` ya dice "incluye registrar saldos iniciales, CC-08" (change 08).

**Antes:**

```markdown
| ADMIN_CONFIGURACION | Configuración de la organización | ✓ | | | | |
| IMPORTAR_DATOS | Importaciones y puesta en marcha (incluye registrar saldos iniciales, CC-08) | ✓ | | | | |
| VER_COSTOS | Ver costos | ✓ | ✓ | | | |
| TRANSFERIR_STOCK | Transferencias | ✓ | ✓ | ✓ | ✓ | |
```

**Después:**

```markdown
| ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02) | ✓ | | | | |
| IMPORTAR_DATOS | Importaciones y puesta en marcha (incluye registrar saldos iniciales, CC-08, y stock inicial, STK-10) | ✓ | | | | |
| VER_COSTOS | Ver costos (incluye el costo promedio de un producto y los costos del kardex y del stock) | ✓ | ✓ | | | |
| TRANSFERIR_STOCK | Transferencias; ver ubicaciones, stock por ubicación y kardex (sin costos) | ✓ | ✓ | ✓ | ✓ | |
```

## 4. `docs/01-dominio.md` §21 — efecto del stock inicial

Fuente: `design.md` D4, ADR-037.

**Antes:**

```markdown
| Stock inicial | + | Recalcula | — | — | — | Sí |
```

**Después:**

```markdown
| Stock inicial | + / − (corrección, STK-10) | Recalcula (+); no cambia (−) | — | — | — | Sí |
```

## 5. `docs/02-arquitectura.md` §5.3 — `catalogo` depende de `costeo`

Fuente: `design.md` enmienda a D3 (2026-09-30), ADR-036 punto 5, ADR-039 punto 2.

La ruta `GET /api/v1/catalogo/productos/{producto_id}/costo` vive en `catalogo` y llama a `costeo/service.py`, por lo que `catalogo` deja de estar "sin dependencias de negocio". No hay ciclo: `costeo` no importa a `catalogo`.

**Antes:**

```
precios ──► catalogo, proveedores (costos informados)
stock ──► catalogo, costeo
facturacion ──► ventas (lectura), cuentas_corrientes, costeo
sync ──► todos los módulos con comandos
auditoria, configuracion, identidad ◄── todos
cuentas_corrientes, costeo, catalogo ──► (sin dependencias de negocio)
```

**Después:**

```
precios ──► catalogo, proveedores (costos informados)
stock ──► catalogo, costeo
catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)
facturacion ──► ventas (lectura), cuentas_corrientes, costeo
sync ──► todos los módulos con comandos
auditoria, configuracion, identidad ◄── todos
cuentas_corrientes, costeo ──► (sin dependencias de negocio)
```

## 6. `docs/03-modelo-de-datos.md` §2.3 — excepción de las tablas de saldo sin `id`

Fuente: ADR-039 punto 5 (aplica ADR-035 punto 6).

**Antes:**

```markdown
Excepción: una tabla de saldo cuya clave natural es compuesta y que ninguna otra tabla referencia no lleva `id`; su clave primaria empieza por `organizacion_id` (INV-02). Hoy es el caso de `saldo_cuenta` (ADR-035).
```

**Después:**

```markdown
Excepción: una tabla de saldo cuya clave natural es compuesta y que ninguna otra tabla referencia no lleva `id`; su clave primaria empieza por `organizacion_id` (INV-02). Hoy es el caso de `saldo_cuenta` (ADR-035), `stock_saldo` y `costo_producto` (ADR-039).
```

## 7. `docs/03-modelo-de-datos.md` §7 — `costo_producto` y `costo_producto_mov`

Fuente: `design.md` D10, D12 y D13, ADR-039; migración `a8b9c0d1e2f3_stock_y_costeo.py`.

### 7.1 `costo_producto`

**Antes:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id` | `uuid` | PK compuesta |
| `costo_promedio` | `numeric(18,6)` | CST-10 |
| `stock_total` | `integer` | Suma de `stock_saldo` del producto |
| `actualizado_en` | `timestamptz` | |
```

**Después:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id` | `uuid` | PK compuesta (sin `id`, §2.3). FK compuesta `(organizacion_id, producto_id) → producto` |
| `costo_promedio` | `numeric(18,6)` | CST-10. **Nulo** hasta el primer ingreso con costo (ADR-039); `CHECK (costo_promedio IS NULL OR costo_promedio > 0)` |
| `stock_total` | `integer` | `NOT NULL DEFAULT 0`. Suma de `stock_saldo` del producto; cambia con todo movimiento |
| `actualizado_en` | `timestamptz` | |

La fila nace de forma perezosa con el primer movimiento del producto (`INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`).
```

### 7.2 `costo_producto_mov`

**Antes:**

```markdown
`id`, `organizacion_id`, `producto_id`, `origen_tipo` (`COMPRA`, `ANULACION_COMPRA`, `STOCK_INICIAL`, `ANULACION_VENTA`), `origen_id`, `cantidad` `integer`, `costo_ingreso` `numeric(18,6)`, `stock_anterior`, `promedio_anterior`, `stock_nuevo`, `promedio_nuevo`, `recalculado` `boolean` (falso cuando se mantuvo el promedio, CMP-06), `operation_id`, `registered_at`.
```

**Después:**

```markdown
`id`, `organizacion_id` (`UNIQUE (organizacion_id, id)`), `producto_id` (FK compuesta a `producto`), `origen_tipo` (`COMPRA`, `ANULACION_COMPRA`, `STOCK_INICIAL`, `ANULACION_VENTA`; `CHECK` de catálogo), `origen_id`, `cantidad` `integer`, `costo_ingreso` `numeric(18,6)`, `stock_anterior` `integer`, `promedio_anterior` `numeric(18,6)` (nulo en el primer ingreso del producto), `stock_nuevo` `integer`, `promedio_nuevo` `numeric(18,6)`, `recalculado` `boolean` (falso cuando se mantuvo el promedio, CMP-06), `operation_id`, `registered_at`. El usuario de aplicación solo tiene `SELECT` e `INSERT` (INV-05).
```

## 8. `docs/03-modelo-de-datos.md` §9 — `ubicacion`, `stock_saldo` y `stock_movimiento`

Fuente: `design.md` D7, D10, D12 y D13, ADR-038 y ADR-039.

### 8.1 `ubicacion`

**Antes:**

```markdown
`id`, `organizacion_id`, `nombre`, `tipo` (`DEPOSITO`, `VEHICULO`, `OTRO`), `requiere_toma` `boolean`, `activo` (STK-02).
```

**Después:**

```markdown
`id`, `organizacion_id`, `nombre`, `tipo` (`DEPOSITO`, `VEHICULO`, `OTRO`; `CHECK` de catálogo), `requiere_toma` `boolean`, `activo`, `creado_en`, `actualizado_en`, `actualizado_por_id` (STK-02; dato maestro, §2.3). `UNIQUE (organizacion_id, id)`. Restricciones: `ux_ubicacion__nombre` único sobre `(organizacion_id, lower(nombre))`, activas o no, y `CHECK (tipo <> 'VEHICULO' OR requiere_toma)` (ADR-038). El usuario de aplicación tiene `SELECT`, `INSERT` y `UPDATE`.
```

### 8.2 `stock_saldo`

**Antes:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id`, `ubicacion_id` | `uuid` | PK compuesta |
| `cantidad_base` | `integer` | Puede ser negativa (STK-05, STK-06) |
| `actualizado_en` | `timestamptz` | |
```

**Después:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id`, `ubicacion_id` | `uuid` | PK compuesta (sin `id`, §2.3). FK compuestas a `producto` y a `ubicacion` |
| `cantidad_base` | `integer` | `NOT NULL DEFAULT 0`. Puede ser negativa (STK-05, STK-06); ningún camino del change 09 la deja negativa |
| `actualizado_en` | `timestamptz` | |

La fila nace de forma perezosa con el primer movimiento del par (`INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`). El usuario de aplicación tiene `SELECT`, `INSERT` y `UPDATE`.
```

### 8.3 `stock_movimiento`

**Antes:**

```markdown
| `jornada_id`, `motivo_id` | `uuid` | Opcionales |
| Columnas de operación | | |

Índices: `(organizacion_id, producto_id, ubicacion_id, occurred_at)` para kardex y verificación de consistencia; `(organizacion_id, origen_tipo, origen_id)` para reversiones.
```

**Después:**

```markdown
| `jornada_id`, `motivo_id` | `uuid` | Opcionales. `motivo_id` con FK compuesta a `motivo`; **`jornada_id` sin FK** hasta que exista `jornada` (change 15, mismo trato que `comando.jornada_id`) |
| `operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at` | | Columnas de operación (§2.3), todas `NOT NULL`; `dispositivo_id` con FK compuesta a `dispositivo` y `usuario_id` a `usuario` |

`UNIQUE (organizacion_id, id)`; FK compuestas a `producto` y `ubicacion`; `CHECK` de catálogo en `tipo` (los nueve tipos de la etapa 1 de STK-03). El usuario de aplicación solo tiene `SELECT` e `INSERT` (INV-05).

Índices: `(organizacion_id, producto_id, ubicacion_id, occurred_at, id)` para kardex y verificación de consistencia; `(organizacion_id, origen_tipo, origen_id)` para reversiones.
```

## 9. `docs/03-modelo-de-datos.md` §16 — índice del kardex

Fuente: D12.

**Antes:**

```markdown
| Kardex de un producto | `stock_movimiento (organizacion_id, producto_id, ubicacion_id, occurred_at)` |
```

**Después:**

```markdown
| Kardex de un producto | `stock_movimiento (organizacion_id, producto_id, ubicacion_id, occurred_at, id)` |
```

---

## 10. Qué no cambia

- `docs/00`: sin cambios.
- `docs/01` CST-10, CST-11, CST-13, CST-14, STK-01 a STK-09: sin cambios (STK-05 sigue valiendo para los demás tipos; STK-10 fija la excepción de la corrección de stock inicial, sin `PERMITIR_STOCK_NEGATIVO`).
- `docs/02` §6.5 (`STOCK_INICIAL_REGISTRAR` solo online), §7.2 a §7.4 (orden de bloqueo y `UPDATE ... WHERE cantidad_base >= :q`): el código los cumple tal cual.
- `docs/03` §15 (INV-04 e INV-05 ya listan `integer` en cantidades y permisos sobre libros).

## 11. Notas de roadmap (para `docs/04-roadmap-changes.md`, al archivar, con confirmación del usuario)

Se insertan como párrafos nuevos debajo de la "Deuda nominada por el change 08 ... para el change 10", con el mismo formato que las demás deudas nominadas. La tabla de changes (`04` §3) y su dependencia de orden no cambian.

**Change 09 (`stock-y-costeo`) archivado:** *(redactar al archivar con la fecha, las specs sincronizadas y los ADR vigentes, como el párrafo del change 08)*.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 10 (`importacion-inicial`):** la importación de stock inicial reutiliza `stock/service.py::registrar_stock_inicial` fila por fila, con el permiso `IMPORTAR_DATOS` (ADR-036). Hereda STK-10 y ADR-037: varias filas por producto son válidas mientras el producto no tenga movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES` en caso contrario); el costo es una cadena decimal positiva con hasta 6 decimales (`COSTO_INVALIDO`); una ubicación o un producto ajeno o inexistente responde 404; uno inactivo, 409 (`UBICACION_INACTIVA`, `PRODUCTO_INACTIVO`). Cada fila rechazada se traduce a su número de fila en el informe de errores. Como `STOCK_INICIAL_REGISTRAR` es solo online, la importación corre en el servidor. **Pregunta abierta para ese change:** si la importación necesita fechar el stock inicial al día de corte, se reabre el momento del movimiento (hoy, el `occurred_at` del sobre), como D5-C del change 08.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 11 (`compras-y-deuda-proveedor`):** los ingresos y egresos de compra y de anulación de compra entran por `stock/service.py::registrar_movimientos` (único camino para cambiar stock, ADR-039), que toma el orden global de bloqueo; quien necesite `saldo_cuenta` lo bloquea antes de llamar. Queda **sin decidir** qué guarda `costo_producto_mov` en una `ANULACION_COMPRA` con `recalculado = false` (CMP-06): la tabla admite el origen y la columna, pero la regla de qué valores se registran al mantener el promedio es del change 11.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 15 (`jornadas`):** agregar la clave foránea compuesta de `stock_movimiento.jornada_id` a `jornada` (la columna nació nulable y sin FK, ADR-039 punto 7; el libro puede tener filas) y aplicar STK-09 en `stock/service.py::registrar_movimientos`. Un stock inicial en un vehículo con toma se acepta hoy sin jornada.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 18a (`venta-online-core`):** `costo_producto.costo_promedio` es nulo hasta el primer ingreso con costo (ADR-039 punto 6). El change 18a decide cómo costea una venta de un producto sin promedio (rechazarla, costo cero con observación u otra regla); `costeo/service.py::aplicar_egreso` devuelve `costo_valorizacion` nulo en ese caso y no decide por su cuenta.
