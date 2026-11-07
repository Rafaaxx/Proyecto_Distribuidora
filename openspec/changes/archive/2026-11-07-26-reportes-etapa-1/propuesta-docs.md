# Propuesta de cambios a `docs/` — change 26 `reportes-etapa-1`

> **Borrador con las opciones aprobadas en 0.1 (2026-11-06): A en todas salvo D8 = B.** Se completa con las precisiones del apply (tarea 16.2). Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia. Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-070-reportes-de-la-etapa-1.md`.
>
> **Cuidado al aplicar:** toda fila de las tablas de `01-dominio.md` debe conservar la columna `| ID |` al principio y `| etapa |` al final (el archivo de un change anterior truncó filas). Después de aplicar, correr `frontend/tests/unit/ayuda/trazabilidad.test.ts`.
>
> Orden: `01` REP-02, REP-03, REP-04, §19 (tabla de permisos y párrafo de lecturas); `02` §5.3, §11 (paginación y fila Reportes); `03` §16; `04` §2, §10 (deuda del 14), §11 (párrafo del 26), §12.

---

## `01-dominio.md`

### REP-02 (período y anuladas) — D1, D2

**Actual**

> | REP-02 | Las ventas se asignan al período por su fecha de negocio (TR-04). Las ventas anuladas se excluyen de los totales de su período y se informan por separado. | 1 |

**Propuesto**

> | REP-02 | Las ventas se asignan al período por su fecha de negocio (TR-04). Las ventas anuladas se excluyen de los totales de su período y se informan por separado. **El período son fechas de negocio inclusivas; sin fechas, el mes en curso hasta hoy, y como máximo 366 días (`PERIODO_DEMASIADO_LARGO`). Una venta anulada se excluye del período de la venta aunque se anule después, y se lista en ese período con la fecha y el motivo de la anulación (ADR-070).** | 1 |

### REP-03 (cajas equivalentes y desgloses) — D3, D4

**Actual**

> | REP-03 | Las cantidades se informan en cajas equivalentes, unidades base y detalle por presentación vendida. | 1 |

**Propuesto**

> | REP-03 | Las cantidades se informan en cajas equivalentes, unidades base y detalle por presentación vendida. **Las cajas equivalentes de cada línea usan sus `unidades_referencia` congeladas, se suman exactas y se redondean a 2 decimales una sola vez por cifra. El reporte de ventas trae resumen, por día, por vendedor y por producto; por producto, solo cantidades y neto (ADR-070).** | 1 |

### REP-04 (utilidad) — D5

**Actual**

> | REP-04 | Utilidad real = neto − costo congelado − IVA absorbido asignado. Solo la ven usuarios con `VER_UTILIDAD`. | 1 |

**Propuesto**

> | REP-04 | Utilidad real = neto − costo congelado − IVA absorbido asignado. Solo la ven usuarios con `VER_UTILIDAD`. **Con la utilidad se informa el costo vendido. Se calcula solo sobre las líneas con costo; las vendidas sin costo (VTA-05, sin conexión) se informan aparte con su cantidad y su neto. Hasta que exista el módulo de facturación, el IVA absorbido asignado es cero. No se informa margen porcentual (ADR-070).** | 1 |

### §19 (tabla de permisos, fila `VER_REPORTES`) — D8 = B

**Actual**

> | VER_REPORTES | Reportes | ✓ | ✓ | ✓ | | ✓ |

**Propuesto**

> | VER_REPORTES | Reportes. **Los saldos de proveedores exigen además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD` (ADR-070)** | ✓ | ✓ | ✓ | | ✓ |

### §19 (lecturas de los reportes) — D5, D7, D8, D9, D10

**Actual (párrafo final de la sección, sin cambios)**

> El listado, el detalle **y el resumen** de jornadas se leen con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, […]

**Propuesto (párrafo nuevo a continuación)**

> Los reportes (ventas por período, rendiciones, saldos de clientes y de proveedores, observaciones por vendedor y ajustes por motivo) se leen con `VER_REPORTES` y alcanzan a toda la organización. Con `VER_UTILIDAD` traen además el costo vendido y la utilidad (REP-04); con `VER_COSTOS`, el valor de las diferencias de rendición y de los ajustes. El resumen de una jornada se lee también desde los reportes con `VER_REPORTES`. Los saldos de clientes se leen solo con `VER_REPORTES`; los saldos de proveedores, con `VER_REPORTES` y además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD` (con la plantilla, ADM, GES y CON; el Supervisor no, por el criterio de ADR-033), y `/admin` oculta su pestaña a quien no cumple la regla. Desde los reportes, «Ver estado de cuenta» exige el permiso de la ficha y «Ver en Revisión», `REVISAR_OBSERVACIONES` (ADR-070).

---

## `02-arquitectura.md`

### §5.3 (dependencias de `reportes`) — D6

**Actual (bloque de dependencias, fila nueva antes de `auditoria, configuracion, identidad ◄── todos`)**

> importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad (solo por service.py; nadie depende de importacion, ADR-042)

**Propuesto (se agrega la fila siguiente)**

> reportes ──► lectura de las tablas de todos los módulos con SQLAlchemy Core (solo sus `models`, excepción de §5.2) y stock (resumen de la jornada, por service.py); nadie depende de reportes; sin comandos (ADR-070)

### §11 (paginación de los listados) — D14

**Actual**

> - Los listados usan paginación por cursor y un límite máximo por página.

**Propuesto**

> - Los listados usan paginación por cursor y un límite máximo por página. **Excepción: las listas de los reportes («Por día», «Por producto», anuladas, jornadas y saldos) se paginan por número de página de a 50 filas, con `total_filas` y `paginas`, y los totales del reporte se calculan sobre todo el período y los filtros (ADR-070).**

### §11 (fila Reportes) — D6 a D10, D14

**Actual**

> | Reportes | ventas por período, rendición, saldos |

**Propuesto**

> | Reportes | `GET /reportes/ventas`, `GET /reportes/rendiciones`, `GET /reportes/rendiciones/{jornada_id}`, `GET /reportes/saldos/clientes`, `GET /reportes/saldos/proveedores`, `GET /reportes/observaciones`, `GET /reportes/ajustes`, todas con `VER_REPORTES` (saldos de proveedores, además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`); período por fechas de negocio; listas largas paginadas por número de a 50 (`pagina`; en ventas, `pagina_por_dia`, `pagina_por_producto` y `pagina_anuladas`) (ADR-070) |

