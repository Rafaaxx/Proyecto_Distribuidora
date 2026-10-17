# Propuesta de cambios a `docs/` — change 17b `medios-de-pago-y-roles`

> **Completada con lo aprobado el 2026-10-17 (D0 a D12, opción A en todas) y las precisiones del apply (ver "Precisiones del apply" al final). No se aplica a `docs/` sin el visto bueno del usuario.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones están en `docs/adr/ADR-053-medios-de-pago-administrables-y-permisos-por-rol.md` (estado *Propuesto*, hasta que el usuario lo apruebe junto con esta propuesta).
>
> Orden: `01` §4, §19; `02` §6.5, §11; `03` §4; `04` §2, §4, §8 (fila, nota del 06b y deudas); precisiones del apply.

---

## `01-dominio.md`

### §4 Configuración por organización — fila "Medios de pago"

**Texto actual**

> | Medios de pago | Lista con indicador de referencia obligatoria | Efectivo, transferencia, cheque, billetera, tarjeta | 1 |

**Texto propuesto**

> | Medios de pago | Lista con indicador de referencia obligatoria; nombre único en la organización sin distinguir mayúsculas; se dan de baja y se reactivan, nunca se borran, y siempre queda al menos uno activo (ADR-053) | Efectivo, transferencia (con referencia), cheque (con referencia), billetera, tarjeta (con referencia) | 1 |

### §19 Permisos y roles — fila `ADMIN_USUARIOS`

**Texto actual**

> | ADMIN_USUARIOS | Usuarios, roles y permisos (incluye definir el tope de descuento manual de cada rol y consultar los roles con su tope) | ✓ | | | | |

**Texto propuesto**

> | ADMIN_USUARIOS | Usuarios, roles y permisos (incluye cambiar los permisos de cada rol, consultar el catálogo de permisos, definir el tope de descuento manual de cada rol y consultar los roles con su tope). Ningún cambio puede dejar la organización sin un usuario activo con este permiso (ADR-053) | ✓ | | | | |

### §19 Permisos y roles — fila `ADMIN_CONFIGURACION`

**Texto actual**

> | ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02) | ✓ | | | | |

**Texto propuesto**

> | ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02, y crear, modificar, dar de baja y reactivar medios de pago, ADR-053) | ✓ | | | | |

### §19 — párrafo "Roles:"

**Texto actual**

> Roles: ADM = Administrador, GES = Administración, SUP = Supervisor comercial, VEN = Vendedor/Repartidor, CON = Consulta/Dirección. Los roles son plantillas: la organización puede modificar su composición y los topes de descuento. El vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad.

**Texto propuesto**

> Roles: ADM = Administrador, GES = Administración, SUP = Supervisor comercial, VEN = Vendedor/Repartidor, CON = Consulta/Dirección. Los roles son plantillas: la organización puede modificar su composición y los topes de descuento. Hasta el change de usuarios y roles no se crean roles nuevos ni se desactivan (ADR-028 D9.5, ADR-053). El vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad.

---

## `02-arquitectura.md`

### §6.5 Tipos de comando de la etapa 1 — filas nuevas

**Texto actual** (fila anterior, sin cambios)

> | `ROL_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`) | ✓ | |

**Texto propuesto** (se agregan después de esa fila)

> | `ROL_PERMISOS_CAMBIAR` (con `ADMIN_USUARIOS`; rechaza `IDENTIDAD_SIN_ADMINISTRADOR`, 409, ADR-053) | ✓ | |
> | `MEDIO_PAGO_CREAR`, `MEDIO_PAGO_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO` 422, `NOMBRE_DUPLICADO` y `ULTIMO_MEDIO_ACTIVO` 409, ADR-053) | ✓ | |

### §11 API — fila "Identidad"

**Texto actual**

> | Identidad | usuarios, roles (con su tope de descuento), dispositivos, PIN |

**Texto propuesto**

