# ADR-028 — La sesión exige usuario y rol activos, sin perder la cola offline

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-25 |
| Referenciado en | ADR-011; ADR-012; ADR-017; ADR-027; `01-dominio.md` SEG-01, SEG-06, SYN-05, SYN-06, SYN-09, SYN-10, RUT-05, RUT-09; `02-arquitectura.md` §6.3, §6.4, §12.1, §12.3; `03-modelo-de-datos.md` §4 (`usuario.estado`, `rol.activo`); `openspec/changes/06b-permisos-efectivos-interfaz/design.md` D9 |

**Surgido del change 06b. Dominio CRÍTICO (autenticación y autorización). Aprobado explícitamente por el usuario el 2026-09-25, con las opciones D9.1, D9.2-A, D9.3-B y D9.4-A, y D9.5 como nota para el futuro change de baja de usuarios; estado *Vigente*.**

## Contexto

`03` §4 define `usuario.estado` (`ACTIVO`, `INACTIVO`) y `rol.activo`. `domain/usuarios.py` ya declara la transición `ACTIVO ↔ INACTIVO`. Pero hoy la sesión solo mira esos campos en un lugar:

| Punto | ¿Mira `usuario.estado`? | ¿Mira `rol.activo`? |
| --- | --- | --- |
| `identidad/service.py::iniciar_sesion` (login) | Sí: un usuario `INACTIVO` recibe el rechazo genérico de credenciales | No |
| `identidad/service.py::renovar_sesion` (refresh) | No | No |
| `identidad/service.py::listar_permisos_del_usuario` (usada en cada petición por `core/autenticacion.py::requiere_permiso`, y por `GET /yo` de ADR-027) | No | No |
| `POST /api/v1/sync/comandos` (`obtener_contexto_autenticado`, sin permiso por ruta) | No | No |

Consecuencia: un usuario pasado a `INACTIVO` conserva todos los permisos de su rol con su access token vigente, y puede seguir renovando la sesión con su refresh token. Como el vencimiento del refresh es deslizante (30 días desde cada rotación, ADR-017), **un dispositivo que se use al menos una vez por mes no pierde nunca la sesión**. Lo mismo vale para un rol con `activo = false`.

**Hoy la brecha es latente.** Ningún comando cambia el estado de un usuario ni desactiva un rol: los comandos de `identidad` son `USUARIO_CREAR`, `USUARIO_DESBLOQUEAR`, `ROL_PERMISOS_CAMBIAR`, `DISPOSITIVO_REVOCAR` y `PIN_AUTORIZACION_ROTAR`; `rol.activo` solo se escribe en `true` al crear las plantillas. Pasa a ser real el día que un change agregue la baja de usuarios o de roles (pantallas de usuarios y roles). Cerrarla antes evita que ese change nazca con un agujero.

Por qué no alcanza con "rechazar al inactivo en todos lados": el vendedor puede tener **ventas y cobranzas offline en la cola** cuando lo dan de baja. `00` §3 ("la realidad física manda": una venta offline ya entregada nunca se rechaza al sincronizar), SYN-05 (una venta o cobranza offline nunca se rechaza por permisos), SYN-09 (el dispositivo no borra una operación hasta que se acepta) y SYN-10 (si al sincronizar el usuario ya no tiene el permiso, se acepta con `PERMISO_REVOCADO`) exigen que esas operaciones lleguen al servidor. Y RUT-05 exige la cola vacía para rendir la jornada. Pero el lote se envía con un access token (`02` §6.4: solo ese usuario, autenticado en ese dispositivo, sincroniza su cola), y el access token dura 15 minutos: **si la renovación rechaza al inactivo, la cola del teléfono queda sin forma de subir**, porque el login también lo rechaza (`02` §12.3 dice que la cola "se sincroniza cuando inicia sesión el mismo usuario", y ese usuario ya no puede).

Hay además un hueco relacionado que condiciona el calendario: `POST /sync/comandos` todavía no aplica el paso 4 de `02` §6.3 (permisos por comando, online y offline). `sync/api.py` lo dejó para cuando existan comandos offline. Hoy todos los tipos declarados son solo `ONLINE` y no existen jornadas (change 15). Por lo tanto, la parte offline de esta decisión solo se puede implementar cuando llegue ese paso.

## Decisiones abiertas

### D9.1 — Qué se corta con conexión (sin alternativas razonables en disputa)

Toda petición autenticada que no sea el lote de sincronización se rechaza si el usuario está `INACTIVO` o su rol tiene `activo = false`, en la petición siguiente y sin esperar a que venza el access token (misma lógica que ADR-017 para un permiso quitado):

