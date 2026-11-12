# nota-de-venta Specification

## Purpose

Entregar al cliente el comprobante interno de una venta confirmada, sin validez fiscal, generado en el dispositivo, compartible o descargable y reimprimible desde administración (VTA-13, ADR-008), para ventas de los modos impositivos A y B según el modo congelado en la venta; la nota de una venta de modo C queda como deuda de la etapa 4 y, hasta entonces, no se genera. Escrita con las opciones A de `design.md` D0 a D14, aprobadas el 2026-10-27 (D14 en la tarea 0.3).

## Requirements

### Requirement: Los datos de la nota se leen en una sola llamada

El sistema DEBE ofrecer `GET /api/v1/ventas/{venta_id}/nota`, con `VENDER` o `ANULAR_VENTA`, que devuelva los datos de la organización (nombre, CUIT, domicilio y teléfono configurados), su zona horaria, si muestra saldo, los del cliente (nombre, razón social, documento, dirección, si es consumidor final), número, momento, vendedor, modo impositivo congelado, estado, las líneas congeladas en su orden con su presentación, su alícuota y su IVA, los totales (neto, IVA y total), la cobranza con sus medios e importes, el saldo de la nota y la anulación si existe. Los importes DEBEN viajar como string. NO DEBE incluir costos ni el snapshot de crédito. Una venta inexistente o de otra organización DEBE responder 404 (`design.md` D2, D13).

#### Scenario: Venta con cobranza
- **GIVEN** la venta V03-000142 a Kiosco La Esquina por $80.000 con una cobranza de $20.000 en efectivo
- **WHEN** el usuario `vendedor` pide su nota
- **THEN** recibe 200 con `"total": "80000.00"`, la cobranza `"importe": "20000.00"` con el medio "Efectivo" y su importe, las líneas en su orden y sin `costo_unitario` ni crédito
- **Regla:** VTA-13; INV-03; VTA-11

#### Scenario: Valores congelados
- **GIVEN** una venta confirmada y, después, una nueva versión de la lista con otro precio
- **WHEN** se pide su nota
- **THEN** los precios, brutos, descuentos, netos, alícuotas, IVA y el modo impositivo son los congelados en la venta
- **Regla:** VTA-03; INV-10

#### Scenario: Venta de modo B con alícuotas
- **GIVEN** una venta de modo B insertada directamente en la base por la prueba (la confirmación rechaza B hasta la etapa 4) con líneas al 21 % y al 10,5 %
- **WHEN** se pide su nota
- **THEN** recibe `"modo_impositivo": "B"`, cada línea con `"alicuota"` (por ejemplo `"0.210000"`) e `"importe_iva"` como string, y `total_neto`, `total_iva` y `total` congelados
- **Regla:** VTA-03; INV-03; INV-14

#### Scenario: Sin permiso
- **WHEN** un usuario sin `VENDER` ni `ANULAR_VENTA` pide la nota
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **Regla:** SEG-06; `01` §19

#### Scenario: Otra organización
- **WHEN** se pide la nota de una venta de otra organización o de un identificador inexistente
- **THEN** responde 404, sin distinguir los dos casos
- **Regla:** INV-21; SEG-07

### Requirement: La nota muestra lo que exige VTA-13

La nota DEBE titularse "Nota de venta" y mostrar: número; fecha y hora en la zona horaria de la organización; vendedor; nombre y CUIT de la organización y, si están configurados, su domicilio y teléfono; nombre del cliente y, si existen, razón social, documento y dirección, o "Consumidor final"; cada línea con su cantidad en la presentación, producto y presentación, precio por presentación, bruto, descuento e importe neto; subtotal, descuentos si los hay, las filas de IVA que correspondan al modo impositivo congelado (requisito siguiente) y total; la cobranza con cada medio e importe, o que no hubo cobro en el acto; el saldo si corresponde; y al pie la leyenda "Documento no válido como factura". NO DEBE mostrar nombres de reglas de descuento, autorizadores, costos ni datos de crédito (`design.md` D3, D7, D12).

#### Scenario: Línea en cajas y unidades
- **GIVEN** una venta con 2 cajas de 12 y 3 unidades del mismo producto
- **WHEN** se arma la nota
- **THEN** aparecen dos líneas, cada una con su cantidad en su presentación y su importe congelado
- **Regla:** VTA-02; CAT-08; VTA-13

