# ADR-021 — Resolución de organización en el login

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-19 |
| Referenciado en | `docs/01` (usuario único por organización), `docs/02` §12/§18, change 03 |

## Contexto

`usuario` es único por `(organizacion_id, usuario)`, no globalmente: el mismo nombre de usuario (por ejemplo `admin`) puede existir en organizaciones distintas. El login recibe usuario y contraseña antes de que exista ningún token, así que no hay forma de obtener `organizacion_id` del JWT como en el resto de las rutas (regla no negociable de `CLAUDE.md` §4: "`organizacion_id` se toma siempre del token JWT, nunca del cuerpo de la petición" — esa regla aplica a rutas autenticadas; el login es la excepción que la antecede).

Sin resolver la organización antes de validar credenciales, el backend no sabe contra qué fila de `usuario` comparar la contraseña.

## Decisión

El cuerpo de la petición de login incluye `organizacion_slug` (o `organizacion_codigo`) además de `usuario` y `contraseña`. El usuario final solo escribe usuario y contraseña; el frontend inyecta el slug desde su configuración de build (`VITE_ORG_SLUG` u equivalente), sin que la persona lo vea ni lo elija en un selector.

El backend resuelve `organizacion_slug → organizacion_id` con una consulta de lookup contra la tabla `organizacion` **antes** de validar credenciales. Si el slug no existe, el login falla con el mismo mensaje genérico que una contraseña incorrecta (no revela si el slug es válido).

Rate limiting de login (ADR-018) se aplica por `(usuario, organizacion_id)` y por IP — no solo por IP global, para no confundir intentos fallidos de organizaciones distintas entre sí.

Camino de evolución explícito: en una etapa posterior (multi-tenant con subdominios), el slug puede resolverse desde el subdominio de la request en vez de venir en el body, sin cambiar el resto del backend — la función de resolución de slug queda aislada para ese reemplazo.

## Consecuencias

- El contrato de `POST /auth/login` incluye `organizacion_slug` en el body, documentado en la spec `identidad/autenticacion-y-sesion`.
- La tabla `organizacion` necesita una columna `slug` única (si no existe ya) para este lookup — verificar contra `03-modelo-de-datos.md` y agregar migración si falta.
- El lookup de slug es una consulta sin filtro de `organizacion_id` (es, por definición, cómo se obtiene ese filtro) — se declara como excepción explícita, mismo patrón que las funciones de catálogo global ya documentadas en el change 03.
- Rate limit de intentos de login se particiona por organización además de por IP, evitando que el bloqueo de una organización afecte a otra que comparte IP (ej. NAT de un mismo edificio).
- El frontend necesita saber su propio slug en tiempo de build o despliegue (una variable de entorno por instancia/organización desplegada), no en tiempo de ejecución por usuario.

## Alternativas consideradas

- **Selector de organización visible en el login:** más flexible (un mismo frontend sirve a varias organizaciones), pero expone el listado o requiere que el usuario lo escriba a mano, y agrega fricción a cada login. Descartado para esta etapa; el modelo de despliegue actual es una instancia por organización.
- **Búsqueda global de usuario+contraseña sin organización:** evita pedir cualquier dato adicional, pero rompe el patrón "todo query filtra por organización" del proyecto, complica el rate limiting por organización y agrega superficie de ataque (permite enumerar si un usuario existe en alguna organización probando contraseñas contra todas). Descartado.
