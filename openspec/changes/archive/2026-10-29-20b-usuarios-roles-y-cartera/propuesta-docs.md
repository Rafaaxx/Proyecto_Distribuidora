# Propuesta de cambios a `docs/` — change 20b `usuarios-roles-y-cartera`

> **Estado: propuesta, sin aplicar.** Ningún archivo de `docs/00` a `docs/04` se modificó. Cada punto muestra el texto actual (citado de `docs/`; con "…" donde se omite lo que no cambia) y el texto propuesto. Se aplica solo con el visto bueno del usuario. El único archivo de `docs/` que el apply sí tocó es `docs/adr/ADR-060-usuarios-roles-y-cartera.md` (sigue *Propuesto* hasta el archivo).

## `00-vision-y-alcance.md`

### §6.4 Etapa 4 — Producto comercial

**Actual:**

```
- Roles personalizados desde la interfaz.
- Importadores genéricos y migración de saldos.
- Bootstrap incremental y filtrado de datos offline por vendedor o zona.
```

**Propuesto** (se quita el primer punto de la etapa 4 y se parte el tercero):

```
- Importadores genéricos y migración de saldos.
- Bootstrap incremental y filtrado de datos offline por zona.
```

Y en la §6.1 (etapa 1), junto a las demás capacidades de identidad, agregar:

```
- Administración de usuarios desde la interfaz (alta, edición, baja y reactivación, cambio de rol, contraseña y tope de descuento propio), roles personalizados (crear, renombrar, dar de baja y reactivar) y asignación de clientes a vendedores (change 20b, ADR-060).
```

Nota: el filtrado de los datos offline **por vendedor** (el bootstrap baja la cartera con "vacía = todos") pasa al change 21; **por zona** sigue en la etapa 4.

## `01-dominio.md`

### §19 Permisos y roles

**Actual** (fila `ADMIN_USUARIOS`):

```
| ADMIN_USUARIOS | Usuarios, roles y permisos (incluye cambiar los permisos de cada rol, consultar el catálogo de permisos, definir el tope de descuento manual de cada rol y consultar los roles con su tope). Ningún cambio puede dejar la organización sin un usuario activo con este permiso (ADR-053) | ✓ | | | | |
```

**Propuesto:**

```
| ADMIN_USUARIOS | Usuarios, roles y permisos: alta, edición, baja y reactivación de usuarios, cambio de rol, restablecimiento de contraseña y tope de descuento propio de cada usuario; crear, renombrar, dar de baja y reactivar roles, cambiar los permisos de cada rol, consultar el catálogo de permisos, definir el tope de descuento manual de cada rol y consultar los roles con su tope y los usuarios con su rol. Ningún cambio —baja de usuario, cambio de rol, baja de rol ni cambio de permisos— puede dejar la organización sin un usuario activo con este permiso (ADR-053, ADR-060) | ✓ | | | | |
```

**Actual** (fila `GESTIONAR_CLIENTES`):

```
| GESTIONAR_CLIENTES | Alta y edición de clientes; ver su cuenta corriente | ✓ | ✓ | ✓ | | |
```

**Propuesto:**

```
| GESTIONAR_CLIENTES | Alta y edición de clientes; ver su cuenta corriente; asignar clientes a vendedores (cartera, ADR-060) | ✓ | ✓ | ✓ | | |
```

**Actual** (párrafo de los roles):

```
Roles: ADM = Administrador, GES = Administración, SUP = Supervisor comercial, VEN = Vendedor/Repartidor, CON = Consulta/Dirección. Los roles son plantillas: la organización puede modificar su composición y los topes de descuento. Hasta el change de usuarios y roles no se crean roles nuevos ni se desactivan (ADR-028 D9.5, ADR-053). El vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad.
```

**Propuesto:**

