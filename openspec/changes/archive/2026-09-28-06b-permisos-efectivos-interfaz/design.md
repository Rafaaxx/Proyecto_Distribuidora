## Context

Ver `proposal.md` (Why). La decisión de fondo ya está tomada y vigente en ADR-027: endpoint `GET /api/v1/yo` y consumo en `/admin` con `usePermisos()`/`<SiTienePermiso>`. Este documento resuelve **cómo** implementarla y deja a la vista lo que ADR-027 no fija.

Estado del código relevante (inspeccionado el 2026-09-25):

- **Backend.**
  - `core/autenticacion.py::requiere_permiso` llama en cada petición, sin caché, a `identidad_service.listar_permisos_del_usuario(organizacion_id, usuario_id, sesion) -> frozenset[str]`. Esa función es el único punto de lectura de permisos: toma los permisos del rol del usuario y devuelve un conjunto vacío si el usuario no existe en esa organización.
  - `obtener_contexto_autenticado` resuelve usuario, organización y dispositivo desde el token sin exigir permiso.
  - `identidad/api.py` tiene un único `router` con prefijo `/identidad`. No existen `identidad/schemas.py` ni `identidad/queries.py`: los esquemas viven en `api.py`.
  - `Usuario.nombre`, `Organizacion.nombre` y `Rol.nombre` son `NOT NULL`, y `Usuario.rol_id` es `NOT NULL`, así que `rol` nunca es nulo. El repositorio ya expone `obtener_usuario_por_id`, `obtener_organizacion_por_id` y `obtener_rol_por_id`.
  - **Brecha de sesión (verificada el 2026-09-25, base de D9):** `listar_permisos_del_usuario` no mira `usuario.estado` (`ACTIVO`/`INACTIVO`, `CHECK` en `identidad/models.py`) ni `rol.activo`. `renovar_sesion` tampoco mira el estado del usuario. Solo `iniciar_sesion` exige `estado == "ACTIVO"`. `POST /sync/comandos` usa `obtener_contexto_autenticado` y todavía no aplica permisos por comando (paso 4 de `02` §6.3, `sync/api.py`). Es latente: ningún comando cambia `usuario.estado` ni `rol.activo` (solo existen `USUARIO_CREAR`, `USUARIO_DESBLOQUEAR`, `ROL_PERMISOS_CAMBIAR`, `DISPOSITIVO_REVOCAR` y `PIN_AUTORIZACION_ROTAR`, y `rol.activo` solo se escribe en `true` al crear las plantillas).
- **Ratchets.**
  - `tests/integration/test_inv21_ratchet_rutas.py` exige toda ruta de negocio en `COBERTURA_DE_AISLAMIENTO`, con prueba real de dos organizaciones y login real.
  - `tests/integration/test_ratchet_permiso_por_ruta.py` exige `requiere_permiso` en toda ruta que no esté en `RUTAS_EXENTAS_DE_PERMISO`.
  - `test_inv21_organizacion_siempre_del_token.py` recorre `COBERTURA_DE_AISLAMIENTO` buscando `organizacion_id` como parámetro.
  - El ratchet del bus solo mira escrituras.
- **Frontend.**
  - `lib/auth/tokenStore.ts` guarda el token en una variable de módulo, con `fijar`, `limpiar` y `obtener`.
  - `lib/api/httpClient.ts::apiFetch` renueva el token **solo ante un 401**, una vez y compartiendo la renovación en curso. Llama a `fijarAccessToken` si la renovación sale bien y a `limpiarAccessToken` si falla.
  - `useLogin` llama a `fijarAccessToken` y `LoginScreen` navega a `/admin/dispositivos`.
  - El `QueryClient` es de módulo en `AdminScreen.tsx`.
  - `AdminLayout.tsx` muestra Catálogo, Proveedores y Dispositivos a todos.
  - Patrón reactivo presente en `DispositivosScreen` (`PermisoRequeridoError`), `ProductosListScreen` y `CategoriasYMarcasScreen` (`PermisoRequeridoCatalogoError`), `ProveedoresListScreen` y `CostosHistorialScreen` (`PermisoRequeridoProveedoresError`), y en `ProductoFormScreen` (`useCostoVigente` solo para el enlace, tarea 14.3 del 06).
  - `CostosCargaScreen` y el enlace "Cargar costos" de `ProveedorFormScreen` no distinguen permiso: hoy muestran un error genérico.
  - `tests/e2e/` está vacío (`.gitkeep`): no hay Playwright configurado.

