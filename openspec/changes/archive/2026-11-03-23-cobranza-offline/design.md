# Diseño técnico — 23-cobranza-offline

> **Estado: DECISIONES APROBADAS (tarea 0.1) y TEXTOS APROBADOS (tarea 0.2) el 2026-11-03: el usuario aprobó D0 a D12, todas en la opción A, y todos los textos de interfaz y de ayuda tal como están escritos en este documento (0.2).** Cada decisión tiene dos o tres opciones con sus consecuencias; la recomendada es **A**. Las decisiones se documentan en **ADR-067** (*Propuesto* hasta el archivo, `docs/adr/ADR-067-cobranza-sin-conexion-en-el-telefono.md`).
>
> **Gobernanza.** **CRÍTICA: ninguna** (el servidor no cambia: las reglas de dinero de COB-01 a COB-05 y SYN-05 ya están en ADR-052). **ALTA:** D2 (contrato del sobre de dinero con el servidor), D4 (qué valida el teléfono antes de tomar un pago) y D6 (qué cuenta en el crédito local, deuda de ADR-065). **MEDIA:** D1, D3, D5, D7, D8, D10, D11. **BAJA:** D0, D9, D12. **De negocio** (el agente solo recomienda; decide el usuario): **D0, D3, D4, D6, D7, D9**. Las que más conviene mirar: **D6, D4 (referencia obligatoria) y D7**. **Cambian `docs/`:** D5 (`02` §13.2), D6 (CRE-08, COB-04), D7 (RUT-09, `02` §6.6), D10 (`02` §13.3).
>
> **Revisión.** Decisiones (0.1) y textos (0.2) aprobados antes del apply (2026-11-03). El usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Servidor.** `cobranzas/commands.py` declara `COBRANZA_REGISTRAR` v1 en `ONLINE` y `OFFLINE` (ADR-052): sin conexión el bus valida la jornada del sobre (`JORNADA_REQUERIDA`, `JORNADA_AJENA`, `JORNADA_INEXISTENTE`), anota `PERMISO_REVOCADO` y `JORNADA_LIBERADA`; el servicio rechaza solo lo malformado (`MEDIOS_INVALIDOS`, `MEDIOS_NO_SUMAN_IMPORTE`, contenido), lo inexistente o ajeno (`RECURSO_NO_ENCONTRADO`) y `COBRANZA_DUPLICADA`, y acepta con `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE` y `CLIENTE_NO_HABILITADO`. Lo cubre `tests/integration/test_cobranzas_offline.py`. El bootstrap trae clientes `ACTIVO` y `SUSPENDIDO` (y el consumidor final) con saldo y límite, medios activos con `requiere_referencia` y los permisos (SYN-11). El rol Vendedor/Repartidor ya tiene `REGISTRAR_COBRANZA`.
- **Teléfono (22a a 22d).** `sync/confirmarVentaLocal.ts` y `sync/anularVentaLocal.ts` son el patrón de la transacción local (operación, movimientos, comando, última secuencia); `sync/sobre.ts` arma los sobres; `domain/ruta/disponiblesLocales.ts` concilia por operación con la secuencia procesada y ya suma `COBRANZA_CREDITO`; `sync/aplicarResultados.ts` escribe el estado por `operation_id` y por tipo; `textosDeSincronizacion.ts` traduce con el fixture de códigos; `sync/ventasPendientes.ts` arma «N ventas y M anulaciones sin enviar»; `sync/estadoDeJornada.ts` y `domain/ruta/avisoDeJornada.ts` cortan «Vender» y «Anular venta»; `PasoCobro.tsx` y `armadoDeVentaLocal.ts` ya validan medios, suma y referencia del cobro de una venta. La tabla `cobranzas` (Dexie v3) guarda solo el cobro de una venta (`venta_id` obligatorio, sin estado de envío propio).

Lo que `docs/` **no** resuelve: alcance (D0); si va por la cola (D1); qué se prueba en el servidor (D2); a quién se cobra en el teléfono (D3); qué valida el teléfono (D4); cómo se guarda (D5); la cobranza rechazada en el saldo local (D6, deuda de ADR-065); el corte de «Cobrar» (D7); pantallas (D8); comprobante (D9); pendientes y «Sincronización» (D10); textos (D11); ayuda (D12).

## Goals / Non-Goals

**Goals:** cobrar sin señal con el mismo resultado en el servidor que hoy da el lote; saldo y crédito locales exactos con cobranzas, aunque se pierda una respuesta; que el vendedor vea qué pasó con cada cobranza.

