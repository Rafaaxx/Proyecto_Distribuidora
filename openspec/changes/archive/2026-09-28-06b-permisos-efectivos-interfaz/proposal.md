## Qué resuelve este change

Da a `/admin` una única fuente para decidir qué mostrar: `GET /api/v1/yo` (permisos efectivos, misma función que autoriza en el servidor), con `usePermisos()` y `<SiTienePermiso>`. Reemplaza el patrón "consulto y si da 403, oculto" de los changes 03 a 06 (ADR-027).

## Why

Hoy cada pantalla oculta ante un 403, el menú muestra todo a cualquiera y `ProductoFormScreen` hace un pedido extra solo para decidir un enlace. El change 07 y los siguientes deben nacer con el mecanismo nuevo (`04` §4).

## What Changes

- **Backend (`identidad`, lectura, sin bus):** `GET /api/v1/yo` devuelve `usuario`, `organizacion`, `rol` y `permisos` en orden alfabético.
  - Exige un access token válido y ningún permiso.
  - Usuario y organización salen del token.
  - Los permisos salen de la misma función que usa `requiere_permiso`.
  - Entra en la cobertura de aislamiento INV-21 y en la lista explícita de exentas del ratchet de permiso por ruta.
- **Frontend `/admin`:**
  - Consulta `['yo']` al iniciar sesión. Se invalida en cada renovación del access token y se descarta si la renovación falla.
  - `usePermisos()`, `<SiTienePermiso permiso>` y menú de `AdminLayout` por permiso.
- **Retiro del patrón reactivo:** ocho pantallas pasan a decidir su visibilidad con `usePermisos()`: dispositivos, productos, categorías y marcas, ficha de producto (sin la consulta extra `useCostoVigente`), proveedores, ficha de proveedor ("Cargar costos"), carga de costos e historial. Un 403 del servidor se sigue mostrando como "No tenés permiso".
- **`/ruta` no cambia** (SYN-10, SYN-11).
- **Cierre de la brecha de sesión con usuario o rol inactivo** (decisión del usuario del 2026-09-25, **CRÍTICO**, ADR-028 *Vigente*, aprobado el 2026-09-25 con D9.2-A, D9.3-B y D9.4-A).
  - Hoy `listar_permisos_del_usuario` (la fuente de `requiere_permiso` y de `/yo`) y `renovar_sesion` ignoran `usuario.estado` y `rol.activo`. Solo el login los mira. Así, un usuario pasado a `INACTIVO` conserva el acceso y puede renovar la sesión indefinidamente. Es latente: todavía ningún comando da de baja usuarios ni roles.
  - Con la opción recomendada de ADR-028:
    - las rutas de negocio y `/yo` rechazan al inactivo con 401 en la petición siguiente;
    - la renovación lo rechaza y revoca sus familias de refresh;
    - el lote de sincronización no se cierra por ruta, para que una cola offline pendiente nunca quede varada (SYN-05, SYN-09, SYN-10, `00` §3).
  - El tratamiento `PERMISO_REVOCADO` del lote queda como deuda nominada para el change que agregue los permisos por comando en sync.
  - **No se escribe código de esta parte hasta la aprobación explícita de ADR-028 y D9.**

## Reglas e invariantes

- **SEG-06:** ocultar nunca reemplaza la validación del servidor. Las pruebas de permiso siguen del lado del servidor.
- **Con D9:** SEG-01, SEG-06, SYN-05, SYN-09, SYN-10, RUT-05, ADR-017 y ADR-028.
- También aplica: SEG-07, `01` §19, ADR-017 (permisos fuera del token) y ADR-027.
- **INV-21 (sobre `GET /yo`):** la ruta no recibe identificadores. Una prueba con dos organizaciones y login real verifica que el usuario de B solo obtiene lo suyo, aunque informe la organización A en la consulta o en un encabezado. El ratchet de rutas falla si falta la cobertura.
- **Fixtures compartidos:** no toca precios, descuentos ni costos, así que no agrega ni modifica ninguno.

