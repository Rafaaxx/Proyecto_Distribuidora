# Diseño técnico — 20-nota-de-venta

> **Estado: D0 a D13 APROBADAS por el usuario el 2026-10-27, todas con la opción A recomendada** (incluidas D3 domicilio y teléfono, D4 saldo congelado opcional, D5 marca ANULADA y D12 nombre y leyenda), y aprobados los textos de ayuda de D11 (tarea 0.2). **Cambio de alcance aprobado el mismo día:** la nota no queda atada al monotributo; funciona para los modos impositivos A, B y C tomando el `modo_impositivo` congelado en la venta (D7, D14). **D14 APROBADA el 2026-10-27 (tarea 0.3):** modos A y B en este change (modo B con la opción A recomendada, sin columna "IVA %"); el **modo C queda como deuda nominada a la etapa 4**: la nota de una venta C no se genera y la pantalla avisa que todavía no está disponible (Q1 y Q2 pasan a esa deuda).
>
> **Ampliación de alcance 2026-10-28 (D15):** el usuario aprobó, tras la prueba manual, que el nombre y el CUIT de la organización se puedan editar desde Configuración (ampliación posterior del mismo día: antes solo el CUIT, dentro de Nota de venta). **D15 fue aprobada el mismo día** (comando propio, sección propia, solo largo del CUIT, sin ayuda); ver D15.
>
> **Gobernanza por dominio.** El change no mueve libros ni dinero: lee una venta congelada y agrega tres parámetros de configuración. **ALTO** (se propone y se espera revisión): **D2** (contrato de la lectura), **D4** (qué saldo se imprime), **D5** (marca de anulada). **MEDIO:** D1, D3, D7, D8, D10. **BAJO:** D0, D6, D9, D11, D12, D13. **De negocio** (el agente no decide; solo recomienda): **D3, D4, D5, D6, D7, D12, D14**. D14 es **MEDIO** (presentación de datos congelados; no mueve libros ni dinero).

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Venta congelada** (18a, 18b, 19): `venta` con `numero`, `occurred_at`, `cliente_id`, `usuario_id`, `modo_impositivo` (congelado; siempre `A` en la etapa 1 porque `ventas/domain/calculo.py` rechaza B y C con `MODO_IMPOSITIVO_NO_SOPORTADO` hasta la etapa 4), `total_neto`, `total_iva` (cero en modo A), `total` (`total = total_neto + total_iva`, INV-14), `estado`, y el snapshot de crédito `credito_saldo_considerado` (nulo antes del 18b; con conexión lo calcula el servidor con el saldo bloqueado, sin conexión es la evaluación del dispositivo). `venta_linea` con `cantidad`, `unidades_presentacion`, `precio_referencia`, `unidades_referencia`, `importe_bruto`, `importe_descuento`, `importe_neto`, `alicuota` e `importe_iva` congelados (VTA-03; IVA cero en modo A), y `venta_linea_descuento`. `venta_anulacion` con momento, motivo y `devuelve_dinero`. `GET /ventas/{id}` (`VENDER` o `ANULAR_VENTA`) devuelve casi todo, pero no los datos de la organización ni del cliente (documento, dirección) ni los medios de la cobranza.
- **Frontend**: `domain/ventas/presentacion.ts::textoDeCantidadDeLinea` (CAT-08), `domain/ventas/calculoDeVenta.ts::calcularBrutoDelPedido` (PRC-22, con fixtures compartidos) y `calcularSaldoResultanteDeVenta` (CRE-02), `lib/money.ts::formatearImporte`, `lib/fecha.ts::formatearFechaHoraEnZona`, `lib/descarga.ts::guardarArchivo`. La pantalla "Venta registrada" (`VentaFormScreen`) y `VentaDetalleScreen`. `pdfmake` **no está instalado**.
- **Configuración**: `configuracion_organizacion` (módulo `identidad`) con el patrón `router_parametros` (`/configuracion/descuento-manual`, `/configuracion/credito`) y comandos `*_CONFIGURAR` con `ADMIN_CONFIGURACION` y auditoría del valor anterior y el nuevo. `organizacion` tiene `nombre` y `cuit` (opcional, sembrado nulo; no hay comando que los edite: el del nombre y el CUIT se agrega en D15).
- **ADR-008**: nombre "Nota de venta", leyenda "Documento no válido como factura", pdfmake en el dispositivo, Web Share API y descarga en escritorio, la misma función para reimprimir; nombre y leyenda "se validan con el contador antes de implementar" (también ADR-007). **ADR-045**: una organización no inscripta (monotributo) vende en modo A, a precio final, sin IVA discriminado. **ADR-009** y **VTA-04**: modo A sin IVA en la venta; modo B, IVA de línea `neto × alícuota` redondeado a 2 decimales y total neto más IVA; modo C, precio con IVA incluido y neto derivado dividiendo por `1 + alícuota` (B y C operativos en la etapa 4; el modelo los soporta desde la etapa 1).

