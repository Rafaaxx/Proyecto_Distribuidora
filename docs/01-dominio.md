# 01 — Dominio

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Versión | 1.0 |
| Fecha | 2026-09-16 |
| Depende de | `00-vision-y-alcance.md` |
| Documentos relacionados | `02-arquitectura.md`, `03-modelo-de-datos.md`, `adr/` |

## 1. Propósito y uso

Define el lenguaje del negocio, las reglas que el sistema debe cumplir, las máquinas de estado, los permisos y los invariantes. Es independiente de la tecnología: no describe tablas, endpoints ni componentes (ver `02` y `03`).

Cada regla tiene un identificador estable (`CST-03`, `VTA-04`, `INV-12`). Las specs de OpenSpec, las pruebas y los commits referencian estos identificadores. Un identificador nunca se reutiliza: si una regla se elimina, se marca como derogada.

La columna **Etapa** indica cuándo se implementa la regla. Las reglas marcadas con etapa posterior se documentan para que el modelo de la etapa 1 no las impida.

## 2. Glosario

| Término | Definición |
| --- | --- |
| Organización | Empresa que usa el sistema (tenant). Todo dato de negocio pertenece a una. |
| Unidad base | Unidad mínima e indivisible de un producto en la que se cuenta el stock (botella, lata, alfajor). Siempre entera. |
| Presentación | Forma en que un producto se compra o vende, con su cantidad de unidades base (botella = 1, caja x6 = 6). |
| Presentación de referencia | Presentación sobre la que se fija el precio de lista de un producto; normalmente la caja habitual de venta. |
| Cajas equivalentes | Cantidad base dividida por las unidades de la presentación de referencia. 15 botellas de un vino x6 = 2,5 cajas equivalentes. |
| Costo informado | Costo que comunica el proveedor, en la presentación en que lo informa, con vigencia. Se usa para calcular precios. |
| Costo base | Costo neto por unidad base, derivado de un costo informado o de una compra. |
| Costo promedio | Costo promedio ponderado móvil por unidad base de un producto. Se usa para costear ventas. |
| Costo congelado | Costo asignado a una línea de venta al confirmarla. No cambia nunca. |
| Lista de precios | Política comercial con nombre (general, mayorista, especial). |
| Versión de lista | Publicación concreta de una lista, con vigencia y precios. Inmutable una vez publicada. |
| Precio de referencia | Precio neto de un producto en su presentación de referencia dentro de una versión de lista. |
| Nota de venta | Comprobante interno de una venta, sin validez fiscal. |
| Comando | Operación de escritura enviada al servidor con un identificador único (`operation_id`). |
| Dispositivo | Navegador o teléfono registrado desde el que un usuario opera. Tiene prefijo de numeración propio. |
| Jornada | Período de trabajo de un vendedor sobre una ubicación, desde la apertura hasta el cierre. |
| Toma de ubicación | Asignación exclusiva de una ubicación a una jornada abierta. |
| Rendición | Cierre de jornada con conteo físico, comparación contra el stock esperado y registro de diferencias. |
| Bootstrap | Descarga de datos necesarios para operar sin conexión, al abrir la jornada. |
| Cuenta corriente | Libro de movimientos de un cliente o proveedor. El saldo se deriva de los movimientos. |
| Saldo | Deuda neta de un cliente con la organización, o de la organización con un proveedor. Negativo significa saldo a favor. |
| Límite de crédito | Saldo máximo aceptado para un cliente. |
| Crédito disponible | Límite de crédito menos saldo actual. |
| Exceso de crédito | Parte del saldo resultante de una venta que supera el límite. |
| Tolerancia offline | Exceso de crédito que se acepta sin autorización cuando no hay conexión. |
| Cobranza | Ingreso de dinero de un cliente, con uno o varios medios de pago. |
| Medio de pago | Instrumento de cobro o pago (efectivo, transferencia, cheque, billetera, tarjeta). Cuenta corriente no es un medio de pago. |
| Observación | Marca que el servidor agrega a una operación aceptada que requiere revisión (stock negativo, exceso detectado, etc.). |
| Anulación | Reversión total de una operación confirmada mediante movimientos inversos. |
| Ajuste | Movimiento correctivo con motivo y permiso (stock, cuenta corriente). |
| Modo impositivo | Forma en que la organización trata el IVA en precios y ventas (A, B o C). |
| Modalidad de IVA | En facturas sobre ventas sin IVA: IVA a cargo del cliente o absorbido por la organización. |
| Utilidad real | Venta neta menos costo congelado menos IVA absorbido asignado. |

## 3. Reglas transversales

| ID | Regla | Etapa |
| --- | --- | --- |
| TR-01 | Los importes monetarios se representan en decimal exacto con 2 decimales. Nunca se usan números de punto flotante binario. | 1 |
| TR-02 | Los costos por unidad base se representan con 6 decimales. Los porcentajes, con 6 decimales como fracción (21% = 0,210000). | 1 |
| TR-03 | El redondeo monetario usa "mitad hacia arriba" (0,005 → 0,01) y se aplica solo en los puntos que define cada regla. Los valores intermedios no se redondean. | 1 |
| TR-04 | Las fechas y horas se almacenan en UTC y se presentan en la zona horaria de la organización. La fecha de negocio de una operación es su `occurred_at` convertido a esa zona. | 1 |
| TR-05 | Toda operación registra dos momentos: `occurred_at` (cuándo ocurrió, informado por el dispositivo) y `registered_at` (cuándo la registró el servidor). | 1 |
| TR-06 | Ninguna operación confirmada se edita ni se borra. Las correcciones se hacen con anulaciones, ajustes o nuevas versiones. | 1 |
| TR-07 | Toda operación de escritura se identifica con un `operation_id` generado por quien la origina (ver SYN). | 1 |
| TR-08 | Todo dato de negocio pertenece a una organización y solo es visible y modificable desde ella. | 1 |
| TR-09 | Los catálogos configurables (motivos de ajuste, medios de pago, alícuotas, categorías) son datos de la organización, no valores fijos en código. | 1 |
| TR-10 | Toda validación de negocio se ejecuta en el servidor, aunque el cliente la haya ejecutado antes. | 1 |

## 4. Configuración por organización

| Parámetro | Valores | Organización inicial | Etapa |
| --- | --- | --- | --- |
| Moneda | Código ISO | ARS | 1 |
| Zona horaria | IANA | America/Argentina/Mendoza | 1 |
| Modo impositivo | A / B / C | A | 1 (B y C: 4) |
| Alícuotas de IVA disponibles | Lista | 21%, 10,5%, 0% | 1 |
| Modalidad de IVA por defecto al facturar | CLIENTE / ABSORBIDO | A definir al configurar | Facturación |
| Lista de precios por defecto | Lista | General | 1 |
| Política de crédito por defecto | ADVERTIR / AUTORIZAR / BLOQUEAR | AUTORIZAR | 1 |
| Tolerancia offline de crédito | Importe o porcentaje del límite | A definir al configurar | 1 |
| Stock negativo online | Bloqueado salvo permiso | Bloqueado | 1 |
| Descuento manual | Habilitado / deshabilitado | Habilitado | 1 |
| Motivo obligatorio en descuento manual | Sí / no | A definir | 1 |
| Motivo obligatorio al usar lista no asignada o versión anterior | Sí / no | Sí | 1 |
| Redondeo por defecto | Múltiplo y dirección | A definir | 1 |
| Venta a consumidor final genérico | Sí / no | A definir | 1 |
| Estado de facturación inicial por defecto | NO_REQUIERE / PENDIENTE | NO_REQUIERE | 1 |
| Medios de pago | Lista con indicador de referencia obligatoria | Efectivo, transferencia, cheque, billetera, tarjeta | 1 |
| Motivos de ajuste de stock | Lista | Rotura, vencimiento, muestra, consumo interno, diferencia de inventario, otro | 1 |
| Intentos fallidos de PIN antes de bloquear | Número | 5 | 1 |

