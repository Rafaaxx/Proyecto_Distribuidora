# ADR-053 — Medios de pago administrables y permisos por rol: `ADMIN_CONFIGURACION` administra los medios, `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR`, nombre único sin distinguir mayúsculas, baja libre salvo el último medio activo, Transferencia, Cheque y Tarjeta piden referencia, solo se cambian los permisos de los roles que existen, ningún cambio deja la organización sin administrador

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-17 |
| Referenciado en | `openspec/changes/17b-medios-de-pago-y-roles/design.md` D0 a D12 y `specs/organizacion/administracion-de-medios-de-pago`, `specs/organizacion/catalogos-configurables`, `specs/identidad/administracion-de-roles`, `specs/identidad/usuarios-y-roles`, `specs/sistema/ayuda-contextual`; `01-dominio.md` §4, §19, §20, COB-02, PAG-01, CAT-05, TR-06, TR-09, TR-10, SYN-07, AUD-01, INV-01, INV-02, INV-05, INV-06, INV-21; `02-arquitectura.md` §6.5, §11; `03-modelo-de-datos.md` §4; `04-roadmap-changes.md` §2, §4, §8; ADR-011 (lo reutiliza), ADR-017, ADR-022 (lo precisa), ADR-027, ADR-028 (lo precisa, D9.5), ADR-038 (lo reutiliza), ADR-051, ADR-052 (lo reutiliza) |

**Decisiones D0 a D12 del change aprobadas por el usuario el 2026-10-17, opción A en todas, con aprobación explícita de D1, D4, D5, D7 y D8. Las confirmaciones críticas de las tareas 6.0 (protección del último administrador) y 9.0 (pantalla de roles) se dieron el mismo día, y los textos de ayuda (tarea 0.2) con sus correcciones. El 2026-10-17 el usuario aprobó el ADR junto con `propuesta-docs.md`, que se aplicó a `docs/`: el ADR queda *Vigente*.**

## Contexto

La prueba manual del change 17 mostró dos faltantes. Los medios de pago eran datos (TR-09), pero ningún comando los escribía: la lista salía de la siembra y la marca "pide referencia" estaba en `false` en todos. Y los roles eran plantillas modificables (`01` §19), pero solo existía el comando `ROL_PERMISOS_CAMBIAR`, sin pantalla ni lectura del catálogo de permisos, y sin ninguna protección: se le podía quitar `ADMIN_USUARIOS` al único rol que lo tiene y nadie podía devolverlo salvo tocando la base.

Lo que `docs/` no resolvía: quién administra los medios (`01` §19 no los nombra), qué se puede editar de ellos y con qué comandos (TR-09), si el nombre es único, qué pasa al darlos de baja (CAT-05 dice "se desactiva", sin reglas), qué medios piden referencia (`01` §4), qué se puede hacer con los roles desde la aplicación (`00` §3 y `01` §19 permiten crearlos y modificarlos; ADR-028 D9.5 deja la baja de usuarios y roles para otro change) y cómo evitar quedarse sin administrador.

## Decisión

### Alcance y tamaño

1. **Un change en tres lotes (D0).** (1) medios de pago, backend; (2) roles, backend, crítico; (3) pantallas, ayuda, concurrencia, cobertura, este ADR, la propuesta de documentación y la prueba manual. Sin frenar entre lotes salvo en las confirmaciones críticas (tareas 6.0 y 9.0).

### Medios de pago

