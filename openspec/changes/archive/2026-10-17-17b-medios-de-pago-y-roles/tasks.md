# Tareas — 17b-medios-de-pago-y-roles

> Modo TDD estricto: en cada tarea de los grupos 1 a 13, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. El grupo 13 completa la cobertura por escenario e invariante; no la reemplaza. Las tareas están escritas con la opción **recomendada** de cada decisión de `design.md`; si el usuario elige otra en 0.1, se actualizan antes del apply.
>
> **Dónde va el código:** `backend/app/modules/configuracion/` suma `commands.py` (handlers de medios) y amplía `domain/valores.py`, `repository.py`, `service.py`, `schemas.py` y `api.py`. La protección del último administrador va en `identidad/domain/usuarios.py` (regla pura) y `identidad/service.py::cambiar_composicion_rol`. Frontend: `frontend/src/areas/admin/configuracion/` (pestaña nueva), área nueva `frontend/src/areas/admin/roles/`, `features/configuracion/`, `features/identidad/`.
>
> **Lotes de apply (tres, `design.md` D0):** Lote 1 = grupos 1 a 5 (medios de pago, backend). Lote 2 = grupos 6 y 7 (roles, backend, **CRÍTICO**). Lote 3 = grupos 8 a 15 (pantallas, ADR, ayuda, concurrencia, cobertura, propuesta de docs y prueba manual). No se frena entre lotes a esperar revisión; el resumen de cada lote informa las comprobaciones automáticas. El usuario revisa con todo el change implementado. **Sí se frena** en las confirmaciones de las piezas críticas (6.0 y 9.0).
>
> **Gobernanza:** **CRÍTICO** (se muestra el cambio exacto y se espera aprobación explícita antes de escribir; cualquier ampliación se detiene y se consulta): **grupo 6** (D8, protección del último administrador) y **grupo 9** (D7, D9, pantalla que cambia permisos). **ALTO** (se muestra y se espera visto bueno, que puede darse en 0.1): **grupo 1** (D3, D5: migración que cambia datos de la organización existente) y **tarea 4.2** (D4, reglas de la baja). **MEDIO:** grupos 3, 4 (salvo 4.2), 7 y 8. **BAJO:** grupos 2, 5 y 10 a 15.
>
> **Fixtures compartidos:** este change no agrega ni modifica reglas de cálculo de precios, descuentos ni costos; no hay tarea de fixtures. Si durante el apply aparece un cálculo compartido entre Python y TypeScript, se detiene y se agrega el fixture antes del código.
>
> **Cómo correr las suites:** `pytest` por carpeta (`tests/unit`, `tests/integration`, `tests/concurrency`, `tests/properties`) con `backend/.venv`; las de frontend, con Docker detenido.

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones: el usuario aprueba D0 a D12 de `design.md`, con aprobación **explícita** de las críticas (D7, D8) y las altas (D1, D4, D5). Se anota fecha y opción en cada decisión; si alguna difiere de la recomendada, se actualizan proposal, specs y tareas antes del apply (`openspec-update-change`). Verificable: `design.md` sin "PENDIENTE" en D0 a D12 (los textos de D12 se aprueban en 0.2).
- [x] 0.2 Textos de ayuda: el usuario revisa los cinco textos de D12 (estilo del 16b) y los aprueba o corrige. Se anota en D12 la fecha y lo aprobado. Bloquea solo la tarea 11.1; los lotes 1 y 2 pueden empezar antes.

## 1. Migración (Lote 1, ALTO)

