# Tareas — 16b-ayuda-contextual

> Modo TDD estricto: en cada tarea de los grupos 1 a 8, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Nada de aserciones triviales: cada prueba ejercita un comportamiento (abrir, cerrar, foco, texto visible, falla de una clave).
>
> **Decisiones:** D0 a D10 de `design.md` APROBADAS el 2026-10-15 (opción A). Ajuste aplicado al empezar el apply: se quitó la clave `descuentos.operador` (quedan 27) de spec y tareas; valen los textos de "Revisión del usuario" de D9.
>
> **Dónde va el código:** el componente en `frontend/src/components/ui/Ayuda.tsx`; los textos y las páginas en `frontend/src/ayuda/` (`textos.ts`, `AyudaIndiceScreen.tsx`, `AyudaTemaScreen.tsx`); las pruebas en `frontend/tests/unit/` (`components/`, `ayuda/` y las de cada área). Sin backend, sin migración y sin dependencias nuevas.
>
> **Gobernanza:** **BAJO** (grupos 1 a 4 y 6: componente, archivo, prueba de trazabilidad, páginas, menú). **MEDIO** (grupo 5: el contenido de los textos explica reglas de negocio; se copia el texto aprobado en D9, sin ampliarlo; un texto que necesite decir algo que la regla no dice se detiene y se consulta; grupo 7: ADR y propuesta de docs).
>
> **Lotes:** uno solo (D0 = A). No se frena a esperar revisión hasta el final.
>
> **Cómo correr las suites:** las de frontend con Docker detenido: `npm run test`, `npm run typecheck`, `npm run lint`.

## 0. Aprobación (bloqueante)

- [x] 0.1 El usuario revisa y aprueba (o cambia) D0 a D10 de `design.md`, de a una y con su ejemplo, y en D9 **cada texto** del inventario. Se anota fecha y opción en cada decisión y se ajustan proposal, spec y tareas si alguna no es la A. Verificable: `design.md` sin ninguna "PENDIENTE".

## 1. Componente `Ayuda`

- [x] 1.1 RED en `frontend/tests/unit/components/Ayuda.test.tsx` (requisitos "El botón de ayuda se abre con clic, tap o teclado" y "La ayuda es accesible con lector de pantalla"; cita ADR-051), con un archivo de textos de prueba inyectado o con claves reales: el botón tiene nombre "Ayuda: <título>", `aria-expanded="false"` y `aria-controls` hacia el panel; clic abre (texto y ejemplo visibles, `aria-expanded="true"`); Enter y Espacio abren y no envían el `<form>` que lo contiene; Escape cierra y devuelve el foco al botón; `pointerdown` fuera cierra, dentro del panel no; volver a activar el botón cierra; abrir un segundo `Ayuda` cierra el primero; con `verMas` muestra el enlace "Ver más" hacia `/admin/ayuda/<tema>` con `target="_blank"` y `rel` que incluye `noopener`; sin `verMas` no hay enlace. GREEN en `components/ui/Ayuda.tsx` (D2 = A), sin dependencias. Verificable: `npm run test -- tests/unit/components`.
- [x] 1.2 Red de seguridad: suites que usan `Campo` en verde, anotar la línea base. RED en `frontend/tests/unit/components/Field.test.tsx`: `Campo` sin `ayuda` se ve como hoy; con `ayuda` muestra el "(?)" al lado de la etiqueta y **fuera** del `<label>` (activar el botón no enfoca el control; la etiqueta sigue asociada al control). GREEN en `components/ui/Field.tsx` (D8 = A). Verificable: la línea base sigue en verde.

## 2. Archivo único de textos