## 5. Catálogo

| ID | Regla | Etapa |
| --- | --- | --- |
| CAT-01 | Todo producto tiene código único dentro de la organización, nombre, categoría, marca opcional, unidad base, alícuota de IVA y proveedor. El nombre del producto no puede quedar vacío ni de solo espacios tras recortar (`NOMBRE_INVALIDO`, 422) y la unidad base tampoco (`VALOR_OBLIGATORIO`, 422). Los textos válidos se guardan recortados. | 1 |
| CAT-02 | Un producto tiene una o más presentaciones. Cada presentación indica unidades base (entero ≥ 1), si se usa en venta y si se usa en compra. El nombre de cada presentación no puede quedar vacío ni de solo espacios tras recortar (`NOMBRE_INVALIDO`, 422); el texto válido se guarda recortado. | 1 |
| CAT-03 | Cada producto tiene exactamente una presentación de referencia, que debe usarse en venta. | 1 |
| CAT-04 | Las unidades de una presentación ya usada en alguna operación no pueden modificarse. Para cambiar el contenido se crea una presentación nueva y se desactiva la anterior. | 1 |
| CAT-05 | Un producto o presentación usado en operaciones no se elimina: se desactiva. Los inactivos no se ofrecen en nuevas operaciones. | 1 |
| CAT-06 | En la etapa 1 cada producto tiene un único proveedor. El modelo admite proveedores adicionales. | 1 (varios: 4) |
| CAT-07 | La venta de unidades sueltas requiere una presentación de venta de 1 unidad base. | 1 |

**Visualización de cantidades (CAT-08, etapa 1).** Una cantidad base `q` de un producto con presentación de referencia de `u` unidades se muestra como `floor(|q| / u)` cajas y `|q| mod u` unidades, con signo negativo si `q < 0`.

| Producto | Referencia | Cantidad base | Visualización |
| --- | --- | --- | --- |
| Vino A | Caja x6 | 31 | 5 cajas + 1 unidad |
| Cerveza B | Caja x12 | 31 | 2 cajas + 7 unidades |
| Vino A | Caja x6 | −8 | −(1 caja + 2 unidades) |

## 6. Proveedores, costos y compras

### 6.1 Costo informado

| ID | Regla | Etapa |
| --- | --- | --- |
| CST-01 | Un costo informado registra proveedor, producto, presentación, valor, si incluye IVA, bonificación opcional (porcentaje), vigencia desde y observación. | 1 |
| CST-02 | El costo base derivado se calcula como `valor × (1 − bonificación) / (1 + alícuota si incluye IVA) / unidades de la presentación`, redondeado a 6 decimales solo al final. | 1 |
| CST-03 | Los costos informados no se sobrescriben. El vigente para una fecha es el de mayor vigencia desde que no supere esa fecha. | 1 |
| CST-04 | El costo informado se usa para calcular precios. No se usa para costear ventas. | 1 |
| CST-05 | Puede cargarse un costo por producto o varios de un proveedor en una sola operación. La importación **inicial** de costos desde una planilla es de la etapa 1 (change 10, por `informar_costos`); la importación masiva **recurrente** es de la etapa 2. | 1 (importación inicial; masiva recurrente: 2) |

Ejemplos de CST-02:

| Informado | Incluye IVA | Bonificación | Costo base |
| --- | --- | --- | --- |
| Caja x12 a $18.000 | No | — | $1.500,000000 |
| Botella a $1.000 | No | — | $1.000,000000 |
| Caja x12 a $18.000 | Sí (21%) | — | 18.000 / 1,21 / 12 = $1.239,669421 |
| Caja x12 a $18.000 | No | 10% | 18.000 × 0,9 / 12 = $1.350,000000 |

### 6.2 Costo promedio

| ID | Regla | Etapa |
| --- | --- | --- |
| CST-10 | Cada producto tiene un costo promedio por organización, único para todas las ubicaciones. | 1 |
| CST-11 | Un ingreso con costo (compra, stock inicial, anulación de venta) recalcula el promedio: si el stock total previo es mayor que cero, `(stock × promedio + cantidad × costo) / (stock + cantidad)`; si es cero o negativo, el promedio pasa a ser el costo del ingreso. | 1 |
| CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio. Los egresos por ajuste, y los de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. | 1 |
| CST-13 | Cada cambio del promedio se registra con valor anterior, valor nuevo, operación origen y momento, de forma que el promedio en cualquier momento pueda reconstruirse. | 1 |
| CST-14 | El cálculo del costo de venta está encapsulado en un único servicio de costeo. Ninguna otra parte del sistema calcula costos de venta. | 1 |
| CST-15 | La estrategia FIFO podrá habilitarse desde una fecha de corte sin modificar costos congelados anteriores. | 4 |

Ejemplo de CST-11:

| Paso | Stock total | Costo promedio |
| --- | --- | --- |
| Compra 60 a $1.000 | 60 | $1.000,000000 |
| Compra 60 a $1.100 | 120 | (60.000 + 66.000) / 120 = $1.050,000000 |
| Venta 72 (costo congelado $75.600,00) | 48 | $1.050,000000 |
| Compra 60 a $1.200 | 108 | (50.400 + 72.000) / 108 = $1.133,333333 |

### 6.3 Compras

| ID | Regla | Etapa |
| --- | --- | --- |
| CMP-01 | Una compra registra proveedor, fecha, ubicación de destino, condición (contado o crédito) y al menos una línea. Cada línea indica producto, presentación de compra, cantidad, valor por presentación, si incluye IVA y bonificación opcional. | 1 |
| CMP-02 | Cada línea deriva cantidad base y costo base neto con la fórmula de CST-02. El total neto de la compra es la suma de `cantidad base × costo base` de sus líneas, redondeada a 2 decimales por línea. | 1 |
| CMP-03 | Confirmar una compra, en una sola transacción: ingresa stock en la ubicación de destino, recalcula el costo promedio de cada producto, registra la compra en la cuenta corriente del proveedor, registra el pago si es de contado y audita. | 1 |
| CMP-04 | Si el costo base de una línea difiere del costo informado vigente, el sistema ofrece registrarlo como nuevo costo informado. Nunca lo registra automáticamente. | 1 |
| CMP-05 | Una compra confirmada solo se corrige por anulación total, con permiso y motivo. La anulación egresa el stock ingresado y revierte la cuenta corriente del proveedor. | 1 |
| CMP-06 | Al anular una compra, si el stock restante es mayor que cero y el promedio resultante de revertir el ingreso es positivo, se recalcula el promedio; en otro caso se mantiene el vigente y la anulación queda con observación. | 1 |
| CMP-07 | La anulación de una compra que deje stock negativo requiere `PERMITIR_STOCK_NEGATIVO`. | 1 |
| CMP-08 | Las compras se registran solo con conexión. | 1 |
| CMP-09 | Órdenes de compra, recepción parcial, vencimientos y notas de crédito o débito de proveedor. | 2 |