- [x] 1.1 RED: `backend/tests/integration/test_medios_pago_migracion.py` exige (D3, D5): índice `ux_medio_pago__nombre` único sobre `(organizacion_id, lower(nombre))` (dos nombres que solo difieren en mayúsculas se rechazan en la misma organización y se aceptan en organizaciones distintas; cita INV-02); en una organización creada antes de la migración con sus cinco medios sin referencia, Transferencia, Cheque y Tarjeta quedan con `requiere_referencia = true` y Efectivo y Billetera no; un medio de otro nombre no cambia. GREEN: una revisión de Alembic sobre `d7e8f9a0b1c2`.
- [x] 1.2 RED (mismo archivo): con dos medios "Billetera" y "billetera" en una organización, la migración aborta con un mensaje que nombra la organización y el nombre, sin cambiar nada. GREEN en la misma revisión.
- [x] 1.3 RED: ciclo `upgrade → downgrade → upgrade` sobre una base con datos (medios usados en una cobranza y en un pago a proveedor): sube y baja limpio, no duplica medios y deja como aserción explícita que el `downgrade` borra el índice y **no** revierte las marcas de referencia (D5-A). Verificable: `04` §2.1 punto 4.
- [x] 1.4 RED: `test_modelos_coinciden_con_migracion.py` incluye el índice nuevo; `test_inv05_*` confirma que `app_runtime` sigue sin `DELETE` sobre `medio_pago` (cita INV-05, TR-06). GREEN en 2.1.

## 2. Modelos y siembra (Lote 1)

- [x] 2.1 RED: las pruebas de 1.4. GREEN: `configuracion/models.py` declara el índice (`alembic revision --autogenerate` sin diferencias). Verificable: `mypy app` limpio.
- [x] 2.2 Red de seguridad: pruebas de siembra. RED (spec `organizacion/catalogos-configurables`, "Valores por defecto de la siembra"; cita `01` §4, COB-02): una organización recién sembrada tiene Transferencia, Cheque y Tarjeta con referencia obligatoria, y Efectivo y Billetera sin. GREEN en `app/seed.py` (la lista de medios iniciales lleva la marca de cada uno).

## 3. Dominio de medios (Lote 1)

- [x] 3.1 RED en `backend/tests/unit/test_configuracion_medios_dominio.py` (D2, D3): el nombre se recorta; vacío o de solo espacios lanza un error con código `NOMBRE_INVALIDO` (422), alineado con CAT-01 y ubicaciones (la clase existente `NombreVacioError` se alinea o se reemplaza, sin cambiar a quien ya la usa). GREEN en `configuracion/domain/valores.py`.
- [x] 3.2 RED (mismo archivo; D4): regla pura `validar_quedan_medios_activos(activos_antes, medio, activo_nuevo)`: dar de baja el único activo lanza `ULTIMO_MEDIO_ACTIVO` (409); con dos activos, o al reactivar, no. GREEN en el dominio.

## 4. Comandos de medios de pago (Lote 1)