- [x] 2.1 RED en `frontend/tests/unit/ayuda/textos.test.ts` (requisito "El texto es corto, trae un ejemplo y cita su regla"): toda entrada de `AYUDAS` tiene título y texto no vacíos y al menos un ID en `reglas`; todo `verMas` apunta a un tema de `TEMAS`; todo tema tiene título, al menos una sección y al menos un ID. GREEN: `frontend/src/ayuda/textos.ts` con los tipos `ClaveDeAyuda` y `TemaDeAyuda` (D3 = A), las 27 claves con el texto **aprobado** en D9 (copiado, no reescrito) y los tres temas. Verificable: `npm run typecheck` rechaza una clave inexistente (se comprueba con una línea `// @ts-expect-error` en la prueba).
- [x] 2.2 RED en `frontend/tests/unit/ayuda/trazabilidad.test.ts` (requisito "Todos los textos viven en un único archivo"; D10 = A, punto 2): (a) recorre `frontend/src/**/*.tsx`, junta las claves de `<Ayuda clave="…">` y de `ayuda="…"` y exige que cada una exista en `AYUDAS`, nombrando archivo y clave si no; (b) cada ID de `reglas` existe en `docs/01-dominio.md` como primera columna de una tabla (`| DSC-03 |`) o, si es `ADR-NNN`, como archivo en `docs/adr/`; (c) si `docs/` no se encuentra, falla con un mensaje claro (no se saltea). TRIANGULATE con un archivo de prueba que usa una clave mal escrita y una entrada con `'DSC-6'`: las dos fallan con su nombre. GREEN si hace falta. Verificable: la prueba pasa con el archivo real.

## 3. Páginas "Ver más"

- [x] 3.1 RED en `frontend/tests/unit/ayuda/AyudaScreens.test.tsx` (requisito "Las páginas 'Ver más' explican los temas largos"): `/admin/ayuda` lista los tres temas con enlaces; `/admin/ayuda/descuentos`, `/topes` y `/precio` muestran el título y las secciones del tema con sus ejemplos (los del spec: 9,84 %; "una autorización cubre toda la venta"; $7.800,00 y $8.571,43 → $8.600 / $8.600 / $8.500); `/admin/ayuda/no-existe` muestra "No encontramos ese tema de ayuda" con enlace al índice; ninguna página hace una petición (se comprueba que `fetch` no se llama). GREEN en `ayuda/AyudaIndiceScreen.tsx` y `ayuda/AyudaTemaScreen.tsx` (D5 = A), con la página de tema reutilizable fuera de `/admin` (D7 = A).
- [x] 3.2 Red de seguridad: `app-routing` y las pruebas de `AdminLayout` en verde. RED: un usuario de Administración (sin `GESTIONAR_DESCUENTOS`) ve "Ayuda" en el menú y entra a los tres temas (D6 = A); el resto del menú no cambia. GREEN en `areas/admin/AdminScreen.tsx` (rutas `ayuda` y `ayuda/:tema` con `Suspense`) y `AdminLayout.tsx` (entrada "Ayuda" al final). Verificable: `npm run test`.

## 4. Descuentos y topes en pantalla (claves 1 a 10)

- [x] 4.1 Red de seguridad: suites de `areas/admin/descuentos` en verde. RED (requisito "Las pantallas de descuentos explican sus reglas"; cita DSC-03, DSC-05, DSC-06): en el formulario de regla, los "(?)" de "Alcance de la regla", "Medida", "Umbral", "Acción", "Prioridad", "Acumulable" y vigencia existen y abren su texto (al menos "Umbral" con 60 unidades, "Prioridad" con "número más bajo" y "Acumulable" con 9,84 %); abrir uno no cambia lo cargado ni envía; el detalle de una regla en borrador muestra el "(?)" junto a "Activar"; "Topes por rol" lo muestra en "Tope de descuento (%)" con "Ver más" a `topes`. GREEN agregando las claves en `ReglaFormScreen`, `ReglaDetalleScreen` y `TopeDialogo`, sin otra lógica.

## 5. Listas de precios, compras y stock en pantalla (claves 11 a 28, numeración original; la 3 eliminada)