### 6.4 Pagos a proveedores

| ID | Regla | Etapa |
| --- | --- | --- |
| PAG-01 | Un pago registra proveedor, fecha, importe y uno o más medios cuya suma es igual al importe. | 1 |
| PAG-02 | El pago reduce el saldo general del proveedor. No modifica costos. | 1 |
| PAG-03 | Un pago confirmado solo se corrige por anulación con permiso y motivo. | 1 |

## 7. Precios

### 7.1 Listas y versiones

| ID | Regla | Etapa |
| --- | --- | --- |
| PRC-01 | Una lista tiene nombre y regla de redondeo. Sus precios viven en versiones. | 1 |
| PRC-02 | Una versión tiene estado almacenado (BORRADOR, PUBLICADA, ANULADA), vigencia desde y vigencia hasta opcional. | 1 |
| PRC-03 | La versión vigente de una lista en un momento es la PUBLICADA con mayor vigencia desde que no supere ese momento y cuya vigencia hasta, si existe, sea posterior. Los estados PROGRAMADA, VIGENTE e HISTÓRICA se derivan de las fechas y no se almacenan. | 1 |
| PRC-04 | Una versión publicada es inmutable. Las correcciones generan una versión nueva. | 1 |
| PRC-05 | Solo puede anularse una versión publicada cuya vigencia aún no comenzó. | 1 |
| PRC-06 | Publicar requiere `PUBLICAR_LISTAS` y queda auditado. | 1 |

### 7.2 Cálculo del precio de referencia

| ID | Regla | Etapa |
| --- | --- | --- |
| PRC-10 | Cada versión tiene, por producto, un único precio de referencia sobre la presentación de referencia. Las demás presentaciones se venden a precio proporcional. | 1 |
| PRC-11 | El costo de referencia es `costo base del costo informado vigente × unidades de la presentación de referencia`. | 1 |
| PRC-12 | El margen puede ser markup (`precio = costo × (1 + m)`) o margen bruto (`precio = costo / (1 − m)`, con `m < 1`). Toda regla de margen indica cuál usa y la interfaz muestra la fórmula aplicada. | 1 |
| PRC-13 | Las reglas de margen pertenecen a una lista y se resuelven por precedencia, de más específica a más general: producto, marca, categoría, proveedor, lista. | 1 |
| PRC-14 | El redondeo se define por múltiplo (10, 50, 100, 500…) y dirección (arriba, más cercano, abajo), por lista con sobrescritura opcional por categoría. En "más cercano", el punto medio redondea hacia arriba. | 1 |
| PRC-15 | En modos A y B el redondeo se aplica al precio neto. En modo C se aplica al precio con IVA incluido. | 1 (C: 4) |
| PRC-16 | Cada precio de versión guarda costo de referencia usado, regla de margen aplicada, precio calculado sin redondear, precio final y si fue fijado manualmente. | 1 |
| PRC-17 | Ante nuevos costos informados, el sistema genera una versión BORRADOR que copia la versión vigente y recalcula los productos afectados. Los precios fijados manualmente se conservan y se señalan si su margen resultante es menor que el de la regla aplicable. | 1 |

Ejemplo (costo base del vino $1.000, caja x6, costo de referencia $6.000, redondeo a múltiplo de 100):

| Regla | Calculado | Arriba | Más cercano | Abajo |
| --- | --- | --- | --- | --- |
| Markup 30% | $7.800,00 | $7.800 | $7.800 | $7.800 |
| Margen bruto 30% | $8.571,43 | $8.600 | $8.600 | $8.500 |

### 7.3 Precio en la venta

| ID | Regla | Etapa |
| --- | --- | --- |
| PRC-20 | La lista de una venta es la asignada al cliente o, si no tiene, la lista por defecto de la organización. Se usa la versión vigente al `occurred_at` de la venta. | 1 |
| PRC-21 | Usar otra lista o una versión anterior requiere `USAR_LISTA_ANTERIOR` y motivo según configuración. | 1 |
| PRC-22 | El importe bruto de una línea es `precio de referencia × cantidad base / unidades de referencia`, redondeado a 2 decimales una sola vez. El precio unitario por presentación se muestra redondeado pero nunca se usa para calcular totales. | 1 |
| PRC-23 | La venta congela, por línea, versión de lista, precio de referencia y unidades de referencia. | 1 |

Ejemplos de PRC-22 (caja x6):

| Precio de referencia | Cantidad | Bruto |
| --- | --- | --- |
| $12.500 | 2 cajas + 3 unidades (15 base) | 12.500 × 15 / 6 = $31.250,00 |
| $8.600 | 3 unidades | 8.600 × 3 / 6 = $4.300,00 |
| $8.600 | 1 unidad | 8.600 / 6 = $1.433,33 |

## 8. Stock, ubicaciones y ruta

### 8.1 Stock

| ID | Regla | Etapa |
| --- | --- | --- |
| STK-01 | El stock se lleva por producto y ubicación, en unidades base enteras. | 1 |
| STK-02 | Una ubicación tiene nombre, tipo (depósito, vehículo, otro), estado e indicador de si requiere toma para operar. Los vehículos requieren toma. | 1 |
| STK-03 | Todo cambio de stock es un movimiento con producto, ubicación, cantidad con signo, tipo y operación origen. Tipos: STOCK_INICIAL, COMPRA, ANULACION_COMPRA, VENTA, ANULACION_VENTA, TRANSFERENCIA_SALIDA, TRANSFERENCIA_ENTRADA, AJUSTE, DIFERENCIA_RENDICION. | 1 (DEVOLUCION, RECUENTO: 2) |
| STK-04 | El stock de un producto en una ubicación es la suma de sus movimientos. | 1 |
| STK-05 | Con conexión, una operación que deje stock negativo se rechaza salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`; en ese caso se acepta con observación. | 1 |
| STK-06 | Sin conexión, una venta que deje stock negativo se acepta al sincronizar con observación STOCK_NEGATIVO. | 1 |
| STK-07 | Una transferencia genera, en la misma transacción, una salida en origen y una entrada en destino por la misma cantidad. No modifica costos. | 1 |
| STK-08 | Un ajuste requiere `AJUSTAR_STOCK` y un motivo del catálogo de la organización. | 1 |
| STK-09 | Mientras una ubicación está tomada, solo la jornada que la tomó puede generar movimientos sobre ella, salvo la rendición y usuarios con `LIBERAR_UBICACION`, con auditoría. | 1 |
| STK-10 | Un producto admite varios `STOCK_INICIAL`, cada uno con su cantidad con signo distinta de cero. Uno positivo es un ingreso con costo (CST-11); uno negativo es una corrección: egresa al promedio vigente sin recalcularlo y no puede dejar negativo el saldo de la ubicación (`STOCK_INSUFICIENTE`, sin excepción por `PERMITIR_STOCK_NEGATIVO`). Se admiten solo mientras el producto no tenga en la organización movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES`). Un costo mal cargado se corrige llevando el stock total a cero y recargando. | 1 |

