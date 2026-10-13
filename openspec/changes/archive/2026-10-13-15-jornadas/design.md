# Diseño técnico — 15-jornadas

> **Estado: D0 a D22 APROBADAS el 2026-10-09 (opción A en todas; D1 como variante de A, ver D1).** El usuario las revisó de a una (tarea 0.1), incluidas con aprobación explícita las críticas (D8, D17, D18, D19) y las altas (D12, D15, D22). Cada decisión conserva su contexto, las opciones consideradas y la elegida; proposal, specs y tareas están escritos con lo aprobado.
>
> Todo se documenta en **ADR-049** (estado *Propuesto* durante el apply, último lote; incluye la convención de archivos propios por área dentro de un módulo grande, D1). Enmendaría `02` §7.3 (dónde entran la toma y la jornada), ADR-022 y ADR-048 punto 23 (un cuarto comando lleva motivo a la auditoría, y la fila del bus gana una observación), ADR-039 punto 7 (la FK de `jornada_id`) y precisa ADR-028 (D9.3-B) y ADR-038 (punto 4 y consecuencias).
>
> **Gobernanza por dominio.** **CRÍTICO** (análisis y aprobación explícita antes de escribir; lote con revisión propia): **D8** (auditoría), **D18 y D19** (sesión y renovación, ADR-028) y la parte de sesión de **D17**. **ALTO** (se propone y se espera revisión): **D12** (bus), **D15** (quién lee, permisos) y la parte del bus de **D17** y **D22**. El resto es **MEDIO** (stock). Aprobadas las decisiones, el código se escribe por lotes y con la revisión explícita que pide cada pieza crítica o alta.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Ubicaciones** (change 09, ADR-038): `ubicacion.requiere_toma` con `CHECK (tipo <> 'VEHICULO' OR requiere_toma)`. Es solo un indicador guardado: nadie lo valida. `UBICACION_MODIFICAR` (`PUT`, reemplazo completo) toma la ubicación `FOR UPDATE` y rechaza desactivar con stock (`UBICACION_CON_STOCK`).
- **Única puerta del libro** `stock/service.py::registrar_movimientos` (ADR-039, ADR-048): toma las ubicaciones `FOR SHARE` (y exige que estén activas), los productos `FOR SHARE`, `costo_producto` y `stock_saldo`, y aplica las líneas. Recibe `usuario_id`, `dispositivo_id`, `operation_id`, `occurred_at` y `permitir_negativo` (el permiso lo resuelve el handler y lo pasa como dato). `LineaDeMovimiento.jornada_id` existe y **nadie lo llena**. La llaman `stock` (stock inicial, transferencia, ajuste y sus anulaciones), `proveedores/service.py` (compra y anulación de compra) e `importacion` (stock inicial, por `registrar_stock_inicial`).
- **Columnas sin FK:** `stock_movimiento.jornada_id` (ADR-039 punto 7) y `comando.jornada_id` (D8 del change 04). `SobreComando.jornada_id` ya viaja desde el lote hasta `repository.reservar_comando`; los endpoints REST no lo envían.
- **Bus** (`sync/service.py`): `procesar_comando` reserva, ejecuta y audita con **una** fila (ADR-022). Los handlers devuelven de 3 a 5 elementos; el quinto es `DatosDeAuditoria(motivo_id)` y un ratchet fija que **solo** tres comandos lo devuelven (ADR-048 punto 23). `identidad_service.registrar_auditoria` ya acepta `observacion` y el bus no la llena.
- **Permisos por comando:** en REST los comprueba la dependencia de la ruta (`requiere_comando_online`) y, otra vez, cada handler de `stock` (`_exigir_permiso`). El catálogo de tipos (`app/commands/catalogo.py`) declara solo `admite_online` y `admite_offline`, **no** el permiso. `POST /sync/comandos` no comprueba ninguno y `_procesar_item_de_lote` invoca `funcion(sobre, contenido)` sin `sesion` ni `reloj`, así que ningún handler real funciona por el lote (deuda nominada al 17). **Ningún tipo declarado admite `OFFLINE`.**
- **Sesión** (ADR-028, change 06b): `renovar_sesion` rechaza y revoca al usuario o rol inactivo; el comentario del código dice que la excepción D9.3-B espera a las jornadas. Toda ruta menos el lote llama a `exigir_sesion_habilitada`.
- **Catálogos:** los permisos `ABRIR_JORNADA` (ADM, SUP, VEN), `RENDIR_JORNADA` (ADM, GES, SUP) y `LIBERAR_UBICACION` (ADM, SUP) ya están en el catálogo y en las plantillas. El ámbito de motivo `LIBERACION_JORNADA` está en `ck_motivo__ambito` y en `AMBITOS_MOTIVO`, pero **no hay ningún motivo sembrado**. Los códigos `JORNADA_LIBERADA` y `PERMISO_REVOCADO` están en el catálogo de observaciones y nada los emite.
- **Frontend:** `/admin` con la sección Stock (TanStack Query); `/ruta` es una pantalla vacía hasta el change 21.
- **`jornada` no existe:** ni tabla, ni modelo, ni comandos.

Lo que `docs/` **no** resuelve (cada punto es una decisión abierta):

- `04` §8 pone "cierre" en el 15 y también en el 24; `01` §18 solo llega a `CERRADA` pasando por `EN_RENDICION`, y la rendición (conteo, RUT-05 a RUT-07) es del 24. → D2.
- RUT-01 e INV-16 hablan de "una ubicación que requiere toma"; el índice de `03` §9 es sobre **toda** ubicación. No dice si se abre jornada en un depósito, ni cuántas jornadas puede tener un usuario o un dispositivo. → D3.
- RUT-02 ("antes o durante la apertura") no dice si la carga viaja dentro de `JORNADA_ABRIR`. → D4. RUT-03 pide ejecutar el bootstrap, que es del 21. → D5.
- STK-09 no define "tomada" para una ubicación con toma y sin jornada, ni cómo se reconoce "la jornada que la tomó" en un comando online (ADR-005 dice "el dispositivo", STK-09 "la jornada"), ni qué pasa en `EN_RENDICION`, ni qué significa "con auditoría". → D6, D7, D8.
- `02` §7.3 pone `jornada` como último nivel de bloqueo y no dice con qué se serializa la apertura. → D9.
- `03` §9 lista `jornada` sin columnas de operación, sin quién rindió o cerró y sin restricciones de coherencia; no existe una tabla de toma. → D10.
- Ningún documento dice qué hace el bus con un `jornada_id` inexistente. → D12.
- RUT-09 pide motivo; no hay motivos sembrados. → D13. ADR-038 no contempla desactivar una ubicación tomada. → D14. `01` §19 no dice quién lee jornadas. → D15.
- ADR-028 dejó escrito: "queda por definir en el change 15 si una jornada `LIBERADA` sigue habilitando la entrega de su cola". → D18.
- `02` §6.3 paso 4 habla de "los permisos vigentes al abrir la jornada" y ninguna tabla los guarda. → D20.

