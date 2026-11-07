## Purpose

Define el reporte de ventas del período: totales, desgloses por día, vendedor y producto, cantidades en cajas equivalentes, unidades base y presentaciones, las anuladas aparte y la utilidad real solo para quien puede verla (REP-02, REP-03, REP-04, REP-05).

## ADDED Requirements

### Requirement: El reporte de ventas suma las ventas confirmadas del período con sus valores congelados

`GET /api/v1/reportes/ventas` (con `VER_REPORTES`, filtro opcional `vendedor_id`) DEBE devolver el **resumen** (cantidad de ventas, cajas equivalentes, unidades base, bruto, descuentos, neto, IVA y total), y los mismos importes **por día** (fecha de negocio, **la más reciente primero**, paginado de a 50 con `pagina_por_dia`) y **por vendedor** (usuario de la venta, por neto descendente, sin paginar), solo con las ventas `CONFIRMADA` cuyo `occurred_at` cae en el período. DEBE usar únicamente los valores congelados de cada venta y línea, nunca precios ni costos actuales. El resumen y «Por vendedor» DEBEN ser los de todo el período, sin importar la página pedida. Los importes DEBEN viajar como string con 2 decimales y el total DEBE ser neto más IVA (REP-01, REP-02, REP-05, INV-03, INV-14; `design.md` D3, D14).

#### Scenario: Totales del período
- **GIVEN** dos ventas confirmadas del período de `vendedor`, con netos `"1000.00"` y `"500.00"` y IVA cero (modo A)
- **WHEN** se pide el reporte del período
- **THEN** el resumen informa 2 ventas, neto `"1500.00"`, IVA `"0.00"` y total `"1500.00"`
- **AND** el desglose por vendedor tiene una fila de `vendedor` con los mismos importes
- **Regla:** REP-01; INV-14

#### Scenario: Valores congelados
- **GIVEN** una venta confirmada del período
- **WHEN** después se publica una versión nueva de su lista con otros precios y se registra una compra que cambia el costo promedio
- **THEN** el reporte del período informa los mismos importes, costo vendido y utilidad que antes
- **Regla:** REP-05; INV-10

#### Scenario: Concilia con las ventas registradas
- **GIVEN** las ventas de un período
- **WHEN** se compara el reporte con la suma en SQL de `venta.total` de las `CONFIRMADA` del período y con el listado de ventas filtrado por `CONFIRMADA` y las mismas fechas
- **THEN** la cantidad y el total coinciden
- **Regla:** REP-01; `00` §9 criterio 11

#### Scenario: Por día, el más reciente primero
- **GIVEN** ventas confirmadas del 2026-11-02, del 2026-11-05 y del 2026-11-03
- **WHEN** se pide el reporte del período
- **THEN** «Por día» trae el 2026-11-05, el 2026-11-03 y el 2026-11-02, en ese orden
- **Regla:** TR-04; `design.md` D14

#### Scenario: Filtro por vendedor
- **GIVEN** ventas de `vendedor` y de `vendedor2` en el período
- **WHEN** se filtra por `vendedor2`
- **THEN** todos los totales y desgloses incluyen solo las de `vendedor2`
- **Regla:** REP-01

#### Scenario: Período sin ventas
- **WHEN** se pide un período sin ventas confirmadas
- **THEN** el resumen trae cero en cantidades e importes y los desgloses vienen vacíos
- **Regla:** REP-01

### Requirement: Las ventas anuladas se excluyen de su período y se informan aparte

Una venta `ANULADA` NO DEBE entrar en ningún total ni desglose del período de su `occurred_at`, aunque la anulación sea posterior a ese período. La respuesta DEBE traer la sección de anuladas del período con su cantidad y su total (de todo el período) y la lista, paginada de a 50 con `pagina_anuladas` y con la venta más reciente primero (fecha de la venta descendente, desempate por el identificador de la venta), de cada una con número, fecha de la venta, cliente, vendedor, total, momento de la anulación, motivo y si se devolvió el dinero (REP-02; VTA-22; `design.md` D2, D14).

#### Scenario: Anulada dentro del período
- **GIVEN** tres ventas del período, una de ellas anulada con el motivo «Error de carga»
- **WHEN** se pide el reporte
- **THEN** el resumen cuenta 2 ventas
- **AND** la sección de anuladas informa 1 venta con su total, el motivo y el momento de la anulación
- **Regla:** REP-02

#### Scenario: Anulada después del período
- **GIVEN** una venta del 2026-10-30 anulada el 2026-11-02
- **WHEN** se pide el reporte de octubre
- **THEN** la venta no suma en octubre y aparece en sus anuladas con «Anulada el» 02/11/2026
- **AND** no aparece en el reporte de noviembre
- **Regla:** REP-02

#### Scenario: Anuladas en páginas, la más reciente primero
- **GIVEN** 55 ventas anuladas del período
- **WHEN** se pide el reporte con `pagina_anuladas=2`
- **THEN** la sección informa 55 anuladas con el total de las 55 y trae las 5 más antiguas por fecha de la venta
- **AND** la página 1 empieza por la venta más reciente
- **Regla:** REP-02; `design.md` D14

### Requirement: Las cantidades se informan en cajas equivalentes, unidades base y por presentación