### 8.2 Jornada y rendición

| ID | Regla | Etapa |
| --- | --- | --- |
| RUT-01 | Una jornada tiene usuario, dispositivo, ubicación, apertura y cierre. Una ubicación que requiere toma admite como máximo una jornada no cerrada. | 1 |
| RUT-02 | La carga del vehículo es una transferencia desde depósito, con conexión, antes o durante la apertura. | 1 |
| RUT-03 | La apertura requiere conexión y `ABRIR_JORNADA`. Toma la ubicación y ejecuta el bootstrap. | 1 |
| RUT-04 | Durante la jornada, las ventas del dispositivo descuentan stock de la ubicación tomada. | 1 |
| RUT-05 | La rendición requiere conexión, `RENDIR_JORNADA` y que el dispositivo no tenga comandos pendientes de esa jornada. | 1 |
| RUT-06 | En la rendición se registra el conteo físico por producto. La diferencia entre contado y esperado genera un movimiento DIFERENCIA_RENDICION auditado. | 1 |
| RUT-07 | El resumen de rendición muestra stock al abrir, ingresos, ventas, anulaciones, stock esperado, contado, diferencias y cobranzas por medio de pago. | 1 |
| RUT-08 | Tras la rendición puede transferirse el remanente a depósito. El cierre libera la ubicación. | 1 |
| RUT-09 | Un usuario con `LIBERAR_UBICACION` puede liberar una jornada abierta con motivo. Los comandos posteriores de esa jornada se aceptan al sincronizar con observación JORNADA_LIBERADA. | 1 |
| RUT-10 | Rendición completa de efectivo con caja y tesorería. | 2 |

## 9. Clientes y crédito

### 9.1 Clientes

| ID | Regla | Etapa |
| --- | --- | --- |
| CLI-01 | Un cliente tiene nombre, razón social y CUIT/DNI opcionales, dirección, contacto, lista asignada opcional, límite y política de crédito opcionales, tolerancia offline opcional, estado de facturación inicial opcional y estado. El estado de facturación inicial del cliente es `NO_REQUIERE`, `PENDIENTE` o nulo (el de la organización); otro valor se rechaza con `ESTADO_FACTURACION_INVALIDO` (422). | 1 |
| CLI-02 | Estados: ACTIVO, SUSPENDIDO, INACTIVO. Vender a un cliente suspendido requiere `VENDER_CLIENTE_SUSPENDIDO`. A un cliente inactivo no se le vende. | 1 |
| CLI-03 | Si la organización lo habilita, existe un cliente genérico "consumidor final" con límite de crédito cero. El consumidor final solo puede estar `ACTIVO` o `SUSPENDIDO`: no se inactiva (ADR-029). | 1 |
| CLI-04 | Los clientes con operaciones no se eliminan: se inactivan. | 1 |
| CLI-05 | El documento de un cliente se valida por tipo: los valores válidos son CUIT y DNI; el CUIT tiene 11 dígitos y el DNI entre 7 y 8, siempre solo numéricos. El número se normaliza a dígitos antes de comparar y de guardar. | 1 |
| CLI-06 | Un cliente `INACTIVO` puede volver a `ACTIVO` solo si no tiene operaciones; con operaciones, `INACTIVO` es terminal (ADR-030). | 1 |

### 9.2 Crédito (ADR-003)

| ID | Regla | Etapa |
| --- | --- | --- |
| CRE-01 | Crédito disponible = límite − saldo actual. Límite vacío significa sin control; límite cero significa solo contado. | 1 |
| CRE-02 | Una venta consume crédito solo por su parte no cobrada en el momento. El saldo resultante es `saldo actual + total de la venta − cobranza registrada con la venta`. | 1 |
| CRE-03 | Si el saldo resultante supera el límite, el exceso se trata según la política del cliente o, si no tiene, la de la organización: ADVERTIR, AUTORIZAR o BLOQUEAR. | 1 |
| CRE-04 | ADVERTIR: se muestra el exceso y el usuario puede confirmar. La venta queda con observación. | 1 |
| CRE-05 | AUTORIZAR con conexión: confirma un usuario con `SUPERAR_CREDITO` o un supervisor que ingresa su PIN en el dispositivo. | 1 |
| CRE-06 | AUTORIZAR sin conexión: si el exceso no supera la tolerancia offline (del cliente o de la organización), se confirma con observación EXCESO_CREDITO_AUTORIZADO_OFFLINE. Si la supera, se comporta como BLOQUEAR salvo permiso propio o PIN de supervisor. | 1 |
| CRE-07 | BLOQUEAR: la venta no se confirma. El usuario puede aumentar la cobranza o reducir el pedido. | 1 |
| CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada. | 1 |
| CRE-09 | Al sincronizar, el servidor recalcula con el saldo real y nunca rechaza la venta por crédito. Si detecta un exceso que el dispositivo no detectó, agrega la observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración. | 1 |
| CRE-10 | La venta congela límite, saldo considerado, disponible, exceso, política aplicada, si fue online u offline, forma de resolución y autorizador. | 1 |
| CRE-11 | Autorización remota de excepciones. | 2 |
| CRE-12 | Bloqueo por antigüedad de deuda. | 2 |

Ejemplo: límite $200.000, saldo $150.000, venta $80.000 con cobranza de $20.000. Saldo resultante $210.000, exceso $10.000. Con tolerancia offline de $20.000 se confirma con observación; con tolerancia de $5.000 se bloquea salvo permiso o PIN.

## 10. Descuentos (ADR-004)

| ID | Regla | Etapa |
| --- | --- | --- |
| DSC-01 | Una regla de descuento tiene tipo, condición, acción, alcance, vigencia, prioridad, indicador de acumulable y estado. | 1 |
| DSC-02 | Tipos de la etapa 1: VOLUMEN_OPERACION (sobre toda la venta) y VOLUMEN_ALCANCE (sobre líneas de productos, categorías o marcas determinadas). | 1 |
| DSC-03 | La condición de volumen compara, con operador explícito (≥ o >), una medida contra un umbral. Medidas: cajas equivalentes, unidades base o importe bruto de las líneas elegibles. | 1 |
| DSC-04 | Acciones de la etapa 1: porcentaje sobre las líneas elegibles o importe fijo distribuido entre ellas en proporción a su bruto; el remanente de redondeo se asigna a la línea de mayor importe. | 1 |
| DSC-05 | Orden de resolución: (1) bruto por línea desde la lista; (2) se evalúan las reglas activas y vigentes cuyo alcance aplica; (3) entre las no acumulables se aplica solo la de mayor beneficio total, con desempate por prioridad; (4) las acumulables se aplican en orden de prioridad, cada una sobre el resultado anterior; (5) se aplica el descuento manual sobre el resultado. | 1 |
| DSC-06 | El descuento manual requiere que la organización lo tenga habilitado y el permiso `DESCUENTO_MANUAL`, cuyo tope porcentual depende del rol. Superar el tope requiere `AUTORIZAR_DESCUENTO` o PIN de supervisor. | 1 |
| DSC-07 | Cada descuento se calcula y redondea a 2 decimales por línea. | 1 |
| DSC-08 | Cada línea guarda cada descuento aplicado con origen (AUTOMATICO o MANUAL), regla, porcentaje o importe, motivo y autorizador. | 1 |
| DSC-09 | Con conexión, el servidor recalcula los descuentos y rechaza la confirmación si difieren de los enviados. Sin conexión, acepta los descuentos registrados y agrega la observación DESCUENTO_DIFIERE si su cálculo no coincide. | 1 |
| DSC-10 | Fidelización por historial, promociones por cliente o segmento, precio especial, bonificación en unidades y control de margen mínimo. | 2 |