Lo que `docs/` **no** resuelve (cada punto es una decisión):

- Dónde se arma la nota y con qué datos, para que el 22a la genere sin conexión con la misma función. → D1, D2.
- VTA-13 dice "datos de la organización", pero la organización solo tiene nombre y CUIT. → D3.
- VTA-13 dice "saldo resultante si la organización lo configura", pero no existe ese parámetro ni se dice qué saldo es en una reimpresión. → D4, D10.
- ADR-058 deja al 20 la marca de la venta anulada. → D5.
- Nada dice si la reimpresión se distingue del original, ni las columnas ni el tamaño de página. → D6, D7.
- La carga de pdfmake (tamaño del bundle, fuentes) y el comportamiento de Web Share API. → D8, D9.
- La validación del nombre y la leyenda con el contador. → D12.
- Cómo se presenta el IVA de una venta de modo B o C en la nota (VTA-13 no lo dice; VTA-04 solo define el cálculo). → D14 (B resuelto; C diferido a la etapa 4).

## Goals / Non-Goals

**Goals:** una sola función pura que arma la nota a partir de datos neutros de la venta y la convierte en PDF; compartir o descargar desde `/admin`; reimpresión desde el detalle; parámetros de la nota administrables; contrato que el 22a reutiliza con un adaptador desde Dexie.

**Non-Goals:** generación sin conexión (22a); precarga del módulo de PDF y de las fuentes en el service worker (21); plantillas por organización; impresoras térmicas; comprobante de cobranza (COB-06); facturación; alta autoservicio de organizaciones (onboarding, `00` §6.4, etapa 4).

## Decisions

### D0 — Tamaño y lotes · técnica · BAJO

- **A (recomendada). Un change en tres lotes**, sin frenar entre lotes salvo en los puntos de control: **Lote 1** dominio puro de la nota y del documento PDF, dependencia `pdfmake`, compartir y descargar; **Lote 2** migración, comando `NOTA_VENTA_CONFIGURAR` y lectura `GET /ventas/{id}/nota`; **Lote 3** pantallas, ayuda, cobertura, ADR, docs y prueba manual. Consecuencia: entra en el tamaño de `04` §2 (uno a dos días).
  **Aprobada (A), 2026-10-27.**
- **B. Dividir en 20a (PDF y lectura) y 20b' (configuración).** Consecuencia: la nota sale primero sin saldo ni domicilio; un change más y el nombre `20b` ya está tomado.
- **C. Sin configuración: saldo siempre visible.** Consecuencia: contradice VTA-13 ("si la organización lo configura").

### D1 — Dónde y cómo se arma la nota · arquitectura · MEDIO

**Contexto.** `02` §13.6: en el dispositivo, "a partir de los datos locales de la venta", y "la misma función" desde administración.

- **A (recomendada). Tres piezas en el frontend.** (1) `domain/ventas/notaDeVenta.ts::armarNotaDeVenta(datos: DatosDeNotaDeVenta): ContenidoDeNota`, pura, sin pdfmake ni React: recibe un tipo neutro (organización, cliente, venta, líneas, descuentos, cobranza, saldo, anulación, zona horaria) y devuelve el contenido ya formateado (textos, filas y totales con `formatearImporte`). (2) `lib/nota/documento.ts::documentoDeNota(contenido)`, pura, devuelve la definición de documento de pdfmake. (3) `lib/nota/pdf.ts::generarPdfDeNota(contenido): Promise<Blob>` carga pdfmake bajo demanda (D8). Adaptadores: `features/ventas/nota.ts::datosDeNotaDesdeApi(respuesta)` en este change; el 22a agrega `datosDeNotaDesdeDexie`. Consecuencia: las reglas de contenido se prueban sin PDF; el 22a no toca el armado.
  **Aprobada (A), 2026-10-27.**