- [x] 4.1 Red de seguridad: suites de `configuracion`, ratchet de rutas y de comandos, `lint-imports`. RED en `backend/tests/integration/test_medio_pago_comandos.py` (spec `organizacion/administracion-de-medios-de-pago`, requisito "Un medio de pago se crea por comando"; cita TR-09, INV-06, INV-21): `MEDIO_PAGO_CREAR` v1 por `POST /api/v1/configuracion/medios-pago` (`requiere_comando_online("ADMIN_CONFIGURACION")`); alta, nombre recortado, `NOMBRE_INVALIDO`, `NOMBRE_DUPLICADO` (409, también contra un inactivo y sin distinguir mayúsculas; el mismo nombre en otra organización se acepta), 403 sin permiso, doble envío con el mismo `operation_id`, una fila de auditoría con `despues` (D11). GREEN: `configuracion/commands.py` (handler registrado, `declarar_tipo(..., admite_online=True, admite_offline=False)`), `service.py`, `repository.py` (traduce la violación de `ux_medio_pago__nombre` a `NOMBRE_DUPLICADO`), `schemas.py`, `api.py`.
- [x] 4.2 **(ALTO, D4)** RED (mismo archivo; requisito "Un medio de pago se modifica, se da de baja y se reactiva por comando"; cita CAT-05, TR-06, COB-02, PAG-01): `MEDIO_PAGO_MODIFICAR` v1 por `PUT /api/v1/configuracion/medios-pago/{id}` con reemplazo completo (nombre, `requiere_referencia`, `activo`); renombrar, marcar referencia (una cobranza y un pago con conexión sin referencia responden `REFERENCIA_OBLIGATORIA`), baja (deja de listarse en `GET /configuracion/medios-pago`, sigue legible por id y en el detalle de la cobranza y del pago que lo usan; una cobranza nueva con conexión responde `MEDIO_PAGO_INACTIVO`), reactivación, `ULTIMO_MEDIO_ACTIVO` (409; el repositorio bloquea los medios de la organización con `FOR UPDATE` antes de contar), `NOMBRE_DUPLICADO` al renombrar, 404 para otra organización o id inexistente, doble envío, auditoría con `antes` y `despues`. GREEN en los mismos archivos.
- [x] 4.3 RED: el ratchet de rutas de escritura confirma que las dos rutas pasan por el bus y declaran `ADMIN_CONFIGURACION`; el catálogo de tipos de comando incluye `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR` solo `ONLINE` (cita `02` §6.5); por el lote en modo `ONLINE` se comportan igual que por REST; ninguna ruta ni comando borra medios. GREEN si hace falta. Verificable: `lint-imports` (`configuracion/commands.py` no importa otros módulos de negocio) y `mypy app` limpios.

## 5. Lectura completa de medios (Lote 1)

- [x] 5.1 RED en `backend/tests/integration/test_medios_pago_lectura.py` (requisito "La administración lee todos los medios de pago"; D6; cita TR-08, INV-21): `GET /api/v1/configuracion/medios-pago/todos` con `ADMIN_CONFIGURACION` devuelve activos e inactivos de la organización del token, ordenados por nombre, con `requiere_referencia`, `activo` y `actualizado_en`; 403 sin permiso; `GET /configuracion/medios-pago` sigue igual (solo activos, cualquier sesión). GREEN en `api.py`, `queries.py`. Verificable: `npm run` de generación de tipos del OpenAPI actualizado (`schema.gen.ts`).

## 6. Que la organización no se quede sin administrador (Lote 2, **CRÍTICO**)

- [x] 6.0 **Confirmación crítica (APROBADA por el usuario el 2026-10-17: bloqueo FOR UPDATE de la configuración solo cuando se quita ADMIN_USUARIOS; conteo en SQL; regla pura con conteos; SinAdministradorError IDENTIDAD_SIN_ADMINISTRADOR 409, mensaje "La organización se quedaría sin nadie que administre usuarios y roles"; el rechazo no toca PIN):** antes de escribir código, mostrar al usuario el cambio exacto de `cambiar_composicion_rol` (dónde se bloquea, cómo se cuenta, el código de error y que el rechazo no toca el PIN) y esperar su aprobación explícita. Se anota fecha.
- [x] 6.1 RED en `backend/tests/unit/test_identidad_sin_administrador.py` (D8): regla pura que, dados los usuarios activos con rol activo y los permisos de cada rol después del cambio, dice si queda al menos uno con `ADMIN_USUARIOS`; casos: único rol con el permiso pierde el permiso (falla), otro rol con usuario activo lo conserva (pasa), otro rol solo con usuarios inactivos (falla), rol inactivo con el permiso (no cuenta). GREEN en `identidad/domain/usuarios.py`.
- [x] 6.2 Red de seguridad: suites de `identidad` (incluida la invalidación de PIN). RED en `backend/tests/integration/test_rol_sin_administrador.py` (spec `identidad/usuarios-y-roles`, requisito "Ningún cambio de permisos deja la organización sin administrador"; cita ADR-053, TR-10, INV-01, INV-02, INV-06): `PUT /identidad/roles/{id}/permisos` responde 409 `IDENTIDAD_SIN_ADMINISTRADOR` en los casos de 6.1; el rol queda igual y el PIN sigue vigente; con otro usuario activo con el permiso se acepta; otra organización no cuenta; doble envío. GREEN en `identidad/service.py::cambiar_composicion_rol`: bloquea la configuración de la organización (`obtener_configuracion_bloqueada`) antes de contar y valida **antes** de escribir y de invalidar PIN; error de dominio con código estable en `identidad`.

