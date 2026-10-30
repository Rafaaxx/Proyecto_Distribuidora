# Propuesta de cambios a `docs/` — change 20c `catalogos-de-configuracion`

> **Completada en la tarea 13.1 con lo aprobado en 0.1 (D0 a D15, 2026-10-30, opción A) y las precisiones del apply (ver el final). Se aplica a `docs/` al archivar el change, con el visto bueno del usuario.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-061-catalogos-de-configuracion.md` (*Propuesto*).
>
> Orden: `01` §4, §19; `02` §6.5, §7.3; `03` §4; `04` §9.

---

## `01-dominio.md`

### §4 Configuración por organización — fila "Alícuotas de IVA disponibles"

**Texto actual**

> | Alícuotas de IVA disponibles | Lista | 21%, 10,5%, 0% | 1 |

**Texto propuesto**

> | Alícuotas de IVA disponibles | Lista; nombre y porcentaje únicos en la organización; el porcentaje (de 0 a menos de 100 %) no cambia una vez creada; se dan de baja y se reactivan, nunca se borran; no se da de baja una que use un producto activo ni la última activa; la administra `ADMIN_CONFIGURACION` con `ALICUOTA_CREAR` y `ALICUOTA_MODIFICAR` (ADR-061) | 21%, 10,5%, 0% | 1 |

### §4 — fila "Redondeo por defecto"

**Texto actual**

> | Redondeo por defecto | Múltiplo y dirección | A definir; lo define el change 20c (`catalogos-de-configuracion`) | 1 |*solo precarga el formulario de una lista nueva cuando esté definido; la lista siempre tiene su propio redondeo (PRC-01)* |

**Texto propuesto**

> | Redondeo por defecto | Múltiplo y dirección, los dos o ninguno, con el dominio de PRC-01 y PRC-14; lo define `REDONDEO_POR_DEFECTO_DEFINIR` (`ADMIN_CONFIGURACION`, solo con conexión, auditado); se lee con `ADMIN_CONFIGURACION` o `GESTIONAR_LISTAS` (ADR-061) | Sin definir | 1 |*solo precarga el formulario de una lista nueva cuando está definido; sin definir, el formulario empieza vacío; no cambia las listas existentes; la lista siempre tiene su propio redondeo (PRC-01)* |

### §4 — fila "Motivos de ajuste de stock"

**Texto actual**

> | Motivos de ajuste de stock | Lista | Rotura, vencimiento, muestra, consumo interno, diferencia de inventario, otro | 1 |

**Texto propuesto**

> | Motivos de ajuste de stock | Lista | Rotura, vencimiento, muestra, consumo interno, diferencia de inventario, otro | 1 |
> | Motivos (todos los ámbitos) | Lista por ámbito de la lista cerrada de `03` §4; nombre único en la organización y el ámbito sin distinguir mayúsculas; el ámbito no cambia; se dan de baja y se reactivan, nunca se borran, y cada ámbito conserva al menos uno activo; los administra `ADMIN_CONFIGURACION` con `MOTIVO_CREAR` y `MOTIVO_MODIFICAR` (ADR-061) | Los sembrados de cada ámbito (`03` §4) | 1 |

### §19 Permisos y roles — fila `ADMIN_CONFIGURACION`

**Texto actual**

> | ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02, y crear, modificar, dar de baja y reactivar medios de pago, ADR-053) | ✓ | | | | |

**Texto propuesto**

> | ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02; crear, modificar, dar de baja y reactivar medios de pago, ADR-053; motivos de cada ámbito y alícuotas de IVA, y definir el redondeo por defecto, ADR-061) | ✓ | | | | |

---

## `02-arquitectura.md`

### §6.5 Tipos de comando de la etapa 1 — filas nuevas (después de la de medios de pago)

**Texto actual** (fila anterior, sin cambios)

> | `MEDIO_PAGO_CREAR`, `MEDIO_PAGO_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO` 422, `NOMBRE_DUPLICADO` y `ULTIMO_MEDIO_ACTIVO` 409, ADR-053) | ✓ | |

**Texto propuesto** (filas agregadas)

> | `MOTIVO_CREAR`, `MOTIVO_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO` y `AMBITO_INVALIDO` 422, `NOMBRE_DUPLICADO` y `ULTIMO_MOTIVO_ACTIVO` 409, ADR-061) | ✓ | |
> | `ALICUOTA_CREAR`, `ALICUOTA_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO`, `CONFIGURACION_VALOR_ALICUOTA_INVALIDO` y `VALOR_NO_MODIFICABLE` 422, `NOMBRE_DUPLICADO`, `VALOR_DUPLICADO`, `ALICUOTA_EN_USO` (informa en `productos` la cantidad de productos activos que la usan) y `ULTIMA_ALICUOTA_ACTIVA` 409, ADR-061) | ✓ | |
> | `REDONDEO_POR_DEFECTO_DEFINIR` (con `ADMIN_CONFIGURACION`; `REDONDEO_INVALIDO` 422, ADR-061) | ✓ | |

Y al párrafo de auditoría de `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR` se suma: "Los comandos de motivos, alícuotas y redondeo por defecto (ADR-061) dejan las mismas dos filas, con la entidad `motivo`, `alicuota_iva` o `configuracion_organizacion`."

### §7.3 Orden global de bloqueo — párrafo de `MEDIO_PAGO_MODIFICAR`

**Texto actual**

> `MEDIO_PAGO_MODIFICAR`: bloquea los medios de la organización `FOR UPDATE` antes de contar los activos.

**Texto propuesto**

> `MEDIO_PAGO_MODIFICAR`: bloquea los medios de la organización `FOR UPDATE` antes de contar los activos. `MOTIVO_MODIFICAR` (baja): bloquea `FOR UPDATE` los motivos del ámbito de la organización antes de contar los activos. `ALICUOTA_MODIFICAR` (baja): bloquea `FOR UPDATE` las alícuotas activas de la organización antes de contar las activas y los productos activos que la usan; el alta y la modificación de un producto leen su alícuota `FOR SHARE` (ADR-061).

---

## `03-modelo-de-datos.md`

### §4 — tabla `alicuota_iva`, `medio_pago`, `motivo`

**Texto actual**

> | `alicuota_iva` | `id`, `organizacion_id`, `nombre`, `valor` `numeric(9,6)`, `activo` |

y

> | `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |

