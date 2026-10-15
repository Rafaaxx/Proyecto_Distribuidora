# ADR-051 — Ayuda contextual: adelanto desde la etapa 4, componente propio sin dependencias, archivo único de textos con reglas citadas, páginas "Ver más" en `/admin`, ayuda sin permisos ni red, enganche por `Campo`, inventario de 27 claves y tres redes para mantener los textos al día

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-15 |
| Referenciado en | `openspec/changes/16b-ayuda-contextual/design.md` D0 a D10 y `specs/sistema/ayuda-contextual`; `00-vision-y-alcance.md` §6.4; `02-arquitectura.md` §4, §13.1; `04-roadmap-changes.md` §2.1, §4, §8 |

**Decisiones D0 a D10 del change aprobadas por el usuario el 2026-10-15, opción A en todas. En D9 el usuario pidió textos más simples (para qué sirve, qué hace cada opción en palabras de todos los días, un ejemplo con productos reales, tres o cuatro oraciones) y los redactó él; quedaron 27 claves porque eliminó la de "Operador" (se entiende sola). Aprobado junto con `propuesta-docs.md`, el ADR queda *Vigente* el 2026-10-15.**

## Contexto

El sistema ya tiene reglas que no se adivinan mirando el campo: qué mide una regla de descuento y cómo se desempatan dos no acumulables (ADR-050), cuándo un descuento manual pide autorización (DSC-06), qué cambia entre markup y margen bruto (PRC-12), cómo se descuenta el IVA del costo según la condición de la organización (CST-06) o qué significa que una ubicación esté tomada (STK-09). El usuario pidió explicarlas en pantalla, junto al campo, y que cada change futuro traiga su ayuda.

Lo que `docs/` decía: `00` §6.4 junta "documentación de usuario y ayuda contextual" en la etapa 4; `04` §2.1 no menciona la ayuda. Lo que existía en el código: `Campo`, `Dialogo`, `Boton`, `Tarjeta`, `Tabla`; ningún popover ni tooltip; ninguna librería de popover en el stack (`CLAUDE.md` §2). Lo que `docs/` no resolvía y este ADR fija: si se adelanta la ayuda, qué parte; cómo se construye el botón para que sirva con el dedo, el teclado y un lector de pantalla; dónde viven los textos y cómo se garantiza que cada uno responda a una regla vigente; si se muestran los IDs; dónde se leen los temas largos; si la ayuda depende de permisos y de la red; y cómo se evita que los textos queden viejos.

## Decisión

### Alcance y componente

1. **Adelantar solo la ayuda contextual (D0 y D1).** Un solo change, en un lote, con la ayuda de las pantallas actuales que tienen reglas difíciles. La ayuda contextual (los "(?)" y las páginas "Ver más" de temas puntuales) pasa de la etapa 4 a la etapa 1; el manual, las guías de tareas y la búsqueda siguen en la etapa 4. Precisa `00` §6.4 y suma la fila 16b entre el 16 y el 17 en `04` §4 y §8.
2. **Componente propio `Ayuda`, sin dependencias (D2).** `frontend/src/components/ui/Ayuda.tsx`: un `<button type="button">` nativo (Enter y Espacio sin código extra, y sin enviar el formulario que lo contenga) con nombre accesible "Ayuda: <título>", `aria-expanded` y `aria-controls`. El panel es no modal, existe en el DOM solo mientras está abierto y se ubica justo después del botón (Tab llega al "Ver más"). Cierra con Escape (devuelve el foco al botón), con un `pointerdown` fuera del botón y del panel y al abrirse otra ayuda: queda a lo sumo un panel abierto. El ancho es `min(18rem, 100vw − 2rem)`, se corre para no salirse por la derecha de una pantalla angosta y su `z-index` está por encima del de `Dialogo`; Escape dentro de un diálogo cierra la ayuda y no el diálogo. No se usa el atributo `popover` del navegador (jsdom no lo implementa y las pruebas de accesibilidad no se podrían escribir) ni una librería (Radix, Floating UI): sumaría una dependencia fuera del stack para un solo componente.
3. **Cómo se engancha (D8).** `Campo` suma una prop opcional `ayuda?: ClaveDeAyuda` que pone el "(?)" al lado de la etiqueta y **fuera** del `<label>`: activarlo no mueve el foco al control ni marca una casilla. `Tabla` suma `ayuda?` por columna para el encabezado. En los demás lugares (botones, títulos de sección) se usa `<Ayuda clave="…" />` directo, siempre fuera del encabezado o del botón para no cambiar su nombre accesible. Las pantallas no escriben texto de ayuda.

### Los textos

