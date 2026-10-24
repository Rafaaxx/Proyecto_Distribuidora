# Propuesta de cambios a `docs/` — change 18b `venta-online-descuentos-credito`

> **Estado: COMPLETA (tarea 20.1, 2026-10-23), alineada con todo lo aprobado hasta el 2026-10-23: D0 a D22 (2026-10-21, opción A, D21 = A + B), la revisión de D3 y D23/D24 (2026-10-22, confirmadas en la tarea 0.3) y las precisiones de los lotes 3 y 4 (2026-10-23). No se aplica a `docs/` sin el visto bueno del usuario.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones quedan en `docs/adr/ADR-055-descuentos-credito-y-pin-en-la-venta.md` y `ADR-056-*.md`.
>
> Orden: `01` §4, §5 (CLI-03), §9.2, §10, §13, §14, §19, §20 (nota); `02` §6.5, §10.4, §12.4; `03` §4, §12, §13; `04` §2, §9.

---

## `01-dominio.md`

### §4 Motivo obligatorio en descuento manual (D13)

**Texto actual**

> | Motivo obligatorio en descuento manual | Sí / no | A definir; mientras esté sin definir, el motivo no es obligatorio (el comando que lo define llega con el change 18b) | 1 |

**Texto propuesto**

> | Motivo obligatorio en descuento manual | Sí / no | A definir; mientras esté sin definir, el motivo no es obligatorio. Lo define `DESCUENTO_MANUAL_CONFIGURAR` (`ADMIN_CONFIGURACION`), junto con la habilitación (ADR-055) | 1 |

### §4 Política y tolerancia de crédito (D8, D14)

**Texto actual**

> | Política de crédito por defecto | ADVERTIR / AUTORIZAR / BLOQUEAR | AUTORIZAR | 1 |
> | Tolerancia offline de crédito | Importe o porcentaje del límite | A definir al configurar | 1 |

**Texto propuesto**

> | Política de crédito por defecto | ADVERTIR / AUTORIZAR / BLOQUEAR; la define `CREDITO_ORGANIZACION_CONFIGURAR` (`ADMIN_CONFIGURACION`) | AUTORIZAR | 1 |
> | Tolerancia offline de crédito | Importe o porcentaje del límite (el porcentaje con dos decimales, `5.00` = 5 %, se aplica sobre el límite y se redondea a centavos, ADR-032, ADR-055); sin tolerancia en el cliente ni en la organización, la tolerancia es cero | A definir al configurar | 1 |

### §9.2 CRE-03 (D5)

**Texto actual**

> | CRE-03 | Si el saldo resultante supera el límite, el exceso se trata según la política del cliente o, si no tiene, la de la organización: ADVERTIR, AUTORIZAR o BLOQUEAR. | 1 |

**Texto propuesto**

> | CRE-03 | Si el saldo resultante supera el límite, el exceso se trata según la política del cliente o, si no tiene, la de la organización: ADVERTIR, AUTORIZAR o BLOQUEAR. El exceso es la parte no cobrada de la venta que queda por encima del límite: `mín(máx(0, total − cobranza), máx(0, saldo resultante − límite))`; una venta cobrada entera nunca tiene exceso, aunque el cliente ya esté excedido (ADR-055). | 1 |

### §9.2 CRE-04, CRE-05, CRE-07 (D6)

**Texto actual**

> | CRE-04 | ADVERTIR: se muestra el exceso y el usuario puede confirmar. La venta queda con observación. | 1 |
> | CRE-05 | AUTORIZAR con conexión: confirma un usuario con `SUPERAR_CREDITO` o un supervisor que ingresa su PIN en el dispositivo. | 1 |
> | CRE-07 | BLOQUEAR: la venta no se confirma. El usuario puede aumentar la cobranza o reducir el pedido. | 1 |

**Texto propuesto**

