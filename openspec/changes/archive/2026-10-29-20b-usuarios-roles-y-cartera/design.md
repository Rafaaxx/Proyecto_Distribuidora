# Diseño técnico — 20b-usuarios-roles-y-cartera

> **Estado: APROBADAS (2026-10-28).** D0 a D19 con la opción A recomendada, **salvo D8, que pasa a la opción B** ("Mi contraseña" entra en este change), más la decisión nueva **D20** ("Mi contraseña"), aprobada con el diseño de este documento. Los textos de ayuda de D18 también quedaron aprobados (tarea 0.2). Gobernanza **CRÍTICA** (identidad y permisos, `04` §9). Sigue abierto el punto de control 8.0 (visto bueno antes de `ROL_BAJA`).
>
> **Gobernanza por decisión.** **CRÍTICA:** D1, D2, D3, D4, D5, D7, D8, D11, D20. **ALTA:** D6, D10, D12, D14, D15. **MEDIA:** D9, D13, D16, D17, D19. **BAJA:** D0, D18. **De negocio** (el agente solo recomienda; decide el usuario): **D0, D5, D6, D8, D10, D11, D12, D13, D14, D15, D20**.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Sesión (06b, 15; ADR-028):** `requiere_permiso`, `GET /yo` y `listar_permisos_del_usuario` ya rechazan al usuario `INACTIVO` o de rol con `activo = false` en la petición siguiente (D9.1, D9.2-A: 401 genérico). `renovar_sesion` ya rechaza y revoca las familias del usuario con `motivo_revocacion` `USUARIO_INACTIVO` o `ROL_INACTIVO`, salvo los dispositivos con jornada no cerrada (D9.3-B, puerto `hay_jornada_no_cerrada`), y audita `REVOCAR_SESIONES_REFRESH_USUARIO` (`origen = 'SISTEMA'`) o `RENOVAR_SESION_CON_JORNADA_PENDIENTE`. `repository.revocar_sesiones_refresh_de_usuario(..., excepto_dispositivo_ids=...)` y `dispositivos_con_sesion_vigente` existen.
- **Lote (17; ADR-052):** los comandos `OFFLINE` de un usuario o rol inactivo se aceptan con `PERMISO_REVOCADO` (SYN-10); el lote no rechaza al inactivo por ruta.
- **Último administrador (17b; ADR-053 punto 11):** regla pura `validar_queda_administrador` (recibe conteos), conteos SQL `contar_administradores_en_otros_roles` y `contar_usuarios_activos_del_rol`, y bloqueo `FOR UPDATE` de `configuracion_organizacion` como exclusión mutua de la organización (`02` §7.3). Hoy solo la usa `ROL_PERMISOS_CAMBIAR`.
- **Comandos de `identidad`:** `USUARIO_CREAR` (contraseña fuera del contenido, `exige_credenciales_efimeras`, ADR-056), `USUARIO_DESBLOQUEAR` (marcador en `intento_login`, ADR-057), `ROL_PERMISOS_CAMBIAR` (invalida el PIN de los usuarios del rol que pierde los permisos de autorización, ADR-011), `ROL_TOPE_DESCUENTO_DEFINIR` (una fila de auditoría con antes y después, ADR-050 punto 13), `PIN_AUTORIZACION_ROTAR`, `DISPOSITIVO_REVOCAR`. Lecturas `GET /identidad/usuarios` (sin `password_hash`), `GET /identidad/roles` (con permisos, tope y usuarios activos), `GET /identidad/permisos`.
- **Esquema:** `usuario.estado` (`ACTIVO`, `INACTIVO`; transición pura `ACTIVO ↔ INACTIVO` ya declarada), `usuario.tope_descuento_override numeric(9,6)` nulable (sin comando que lo escriba), `rol.activo`, `rol.nombre` **sin** índice único, `cliente` **sin** columna de vendedor.
- **Tope aplicable:** `obtener_datos_para_descuento_manual` ya devuelve `tope_propio` y `tope_rol`; la evaluación (DSC-06, `dsc-06-descuento-manual.json`) y `GET /ventas/contexto` ya usan el propio cuando existe.
- **Frontend:** área `/admin/roles` (17b: `RolesScreen`, `RolPermisosEditor`, confirmación "Agrega / Quita", aviso de propio rol, explicación de `IDENTIDAD_SIN_ADMINISTRADOR`), "Topes por rol" (16), "PIN de autorización" (18b). **No existe pantalla de usuarios.**

Lo que `docs/` **no** resuelve (cada punto es una decisión): el tamaño del change (D0); qué comandos tiene un usuario (D1); qué hace exactamente una baja (D2); cómo se extiende la regla del último administrador y con qué bloqueo (D3, D4); la autobaja (D5); la baja con jornada abierta o con cartera (D6); los efectos del cambio de rol (D7); la contraseña, restablecida por el administrador y cambiada por el propio usuario (D8, D20); qué datos se editan (D9); la creación de roles, que `00` §6.4 pone en la etapa 4 y `04` en el 20b (D10); la baja de roles (D11); el tope propio (D12); el modelo, el efecto y la administración de la cartera (D13 a D15); pantallas, auditoría y ayuda (D16 a D18); lo que necesita el 21 (D19).

## Goals / Non-Goals

**Goals:** cerrar ADR-028 D9.5 con comandos reales; extender ADR-053 a toda operación que pueda dejar la organización sin administrador; tope propio por usuario; contraseña propia con la actual ("Mi contraseña", D20); cartera administrable con una función pública que el 21 reutilice.

