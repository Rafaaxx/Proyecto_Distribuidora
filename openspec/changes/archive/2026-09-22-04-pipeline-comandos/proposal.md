## Qué resuelve este change

Construye el pipeline único de escritura de ADR-012: el sobre del comando, la huella canónica, la reserva de idempotencia, la transacción del bus con reintentos transitorios, `POST /sync/comandos`, la cuarentena y las observaciones. Cierra INV-06.

## Why

Es el último change del Hito 1 y el que hace cumplir la regla que gobierna todo lo que sigue: **después del 04, ninguna escritura se implementa fuera del bus** (`04` §5). Los changes 05..27 escriben sobre este pipeline; si nace incompleto, el riesgo de `04` §14 se materializa en el 18a, cuando ya hay veinte endpoints construidos encima. Además, el change 03 dejó tres escrituras de maestros fuera del bus (su D6) porque el bus no existía: este change es el único momento en que esa deuda se puede saldar sin que se multiplique.

## What Changes

- **Tablas** de `03` §13: `comando` con `UNIQUE (organizacion_id, operation_id)` (INV-06), `comando_cuarentena` y `observacion` con su índice parcial de pendientes.
- **Sobre del comando** (`02` §6.2): `operation_id`, tipo, versión, modo, organización/usuario/dispositivo del token, jornada, `occurred_at`, secuencia, `app_version`, contenido y huella. La huella la calcula el servidor sobre JSON canónico; nunca se confía en la del cliente (SYN-01).
- **Bus** (`02` §6.3): verificación de dispositivo → reserva de idempotencia con `INSERT … ON CONFLICT DO NOTHING` → validación estructural por tipo y versión → permisos → handler → resultado → auditoría → commit. Los handlers no hacen commit.
- **Idempotencia** (SYN-02, INV-06): misma huella devuelve el resultado guardado; huella distinta rechaza con `COMANDO_INCONSISTENTE`; un fallo ONLINE revierte también la reserva.
- **Reintentos transitorios**: `40001` y `40P01` hasta 3 veces con espera incremental, reintentando la transacción completa.
- **Entrada REST** (`02` §6.1): dependencia que exige el encabezado `Operation-Id` en toda escritura y arma el sobre en modo `ONLINE`.
- **`POST /api/v1/sync/comandos`** (`02` §6.4): hasta 50 comandos ordenados por secuencia, un resultado por comando, un error transitorio corta el lote (SYN-03); la cola es del usuario autenticado en ese dispositivo.
- **Cuarentena** (SYN-06): un comando de dispositivo revocado se guarda en transacción aparte y se responde RECHAZADO; no se pierde.
- **Observaciones** (SYN-04, SYN-07): el bus persiste las observaciones que devuelve un handler y el resultado pasa a `ACEPTADO_CON_OBSERVACIONES`. La bandeja y la resolución son del change 25.
- **Compatibilidad de versiones** (`02` §6.6): registro de handlers por tipo **y** versión, y publicación de la versión mínima de aplicación.
- **Deuda del change 03 saldada**: alta de usuario, revocación de dispositivo y rotación de PIN pasan a ser comandos (`USUARIO_CREAR`, `DISPOSITIVO_REVOCAR`, `PIN_AUTORIZACION_ROTAR`), envolviendo `identidad/service.py` sin reescribirlo; `auditoria.operation_id` deja de ser opcional para los eventos originados en un comando — ver B2.
- **Logging de contexto de comando** (`02` §17): `operation_id`, organización, usuario y dispositivo dejan de estar vacíos; se agregan las métricas de comando.

## Bloqueantes (decisiones que `docs/` no resuelve)

- **B1 — Serialización canónica de la huella.** `02` §6.2 fija dos propiedades (claves ordenadas, decimales como string) de las seis que hace falta congelar (separadores, escape Unicode, ausente vs. nulo, orden dentro de arreglos, normalización de texto). Es un contrato de cable compartido con el cliente TypeScript y **irreversible**: cambiarlo invalida la idempotencia de los comandos ya encolados en dispositivos. **Requiere ADR** (extensión de ADR-012). Ver `design.md` D1.
- **B2 — `auditoria.operation_id` obligatorio frente a los eventos sin comando.** AUD-02 lo pide en cada registro, pero el inicio de sesión no tiene ni puede tener `operation_id` (change 03, D6). Hay que decidir cómo se expresa la obligatoriedad sin inventar identificadores falsos. **Requiere confirmación humana** y queda como extensión de ADR-012 o nota en AUD. Ver `design.md` D2.

