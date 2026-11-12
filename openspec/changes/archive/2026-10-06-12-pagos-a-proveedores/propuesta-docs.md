# Propuesta de cambios a `docs/` — change 12 (tarea 12.2)

> **Estado: APROBADA por el usuario y APLICADA el 2026-10-06 (incluida PAG-04).** Texto original de la propuesta: `docs/01`, `docs/02`, `docs/03` y `docs/04` sin tocar. Cada sección muestra el texto actual y el texto propuesto; al aprobar, se aplican en un solo paso junto con el estado *Vigente* de ADR-046. Todo recoge lo aprobado en `design.md` D0 a D11 y en ADR-046 (estado *Propuesto*); no hay decisiones nuevas, salvo los puntos marcados **[a decidir]**.
>
> Fuera de alcance (ya resueltos el 2026-10-03): la corrección de "`ANULADO`" por "`ANULADA`" en ADR-043 y en la spec `proveedores/anulacion-de-compras`, y el estado *Vigente* de ADR-043 y ADR-044.

---

## `docs/01-dominio.md`

### §6.4 Pagos a proveedores (PAG-01 a PAG-03)

**Texto actual**

| ID | Regla | Etapa |
| --- | --- | --- |
| PAG-01 | Un pago registra proveedor, fecha, importe y uno o más medios cuya suma es igual al importe. | 1 |
| PAG-02 | El pago reduce el saldo general del proveedor. No modifica costos. | 1 |
| PAG-03 | Un pago confirmado solo se corrige por anulación con permiso y motivo. | 1 |

**Texto propuesto**

| ID | Regla | Etapa |
| --- | --- | --- |
| PAG-01 | Un pago registra proveedor, fecha, importe y de 1 a 20 medios activos de la organización cuya suma es igual al importe (INV-08), con la referencia que cada medio exija; el mismo medio puede repetirse. La fecha es la del pago real: no puede ser posterior a hoy y no tiene límite hacia atrás; el movimiento de cuenta usa el momento en que se registra. Admite una observación opcional (guardada recortada) donde se anota, por ejemplo, qué facturas paga. Se puede pagar a un proveedor inactivo (ADR-046). | 1 |
| PAG-02 | El pago reduce el saldo general del proveedor y no se imputa a ninguna compra. Puede superar la deuda: el saldo queda a nuestro favor y la próxima compra a crédito lo absorbe, sin operación nueva; la pantalla pide confirmación explícita cuando el pago lo deja a nuestro favor. No modifica costos ni stock. Desde el primer pago la cuenta del proveedor ya no admite saldo inicial (CC-08). | 1 |
| PAG-03 | Un pago confirmado solo se corrige por anulación con permiso y con un motivo del ámbito `ANULACION_PAGO`. La anulación deja el pago `ANULADA` y registra un movimiento `ANULACION_PAGO` que devuelve el saldo (CC-03). El pago de una compra de contado se anula por separado solo si la compra ya está anulada (sin devolución del pago, CMP-05); mientras la compra esté vigente se rechaza. Se puede anular el pago de un proveedor inactivo (ADR-046). | 1 |
| PAG-04 | Los pagos se registran y se anulan solo con conexión. **[a decidir]** Regla nueva, simétrica a CMP-08; hoy solo figura en `02` §6.5 y en la spec `proveedores/pagos-a-proveedores`. | 1 |

### §19 Permisos y roles (lecturas)

No hay permisos nuevos (ADR-046). Se amplía el alcance de dos filas para dejar escrita la lectura.

**Texto actual**

| REGISTRAR_PAGO_PROVEEDOR | Registrar pagos | ✓ | ✓ | | | |
| ANULAR_PAGO_PROVEEDOR | Anular pagos | ✓ | ✓ | | | |

**Texto propuesto**

| REGISTRAR_PAGO_PROVEEDOR | Registrar pagos; ver el listado y el detalle de pagos, el saldo del proveedor y elegir proveedor | ✓ | ✓ | | | |
| ANULAR_PAGO_PROVEEDOR | Anular pagos; ver el listado y el detalle de pagos | ✓ | ✓ | | | |