## Goals / Non-Goals

**Goals:** la jornada como entidad con su máquina de estados y su auditoría; INV-16 garantizado por la base y probado con commits reales; STK-09 aplicado en un solo lugar y a todos los caminos que mueven stock; las dos FK heredadas; la excepción de renovación de ADR-028; cero regresiones en stock inicial, compras, importación, transferencias y ajustes sobre ubicaciones sin toma.

**Non-Goals:** bootstrap (21); conteo, diferencias, resumen y remanente (24); venta y cobranza (17, 18a); permisos por comando en el lote y `PERMISO_REVOCADO` (D17); emitir `JORNADA_LIBERADA` (D21); la firma tipada de los handlers (D22); pantallas de `/ruta`; guardar una foto del stock al abrir (se reconstruye del libro a `abierta_en`, INV-12; lo usará RUT-07 en el 24); baja de usuarios y roles.

## Decisions

### D0 — Tamaño del change y lotes · técnica

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** `04` §2 pide entre medio día y tres días. El alcance suma una tabla, cuatro comandos, STK-09 en la puerta (que toca tres módulos), un cambio en el bus, uno en la sesión, tres lecturas y pantallas. No entra en tres días. El 14 fue una excepción aceptada con cuatro lotes.

- **A (recomendada). Un change en cuatro lotes, con revisión del usuario entre cada uno:**
  1. **Lote 1:** migración (tabla, FK, motivos), modelos, dominio, `JORNADA_ABRIR` de punta a punta y el bus ante una jornada inexistente (D12, ALTO).
  2. **Lote 2:** `JORNADA_RENDIR`, `JORNADA_CERRAR`, `JORNADA_LIBERAR` con su auditoría (D8, CRÍTICO), STK-09 en la puerta y en todos los caminos, ubicación tomada, lecturas y ratchets.
  3. **Lote 3 (CRÍTICO, solo sesión):** excepción de renovación de ADR-028 (D17 a D19). Es autocontenido: si los lotes 1 y 2 se alargan, se corta a un `15b` sin rehacer nada.
  4. **Lote 4:** pantallas, concurrencia, propiedades, cobertura, ADR-049, propuesta de docs y verificación manual.
  Consecuencia: vuelve a superar `04` §2 y se anota la excepción.
- **B. Dividir en `15a-jornadas` (lotes 1, 2 y 4) y `15b-sesion-con-jornada` (lote 3).** El 15a queda más cerca del tope y la pieza crítica se revisa sola, con su propio archivo. Consecuencia: dos proposals, dos ADR o uno compartido, y `04` §4 suma una fila; el 18a no depende del 15b.
- **C. Dividir en `15a` (backend) y `15b` (pantallas).** Consecuencia: el 15a se archiva sin flujo probado en el navegador (`04` §2.1 punto 5) y la liberación por un supervisor solo existiría por API.

**Ejemplo.** Al cerrar el lote 1, un Vendedor abre por API una jornada sobre "Camioneta 1" y un segundo intento responde `UBICACION_TOMADA`. Al cerrar el lote 2, otro Vendedor ya no puede transferir a esa camioneta.

### D1 — Dónde vive el código de jornadas · técnica · ADR-049

> **APROBADA el 2026-10-09: variante de A.** Dentro del módulo `stock`, con archivos propios para la lógica, el acceso a datos y los handlers de jornadas.

**Contexto.** `02` §5.1 asigna jornadas y rendición al módulo `stock`. `stock` ya es el módulo más grande del backend (6.345 líneas: `service.py` 1.347, `repository.py` 1.145, `commands.py` 616). `CLAUDE.md` §7 describe un archivo por rol (`commands.py`, `repository.py`, `service.py`); seguirlo al pie de la letra volcaría toda la jornada en esos tres archivos.

- **A. Dentro de `stock`, un archivo por rol**, como dice `02` §5.1 y `CLAUDE.md` §7: `stock/domain/jornadas.py`, funciones en `stock/service.py`, handlers en `stock/commands.py`, rutas bajo `/api/v1/stock/jornadas`. La puerta del libro consulta la jornada sin cruzar módulos. Consecuencia: `service.py`, `repository.py` y `commands.py` siguen creciendo con una segunda responsabilidad mezclada con los movimientos; no hay contrato nuevo de import-linter.
- **B. Módulo nuevo `jornadas`.** Consecuencia: `jornadas` necesita las ubicaciones de `stock` y la puerta de `stock` necesita la jornada: un ciclo que obliga a un puerto de registro y a enmendar `02` §5.1 y §5.3.
- **Aprobada: variante de A, con archivos propios dentro de `stock`.** Sigue siendo el módulo `stock` (sin módulo nuevo, sin ciclo, sin contrato de import-linter entre módulos), pero lo de jornadas vive en archivos propios, separados de los de movimientos:
  - `stock/domain/jornadas.py`: máquina de estados y decisión de toma, puro (la carpeta `domain/` ya separa por tema).
  - `stock/jornadas_repository.py`: acceso a datos de `jornada` (insertar, bloquear, leer la jornada no cerrada de una ubicación, listar).
  - `stock/jornadas_casos.py`: los casos de uso de escritura y de consulta pública (`abrir`, `rendir`, `cerrar`, `liberar`, `existe`, `tiene_jornada_no_cerrada`). Usa solo `jornadas_repository` y `domain/jornadas.py`; nunca importa `service.py` (para que `service.py` pueda importarlo sin ciclo).
  - `stock/jornadas_commands.py`: los cuatro handlers `JORNADA_*` y la declaración de sus tipos.
  - `stock/service.py` **sigue siendo la única puerta pública** del módulo: expone las funciones de jornada que otros módulos necesitan (`existe_jornada` para el bus, `tiene_jornada_no_cerrada` para `identidad`, y las de apertura, rendición, cierre y liberación para sus handlers y la ruta), delegando en `jornadas_casos.py` sin contener su implementación. La parte de STK-09 que vive dentro de `registrar_movimientos` se queda en `service.py` (es la puerta del libro) y consulta la jornada con `jornadas_repository`.
  - Rutas, esquemas y consultas de lectura de jornadas **se quedan por ahora en `stock/api.py`, `stock/schemas.py` y `stock/queries.py`** (lectura más conservadora: se separan solo la lógica, el acceso a datos y los handlers). El modelo `Jornada` va en `stock/models.py`.
  - Los archivos de movimientos existentes **no se parten ni se refactorizan** en este change.
  - Los tres archivos nuevos se suman a los contratos de import-linter que impiden que otros módulos alcancen `stock` por dentro, y `main.py` importa `jornadas_commands` para registrar los tipos.
  Por qué: el módulo no se parte (el ciclo con la puerta del libro lo impide), pero tampoco se agranda más de lo necesario; cada área se lee y se prueba por separado. Esto se aparta de la disposición de un archivo por rol de `CLAUDE.md` §7, así que **ADR-049 lo registra como convención para módulos grandes** (archivos propios por área, prefijados con el nombre del área, con `service.py` como única puerta) y **el change 24 (rendición) debe seguirla** para su código dentro de `stock`.