> | CRE-04 | ADVERTIR: se muestra el exceso y el usuario puede confirmar aceptándolo expresamente (sin aceptación, `EXCESO_CREDITO_SIN_ACEPTAR`). La venta queda con observación `EXCESO_CREDITO_ADVERTIDO`. | 1 |
> | CRE-05 | AUTORIZAR con conexión: confirma un usuario con `SUPERAR_CREDITO` (se resuelve primero) o un supervisor con ese permiso que ingresa su PIN en el dispositivo; sin ninguno, `AUTORIZACION_CREDITO_REQUERIDA`. | 1 |
> | CRE-07 | BLOQUEAR: la venta no se confirma (`CREDITO_EXCEDIDO`), sin excepción de permiso. El usuario puede aumentar la cobranza o reducir el pedido. | 1 |

### §9.2 CRE-10 (D7, D12)

**Texto actual**

> | CRE-10 | La venta congela límite, saldo considerado, disponible, exceso, política aplicada, si fue online u offline, forma de resolución y autorizador. | 1 |

**Texto propuesto**

> | CRE-10 | La venta congela límite, saldo considerado, disponible, exceso, política aplicada, si fue online u offline, forma de resolución y autorizador. Sin conexión se congela la evaluación del dispositivo; el recálculo del servidor queda en la observación (CRE-09). Un límite vacío se congela vacío, con resolución `SIN_EXCESO` (ADR-055). | 1 |

### §10 DSC-09 (D10, D11)

**Texto actual**

> | DSC-09 | Con conexión, el servidor recalcula los descuentos y rechaza la confirmación si difieren de los enviados. Sin conexión, acepta los descuentos registrados y agrega la observación DESCUENTO_DIFIERE si su cálculo no coincide. | 1 |

**Texto propuesto**

> | DSC-09 | Con conexión, el servidor recalcula los descuentos y rechaza la confirmación si difieren de los enviados (`DESCUENTO_DIFIERE`, 409). Sin conexión, acepta los descuentos registrados y agrega una observación DESCUENTO_DIFIERE por venta si su cálculo no coincide o si el descuento manual no pasa la evaluación con los datos vigentes (tope, permiso, habilitación, motivo, autorizador), con las causas en el detalle (ADR-055). | 1 |

### §4 Intentos fallidos de PIN (D3)

**Texto actual**

> | Intentos fallidos de PIN antes de bloquear | Número | 5 | 1 |

**Texto propuesto**

> | Intentos fallidos de PIN antes de bloquear | Número | 5; vale para el PIN de desbloqueo local y, con conexión, para los fallos de un mismo usuario contra el PIN de un mismo supervisor (`intentos_pin_max`). El tope general por supervisor (20 fallos de cualquier usuario) es una constante del código, no un parámetro (ADR-055) | 1 |

### §5 CLI-03 (D17)

**Texto actual**

> | CLI-03 | Si la organización lo habilita, existe un cliente genérico "consumidor final" con límite de crédito cero. El consumidor final solo puede estar `ACTIVO` o `SUSPENDIDO`: no se inactiva (ADR-029). | 1 |

**Texto propuesto:** el mismo, más: "En la venta se evalúa con su límite cero y su snapshot de crédito se congela; con conexión `CONSUMIDOR_FINAL_CONTADO` se evalúa antes que el crédito y ningún permiso ni PIN la supera; sin conexión solo rigen `CONSUMIDOR_FINAL_CON_DEUDA` o `CLIENTE_NO_HABILITADO`, sin observaciones de crédito repetidas (ADR-055)."

### §9.2 CRE-06 y CRE-09 (D7, D8)

**Texto actual**

> | CRE-06 | AUTORIZAR sin conexión: si el exceso no supera la tolerancia offline (del cliente o de la organización), se confirma con observación EXCESO_CREDITO_AUTORIZADO_OFFLINE. Si la supera, se comporta como BLOQUEAR salvo permiso propio o PIN de supervisor. | 1 |
> | CRE-09 | Al sincronizar, el servidor recalcula con el saldo real y nunca rechaza la venta por crédito. Si detecta un exceso que el dispositivo no detectó, agrega la observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración. | 1 |