2. **Quién administra (D1).** `ADMIN_CONFIGURACION`; sin permiso nuevo. `01` §19 lo nombra. La pestaña "Medios de pago" va en "Configuración".
3. **Comandos (D2).** `MEDIO_PAGO_CREAR` v1 (nombre y si pide referencia; nace activo) y `MEDIO_PAGO_MODIFICAR` v1 (reemplazo completo: nombre, `requiere_referencia`, `activo`), ambos solo `ONLINE`, por `POST` y `PUT /configuracion/medios-pago`. La baja y la reactivación son el cambio de `activo`. Renombrar está permitido: las cobranzas y los pagos guardan el id, así que los viejos se ven con el nombre nuevo (las observaciones de cobranza ya guardan el nombre de entonces, ADR-052). Errores: `NOMBRE_INVALIDO` (422; el nombre se recorta), `NOMBRE_DUPLICADO` (409), `ULTIMO_MEDIO_ACTIVO` (409), 404 para otra organización o inexistente.
4. **Nombre único (D3).** `ux_medio_pago__nombre` sobre `(organizacion_id, lower(nombre))`, activos o no (como ubicaciones, ADR-038): no se crea "efectivo" si existe "Efectivo", ni aunque esté de baja; se reactiva. La migración aborta con un mensaje que nombra la organización y el nombre si ya hubiera repetidos.
5. **Baja (D4).** Libre y reversible, salvo que no quede ningún medio activo (`ULTIMO_MEDIO_ACTIVO`). El comando bloquea los medios de la organización `FOR UPDATE` antes de contar, para que dos bajas simultáneas no dejen cero. Un medio de baja deja de listarse en `GET /configuracion/medios-pago`, sigue legible por id y en el detalle de la cobranza y del pago que lo usan; con conexión, cobrar o pagar con él responde `MEDIO_PAGO_INACTIVO`.
6. **Valores por defecto (D5).** Transferencia, Cheque y Tarjeta piden referencia; Efectivo y Billetera no (aprobado el 2026-10-16). Llegan por la siembra (organizaciones nuevas) y por la migración, que pone `requiere_referencia = true` en los medios de toda organización existente con esos nombres (sin distinguir mayúsculas). Es seguro porque hasta este change nadie pudo cambiar la marca. El `downgrade` borra el índice y **no** revierte las marcas (después del 17b el valor pudo haberlo elegido una persona); una prueba lo deja escrito. Desde la migración, una cobranza o un pago con transferencia sin número se rechaza con conexión (`REFERENCIA_OBLIGATORIA`) y sin conexión queda con `REFERENCIA_FALTANTE` (ADR-052).
7. **Lectura (D6).** `GET /configuracion/medios-pago/todos` con `ADMIN_CONFIGURACION`: activos e inactivos, ordenados por nombre. `GET /configuracion/medios-pago` queda igual (solo activos, cualquier sesión). Cada ruta declara un solo permiso (ratchet de rutas).
8. **Auditoría (D11).** Cada comando de medios deja **dos filas de auditoría** con el mismo `operation_id`: la genérica del bus (`entidad = 'comando'`, ADR-022) y la de la entidad (`entidad = 'medio_pago'`) con `despues` en el alta y `antes` y `despues` en la modificación (nombre, pide referencia, activo). Es el mismo patrón que la condición de IVA y `modificar_credito`. El diseño (D11) describía una sola fila; el usuario aprobó en el apply mantener las dos, para no romper el patrón ya establecido. Un rechazo por D4 deja solo la fila del comando rechazado.
9. **Dónde vive la comprobación de permiso.** El handler comprueba `ADMIN_CONFIGURACION` primero, por `configuracion/service.py::exigir_permiso_de_medios_pago`. Está en el servicio y no en el handler por el ratchet de módulos: `configuracion/commands.py` no puede importar `identidad`, y `configuracion/service.py` es el único archivo del módulo que alcanza a `identidad`. Un rechazo de permiso no deja medio, reserva del `operation_id` ni auditoría.

### Roles

10. **Qué se puede hacer con los roles (D7; crítica).** Solo cambiar los permisos de los roles que existen, con una pantalla "Roles y permisos" (`/admin/roles`, `ADMIN_USUARIOS`) sobre `ROL_PERMISOS_CAMBIAR` y la lectura nueva del catálogo, `GET /identidad/permisos` (código, descripción y módulo, en el orden de `01` §19). `GET /identidad/roles` suma la cantidad de usuarios activos de cada rol (contada con SQL). **No** se crean ni se desactivan roles, ni se crean ni se cambian de rol usuarios: queda para el "change de usuarios y roles" (ADR-028 D9.5), anotado en el roadmap como pendiente sin número.
11. **Último administrador (D8; crítica; TR-10).** `ROL_PERMISOS_CAMBIAR` se rechaza con `IDENTIDAD_SIN_ADMINISTRADOR` (409, "La organización se quedaría sin nadie que administre usuarios y roles") si, después del cambio, ningún usuario `ACTIVO` con rol activo tendría `ADMIN_USUARIOS`. La regla de dominio es pura y recibe conteos; el conteo es SQL. La validación va **antes** de escribir y de invalidar el PIN: el rol queda como estaba y no se toca ningún PIN. **El bloqueo `FOR UPDATE` de la configuración de la organización se toma solo cuando se está quitando `ADMIN_USUARIOS`** (el resto de los cambios de permisos no paga el bloqueo): así dos cambios simultáneos que quitan el permiso a roles distintos se serializan y el segundo ve el rol del primero ya sin el permiso. Los permisos actuales del rol editado se leen antes del bloqueo; no es un hueco: el cambio solo quita lo que esa lectura decía que había, y el permiso se valida siempre que la lectura lo incluía. Las pruebas de concurrencia lo cubren, incluso dos cambios simultáneos sobre el mismo rol. El futuro change de usuarios y roles aplica la misma regla a la baja de usuarios y de roles y al cambio de rol de un usuario.
12. **Pantalla (D9).** Lista de roles (estado, cantidad de permisos y de usuarios activos); al elegir uno, permisos agrupados por módulo con descripción y casilla; al guardar, un resumen "Agrega / Quita" con confirmación; avisos cuando el rol se queda sin permisos de autorización (se borra el PIN de sus usuarios, ADR-011) y cuando quien edita cambia su propio rol; explicación en palabras simples de `IDENTIDAD_SIN_ADMINISTRADOR`; reintento con el mismo `Operation-Id`; enlace a "Topes por rol"; al guardar se invalida la consulta `['yo']` para que el menú propio se actualice (ADR-017, ADR-027). Los permisos de funciones que todavía no existen (ventas, facturación, reportes) se muestran con la marca "llega más adelante".