> | Identidad | usuarios, roles (con su tope de descuento y sus permisos), catálogo de permisos (`GET /identidad/permisos`), dispositivos, PIN |

### §11 API — fila "Configuración"

**Texto actual**

> | Configuración | parámetros, medios de pago, motivos, alícuotas |

**Texto propuesto**

> | Configuración | parámetros, medios de pago (alta y modificación por `POST`/`PUT /configuracion/medios-pago`; activos con cualquier sesión y todos con `GET /configuracion/medios-pago/todos` y `ADMIN_CONFIGURACION`), motivos, alícuotas |

---

## `03-modelo-de-datos.md`

### §4 `alicuota_iva`, `medio_pago`, `motivo` — fila `medio_pago`

**Texto actual**

> | `medio_pago` | `id`, `organizacion_id`, `nombre`, `requiere_referencia` `boolean`, `activo` |

**Texto propuesto**

> | `medio_pago` | `id`, `organizacion_id`, `nombre` (`ux_medio_pago__nombre` único sobre `(organizacion_id, lower(nombre))`, activos o no; ADR-053), `requiere_referencia` `boolean`, `activo` |

### §4 — párrafo de siembra (se agrega una oración al final)

**Texto actual** (final del párrafo)

> … la migración del change 17 los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-052).

**Texto propuesto**

> … la migración del change 17 los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-052). Las organizaciones nuevas nacen con Transferencia, Cheque y Tarjeta con `requiere_referencia = true` y Efectivo y Billetera sin; la migración del change 17b marca así los medios con esos nombres de las organizaciones existentes y no lo revierte al bajar. Los medios se crean y modifican con `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR`; el usuario de aplicación sigue sin `DELETE` sobre `medio_pago` (ADR-053).

---

## `04-roadmap-changes.md`

### §2 Convenciones — "Tamaño"

Sin cambios: el 17b entra en el tamaño normal (D0-A).

### §4 Tabla de dependencias — fila nueva y fila del 18a

**Texto actual**

> | 17 cobranzas | 07, 08, 15 |
> | 18a venta-online-core | 07, 08, 09, 11b, 13, 15, 17 |

**Texto propuesto**

> | 17 cobranzas | 07, 08, 15 |
> | 17b medios-de-pago-y-roles | 06b, 17 |
> | 18a venta-online-core | 07, 08, 09, 11b, 13, 15, 17, 17b |

### §8 Hito 4 — fila nueva en la tabla (después de la del 17)

**Texto actual**

> | 17 | `cobranzas` | Cobranza independiente con varios medios, anulación, efecto en cuenta corriente | INV-08, CC-05 |

**Texto propuesto**

> | 17 | `cobranzas` | Cobranza independiente con varios medios, anulación, efecto en cuenta corriente | INV-08, CC-05 |
> | 17b | `medios-de-pago-y-roles` | Alta, edición, baja y reactivación de medios de pago; Transferencia, Cheque y Tarjeta piden referencia (siembra y organizaciones existentes); pantalla "Roles y permisos" para cambiar los permisos de un rol, sin dejar la organización sin administrador; ayuda contextual. Surgido de la prueba manual del 17 (ADR-053) | — |

### §6 Hito 2 — nota del change 06b para el change de usuarios y roles (se agrega una oración al final)

**Texto actual** (final de la nota)

> … Ese change es también el que tiene que decidir el motivo de auditoría de cada caso, que hoy solo existe para `USUARIO_INACTIVO` y `ROL_INACTIVO`.

**Texto propuesto**

> … Ese change es también el que tiene que decidir el motivo de auditoría de cada caso, que hoy solo existe para `USUARIO_INACTIVO` y `ROL_INACTIVO`. **Precisión del change 17b (ADR-053):** el 17b trajo la pantalla para cambiar los permisos de un rol y la regla de que ningún cambio deja la organización sin un usuario activo con `ADMIN_USUARIOS`; el change de usuarios y roles aplica la misma regla a la baja de usuarios, a la de roles y al cambio de rol de un usuario, y trae además la pantalla de usuarios, el cambio de rol y la creación de roles.

