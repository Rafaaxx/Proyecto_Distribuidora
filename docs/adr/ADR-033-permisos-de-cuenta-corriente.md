# ADR-033 — Permisos de la cuenta corriente: `IMPORTAR_DATOS` registra el saldo inicial; `GESTIONAR_CLIENTES` y `GESTIONAR_PROVEEDORES` leen el estado de cuenta

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-29 |
| Referenciado en | `openspec/changes/08-cuentas-corrientes/design.md` D1 y D2 y `specs/cuentas-corrientes/saldo-inicial`, `specs/cuentas-corrientes/estado-de-cuenta`; `01-dominio.md` §19 (permisos) y §21 (saldo inicial); ADR-027 (permisos efectivos); ADR-031 (separación de permisos de clientes y crédito) |

**Decisiones (D1, opción A; D2, opción A) aprobadas por el usuario el 2026-09-29. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

`01` §19 lista los permisos del sistema, pero no tiene uno para registrar un saldo inicial ni uno para ver la cuenta corriente. El change 08 introduce las dos capacidades: el comando `SALDO_INICIAL_REGISTRAR` (solo online, `02` §6.5), que cambia el saldo de un cliente o de un proveedor sin que exista una venta o una compra detrás y por eso es una escritura sensible, y el estado de cuenta, que expone la deuda de una entidad. El bus declara un permiso por tipo de comando y el ratchet de rutas exige un permiso por ruta, así que había que elegir cuáles.

Se registra como ADR porque el reparto de permisos afecta a más de un change: el change 10 (importación de planillas) va a cargar los saldos iniciales por el mismo camino, y los changes 17 y 26 leen o muestran saldos con sus propios permisos.

## Decisión

1. **Registrar un saldo inicial** (`SALDO_INICIAL_REGISTRAR`, tanto de clientes como de proveedores) exige `IMPORTAR_DATOS` ("Importaciones y puesta en marcha", `01` §19). Es un único comando con un único permiso. La carga a mano desde la pantalla y la importación por planilla del change 10 usan el mismo permiso.
2. **Leer el estado de cuenta** exige el permiso de la entidad, el mismo que da acceso a su ficha: `GESTIONAR_CLIENTES` para `GET /api/v1/clientes/{id}/cuenta-corriente` y `GESTIONAR_PROVEEDORES` para `GET /api/v1/proveedores/{id}/cuenta-corriente`. Es el mismo criterio de ADR-031 punto 3: ver un dato no exige poder editarlo.
3. **No se agrega ningún permiso nuevo** al catálogo `permiso`: no hay migración de permisos ni cambio de plantillas de rol.

## Consecuencias

- Con las plantillas actuales, solo el Administrador (ADM) puede registrar un saldo inicial. Administración (GES) no puede, salvo que la organización agregue `IMPORTAR_DATOS` a su rol: es un cambio de plantilla, no de código.
- Con las plantillas actuales, ADM, GES y SUP ven la cuenta de los clientes; ADM y GES la de los proveedores. El rol Consulta/Dirección (CON) no la ve en esta pantalla: sus saldos le llegan con el reporte de saldos del change 26 (`VER_REPORTES`). El vendedor tampoco: el saldo de sus clientes le llega con el bootstrap (SYN-11, change 21), no con la pantalla de `/admin`.
- La interfaz decide qué mostrar con `usePermisos()` (ADR-027): la acción "Registrar saldo inicial" solo se ofrece con `IMPORTAR_DATOS`, y la API responde 403 `PERMISO_REQUERIDO` si se la invoca sin él.
- Si más adelante se necesita que otro rol cargue o vea saldos sin heredar el resto de los permisos de la ficha, se agrega un permiso nuevo en `01` §19 con su migración del catálogo; hoy no hay motivo.

## Alternativas consideradas

- **Permiso de la entidad para registrar el saldo inicial** (`GESTIONAR_CREDITO` para clientes y `GESTIONAR_PROVEEDORES` para proveedores): descartada: como el bus declara un permiso por tipo de comando, obliga a partir el comando en dos, distinto de `02` §6.5; y "editar el límite de crédito" y "crear deuda" son cosas distintas que quedarían bajo el mismo permiso.
- **Permiso nuevo `REGISTRAR_SALDO_INICIAL`**: descartada: es lo más explícito, pero agrega un permiso y una migración del catálogo para una tarea que se hace una vez en la vida de la organización.
- **`VER_REPORTES` para leer las cuentas**: descartada: daría acceso a la cuenta de proveedores al Supervisor comercial (que hoy no ve la ficha del proveedor) y haría que el permiso de reportes gobernara una pantalla operativa.
- **Permiso nuevo `VER_CUENTAS_CORRIENTES`**: descartada: obliga a decidir su reparto por rol sin una necesidad concreta.