- **B. Generar el PDF en el servidor** (Python). Consecuencia: contradice `02` §13.6 y ADR-008; no sirve sin conexión.
- **C. Armar el PDF directamente desde `VentaDetalleResponse`.** Consecuencia: acopla la nota a la forma de la API; el 22a tendría que imitar esa forma desde Dexie, y faltan datos (organización, cliente, medios).

### D2 — Lectura de los datos de la nota · contrato · ALTO

- **A (recomendada). `GET /api/v1/ventas/{venta_id}/nota`**, con `VENDER` o `ANULAR_VENTA` (como el detalle, D13), 404 si no existe o es de otra organización (INV-21, SEG-07). Devuelve en una llamada: `organizacion` (`nombre`, `cuit`, `domicilio`, `telefono`), `zona_horaria`, `muestra_saldo`; `cliente` (`nombre`, `razon_social`, `documento_tipo`, `documento_numero`, `direccion`, `es_consumidor_final`); `numero`, `occurred_at`, `vendedor_nombre`, `modo_impositivo`, `estado`; `lineas` en su orden (producto y presentación por nombre, `cantidad`, `unidades_presentacion`, `precio_referencia`, `unidades_referencia`, `importe_bruto`, `importe_descuento`, `importe_neto`, `alicuota`, `importe_iva`, todos congelados); `total_neto`, `total_iva`, `total`; `cobranza` (`importe`, `estado`, `medios`: nombre e importe, sin referencias) o nulo; `saldo_resultante` (D4) o nulo; `anulacion` (`anulada_en`, `motivo_nombre`, `devuelve_dinero`) o nulo. Sin costos ni crédito. Importes como string (INV-03). Lo arma `ventas/queries.py`, con los datos ajenos por `service.py` de `identidad`, `clientes`, `cobranzas` y `configuracion` (contratos de `lint-imports` existentes). Tras confirmar con conexión, "Venta registrada" lee esta misma ruta. Consecuencia: una sola fuente, idéntica al original y a la reimpresión.
  **Aprobada (A), 2026-10-27.**
- **B. Ampliar `GET /ventas/{id}`** con organización, cliente y medios. Consecuencia: engorda una lectura que usa el listado y el detalle, y mezcla datos de impresión con datos de gestión.
- **C. Componer en el frontend** con el detalle más lecturas de configuración, cliente y cobranza. Consecuencia: cuatro llamadas; la de configuración exige `ADMIN_CONFIGURACION`, que el vendedor no tiene.

### D3 — Datos de la organización en la nota · negocio · MEDIO

- **A (recomendada).** Nombre y CUIT (si existe) de `organizacion`, más **domicilio y teléfono opcionales** que se cargan en la configuración de la nota (D10). Sin condición frente al IVA: la nota no es un comprobante fiscal (ADR-007, ADR-045), y cómo se presenta el IVA lo decide el modo congelado en la venta (D14), no la condición actual de la organización. Consecuencia: el cliente sabe a quién le compró y cómo comunicarse; se agregan dos textos libres.
  **Aprobada (A), 2026-10-27.**
- **B. Solo nombre y CUIT.** Consecuencia: sin cambios de datos, pero la nota no trae domicilio ni teléfono.
- **C. Datos fiscales completos** (razón social, ingresos brutos, inicio de actividades, condición frente al IVA). Consecuencia: es materia del módulo de facturación (Factura C) y puede confundir la nota con una factura.

### D4 — Saldo resultante · negocio · ALTO

**Contexto.** VTA-13: "saldo resultante si la organización lo configura". CRE-02: saldo resultante = saldo actual + total − cobranza registrada con la venta.

- **A (recomendada).** Parámetro `nota_venta_muestra_saldo`, **por defecto no** (lectura literal de VTA-13). Si está activo, la nota muestra "Saldo de la cuenta después de esta venta" = `credito_saldo_considerado + total − cobranza de la venta` (CRE-02), calculado en el servidor por una función pura `ventas/domain/nota.py::saldo_de_la_nota` (fórmula CRE-02 con `core/money.py`, la misma de `clientes/domain/credito.py`, sin importar el dominio ajeno), que también decide cuándo se omite. No se muestra: al consumidor final (no tiene cuenta, CLI-03), en una venta sin snapshot (anterior al 18b) ni en una venta anulada (D5). Consecuencia: la reimpresión reproduce exactamente el saldo de la nota original, con conexión (saldo del servidor) y sin conexión (saldo que vio el dispositivo, que es el que el 22a imprimirá); un saldo a favor se muestra como tal.
  **Aprobada (A), 2026-10-27.**
