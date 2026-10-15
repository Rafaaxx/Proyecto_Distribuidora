# Diseño técnico — 16b-ayuda-contextual

> **Estado: D0 a D10 APROBADAS por el usuario el 2026-10-15, opción A en todas.** En D9 el usuario pidió textos más simples: valen los de "Revisión del usuario" (27 claves; la 3 `descuentos.operador` eliminada). Lo aprobado se documenta en **ADR-051** (estado *Propuesto* durante el apply).
>
> **Gobernanza por dominio.** No hay backend, base, permisos ni lógica de negocio: todo es **BAJO** (D0, D2 a D8: componente, archivo, rutas) salvo **MEDIO** en **D1** (adelanta una funcionalidad de la etapa 4), **D9** (el contenido de los textos explica reglas de negocio: un texto equivocado enseña mal una regla, sobre todo en descuentos y topes, cuyo dominio es crítico) y **D10** (un punto nuevo en la definición de terminado de todos los changes). El usuario revisa el texto de cada clave de D9 antes de cerrar el change.

## Context

Ver `proposal.md` (Why). Lo que existe y este change usa:

- **Componentes base** en `frontend/src/components/ui/`: `Campo` (`Field.tsx`: etiqueta, control y error con `htmlFor` conectado; la etiqueta es un `string`), `Dialogo` (modal, sin cierre por Escape ni clic afuera), `Boton`, `Tarjeta`, `Tabla`, `Alerta`, `Insignia`, `EncabezadoDePagina`. No hay ningún popover ni tooltip.
- **Stack** (`CLAUDE.md` §2): React, TypeScript estricto, Tailwind, React Router; pruebas con Vitest, Testing Library (`@testing-library/react`, `user-event`, `jest-dom`) y jsdom. No hay librería de popover (Radix, Floating UI, Headless UI).
- **Rutas:** `/admin/*` con `AdminLayout` (menú armado por permisos, ADR-027) y áreas cargadas con `Suspense`; `/ruta/*` hoy es una sola pantalla sin contenido de negocio.
- **Textos de presentación** ya separados de las pantallas en `frontend/src/domain/*/presentacion.ts` (por ejemplo, las causas de "sin precio" y las señales del borrador en `domain/precios/presentacion.ts`): la ayuda no los reemplaza, los acompaña.
- **Reglas** con ID estable en `docs/01-dominio.md` (tabla `| ID | Regla | Etapa |`) y ADR numerados en `docs/adr/`. ADR-050 precisa los descuentos y los topes.
- `docs/00` §6.4 pone "Documentación de usuario y ayuda contextual" en la etapa 4; `docs/04` §2.1 no menciona ayuda.

## Goals / Non-Goals

**Goals:** un botón "(?)" accesible y usable con el dedo; un único archivo de textos trazable a las reglas; tres páginas "Ver más"; la ayuda de las pantallas actuales con reglas difíciles; una regla para que los changes futuros traigan su ayuda.

**Non-Goals:** manual de usuario, búsqueda, ayuda en `/ruta` (D7), textos editables por la organización, traducción, mostrar el efecto de los descuentos en una venta (18b).

## Decisions

### D0 — Tamaño y corte · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** `04` §2 pide entre medio día y tres días. El alcance: un componente, un archivo, tres páginas, una ruta y un menú, y 28 claves en 14 pantallas (D9). Lo caro es redactar y revisar los textos, no el código.

- **A (recomendada). Un change con las 28 claves**, en un lote: componente y pruebas, archivo y prueba de trazabilidad, páginas, y después las claves pantalla por pantalla. Consecuencia: cabe en uno o dos días.
- **B. Cortar:** el 16b trae el componente, las páginas y la ayuda de Descuentos y Listas de precios (19 claves); Compras y Stock (9 claves) pasan a un `16c-ayuda-compras-y-stock`. Consecuencia: dos proposals y una fila más en `04` §4.
- **C. Mínimo:** solo Descuentos y Topes (10 claves), que es lo que originó el pedido. Consecuencia: precios, compras y jornadas siguen sin ayuda hasta otro change.

**Ejemplo.** Con A, al cerrar el change el usuario abre "Compras" y encuentra el "(?)" de "Total de factura"; con B, lo encuentra recién con el 16c.

### D1 — Adelantar la ayuda contextual de la etapa 4 · alcance · MEDIO · ADR-051 · **APROBADA 2026-10-15: opción A**

**Contexto.** `00` §6.4 junta "documentación de usuario y ayuda contextual" en la etapa 4. El usuario pidió la ayuda ahora y que cada change futuro traiga la suya.

- **A (recomendada). Adelantar solo la ayuda contextual** (los "(?)" y las páginas "Ver más" de temas puntuales) a la etapa 1, y dejar en la etapa 4 la **documentación de usuario completa** (manual, guías de tareas, búsqueda). Consecuencia: `00` §6.4 se precisa, `04` suma la fila del 16b entre el 16 y el 17 y el punto 8 de §2.1 (D10); ADR-051 lo registra.
- **B. Adelantar todo, manual incluido.** Consecuencia: el change deja de ser chico y hay que escribir un manual de pantallas que todavía cambian (venta, ruta).
- **C. No adelantar y usar el atributo `title` del navegador.** Consecuencia: no funciona con el dedo ni con teclado, y los lectores de pantalla lo leen mal; no resuelve el pedido.