## Goals / Non-Goals

**Goals:**
- Una sola fuente de permisos para `/admin`, que salga de la misma función que autoriza en el servidor.
- Que ninguna pantalla haga un pedido solo para averiguar un permiso.
- Dejar el mecanismo listo para que el change 07 y siguientes solo declaren `<SiTienePermiso permiso="…">`.
- INV-21 cubierto sobre la ruta nueva, dentro de los ratchets existentes.
- Cerrar la brecha de sesión con usuario o rol inactivo (D9, ADR-028) antes de que exista el comando de baja, sin perder ni varar la cola offline.

**Non-Goals:**
- Cambiar cómo autoriza el servidor por permiso. `requiere_permiso` solo suma la verificación de usuario y rol activos (D9), sin cambiar la regla de permisos.
- El comando de baja de usuarios o de roles (D9.5 queda como nota para ese change).
- Renovación proactiva del token por temporizador.
- Restaurar la sesión al volver a `/admin` (raíz → `login`).
- `/ruta` y bootstrap.
- Pantallas de usuarios y roles.

## Decisions

> **Estado:** D1 a D8 están **aprobadas por el usuario el 2026-09-25**, todas con la opción A: técnicas D1-A, D2-A, D7-A y D8-A; comportamiento visible D3-A (**B1**), D4-A (**B2**), D5-A (**B3**) y D6-A (**B4**). Las specs delta reflejan esas opciones; las marcas **(B1)** a **(B4)** solo identifican de qué decisión sale cada escenario. Ninguna de estas decisiones cambia reglas de negocio de `01`. Si el usuario lo pide, B1 y B2 se registran como enmienda a ADR-027, porque aplican a todas las pantallas futuras (tarea 0.7, opcional). D1, D2, D7 y D8 no requieren ADR: son detalle de implementación de ADR-027.
>
> **D9 (brecha de sesión con usuario o rol inactivo) es CRÍTICA. El usuario la aprobó explícitamente el 2026-09-25** (ADR-028 *Vigente*: D9.1, D9.2-A, D9.3-B, D9.4-A). No quedan decisiones abiertas. El grupo 2 de `tasks.md` sigue con puntos de control por paso (gobernanza CRÍTICA).

### D1 — Ruta, router y función de servicio (técnica; A aprobada por el usuario el 2026-09-25)

ADR-027 fija la ruta `GET /api/v1/yo`, en el módulo `identidad`. Pero el router de `identidad` tiene prefijo `/identidad`.

- **A) Segundo router sin prefijo en `identidad/api.py`** (`router_yo = APIRouter(tags=["identidad"])`, ruta `/yo`), incluido en `api_v1/__init__.py`.
  - La dependencia es `obtener_contexto_autenticado`, no `requiere_permiso`.
  - El servicio es una función nueva, `identidad_service.obtener_yo(organizacion_id, usuario_id, sesion) -> DatosYo` (dataclass congelada). Lee usuario, organización y rol con los repositorios existentes, llama a `listar_permisos_del_usuario` y devuelve `sorted(...)`.
  - El esquema `YoResponse` va en `api.py`, igual que los demás de `identidad`.
  - **Consecuencia:** la ruta es exactamente la de ADR-027. Hay una sola fuente de permisos. Es el mismo patrón de dos routers que ya usa `proveedores/api.py`.
- **B) `/api/v1/identidad/yo` bajo el router existente.**
  - **Consecuencia:** es más simple, pero contradice la ruta fijada en ADR-027 y en `04` §6, y obliga a enmendar ambos.
- **C) En `api_v1/auth.py`.**
  - **Consecuencia:** mezcla autorización con el flujo de autenticación, que ADR-027 separa a propósito (cookie restringida a `/api/v1/auth`). Además, `auth.py` está exento de ambos ratchets.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