- **B. El saldo que el servidor dejó al procesarla** (`comando.resultado.saldo`). Consecuencia: exacto para el servidor, pero en una venta sin conexión difiere de la nota que se entregó en la calle.
- **C. El saldo actual al reimprimir.** Consecuencia: la misma nota cambia con el tiempo y deja de describir la venta.

### D5 — Nota de una venta anulada · negocio · ALTO (deuda de ADR-058)

- **A (recomendada).** Se genera igual, con **marca visible**: la palabra "ANULADA" en diagonal en cada página y, debajo del encabezado, "Venta anulada el {fecha y hora}. Motivo: {motivo}." más "Se devolvió lo cobrado." o "Lo cobrado quedó a favor del cliente." cuando hubo cobranza (VTA-22). No muestra saldo. Consecuencia: el documento no se puede usar como constancia de una venta vigente, y sirve para entregar al cliente la constancia de la anulación.
  **Aprobada (A), 2026-10-27.**
- **B. No se genera** (botones ocultos en una venta anulada). Consecuencia: más simple, pero el cliente no recibe constancia y una nota vieja compartida antes de anular sigue circulando igual.
- **C. Sin marca.** Consecuencia: la reimpresión de una venta anulada es indistinguible de una vigente.

### D6 — Reimpresión · negocio · BAJO

- **A (recomendada). Idéntica al original** (misma función y mismos datos; ADR-008). Consecuencia: un solo formato; la única diferencia posible es la marca de D5.
  **Aprobada (A), 2026-10-27.**
- **B. Con la leyenda "Reimpresión" y su fecha.** Consecuencia: distingue copias, pero obliga a saber si es la primera generación, dato que no existe (la nota no se guarda).

### D7 — Contenido, columnas y página · negocio · MEDIO

- **A (recomendada).** Página **A4 vertical** (se comparte por WhatsApp y se imprime en la oficina). Encabezado: "Nota de venta", número, fecha y hora en la zona de la organización (TR-04), vendedor; organización (D3); cliente: nombre, razón social, documento y dirección si existen, o "Consumidor final". Tabla de líneas en su orden: **Cantidad** (`textoDeCantidadDeLinea`, CAT-08), **Producto** (producto · presentación), **Precio** (por presentación: `calcularBrutoDelPedido(precio_referencia, unidades_referencia, unidades_presentacion)`, PRC-22), **Bruto**, **Descuento** (importe de la línea; vacío si es cero), **Importe** (neto). Totales: Subtotal (suma de brutos), Descuentos (suma, si hay) y **Total**; las filas de IVA dependen del `modo_impositivo` congelado en la venta (D14): en modo A no hay ninguna (VTA-04, ADR-045). Cobranza: "Cobrado" con cada medio e importe, o "Sin cobro en el acto". Saldo (D4). Pie: la leyenda (D12). Sin nombres de reglas de descuento, autorizadores, costos ni crédito. Consecuencia: el precio por presentación es el mismo que mostró la pantalla de venta; el bruto de la línea es el congelado y puede diferir en centavos del precio × cantidad (PRC-22 redondea una vez).
  **Aprobada (A), 2026-10-27.**
- **B. Sin columna de precio** (cantidad, producto, bruto, descuento, neto). Consecuencia: sin diferencias de centavos, pero el cliente no ve el precio unitario.
- **C. Formato ticket de 80 mm.** Consecuencia: preparado para impresoras térmicas, fuera de alcance, y poco legible al compartirlo.

### D8 — pdfmake y fuentes · técnica · MEDIO

- **A (recomendada).** `pdfmake` en `dependencies` con **versión exacta** (sin `^`), la última estable al instalar, con las fuentes Roboto embebidas que trae (`vfs_fonts`) y `@types/pdfmake` si la versión no trae tipos; se registra en ADR-059. Se carga con `import()` dinámico solo al generar la nota, para no sumar su peso al bundle inicial; el 21 precarga ese fragmento para el uso sin conexión. Instalar la dependencia exige reconstruir la imagen de Docker del frontend. Consecuencia: primera generación con una espera breve; ningún costo para quien no genera notas.
  **Aprobada (A), 2026-10-27.**