## 7. Catálogo de permisos (Lote 2)

- [x] 7.1 RED en `backend/tests/integration/test_identidad_permisos_catalogo.py` (spec `identidad/administracion-de-roles`, requisito "El catálogo de permisos se lee por API"; cita `01` §19): `GET /api/v1/identidad/permisos` con `ADMIN_USUARIOS` devuelve código, descripción y módulo en el orden de `01` §19; 403 sin permiso. GREEN en `identidad/api.py` y `service.py`. Verificable: ratchet de permiso por ruta y `schema.gen.ts` actualizado.
- [x] 7.2 RED: `GET /identidad/roles` suma la cantidad de usuarios activos de cada rol (para D9), sin otros cambios. GREEN en `identidad/repository.py` (cuenta con SQL, no en Python).

## 8. Pantalla de medios de pago (Lote 3)

- [x] 8.1 Red de seguridad: suites de `areas/admin/configuracion`. RED en `frontend/tests/unit/configuracion/MediosPagoScreen.test.tsx` (requisito "La pantalla de medios de pago"; D2, D4): pestaña "Medios de pago" en `ConfiguracionArea` (`/admin/configuracion/medios-pago`), solo con `ADMIN_CONFIGURACION`; lista con nombre, "Pide referencia" y estado; alta y edición con React Hook Form + Zod; baja y reactivación con confirmación; `NOMBRE_DUPLICADO`, `NOMBRE_INVALIDO` y `ULTIMO_MEDIO_ACTIVO` en palabras simples; reintento con el mismo `Operation-Id`; la lista se refresca y las consultas de medios activos (`['medios-pago']`) se invalidan. GREEN en `frontend/src/areas/admin/configuracion/MediosPagoScreen.tsx` y `features/configuracion/` (api y hooks). Sin lógica de negocio en el componente.

## 9. Pantalla de roles y permisos (Lote 3, **CRÍTICO**)

- [x] 9.0 **Confirmación crítica (APROBADA por el usuario el 2026-10-17, diseño D9-A tal como se mostró: lista de roles con estado, permisos y usuarios activos; permisos por módulo con descripción, casilla y "llega más adelante"; resumen Agrega/Quita con confirmación; avisos de PIN y de rol propio; enlace a Topes por rol; sin crear ni desactivar roles):** antes de escribir código, mostrar al usuario el diseño de la pantalla (agrupación por módulo, resumen y avisos de D9) y esperar su aprobación explícita. Se anota fecha.
- [x] 9.1 Red de seguridad: suites de `features/identidad` y `areas/admin/descuentos` (Topes por rol). RED en `frontend/tests/unit/roles/RolesScreen.test.tsx` (spec `identidad/administracion-de-roles`, requisito "La pantalla de roles y permisos"; D7, D9; cita `01` §19, ADR-011, ADR-017, ADR-027): sección "Roles y permisos" (`/admin/roles`) en `features/identidad/secciones.ts` con `ADMIN_USUARIOS`; lista de roles con estado, cantidad de permisos y de usuarios activos; permisos agrupados por módulo con descripción y casilla, y la marca "llega más adelante" en los de funciones que todavía no existen; resumen "Agrega / Quita" con confirmación; aviso de PIN cuando el rol se queda sin permisos de autorización (la lista de esos permisos sale de `domain/identidad/`, no del componente); aviso al editar el propio rol; `IDENTIDAD_SIN_ADMINISTRADOR` explicado; reintento con el mismo `Operation-Id`; enlace a "Topes por rol"; sin crear, desactivar ni borrar roles; al guardar se invalida `['yo']` para que el menú propio se actualice. GREEN en `frontend/src/areas/admin/roles/` y `features/identidad/`.