**Ejemplo.** `registrar_movimientos` (en `service.py`) pregunta por la jornada no cerrada de "Camioneta 1" con `jornadas_repository`, dentro de su propio orden de bloqueo; el bus pregunta por una jornada solo con `stock_service.existe_jornada`, que delega en `jornadas_casos.py`.

### D2 — Qué cierre entrega el 15, sin rendición · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** `04` §8 pide en el 15 "cierre" y en el 24 "conteo físico, diferencias, resumen, remanente, cierre". `01` §18 solo admite `ABIERTA → EN_RENDICION → CERRADA`. Hasta que llegue el 24, las jornadas cerradas no tendrán conteo; serán solo datos de desarrollo y de prueba mientras se construye el roadmap (el usuario presentará el sistema completo funcionando).

- **A (recomendada). `JORNADA_RENDIR` sin conteo y `JORNADA_CERRAR`.** `JORNADA_RENDIR` v1 (`RENDIR_JORNADA`) pasa `ABIERTA → EN_RENDICION` y guarda `rendida_en`; no registra conteo ni diferencias. `JORNADA_CERRAR` (`RENDIR_JORNADA`) pasa `EN_RENDICION → CERRADA` y libera la ubicación (RUT-08). `01` §18 queda sin enmienda. El 24 agrega el conteo como una versión nueva de `JORNADA_RENDIR` y las tablas `rendicion`. Consecuencias: quedan jornadas `CERRADA` con `rendida_en` y sin fila de `rendicion` (las anteriores al 24, solo datos de desarrollo y de prueba), y cerrar son dos pasos. RUT-05 (cola vacía) no se puede comprobar en el servidor y queda para el 24.
- **B. Cierre directo `ABIERTA → CERRADA`** con `JORNADA_CERRAR`, sin `JORNADA_RENDIR`, hasta el 24. Consecuencia: enmienda `01` §18 con una transición que el 24 tendría que retirar o conservar; un paso en lugar de dos.
- **C. Sin cierre en el 15.** La única salida es `JORNADA_LIBERAR`. Consecuencia: contradice la fila del 15 en `04` §8, y cada jornada normal terminaría como "liberación forzada" con motivo, lo que vacía de sentido la auditoría de RUT-09.

**Ejemplo (A).** A las 18:00 la Supervisora marca "Rendir" sobre la jornada de "Camioneta 1" (queda `EN_RENDICION`, la camioneta sigue tomada) y después "Cerrar" (queda `CERRADA`, la camioneta libre). Con B sería un solo botón "Cerrar".

### D3 — Dónde se abre una jornada y cuántas a la vez · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** RUT-01 e INV-16 limitan a una jornada no cerrada la ubicación "que requiere toma". El índice de `03` §9 alcanza a toda ubicación. `03` §12 dice que `venta.jornada_id` es "nulo en ventas desde PC". RUT-04 habla de "la ubicación tomada" del dispositivo, en singular. Ninguna regla limita las jornadas por usuario o por dispositivo.

- **A (recomendada). Solo sobre ubicaciones activas con `requiere_toma`, y a lo sumo una jornada no cerrada por dispositivo y una por usuario.** Abrir sobre una ubicación sin toma responde `UBICACION_SIN_TOMA` (409); inactiva, `UBICACION_INACTIVA`; tomada, `UBICACION_TOMADA`; el dispositivo o el usuario ya con jornada, `DISPOSITIVO_CON_JORNADA` o `USUARIO_CON_JORNADA` (409). Tres índices únicos parciales (ubicación, dispositivo, usuario) sobre `estado IN ('ABIERTA','EN_RENDICION')`. La jornada es del usuario y del dispositivo del token: nadie abre para otro. Consecuencia: el índice de `03` §9 queda como está (equivale a INV-16 porque no hay jornadas sobre ubicaciones sin toma); la venta de depósito sigue sin jornada.
- **B. Igual que A, sin el límite por usuario.** Un usuario con dos teléfonos podría tener dos vehículos tomados. Consecuencia: la excepción de renovación de ADR-028 ("ese dispositivo… de ese usuario") sigue funcionando, pero la rendición por vendedor del 26 tendría dos jornadas simultáneas del mismo vendedor.
- **C. Jornadas sobre cualquier ubicación**, exclusivas solo donde hay toma. Consecuencia: el índice necesita el indicador de toma desnormalizado en `jornada` y enmienda `03` §9; abre el "mostrador con jornada", que ningún documento pide.

**Ejemplo (A).** Juan abre sobre "Camioneta 1" desde su teléfono V03. Si intenta abrir "Camioneta 2" recibe `USUARIO_CON_JORNADA`; si Pedro inicia sesión en ese mismo teléfono e intenta abrir "Camioneta 2", `DISPOSITIVO_CON_JORNADA`; abrir sobre "Depósito central" responde `UBICACION_SIN_TOMA`.

### D4 — Carga del vehículo (RUT-02) · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).** Salda la deuda (2) del change 14.

**Contexto.** RUT-02: "transferencia desde depósito, con conexión, antes o durante la apertura". ADR-048 nominó: "reutiliza `STOCK_TRANSFERIR`".

- **A (recomendada). La carga es siempre un `STOCK_TRANSFERIR` aparte.** Antes de abrir, la camioneta no está tomada y cualquiera con `TRANSFERIR_STOCK` la carga (D6). Con la jornada abierta, la carga la hace el vendedor de la jornada desde su dispositivo, o alguien con `LIBERAR_UBICACION`. `JORNADA_ABRIR` no lleva líneas. La pantalla de la jornada ofrece "Cargar vehículo", que abre el alta de transferencia con el destino precargado. Consecuencia: abrir y cargar son dos operaciones; un encargado de depósito sin `LIBERAR_UBICACION` (plantilla Administración) no puede cargar una camioneta ya tomada.
- **B. `JORNADA_ABRIR` admite líneas de carga** y las transfiere en la misma transacción. Consecuencia: apertura atómica con su carga, pero un comando con dos responsabilidades, dos permisos (`ABRIR_JORNADA` y `TRANSFERIR_STOCK`) y una transferencia que no nace de `STOCK_TRANSFERIR`.

**Ejemplo (A).** 7:30, el encargado transfiere 48 de Vino A del depósito a "Camioneta 1" (libre). 8:00, Juan abre la jornada. 11:00, Juan vuelve al depósito y él mismo, desde su teléfono, transfiere 24 más.