- **B. Importación estática.** Consecuencia: todo `/admin` carga pdfmake y sus fuentes desde el inicio.
- **C. Fuentes propias embebidas.** Consecuencia: más peso y una tarea de fuentes sin necesidad.

### D9 — Compartir y descargar · técnica · BAJO

- **A (recomendada).** `lib/nota/compartir.ts`: "Compartir nota" aparece solo si `navigator.canShare?.({ files: [archivo] })` es verdadero, y llama a `navigator.share({ files, title })`; si el usuario cancela (`AbortError`) no pasa nada; otro error muestra un aviso y ofrece descargar. "Descargar nota" está siempre (respaldo, `04` §9) y usa `guardarArchivo`. Nombre del archivo: `nota-de-venta-{numero}.pdf`. Consecuencia: en el teléfono se comparte; en escritorio se descarga (ADR-008).
  **Aprobada (A), 2026-10-27.**
- **B. Un solo botón que intenta compartir y si no descarga.** Consecuencia: en el teléfono no hay forma de bajar el archivo cuando compartir falla en silencio.

### D10 — Configuración de la nota · contrato · MEDIO

- **A (recomendada).** Migración: `configuracion_organizacion` suma `nota_venta_muestra_saldo boolean NOT NULL DEFAULT false`, `nota_venta_domicilio text NULL` y `nota_venta_telefono text NULL`, con `CHECK` de longitud (domicilio hasta 200, teléfono hasta 50, sin cadena vacía). Comando `NOTA_VENTA_CONFIGURAR` v1, solo `ONLINE`, permiso `ADMIN_CONFIGURACION`, contenido (`extra="forbid"`) `muestra_saldo` (booleano estricto), `domicilio` y `telefono` (texto recortado o nulo; vacío pasa a nulo; demasiado largo `DATO_DE_NOTA_INVALIDO`, 422). Rutas `GET` y `POST /api/v1/configuracion/nota-de-venta` en `router_parametros`. Auditoría del valor anterior y el nuevo (AUD-01). Enviar los mismos valores se acepta (como `CREDITO_ORGANIZACION_CONFIGURAR`). Pantalla "Nota de venta" en Configuración. Consecuencia: sigue el patrón de los parámetros existentes; columnas con prefijo porque hoy solo las usa la nota.
  **Aprobada (A), 2026-10-27.**
- **B. Domicilio y teléfono en `organizacion`, con un comando de datos de la organización.** Consecuencia: más general, pero abre la edición de nombre y CUIT, que no está pedida.

### D11 — Ayuda contextual · BAJO

Claves nuevas en `ayuda/textos.ts`, **sin ejemplos**, citando su regla (ADR-051): `ventas.notaDeVenta` (qué es, que no es factura y que es la misma al reimprimir; VTA-13, ADR-008), `ventas.notaAnulada` (qué muestra la nota de una venta anulada; ADR-058, ADR-059), `configuracion.notaMuestraSaldo` (qué saldo se imprime y cuándo no; VTA-13, CRE-02) y `configuracion.notaDatosOrganizacion` (domicilio y teléfono; VTA-13). Textos aprobados por el usuario en la tarea 0.2 (2026-10-27). El 2026-10-28, al revisar los textos, el usuario quitó `ventas.compartirNota` (compartir o descargar) por obvia.

### D12 — Nombre y leyenda · negocio · BAJO

- **A (recomendada).** Se usan los de ADR-008 ("Nota de venta", "Documento no válido como factura") en una sola constante del dominio; aprobados por el usuario en la tarea 0.1 (2026-10-27). Consecuencia: cambiarlo después es tocar una constante y su prueba.
  **Aprobada (A), 2026-10-27.**
- **B. Leyenda configurable por organización.** Consecuencia: es una plantilla por organización, fuera de alcance (`00` §5).

### D13 — Permisos · BAJO

- **A (recomendada).** Sin permiso nuevo: la lectura de la nota y los botones exigen `VENDER` o `ANULAR_VENTA`, igual que el detalle (cualquier venta de la organización); la configuración, `ADMIN_CONFIGURACION`. Consecuencia: un vendedor reimprime cualquier venta, como hoy ve cualquier detalle; acotarlo a "sus clientes" llega con el 20b si se decide.
  **Aprobada (A), 2026-10-27.**