## 10. ADR (Lote 3)

- [x] 10.1 Redactar `docs/adr/ADR-053-medios-de-pago-administrables-y-permisos-por-rol.md` (estado *Propuesto*) con las decisiones aprobadas en 0.1, las precisiones del apply y la nota sobre ADR-028 D9.5 (la baja de usuarios y roles sigue pendiente y debe aplicar la misma regla de D8). Va antes de 11.1, porque los textos de ayuda citan ADR-053 y la prueba de trazabilidad exige que exista.

## 11. Ayuda contextual (Lote 3)

- [x] 11.1 **Ayuda: claves nuevas `mediosPago.requiereReferencia`, `mediosPago.baja`, `roles.permisos`, `roles.ultimoAdministrador` y `roles.autorizacion`; ninguna revisada; sin tema "Ver más"** (D12, ADR-051). Requiere 0.2 y 10.1. Revisar con `grep` los textos que citan COB-02 (`cobranzas.medios`) por si el cambio de D5 los afecta (no se espera cambio). RED: `tests/unit/ayuda/trazabilidad.test.ts` y las pruebas de pantalla de 8.1 y 9.1 exigen los "(?)" del requisito "Las pantallas de medios de pago y de roles explican sus reglas" con los textos aprobados en 0.2. GREEN en `frontend/src/ayuda/textos.ts` y las pantallas.

## 12. Concurrencia (Lote 3)

- [x] 12.1 RED en `backend/tests/concurrency/test_medios_y_roles_concurrencia.py` (commits reales de sesiones independientes): dos bajas simultáneas de los dos últimos medios activos (una sola se acepta; cita INV-01, ADR-053); dos `ROL_PERMISOS_CAMBIAR` simultáneos que quitan `ADMIN_USUARIOS` a los dos únicos roles que lo tienen (uno solo se acepta; cita ADR-053); dos altas simultáneas de "Mercado Pago" (una `NOMBRE_DUPLICADO`); doble envío simultáneo del mismo comando (cita INV-06). GREEN si hace falta. Una falla intermitente se investiga, no se ignora.

## 13. Cobertura por escenario e invariante (Lote 3)

- [x] 13.1 Cada escenario de las cinco specs delta tiene al menos una prueba que lo nombra; INV-01, INV-02, INV-05, INV-06 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas, `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación.

## 14. Propuesta de docs (Lote 3)

- [x] 14.1 Completar `openspec/changes/17b-medios-de-pago-y-roles/propuesta-docs.md` (borrador ya escrito con la opción recomendada) con lo aprobado en 0.1 y las precisiones del apply: `01` §4 y §19, `02` §6.5 y §11, `03` §4, y `04` §2, §4 (fila del 17b y su "Depende de"), §8 (fila del 17b en el hito 4, deudas) y la nota del change de usuarios y roles. **No se aplica a `docs/`** sin el visto bueno del usuario.

## 15. Prueba manual (Lote 3)

- [x] 15.1 El orquestador le da al usuario, en el chat, el paso a paso de la prueba manual en el navegador: crear "Mercado Pago" con referencia; intentar "mercado pago" repetido; renombrar y dar de baja "Billetera" y ver que un pago viejo la sigue mostrando y que ya no se ofrece al cobrar; intentar dar de baja el último activo; cobrar por "Transferencia" sin número (rechazo) y con número; reactivar; en "Roles y permisos", quitar "Anular cobranzas" al Supervisor comercial y comprobar con un supervisor que ya no puede anular; intentar quitarle "Usuarios, roles y permisos" al Administrador (rechazo explicado); ver los "(?)"; entrar con un usuario sin permisos y no ver las secciones. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5.