**Non-Goals:** anular cobranzas en el teléfono (COB-05); comprobante (COB-06); cobranzas en la rendición (24); resolver rechazadas (25); cambios en el servidor.

## Decisions

### D0 — Alcance y lotes · alcance · BAJA · de negocio · `04` §11

- **A (recomendada). Un change en tres lotes:** **Lote 1** contrato y núcleo (fixtures y pruebas del servidor, Dexie v5, reglas locales, cobranza local atómica, conciliación, resultados); **Lote 2** pantallas, corte, pendientes, textos y ayuda; **Lote 3** punta a punta, ADR, `propuesta-docs.md`, cobertura, suites y prueba manual. Consecuencia: más chico que el 22d porque el servidor no cambia.
- **B. Cuatro lotes** (servidor aparte). Consecuencia: un subagente más para unas pocas pruebas sin código de producción.

### D1 — En `/ruta` la cobranza va siempre por la cola · técnica · MEDIA · ADR-063 D1, ADR-066 D4, SYN-03

- **A (recomendada).** Con o sin señal se confirma en el teléfono y se encola `COBRANZA_REGISTRAR` v1 `OFFLINE` con la jornada de la sesión; con señal se dispara la sincronización enseguida (como la venta y la anulación). Consecuencia: un solo camino y un solo orden (secuencia); la cobranza cuenta en el saldo local en el acto; el vendedor ve «Sin enviar» unos segundos.
- **B.** Con señal, `POST /cobranzas` (`ONLINE`); sin señal, la cola. Consecuencia: dos caminos; con señal un medio inactivo se rechazaría (`MEDIO_PAGO_INACTIVO`) con la plata ya en la mano; el saldo local tendría que esperar a un bootstrap.

### D2 — Servidor y contrato · técnica · ALTA · SYN-01, SYN-05, SYN-06, INV-17, ADR-052

- **A (recomendada). Sin cambios de código en el servidor.** Fixture `shared/fixtures/sync/cobranza-registrar-offline.json` (sobre `OFFLINE` con un medio, con dos medios y referencia, con observación) que el esquema del lote acepta y que el teléfono arma igual (Vitest). Pruebas de caracterización por el lote con PostgreSQL real: el sobre del fixture aceptado; una venta y una cobranza al mismo cliente en el mismo lote, en orden; un rechazo de la cobranza (cliente inexistente) no corta el lote; doble envío igual; y la lista final de rechazos posibles recorriendo el bus y `registrar_cobranza` (para el fixture de códigos, D11). Si alguna prueba exigiera cambiar el servidor, **detenerse y consultar**. Consecuencia: el contrato queda fijado en los dos lados sin tocar reglas de dinero.
- **B. Solo pruebas del teléfono.** Consecuencia: nada comprueba que el sobre del teléfono sea el que el servidor acepta hasta la prueba manual.

### D3 — A quién se cobra y quién cobra · negocio · MEDIA · COB-01, CLI-03, `01` §19, SYN-10

- **A (recomendada).** «Cobrar» aparece con `REGISTRAR_COBRANZA` en los permisos del bootstrap y datos del día. Se cobra a clientes del bootstrap (`ACTIVO` y `SUSPENDIDO`, sin aviso por el estado), de la cartera o no (la cartera ordena el selector, no restringe). **Al consumidor final no**: no aparece en el selector y su ficha no ofrece «Cobrar» (COB-01: `CONSUMIDOR_FINAL_SIN_CUENTA`; el servidor lo aceptaría con `CLIENTE_NO_HABILITADO` solo como red de seguridad). Un cliente inactivo no está en el teléfono: se cobra desde `/admin`. Sin PIN de supervisor. Consecuencia: el teléfono no genera cobranzas que COB-01 prohíbe.
- **B.** Igual, pero también al consumidor final, que llega con `CLIENTE_NO_HABILITADO`. Consecuencia: contradice COB-01 y deja una observación segura para administración.

### D4 — Qué valida el teléfono antes de encolar · negocio · ALTA · COB-01, COB-02, INV-08, ADR-052 punto 5