**Ejemplo.** Con A, el change 17 (`cobranzas`) trae sus "(?)" (por ejemplo, cómo se imputa una cobranza) como parte de su definición de terminado; el manual de usuario sigue en la etapa 4.

### D2 — Componente propio, popover nativo o librería · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** El panel tiene que abrir con clic, tap y teclado, cerrar con Escape y clic afuera, informar su estado al lector de pantalla y entrar en el ancho de un teléfono. `CLAUDE.md` §2 fija el stack y no hay librería de popover.

- **A (recomendada). Componente propio `Ayuda`** en `components/ui/Ayuda.tsx`: un `<button type="button">` nativo (Enter y Espacio gratis) con `aria-label="Ayuda: <concepto>"`, `aria-expanded` y `aria-controls`; el panel es un elemento no modal con `id` propio, ubicado justo después del botón en el orden del documento (Tab llega al "Ver más"), con posición absoluta y ancho `min(18rem, 100vw − 2rem)`. Cierra con Escape (y devuelve el foco al botón), con un `pointerdown` fuera del botón y del panel, y al activar otra ayuda (un evento del documento: queda abierto un solo panel). Sin dependencias. Consecuencia: unas 80 líneas más sus pruebas, todo bajo control y probado con jsdom.
- **B. Atributo `popover` del navegador** (`popovertarget`, cierre "light dismiss" y Escape nativos). Consecuencia: menos código, pero jsdom no implementa `showPopover`, así que las pruebas de accesibilidad pedidas (clic, teclado, Escape, clic afuera) no se pueden escribir en Vitest; y en navegadores viejos de teléfonos no anda.
- **C. Librería (Radix Popover o Floating UI).** Consecuencia: resuelve posición y foco, pero suma una dependencia fuera del stack para un solo componente, contra `CLAUDE.md` §2; obliga a reconstruir la imagen del frontend.

**Ejemplo.** Con A, en el teléfono el vendedor toca "(?)", lee el panel debajo del campo y toca afuera para cerrarlo; con un lector de pantalla oye "Ayuda: Medida, botón, contraído".

### D3 — Estructura del archivo de textos · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** El usuario pidió un único archivo para corregir textos en un lugar. Hace falta que una clave mal escrita no pase y que cada texto se pueda rastrear a su regla.

- **A (recomendada). Un módulo TypeScript `frontend/src/ayuda/textos.ts`** con dos constantes: `AYUDAS` (clave → `{ titulo, texto, ejemplo?, reglas, verMas? }`) y `TEMAS` (tema → `{ titulo, reglas, secciones: { titulo, parrafos, ejemplo? }[] }`), declaradas `as const satisfies` sus tipos. `ClaveDeAyuda = keyof typeof AYUDAS` y `TemaDeAyuda = keyof typeof TEMAS`: el componente solo acepta claves existentes (falla `npm run typecheck`). Claves `area.concepto` en español (`descuentos.medida`). `reglas` es una lista de IDs (`'DSC-03'`, `'ADR-050'`). Texto plano, sin HTML ni Markdown. Consecuencia: sin parser ni dependencias; el archivo se lee como un documento.
- **B. Un JSON** (`ayuda.json`) con el mismo contenido. Consecuencia: las claves dejan de ser un tipo (la prueba de D10 es la única red) y no admite comentarios para el mantenedor.
- **C. Un Markdown por tema** más un archivo de claves cortas. Consecuencia: dos lugares en vez de uno y un parser de Markdown nuevo.

**Ejemplo.** Con A, `<Ayuda clave="descuentos.medidda" />` no compila; corregir el ejemplo de las cajas equivalentes es editar una línea de `textos.ts`.

### D4 — ¿Se muestran los IDs de regla en pantalla? · contenido · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** Cada texto cita su regla para mantenerlo. La persona que usa la pantalla no conoce `docs/01`.

- **A (recomendada). No se muestran:** los IDs viven en el archivo y en las pruebas. Consecuencia: el panel queda corto y en lenguaje de negocio.
- **B. Se muestran en chico al pie del panel** ("Regla DSC-03"). Consecuencia: ayuda a reportar dudas, pero suma ruido en el teléfono.
- **C. Solo en las páginas "Ver más"**, al pie de cada sección. Consecuencia: punto intermedio; la página larga sí puede llevarlos.

**Ejemplo.** Con A, el panel de "Operador" dice "≥ 20 incluye 20; > 20 no…" sin "DSC-03".

### D5 — Ruta de las páginas "Ver más" y cómo se abren · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** Un formulario de `/admin` a medio cargar se pierde si se navega fuera en la misma pestaña.

- **A (recomendada). `/admin/ayuda` (índice) y `/admin/ayuda/:tema` dentro de `AdminLayout`**, con una entrada "Ayuda" al final del menú. El "Ver más" del panel abre la página en **otra pestaña** (`target="_blank"`, `rel="noopener"`); el índice y la navegación entre temas, en la misma. Un tema inexistente muestra "No encontramos ese tema de ayuda" y un enlace al índice. Las páginas se cargan con `Suspense` como las áreas. Consecuencia: el formulario no se pierde; la ayuda tiene dirección propia para compartirla.
- **B. Misma pestaña.** Consecuencia: más simple, pero se pierde lo cargado al seguir "Ver más".
- **C. Sin páginas: el tema largo se abre en un `Dialogo` sobre la pantalla.** Consecuencia: no se pierde nada y funcionaría igual en `/ruta`, pero no hay índice ni dirección para volver a leerlo; contradice lo acordado ("una página de ayuda").

