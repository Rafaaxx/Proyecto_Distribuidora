# Propuesta de cambios a `docs/` — change 20 `nota-de-venta`

> **No se aplica a `docs/` sin el visto bueno del usuario** (`CLAUDE.md` §1 y §6). Fuente: ADR-059 (punto 12 para el IVA según el modo) y `design.md` D0 a D15 (D15: nombre y CUIT de la organización, ampliación del 2026-10-28, aprobada). Cada bloque muestra el texto actual y el propuesto.

## 1. `docs/01-dominio.md` — VTA-13 (línea 338)

**Texto actual**

> La nota de venta muestra datos de la organización y del cliente, número, fecha, vendedor, líneas en su presentación, descuentos, total, cobranza, saldo resultante si la organización lo configura y la leyenda de documento no válido como factura.

**Texto propuesto**

> La nota de venta se arma solo con los valores congelados de la venta (ADR-059) y muestra: nombre, CUIT y, si están cargados, domicilio y teléfono de la organización; razón social, documento y dirección del cliente (o "Consumidor final"); número, fecha y hora en la zona de la organización y vendedor; las líneas en su presentación con cantidad, precio por presentación (PRC-22), bruto, descuento e importe; subtotal, descuentos y total; la cobranza en el acto con sus medios (o "Sin cobro en el acto"); y la leyenda "Documento no válido como factura" (ADR-008).
>
> - **Saldo:** solo si la organización activa "mostrar saldo" (por defecto no). Es el saldo resultante de CRE-02 calculado con el saldo congelado de la venta (`credito_saldo_considerado + total − cobranza de la venta`), así la reimpresión reproduce la original. No se muestra al consumidor final, en una venta sin ese dato ni en una anulada. Un saldo negativo se rotula "a favor del cliente".
> - **Venta anulada:** la nota lleva la marca "ANULADA" en cada página y una línea con la fecha, el motivo y el destino de lo cobrado (VTA-22); no lleva saldo. La reimpresión de una venta vigente es idéntica al original y no lleva marca de copia.
> - **IVA según el modo impositivo congelado en la venta** (nunca el actual de la organización): modo A, sin filas de IVA; modo B, líneas netas y, en los totales, Neto, una fila "IVA {alícuota} %" por alícuota presente (incluida la de 0 %, de mayor a menor) y Total; modo C, la nota todavía no se genera (deuda de la etapa 4, `04` §9).

## 2. `docs/01-dominio.md` — §4 Configuración por organización (tabla, después de "Medios de pago")

**Texto actual:** no existen los parámetros.

**Texto propuesto (tres filas nuevas)**

| Parámetro | Valores | Organización inicial | Etapa |
| --- | --- | --- | --- |
| Mostrar el saldo en la nota de venta | Sí / no; lo define `NOTA_VENTA_CONFIGURAR` (`ADMIN_CONFIGURACION`, solo con conexión, auditado) | No | 1 |
| Domicilio de la organización en la nota | Texto opcional, hasta 200 caracteres; vacío = nulo; mismo comando | Sin cargar | 1 |
| Teléfono de la organización en la nota | Texto opcional, hasta 50 caracteres; vacío = nulo; mismo comando | Sin cargar | 1 |

El texto demasiado largo se rechaza con `DATO_DE_NOTA_INVALIDO` (422).

**Ampliación D15 (2026-10-28, aprobada).** En la tabla del bloque 2, agregar dos filas: "Nombre de la organización | Obligatorio, recortado, hasta 200 caracteres; lo define `ORGANIZACION_DATOS_CONFIGURAR` (`ADMIN_CONFIGURACION`, solo con conexión, auditado) | El sembrado | 1" y "CUIT de la organización | 11 dígitos, opcional; vacío = nulo; mismo comando | Sin cargar (nulo) | 1". En el bloque 1 (VTA-13), el nombre y el CUIT (si está cargado) se imprimen en el encabezado. `docs/03` no cambia: `organizacion.cuit` ya existe como `text` nulable (revisar si la tabla `organizacion` lo documenta como editable). `docs/04` §9: si el usuario pide validar el dígito verificador, nominar la deuda de hacerlo en el CUIT de proveedor, cliente y organización a la vez.

