# Diseño técnico — 17-cobranzas

> **Estado: D0 a D20 APROBADAS 2026-10-15; A en todas salvo D13 = C.** Con D13-C, una cobranza sin conexión con un medio inactivo o sin la referencia que el medio exige se acepta con las observaciones nuevas `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (enmienda `01` SYN-07 con dos códigos). Proposal, specs, tareas y propuesta de docs están actualizados con lo aprobado. Textos de ayuda de D20 aprobados 2026-10-15, con la variante **5b** para `cobranzas.observaciones` (tarea 0.2).
>
> Todo se documenta en **ADR-052** (estado *Propuesto* durante el apply, último lote). Precisaría ADR-012 (permisos en el lote), ADR-028 (parte offline de la baja), ADR-034 (movimientos `COBRANZA` y `ANULACION_COBRANZA` con comando), ADR-046 (validación de medios compartida) y ADR-049 (jornada del sobre, `JORNADA_LIBERADA`), y enmendaría `01` COB-01, COB-05, SYN-07 (dos códigos nuevos, D13), SYN-10 y §19, `02` §5.3, §6.3, §6.5 y §7.3, y `03` §12 y §13 (`observacion.codigo`).
>
> **Gobernanza por dominio.** **CRÍTICO** (análisis y aprobación explícita antes de escribir; lote propio): **D10** (quién puede registrar una cobranza que llega sin conexión y qué pasa si perdió el permiso) y **D11** (contra qué permisos se compara). **ALTO** (se propone y se espera revisión): **D12** (qué jornada vale para una cobranza offline), **D13** (qué cobranzas offline se rechazan), **D14** (quién lee cobranzas, saldos y clientes) y **D15** (auditoría). **MEDIO** (dinero y cuenta corriente): D1 a D8 y D19. **BAJO** (técnicas, sin regla de negocio): D0, D9, D16, D17, D18 y D20.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Cuenta corriente** (change 08, ADR-034, ADR-035): `cuentas_corrientes/service.py::registrar_movimiento` valida tipo y sentido, bloquea `saldo_cuenta`, inserta y actualiza el saldo. Los tipos `COBRANZA` (reduce) y `ANULACION_COBRANZA` (aumenta) ya están en el `CHECK` y en el catálogo de sentidos; nadie los escribe. CC-08: desde el primer movimiento de otro tipo, la cuenta ya no admite `SALDO_INICIAL` (`CUENTA_CON_OPERACIONES`).
- **Pago a proveedor** (change 12, ADR-046): el gemelo del lado proveedor. `proveedores/domain/pagos.py::validar_medios` (pura) valida suma exacta (`MEDIOS_NO_SUMAN_IMPORTE`), rango de 1 a 20 (`MEDIOS_INVALIDOS`), referencia obligatoria (`REFERENCIA_OBLIGATORIA`) y medio activo (`MEDIO_PAGO_INACTIVO`). `cobranzas` no puede importar `proveedores` (`02` §5.3).
- **Configuración** (change 02): `medio_pago` con `requiere_referencia`; el ámbito `ANULACION_COBRANZA` está en `ck_motivo__ambito` y **no tiene motivos sembrados**. `GET /configuracion/medios-pago` y `GET /configuracion/motivos?ambito=` con cualquier sesión.
- **Permisos** (change 03): `REGISTRAR_COBRANZA` (Administrador, Administración, Supervisor, Vendedor) y `ANULAR_COBRANZA` (Administrador, Administración, Supervisor) ya están en el catálogo y en las plantillas.
- **Jornadas** (change 15, ADR-049): `stock/service.py::existe_jornada`, `tiene_jornada_no_cerrada`; el bus rechaza `JORNADA_INEXISTENTE` antes de reservar (paso 1b). Los códigos `PERMISO_REVOCADO`, `JORNADA_LIBERADA` y `CLIENTE_NO_HABILITADO` están en el catálogo de observaciones y nada los emite. La excepción de renovación de un usuario inactivo con jornada no cerrada ya funciona, pero hoy el token no abre nada.
- **Bus** (change 04): `registro.HandlerFuncion = Callable[[SobreComando, BaseModel], object]`. Los 54 handlers registrados declaran `sesion` y `reloj` como argumentos por nombre y se registran con `# type: ignore[arg-type]`; por REST, cada `api.py` llama a `procesar_comando` con un envoltorio que los pasa. **Por el lote, `_procesar_item_de_lote` llama `funcion(sobre, contenido)` sin sesión ni reloj: hoy ningún handler real funciona por el lote**, ni siquiera en modo `ONLINE`. Cada handler valida su propio permiso (`_exigir_permiso` → 403); no hay paso 4 en el bus.
- **No existen:** el módulo `cobranzas`, sus tres tablas, `venta`, el selector liviano de clientes ni una lectura del saldo de un cliente fuera del estado de cuenta (`GESTIONAR_CLIENTES`).

Lo que `docs/` **no** resuelve (cada punto es una decisión abierta):

- COB-01 da `occurred_at` como único momento; PAG-01 tiene además `fecha` del pago real. → D3.
- CLI-02 habla de vender a suspendidos e inactivos, no de cobrarles; CC-08 excluye al consumidor final del saldo inicial, no de la cobranza. → D4.
- VTA-11 admite el excedente en la cobranza con la venta; COB-03 no dice nada de la cobranza independiente que supera la deuda. → D5.
- COB-05 pide motivo y no hay motivos sembrados. → D6. No dice si se anula una cobranza de una jornada ya cerrada ni qué pasa con la de origen `VENTA`. → D7.
- `03` §12 tiene `cobranza.jornada_id`; `02` §6.2 dice que `jornada_id` es obligatorio en comandos de ruta, sin decir si una cobranza **con conexión** del vendedor en jornada lleva la jornada. → D8.
- Las cinco deudas del bus (`04` §8). → D9 a D12.
- SYN-05 dice que una cobranza offline no se rechaza por reglas de negocio, sin decir cuáles lo son, y SYN-07 no tiene código para un medio inactivo ni para una referencia faltante. → D13.
- `01` §19 dice que el vendedor ve el saldo "de sus clientes"; `03` no asigna clientes a vendedores. Tampoco dice quién lee cobranzas. → D14.
- AUD-01 audita "cobranzas anuladas"; no dice si la fila lleva el motivo. → D15.

