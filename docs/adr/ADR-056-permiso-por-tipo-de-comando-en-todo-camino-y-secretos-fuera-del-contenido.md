# ADR-056 — Permiso por tipo de comando exigido por el bus en todo camino y secretos fuera del contenido

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-24, archivo del change 18b) |
| Fecha | 2026-10-22 |
| Referenciado en | `openspec/changes/18b-venta-online-descuentos-credito/design.md` D23 (y D2, D21); `01-dominio.md` SEG-06, SYN-05, SYN-06, SYN-10; `02-arquitectura.md` §6.2, §6.3 (paso 4), §6.5, §17; ADR-012, ADR-019, ADR-022, ADR-028, ADR-048, ADR-049, ADR-052, ADR-055 |

**El usuario aprobó en principio el 2026-10-22 resolver esto dentro del change 18b y ese mismo día confirmó la regla concreta (tarea 0.3): la opción A (ni B ni C), el código `MODO_NO_ADMITIDO_PARA_TIPO` para los tipos con secretos en el lote y el renombre `permiso_offline` → `permisos`. Vigente desde el 2026-10-24, al archivar el change 18b.**

## Contexto

SEG-06: "El servidor valida los permisos en cada comando". `02` §6.3, paso 4: en `ONLINE` el permiso "lo valida el handler, por REST y por el lote". El lote (`POST /api/v1/sync/comandos`) admite ítems `ONLINE` a propósito (la spec `sistema/pipeline-de-comandos` exige que un comando dé el mismo resultado por REST y por el lote; ADR-048 punto 5 y ADR-049 punto 19 lo usan). La ruta REST exige el permiso con `requiere_comando_online`; el lote no: `procesar_comando` recibe `verificar_permiso`, que por defecto no hace nada, y `_evaluar_permiso_offline` solo actúa en `OFFLINE` (ADR-052 punto 8).

Revisando los 61 tipos declarados en 12 módulos, 17 handlers no exigen su permiso y confían en la ruta: `USUARIO_CREAR`, `ROL_PERMISOS_CAMBIAR`, `PIN_AUTORIZACION_ROTAR`, `USUARIO_DESBLOQUEAR` (`ADMIN_USUARIOS`), `DISPOSITIVO_REVOCAR` (`GESTIONAR_DISPOSITIVOS`), los nueve de `catalogo` (`GESTIONAR_CATALOGO`), `PROVEEDOR_CREAR`, `PROVEEDOR_MODIFICAR` (`GESTIONAR_PROVEEDORES`) y `COSTO_INFORMAR` (`EDITAR_COSTOS`). Cualquier usuario con sesión puede ejecutarlos por el lote: por ejemplo, darle a su propio rol todos los permisos o definir el PIN de un supervisor y autorizarse sus propios descuentos. Los otros 44 sí lo exigen, cada módulo con su propia copia de `_exigir_permiso`.

Además, `USUARIO_CREAR` lleva la contraseña en claro dentro del contenido: entra a la huella (recuperable por fuerza bruta si es débil, porque el resto del contenido es conocido), al contenido de `comando_cuarentena` si el dispositivo está revocado y al `input` de un 422. `PIN_AUTORIZACION_ROTAR` tenía el mismo problema con el PIN (lo corrige ADR-055). No hay otros secretos en contenidos de comandos: no existe comando de cambio de contraseña, el PIN de desbloqueo vive solo en el dispositivo y la importación no transporta credenciales.

## Decisión (opción A, confirmada por el usuario el 2026-10-22)

