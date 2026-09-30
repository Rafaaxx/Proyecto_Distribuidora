# Propuesta de cambios a `docs/` — change 08-cuentas-corrientes

> **Estado: aprobado y aplicado el 2026-09-30** (incluida la nota de §3.3 en `03` §2.3). Texto original:
>
> **Estado: pendiente de aprobación del usuario.** Este archivo es la tarea 9.1: el texto exacto que se propone para `docs/01-dominio.md` y `docs/03-modelo-de-datos.md`. **Ninguno de los dos archivos fue editado.** Cuando el usuario apruebe (o cambie) el texto, se aplica tal cual y se marca 9.1. Cada cambio refleja únicamente lo ya aprobado en `design.md` (D1 a D14) y lo implementado; no agrega decisiones nuevas.
>
> Los ADR-033, ADR-034 y ADR-035 están escritos en `docs/adr/` con estado *Propuesto*; pasan a *Vigente* cuando el usuario apruebe su texto.

Prioridad de fuentes (`CLAUDE.md` §1): `docs/adr/` > `docs/00` a `docs/04`. Por eso los ADR se aprueban primero y estos dos documentos los reflejan.

---

## 1. `docs/01-dominio.md` §12.1 — agregar CC-08

Fuente: `design.md` D3 y ADR-034 puntos 1 y 2.

**Antes** (fin de la tabla de §12.1):

```markdown
| CC-07 | El estado de cuenta muestra los movimientos en orden de `occurred_at` con saldo acumulado calculado al consultar. | 1 (PDF: 2) |

### 12.2 Cobranzas
```

**Después:**

```markdown
| CC-07 | El estado de cuenta muestra los movimientos en orden de `occurred_at` con saldo acumulado calculado al consultar. | 1 (PDF: 2) |
| CC-08 | Una cuenta admite varios movimientos `SALDO_INICIAL`, cada uno con su sentido; un error de carga se corrige con otro `SALDO_INICIAL` en sentido contrario por la diferencia. Se admiten solo mientras la cuenta no tenga movimientos de otro tipo (`CUENTA_CON_OPERACIONES`). No se carga saldo inicial al consumidor final (`CONSUMIDOR_FINAL_SIN_CUENTA`); cualquier otro estado de cliente o de proveedor lo admite. | 1 |

### 12.2 Cobranzas
```

## 2. `docs/01-dominio.md` §19 — anotar el uso de tres permisos

Fuente: `design.md` D1 y D2, ADR-033.

Los permisos no cambian (no hay permiso nuevo, D1-A y D2-A). Solo se amplía el "Alcance" de tres filas para que la tabla diga para qué se usan hoy.

**Antes:**

```markdown
| IMPORTAR_DATOS | Importaciones y puesta en marcha | ✓ | | | | |
| GESTIONAR_CLIENTES | Alta y edición de clientes | ✓ | ✓ | ✓ | | |
| GESTIONAR_PROVEEDORES | Alta y edición de proveedores | ✓ | ✓ | | | |
```

**Después:**

```markdown
| IMPORTAR_DATOS | Importaciones y puesta en marcha (incluye registrar saldos iniciales, CC-08) | ✓ | | | | |
| GESTIONAR_CLIENTES | Alta y edición de clientes; ver su cuenta corriente | ✓ | ✓ | ✓ | | |
| GESTIONAR_PROVEEDORES | Alta y edición de proveedores; ver su cuenta corriente | ✓ | ✓ | | | |
```

## 3. `docs/03-modelo-de-datos.md` §12 — `cuenta_movimiento` y `saldo_cuenta`

Fuente: `design.md` D6, D11 y D14, ADR-035; migración `e6f7a8b9c0d1_cuentas_corrientes.py`.

### 3.1 `cuenta_movimiento`

**Antes:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `cuenta_tipo` | `text` | `CLIENTE`, `PROVEEDOR` |
| `entidad_id` | `uuid` | Cliente o proveedor |
| `tipo` | `text` | CC-02, CC-03 |
| `sentido` | `text` | `AUMENTA`, `REDUCE` |
| `importe` | `numeric(14,2)` | `CHECK (importe > 0)` |
| `origen_tipo`, `origen_id` | `text`, `uuid` | |
| `occurred_at`, `registered_at`, `usuario_id`, `operation_id` | | |

**No tiene columna de saldo acumulado.** El saldo se calcula (CC-04) y se materializa en `saldo_cuenta`.