**Non-Goals:** "olvidé mi contraseña" por correo (lo cubre el restablecimiento del administrador, D8) y la edición propia de nombre y email (D20); permisos por usuario (etapa 4); zonas o rutas; bootstrap (21); cambiar `renovar_sesion` o el lote (ya cumplen ADR-028).

## Decisions

### D0 — Tamaño, lotes y posible división · alcance · BAJA · negocio

**Contexto.** El 20b junta cuatro piezas: (1) usuarios, (2) roles, (3) tope propio, (4) cartera. (1) y (2) son CRÍTICAS; (3) es pequeña (la columna existe); (4) es ALTA y toca `clientes`, `ventas` y `cobranzas` (solo lecturas). El 27a y el 21 dependen del 20b.

- **A (recomendada). Un change en cuatro lotes**, sin frenar entre lotes salvo en los puntos de control: **Lote 1** dominio y comandos de usuario (D1 a D9, D12) con su concurrencia; **Lote 2** roles (D10, D11) y migración; **Lote 3** cartera (D13 a D15); **Lote 4** pantallas, ayuda, cobertura, ADR, docs y prueba manual. Consecuencia: una sola confirmación de alcance, un solo ADR; el 27a y el 21 esperan un solo change. Tamaño por encima del habitual de `04` §2 (estimado tres a cuatro días); el Lote 3 es autocontenido y, si se desborda, se puede cortar sin tocar los lotes 1 y 2.
- **B. Dividir en 20b (usuarios, roles y tope) y 20d (cartera).** Consecuencia: el núcleo crítico se revisa y se archiva antes; pero el 27a ("crear usuarios y asignar clientes desde la aplicación") y el 21 (bootstrap con la cartera) pasan a depender también del 20d: hay que agregar una fila a `04` §4 y renumerar las deudas. Dos rondas de revisión y de prueba manual.
- **C. Dividir en tres** (usuarios y tope / roles / cartera). Consecuencia: tres changes chicos para una misma pantalla; la regla del último administrador queda repartida entre dos. No recomendada.

### D1 — Comandos de usuario · contrato · CRÍTICA

- **A (recomendada). Un comando por acción**, todos `ONLINE`, `ADMIN_USUARIOS`, declarados en el catálogo (ADR-056): `USUARIO_MODIFICAR` v1 (nombre y email, reemplazo completo), `USUARIO_BAJA` v1 (`usuario_id`, `observacion` opcional), `USUARIO_REACTIVAR` v1, `USUARIO_ROL_CAMBIAR` v1 (`usuario_id`, `rol_id`), `USUARIO_CONTRASENA_RESTABLECER` v1 (contraseña fuera del contenido, D8) y `USUARIO_TOPE_DESCUENTO_DEFINIR` v1 (D12). Rutas: `PUT /identidad/usuarios/{id}`, `POST .../baja`, `POST .../reactivacion`, `PUT .../rol`, `POST .../contrasena`, `PUT .../tope-descuento`. Una transición inválida (baja de un inactivo, reactivar un activo) responde 409 `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA` (ya existe). Consecuencia: cada acción tiene su permiso, su auditoría y sus reglas sin ramas; un cambio de rol nunca viaja escondido en una edición de datos.
- **B. Un `USUARIO_MODIFICAR` de reemplazo completo** (nombre, email, rol, estado, tope), como `MEDIO_PAGO_MODIFICAR`. Consecuencia: un solo comando, pero cada edición de un email pasa por la regla del último administrador y por la revocación; el handler decide qué cambió; la auditoría mezcla acciones de riesgo distinto.
- **C. A, pero la baja y la reactivación como un solo `USUARIO_ESTADO_CAMBIAR`.** Consecuencia: un comando menos; la reactivación hereda campos (observación) que no usa.

### D2 — Qué hace la baja de un usuario · seguridad · CRÍTICA

**Contexto.** ADR-028 D9.5: la baja revoca las sesiones "en la misma transacción, salvo la excepción de D9.3-B, y lo audita". `docs/` no dice qué pasa con el PIN ni con el motivo de revocación.

- **A (recomendada).** En una transacción, en este orden: (1) validaciones (D3, D4, D5); (2) `usuario.estado = 'INACTIVO'`; (3) revocar todas las familias de refresh vigentes del usuario **excepto** las de los dispositivos con jornada no cerrada de ese usuario, con `motivo_revocacion = 'USUARIO_INACTIVO'` (el mismo valor que ya usa la renovación: un solo vocabulario); (4) borrar el PIN de autorización (las tres columnas a nulo, como ADR-011 al perder los permisos de autorización): un inactivo no autoriza, y al reactivarlo hay que definirlo de nuevo; (5) auditoría (D17): la fila del comando (`BAJA_USUARIO`, `antes`/`despues` con el estado, observación) y, solo si se revocó alguna familia, `REVOCAR_SESIONES_REFRESH_USUARIO` con `origen = 'COMANDO'` y el mismo `operation_id`, que distingue esta revocación de la que hace la renovación (`origen = 'SISTEMA'`). Lo demás no cambia: el acceso se corta en la petición siguiente por D9.1 (ya implementado); los dispositivos con jornada siguen renovando y entregan su cola con `PERMISO_REVOCADO` (D9.3-B, SYN-10); no se revocan dispositivos (son de la organización, no del usuario); la cartera y el tope propio se conservan. La **reactivación** solo vuelve el estado a `ACTIVO` (D3 no aplica: suma un administrador) y audita `REACTIVAR_USUARIO`; el usuario inicia sesión de nuevo.
- **B. Como A, pero conservar el PIN.** Consecuencia: al reactivar, el supervisor autoriza sin redefinirlo; un PIN de alguien que se fue queda guardado (aunque inutilizable mientras esté inactivo).
- **C. Revocar también las sesiones con jornada no cerrada.** Consecuencia: contradice ADR-028 D9.3-B; la cola queda varada en el teléfono. No recomendada.