**Ejemplo.** Con A, mientras carga una regla, el Administrador sigue "Ver más" en "Acumulable", lee "Cómo se aplican los descuentos" en otra pestaña y vuelve al formulario intacto.

### D6 — ¿La ayuda depende de los permisos? · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** Las pantallas ya se muestran según permisos (ADR-027). La ayuda no tiene datos.

- **A (recomendada). No se filtra.** Un "(?)" aparece junto a su campo, y el campo ya está filtrado; las páginas "Ver más" y el índice las ve todo usuario con sesión en `/admin`. Consecuencia: cero lógica de permisos nueva; un vendedor puede leer cómo funcionan los topes, que es justo lo que necesita entender.
- **B. Cada tema declara el permiso que lo muestra** (topes con `ADMIN_USUARIOS`). Consecuencia: más código y pruebas; oculta a un vendedor por qué su descuento pide autorización.
- **C. Ocultar solo "Cómo funcionan los topes"** a quien no tiene `DESCUENTO_MANUAL` ni `ADMIN_USUARIOS`. Consecuencia: un caso especial sin regla en `docs/` que lo pida.

**Ejemplo.** Con A, un usuario de Administración abre "Ayuda" y lee los tres temas; no ve el "(?)" de "Tope de descuento" porque no ve esa pantalla.

### D7 — La ayuda en `/ruta` y sin conexión · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** `/ruta` no tiene pantallas de negocio todavía; las tendrá con el 18b (venta, descuento manual) y el 21 (PWA, sin conexión).

- **A (recomendada). Nada en `/ruta` en este change, con el camino preparado:** el archivo de textos y el componente no dependen de `/admin` ni de la red (están en el paquete de JavaScript), así que el precache del 21 los incluye; la página de tema se escribe como componente reutilizable y `/ruta` montará su propia `/ruta/ayuda/:tema` cuando tenga pantallas. Deuda nominada al 18b (los "(?)" del descuento manual en la venta) y al 21 (la ruta de ayuda en `/ruta` sin conexión; en la PWA instalada, "Ver más" no abre otra pestaña sino la ruta interna). Consecuencia: nada se rehace.
- **B. Crear ya `/ruta/ayuda/:tema`.** Consecuencia: una ruta sin ninguna pantalla que la enlace.
- **C. Servir los textos desde el backend.** Consecuencia: la ayuda no anda sin conexión, suma un endpoint y contradice D3.

**Ejemplo.** Con A, en el 18b el vendedor sin conexión toca el "(?)" del descuento manual y lee el texto, porque viene en el paquete.

### D8 — Cómo se engancha en las pantallas · técnica · BAJO · **APROBADA 2026-10-15: opción A**

**Contexto.** La mayoría de los conceptos son campos (`Campo`); otros son botones ("Activar", "Liberar", "Generar borrador"), encabezados de tabla ("Toma actual") o señales.

- **A (recomendada). `Campo` suma una prop opcional `ayuda?: ClaveDeAyuda`** que pone el "(?)" al lado de la etiqueta, **fuera** del `<label>` (activarlo no mueve el foco al control); en los demás lugares se usa `<Ayuda clave="…" />` directo. Las pantallas no escriben texto de ayuda. Consecuencia: un cambio chico y retrocompatible en `Campo`; las suites existentes no cambian.
- **B. Un envoltorio `CampoConAyuda`.** Consecuencia: dos componentes de campo para lo mismo.
- **C. Solo `<Ayuda>` directo en cada pantalla.** Consecuencia: cada pantalla arma la fila etiqueta + ayuda a mano, con riesgo de meter el botón dentro del `<label>`.

**Ejemplo.** Con A, el formulario de regla pasa de `<Campo id="medida" etiqueta="Medida">` a `<Campo id="medida" etiqueta="Medida" ayuda="descuentos.medida">`.

### D9 — Inventario de "(?)" y textos · contenido · MEDIO · **APROBADA 2026-10-15: opción A, con los textos reescritos de "Revisión del usuario" (27 claves; la 3 eliminada)**

**Contexto.** El usuario pidió ayuda en las pantallas actuales con reglas difíciles; lo simple lleva poco o nada. Cada texto se apoya en una regla de `docs/01` o en un ADR vigente y no agrega nada que la regla no diga. Los ejemplos salen de `docs/01` o de ADR-050 cuando existen; los que se arman con aritmética propia se marcan *(armado)*.

- **A (recomendada). Las 28 claves de la tabla**, con los textos propuestos como borrador que el usuario corrige.
- **B. Solo las claves que nombró el usuario** (descuentos, topes, margen, precedencia, redondeo, publicación, costo según IVA, promedio, toma y liberación: 17 claves). Consecuencia: quedan sin ayuda bonificación, umbral, vigencia de reglas, señales del borrador, sin precio y precio manual.
- **C. Un "(?)" en cada campo de esas pantallas.** Consecuencia: ayuda en "Nombre" y "Observación", ruido que oculta lo importante.

Los textos no dicen que el tope y las reglas recién se ven en una venta con el 18b: quedarían viejos al archivarse el 18b (se avisa en la prueba manual).

**Descuentos — formulario de regla** (`ReglaFormScreen`, detalle `ReglaDetalleScreen`) y **Topes por rol** (`TopeDialogo`):