## 3. `docs/02-arquitectura.md` — §13.6 Nota de venta (líneas 639 a 643)

**Texto actual**

> - Se genera en el dispositivo con pdfmake, con fuentes embebidas, a partir de los datos locales de la venta (VTA-13).
> - Se comparte con Web Share API (archivos) cuando está disponible; si no, se descarga.
> - La misma función genera la nota desde administración para reimpresión.

**Texto propuesto**

> - El contenido de la nota lo arma una función pura (`domain/ventas/notaDeVenta.ts`) a partir de un tipo neutro con los valores congelados de la venta; otra función lo convierte en la definición del documento (`lib/nota/documento.ts`, A4 vertical). Cada origen de datos tiene su adaptador: la API en administración (`GET /api/v1/ventas/{id}/nota`, con `VENDER` o `ANULAR_VENTA`) y, en `/ruta`, Dexie (change 22a). Nada del armado conoce pdfmake ni React.
> - El PDF se genera en el dispositivo con pdfmake (versión exacta) y sus fuentes embebidas, cargados con `import()` dinámico solo al generar la nota: no pesan en el bundle inicial.
> - Se comparte con Web Share API (archivos) solo si el navegador comparte archivos (`navigator.canShare`); la descarga está siempre. Archivo `nota-de-venta-{numero}.pdf`.
> - La nota no se guarda: cada generación sale de los datos congelados. La misma función sirve al original y a la reimpresión.

## 4. `docs/03-modelo-de-datos.md` — §4 `configuracion_organizacion` (después de `estado_facturacion_default`)

**Texto actual:** la tabla termina en `estado_facturacion_default`.

**Texto propuesto (tres filas nuevas)**

| Columna | Tipo | Notas |
| --- | --- | --- |
| `nota_venta_muestra_saldo` | `boolean` | `NOT NULL DEFAULT false`; si la nota imprime el saldo resultante (VTA-13, CRE-02) |
| `nota_venta_domicilio` | `text` | Nulo si no se cargó; `CHECK` de no vacío y de hasta 200 caracteres |
| `nota_venta_telefono` | `text` | Nulo si no se cargó; `CHECK` de no vacío y de hasta 50 caracteres |

## 5. `docs/04-roadmap-changes.md` — §9, después del párrafo del change 19

**Texto propuesto (párrafo nuevo)**

> **Change 20 (`nota-de-venta`) archivado — deudas saldadas (ADR-059):** del 19, la marca de la nota de una venta anulada (ADR-058). VTA-13 queda cubierto con la generación en el dispositivo, "Compartir nota" (Web Share API) y "Descargar nota", la reimpresión desde el detalle de la venta, el saldo opcional con el saldo congelado de la venta y los tres parámetros de la nota en Configuración. **Deudas nuevas:** al **21** (`pwa-y-bootstrap`), bajar en el bootstrap los parámetros de la nota (mostrar saldo, domicilio y teléfono) y los datos de la organización, y precargar el fragmento de pdfmake en el service worker; al **22a** (`cola-confirmacion-local`), el adaptador desde Dexie y compartir la nota sin señal (`00` §9 criterio 7); a la **etapa 4**, la nota de las ventas de **modo C** (hoy la pantalla avisa que todavía no está disponible y el armado la rechaza con `NOTA_MODO_C_NO_DISPONIBLE`): resolver qué guardan `precio_referencia`, `importe_bruto` e `importe_descuento` en modo C y cómo se obtienen los importes con IVA de la línea (`design.md` Q1), el rótulo y la leyenda del IVA contenido, validados con el contador si corresponde (Q2), y quitar el rechazo; y repetir la prueba manual de la nota con ventas reales de modo B (hoy cubierto con datos fabricados). Habilitar el modo C en la confirmación sin saldar esta deuda deja esas ventas sin nota.