### D3 — Último administrador en baja, cambio de rol y baja de rol · seguridad · CRÍTICA

**Contexto.** ADR-053 punto 11 y su enmienda a ADR-028: la baja de un usuario, la de un rol y el cambio de rol "no pueden dejar la organización sin un usuario activo con `ADMIN_USUARIOS`".

- **A (recomendada). Generalizar la regla pura** a "administradores después del cambio ≥ 1", con un conteo SQL único `contar_administradores(organizacion_id, excluir_usuario_id=None, excluir_rol_id=None, rol_sustituto=(usuario_id, rol_id)=None)` sobre usuarios `ACTIVO` de roles activos con el permiso. Se aplica a: `USUARIO_BAJA` (excluye al usuario), `USUARIO_ROL_CAMBIAR` (cuenta al usuario con el rol nuevo), `ROL_BAJA` (excluye el rol; con D11-A nunca dispara porque el rol no tiene usuarios activos, queda como defensa en profundidad) y `ROL_PERMISOS_CAMBIAR` (sin cambio de comportamiento). Rechazo: 409 `IDENTIDAD_SIN_ADMINISTRADOR` (el código de ADR-053, sin código nuevo), validado **antes** de escribir, revocar o borrar el PIN (INV-01). `validar_queda_administrador` se reescribe sobre el conteo general y las pruebas del 17b quedan como red de seguridad. Con D5-A (autobaja prohibida) solo otro administrador puede dar de baja, así que en `USUARIO_BAJA` la regla solo dispara en una carrera (D4) y se prueba como defensa en profundidad; en `USUARIO_ROL_CAMBIAR` dispara en el caso común del administrador único que se cambia a sí mismo.
- **B. Una función por comando** con sus propios conteos. Consecuencia: cuatro variantes de la misma regla; más fácil que una diverja.
- **C. Proteger al usuario `admin` sembrado** (no se da de baja ni cambia de rol). Consecuencia: simple, pero no cubre a una organización cuyo administrador real es otro, y ata la regla a un nombre.

### D4 — Concurrencia y revalidación de quien ejecuta · seguridad · CRÍTICA

**Contexto.** Dos administradores A y B que se dan de baja mutuamente a la vez: el permiso de cada uno se verificó **antes** de la transacción del otro. Con dos administradores, la regla de D3 ya serializada rechaza el segundo. Con tres, los dos pasan y el comando de B se aplica aunque B ya fue dado de baja por A un instante antes.