## Goals / Non-Goals

**Goals:** registrar y anular cobranzas independientes con conexión, con su efecto exacto en la cuenta corriente; aceptar `COBRANZA_REGISTRAR` por el lote en modo `OFFLINE` con las garantías de SYN-05, SYN-10 y RUT-09; dejar el bus listo para que `VENTA_CONFIRMAR` y `VENTA_ANULAR` sean `OFFLINE` sin tocarlo; pantallas usables en `/admin`.

**Non-Goals:** la cola local, Dexie y la pantalla de `/ruta` (23); el saldo local (CRE-08); la cobranza con la venta (18a) y su anulación (19); comprobante (COB-06); imputación (COB-03); rendición (24); bandeja de observaciones (25).

## Decisions

### D0 — Tamaño del change y lotes · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** `04` §2 pide de medio día a tres días. Este change suma un módulo nuevo con dos comandos y tres tablas, pantallas, y cinco deudas del bus que tocan los 54 handlers. ADR-049 descartó "todo al 17" porque "carga al 17 con sesión, bus y cobranzas juntos", pero igual le asignó al 17 el paso 4, `PERMISO_REVOCADO`, la jornada del sobre y la firma. Los changes 14, 15 y 16 fueron excepciones aceptadas en cuatro lotes.

- **A (recomendada). Un change en cinco lotes**, sin frenar entre lotes salvo en las confirmaciones de alcance de las piezas críticas y altas:
  1. **Lote 1:** firma tipada de los handlers y despacho por lote (D9), con una prueba que despacha por el lote cada tipo registrado. No toca negocio.
  2. **Lote 2:** migración, modelos, dominio y `COBRANZA_REGISTRAR` `ONLINE` de punta a punta (D1 a D5, D8, D16 a D18).
  3. **Lote 3:** `COBRANZA_ANULAR`, motivos, auditoría y lecturas (D6, D7, D14, D15).
  4. **Lote 4 (CRÍTICO):** el camino `OFFLINE`: permisos por comando, `PERMISO_REVOCADO`, jornada del sobre y `JORNADA_LIBERADA` (D10 a D13). Autocontenido: si se alarga, se corta a un `17b` sin rehacer nada (el tipo queda `ONLINE` hasta entonces).
  5. **Lote 5:** pantallas, ayuda, concurrencia, cobertura, ADR-052, propuesta de docs y prueba manual.
  Consecuencia: vuelve a superar `04` §2 y se anota la excepción. Cumple `04` §2.1 punto 5 con las pantallas del lote 5.
- **B. Dividir ahora en `17a-cobranzas` (lotes 2, 3 y 5) y `17b-comandos-offline-en-el-lote` (lotes 1 y 4).** Consecuencia: el 17a declara `COBRANZA_REGISTRAR` solo `ONLINE`; el 18a depende del 17a y el 23 del 17b. El 17b se archiva sin nada que probar en el navegador (no hay cola offline hasta el 22a).
- **C. Dividir con el bus primero (`17a` bus, `17b` cobranzas).** Consecuencia: es la opción que ADR-049 ya descartó: un bus nuevo sin ningún comando real que lo ejercite.

**Ejemplo.** Al cerrar el lote 2, un Administrador registra por API una cobranza de $50.000,00 a Kiosco La Esquina y su saldo pasa de $150.000,00 a $100.000,00. Al cerrar el lote 4, la misma cobranza enviada por el lote en modo `OFFLINE` desde la jornada del vendedor se acepta.

### D1 — Qué cobranzas entran · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-01 admite origen `VENTA` o `INDEPENDIENTE`; la venta no existe hasta el 18a, y VTA-22 (devolver el dinero al anular la venta) es del 19. La fila 23 del roadmap es "cobranza offline" del lado del dispositivo.

- **A (recomendada). Solo cobranzas `INDEPENDIENTE`**, registradas con conexión desde `/admin` y por el lote en modo `OFFLINE` (para que el 22a y el 23 ya encuentren el servidor listo). El servicio deja una función `registrar_cobranza` que el 18a llamará con origen `VENTA` dentro de la transacción de la venta; en este change una cobranza de origen `VENTA` no se puede registrar por comando. Consecuencia: el 18a no toca `cobranzas` salvo para pasar `venta_id`.
- **B. Solo con conexión; el modo `OFFLINE` se declara en el 23.** Consecuencia: las deudas del bus siguen abiertas sin un tipo que las ejercite, contra lo que nominaron los changes 05, 14 y 15.
- **C. Incluir también la cobranza con la venta.** Consecuencia: imposible sin la tabla `venta`.

**Ejemplo.** Con A, el lunes la administración carga la transferencia de $20.000,00 que mandó Kiosco La Esquina; la cobranza nace `CONFIRMADA`, origen `INDEPENDIENTE`, sin venta.

### D2 — Contenido de la cobranza · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-01 y COB-02 piden importe mayor que cero, uno o más medios que suman el importe y la referencia que el medio exija. No dicen cuántos medios, si se repiten ni si hay observación. `02` §9 dice que la cobranza recibe su identificador **en el dispositivo**.

- **A (recomendada). Igual que el pago a proveedor (ADR-046 punto 7):** `importe` explícito (mayor que cero, dos decimales, `IMPORTE_INVALIDO`), de 1 a 20 medios (`MEDIOS_INVALIDOS`), cada uno activo, con importe positivo y referencia donde se exige; el mismo medio puede repetirse; **observación opcional** de hasta 500 caracteres, recortada y nula si queda vacía (por ejemplo, "paga facturas de septiembre"). El contenido trae `cobranza_id` (UUIDv7 generado por quien origina, también en `/admin`): un `cobranza_id` ya usado por otra operación se rechaza (`COBRANZA_DUPLICADA`, 409). Consecuencia: `03` §12 suma `cobranza.observacion`.
- **B. Igual que A, sin observación.** Consecuencia: no hay dónde anotar a qué corresponde, porque no hay imputación (COB-03).
- **C. Sin `importe` explícito (se deriva de la suma de medios).** Consecuencia: INV-08 se cumple por construcción y se pierde la detección del error de tipeo.

