# Propuesta de cambios a `docs/` — change 28 `aceptacion-y-endurecimiento`

> **Borrador con las opciones A de `design.md`, aprobadas el 2026-11-10 (0.1), y Q2 resuelta (permiso `VER_CONSISTENCIA`).** Completado con las precisiones del apply (tarea 8.3, hecho): ver las notas «Precisión del apply» de abajo. **Pendiente: visto bueno del usuario para aplicarlo a `docs/`.** Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia. Las decisiones van en `docs/adr/ADR-073-aceptacion-y-endurecimiento.md`.
>
> Orden: `02` §7.6, §15, §16.2, §18; `03` (tabla nueva, roles); `04` §12 y deuda del 14; ADR-018, ADR-057, ADR-071 (notas de enmienda).

---

## `02-arquitectura.md`

### §7.6 Verificación de consistencia — D2, D4, D5, D6

**Actual**

> Una tarea diaria compara cada tabla de saldo con la suma de su libro. Cualquier diferencia se registra como error crítico en el log y se notifica al administrador. Nunca se corrige automáticamente: una diferencia indica un defecto que debe investigarse.

**Propuesto**

> Una tarea diaria (servicio `tareas`, `TAREAS_HORA`) compara, por organización, `saldo_cuenta` con su libro, `stock_saldo` con su libro, `stock_total` con la suma de los saldos del producto y el promedio vigente con el último `costo_producto_mov`. El resultado se guarda en `verificacion_consistencia`; una diferencia se registra como error crítico en el log, deja no sana la salud del servicio, usa el aviso externo opcional y se muestra en `/admin` a quien tiene `ADMIN_CONFIGURACION` mientras el último resultado tenga diferencias. Nunca se corrige automáticamente: una diferencia indica un defecto que debe investigarse (ADR-015, ADR-073).

### §15 Estrategia de pruebas — D11 a D16

Agregar a las reglas:

> - Un ratchet verifica que cada invariante de `01` §20 de la etapa 1 (todos salvo INV-09 e INV-20) esté citado por una prueba que corre la CI (ADR-073).
> - La cobertura de aislamiento asocia cada ruta de negocio con las pruebas que la ejercen; el ratchet falla si una no existe o no cita INV-21 (ADR-073).
> - La suite de Playwright corre contra el compose de producción en un proyecto aparte (`distribuidora-aceptacion`), con la siembra del escenario de aceptación; falla ante cualquier violación de CSP. El criterio 12 lo cubren las pruebas de restauración de `backend/tests/infra` (ADR-073).

Reemplazar el párrafo del paso 5:

> El paso 5 corre `tests/integration` y `tests/infra` (compose de producción, Caddyfile en los dos modos de `CADDY_TLS`, imágenes de respaldo, roles de base) y, en un paso propio, `tests/concurrency` (ADR-071, ADR-073).

### §16.1 Desarrollo — D14

Reemplazar la segunda viñeta:

> - Datos de ejemplo cargables con un comando: `python -m app.seed` (organización inicial) y `python -m app.seed --escenario-aceptacion` (usuarios, ubicaciones y configuración de la demostración de `00` §9; repetible).

### §16.2 Producción — D2, D3

Agregar a la tabla:

> | `tareas` | Todos los días a `TAREAS_HORA`: verificación de consistencia por organización y limpieza de `intento_login` de más de 24 horas, con el rol `app_mantenimiento` (ADR-073) |

Agregar a las viñetas: red `datos` también para `tareas`; `app_mantenimiento` se crea con `30-init-mantenimiento-role.sh` en un volumen nuevo o con el SQL del runbook antes de migrar.

### §18 Seguridad — D3, D8, D9, D10

Reemplazar «Encabezados de seguridad, incluida una política CSP restrictiva.» por:

> - Encabezados en Caddy para toda respuesta (fragmento compartido con el perfil `lan`): CSP `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`, `X-Frame-Options: DENY`, sin `Server`. La documentación de la API no se publica en producción (ADR-073).

Agregar a la viñeta de roles:

> … y un cuarto, `app_mantenimiento`, que solo lee saldos y libros, inserta resultados de verificación y borra `intento_login` de más de 24 horas. Una matriz de privilegios por rol y tabla, verificada por prueba, fija todo `GRANT` (ADR-073).

## `01-dominio.md`

### §19 Permisos y roles — Q2, D5