**Texto propuesto**

> | `alicuota_iva` | `id`, `organizacion_id`, `nombre` (`ux_alicuota_iva__nombre` único sobre `(organizacion_id, lower(nombre))`), `valor` `numeric(9,6)` (`ux_alicuota_iva__valor` único sobre `(organizacion_id, valor)`; `ck_alicuota_iva__valor`: `valor >= 0 AND valor < 1`; no cambia después del alta), `activo`; activas o no; ADR-061 |

y

> | `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`; no cambia después del alta), `nombre` (`ux_motivo__nombre` único sobre `(organizacion_id, ambito, lower(nombre))`, activos o no; ADR-061), `activo` |

Y al final del párrafo que sigue a la tabla se suma: "Los motivos y las alícuotas se crean y modifican con `MOTIVO_CREAR`, `MOTIVO_MODIFICAR`, `ALICUOTA_CREAR` y `ALICUOTA_MODIFICAR`; el usuario de aplicación sigue sin `DELETE` sobre `motivo` y `alicuota_iva`. La administración lee todos los motivos con `GET /configuracion/motivos/todos` y las alícuotas con `GET /configuracion/alicuotas`, que admite también `ADMIN_CONFIGURACION` (ADR-061)."

### §4 — tabla `configuracion_organizacion`, filas del redondeo

**Texto actual**

> | `redondeo_multiplo` | `numeric(14,2)` | |
> | `redondeo_direccion` | `text` | `ARRIBA`, `CERCANO`, `ABAJO` |

**Texto propuesto**

> | `redondeo_multiplo` | `numeric(14,2)` | Nulo = sin definir; `> 0` (`ck_configuracion_organizacion__redondeo_multiplo_positivo`); lo escribe `REDONDEO_POR_DEFECTO_DEFINIR` (ADR-061) |
> | `redondeo_direccion` | `text` | `ARRIBA`, `CERCANO`, `ABAJO`; nulo si y solo si el múltiplo es nulo (`ck_configuracion_organizacion__redondeo_coherente`) |

---

## `04-roadmap-changes.md`

### §9 — fila del 20c

**Texto actual**

> | 20c | `catalogos-de-configuracion` | Pantallas de alta y baja de motivos por ámbito y de alícuotas de IVA (TR-09), y comando para definir el redondeo por defecto de la organización (`01` §4), que precarga el formulario de una lista nueva. Gobernanza **BAJA** | — |

**Texto propuesto**

> | 20c | `catalogos-de-configuracion` | Pantallas de alta y baja de motivos por ámbito y de alícuotas de IVA (TR-09), y comando para definir el redondeo por defecto de la organización (`01` §4), que precarga el formulario de una lista nueva. Gobernanza **BAJA**. Terminado (change 20c, ADR-061): motivos y alícuotas con alta, cambio de nombre, baja y reactivación (ámbito y porcentaje fijos; ningún ámbito sin motivo activo; ninguna alícuota de baja en un producto activo) y redondeo por defecto. **Deudas saldadas:** pantalla de motivos (17b, 18b), pantalla de alícuotas (TR-09, 17b) y redondeo por defecto (`01` §4, ADR-047). | — |

### §9 — párrafo nuevo después de "Deudas nuevas del change 20b"

**Texto propuesto**

> **Deudas nuevas del change 20c (`catalogos-de-configuracion`):** **al change 21 (`pwa-y-bootstrap`):** bajar en el bootstrap (SYN-11) los motivos y las alícuotas activos con `configuracion/service.py` (`listar_motivos_activos`, `listar_alicuotas_activas`). **Al 22a/22c:** qué pasa con un motivo dado de baja usado en un comando sin conexión fuera del descuento manual (que ya tiene la causa `MOTIVO` de `DESCUENTO_DIFIERE`, DSC-09), por ejemplo la venta con lista anterior.

---

## Precisiones del apply (Lote 3)

- **`CONFIGURACION_VALOR_ALICUOTA_INVALIDO` responde 422** (antes 400), igual que los demás errores de validación del cuerpo; ya figura así en la propuesta de `02` §6.5.
- **`ALICUOTA_EN_USO` trae `productos` en el Problem Details**: la pantalla de alícuotas muestra la cantidad ("la usan 3 productos activos"). Ya figura en la propuesta de `02` §6.5.
- **Formulario de lista nueva (`01` §4, PRC-01):** con el redondeo por defecto definido, "Nueva lista" lo trae; sin definir, o si la lectura falla, el múltiplo queda vacío y la dirección sin elegir y no se envía hasta completarlos. La edición de una lista existente muestra siempre el suyo. Ya figura en la fila "Redondeo por defecto" de `01` §4.
- **`GET /configuracion/alicuotas` sigue paginada** e incluye las inactivas; la pantalla de alícuotas recorre todas las páginas con la misma consulta que usa el formulario de productos.
- **Sin cambios** a `docs/` por la ayuda contextual: las seis claves nuevas viven en `frontend/src/ayuda/textos.ts` y citan ADR-061; el texto de `precios.redondeo` (PRC-01, PRC-14) no necesitó cambios.