- `requiere_permiso` (y por lo tanto `requiere_comando_online`): rechazo antes de mirar el permiso.
- `GET /api/v1/yo` (ADR-027): rechazo, nunca una lista vacía que parezca una sesión válida.
- `listar_permisos_del_usuario` devuelve el conjunto vacío para un usuario o rol inactivo (falla cerrada, defensa en profundidad para cualquier consumidor futuro).
- El login ya rechaza al usuario inactivo y se mantiene igual (rechazo genérico, sin revelar la causa). Se agrega el rol inactivo al mismo rechazo genérico.

### D9.2 — Código de error para el usuario o rol inactivo

- **A) Reusar los 401 existentes** (recomendada): `IDENTIDAD_ACCESS_TOKEN_INVALIDO` en las rutas y `/yo`; `IDENTIDAD_REFRESH_TOKEN_INVALIDO` en la renovación. El cliente ya sabe qué hacer (renovar, y si no puede, pedir login; D3-A del 06b). No revela el estado del usuario a quien tenga el token. Es el mismo criterio que el login (rechazo genérico) y que D1 del 06b (usuario inexistente → `IDENTIDAD_ACCESS_TOKEN_INVALIDO`).
- **B) Código nuevo `IDENTIDAD_USUARIO_INACTIVO` (401).** La interfaz podría mostrar "Tu usuario fue dado de baja". A cambio, informa el estado del usuario y agrega un código al catálogo de `02` §11.
- **C) `403 PERMISO_REQUERIDO`** (tratarlo como "sin permisos"). No corta la sesión: el cliente no renueva ni pide login, y la persona queda en una interfaz vacía. No recomendada.

### D9.3 — Renovación de sesión de un usuario o rol inactivo, y entrega de la cola offline

- **A) Corte total.** `renovar_sesion` rechaza y revoca las familias de refresh del usuario (`motivo_revocacion = 'USUARIO_INACTIVO'` o `'ROL_INACTIVO'`, auditado). El lote también rechaza al inactivo.
  - A favor: es lo más simple y seguro, y la sesión muere en 15 minutos como máximo.
  - En contra: la cola offline queda varada en el teléfono. SYN-09 evita que se borre, pero no llega al servidor, y RUT-05 impide rendir la jornada. Recuperarla exige un procedimiento manual: reactivar al usuario, que inicie sesión, que sincronice y volver a desactivarlo. Durante ese lapso tiene todos sus permisos otra vez, y las ventas se aceptan sin `PERMISO_REVOCADO`. Choca con "la realidad física manda".
- **B) Corte online con canal acotado para la cola** (recomendada).
  - `renovar_sesion` rechaza y revoca las familias de refresh del usuario inactivo, **salvo** que ese dispositivo tenga una jornada no cerrada de ese usuario. Solo en ese caso emite el access token, porque es el único caso en que puede haber comandos offline pendientes (`02` §6.2: `OFFLINE` solo con jornada abierta).
  - Ese token no abre nada más: toda otra ruta rechaza al inactivo (D9.1). Solo `POST /sync/comandos` lo acepta.
  - En el lote, los comandos `OFFLINE` del inactivo se aceptan con la observación `PERMISO_REVOCADO` (SYN-10, SYN-05), para que un usuario con `REVISAR_OBSERVACIONES` los revise (SYN-08). Los comandos `ONLINE` se rechazan, igual que en REST.
  - Cuando la jornada se cierra, o la libera un supervisor (RUT-09), la excepción deja de aplicar y la sesión muere en la renovación siguiente. Queda por definir en el change 15 si una jornada `LIBERADA` sigue habilitando la entrega de su cola.
  - **Mientras no existan jornadas (hasta el change 15), la excepción nunca se cumple**: en el 06b, B se comporta igual que A para la renovación, sin varar nada, porque hoy no hay comandos offline. La rama del lote (`PERMISO_REVOCADO` por comando) se implementa con el paso 4 de `02` §6.3, en el change que lo agregue (15 o 18a), como deuda nominada.
  - A favor: ninguna venta entregada se pierde ni se traba, y la ventana en la que el inactivo tiene sesión queda acotada a su jornada en curso y a un solo uso, entregar su cola.
  - En contra: agrega una condición a la renovación que depende del módulo de jornadas, y un inactivo con jornada abierta podría fabricar comandos offline hasta cerrar la jornada. Lo mitiga que todos quedan con `PERMISO_REVOCADO` para revisión, y que el supervisor puede liberar la jornada (RUT-09) o revocar el dispositivo (SYN-06: cuarentena).