## Decisiones

**Aprobadas por el usuario el 2026-09-25** (todas con la opción A de `design.md`):

- **B1 (D3):** el menú falla cerrado mientras `/yo` carga o si falla, con **Reintentar** o un enlace a iniciar sesión.
- **B2 (D4):** quien entra por URL a una pantalla sin permiso ve "No tenés permiso…", y la pantalla no pide sus datos.
- **B3 (D5):** el login lleva a `/admin/inicio`, que redirige a la primera sección permitida, o informa que no hay ninguna.
- **B4 (D6):** el encabezado muestra "usuario · organización · rol".
- **Técnicas:**
  - D1: segundo router sin prefijo, `GET /api/v1/yo`, `obtener_yo`, y 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` si el usuario no existe.
  - D2: aviso de cambios desde `tokenStore`, invalidar `['yo']` con `cancelRefetch: false` y descartarla al limpiar el token.
  - D7: sin Playwright.
  - D8: unión literal `CodigoPermiso`.

**Abierta (CRÍTICA, bloquea solo el grupo 2 de `tasks.md`):** **D9 / ADR-028**, sesión con usuario o rol inactivo. Quedan por decidir el código de error, la renovación y la cola offline, y la semántica del rol inactivo. Las opciones y la recomendación están en `design.md` D9 y en ADR-028.

## No incluye

- Permisos en las respuestas de login o refresh (ADR-027).
- Renovación proactiva del token o restaurar la sesión al recargar.
- Topes de descuento en `/yo`.
- Pantallas de usuarios y roles, y el comando de baja de usuarios o roles (D9.5 queda como nota para ese change).
- La rama `PERMISO_REVOCADO` del lote para el usuario inactivo (deuda nominada, D9.3-B).
- Cambios en `/ruta`.
- Suite Playwright (D7).

## Capabilities

### New Capabilities
- `identidad/permisos-efectivos`: `GET /yo` y su consumo en `/admin` (consulta `['yo']`, refresco por renovación, `usePermisos`, `<SiTienePermiso>`, menú por permiso).

### Modified Capabilities
- `identidad/autorizacion-por-permiso`: `GET /yo` queda exenta del permiso por ruta de forma explícita. Sigue exigiendo sesión. Con D9, la autorización exige usuario y rol activos.
- `identidad/autenticacion-y-sesion`: con D9, la renovación y el login exigen usuario y rol activos.
- `sync/lote-de-comandos`: con D9, el lote no rechaza en bloque al usuario inactivo. El tratamiento por comando queda pendiente de D9.3.
- `catalogo/administracion-de-catalogo`: la pantalla decide su visibilidad con los permisos efectivos, no con la respuesta 403.
- `proveedores/administracion-de-proveedores`: lo mismo para proveedores y costos. El enlace al historial deja de depender de la consulta de costo vigente.

## Impact

- **Backend:** `identidad/api.py` (router sin prefijo, `YoResponse`), `identidad/service.py` (`obtener_yo`; con D9: `exigir_sesion_habilitada`, `listar_permisos_del_usuario`, `renovar_sesion`, `iniciar_sesion`), `core/autenticacion.py` (`requiere_permiso`, con D9), los dos ratchets y `openapi.json`. Sin migración.
- **Frontend:** `tokenStore.ts` (aviso de cambio de token), `features/identidad/`, `AdminScreen.tsx`, `AdminLayout.tsx`, las ocho pantallas y `schema.gen.ts`.
- **Docs:**
  - `docs/adr/ADR-028-sesion-exige-usuario-y-rol-activos.md`: *Vigente* (aprobado por el usuario el 2026-09-25).
  - La fila del 06b en `04-roadmap-changes.md` se actualiza **al archivar**, no ahora. Suma el cierre de la brecha (ADR-028) y la deuda nominada del lote (`PERMISO_REVOCADO` para el inactivo) para el change que agregue los permisos por comando en sync.
  - Opcionalmente, una enmienda a ADR-027 con B1 y B2.