Índice principal: `(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)`.
```

**Después:**

```markdown
| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | `UNIQUE (organizacion_id, id)` |
| `cuenta_tipo` | `text` | `CLIENTE`, `PROVEEDOR` |
| `entidad_id` | `uuid` | Cliente o proveedor |
| `cliente_id` | `uuid` | **Generada** por la base: `entidad_id` si `cuenta_tipo = CLIENTE`, si no nulo. FK compuesta `(organizacion_id, cliente_id) → cliente` |
| `proveedor_id` | `uuid` | **Generada** por la base: `entidad_id` si `cuenta_tipo = PROVEEDOR`, si no nulo. FK compuesta `(organizacion_id, proveedor_id) → proveedor` |
| `tipo` | `text` | CC-02, CC-03. `CHECK` de catálogo y de coherencia con `cuenta_tipo` (sin los tipos de IVA, que agrega el módulo de facturación) |
| `sentido` | `text` | `AUMENTA`, `REDUCE` |
| `importe` | `numeric(14,2)` | `CHECK (importe > 0)` |
| `origen_tipo`, `origen_id` | `text`, `uuid` | |
| `occurred_at`, `registered_at`, `usuario_id`, `operation_id` | | `usuario_id` con FK compuesta a `usuario` |
| `dispositivo_id` | `uuid` | `NOT NULL`. FK compuesta `(organizacion_id, dispositivo_id) → dispositivo` (§2.3) |

`cliente_id` y `proveedor_id` no las escribe nadie: las calcula PostgreSQL, y existen para que la referencia a `cliente` o a `proveedor` sea una clave foránea compuesta (§2.4) aunque `entidad_id` apunte a dos tablas según `cuenta_tipo`. El emparejamiento entre `tipo` y `sentido` (por ejemplo, `VENTA` siempre `AUMENTA`) no tiene `CHECK` en la base: lo verifica el dominio (ADR-034).

**No tiene columna de saldo acumulado.** El saldo se calcula (CC-04) y se materializa en `saldo_cuenta`.

Índice principal: `(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)`.
```

### 3.2 `saldo_cuenta`

**Antes:**

```markdown
`organizacion_id`, `cuenta_tipo`, `entidad_id` (PK compuesta), `saldo` `numeric(14,2)`, `actualizado_en`. Es la fila que se bloquea al evaluar crédito y al registrar movimientos (`02` §7.3).
```

**Después:**

```markdown
`organizacion_id`, `cuenta_tipo`, `entidad_id` (PK compuesta, sin `id`: ninguna tabla referencia una fila de saldo), `cliente_id` y `proveedor_id` (generadas, con las mismas FK compuestas que `cuenta_movimiento`), `saldo` `numeric(14,2) NOT NULL DEFAULT 0`, `actualizado_en`. Es la fila que se bloquea al evaluar crédito y al registrar movimientos (`02` §7.3). La fila nace de forma perezosa con el primer movimiento de la cuenta (`INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`).
```

### 3.3 Nota sobre `docs/03` §2.3

ADR-035 punto 3 aclara que la regla "toda tabla de negocio tiene `id`" no rige para `saldo_cuenta`. **No se propone editar `03` §2.3**: la aclaración vive en el ADR (D11: "`03` §2.3 se aclara en el ADR"). Si el usuario prefiere además una nota en §2.3, se agrega como edición adicional con su texto aprobado.

---

## 4. Qué no cambia

- `docs/00`, `docs/02` y `docs/04` (salvo el cierre del change: la nota del change 10 de más abajo y el estado del roadmap al archivar, que se hacen en `verificacion.md` y en el archivado).
- `docs/01` §21 (la fila "Saldo inicial" ya dice `+ / −` en cuentas de cliente y de proveedor y auditoría "Sí").
- `docs/01` CC-02: sigue listando `IVA_FACTURA` y `ANULACION_IVA_FACTURA` (el `CHECK` de la base los deja para la migración de facturación).

## 5. Nota de roadmap para el change 10 (para `docs/04`, al archivar)

> Change 10 (importación de planillas): la importación de saldos iniciales reutiliza `cuentas_corrientes/service.py::registrar_saldo_inicial` fila por fila, con el permiso `IMPORTAR_DATOS`. Hereda CC-08: varias filas por cuenta son válidas mientras la cuenta no tenga movimientos de otro tipo; el consumidor final se rechaza (`CONSUMIDOR_FINAL_SIN_CUENTA`); una entidad ajena o inexistente responde 404.

Se aplica a `docs/04-roadmap-changes.md` al archivar el change (`04` §2.1 punto 6), con confirmación del usuario.