- **C) Inactivo tratado como dispositivo revocado (cuarentena).** Igual que B para la renovación, pero el lote del inactivo va entero a `comando_cuarentena` con motivo `USUARIO_INACTIVO` y responde `RECHAZADO`, para revisión manual.
  - A favor: nada entra a los libros sin una persona que lo mire.
  - En contra: contradice SYN-05 y SYN-10 (la venta offline se acepta con observación, no se rechaza) y amplía la lista cerrada de SYN-06. Exige enmendar `01` §13, y la venta ya entregada no descuenta stock ni genera deuda hasta que alguien la reprocese.
- **D) No cortar la renovación** (solo D9.1). Es lo más simple para el offline. Pero con el vencimiento deslizante, el inactivo mantiene su familia de refresh viva indefinidamente mientras use el dispositivo. Aunque no pueda operar online, conserva una sesión que no debería existir. No recomendada.

### D9.4 — Semántica de `rol.activo = false`

- **A) Igual que un usuario inactivo** (recomendada): quien tiene ese rol no pasa la autorización ni renueva, con las mismas reglas de D9.1 a D9.3. Hay una sola regla para la sesión ("usuario y rol activos"), y falla cerrada.
- **B) El rol inactivo no aporta permisos, pero la sesión sigue.** `listar_permisos_del_usuario` devuelve vacío, las rutas responden 403 y `/yo` responde 200 con lista vacía. Tiene más matices, pero deja sesiones vivas sin propósito.
- **Complemento para el change que agregue la baja de roles** (no se decide acá): con el criterio de ADR-024 y ADR-026, rechazar desactivar un rol que tiene usuarios activos asignados. Así, el caso D9.4 queda solo como defensa en profundidad.

### D9.5 — Al dar de baja (para el change que agregue el comando; se registra ahora para que no se olvide)

Recomendación: el comando que pase un usuario a `INACTIVO` revoca en la misma transacción todas sus sesiones de refresh, salvo la excepción de D9.3-B, y lo audita (AUD-01: cambios de usuarios), igual que `DISPOSITIVO_REVOCAR` revoca las del dispositivo. En el 06b no hay comando de baja, así que esta parte no se implementa.

## Recomendación conjunta

D9.1 como está, **D9.2-A**, **D9.3-B**, **D9.4-A** y D9.5 como nota para el change de usuarios y roles.

En el 06b se implementa:

- la verificación de usuario y rol activos en `requiere_permiso`, `GET /yo` y `listar_permisos_del_usuario`;
- el rechazo con revocación en `renovar_sesion` (sin la excepción de jornada, que no puede cumplirse todavía);
- el login rechazando también el rol inactivo;
- pruebas de integración que fijan que el lote de sincronización **no** rechaza en bloque al inactivo por ruta, para preservar el canal de B.

La rama offline del lote (`PERMISO_REVOCADO` para el inactivo) queda como deuda nominada para el change que implemente el paso 4 de `02` §6.3.

## Consecuencias (si se aprueba la recomendación)

- Una baja de usuario o de rol tiene efecto en la petición siguiente con conexión, como un permiso quitado (ADR-017). La interfaz `/admin` lo refleja sola: 401, renovación rechazada, `['yo']` descartada y aviso de iniciar sesión (D2-A y D3-A del 06b).
- Una sesión de un inactivo no sobrevive a la renovación, salvo, a partir del change 15, la entrega de la cola de su jornada abierta.
- Ninguna venta ni cobranza offline se pierde ni queda varada por una baja (`00` §3, SYN-05, SYN-09, SYN-10). RUT-05 sigue siendo cumplible.
- `requiere_permiso` hace una lectura más por petición, la del usuario con su rol. Se resuelve con la misma consulta que ya lee al usuario en `listar_permisos_del_usuario`, así que no suma un viaje extra a la base.
- Sin cambio de esquema: `motivo_revocacion` es texto libre y la auditoría ya existe.
- Hasta que exista el comando de baja, las pruebas siembran `INACTIVO` o `activo = false` directamente en la base de prueba.
- **Observación relacionada, fuera de este ADR:** un dispositivo revocado tiene el mismo problema de entrega. `revocar_dispositivo` revoca sus refresh tokens, así que su cola solo llega a la cuarentena de SYN-06 mientras le dure el access token. Se anota para que el usuario decida si se trata aparte.

## Alternativas consideradas

Las opciones no recomendadas de D9.2 a D9.4 (arriba). Además:

- **Verificar el estado dentro de `obtener_contexto_autenticado`**, en toda ruta autenticada. Es un solo punto, pero rechazaría también el lote de sincronización y cerraría el canal de D9.3-B. Descartada.
- **Poner el estado en el access token.** Tendría la misma latencia de 15 minutos que ADR-017 descartó para los permisos. Descartada.