```
Roles: ADM = Administrador, GES = Administración, SUP = Supervisor comercial, VEN = Vendedor/Repartidor, CON = Consulta/Dirección. Los roles son plantillas: la organización puede modificar su composición y los topes de descuento, renombrarlos, crear roles nuevos, darlos de baja (solo sin usuarios activos) y reactivarlos; el nombre es único por organización sin distinguir mayúsculas, aunque el otro rol esté de baja (ADR-028 D9.5, ADR-053, ADR-060). Un usuario puede tener además un tope de descuento propio que reemplaza al de su rol. El vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad.
```

**Actual** (frase sobre "sus clientes"):

```
"Sus clientes" son todos los de la organización mientras no exista una asignación de clientes a vendedores (ADR-052).
```

**Propuesto** (se quita "hasta el change de usuarios y roles…" y se fija D14):

```
"Sus clientes" son los clientes que tiene asignados el vendedor (`cliente.vendedor_id`). Quien llega a los clientes solo por `VENDER` o `REGISTRAR_COBRANZA` ve primero sus clientes asignados y el consumidor final, y puede buscar en todos; si no tiene ningún cliente asignado ve todos; quien tiene `GESTIONAR_CLIENTES` ve todos siempre. La cartera ordena lo que se ofrece y no restringe: vender o cobrar a un cliente fuera de la cartera se permite, con y sin conexión, sin rechazo ni observación (INV-17). El consumidor final no se asigna a ningún vendedor (CLI-03) (ADR-052, ADR-060).
```

### §18 Máquinas de estado

**Actual:** la tabla no incluye `Usuario` ni `Rol`.

**Propuesto** (dos filas nuevas después de `Dispositivo`) y un párrafo:

```
| Usuario | Almacenada | ACTIVO ↔ INACTIVO | 1 |
| Rol | Almacenada | ACTIVO ↔ INACTIVO (la baja solo sin usuarios activos) | 1 |

**Usuario.** `ACTIVO → INACTIVO` es la baja (`USUARIO_BAJA`): corta el acceso en la petición siguiente, revoca las sesiones de refresh salvo las de dispositivos con una jornada no cerrada del usuario, borra su PIN de autorización y conserva su rol, su tope propio y su cartera. `INACTIVO → ACTIVO` es la reactivación (`USUARIO_REACTIVAR`); el usuario inicia sesión de nuevo y define su PIN otra vez si lo necesita. Una baja de un inactivo o una reactivación de un activo se rechaza con `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA`. Nadie se da de baja a sí mismo (`IDENTIDAD_AUTOBAJA`) y ninguna baja deja la organización sin un usuario activo con `ADMIN_USUARIOS` (ADR-053, ADR-060).

**Rol.** `ACTIVO → INACTIVO` es la baja (`ROL_BAJA`) y solo se acepta si el rol no tiene usuarios activos (`IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`); un rol de baja no se asigna, no aparece en los selectores y sus permisos se pueden seguir editando. `INACTIVO → ACTIVO` es libre (`ROL_REACTIVAR`). Ninguna plantilla está protegida (ADR-060).
```

### AUD-01

**Actual:** "Se auditan: inicio de sesión, cambios de usuarios, roles, permisos y dispositivos; … cambios del tope de descuento de un rol (una fila con el valor anterior y el nuevo); …"

**Propuesto** (se amplía la enumeración de acciones de usuarios y roles):

```
… cambios de usuarios, roles, permisos y dispositivos (modificar usuario, baja y reactivación de usuario, cambio de rol de un usuario, restablecimiento de contraseña, cambio de la propia contraseña —`CAMBIAR_CONTRASENA_PROPIA`, sin dato alguno de la contraseña—, alta, renombre, baja y reactivación de rol, y la revocación de sesiones de una baja o de un cambio de contraseña, `REVOCAR_SESIONES_REFRESH_USUARIO` con `origen = 'COMANDO'`); … cambios del tope de descuento de un rol y del tope propio de un usuario (una fila con el valor anterior y el nuevo, `TOPE_DESCUENTO_USUARIO`); asignación de clientes a vendedores (una fila por cliente cambiado, `ASIGNAR_VENDEDOR_CLIENTE`, con el vendedor anterior y el nuevo); …
```

### DSC-06