### D5 — Bootstrap en la apertura (RUT-03) · técnica

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** RUT-03: la apertura "toma la ubicación y ejecuta el bootstrap". `GET /api/v1/sync/bootstrap` es del change 21 (`04` §11), que depende del 20.

- **A (recomendada). El 15 no ejecuta bootstrap.** `JORNADA_ABRIR` toma la ubicación y devuelve la jornada; el 21 encadena el bootstrap después de abrir. Consecuencia: RUT-03 queda cumplida a medias hasta el 21 y se anota como deuda nominada.
- **B. Un bootstrap mínimo ya** (stock de la ubicación tomada y permisos). Consecuencia: adelanta un contrato que el 21 va a rehacer con Dexie, sin consumidor.

**Ejemplo.** La respuesta de `JORNADA_ABRIR` trae el id de la jornada, la ubicación y `abierta_en`; el stock de la camioneta se sigue leyendo con `GET /stock/ubicaciones/{id}/saldos`.

### D6 — Alcance de STK-09: qué es "tomada" y quién es "la jornada" · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).** Salda la deuda del 09 y la deuda (1) del 14.

**Contexto.** STK-09: "Mientras una ubicación está tomada, solo la jornada que la tomó puede generar movimientos sobre ella, salvo la rendición y usuarios con `LIBERAR_UBICACION`, con auditoría." ADR-005 dice "solo el dispositivo que la tomó". `02` §6.4: la cola es del usuario autenticado en ese dispositivo.

- **A (recomendada). Literal y por usuario más dispositivo.**
  1. Una ubicación está **tomada** mientras tiene una jornada `ABIERTA` o `EN_RENDICION`. Una ubicación con `requiere_toma` y **sin** jornada se mueve libremente (lo exige RUT-02 "antes de la apertura", el stock inicial y el remanente después del cierre).
  2. Un movimiento es **de la jornada** si la jornada está `ABIERTA` y el usuario **y** el dispositivo del comando son los de la jornada. El servidor lo deduce del token: los comandos de stock no envían `jornada_id`. Si el sobre trae uno (lote), tiene que ser el de esa jornada. El movimiento se guarda con `stock_movimiento.jornada_id`.
  3. **Excepción:** quien tiene `LIBERAR_UBICACION` mueve una ubicación tomada, en cualquier estado de la jornada; el movimiento queda sin `jornada_id` y señalado en la auditoría (D8).
  4. En `EN_RENDICION` la propia jornada ya no mueve stock: solo la excepción (y, desde el 24, la rendición).
  5. Cualquier otro caso responde `UBICACION_TOMADA` (409) y no escribe nada. Los permisos propios de cada comando (`TRANSFERIR_STOCK`, `AJUSTAR_STOCK`…) se siguen exigiendo además.
  Consecuencia: si al vendedor se le rompe el teléfono, no opera desde otro hasta que un supervisor libere la jornada (es para lo que existe RUT-09).
- **B. Una ubicación con toma nunca se mueve sin jornada** (salvo `LIBERAR_UBICACION`). Consecuencia: contradice RUT-02 ("antes de la apertura"); el stock inicial, la compra directa al vehículo y la devolución del remanente quedarían reservados a Administrador y Supervisor.
- **C. "La jornada" es el usuario, desde cualquier dispositivo.** Consecuencia: se aparta de ADR-005; cuando exista la cola offline, dos dispositivos del mismo usuario venderían el mismo stock sin verse.

**Ejemplo (A).** "Camioneta 1" tomada por Juan (teléfono V03). Juan transfiere 6 de Vino A a "Depósito central" desde V03: se acepta y la línea de la camioneta guarda su jornada. Pedro (Vendedor) transfiere 6 a "Camioneta 1": `UBICACION_TOMADA`. La Supervisora transfiere 12: se acepta por la excepción. Juan, desde la PC de la oficina: `UBICACION_TOMADA`.

### D7 — Dónde se aplica STK-09 y a qué caminos · técnica · ADR-049

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** Seis caminos mueven stock y todos pasan por `registrar_movimientos`: stock inicial (pantalla e importación), compra, anulación de compra, transferencia, ajuste y las dos anulaciones del 14.

- **A (recomendada). En la única puerta, para todos los caminos.** `registrar_movimientos` suma un parámetro `puede_operar_ubicacion_tomada` (por defecto `False`: falla cerrado), como `permitir_negativo`. Quien llama lo resuelve con `LIBERAR_UBICACION` del usuario: los handlers de `stock`, y `proveedores/service.py` (compra y anulación) e `importacion` (stock inicial), que son tres llamadas. La puerta decide por cada ubicación de las líneas y devuelve qué líneas pasaron por excepción. Consecuencia: toca dos módulos archivados, para pasar el permiso y, si D8 = A, para devolver la constancia de la excepción; ningún camino presente o futuro (venta, rendición) esquiva la regla.
- **B. En la puerta, pero la excepción solo la honran los comandos de `stock`.** Compras e importación sobre una ubicación tomada se rechazan siempre. Consecuencia: no se toca `proveedores` ni `importacion`, pero agrega una restricción de negocio que STK-09 no dice (un Administrador no podría anular una compra cuyo destino hoy está tomado).
- **C. En cada servicio, fuera de la puerta.** Consecuencia: seis validaciones repetidas y la séptima (la venta) depende de que alguien se acuerde; contradice ADR-039 (única puerta).

**Ejemplo (A).** Administración (sin `LIBERAR_UBICACION`) registra una compra con destino "Camioneta 1" tomada: `UBICACION_TOMADA`, sin compra, sin deuda y sin movimiento (INV-01). El Administrador sí puede.

### D8 — Auditoría de la liberación y de la excepción · de negocio · ADR-049 · **CRÍTICO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.** Dominio de auditoría: se escribe solo con el alcance escrito.

**Contexto.** AUD-01 pide auditar la "liberación forzada de ubicaciones"; RUT-09 pide motivo; STK-09 dice "con auditoría" para la excepción. El bus escribe una sola fila por comando (ADR-022) y copia el motivo en exactamente tres comandos (ADR-048 punto 23, con ratchet). `auditoria.observacion` existe y el bus no la llena.

- **A (recomendada). Motivo en la liberación y observación en la excepción, siempre en la única fila del bus.**
  1. `JORNADA_LIBERAR` devuelve `DatosDeAuditoria(motivo_id)`: el ratchet pasa de tres comandos a **cuatro**.
  2. `DatosDeAuditoria` gana un campo opcional `observacion`, que el bus copia a `auditoria.observacion`. Lo devuelven los comandos que movieron una ubicación tomada por excepción (los cinco de stock que mueven mercadería, `COMPRA_CONFIRMAR`, `COMPRA_ANULAR` e `IMPORTACION_REGISTRAR`), con un texto fijo que nombra la regla y la jornada (`STK-09: ubicación tomada por la jornada <id>`). Un segundo ratchet fija qué comandos pueden devolverlo.
  3. Las cuatro transiciones quedan auditadas por la fila del bus (`accion` = tipo del comando).
  Consecuencia: enmienda ADR-022 y ADR-048 punto 23; toca `sync/service.py` y `app/commands/auditoria.py`. Sin migración.
