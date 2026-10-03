# ADR-043 — Deuda por total de factura, pago de contado, anulación de compras, errores nuevos y permisos de lectura de apoyo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-02 |
| Referenciado en | `openspec/changes/11-compras-y-deuda-proveedor/design.md` D1, D2, D3, D4, D5, D6, D7, D11, D13, D14, D16, D17 y D18 y `specs/proveedores/compras`, `specs/proveedores/anulacion-de-compras`, `specs/proveedores/administracion-de-compras`; `01-dominio.md` CMP-01 a CMP-08, CC-05; `02-arquitectura.md` §5.3 y §6.5; `03-modelo-de-datos.md` §4 y §6; ADR-012 (bus de comandos), ADR-034 y ADR-035 (cuentas corrientes); ADR-044 |

**Decisiones D1 a D7, D11, D13, D14 y D16 (opción A en cada una) aprobadas por el usuario el 2026-10-02; D17 y D18 aprobadas el 2026-10-02 durante el apply. Texto del ADR pendiente de aprobación; estado *Propuesto*.**

## Contexto

`01` CMP-02 define el total neto de una compra y CMP-03 manda registrar la compra en la cuenta del proveedor y el pago si es de contado, pero nada dice qué importe es la deuda (con o sin IVA), cómo se registra un pago cuyo módulo (`pagos-a-proveedores`) es del change 12, qué pasa con ese pago al anular, ni qué permisos y errores corresponden. `03` §6 no vincula un pago con su compra ni congela la alícuota de la línea.

## Decisión

1. **La deuda es el total de factura informado (D1).** `compra.total_factura numeric(14,2) > 0` es el importe del comprobante del proveedor. La pantalla lo sugiere como `total neto + IVA de cada línea` (alícuota del producto) y el usuario lo corrige (percepciones, redondeos, proveedor sin IVA discriminado). La cuenta del proveedor y el pago de contado usan `total_factura`; stock, costo base y promedio usan el neto (CST-02, CST-04). Un total con más de dos decimales se rechaza (`IMPORTE_INVALIDO`).
2. **Pago de contado (D2).** El change 11 crea `pago_proveedor` y `pago_proveedor_medio` (`03` §6). Una compra de contado genera, en la misma transacción, un pago `origen = COMPRA` con `compra_id` (único si no es nulo), por `total_factura`, con uno o más medios activos de la organización que suman exactamente el importe (INV-08, `MEDIOS_NO_SUMAN_IMPORTE`) y con referencia donde el medio la exige (`REFERENCIA_OBLIGATORIA`). **La `fecha` del pago es la `fecha` de la compra.** Una compra a crédito con medios, o de contado sin ellos, se rechaza con `CONDICION_INVALIDA`. El change 12 agrega el pago independiente y su anulación sobre las mismas tablas.
3. **Anulación del pago (D3).** `COMPRA_ANULAR` lleva `devuelve_pago`, obligatorio en una compra de contado y prohibido en una de crédito: **faltante en contado o presente en crédito es `CONDICION_INVALIDA`**. Con `true` el pago pasa a `ANULADO` y se registra `ANULACION_PAGO` (el saldo vuelve a como estaba); con `false` el pago se mantiene y queda saldo a favor nuestro, que se compensa con la próxima compra.
4. **Solo productos del proveedor (D4).** Cada línea debe ser de un producto cuyo proveedor es el de la compra (`PROVEEDOR_NO_CORRESPONDE`), como los costos informados (CAT-06).
5. **Cantidades y valores (D5).** `cantidad > 0` con hasta tres decimales y `cantidad × unidades` entero (`CANTIDAD_INVALIDA`, INV-04); `valor > 0` con dos decimales (`VALOR_INVALIDO`); bonificación en `[0, 1)` (`BONIFICACION_INVALIDA`); el mismo producto puede repetirse y se aplica en el orden recibido; hasta 200 líneas (`LINEAS_INVALIDAS`); sin líneas, `COMPRA_SIN_LINEAS` (INV-07).
6. **Fecha y momentos (D6).** `fecha` es la del comprobante, obligatoria y no posterior a la fecha de negocio de hoy (`FECHA_INVALIDA`). Los movimientos de stock y de cuenta usan el `occurred_at` del comando.
7. **Oferta de costo informado (D7).** La respuesta de `COMPRA_CONFIRMAR` lista las líneas cuyo costo base difiere del costo informado vigente a la fecha de la compra o que no lo tienen (`diferencias_de_costo`); nunca registra nada por sí misma (CMP-04). La pantalla, con `EDITAR_COSTOS`, envía `COSTO_INFORMAR` con `vigencia_desde` = fecha de la compra.
8. **Maestros inactivos (D11).** Se puede anular aunque el proveedor, el producto o la presentación se hayan desactivado; una ubicación inactiva bloquea la anulación (`UBICACION_INACTIVA`, también al confirmar).
9. **Número de comprobante (D13).** Opcional, informativo, buscable, sin unicidad. **Ubicación (D16):** cualquier ubicación activa, incluidos vehículos.
10. **Permisos (D14).** `COMPRA_CONFIRMAR`: `REGISTRAR_COMPRA` (también de contado). `COMPRA_ANULAR`: `ANULAR_COMPRA`, más `PERMITIR_STOCK_NEGATIVO` si deja stock negativo (CMP-07). Leer compras: `REGISTRAR_COMPRA` **o** `ANULAR_COMPRA`. Medios de pago y motivos: cualquier usuario autenticado. Sin permisos nuevos.
11. **Lecturas de apoyo del formulario (D17 y D18).** Se abre **solo la lectura** a `REGISTRAR_COMPRA`, conservando el permiso que ya la abría: `GET /catalogo/productos` y su detalle (`GESTIONAR_CATALOGO` o `REGISTRAR_COMPRA`), `GET /configuracion/alicuotas`, `GET /proveedores/opciones` y `GET /stock/ubicaciones` (esta última, `TRANSFERIR_STOCK` o `REGISTRAR_COMPRA`). Ninguna escritura cambia. Desvíos aceptados de la interfaz: fecha por defecto = fecha local del navegador (`/yo` no trae la zona de la organización), cantidades "5 cajas + 1 un." con el formateador de stock, condición por defecto "A crédito".
12. **Mecanismo del bus.** Un handler puede devolver, además del resultado, observaciones de negocio (`ResultadoHandlerConObservaciones` con `ObservacionProducida`, definida en `app/commands/observaciones.py` para que el `commands.py` de un módulo de negocio no importe `sync`); el bus las registra (SYN-04, SYN-07) y el estado del comando pasa a `ACEPTADO_CON_OBSERVACIONES`. `COMPRA_ANULAR` emite `ANULACION_COMPRA_SIN_RECALCULO` (ADR-044) y `STOCK_NEGATIVO`. En `app/core/autenticacion.py`, `requiere_algun_permiso(*códigos)` exige cualquiera de los permisos (el marcador `permiso_requerido` los une con ` o `, así los ratchets de permiso por ruta lo reconocen) y `requiere_sesion` exige solo una sesión habilitada, sin permiso (medios de pago y motivos).
13. **Códigos de error nuevos** (todos `DomainError` con código estable): `CANTIDAD_INVALIDA`, `COMPRA_SIN_LINEAS`, `LINEAS_INVALIDAS`, `IMPORTE_INVALIDO`, `CONDICION_INVALIDA`, `MEDIOS_NO_SUMAN_IMPORTE`, `REFERENCIA_OBLIGATORIA`, `FECHA_INVALIDA`, `MEDIO_PAGO_INACTIVO`, `MOTIVO_INVALIDO`, `CURSOR_INVALIDO` y `RANGO_DE_FECHAS_INVALIDO` (422); `UBICACION_INACTIVA` y `COMPRA_YA_ANULADA` (409). Un error de línea indica la línea en el Problem Details. Un recurso de otra organización responde 404 (INV-21).
14. **Modelo de datos (D12).** `compra` agrega `total_factura`, `numero_comprobante`, `observacion` y la coherencia "anulada ⇔ motivo, momento y usuario"; `compra_linea` agrega `orden` y `alicuota_aplicada numeric(9,6)` (congelada); `pago_proveedor` agrega `origen`, `compra_id`, `anulado_en`, `anulado_por_id` y `anulacion_motivo_id` nulable (el change 12 decide su motivo). `app_runtime` tiene `SELECT, INSERT, UPDATE` solo sobre el estado y la anulación de `compra` y `pago_proveedor`, `SELECT, INSERT` sobre líneas y medios y nunca `DELETE` (INV-05). Motivos de anulación de compra sembrados: "Error de carga", "Devolución al proveedor" y "Otro" (D8).
15. **Dependencias y bloqueos.** `proveedores -> catalogo, stock, costeo, cuentas_corrientes, configuracion`, solo por `service.py`; contrato de import-linter actualizado. Confirmar bloquea en este orden: proveedor `FOR SHARE`, `saldo_cuenta` del proveedor, `stock.registrar_movimientos` (ADR-039); anular toma antes la compra `FOR UPDATE` (`COMPRA_YA_ANULADA` con la fila tomada).