| # | Pantalla → campo | Clave | Reglas | Texto propuesto (ejemplo) | Ver más |
| --- | --- | --- | --- | --- | --- |
| 1 | Regla → Alcance de la regla | `descuentos.alcance` | DSC-02, ADR-050 | "Toda la venta: la condición mide y descuenta todas las líneas. Productos, categorías o marcas: solo las líneas que coinciden con **alguno** de los elegidos." (Elegir la marca Bodega Norte y la categoría Cervezas incluye un vino de Bodega Norte.) *(armado)* | descuentos |
| 2 | Regla → Medida | `descuentos.medida` | DSC-03, ADR-050 | "Cajas equivalentes: cada línea suma sus unidades divididas por las de su caja, sin redondear, y se pueden mezclar productos. Unidades base: botellas o latas. Importe bruto: pesos antes de descuentos." (15 botellas de un vino x6 son 2,5 cajas; 2 botellas de tres vinos x6 suman 1 caja.) | descuentos |
| 3 | Regla → Operador | `descuentos.operador` | DSC-03 | "≥ incluye el umbral; > exige pasarlo." (Con ≥ 20, 20 cajas aplican y 19 cajas + 5 botellas de un vino x6 = 19,83 no; con > 20, 20 cajas exactas no.) | — |
| 4 | Regla → Umbral | `descuentos.umbral` | DSC-03 | "Mayor que 0. En cajas, hasta 4 decimales; en unidades base, entero; en importe, hasta 2 decimales." (2,5 cajas; 60 unidades; $31.250,00.) | — |
| 5 | Regla → Acción | `descuentos.accion` | DSC-04, DSC-07 | "Porcentaje: se descuenta de cada línea elegible, redondeado por línea. Importe fijo: se reparte entre las líneas elegibles según su importe; nunca deja una línea por debajo de $0." ($1.000 sobre líneas de $31.250,00 y $4.300,00 → $879,04 y $120,96.) | descuentos |
| 6 | Regla → Prioridad | `descuentos.prioridad` | DSC-05, ADR-050 | "El número más bajo es la mayor prioridad (1 va primero). Entre no acumulables gana la que más descuenta en toda la venta; la prioridad solo desempata. Entre acumulables, fija el orden." (R2 da $12.000 y R1 $11.800: gana R2 aunque R1 tenga prioridad 1.) | descuentos |
| 7 | Regla → Acumulable | `descuentos.acumulable` | DSC-03, DSC-05, ADR-050 | "No acumulable: compite y gana una sola por venta. Acumulable: se aplica después, sobre lo que dejó la anterior. Su condición siempre mira las cantidades y el bruto originales." (8 % y después 2 % dan 9,84 %, no 10 %.) | descuentos |
| 8 | Regla → Vigencia desde / hasta | `descuentos.vigencia` | ADR-050 | "La regla aplica desde la fecha 'desde' (si la dejás vacía, desde que la activás) y hasta antes de la 'hasta'. Sin 'hasta', no vence." (Desde el 1/11 00:00 hasta el 1/12 00:00: aplica todo noviembre.) *(armado)* | — |
| 9 | Detalle → Activar | `descuentos.activar` | ADR-050, `01` §18 | "Una regla se edita solo como borrador. Activada o pausada solo cambia de estado o de fecha de fin ('Poner fin'); para cambiar otra cosa, pausala y creá otra." | — |
| 10 | Topes por rol → Tope de descuento (%) | `descuentos.tope` | DSC-06, ADR-050 | "Limita solo el descuento manual, no los automáticos. Se compara una vez por venta contra el mayor porcentaje manual de sus líneas; si lo supera, hace falta una autorización, que cubre toda la venta. Los roles nacen con 0 % salvo el Administrador." (Tope 5 %: 3 % general y una línea al 10 % piden autorización.) *(armado)* | topes |

**Listas de precios** (`ListaFormScreen`, `RedondeosDeCategoria`, `ReglaDialogo`, `BorradorScreen`, `PrecioManualDialogo`, `PublicarDialogo`):

| # | Pantalla → campo | Clave | Reglas | Texto propuesto (ejemplo) | Ver más |
| --- | --- | --- | --- | --- | --- |
| 11 | Lista → Múltiplo y dirección del redondeo | `precios.redondeo` | PRC-01, PRC-14, PRC-15 | "El precio calculado se lleva al múltiplo: arriba, abajo o al más cercano (en la mitad, sube). Se redondea el precio sin IVA." ($8.571,43 a múltiplo 100: $8.600 arriba, $8.600 al más cercano, $8.500 abajo.) | precio |
| 12 | Lista → Redondeo por categoría | `precios.redondeoCategoria` | PRC-14 | "Si una categoría tiene su propio redondeo activo, manda sobre el de la lista para sus productos. Si el redondeo deja el precio en $0, el producto queda sin precio." | precio |
| 13 | Regla de margen → Tipo de margen | `precios.tipoMargen` | PRC-12 | "Markup: costo × (1 + m). Margen bruto: costo / (1 − m), y m tiene que ser menor que 100 %." (Costo $6.000 y 30 %: markup $7.800,00; margen bruto $8.571,43.) | precio |
| 14 | Regla de margen → Se aplica a | `precios.alcanceMargen` | PRC-13 | "Manda la regla más específica: producto, marca, categoría, proveedor y por último la lista. Hay a lo sumo una activa por alcance. Un cambio rige desde el próximo borrador." | precio |
| 15 | Borrador → Generar / Regenerar borrador | `precios.borrador` | PRC-17, PRC-18 | "Informar un costo no cambia ningún precio: generás un borrador que recalcula todos los productos activos desde la versión publicada. Los precios manuales se conservan. Hay un solo borrador por lista; regenerar lo reemplaza." | precio |
| 16 | Borrador → señales del precio | `precios.senales` | PRC-11, PRC-17 | "Costos distintos por presentación: el costo por botella de la caja y el de la unidad no coinciden. Otra regla de IVA: el costo se cargó con otra condición de IVA. Margen menor: el precio manual quedó debajo del calculado." | — |
| 17 | Borrador → Productos sin precio | `precios.sinPrecio` | PRC-19 | "Un producto activo queda sin precio si no tiene costo, regla de margen o presentación de referencia, si el precio da $0 o menos, o si hoy se podría calcular (regenerá). Solo se le fija precio manual si tiene presentación de referencia." | — |
| 18 | Precio manual | `precios.precioManual` | PRC-16, PRC-17 | "Fija el precio a mano. El próximo borrador lo conserva y avisa si quedó por debajo del calculado. Se admite aunque el producto no tenga costo." | — |
| 19 | Publicar → Vigencia desde / hasta | `precios.publicacion` | PRC-02, PRC-03, PRC-05 | "Sin 'desde', rige al publicar; nunca antes. La versión anterior deja de regir sola y vuelve a regir si la nueva vence. Solo se anula una versión que todavía no empezó." | precio |

