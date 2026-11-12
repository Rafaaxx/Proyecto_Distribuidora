# ADR-060 — Usuarios, roles y cartera: comandos por acción, baja que corta el acceso sin varar la cola, último administrador en toda operación con exclusión mutua y revalidación, roles nuevos y baja de roles sin usuarios activos, tope propio por usuario y cartera que ordena sin restringir

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-29, archivo del change 20b) |
| Fecha | 2026-10-28 |
| Referenciado en | `openspec/changes/20b-usuarios-roles-y-cartera/design.md` D0 a D20 y `specs/identidad/administracion-de-usuarios`, `specs/identidad/usuarios-y-roles`, `specs/identidad/administracion-de-roles`, `specs/identidad/autenticacion-y-sesion`, `specs/clientes/cartera-de-clientes`, `specs/sistema/pipeline-de-comandos`, `specs/sistema/ayuda-contextual`; `00-vision-y-alcance.md` §6.4; `01-dominio.md` §18, §19, AUD-01, DSC-06, SEG-05, SYN-05, SYN-10, SYN-11, CLI-03, INV-01, INV-02, INV-06, INV-17, INV-21; `02-arquitectura.md` §7.3, §11; `03-modelo-de-datos.md` §4, §10; ADR-011, ADR-017, ADR-027, ADR-028 (lo cumple, D9.5), ADR-050 (deuda 4), ADR-052 (punto 14), ADR-053 (lo extiende, punto 11 y deuda 1), ADR-018, ADR-056, ADR-057 |

**Change 20b. Gobernanza CRÍTICA. Decisiones aprobadas por el usuario el 2026-10-28 (tarea 0.1): D0 a D19 con la opción A recomendada, salvo D8, que pasa a la opción B ("Mi contraseña" entra en este change), y D20 nueva. Vigente desde el 2026-10-29, al archivar el change 20b.**

## Contexto

ADR-028 cerró por adelantado la brecha de la sesión de un usuario o rol inactivo, pero ningún comando cambiaba `usuario.estado` ni `rol.activo` (D9.5 quedó como nota). ADR-053 impidió quedarse sin administrador al cambiar permisos y pidió aplicar la misma regla a la baja de usuarios, a la de roles y al cambio de rol. ADR-050 dejó el tope propio por usuario sin comando. ADR-052 dejó "sus clientes" como todos los de la organización mientras no hubiera asignación. `00` §6.4 pone los roles personalizados en la etapa 4; `04` §9 los asignó al 20b el 2026-10-24.

## Decisión (propuesta)