### §8 — párrafo nuevo después de "Change 17 (`cobranzas`) — deudas saldadas"

**Texto propuesto**

> **Change 17b (`medios-de-pago-y-roles`):** medios de pago administrables por `ADMIN_CONFIGURACION` y permisos por rol desde `/admin` (ADR-053). **Deudas nuevas, sin dueño:** pantalla de motivos (alta y baja por ámbito) y de alícuotas (TR-09); el change de usuarios y roles (nota del 06b).

---

## Precisiones del apply (aprobadas o informadas durante la implementación)

Estas precisiones no cambian lo aprobado en D0 a D12; fijan cómo quedó implementado y deben leerse junto con el ADR-053.

### `02-arquitectura.md` §6.5 — auditoría de los comandos de medios (D11, ADR-022)

**Texto propuesto** (se agrega al final del párrafo de `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR`)

> Cada uno deja dos filas de auditoría con el mismo `operation_id`: la genérica del bus (`entidad = 'comando'`, ADR-022) y la de la entidad (`entidad = 'medio_pago'`) con `despues` en el alta y `antes` y `despues` en la modificación (AUD-01), igual que la condición de IVA y la modificación de crédito. El diseño (D11) describía una sola fila; el usuario aprobó mantener las dos para no romper el patrón establecido.

### `02-arquitectura.md` §7.3 — bloqueos del último administrador y del último medio activo (D4, D8)

**Texto propuesto** (se agregan a la lista de bloqueos de `02` §7.3)

> `ROL_PERMISOS_CAMBIAR`: solo cuando el cambio quita `ADMIN_USUARIOS` bloquea `FOR UPDATE` la fila de configuración de la organización y recién entonces cuenta, en SQL, los usuarios activos con rol activo que conservan el permiso; el resto de los cambios de permisos no paga el bloqueo (ADR-053). `MEDIO_PAGO_MODIFICAR`: bloquea los medios de la organización `FOR UPDATE` antes de contar los activos.

### `02-arquitectura.md` — dónde vive la comprobación de permiso de los medios (módulo `configuracion`)

**Texto propuesto** (nota en la descripción de módulos)

> `configuracion/commands.py` no importa otros módulos de negocio; el permiso `ADMIN_CONFIGURACION` de los comandos de medios se comprueba con `configuracion/service.py::exigir_permiso_de_medios_pago`, único archivo del módulo que alcanza a `identidad`.

### `01-dominio.md` §20 — cobertura de invariantes

**Texto propuesto** (nota, sin cambiar las filas)

> INV-01 (el último medio activo y el último administrador), INV-02 (nombre único por organización), INV-05 (el usuario de aplicación sin `DELETE` sobre `medio_pago`), INV-06 (doble envío) e INV-21 (lectura de todos los medios solo con `ADMIN_CONFIGURACION`) tienen pruebas que los citan por ID en el change 17b, incluidas pruebas de concurrencia con commits reales (dos bajas simultáneas de los dos últimos medios; dos cambios simultáneos que quitan `ADMIN_USUARIOS` a los dos únicos roles que lo tienen; dos altas simultáneas del mismo nombre).

### `03-modelo-de-datos.md` §4 — downgrade de la migración del 17b

**Texto propuesto** (se agrega a la oración de siembra)

> El `downgrade` de la migración del 17b borra `ux_medio_pago__nombre` y no revierte `requiere_referencia`; una prueba de ida y vuelta con cobranzas y pagos que usan los medios lo deja escrito.

### `04-roadmap-changes.md` §2 — tamaño del 17b

**Texto propuesto** (nota en la fila del 17b)

> El 17b entró en tres lotes (medios de pago en el backend; roles en el backend, crítico; pantallas y cierre). Pasa de la estimación de medio día de `04` §2: se anota como excepción de tamaño, igual que el 17.