---

## `03-modelo-de-datos.md`

### §16 (vista de utilidad) — D6

**Actual**

> Los reportes de utilidad por producto, cliente o proveedor se implementan como vistas (`vista_venta_utilidad`) que combinan `venta_linea` con `ajuste_iva_absorbido`. En la etapa 1 son vistas simples; si el volumen lo exige, pasan a vistas materializadas con actualización programada.

**Propuesto**

> Los reportes de utilidad por producto, cliente o proveedor (REP-06, etapa 2) se implementan como vistas (`vista_venta_utilidad`) que combinan `venta_linea` con `ajuste_iva_absorbido`; si el volumen lo exige, pasan a vistas materializadas con actualización programada. **Los reportes de la etapa 1 (change 26) consultan las tablas con SQLAlchemy Core, sin vistas ni migración; la utilidad del período suma `venta_linea` con el IVA absorbido en cero hasta que exista `ajuste_iva_absorbido` (ADR-070).**

---

## `04-roadmap-changes.md`

### §2 (tamaño) — D0

Al final de la viñeta «Tamaño», agregar: **«El change 26 (`reportes-etapa-1`) se implementa en seis lotes y puede pasar de la estimación: se anota como excepción de tamaño (ADR-070).»**

### §10 (deuda del 14)

Al final del párrafo «Deuda nominada por el change 14 para los changes 26 y 28 (reportes y auditoría)», agregar: **«El 26 salda la parte (2) en reportes (ajustes y pérdidas por motivo, ADR-070); la consulta de auditoría con motivo y las partes (1) y (3) quedan en el 28.»**

### §11 (párrafo del 26, al archivar)

Agregar después del párrafo del change 25: **«Change 26 (`reportes-etapa-1`) archivado {fecha} — terminado (ADR-070).** Entrega: el módulo `reportes` de solo lectura y la sección «Reportes» de `/admin` con ventas por período (anuladas aparte, cajas equivalentes, utilidad con `VER_UTILIDAD` y líneas sin costo aparte), rendiciones por vendedor y jornada, saldos de clientes y proveedores (los de proveedores con la regla compuesta de `01` §19), observaciones por vendedor y ajustes por motivo, con las listas largas paginadas por número de a 50 y lo más reciente primero en jornadas, anuladas y «Por día»; sin migración, sin permisos nuevos ni Dexie nuevo. **Deudas saldadas:** del 12 (saldos de proveedores), del 14 (parte 2), del 18a (utilidad y líneas sin costo), del 19 (anuladas aparte), del 24 (rendición por vendedor y jornada), del 25 (observaciones por vendedor). **Deudas nuevas:** al **módulo de facturación**, el IVA absorbido en la utilidad; al **28**, las partes (1) y (3) de la deuda del 14; a la **etapa 2**, REP-06, saldo a una fecha y exportación. **Prueba manual:** 2026-11-07 (con los ajustes de D14) y {fecha de la repetición, 21.6}.»

### §12 (fila 26)

Sin cambios en la fila.

## Precisiones del apply (tarea 16.2)

No cambian lo propuesto arriba; conviene tenerlas presentes al aplicar esta propuesta (detalle en `ADR-070`, «Precisiones del apply»):

- **`01` REP-04 y §19:** el costo vendido y la utilidad salen de las líneas con costo; neto, IVA y total, de la cabecera de la venta. Los saldos de proveedores se muestran por nombre (el proveedor no tiene código) con el estado de `activo`.
- **`01` §19 (lecturas de los reportes):** el detalle de una jornada desde el reporte (`GET /reportes/rendiciones/{jornada_id}`) trae el código, el nombre y la referencia de cada producto, de modo que `VER_REPORTES` no necesita el permiso del catálogo ni el de stock.
- **`02` §5.3 y §11:** `reportes` repite la forma del resumen de jornada (no importa los esquemas de `stock`) y duplica en su dominio el error `RANGO_DE_FECHAS_INVALIDO`; las lecturas usan el reloj inyectable.
- **`04` §11 (párrafo del 26):** agregar las propiedades de `test_reportes_propiedades.py` y la conciliación con el listado de ventas.
- **Al aplicarla:** verificar que las filas de `01` conserven `| ID |` y `| etapa |` (gotcha del archive). **No se aplica a `docs/` sin el visto bueno del usuario.**

