# ADR-018 — Rate limiting de login con tabla PostgreSQL

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §18, change 03 |

## Contexto

El endpoint de login necesita protección contra ataques de fuerza bruta. Con varios workers de FastAPI, un contador en memoria no comparte estado entre procesos: un atacante puede hacer N intentos contra cada worker sin activar el límite.

## Decisión

Tabla `intento_login` en PostgreSQL con columnas `usuario_id` (nulo si el usuario no existe), `ip`, `exito` boolean, `creado_en`. Dos límites independientes evaluados en cada intento:

- **Por usuario:** 5 intentos fallidos en los últimos 15 minutos → 429 con momento de desbloqueo.
- **Por IP:** 20 intentos fallidos en los últimos 15 minutos → 429.

Desbloqueo automático al vencer la ventana. Un usuario con `ADMIN_USUARIOS` puede desbloquear manualmente registrando un intento de desbloqueo. Una tarea de limpieza borra registros con más de 24 horas.

Si el usuario está bloqueado, la respuesta no revela si la cuenta existe.

## Consecuencias

- Sin nueva infraestructura: no se agrega Redis ni ningún servicio externo.
- Performance no es una preocupación: el login es infrecuente y la consulta filtra por `creado_en >= now() - interval '15 minutes'` con índice.
- La tabla también actúa como log de intentos de acceso fallidos (AUD-01).
- Los umbrales (5 intentos, 15 minutos, 20 por IP) son configurables en `configuracion_organizacion` si en el futuro se necesita ajustar por organización.

## Alternativas consideradas

- **Redis:** estándar para APIs de alto tráfico. Descartado porque agrega infraestructura (despliegue, monitoreo, backup) para un endpoint de login de volumen muy bajo.
- **En memoria por proceso:** no funciona con varios workers. Descartado.
- **Rate limit en Caddy:** posible como defensa adicional en la capa de proxy, pero no reemplaza el control por usuario (Caddy solo ve la IP). Puede agregarse como defensa en profundidad sin tocar este ADR.

## Enmienda del change 18b (ADR-055)

(1) **El bloqueo dura 15 minutos desde el último fallo.** Para cada límite (5 por usuario, 20 por IP), sea F el último fallo contado (por usuario, posterior al último desbloqueo manual): hay bloqueo si en (F − 15 min, F] hay al menos el límite y ahora < F + 15 min. El 429 informa F + 15 min; al vencer, el cupo vuelve entero. Antes el momento informado era el del fallo más antiguo de la ventana más 15 minutos y cada reintento lo extendía en la práctica. (2) **Los intentos bloqueados no cuentan ni se insertan.** Un intento rechazado por el bloqueo deja de escribirse en `intento_login` (no llegó a probar credenciales): "un `INSERT` por intento fallido" pasa a "por intento fallido que probó credenciales". Su rastro queda en la auditoría `LOGIN_BLOQUEADO_POR_INTENTOS` (por usuario, como hasta ahora) y en el log. (3) **Las contraseñas incorrectas de "Mi PIN" comparten el límite:** se anotan en `intento_login` (usuario e IP del cliente, `request.client.host`) en una transacción aparte, se evalúan los mismos dos límites antes de verificar la contraseña y el bloqueo responde `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` (429), también con la contraseña correcta; cinco fallos en "Mi PIN" bloquean también el login. (3b) **Texto del 429:** "Demasiados intentos. Probá de nuevo a las 23:45." con la hora de desbloqueo en HH:MM (24 h) en la zona horaria de la organización solo para "Mi PIN" (usuario ya autenticado); **el 429 del login (por IP y por par escrito) usa siempre la zona por defecto `America/Argentina/Buenos_Aires`, exista o no la organización (cambio confirmado el 2026-10-24, ADR-057)**. El texto tiene SIEMPRE esa forma, para que no revele si la organización o el usuario existen (nunca "más tarde"). Mismo código y mismo 429. (4) Sin cambios: los umbrales, el mensaje genérico que no revela si la cuenta existe, el desbloqueo manual (`USUARIO_DESBLOQUEAR`, solo el límite por usuario), la tabla y sus índices. (5) **Nota de despliegue:** detrás de Caddy la IP que ve el backend es la del proxy hasta configurar `uvicorn --proxy-headers --forwarded-allow-ips=<IP de Caddy>`, que corrige el límite por IP del login y de "Mi PIN" a la vez.

(6) **El límite de 5 es por par escrito (ADR-057, *Vigente* desde el 2026-10-24, al archivar el change 18b; confirmado por el usuario ese día).** El contador "por usuario" pasa a ser por el par (slug de organización, nombre de usuario) **tal como se escribió**, con la misma comparación exacta que el login, exista o no la organización o el usuario: un nombre inexistente se bloquea en el mismo intento que uno existente. Se guarda en `intento_login.clave_intento` (SHA-256 del par, índice `(clave_intento, creado_en)`); `usuario_id` se sigue llenando cuando el par resuelve un usuario, pero no se usa para contar. "Mi PIN" cuenta con el par guardado del propio usuario. El desbloqueo manual inserta el marcador con la clave del usuario y neutraliza los fallos anteriores de esa clave. El límite por par se evalúa después del de IP y antes de buscar el usuario. Todo rechazo de credenciales verifica la contraseña (contra un hash Argon2id ficticio si no hay usuario utilizable), para que el tiempo de respuesta no revele si el usuario existe o está activo. El bloqueo de un par sin usuario no escribe auditoría (solo log WARNING sin el texto escrito); el de un usuario real sigue escribiendo `LOGIN_BLOQUEADO_POR_INTENTOS`. El 429 del login muestra siempre la hora argentina (punto 3b). Donde este ADR dice "`usuario_id` (nulo si el usuario no existe)" y "Por usuario: 5 intentos fallidos", se lee "por par escrito".