Ejemplo de DSC-03 con regla "cajas equivalentes ≥ 20 → 5%": 19 cajas + 5 unidades de un vino x6 son 19,83 cajas equivalentes y no aplica; 20 cajas aplica.

## 11. Ventas

### 11.1 Composición

| ID | Regla | Etapa |
| --- | --- | --- |
| VTA-01 | Una venta tiene `operation_id`, número de nota de venta, cliente, vendedor, dispositivo, jornada si corresponde, ubicación, `occurred_at`, `registered_at` y al menos una línea. | 1 |
| VTA-02 | Cada línea corresponde a un producto y una presentación de venta. Un mismo producto en dos presentaciones (2 cajas y 3 unidades) son dos líneas. | 1 |
| VTA-03 | Cada línea congela cantidad en la presentación, unidades de la presentación, cantidad base, versión de lista, precio de referencia, unidades de referencia, bruto, descuentos, neto, alícuota, IVA y costo. | 1 |
| VTA-04 | Neto de línea = bruto − descuentos. En modo A el IVA de la venta es cero y el total es la suma de netos. En modo B el IVA de línea es `neto × alícuota` redondeado a 2 decimales y el total es neto más IVA. En modo C el precio incluye IVA y el neto de línea se deriva dividiendo por `1 + alícuota`. | 1 (B y C: 4) |
| VTA-05 | El costo congelado de una línea es `costo promedio vigente al procesar la venta en el servidor × cantidad base`, redondeado a 2 decimales. En ventas offline, el promedio es el vigente al sincronizar. | 1 |
| VTA-06 | El número de nota de venta es el prefijo del dispositivo seguido de un correlativo del dispositivo (`V03-000142`). Es único por organización. | 1 |
| VTA-07 | El carrito y la cotización no se persisten en el servidor. Solo existen ventas confirmadas. | 1 |
| VTA-08 | El estado de facturación inicial de la venta es el configurado en el cliente o, si no tiene, el de la organización. | 1 |

### 11.2 Confirmación

| ID | Regla | Etapa |
| --- | --- | --- |
| VTA-10 | Confirmar requiere `VENDER`, cliente habilitado (CLI-02) y precio resoluble (PRC-20). | 1 |
| VTA-11 | La cobranza registrada con la venta puede ser nula, parcial, total o superior al total. El excedente reduce el saldo previo del cliente. | 1 |
| VTA-12 | Confirmar una venta registra, en una sola transacción: la venta y sus líneas, los movimientos de stock, el costo congelado, el débito por el total en la cuenta corriente, la cobranza y su crédito si existe, la evaluación de crédito, el estado de facturación, las observaciones y la auditoría. Si algo falla, no se registra nada. | 1 |
| VTA-13 | La nota de venta muestra datos de la organización y del cliente, número, fecha, vendedor, líneas en su presentación, descuentos, total, cobranza, saldo resultante si la organización lo configura y la leyenda de documento no válido como factura. | 1 |

### 11.3 Anulación

| ID | Regla | Etapa |
| --- | --- | --- |
| VTA-20 | Una venta confirmada solo se corrige por anulación total, con `ANULAR_VENTA` y motivo. | 1 (devolución parcial: 2) |
| VTA-21 | La anulación ingresa el stock a la ubicación original al costo congelado de cada línea (recalculando el promedio según CST-11) y registra un crédito en la cuenta corriente por el total de la venta. | 1 |
| VTA-22 | Al anular se indica si se devuelve el dinero cobrado con la venta. Si se devuelve, se anula también esa cobranza; si no, queda como saldo a favor. | 1 |
| VTA-23 | No se puede anular una venta con estado de facturación PARCIAL o FACTURADA sin anular antes la factura. | Facturación |
| VTA-24 | Sin conexión, un vendedor con `ANULAR_VENTA` puede anular solo ventas de su jornada en curso. La anulación es un comando que referencia el `operation_id` de la venta. | 1 |

## 12. Cuenta corriente y cobranzas

### 12.1 Cuenta corriente

| ID | Regla | Etapa |
| --- | --- | --- |
| CC-01 | La cuenta corriente de cada cliente y de cada proveedor es un libro de movimientos. Cada movimiento tiene tipo, sentido (aumenta o reduce el saldo), importe positivo, operación origen, `occurred_at` y `registered_at`. | 1 |
| CC-02 | Tipos para clientes: SALDO_INICIAL, VENTA, ANULACION_VENTA, COBRANZA, ANULACION_COBRANZA, IVA_FACTURA, ANULACION_IVA_FACTURA. | 1 (IVA: facturación; AJUSTE y notas: 2) |
| CC-03 | Tipos para proveedores: SALDO_INICIAL, COMPRA, ANULACION_COMPRA, PAGO, ANULACION_PAGO. | 1 |
| CC-04 | Saldo = suma de movimientos que aumentan − suma de movimientos que reducen. No existe un saldo editable ni un saldo acumulado por movimiento. | 1 |
| CC-05 | Una venta registra un débito por su total aunque se cobre en el momento; la cobranza registra su propio crédito. Lo mismo para compras de contado y sus pagos. | 1 |
| CC-06 | Los movimientos no se editan ni se borran. | 1 |
| CC-07 | El estado de cuenta muestra los movimientos en orden de `occurred_at` con saldo acumulado calculado al consultar. | 1 (PDF: 2) |
| CC-08 | Una cuenta admite varios movimientos `SALDO_INICIAL`, cada uno con su sentido; un error de carga se corrige con otro `SALDO_INICIAL` en sentido contrario por la diferencia. Se admiten solo mientras la cuenta no tenga movimientos de otro tipo (`CUENTA_CON_OPERACIONES`). No se carga saldo inicial al consumidor final (`CONSUMIDOR_FINAL_SIN_CUENTA`); cualquier otro estado de cliente o de proveedor lo admite. | 1 |

### 12.2 Cobranzas

| ID | Regla | Etapa |
| --- | --- | --- |
| COB-01 | Una cobranza tiene `operation_id`, cliente, `occurred_at`, importe mayor que cero, usuario, dispositivo, origen (VENTA o INDEPENDIENTE) y uno o más medios. | 1 |
| COB-02 | La suma de los medios es igual al importe. Los medios configurados con referencia obligatoria (por ejemplo transferencia) exigen referencia. | 1 |
| COB-03 | Una cobranza reduce el saldo general del cliente. En la etapa 1 no se imputa a ventas. | 1 (imputación: 4) |
| COB-04 | Las cobranzas pueden registrarse sin conexión y se consideran en el saldo local (CRE-08). | 1 |
| COB-05 | Una cobranza solo se corrige por anulación con `ANULAR_COBRANZA` y motivo. | 1 |
| COB-06 | Comprobante de cobranza compartible. | 2 |