Si el usuario del token no existe en la organización del token (solo es posible con una base reiniciada o sembrada de nuevo bajo un token vigente), la respuesta es **401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO`**, no 404. Así el cliente intenta renovar y, si no puede, pide login. Nunca devuelve datos parciales.

### D2 — Cómo se entera la consulta `['yo']` de cada renovación del token (técnica; A aprobada por el usuario el 2026-09-25)

El token se renueva dentro de `apiFetch`, fuera de React. La consulta vive en el `QueryClient` de `AdminScreen`.

- **A) `tokenStore` avisa de sus cambios.** Expone `suscribirACambiosDeToken(listener) → desuscribir`. Avisa en `fijarAccessToken` (login o renovación) y en `limpiarAccessToken` (renovación fallida).
  - `AdminScreen` se suscribe una vez.
  - Si hay token nuevo, llama a `queryClient.invalidateQueries({ queryKey: ['yo'] }, { cancelRefetch: false })`, para no cancelar y duplicar una consulta `['yo']` en curso que fue justamente la que disparó la renovación.
  - Si el token se limpió, llama a `queryClient.removeQueries({ queryKey: ['yo'] })`.
  - La consulta usa `staleTime: Infinity` y `refetchOnWindowFocus: false`: solo se repite por esta invalidación, que es "un pedido extra por sesión y por renovación" (ADR-027).
  - **Consecuencia:** `tokenStore` es el único lugar donde cambia el token, así que no hay forma de olvidar un camino (login, renovación o fallo). `httpClient` no conoce React ni TanStack.
- **B) `httpClient` acepta un callback `alRenovarToken`,** registrado por `AdminScreen`.
  - **Consecuencia:** el login no pasa por la renovación y necesita su propio aviso. Quedan dos caminos que mantener.
- **C) El token forma parte de la clave de la consulta (`['yo', token]`).**
  - **Consecuencia:** refresca solo, pero pone el access token en claves de caché visibles en las devtools y deja entradas viejas. Descartada.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D3 — Menú mientras `/yo` carga o si falla (**B1**; A aprobada por el usuario el 2026-09-25)

ADR-027 no dice qué se ve antes de tener los permisos ni si la consulta falla.

- **A) Falla cerrada.**
  - Mientras está pendiente, el menú no muestra ninguna sección protegida. El encabezado sí se muestra.
  - Si falla, un aviso "No se pudieron obtener tus permisos" con botón **Reintentar**. Si falla porque la sesión terminó (401 tras una renovación fallida), el aviso ofrece ir a iniciar sesión.
  - **Consecuencia:** nunca se muestra una opción no confirmada. Es el mismo criterio que la tarea 14.3 del 06 ("no se asume permiso sin confirmación"). Hay un instante sin menú al entrar.
- **B) Falla abierta.** Mientras carga o si falla, se muestran todas las secciones y el servidor responde 403 donde corresponda.
  - **Consecuencia:** no hay menú vacío, pero reaparece justo el problema que ADR-027 quiere eliminar: opciones visibles que el usuario no puede usar.
- **C) Bloqueo total.** Todo `/admin` muestra "Cargando…" o una pantalla de error completa hasta tener `/yo`.
  - **Consecuencia:** es tan seguro como A, pero oculta también el encabezado y el "Volver". Es más invasivo ante un error transitorio.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D4 — Entrar por URL a una pantalla sin permiso (**B2**; A aprobada por el usuario el 2026-09-25)

ADR-027 dice que las pantallas usan **solo** este mecanismo para mostrar u ocultar, pero no qué pasa si el usuario escribe la dirección.

- **A) La pantalla muestra "No tenés permiso para …" sin pedir sus datos.**
  - Se usa el mismo texto que hoy muestra cada pantalla ante un 403.
  - El componente que carga datos queda dentro de `<SiTienePermiso permiso fallback={<SinPermiso …/>}>`. Así, sus consultas ni se montan.
  - Mientras `/yo` está pendiente, la pantalla muestra "Cargando…", no "sin permiso".
  - **Consecuencia:** los escenarios existentes ("ve el mensaje de falta de permiso") siguen valiendo y no hay pedidos de más. El manejo del 403 del servidor queda solo como red de seguridad.
- **B) Guardia por ruta que redirige en silencio a la primera sección permitida.**
  - **Consecuencia:** el usuario no entiende por qué no llegó adonde quería. Cambia escenarios ya archivados de catálogo y proveedores ("ve el mensaje…").
- **C) Mantener la consulta y resolver por el 403.**
  - **Consecuencia:** contradice ADR-027 ("solo este mecanismo").

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D5 — A dónde lleva el login (**B3**; A aprobada por el usuario el 2026-09-25)

Hoy `LoginScreen` navega siempre a `/admin/dispositivos`. Solo ADM y SUP tienen `GESTIONAR_DISPOSITIVOS` (`01` §19), así que un usuario de Administración ve "No tenés permiso" apenas entra.

- **A) Primera sección permitida.**
  - El login navega a una ruta índice nueva dentro del layout (`/admin/inicio`).
  - Esa ruta espera `/yo` y redirige a la primera sección permitida, en el orden del menú: Catálogo, Proveedores, Dispositivos.
  - Si no hay ninguna, muestra "Tu usuario no tiene secciones de administración disponibles".
  - Menú y redirección comparten una única lista de secciones (`features/identidad/secciones.ts`: ruta, etiqueta y permiso).
  - **Consecuencia:** nadie aterriza en una pantalla prohibida, y el change 07 suma su sección en un solo lugar.
- **B) Mantener `/admin/dispositivos`.**
  - **Consecuencia:** no cambia el flujo, pero el primer contacto de GES, VEN o CON es un mensaje de falta de permiso.
- **C) Página "Inicio" fija con accesos a las secciones permitidas.**
  - **Consecuencia:** agrega una pantalla nueva que ningún documento pide.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D6 — ¿El encabezado muestra usuario, organización y rol? (**B4**; A aprobada por el usuario el 2026-09-25)

ADR-027 devuelve `usuario`, `organizacion` y `rol` con su `nombre`, pero no dice si se muestran.

- **A) Sí.** A la derecha del encabezado de `AdminLayout`: "{usuario.nombre} · {organizacion.nombre} · {rol.nombre}".
  - **Consecuencia:** cuesta poco, sirve en PCs compartidas y en la verificación manual (se ve con qué usuario y rol se está probando), y usa los datos que el endpoint ya devuelve.
- **B) No.** El endpoint los devuelve y la interfaz todavía no los usa.
  - **Consecuencia:** hay datos devueltos sin uso, y la verificación manual depende de recordar con qué usuario se entró.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.** No incluye botón de cierre de sesión: ningún documento lo pide para este change.

### D7 — ¿Prueba punta a punta con Playwright en este change? (técnica; A aprobada por el usuario el 2026-09-25)

`02` §15 reserva Playwright para los criterios de `00` §9, en la rama principal. `tests/e2e/` está vacío y no hay configuración.

- **A) No.** La cobertura es:
  - integración del backend (Testcontainers, HTTP real, login real);
  - unitarias de frontend con Vitest (hook, componente, menú, pantallas, aviso del `tokenStore`, invalidación por renovación);
  - verificación manual en el navegador (grupo 10).
  - **Consecuencia:** es igual que los changes 03 a 06. Montar Playwright es un trabajo aparte.
- **B) Sí:** configurar Playwright y un caso (login GES → menú sin Dispositivos).
  - **Consecuencia:** agrega infraestructura (entorno levantado, siembra de usuarios por rol) que excede el tamaño de un change "chico" (ADR-027).

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D8 — Tipo de los códigos de permiso en el frontend (técnica; A aprobada por el usuario el 2026-09-25)

- **A) Unión literal `CodigoPermiso` en `frontend/src/domain/identidad/permisos.ts`,** con los códigos de `01` §19.
  - `usePermisos().tiene(permiso: CodigoPermiso)` y `<SiTienePermiso permiso: CodigoPermiso>`. La respuesta de la API sigue siendo `string[]`, y un código desconocido simplemente no se usa.
  - **Consecuencia:** un error de tipeo en una pantalla es un error de compilación. Si el backend agrega un permiso, el frontend lo suma cuando lo necesite.
- **B) `string` libre.**
  - **Consecuencia:** un error de tipeo oculta una sección para siempre sin ningún aviso.

**Recomendación: A. Aprobada por el usuario el 2026-09-25.**

### D9 — Sesión con usuario o rol inactivo (**CRÍTICO — aprobada por el usuario el 2026-09-25: D9.1, D9.2-A, D9.3-B, D9.4-A; D9.5 como nota**)

El usuario decidió el 2026-09-25 incluir en el 06b la brecha de Context ("Brecha de sesión"). La decisión de fondo está en **ADR-028** (*Vigente*, aprobado el 2026-09-25). Este resumen no la reemplaza: si difieren, manda el ADR (`CLAUDE.md` §1).

- **D9.1 — Qué se corta con conexión.** No hay alternativas en disputa. Un usuario `INACTIVO` o con rol inactivo se rechaza en:
  - `requiere_permiso` (y por lo tanto `requiere_comando_online`), antes de mirar el permiso;
  - `GET /yo`;
  - `listar_permisos_del_usuario`, que devuelve vacío (falla cerrada);
  - el login, que ya rechaza al usuario inactivo y suma el rol inactivo al mismo rechazo genérico.
  
  **No** se verifica en `obtener_contexto_autenticado`, porque cerraría el lote de sincronización (ver D9.3).
- **D9.2 — Código de error.**
  - A) Reusar `401 IDENTIDAD_ACCESS_TOKEN_INVALIDO` en rutas y `/yo`, y `401 IDENTIDAD_REFRESH_TOKEN_INVALIDO` en la renovación (**recomendada**: el cliente ya lo maneja y no revela el estado).
  - B) Código nuevo `IDENTIDAD_USUARIO_INACTIVO`.
  - C) `403 PERMISO_REQUERIDO`, que no corta la sesión.
- **D9.3 — Renovación y cola offline.**
  - A) Corte total. La cola offline queda varada; recuperarla exige reactivar al usuario a mano.
  - B) Corte online con canal acotado (**recomendada**). `renovar_sesion` rechaza y revoca las familias de refresh del inactivo, auditado, salvo que el dispositivo tenga una jornada no cerrada de ese usuario. Ese token solo lo acepta `POST /sync/comandos`, donde los comandos `OFFLINE` se aceptan con `PERMISO_REVOCADO` (SYN-10, SYN-05) y los `ONLINE` se rechazan. Sin jornadas (hasta el change 15), la excepción no aplica: en el 06b se implementa el rechazo, y la rama del lote queda como deuda nominada.
  - C) Cuarentena, como un dispositivo revocado. Contradice SYN-05 y SYN-10, y exige enmendar SYN-06.
  - D) No cortar la renovación. Con el vencimiento deslizante, la sesión nunca muere.
- **D9.4 — Rol con `activo = false`.**
  - A) Igual que un usuario inactivo (**recomendada**).
  - B) Sin permisos, pero con la sesión viva (403 en las rutas, `/yo` con lista vacía).
- **D9.5 — Nota para el change que agregue la baja de usuarios o roles** (no se implementa acá):
  - la baja revoca en la misma transacción las sesiones de refresh del usuario, y lo audita;
  - un rol con usuarios activos no se desactiva (criterio de ADR-024 y ADR-026).

**Punto técnico de implementación**, detalle de D9.1 que no requiere ADR:

- Una función nueva en `identidad/service.py`, `exigir_sesion_habilitada(organizacion_id, usuario_id, sesion)`. Lee usuario y rol en una sola consulta y lanza el error de D9.2 si el usuario no existe, está `INACTIVO` o su rol está inactivo.
- La usan `requiere_permiso` (antes de `listar_permisos_del_usuario`), `obtener_yo` (D1) y `renovar_sesion`.
- `obtener_yo` sigue tomando los permisos **solo** de `listar_permisos_del_usuario`, así se conserva "misma función" (ADR-027).

**Gobernanza: CRÍTICA.** Solo análisis hasta la aprobación explícita del usuario de ADR-028 y de D9 (tarea 0.9). Las specs delta marcan con **(D9)** los escenarios que dependen de esta decisión.

### Contrato de `GET /api/v1/yo`

| Campo | Valor |
| --- | --- |
| Método y ruta | `GET /api/v1/yo` (D1-A) |
| Autenticación | `Authorization: Bearer <access token>` (`obtener_contexto_autenticado`) |
| Permiso | Ninguno. Figura en `RUTAS_EXENTAS_DE_PERMISO` con el motivo escrito. |
| Parámetros | Ninguno. Todo sale del token. Cualquier parámetro de consulta o encabezado extra se ignora. |
| Bus de comandos / auditoría | No (lectura) |
| Éxito | `200` |
| Errores | `401 IDENTIDAD_ACCESS_TOKEN_AUSENTE` / `IDENTIDAD_ACCESS_TOKEN_INVALIDO` / `IDENTIDAD_ACCESS_TOKEN_EXPIRADO` (Problem Details). El caso "usuario del token inexistente" también es `401 IDENTIDAD_ACCESS_TOKEN_INVALIDO` (D1). Usuario `INACTIVO` o rol con `activo = false`: 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` (D9.2-A). Nunca `403` ni `404`. |

