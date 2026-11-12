# Change 20b-usuarios-roles-y-cartera

## Qué resuelve este change

Permite administrar desde `/admin` los usuarios (alta, edición, baja, reactivación, cambio de rol, contraseña —restablecida por el administrador y cambiada por cada usuario— y tope propio de descuento), crear y dar de baja roles, y asignar clientes a vendedores ("sus clientes", `01` §19). Toda baja corta el acceso sin varar la cola offline (ADR-028) y nada deja la organización sin administrador (ADR-053).

## Why

`04` §9 (fila 20b y "Deudas reasignadas"): ADR-028 D9.5 (ningún comando cambia `usuario.estado` ni `rol.activo`), ADR-053 deuda 1, ADR-050 deuda 4 (tope propio) y la cartera del 17 (ADR-052 punto 14). El 27a necesita crear usuarios y asignar clientes desde la aplicación; el 21, la cartera para el bootstrap (SYN-11).

## What Changes

- **Usuarios** (`design.md` D1 a D9 y D20): comandos nuevos para modificar datos, dar de baja, reactivar, cambiar de rol y restablecer la contraseña; `USUARIO_CREAR` rechaza un rol inactivo. La baja revoca en la misma transacción las familias de refresh del usuario (salvo los dispositivos con jornada no cerrada, ADR-028 D9.3-B), audita `REVOCAR_SESIONES_REFRESH_USUARIO`, borra el PIN y no toca la cola offline (SYN-05, SYN-10).
- **Mi contraseña** (D20): comando `CONTRASENA_PROPIA_CAMBIAR` para cualquier usuario autenticado, con la contraseña actual (el fallo cuenta para el bloqueo de inicio de sesión, ADR-018/ADR-057), que cierra sus otras sesiones (`CONTRASENA_CAMBIADA`, salvo dispositivos con jornada no cerrada) y conserva la actual; pantalla en un menú "Mi cuenta" junto a "Mi PIN".
- **Último administrador** (D3, D4): la regla de ADR-053 se aplica a la baja de usuario, al cambio de rol y a la baja de rol, serializada con el bloqueo de la configuración de la organización y con revalidación de quien ejecuta.
- **Roles** (D10, D11): crear un rol (nombre único sin distinguir mayúsculas, permisos y tope), renombrarlo, darlo de baja (rechazado si tiene usuarios activos) y reactivarlo.
- **Tope propio por usuario** (D12; DSC-06): definir o quitar `tope_descuento_override`, auditado con el valor anterior y el nuevo.
- **Cartera de clientes** (D13 a D15): asignar un vendedor a cada cliente y definir qué cambia "sus clientes" en las lecturas para vender y cobrar.
- **Pantallas** (D16): "Usuarios" en `/admin`, alta y baja de roles en "Roles y permisos", vendedor en la ficha y en el listado de clientes; menú "Mi cuenta" con "Mi contraseña" (D20); ayuda contextual (D18).
- **Migración**: índice único del nombre de rol y `cliente.vendedor_id` con su clave foránea compuesta.

## Decisiones

Gobernanza **CRÍTICA** (identidad y permisos): **D0 a D20 y los textos de ayuda fueron aprobados el 2026-10-28** (D8 en la opción B; D20 nueva); queda el punto de control 8.0 antes de `ROL_BAJA`. **ADR-060** (*Propuesto* hasta el archivo).

## No incluye

"olvidé mi contraseña" por correo (lo cubre el restablecimiento del administrador, D8) y la edición propia de nombre y email; "Mi contraseña" en `/ruta` (llega con el 21); permisos por usuario (etapa 4); borrar usuarios o roles (INV-05); el bootstrap con la cartera (21); motivos y alícuotas (20c); zonas o rutas.

## Invariantes

No cierra invariantes de `01` §20. Prueba citándolos: **INV-01** (un rechazo no deja cambios ni revoca sesiones), **INV-02**/**INV-21** (filtrado por organización; ajeno → 404), **INV-05** (nada se borra), **INV-06** (doble envío), **INV-03** (tope como string decimal), **INV-17** (lo offline de un usuario dado de baja se acepta). Concurrencia con commits reales. **Sin fixtures compartidos nuevos** (el tope ya se evalúa con `dsc-06`).

## Capabilities

### New Capabilities

- `identidad/administracion-de-usuarios`: comandos y pantalla de usuarios: datos, baja, reactivación, cambio de rol, contraseña y tope propio.
- `clientes/cartera-de-clientes`: asignación de clientes a vendedores y su efecto en las lecturas para vender y cobrar.

### Modified Capabilities

- `identidad/usuarios-y-roles`: último administrador ampliado a baja, cambio de rol y baja de rol; tope propio por comando; alta con rol activo.
- `identidad/administracion-de-roles`: crear, renombrar, dar de baja y reactivar roles.
- `identidad/autenticacion-y-sesion`: la baja revoca las sesiones en el acto, con la excepción de la jornada; "Mi contraseña" (cambio propio).
- `sistema/pipeline-de-comandos`: tipos nuevos en el catálogo.
- `sistema/ayuda-contextual`: textos de usuarios, roles y cartera.

## Impact

Backend: `identidad/` (dominio, servicio, comandos, rutas), `clientes/` (columna, comando, lecturas), `ventas/` y `cobranzas/` solo en las lecturas de clientes para elegir; una migración. Frontend: área nueva `/admin/usuarios`, `areas/admin/cuenta/MiContrasenaScreen` y menú "Mi cuenta" en `AdminLayout`, `areas/admin/roles`, `areas/admin/clientes`, `ayuda/textos.ts`. Docs (`propuesta-docs.md`, incluida la enmienda de `00` §6.4) y ADR-060.
