# Change 20-nota-de-venta

## Qué resuelve este change

Genera en el dispositivo, con pdfmake, la nota de venta de una venta confirmada (VTA-13), la comparte con Web Share API o la descarga como respaldo, y la reimprime desde el detalle de la venta en `/admin`. Es la misma función que el change 22a usará sin conexión.

## Why

`04` §9, fila 20 (VTA-13; ADR-008; `02` §13.6). Deudas que llegan al 20: del **11b** (ADR-045), la organización inicial es monotributista y vende a precio final (modo A), pero la nota no debe quedar atada al monotributo: el usuario pidió (2026-10-27) que sirva para los modos A, B y C (ADR-009, VTA-04) según el modo congelado en la venta (A y B en este change; C diferido a la etapa 4, D14); del **19** (ADR-058), decidir si la nota de una venta anulada lleva una marca. Hoy el cliente no se lleva comprobante, y el despliegue temprano (27a) espera a este change.

## What Changes

- **Nota de venta** (VTA-13): datos de la organización y del cliente, número, fecha y hora, vendedor, líneas en su presentación con precio, bruto, descuento y neto, total, cobranza con sus medios, saldo resultante si la organización lo configura y la leyenda "Documento no válido como factura" (ADR-008). El IVA se presenta según el `modo_impositivo` congelado en la venta, no según la condición actual de la organización: modo A sin IVA (precio final, ADR-045); modo B con neto, una fila de IVA por alícuota y total (VTA-04, VTA-03); **modo C: la nota no se genera y la pantalla avisa que todavía no está disponible**, deuda nominada a la etapa 4 (`docs/` no define qué guardan las columnas de la línea en modo C ni el rótulo del IVA contenido). Como la confirmación rechaza B y C hasta la etapa 4, esos modos se prueban con ventas fabricadas (`design.md` D3, D4, D7, D12, D14).
- **Generación en el dispositivo** (`02` §13.6): una función pura arma el contenido a partir de datos neutros de la venta; otra lo convierte en el documento de pdfmake, cargado bajo demanda con fuentes embebidas. El 22a solo agrega el adaptador desde Dexie (D1, D8).
- **Compartir o descargar** (ADR-008): "Compartir nota" con Web Share API (archivos) cuando el navegador lo admite; "Descargar nota" siempre, como respaldo (D9).
- **Lectura `GET /api/v1/ventas/{venta_id}/nota`**: todos los datos de la nota en una llamada, con `VENDER` o `ANULAR_VENTA`, 404 entre organizaciones (D2, D13).
- **Venta anulada**: la nota lleva la marca "ANULADA" con fecha y motivo, y no muestra saldo (D5).
- **Configuración de la nota**: comando `NOTA_VENTA_CONFIGURAR` v1 (`ADMIN_CONFIGURACION`, auditado) con "mostrar saldo" (por defecto no) y domicilio y teléfono opcionales de la organización; migración con tres columnas en `configuracion_organizacion` y pantalla en Configuración (D3, D4, D10).
- **Nombre y CUIT de la organización** (D15, ampliación aprobada el 2026-10-28 tras la prueba manual): se editan en Configuración y se guardan en `organizacion.nombre` (obligatorio, hasta 200 caracteres) y `organizacion.cuit` (opcional, 11 dígitos, vacío = nulo) por un comando con `ADMIN_CONFIGURACION`, auditado, solo con conexión. Sin migración. Comando propio `ORGANIZACION_DATOS_CONFIGURAR`, en la sección "Datos de la organización" (`/admin/configuracion/organizacion`); el CUIT se valida solo por largo (sin dígito verificador); sin ayuda contextual nueva.
- **Pantallas `/admin`**: botones en "Venta registrada" y en el detalle, la pantalla de configuración y la ayuda contextual (D11).

## Decisiones

`design.md` D15 (nombre y CUIT de la organización) **aprobada el 2026-10-28** (comando propio, sección propia, CUIT sin dígito verificador, sin ayuda nueva). D0 a D13 **aprobadas por el usuario el 2026-10-27**, todas con la opción A (incluidas D3 domicilio y teléfono, D4 saldo congelado opcional, D5 marca ANULADA, D12 nombre y leyenda), y los textos de ayuda de D11 (tarea 0.2). **D14 aprobada el 2026-10-27 (tarea 0.3):** modo B con la opción A (Neto, una fila "IVA {alícuota} %" por alícuota, incluida la de 0 %, en orden descendente, y Total; sin columna "IVA %"); modo C diferido a la etapa 4 (la nota se rechaza con `NOTA_MODO_C_NO_DISPONIBLE` y se avisa; Q1 y Q2 pasan a esa deuda). Borrador **ADR-059** (*Propuesto*).

## No incluye

Nota de las ventas de modo C (deuda de la etapa 4, D14); generación sin conexión desde Dexie y envío por WhatsApp sin señal (22a, `00` §9 criterio 7); precarga del módulo de PDF en el service worker (21); comprobante de cobranza (COB-06, etapa 2); plantillas por organización; impresoras térmicas; facturación (Factura C, módulo aparte, ADR-007); alta autoservicio de organizaciones (onboarding, `00` §6.4, etapa 4).

## Invariantes

No cierra invariantes de `01` §20. Respeta: **INV-21** (404 entre organizaciones, prueba dinámica de rutas); **INV-06** (doble envío del comando); **INV-03** (importes como string); **INV-10** (la nota muestra lo congelado, no recalcula). Sin cambios en reglas de cálculo: **no agrega ni modifica fixtures compartidos** (reutiliza PRC-22 y CRE-02 ya cubiertos; el desglose de IVA por alícuota suma valores congelados, no recalcula VTA-04). **INV-06** también para el nombre y el CUIT (D15). **INV-14** (las filas de IVA suman el `total_iva` congelado).

## Capabilities

### New Capabilities

- `ventas/nota-de-venta`: contenido, lectura, generación, compartir y descargar, reimpresión y marca de anulada.

### Modified Capabilities

- `organizacion/parametros-de-organizacion`: parámetros de la nota por comando y pantalla.
- `sistema/pipeline-de-comandos`: tipos `NOTA_VENTA_CONFIGURAR` y, según D15, `ORGANIZACION_DATOS_CONFIGURAR` en el catálogo.
- `sistema/ayuda-contextual`: textos de la nota y de su configuración.

## Impact

Backend: `ventas/` (lectura), `identidad/` (comando y columnas), una migración. Frontend: dependencia `pdfmake` (reconstruir la imagen de Docker), `domain/ventas/`, `lib/nota/`, pantallas de ventas y configuración, `ayuda/textos.ts`. Docs y ADR-059. Gobernanza **MEDIA** (lectura y configuración, sin libros ni dinero).