**Compras y costos** (`CompraFormScreen`, `CostosCargaScreen`, `CompraResultado`):

| # | Pantalla → campo | Clave | Reglas | Texto propuesto (ejemplo) | Ver más |
| --- | --- | --- | --- | --- | --- |
| 20 | Compra y costos → Valor + Incluye IVA (responsable inscripto) | `costos.valorConIva` | CST-02, CST-06 | "Valor por presentación. Si incluye IVA, el IVA se descuenta del costo porque se recupera como crédito fiscal." (Caja x12 a $18.000 con IVA: 18.000 / 1,21 / 12 = $1.239,669421 por botella.) | — |
| 21 | Compra y costos → Valor pagado (monotributo o exento) | `costos.valorPagado` | CST-02, CST-06 | "Lo que pagaste por la presentación. El IVA es parte del costo: no se descuenta." (Caja x12 a $21.780: 21.780 / 12 = $1.815,000000 por botella.) | — |
| 22 | Compra y costos → Bonificación % | `costos.bonificacion` | CST-02 | "Se descuenta del valor antes de calcular el costo por unidad." (Caja x12 a $18.000 con 10 %: 18.000 × 0,9 / 12 = $1.350,000000.) | — |
| 23 | Compra y costos → Costo base | `costos.costoBase` | CST-02, CMP-02 | "Costo de una unidad base (botella, lata), con 6 decimales y redondeado solo al final." (Caja x12 a $18.000 sin IVA: $1.500,000000.) | — |
| 24 | Compra → Total de factura | `compras.totalFactura` | CMP-02, CMP-03 | "Se sugiere el neto más el IVA de cada línea (o el neto a secas si el IVA no se computa); corregilo para que coincida con la factura. La cuenta del proveedor usa este total; el stock y el costo promedio, el neto." | — |
| 25 | Resultado → Registrar como costo informado | `compras.costoPromedioEInformado` | CST-04, CST-11, CMP-04 | "La compra ya recalculó el costo promedio, que costea las ventas. El costo informado es el que usa la lista de precios: se registra solo si lo pedís." (60 a $1.000 y después 60 a $1.100 dejan un promedio de $1.050.) | — |

**Stock y jornadas** (`UbicacionFormScreen`, `UbicacionesListScreen`, `JornadaAbrirScreen`, `JornadaDetalleScreen`):

| # | Pantalla → campo | Clave | Reglas | Texto propuesto (ejemplo) | Ver más |
| --- | --- | --- | --- | --- | --- |
| 26 | Ubicación → Requiere toma | `stock.requiereToma` | STK-02, STK-09, RUT-01 | "Una ubicación que requiere toma se trabaja con una jornada: mientras está tomada, solo esa jornada mueve su stock. Los vehículos siempre la requieren." | — |
| 27 | Ubicaciones → Toma actual; Abrir jornada | `stock.tomaActual` | STK-09, RUT-01 | "Tomada: tiene una jornada abierta o en rendición. Con la jornada abierta, solo ella (su vendedor desde su dispositivo) mueve el stock; en rendición, ya no. Quien tiene 'Liberar ubicación' la mueve siempre; cualquier otro movimiento se rechaza." | — |
| 28 | Jornada → Liberar | `stock.liberacion` | RUT-09, STK-09, AUD-01 | "Destraba la ubicación sin tocar el stock del vehículo. Pide un motivo y queda auditada. Lo que el vendedor envíe después de esa jornada se acepta con una observación." | — |

**Temas "Ver más"** (`TEMAS`): `descuentos` — "Cómo se aplican los descuentos" (DSC-03 a DSC-05, ADR-050: qué mide la condición; un ganador no acumulable por venta y sus desempates; acumulables en orden; el manual al final, propio o general; con los ejemplos de 2, 3, 6 y 7). `topes` — "Cómo funcionan los topes" (DSC-06, ADR-050 puntos 12 y 13: solo el manual; una evaluación por venta contra el mayor porcentaje; autorización propia o de otro usuario con `AUTORIZAR_DESCUENTO`, una por venta, sin límite del autorizador; roles en 0 % salvo el Administrador; "Sin tope" es 100 %). `precio` — "Cómo se calcula el precio de una lista" (PRC-11 a PRC-15, PRC-17: costo de referencia, margen por precedencia, redondeo de lista o categoría, borrador y publicación, con el ejemplo del vino de $6.000).