- **A (recomendada). Exclusión mutua + revalidación.** Todo comando que puede cambiar quién administra o quién pertenece a un rol (`USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `ROL_BAJA`, `ROL_REACTIVAR`, `USUARIO_CREAR`, y `ROL_PERMISOS_CAMBIAR` cuando quita `ADMIN_USUARIOS`) toma **primero** `configuracion_organizacion FOR UPDATE` (el mutex que ya usa ADR-053), después el rol o los roles involucrados y el usuario objetivo `FOR UPDATE`, siempre en ese orden (configuración → rol → usuario → `sesion_refresh`); y, ya con el bloqueo, **revalida** que quien ejecuta sigue `ACTIVO`, con rol activo y con `ADMIN_USUARIOS` (si no: `PERMISO_REQUERIDO` 403, sin cambios). Se agrega a `02` §7.3. Consecuencia: las operaciones de identidad de una organización se serializan (volumen ínfimo); "A da de baja a B y B a A" deja exactamente una baja; una baja de rol y un cambio de rol hacia ese rol no se cruzan; un alta en un rol que se está dando de baja ve el rol inactivo.
- **B. Solo exclusión mutua, sin revalidar.** Consecuencia: con tres o más administradores, un administrador recién dado de baja puede completar un comando ya en curso. Riesgo bajo pero real en un dominio crítico.
- **C. Bloquear solo las filas de usuario y rol tocadas.** Consecuencia: no serializa operaciones sobre usuarios distintos; la regla de D3 cuenta sobre datos que otro está cambiando (el hueco que ADR-053 cerró con el mutex).

### D5 — Autobaja y cambio del propio rol · seguridad · CRÍTICA · negocio

- **A (recomendada).** **Autobaja prohibida:** `USUARIO_BAJA` sobre el propio `usuario_id` responde 409 `IDENTIDAD_AUTOBAJA` ("No podés darte de baja a vos mismo; pedíselo a otro administrador"), aunque haya otros administradores: evita quedar afuera por error y deja siempre un segundo par de ojos. **Cambio del propio rol permitido**, sujeto a D3, con el mismo aviso de la pantalla de roles del 17b ("vas a cambiar tu propio acceso") y confirmación; tras guardar se invalida `['yo']` (ADR-027).
- **B. Ambas prohibidas** (autobaja y propio rol). Consecuencia: más seguro; un administrador único que quiere pasarse a un rol nuevo tiene que crear otro usuario administrador primero.
- **C. Ambas permitidas**, solo con D3. Consecuencia: el administrador puede cortarse el acceso a sí mismo si hay otro; la pantalla lo cierra en el acto.

### D6 — Baja con jornada no cerrada o con clientes asignados · operación · ALTA · negocio

- **A (recomendada). Se permite, con avisos.** La pantalla avisa antes de confirmar: "tiene una jornada abierta en {ubicación}: su teléfono podrá subir lo pendiente, pero no podrá operar; para liberar la ubicación, liberá la jornada (RUT-09)" y "tiene {n} clientes asignados: quedan sin vendedor visible hasta reasignarlos". El backend no rechaza (la realidad física manda, `00` §3). Los avisos salen de lecturas existentes (jornadas, D19 cartera) que la pantalla consulta; `identidad` no importa `stock` ni `clientes`.
- **B. Rechazar la baja con jornada no cerrada** (`USUARIO_CON_JORNADA_ABIERTA`). Consecuencia: obliga a liberar primero; un vendedor que se fue a mitad de jornada sigue activo hasta que un supervisor libere.
- **C. Rechazar la baja con clientes asignados.** Consecuencia: obliga a reasignar antes de dar de baja; más pasos para un caso urgente.

### D7 — Efectos del cambio de rol · seguridad · CRÍTICA

- **A (recomendada).** `USUARIO_ROL_CAMBIAR`: rechaza un rol inexistente o de otra organización (404) y un rol inactivo (409 `IDENTIDAD_ROL_INACTIVO`); mismo rol → se acepta sin cambios ni auditoría de entidad (como el resto de los `*_CONFIGURAR`). Aplica D3 y D4. Si el rol nuevo no tiene ningún permiso de autorización (`PERMISOS_AUTORIZACION_EXCEPCION`) borra el PIN (ADR-011, mismo criterio que `ROL_PERMISOS_CAMBIAR`). **No revoca sesiones**: los permisos se leen en cada petición (ADR-017), así que el cambio rige en la petición siguiente; con jornada abierta, lo que el teléfono haga sin conexión se compara al sincronizar con los permisos del rol nuevo (SYN-10). Conserva el tope propio y la cartera. Auditoría `CAMBIO_ROL_USUARIO` con el rol anterior y el nuevo.
- **B. Como A, pero revocando las sesiones** (salvo jornada). Consecuencia: fuerza un login nuevo; no aporta seguridad (los permisos ya se leen por petición) y molesta.
- **C. Prohibir el cambio de rol con jornada no cerrada.** Consecuencia: evita permisos distintos entre teléfono y servidor a mitad de jornada, pero SYN-10 ya lo resuelve.

### D8 — Contraseña · seguridad · CRÍTICA · negocio

> **APROBADA la opción B (2026-10-28):** el restablecimiento por el administrador de A, más "Mi contraseña" (diseño en D20). Donde A dice que "Mi contraseña" queda fuera y se nomina al 28, **ya no rige**.

**Contexto.** Hoy la contraseña solo se define en el alta. No hay "olvidé mi contraseña" ni cambio propio. `USUARIO_DESBLOQUEAR` neutraliza el bloqueo por intentos (ADR-057).

- **A. Restablecer por el administrador** (base de la opción aprobada). `USUARIO_CONTRASENA_RESTABLECER` v1: la contraseña nueva viaja fuera del contenido (`exige_credenciales_efimeras`, ADR-056; misma validación que el alta). En la misma transacción: revoca las familias del usuario salvo las de dispositivos con jornada no cerrada (`motivo_revocacion = 'CONTRASENA_RESTABLECIDA'`), inserta el marcador de desbloqueo de `USUARIO_DESBLOQUEAR` (quien la restablece para que pueda entrar, no debería encontrarlo bloqueado) y audita `RESTABLECER_CONTRASENA` (sin la contraseña). No toca el PIN. Se permite sobre un usuario inactivo (queda listo para reactivar) y sobre uno mismo. "Mi contraseña" no está en A: la trae la opción B (D20).
- **B (APROBADA). A más "Mi contraseña"** (`CONTRASENA_PROPIA_CAMBIAR`, con la actual, contando fallos como el login, como "Mi PIN"). Consecuencia: más completo; suma una pantalla y un comando a un change ya grande.
- **C. Restablecer sin revocar sesiones ni desbloquear.** Consecuencia: si la contraseña se filtró, quien la tenía conserva su sesión hasta 30 días.

### D9 — Datos editables y alta · contrato · MEDIA

- **A (recomendada).** `USUARIO_MODIFICAR` edita `nombre` (obligatorio, recortado, hasta 200) y `email` (opcional; vacío = nulo; sin verificar dominio). El **nombre de inicio de sesión (`usuario`) no se edita**: es la clave del bloqueo por nombre escrito (ADR-057) y de la auditoría que lo cita; si está mal, se da de baja y se crea otro. El alta (`USUARIO_CREAR`, sin versión nueva) suma la validación del rol activo (409 `IDENTIDAD_ROL_INACTIVO`), el bloqueo de D4 y el nombre de usuario duplicado como 409 `IDENTIDAD_USUARIO_DUPLICADO` (hoy truena la restricción única). El tope propio no va en el alta: se define después (D12). **Regla de la contraseña (decisión del usuario, 2026-10-28, revisión del Lote 1):** `validar_contrasena` exige **al menos 8 caracteres**, sin reglas de mayúsculas, números ni símbolos, y no estar en blanco (ocho espacios se rechazan como en blanco); vale para el alta, el restablecimiento y D20; 422 `IDENTIDAD_CONTRASENA_INVALIDA`. Rige solo al definir una contraseña nueva: las existentes no se invalidan y el inicio de sesión no cambia.
- **B. Permitir renombrar `usuario`.** Consecuencia: hay que decidir qué pasa con los intentos de login de la clave vieja (ADR-057 punto 6) y con los registros que lo muestran.
- **C. Un alta v2 con tope y cartera.** Consecuencia: versión nueva de un comando existente (`02` §6.6) para ahorrar un paso de pantalla.

### D10 — Roles nuevos · alcance · ALTA · negocio

**Contexto.** `00` §6.4 pone "Roles personalizados desde la interfaz" en la **etapa 4**; `01` §19 dice "hasta el change de usuarios y roles no se crean roles nuevos"; `04` §9 (aprobado el 2026-10-24) los asigna al 20b. Hay que enmendar `00` §6.4.

- **A (recomendada).** `ROL_CREAR` v1 (`nombre`, `permisos`, `tope_descuento` opcional, por defecto 0; nace activo) y `ROL_RENOMBRAR` v1, ambos `ONLINE`, `ADMIN_USUARIOS`. Nombre recortado, 1 a 100 caracteres, **único por organización sin distinguir mayúsculas**, activos o no (índice `ux_rol__nombre` sobre `(organizacion_id, lower(nombre))`, como medios de pago y ubicaciones); la migración aborta nombrando la organización y el nombre si ya hubiera repetidos. Errores: `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO` (422), `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO` (409), permiso fuera del catálogo como hoy en `ROL_PERMISOS_CAMBIAR`. Las cinco plantillas se pueden renombrar como cualquier rol. En la pantalla, "Nuevo rol" ofrece "copiar permisos de" un rol existente (solo interfaz: el comando recibe la lista). Se enmienda `00` §6.4 (roles personalizados adelantados a la etapa 1).
- **B. Sin crear roles**: solo baja y renombrar las plantillas. Consecuencia: respeta `00` §6.4, contradice `04` §9 y la deuda de ADR-053.
- **C. Crear solo copiando una plantilla** (sin elegir permisos en el alta). Consecuencia: dos pasos para un rol a medida.

### D11 — Baja y reactivación de roles · seguridad · CRÍTICA · negocio

- **A (recomendada).** `ROL_BAJA` v1 y `ROL_REACTIVAR` v1 (`ONLINE`, `ADMIN_USUARIOS`). La baja se **rechaza si el rol tiene usuarios activos** (409 `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, con la cantidad en el mensaje), el complemento que ADR-028 D9.4 sugería: así nunca corta el acceso de nadie y D9.4-A queda solo como defensa en profundidad (ya implementada). Con usuarios inactivos se permite. Aplica D3 y D4. Un rol inactivo no se asigna (D7, D9), no aparece en los selectores, sigue en la lista de roles marcado "De baja" y sus permisos se pueden seguir editando. Ninguna plantilla está protegida: la regla de D3 ya impide dejar la organización sin administrador. La reactivación es libre. Auditoría `BAJA_ROL` y `REACTIVAR_ROL`. **Punto de control 8.0 (aprobado 2026-10-28):** el orden mutex -> rol `FOR UPDATE` -> conteo de usuarios activos -> defensa de D3 -> escritura -> auditoría queda aprobado; `ROL_PERMISOS_CAMBIAR` no toma bloqueo extra del rol cuando no quita `ADMIN_USUARIOS` (inocuo: se pueden editar los permisos de un rol de baja). Baja de un rol ya de baja y reactivación de uno ya activo se aceptan sin cambios ni auditoría de entidad (mismo criterio que un renombre o un tope sin cambio). `ROL_CREAR` y `ROL_RENOMBRAR` también toman el mutex de identidad para serializar los nombres y revalidar a quien ejecuta.
- **B. Permitir la baja con usuarios activos** y revocar en el acto las sesiones de todos ellos (salvo jornada), con `motivo_revocacion = 'ROL_INACTIVO'`. Consecuencia: corta de un golpe a un grupo; un error deja a todos los vendedores afuera.
- **C. A, pero proteger la plantilla Administrador.** Consecuencia: redundante con D3 y ata la regla a un nombre renombrable.