- **B. Permiso nuevo `REIMPRIMIR_NOTA`.** Consecuencia: un permiso más en el catálogo y en los roles, sin un caso que lo pida.

### D14 — IVA en la nota según el modo impositivo congelado · negocio · MEDIO · **APROBADA 2026-10-27 (tarea 0.3): A y B ahora, C diferido a la etapa 4**

**Contexto.** El usuario pidió (2026-10-27) que la nota no quede atada al monotributo: debe servir para los modos A, B y C. VTA-03 congela en cada línea `alicuota` e `importe_iva`, y la venta congela `modo_impositivo`, `total_neto`, `total_iva` y `total` (INV-14). La nota **usa siempre el modo congelado de la venta**, nunca la condición frente al IVA ni el modo actuales de la organización (INV-10): una venta de modo A sigue saliendo en modo A aunque la organización pase a responsable inscripto. Todo lo que sigue se arma en `armarNotaDeVenta` con los datos que ya viajan (D2, con `alicuota` por línea), así el 22a lo hereda sin conexión. Hoy ninguna venta real es de modo B o C (`calculo.py` los rechaza hasta la etapa 4): las pruebas de esos modos usan ventas fabricadas.

- **A (recomendada).**
  - **Modo A:** sin filas de IVA; Total = `total` congelado (igual a la suma de netos, VTA-04). Es lo ya descrito en D7.
  - **Modo B (IVA discriminado):** las líneas muestran sus importes netos congelados (las seis columnas de D7). Totales: Subtotal, Descuentos (si hay), **Neto** (`total_neto`), una fila **"IVA {alícuota} %"** por cada alícuota presente en la venta, en orden de alícuota descendente, con la **suma de `importe_iva` congelado de las líneas de esa alícuota** (incluida la de 0 % si hay líneas con esa alícuota), y **Total** (`total`). La suma de las filas de IVA es `total_iva` porque el IVA de la venta es la suma de los IVA de línea (VTA-04 modo B). No se recalcula IVA sobre la suma de netos por alícuota (eso es FAC-08, del módulo de facturación, y podría diferir en centavos del total congelado).
  - **Modo C (IVA contenido) — diferido a la etapa 4 (deuda).** `docs/` no define qué guardan las columnas de la línea en modo C ni el rótulo del IVA contenido (Q1, Q2), y la alternativa que no inventa reglas es no presentarlo todavía: `armarNotaDeVenta` **rechaza** una venta de modo C con un error de dominio propio del frontend (`NotaNoDisponibleParaModoC`, código estable `NOTA_MODO_C_NO_DISPONIBLE`), y las pantallas, en lugar de los botones de la nota, muestran el aviso "La nota de venta todavía no está disponible para ventas con IVA incluido (modo C)." La lectura `GET /ventas/{id}/nota` **no** rechaza por modo (devuelve los datos congelados; la presentación es del frontend), así la etapa 4 solo completa el armado. Presentación prevista, a confirmar en la etapa 4 junto con Q1 y Q2: líneas y Total con IVA incluido y, debajo del Total, el IVA contenido por alícuota y su suma (`total_iva`), sin fila de neto.
  - El porcentaje se formatea desde la alícuota congelada (fracción `numeric(9,6)`: `0.210000` → "21 %", `0.105000` → "10,5 %") con `decimal.js`, sin pasar por `number`.
  - Consecuencia: la nota describe la venta tal como se registró en cualquier modo; no agrega fixtures compartidos (es presentación de sumas de valores congelados, sin gemela en Python; el servidor solo devuelve los datos).
  **Aprobada 2026-10-27:** modo A y modo B como se describen (opción A, sin columna "IVA %"; Q0 cerrada); modo C como deuda de la etapa 4 con rechazo y aviso (alternativa prevista en Open Questions).
- **B. Igual que A, más una columna "IVA %" en la tabla de líneas en los modos B y C.** Consecuencia: el cliente ve qué alícuota tiene cada producto; la tabla pasa a siete columnas en esos modos. Descartada.
- **C. Solo modo A en este change; B y C rechazados con un aviso hasta la etapa 4.** Consecuencia: contradice el pedido del usuario del 2026-10-27. Descartada.

### D15 — Nombre y CUIT de la organización editables · contrato · MEDIO · **APROBADA 2026-10-28**

