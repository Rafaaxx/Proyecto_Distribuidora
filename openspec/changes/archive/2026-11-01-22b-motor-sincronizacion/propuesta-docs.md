# Propuesta de cambios a `docs/` — change 22b `motor-sincronizacion`

> **Propuesta completa (tarea 17.1) con lo aprobado en 0.1 (opción A en todas, salvo D6 = B) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-064-motor-de-sincronizacion-del-telefono.md` (hoy *Propuesto*; pasa a *Vigente* al archivar).
>
> Orden: `01` §13 SYN-09; `02` §6.6, §12.1, §12.4, §13.2, §13.3, §13.5; `04` §11.

---

## `01-dominio.md`

### §13 — SYN-09 (estados de envío; el resultado no borra)

**Texto actual**

> | SYN-09 | El dispositivo no elimina una operación local hasta recibir ACEPTADO o ACEPTADO_CON_OBSERVACIONES. Un RECHAZADO queda visible en el dispositivo. Ni el bootstrap, ni el cierre de sesión, ni el inicio de sesión de otro usuario borran ventas, cobranzas, movimientos ni comandos locales; quedan «Sin enviar» (`PENDIENTE`) hasta el envío (ADR-063). | 1 |

**Texto propuesto**

> | SYN-09 | El dispositivo no elimina una operación local hasta recibir ACEPTADO o ACEPTADO_CON_OBSERVACIONES, y ni siquiera entonces la borra: el resultado solo cambia su estado de envío. Cada venta local es «Sin enviar» (`PENDIENTE`) al confirmarla y pasa a «Enviada» (`ACEPTADA`), «Con observaciones» (`CON_OBSERVACIONES`) o «Rechazada» (`RECHAZADA`) únicamente con el resultado del servidor. Un RECHAZADO queda visible en el dispositivo, no se reenvía solo y se avisa. Ni el bootstrap, ni el cierre de sesión, ni el inicio de sesión de otro usuario, ni el bloqueo del PIN de desbloqueo, ni recibir el resultado borran ventas, cobranzas, movimientos ni comandos locales (ADR-063, ADR-064). | 1 |

---

## `02-arquitectura.md`

### §6.6 — Compatibilidad de versiones (versión de la compilación y bloqueo en el teléfono)

**Texto actual**

> - El servidor publica la versión mínima de la aplicación. Una aplicación por debajo de la mínima puede sincronizar su cola pero no confirmar operaciones nuevas hasta actualizarse.

**Texto propuesto**

> - El servidor publica la versión mínima de la aplicación (`GET /api/v1/version`, `app_version_minima`). Una aplicación por debajo de la mínima puede sincronizar su cola pero no confirmar operaciones nuevas hasta actualizarse.
> - La compilación del frontend lleva su versión (`APP_VERSION`, formato `X.Y.Z`; por omisión `dev`). El teléfono guarda en `meta` la última mínima conocida cada vez que sincroniza y compara por números, no por texto. Por debajo de la mínima, «Vender» queda deshabilitado en el inicio y en la ficha del cliente, y «Confirmar venta» no confirma (con un carrito abierto, el carrito sigue y se muestra el aviso); la cola se sigue enviando. Sin señal vale la última mínima conocida. Si la versión de la compilación o la mínima no tienen formato `X.Y.Z`, no se restringe nada. La compilación de producción debe definir `APP_VERSION` (ADR-064).

### §12.1 — Tokens (renovación serializada entre pestañas, D11 = A)

**Texto actual**

> - Reutilizar un refresh token ya rotado revoca toda la familia de tokens de ese dispositivo.

**Texto propuesto**

> - Reutilizar un refresh token ya rotado revoca toda la familia de tokens de ese dispositivo.
> - **DEBE:** en `/ruta`, la renovación del access token con el refresh token se serializa entre las pestañas del navegador con un Web Lock (`distribuidora:renovacion`): el refresh token rota en cada uso, así que dos pestañas que renuevan a la vez presentarían el mismo refresh token y la segunda revocaría la familia. La cookie se lee dentro del candado, por lo que la pestaña que espera envía la que dejó la anterior. Un reuso real de un refresh token ya rotado sigue revocando la familia. Sin Web Locks queda una renovación en vuelo por pestaña. No hay cambios en el servidor (ADR-064).

### §12.4 — Autorización de supervisor sin conexión (límite local entre pestañas, D9)

**Texto actual**

> - **Riesgo aceptado:** una derivación de un PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo. Mitigaciones: longitud mínima, rotación desde administración, límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría. El límite local cuenta los fallos por par (usuario, supervisor) en la tabla `intentos_pin`; al llegar a `intentos_pin_max` el PIN de ese supervisor queda bloqueado en el teléfono hasta el próximo bootstrap, sin guardar horas (ADR-063).

**Texto propuesto**

> - **Riesgo aceptado:** una derivación de un PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo. Mitigaciones: longitud mínima, rotación desde administración, límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría. El límite local cuenta los fallos por par (usuario, supervisor) en la tabla `intentos_pin`; al llegar a `intentos_pin_max` el PIN de ese supervisor queda bloqueado en el teléfono hasta el próximo bootstrap, sin guardar horas (ADR-063). **DEBE:** el límite vale entre pestañas: la verificación completa de un par (lectura del estado, derivación y escritura del fallo) corre bajo un Web Lock por par (`distribuidora:pin:{usuario}:{supervisor}`) y dentro de una transacción de lectura y escritura de Dexie, y el bloqueo se vuelve a leer antes de responder; así, intentos simultáneos desde dos pestañas no superan `intentos_pin_max` en total y ninguna derivación de más pasa como correcta después del bloqueo. Dos supervisores distintos no se esperan entre sí. Sin Web Locks rigen la transacción atómica y la nueva lectura. Esto cierra el contador de la interfaz y no cambia el riesgo aceptado de arriba (ADR-064).

### §13.2 — Base local (Dexie): `cola.estado` con resultado y `meta` con la sincronización

**Texto actual**

> | `ventas`, `cobranzas` | Operaciones locales con estado de envío (`PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`) y los datos congelados de la nota |
> …
> | `cola` | Comandos pendientes ordenados por secuencia; `operation_id` único |

(y el párrafo «`meta` guarda también el usuario local, la jornada, la fecha del bootstrap y la derivación del PIN con su contador de fallos…»)

**Texto propuesto**

> | `ventas`, `cobranzas` | Operaciones locales con estado de envío (`PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`; solo cambia con el resultado del servidor) y los datos congelados de la nota |
> …
> | `cola` | Comandos ordenados por secuencia; `operation_id` único. `estado` es `PENDIENTE` hasta el resultado y luego `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO`, con el código de error y el momento del resultado. Nada se borra; se envían solo los `PENDIENTE` del usuario y del dispositivo de la sesión (ADR-064) |
>
> Párrafo de `meta`: se agrega que `meta` guarda además el estado de la sincronización: `ultima_sincronizacion` (momento del último ciclo exitoso), `ultimo_error_sync` (tipo, código y momento del último corte, que un éxito posterior borra) y `app_version_minima` (última mínima conocida, §6.6). No hay versión nueva de Dexie: el índice `estado` de `cola` ya existía (ADR-064).

### §13.3 — Motor de sincronización

**Texto actual**

> - Se dispara al abrir la aplicación, en el evento `online`, después de cada operación local si hay conexión, cada 2 minutos mientras la aplicación está abierta y con el botón "Sincronizar".
> - **DEBE:** una sola sincronización a la vez, garantizada con Web Locks API, incluso con varias pestañas abiertas.
> - Envía lotes en orden (§6.4), aplica los resultados a la base local y reintenta errores transitorios con espera exponencial.
> - Muestra en todo momento: estado de conexión, cantidad de pendientes, última sincronización exitosa y operaciones con observaciones o rechazadas.

**Texto propuesto**

> - Se dispara al abrir la aplicación (al desbloquear o terminar el login), en el evento `online`, **al volver la aplicación a primer plano** (`visibilitychange` a `visible`), después de cada operación local si hay conexión, cada 2 minutos mientras la aplicación está abierta y con el botón "Sincronizar". Todos los disparadores valen solo con la sesión local desbloqueada; con la sesión bloqueada o cerrada no hay ninguno. «Sincronizar», `online` y la vuelta a primer plano ponen la espera exponencial en cero y envían en el momento (D6 = B); la venta y el periodo respetan la espera vigente.
> - **DEBE:** una sola sincronización a la vez, garantizada con Web Locks API (`distribuidora:sync`, `ifAvailable`), incluso con varias pestañas abiertas: la pestaña que no obtiene el candado no espera ni envía y muestra «Sincronizando en otra pestaña». Si llegan disparadores durante un envío propio, se hace a lo sumo una vuelta más al terminar. Sin Web Locks hay un candado dentro de la pestaña; dos pestañas podrían entrar a la vez y es seguro porque el servidor no duplica (INV-06).
> - Usa una cola propia: envía en lotes de hasta 50, en orden de secuencia, solo los `PENDIENTE` del usuario y del dispositivo de la sesión (de cualquier jornada); un `RECHAZADO` no se reenvía solo. Aplica los resultados por `operation_id` en una sola transacción Dexie por lote (INV-01).
> - Clasifica los cortes: transitorios (sin red, 5xx, 429, `ERROR_TRANSITORIO` de un ítem) se reintentan con espera exponencial de 5, 10, 20, 40, 80 y luego 120 s fijos (±20 %); la sesión vencida (401 tras la renovación) no reintenta y pide iniciar sesión con señal; un error del pedido (403, 422) no reintenta solo y se muestra con su código.
> - Muestra en todo momento, en la cabecera de `/ruta`, el estado de conexión y «N sin enviar» (o «Todo enviado»), con un aviso si hay ventas rechazadas; el inicio y la pantalla «Sincronización» muestran además la última sincronización exitosa, el último error con su texto y código, el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas» (ADR-064).

### §13.5 — Service worker (guarda completa con el enrutador de datos)

**Texto actual**

> - Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto: con líneas cargadas el aviso dice «Hay una versión nueva: se instala al terminar la venta» y no ofrece «Actualizar» hasta confirmar o descartar la venta. Salir de la venta con líneas pide confirmar «¿Descartar la venta?» (ADR-063).

**Texto propuesto**

> - Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto: con líneas cargadas el aviso dice «Hay una versión nueva: se instala al terminar la venta» y no ofrece «Actualizar» hasta confirmar o descartar la venta. Con líneas cargadas, toda salida de la venta pide confirmar «¿Descartar la venta?»: el menú inferior, «Cancelar», cualquier enlace del cuerpo (por ejemplo «Ver más» de una ayuda) y el botón atrás del navegador; recargar o cerrar la pestaña pide el aviso propio del navegador (`beforeunload`). Confirmar la venta no pregunta. La aplicación usa el enrutador de datos de React Router (`createBrowserRouter`), que admite `useBlocker`; la guarda vive en la pantalla de venta (`useBlocker` y `beforeunload` con el carrito ocupado), y una referencia `salidaLibre` se enciende antes de las salidas propias de la pantalla (confirmar o descartar a pedido) para que no pregunte por ellas (ADR-063, ADR-064).

---

## `04-roadmap-changes.md`

### §11 — Fila del 22b y deudas

**Texto actual**

> | 22b | `motor-sincronizacion` | Envío de lotes al servidor, bloqueo único con Web Locks, reintentos con espera exponencial, pantalla de estado (pendientes, última sync, errores) | INV-06 (doble sync no duplica) |

**Texto propuesto**

> | 22b | `motor-sincronizacion` | Envío de lotes al servidor, bloqueo único con Web Locks, reintentos con espera exponencial, pantalla de estado (pendientes, última sync, errores) — **terminado (ADR-064)** | INV-06 (doble sync no duplica) |

Y, después del párrafo del change 22a, un párrafo nuevo:

> **Change 22b (`motor-sincronizacion`) archivado (fecha de archivo) — terminado (ADR-064).** Entrega: el motor de sincronización del teléfono (cola propia por secuencia, lotes de 50, un solo envío a la vez con Web Locks, resultados escritos por `operation_id` en una transacción, reintentos con espera exponencial y clasificación de los cortes), disparadores (abrir, `online`, primer plano, después de cada venta, cada 2 minutos y «Sincronizar»), estado en la cabecera de `/ruta`, en el inicio y en la pantalla «Sincronización», versión mínima de la aplicación (`APP_VERSION`), PIN de supervisor y renovación de sesión serializados entre pestañas, guarda completa del carrito con `createBrowserRouter`/`useBlocker`, cuatro claves de ayuda nuevas y `ruta.ventaSinEnviar` revisada. En el servidor, solo la prueba de concurrencia `test_inv06_doble_sincronizacion_venta.py` (sin cambios de código). **Deudas saldadas:** del 22a, enviar la cola por secuencia y solo la del usuario autenticado, escribir `estado_envio`, la versión mínima, el botón «Sincronizar», el PIN de supervisor entre pestañas y la guarda del carrito para los enlaces del cuerpo y el botón atrás. **Deudas nuevas:** al **22c**, conciliar los movimientos locales de las ventas aceptadas con un bootstrap posterior (hasta entonces el saldo y el stock locales las cuentan dos veces) y mostrar el detalle de las observaciones y traducir los códigos de rechazo en la pantalla de conflictos. **Prueba manual:** (fecha y resultado, `04` §2.1 punto 5).