### D12 — Tope propio por usuario · negocio · ALTA

- **A (recomendada).** `USUARIO_TOPE_DESCUENTO_DEFINIR` v1 (`usuario_id`, `tope_descuento` string decimal o `null` para volver al del rol), `ADMIN_USUARIOS`, `ONLINE`; misma validación y código que el rol (`IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, 0 a 1, seis decimales, INV-03); toma el usuario `FOR UPDATE`; **una fila de auditoría** `TOPE_DESCUENTO_USUARIO` con el valor anterior y el nuevo (AUD-01, mismo patrón que `ROL_TOPE_DESCUENTO_DEFINIR`); el mismo valor se acepta sin auditoría de entidad. Se permite aunque el rol no tenga `DESCUENTO_MANUAL` (la pantalla avisa que no tiene efecto mientras el rol no lo tenga). Puede ser mayor o menor que el del rol (`03` §4). Se ve y se edita en la ficha del usuario; "Topes por rol" muestra, por rol, cuántos usuarios tienen tope propio. Rige desde la venta siguiente con conexión; sin conexión, desde el próximo bootstrap (SYN-11, 21).
- **B. Tope propio solo menor o igual que el del rol.** Consecuencia: un tope propio nunca amplía; contradice `03` §4 ("si es nulo rige el del rol", sin límite).
- **C. Sin comando propio: dentro de `USUARIO_MODIFICAR`.** Consecuencia: mezcla un dato comercial auditado aparte con datos personales.

### D13 — Modelo de la cartera · datos · MEDIA · negocio

- **A (recomendada). Un vendedor por cliente:** `cliente.vendedor_id uuid NULL` con clave foránea compuesta `(organizacion_id, vendedor_id) → usuario (organizacion_id, id)` e índice `ix_cliente__vendedor (organizacion_id, vendedor_id)`. Nulo = sin vendedor asignado. El consumidor final no se asigna (siempre visible para todos, CLI-03).
- **B. Varios vendedores por cliente:** tabla `cliente_vendedor (organizacion_id, cliente_id, usuario_id)`. Consecuencia: cubre clientes que visitan dos vendedores (bebidas y alimentos); más complejo de mostrar y de reasignar, y el bootstrap repite clientes entre teléfonos.
- **C. Zonas:** `zona` con clientes y vendedores por zona. Consecuencia: es "filtrado por vendedor o zona" de `00` §6.4 (etapa 4); suma una entidad entera.

### D14 — Qué cambia "sus clientes" · negocio · ALTA

**Contexto.** `01` §19: "el vendedor ve el saldo y el crédito disponible de sus clientes"; ADR-052: "sus clientes son todos los de la organización mientras no exista una asignación". `04` §4: "el bootstrap baja solo los clientes del vendedor (20b)". SYN-05 e INV-17: una venta o cobranza offline nunca se rechaza por reglas de negocio.

- **A (recomendada). La cartera ordena lo que se ofrece, no lo que se permite.** Quien llega a los clientes solo por `VENDER` o `REGISTRAR_COBRANZA` (sin `GESTIONAR_CLIENTES`) recibe en `GET /clientes/opciones` sus clientes asignados más el consumidor final, con un parámetro `alcance=todos` para buscar en todos (la pantalla ofrece "Buscar en todos los clientes"). **Si no tiene ningún cliente asignado, ve todos** (compatibilidad con ADR-052 y con la organización mientras asigna). Vender y cobrar a un cliente fuera de la cartera **se permite** con y sin conexión, sin rechazo ni observación nueva. Quien tiene `GESTIONAR_CLIENTES` ve todos siempre. El 21 baja la cartera (o todos, si está vacía). Sin permiso nuevo; la matriz de `01` §19 no cambia.
- **B. La cartera restringe.** Sin un permiso nuevo `VER_TODOS_LOS_CLIENTES`, las lecturas y los comandos con conexión fuera de la cartera responden 404 o `CLIENTE_FUERA_DE_CARTERA`; sin conexión se aceptan con una observación nueva `CLIENTE_FUERA_DE_CARTERA` (SYN-07). Consecuencia: control fuerte; amplía la matriz de permisos y el catálogo de observaciones; un vendedor que cubre a otro necesita que lo reasignen antes.
- **C. Solo dato y pantalla en este change**; el efecto lo decide el 21. Consecuencia: el 27a arranca con la cartera cargada pero sin efecto visible; pospone una decisión que el 21 necesita resuelta.

### D15 — Quién asigna y cómo · negocio · ALTA

- **A (recomendada).** Comando `CLIENTE_VENDEDOR_ASIGNAR` v1 en `clientes` (`ONLINE`, permiso `GESTIONAR_CLIENTES`): `cliente_ids` (1 a 500) y `vendedor_id` o `null` (quitar). Todo o nada (INV-01); un cliente de otra organización o inexistente → 404; el consumidor final → 409 `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR`. El vendedor debe estar `ACTIVO`, con rol activo y con `VENDER` o `REGISTRAR_COBRANZA` (409 `VENDEDOR_INVALIDO`), validado por `identidad/service.py`. Auditoría: la fila del comando y una de entidad por cliente cambiado (`ASIGNAR_VENDEDOR_CLIENTE`, antes y después). Bloquea los clientes `FOR UPDATE` en orden de id. Si después el vendedor pierde el permiso o se da de baja, la asignación se conserva (D6) y la pantalla lo marca. Pantallas: vendedor en la ficha (un selector), en el listado (columna y filtro, incluido "sin vendedor"), y selección múltiple "Asignar vendedor" en el listado; en la ficha del usuario, "Clientes asignados" con enlace al listado filtrado. La ficha del cliente (`CLIENTE_MODIFICAR`) no cambia. La lista de vendedores elegibles para los selectores sale de `GET /clientes/vendedores` (`GESTIONAR_CLIENTES`; `id` y `nombre`; misma regla de elegibilidad, calculada en SQL), de modo que asignar no exige `ADMIN_USUARIOS`.
- **B. Con `ADMIN_USUARIOS`.** Consecuencia: la asignación queda en manos del administrador de sistema y no de quien administra clientes (GES, SUP).
- **C. Un campo más de `CLIENTE_MODIFICAR`** (v2). Consecuencia: versión nueva de un comando con conexión y offline-agnóstico; sin asignación masiva.

### D16 — Lecturas y pantallas · interfaz · MEDIA

- **A (recomendada).** `GET /identidad/usuarios` suma `rol_nombre`, `rol_activo`, `tope_descuento_override` (string o nulo) y filtro por estado; `GET /identidad/usuarios/{id}` (404 entre organizaciones). `GET /identidad/roles` suma `activo` en los selectores y `usuarios_con_tope_propio` (usuarios de cualquier estado con tope propio definido; el tope se conserva en la baja, D2). Área nueva **"Usuarios"** en `/admin/usuarios` (`ADMIN_USUARIOS`; entrada en el menú, ADR-027): listado con estado, rol y filtro; alta (contraseña con confirmación); ficha con datos, rol, tope propio, contraseña, baja o reactivación (con confirmación y los avisos de D5, D6), desbloqueo (el comando existente) y PIN (enlace a la pantalla existente). El menú "Mi cuenta" ("Mi PIN" y "Mi contraseña") se define en D20. "Roles y permisos" suma "Nuevo rol", "Renombrar", "Dar de baja" y "Reactivar". Reintento con el mismo `Operation-Id`; tras un cambio sobre uno mismo se invalida `['yo']`. Las explicaciones de los códigos nuevos van en palabras simples.
- **B. Usuarios como pestaña dentro de "Roles y permisos".** Consecuencia: menos menú, pero mezcla dos listados largos.

### D17 — Auditoría · trazabilidad · MEDIA

- **A (recomendada).** Mismo patrón que ADR-053 punto 8: la fila genérica del bus (`entidad = 'comando'`) más una fila de entidad con `antes`/`despues` por acción: `MODIFICAR_USUARIO`, `BAJA_USUARIO` (con la observación), `REACTIVAR_USUARIO`, `CAMBIO_ROL_USUARIO`, `RESTABLECER_CONTRASENA`, `CAMBIAR_CONTRASENA_PROPIA` (D20), `TOPE_DESCUENTO_USUARIO`, `ALTA_ROL`, `RENOMBRAR_ROL`, `BAJA_ROL`, `REACTIVAR_ROL`, `ASIGNAR_VENDEDOR_CLIENTE`; y las de efecto: `REVOCAR_SESIONES_REFRESH_USUARIO` (`origen = 'COMANDO'`) e `INVALIDAR_PIN_AUTORIZACION` cuando aplique. `motivo_revocacion` de `sesion_refresh`: `USUARIO_INACTIVO` (baja; el mismo que la renovación), `CONTRASENA_RESTABLECIDA` (D8), `CONTRASENA_CAMBIADA` (D20). Un rechazo deja solo la fila del comando rechazado. Ningún secreto en ninguna fila (ADR-056).
- **B. Solo la fila genérica del bus.** Consecuencia: la auditoría de cambios de usuarios (AUD-01) no muestra el valor anterior.

### D18 — Ayuda contextual · interfaz · BAJA

Claves propuestas, **sin ejemplos** y solo donde la regla no es obvia (**aprobadas sin cambios el 2026-10-28**, incluida la revisada `roles.ultimoAdministrador`; sin clave para "Mi contraseña", por obvia):

- `usuarios.baja` (ADR-028; ADR-053): "Al dar de baja a un usuario deja de poder entrar y se cierran sus sesiones. Si tiene una jornada abierta, su teléfono puede subir lo que vendió o cobró sin conexión, pero no puede operar. No se puede dar de baja al último usuario que administra usuarios y roles, ni a uno mismo."
- `usuarios.cambioDeRol` (ADR-017; ADR-011): "El cambio rige desde la próxima acción del usuario. Si el rol nuevo no puede autorizar excepciones, se borra su PIN de autorización."
- `usuarios.topePropio` (DSC-06): "Si el usuario tiene tope propio, reemplaza al de su rol, sea mayor o menor. Vacío: rige el del rol. Solo tiene efecto si su rol tiene descuento manual."
- `usuarios.contrasena` (ADR-018; ADR-057): "La contraseña nueva cierra sus sesiones abiertas y desbloquea el inicio de sesión si estaba bloqueado."
- `roles.baja` (ADR-028): "Un rol con usuarios activos no se puede dar de baja: primero cambiales el rol. Un rol de baja no se puede asignar."
- `clientes.vendedor` (`01` §19): "Los vendedores ven primero sus clientes asignados y pueden buscar en todos. Un vendedor sin clientes asignados ve todos."
- **Revisada:** `roles.ultimoAdministrador`, para nombrar también la baja de usuarios y de roles y el cambio de rol.

### D19 — Lo que necesita el 21 · contrato · MEDIA

- **A (recomendada).** El 20b deja públicas, sin rutas nuevas para el bootstrap: `clientes/service.py::listar_cartera(organizacion_id, usuario_id) -> list[UUID]` (vacío si no tiene asignados; el 21 aplica la regla "vacía = todos" de D14) y `contar_clientes_asignados(organizacion_id, usuario_id)`; el tope aplicable ya lo da `GET /ventas/contexto` (ADR-055). Se nomina al 21: bajar la cartera (SYN-11) y, si un cliente se reasigna con una jornada abierta, que el teléfono lo vea en el próximo bootstrap.
- **B. Ruta `GET /clientes/cartera` ya en el 20b.** Consecuencia: contrato público que el 21 quizá reemplace.

### D20 — "Mi contraseña" · seguridad · CRÍTICA · negocio · APROBADA (2026-10-28)

**Contexto.** D8-B trae el cambio propio de contraseña. "Mi PIN" (18b, `definir_pin_propio`) ya resuelve el mismo problema —reautenticar con la contraseña actual sin dar a una sesión abierta una vía de fuerza bruta— y D20 lo repite.

- **Comando.** `CONTRASENA_PROPIA_CAMBIAR` v1, `ONLINE`, **sin permiso especial**: cualquier usuario autenticado y activo (`permisos=()`; el bus ya exige sesión válida y usuario activo, ADR-028). Solo actúa sobre **el propio usuario, que sale del token JWT**, nunca del cuerpo (contenido vacío con `extra="forbid"`, como `PIN_AUTORIZACION_PROPIO_DEFINIR`). Ruta `POST /api/v1/yo/contrasena` (junto a `/yo/pin-autorizacion`), 204.
- **Entradas.** Contraseña actual y contraseña nueva. La confirmación de la nueva es **solo de interfaz** (Zod); el servidor no la recibe. La nueva cumple **las mismas reglas** que el alta y el restablecimiento del administrador (misma función de validación, `validar_contrasena`: mínimo de 8 caracteres, sin reglas de composición, D9) y no puede ser igual a la actual (422 `IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL`, que no cuenta como intento fallido).
- **Secretos.** Las dos contraseñas viajan como datos efímeros por clausura (`exige_credenciales_efimeras`, ADR-056, igual que D8 y "Mi PIN"): no figuran en la huella, el comando, la cuarentena, la auditoría, el resultado ni el registro de idempotencia; el lote rechaza el tipo. Ningún `field_validator` sobre los secretos.
- **Contraseña actual incorrecta.** Se reutiliza el código existente `IDENTIDAD_CONTRASENA_INCORRECTA` (403, el mismo de "Mi PIN"; 403 y no 401 porque la interfaz trata el 401 como sesión terminada). **Cuenta como intento fallido de inicio de sesión** (ADR-018, ADR-057): se anota en `intento_login` en una **transacción aparte** que se confirma aunque el comando se rechace (mismo mecanismo y mismos límites que el login y "Mi PIN": usuario 5, IP 20, ventana de 15 minutos). Con el límite alcanzado responde 429 `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, también con la contraseña correcta, sin verificar ni escribir. Todo rechazo lanza una excepción de dominio (sin fila de `comando`), de modo que un reintento con el mismo `Operation-Id` y datos corregidos se procesa. Un cambio exitoso **no** borra los intentos fallidos previos (solo lo hace el desbloqueo del administrador, ADR-057).
- **Sesiones.** En la misma transacción se revocan las familias de refresh del usuario **de los demás dispositivos** (`motivo_revocacion = 'CONTRASENA_CAMBIADA'`), **conservando las del dispositivo de la sesión actual** (el `dispositivo_id` del token), y con la **misma excepción que D2 y D8**: tampoco se revocan las de dispositivos con una jornada no cerrada de ese usuario (ADR-028 D9.3-B; SYN-05, SYN-10), para no varar su cola. Se audita `REVOCAR_SESIONES_REFRESH_USUARIO` con `origen = 'COMANDO'` y el `operation_id`, solo si se revocó alguna familia. Los access tokens de las otras sesiones vencen solos (15 minutos) y su renovación ya no funciona. No toca el PIN de autorización.
- **Auditoría.** Fila genérica del bus más una de entidad `CAMBIAR_CONTRASENA_PROPIA` (sin ningún dato de la contraseña; con la cantidad de familias revocadas).
- **Pantalla.** `frontend/src/areas/admin/cuenta/MiContrasenaScreen.tsx`, junto a `MiPinScreen` (18b), en la ruta `/admin/mi-contrasena`. `AdminLayout` agrupa las dos entradas bajo un menú **"Mi cuenta"**, visible para **todo** usuario; "Mi PIN" conserva su regla actual de visibilidad (`ofreceMiPin`). Campos: contraseña actual, nueva y confirmación (Zod); explica en palabras simples `IDENTIDAD_CONTRASENA_INCORRECTA`, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` y la contraseña inválida; tras el éxito avisa que las demás sesiones se cerraron. Sin clave de ayuda.
- **Fuera de alcance.** "Olvidé mi contraseña" por correo (lo cubre el restablecimiento del administrador, D8) y la edición propia de nombre y email. **En `/ruta`** llega con el change 21 (deuda nominada en `propuesta-docs.md`, `04` §9).
- **Alternativas descartadas.** Exigir `ADMIN_USUARIOS` (el usuario común no podría); límite propio distinto del login (abriría otra vía de fuerza bruta); revocar también la sesión actual (obliga a iniciar sesión justo después de cambiarla).

## Risks / Trade-offs

- [Mutex de la organización] Las operaciones de identidad se serializan → volumen ínfimo; los comandos de negocio no toman ese bloqueo salvo los `*_CONFIGURAR` que ya lo toman (no hay ciclo: ninguno toma después usuario o rol).
- [Revalidación del actor] Un rechazo `PERMISO_REQUERIDO` dentro del handler en lugar de en la ruta → probado con concurrencia real; el mensaje es el mismo.
- ["Mi contraseña" y fuerza bruta] La contraseña actual se verifica con el límite del login y el fallo se confirma en transacción aparte → probado con commits reales (tarea 4.5).
- [Borrado del PIN en la baja] Al reactivar un supervisor hay que redefinir su PIN → aviso en la pantalla de reactivación (D2-A).
- [Cartera "vacía = todos"] Una organización que asigna a algunos vendedores y no a otros: los segundos ven todos → es la transición esperada; la pantalla muestra "sin clientes asignados: ve todos".
- [Nombre de rol duplicado en datos existentes] La migración aborta con un mensaje claro → la base de desarrollo tiene las cinco plantillas con nombres distintos.
- [Tamaño] Change más grande que el promedio → cuatro lotes; el Lote 3 (cartera) se puede cortar a otro change si se desborda (D0).

## Migration Plan

Una revisión de Alembic: índice único `ux_rol__nombre (organizacion_id, lower(nombre))` (aborta si hay repetidos, nombrando organización y nombre) y `cliente.vendedor_id` nulable con su FK compuesta e índice. `downgrade`: quita la columna (se pierde la asignación) y el índice. Sube y baja limpia sobre una base con ventas (`04` §2.1 punto 4). Sin privilegios nuevos: `app_runtime` ya tiene `UPDATE` sobre `usuario`, `rol`, `cliente` y `sesion_refresh`. Ningún dato existente cambia.

## Open Questions

Ninguna. D0 a D20 quedaron confirmadas el 2026-10-28 (D8 en la opción B; D20 nueva). Queda un punto de control: **8.0**, el visto bueno antes de `ROL_BAJA`. Se verifica en el apply, sin cambiar decisiones: que `declarar_tipo` admita `permisos=()` para un comando de cualquier usuario autenticado (si no, se agrega esa variante al bus).