4. **Un archivo único, tipado (D3).** `frontend/src/ayuda/textos.ts` con `AYUDAS` (clave → `{ titulo, texto, ejemplo?, reglas, verMas? }`) y `TEMAS` (tema → `{ titulo, reglas, secciones }`), declaradas `as const satisfies` sus tipos. `ClaveDeAyuda` y `TemaDeAyuda` se derivan de él: una clave mal escrita no compila. Las claves son `area.concepto` en español (`descuentos.medida`). Texto plano: un asterisco marca cursiva y dos, negrita; no hay HTML ni Markdown. El ejemplo, cuando lo hay, va en un recuadro aparte.
5. **Cada texto cita su regla y no se muestra (D4).** `reglas` lista los IDs de `docs/01-dominio.md` o los ADR en que se apoya el texto. Sirven para mantenerlo y no se muestran en pantalla: el panel queda corto y en lenguaje de negocio. Los ejemplos salen de `01` o de ADR-050 cuando existen; los armados con aritmética propia se marcaron al aprobarlos.
6. **Inventario (D9).** 27 claves en 14 pantallas, con los textos que el usuario aprobó el 2026-10-15: **descuentos** (`alcance`, `medida`, `umbral`, `accion`, `prioridad`, `acumulable`, `vigencia`, `activar`, `tope`), **listas de precios** (`redondeo`, `redondeoCategoria`, `tipoMargen`, `alcanceMargen`, `borrador`, `senales`, `sinPrecio`, `precioManual`, `publicacion`), **compras y costos** (`valorConIva`, `valorPagado`, `bonificacion`, `costoBase`, `totalFactura`, `costoPromedioEInformado`) y **stock y jornadas** (`requiereToma`, `tomaActual`, `liberacion`). La clave de "Operador" se eliminó. Un texto que necesite decir algo que su regla no dice se consulta antes de escribirse.
7. **Los textos no hablan del efecto en la venta.** El tope y las reglas de descuento se ven en una venta recién con el change 18b; los textos explican la regla y no prometen una pantalla que todavía no existe. Se avisa en la prueba manual.

### Páginas "Ver más" y alcance

8. **Tres temas, en `/admin/ayuda` (D5).** `descuentos` ("Cómo se aplican los descuentos"), `topes` ("Cómo funcionan los topes") y `precio` ("Cómo se calcula el precio de una lista"), con un índice en `/admin/ayuda` y una página en `/admin/ayuda/:tema`, dentro del layout, con una entrada "Ayuda" al final del menú. El "Ver más" de un panel abre la página en **otra pestaña** (`target="_blank"`, `rel="noopener noreferrer"`) para no perder lo cargado en el formulario. Un tema inexistente muestra "No encontramos ese tema de ayuda" con un enlace al índice. Las páginas se cargan con `Suspense` como las demás áreas.
9. **Sin permisos ni red (D6 y D7).** La ayuda no se filtra por permiso: un "(?)" aparece junto a su campo (ya filtrado) y las páginas y el índice las ve todo usuario con sesión en `/admin`; la entrada "Ayuda" del menú aparece con la sesión confirmada y, como las secciones, falla cerrada mientras `/yo` está pendiente o falló. Nada se pide al servidor: los textos viajan en el paquete de JavaScript, así que el precache del change 21 los incluye. La página de tema es un componente reutilizable (`TemaDeAyudaVista`) para que `/ruta` monte la suya cuando tenga pantallas; en este change no se crea `/ruta/ayuda`.

### Mantener los textos al día

10. **Tres redes (D10).** (1) El punto 8 de `04` §2.1: si el change trae funcionalidad no obvia, sus pantallas traen su ayuda en el archivo único, cada texto citando su regla; si modifica una regla o un ADR, se revisan los textos que lo citan (buscándolo por su ID en `textos.ts`); (2) una prueba de Vitest (`tests/unit/ayuda/trazabilidad.test.ts`) que recorre `frontend/src`, junta las claves de `<Ayuda clave>` y de `ayuda=`, exige que existan, exige que cada entrada y cada tema citen al menos un ID y que cada ID exista en `docs/01-dominio.md` (primera columna de una tabla) o como archivo en `docs/adr/`; si `docs/` no se encuentra, falla con un mensaje claro y no se saltea; (3) una línea en la plantilla de tareas de cada change: "Ayuda: claves nuevas o revisadas (o 'no aplica')". Lo mecánico lo atrapa la prueba; lo semántico, la revisión al tocar la regla.

## Consecuencias

- Sin backend, migración ni dependencias nuevas: no hace falta reconstruir la imagen del frontend. Volver atrás es revertir el commit.
- El nombre accesible del botón es "Ayuda: <título>", así que una consulta por texto de etiqueta que no esté anclada (por ejemplo `getByLabelText(/medida/i)`) encuentra dos elementos en una pantalla con ayuda; las pruebas existentes que lo hacían se anclaron (`/^medida$/i`).
- En una tabla, el "(?)" de un encabezado agrega al nombre accesible de la columna el del botón; las pruebas que buscan columnas lo hacen por texto visible.
- La entrada "Ayuda" del menú obliga a ajustar las pruebas del menú que esperaban "ninguna sección" para un rol sin permisos: ahora esperan solo "Ayuda".
- Una página "Ver más" abierta directamente (otra pestaña) no necesita la sesión para mostrar su contenido, pero el menú de arriba sí la pide: sin sesión restaurada, el layout ofrece "Iniciar sesión" y la página se lee igual.
- Todo texto nuevo pasa por la prueba de trazabilidad: citar un ID inexistente (`DSC-6`) o usar una clave mal escrita rompe la suite y nombra el archivo y la clave.