- **B. Solo el motivo de la liberación.** La excepción no deja marca propia: la fila del bus ya dice quién transfirió. Consecuencia: para saber si un movimiento fue por excepción hay que cruzar la fila con la jornada vigente en ese momento; "con auditoría" queda cumplido en sentido débil.
- **C. Una fila de auditoría adicional por cada excepción.** Consecuencia: rompe "una fila por comando" (ADR-022), ya descartado en el 14.

**Ejemplo (A).** La Supervisora libera la jornada de Juan con el motivo "Dispositivo perdido o averiado": una fila `JORNADA_LIBERAR` con ese `motivo_id`. Después transfiere 12 a una camioneta tomada por Pedro: una fila `STOCK_TRANSFERIR` con la observación `STK-09: ubicación tomada por la jornada …`.

### D9 — Orden de bloqueo: la toma y la jornada · técnica · ADR-049

> **APROBADA (opción A, 2026-10-09).** Precisa `02` §7.3.

**Contexto.** `02` §7.3: `saldo_cuenta` → `producto` → `costo_producto` → `stock_saldo` → `jornada`, con las ubicaciones `FOR SHARE` al comienzo del movimiento (ADR-038) y las filas de la propia operación antes del nivel 1. `02` §7.5: la segunda apertura falla por la restricción. No hay fila que bloquear cuando la ubicación todavía no está tomada.

- **A (recomendada). La toma entra por la fila de la ubicación; la jornada queda última.**
  1. **`JORNADA_ABRIR`** toma la **ubicación `FOR UPDATE`** (el paso de ubicaciones que ya existe, antes del nivel 1) e inserta la jornada. Como todo movimiento toma su ubicación `FOR SHARE`, una apertura y un movimiento simultáneos sobre la misma ubicación se esperan: o el movimiento termina antes de la toma, o ve la ubicación tomada. La unicidad la decide el índice (INV-16): la violación se traduce a `UBICACION_TOMADA`, `DISPOSITIVO_CON_JORNADA` o `USUARIO_CON_JORNADA`; no hay verificación previa que la reemplace.
  2. **Todo movimiento** lee la jornada no cerrada de cada una de sus ubicaciones **`FOR SHARE`, como nivel 5**, después de `stock_saldo`, por `ubicacion_id` ascendente, y recién entonces decide (D6) e inserta.
  3. **`JORNADA_RENDIR`, `JORNADA_CERRAR` y `JORNADA_LIBERAR`** toman su jornada `FOR UPDATE`, revalidan el estado y no tocan stock ni saldos: no pueden cerrar un ciclo.
  4. **`UBICACION_MODIFICAR`** ya toma la ubicación `FOR UPDATE`; lee la jornada después (D14).
  Consecuencia: una liberación espera a los movimientos en curso de esa jornada y al revés. **Deuda para el 24:** la rendición va a necesitar la jornada `FOR UPDATE` **y después** stock; tiene que tomarla como "fila de la propia operación" antes del nivel 1 y ese change debe resolver cómo convive con el nivel 5.
- **B. La apertura toma la ubicación `FOR SHARE`.** Consecuencia: un movimiento ajeno que empezó antes puede confirmarse después de la toma; el stock que ve el vendedor al abrir no es el definitivo.
- **C. Bloqueo consultivo por ubicación** (`pg_advisory_xact_lock`). Consecuencia: se aparta de ADR-015, ya descartado en ADR-039.

**Ejemplo (A).** Pedro transfiere a "Camioneta 1" en el mismo instante en que Juan la abre. Si gana Pedro, la transferencia entra y Juan abre con ese stock; si gana Juan, Pedro recibe `UBICACION_TOMADA`. Nunca queda una transferencia de Pedro confirmada después de la apertura.

### D10 — Modelo de datos de `jornada` · técnica · ADR-049

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** `03` §9 lista `id`, `organizacion_id`, `usuario_id`, `dispositivo_id`, `ubicacion_id`, `estado`, cuatro momentos, `liberada_por_id` y `motivo_liberacion_id`, y el índice de INV-16. El glosario define la "toma de ubicación" pero no hay tabla de toma.

- **A (recomendada). `03` §9 más lo que necesitan las reglas; sin tabla de toma.** La toma **es** la fila de `jornada` en `ABIERTA` o `EN_RENDICION` más su índice. Se agregan: `UNIQUE (organizacion_id, id)`; FK compuestas a `usuario`, `dispositivo`, `ubicacion` y `motivo`; `CHECK` de catálogo en `estado`; columnas de operación de la apertura (`operation_id`, `occurred_at`, `registered_at`, `creado_en`); `rendida_por_id`, `cerrada_por_id` y `observacion_liberacion` (hasta 500, D13); `CHECK` de coherencia por estado (los datos de rendición, cierre y liberación presentes si y solo si el estado los implica); los dos índices únicos parciales de D3; índice de listado `(organizacion_id, abierta_en DESC, id DESC)`. `app_runtime`: `SELECT`, `INSERT` y `UPDATE` **solo** de `estado` y de las columnas de transición; sin `DELETE` (INV-05, TR-06).
- **B. `03` §9 al pie de la letra.** Consecuencia: no se sabe quién rindió o cerró salvo por la auditoría, no hay `operation_id` para enlazar la jornada con su comando y nada impide un estado incoherente.
- **C. Tabla `toma_ubicacion` aparte**, con la jornada referenciándola. Consecuencia: dos filas para un mismo hecho y el índice de INV-16 en otra tabla que la que nombra `03` §15.

**Ejemplo.** Una jornada `LIBERADA` tiene `liberada_en`, `liberada_por_id` y `motivo_liberacion_id` no nulos y `cerrada_en` nulo; un `UPDATE` que deje `estado = 'LIBERADA'` sin motivo lo rechaza la base.

### D11 — Las dos FK heredadas y los datos existentes · técnica · ADR-049

> **APROBADA (opción A, 2026-10-09).** Salda las deudas del 04 y del 09.

**Contexto.** `stock_movimiento.jornada_id` y `comando.jornada_id` tienen filas. Ningún código llena la primera; la segunda puede tener valores sueltos de lotes de prueba.