**Actual:** "… cuyo tope porcentual depende del rol (o del propio usuario, si lo tiene). …"

**Propuesto:**

```
… cuyo tope porcentual es el del propio usuario si lo tiene definido (`USUARIO_TOPE_DESCUENTO_DEFINIR`; reemplaza al del rol, sea mayor o menor, y vacío vuelve al del rol) y, si no, el de su rol; el tope propio solo tiene efecto si el rol tiene `DESCUENTO_MANUAL`. …
```

### §20 Invariantes (párrafo de pruebas)

**Actual:** la tabla de invariantes y su párrafo de cobertura no mencionan el change 20b.

**Propuesto** (párrafo nuevo al final de la §20):

```
**Cobertura del change 20b (ADR-060).** INV-01: la baja, el cambio de rol y la asignación de cartera se rechazan enteros o se aplican enteros (`test_cliente_vendedor_asignar`, `test_usuario_baja`). INV-02: el nombre de rol único por organización (`ux_rol__nombre`) no cruza organizaciones (`test_usuarios_roles_cartera_migracion`). INV-03: el tope propio viaja como fracción string (`test_usuario_tope_descuento_definir`, `usuarios.test.ts`). INV-05: ninguna baja borra usuarios, roles ni su auditoría (`test_inv05_bajas_no_borran`). INV-06: todo comando del change responde igual ante el doble envío. INV-17: una venta o cobranza fuera de la cartera nunca se rechaza (`test_cartera_no_rechaza_operaciones`). INV-21: toda ruta nueva con su prueba de recurso ajeno (404). La regla del último administrador tiene pruebas de conteo (`test_identidad_conteo_administradores`) y de concurrencia real (`test_identidad_bajas_concurrentes`, `test_rol_baja_concurrente`).
```

## `02-arquitectura.md`

### §7.3 Orden global de bloqueo

**Actual:** "`ROL_PERMISOS_CAMBIAR`: solo cuando el cambio quita `ADMIN_USUARIOS` bloquea `FOR UPDATE` la fila de configuración de la organización y recién entonces cuenta, en SQL, los usuarios activos con rol activo que conservan el permiso; el resto de los cambios de permisos no paga el bloqueo (ADR-053)."

**Propuesto** (párrafo nuevo a continuación):