- Fila nueva en la tabla de permisos: `| VER_CONSISTENCIA | Ver el aviso de diferencias de la verificación de consistencia en `/admin` y leer su resultado (solo lectura; no modifica nada) | ✓ | ✓ | | | |` (ADM y GES; **la columna GES corresponde a `Administración`**, comprobar el orden de columnas al aplicar). Verificar que la fila conserve `| ID |` y `| etapa |` si la tabla los lleva (gotcha del archive).
- Cambiar «40 permisos» por «41» donde el documento cuente el catálogo, y agregar una línea en el párrafo de lecturas: «El resultado de la verificación de consistencia se lee con `VER_CONSISTENCIA` (ADR-073)».
- `02` y `03`: ajustar los conteos de permisos del catálogo (40 a 41) donde aparezcan.

## `03-modelo-de-datos.md`

- Tabla nueva `verificacion_consistencia` (columnas de D5), de solo inserción para `app_mantenimiento`; `app_runtime` solo `SELECT`.
- `intento_login`: «se borran las filas de más de 24 horas (tarea diaria, `app_mantenimiento`)».

## `04-roadmap-changes.md`

- §2: excepción de tamaño del change 28 (ocho lotes, ADR-073), si D0 queda en A.
- §12, nota de la deuda del 14: «el 28 salda la parte (1); la consulta de auditoría con motivo y la parte (3) pasan a la etapa 2» (D1 A).
- §12: párrafo de cierre del change 28 al archivar.

## ADR (notas de enmienda)

- **ADR-018 y ADR-057 punto 9:** la limpieza está implementada en el change 28 (ADR-073).
- **ADR-071 punto 3:** CSP y demás encabezados implementados en el 28 (ADR-073).
- **ADR-015 y ADR-039:** la verificación diaria está programada (ADR-073).

---

## Precisiones del apply (tarea 8.3)

Cambios al texto propuesto arriba por lo que salió en el apply (detalle en `ADR-073`, «Precisiones del apply»):

- **`02` §7.6.** Agregar: «El servicio `tareas` puede avisar a un servicio externo de «hombre muerto» (`AVISO_TAREAS_URL`, opcional, distinta de `AVISO_URL` de `copia-externa`): tras cada corrida llama a la dirección si no hubo diferencias ni fallos y a `<dirección>/fail` si los hubo; un aviso que no llega no altera la corrida (ADR-073). Las señales locales son el aviso en `/admin`, el registro crítico y la salud no sana.» Y: «La lectura del resultado pasa por `GET /api/v1/sistema/consistencia` (permiso `VER_CONSISTENCIA`).»
- **`02` §16.2 (tabla de servicios).** `tareas`: redes `datos` y `salida` (solo saliente; sin puertos); variables `TAREAS_HORA`, `TZ`, `AVISO_TAREAS_URL` (opcional) y `APP_MANTENIMIENTO_DB_PASSWORD` (sexto secreto del archivo de entorno). En un entorno existente el rol se crea **antes** de migrar (runbook C12).
- **`02` §16.2 (Caddy).** `FRENTE_SUBRED` y los puertos de Caddy son variables del compose de producción.
- **`02` §15.** La suite de aceptación registra el service worker con `--ignore-certificate-errors` (certificado interno de Caddy); el tramo 5 a 8 corre en un único teléfono sin señal. El criterio 9 lo anula `sup01` desde `/admin`.
- **`02` §18 / frontend.** Zod 4 se configura con `jitless` (`src/lib/zodSinEval.ts`) para no sondear `new Function` bajo la CSP. `/docs`, `/redoc` y `/openapi.json` apagados en producción.
- **`01` §19.** La fila de `VER_CONSISTENCIA` aclara la limitación: el aviso del inicio de `/admin` se arma sobre `REVISAR_OBSERVACIONES`; un rol a medida sin ese permiso no lo ve (fuera de alcance, etapa 2).
- **`00` §9.** Criterios 1 y 3: importar y publicar los hace `Administrador` (`IMPORTAR_DATOS`, `PUBLICAR_LISTAS`), no Gestión. Criterio 9: anulación por supervisor. Criterio 4: con la jornada abierta no se transfiere (STK-09).
- **Al archivar.** Actualizar a mano el texto del requisito de consistencia de `openspec/specs/cuentas-corrientes/libro-de-cuenta-corriente/spec.md` («La tarea diaria… es del change 28») y verificar que las filas de `docs/01` conserven `| ID |` y `| etapa |`.