**Ejemplo.** Cobranza de $50.000,00: $30.000,00 en efectivo y $20.000,00 por transferencia con referencia "0042". Si los medios suman $49.000,00, se rechaza con `MEDIOS_NO_SUMAN_IMPORTE`.

### D3 — Fecha de la cobranza · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-01 da solo `occurred_at` (el momento informado por el dispositivo, TR-05) y `03` no tiene una columna de fecha. El pago a proveedor (PAG-01) tiene además `fecha` (la del recibo, no futura) porque la administración carga los pagos tarde.

- **A (recomendada). Sin campo de fecha propio: el momento de la cobranza es el `occurred_at` del comando**, mostrado en la zona de la organización (TR-04). En la calle es el momento en que el vendedor cobró, aunque sincronice después; en `/admin` es el momento de la carga. Consecuencia: una transferencia recibida ayer y cargada hoy figura hoy.
- **B. Agregar `fecha` como en los pagos** (la del cobro real, no futura, sin límite hacia atrás; el movimiento sigue en `occurred_at`). Consecuencia: enmienda COB-01 y `03` §12; la pantalla pide una fecha más; offline la fecha la pone el teléfono.
- **C. Que el movimiento de cuenta use la fecha de B.** Consecuencia: una cobranza cargada tarde cambia saldos acumulados ya vistos (ADR-046 la descartó).

**Ejemplo.** El vendedor cobra $50.000,00 el martes a las 10:15 sin señal y sincroniza a las 18:00: con A la cobranza dice "martes 10:15" y el movimiento también.

### D4 — Estado del cliente y consumidor final · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** CLI-02 limita la **venta** a suspendidos e inactivos, no la cobranza. El consumidor final (CLI-03) tiene límite cero y no admite saldo inicial (CC-08).

- **A (recomendada). Se cobra a clientes `ACTIVO`, `SUSPENDIDO` e `INACTIVO`** (la deuda existe aunque el cliente esté dado de baja; mismo criterio que el proveedor inactivo, ADR-046 punto 6). El selector de la pantalla ofrece activos y suspendidos; a un inactivo se le cobra desde su cuenta corriente. **Al consumidor final no se le registra una cobranza independiente** (`CONSUMIDOR_FINAL_SIN_CUENTA`, el código de CC-08; **precisión del apply 2026-10-16: responde 422**, igual que `cuentas_corrientes`, no 409): paga en el acto con la venta (18a). Desde la primera cobranza la cuenta ya no admite saldo inicial (CC-08, heredado).
- **B. Rechazar también al inactivo.** Consecuencia: obliga a reactivarlo para cobrar, y CLI-06 no lo deja si tiene operaciones: la deuda de un inactivo no se podría cobrar nunca.
- **C. Admitir también al consumidor final.** Consecuencia: un saldo a favor anónimo que nadie puede reclamar.

**Ejemplo.** Almacén Don Pedro, inactivo, debe $12.000,00 y paga: con A se registra y su saldo queda en $0,00.

### D5 — Cobranza mayor que la deuda · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-03: la cobranza reduce el saldo general, sin imputar. VTA-11 admite el excedente en la cobranza con la venta. Nada dice de la independiente.

- **A (recomendada). Se admite cualquier importe mayor que cero;** si el saldo queda negativo es "Saldo a favor" del cliente y la próxima venta lo absorbe (CC-04, sin operación nueva). El servidor no bloquea ni observa; la pantalla muestra el saldo actual y el resultante y, si queda a favor, pide una confirmación explícita. Igual que ADR-046 punto 4.
- **B. Rechazar la cobranza que supera la deuda.** Consecuencia: no admite anticipos ni el cliente que paga de más para la semana siguiente; offline no se podría rechazar (SYN-05) y quedarían dos reglas.
- **C. Aceptarla con una observación.** Consecuencia: una observación pendiente por un caso habitual; además no existe un código en SYN-07.

**Ejemplo.** Kiosco La Esquina debe $150.000,00 y paga $160.000,00: la pantalla avisa "Le queda saldo a favor de $10.000,00. ¿Confirmás?"; confirmado, el saldo es −$10.000,00.

### D6 — Motivos de anulación · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-05 exige motivo; el ámbito existe sin motivos. Precedente: ADR-046 punto 2 y ADR-048, motivos sembrados en organizaciones nuevas y, de forma idempotente, en las existentes.

- **A (recomendada). Sembrar tres motivos: "Error de carga", "Pago rechazado o no acreditado" y "Otro".** `COBRANZA_ANULAR` exige un motivo activo de la organización y de ese ámbito (`MOTIVO_INVALIDO`, 422; ajeno, 404).
- **B. Reutilizar los de `ANULACION_PAGO`.** Consecuencia: mezcla ámbitos; TR-09 y `03` §4 piden el ámbito propio.
- **C. Sin siembra: que la organización los cree.** Consecuencia: no hay comando para crear motivos; nadie podría anular.

**Ejemplo.** Un cheque de $20.000,00 vuelve rechazado: se anula la cobranza con "Pago rechazado o no acreditado" y el saldo vuelve a $150.000,00.

### D7 — Reglas de la anulación · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** COB-05: anulación con `ANULAR_COBRANZA` y motivo; `02` §6.5: solo con conexión. No dice qué pasa con la de una jornada ya cerrada, la de un cliente inactivo, ni la de origen `VENTA`.

- **A (recomendada).** Solo una `CONFIRMADA` (`COBRANZA_YA_ANULADA`, 409, una sola vez); deja la cobranza `ANULADA`, una fila en `cobranza_anulacion` con motivo y una **observación opcional** de hasta 500 caracteres, y un movimiento `ANULACION_COBRANZA` por el importe completo. Se anula la de cualquier usuario, la de un cliente inactivo y la de una jornada cerrada o liberada (el resumen de rendición del 24 la mostrará anulada). Una de origen `VENTA` se rechaza con `COBRANZA_DE_VENTA` (409): se anula con la venta (VTA-22, 19). Sin anulación parcial.
- **B. Igual que A, sin observación de anulación.** Consecuencia: el número del cheque rechazado no queda en ningún lado.
- **C. Prohibir anular cobranzas de una jornada cerrada.** Consecuencia: un cheque rechazado después de la rendición no se podría reflejar.