```
**Identidad (ADR-060).** `USUARIO_CREAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `ROL_CREAR`, `ROL_RENOMBRAR`, `ROL_BAJA`, `ROL_REACTIVAR` y `ROL_PERMISOS_CAMBIAR` (cuando quita `ADMIN_USUARIOS`) toman **primero** `configuracion_organizacion FOR UPDATE` (el mismo candado de ADR-053), después el rol o los roles involucrados `FOR UPDATE` y el usuario objetivo `FOR UPDATE`, y recién entonces `sesion_refresh`: configuración → rol → usuario → `sesion_refresh`. Con el candado tomado revalidan que quien ejecuta sigue `ACTIVO`, con rol activo y con `ADMIN_USUARIOS` (si no, `PERMISO_REQUERIDO`, sin cambios) y cuentan los administradores restantes en SQL. Ningún comando de otro módulo toma después un usuario o un rol, así que no hay ciclo. "Mi contraseña" (`CONTRASENA_PROPIA_CAMBIAR`) solo toca al propio usuario y a sus familias de refresh y no toma el candado de la organización.
```

### §11 API (códigos de error y catálogo de comandos)

**Actual** (tabla de comandos; filas relacionadas):

```
| `ROL_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`) | ✓ | |
| `ROL_PERMISOS_CAMBIAR` (con `ADMIN_USUARIOS`; rechaza `IDENTIDAD_SIN_ADMINISTRADOR`, 409, ADR-053) | ✓ | |
| `PIN_AUTORIZACION_PROPIO_DEFINIR` (con algún permiso de autorización de excepciones; …) | ✓ | |
```

**Propuesto** (filas nuevas):

```
| `USUARIO_MODIFICAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `USUARIO_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`; `IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO` 422, `IDENTIDAD_AUTOBAJA`, `IDENTIDAD_SIN_ADMINISTRADOR`, `IDENTIDAD_ROL_INACTIVO` y `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA` 409, `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, ADR-060) | ✓ | |
| `USUARIO_CONTRASENA_RESTABLECER` (con `ADMIN_USUARIOS`; `IDENTIDAD_CONTRASENA_INVALIDA` 422; contraseña fuera del contenido, ADR-056) | ✓ | |
| `ROL_CREAR`, `ROL_RENOMBRAR`, `ROL_BAJA`, `ROL_REACTIVAR` (con `ADMIN_USUARIOS`; `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO` 422, `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO`, `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS` y `IDENTIDAD_SIN_ADMINISTRADOR` 409, ADR-060) | ✓ | |
| `CLIENTE_VENDEDOR_ASIGNAR` (con `GESTIONAR_CLIENTES`; de 1 a 500 clientes y un vendedor o `null`; `VENDEDOR_INVALIDO` y `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR` 409, ADR-060) | ✓ | |
| `CONTRASENA_PROPIA_CAMBIAR` (sin permiso: cualquier usuario autenticado y activo, solo la propia; actual y nueva fuera del contenido; `IDENTIDAD_CONTRASENA_INCORRECTA` 403 con el límite de intentos del login, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` 429, `IDENTIDAD_CONTRASENA_INVALIDA` y `IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL` 422, ADR-018, ADR-060) | ✓ | |
```

(Las columnas son «Online» y «Offline»: todos los tipos del change son solo `ONLINE`; los que reciben una contraseña el lote los rechaza igual, por `exige_credenciales_efimeras`.)

**Actual** (frase de los tipos con secretos): "… el lote rechaza ese tipo en cualquier modo con `MODO_NO_ADMITIDO_PARA_TIPO` (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`); …"

**Propuesto:**

```
… (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`, `USUARIO_CONTRASENA_RESTABLECER`, `CONTRASENA_PROPIA_CAMBIAR`); …
```

Y en el catálogo, la salida justificada `sin_permiso` queda con un único tipo, `CONTRASENA_PROPIA_CAMBIAR`, siempre `ONLINE`.

**Códigos de error nuevos** (a la lista de §11): `IDENTIDAD_AUTOBAJA`, `IDENTIDAD_ROL_INACTIVO`, `IDENTIDAD_USUARIO_DUPLICADO`, `IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO`, `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO`, `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO`, `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, `IDENTIDAD_CONTRASENA_INVALIDA`, `IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL`, `VENDEDOR_INVALIDO` y `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR`. **Rutas nuevas:** `GET /identidad/usuarios` (filtros `estado`, `rol_id`, `con_tope_propio`), `GET/PUT /identidad/usuarios/{id}`, `POST .../baja`, `POST .../reactivacion`, `PUT .../rol`, `POST .../contrasena`, `PUT .../tope-descuento`, `POST /identidad/roles`, `PUT /identidad/roles/{id}/nombre`, `POST .../baja`, `POST .../reactivacion`, `POST /yo/contrasena`, `POST /clientes/vendedor`, `GET /clientes/vendedores` (`GESTIONAR_CLIENTES`; vendedores elegibles, `id` y `nombre`), y `GET /clientes/opciones?alcance=todos`, `GET /clientes?vendedor_id=&sin_vendedor=`.

## `03-modelo-de-datos.md`

### §4 Identidad y configuración

**Actual** (`rol`): "`id`, `organizacion_id`, `nombre`, `tope_descuento` `numeric(9,6)`, `activo`"

**Propuesto:**

```
`id`, `organizacion_id`, `nombre` (`ux_rol__nombre` único sobre `(organizacion_id, lower(nombre))`, activos o no; ADR-060), `tope_descuento` `numeric(9,6)`, `activo`
```

**Actual** (`sesion_refresh`): "`id`, `organizacion_id`, `usuario_id`, `dispositivo_id`, `token_hash`, `familia_id`, `emitido_en`, `expira_en`, `usado_en`, `revocado_en`, `motivo_revocacion`. …"

