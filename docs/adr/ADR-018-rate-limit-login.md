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