- **A (recomendada). FK compuesta `(organizacion_id, jornada_id)` con `NOT VALID` más `VALIDATE`, y la migración aborta si hay huérfanos.** Antes de crear la restricción, la migración cuenta las filas con `jornada_id` no nulo: si hay alguna, falla con un mensaje que dice cuántas y en qué tabla, sin modificar nada. El conteo se corre antes como consulta de solo lectura y su resultado se informa en el resumen del lote 1. El `downgrade` quita las FK y la tabla (pérdida explícita, aserción en la prueba de ciclo).
- **B. Poner en nulo los huérfanos.** Consecuencia: la migración modifica filas de `comando` y de un libro de solo inserción (`stock_movimiento`), contra TR-06.
- **C. FK solo en `stock_movimiento`; `comando` sin FK y validado en el bus.** Consecuencia: deja sin saldar la deuda del 04, que `04` §8 pide expresamente.

**Ejemplo.** En desarrollo quedó un `comando` de prueba con un `jornada_id` inventado: la migración se detiene y lo informa; el usuario decide qué hacer con esa fila.

### D12 — El bus ante un `jornada_id` inexistente · técnica · ADR-049 · **ALTO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.** Toca el bus: al aplicar, se muestra el cambio y se espera revisión.

**Contexto.** Con la FK, reservar un comando cuyo sobre nombra una jornada inexistente o de otra organización viola la restricción en el `INSERT` de la reserva y hoy terminaría en un error 500. SYN-06 dice que un comando "con dependencias inexistentes" se rechaza.

- **A (recomendada). Validación previa en el bus, con la FK de respaldo.** Antes de reservar, si el sobre trae `jornada_id`, el bus pregunta a `stock/service.py` si existe en la organización (`sync ──► todos los módulos con comandos`, `02` §5.3). Si no, `JORNADA_INEXISTENTE`: en el lote el ítem queda `RECHAZADO` sin fila de `comando` y el lote sigue; en REST responde 404. La FK queda como red. El bus **no** valida que la jornada sea del usuario ni su estado: eso es regla de cada comando de ruta (D21).
- **B. Capturar la violación de la FK** por el nombre de la restricción y traducirla. Consecuencia: la transacción ya quedó abortada, hay que revertir y el código depende del nombre de una restricción.
- **C. Validar solo en los handlers de ruta.** Consecuencia: la reserva ocurre antes que el handler, así que el 500 sigue ahí.

**Ejemplo.** Un lote trae un comando con un `jornada_id` de otra organización: ese ítem responde `RECHAZADO` con `JORNADA_INEXISTENTE` y los demás se procesan.

### D13 — Liberación: motivo, motivos sembrados y observación · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** RUT-09: "puede liberar una jornada abierta con motivo". El ámbito `LIBERACION_JORNADA` existe sin motivos y no hay alta de motivos por pantalla.

- **A (recomendada).** `JORNADA_LIBERAR` exige `LIBERAR_UBICACION` y un `motivo_id` activo del ámbito `LIBERACION_JORNADA` (`MOTIVO_INVALIDO`, 422; ajeno, 404), admite una observación opcional de hasta 500 caracteres y vale sobre `ABIERTA` o `EN_RENDICION` de cualquier usuario, incluida la propia. Se siembran **"Dispositivo perdido o averiado", "Vendedor ausente" y "Otro"**, en la siembra y, de forma idempotente, en las organizaciones que no tengan ninguno de ese ámbito (precedente de ADR-046 y ADR-048). El stock que queda en el vehículo no se toca: una vez libre, cualquiera con `TRANSFERIR_STOCK` lo devuelve.
- **B. Un solo motivo "Otro"** y la explicación en la observación, obligatoria. Consecuencia: los reportes del 26 no agrupan por causa.
- **C. Sin sembrar.** Consecuencia: no se puede liberar ninguna jornada hasta que exista el alta de motivos.

**Ejemplo.** Juan perdió el teléfono con la jornada abierta. La Supervisora libera con "Dispositivo perdido o averiado" y la observación "Lo dejó en un comercio de Godoy Cruz". "Camioneta 1" queda libre.

### D14 — Una ubicación tomada no se desactiva ni cambia de tipo o de toma · de negocio · ADR-049

> **APROBADA (opción A, 2026-10-09).** Precisa ADR-038 punto 4.

**Contexto.** Una camioneta tomada y sin stock se puede desactivar hoy (ADR-038 solo mira el stock), o pasar a `OTRO` sin toma, y la jornada quedaría sobre una ubicación que no admite movimientos o que ya no requiere toma.

- **A (recomendada). `UBICACION_MODIFICAR` rechaza con `UBICACION_TOMADA` (409)** cualquier cambio de `activo`, `tipo` o `requiere_toma` mientras la ubicación tenga una jornada no cerrada. El nombre sí se puede cambiar.
- **B. Solo se rechaza la desactivación.** Consecuencia: se puede quitar la toma con la jornada abierta, y la jornada queda sobre una ubicación de libre acceso.
- **C. Nada.** Consecuencia: la jornada queda colgada y solo se sale liberándola.

**Ejemplo.** "Camioneta 2" vacía y tomada por Pedro: desactivarla responde `UBICACION_TOMADA`; renombrarla a "Camioneta 2 (Kangoo)" se acepta.

### D15 — Quién lee jornadas · de negocio · ADR-049 · **ALTO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.** Toca permisos de lectura: al aplicar, se muestra qué permiso abre cada lectura.

**Contexto.** `01` §19 no dice quién ve las jornadas. Precedente: el 14 abrió las lecturas con el permiso de la escritura.