**Texto propuesto**

> | CRE-06 | AUTORIZAR sin conexión: si el exceso no supera ("≤") la tolerancia offline (del cliente o de la organización; sin ninguna de las dos es cero; el porcentaje se aplica sobre el límite), se confirma con observación EXCESO_CREDITO_AUTORIZADO_OFFLINE. Si la supera, se comporta como BLOQUEAR salvo permiso propio o PIN de supervisor. La tolerancia no rige con conexión. | 1 |
> | CRE-09 | Al sincronizar, el servidor congela la evaluación que hizo el dispositivo (el objeto de crédito es obligatorio sin conexión), recalcula con el saldo real y nunca rechaza la venta por crédito: solo una evaluación incoherente consigo misma (la resolución no corresponde al exceso, o `PIN_SUPERVISOR`/`PERMISO_PROPIO` sin autorizador) es un comando malformado (`CREDITO_INCONSISTENTE`). Si detecta un exceso que el dispositivo no detectó, agrega la observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración. | 1 |

### §10 DSC-06 (D2, D4, D18)

**Texto actual:** el de la fila DSC-06 de `01` §10 (párrafo largo que termina en "Si la organización exige motivo, hay un motivo por venta.").

**Texto propuesto (frase final nueva):** "El permiso propio se resuelve primero aunque se indique autorizador; si se indica uno, se revisa su permiso antes que su PIN. Sin la credencial que hace falta: `AUTORIZACION_REQUERIDA` (descuento) o `AUTORIZACION_CREDITO_REQUERIDA` (crédito). La autorización de descuento y la de crédito son independientes y, si las da la misma persona, el PIN se pide una vez (ADR-055)."

### §13 SYN-05 (D10)

**Texto actual:** el de la fila SYN-05 de `01` §13.

**Texto propuesto (frase final nueva):** "Los descuentos de una venta sin conexión con importe no positivo o con más de dos decimales, con porcentaje fuera de (0, 1] o que superan el bruto de la línea, o con más de un manual por línea, son un comando malformado (`TOTALES_INCONSISTENTES`) (ADR-055)."

### §13 SYN-07 (D9)

**Texto actual (inicio)**

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, EXCESO_CREDITO_ADVERTIDO, EXCESO_CREDITO_AUTORIZADO_OFFLINE, EXCESO_CREDITO_DETECTADO_SYNC, LISTA_NO_VIGENTE, DESCUENTO_DIFIERE, CLIENTE_NO_HABILITADO, PERMISO_REVOCADO, JORNADA_LIBERADA, ANULACION_COMPRA_SIN_RECALCULO, MEDIO_INACTIVO, REFERENCIA_FALTANTE, VENTA_SIN_COSTO, CONSUMIDOR_FINAL_CON_DEUDA, UBICACION_TOMADA_AL_SINCRONIZAR. …

**Texto propuesto:** agregar `AUTORIZACION_OFFLINE` a la lista y, al final de la fila: "`AUTORIZACION_OFFLINE` se emite solo sin conexión, una por cada autorización de descuento o de crédito resuelta por PIN de supervisor o por permiso propio; su detalle indica el tipo, la resolución, el autorizador y si conserva el permiso al sincronizar (ADR-055)."

### §14 SEG-05 (D2, D3)

**Texto actual**

> | SEG-05 | La autorización de un supervisor mediante PIN queda registrada con el supervisor como autorizador y se audita. | 1 |

**Texto propuesto**

> | SEG-05 | La autorización de un supervisor mediante PIN queda registrada con el supervisor como autorizador y se audita. Con conexión, el servidor verifica el PIN sin guardarlo ni incluirlo en el comando; con `intentos_pin_max` fallos de un mismo usuario, ese usuario no puede usar el PIN de ese supervisor, y con 20 fallos de cualquier usuario el PIN del supervisor se bloquea para todos; cada bloqueo dura 15 minutos desde el último fallo y los intentos durante el bloqueo no cuentan; definir un PIN nuevo reinicia la cuenta. Quien tiene algún permiso de autorización puede definir su propio PIN desde "Mi PIN", confirmando su contraseña (ADR-055). | 1 |