**Ejemplo.** La cobranza de $50.000,00 del martes se anula el viernes: el saldo de Kiosco La Esquina vuelve de $100.000,00 a $150.000,00 y en su cuenta quedan las dos filas.

### D8 — Jornada de una cobranza con conexión · negocio · MEDIO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** `cobranza.jornada_id` sirve para el resumen de rendición (RUT-07, change 24). Hasta el 21 el vendedor opera desde `/admin` en su teléfono. ADR-049 punto 7 deduce "la jornada" del token para el stock.

- **A (recomendada). El servidor la deduce:** si el usuario y el dispositivo del token tienen una jornada `ABIERTA`, la cobranza la lleva; si no, queda sin jornada. Si el sobre trae una jornada, tiene que ser esa (`JORNADA_AJENA`, 409). En `EN_RENDICION` la cobranza queda sin jornada (la jornada ya se está rindiendo).
- **B. Una cobranza con conexión nunca lleva jornada.** Consecuencia: lo que el vendedor cobra en línea no aparece en su rendición.
- **C. La pantalla le pregunta al usuario.** Consecuencia: un paso más y un error posible sin beneficio.

**Ejemplo.** El vendedor con la jornada abierta en la camioneta 2 registra desde su teléfono $50.000,00: la cobranza queda en su jornada. La administración, desde la PC, registra otra: queda sin jornada.

### D9 — Firma tipada y despacho por lote · técnica · BAJO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** Deudas de los changes 05, 14 y 15 (ADR-048 punto 5, ADR-049 punto 19): por el lote ningún handler recibe sesión ni reloj.

- **A (recomendada). `HandlerFuncion` pasa a un `Protocol` con la firma que los 54 handlers ya tienen:** `(sobre, contenido, *, sesion: SesionDeHandler, reloj: Clock) -> object`, donde `SesionDeHandler` es el tipo de la sesión protegida que entrega el bus (`SesionSinCommit`, sin `commit` ni `rollback`). `_procesar_item_de_lote` le pasa la sesión protegida y el reloj, igual que REST. Se quitan los `# type: ignore[arg-type]` del registro y de los handlers (`sesion: object` pasa a `SesionDeHandler`). Una prueba recorre el registro y despacha por el lote un comando válido de cada tipo de stock y de jornada. Consecuencia: cambio mecánico en nueve módulos, sin cambiar ningún comportamiento.
- **B. Un objeto de contexto (`ContextoDeHandler` con sobre, sesión y reloj) como único argumento.** Consecuencia: más prolijo, pero reescribe la firma y el cuerpo de los 54 handlers.
- **C. Solo pasar sesión y reloj en el lote, sin tipar.** Consecuencia: el lote funciona, pero la deuda de tipos sigue abierta.

**Ejemplo.** Hoy, un `STOCK_TRANSFERIR` enviado por el lote en modo `ONLINE` falla al invocar el handler; con A se procesa igual que por REST.

### D10 — Permisos por comando en el lote · seguridad · CRÍTICO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** Paso 4 de `02` §6.3: en `ONLINE` un permiso faltante rechaza; en `OFFLINE` se acepta con `PERMISO_REVOCADO` (SYN-10). ADR-028 (D9.3-B): un usuario o rol inactivo con cola pendiente se acepta con `PERMISO_REVOCADO`. Hoy cada handler valida su permiso y lanza 403.

- **A (recomendada). El catálogo de tipos declara el permiso de cada tipo que admite `OFFLINE`** (`declarar_tipo(..., permiso_offline="REGISTRAR_COBRANZA")`); un ratchet exige que todo tipo `OFFLINE` lo declare. En modo `OFFLINE`, **el bus** hace el paso 4: si el usuario no tiene ese permiso, o el usuario o su rol están inactivos (se evalúa sin permisos), el comando sigue y queda `ACEPTADO_CON_OBSERVACIONES` con `PERMISO_REVOCADO` (detalle: permiso y motivo: `PERMISO_QUITADO`, `USUARIO_INACTIVO` o `ROL_INACTIVO`); el handler recibe `modo` y en `OFFLINE` no vuelve a exigir el permiso. En `ONLINE` (REST o lote) nada cambia: valida el handler y rechaza con 403. Consecuencia: los 50 tipos solo `ONLINE` no se tocan; `VENTA_CONFIRMAR` y `VENTA_ANULAR` solo declaran su permiso.
- **B. Centralizar el paso 4 para todos los tipos**, declarando el permiso de cada uno y quitándolo de los handlers. Consecuencia: toca los 54 handlers y no todos tienen un permiso fijo (la anulación de una transferencia ajena exige además `ANULAR_TRANSFERENCIA`; la toma, `LIBERAR_UBICACION`).
- **C. Que cada handler `OFFLINE` lo resuelva por su cuenta.** Consecuencia: cada tipo futuro tiene que acordarse; un olvido rechaza una venta ya entregada (contra SYN-05).

**Ejemplo.** El lunes el vendedor cobra $50.000,00 sin señal; el martes le quitan `REGISTRAR_COBRANZA`; el miércoles sincroniza: la cobranza se acepta, el saldo baja a $100.000,00 y queda la observación `PERMISO_REVOCADO` para revisar. Si el miércoles intentara registrar otra con conexión, recibe 403.

### D11 — La foto de permisos al abrir la jornada · seguridad · CRÍTICO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** SYN-10: "sin conexión, los permisos vigentes son los descargados al abrir la jornada". ADR-049 punto 19 dejó a este change decidir si se guarda una foto. Como SYN-05 prohíbe rechazar una cobranza offline por permisos, la foto solo cambiaría la observación, no el resultado.

