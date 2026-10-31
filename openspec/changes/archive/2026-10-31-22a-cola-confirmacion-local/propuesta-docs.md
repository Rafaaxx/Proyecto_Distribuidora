# Propuesta de cambios a `docs/` — change 22a `cola-confirmacion-local`

> **Propuesta completa (tareas 19.1 y 19.2) con lo aprobado en 0.1 (opción A en todas, salvo D6 = C y D10 = B) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-063-venta-en-ruta-y-cola-local.md` (*Propuesto* hasta archivar).
>
> Orden: `01` §19 (matriz), §8 STK-06, §9 CRE-08, §13 SYN-09, §14 SEG-05; `02` §7.7, §12.4, §13.2, §13.5, §13.6; `04` §11.

---

## `01-dominio.md`

### §19 — Matriz de permisos: `PERMITIR_STOCK_NEGATIVO` (D6 = C, ADR-063 punto 7)

**Texto actual**

> | PERMITIR_STOCK_NEGATIVO | Operar con stock negativo online | ✓ | | | | |

**Texto propuesto**

> | PERMITIR_STOCK_NEGATIVO | Operar con stock negativo | ✓ | | | | |

**Aprobado por el usuario el 2026-10-31** (este texto y el de STK-06 de abajo). La descripción queda corta, como etiqueta de la pantalla de Roles; que el permiso rige también en el teléfono sin conexión lo dice STK-06. Código: `PERMISOS_DEL_CATALOGO` y la migración de datos `b7d3f1a9c2e4` (las bases ya migradas conservaban el texto viejo).

### §8 — STK-06 (D6 = C)

**Texto actual**

> | STK-06 | Sin conexión, una venta que deje stock negativo se acepta al sincronizar con observación STOCK_NEGATIVO. | 1 |

**Texto propuesto**

> | STK-06 | Sin conexión, el teléfono bloquea la línea que supera el stock del vehículo salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`; con el permiso avisa («Supera el stock del vehículo (quedan N)») y pide confirmación («Vender igual»). El servidor igualmente acepta al sincronizar una venta que deje stock negativo, con observación `STOCK_NEGATIVO`, como red de seguridad (ADR-063). | 1 |

### §9 — CRE-08

**Texto actual**

> | CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada. | 1 |

**Texto propuesto**

> | CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada que todavía no tienen resultado del servidor (débito de la venta menos lo cobrado). Lo mismo rige para el stock del vehículo (RUT-04). La conciliación con un bootstrap posterior a una sincronización aceptada es del change 22c (ADR-063). | 1 |

### §13 — SYN-09

**Texto actual**

> | SYN-09 | El dispositivo no elimina una operación local hasta recibir ACEPTADO o ACEPTADO_CON_OBSERVACIONES. Un RECHAZADO queda visible en el dispositivo. | 1 |

**Texto propuesto**

> | SYN-09 | El dispositivo no elimina una operación local hasta recibir ACEPTADO o ACEPTADO_CON_OBSERVACIONES. Un RECHAZADO queda visible en el dispositivo. Ni el bootstrap, ni el cierre de sesión, ni el inicio de sesión de otro usuario borran ventas, cobranzas, movimientos ni comandos locales; quedan «Sin enviar» (`PENDIENTE`) hasta el envío (ADR-063). | 1 |

### §14 — SEG-05

**Texto actual** (fragmento a ampliar, al final de la regla)

> … Quien tiene algún permiso de autorización puede definir su propio PIN desde "Mi PIN", confirmando su contraseña (ADR-055). | 1 |

**Texto propuesto** (se agrega al final, antes de `| 1 |`)

> … Sin conexión, el teléfono verifica el PIN del supervisor contra la derivación del bootstrap, cuenta los fallos por par (usuario, supervisor) y, con `intentos_pin_max` fallos, bloquea el PIN de ese supervisor en ese teléfono **hasta el próximo bootstrap** (abrir la jornada o «Actualizar datos»): el bloqueo no es por tiempo, porque el reloj del teléfono se puede adelantar; un intento durante el bloqueo no cuenta y un acierto no reinicia la cuenta. El PIN no se guarda ni viaja en el comando (ADR-063).

---

## `02-arquitectura.md`

### §7.7 — Numeración de notas de venta

**Texto actual** (viñeta 2)

> - El dispositivo lleva el correlativo local y lo incrementa al confirmar.

**Texto propuesto**

> - El dispositivo lleva el correlativo local en Dexie (`meta.ultimo_correlativo`, sin `localStorage`) y asigna el número dentro de la misma transacción que confirma la venta: el siguiente es el mayor entre el del bootstrap y el local, más uno. Un carrito descartado no consume número (ADR-063).

### §12.4 — Autorización de supervisor sin conexión

**Texto actual** (viñeta 3, parte final)

> … límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría.

**Texto propuesto**

> … límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría. El límite local cuenta los fallos por par (usuario, supervisor) en la tabla `intentos_pin`; al llegar a `intentos_pin_max` el PIN de ese supervisor queda bloqueado en el teléfono hasta el próximo bootstrap, sin guardar horas (ADR-063).