### §19 Permisos (D21)

**Texto propuesto (nota al pie de la tabla de permisos):** "Los permisos de autorización de excepciones (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR`) habilitan además a definir el propio PIN de autorización («Mi PIN», `PIN_AUTORIZACION_PROPIO_DEFINIR`), confirmando la contraseña; `ADMIN_USUARIOS` define o cambia el de cualquier usuario con alguno de esos permisos (`PIN_AUTORIZACION_ROTAR`) (ADR-055)."

### §20 nota de cobertura

**Texto propuesto (párrafo nuevo al final de §20):** "INV-10 (descuentos de línea y snapshot de crédito sin `UPDATE` ni `DELETE`), INV-01, INV-14, INV-17 e INV-21 tienen pruebas que los citan por ID en el change 18b."

---

## `02-arquitectura.md`

### §6.5 Tipos de comando

**Texto propuesto (filas nuevas):** `DESCUENTO_MANUAL_CONFIGURAR`, `CREDITO_ORGANIZACION_CONFIGURAR` (con `ADMIN_CONFIGURACION`) | ✓ | |; `PIN_AUTORIZACION_PROPIO_DEFINIR` (con algún permiso de autorización de excepciones; confirma la contraseña: `IDENTIDAD_CONTRASENA_INCORRECTA`, 403, y el límite de intentos del login, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, 429, ADR-018) | ✓ | |. Párrafo: "`POST /api/v1/ventas` admite, fuera del contenido, `credenciales` (autorizador y PIN) que el bus entrega al handler sin persistirlas ni incluirlas en la huella; el lote de sincronización no las admite. `POST /api/v1/yo/pin-autorizacion` lleva el PIN nuevo y la contraseña actual del mismo modo, con el contenido del comando vacío (ADR-055)."

### §6.3 paso 4 (D23, ADR-056; confirmado el 2026-10-22)

**Texto actual**

> 4. **Permisos.** En `ONLINE`, un permiso faltante rechaza (lo valida el handler, por REST y por el lote). En `OFFLINE`, el bus valida el permiso que el tipo declara en el catálogo contra los permisos actuales del usuario (inactivo = sin permisos) y, si falta, acepta con `PERMISO_REVOCADO` (SYN-10). …

**Texto propuesto**

> 4. **Permisos.** Todo tipo declara en el catálogo los permisos que exige (alguno de ellos basta). El bus los compara con los permisos actuales del usuario (inactivo = sin permisos) para todo comando, llegue por REST o por el lote: en `ONLINE`, si falta, rechaza con `PERMISO_REQUERIDO` antes del handler; en `OFFLINE`, acepta con `PERMISO_REVOCADO` (SYN-10). La ruta REST además lo exige antes de tocar la base. … (ADR-056)

### §6.5 Catálogo de tipos (D23, ADR-056; confirmado el 2026-10-22)

**Texto propuesto (párrafo nuevo):** "Cada tipo declara sus permisos (`permisos`, reemplaza a `permiso_offline`) y, si siempre recibe un secreto (contraseña o PIN), `exige_credenciales_efimeras`: el secreto viaja fuera del contenido y de la huella, y el lote rechaza ese tipo en cualquier modo (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`); desde un dispositivo revocado no se guarda en cuarentena. Ningún error de validación devuelve el valor recibido (ADR-055, ADR-056)."

### §6.3 orden en el lote (D23, aprobado el 2026-10-23)

**Texto propuesto (frase final del paso 4):** "En el lote el permiso se evalúa antes de validar el contenido: quien no lo tiene recibe solo `PERMISO_REQUERIDO`, nunca el detalle de la validación (ADR-056)."

### §7.3 orden de la venta (D18)

