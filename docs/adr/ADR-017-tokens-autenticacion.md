# ADR-017 — Tokens: access en memoria, refresh rotativo en cookie vinculado a dispositivo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/02` §12 y §19 |

## Contexto

El sistema tiene una PWA que opera offline. Los tokens de autenticación deben ser seguros frente a XSS y permitir revocar sesiones por dispositivo.

## Decisión

**Access token:** JWT firmado, vida de 15 minutos, guardado solo en memoria (no en localStorage ni en cookies). Contiene usuario, organización y dispositivo. Los permisos no viajan en el token; se cargan por petición con caché breve en memoria del proceso.

**Refresh token:** opaco, rotativo en cada uso, guardado en la base como hash. Se envía en cookie `HttpOnly`, `Secure`, `SameSite=Strict`, restringida a `/api/v1/auth`. Vinculado a usuario y dispositivo, con vencimiento deslizante de 30 días.

Reutilizar un refresh token ya rotado revoca toda la familia de tokens de ese dispositivo (detección de robo).

**Sin conexión:** el access token en memoria se pierde al cerrar el navegador. El PIN de desbloqueo (ADR-011) protege la sesión local; al volver la conexión se usa el refresh token para obtener un nuevo access token.

## Consecuencias

- Los permisos no en el token significa que una revocación tiene efecto inmediato con conexión (sin esperar que venza el token).
- La cookie `HttpOnly` impide que JavaScript lea el refresh token, protegiendo frente a XSS.
- Frontend y API en el mismo origen (servidos por Caddy): sin CORS abierto.
- Si el refresh token vence mientras el vendedor está offline (tras 30 días sin conexión), debe hacer login; la cola se conserva.

## Alternativas consideradas

- **Permisos en el token:** más eficiente pero con latencia de revocación igual a la vida del token (15 min). Descartado para un sistema donde revocar permisos debe ser inmediato.
- **Access token en localStorage:** expuesto a XSS. Descartado.