## 13. Sincronización y comandos

| ID | Regla | Etapa |
| --- | --- | --- |
| SYN-01 | Toda operación de escritura, online u offline, es un comando con `operation_id`, tipo, dispositivo, jornada si corresponde, `occurred_at`, contenido y huella del contenido. | 1 |
| SYN-02 | Un `operation_id` es único por organización. Si llega un comando ya procesado con la misma huella, se devuelve el resultado original sin reprocesar. Si llega con distinta huella, se rechaza como inconsistente. | 1 |
| SYN-03 | Los comandos de un dispositivo se procesan en el orden en que se generaron. Un comando que depende de otro (anulación de una venta) se procesa después de él. | 1 |
| SYN-04 | Resultados posibles: ACEPTADO, ACEPTADO_CON_OBSERVACIONES o RECHAZADO. | 1 |
| SYN-05 | Una venta o cobranza registrada sin conexión nunca se rechaza por reglas de negocio (stock, crédito, lista, descuentos, estado del cliente o permisos). Se acepta con las observaciones que correspondan. | 1 |
| SYN-06 | Solo se rechazan comandos malformados, inconsistentes (SYN-02), de otra organización, con dependencias inexistentes o de dispositivos revocados. Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. | 1 |
| SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, EXCESO_CREDITO_ADVERTIDO, EXCESO_CREDITO_AUTORIZADO_OFFLINE, EXCESO_CREDITO_DETECTADO_SYNC, LISTA_NO_VIGENTE, DESCUENTO_DIFIERE, CLIENTE_NO_HABILITADO, PERMISO_REVOCADO, JORNADA_LIBERADA, ANULACION_COMPRA_SIN_RECALCULO. | 1 |
| SYN-08 | Una observación queda PENDIENTE hasta que un usuario con `REVISAR_OBSERVACIONES` la resuelve con un comentario. Resolverla no modifica la operación; las correcciones se hacen con operaciones nuevas. | 1 |
| SYN-09 | El dispositivo no elimina una operación local hasta recibir ACEPTADO o ACEPTADO_CON_OBSERVACIONES. Un RECHAZADO queda visible en el dispositivo. | 1 |
| SYN-10 | Sin conexión, los permisos vigentes son los descargados al abrir la jornada. Si al sincronizar el usuario ya no tiene el permiso, la operación se acepta con PERMISO_REVOCADO. | 1 |
| SYN-11 | El bootstrap incluye: productos y presentaciones activos, clientes con saldo y datos de crédito, versiones de lista vigentes y las anteriores permitidas, reglas de descuento activas, stock de la ubicación tomada, permisos y topes del usuario, credenciales de autorización de supervisores y configuración de la organización. No incluye costos ni utilidades salvo que el usuario tenga `VER_COSTOS`. | 1 |

### 13.1 Importación inicial

| ID | Regla | Etapa |
| --- | --- | :-: |
| IMP-01 | Una importación es una sola operación por archivo: o se escriben todas las filas o ninguna (INV-01). Un archivo con errores se rechaza con el informe completo de errores por fila y columna (`IMPORTACION_CON_ERRORES`). | 1 |
| IMP-02 | Cada fila se valida y se escribe con las mismas reglas que el alta individual de su entidad y produce el mismo código de error ante el mismo dato inválido (TR-10). | 1 |
| IMP-03 | Una importación de maestros solo crea registros; una clave natural que ya existe es un error de duplicado y ningún registro existente se modifica. | 1 |
| IMP-04 | Las referencias entre entidades se escriben por clave natural (categoría y marca por nombre, alícuota por porcentaje, proveedor por nombre, producto por código, cliente por código o documento, ubicación por nombre); no se crean al vuelo. | 1 |
| IMP-05 | Los números de una planilla se leen como decimales exactos: coma decimal y sin separador de miles; un punto se rechaza (INV-03). Las cantidades son enteros (INV-04). | 1 |
| IMP-06 | El stock y los saldos iniciales importados se fechan con el momento de la importación (sin fecha de corte), como los cargados por pantalla (STK-10, CC-08). | 1 |

## 14. Seguridad y sesión (ADR-011)

| ID | Regla | Etapa |
| --- | --- | --- |
| SEG-01 | El inicio de sesión requiere conexión y credenciales. | 1 |
| SEG-02 | Un dispositivo se registra en su primer inicio de sesión y recibe un prefijo de numeración. Un usuario con `GESTIONAR_DISPOSITIVOS` puede revocarlo. | 1 |
| SEG-03 | Con conexión, cada usuario define un PIN para el dispositivo. Sin conexión, el PIN desbloquea la sesión local. | 1 |
| SEG-04 | Superados los intentos fallidos configurados, la sesión local se bloquea y requiere inicio de sesión con conexión. Las operaciones pendientes no se pierden. | 1 |
| SEG-05 | La autorización de un supervisor mediante PIN queda registrada con el supervisor como autorizador y se audita. | 1 |
| SEG-06 | El servidor valida los permisos en cada comando. Ocultar una acción en la interfaz no reemplaza esa validación. | 1 |
| SEG-07 | Un intento de acceder a un recurso de otra organización responde como recurso inexistente. | 1 |

## 15. Auditoría

| ID | Regla | Etapa |
| --- | --- | --- |
| AUD-01 | Se auditan: inicio de sesión, cambios de usuarios, roles, permisos y dispositivos; costos informados; publicación y anulación de versiones de lista; uso de lista no asignada o versión anterior; descuentos manuales y autorizaciones; autorizaciones de crédito; ventas, compras, cobranzas y pagos anulados; ajustes de stock; diferencias de rendición; liberación forzada de ubicaciones; cambios de límite y política de crédito; cambios de configuración; resolución de observaciones; comandos rechazados o en cuarentena. | 1 |
| AUD-02 | Cada registro guarda usuario, dispositivo, acción, entidad, identificador, valor anterior y nuevo cuando aplica, motivo, autorizador, `occurred_at`, `registered_at` y `operation_id`. | 1 |
| AUD-03 | La auditoría es de solo agregado: no se modifica ni se elimina. | 1 |

## 16. Facturación (módulo independiente)

