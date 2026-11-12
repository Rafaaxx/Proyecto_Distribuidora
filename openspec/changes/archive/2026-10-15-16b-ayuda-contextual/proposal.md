# Change 16b-ayuda-contextual

## Qué resuelve este change

Agrega ayuda en pantalla: un botón "(?)" junto a los campos con reglas no obvias, que se abre con clic, tap o teclado y explica la regla en 2 o 3 líneas con un ejemplo, más tres páginas "Ver más" para los temas largos. Todos los textos viven en un único archivo del frontend.

## Why

Al probar el change 16 (2026-10-15) el usuario no entendía "cajas equivalentes", cómo interactúan prioridad y acumulables ni cómo funcionan los topes, y pidió explicaciones en pantalla. Lo mismo pasa con precios, compras y jornadas. `00` §6.4 deja la ayuda contextual para la etapa 4; este change la adelanta (D1, ADR-051).

## What Changes

- **Componente `Ayuda`** propio (sin dependencias): botón "(?)" con nombre accesible y panel no modal; abre con clic, tap, Enter o Espacio y cierra con Escape, clic afuera o el mismo botón. `Campo` acepta una clave de ayuda opcional.
- **Archivo único** `frontend/src/ayuda/textos.ts`: por clave, título, texto, ejemplo, IDs de regla y tema "Ver más". Una clave inexistente no compila; una prueba verifica cada clave usada y cada ID citado contra `docs/`.
- **Páginas "Ver más"** en `/admin/ayuda`: "Cómo se aplican los descuentos", "Cómo funcionan los topes" y "Cómo se calcula el precio de una lista"; entrada "Ayuda" en el menú.
- **Ayuda en las pantallas actuales** (27 claves, inventario en `design.md` D9): Descuentos y Topes por rol (DSC-02 a DSC-07, ADR-050), Listas de precios (PRC-01 a PRC-19), Compras y costos (CST-02, CST-04, CST-06, CST-11, CMP-02 a CMP-04), Stock y jornadas (STK-02, STK-09, RUT-01, RUT-09).
- **Regla hacia adelante:** `04` §2.1 suma un punto: todo change con funcionalidad no obvia trae sus "(?)", cada uno citando su regla (D10).

## Decisiones (bloqueantes)

`design.md` D0 a D10, **pendientes de aprobación**. D1 (adelantar una funcionalidad de la etapa 4) y D10 (definición de terminado) requieren **ADR-051**; D9 (los textos) se revisa texto por texto. Duda abierta de `docs/`, sin resolver acá: PRC-11 no dice de qué presentación sale el costo cuando hay "costos distintos por presentación".

## Tamaño

Uno o dos días. Si el inventario resulta grande, D0 propone cortar Compras y Stock a un `16c`.

## No incluye

Ayuda en `/ruta` (sin pantallas todavía; deuda al 18b y al 21, D7). Ayuda en pantallas simples (catálogo, clientes, cuentas corrientes, pagos, importación). Manual de usuario, búsqueda, textos editables por la organización, traducciones. Backend, base o reglas nuevas: ningún texto define una regla.

## Invariantes

No toca ninguno: no hay escrituras, cálculos ni datos de negocio. No agrega ni modifica fixtures compartidos.

## Capabilities

### New Capabilities

- `sistema/ayuda-contextual`: el botón "(?)" y su accesibilidad, el archivo único con su trazabilidad a reglas, las páginas "Ver más" y la ayuda de las pantallas de descuentos, precios, compras y stock.

### Modified Capabilities

Ninguna: las pantallas no cambian de comportamiento; la ayuda se especifica en la capacidad nueva.

## Impact

Frontend: `components/ui/Ayuda.tsx`, `components/ui/Field.tsx` (prop opcional), `ayuda/` (textos y páginas), `areas/admin/AdminScreen.tsx` y `AdminLayout.tsx`, 14 pantallas de `areas/admin/` (solo agregan claves). Docs: ADR-051 y `propuesta-docs.md`. Sin backend, migración ni dependencias. Gobernanza **BAJA** (componente, rutas) y **MEDIA** (contenido de los textos, que el usuario revisa).