## Consecuencias

- La cuenta del proveedor refleja lo que dice la factura; stock y promedio siguen netos. Un proveedor que no discrimina IVA o una factura con percepciones se cargan sin trucos.
- El change 12 hereda las tablas de pago, la regla de que una compra tiene a lo sumo un pago de origen `COMPRA` y la pregunta abierta de si ese pago puede anularse por separado de la compra.
- Un pago no devuelto deja saldo a favor nuestro (saldo negativo en la cuenta del proveedor), visible como "Saldo a nuestro favor".
- Quien necesite devolver observaciones desde un handler usa el mecanismo del bus, no escribe en `observacion` por su cuenta.
- La interfaz de compras funciona con un usuario que solo tiene `REGISTRAR_COMPRA`, sin darle acceso de escritura a catálogo, proveedores ni stock.

## Alternativas consideradas

- **Deuda = neto más IVA calculado (B de D1):** descartada: no sirve si el proveedor no discrimina IVA ni con percepciones.
- **Deuda = total neto (C de D1):** descartada: al pagar la factura real queda un saldo a favor falso.
- **Un solo medio de pago o contado solo desde el change 12 (B y C de D2):** descartadas: CMP-03 y CC-05 piden el pago en el 11 y el pago mixto es habitual.
- **Anular siempre o nunca el pago (B y C de D3):** descartadas: ambas fuerzan un resultado contable que depende de si el proveedor devolvió el dinero.
- **Dar `GESTIONAR_CATALOGO`, `GESTIONAR_PROVEEDORES` y `TRANSFERIR_STOCK` a quien compra:** descartada: abre escrituras que la compra no necesita (D17, D18).
- **Un endpoint propio con los datos del formulario:** descartada: duplica listados que ya existen y sus filtros.