**Contexto.** En la prueba manual (2026-10-28) el CUIT no aparecía en la nota: `organizacion.cuit` es nulo (la siembra de `seed.py` lo deja en `None`) y no existe pantalla ni comando que lo cargue; tampoco existe uno que corrija el `nombre`, que se imprime en el encabezado. El armado ya lo imprime solo si existe (D3), así que falta poder cargarlo. **El usuario aprobó (2026-10-28) incorporar a este change la edición del nombre y del CUIT de la organización** (ampliación posterior del mismo día: antes solo el CUIT): campos "Nombre" (obligatorio) y "CUIT" (opcional); se guardan en `organizacion.nombre` y `organizacion.cuit` (módulo `identidad`), **no** en una columna nueva de `configuracion_organizacion`; se normaliza a dígitos como el CUIT del proveedor (`importacion/domain/proveedores.py`, `clientes/domain/ficha.py`: se descartan guiones y espacios, no puntos), exige exactamente 11 dígitos y vacío pasa a nulo; el nombre se recorta, no puede quedar vacío y tiene un máximo de 200 caracteres (el mismo de `nota_venta_domicilio`); por el bus, con `ADMIN_CONFIGURACION`, auditoría del valor anterior y el nuevo, rechazo `OFFLINE`, doble envío idempotente y otra organización intacta (mismo patrón que `NOTA_VENTA_CONFIGURAR`). **La alta autoservicio de organizaciones (onboarding) sigue fuera de alcance** (`00` §6.4, etapa 4).

- **A (aprobada). Editar `organizacion.nombre` y `organizacion.cuit`** con las validaciones de arriba. Sin migración (la columna `cuit text NULL` existe desde la etapa 0). Consecuencia: el dato queda donde ya vive y donde lo lee la lectura de la nota (D2), sin duplicarlo.
- **B. Columna `nota_venta_cuit` en `configuracion_organizacion`.** Descartada por el usuario: duplicaría el CUIT (y el nombre) de `organizacion` y la nota podría imprimir uno distinto del que figura en la organización.

**Decisión del usuario (2026-10-28): D15 APROBADA.**

- **(a1) Comando:** separado, **`ORGANIZACION_DATOS_CONFIGURAR` v1** (`ONLINE`, `ADMIN_CONFIGURACION`) con `nombre` y `cuit` juntos (`extra="forbid"`), por `POST /api/v1/configuracion/organizacion` y su `GET`. Auditoría propia (`entidad='organizacion'`, `entidad_id` = la organización, `antes`/`despues` con `nombre` y `cuit`). `NOTA_VENTA_CONFIGURAR` no cambia. Un nombre o CUIT inválido rechaza todo el comando (ninguno de los dos se guarda).
- **(a2) Ubicación:** sección propia **"Datos de la organización"** en Configuración, en `/admin/configuracion/organizacion`, con su enlace en `ConfiguracionArea`, solo con `ADMIN_CONFIGURACION`. "Nota de venta" conserva "mostrar saldo", domicilio y teléfono.
- **(b) Validación del CUIT:** solo normalización a dígitos (se descartan guiones y espacios; los puntos no se aceptan) y largo exacto de 11; **sin dígito verificador**, igual que el CUIT del proveedor y el documento CUIT del cliente (CLI-05).
- **(c) Ayuda:** **ninguna.** No hay clave nueva (`configuracion.datosOrganizacion` no se crea) y el texto de `configuracion.notaDatosOrganizacion` queda **sin cambios** (el usuario: "no hace falta ninguna ayuda").
- **Códigos de error (decididos por el agente, a revisar con el apply):** `CUIT_INVALIDO` y `NOMBRE_DE_ORGANIZACION_INVALIDO` (422), propios de `identidad` (errores de dominio con `DomainError`). No se reutilizan los existentes: `CUIT_INVALIDO` es del módulo `proveedores` y `NOMBRE_INVALIDO` de `catalogo` y `clientes`, cada uno definido en su propio dominio, y un módulo no importa el dominio de otro (`lint-imports`); un código con el nombre de la entidad evita ambigüedad en el cliente.

## Risks / Trade-offs