- **A (recomendada). Sin foto en el servidor: se compara con los permisos actuales.** Si al sincronizar el usuario no tiene el permiso, `PERMISO_REVOCADO`. La foto de SYN-10 es la del dispositivo (bootstrap, change 21): decide qué ofrece la pantalla sin conexión. Consecuencia: un usuario que nunca tuvo el permiso y logra encolar una cobranza también queda con `PERMISO_REVOCADO` (se acepta igual, por SYN-05); un permiso dado después de abrir la jornada vale.
- **B. Guardar los permisos al abrir (`jornada.permisos_al_abrir`) y comparar contra esa foto.** Consecuencia: migración y cambio de `JORNADA_ABRIR`; distingue "se lo quitaron" de "nunca lo tuvo", pero los dos se aceptan; haría falta un código nuevo en SYN-07 para el segundo caso.
- **C. Rechazar si no lo tenía al abrir.** Consecuencia: contradice SYN-05 e INV-17.

**Ejemplo.** Con A, la vendedora abre la jornada con `REGISTRAR_COBRANZA`, se lo quitan al mediodía y sincroniza a la tarde: aceptada con `PERMISO_REVOCADO`. Con B el resultado es el mismo.

### D12 — La jornada de una cobranza sin conexión y `JORNADA_LIBERADA` · ruta · ALTO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** `02` §6.2: el modo `OFFLINE` es "solo en sync con jornada abierta"; SYN-06 solo rechaza lo malformado, inconsistente, de otra organización, con dependencias inexistentes o de dispositivos revocados. RUT-09: los comandos posteriores a la liberación se aceptan con `JORNADA_LIBERADA` "a partir del primer comando de ruta, change 17". RUT-05 (cola vacía antes de rendir) recién se verifica en el 24.

- **A (recomendada).** En `OFFLINE`: sin jornada en el sobre → **rechazado** `JORNADA_REQUERIDA` (malformado); jornada de otro usuario o de otro dispositivo → **rechazado** `JORNADA_AJENA` (inconsistente: la cola es de ese usuario y ese dispositivo); `ABIERTA` → normal; `LIBERADA` → aceptada con `JORNADA_LIBERADA` (detalle: jornada y momento de la liberación); `EN_RENDICION` o `CERRADA` → **aceptada sin observación nueva** (el dinero se cobró; el 24 decide si RUT-05 necesita un código). La cobranza lleva la jornada del sobre en todos los casos aceptados. El servidor lee la jornada `FOR SHARE` (nivel 5) para que una liberación simultánea se vea o espere.
- **B. Igual que A, pero `EN_RENDICION` y `CERRADA` con un código nuevo `JORNADA_CERRADA`** en SYN-07. Consecuencia: enmienda `01` SYN-07; la cobranza tardía queda para revisar desde ya.
- **C. Aceptar también la jornada ajena, con observación.** Consecuencia: una cola con datos de otra sesión entraría al libro.

**Ejemplo.** La supervisora libera la jornada de la camioneta 2 a las 14:00 porque al vendedor se le rompió el teléfono; a las 19:00 el teléfono revive y sincroniza la cobranza de $50.000,00 de las 11:00: se acepta con `JORNADA_LIBERADA` y el saldo baja.

### D13 — Qué no rechaza una cobranza sin conexión (SYN-05, INV-17) · ruta · ALTO · ADR-052 · **APROBADA 2026-10-15: opción C**

**Contexto.** SYN-05 enumera "stock, crédito, lista, descuentos, estado del cliente o permisos". Una cobranza puede llegar con un medio desactivado después de abrir la jornada, una referencia faltante o el consumidor final.

- **A.** Se **rechazan** solo: contenido malformado (esquema, importe no positivo o con tres decimales, medios fuera de 1 a 20, **medios que no suman el importe**: INV-08 es un invariante y el dispositivo lo calcula, no es regla de negocio), cliente o medio inexistente o de otra organización (dependencia, SYN-06), `cobranza_id` repetido y los casos de D12. Se **aceptan**: el permiso (D10), cualquier estado del cliente (D4), un medio inactivo o una referencia faltante (sin observación nueva: lo que llegó es lo que pasó en la calle) y el consumidor final, con `CLIENTE_NO_HABILITADO`.
- **B. Rechazar también el medio inactivo y la referencia faltante como malformados.** Consecuencia: una cobranza ya cobrada queda varada en el teléfono porque alguien desactivó un medio.
- **C (aprobada). Igual que A, pero el medio inactivo y la referencia faltante se aceptan con observaciones nuevas** (`MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`). Consecuencia: enmienda SYN-07 con dos códigos.

**Lo aprobado (C), en detalle.** Motivo del usuario: si en la oficina desactivan un medio por algo importante (por ejemplo, una cuenta bancaria cerrada), quiere enterarse de que entró plata por ahí.

1. **Se rechazan** (sin registro del comando ni efecto; el lote sigue) exactamente los casos de A: malformado, medios que no suman el importe (INV-08), cliente o medio inexistente o de otra organización, `cobranza_id` repetido y los casos de D12.
2. **Se aceptan con observación:**
   - `MEDIO_INACTIVO`: una por cada línea de medio cuyo medio de pago está inactivo al sincronizar. Detalle: `{"medio": <posición de la línea, desde 0>, "medio_pago_id": "<id>", "nombre": "<nombre del medio>", "importe": "<importe de la línea>"}`.
   - `REFERENCIA_FALTANTE`: una por cada línea cuyo medio exige referencia (según la configuración del medio al sincronizar, el mismo criterio que D11 usa con los permisos) y llega sin referencia o con solo espacios. Mismo detalle que `MEDIO_INACTIVO`. La referencia se guarda nula.
   - Una misma línea puede llevar las dos; dos líneas con el mismo medio inactivo dan dos observaciones, cada una con su línea.
   - Conviven con `CLIENTE_NO_HABILITADO`, `PERMISO_REVOCADO` y `JORNADA_LIBERADA` en el mismo comando; el comando queda `ACEPTADO_CON_OBSERVACIONES` y un doble envío devuelve las mismas observaciones sin duplicarlas (INV-06).