## Enmiendas a ADR y documentos anteriores

- **`00` §6.4:** precisado. La etapa 4 conserva la documentación de usuario completa; la ayuda contextual se adelantó a la etapa 1 (`propuesta-docs.md`).
- **`04` §2.1:** punto 8 nuevo (punto 10 de este ADR). **`04` §4 y §8:** fila del 16b entre el 16 y el 17, y las deudas de abajo.
- **`02` §4 y §13.1:** el directorio `frontend/src/ayuda/` y la viñeta de la ayuda contextual.
- **ADR-027 (menú por permisos):** la entrada "Ayuda" es la única del menú que no depende de un permiso; falla cerrada igual que las demás.
- Ningún ADR anterior se contradice.

## Deudas nominadas

1. **Al change 18b (`venta`):** los "(?)" del descuento manual en la venta (porcentaje general, porcentaje propio por línea, tope y autorización), reutilizando las claves de descuentos y el tema `topes`; y revisar los textos que citan DSC-06 y ADR-050 contra lo que la venta termine mostrando.
2. **Al change 21 (`pwa-y-bootstrap`):** la ruta de ayuda en `/ruta` (`/ruta/ayuda/:tema`) con la misma página de tema, sin conexión; en la PWA instalada, "Ver más" navega a la ruta interna en lugar de abrir otra pestaña.
3. **Duda abierta de `01` (PRC-11):** la regla dice que el precio lleva "la presentación de la que salió el costo", pero no dice cómo se elige cuando los costos por unidad base difieren (ADR-047 punto 3 tampoco). El texto de la señal "costos distintos por presentación" se limita a decir qué significa; si el usuario quiere que la ayuda explique la elección, hace falta precisar PRC-11 primero.
4. **Documentación:** los cambios a `docs/00`, `docs/02` y `docs/04` de `openspec/changes/16b-ayuda-contextual/propuesta-docs.md` no se aplican hasta que el usuario los apruebe.

## Alternativas consideradas

- **Cortar el change (ayuda de descuentos y precios ahora, compras y stock en un 16c), o solo Descuentos y Topes (B y C de D0):** descartadas: la primera suma un proposal y una fila más por 9 claves que son texto; la segunda deja precios, compras y jornadas sin ayuda hasta otro change.
- **Adelantar todo, manual incluido, o no adelantar y usar el atributo `title` (B y C de D1):** descartadas: la primera escribe un manual de pantallas que todavía cambian (venta, ruta); la segunda no anda con el dedo ni con el teclado y los lectores de pantalla lo leen mal.
- **El atributo `popover` del navegador, o una librería de popover (B y C de D2):** descartadas: jsdom no implementa `showPopover` y en navegadores viejos de teléfonos no anda; la librería suma una dependencia fuera del stack y obliga a reconstruir la imagen.
- **Un JSON, o un Markdown por tema (B y C de D3):** descartadas: el JSON deja las claves sin tipo y sin comentarios para el mantenedor; el Markdown son dos lugares y un parser nuevo.
- **Mostrar los IDs al pie del panel, o solo en las páginas "Ver más" (B y C de D4):** descartadas: ruido en el teléfono para quien no conoce `docs/01`; el punto intermedio no justifica un caso especial.
- **Abrir "Ver más" en la misma pestaña, o en un `Dialogo` sin página (B y C de D5):** descartadas: se pierde lo cargado en el formulario; el diálogo no tiene índice ni dirección para volver a leerlo, contra lo acordado ("una página de ayuda").
- **Que cada tema declare el permiso que lo muestra, u ocultar solo "topes" (B y C de D6):** descartadas: más código y pruebas para ocultar justo lo que un vendedor necesita entender; la segunda es un caso especial sin regla en `docs/` que lo pida.
- **Crear ya `/ruta/ayuda/:tema`, o servir los textos desde el backend (B y C de D7):** descartadas: una ruta sin pantalla que la enlace; la ayuda no andaría sin conexión y contradice D3.
- **Un envoltorio `CampoConAyuda`, o `<Ayuda>` directo en cada pantalla (B y C de D8):** descartadas: dos componentes de campo para lo mismo; cada pantalla armaría la fila a mano con riesgo de meter el botón dentro del `<label>`.
- **Solo las claves que nombró el usuario, o un "(?)" en cada campo (B y C de D9):** descartadas: la primera deja sin ayuda bonificación, umbral, vigencia, señales, sin precio y precio manual; la segunda llena de ruido "Nombre" y "Observación" y oculta lo importante.
- **Solo la prueba automática, o solo el punto de la definición de terminado (B y C de D10):** descartadas: con la primera nada obliga a que un change nuevo traiga su ayuda; con la segunda una clave borrada o un ID mal escrito pasa sin aviso.