1. **Alcance (D0).** Un change en cuatro lotes: usuarios y tope; roles y migración; cartera; pantallas, ayuda, ADR, docs y prueba manual.
2. **Comandos de usuario (D1).** Uno por acción, `ONLINE`, `ADMIN_USUARIOS`: `USUARIO_MODIFICAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `USUARIO_CONTRASENA_RESTABLECER` (contraseña fuera del contenido, ADR-056) y `USUARIO_TOPE_DESCUENTO_DEFINIR`.
3. **Baja (D2; cumple ADR-028 D9.5).** En una transacción: estado `INACTIVO`; familias de refresh revocadas con `motivo_revocacion = 'USUARIO_INACTIVO'` salvo las de dispositivos con jornada no cerrada (D9.3-B); PIN de autorización borrado; auditoría de la baja y `REVOCAR_SESIONES_REFRESH_USUARIO` con `origen = 'COMANDO'` y el `operation_id`. No revoca dispositivos ni toca la cola offline (SYN-05, SYN-10). La reactivación solo vuelve el estado.
4. **Último administrador (D3; extiende ADR-053 punto 11).** Regla única "administradores después del cambio ≥ 1" sobre usuarios `ACTIVO` de roles activos con `ADMIN_USUARIOS`, aplicada a la baja de usuario, el cambio de rol, la baja de rol y el cambio de permisos. `IDENTIDAD_SIN_ADMINISTRADOR` (409), validado antes de escribir.
5. **Exclusión mutua y revalidación (D4; enmienda `02` §7.3).** Toda operación que cambia quién administra o quién pertenece a un rol toma `configuracion_organizacion FOR UPDATE`, después el rol y el usuario, y revalida con el bloqueo tomado que quien ejecuta sigue activo y con `ADMIN_USUARIOS` (`PERMISO_REQUERIDO` si no).
6. **Autobaja (D5).** Prohibida (`IDENTIDAD_AUTOBAJA`); el cambio del propio rol se permite sujeto al punto 4.
7. **Jornada y cartera en la baja (D6).** No impiden la baja; la pantalla avisa.
8. **Cambio de rol (D7).** A un rol activo de la organización; no revoca sesiones (ADR-017); borra el PIN si el rol nuevo no autoriza excepciones (ADR-011); conserva tope y cartera.
9. **Contraseña (D8-B, D20).** La regla común para definir una nueva (alta, restablecimiento y cambio propio) es de **al menos 8 caracteres, sin reglas de composición y no en blanco** (422 `IDENTIDAD_CONTRASENA_INVALIDA`; decisión del usuario, 2026-10-28); las contraseñas existentes no se invalidan. La restablece el administrador (revoca sesiones salvo jornada, `CONTRASENA_RESTABLECIDA`, y desbloquea el inicio de sesión) y la cambia cada usuario con `CONTRASENA_PROPIA_CAMBIAR`: `ONLINE`, sin permiso especial, solo sobre el usuario del token; actual y nueva fuera del contenido (ADR-056); una actual incorrecta responde `IDENTIDAD_CONTRASENA_INCORRECTA` (403) y cuenta como intento fallido del inicio de sesión, con su bloqueo (ADR-018, ADR-057); cierra las sesiones de los demás dispositivos (`CONTRASENA_CAMBIADA`), conserva la actual y respeta la excepción de la jornada no cerrada (ADR-028 D9.3-B); sin "olvidé mi contraseña" por correo ni edición propia de nombre o email.
10. **Datos (D9).** Se editan nombre y email; el nombre de inicio de sesión no (ADR-057). El alta rechaza rol inactivo y nombre repetido.
11. **Roles nuevos (D10; enmienda `00` §6.4).** `ROL_CREAR` y `ROL_RENOMBRAR`; nombre único por organización sin distinguir mayúsculas (`ux_rol__nombre`).
12. **Baja de roles (D11).** `ROL_BAJA` solo sin usuarios activos (`IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`); `ROL_REACTIVAR` libre; ninguna plantilla protegida. Punto de control 8.0 aprobado el 2026-10-28: orden mutex, rol `FOR UPDATE`, usuarios activos, defensa de D3, escritura y auditoría; `ROL_PERMISOS_CAMBIAR` sin bloqueo extra del rol cuando no quita `ADMIN_USUARIOS` (inocuo, un rol de baja admite editar permisos). Baja de un rol ya de baja y reactivación de uno activo: sin cambio ni auditoría.
13. **Tope propio (D12; salda ADR-050 deuda 4).** Valor o nulo, 0 a 1, una fila de auditoría con el anterior y el nuevo.
14. **Cartera (D13 a D15; salda ADR-052 punto 14).** `cliente.vendedor_id` (un vendedor por cliente; el consumidor final no se asigna); `CLIENTE_VENDEDOR_ASIGNAR` con `GESTIONAR_CLIENTES`, en bloque y todo o nada. La cartera **ordena lo que se ofrece y no restringe**: quien llega a los clientes solo por `VENDER` o `REGISTRAR_COBRANZA` ve primero sus clientes y puede buscar en todos; sin cartera ve todos; nada se rechaza ni se marca por la cartera, con o sin conexión. El índice `ix_cliente__vendedor` es completo (no parcial) sobre `(organizacion_id, vendedor_id)`: también sirve al filtro "sin vendedor" (decisión del usuario, 2026-10-28).
15. **Pantallas, auditoría y ayuda (D16 a D18).** Área "Usuarios"; alta y baja en "Roles y permisos"; vendedor en clientes; auditoría con fila genérica y fila de entidad con antes y después; seis claves de ayuda sin ejemplos; menú "Mi cuenta" ("Mi PIN" y "Mi contraseña") para todo usuario.
16. **Para el 21 (D19).** `clientes/service.py::listar_cartera` y `contar_clientes_asignados`.

## Precisiones del apply (2026-10-29)

Lo que el apply fijó sin cambiar ninguna decisión de arriba:

1. **Cartera: tres precisiones aprobadas el 2026-10-29.** (a) El listado y la ficha de clientes traen `vendedor_valido` y la pantalla marca al vendedor de baja o sin permiso para reasignarlo. (b) El consumidor final entra en la cartera solo con `incluir_consumidor_final=true`: la pantalla de venta lo pide y la de cobranza no. (c) "Tiene cartera" cuenta los clientes asignados de cualquier estado. La lógica de cartera vive en el repositorio y el servicio de `clientes` (sin `queries.py`).
2. **Roles: contadores del tope propio.** `GET /identidad/roles` informa `usuarios_con_tope_propio` (total) y su separación en activos e inactivos; `GET /identidad/usuarios` filtra por estado, rol y "con tope propio". "Topes por rol" muestra "3 (1 inactivo)" (solo "3" sin inactivos), sin selector de activos o todos, y el número lleva al listado de usuarios de ese rol con tope propio.
3. **Secretos y `Operation-Id` en las pantallas.** Las contraseñas (alta, restablecimiento y "Mi contraseña") se escriben enmascaradas, viajan por una referencia efímera que se vacía al terminar y no entran a la caché de consultas, a las variables de la mutación ni al almacenamiento del navegador. Como un rechazo de esos comandos no deja fila de comando, el reintento con los datos corregidos reenvía el mismo `Operation-Id`; en los demás comandos el identificador se renueva cuando cambia lo escrito y se conserva ante un corte de red (INV-06).
4. **Menú "Mi cuenta" (D20).** Es un grupo de enlaces siempre visible para todo usuario con sesión confirmada: "Mi contraseña" siempre y "Mi PIN" solo con algún permiso de autorización (regla del 18b).
5. **Avisos de la baja (D6).** La ficha lee las jornadas no cerradas (`ABIERTA` y `EN_RENDICION`) y los clientes asignados con las lecturas existentes, cada una solo si la sesión tiene el permiso de esa lectura; con más de 100 clientes asignados el aviso dice "más de 100". La baja nunca se rechaza por eso.
6. **Roles de baja en pantalla.** Se muestran como "De baja"; los selectores de rol (alta, cambio de rol, "copiar permisos de") ofrecen solo roles activos, y la ficha conserva el rol actual aunque esté de baja para poder mostrarlo.
7. **Ayuda.** Seis claves nuevas sin ejemplos con los textos exactos de `design.md` D18 y `roles.ultimoAdministrador` revisada para nombrar la baja de usuarios y de roles y el cambio de rol (74 claves en total).
8. **Comandos del change.** Doce tipos nuevos en el catálogo (seis de usuarios, cuatro de roles, `CLIENTE_VENDEDOR_ASIGNAR` y `CONTRASENA_PROPIA_CAMBIAR`), todos `ONLINE`; `USUARIO_CREAR`, ya existente, también cambia (rol activo, contraseña y nombre de usuario libre). Los tres que reciben contraseña rechazan el lote en cualquier modo. Una prueba de catálogo cubre los trece.
9. **Punto abierto: quién ve la lista de vendedores.** Elegir un vendedor en la ficha del cliente, en el filtro y en "Asignar vendedor" necesita la lista de usuarios elegibles, que hoy se lee con `ADMIN_USUARIOS`. Quien tiene `GESTIONAR_CLIENTES` sin `ADMIN_USUARIOS` (la plantilla Administración) ve el aviso de que no puede ver esa lista y solo puede quitar el vendedor. Pendiente de decisión del usuario: una lectura de vendedores elegibles con `GESTIONAR_CLIENTES`.

## Consecuencias

- Una baja corta el acceso con conexión en la petición siguiente y nunca vara la cola offline.
- Siempre queda al menos un usuario activo que administre usuarios y roles, también ante operaciones simultáneas.
- Las operaciones de identidad de una organización se serializan.
- Los roles personalizados se adelantan de la etapa 4 a la etapa 1.
- La cartera no cambia los permisos ni la matriz de `01` §19.
- Una sesión abierta no sirve para adivinar la contraseña: el cambio propio comparte el límite de intentos del inicio de sesión.

## Alternativas consideradas

Las opciones B y C de cada decisión de `design.md`, en particular: dividir el change (D0-B), un solo comando de reemplazo completo (D1-B), conservar el PIN en la baja (D2-B), no revalidar al actor (D4-B), permitir la baja de roles con usuarios activos revocando sus sesiones (D11-B), varios vendedores por cliente (D13-B) y una cartera que restringe con un permiso nuevo (D14-B).

## Deudas nominadas (propuestas)

1. **Al change 21:** bajar en el bootstrap la cartera del vendedor ("vacía = todos").
2. **Al change 21:** "Mi contraseña" en `/ruta`, junto a la pantalla de cuenta de la ruta.