3. **Se aceptan sin observación:** cualquier estado del cliente (D4). El permiso va por D10.
4. **Con conexión no cambia nada** (REST o lote en modo `ONLINE`): un medio inactivo se rechaza con `MEDIO_PAGO_INACTIVO` y una referencia faltante con `REFERENCIA_OBLIGATORIA`, los dos indicando el medio, igual que el pago a proveedor hoy (`proveedores/service.py` rechaza el medio inactivo al resolver los medios; `validar_medios` rechaza la referencia). Las dos observaciones nuevas existen solo en `OFFLINE`.
5. **Dónde vive:** la validación compartida de medios (D17) suma el parámetro `exigir_referencia` (por defecto `True`: pagos y compras de contado no cambian) y una función pura que devuelve las líneas sin referencia; `cobranzas/domain` arma las observaciones; en `OFFLINE`, la resolución de medios del servicio de cobranzas devuelve si cada medio está activo en lugar de lanzar `MEDIO_PAGO_INACTIVO`.
6. **Base y catálogo:** la migración del change amplía `ck_observacion__codigo` y `CODIGOS_OBSERVACION` (`sync/models.py`) con los dos códigos; el `downgrade` vuelve el `CHECK` atrás y aborta si hay observaciones con ellos (una prueba lo deja escrito). El detalle de la cobranza muestra "Medio de pago inactivo" y "Falta la referencia" con la línea afectada.

**Ejemplo.** A las 9:00 la vendedora cobra $10.000,00 con "Billetera"; a las 12:00 la administración desactiva "Billetera" porque cerró esa cuenta; a las 18:00 sincroniza: se acepta, el saldo baja $10.000,00 y queda la observación `MEDIO_INACTIVO` ("Billetera", primera línea, $10.000,00) para revisar. Si la cobranza llegara por transferencia sin número de operación, quedaría `REFERENCIA_FALTANTE` sobre esa línea. Si la administración intenta cargar con conexión una cobranza con "Billetera", recibe `MEDIO_PAGO_INACTIVO`.

### D14 — Quién lee cobranzas, saldos y clientes · permisos · ALTO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** El Vendedor tiene `REGISTRAR_COBRANZA` pero no `GESTIONAR_CLIENTES`, que hoy abre el listado y la cuenta corriente de clientes. `01` §19: "el vendedor ve el saldo y el crédito disponible de sus clientes", pero no existe asignación de clientes a vendedores.

- **A (recomendada).** `GET /cobranzas` y `GET /cobranzas/{id}`: con `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`, todas las de la organización (como los pagos, ADR-046 punto 8). `GET /clientes/{id}/saldo` (saldo actual desde `saldo_cuenta`): con `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`. Un selector liviano nuevo `GET /clientes/opciones` (identificador, nombre, código y estado; sin crédito ni documento): con `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`. "Sus clientes" se lee como **todos los clientes de la organización** hasta que exista una asignación. El estado de cuenta sigue con `GESTIONAR_CLIENTES`. Sin permisos nuevos.
- **B. Igual que A, pero quien solo tiene `REGISTRAR_COBRANZA` ve solo sus propias cobranzas.** Consecuencia: el vendedor no ve lo que cobró la administración a sus clientes; un filtro más en el servidor.
- **C. Abrir el listado completo de clientes a `REGISTRAR_COBRANZA`.** Consecuencia: el vendedor ve límites de crédito y documentos de todos.

**Ejemplo.** Con A, el vendedor elige "Kiosco La Esquina" en el selector, ve "Nos debe $150.000,00" y registra; no puede abrir la ficha ni la cuenta corriente.

### D15 — Auditoría de la anulación · auditoría · ALTO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** AUD-01 audita las cobranzas anuladas; el bus deja una fila por comando (ADR-022) y copia el motivo solo en cuatro comandos (ratchet de ADR-049 punto 9). `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` no lo copian (deuda del 14 a los changes 26 y 28).

- **A (recomendada). `COBRANZA_ANULAR` devuelve el motivo para la fila del bus** (ratchet de cuatro a cinco comandos). `COBRANZA_REGISTRAR` queda auditado por la fila del bus, como todo comando; las observaciones (`PERMISO_REVOCADO`, `JORNADA_LIBERADA`, `CLIENTE_NO_HABILITADO`, `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`) van en `observacion`, no en la auditoría.
- **B. Sin motivo en la fila, como compras y pagos.** Consecuencia: la consulta de auditoría tiene que cruzar con `cobranza_anulacion`; suma a la deuda del 26 y 28.
- **C. Copiar también el motivo a compras y pagos ahora.** Consecuencia: cierra una deuda ajena y toca dos módulos archivados.

**Ejemplo.** La fila de auditoría de la anulación del cheque dice: usuario, `COBRANZA_ANULAR`, la cobranza, "Pago rechazado o no acreditado".

### D16 — Modelo de datos y migración · técnica · BAJO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** `03` §12 lista las tres tablas sin restricciones; `venta` no existe. ADR-046 guardó la anulación del pago en columnas propias; `03` pide una tabla `cobranza_anulacion`.

- **A (recomendada). Las tres tablas de `03` §12:** `cobranza` (con `UNIQUE (organizacion_id, id)`, FK compuestas a `cliente`, `jornada`, `usuario` y `dispositivo`, `estado` `CONFIRMADA`/`ANULADA`, `origen` con `CHECK` de coherencia con `venta_id`, `importe numeric(14,2) > 0`, `observacion` y columnas de operación); `venta_id` **nulable y sin FK** hasta el 18a (que la agrega y aborta si hay filas, precedente de ADR-049 punto 13). `cobranza_medio` (FK a `cobranza` y `medio_pago`, importe positivo, referencia). `cobranza_anulacion` (`cobranza_id` **único**: la base impide anular dos veces; motivo, observación y columnas de operación). `app_runtime`: `SELECT, INSERT` en las tres y `UPDATE` **solo** de `cobranza.estado`; ningún `DELETE` (INV-05). Índices de listado `(organizacion_id, occurred_at DESC, id DESC)`, `(organizacion_id, cliente_id, occurred_at DESC, id DESC)` y `(organizacion_id, jornada_id)`. Siembra idempotente de los motivos de D6. Ampliación de `ck_observacion__codigo` con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (D13). El `downgrade` pierde por diseño cobranzas y motivos, y una prueba lo deja escrito.
- **B. Anulación en columnas de `cobranza`** (como el pago). Consecuencia: contradice `03` §12 y §14; la doble anulación queda protegida solo por el servicio y un `CHECK`.
- **C. Tablas mínimas, restricciones en el servicio.** Consecuencia: INV-05 e INV-02 sin respaldo en la base.