**Ejemplo.** Con A, el usuario lee esta tabla, cambia "Toda la venta" por "Toda la operación" en la clave 1 y aprueba; el apply copia el texto aprobado a `textos.ts`.

#### Revisión del usuario (2026-10-15) — los textos aprobados reemplazan a los de las tablas

**Estilo aprobado:** (1) para qué sirve, en una oración; (2) qué hace cada opción con palabras de todos los días (sin "líneas elegibles", "bruto", "precedencia", "unidades base"); (3) un ejemplo con productos reales; (4) 3 o 4 oraciones como máximo; lo que no entra va al "Ver más". Las reglas citadas y el "Ver más" de cada clave no cambian.

**Clave 3 `descuentos.operador` ELIMINADA** (el usuario: se entiende sola). Quedan 27 claves.

**Descuentos — APROBADOS:**
1. `descuentos.alcance`: "¿A qué productos se aplica la regla? *Toda la venta*: cuenta y descuenta todo lo vendido. *Productos, categorías o marcas*: solo lo que coincida con alguno de los que elijas. Ej.: si elegís la marca Bodega Norte y la categoría Cervezas, entran todos los vinos de Bodega Norte y todas las cervezas."
2. `descuentos.medida`: "Qué se cuenta para saber si la regla se cumple. *Cajas equivalentes*: lo vendido pasado a cajas, aunque se venda suelto (15 botellas de un vino que viene x6 = 2,5 cajas). *Unidades*: botellas o latas sueltas. *Importe*: pesos, a precio de lista, antes de descuentos."
4. `descuentos.umbral`: "El número que hay que alcanzar. En cajas admite decimales (2,5); en unidades, solo enteros (60); en importe, pesos con centavos ($31.250,00)."
5. `descuentos.accion`: "Qué descuento se hace. *Porcentaje*: se descuenta ese % de cada producto que entra en la regla. *Importe fijo*: un monto total que se reparte entre esos productos según lo que vale cada uno. Ej.: $1.000 entre un producto de $31.250 y otro de $4.300 → $879,04 y $120,96."
6. `descuentos.prioridad`: "1 es la más importante. Si se cumplen varias reglas no acumulables, gana la que **más descuento da**, no la de prioridad 1: la prioridad solo decide si dan exactamente lo mismo. En las acumulables, indica en qué orden se aplican."
7. `descuentos.acumulable`: "*No acumulable*: si se cumplen varias, se aplica solo una, la que más descuento da. *Acumulable*: se suma a las demás, y cada una se calcula sobre el precio que dejó la anterior. Ej.: 8 % y después 2 % dan 9,84 %, no 10 %."
8. `descuentos.vigencia`: "Desde cuándo y hasta cuándo aplica. Si dejás 'desde' vacío, aplica desde que la activás. Si dejás 'hasta' vacío, no vence. Ej.: desde el 1/11 hasta el 1/12 = todo noviembre."
9. `descuentos.activar`: "Una regla solo se puede editar mientras es borrador. Activada, solo se puede pausar, reactivar o ponerle fecha de fin. Para cambiarle otra cosa, pausala y creá una nueva."
10. `descuentos.tope`: "Cuánto descuento manual puede dar este rol sin pedir autorización. No limita los descuentos automáticos de las reglas. Si el vendedor pasa el tope en algún producto, la venta necesita **una** autorización, que vale para toda la venta. Los roles empiezan con 0 %, salvo el Administrador. Ej.: con tope 5 %, un 3 % a toda la venta pasa directo; un 10 % a un producto pide autorización."

**Listas de precios — APROBADOS:**
11. `precios.redondeo`: "Para que los precios queden redondos. El precio calculado se lleva al múltiplo que elijas: hacia arriba, hacia abajo o al más cercano (si queda justo en la mitad, sube). Se redondea el precio sin IVA. Ej.: $8.571,43 con múltiplo 100 → $8.600 hacia arriba o al más cercano; $8.500 hacia abajo."
12. `precios.redondeoCategoria`: "Permite que una categoría redondee distinto que el resto de la lista. Si está activo, manda sobre el redondeo de la lista para los productos de esa categoría. Si al redondear el precio queda en $0, el producto queda sin precio."
13. `precios.tipoMargen`: "Cómo se calcula el precio a partir del costo. *Markup*: al costo se le suma un % del costo. *Margen bruto*: el % es la ganancia sobre el precio de venta (tiene que ser menor que 100 %). Ej.: costo $6.000 y 30 % → markup $7.800; margen bruto $8.571,43."
14. `precios.alcanceMargen`: "A qué productos aplica este margen. Si a un producto le corresponden varias reglas, manda la más específica, en este orden: producto, marca, categoría, proveedor y, por último, la de toda la lista. Ej.: si Cervezas tiene 25 % y la cerveza X tiene su propia regla de 20 %, la cerveza X va con 20 %. Los cambios se ven recién en el próximo borrador."
15. `precios.borrador`: "Los precios nuevos se preparan en un borrador antes de publicarlos. Cargar un costo nuevo no cambia ningún precio: hay que generar el borrador, que recalcula todos los productos. Los precios puestos a mano se mantienen. Hay un solo borrador por lista; regenerarlo reemplaza el anterior."
16. `precios.senales`: "Avisos para revisar antes de publicar. *Costos distintos por presentación*: la botella sale distinto si se compró suelta o en caja. *Otra regla de IVA*: el costo se cargó con otra condición frente al IVA. *Margen menor*: el precio puesto a mano quedó por debajo del calculado."
17. `precios.sinPrecio`: "Productos activos a los que el borrador no les pudo calcular precio. Pasa si les falta el costo, una regla de margen o la presentación de referencia, o si el precio da $0 o menos. Si ya corregiste lo que faltaba, regenerá el borrador. Para ponerle precio a mano, el producto tiene que tener presentación de referencia."
18. `precios.precioManual`: "Para fijar un precio a mano en lugar del calculado. Se mantiene en los próximos borradores, que te avisan si quedó por debajo del calculado. Se puede poner aunque el producto no tenga costo."
19. `precios.publicacion`: "Desde cuándo rigen los precios nuevos. Si dejás 'desde' vacío, rigen apenas publicás (nunca puede ser una fecha pasada). Cuando empieza la nueva versión, la anterior deja de regir sola; si la nueva tiene 'hasta' y vence, vuelve a regir la anterior. Solo se puede anular una publicación que todavía no empezó."