### Fuera de alcance

13. **Motivos y alícuotas (D10).** Sin pantalla en este change; deuda en `04`, asignada al change 20c el 2026-10-24 (los motivos sembrados alcanzan para la etapa 1; la alícuota casi no cambia con el monotributo).

### Ayuda

14. **Ayuda contextual (D12, ADR-051).** Cinco claves nuevas, ninguna revisada todavía, sin tema "Ver más", con los textos que el usuario aprobó el 2026-10-17: `mediosPago.requiereReferencia`, `mediosPago.baja`, `roles.permisos`, `roles.ultimoAdministrador` y `roles.autorizacion`.

## Consecuencias

- La migración del change 17b cambia datos de la organización existente (marca de referencia en tres medios) y no se revierte al bajar. Es la única decisión del change con efecto inmediato sobre el comportamiento de cobranzas y pagos ya en uso.
- El nombre de un medio ya no puede repetirse; un medio de baja sigue ocupando su nombre.
- Siempre queda al menos un medio activo y al menos un usuario activo que pueda administrar usuarios y roles.
- Cada comando de medios deja dos filas de auditoría; las consultas de auditoría por entidad deben tenerlo en cuenta.
- Un rol nuevo todavía no puede crearse desde la aplicación; mientras no exista el change de usuarios y roles (20b, `usuarios-roles-y-cartera`, asignado el 2026-10-24), la organización trabaja con las cinco plantillas.

## Enmiendas a ADR y documentos anteriores

- **ADR-028 (sesión exige usuario y rol activos), nota D9.5:** este change **no** trae la baja de usuarios ni de roles. Cuando llegue (change de usuarios y roles, 20b), debe aplicar la misma regla del punto 11 (la baja de un usuario, la de un rol o el cambio de rol de un usuario no pueden dejar la organización sin un usuario activo con `ADMIN_USUARIOS`).
- **ADR-022 (auditoría por comando):** los comandos de medios de pago dejan la fila genérica y la de la entidad (punto 8), igual que la condición de IVA.
- **ADR-011 (PIN de autorización):** la invalidación del PIN al quitar el último permiso de autorización sigue igual; el rechazo por el punto 11 no la dispara.
- Los cambios exactos a `docs/01` a `docs/04` están en `openspec/changes/17b-medios-de-pago-y-roles/propuesta-docs.md` y se aplicaron el 2026-10-17 con el visto bueno del usuario.

## Deudas nominadas

1. **Change de usuarios y roles (asignado el 2026-10-24 al change 20b, `usuarios-roles-y-cartera`):** pantalla de usuarios, alta y cambio de rol, baja de usuarios y de roles con revocación de sesiones (ADR-028 D9.5), creación de roles; todo con la regla del punto 11.
2. **Change 20c, `catalogos-de-configuracion` (antes "sin dueño"; asignado el 2026-10-24):** pantalla de motivos (alta y baja por ámbito) y de alícuotas (TR-09).
3. **Al change 18a (`ventas`):** depende del 17b solo para contar con medios administrables y las marcas de referencia.