- [x] 5.1 Red de seguridad: suites de `areas/admin/precios` en verde. RED (requisito "Las pantallas de listas de precios explican sus reglas"; cita PRC-02, PRC-12, PRC-13): "(?)" en el redondeo de la lista, el redondeo por categoría, "Tipo de margen" (con $7.800,00 y $8.571,43), "Se aplica a" (con la precedencia), "Generar borrador", las señales, "Productos sin precio", "Precio manual" y la vigencia de publicación. GREEN en `ListaFormScreen`, `RedondeosDeCategoria`, `ReglaDialogo`, `BorradorScreen`, `PrecioManualDialogo` y `PublicarDialogo`.
- [x] 5.2 Red de seguridad: suites de `areas/admin/compras` y `areas/admin/proveedores` en verde. RED (requisito "Las pantallas de compras y costos explican sus reglas"; cita CST-02, CST-06, CST-11, CMP-04): con una organización que computa crédito fiscal, el "(?)" de "Valor" muestra el ejemplo de unos $1.239,67; con una monotributista, el de "Valor pagado" muestra $1.815 (la pantalla elige la clave con el dato que ya usa para la etiqueta); "Bonificación %", costo base y "Total de factura"; el resultado de la compra, junto a "Registrar como costo informado", muestra el promedio de $1.050; la carga de costos usa las mismas claves. GREEN en `CompraFormScreen`, `CostosCargaScreen` y `CompraResultado`.
- [x] 5.3 Red de seguridad: suites de `areas/admin/stock` en verde. RED (requisito "Las pantallas de stock y jornadas explican la toma de ubicación"; cita STK-09, RUT-09): "(?)" en "Requiere toma", en "Toma actual" del listado y en la apertura de jornada, y junto a "Liberar" en el detalle de jornada (visible solo donde ya se ve "Liberar"). GREEN en `UbicacionFormScreen`, `UbicacionesListScreen`, `JornadaAbrirScreen` y `JornadaDetalleScreen`.

## 6. Ancho de teléfono

- [x] 6.1 RED: el panel lleva un ancho máximo relativo al viewport y un `z-index` mayor que el de `Dialogo` (prueba de clases en `Ayuda.test.tsx`, con el `(?)` dentro de un `Dialogo` abierto: el panel se ve y cierra con Escape **sin cerrar el diálogo**). GREEN si hace falta. Verificable: `npm run test`, `npm run typecheck` y `npm run lint` en verde.

## 7. Cobertura, ADR y propuesta de documentación

- [x] 7.1 Cada escenario de `specs/sistema/ayuda-contextual/spec.md` tiene al menos una prueba (tabla escenario → prueba en el resumen). Suite completa del frontend en verde (`npm run test`, `npm run typecheck`, `npm run lint`, `npm run build`), sin `skip` ni `xfail` injustificados. Backend sin cambios (`git diff --stat backend/` vacío).
- [x] 7.2 Redactar `docs/adr/ADR-051-ayuda-contextual.md` en estado *Propuesto*, con el formato de ADR-049 y ADR-050 (tabla de estado, contexto, decisión numerada, consecuencias, enmiendas, deudas nominadas, alternativas): lo aprobado en D0 a D10; qué precisa de `00` §6.4; el punto 8 de `04` §2.1; las deudas al 18b (los "(?)" del descuento manual en la venta) y al 21 (`/ruta/ayuda` sin conexión; "Ver más" en la PWA instalada) y la duda abierta de PRC-11.
- [x] 7.3 Revisar `propuesta-docs.md` contra lo aprobado y dejarlo con el **texto actual y el propuesto** de `00` §6.4, `04` §2.1, §4 y §8 (**no se aplica a `docs/` sin el visto bueno del usuario**).

## 8. Verificación manual (último paso)

- [x] 8.1 Si se agregó alguna dependencia (no debería, D2 = A), reconstruir la imagen del frontend; si no, decirlo en el resumen.
- [x] 8.2 El orquestador le da al usuario, en el chat, el paso a paso para probar en el navegador, y el usuario avisa el resultado (sin archivo `verificacion.md`): como Administrador, abrir "Nueva regla" y tocar los "(?)" de "Medida", "Umbral", "Prioridad" y "Acumulable" con el mouse, con Tab + Enter y cerrar con Escape y con un clic afuera; comprobar que lo cargado no se pierde; seguir "Ver más" y ver la página en otra pestaña; abrir "Topes por rol" y su "(?)"; en Listas de precios, los "(?)" de margen, precedencia, redondeo y publicación; en Compras, "Valor" y "Total de factura" y, al confirmar una compra, el de costo promedio; en Stock, "Requiere toma", "Toma actual" y "Liberar"; repetir dos o tres con el navegador en ancho de teléfono (o desde el teléfono); entrar como Administración y abrir "Ayuda" desde el menú; abrir `/admin/ayuda/no-existe`. Leer cada texto y avisar cuál corregir. Se le recuerda que el efecto de reglas y topes en una venta se ve recién en el 18b. Las correcciones se hacen con prueba primero.
