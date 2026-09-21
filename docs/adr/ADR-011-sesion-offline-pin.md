# ADR-011 — Sesión offline y desbloqueo con PIN

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §14, `docs/02` §12 |

## Contexto

El vendedor puede pasar horas sin señal. El access token vence a los 15 minutos. Se necesita una forma de mantener la sesión activa y de que un supervisor autorice excepciones sin conexión.

## Decisión

**Desbloqueo local:** el vendedor define un PIN con conexión, guardado en el dispositivo como derivación PBKDF2 (Web Crypto) con sal e iteraciones altas. Sin señal, el PIN desbloquea la sesión local. Tras superar el límite de intentos configurado, se requiere login con conexión (la cola se conserva).

**PIN de autorización de supervisor:** distinto del PIN de desbloqueo, de al menos 6 dígitos. El bootstrap incluye la derivación PBKDF2 de los supervisores de la organización para validación local. Toda autorización offline queda con observación y auditoría.

**Dispositivos:** se registran en el primer login y pueden revocarse. Los comandos de un dispositivo revocado van a cuarentena.

Al volver la conexión se usa el refresh token. Si venció, se pide login; la cola se conserva y se sincroniza cuando el mismo usuario inicia sesión.

## Consecuencias

- **Riesgo aceptado:** una derivación de PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo. Mitigaciones: longitud mínima de 6 dígitos, rotación desde administración, límite de intentos en la interfaz, toda autorización offline deja observación y auditoría. El cifrado local de IndexedDB se evalúa en la etapa 4.
- Los datos del bootstrap se minimizan (SYN-11): sin costos ni utilidades salvo permiso, sin datos de otras organizaciones.
- Un teléfono perdido se mitiga revocando el dispositivo desde administración.

## Extensión (2026-09-19, change 03) — Invalidación del PIN de autorización al perder el permiso que lo habilita

**Decisión confirmada, sin ADR nuevo (extiende esta misma):** cuando un usuario pierde, por un cambio en la composición de su rol, todos los permisos que habilitan la autorización de excepciones (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR` — la regla `rol_confiere_autorizacion_excepcion`, `03` tarea 5.5), el servidor borra `pin_autorizacion_hash` y `pin_autorizacion_sal` de ese usuario **en la misma transacción** que el cambio de rol/permiso que causó la pérdida, y audita el borrado junto con ese cambio (mismo movimiento, sin exponer el PIN).

- **No hace falta ADR nuevo**: es la consecuencia directa de que el PIN solo tiene sentido para quien puede autorizar excepciones; no cambia ningún mecanismo ya decidido (PBKDF2, quién deriva, rotación).
- **Recuperar el permiso más adelante no restaura el PIN viejo**: el usuario queda sin PIN hasta que un administrador le asigne uno nuevo desde administración (mismo camino que el alta inicial).
- **Riesgo aceptado explícito, no mitigado por esta extensión**: un dispositivo con bootstrap previo retiene el hash PBKDF2 cacheado localmente hasta el próximo bootstrap; durante esa ventana, la autorización offline con el PIN invalidado en el servidor puede seguir "validando" localmente. Es el mismo riesgo aceptado que esta ADR ya declaraba para el PIN en general (ventana de desactualización del caché local), no uno nuevo.
- Implementación: `identidad/service.py`, tarea `03` 8.9.a.