**Propuesto** (se agrega al final del párrafo):

```
`motivo_revocacion` toma uno de: `USUARIO_INACTIVO` (baja de usuario y renovación de un usuario inactivo), `ROL_INACTIVO` (renovación con el rol de baja), `CONTRASENA_RESTABLECIDA` (el administrador restableció la contraseña) y `CONTRASENA_CAMBIADA` (el usuario cambió la suya; se conserva la sesión del dispositivo desde el que se cambió). La baja y los cambios de contraseña no revocan las familias de los dispositivos con una jornada no cerrada del usuario (ADR-028 D9.3-B, ADR-060).
```

### §10 Clientes

**Actual:** la tabla de `cliente` no tiene vendedor.

**Propuesto** (fila nueva después de `lista_precio_id`):

```
| `vendedor_id` | `uuid` | Nulo = sin vendedor asignado. Clave foránea compuesta `(organizacion_id, vendedor_id)` a `usuario (organizacion_id, id)` e índice completo `ix_cliente__vendedor (organizacion_id, vendedor_id)` (sirve también al filtro "sin vendedor"). Lo cambia solo `CLIENTE_VENDEDOR_ASIGNAR`, no `CLIENTE_MODIFICAR`. El consumidor final no se asigna (CLI-03). Si el vendedor se da de baja o pierde el permiso, la asignación se conserva y la pantalla la marca para reasignar (ADR-060) |
```

## `04-roadmap-changes.md`

### §9 Hito 5 — Venta (fila del 20b y deudas)

**Actual** (fila): "20b | `usuarios-roles-y-cartera` | Pantalla de usuarios … asignación de clientes a vendedores ("sus clientes", `01` §19). Gobernanza **CRÍTICA** … | — (no cierra ningún invariante de `01` §20; cumple ADR-028 D9.5 y respeta INV-21)"

**Propuesto** (se marca terminado y se anota lo que salda y lo que deja):

```
… Terminado (change 20b, ADR-060): usuarios (alta, edición, baja y reactivación, cambio de rol, contraseña restablecida por el administrador y cambiada por cada usuario, tope propio), roles nuevos, renombrados y de baja, cartera de clientes y menú "Mi cuenta". **Deudas saldadas:** ADR-028 D9.5 (la baja de usuarios y de roles con su revocación y su auditoría), ADR-053 deuda 1 (el change de usuarios y roles), ADR-050 deuda 4 (el tope propio por usuario) y la asignación de clientes a vendedores del 17 (ADR-052 punto 14).
```

**Deudas nuevas** (párrafo a continuación de "Deudas reasignadas"):

```
**Deudas nuevas del change 20b (`usuarios-roles-y-cartera`):** **al change 21 (`pwa-y-bootstrap`):** bajar la cartera del vendedor en el bootstrap (SYN-11) con "vacía = todos" (`clientes/service.py::listar_cartera`, D19); y "Mi contraseña" en `/ruta`, junto a la pantalla de cuenta de la ruta (en `/admin` entra en el 20b, D20). No hay deuda al 28 por la contraseña: "olvidé mi contraseña" por correo queda cubierto por el restablecimiento del administrador.
```

## Resumen de lo que toca cada archivo

| Archivo | Secciones |
| --- | --- |
| `00` | §6.1 (suma), §6.4 (quita roles personalizados; el filtrado por vendedor pasa al 21) |
| `01` | §18 (máquinas Usuario y Rol), §19 (`ADMIN_USUARIOS`, `GESTIONAR_CLIENTES`, roles, "sus clientes"), AUD-01, DSC-06, §20 (cobertura) |
| `02` | §7.3 (orden de bloqueo de identidad), §11 (comandos, códigos y rutas) |
| `03` | §4 (`ux_rol__nombre`, `motivo_revocacion`), §10 (`cliente.vendedor_id`) |
| `04` | §9 (20b terminado, deudas saldadas y deudas nuevas) |