#### Scenario: Precio por presentación
- **WHEN** se arma una línea de 2 cajas de 12 con precio de referencia por unidad
- **THEN** el precio que muestra es el de una caja, calculado con la misma regla del bruto, y el bruto es el congelado
- **Regla:** PRC-22; VTA-03

#### Scenario: Consumidor final
- **WHEN** se arma la nota de una venta al consumidor final
- **THEN** el cliente aparece como "Consumidor final" y no se muestra saldo
- **Regla:** CLI-03; VTA-13

#### Scenario: Leyenda
- **WHEN** se arma cualquier nota
- **THEN** lleva el título "Nota de venta" y al pie "Documento no válido como factura"
- **Regla:** VTA-13; ADR-008

#### Scenario: Datos opcionales ausentes
- **GIVEN** una organización sin domicilio ni teléfono configurados y un cliente sin documento
- **WHEN** se arma la nota
- **THEN** esos renglones no aparecen, sin etiquetas vacías
- **Regla:** VTA-13; CLI-01

### Requirement: La nota presenta el IVA según el modo impositivo congelado en la venta

La nota DEBE presentar el IVA según el `modo_impositivo` congelado en la venta, y NO DEBE depender de la condición frente al IVA ni del modo impositivo actuales de la organización. Los importes de IVA DEBEN salir de los valores congelados (`alicuota` e `importe_iva` de cada línea, `total_neto`, `total_iva` y `total` de la venta), sin recalcularlos. En **modo A** la nota DEBE mostrar los importes a precio final y NO DEBE mostrar fila ni columna de IVA. En **modo B** DEBE mostrar las líneas con sus importes netos, el **Neto** de la venta, una fila **"IVA {alícuota} %"** por cada alícuota presente en la venta, en orden descendente, con la suma de los IVA de las líneas de esa alícuota, y el **Total**. En **modo C** la nota NO DEBE generarse: el armado DEBE rechazar la venta con el error `NOTA_MODO_C_NO_DISPONIBLE` y la pantalla DEBE avisar que la nota todavía no está disponible para ventas con IVA incluido, sin ofrecer "Compartir nota" ni "Descargar nota"; la presentación del modo C es deuda de la etapa 4 (`design.md` D7, D14, Q1, Q2). La lectura de los datos de la nota NO DEBE rechazar por modo.

#### Scenario: Modo A
- **GIVEN** una venta de modo A de $80.000 con líneas de alícuota 21 % y 10,5 % congeladas
- **WHEN** se arma la nota
- **THEN** el total es $80.000, igual a la suma de los netos, y no hay ningún renglón ni columna de IVA
- **Regla:** VTA-04; ADR-045

#### Scenario: Modo B con dos alícuotas
- **GIVEN** una venta de modo B (datos fabricados: B es de la etapa 4) con una línea de neto $10.000,00 e IVA $2.100,00 al 21 %, otra de neto $4.000,00 e IVA $840,00 al 21 % y otra de neto $2.000,00 e IVA $210,00 al 10,5 %, con `total_neto` $16.000,00, `total_iva` $3.150,00 y `total` $19.150,00
- **WHEN** se arma la nota
- **THEN** muestra Neto $16.000,00, "IVA 21 %" $2.940,00, "IVA 10,5 %" $210,00 y Total $19.150,00, en ese orden
- **Regla:** VTA-04; VTA-03; INV-14; INV-10

#### Scenario: Modo B con alícuota cero
- **GIVEN** una venta de modo B (fabricada) con una línea al 21 % y otra al 0 %
- **WHEN** se arma la nota
- **THEN** hay una fila "IVA 21 %" y una fila "IVA 0 %" de $0,00, y la suma de las filas de IVA es el `total_iva` congelado
- **Regla:** VTA-04; INV-14

#### Scenario: Venta de modo C: la nota no se genera
- **GIVEN** una venta de modo C (fabricada: C es de la etapa 4) con líneas al 21 % y al 10,5 %
- **WHEN** se intenta armar su nota
- **THEN** el armado se rechaza con `NOTA_MODO_C_NO_DISPONIBLE` y no se genera ningún PDF
- **Regla:** VTA-04; ADR-059 (deuda de la etapa 4)