Y, a continuación de la tabla de roles, una oración: "El listado y el detalle de pagos exigen `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`; el saldo de un proveedor se lee con `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA`; la lista de proveedores para elegir también con `REGISTRAR_PAGO_PROVEEDOR`; medios de pago y motivos, con cualquier sesión (ADR-043, ADR-046)."

### §21 Efectos de cada evento

**Texto actual** (fila existente, sin fila de anulación de pago)

| Pago a proveedor | — | — | — | − | — | Sí |

**Texto propuesto** (se agrega la fila siguiente, a continuación de "Pago a proveedor")

| Anulación de pago | — | — | — | + | — | Sí |

---

## `docs/02-arquitectura.md`

### §6.5 Tipos de comando de la etapa 1 (comandos y lecturas)

La tabla ya lista `PAGO_PROVEEDOR_REGISTRAR` y `PAGO_PROVEEDOR_ANULAR` como solo online; no cambia.

**Texto propuesto** (párrafo nuevo a continuación del que describe `COMPRA_ANULAR`)

> `PAGO_PROVEEDOR_REGISTRAR` lleva proveedor, fecha, importe, de 1 a 20 medios y una observación opcional, y exige `REGISTRAR_PAGO_PROVEEDOR`; `PAGO_PROVEEDOR_ANULAR` lleva el pago y un motivo del ámbito `ANULACION_PAGO`, y exige `ANULAR_PAGO_PROVEEDOR`. Los errores propios son `MEDIOS_INVALIDOS` (422), `PAGO_YA_ANULADO` y `PAGO_DE_COMPRA_VIGENTE` (409). Las lecturas son `GET /pagos-proveedores` (filtros de proveedor, estado, origen y fechas, con cursor), `GET /pagos-proveedores/{id}` (ambos con `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`) y `GET /proveedores/{id}/saldo` (con `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA`); `GET /proveedores/opciones` también se abre, solo en lectura, a `REGISTRAR_PAGO_PROVEEDOR` (ADR-046).

### §7.3 Orden global de bloqueo (fila de la operación)

**Texto actual**

> **DEBE:** toda transacción que bloquee varias filas lo hace en este orden, y dentro de cada nivel ordenando por clave:
> 1. `saldo_cuenta` (cliente o proveedor de la operación)
> 2. `costo_producto` (por `producto_id` ascendente)
> 3. `stock_saldo` (por `producto_id` y `ubicacion_id` ascendentes)
> 4. `jornada` (si la operación la valida)

**Texto propuesto** (se agrega, a continuación de la lista)

> Las filas de la propia operación que el comando corrige o anula se toman **antes** del nivel 1, en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`). `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` usan el mismo orden (compra, pago, `saldo_cuenta`), así que anular una compra y anular su pago a la vez no se interbloquean y dejan una sola `ANULACION_PAGO`. `PAGO_PROVEEDOR_REGISTRAR` parte del nivel 1 (`saldo_cuenta` del proveedor) (ADR-043 punto 15, ADR-046).

---

## `docs/03-modelo-de-datos.md`

### §4 `motivo` (ámbito `ANULACION_PAGO` y sus motivos)

**Texto actual**

> | `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |
>
> Las organizaciones nuevas nacen con tres motivos del ámbito `ANULACION_COMPRA` ("Error de carga", "Devolución al proveedor" y "Otro"); la migración del change 11 los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno. [...]

**Texto propuesto**