Cuerpo `200` (`YoResponse`, `model_config from_attributes` no aplica: se arma desde `DatosYo`):

```json
{
  "usuario": { "id": "0192…", "nombre": "Administrador" },
  "organizacion": { "id": "0192…", "nombre": "Organización inicial" },
  "rol": { "id": "0192…", "nombre": "Administrador" },
  "permisos": ["ADMIN_CONFIGURACION", "ADMIN_USUARIOS", "…", "VER_UTILIDAD"]
}
```

- **Tipos:** `id` es UUID en texto. `nombre`, un texto no vacío. `permisos`, una lista de códigos únicos en orden alfabético ascendente (orden de `sorted()` de Python sobre ASCII); puede estar vacía.
- **No incluye:** `usuario.usuario` (nombre de login), email, estado, secretos, tope de descuento, dispositivo ni `slug`. Cualquier campo nuevo pasa por una enmienda de este contrato.
- **Tipos del cliente:** se regeneran `backend/openapi.json` y `frontend/src/api/schema.gen.ts`.

## Risks / Trade-offs

- **[La renovación es reactiva: solo ocurre ante un 401]** → Un usuario inactivo sigue viendo el menú viejo hasta su próxima petición. En ese momento se renueva y `['yo']` se refresca. Es aceptable, porque la interfaz nunca protege (SEG-06, ADR-027 §4). La renovación proactiva queda fuera de alcance.
- **[Doble pedido de `/yo` al recargar la página]** (la consulta `['yo']` recibe 401, dispara la renovación y la renovación la invalida) → `cancelRefetch: false` en D2. Una prueba unitaria verifica que hay un solo `/yo` exitoso por renovación.
- **[Divergencia entre `/yo` y la autorización]** → `obtener_yo` llama a `listar_permisos_del_usuario`, no al repositorio. Una prueba de integración compara la lista con lo que autoriza el servidor (escenario "Lo informado coincide…").
- **[Brecha de sesión con usuario o rol inactivo, ahora dentro del alcance]** → El usuario decidió el 2026-09-25 cerrarla en este change. Ver D9 y ADR-028 (CRÍTICO, aprobado el 2026-09-25).
- **[La rama offline de D9 depende de un paso que todavía no existe]** → El lote de sincronización no aplica permisos por comando (paso 4 de `02` §6.3). Con D9.3-B, el tratamiento `PERMISO_REVOCADO` para el inactivo queda como deuda nominada para el change que agregue ese paso (15 o 18a). Se anota en `04` al archivar. En el 06b, una prueba fija que el lote no rechaza en bloque al inactivo por ruta, para no cerrar el canal.
- **[Un dispositivo revocado tiene el mismo problema de entrega que un usuario inactivo]** → `revocar_dispositivo` revoca sus refresh tokens, así que su cola solo llega a la cuarentena (SYN-06) mientras le dure el access token. Fuera de alcance; está anotado en ADR-028 para que el usuario decida si se trata aparte.
- **[Pruebas de pantallas existentes que simulan un 403 para ocultar]** → Se reescriben para sembrar `['yo']` en el `QueryClient` de prueba. Se conserva un caso de 403 del servidor por pantalla como red de seguridad. Se anota la línea base antes de tocarlas.
- **[Olvidar una pantalla con el patrón viejo]** → La tarea 8.6 cierra con un `grep` de `PermisoRequerido…Error` y `useCostoVigente` en `areas/admin`: solo pueden quedar usos para el manejo del 403 del servidor, nunca para decidir visibilidad.

## Migration Plan

- Sin migración de Alembic ni cambios de esquema. `04` §2.1 punto 4 no aplica: no hay revisión nueva.
- Backend y frontend se despliegan juntos. Si el frontend llegara sin el backend, `/yo` respondería 404 y el menú quedaría sin secciones con el aviso de error (D3-A: falla cerrada). No se expone nada.
- Rollback: revertir el commit del change. No quedan datos que limpiar.

## Open Questions

Ninguna. D1 a D9 están aprobadas por el usuario (2026-09-25). D9.5 es una nota para el change de usuarios y roles.