- **A (recomendada).** Importe mayor que cero con dos decimales como máximo (`decimal.js`); de 1 a 20 medios activos del bootstrap (el mismo medio puede repetirse), cada uno con importe positivo; **suma igual al importe** (INV-08); **referencia obligatoria** donde el medio la exige (igual que el cobro de una venta en el teléfono; vacía o de solo espacios no vale); observación opcional de hasta 500 caracteres, recortada. Muestra el saldo local actual y el resultante (CRE-08); si el resultante queda **a favor** del cliente, pide confirmar «El cliente queda con {importe} a favor.» antes de guardar. Consecuencia: el teléfono no produce `MEDIOS_NO_SUMAN_IMPORTE` ni `REFERENCIA_FALTANTE`; `MEDIO_INACTIVO` solo aparece si el medio se dio de baja después del bootstrap.
- **B.** Igual, pero la referencia faltante se permite con un aviso (el servidor la acepta con `REFERENCIA_FALTANTE`). Consecuencia: sirve si el cliente transfiere y todavía no tiene el número; cada caso deja una observación pendiente y difiere del cobro de la venta.

### D5 — Cómo se guarda la cobranza en el teléfono · técnica · MEDIA · `02` §13.2, INV-01

- **A (recomendada). Dexie v5 sobre la tabla `cobranzas`**: `'cobranza_id, venta_id, operation_id, cliente_id, jornada_id, estado_envio'` (solo agrega índices; no modifica filas). `CobranzaLocal` suma `origen` (`VENTA` | `INDEPENDIENTE`; una fila sin el campo es de una venta), y para la suelta `venta_id: null`, `cliente_id`, `occurred_at`, `observacion` y `estado_envio`, más los nombres de los medios congelados para el detalle. Una transacción escribe la cobranza, un `COBRANZA_CREDITO` con el `operation_id` de la cobranza, el comando `COBRANZA_REGISTRAR` `OFFLINE` con la siguiente secuencia y la última secuencia; reconfirmar el mismo `cobranza_id` devuelve la existente (identificadores generados al abrir el formulario). `aplicarResultados` escribe el estado en `cobranzas` por `operation_id` cuando el tipo es `COBRANZA_REGISTRAR`. Consecuencia: `cobranzas` es la tabla que `02` §13.2 ya describe con estado de envío; el cambio de versión es aditivo.
- **B. Tabla nueva `cobranzas_sueltas`** (v5). Consecuencia: no toca el tipo del cobro de una venta, pero dos tablas para la misma entidad y `02` §13.2 queda desalineado.

### D6 — La cobranza en el saldo local y la cobranza rechazada · negocio · ALTA · CRE-08, COB-04, SYN-06, SYN-09, ADR-065 D2

- **A (recomendada).** La cobranza cuenta **desde que se confirma** por la regla de CRE-08 (su secuencia contra la secuencia procesada). **Una cobranza suelta «Rechazada» deja de contar.** El servidor solo la rechaza por datos (cliente o medio inexistente, malformado, duplicada, jornada), nunca por reglas de negocio, así que no está en la cuenta del cliente: contarla liberaría crédito que el sistema no reconoce. El cobro de una venta sigue la regla de su venta (ADR-065 D2, sin cambios). Consecuencia: el teléfono nunca muestra más crédito que el real por una cobranza que no existe; el vendedor tiene la plata y avisa a administración (la resolución es del 25).
- **B. La rechazada sigue contando hasta el fin de la jornada** (simétrica con la venta rechazada). Consecuencia: refleja la plata que el vendedor cobró, pero el vendedor puede seguir vendiendo a crédito contra un pago que el sistema no tiene.
- **C. Cuenta solo cuando el servidor la acepta.** Consecuencia: sin señal el cliente que pagó no recupera crédito en todo el día; contradice COB-04.

### D7 — «Cobrar» con la jornada no abierta y la versión mínima · negocio · MEDIA · RUT-09, `02` §6.6, ADR-064, ADR-066

- **A (recomendada).** «Cobrar» se deshabilita igual que «Vender»: con la jornada marcada como no abierta (ADR-066, con el mismo aviso por estado) y por debajo de la versión mínima; «Confirmar cobranza» no confirma y el formulario sigue. La cola se sigue enviando. Los avisos se amplían: «Lo que ya vendiste y cobraste se sigue enviando.» Consecuencia: el teléfono no origina operaciones de una jornada que ya no está abierta (con `EN_RENDICION` el servidor la aceptaría sin observación y RUT-05 quedaría en falso); se cobra desde `/admin` o con una jornada nueva.
- **B. Cobrar sigue habilitado** (el servidor acepta con `JORNADA_LIBERADA`). Consecuencia: la plata se registra igual, pero puede llegar sobre una jornada en rendición o cerrada, que el 24 todavía no sabe tratar.

### D8 — Pantallas · interfaz · MEDIA · COB-01, COB-02, SYN-09