1. **Cada tipo declara su permiso.** `declarar_tipo` exige `permisos`, una tupla no vacía con semántica "alguno de", que reemplaza a `permiso_offline` y sirve para los dos modos. Falla al importar si falta. La única excepción es `sin_permiso="<justificación>"`, explícita y en una lista revisada por un ratchet; hoy ningún tipo la usa.
2. **El bus exige el permiso en todo camino.** `procesar_comando` hace el paso 4 de `02` §6.3 para todo sobre, venga por REST o por el lote: en `ONLINE`, sin ninguno de los permisos declarados (usuario o rol inactivo = sin permisos, ADR-028), `PERMISO_REQUERIDO` (403) antes del handler, sin fila de `comando` ni efecto; en `OFFLINE`, `PERMISO_REVOCADO` sin rechazar, como hasta ahora (SYN-05, SYN-10). Se quita el parámetro `verificar_permiso`.
3. **La ruta conserva su control** previo a la base, y debe coincidir con el catálogo (ratchet). Los controles propios de los handlers se conservan; los permisos condicionales (`PERMITIR_STOCK_NEGATIVO`, `LIBERAR_UBICACION`, `VER_COSTOS`, etc.) siguen en el handler.
4. **Secretos fuera del contenido y fuera del lote.** Un tipo que siempre recibe un secreto se declara con `exige_credenciales_efimeras` (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`): su ruta separa el secreto del cuerpo antes de armar el contenido y la huella y lo entrega al handler por clausura como `SecretStr` (ADR-055, D2). El lote rechaza esos tipos en cualquier modo, antes de reservar (`MODO_NO_ADMITIDO_PARA_TIPO`, 422, confirmado), y desde un dispositivo revocado los responde `DISPOSITIVO_REVOCADO` sin guardarlos en cuarentena.
5. **`USUARIO_CREAR` sin contraseña en el contenido**, con `extra="forbid"`: un contenido con `password` es malformado.
6. **Ratchets.** Todo tipo declarado tiene permisos o una excepción justificada; permiso de la ruta igual al del catálogo; para cada tipo `ONLINE`, un usuario sin el permiso que lo envía por el lote recibe `PERMISO_REQUERIDO`; ningún esquema de contenido declara un campo `SecretStr` ni de nombre `password`, `password_actual`, `contrasena`, `pin` o `secreto`.

**Ejemplo.** Pedro, Vendedor, envía por el lote `ROL_PERMISOS_CAMBIAR` en `ONLINE` para sumar `AUTORIZAR_DESCUENTO` a su rol: antes se aceptaba; ahora recibe `PERMISO_REQUERIDO` y el rol no cambia. Un Administrador que envía `USUARIO_CREAR` por el lote recibe `MODO_NO_ADMITIDO_PARA_TIPO`; por la ruta, el usuario se crea y la contraseña no queda en la huella ni en ningún registro.

## Consecuencias

- SEG-06 se cumple en un solo lugar para todos los tipos, y un tipo nuevo no puede olvidarse el permiso.
- Un comando sigue dando el mismo resultado por REST y por el lote, salvo los tipos con secretos, que solo entran por su ruta.
- La contraseña del alta y los PIN no quedan en la huella, la cuarentena, la auditoría, el resultado ni los registros.
- Cambian todas las declaraciones de tipos (`permiso_offline` → `permisos`) y las pruebas que despachaban por el lote sin el permiso.
- Los controles de permiso de los handlers quedan redundantes; sacarlos es una limpieza posterior.

## Alternativas consideradas

- **B. A más: el lote solo admite `OFFLINE`** (`02` §6.2: "`ONLINE` en REST; `OFFLINE` solo en sync"). Menos superficie, pero contradice la spec del pipeline, ADR-048 punto 5 y ADR-049 punto 19, cambia unas veinte suites y no agrega seguridad una vez que el bus exige el permiso.
- **C. A más: el lote rechaza los tipos que no admiten `OFFLINE`.** Intermedio, con las mismas contradicciones que B para transferencias y jornadas.
- **D. Agregar el control a los 17 handlers que no lo tienen**, sin declarar nada. Cierra el hueco de hoy, pero el próximo handler puede olvidarlo de nuevo y no hay ratchet posible.

## Precisiones del apply (2026-10-22 y 2026-10-23)

1. **La tabla de tipos coincide con las rutas.** Al implementar (tareas 22.1 y 22.2) se revisaron los 62 tipos declarados (los 61 del borrador más `PIN_AUTORIZACION_PROPIO_DEFINIR`): el permiso de cada uno coincide con el de su ruta, sin diferencias, y la lista de excepciones `sin_permiso` quedó **vacía**. `PIN_AUTORIZACION_PROPIO_DEFINIR` declara los cuatro permisos de autorización de excepciones; `VENTA_CONFIRMAR`, `VENDER`; `COBRANZA_REGISTRAR`, `REGISTRAR_COBRANZA`.
2. **Orden en el lote (aprobado el 2026-10-23).** El permiso del tipo se evalúa **antes** de validar el contenido: en `ONLINE`, quien no tiene el permiso recibe solo `PERMISO_REQUERIDO` y nunca el detalle de la validación; sin conexión un permiso revocado no rechaza (SYN-10) y un contenido inválido sigue siendo un rechazo. El rechazo por contenido tampoco deja fila de `comando`.
3. **El lote conserva un chequeo mínimo para `credenciales`:** `ItemLoteComandoRequest` es `extra="forbid"` y un ítem con `credenciales` dentro del contenido se rechaza como malformado (también con el dispositivo revocado: no va a la cuarentena). Los tipos con `exige_credenciales_efimeras` se rechazan antes de reservar, en `ONLINE` y en `OFFLINE`, y desde un dispositivo revocado se responden `DISPOSITIVO_REVOCADO` sin guardar su contenido; los demás ítems del mismo lote sí van a cuarentena.
4. **`USUARIO_CREAR`** queda con `usuario`, `nombre`, `email` y `rol_id` en el contenido (`extra="forbid"`); la contraseña llega por clausura como `SecretStr` desde `POST /api/v1/identidad/usuarios` y se valida con las reglas existentes sin el valor en el mensaje. Una base de desarrollo con contenido viejo con `password` en una cuarentena se recrea (no hay producción).
5. **Ratchets implementados:** `test_catalogo_tipos_permisos.py` (declaración obligatoria), `test_ratchet_permiso_por_tipo.py` (el permiso de la ruta coincide con el del catálogo, verificado por mutación), `test_bus_permiso_en_todo_camino.py` (parametrizada sobre el catálogo: sin el permiso, `PERMISO_REQUERIDO` y sin efectos; con él, mismo resultado por REST y por el lote; usuario inactivo con token vigente: `PERMISO_REQUERIDO` en `ONLINE` y `PERMISO_REVOCADO` en `OFFLINE`) y `test_ratchet_contenido_sin_secretos.py` (la única excepción explícita es `VENTA_CONFIRMAR`, cuyas credenciales son opcionales y viajan en el cuerpo, no en el contenido).
6. **Las pruebas que despachaban por el lote con un usuario sin el permiso del tipo se corrigieron** (cada cambio de rol lo envía ahora el usuario de ese rol); se anotan en la tarea 22.3.

## Enmiendas que produce (al pasar a *Vigente*)

- **ADR-012 (pipeline):** el paso 4 lo hace el bus con el permiso del catálogo, para todo sobre (sección "Enmienda del change 18b" agregada).
- **ADR-052 punto 8:** `permisos` reemplaza a `permiso_offline` y vale también para `ONLINE` (sección "Enmienda del change 18b" agregada).
- **ADR-019:** el PIN y la contraseña viajan fuera del contenido (sección agregada, junto con la definición de PIN trivial).
- **`02` §6.3 paso 4 y §6.5:** se proponen en `propuesta-docs.md` del change 18b.
