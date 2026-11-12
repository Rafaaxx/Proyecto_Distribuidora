# ADR-027 — Permisos efectivos para la interfaz: endpoint `GET /yo` como complemento de ADR-017

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-25 |
| Referenciado en | ADR-017; `02-arquitectura.md` §12.1, §13; `01-dominio.md` SEG-06, SYN-10, SYN-11; `04-roadmap-changes.md` change 06b |

**Surgido de la verificación manual del change 06 (tarea 13.5). Texto aprobado por el usuario el 2026-09-25; estado *Vigente*. Se implementa en el change 06b (`permisos-efectivos-interfaz`).**

## Contexto

ADR-017 decidió que los permisos **no viajan en el access token** y que el servidor los carga en cada petición, para que quitar un permiso tenga efecto inmediato con conexión. Esa decisión se mantiene: es la que corresponde en un sistema con dinero y personal rotativo, y SEG-06 exige que el servidor valide los permisos en cada comando de todos modos.

ADR-017 no resolvió cómo se entera la **interfaz** de qué puede hacer el usuario. Para `/ruta` está resuelto: el bootstrap incluye los permisos y topes del usuario (SYN-11), y sin conexión rigen esos (SYN-10). Para `/admin` no hay nada, y cada pantalla lo resolvió a su manera:

- `DispositivosScreen.tsx`, `ProveedoresListScreen.tsx` y `CostosHistorialScreen.tsx` hacen la consulta real y, si responde 403, muestran "No tenés permiso".
- `ProductoFormScreen.tsx` (change 06, tarea 14.3) consulta el costo vigente **solo para saber** si debe mostrar el enlace al historial: es un pedido de más en cada apertura de un producto.
- `AdminLayout.tsx` muestra todas las entradas del menú (por ejemplo "Proveedores") a cualquier usuario, aunque después la pantalla le diga que no tiene permiso.

Este patrón "consulto y si da 403, oculto" hace pedidos de más, muestra opciones que el usuario no puede usar y no escala a los changes siguientes, que suman pantallas con permisos distintos (`GESTIONAR_CLIENTES`, `PUBLICAR_LISTAS`, `VER_COSTOS` en reportes, etc.).

## Decisión

**1. Endpoint `GET /api/v1/yo`** (módulo `identidad`, lectura, sin bus de comandos). Requiere un access token válido y ningún permiso en particular. Devuelve:

```json
{
  "usuario": { "id": "…", "nombre": "…" },
  "organizacion": { "id": "…", "nombre": "…" },
  "rol": { "id": "…", "nombre": "…" },
  "permisos": ["GESTIONAR_CATALOGO", "VER_COSTOS", "…"]
}
```

- `permisos` sale de la **misma función** que usa el servidor para autorizar cada petición (`identidad/service.py`, permisos vigentes del usuario tomados de su rol). No existe una segunda fuente de verdad.
- `organizacion_id` y `usuario_id` salen del token, nunca de la petición.
- La lista va ordenada alfabéticamente, así la respuesta es estable.

**2. Frontend `/admin`:**

- Una única consulta TanStack Query `['yo']` se hace al iniciar sesión y se invalida **en cada renovación del access token** (cada 15 minutos o antes). Así, un permiso quitado también desaparece de la interfaz en ese plazo.
- Hook `usePermisos()` y componente `<SiTienePermiso permiso="…">`. El menú de `AdminLayout` y las pantallas usan **solo** este mecanismo para mostrar u ocultar.
- Se eliminan los usos del patrón reactivo para decidir visibilidad, empezando por la consulta extra de `ProductoFormScreen.tsx`. Una pantalla sigue tratando un 403 del servidor mostrando "No tenés permiso" (por ejemplo, si el permiso se quitó entre dos renovaciones), pero ya no lo usa para decidir qué mostrar.

**3. `/ruta` no cambia:** sigue usando los permisos del bootstrap (SYN-10, SYN-11).

**4. La interfaz nunca protege.** Ocultar una acción es una comodidad. El servidor sigue validando cada petición y cada comando (SEG-06, ADR-017), y toda prueba de permiso sigue siendo del lado del servidor.

## Consecuencias

- Se mantiene la revocación inmediata en el servidor (ADR-017). En la interfaz, un permiso quitado deja de mostrarse en 15 minutos como máximo, o al recargar la página.
- Hay un pedido extra por sesión y por renovación, en lugar de uno por pantalla o enlace.
- Los permisos no se guardan en `localStorage` ni en IndexedDB en `/admin`: viven en la caché en memoria de TanStack Query, igual que el access token (ADR-017).
- Implementarlo requiere un change propio, chico, con backend (endpoint + pruebas de aislamiento INV-21) y frontend (hook, componente, menú, retiro del patrón reactivo). Se ubica como change **06b** (`permisos-efectivos-interfaz`), **después de archivar el change 06 y antes del change 07** (`clientes`), para que los changes siguientes nazcan usando el mecanismo (`04-roadmap-changes.md` §4 y §6).
- `02-arquitectura.md` §12.1 suma una línea que remite a este ADR.

## Alternativas consideradas

- **Permisos en el access token.** Es lo más simple para la interfaz, pero es justo lo que ADR-017 descartó: un permiso quitado seguiría valiendo hasta 15 minutos también en el servidor. Descartado.
- **Permisos en un token separado solo para la interfaz** (un JWT sin validez para la API). Duplica el mecanismo de firma y renovación sin ventajas sobre un endpoint de lectura. Descartado.
- **Mantener el patrón reactivo (403 → ocultar).** Tiene los problemas descritos en el contexto y crece con cada change. Descartado.
- **Devolver los permisos en la respuesta de login y de refresh.** Evita un pedido, pero mezcla autorización con el flujo de autenticación (cookie restringida a `/api/v1/auth`, ADR-017) y obliga a renovar el token para refrescar permisos. Se puede reconsiderar como optimización más adelante; no es necesario ahora.