**Texto propuesto (párrafo nuevo):** "Dentro de `VENTA_CONFIRMAR` no hay bloqueos nuevos: cliente y lista, `saldo_cuenta` (nivel 1), productos, motor de descuentos y comparación (precio, descuento, total), evaluación del descuento manual, evaluación de crédito con el saldo bloqueado, verificación de los PIN necesarios (permiso, bloqueo, PIN; el contador de fallos va en una transacción aparte), stock, escrituras y dispositivo. Precedencia de rechazos: contenido, cliente, precio, descuento, tope y motivo, crédito, PIN, stock, número (ADR-055)."

### §18 Seguridad (D24, enmienda a ADR-018)

**Texto actual**

> - Límite de intentos en login por usuario y por IP.

**Texto propuesto**

> - Límite de intentos en login por usuario (5) y por IP (20): cada bloqueo dura 15 minutos desde el último fallo; los intentos durante el bloqueo no cuentan ni lo extienden (ADR-018 enmendado). Detrás del proxy, el backend toma la IP del cliente de los encabezados reenviados (`--proxy-headers`).
> - El servidor exige el permiso de cada comando por cualquier camino (ADR-056).
> - El límite de 5 del login se cuenta por el par (organización, usuario) tal como se escribió, exista o no (un nombre inexistente se bloquea igual que uno real); todo rechazo de credenciales verifica la contraseña (hash ficticio si no hay usuario utilizable); el 429 del login muestra siempre la hora de `America/Argentina/Buenos_Aires` (ADR-057, enmienda a ADR-018).

### §10.4 Motor de cálculo compartido (D5)

**Texto actual (fragmento)**

> el motor completo de venta —bruto, descuentos, totales, crédito— vivirá en `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` desde el change 18a, … Los de crédito se agregan en el 18b (ADR-054).

**Texto propuesto:** "… el motor de venta —bruto, descuentos y totales— vive en `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts`; la evaluación de crédito (CRE-01 a CRE-08) vive en `clientes/domain/credito.py` y `frontend/src/domain/credito/`, con sus casos en `shared/fixtures/calculo/cre-01-credito.json` (`"motor": "cre01"`) (ADR-055)."

### §12.4 Autorización de supervisor

**Texto propuesto (viñeta nueva):** "Con conexión, el PIN viaja fuera del contenido del comando y el servidor lo verifica contra la derivación guardada; los fallos se cuentan por usuario que intenta y supervisor en una transacción aparte: al llegar a `intentos_pin_max` ese usuario no puede usar ese PIN, y con 20 fallos sumando todos los usuarios el PIN se bloquea para todos; cada bloqueo dura 15 minutos desde el último fallo y los intentos durante el bloqueo no cuentan; toda definición del PIN reinicia la cuenta. El servidor rechaza PIN triviales: todos los dígitos iguales o una escalera de paso 1, ascendente o descendente (ADR-019, ADR-055). Cada supervisor puede definir su propio PIN confirmando su contraseña («Mi PIN»); las contraseñas incorrectas cuentan para el límite del login (ADR-018)."

---

## `03-modelo-de-datos.md`

### §12 `venta` (D12)

**Texto actual**

> | `credito_limite`, `credito_saldo_considerado`, `credito_disponible`, `credito_exceso` | `numeric(14,2)` | CRE-10; las agrega el change 18b (ADR-054 D15) |
> | `credito_politica`, `credito_resolucion` | `text` | Las agrega el 18b. `ADVERTENCIA_ACEPTADA`, `PERMISO_PROPIO`, `PIN_SUPERVISOR`, `TOLERANCIA_OFFLINE`, `SIN_EXCESO` |
> | `credito_autorizador_id` | `uuid` | Lo agrega el 18b |

**Texto propuesto**