> | `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, **`ANULACION_PAGO`**, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |
>
> Las organizaciones nuevas nacen con tres motivos del ámbito `ANULACION_COMPRA` ("Error de carga", "Devolución al proveedor" y "Otro") **y tres del ámbito `ANULACION_PAGO` ("Error de carga", "Pago rechazado o devuelto" y "Otro")**; la migración del change 11 agrega los primeros y la del change 12 (`d1e2f3a4b5c6`) los segundos, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito. [...resto igual...]

### §6 `pago_proveedor` y `pago_proveedor_medio`

**Texto actual** (fila de `pago_proveedor` y párrafo siguiente)

> | `pago_proveedor` | `id`, `organizacion_id`, `proveedor_id`, `fecha`, `importe` `numeric(14,2)` `CHECK (> 0)`, `estado` (`CONFIRMADA`, `ANULADA`), `origen` (`COMPRA`, `INDEPENDIENTE`), `compra_id` (nulo si el origen es `INDEPENDIENTE`; único si no es nulo), `anulado_en`, `anulado_por_id`, `anulacion_motivo_id` (nulable: el change 12 decide el motivo de anulación de un pago), columnas de operación |
>
> INV-08 [...] El change 11 crea estas tablas para el pago de una compra de contado (`origen = COMPRA`, ADR-043); el change 12 agrega el pago independiente sobre las mismas tablas. [...]

**Texto propuesto**

> | `pago_proveedor` | `id`, `organizacion_id`, `proveedor_id`, `fecha` (la del pago real), `importe` `numeric(14,2)` `CHECK (> 0)`, `estado` (`CONFIRMADA`, `ANULADA`), `origen` (`COMPRA`, `INDEPENDIENTE`), `compra_id` (nulo si el origen es `INDEPENDIENTE`; único si no es nulo), **`observacion` `text` (opcional, inmutable; hasta 500 caracteres, aplicado en el esquema de la API y en el contenido del comando, sin `CHECK`)**, `anulado_en`, `anulado_por_id`, `anulacion_motivo_id` (nulable en la columna; `ck_pago_proveedor__anulacion_coherente` exige "anulada ⇔ momento, usuario **y motivo**", igual que `compra`), columnas de operación |
>
> Índices de listado: `(organizacion_id, fecha DESC, id DESC)` y `(organizacion_id, proveedor_id, fecha DESC, id DESC)`.
>
> INV-08 [...] El change 11 creó estas tablas para el pago de una compra de contado (`origen = COMPRA`, ADR-043); el change 12 agregó el pago independiente sobre las mismas tablas, con la anulación en columnas del propio pago (no en una tabla aparte como `cobranza_anulacion`, ADR-046). `observacion` queda fuera del `UPDATE` de `app_runtime`. [...]

---

## `docs/04-roadmap-changes.md`

### §7 (tabla del hito 3, fila del change 12)

**Texto actual**

> | 12 | `pagos-a-proveedores` | Pago con varios medios, anulación, saldo de proveedor | INV-08 |

**Texto propuesto**

> | 12 | `pagos-a-proveedores` | Pago independiente con 1 a 20 medios, anulación con motivo propio, lectura liviana del saldo del proveedor (el reporte de saldos es del 26), área "Pagos a proveedores" | INV-08 (cerrado para pagos; sigue pendiente para cobranzas en el 17), INV-13 |

### §7 (deuda del change 11 para el 12)

**Texto actual:** la deuda "nominada por el change 11 [...] para el change 12" con los puntos (a), (b) y (c).

**Texto propuesto** (se agrega al final del párrafo, como en las deudas ya saldadas)

> **Saldada por el change 12 (fecha de archivo) (ADR-046):** (a) ámbito de motivo `ANULACION_PAGO` con tres motivos sembrados y `CHECK` estricto de anulación; (b) el pago de una compra se anula por separado solo si la compra ya está anulada (`PAGO_DE_COMPRA_VIGENTE` en otro caso); (c) el saldo a nuestro favor se compensa solo por el saldo general, con confirmación explícita en el alta de pago y aviso en el alta de compra.

### §7 (deudas nuevas, a evaluar)

Párrafo nuevo, "Deuda nominada por el change 12 (`pagos-a-proveedores`)":

1. **Reporte de saldos de proveedores (change 26):** el 12 solo entrega `GET /proveedores/{id}/saldo`; no hay columna de saldo en el listado de proveedores.
2. **Corrección del saldo inicial después del primer pago (etapa 2):** desde el primer `PAGO` la cuenta rechaza `SALDO_INICIAL` (CC-08); la corrección espera a los ajustes de cuenta corriente.
3. **Imputación de pagos a compras y vencimientos (etapa 2, CMP-09):** el 12 no imputa (PAG-02); la observación libre del pago es el único vínculo con las facturas.