#### Scenario: La pantalla informa que la nota de modo C no está disponible
- **GIVEN** el detalle de una venta de modo C (fabricada)
- **WHEN** el usuario con `VENDER` lo abre
- **THEN** no aparecen "Compartir nota" ni "Descargar nota" y se ve el aviso de que la nota todavía no está disponible para ventas con IVA incluido
- **Regla:** VTA-13; ADR-059

#### Scenario: La lectura de una venta de modo C no se rechaza
- **GIVEN** una venta de modo C insertada directamente en la base por la prueba
- **WHEN** se pide `GET /ventas/{id}/nota`
- **THEN** recibe 200 con `"modo_impositivo": "C"` y sus valores congelados, sin recalcular
- **Regla:** VTA-03; INV-10

#### Scenario: El modo congelado manda sobre la condición actual
- **GIVEN** una venta de modo A registrada cuando la organización era `MONOTRIBUTO` y, después, la organización pasa a `RESPONSABLE_INSCRIPTO`
- **WHEN** se reimprime su nota
- **THEN** sale en modo A, sin ningún renglón de IVA, idéntica a la original
- **Regla:** VTA-03; INV-10; ADR-045; ADR-008

### Requirement: La nota muestra el saldo solo si la organización lo configura

Si la organización tiene activo "mostrar saldo", la nota DEBE mostrar "Saldo de la cuenta después de esta venta" igual a `saldo considerado al vender + total − cobranza registrada con la venta`, con los valores congelados de la venta; un saldo negativo DEBE mostrarse como saldo a favor. NO DEBE mostrarse si el parámetro está inactivo, si el cliente es el consumidor final, si la venta no tiene saldo considerado congelado o si la venta está anulada (`design.md` D4).

#### Scenario: Saldo resultante
- **GIVEN** "mostrar saldo" activo y una venta de $80.000 con cobranza de $20.000 a un cliente con saldo considerado de $150.000
- **WHEN** se arma la nota
- **THEN** muestra un saldo de $210.000
- **Regla:** VTA-13; CRE-02

#### Scenario: Reimpresión con el mismo saldo
- **GIVEN** la venta anterior y, después, una cobranza de $50.000 del mismo cliente
- **WHEN** se reimprime la nota
- **THEN** sigue mostrando $210.000
- **Regla:** VTA-13; CRE-02; INV-10

#### Scenario: Parámetro inactivo
- **GIVEN** "mostrar saldo" inactivo
- **WHEN** se arma la nota de esa venta
- **THEN** no hay renglón de saldo
- **Regla:** VTA-13

#### Scenario: Venta sin saldo congelado
- **GIVEN** "mostrar saldo" activo y una venta registrada antes de que existiera el snapshot de crédito
- **WHEN** se arma su nota
- **THEN** no hay renglón de saldo
- **Regla:** VTA-13; CRE-10

### Requirement: La nota de una venta anulada lleva la marca de anulada

La nota de una venta `ANULADA` DEBE generarse con la palabra "ANULADA" visible en cada página y con la fecha y hora de la anulación, su motivo y, si la venta tenía cobranza, si se devolvió lo cobrado o quedó a favor del cliente. NO DEBE mostrar saldo (`design.md` D5).

#### Scenario: Anulada con devolución
- **GIVEN** la venta V03-000142 anulada con el motivo "Error de carga" y devolución de lo cobrado
- **WHEN** se arma la nota
- **THEN** lleva la marca "ANULADA", la fecha de anulación, el motivo y "Se devolvió lo cobrado.", sin saldo
- **Regla:** VTA-20; VTA-22; ADR-058

#### Scenario: Anulada sin devolución
- **GIVEN** una venta con cobranza anulada sin devolver el dinero
- **WHEN** se arma la nota
- **THEN** dice que lo cobrado quedó a favor del cliente
- **Regla:** VTA-22

#### Scenario: Venta vigente
- **WHEN** se arma la nota de una venta `CONFIRMADA`
- **THEN** no lleva ninguna marca de anulación
- **Regla:** VTA-13

### Requirement: La nota se comparte o se descarga en el dispositivo

La nota DEBE generarse como PDF en el dispositivo, con fuentes embebidas, a partir de los datos de la venta. Si el navegador puede compartir archivos, DEBE ofrecerse "Compartir nota" con Web Share API; "Descargar nota" DEBE ofrecerse siempre. El archivo DEBE llamarse `nota-de-venta-{numero}.pdf`. Si el usuario cancela el compartir no DEBE pasar nada más; si compartir falla por otra causa, DEBE avisarse y ofrecer la descarga (`design.md` D1, D8, D9).