> | `credito_limite`, `credito_saldo_considerado`, `credito_disponible`, `credito_exceso` | `numeric(14,2)` | CRE-10. Nulos en las ventas anteriores al 18b; límite, disponible y exceso nulos juntos significan sin control |
> | `credito_politica`, `credito_resolucion` | `text` | `ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`; `ADVERTENCIA_ACEPTADA`, `PERMISO_PROPIO`, `PIN_SUPERVISOR`, `TOLERANCIA_OFFLINE`, `SIN_EXCESO` |
> | `credito_autorizador_id` | `uuid` | FK compuesta a `usuario`; obligatorio con `PIN_SUPERVISOR` |

### §12 `venta_linea_descuento` (D12)

**Texto actual**

> `id`, `organizacion_id`, `venta_linea_id`, `origen` (`AUTOMATICO`, `MANUAL`), `regla_id` (nulo si manual), `porcentaje` `numeric(9,6)`, `importe` `numeric(14,2)`, `motivo_id`, `autorizador_id` (DSC-08).

**Texto propuesto:** el mismo, más `orden`; FK compuestas a `venta_linea`, `regla_descuento`, `motivo` y `usuario`; `CHECK` de origen, regla nula si y solo si es manual, importe > 0, porcentaje en (0, 1] o nulo (importe fijo); índice único parcial por línea donde `origen = 'MANUAL'`; `app_runtime` con `SELECT, INSERT` (INV-10).

### §4 y §13

**Texto propuesto (revisado 2026-10-22, D3):** tabla nueva `intento_pin_autorizacion` (`id`, `organizacion_id`, `autorizador_id`, `intentante_id` —obligatorio salvo en la fila marcador—, `exito` —`true` solo en la fila que reinicia la cuenta al definir el PIN—, `creado_en`; índices `(organizacion_id, autorizador_id, creado_en)` y `(organizacion_id, autorizador_id, intentante_id, creado_en)`; solo inserción); `ck_observacion__codigo` suma `AUTORIZACION_OFFLINE`.

---

## `04-roadmap-changes.md`

### §2 Tamaño

**Texto propuesto (al final de la viñeta de tamaño):** "El change 18b (`venta-online-descuentos-credito`) se implementa en cinco lotes y pasa de la estimación: se anota como excepción de tamaño (ADR-055)."

### §9 Fila 18b (D15)

**Texto actual (fragmento):** "… su propio tope de descuento aplicable (p. ej. "Podés descontar hasta 5 %; más pide autorización"), recibido con el bootstrap (SYN-11)."

**Texto propuesto:** "… su propio tope de descuento aplicable (…), recibido con la lectura de contexto de venta (`GET /api/v1/ventas/contexto`), que el bootstrap del 21 reutiliza (SYN-11; ADR-055)."

### §9 Deudas (al archivar)

**Texto propuesto (párrafo nuevo):** "**Change 18b — deudas saldadas (ADR-055):** del 16 (motor y evaluación en la venta, pantalla con general y propio, PIN, `venta_linea_descuento`, DSC-09, auditoría, comando de parámetros, motivos, tope visible, sin conexión), del 16b (ayuda del descuento manual en la venta), del 18a (columnas `credito_*`, crédito y descuentos sin conexión, consumidor final frente al límite cero) y de ADR-032 (tolerancia porcentual). **Deudas nuevas:** una limpieza periódica de las filas de `intento_login` de más de 24 horas, prevista por ADR-018 y todavía no implementada (no hay código que las borre y `app_runtime` no tiene `DELETE`; ADR-057 punto 9), sin dueño; al **21**, incluir en el bootstrap el contexto de venta (tope, motivos, autorizadores con la derivación del PIN) y los datos de crédito por cliente con la tolerancia aplicable; al **22a**, verificación local del PIN con límite de intentos en la interfaz y el armado de la evaluación de crédito del dispositivo; al **25**, mostrar `AUTORIZACION_OFFLINE`, las causas de `DESCUENTO_DIFIERE` y `EXCESO_CREDITO_DETECTADO_SYNC` (la "notificación a administración" de CRE-09); sin dueño: alta y baja de motivos (ya nominada por el 17b)."