**Compras y costos — APROBADOS:**
20. `costos.valorConIva`: "El precio de la presentación como figura en la factura. Si marcás que incluye IVA, el sistema se lo saca al costo, porque como responsable inscripto ese IVA lo recuperás. Ej.: caja x12 a $18.000 con IVA → $18.000 / 1,21 / 12 = unos $1.239,67 por botella."
21. `costos.valorPagado`: "Lo que pagaste por la presentación, con el IVA incluido. Como el IVA no lo recuperás, es parte del costo y no se descuenta. Ej.: caja x12 a $21.780 → $21.780 / 12 = $1.815 por botella."
22. `costos.bonificacion`: "El descuento que te hizo el proveedor en ese producto. Se resta del valor antes de calcular el costo. Ej.: caja x12 a $18.000 con 10 % → $16.200, o sea $1.350 por botella."
23. `costos.costoBase`: "Lo que te cuesta una sola botella o lata. Es el costo que el sistema usa para todo (precios y ganancia de las ventas) y se calcula a partir de la presentación que compraste. Ej.: caja x12 a $18.000 sin IVA → $1.500 por botella."
24. `compras.totalFactura`: "El total que figura en la factura del proveedor. El sistema te sugiere uno sumando los productos (con su IVA, si corresponde); corregilo si no coincide. Este total es lo que le debés al proveedor; el costo de la mercadería se calcula con los valores de cada producto, no con este total."
25. `compras.costoPromedioEInformado`: "Al registrar la compra, el sistema ya actualizó el **costo promedio**, que se usa para calcular la ganancia de cada venta. El **costo informado** es otro: es el que usa la lista de precios, y solo cambia si marcás esta opción. Ej.: tenías 60 botellas a $1.000 y compraste 60 a $1.100 → el promedio queda en $1.050."

**Stock y jornadas — APROBADOS:**
26. `stock.requiereToma`: "Para ubicaciones que un vendedor usa durante su jornada, como un vehículo. Mientras un vendedor la tiene tomada, solo su jornada puede mover el stock de ahí. Los vehículos siempre la requieren."
27. `stock.tomaActual`: "Muestra qué jornada tiene tomada esta ubicación. Mientras la jornada está abierta, solo ese vendedor (desde su dispositivo) puede mover el stock. Cuando pasa a rendición, ya nadie puede, salvo quien tiene el permiso 'Liberar ubicación'."
28. `stock.liberacion`: "Destraba la ubicación cuando una jornada quedó trabada (por ejemplo, se le rompió el teléfono al vendedor). No toca el stock del vehículo. Pide un motivo y queda registrado quién lo hizo. Si después llegan ventas de esa jornada desde el dispositivo, se aceptan, pero quedan marcadas para revisar."

**Páginas "Ver más" — APROBADAS** (contenido; el apply las maqueta con títulos, listas y recuadros de ejemplo):

`descuentos` — "Cómo se aplican los descuentos": En una venta pueden cumplirse varias reglas a la vez; el sistema las resuelve siempre en este orden. (1) Qué reglas se cumplen: se revisa cada regla activa y vigente; para saber si se cumple se mira siempre la venta antes de cualquier descuento (cantidades y precios de lista). Ej.: con "≥ 20 cajas → 5 %", 19 cajas + 5 botellas de un vino x6 = 19,83 cajas, no se cumple; 20 cajas sí. (2) Entre las no acumulables gana una sola: la que más descuento da en pesos en toda la venta; la prioridad solo desempata si dan exactamente lo mismo (gana el número más bajo). Ej.: 12 cajas de Vino A ($150.000) y 10 de Vino B ($86.000); "≥ 20 cajas → 5 %" sobre toda la venta daría $11.800 y "≥ 10 cajas de Vino A → 8 %" daría $12.000: gana la segunda y Vino B queda sin descuento aunque la otra lo incluía. (3) Las acumulables se suman una después de otra, en orden de prioridad, cada una sobre el precio que dejó la anterior: 8 % y después 2 % = 9,84 %, no 10 %. (4) Al final, el descuento manual del vendedor sobre lo que quedó: uno general para toda la venta o uno distinto en un producto, que reemplaza al general en ese producto.