- **A (recomendada).** **Entradas:** «Cobrar» en la ficha del cliente (`/ruta/cobrar?cliente={id}`) y en el inicio (`/ruta/cobrar`, con selector de cliente con la cartera primero, sin el consumidor final). **Pantalla de cobro:** cliente, saldo local actual, importe, medios (el editor de medios del cobro de la venta, extraído para reutilizarlo), observación, saldo resultante; «Confirmar cobranza» con «¿Registrar la cobranza de {importe} a {cliente}?» y, si queda a favor, el aviso de D4. **Guarda:** con datos cargados, salir pide «¿Descartar la cobranza?» y la versión nueva del service worker espera (mismo mecanismo que el carrito). **Después:** «Cobranza guardada» (`/ruta/cobranzas/:id`) con cliente, importe, medios, observación, momento, estado de envío y su explicación (observaciones o rechazo). **«Cobranzas de hoy»** (`/ruta/cobranzas`): las cobranzas sueltas de la jornada con cliente, importe, hora y estado; acceso desde el inicio y desde la ficha. Todo precacheado como el resto de `/ruta`. Consecuencia: el mismo recorrido que la venta; las cobranzas del día se revisan en un lugar.
- **B. Solo desde la ficha**, sin «Cobranzas de hoy» (la cobranza se ve solo en «Sincronización»). Consecuencia: menos pantallas, pero el vendedor no puede revisar lo cobrado en el día.

### D9 — Comprobante · negocio · BAJA · COB-06

- **A (recomendada). Sin comprobante**: COB-06 es de la etapa 2. «Cobranza guardada» muestra los datos en pantalla. Consecuencia: sin trabajo de pdfmake; el cliente no recibe constancia desde el teléfono.
- **B. Un texto para compartir** («Compartir» con cliente, importe, medios y fecha). Consecuencia: adelanta una parte de COB-06 sin su definición.

### D10 — «Sincronización» y pendientes · interfaz · MEDIA · SYN-09, `02` §13.3

- **A (recomendada).** «Sincronización» lista también las cobranzas «Con observaciones» y «Rechazadas» como «Cobranza a {cliente}», con su texto y acceso al detalle. Lo pendiente se dice uniendo las partes que no son cero: «2 ventas, 1 anulación y 1 cobranza sin enviar», «1 cobranza sin enviar», «3 cobranzas sin enviar»; igual en el inicio y en los avisos de cierre de sesión y de pendientes de otro usuario. Consecuencia: lo pendiente nunca omite una cobranza.
- **B.** Un total: «N operaciones sin enviar». Consecuencia: más simple, pero el vendedor no sabe qué falta enviar.

### D11 — Textos de rechazos y observaciones de la cobranza · interfaz · MEDIA · SYN-06, SYN-07

- **A (recomendada).** El fixture `codigos-de-sincronizacion.json` suma `rechazos_de_cobranza` (lista final fijada por la prueba de D2) y `observaciones_de_cobranza` (`MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`, `PERMISO_REVOCADO`, `JORNADA_LIBERADA`, `CLIENTE_NO_HABILITADO`). Textos propuestos (sin ejemplos; se aprueban en 0.2):
  - Rechazos, seguidos de «El cobro no quedó registrado en el sistema y el teléfono ya no lo descuenta de la cuenta del cliente; avisá a administración.»: `RECURSO_NO_ENCONTRADO` «El sistema no tiene el cliente o el medio de pago de la cobranza.» · `COBRANZA_DUPLICADA` «El sistema ya tenía otra cobranza con el mismo identificador.» · `JORNADA_AJENA` «La cobranza es de otra jornada.» · `DISPOSITIVO_REVOCADO` «Este teléfono fue dado de baja; la cobranza quedó para revisión.» · el resto (`MEDIOS_INVALIDOS`, `MEDIOS_NO_SUMAN_IMPORTE`, contenido, tipo, versión, modo, inconsistente, jornada inexistente o requerida) «La cobranza llegó con datos incompletos o inválidos.»
  - Observaciones: `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` reutilizan los textos actuales (con el nombre del medio); `PERMISO_REVOCADO` sin cambio; `JORNADA_LIBERADA` «La jornada había sido liberada cuando llegó la cobranza.»; `CLIENTE_NO_HABILITADO` «El consumidor final no lleva cobranzas sueltas; administración la revisa.»
  Consecuencia: un código nuevo sin texto rompe una prueba, no la pantalla.
- **B. Los textos de la venta** también para la cobranza. Consecuencia: «La venta llegó…» sobre una cobranza confunde.

### D12 — Ayuda contextual · interfaz · BAJA · ADR-051