- [pdfmake en jsdom] La generación real puede no correr en el entorno de Vitest → las pruebas cubren `armarNotaDeVenta` y `documentoDeNota` (puros); una prueba de humo genera el PDF en Node y verifica la cabecera `%PDF`; la prueba manual cierra el resto.
- [Peso del bundle] pdfmake y sus fuentes pesan del orden de 1 MB → carga dinámica (D8) y `npm run build` revisa que el fragmento quede aparte.
- [Web Share API desigual] Algunos navegadores no comparten archivos → "Descargar nota" siempre visible (D9).
- [Saldo sin snapshot] Ventas anteriores al 18b no tienen `credito_saldo_considerado` → la nota omite el saldo (D4); solo afecta datos de desarrollo.
- [Nombre y leyenda sin validar] ADR-007 y ADR-008 piden validarlos con el contador → punto de control 0.1 (D12).
- [Modo B sin ventas reales] Hasta la etapa 4 no hay ventas B → las pruebas usan datos fabricados (tipo neutro en el frontend, filas insertadas directamente en la base en la integración); la etapa 4 debe repetir la prueba manual con ventas reales.
- [Modo C sin nota] Una venta de modo C no tiene nota hasta la etapa 4 → hoy no existen (la confirmación las rechaza), así que no afecta la operación; queda como **deuda nominada a la etapa 4** (Q1 semántica de las columnas de la línea en modo C, Q2 rótulo y leyenda del IVA contenido, validados con el contador si corresponde), registrada en ADR-059 y en la propuesta de cambios a `docs/` (tarea 10.2, `04` §9). El rechazo explícito evita que la etapa 4 habilite C en la confirmación sin completar la nota sin que se note: la prueba de rechazo falla y obliga a revisarla.
- [Domicilio y teléfono fuera del bootstrap] Sin conexión el 22a necesita estos datos → deuda nominada al 21 (bootstrap con los parámetros de la nota).

## Migration Plan

Una revisión de Alembic suma las tres columnas con su `DEFAULT` y sus `CHECK`; el `downgrade` las quita (no hay datos que se pierdan salvo los textos cargados). Sube y baja limpia sobre una base con ventas (`04` §2.1 punto 4). Sin cambios de privilegios: `app_runtime` ya tiene `UPDATE` sobre `configuracion_organizacion`. Tras instalar `pdfmake`, reconstruir la imagen del frontend (`docker compose build frontend`).

## Open Questions

**D15 (2026-10-28) aprobada por el usuario** (comando `ORGANIZACION_DATOS_CONFIGURAR`, sección "Datos de la organización", CUIT sin dígito verificador, sin ayuda); no deja preguntas abiertas. D0 a D14 están aprobadas (2026-10-27). **Q0 cerrada** en la tarea 0.3: el desglose del modo B es la suma de los IVA de línea congelados, una fila por alícuota presente incluida la de 0 %, en orden descendente, sin columna "IVA %" (opción A). **Q1 y Q2 no se resuelven en este change: pasan a la deuda del modo C de la nota, nominada a la etapa 4** (ver D14 y Risks):

- **Q1 (modo C, semántica de las columnas; deuda etapa 4).** VTA-04 dice que en modo C "el precio incluye IVA y el neto de línea se deriva dividiendo por `1 + alícuota`", y `03` §4 exige `importe_neto = importe_bruto − importe_descuento`. `docs/` no define si en modo C `precio_referencia`, `importe_bruto` e `importe_descuento` se guardan con IVA o sin IVA, ni cómo se reparte el redondeo entre neto e IVA de la línea. La nota necesita mostrar precio, bruto, descuento e importe **con IVA**: o se guardan así, o se derivan (por ejemplo, importe con IVA = `importe_neto + importe_iva`), y la derivación del precio y del bruto con IVA no está definida. Es una decisión de la etapa 4 que hay que tomar (o adelantar con un ADR) antes de implementar el modo C de la nota.
- **Q2 (modo C, rótulo y leyenda; deuda etapa 4).** ¿Cómo se rotula el IVA incluido ("IVA contenido", por alícuota o solo el total) y lleva alguna leyenda adicional? `docs/` no lo dice; si responde a una exigencia normativa para comprobantes al consumidor, se valida con el contador (como ADR-007 y ADR-008 hicieron con el nombre y la leyenda).

Decisión de 0.3 (2026-10-27): se tomó esa alternativa. Se implementan A y B; la nota de una venta C no se genera y la pantalla lo avisa, hasta que la etapa 4 resuelva Q1 y Q2.