**Ejemplo.** Con A, dos anulaciones del mismo cheque que llegan a la vez: la segunda choca con el único de `cobranza_anulacion` si se saltara el bloqueo del servicio.

**Precisión del apply aprobada 2026-10-16 (D16):** `cobranza_medio` lleva una columna `orden` (posición de la línea, desde 0, con `UNIQUE (organizacion_id, cobranza_id, orden)`) que `03` §12 no lista; se conserva porque los detalles de `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` citan la línea por su posición. Va en `propuesta-docs.md` (tarea 19.1).

### D17 — Validación de medios compartida y dependencias del módulo · técnica · BAJO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** `validar_medios` vive en `proveedores/domain/pagos.py`; `02` §5.3 dice `cobranzas ──► cuentas_corrientes` solamente, pero la cobranza necesita clientes, medios, motivos, la jornada y los permisos.

- **A (recomendada). Mover `validar_medios` (pura) a `configuracion/domain/medios.py`**, expuesta por `configuracion/service.py`, sin cambiar sus códigos; pagos y compras de contado la importan desde ahí (red de seguridad: sus suites sin cambios). `cobranzas ──► cuentas_corrientes, clientes, configuracion, stock (jornada), identidad (permisos)`, solo por `service.py`, con contratos de import-linter; nadie depende de `cobranzas` salvo `sync` y, desde el 18a, `ventas`.
- **B. Copiar la validación en `cobranzas/domain`.** Consecuencia: dos copias que pueden divergir.
- **C. Importar `proveedores/service.py` desde `cobranzas`.** Consecuencia: una dependencia sin sentido de negocio.

**Ejemplo.** Una referencia de solo espacios en una transferencia da `REFERENCIA_OBLIGATORIA` igual en un pago y en una cobranza, porque es la misma función.

**Precisión del apply aprobada 2026-10-16 (D17):** el contrato de import-linter de `cobranzas.domain` lleva 3 `ignore_imports` hacia `configuracion.domain.medios` (la validación compartida pura, D17). Se conservan; se registran en ADR-052 (tarea 18.1).

### D18 — Bloqueo, concurrencia e idempotencia · técnica · BAJO · ADR-052 · **APROBADA 2026-10-15: opción A**

**Contexto.** `02` §7.3: las filas de la operación que se anula van antes del nivel 1; la jornada es el nivel 5.

- **A (recomendada).** `COBRANZA_REGISTRAR`: `saldo_cuenta` del cliente (nivel 1; un cliente ajeno o inexistente da 404 ahí), luego la jornada `FOR SHARE` (nivel 5) si corresponde, e inserción de cobranza, medios y movimiento. `COBRANZA_ANULAR`: `cobranza FOR UPDATE` (revalida estado), luego `saldo_cuenta`. La reserva del bus cubre los dos (INV-06). Pruebas con commits reales: dos anulaciones simultáneas (una gana, la otra `COBRANZA_YA_ANULADA`, un solo movimiento); dos cobranzas simultáneas al mismo cliente (saldo exacto, INV-13); cobranza frente a saldo inicial (CC-08); cobranza offline frente a liberación de su jornada (ve `ABIERTA` o `LIBERADA`, nunca un estado intermedio).
- **B. Bloquear la cobranza también al registrar.** Consecuencia: no aporta (la fila es nueva).
- **C. Sin bloqueos explícitos, confiar en la reserva.** Consecuencia: dos cobranzas distintas al mismo cliente podrían dejar el saldo mal.

**Ejemplo.** Dos cobranzas de $50.000,00 al mismo tiempo sobre $150.000,00 dejan $50.000,00, nunca $100.000,00.

### D19 — Pantallas · negocio · MEDIO · **APROBADA 2026-10-15: opción A**

- **A (recomendada).** Área "Cobranzas" en `/admin` (`/admin/cobranzas`): listado paginado con filtros (cliente, estado, usuario, jornada, fechas), alta, detalle con medios, jornada y observaciones, y anulación con motivo. Alta: selector de clientes (D14), saldo actual y resultante ("Nos debe" / "Saldo a favor"), medios con suma en vivo y referencia cuando se exige, confirmación si queda a favor (D5), reintento con el mismo `Operation-Id`. Botón "Registrar cobranza" en la cuenta corriente del cliente con el cliente precargado, y enlace de cada movimiento `COBRANZA` y `ANULACION_COBRANZA` a su cobranza, visible según D14. Diseñada para usarse también en el teléfono del vendedor hasta el 23.
- **B. Sin área propia: solo desde la cuenta corriente.** Consecuencia: el vendedor no tiene cuenta corriente (D14) y nadie ve las cobranzas del día.
- **C. Además, la pantalla de `/ruta`.** Consecuencia: adelanta el 23 sin cola local.

**Ejemplo.** La administración filtra "hoy" y ve las tres cobranzas del día con su total por cliente.

### D20 — Ayuda contextual · técnica · BAJO · ADR-051 · **APROBADA 2026-10-15: opción A con un tema nuevo** · **textos aprobados 2026-10-15, clave 5 = variante 5b**

- **A (aprobada).** Claves nuevas en `frontend/src/ayuda/textos.ts`, con el estilo aprobado en el 16b: `cobranzas.medios`, `cobranzas.saldoAFavor`, `cobranzas.jornada`, `cobranzas.anulacion` y `cobranzas.observaciones` (textos abajo). Con un tema "Ver más" nuevo, `cobranzas-observaciones`, por la variante 5b de la clave 5 (elegida en la tarea 0.2).
- **B. Solo medios y anulación.** Consecuencia: el saldo a favor y la jornada quedan sin explicar.
- **C. Además, un tema "Ver más" de cobranzas.** Consecuencia: texto largo sin necesidad.

