# ADR-040 — La importación es todo o nada: un comando por archivo, savepoints por fila y registro solo de las confirmadas

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-01 |
| Referenciado en | `openspec/changes/10-importacion-inicial/design.md` D1 y D14 y `specs/importacion/registro-de-importaciones`; `01-dominio.md` INV-01, INV-05, INV-06, TR-10; `02-arquitectura.md` §6.5 y §7; `03-modelo-de-datos.md` §13; ADR-012 (pipeline de comandos idempotentes); ADR-022 (auditoría única) |

**Decisiones D1 y D14 (opción A en cada una) aprobadas por el usuario el 2026-10-01. Texto del ADR aprobado por el usuario el 2026-10-01; estado *Vigente*.**

## Contexto

`docs/` no dice si una importación es atómica ni cómo se lleva al bus de comandos: un comando por archivo, uno por fila o uno por lote. La sesión que el bus entrega al handler (`SesionSinCommit`) prohíbe `commit`, `rollback` y `close` (`CLAUDE.md` §4: los handlers no confirman), pero deja pasar `begin_nested()`. El bus guarda solo la huella del contenido de un comando, no el contenido (`03` §13). `03` §13 describe una tabla `importacion` con `filas_ok`, `filas_error` y `errores`, que sugiere un modo parcial.

## Decisión

1. **Un comando por archivo.** `IMPORTACION_REGISTRAR` (v1, `ONLINE`, sin soporte offline, permiso `IMPORTAR_DATOS`) lleva el archivo ya convertido a filas de texto: `{tipo, archivo_nombre, filas: [{fila, valores: {columna: texto}}]}`. La huella es la de las filas, así que el mismo archivo da la misma huella (SYN-02, INV-06).
2. **Todo o nada con informe completo.** El handler escribe cada fila por el `service.py` del módulo dueño dentro de un savepoint (`begin_nested`). Si la fila falla, revierte **solo su savepoint**, anota `{fila, columna, codigo, mensaje}` y sigue con la siguiente. Al terminar, si hubo algún error lanza `IMPORTACION_CON_ERRORES` (422, `extension.errores`, con **todos** los errores) y el bus revierte la transacción entera, incluida la reserva del `operation_id`. Sin errores inserta la fila de `importacion` y el bus confirma. Cumple INV-01 al nivel de archivo.
3. **Los savepoints no son un `commit`.** Un `begin_nested()` dentro del handler no confirma ni libera la transacción del bus; la regla "los handlers no hacen `commit`" sigue entera. El handler no atrapa errores de dominio fuera del savepoint de la fila.
4. **Se corrige reenviando el archivo entero** con otro `Operation-Id`: como un rechazo no deja efectos ni reserva, no hay estados intermedios ni filas a medio cargar.
5. **Registro `importacion`.** Las columnas de `03` §13 más las de operación (`operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at`, `03` §2.3), con FK compuestas a `usuario` y `dispositivo`. Con el punto 2 solo se guardan importaciones **confirmadas**: `estado` = `CONFIRMADA`, `filas_error` = 0, `errores` = `[]` (las columnas quedan listas para un modo parcial futuro). La tabla es de solo inserción (`GRANT SELECT, INSERT` para el usuario de la aplicación, INV-05). Los intentos rechazados quedan en el log de la aplicación y no en la base.
6. **Reintentos transitorios.** Si el bus reintenta el comando por un error transitorio, re-ejecuta la importación entera; la atomicidad impide efectos duplicados.

## Consecuencias

- Un archivo es una operación. Una fila mala de 2.000 obliga a reenviar todo, lo que es barato porque no hubo efectos.
- La transacción es larga y toma bloqueos por fila; el límite de 2.000 filas (ADR-041) y el orden de bloqueo estable de la puesta en marcha (`02` §7.3) lo acotan. El costo de los savepoints se midió con 2.000 filas de proveedores (`verificacion.md`).
- No hay "importación a medias" que reconciliar; el historial solo muestra lo que existe.
- Quien quiera un modo parcial deberá registrar un ADR nuevo: cambia el significado de `estado` y de `filas_error`.

## Alternativas consideradas

- **Parcial (confirmar las filas buenas):** descartada: deja la organización a medio cargar, y reenviar todo duplica o choca con duplicados; obliga a armar archivos con solo las filas corregidas.
- **Un comando por fila desde el navegador:** descartada: contradice "la importación corre en el servidor" (`04` §6), no tiene registro de importación y deja la lectura y el informe en el cliente.
- **Guardar también los intentos rechazados en una transacción aparte (como la cuarentena):** descartada para este change: agrega una escritura fuera del bus y un estado `RECHAZADA` sin un caso de uso que lo pida; reconsiderable con un ADR si la auditoría lo exige.
