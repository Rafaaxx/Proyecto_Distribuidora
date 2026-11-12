# Diseño técnico — 17b-medios-de-pago-y-roles

> **Estado: D0 a D12 APROBADAS por el usuario el 2026-10-17, opción A (recomendada) en todas, con aprobación explícita de D1, D4, D5, D7 y D8.** Cada decisión trae dos o tres opciones, sus consecuencias y una recomendada. Lo que se apruebe se documenta en **ADR-053** (estado *Propuesto* durante el apply, último lote) y en `propuesta-docs.md`. Precisaría ADR-028 (nota D9.5: este change **no** trae la baja de usuarios ni de roles) y enmendaría `01` §4 y §19, `02` §6.5 y §11, `03` §4 y `04` §2, §4 y §8.
>
> **Gobernanza por dominio.** **CRÍTICO** (análisis y aprobación explícita antes de escribir; cualquier ampliación se detiene y se consulta): **D7** (qué se puede hacer con los roles) y **D8** (la protección del último administrador). **ALTO** (se propone y se espera visto bueno): **D1** (quién administra los medios), **D4** (reglas de la baja) y **D5** (cambiar datos de la organización que ya existe). **MEDIO:** D2, D3, D9 y D10. **BAJO:** D0, D6, D11 y D12.
>
> **Revisión.** El usuario revisa con todo el change implementado; no se frena entre lotes. Sí se frena antes de escribir el código de las piezas críticas (D7, D8), en las tareas que lo dicen.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **`configuracion`** (change 02): tabla `medio_pago` (`id`, `organizacion_id`, `nombre`, `requiere_referencia`, `activo`, `creado_en`, `actualizado_en`, `actualizado_por_id`), con `UNIQUE (organizacion_id, id)` y **sin** unicidad de nombre. `service.py` ya tiene `crear_medio_pago`, `desactivar_medio_pago`, `obtener_medio_pago` (activo o no) y `listar_medios_pago_activos`, pero **no hay ningún comando**: el módulo no tiene `commands.py`. `app_runtime` tiene `SELECT, INSERT, UPDATE` sobre `medio_pago` (sin `DELETE`). `GET /configuracion/medios-pago` devuelve solo los activos, con cualquier sesión (ADR-043).
- **Validación de medios** (`configuracion/domain/medios.py`, change 17): suma exacta, de 1 a 20 medios, medio activo y referencia obligatoria; la usan pagos a proveedores y cobranzas. Sin conexión, un medio inactivo o una referencia faltante se aceptan con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (ADR-052, D13-C). **Este change no la toca**: solo cambia los datos que lee.
- **Siembra** (`app/seed.py`): crea la organización inicial con los cinco medios, todos con `requiere_referencia=False`. Las migraciones de los changes 11, 12, 14, 15 y 17 ya sembraron motivos en organizaciones existentes de forma idempotente: hay precedente para una migración de datos.
- **Patrón de maestros** (categorías, change 05; ubicaciones, change 14, ADR-038): `X_CREAR` + `X_MODIFICAR` con reemplazo completo, incluido `activo`; nombre único `(organizacion_id, lower(nombre))` en ubicaciones; una fila de auditoría por comando (ADR-022).
- **Roles** (change 03 y 04): `ROL_PERMISOS_CAMBIAR` v1 (`ADMIN_USUARIOS`, solo `ONLINE`) sobre `identidad/service.py::cambiar_composicion_rol`: reemplaza el conjunto, rechaza un código inexistente, audita antes/después e **invalida el PIN** de los usuarios del rol si pierde su último permiso de autorización (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR`; ADR-011). **No protege** contra quitarle `ADMIN_USUARIOS` al único rol que lo tiene. `GET /identidad/roles` devuelve roles con tope y permisos. **No hay** lectura del catálogo de permisos (vive en `identidad/domain/permisos.py`, con código, descripción y módulo) ni pantalla de usuarios: `GET/POST /identidad/usuarios` existen sin pantalla, y **ningún comando cambia el rol de un usuario**.
- **Efecto de un permiso quitado** (ADR-017, ADR-027, 06b): vale en la petición siguiente; el menú de `/admin` se actualiza al renovar.
- **Menú** (`features/identidad/secciones.ts`): "Configuración" con `ADMIN_CONFIGURACION` (pestañas "Fiscal" y "Lista predeterminada"); ninguna sección con `ADMIN_USUARIOS` (la pantalla "Topes por rol" vive en Descuentos y exige además `GESTIONAR_DESCUENTOS`).

Lo que `docs/` **no** resuelve (cada punto es una decisión abierta):

- `01` §19 da a `ADMIN_CONFIGURACION` "configuración de la organización" sin nombrar los medios. → D1.
- TR-09 dice que los medios son datos, sin decir qué se edita ni con qué comandos. → D2. `03` §4 no pide nombre único. → D3.
- CAT-05 dice "se desactiva", sin reglas para la baja de un medio. → D4.
- `01` §4 dice "lista con indicador de referencia obligatoria" sin decir cuáles lo tienen. → D5 (valores aprobados por el usuario el 2026-10-16; falta decidir cómo llegan a la organización existente).
- `00` §3 y `01` §19 permiten a la organización crear y modificar roles; ADR-028 D9.5 deja la baja de usuarios y roles para "el change de usuarios y roles". → D7.
- Nada impide dejar la organización sin nadie que administre usuarios. → D8.

## Goals / Non-Goals

**Goals:** que un administrador cree, edite, dé de baja y reactive medios de pago desde `/admin`, por el bus, sin borrar nada; que Transferencia, Cheque y Tarjeta pidan referencia en toda organización; que un administrador cambie los permisos de un rol desde `/admin` sin poder dejar la organización sin administrador.

**Non-Goals:** crear o desactivar roles, crear, desactivar o cambiar de rol a usuarios (D7); motivos y alícuotas (D10); topes (ya en el 16); la lista de medios sin conexión (21).

## Decisions

### D0 — Tamaño y lotes · técnica · BAJO

- **A (recomendada). Un change en tres lotes**, sin frenar entre lotes salvo las confirmaciones de D7 y D8:
  1. **Lote 1 — Medios de pago (backend):** migración (índice único y valores por defecto), siembra, dominio, `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR`, lectura completa.
  2. **Lote 2 — Roles (backend, CRÍTICO):** protección del último administrador en `cambiar_composicion_rol` y `GET /identidad/permisos`.
  3. **Lote 3 — Pantallas y cierre:** "Medios de pago", "Roles y permisos", ayuda, concurrencia, cobertura, ADR-053, propuesta de docs, prueba manual.
  Consecuencia: entra en `04` §2 (de medio día a tres días).
- **B. Dos changes: `17b-medios-de-pago` y `17c-permisos-por-rol`.** Consecuencia: dos archivados, dos pruebas manuales; el 18a solo necesita el primero.
- **C. Un lote único.** Consecuencia: la pieza crítica (D8) queda mezclada con el resto y su confirmación frena todo.

**Ejemplo.** Al cerrar el lote 1, por API, se crea "Mercado Pago" y se da de baja "Billetera"; al cerrar el lote 3, lo mismo desde la pantalla.

### D1 — Quién administra los medios de pago · negocio · ALTO · ADR-053

**Contexto.** `01` §19: `ADMIN_CONFIGURACION` = "Configuración de la organización (incluye … ubicaciones, STK-02)". Solo lo tiene el Administrador. `01` §4 pone los medios en la tabla "Configuración por organización".

- **A (recomendada). `ADMIN_CONFIGURACION`**, y `01` §19 lo nombra ("incluye crear, modificar, desactivar y reactivar medios de pago"). Consecuencia: sin permiso nuevo ni migración del catálogo; la pantalla va en "Configuración", que ya se ofrece con ese permiso.
- **B. Permiso nuevo `GESTIONAR_MEDIOS_PAGO`** (Administrador y Administración). Consecuencia: la administración podría tocar medios sin tocar la configuración fiscal; agrega un permiso al catálogo (migración, plantillas, `01` §19).
- **C. `GESTIONAR_CATALOGO`.** Consecuencia: lo tendría Administración, pero mezcla productos con dinero.

**Ejemplo.** Rafa (Administrador) agrega "Mercado Pago"; Laura (Administración) no ve la pestaña.

### D2 — Comandos y qué se puede cambiar · negocio · MEDIO · ADR-053

- **A (recomendada). `MEDIO_PAGO_CREAR` (nombre, pide referencia) y `MEDIO_PAGO_MODIFICAR` (reemplazo completo: nombre, pide referencia y activo)**, igual que categorías y ubicaciones; v1, solo `ONLINE`. Un medio nace activo. Cambiar el nombre está permitido: las cobranzas y los pagos guardan el id, así que los viejos se ven con el nombre nuevo (las observaciones de cobranza ya guardan el nombre de entonces, ADR-052). Errores: `NOMBRE_INVALIDO` (422, vacío o solo espacios; se guarda recortado), `NOMBRE_DUPLICADO` (409, D3), `ULTIMO_MEDIO_ACTIVO` (409, D4), medio de otra organización o inexistente → 404. Modificar sin cambios no escribe ni audita de más: deja la fila de auditoría del comando, como los demás maestros.
- **B. Además, comandos separados `MEDIO_PAGO_DESACTIVAR` y `MEDIO_PAGO_REACTIVAR`.** Consecuencia: cuatro comandos en vez de dos; rompe el patrón de maestros.
- **C. Como A, pero el nombre no se cambia una vez usado.** Consecuencia: protege la lectura de la historia, pero obliga a crear un medio nuevo para corregir una falta de ortografía.

**Ejemplo.** "Billetera" pasa a llamarse "Mercado Pago": el pago de ayer de $10.000 figura como "Mercado Pago".

### D3 — Nombre único · técnica · MEDIO

- **A (recomendada). Único por organización sin distinguir mayúsculas, activos o no** (`ux_medio_pago__nombre` sobre `(organizacion_id, lower(nombre))`, como ubicaciones, ADR-038). La migración aborta con un mensaje claro si ya hay nombres repetidos (la siembra no los tiene). Consecuencia: no se puede crear "efectivo" si existe "Efectivo", ni aunque esté de baja: se reactiva.
- **B. Único solo entre los activos** (índice parcial). Consecuencia: dos "Billetera", una de baja; confunde la historia.
- **C. Sin unicidad.** Consecuencia: dos "Transferencia" en el desplegable de la cobranza.

### D4 — Reglas de la baja · negocio · ALTO · ADR-053

**Contexto.** CAT-05/TR-06: no se borra; los inactivos no se ofrecen y se siguen leyendo por id. El change 17 ya resolvió qué pasa con una cobranza sin señal que usa un medio dado de baja (`MEDIO_INACTIVO`).

- **A (recomendada). Baja y reactivación libres, salvo que quede ningún medio activo** (`ULTIMO_MEDIO_ACTIVO`, 409). Para que dos bajas simultáneas no dejen cero, el comando bloquea los medios de la organización antes de contar. Consecuencia: sin medios activos no se podría cobrar ni pagar; con conexión, cobrar o pagar con un medio de baja sigue respondiendo `MEDIO_PAGO_INACTIVO`.
- **B. Sin ninguna restricción.** Consecuencia: se puede quedar sin medios y ninguna cobranza ni pago se registra.
- **C. Como A, y además no se da de baja un medio mientras haya jornadas abiertas.** Consecuencia: evita marcas `MEDIO_INACTIVO`, pero traba a la oficina durante el día.

**Ejemplo.** Con solo "Efectivo" activo, darlo de baja responde "Tiene que quedar al menos un medio de pago activo".

### D5 — Valores por defecto de "pide referencia" · negocio · ALTO · ADR-053

**Aprobado por el usuario el 2026-10-16:** Transferencia, Cheque y Tarjeta piden referencia; Efectivo y Billetera no. Falta decidir cómo llegan a la organización que ya existe.

- **A (recomendada). Siembra y migración.** La siembra de una organización nueva los crea así. La migración pone `requiere_referencia = true` en los medios de toda organización existente llamados exactamente (sin distinguir mayúsculas) "Transferencia", "Cheque" o "Tarjeta". Es seguro porque hasta este change **nadie pudo cambiar** esa marca (no había comando). El `downgrade` no la vuelve atrás (se documenta y una prueba lo deja escrito): después del 17b, el valor pudo haberlo elegido una persona. Consecuencia: desde la migración, una cobranza o un pago con transferencia sin número se rechaza con conexión (`REFERENCIA_OBLIGATORIA`) y sin conexión queda con `REFERENCIA_FALTANTE`.
- **B. Solo organizaciones nuevas.** La organización existente lo cambia a mano en la pantalla nueva. Consecuencia: depende de que alguien se acuerde; en la organización real, hasta entonces, nada pide referencia.
- **C. Solo migración, sin tocar la siembra.** Consecuencia: una organización nueva vuelve a nacer sin referencias.

**Ejemplo.** Al subir la migración, cobrar $20.000 por "Transferencia" sin número responde "Este medio de pago exige referencia".

### D6 — Lectura para la pantalla · técnica · BAJO

- **A (recomendada). Ruta nueva `GET /configuracion/medios-pago/todos`** con `ADMIN_CONFIGURACION`: activos e inactivos, ordenados por nombre, con `requiere_referencia`, `activo` y `actualizado_en`. `GET /configuracion/medios-pago` queda igual (solo activos, cualquier sesión). Consecuencia: cada ruta declara un solo permiso (ratchet de rutas).
- **B. Parámetro `?incluir_inactivos=true` en la ruta existente,** con permiso solo cuando vale `true`. Consecuencia: una ruta con dos reglas de permiso; el ratchet no lo cubre.

### D7 — Qué se puede hacer con los roles · negocio · **CRÍTICO** · ADR-053

**Contexto.** `00` §3: "una organización puede crear roles propios combinando permisos". `01` §19: "la organización puede modificar su composición y los topes". ADR-028 D9.5 y `04` (nota del 06b): el "change de usuarios y roles" trae la baja de usuarios y de roles, con revocación de sesiones y sin trabar la cola offline. Hoy no hay pantalla de usuarios y **ningún comando cambia el rol de un usuario**.

- **A (recomendada). Solo cambiar los permisos de los roles que ya existen**, con una pantalla sobre `ROL_PERMISOS_CAMBIAR` y la lectura nueva del catálogo de permisos (`GET /identidad/permisos`, `ADMIN_USUARIOS`). Crear roles, desactivarlos y todo lo de usuarios queda para el "change de usuarios y roles", que se anota en el roadmap como pendiente (sin número, igual que hoy). Consecuencia: cubre lo que faltó en la prueba del 17; el riesgo crítico queda acotado a un comando que ya existe.
- **B. A + crear roles** (`ROL_CREAR`: nombre y permisos, opcionalmente copiando otro rol). Consecuencia: un rol nuevo solo serviría para usuarios nuevos creados por API, porque no hay forma de pasarle un usuario existente ni pantalla de usuarios: queda a medias.
- **C. Todo el "change de usuarios y roles" acá** (pantalla de usuarios, alta, cambio de rol, baja de usuarios y de roles con ADR-028). Consecuencia: duplica o triplica el change, todo en dominio crítico, y atrasa el 18a.

**Ejemplo.** Rafa le quita "Anular cobranzas" al Supervisor comercial; Ana (supervisora) deja de ver "Anular" en su próxima acción.

### D8 — Que la organización no se quede sin administrador · negocio · **CRÍTICO** · ADR-053

**Contexto.** Hoy Rafa puede quitarle `ADMIN_USUARIOS` al rol Administrador; desde la petición siguiente nadie puede devolvérselo, y solo se arregla tocando la base.

- **A (recomendada). Regla en el servidor:** `ROL_PERMISOS_CAMBIAR` se rechaza con `IDENTIDAD_SIN_ADMINISTRADOR` (409) si, después del cambio, **ningún usuario `ACTIVO` con rol activo** tendría `ADMIN_USUARIOS`. El comando bloquea la configuración de la organización antes de contar, para que dos cambios simultáneos sobre roles distintos no lo esquiven. El rol queda como estaba y no se invalida ningún PIN. El futuro change de usuarios y roles aplica la misma regla a la baja de usuarios y de roles. Consecuencia: regla de negocio nueva (TR-10: se valida en el servidor); la pantalla la explica con un "(?)".
- **B. El rol Administrador no se edita** (solo lectura). Consecuencia: más simple, pero contradice "los roles son plantillas" y no impide quitárselo a otro rol que sea el único con el permiso.
- **C. Solo un aviso en la pantalla, sin regla en el servidor.** Consecuencia: por API se puede romper igual.

**Ejemplo.** Si solo Rafa es Administrador, quitarle "Usuarios, roles y permisos" al rol Administrador responde "La organización se quedaría sin nadie que administre usuarios y roles". Si Laura (Administración) también tuviera ese permiso, el cambio se acepta.

### D9 — Pantalla "Roles y permisos" · negocio · MEDIO

- **A (recomendada). Sección nueva del menú "Roles y permisos"** (`/admin/roles`, con `ADMIN_USUARIOS`): lista de roles (nombre, estado, cantidad de permisos y de usuarios activos); al elegir uno, sus permisos agrupados por módulo (Ventas, Cobranzas, Stock…), cada uno con su descripción y una casilla; al guardar, un resumen "Agrega: … / Quita: …" con confirmación, y avisos cuando se quita un permiso de autorización (se borra el PIN de sus usuarios, D11) o se toca el propio rol de quien edita. Reintento con el mismo `Operation-Id`. Un enlace a "Topes por rol" (Descuentos). Los permisos de funciones que todavía no existen (venta, facturación, reportes) se muestran igual, con la marca "llega más adelante".
- **B. Dentro de "Topes por rol" (Descuentos).** Consecuencia: exige además `GESTIONAR_DESCUENTOS` y mezcla dos temas.
- **C. Lista de permisos sin agrupar ni resumen.** Consecuencia: 40 casillas seguidas; fácil equivocarse.

### D10 — Otros catálogos sin pantalla (motivos y alícuotas) · alcance · MEDIO

**Contexto.** TR-09 también cubre motivos y alícuotas. Hoy los motivos se siembran por migración y no se pueden agregar ni dar de baja; las alícuotas solo se leen.

- **A (recomendada). Fuera de este change**, anotados como deuda en `04` (sin dueño, igual que el change de usuarios y roles). Consecuencia: el change queda chico; los motivos sembrados alcanzan para la etapa 1 ("Otro" en cada ámbito); la alícuota casi no cambia (monotributo).
- **B. Agregar acá la pantalla de motivos** (alta, nombre, baja; mismo patrón). Consecuencia: un tercer lote; suma reglas propias (no dar de baja el último motivo de un ámbito).
- **C. Agregar motivos y alícuotas.** Consecuencia: las alícuotas tocan productos y precios (riesgo en el cálculo).

### D11 — Auditoría · técnica · BAJO · AUD-01

- **A (recomendada).** Una fila por comando (ADR-022), con `antes` y `despues` (nombre, pide referencia, activo) en `MEDIO_PAGO_MODIFICAR` y `despues` en `MEDIO_PAGO_CREAR` ("cambios de configuración", AUD-01). `ROL_PERMISOS_CAMBIAR` sigue como está. Un rechazo por D4 o D8 no deja cambios, solo la fila de comando rechazado. La invalidación del PIN sigue dejando sus filas (`INVALIDAR_PIN_AUTORIZACION`).
- **B. Solo la fila del comando, sin antes/después.** Consecuencia: no se sabe qué cambió.

### D12 — Ayuda contextual · técnica · BAJO · ADR-051

- **A (recomendada).** Cinco claves nuevas en `frontend/src/ayuda/textos.ts`, con el estilo aprobado en el 16b (para qué sirve en una oración; palabras de todos los días; un ejemplo con nombres y montos reales; tres o cuatro oraciones). Sin tema "Ver más".
- **B. Solo "pide referencia" y "permisos del rol".** Consecuencia: la baja, el último administrador y el PIN quedan sin explicar.

**Textos aprobados por el usuario el 2026-10-17 (tarea 0.2), con sus correcciones: el 3 dice «ya no ven el botón» sin nombre y el 4 va sin ejemplo. Usar estos textos exactos:**

| # | Clave | Pantalla y campo | Reglas | Texto propuesto |
| --- | --- | --- | --- | --- |
| 1 | `mediosPago.requiereReferencia` | Medios de pago · "Pide referencia" | COB-02, PAG-01, SYN-07 | "Marcalo si cada vez que se use este medio hay que anotar un dato para encontrar la plata después, como el número de la transferencia o del cheque. Con conexión, sin ese dato no se guarda el cobro ni el pago; si el vendedor está sin señal, entra igual y queda marcado para revisar. Ej.: «Transferencia» pide referencia: al cobrar $20.000 por transferencia hay que escribir el n.º 0042." |
| 2 | `mediosPago.baja` | Medios de pago · "Dar de baja" | CAT-05, TR-06, ADR-053 | "Deja de ofrecerse en cobros y pagos nuevos. No se borra: los de antes lo siguen mostrando, y lo podés volver a activar cuando quieras. Siempre tiene que quedar al menos un medio activo. Ej.: cerraste la cuenta de la billetera → das de baja «Billetera»; el pago de $10.000 de ayer sigue diciendo «Billetera»." |
| 3 | `roles.permisos` | Roles y permisos · Permisos del rol | `01` §19, ADR-017 | "Lo que puede hacer cada persona que tiene este rol. Cuando guardás, el cambio vale para todos los usuarios del rol desde su próxima acción, sin cerrar la sesión. Ej.: le quitás «Anular cobranzas» al Supervisor comercial → ya no ven el botón «Anular» en las cobranzas." |
| 4 | `roles.ultimoAdministrador` | Roles y permisos · "Usuarios, roles y permisos" | ADR-053 | "Siempre tiene que quedar al menos una persona activa que pueda administrar usuarios y roles; si no, nadie podría arreglar los permisos después. Por eso no te deja quitar este permiso si es el último que lo tiene." |
| 5 | `roles.autorizacion` | Roles y permisos · permisos de autorización | ADR-011 | "Con estos permisos, la persona puede autorizar excepciones con su PIN, como un descuento mayor o vender pasado el límite de crédito. Si el rol se queda sin ninguno, se borra el PIN de sus usuarios y, si después se los devolvés, cada uno tiene que crear uno nuevo. Ej.: le sacás «Autorizar descuentos» y «Vender con exceso de crédito» al Supervisor → el PIN de Ana deja de servir." |

## Risks / Trade-offs

- **[D5 cambia el comportamiento de cobranzas y pagos ya en uso]** → desde la migración, transferencias, cheques y tarjetas piden número; lo dice el texto 1 y la prueba manual lo ejercita. Sin conexión no se rechaza nada (ADR-052).
- **[D8 se apoya en una cuenta que puede cambiar al mismo tiempo]** → bloqueo de la configuración de la organización y prueba de concurrencia con commits reales (dos cambios simultáneos sobre roles distintos).
- **[D4: dos bajas simultáneas]** → bloqueo de los medios de la organización y prueba de concurrencia.
- **[Quien edita su propio rol se puede quitar permisos que usa]** → aviso en la confirmación (D9); D8 impide el caso irreparable.
- **[Renombrar cambia cómo se lee la historia]** (D2-A) → aceptado; las observaciones guardan el nombre de entonces.
- **[Un rol nuevo sigue sin poder crearse]** (D7-A) → se anota en `04` como el pendiente "change de usuarios y roles".

## Migration Plan

Una revisión de Alembic sobre `d7e8f9a0b1c2` (change 17): (1) verifica que no haya nombres repetidos (sin distinguir mayúsculas) por organización y, si los hay, aborta con la lista; (2) crea `ux_medio_pago__nombre` sobre `(organizacion_id, lower(nombre))`; (3) pone `requiere_referencia = true` en "Transferencia", "Cheque" y "Tarjeta" de toda organización (D5-A), idempotente. `downgrade` borra el índice y **no** revierte los valores (D5-A); una prueba lo deja escrito. Sin columnas nuevas ni cambios de privilegios.

## Open Questions

- D7: cuándo se programa el "change de usuarios y roles" (crear y desactivar roles, pantalla de usuarios, cambio de rol, baja con ADR-028). Antes de producción conviene tenerlo.
- D10: si en la operación real aparecen motivos que faltan, la pantalla de motivos se puede sumar como change chico.