**Textos (aprobados por el usuario el 2026-10-15).** Reescritos con el estilo del 16b (`archive/2026-10-15-16b-ayuda-contextual/design.md` D9, "Revisión del usuario"): para qué sirve en una oración; cada opción con palabras de todos los días; un ejemplo con nombres y montos reales; tres o cuatro oraciones como máximo. Las reglas citadas no cambian, salvo `cobranzas.observaciones`, que suma SYN-07 por las marcas nuevas de D13.

| # | Clave | Pantalla y campo | Reglas | Texto propuesto |
| --- | --- | --- | --- | --- |
| 1 | `cobranzas.medios` | Alta · Medios de pago | COB-01, COB-02, INV-08 | "Cómo te pagó el cliente. Podés repartir el total entre varios medios, y la suma tiene que dar justo lo que cobraste. Algunos medios, como la transferencia, piden el número de la operación. Ej.: Kiosco La Esquina paga $50.000: $30.000 en efectivo y $20.000 por transferencia (n.º 0042)." |
| 2 | `cobranzas.saldoAFavor` | Alta · Saldo resultante | COB-03, CC-04 | "Lo que el cliente va a deber después de este pago. El pago baja lo que debe en total, no una factura en particular. Si paga de más, le queda plata a favor y se descuenta sola de su próxima compra. Ej.: Kiosco La Esquina debe $150.000 y paga $160.000 → le quedan $10.000 a favor." |
| 3 | `cobranzas.jornada` | Alta y detalle · Jornada | RUT-07 | "Muestra en qué recorrido del vendedor entró este pago. Si lo cobra un vendedor con su jornada abierta, queda en esa jornada y aparece cuando rinde la plata. Lo que se carga desde la oficina no lleva jornada. Ej.: Juan cobra $50.000 en Kiosco La Esquina desde la camioneta 2 → figura en su jornada de hoy." |
| 4 | `cobranzas.anulacion` | Detalle · Anular | COB-05, CC-02 | "Deja el pago sin efecto: el cliente vuelve a deber lo mismo que antes. No se borra: queda como anulado, con el motivo y quién lo anuló. Se anula entero; si te equivocaste en un medio, anulalo y cargalo de nuevo. Ej.: un cheque de $20.000 de Almacén Don Pedro vuelve rechazado → lo anulás y su deuda sube $20.000." |
| 5 | `cobranzas.observaciones` | Detalle · Observaciones | SYN-05, SYN-07, SYN-10, RUT-09 | "Avisos para revisar en un pago que el vendedor cargó sin señal. El pago se tomó igual, porque la plata ya se cobró. *Medio inactivo*: entró plata por un medio que en la oficina dieron de baja (ej.: $10.000 por «Billetera» después de cerrar esa cuenta). *Falta la referencia*: una transferencia llegó sin número de operación. *Permiso revocado*: al vendedor le habían quitado el permiso de cobrar. *Jornada liberada*: su jornada ya se había destrabado desde la oficina. *Cliente no habilitado*: se le cobró a «Consumidor final», que no tiene cuenta." |

**Largo de la clave 5.** Con cinco marcas, el texto pasa de cuatro oraciones (el máximo del estilo). Había dos caminos; el usuario eligió **5b** el 2026-10-15 (tarea 0.2):

- **5a (en la tabla).** Un solo texto con las cinco marcas, una por renglón. Más largo que el resto, pero todo en el mismo lugar.
- **5b ("Ver más", tema nuevo `cobranzas-observaciones`).** El "(?)" queda corto: "Avisos para revisar en un pago que el vendedor cargó sin señal. El pago se tomó igual, porque la plata ya se cobró. Cada aviso dice qué pasó y en qué medio; tocá «Ver más» para ver qué significa cada uno." La página "Ver más" — "Avisos de los pagos cargados sin señal" — lleva las cinco marcas de 5a, cada una con su ejemplo (Billetera; transferencia de $20.000 sin número; vendedor sin permiso; jornada de la camioneta 2 destrabada a las 14:00; «Consumidor final»), y explica que la bandeja para darlas por revisadas llega más adelante. Consecuencia: un tema "Ver más" más (D20 pasaría a "A con un tema nuevo") y su ruta, con el mecanismo del 16b (ADR-051).

Con 5b, la tarea 15.1 suma el tema y la spec `sistema/ayuda-contextual` su escenario; la recomendación es **5b**, porque estas marcas van a crecer con la venta (18a) y la bandeja (25).

## Risks / Trade-offs

- **[Lote 1 toca nueve módulos]** → cambio mecánico de tipos; red de seguridad de la suite completa antes y después; ningún comportamiento cambia.
- **[El camino `OFFLINE` no se puede probar en el navegador hasta el 22a]** → integración y concurrencia por el lote; la prueba manual lo ejercita por API.
- **[`PERMISO_REVOCADO` sin foto (D11-A)]** → un usuario que nunca tuvo el permiso queda con la misma observación; se acepta igual por SYN-05.
- **[Cobranzas tardías sobre una jornada cerrada (D12-A)]** → aceptadas sin marca hasta que el 24 decida.
- **[Observaciones nuevas sin bandeja (D13-C)]** → `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` quedan pendientes y se ven en el detalle de la cobranza; la bandeja para resolverlas llega con el 25.
- **[`venta_id` sin FK]** → el 18a la agrega; la migración aborta si hay filas con venta.

## Migration Plan

Una revisión de Alembic sobre `b5c6d7e8f9a0`: tres tablas, privilegios, índices, siembra idempotente de motivos y ampliación de `ck_observacion__codigo` con los dos códigos de D13. `downgrade` borra las tablas y los motivos de `ANULACION_COBRANZA` y vuelve el `CHECK` atrás (aborta si hay observaciones con los códigos nuevos); una prueba deja escrito que se pierden las cobranzas. Sin cambios de datos en tablas existentes.

## Open Questions

- D3: si la administración carga transferencias atrasadas con frecuencia, conviene B.
- D12: si una cobranza tardía sobre una jornada cerrada debe marcarse ya (B) o esperar al 24.
- D14: cuándo llega la asignación de clientes a vendedores ("sus clientes").