| ID | Regla | Etapa |
| --- | --- | --- |
| FAC-01 | Facturar nunca vuelve a generar la deuda de la mercadería de una venta. | Facturación |
| FAC-02 | En ventas registradas sin IVA, con modalidad CLIENTE, la factura genera un único débito IVA_FACTURA vinculado a ella. El neto y la utilidad de las ventas no cambian. | Facturación |
| FAC-03 | Con modalidad ABSORBIDO, el saldo del cliente no cambia. La utilidad se reduce mediante un ajuste por IVA absorbido distribuido por línea, sin modificar los valores congelados de la venta. | Facturación |
| FAC-04 | La modalidad se resuelve en cascada organización → cliente → factura, se congela en la factura, y cambiarla a ABSORBIDO respecto del valor por defecto requiere `FACTURAR_ABSORBIENDO_IVA`. | Facturación |
| FAC-05 | Anular una factura revierte su efecto fiscal con movimientos inversos. | Facturación |
| FAC-06 | Una factura incluye ventas de un solo cliente, todas con la misma modalidad. | Facturación |
| FAC-07 | El importe facturado acumulado de una venta no supera su importe facturable. | Facturación |
| FAC-08 | El IVA de la factura se calcula por alícuota sobre la suma de netos de esa alícuota. En modalidad ABSORBIDO, el neto real y el IVA absorbido de cada alícuota se distribuyen entre las líneas en proporción a su neto, con el remanente de redondeo en la última línea. | Facturación |
| FAC-09 | Estados de facturación de una venta: NO_REQUIERE, PENDIENTE, PARCIAL, FACTURADA. El cambio entre NO_REQUIERE y PENDIENTE está permitido mientras no haya importe facturado y queda auditado. | 1 (estado), Facturación (transiciones de facturado) |
| FAC-10 | La facturación nunca escribe directamente en la cuenta corriente ni en la utilidad: solicita al núcleo el registro del efecto fiscal dentro de su transacción. | Facturación |

Ejemplo de FAC-02 y FAC-03 (ventas por $100.000 netos al 21%, costo $70.000):

| | CLIENTE | ABSORBIDO |
| --- | --- | --- |
| Neto facturado | $100.000,00 | $82.644,63 |
| IVA | $21.000,00 | $17.355,37 |
| Total factura | $121.000,00 | $100.000,00 |
| Cuenta corriente | Débito de $21.000,00 | Sin cambio |
| Utilidad | $30.000,00 | $12.644,63 |

## 17. Reportes

| ID | Regla | Etapa |
| --- | --- | --- |
| REP-01 | Los reportes se calculan desde las operaciones registradas. No existen cifras mantenidas manualmente. | 1 |
| REP-02 | Las ventas se asignan al período por su fecha de negocio (TR-04). Las ventas anuladas se excluyen de los totales de su período y se informan por separado. | 1 |
| REP-03 | Las cantidades se informan en cajas equivalentes, unidades base y detalle por presentación vendida. | 1 |
| REP-04 | Utilidad real = neto − costo congelado − IVA absorbido asignado. Solo la ven usuarios con `VER_UTILIDAD`. | 1 |
| REP-05 | Los reportes usan los valores congelados de cada operación, nunca precios ni costos actuales. | 1 |
| REP-06 | Utilidad por producto, cliente, proveedor y categoría; costo vendido por proveedor frente a deuda; comparativos; exportación. | 2 |

## 18. Máquinas de estado

Cada entidad tiene estados independientes entre sí. Los estados derivados se calculan y no se almacenan.

| Entidad | Máquina | Estados y transiciones | Etapa |
| --- | --- | --- | --- |
| Venta | Operativa | CONFIRMADA → ANULADA | 1 |
| Venta | Operativa (ampliación) | CONFIRMADA → DEVUELTA_PARCIAL → DEVUELTA_TOTAL | 2 |
| Venta | Facturación | NO_REQUIERE ↔ PENDIENTE → PARCIAL → FACTURADA | 1 / Facturación |
| Venta | Sincronización (en dispositivo) | LOCAL_PENDIENTE → ENVIANDO → ACEPTADA \| ACEPTADA_CON_OBSERVACIONES \| RECHAZADA | 1 |
| Compra | Operativa | CONFIRMADA → ANULADA | 1 |
| Cobranza / Pago | Operativa | CONFIRMADA → ANULADA | 1 |
| Versión de lista | Almacenada | BORRADOR → PUBLICADA → ANULADA (solo antes de su vigencia) | 1 |
| Versión de lista | Derivada | PROGRAMADA / VIGENTE / HISTÓRICA | 1 |
| Regla de descuento | Almacenada | BORRADOR → ACTIVA ↔ PAUSADA | 1 |
| Regla de descuento | Derivada | VENCIDA | 1 |
| Cliente | Almacenada | ACTIVO ↔ SUSPENDIDO; ACTIVO/SUSPENDIDO → INACTIVO; INACTIVO → ACTIVO solo sin operaciones | 1 |
| Jornada | Almacenada | ABIERTA → EN_RENDICION → CERRADA; ABIERTA/EN_RENDICION → LIBERADA | 1 |
| Dispositivo | Almacenada | ACTIVO → REVOCADO | 1 |
| Observación | Almacenada | PENDIENTE → RESUELTA | 1 |
| Factura | Almacenada | EMITIDA → ANULADA | Facturación |

**Cliente.** Un cliente nace `ACTIVO` (change 07, D7). `INACTIVO` admite una sola salida —volver a `ACTIVO`— y solo si el cliente no tiene operaciones (CLI-06, ADR-030); cuando existan ventas, cobranzas o compras, la transición queda fuera de la máquina. El cliente consumidor final nunca pasa a `INACTIVO` (CLI-03, ADR-029).

## 19. Permisos y roles

| Permiso | Alcance | ADM | GES | SUP | VEN | CON |
| --- | --- | :-: | :-: | :-: | :-: | :-: |
| ADMIN_USUARIOS | Usuarios, roles y permisos | ✓ | | | | |
| ADMIN_CONFIGURACION | Configuración de la organización (incluye crear, modificar y desactivar ubicaciones, STK-02) | ✓ | | | | |
| GESTIONAR_DISPOSITIVOS | Ver y revocar dispositivos | ✓ | | ✓ | | |
| IMPORTAR_DATOS | Importaciones y puesta en marcha (incluye registrar saldos iniciales, CC-08, y stock inicial, STK-10) | ✓ | | | | |
| GESTIONAR_CATALOGO | Productos, presentaciones, categorías | ✓ | ✓ | | | |
| GESTIONAR_CLIENTES | Alta y edición de clientes; ver su cuenta corriente | ✓ | ✓ | ✓ | | |
| GESTIONAR_CREDITO | Límite, política y tolerancia de clientes | ✓ | ✓ | | | |
| GESTIONAR_PROVEEDORES | Alta y edición de proveedores; ver su cuenta corriente | ✓ | ✓ | | | |
| VER_COSTOS | Ver costos (incluye el costo promedio de un producto y los costos del kardex y del stock) | ✓ | ✓ | | | |
| EDITAR_COSTOS | Registrar costos informados | ✓ | ✓ | | | |
| VER_UTILIDAD | Ver utilidad | ✓ | ✓ | | | ✓ |
| GESTIONAR_LISTAS | Reglas de margen, redondeo y borradores | ✓ | ✓ | | | |
| PUBLICAR_LISTAS | Publicar y anular versiones | ✓ | | | | |
| USAR_LISTA_ANTERIOR | Lista no asignada o versión anterior en venta | ✓ | | ✓ | | |
| GESTIONAR_DESCUENTOS | Reglas de descuento | ✓ | | | | |
| REGISTRAR_COMPRA | Registrar compras | ✓ | ✓ | | | |
| ANULAR_COMPRA | Anular compras | ✓ | ✓ | | | |
| REGISTRAR_PAGO_PROVEEDOR | Registrar pagos | ✓ | ✓ | | | |
| ANULAR_PAGO_PROVEEDOR | Anular pagos | ✓ | ✓ | | | |
| TRANSFERIR_STOCK | Transferencias; ver ubicaciones, stock por ubicación y kardex (sin costos) | ✓ | ✓ | ✓ | ✓ | |
| AJUSTAR_STOCK | Ajustes | ✓ | ✓ | | | |
| PERMITIR_STOCK_NEGATIVO | Operar con stock negativo online | ✓ | | | | |
| ABRIR_JORNADA | Abrir jornada y tomar ubicación | ✓ | | ✓ | ✓ | |
| RENDIR_JORNADA | Rendir y cerrar jornada | ✓ | ✓ | ✓ | | |
| LIBERAR_UBICACION | Liberación forzada | ✓ | | ✓ | | |
| VENDER | Confirmar ventas | ✓ | | ✓ | ✓ | |
| ANULAR_VENTA | Anular ventas | ✓ | ✓ | ✓ | | |
| DESCUENTO_MANUAL | Descuento manual hasta el tope del rol | ✓ (sin tope) | | ✓ | ✓ | |
| AUTORIZAR_DESCUENTO | Superar tope de descuento | ✓ | | ✓ | | |
| SUPERAR_CREDITO | Vender con exceso de crédito | ✓ | | ✓ | | |
| VENDER_CLIENTE_SUSPENDIDO | Vender a suspendidos | ✓ | | ✓ | | |
| REGISTRAR_COBRANZA | Registrar cobranzas | ✓ | ✓ | ✓ | ✓ | |
| ANULAR_COBRANZA | Anular cobranzas | ✓ | ✓ | ✓ | | |
| REVISAR_OBSERVACIONES | Resolver observaciones | ✓ | ✓ | ✓ | | |
| VER_REPORTES | Reportes | ✓ | ✓ | ✓ | | ✓ |
| VER_AUDITORIA | Consultar auditoría | ✓ | | | | ✓ |
| FACTURAR | Emitir facturas | ✓ | ✓ | | | |
| FACTURAR_ABSORBIENDO_IVA | Emitir con IVA absorbido | ✓ | | | | |
| ANULAR_FACTURA | Anular facturas | ✓ | ✓ | | | |