`topes` — "Cómo funcionan los topes": El tope es cuánto descuento manual puede dar alguien sin pedir permiso; se configura por rol en "Topes por rol". Solo cuenta el descuento manual (lo de las reglas automáticas no suma). Se revisa una vez por venta, contra el porcentaje manual más alto que haya quedado en algún producto. Si lo supera, hace falta una autorización, y una sola alcanza para toda la venta: puede darla el mismo vendedor si tiene el permiso de autorizar, o un supervisor con su PIN. Quien autoriza puede aprobar cualquier porcentaje, aunque su propio tope sea menor; queda registrado quién autorizó. Los roles empiezan con 0 %, salvo el Administrador (sin tope): hasta configurarlos, cualquier descuento manual pide autorización. Ej. con tope 5 %: 5 % a toda la venta pasa directo; 5 % a toda la venta y 10 % a un producto pide una autorización; 10 % a toda la venta pero 3 % puesto en cada producto → el máximo que quedó es 3 % y pasa directo.

`precio` — "Cómo se calcula el precio de una lista": Cada precio sale de tres pasos y después se publica. (1) El costo: el costo informado vigente del producto (no el promedio), llevado a su presentación de referencia, por ejemplo la caja (PRC-11, CST-04). (2) El margen: la regla de margen más específica que le corresponda, en este orden: producto, marca, categoría, proveedor o la de toda la lista. (3) El redondeo: al múltiplo de la lista, o al de su categoría si tiene uno propio. Ej.: vino con costo $6.000 y margen bruto 30 % → $8.571,43; redondeo a múltiplo 100 hacia arriba → $8.600. Nada cambia hasta que publicás: cargar un costo o cambiar una regla no toca los precios; primero generás un borrador, que recalcula todo y avisa lo que conviene revisar, y después lo publicás, ahora o con fecha. Los precios puestos a mano se mantienen de un borrador al siguiente.

**Corrección tras verificar PRC-11:** el borrador de "Ver más" decía "el último costo que cargaste para la lista"; PRC-11 dice "costo informado vigente × unidades de la presentación de referencia", y así quedó.

### D10 — Cómo se mantienen al día los textos · proceso · MEDIO · ADR-051 · **APROBADA 2026-10-15: opción A**

**Contexto.** El usuario pidió que cada change futuro traiga sus "(?)". Un texto puede quedar viejo si cambia la regla que cita.

- **A (recomendada). Tres redes:** (1) **punto 8 de `04` §2.1**: "Si el change trae funcionalidad no obvia, sus pantallas traen su ayuda en el archivo único, cada texto citando su regla; si el change modifica una regla de `docs/01` o un ADR, se revisan los textos que la citan"; (2) **prueba automática** en Vitest que recorre `frontend/src`, junta toda clave usada en `<Ayuda clave>` y en `ayuda=` y exige que exista, exige que cada entrada y cada tema citen al menos un ID, y que cada ID exista en `docs/01-dominio.md` (como `| ID |` de una tabla) o como archivo en `docs/adr/`; (3) **una línea en la plantilla de tareas** de cada change: "Ayuda: claves nuevas o revisadas (o 'no aplica')". Consecuencia: lo mecánico lo atrapa la prueba; lo semántico (un texto que ya no dice lo que dice la regla) lo atrapa la revisión al tocar la regla, buscando su ID en `textos.ts`.
- **B. Solo la prueba automática.** Consecuencia: nada obliga a que un change nuevo traiga su ayuda.
- **C. Solo el punto de la definición de terminado, sin prueba.** Consecuencia: una clave borrada o un ID mal escrito pasa sin aviso.

**Ejemplo.** Con A, si el 18b cambia DSC-06, la búsqueda de `DSC-06` en `textos.ts` muestra las claves 10 y el tema `topes` para revisar; si alguien escribe `'DSC-6'`, la prueba falla.

## Dudas abiertas de `docs/` (no se resuelven acá)

1. **PRC-11 y "costos distintos por presentación".** La regla dice que el precio lleva "la presentación de la que salió el costo", pero no dice **cómo se elige** cuando los costos por unidad base difieren (ADR-047 punto 3 tampoco). El texto de la clave 16 se limita a decir qué significa la señal y no explica la elección. Si el usuario quiere que la ayuda lo explique, hace falta precisar PRC-11 primero.

## Risks / Trade-offs

- [Un texto simplifica de más y enseña mal una regla] → cada texto cita su regla, el usuario lo revisa en D9 y en la prueba manual; los de descuentos y topes se comparan contra ADR-050.
- [Los textos quedan viejos] → D10 (punto de la definición de terminado y búsqueda por ID).
- [La prueba de trazabilidad lee `../docs` y la imagen del frontend solo monta `frontend/`] → la prueba localiza la raíz del repositorio y, si `docs/` no está, falla con un mensaje claro (no se saltea); se corre como las demás suites del frontend, con Docker detenido.
- [El panel se sale de la pantalla en el teléfono o queda tapado por un diálogo] → ancho máximo relativo al viewport y `z-index` por encima del `Dialogo`; se prueba a mano en ancho de teléfono.
- ["Ver más" en otra pestaña dentro de la PWA instalada] → no aplica hasta el 21 (D7).

## Migration Plan

Sin migración ni backend. Despliegue con el frontend; volver atrás es revertir el commit. Sin dependencias nuevas: no hace falta reconstruir imágenes.

## Open Questions

Ninguna que cambie el plan: D0 a D10 se aprueban antes del apply y la duda de PRC-11 no bloquea.