### §13.2 — Base local (Dexie)

**Texto actual**

> | `meta` | Versión de esquema local, dispositivo, último correlativo, fecha de bootstrap |
> | `ventas`, `cobranzas` | Operaciones locales con estado de sincronización |
> | `movimientos_locales` | Efectos locales sobre stock y saldos, para calcular disponibles |
> | `cola` | Comandos pendientes ordenados por secuencia |

**Texto propuesto**

> | `meta` | Versión de esquema local, dispositivo, último correlativo y última secuencia, fecha de bootstrap |
> | `ventas`, `cobranzas` | Operaciones locales con estado de envío (`PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`) y los datos congelados de la nota |
> | `movimientos_locales` | Efectos locales sobre stock y saldos (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO`), para calcular disponibles |
> | `cola` | Comandos pendientes ordenados por secuencia; `operation_id` único |
> | `intentos_pin` | Fallos del PIN de supervisor por par (usuario, supervisor) y su bloqueo |
>
> Se agrega: «Las tablas de operaciones (versión 3 de Dexie) no las toca el bootstrap. Confirmar una venta local escribe venta, cobranza, movimientos, comando y los dos contadores en **una sola transacción**: todo o nada. Reconfirmar con el mismo `operation_id` no encola otra venta (ADR-063).»

### §13.5 — Service worker

**Texto actual** (viñeta 3)

> - Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto.

**Texto propuesto**

> - Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto: con líneas cargadas el aviso dice «Hay una versión nueva: se instala al terminar la venta» y no ofrece «Actualizar» hasta confirmar o descartar la venta. Salir de la venta con líneas pide confirmar «¿Descartar la venta?» (ADR-063).

### §13.6 — Nota de venta

**Texto actual** (viñeta 1, parte final)

> … la API en administración (`GET /api/v1/ventas/{id}/nota`, con `VENDER` o `ANULAR_VENTA`) y, en `/ruta`, Dexie (change 22a). …

**Texto propuesto**

> … la API en administración (`GET /api/v1/ventas/{id}/nota`, con `VENDER` o `ANULAR_VENTA`) y, en `/ruta`, Dexie: la venta local congela los datos de la nota al confirmar (`domain/ventas/notaDesdeLocal.ts`) y el adaptador llama a la misma función de armado, sin señal (ADR-063). …

---

## `04-roadmap-changes.md`

### §11 — Fila del 22a y estado

**Texto actual**

> | 22a | `cola-confirmacion-local` | Confirmación local atómica en Dexie … | INV-01 (transacción Dexie) |

**Texto propuesto** (agregar, tras la fila, el párrafo de estado como en los changes anteriores)

> **Change 22a (`cola-confirmacion-local`) archivado (fecha de archivo) — terminado (ADR-063).** Entrega: toda venta de `/ruta` se confirma en el teléfono (con o sin señal) en una sola transacción Dexie (venta, cobranza, movimientos locales, comando `VENTA_CONFIRMAR` `OFFLINE` y contadores), con número y secuencia asignados en la transacción; Dexie v3 con `ventas`, `cobranzas`, `movimientos_locales`, `cola` e `intentos_pin`; saldo y stock locales (CRE-08, RUT-04); reglas locales (cliente suspendido, consumidor final exacto, lista y versión, descuentos, stock con `PERMITIR_STOCK_NEGATIVO`, crédito con tolerancia sin conexión); PIN de supervisor verificado en el teléfono con límite de intentos y bloqueo hasta el próximo bootstrap; fixture de contrato `shared/fixtures/sync/venta-confirmar-offline.json` validado por Vitest y por el lote del backend; pantallas Vender (3 pasos), Venta guardada, Ventas de hoy y «N ventas sin enviar» en el inicio; nota con datos congelados y «Compartir nota» sin señal; guarda del carrito frente a la versión nueva del service worker; aviso al cerrar sesión o entrar otro usuario con pendientes; cinco claves de ayuda nuevas. Sin código nuevo en el servidor. **Deudas saldadas:** del 18a (reglas de la venta con los datos del bootstrap, ADR-054), del 18b (crédito y descuentos locales, PIN de supervisor en el teléfono, ADR-055), del 20 (adaptador de la nota desde Dexie, ADR-059), del 20c (motivo dado de baja en un comando sin conexión, ADR-061) y del 21 (guarda del carrito, tablas de operaciones en Dexie v3, prueba de que el bootstrap no las toca, ADR-062). **Deudas nuevas:** al **22b**, enviar la cola por secuencia y solo la del usuario autenticado (`02` §6.4), escribir `estado_envio`, la versión mínima de la aplicación (`02` §6.6), el botón «Sincronizar», serializar los intentos de PIN de supervisor entre pestañas con Web Locks, y la guarda del carrito para los enlaces del cuerpo de Vender y el botón atrás del navegador (hoy solo el menú inferior y «Cancelar»; `BrowserRouter` no admite `useBlocker`); al **22c**, conciliar los movimientos locales con un bootstrap posterior a una sincronización aceptada. **Prueba manual:** (fecha) en escritorio y en Android (Chrome) (`04` §2.1 punto 5).