- **A (recomendada).** Sin ejemplos. **Nuevas:**
  - `ruta.cobrar` — **Cobrar a un cliente**: «Registra un pago del cliente, también sin señal. Baja lo que debe en total y le libera crédito enseguida en el teléfono. Se envía al sistema como las ventas. Si te equivocaste, avisá a administración: la cobranza se anula desde la oficina.» (COB-01, COB-03, COB-04, COB-05, CRE-08, ADR-067)
  - `ruta.cobranzaRechazada` — **Cobranza rechazada**: «El sistema no aceptó la cobranza. En el detalle ves el motivo. El teléfono deja de descontarla de la cuenta del cliente. No se vuelve a enviar sola: avisá a administración.» (SYN-06, SYN-09, ADR-067)
  - `ruta.medios` — **Medios de pago**: «Cómo te pagó el cliente. Podés repartir el importe entre varios medios y la suma tiene que dar justo el importe. Algunos medios piden el número de la operación.» (COB-01, COB-02, INV-08) — versión sin ejemplo de `cobranzas.medios`, que sigue igual en `/admin`.
  - `ruta.saldoDespuesDelCobro` — **Saldo después del cobro**: «Lo que el cliente va a deber después de este pago, según el teléfono. Si paga de más, le queda a favor.» (COB-01, COB-03, CC-04, CRE-08)
  **Revisadas:**
  - `ruta.creditoSinSenal`: «Se calcula con la deuda de la última actualización de datos, más lo que le vendiste y menos lo que le cobraste y le anulaste desde el teléfono después.» (CRE-08, CRE-09, ADR-065, ADR-066, ADR-067)
  - `ruta.sincronizar`: «Envía al sistema las ventas, anulaciones y cobranzas sin enviar de tu usuario, en el orden en que las hiciste. Se hace sola al abrir la aplicación o volver a ella, al volver la señal, después de cada operación y cada 2 minutos. Enviar dos veces lo mismo no lo duplica.» (SYN-02, SYN-03, INV-06)
  - `ruta.observacionesYRechazos`: «Muestra qué anotó el sistema en cada venta, anulación o cobranza enviada y por qué no aceptó las rechazadas. Las observaciones las revisa administración; no tenés que hacer nada. Lo rechazado no se vuelve a enviar solo.» (SYN-04, SYN-07, SYN-08, SYN-09)
  - `ruta.jornadaNoAbierta`: «El sistema avisó que tu jornada ya no está abierta. No podés vender, anular ventas ni cobrar; lo que ya hiciste se sigue enviando. Para seguir, abrí una jornada nueva con señal.» (RUT-09, RUT-03, ADR-066, ADR-067)
  - `ruta.versionMinima`: «Esta versión de la aplicación ya no puede confirmar ventas ni cobranzas nuevas. Lo guardado se sigue enviando. Actualizá la aplicación para seguir.» (ADR-064, ADR-067)
  Consecuencia: ADR-067 existe como *Propuesto* desde la propuesta, así la prueba de IDs citados pasa.
- **B. Reutilizar `cobranzas.medios` y `cobranzas.saldoAFavor` con sus ejemplos** y sin revisar las de ruta. Consecuencia: los textos de crédito, sincronización y jornada dejan de ser ciertos.

## Risks / Trade-offs

- [Venta y cobranza del mismo cliente en el mismo lote] → la secuencia las procesa en orden; prueba de caracterización (D2).
- [Respuesta perdida de una cobranza] → el bootstrap con la secuencia procesada la deja de contar sin depender de la respuesta; el reenvío es idempotente (INV-06).
- [Dexie v5 en teléfonos con datos] → solo agrega índices; prueba de que una v4 con ventas, cobros, anulaciones y cola abre en v5 sin perder nada y las filas viejas siguen como cobro de venta.
- [Medio dado de baja después del bootstrap] → el servidor acepta con `MEDIO_INACTIVO` (ADR-052); el teléfono lo muestra «Con observaciones».
- [Cobranza al cliente que el bootstrap ya no trae] → la cobranza guardada conserva el nombre del cliente para el detalle; el envío no depende del maestro local.

## Migration Plan

Sin migración del servidor ni permisos nuevos. Dexie v5 aditiva. Un servidor anterior ya acepta `COBRANZA_REGISTRAR` `OFFLINE` (change 17), así que el orden de despliegue no importa; volver atrás el frontend deja las cobranzas encoladas en la cola, que la versión anterior sigue enviando (el motor no filtra por tipo) aunque no las muestre.