Roles: ADM = Administrador, GES = Administración, SUP = Supervisor comercial, VEN = Vendedor/Repartidor, CON = Consulta/Dirección. Los roles son plantillas: la organización puede modificar su composición y los topes de descuento. El vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad.

## 20. Invariantes

Deben cumplirse siempre y estar cubiertos por pruebas automatizadas.

| ID | Invariante | Origen |
| --- | --- | --- |
| INV-01 | Una operación de negocio se registra completa o no se registra. | V-01 |
| INV-02 | Todo dato de negocio pertenece a exactamente una organización. | DB-01 |
| INV-03 | Ningún importe, costo o porcentaje se representa con punto flotante binario. | DB-02 |
| INV-04 | Las cantidades de stock en unidad base son enteras. | DB-03 |
| INV-05 | Ninguna venta, compra, cobranza, pago, movimiento ni registro de auditoría confirmado se borra. | DB-04 |
| INV-06 | Un `operation_id` es único por organización, y reprocesar un comando no duplica efectos. | DB-05 |
| INV-07 | Toda venta y toda compra tiene al menos una línea. | DB-06 |
| INV-08 | La suma de medios de una cobranza o pago es igual a su importe. | DB-07 |
| INV-09 | El importe facturado de una venta no supera su importe facturable. | DB-08 |
| INV-10 | Los valores congelados de una venta (lista, precio, unidades, descuentos, costo, evaluación de crédito) no cambian después de confirmarla. | DB-09, DB-10 |
| INV-11 | Una versión de lista publicada no cambia. | Nuevo |
| INV-12 | El stock de cada producto y ubicación es igual a la suma de sus movimientos. | Nuevo |
| INV-13 | El saldo de cada cuenta corriente es igual a la suma de sus movimientos. | Nuevo |
| INV-14 | Total de una venta = suma de netos de sus líneas + suma de IVA de sus líneas. | Nuevo |
| INV-15 | Una transferencia no modifica el stock total del producto en la organización. | Nuevo |
| INV-16 | Una ubicación que requiere toma tiene como máximo una jornada no cerrada. | Nuevo |
| INV-17 | Una venta o cobranza offline nunca se rechaza por reglas de negocio. | Nuevo |
| INV-18 | Las unidades de una presentación usada en operaciones no cambian. | Nuevo |
| INV-19 | Anular una venta deja el stock y el saldo del cliente como si no se hubiera registrado, sin borrar ningún registro. | Nuevo |
| INV-20 | Facturar nunca vuelve a generar la deuda de la mercadería. | FAC-01 |
| INV-21 | Ningún usuario obtiene ni modifica datos de otra organización. | T-022 |

## 21. Efectos de cada evento

| Evento | Stock | Costo promedio | Cta. cliente | Cta. proveedor | Utilidad | Auditoría |
| --- | --- | --- | --- | --- | --- | --- |
| Stock inicial | + / − (corrección, STK-10) | Recalcula (+); no cambia (−) | — | — | — | Sí |
| Saldo inicial | — | — | + / − | + / − | — | Sí |
| Costo informado | — | — | — | — | — | Sí |
| Versión publicada | — | — | — | — | — | Sí |
| Compra | + | Recalcula | — | + (y − si contado) | — | Sí |
| Anulación de compra | − | Recalcula o mantiene | — | − | — | Sí |
| Pago a proveedor | — | — | — | − | — | Sí |
| Transferencia | − origen / + destino | — | — | — | — | Sí |
| Ajuste de stock | + / − | — | — | — | — | Sí |
| Venta | − | — | + total (y − si cobra) | — | Congela | Sí |
| Anulación de venta | + | Recalcula | − total | — | Excluye | Sí |
| Cobranza | — | — | − | — | — | Sí |
| Diferencia de rendición | + / − | — | — | — | — | Sí |
| Factura modalidad CLIENTE | — | — | + IVA | — | — | Sí |
| Factura modalidad ABSORBIDO | — | — | — | — | − IVA absorbido | Sí |

## 22. Trazabilidad con la documentación original

| Original | Estado en este documento |
| --- | --- |
| Estados de venta "Parcialmente cobrada / Cobrada" (doc 00 §14) | Derogado: incompatible con cuenta corriente general. Reaparece solo con imputación por operación (etapa 4). |
| "Cuenta corriente" como medio de pago (doc 00 §3) | Derogado: ver glosario y CC-05. |
| Débito solo por saldo no cubierto (doc 02 §10) | Reemplazado por CC-05. |
| Saldo en PROVEEDOR y saldo por movimiento (ERD) | Derogado por CC-04. |
| FIFO como estrategia inicial (doc 02 §7, T-019) | Reemplazado por promedio ponderado (CST-10 a CST-15). |
| Estado "Rechazada" para ventas offline (doc 00 §14) | Restringido por SYN-05 y SYN-06. |
| "Facturar no modifica saldo ni utilidad" (doc 00 §15, doc 02 §11) | Reemplazado por FAC-01 a FAC-05. |
| Precio por presentación (ERD PRECIO_ITEM) | Reemplazado por PRC-10 y PRC-22. |
| V-01, DB-01 a DB-10 | Consolidados en INV-01 a INV-10. |