- **A (recomendada). Cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION` lee todas las jornadas de la organización**: `GET /stock/jornadas` (filtros de ubicación, usuario, estado y fechas; cursor) y `GET /stock/jornadas/{id}`. `GET /stock/jornadas/actual` devuelve la jornada no cerrada del usuario y el dispositivo del token (o 404), con `ABRIR_JORNADA`. El listado de ubicaciones (`TRANSFERIR_STOCK`) indica cuáles están tomadas y por quién. Sin permiso nuevo.
- **B. Con solo `ABRIR_JORNADA` se ven solo las propias.** Consecuencia: el Vendedor no sabe quién tiene la camioneta que quiere abrir; un criterio de alcance más (como `ANULAR_TRANSFERENCIA`).
- **C. Permiso nuevo `VER_JORNADAS`.** Consecuencia: catálogo de 41 permisos y migración de plantillas, por una lectura sin datos sensibles.

**Ejemplo (A).** Pedro (Vendedor) ve en el listado que "Camioneta 1" la tiene Juan desde las 8:00.

### D16 — Pantallas · de negocio

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** `CLAUDE.md` §2: TanStack Query solo en `/admin`, Dexie solo en `/ruta`. `/ruta` nace en el 21.

- **A (recomendada). En `/admin`, dentro de la sección Stock:** "Jornadas" (listado con filtros y estado), "Abrir jornada" (elige una ubicación con toma y libre; aviso de que requiere conexión; reintento con el mismo `operation_id`), detalle con "Cargar vehículo" (D4), "Rendir", "Cerrar" y "Liberar" (diálogo con motivo obligatorio), cada acción según permiso y estado. En el listado de ubicaciones y en el stock por ubicación, la marca "Tomada por…". El alta de transferencia y de ajuste muestran el mensaje de `UBICACION_TOMADA`. Consecuencia: el vendedor abre desde `/admin` en su teléfono hasta el 21.
- **B. Una pantalla mínima en `/ruta`**, online. Consecuencia: `/ruta` no puede usar TanStack Query y todavía no tiene Dexie; habría que inventar una tercera forma de leer.
- **C. Sin pantallas.** Consecuencia: incumple `04` §2.1 punto 5.

**Ejemplo.** Juan entra a `/admin` desde el teléfono, ve "Abrir jornada", elige "Camioneta 1" y queda en el detalle de su jornada.

### D17 — Deuda del 06b: permisos por comando en el lote, `PERMISO_REVOCADO` y renovación · técnica · **ALTO (bus) y CRÍTICO (sesión)**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.**

**Contexto.** `04` §6 nominó "para el 15 o el 18a" tres piezas: (a) el paso 4 de `02` §6.3 en `POST /sync/comandos`; (b) `PERMISO_REVOCADO` para comandos `OFFLINE` de un usuario o rol inactivo (SYN-10); (c) la excepción de renovación con jornada no cerrada (ADR-028 D9.3-B). Hechos del código: ningún tipo admite `OFFLINE`; el lote no puede ejecutar ningún handler real porque no les pasa `sesion` ni `reloj` (deuda del 17); el catálogo de tipos no declara permisos. La pieza (c) solo depende de que exista `jornada`. El primer tipo `OFFLINE` es `COBRANZA_REGISTRAR`, del change **17**, que ya carga con la deuda de la firma de los handlers y va antes que el 18a.

- **A (recomendada). Se reparte.** El 15 implementa **(c)** en el lote 3, como pieza crítica aislada (D18, D19). **(a) y (b) pasan al 17**, no al 18a: es el primer change con un tipo `OFFLINE` y el que arregla el despacho por lote; sin eso, (a) y (b) solo se podrían probar con handlers de prueba. Consecuencias: hasta el 17 la excepción de renovación no tiene efecto visible (un inactivo con jornada abierta renueva un token que no abre nada, porque toda otra ruta lo rechaza y el lote no tiene tipos `OFFLINE`); `04` §4 debe decir que el 17 depende del 15 (hoy no lo dice y `cobranza.jornada_id` lo necesita).
- **B. Todo al 17 (o al 18a).** El 15 solo deja la consulta pública "¿este usuario tiene una jornada no cerrada en este dispositivo?". Consecuencia: el 15 no toca autenticación; el 17 carga con sesión, bus y cobranzas juntos.
- **C. Todo en el 15.** Declarar el permiso de cada tipo en el catálogo (unos cincuenta tipos de ocho módulos), tipar la firma de los handlers (deuda del 17) y probar `PERMISO_REVOCADO` con handlers de prueba. Consecuencia: un quinto lote que toca todos los módulos, sin ningún comando real que lo ejercite.

**Ejemplo (A).** Hoy: a Juan lo dan de baja con la jornada abierta; su renovación se acepta y cualquier pantalla le responde 401. En el 17: su cobranza offline sube y queda `ACEPTADO_CON_OBSERVACIONES` con `PERMISO_REVOCADO`.

### D18 — Renovación del usuario inactivo: qué jornadas la habilitan · de negocio · ADR-049 · **CRÍTICO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.** Autenticación: se escribe solo con el alcance confirmado al empezar el lote 3. Aplica porque D17 = A.

**Contexto.** ADR-028 D9.3-B (aprobada): la renovación de un usuario o rol inactivo se rechaza y revoca "salvo que ese dispositivo tenga una jornada no cerrada de ese usuario". El mismo ADR dice: "cuando la jornada se cierra, o la libera un supervisor, la excepción deja de aplicar" y, a renglón seguido, "queda por definir en el change 15 si una jornada `LIBERADA` sigue habilitando la entrega de su cola". RUT-09 acepta los comandos posteriores a la liberación con `JORNADA_LIBERADA`.

- **A (recomendada). Solo `ABIERTA` y `EN_RENDICION`** (los estados del índice de INV-16), del mismo usuario **y** del mismo dispositivo que renueva. Con la excepción, la renovación rota el refresh como siempre, **no** revoca las familias del usuario y deja una fila de auditoría (`RENOVAR_SESION_CON_JORNADA_PENDIENTE`, `origen = SISTEMA`) por cada renovación. El inicio de sesión sigue rechazando al inactivo, con o sin jornada. **La revocación en bloque también respeta la excepción:** si el mismo usuario intenta renovar desde otro dispositivo sin jornada, se rechaza y se revocan sus familias de refresh **menos** la del dispositivo que tiene la jornada no cerrada (ADR-028 D9.5: "salvo la excepción de D9.3-B"); si no, ese rechazo cerraría el canal de la cola. Consecuencias: la sesión del inactivo muere en la primera renovación después de cerrar o liberar; si un supervisor libera la jornada de un usuario ya dado de baja **antes** de que sincronice, esa cola queda varada (recuperarla exige reactivarlo). El orden correcto para cortar a un vendedor con ventas pendientes es: que sincronice, y después liberar.
- **B. También `LIBERADA`, durante una ventana** (por ejemplo, 72 horas desde `liberada_en`). Consecuencia: la cola de una jornada liberada siempre llega (coherente con RUT-09), pero el inactivo conserva una sesión viva después de que el supervisor quiso cortarlo, y hay que elegir y documentar un plazo.
- **C. También `LIBERADA`, sin plazo.** Consecuencia: la sesión del inactivo no muere nunca en ese dispositivo. No recomendada.

**Ejemplo (A).** A Juan lo dan de baja a las 12:00 con la jornada abierta. A las 12:10 su teléfono renueva: se acepta y queda auditado. A las 18:00 la Supervisora cierra la jornada; a las 18:05 la renovación se rechaza y sus sesiones quedan revocadas.

### D19 — Cómo sabe `identidad` que hay una jornada no cerrada · técnica · ADR-049 · **CRÍTICO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.** Aplica porque D17 = A.

**Contexto.** `02` §5.3: `identidad ◄── todos`; `identidad` no importa `stock`. El proyecto ya resolvió tres veces la consulta inversa con un puerto de registro (ADR-023, ADR-025, ADR-048 punto 6).

- **A (recomendada). Puerto de registro en `identidad/service.py`.** `stock/service.py` registra al importarse una consulta "¿hay una jornada no cerrada de este usuario en este dispositivo?". **Falla cerrado hacia el corte:** sin consulta registrada, la excepción no existe y la renovación del inactivo se rechaza y revoca como hoy. Una prueba de arranque verifica que `app.main` deja la consulta registrada. La renovación solo consulta el puerto cuando el usuario o el rol están inactivos: el camino normal no cambia. Un contrato de import-linter prohíbe a `identidad` importar `stock`.
- **B. `identidad` importa `stock/service.py`.** Consecuencia: invierte `02` §5.3 y crea un ciclo (`stock` ya importa `identidad`).
- **C. `identidad` lee `jornada` con SQL directo.** Consecuencia: viola `02` §5.2 (un módulo usa a otro solo por su `service.py`).

**Ejemplo.** En una prueba que no importa `stock`, la renovación de un usuario inactivo se rechaza aunque exista una jornada abierta en la base: sin puerto no hay excepción.

### D20 — Foto de los permisos al abrir la jornada (SYN-10) · técnica

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** `02` §6.3 paso 4: en `OFFLINE` "se valida contra los permisos vigentes al abrir la jornada". Ninguna tabla guarda esos permisos. Quien los use será el change que implemente el paso 4 (D17).

- **A (recomendada). El 15 no los guarda.** El change que implemente el paso 4 decide si hace falta la foto (SYN-05 impide rechazar una venta offline por permisos, así que la foto no cambiaría el resultado salvo para un permiso que el usuario nunca tuvo) y, si hace falta, agrega la columna. Las jornadas duran un día: no se pierde historia útil.
- **B. Guardar `permisos_al_abrir` desde ahora**, sin consumirlo. Consecuencia: una columna y código sin lector, definidos antes de conocer la regla que los usa.

**Ejemplo.** Una jornada abierta el día anterior al despliegue del 17 no tendría foto; con A ese change define qué hacer con ella.

### D21 — Observación `JORNADA_LIBERADA` (segunda mitad de RUT-09) · técnica

> **APROBADA (opción A, 2026-10-09).**

**Contexto.** RUT-09: "los comandos posteriores de esa jornada se aceptan al sincronizar con observación `JORNADA_LIBERADA`". Solo aplica a comandos `OFFLINE` de ruta, y no existe ninguno.

- **A (recomendada). El 15 no construye el evaluador.** Entrega la jornada, su estado y las consultas públicas; el primer comando de ruta (cobranza en el 17, venta en el 18a) define cómo valida la jornada del sobre y emite la observación. En el 15, un comando **online** de la propia jornada sobre una jornada ya liberada o cerrada simplemente no tiene toma que lo ampare (D6). Queda como deuda nominada.
- **B. Construir ahora una función pública** que, dado un sobre con jornada, devuelva "aceptar", "aceptar con `JORNADA_LIBERADA`" o "rechazar", probada con un handler de prueba. Consecuencia: reglas sin consumidor (qué estados aceptan, qué `operacion_tipo` lleva la observación), que el 17 probablemente cambie.

**Ejemplo.** En el 18a: una venta offline de las 16:00 de una jornada liberada a las 15:00 se acepta con `JORNADA_LIBERADA`.

### D22 — Los handlers de stock por el lote del bus · técnica · **ALTO**

> **APROBADA (opción A, 2026-10-09), con aprobación explícita del usuario.**

**Contexto.** `_procesar_item_de_lote` no pasa `sesion` ni `reloj` (deuda nominada al 17). Los cuatro comandos de jornada son solo `ONLINE` y entran por REST, y STK-09 vive en la puerta del libro: nada de este diseño usa el lote.

- **A (recomendada). Se queda en el 17.** Los handlers de jornada nacen con la misma firma que los de `stock` (plantilla D7 del change 04), y el 17 los corrige a todos juntos.
- **B. Adelantarla al 15.** Consecuencia: cambia la firma de unos cincuenta handlers de ocho módulos y el despacho por lote, sin que el 15 lo necesite.

**Ejemplo.** `JORNADA_ABRIR` enviado dentro de un lote falla igual que hoy falla `STOCK_TRANSFERIR` por el lote; por REST funciona.

## Risks / Trade-offs

- **[STK-09 rompe flujos que hoy funcionan]** (transferir a una camioneta tomada, compra con destino a un vehículo tomado) → mensaje propio de `UBICACION_TOMADA`, marca "Tomada por…" en las pantallas y verificación manual de los tres casos; las ubicaciones sin jornada no cambian.
- **[Interbloqueo entre movimientos y transiciones de jornada]** → la apertura solo toma la ubicación (primer paso de todos) y las demás transiciones solo la jornada (último nivel); pruebas de concurrencia en ambos órdenes (D9).
- **[La migración se detiene por huérfanos]** → consulta de solo lectura antes de aplicar e informe en el resumen del lote 1 (D11).
- **[La excepción de renovación deja viva la sesión de un inactivo]** → el token no abre ninguna ruta salvo el lote, cada renovación queda auditada, y la excepción termina al cerrar o liberar (D18). Hasta el 17 no tiene efecto útil.
- **[Jornadas cerradas sin conteo hasta el 24]** → consecuencia aceptada de D2; son solo datos de desarrollo y de prueba mientras se construye el roadmap, y el 24 decide qué hace con ellas (puede ignorarlas o limpiarlas).
- **[La rendición del 24 necesita la jornada antes que el stock]** → deuda nominada con el problema descrito (D9).
- **[Dos módulos archivados reciben un parámetro]** (`proveedores`, `importacion`) → por defecto falla cerrado; sus suites son red de seguridad de la tarea que los toca (D7).

## Migration Plan

Una revisión de Alembic sobre `f3a4b5c6d7e8`: crea `jornada` con sus restricciones, índices y privilegios; siembra los motivos de `LIBERACION_JORNADA` en las organizaciones que no tengan; comprueba huérfanos y agrega las dos FK (`NOT VALID` y `VALIDATE`). No modifica filas de `stock_movimiento`, `comando` ni `auditoria`. `downgrade`: quita las FK, la tabla y los motivos sembrados (pérdida explícita de las jornadas; los movimientos conservan su `jornada_id` sin referencia). Sin dependencias nuevas de Python ni de npm.

## Deudas nominadas

- **Al 17 (`cobranzas`):** paso 4 de `02` §6.3 en el lote y `PERMISO_REVOCADO` (D17); foto de permisos (D20); validación de la jornada del sobre y `JORNADA_LIBERADA` (D21); firma de los handlers (D22). `04` §4 debe sumar la dependencia 17 → 15.
- **Al 21 (`pwa-y-bootstrap`):** bootstrap al abrir (D5) y apertura desde `/ruta` (D16).
- **Al 24 (`rendicion`):** conteo como versión nueva de `JORNADA_RENDIR`, RUT-05, jornadas cerradas sin conteo (D2) y el orden de bloqueo de la rendición (D9).