El desglose **por producto** (por neto descendente, paginado de a 50 con `pagina_por_producto`) DEBE informar, por producto vendido, código, nombre, cajas equivalentes, unidades base y neto, y el detalle por presentación vendida (nombre, unidades de la presentación congeladas, cantidad en la presentación y unidades base). Las cajas equivalentes de cada línea DEBEN ser su `cantidad_base` dividida por sus `unidades_referencia` congeladas, sumadas exactas en la base y redondeadas una sola vez a 2 decimales «mitad hacia arriba» por cifra informada, como string. Las unidades base DEBEN ser enteras. El desglose por producto NO DEBE traer costo ni utilidad (REP-06 es de la etapa 2) (REP-03, REP-05, TR-03; `design.md` D3, D4, D14).

#### Scenario: Cajas equivalentes del glosario
- **GIVEN** un vino con presentación de referencia caja x6 y una venta del período de 15 botellas sueltas
- **WHEN** se pide el reporte
- **THEN** el producto informa `"2.50"` cajas equivalentes y 15 unidades base
- **Regla:** REP-03; glosario (cajas equivalentes)

#### Scenario: Detalle por presentación
- **GIVEN** ventas del período del mismo vino: 2 cajas x6 y 3 botellas
- **WHEN** se pide el reporte
- **THEN** el producto informa 15 unidades base y `"2.50"` cajas equivalentes, con dos filas de detalle: caja x6 (6 unidades) con cantidad 2 y 12 unidades base, y botella (1 unidad) con cantidad 3 y 3 unidades base
- **Regla:** REP-03; VTA-02

#### Scenario: La referencia cambió entre ventas
- **GIVEN** una venta de 6 botellas cuando la referencia era caja x6 y otra de 6 botellas después de cambiarla a caja x12
- **WHEN** se pide el reporte que incluye las dos
- **THEN** el producto informa `"1.50"` cajas equivalentes (1 + 0,5), con las referencias congeladas de cada línea
- **Regla:** REP-05; PRC-23

#### Scenario: Redondeo una sola vez
- **GIVEN** tres ventas de 1 botella de un producto con referencia caja x6
- **WHEN** se pide el reporte
- **THEN** el producto informa `"0.50"` cajas equivalentes (3/6 exacto), no la suma de tres redondeos (`"0.51"`)
- **Regla:** TR-03

### Requirement: Costo vendido y utilidad solo con `VER_UTILIDAD`, sin las líneas sin costo

Con `VER_UTILIDAD`, el resumen, cada día y cada vendedor DEBEN traer costo vendido (suma de `costo_total` de las líneas con costo) y utilidad (`importe_neto − costo_total − IVA absorbido asignado`, sumada solo sobre las líneas con costo; el IVA absorbido es cero mientras no exista el módulo de facturación) y, aparte, la cantidad de líneas sin costo y su neto. Sin `VER_UTILIDAD`, esos campos DEBEN venir en `null` y la respuesta DEBE indicar `ve_utilidad: false`. No se informa margen porcentual (REP-04, VTA-05; ADR-054; `design.md` D5).

#### Scenario: Utilidad con permiso
- **GIVEN** una venta del período con dos líneas: neto `"1000.00"` con costo `"700.00"` y neto `"200.00"` con costo `"150.00"`
- **WHEN** `consulta` (con `VER_UTILIDAD`) pide el reporte
- **THEN** el resumen informa costo vendido `"850.00"` y utilidad `"350.00"`
- **Regla:** REP-04

#### Scenario: Sin permiso de utilidad
- **WHEN** `sup01` (con `VER_REPORTES`, sin `VER_UTILIDAD`) pide el mismo reporte
- **THEN** recibe cantidades e importes, con costo vendido, utilidad y líneas sin costo en `null` y `ve_utilidad: false`
- **AND** la pantalla no muestra las columnas «Costo vendido» ni «Utilidad»
- **Regla:** REP-04; `01` §19

#### Scenario: Línea vendida sin costo
- **GIVEN** una venta sin conexión del período con una línea de neto `"300.00"` sin costo (producto sin promedio) y otra de neto `"1000.00"` con costo `"700.00"`
- **WHEN** `consulta` pide el reporte
- **THEN** el costo vendido es `"700.00"`, la utilidad `"300.00"` y se informa 1 línea sin costo con neto `"300.00"`
- **AND** el neto del resumen sigue siendo `"1300.00"`
- **Regla:** REP-04; VTA-05; ADR-054

#### Scenario: Las anuladas no suman utilidad
- **GIVEN** una venta anulada del período con costo
- **WHEN** se pide el reporte con `VER_UTILIDAD`
- **THEN** su costo y su utilidad no entran en ningún total
- **Regla:** REP-02; REP-04

### Requirement: La pestaña «Ventas»

La pestaña «Ventas» DEBE mostrar el resumen, las tablas por día, por vendedor y por producto (con el detalle por presentación desplegable), la nota «Líneas sin costo…» cuando hay líneas sin costo y la sección «Ventas anuladas del período», con la navegación entre páginas de «Por día», «Por producto» y las anuladas (`reportes/area-de-reportes`), con importes formateados desde su string sin convertirlos a número para calcular, y los textos vacíos «Sin ventas en el período.» y «Sin ventas anuladas en el período.» (`design.md` D11, D12).

#### Scenario: Con utilidad y líneas sin costo
- **GIVEN** `consulta` y un período con ventas, una línea sin costo y una anulada
- **WHEN** abre «Ventas»
- **THEN** ve «Costo vendido» y «Utilidad», la nota de líneas sin costo y la anulada en su sección
- **Regla:** REP-02; REP-04

#### Scenario: Período vacío
- **WHEN** elige un período sin ventas
- **THEN** ve «Sin ventas en el período.» y «Sin ventas anuladas en el período.»
- **Regla:** REP-01