## No incluye

- Bandeja de observaciones, resolución con comentario y `OBSERVACION_RESOLVER`: change 25 (SYN-08).
- Revisión de la cuarentena (endpoint, permiso y política de reenvío): no hay permiso para ello en `01` §19 y ninguna regla dice si un comando en cuarentena puede reenviarse. Acá solo se persiste. Ver `design.md` D6.
- Modo `OFFLINE` ejercido de punta a punta: exige jornada abierta (change 15) y comandos de venta/cobranza (changes 17, 18a). El modo existe en el sobre y se rechaza mientras ningún handler lo declare.
- Cola local, bootstrap y motor de sincronización del dispositivo: changes 21, 22a y 22b.
- Los demás tipos de comando de `02` §6.5: cada uno llega con su change.

## Invariantes

- **INV-06**: `UNIQUE (organizacion_id, operation_id)` más pruebas de concurrencia con commits reales (dos envíos simultáneos del mismo `operation_id` producen un solo efecto).
- **INV-02**: las tres tablas nuevas llevan `organizacion_id` y unicidad compuesta; pasan la verificación estructural del change 02 sin exenciones.
- **INV-05**: `comando`, `comando_cuarentena` y `observacion` reciben sus `GRANT` explícitos según ADR-020; ninguna admite `DELETE`.
- **INV-21**: las rutas nuevas se declaran en el ratchet del change 02 con su prueba de acceso ajeno → 404.

## Capabilities

### New Capabilities
- `sistema/pipeline-de-comandos`: sobre, huella, reserva de idempotencia, transacción del bus, reintentos, resultados, registro de handlers por tipo y versión (ADR-012, `02` §6, SYN-01, SYN-02, SYN-04, INV-06).
- `sync/lote-de-comandos`: `POST /sync/comandos`, orden por secuencia, corte del lote ante error transitorio, propiedad de la cola (SYN-03, SYN-09, `02` §6.4).
- `sync/cuarentena-de-comandos`: qué se guarda de un comando de dispositivo revocado y por qué no se pierde (SYN-06).
- `sync/observaciones`: cómo nace una observación, qué guarda y qué estado deja en el comando (SYN-04, SYN-07).

### Modified Capabilities
- `sistema/logging-estructurado`: los campos `operation_id`, organización, usuario y dispositivo dejan de estar previstos y pasan a poblarse; se agregan métricas por comando (`02` §17).
- `sistema/salud-y-version`: el servidor publica la versión mínima de aplicación (`02` §6.6).
- `auditoria/registro-de-auditoria`: todo registro originado en un comando lleva su `operation_id`, exigido por la base (B2).
- `identidad/usuarios-y-roles`: el alta de usuario se ejecuta como comando idempotente del bus.
- `identidad/dispositivos`: la revocación de dispositivo se ejecuta como comando idempotente del bus.
- `identidad/pin-de-autorizacion`: la rotación de PIN se ejecuta como comando idempotente del bus.

## Impact

- Código nuevo: `backend/app/commands/` (sobre, huella, bus, registro, idempotencia, reintentos), `backend/app/modules/sync/` (api, schemas, models, repository, service), una revisión de Alembic, y los tres handlers de maestros que envuelven `identidad/service.py`.
- Contrato: `POST /sync/comandos` y el encabezado `Operation-Id` entran al OpenAPI; los tipos del frontend se regeneran (`02` §11). El cliente de administración pasa a generar un `operation_id` por escritura.
- Límites entre módulos: `sync` depende de todos los módulos con comandos (`02` §5.3); hay que declararlo en `import_linter`.
- Deuda heredada del change 03 que este change **no** salda y que se re-nomina explícitamente: la fixture `_limpiar_datos_confirmados` de `test_auth_api.py` produce un teardown intermitente al correr aislada. Es del arnés compartido (`conftest.py`), no del pipeline; ver tarea 0.3.
- Este change no toca precios, descuentos ni costos: no agrega ni modifica fixtures compartidos de cálculo.