#### Scenario: Teléfono que comparte archivos
- **GIVEN** un navegador que admite compartir archivos
- **WHEN** el usuario toca "Compartir nota" de la venta V03-000142
- **THEN** se abre el menú de compartir con el archivo `nota-de-venta-V03-000142.pdf`
- **Regla:** VTA-13; ADR-008

#### Scenario: Escritorio sin Web Share API
- **GIVEN** un navegador que no comparte archivos
- **WHEN** se abre la venta
- **THEN** no aparece "Compartir nota" y "Descargar nota" baja el PDF
- **Regla:** ADR-008

#### Scenario: Compartir cancelado
- **WHEN** el usuario cierra el menú de compartir sin elegir destino
- **THEN** no aparece ningún error ni se descarga nada
- **Regla:** ADR-008

#### Scenario: Compartir falla
- **WHEN** compartir falla por una causa distinta de la cancelación
- **THEN** se avisa y se ofrece descargar la nota
- **Regla:** ADR-008

### Requirement: La nota se obtiene al confirmar y se reimprime desde el detalle

La pantalla "Venta registrada" y el detalle de la venta en `/admin` DEBEN ofrecer la nota a quien tiene `VENDER` o `ANULAR_VENTA`. La nota reimpresa DEBE ser idéntica a la original, salvo la marca de anulada si la venta se anuló después. Si la lectura de la nota falla, la pantalla DEBE avisarlo y permitir reintentar sin perder la venta registrada (`design.md` D2, D6).

#### Scenario: Recién confirmada
- **GIVEN** el usuario `vendedor` acaba de confirmar la venta V03-000142
- **WHEN** toca "Descargar nota" en "Venta registrada"
- **THEN** baja la nota de esa venta
- **Regla:** VTA-13

#### Scenario: Reimpresión idéntica
- **WHEN** el usuario `admin` reimprime desde el detalle una venta vigente
- **THEN** la nota tiene el mismo contenido que la generada al confirmarla, sin leyenda de copia
- **Regla:** VTA-13; ADR-008

#### Scenario: Error al leer la nota
- **GIVEN** la lectura de la nota responde con un error de red
- **WHEN** el usuario pide la nota
- **THEN** ve un aviso con la opción de reintentar y la venta sigue registrada
- **Regla:** VTA-13

### Requirement: La nota de una venta del teléfono se arma con sus datos congelados y sin señal

Al confirmar una venta en `/ruta`, el teléfono DEBE congelar en la venta local todos los datos que la nota muestra (organización, cliente, número, fecha y hora, vendedor, modo impositivo, líneas con sus nombres e importes, totales, cobranza con sus medios y, si corresponde, el saldo resultante) y DEBE generar la nota con la misma función de armado que la administración, sin conexión. Una reimpresión DEBE ser idéntica a la original aunque un bootstrap posterior cambie los datos maestros (`design.md` D15; ADR-059).

#### Scenario: Compartir sin señal
- **GIVEN** `vendedor` con la red cortada y la venta V03-000142 recién confirmada, en un teléfono que comparte archivos
- **WHEN** toca "Compartir nota"
- **THEN** se abre el menú de compartir con `nota-de-venta-V03-000142.pdf`
- **Regla:** VTA-13; `00` §9 criterio 7

#### Scenario: Reimpresión tras un bootstrap
- **GIVEN** la venta V03-000142 de "Kiosco La Esquina" y un bootstrap posterior que cambió la razón social del cliente
- **WHEN** el vendedor descarga otra vez la nota desde "Ventas de hoy"
- **THEN** la nota muestra la razón social del momento de la venta
- **Regla:** VTA-13; ADR-059

#### Scenario: Saldo en la nota
- **GIVEN** una organización con "mostrar saldo" activo y una venta de $80.000 con $20.000 cobrados a un cliente con saldo considerado de $150.000
- **WHEN** se genera la nota
- **THEN** muestra un saldo de $210.000,00
- **Regla:** VTA-13; CRE-02

#### Scenario: Consumidor final
- **GIVEN** "mostrar saldo" activo y una venta al consumidor final
- **WHEN** se genera la nota
- **THEN** dice "Consumidor final" y no muestra saldo
- **Regla:** VTA-13
